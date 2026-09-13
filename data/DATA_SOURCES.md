# RELAY operational data

RELAY's operational tables are loaded from two public Kaggle datasets by
[`data/kaggle_import.py`](kaggle_import.py). There is no synthetic seed data.
Everything the agent and the UI reason over is either a dataset value, a
calculation over dataset values, or left empty. Where neither dataset carries a
value, this document says so.

```bash
python -m data.kaggle_import --dry-run   # download, transform, validate — writes nothing
python -m data.kaggle_import             # replace Supabase data, then run exception detection
```

The load resets the schema and inserts every table in **one transaction**. If
anything fails, the previous data stays exactly as it was. Downloads are cached
by `kagglehub`.

## Sources

| Source | Kaggle | Used for |
|---|---|---|
| **SCMS Delivery History** — USAID Supply Chain Management System, 10,324 line items, 2006–2015 | [`divyeshardeshana/supply-chain-shipment-pricing-data`](https://www.kaggle.com/datasets/divyeshardeshana/supply-chain-shipment-pricing-data) | suppliers, products, customers, purchase orders, customer orders, shipments, carriers |
| **Inventory Management E-Grocery** — 1,000 SKUs across 5 Indonesian distribution centres | [`mustofaahmad/inventory-management-grocery-industry`](https://www.kaggle.com/datasets/mustofaahmad/inventory-management-grocery-industry) | warehouses, products, suppliers, inventory |

The two sources describe different networks, and RELAY keeps them distinct.
Record IDs carry their origin: `SCMS-…` or `EG-…`. The `data_sources` table
records what was loaded and when.

## Timeline replay (SCMS)

SCMS is a closed history: every line was eventually delivered. To give the
workspace a live state, the importer picks an **as-of date** inside the history
and treats it as today:

- a line issued before the as-of date and delivered before it is **history**:
  delivered, with its real lateness;
- a line issued before it but delivered after it is **live**: `DELAYED` if its
  scheduled date has already passed, `IN_TRANSIT` if it is due within 21 days,
  otherwise `CREATED` (booked, awaiting dispatch);
- a line issued after it is **future** and is left out.

Every date is then shifted by the same number of days so the as-of date lands on
the load date. Relative timings and recorded lateness are unchanged, and nothing
about a live line's eventual delivery is written into its record.

By default the as-of date is the day in the final two years with the most
overdue purchase orders, then overdue shipments, subject to leaving out at most 5% of lines as future. Pin it
with `--as-of YYYY-MM-DD`.

## Field mapping

### SCMS

| RELAY | SCMS source |
|---|---|
| `suppliers` | `Vendor` (the internal "SCMS from RDC" source excluded) |
| `suppliers.reliability_rating` | share of the vendor's delivered lines on or before schedule, shrunk toward the network rate with a weight of 10 lines, so small samples don't read as 100% |
| `suppliers.lead_time_days` | median of `Scheduled Delivery Date − PO Sent to Vendor Date` |
| `suppliers.city` / `country` | most common `Manufacturing Site`, split at its last comma |
| `suppliers.capacity_units_per_day` | 90th-percentile monthly delivered quantity ÷ 30 (observed peak throughput) |
| `suppliers.current_capacity_utilized` | quantity scheduled in the 30 days before the as-of date ÷ 30 |
| `products` | one per `Item Description`; SKU `SCMS-<group>-<n>`; category = product group (Antiretrovirals, HIV rapid diagnostic tests, …), the same vocabulary as supplier categories |
| `products.unit_cost` / `unit_price` | median `Pack Price` on vendor (direct-drop) lines / on client (RDC) lines |
| `products.weight_kg` | median `Weight ÷ Line Item Quantity` (per pack) |
| `products.primary_supplier_id` | the vendor that supplies the item most often |
| `customers` | destination `Country`; tier by delivered value (top 5 VIP, next 5 Enterprise, next 10 Priority) |
| `purchase_orders` + items | `SCMS-…` PO numbers (direct drop from vendor to country) |
| `orders` + `order_items` | `SO-…` sales orders fulfilled from the regional distribution centre |
| `shipments` | one per `ASN/DN #`; freight = recorded `Freight Cost (USD)`, weight = recorded `Weight (Kilograms)` |
| `carriers` | one per `Shipment Mode` (Air, Air charter, Truck, Ocean); reliability = on-time share, `freight_cost_per_kg` = median freight ÷ weight |
| `warehouses` | the regional distribution centre plus one delivery point per destination country |

### E-Grocery

| RELAY | E-Grocery source |
|---|---|
| `warehouses` | `Warehouse_ID`, `Warehouse_Location` ("City - Area") |
| `products` | `SKU_ID`, `SKU_Name`, `Category`, `Unit_Cost_USD`, `ABC_Class` → criticality (A high, B medium, C low) |
| `inventory.quantity_available` | `Quantity_On_Hand − Quantity_Reserved − Quantity_Committed` (available to promise) |
| `inventory.quantity_reserved` | `Quantity_Reserved + Quantity_Committed` |
| `inventory.reorder_point` / `safety_stock` | `Reorder_Point`, `Safety_Stock` |
| `suppliers` | `Supplier_ID`, `Supplier_Name`; reliability = mean `Supplier_OnTime_Pct`; lead time = median `Lead_Time_Days` |
| `suppliers.current_capacity_utilized` | sum of `Avg_Daily_Sales` across the supplier's SKUs |

## Not in either dataset

These are the only values RELAY does not take from the data.

| Value | Treatment |
|---|---|
| Grocery selling price | Not recorded — `unit_price` = `unit_cost`, so exposure is valued at cost |
| Grocery supplier capacity | Assumed 80% utilised: capacity = daily demand ÷ 0.8 |
| Grocery supplier location | `Not recorded` (country Indonesia) |
| Expedited lead times | lead time × 0.65, the ratio of SCMS air-charter to air lead times (only 18 charter lines have both dates, so treat it as indicative) |
| Customer SLA hours | By tier: VIP 24 h, Enterprise 36 h, Priority 48 h, Standard 72 h |
| Product criticality (SCMS) | Paediatric → critical; antiretrovirals and antimalarials → high; diagnostics → medium |
| Order priority | Highest criticality among the order's items |
| PO issue date, where not recorded (~55%) | Scheduled date minus the vendor's median recorded lead time |
| Routes, distances, transit speeds | Not recorded — left empty; the agent does not propose reroutes |
| Carrier names | SCMS records the mode, not the forwarder; carriers are named by mode |
| Warehouse capacity, operating cost, holding cost | Left empty |
| Shipments with no recorded mode (360 lines) | No shipment record; their purchase or sales order is still loaded |

Two observations about the sources themselves:

- **The E-Grocery dataset looks generated.** Product names follow a pattern
  ("Pantry Product 13", "Fresh Product 112"), and about a fifth of SKUs sit at or
  below safety stock. RELAY loads it as published.
- **SCMS is genuine delivery history.** Most lines arrived on time (88.5%), so at
  any replay point only a handful of shipments are overdue.
