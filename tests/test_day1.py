"""
Data-layer tests against the live Supabase database, which is loaded from the
Kaggle datasets (see data/DATA_SOURCES.md).

These tests are READ-ONLY. They never reseed or modify the database; load it
with `python -m data.kaggle_import` first. If it is empty they skip.

- Supabase / PostgreSQL configuration enforcement (no SQLite fallback)
- All core tables present, plus data provenance
- Referential integrity across the loaded records
- The replayed SCMS snapshot is live and does not leak future deliveries
- Reliability and freight metrics derived from delivery history
- Exception detection covers every delayed shipment and every shortage
"""

import pytest

from database.client import ConfigurationError, DatabaseClient, get_db
from database.queries.supply_chain import SupplyChainQueries


def test_configuration_enforcement_without_credentials(monkeypatch):
    """The client requires Supabase credentials and does NOT fall back to SQLite."""
    monkeypatch.setenv("SUPABASE_DB_URL", "")
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_KEY", "")
    DatabaseClient.reset_instance()

    with pytest.raises(ConfigurationError) as exc_info:
        DatabaseClient.get_instance(db_url="")

    assert "Missing Supabase PostgreSQL configuration" in str(exc_info.value)
    assert ".env" in str(exc_info.value)


@pytest.fixture(scope="module")
def postgres_db():
    """A connected, already-loaded database. Skips rather than seeding."""
    DatabaseClient.reset_instance()
    try:
        db = get_db()
    except (ConfigurationError, RuntimeError) as err:
        pytest.skip(f"Supabase PostgreSQL not configured in .env: {err}")
    status = db.test_connection()
    if not status["connected"]:
        pytest.skip(f"Cannot reach Supabase PostgreSQL: {status.get('error')}")
    if not db.execute_query("SELECT 1 FROM shipments LIMIT 1"):
        pytest.skip("Database is empty — load it with `python -m data.kaggle_import`.")
    return db


def _count(db, sql):
    return db.execute_query(sql)[0]["n"]


def test_database_connection(postgres_db):
    status = postgres_db.test_connection()
    assert status["connected"] is True, f"Database connection failed: {status.get('error')}"
    assert status["backend"] == "postgresql"


def test_required_tables_exist(postgres_db):
    for table in (
        "customers", "products", "warehouses", "inventory", "suppliers", "carriers", "routes",
        "orders", "order_items", "purchase_orders", "purchase_order_items", "shipments",
        "exceptions", "resolution_options", "actions", "audit_logs", "data_sources",
    ):
        postgres_db.execute_query(f"SELECT COUNT(*) AS n FROM {table}")


def test_data_is_the_kaggle_import(postgres_db):
    """Provenance is recorded, and no synthetic demo record survives."""
    sources = {row["id"]: row for row in postgres_db.execute_query("SELECT * FROM data_sources")}
    assert set(sources) == {"SCMS", "EGROCERY"}
    assert all(row["rows_loaded"] > 0 for row in sources.values())
    assert _count(postgres_db, "SELECT COUNT(*) AS n FROM products WHERE id NOT LIKE 'SCMS-%' AND id NOT LIKE 'EG-%' AND id NOT LIKE 'PROD-%'") == 0
    assert _count(postgres_db, "SELECT COUNT(*) AS n FROM warehouses WHERE id IN ('WH-MUM-01', 'WH-BLR-01')") == 0
    assert _count(postgres_db, "SELECT COUNT(*) AS n FROM inventory") >= 1000
    assert _count(postgres_db, "SELECT COUNT(*) AS n FROM shipments") > 5000


def test_referential_integrity(postgres_db):
    orphans = {
        "order_items -> orders": "SELECT COUNT(*) AS n FROM order_items i LEFT JOIN orders o ON o.id = i.order_id WHERE o.id IS NULL",
        "po items -> purchase_orders": "SELECT COUNT(*) AS n FROM purchase_order_items i LEFT JOIN purchase_orders p ON p.id = i.purchase_order_id WHERE p.id IS NULL",
        "shipments -> carriers": "SELECT COUNT(*) AS n FROM shipments s LEFT JOIN carriers c ON c.id = s.carrier_id WHERE c.id IS NULL",
        "inventory -> products": "SELECT COUNT(*) AS n FROM inventory i LEFT JOIN products p ON p.id = i.product_id WHERE p.id IS NULL",
        "products -> suppliers": "SELECT COUNT(*) AS n FROM products p LEFT JOIN suppliers s ON s.id = p.primary_supplier_id WHERE p.primary_supplier_id IS NOT NULL AND s.id IS NULL",
        "shipments -> a PO or an order": "SELECT COUNT(*) AS n FROM shipments WHERE order_id IS NULL AND purchase_order_id IS NULL AND id LIKE 'SCMS-%'",
    }
    for label, sql in orphans.items():
        assert _count(postgres_db, sql) == 0, f"orphaned records: {label}"


def test_replayed_snapshot_is_live_without_leaking_the_future(postgres_db):
    by_status = {r["status"]: r["n"] for r in postgres_db.execute_query(
        "SELECT status, COUNT(*) AS n FROM shipments GROUP BY status")}
    assert by_status.get("DELIVERED", 0) > 1000, "delivery history is missing"
    assert by_status.get("IN_TRANSIT", 0) + by_status.get("CREATED", 0) + by_status.get("DELAYED", 0) > 0, \
        "nothing is in flight — the replay did not produce a live state"
    # Live records must not carry their eventual (future) delivery.
    assert _count(postgres_db, "SELECT COUNT(*) AS n FROM shipments WHERE status <> 'DELIVERED' AND actual_delivery_date IS NOT NULL") == 0
    assert _count(postgres_db, "SELECT COUNT(*) AS n FROM shipments WHERE status = 'DELAYED' AND delay_hours <= 0") == 0
    assert _count(postgres_db, "SELECT COUNT(*) AS n FROM shipments WHERE status = 'DELAYED' AND expected_delivery_date >= CURRENT_TIMESTAMP") == 0


def test_metrics_derived_from_history(postgres_db):
    carriers = SupplyChainQueries.list_carriers()
    assert {c["mode"] for c in carriers} >= {"AIR", "ROAD", "OCEAN"}
    for carrier in carriers:
        assert 0 < float(carrier["reliability_rating"]) <= 1
        assert float(carrier["freight_cost_per_kg"]) > 0
    for supplier in SupplyChainQueries.list_suppliers():
        assert 0 <= float(supplier["reliability_rating"]) <= 1
        assert supplier["lead_time_days"] >= 1


def test_lookups_resolve_real_records(postgres_db):
    po_number = postgres_db.execute_query("SELECT po_number FROM purchase_orders WHERE id LIKE 'SCMS-%' LIMIT 1")[0]["po_number"]
    po = SupplyChainQueries.get_purchase_order(po_number)
    assert po and po["items"] and SupplyChainQueries.get_supplier(po["supplier_id"])

    order_number = postgres_db.execute_query("SELECT order_number FROM orders LIMIT 1")[0]["order_number"]
    order = SupplyChainQueries.get_order(order_number)
    assert order and order["items"] and SupplyChainQueries.get_customer(order["customer_id"])

    number = postgres_db.execute_query("SELECT shipment_number FROM shipments WHERE status = 'DELIVERED' LIMIT 1")[0]["shipment_number"]
    shipment = SupplyChainQueries.get_shipment(number)
    assert shipment and shipment["carrier_name"]

    stocked = postgres_db.execute_query("SELECT product_id FROM inventory LIMIT 1")[0]["product_id"]
    product = SupplyChainQueries.get_product(stocked)
    assert product and product["primary_supplier_id"], "grocery SKUs carry their supplier"


def test_detection_covers_every_delay_and_shortage(postgres_db):
    """Every delayed shipment and every stock line at/below safety stock has an exception."""
    uncovered_shipments = _count(postgres_db, """
        SELECT COUNT(*) AS n FROM shipments s
        WHERE s.status = 'DELAYED' AND NOT EXISTS (
            SELECT 1 FROM exceptions e
            WHERE e.shipment_id = s.id OR (s.purchase_order_id IS NOT NULL AND e.purchase_order_id = s.purchase_order_id))
    """)
    uncovered_stock = _count(postgres_db, """
        SELECT COUNT(*) AS n FROM inventory i
        WHERE i.quantity_available <= i.safety_stock AND NOT EXISTS (
            SELECT 1 FROM exceptions e WHERE e.warehouse_id = i.warehouse_id AND e.product_id = i.product_id)
    """)
    assert uncovered_shipments == 0, f"{uncovered_shipments} delayed shipments have no exception"
    assert uncovered_stock == 0, f"{uncovered_stock} shortages have no exception"
    detections = _count(postgres_db, "SELECT COUNT(*) AS n FROM audit_logs WHERE agent_step = 'DETECTION'")
    assert detections >= _count(postgres_db, "SELECT COUNT(*) AS n FROM exceptions") * 0.99
