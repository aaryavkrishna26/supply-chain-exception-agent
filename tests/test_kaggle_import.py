"""
Importer tests: transform the cached Kaggle datasets and check the result.

No database access. Needs the datasets in the kagglehub cache (the first
`python -m data.kaggle_import` downloads them); skips otherwise.
"""

from datetime import datetime, timezone

import pytest

from data import kaggle_import as ki

TODAY = datetime(2026, 9, 11, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def built():
    try:
        return ki.build(today=TODAY, as_of="2015-07-05")
    except Exception as err:  # offline and uncached
        pytest.skip(f"Kaggle datasets unavailable: {err}")


def test_european_number_parsing():
    assert ki._eu_number("$2.084,25") == 2084.25
    assert ki._eu_number("28,57") == 28.57
    assert ki._eu_number("70,68%") == 70.68
    assert ki._eu_number("1.377") == 1377.0
    assert ki._eu_number("51.0") == 51.0


def test_manufacturing_site_split():
    assert ki._split_site("Ranbaxy, Paonta Shahib, India") == ("Ranbaxy, Paonta Shahib", "India")
    assert ki._split_site("ABBVIE GmbH & Co.KG Wiesbaden") == ("ABBVIE GmbH & Co.KG Wiesbaden", None)


def test_build_passes_the_database_rules(built):
    tables, _ = built
    ki.validate(tables)  # raises on any PK, FK, CHECK, NOT NULL or length violation


def test_row_counts_reflect_the_sources(built):
    tables, summary = built
    assert len(tables["inventory"]) == 1000
    assert len(tables["products"]) == 1000 + len({p["id"] for p in tables["products"] if p["id"].startswith("SCMS-")})
    assert summary["scms"]["rows_in_source"] == 10324
    assert summary["scms"]["future_lines_excluded"] < 0.05 * 10324


def test_live_records_never_carry_future_deliveries(built):
    tables, _ = built
    for shipment in tables["shipments"]:
        if shipment["status"] != "DELIVERED":
            assert shipment["actual_delivery_date"] is None
        if shipment["status"] == "DELAYED":
            assert shipment["delay_hours"] > 0 and shipment["expected_delivery_date"] < TODAY
    for po in tables["purchase_orders"]:
        if po["status"] != "RECEIVED":
            assert po["actual_delivery_date"] is None


def test_snapshot_has_live_and_historical_state(built):
    tables, _ = built
    statuses = {s["status"] for s in tables["shipments"]}
    assert {"DELIVERED", "DELAYED"} <= statuses
    assert {"IN_TRANSIT", "CREATED"} & statuses


def test_available_stock_is_available_to_promise(built):
    tables, _ = built
    for row in tables["inventory"]:
        assert row["quantity_available"] >= 0
        assert row["reorder_point"] >= 0 and row["safety_stock"] >= 0


def test_no_invented_values(built):
    tables, _ = built
    assert all(c["base_cost_per_km"] is None and c["avg_speed_kmh"] is None for c in tables["carriers"])
    assert all(w["operating_cost_per_day"] is None for w in tables["warehouses"])
    assert not tables["routes"], "no route data exists in either source"
