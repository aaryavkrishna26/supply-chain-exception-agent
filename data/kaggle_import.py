"""
Kaggle data import for RELAY.

Loads two public Kaggle datasets into Supabase in place of the old synthetic seed:

  * SCMS Delivery History — divyeshardeshana/supply-chain-shipment-pricing-data
      USAID Supply Chain Management System line-item deliveries, 2006-2015.
      -> suppliers (vendors), products, customers (destination countries),
         purchase orders (direct-drop), customer orders (sales orders from the
         regional distribution centre), shipments (ASN / DN), carriers (modes)

  * Inventory Management E-Grocery — mustofaahmad/inventory-management-grocery-industry
      1,000 SKU stock positions across 5 Indonesian distribution centres.
      -> warehouses, products, suppliers, inventory

Timeline replay
  SCMS is a closed history: every line was eventually delivered. To give the
  workspace a live operational state, the importer picks an as-of date inside
  the history and treats it as "now". Lines issued before it and delivered after
  it are in flight — overdue ones become DELAYED — lines issued after it are left
  out as future, and every date is shifted so the as-of date lands on today.
  Relative timings and recorded lateness are unchanged. Nothing about a line's
  eventual delivery leaks into its live record.

Every value the datasets do not carry is either left NULL or derived by a named
rule below; data/DATA_SOURCES.md lists them all.

Usage
  python -m data.kaggle_import --dry-run          # download, transform, validate — no writes
  python -m data.kaggle_import                    # replace Supabase data, then run detection
  python -m data.kaggle_import --as-of 2015-05-31 # pin the replay point
"""

from __future__ import annotations

import argparse
import logging
import math
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger("kaggle_import")

SCMS_REF = "divyeshardeshana/supply-chain-shipment-pricing-data"
SCMS_FILE = "SCMS_Delivery_History_Dataset.csv"
GROCERY_REF = "mustofaahmad/inventory-management-grocery-industry"
GROCERY_FILE = "Inventory Management E-Grocery - InventoryData.csv"

SCHEMA_FILE = Path(__file__).resolve().parents[1] / "database" / "schema.sql"

# Parent tables first, so every foreign key resolves during the load.
LOAD_ORDER = [
    "customers",
    "suppliers",
    "products",
    "warehouses",
    "inventory",
    "carriers",
    "routes",
    "orders",
    "order_items",
    "purchase_orders",
    "purchase_order_items",
    "shipments",
    "data_sources",
]

# ---------------------------------------------------------------------------
# Derivation rules — every value the datasets do not carry directly.
# Documented in data/DATA_SOURCES.md; change them here and nowhere else.
# ---------------------------------------------------------------------------
GROCERY_ASSUMED_UTILISATION = 0.80  # grocery supplier capacity is not recorded
RELIABILITY_PRIOR_WEIGHT = 10       # shrink small-sample on-time rates toward the network mean
IN_TRANSIT_WINDOW_DAYS = 21         # undelivered and due within this window -> IN_TRANSIT, else CREATED
NEW_PO_WINDOW_DAYS = 7              # open PO issued within this window -> ISSUED, else CONFIRMED
MAX_FUTURE_SHARE = 0.05             # the as-of auto-pick may leave out at most 5% of lines as future
AS_OF_SEARCH_DAYS = 730             # the auto-pick searches the final two years of the history

TIER_BY_RANK = [(5, "VIP"), (10, "ENTERPRISE"), (20, "PRIORITY")]
SLA_BY_TIER = {"VIP": 24, "ENTERPRISE": 36, "PRIORITY": 48, "STANDARD": 72}
CRITICALITY_ORDER = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
ABC_TO_CRITICALITY = {"A": "HIGH", "B": "MEDIUM", "C": "LOW"}

PRODUCT_GROUPS = {
    "ARV": "Antiretrovirals",
    "HRDT": "HIV rapid diagnostic tests",
    "ANTM": "Antimalarials",
    "ACT": "Artemisinin combination therapy",
    "MRDT": "Malaria rapid diagnostic tests",
}

# Shipment mode -> (carrier id, display name, schema mode). SCMS records the mode,
# not the forwarder, so carriers are modes.
SHIPMENT_MODES = {
    "Air": ("SCMS-AIR", "Air freight", "AIR"),
    "Air Charter": ("SCMS-AIRCHARTER", "Air charter", "AIR"),
    "Truck": ("SCMS-TRUCK", "Road freight (truck)", "ROAD"),
    "Ocean": ("SCMS-OCEAN", "Ocean freight", "OCEAN"),
}

# Province of each grocery distribution-centre city (geography, not dataset content).
INDONESIA_PROVINCES = {
    "Bandung": "West Java",
    "Jakarta": "DKI Jakarta",
    "Surabaya": "East Java",
    "Medan": "North Sumatra",
    "Denpasar": "Bali",
}

RDC_ID = "SCMS-RDC"
RDC_NAME = "SCMS Regional Distribution Centre"

Tables = Dict[str, List[Dict[str, Any]]]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _slug(text: Any, limit: int = 32) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", str(text).upper()).strip("-")[:limit]


def _eu_number(value: Any) -> float:
    """Parse the grocery export's European number format: '$2.084,25', '28,57', '70,68%', '1.377'."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return float("nan")
    text = str(value).replace("$", "").replace("%", "").strip()
    if not text:
        return float("nan")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", text):  # '1.377' is a thousands separator
        text = text.replace(".", "")
    return float(text)


def _mode(series: pd.Series) -> Any:
    values = series.dropna()
    return values.value_counts().index[0] if len(values) else None


def _float(value: Any, digits: int = 2) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else round(number, digits)


def _stamp(value: Any, shift: timedelta) -> Optional[datetime]:
    """Shift a dataset date onto the live timeline, as a UTC midday timestamp."""
    if value is None or pd.isna(value):
        return None
    shifted = (pd.Timestamp(value) + shift).to_pydatetime()
    return shifted.replace(hour=12, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)


def _split_site(site: Any) -> Tuple[str, Optional[str]]:
    """'Ranbaxy, Paonta Shahib, India' -> ('Ranbaxy, Paonta Shahib', 'India')."""
    parts = [p.strip() for p in str(site or "").split(",") if p.strip()]
    if len(parts) >= 2 and re.fullmatch(r"[A-Za-z .'\-]{3,40}", parts[-1]):
        return ", ".join(parts[:-1])[:100], parts[-1][:100]
    return (str(site).strip() or "Not recorded")[:100], None


def download(ref: str, filename: str) -> Path:
    """Fetch a Kaggle dataset through kagglehub's cache and return the CSV path."""
    import kagglehub

    root = Path(kagglehub.dataset_download(ref))
    matches = [root / filename] if (root / filename).exists() else list(root.rglob(filename))
    if not matches:
        raise FileNotFoundError(f"{filename} not found in Kaggle dataset {ref} ({root})")
    return matches[0]


# ---------------------------------------------------------------------------
# SCMS — procurement, customer fulfilment and freight
# ---------------------------------------------------------------------------

def load_scms_frame(path: Path) -> pd.DataFrame:
    raw = pd.read_csv(path, dtype=str, encoding="utf-8-sig")  # UTF-8 with a byte-order mark
    df = pd.DataFrame(
        {
            "line_id": raw["ID"].str.strip(),
            "project": raw["Project Code"],
            "ref": raw["PO / SO #"].str.strip(),
            "asn": raw["ASN/DN #"].str.strip(),
            "country": raw["Country"].str.strip(),
            "fulfil": raw["Fulfill Via"],
            "inco": raw["Vendor INCO Term"],
            "mode": raw["Shipment Mode"],
            "group": raw["Product Group"],
            "sub": raw["Sub Classification"],
            "vendor": raw["Vendor"].str.strip(),
            "item": raw["Item Description"].str.strip(),
            "site": raw["Manufacturing Site"],
            "freight_raw": raw["Freight Cost (USD)"],
        }
    )
    df["sched"] = pd.to_datetime(raw["Scheduled Delivery Date"], format="%d-%b-%y")
    df["delivered"] = pd.to_datetime(raw["Delivered to Client Date"], format="%d-%b-%y")
    df["sent"] = pd.to_datetime(raw["PO Sent to Vendor Date"], format="%m/%d/%y", errors="coerce")
    df["qty"] = pd.to_numeric(raw["Line Item Quantity"])
    df["value"] = pd.to_numeric(raw["Line Item Value"])
    df["pack_price"] = pd.to_numeric(raw["Pack Price"])
    df["freight"] = pd.to_numeric(raw["Freight Cost (USD)"], errors="coerce")
    df["weight"] = pd.to_numeric(raw["Weight (Kilograms)"], errors="coerce")
    df["is_so"] = df["ref"].str.startswith("SO")

    # Issue date: recorded for ~45% of lines. Otherwise scheduled date minus the
    # vendor's median recorded lead time (network median when the vendor has none).
    df["lead"] = (df["sched"] - df["sent"]).dt.days
    vendor_lead = df.groupby("vendor")["lead"].median()
    fallback = pd.to_timedelta(df["vendor"].map(vendor_lead).fillna(df["lead"].median()), unit="D")
    df["issued"] = df["sent"].fillna(df["sched"] - fallback)
    return df


def pick_as_of(df: pd.DataFrame) -> pd.Timestamp:
    """Replay point with the most overdue POs, then shipments, leaving at most MAX_FUTURE_SHARE of lines out.

    Ties resolve to the latest date, so as much history as possible is loaded.
    """
    end = df["delivered"].max().normalize()
    best: Optional[Tuple[Tuple[int, int], pd.Timestamp]] = None
    for day in pd.date_range(end - pd.Timedelta(days=AS_OF_SEARCH_DAYS), end, freq="D"):
        if (df["issued"] > day).mean() > MAX_FUTURE_SHARE:
            continue
        live = (df["issued"] <= day) & (df["delivered"] > day)
        overdue = live & (df["sched"] < day)
        # Prefer a snapshot with overdue purchase orders and overdue shipments both present.
        overdue_pos = df.loc[overdue & ~df["is_so"], "ref"].nunique()
        score = (overdue_pos, df.loc[overdue, "asn"].nunique())
        if best is None or score >= best[0]:
            best = (score, day)
    if best is None:
        raise ValueError("No replay date satisfies the future-share limit.")
    return best[1]


def _criticality_scms(group: str, sub: str) -> str:
    if sub == "Pediatric":
        return "CRITICAL"  # paediatric formulations have no substitutes
    if group in ("ARV", "ACT", "ANTM"):
        return "HIGH"      # treatment commodities
    return "MEDIUM"        # diagnostics


def build_scms(
    df: pd.DataFrame, today: datetime, as_of: pd.Timestamp
) -> Tuple[Tables, Dict[str, Any], float]:
    rows_in_source = len(df)
    shift = timedelta(days=(today.date() - as_of.date()).days)

    df = df[df["issued"] <= as_of].copy()
    df["is_delivered"] = df["delivered"] <= as_of
    df["is_overdue"] = ~df["is_delivered"] & (df["sched"] < as_of)
    df["is_moving"] = (
        ~df["is_delivered"]
        & ~df["is_overdue"]
        & ((df["sched"] - as_of).dt.days <= IN_TRANSIT_WINDOW_DAYS)
    )

    history = df[df["is_delivered"]]
    on_time = history["delivered"] <= history["sched"]
    network_on_time = float(on_time.mean())

    # Expedite lead-time factor: air charter vs regular air, from recorded lead times.
    air_lead = df.loc[df["mode"] == "Air", "lead"].median()
    charter_lead = df.loc[df["mode"] == "Air Charter", "lead"].median()
    expedite_factor = round(float(charter_lead / air_lead), 2) if air_lead and charter_lead else 0.5

    tables: Tables = {k: [] for k in LOAD_ORDER}

    # Suppliers — every vendor except the internal RDC stock source.
    po_lines = df[~df["is_so"]]
    vendor_ids: Dict[str, str] = {}
    for n, (vendor, lines) in enumerate(sorted(po_lines.groupby("vendor"), key=lambda kv: kv[0]), start=1):
        vendor_ids[vendor] = f"SCMS-V{n:03d}"
        delivered = lines[lines["is_delivered"]]
        hits = int((delivered["delivered"] <= delivered["sched"]).sum())
        reliability = (hits + RELIABILITY_PRIOR_WEIGHT * network_on_time) / (
            len(delivered) + RELIABILITY_PRIOR_WEIGHT
        )
        lead = lines["lead"].median()
        lead_days = max(1, int(round(lead if not pd.isna(lead) else df["lead"].median())))
        basis = delivered if len(delivered) else lines
        monthly = basis.groupby(basis["delivered"].dt.to_period("M"))["qty"].sum()
        peak_daily = float(monthly.quantile(0.9)) / 30 if len(monthly) else 0.0
        recent = lines[(lines["sched"] > as_of - pd.Timedelta(days=30)) & (lines["sched"] <= as_of)]
        city, country = _split_site(_mode(lines["site"]))
        tables["suppliers"].append(
            {
                "id": vendor_ids[vendor],
                "name": vendor[:255],
                "code": vendor_ids[vendor],
                "category": PRODUCT_GROUPS.get(_mode(lines["group"]), _mode(lines["group"])),
                "city": city,
                "country": country,
                "lead_time_days": lead_days,
                "expedite_lead_time_days": max(1, int(round(lead_days * expedite_factor))),
                "reliability_rating": round(min(1.0, max(0.0, reliability)), 2),
                "capacity_units_per_day": max(1, int(math.ceil(peak_daily))),
                "current_capacity_utilized": int(round(float(recent["qty"].sum()) / 30)),
                "expedite_cost_multiplier": None,
                "contact_email": None,
                "is_active": True,
            }
        )

    # Products — one per item description.
    product_ids: Dict[str, str] = {}
    product_criticality: Dict[str, str] = {}
    for n, (item, lines) in enumerate(sorted(df.groupby("item"), key=lambda kv: kv[0]), start=1):
        pid = f"SCMS-P{n:03d}"
        product_ids[item] = pid
        group, sub = _mode(lines["group"]), _mode(lines["sub"])
        priced = lines[lines["pack_price"] > 0]
        vendor_price = priced.loc[~priced["is_so"], "pack_price"].median()
        unit_cost = vendor_price if not pd.isna(vendor_price) else priced["pack_price"].median()
        unit_cost = 0.0 if pd.isna(unit_cost) else float(unit_cost)
        client_price = priced.loc[priced["is_so"], "pack_price"].median()
        unit_price = float(client_price) if not pd.isna(client_price) else unit_cost
        per_pack = (lines["weight"] / lines["qty"]).where(lines["weight"] > 0).median()
        vendor = _mode(lines.loc[~lines["is_so"], "vendor"])
        product_criticality[pid] = _criticality_scms(group, sub)
        tables["products"].append(
            {
                "id": pid,
                "sku": f"SCMS-{group}-{n:03d}",
                "name": item[:255],
                # Same vocabulary as supplier categories, so alternative-supplier search matches.
                "category": PRODUCT_GROUPS.get(group, group),
                "unit_price": round(unit_price, 2),
                "unit_cost": round(unit_cost, 2),
                "weight_kg": _float(per_pack, 4),
                "critical_level": product_criticality[pid],
                "primary_supplier_id": vendor_ids.get(vendor),
            }
        )
    df["product_id"] = df["item"].map(product_ids)

    # Customers — the destination country programmes, tiered by delivered value.
    value_by_country = df.groupby("country")["value"].sum().sort_values(ascending=False)
    customer_ids: Dict[str, str] = {}
    for rank, (country, _) in enumerate(value_by_country.items(), start=1):
        tier = next((t for limit, t in TIER_BY_RANK if rank <= limit), "STANDARD")
        customer_ids[country] = f"SCMS-C-{_slug(country, 24)}"
        tables["customers"].append(
            {
                "id": customer_ids[country],
                "name": country[:255],
                "email": None,
                "tier": tier,
                "sla_hours": SLA_BY_TIER[tier],
                "contact_phone": None,
                "shipping_address": country,
            }
        )

    # Warehouses — the RDC (sales-order source) and one delivery point per country.
    tables["warehouses"].append(
        {
            "id": RDC_ID,
            "name": RDC_NAME,
            "code": RDC_ID,
            "location": "Regional distribution network (site not recorded)",
            "city": "Not recorded",
            "state": None,
            "country": None,
            "capacity_sqft": None,
            "operating_cost_per_day": None,
            "is_active": True,
        }
    )
    point_ids: Dict[str, str] = {}
    for country in sorted(df["country"].unique()):
        point_ids[country] = f"SCMS-DP-{_slug(country, 24)}"
        tables["warehouses"].append(
            {
                "id": point_ids[country],
                "name": f"{country} delivery point"[:255],
                "code": f"DP-{_slug(country, 24)}",
                "location": country,
                "city": country[:100],
                "state": None,
                "country": country,
                "capacity_sqft": None,
                "operating_cost_per_day": None,
                "is_active": True,
            }
        )

    # Carriers — one per recorded shipment mode, rated on delivered history.
    per_kg = (history["freight"] / history["weight"]).where(
        (history["freight"] > 0) & (history["weight"] > 0)
    )
    for mode, (cid, name, schema_mode) in SHIPMENT_MODES.items():
        mask = history["mode"] == mode
        if not mask.any():
            continue
        tables["carriers"].append(
            {
                "id": cid,
                "name": name,
                "code": cid,
                "mode": schema_mode,
                "reliability_rating": round(float(on_time[mask].mean()), 2),
                "base_cost_per_km": None,
                "expedite_cost_multiplier": None,
                "avg_speed_kmh": None,
                "freight_cost_per_kg": _float(per_kg[mask].median()),
                "contact_phone": None,
                "is_active": True,
            }
        )

    # Customer orders (SO-…) and purchase orders (SCMS-… / DSCM-…).
    order_ids: Dict[str, str] = {}
    po_ids: Dict[str, str] = {}
    for ref, lines in df.groupby("ref"):
        issued = lines["issued"].min()
        notes = f"Project {_mode(lines['project'])} · INCO {_mode(lines['inco'])} · {_mode(lines['fulfil'])}"
        if bool(lines["is_so"].iloc[0]):
            oid = f"SCMS-ORD-{_slug(ref)}"
            order_ids[ref] = oid
            if lines["is_delivered"].all():
                status = "DELIVERED"
            elif lines["is_overdue"].any():
                status = "DELAYED"
            elif lines["is_moving"].any():
                status = "SHIPPED"
            else:
                status = "PROCESSING"
            priority = max(
                (product_criticality[p] for p in lines["product_id"]),
                key=CRITICALITY_ORDER.index,
            )
            country = lines["country"].iloc[0]
            tables["orders"].append(
                {
                    "id": oid,
                    "order_number": ref,
                    "customer_id": customer_ids[country],
                    "order_date": _stamp(issued, shift),
                    "required_delivery_date": _stamp(lines["sched"].max(), shift),
                    "status": status,
                    "total_amount": _float(lines["value"].sum()),
                    "shipping_city": country[:100],
                    "shipping_address": country,
                    "priority": priority,
                    "assigned_warehouse_id": RDC_ID,
                }
            )
            for line in lines.itertuples(index=False):
                tables["order_items"].append(
                    {
                        "id": f"SCMS-OI-{line.line_id}",
                        "order_id": oid,
                        "product_id": line.product_id,
                        "quantity": int(line.qty),
                        "unit_price": _float(line.pack_price),
                        "total_price": _float(line.value),
                        "fulfilled_quantity": int(line.qty) if line.is_delivered else 0,
                    }
                )
        else:
            poid = f"SCMS-PO-{_slug(ref)}"
            po_ids[ref] = poid
            if lines["is_delivered"].all():
                status = "RECEIVED"
            elif lines["is_overdue"].any():
                status = "DELAYED"
            elif lines["is_moving"].any():
                status = "IN_TRANSIT"
            elif (as_of - issued).days <= NEW_PO_WINDOW_DAYS:
                status = "ISSUED"
            else:
                status = "CONFIRMED"
            tables["purchase_orders"].append(
                {
                    "id": poid,
                    "po_number": ref,
                    "supplier_id": vendor_ids[lines["vendor"].iloc[0]],
                    "destination_warehouse_id": point_ids[lines["country"].iloc[0]],
                    "issue_date": _stamp(issued, shift),
                    "expected_delivery_date": _stamp(lines["sched"].max(), shift),
                    "actual_delivery_date": (
                        _stamp(lines["delivered"].max(), shift) if lines["is_delivered"].all() else None
                    ),
                    "status": status,
                    "total_cost": _float(lines["value"].sum()),
                    "is_expedited": bool((lines["mode"] == "Air Charter").any()),
                    "notes": notes,
                }
            )
            for line in lines.itertuples(index=False):
                tables["purchase_order_items"].append(
                    {
                        "id": f"SCMS-POI-{line.line_id}",
                        "purchase_order_id": poid,
                        "product_id": line.product_id,
                        "quantity_ordered": int(line.qty),
                        "quantity_received": int(line.qty) if line.is_delivered else 0,
                        "unit_cost": _float(line.pack_price),
                        "total_cost": _float(line.value),
                    }
                )

    # Shipments — one per ASN / DN; lines without a recorded mode have no carrier.
    skipped_no_mode = 0
    for asn, lines in df.groupby("asn"):
        mode = _mode(lines["mode"])
        if mode not in SHIPMENT_MODES:
            skipped_no_mode += len(lines)
            continue
        ref = lines["ref"].iloc[0]
        is_so = bool(lines["is_so"].iloc[0])
        sched = lines["sched"].max()
        delivered_all = bool(lines["is_delivered"].all())
        if delivered_all:
            status = "DELIVERED"
            late_days = max(0, (lines["delivered"].max() - sched).days)
            state = f"Delivered {late_days} days after schedule." if late_days else "Delivered on schedule."
        elif lines["is_overdue"].any():
            status = "DELAYED"
            late_days = max(0, (as_of - sched).days)
            state = f"Past scheduled delivery by {late_days} days; not yet delivered."
        elif lines["is_moving"].any():
            status, late_days, state = "IN_TRANSIT", 0, "In transit; on schedule."
        else:
            status, late_days, state = "CREATED", 0, "Booked; awaiting dispatch."

        freight_notes = []
        text = lines["freight_raw"].fillna("")
        if text.str.contains("Included in Commodity", case=False).any():
            freight_notes.append("freight included in commodity cost")
        if text.str.contains("Invoiced Separately", case=False).any():
            freight_notes.append("freight invoiced separately")
        booked = text.str.extract(r"See ((?:ASN|DN)-\d+)")[0].dropna()
        if len(booked):
            freight_notes.append(f"freight booked under {booked.iloc[0]}")
        country = lines["country"].iloc[0]
        if is_so:
            origin = RDC_NAME
        else:
            site_city, site_country = _split_site(_mode(lines["site"]))
            origin = f"{site_city}, {site_country}" if site_country else site_city
        weight = lines["weight"].where(lines["weight"] > 0).sum(min_count=1)
        tables["shipments"].append(
            {
                "id": f"SCMS-SH-{_slug(asn)}",
                "shipment_number": asn,
                "order_id": order_ids.get(ref) if is_so else None,
                "purchase_order_id": None if is_so else po_ids.get(ref),
                "carrier_id": SHIPMENT_MODES[mode][0],
                "route_id": None,
                "origin_location": origin[:255],
                "destination_location": country[:255],
                "pickup_date": None,
                "expected_delivery_date": _stamp(sched, shift),
                "actual_delivery_date": _stamp(lines["delivered"].max(), shift) if delivered_all else None,
                "status": status,
                "shipping_cost": _float(lines["freight"].sum(min_count=1)) or 0.0,
                "delay_hours": int(late_days * 24),
                "weight_kg": _float(weight),
                "current_location": country[:255] if delivered_all else None,
                "tracking_notes": " ".join(
                    [state, f"INCO {_mode(lines['inco'])} · {_mode(lines['fulfil'])}."]
                    + ([("; ".join(freight_notes)).capitalize() + "."] if freight_notes else [])
                ),
            }
        )

    live = df[~df["is_delivered"]]
    summary = {
        "rows_in_source": rows_in_source,
        "rows_loaded": len(df),
        "as_of": as_of.date(),
        "shift_days": shift.days,
        "future_lines_excluded": rows_in_source - len(df),
        "lines_without_mode": skipped_no_mode,
        "live_lines": len(live),
        "overdue_lines": int(df["is_overdue"].sum()),
        "network_on_time": round(network_on_time, 3),
        "expedite_factor": expedite_factor,
    }
    return tables, summary, expedite_factor


# ---------------------------------------------------------------------------
# E-Grocery — distribution centres, SKUs, stock positions
# ---------------------------------------------------------------------------

def build_grocery(path: Path, today: datetime, expedite_factor: float) -> Tuple[Tables, Dict[str, Any]]:
    df = pd.read_csv(path, dtype=str)
    for col in ("Avg_Daily_Sales", "Reorder_Point", "Unit_Cost_USD", "Supplier_OnTime_Pct"):
        df[col] = df[col].map(_eu_number)
    for col in ("Quantity_On_Hand", "Quantity_Reserved", "Quantity_Committed", "Safety_Stock", "Lead_Time_Days"):
        df[col] = pd.to_numeric(df[col]).astype(int)
    received = pd.to_datetime(df["Received_Date"])
    as_of = max(received.max(), pd.to_datetime(df["Audit_Date"]).max())
    shift = timedelta(days=(today.date() - as_of.date()).days)

    tables: Tables = {k: [] for k in LOAD_ORDER}

    for wid, location in df.groupby("Warehouse_ID")["Warehouse_Location"].first().items():
        city, _, area = str(location).partition(" - ")
        city, area = city.strip(), area.strip()
        tables["warehouses"].append(
            {
                "id": f"EG-{wid}",
                "name": f"{city} Distribution Centre ({area})" if area else f"{city} Distribution Centre",
                "code": wid,
                "location": area or city,
                "city": city,
                "state": INDONESIA_PROVINCES.get(city),
                "country": "Indonesia",
                "capacity_sqft": None,
                "operating_cost_per_day": None,
                "is_active": True,
            }
        )

    for sid, lines in df.groupby("Supplier_ID"):
        lead = max(1, int(round(float(lines["Lead_Time_Days"].median()))))
        daily = float(lines["Avg_Daily_Sales"].sum())
        tables["suppliers"].append(
            {
                "id": f"EG-{sid}",
                "name": str(lines["Supplier_Name"].iloc[0])[:255],
                "code": f"EG-{sid}",
                "category": _mode(lines["Category"]),
                "city": "Not recorded",
                "country": "Indonesia",
                "lead_time_days": lead,
                "expedite_lead_time_days": max(1, int(round(lead * expedite_factor))),
                "reliability_rating": round(float(lines["Supplier_OnTime_Pct"].mean()) / 100, 2),
                "capacity_units_per_day": max(1, int(math.ceil(daily / GROCERY_ASSUMED_UTILISATION))),
                "current_capacity_utilized": int(round(daily)),
                "expedite_cost_multiplier": None,
                "contact_email": None,
                "is_active": True,
            }
        )

    for row in df.to_dict("records"):
        sku = row["SKU_ID"]
        unit_cost = round(float(row["Unit_Cost_USD"]), 2)
        committed = int(row["Quantity_Reserved"]) + int(row["Quantity_Committed"])
        tables["products"].append(
            {
                "id": f"EG-{sku}",
                "sku": sku,
                "name": str(row["SKU_Name"])[:255],
                "category": row["Category"],
                # The export carries cost only; exposure is valued at cost.
                "unit_price": unit_cost,
                "unit_cost": unit_cost,
                "weight_kg": None,
                "critical_level": ABC_TO_CRITICALITY.get(row["ABC_Class"], "MEDIUM"),
                "primary_supplier_id": f"EG-{row['Supplier_ID']}",
            }
        )
        tables["inventory"].append(
            {
                "id": f"EG-INV-{sku}",
                "warehouse_id": f"EG-{row['Warehouse_ID']}",
                "product_id": f"EG-{sku}",
                # Available-to-promise: on hand less reserved and committed stock.
                "quantity_available": max(0, int(row["Quantity_On_Hand"]) - committed),
                "quantity_reserved": committed,
                "quantity_in_transit": 0,
                "reorder_point": int(round(float(row["Reorder_Point"]))),
                "safety_stock": int(row["Safety_Stock"]),
                "unit_holding_cost_per_day": None,
                "last_restocked_at": _stamp(pd.Timestamp(row["Received_Date"]), shift),
            }
        )

    summary = {
        "rows_in_source": len(df),
        "rows_loaded": len(df),
        "as_of": as_of.date(),
        "shift_days": shift.days,
    }
    return tables, summary


# ---------------------------------------------------------------------------
# Validation — the same rules the database enforces, checked before any write
# ---------------------------------------------------------------------------

PRIMARY_KEYS = {name: "id" for name in LOAD_ORDER}
UNIQUE_COLUMNS = {
    "products": ["sku"],
    "warehouses": ["code"],
    "suppliers": ["code"],
    "carriers": ["code"],
    "orders": ["order_number"],
    "purchase_orders": ["po_number"],
    "shipments": ["shipment_number"],
}
FOREIGN_KEYS = {
    "products": [("primary_supplier_id", "suppliers")],
    "inventory": [("warehouse_id", "warehouses"), ("product_id", "products")],
    "orders": [("customer_id", "customers"), ("assigned_warehouse_id", "warehouses")],
    "order_items": [("order_id", "orders"), ("product_id", "products")],
    "purchase_orders": [("supplier_id", "suppliers"), ("destination_warehouse_id", "warehouses")],
    "purchase_order_items": [("purchase_order_id", "purchase_orders"), ("product_id", "products")],
    "shipments": [("order_id", "orders"), ("purchase_order_id", "purchase_orders"), ("carrier_id", "carriers")],
}
REQUIRED = {
    "customers": ["name"],
    "products": ["sku", "name", "unit_price", "unit_cost"],
    "warehouses": ["name", "code", "location", "city"],
    "inventory": ["warehouse_id", "product_id", "quantity_available", "reorder_point", "safety_stock"],
    "suppliers": ["name", "code", "city", "lead_time_days"],
    "carriers": ["name", "code"],
    "orders": ["order_number", "customer_id", "required_delivery_date", "total_amount", "shipping_city"],
    "order_items": ["order_id", "product_id", "quantity", "unit_price", "total_price"],
    "purchase_orders": ["po_number", "supplier_id", "destination_warehouse_id", "expected_delivery_date", "total_cost"],
    "purchase_order_items": ["purchase_order_id", "product_id", "quantity_ordered", "unit_cost", "total_cost"],
    "shipments": ["shipment_number", "carrier_id", "origin_location", "destination_location", "expected_delivery_date", "shipping_cost"],
    "data_sources": ["name"],
}
ENUMS = {
    ("customers", "tier"): {"STANDARD", "PRIORITY", "ENTERPRISE", "VIP"},
    ("products", "critical_level"): set(CRITICALITY_ORDER),
    ("carriers", "mode"): {"ROAD", "AIR", "RAIL", "OCEAN"},
    ("orders", "status"): {"PENDING", "PROCESSING", "SHIPPED", "DELIVERED", "DELAYED", "CANCELLED", "EXCEPTION"},
    ("orders", "priority"): set(CRITICALITY_ORDER),
    ("purchase_orders", "status"): {"ISSUED", "CONFIRMED", "IN_TRANSIT", "RECEIVED", "DELAYED", "CANCELLED", "EXPEDITED"},
    ("shipments", "status"): {"CREATED", "IN_TRANSIT", "OUT_FOR_DELIVERY", "DELIVERED", "DELAYED", "REROUTED", "EXCEPTION", "CANCELLED"},
}
LENGTH_LIMITS = {
    "name": 255, "code": 50, "city": 100, "category": 100, "sku": 100, "location": 255,
    "shipment_number": 100, "po_number": 100, "order_number": 100, "country": 100,
    "origin_location": 255, "destination_location": 255, "shipping_city": 100, "state": 100,
}


def validate(tables: Tables) -> None:
    problems: List[str] = []
    ids = {name: {row["id"] for row in rows} for name, rows in tables.items()}
    for name, rows in tables.items():
        if not rows:
            continue
        keys = set(rows[0])
        if any(set(row) != keys for row in rows):
            problems.append(f"{name}: rows do not share one column set")
        if len(ids[name]) != len(rows):
            problems.append(f"{name}: duplicate primary keys")
        for column in UNIQUE_COLUMNS.get(name, []):
            values = [row[column] for row in rows]
            if len(set(values)) != len(values):
                problems.append(f"{name}.{column}: duplicate values")
        for column in REQUIRED.get(name, []):
            missing = sum(1 for row in rows if row.get(column) is None)
            if missing:
                problems.append(f"{name}.{column}: {missing} NULL values in a NOT NULL column")
        for column, parent in FOREIGN_KEYS.get(name, []):
            orphans = {row[column] for row in rows if row.get(column) is not None} - ids.get(parent, set())
            if orphans:
                problems.append(f"{name}.{column}: {len(orphans)} values missing from {parent}")
        for (table, column), allowed in ENUMS.items():
            if table == name:
                bad = {row.get(column) for row in rows} - allowed - {None}
                if bad:
                    problems.append(f"{name}.{column}: values outside the CHECK constraint {sorted(bad)}")
        for column, limit in LENGTH_LIMITS.items():
            if column in keys:
                long = sum(1 for row in rows if isinstance(row.get(column), str) and len(row[column]) > limit)
                if long:
                    problems.append(f"{name}.{column}: {long} values longer than {limit}")
    for row in tables.get("suppliers", []) + tables.get("carriers", []):
        if row.get("reliability_rating") is not None and not 0 <= row["reliability_rating"] <= 1:
            problems.append(f"reliability outside 0..1 on {row['id']}")
    for row in tables.get("inventory", []):
        if min(row["quantity_available"], row["quantity_reserved"], row["quantity_in_transit"]) < 0:
            problems.append(f"negative inventory quantity on {row['id']}")
    for name, column in (("order_items", "quantity"), ("purchase_order_items", "quantity_ordered")):
        if any(row[column] <= 0 for row in tables.get(name, [])):
            problems.append(f"{name}.{column}: non-positive quantity")
    if problems:
        raise ValueError("Import validation failed:\n  - " + "\n  - ".join(problems))


# ---------------------------------------------------------------------------
# Build, load, run
# ---------------------------------------------------------------------------

def build(today: Optional[datetime] = None, as_of: Optional[str] = None) -> Tuple[Tables, Dict[str, Any]]:
    today = today or datetime.now(timezone.utc)
    scms_path = download(SCMS_REF, SCMS_FILE)
    grocery_path = download(GROCERY_REF, GROCERY_FILE)

    frame = load_scms_frame(scms_path)
    replay = pd.Timestamp(as_of) if as_of else pick_as_of(frame)
    scms_tables, scms_summary, expedite_factor = build_scms(frame, today, replay)
    grocery_tables, grocery_summary = build_grocery(grocery_path, today, expedite_factor)

    tables: Tables = {name: scms_tables[name] + grocery_tables[name] for name in LOAD_ORDER}
    tables["data_sources"] = [
        {
            "id": "SCMS",
            "name": "SCMS Delivery History (USAID)",
            "kaggle_ref": SCMS_REF,
            "rows_in_source": scms_summary["rows_in_source"],
            "rows_loaded": scms_summary["rows_loaded"],
            "source_as_of": scms_summary["as_of"],
            "replayed_to": today.date(),
            "notes": (
                f"Replayed as of {scms_summary['as_of']}; dates shifted +{scms_summary['shift_days']} days. "
                f"{scms_summary['future_lines_excluded']} lines issued after the replay point left out as future."
            ),
        },
        {
            "id": "EGROCERY",
            "name": "Inventory Management E-Grocery",
            "kaggle_ref": GROCERY_REF,
            "rows_in_source": grocery_summary["rows_in_source"],
            "rows_loaded": grocery_summary["rows_loaded"],
            "source_as_of": grocery_summary["as_of"],
            "replayed_to": today.date(),
            "notes": f"Stock snapshot as of {grocery_summary['as_of']}; dates shifted +{grocery_summary['shift_days']} days.",
        },
    ]
    return tables, {"scms": scms_summary, "grocery": grocery_summary}


def load(tables: Tables, db=None) -> None:
    """Reset the schema and load every table in ONE transaction.

    PostgreSQL DDL is transactional, so a failure anywhere leaves the previous
    data exactly as it was.
    """
    from sqlalchemy import MetaData, Table, text

    from database.client import get_db

    db = db or get_db()
    ddl = SCHEMA_FILE.read_text(encoding="utf-8")
    with db.engine.begin() as conn:
        conn.execute(text(ddl))
        metadata = MetaData()
        for name in LOAD_ORDER:
            rows = tables.get(name) or []
            if not rows:
                continue
            table = Table(name, metadata, autoload_with=conn)
            for start in range(0, len(rows), 1000):
                conn.execute(table.insert(), rows[start : start + 1000])
            logger.info("loaded %-22s %6d rows", name, len(rows))


def run(dry_run: bool = False, as_of: Optional[str] = None, detect: bool = True) -> Dict[str, Any]:
    tables, summary = build(as_of=as_of)
    validate(tables)
    summary["counts"] = {name: len(rows) for name, rows in tables.items()}
    _report(tables, summary)
    if dry_run:
        print("\nDry run — validated, nothing written.")
        return summary

    load(tables)
    print("\nSupabase data replaced.")
    if detect:
        from services.exception_detector import ExceptionDetector

        found = ExceptionDetector().run_all_detectors()
        summary["exceptions_detected"] = len(found)
        by_type: Dict[str, int] = {}
        for exc in found:
            by_type[exc["exception_type"]] = by_type.get(exc["exception_type"], 0) + 1
        print(f"Exception detection: {len(found)} exceptions  {by_type}")
    return summary


def _report(tables: Tables, summary: Dict[str, Any]) -> None:
    scms, grocery = summary["scms"], summary["grocery"]
    print("\nRELAY Kaggle import")
    print(f"  SCMS     {scms['rows_in_source']:>6} lines · replay as of {scms['as_of']} (+{scms['shift_days']} days)"
          f" · {scms['future_lines_excluded']} future lines left out · {scms['lines_without_mode']} lines without a mode (no shipment)")
    print(f"           live lines {scms['live_lines']} · overdue lines {scms['overdue_lines']}"
          f" · network on-time {scms['network_on_time']:.1%} · expedite lead factor {scms['expedite_factor']}")
    print(f"  Grocery  {grocery['rows_in_source']:>6} SKUs  · snapshot {grocery['as_of']} (+{grocery['shift_days']} days)")
    print("\n  table                   rows")
    for name in LOAD_ORDER:
        print(f"  {name:<22} {len(tables.get(name) or []):>6}")
    ships = tables["shipments"]
    status = pd.Series([s["status"] for s in ships]).value_counts().to_dict()
    po_status = pd.Series([p["status"] for p in tables["purchase_orders"]]).value_counts().to_dict()
    print(f"\n  shipments by status        {status}")
    print(f"  purchase orders by status  {po_status}")
    short = sum(1 for i in tables["inventory"] if i["quantity_available"] <= i["safety_stock"])
    print(f"  stock lines at/below safety stock: {short}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Load the Kaggle datasets into Supabase.")
    parser.add_argument("--dry-run", action="store_true", help="download, transform and validate only")
    parser.add_argument("--as-of", default=None, help="SCMS replay date (YYYY-MM-DD); auto-picked if omitted")
    parser.add_argument("--no-detect", action="store_true", help="skip exception detection after loading")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    run(dry_run=args.dry_run, as_of=args.as_of, detect=not args.no_detect)
    return 0


if __name__ == "__main__":
    sys.exit(main())
