"""
Agent tests against the live Kaggle-loaded database.

Exceptions are picked from what the detector actually found, not from fixed demo
IDs. Every database WRITE the agent would make (audit entries, status changes,
persisted options) is stubbed out, so these tests leave the data untouched.
Investigations use the configured LLM when a key is present, and otherwise the
deterministic reasoner.

- Tool registry executing against real records
- Exception loading by code and by ID
- Investigation of a real inventory shortage and a real shipment delay
- Resolution planning that proposes grounded, executable options
"""

import pytest

from database.client import DatabaseClient, get_db
from database.queries.exceptions import ExceptionQueries
from database.queries.supply_chain import SupplyChainQueries
from models.schemas import InvestigationResult, InvestigationStep
from tools import INVESTIGATION_TOOLS, find_available_inventory, get_order, get_purchase_order, get_shipment


@pytest.fixture(scope="module")
def live_db():
    DatabaseClient.reset_instance()
    try:
        db = get_db()
    except Exception as err:
        pytest.skip(f"Supabase not configured: {err}")
    if not db.test_connection()["connected"]:
        pytest.skip("Supabase database unreachable")
    if not db.execute_query("SELECT 1 FROM exceptions LIMIT 1"):
        pytest.skip("No exceptions detected — load data with `python -m data.kaggle_import`.")
    return db


@pytest.fixture
def no_writes(monkeypatch):
    """Block every write the agent would make, so tests never alter the data."""
    from database.client import DatabaseClient as Client
    from services.audit_service import AuditService

    def _blocked(self, sql, params=None):
        raise AssertionError(f"unexpected database write during a read-only test: {' '.join(sql.split())[:80]}")

    monkeypatch.setattr(Client, "execute_statement", _blocked)
    monkeypatch.setattr(AuditService, "log_step", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(ExceptionQueries, "update_exception_status", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(ExceptionQueries, "add_resolution_option", staticmethod(lambda data: data["id"]))


def _exception_of(db, exception_type):
    rows = db.execute_query(
        "SELECT id FROM exceptions WHERE exception_type = :t AND status = 'OPEN' "
        "ORDER BY estimated_financial_loss DESC LIMIT 1",
        {"t": exception_type},
    )
    if not rows:
        pytest.skip(f"No open {exception_type} exception in the current data")
    return ExceptionQueries.get_exception(rows[0]["id"])


def test_tool_registry_and_live_execution(live_db):
    assert len(INVESTIGATION_TOOLS) == 16, f"Expected 16 tools, found {len(INVESTIGATION_TOOLS)}"

    order_number = live_db.execute_query("SELECT order_number FROM orders LIMIT 1")[0]["order_number"]
    order = get_order(order_number)
    assert order and "items" in order and order.get("customer_tier")

    po_number = live_db.execute_query("SELECT po_number FROM purchase_orders LIMIT 1")[0]["po_number"]
    po = get_purchase_order(po_number)
    assert po and po["supplier_id"]

    number = live_db.execute_query("SELECT shipment_number FROM shipments LIMIT 1")[0]["shipment_number"]
    shipment = get_shipment(number)
    assert shipment and "carrier_name" in shipment

    product_id = live_db.execute_query(
        "SELECT product_id FROM inventory WHERE quantity_available > 0 LIMIT 1"
    )[0]["product_id"]
    assert find_available_inventory(product_id), "stocked product should be found in the network"


def test_real_exception_loading(live_db):
    code = live_db.execute_query("SELECT exception_code FROM exceptions LIMIT 1")[0]["exception_code"]
    by_code = ExceptionQueries.get_exception(code)
    assert by_code is not None
    by_id = ExceptionQueries.get_exception(by_code["id"])
    assert by_id and by_id["id"] == by_code["id"]


def _assert_investigation(result, exception_type):
    assert isinstance(result, InvestigationResult)
    assert result.investigation_complete is True
    assert result.exception_type == exception_type
    assert len(result.tools_used) >= 2
    assert result.root_cause and len(result.root_cause.strip()) > 10
    assert result.stockout_risk in ("CRITICAL", "HIGH", "MEDIUM", "LOW")
    for step in result.investigation_steps:
        assert isinstance(step, InvestigationStep)
        assert step.tool_name in INVESTIGATION_TOOLS


def test_investigates_a_real_inventory_shortage(live_db, no_writes):
    from services.investigation_service import InvestigationService

    exc = _exception_of(live_db, "INVENTORY_SHORTAGE")
    result = InvestigationService.investigate(exc["id"], max_steps=6)
    _assert_investigation(result, "INVENTORY_SHORTAGE")


def test_investigates_a_real_shipment_delay(live_db, no_writes):
    from services.investigation_service import InvestigationService

    exc = _exception_of(live_db, "SHIPMENT_DELAY")
    result = InvestigationService.investigate(exc["id"], max_steps=6)
    _assert_investigation(result, "SHIPMENT_DELAY")
    assert "get_delivery_status" in result.tools_used or "get_shipment" in result.tools_used


def test_shortage_resolution_offers_a_grounded_replenishment(live_db):
    """The deterministic reasoner sizes a replenishment PO from real stock and supplier data."""
    from agents.resolution_agent import AutonomousResolutionReasoner, gather_resolution_context_node

    exc = _exception_of(live_db, "INVENTORY_SHORTAGE")
    context = gather_resolution_context_node({
        "exception_id": exc["id"],
        "investigation_result": {"exception_type": "INVENTORY_SHORTAGE"},
    })["live_context"]
    options = AutonomousResolutionReasoner.generate_options(
        investigation={"exception_type": "INVENTORY_SHORTAGE"}, live_context=context
    )
    replenish = [o for o in options if o["action_type"] == "REPLENISHMENT_PO"]
    assert replenish, f"no replenishment option; got {[o['action_type'] for o in options]}"
    params = replenish[0]["parameters"]
    assert SupplyChainQueries.get_product(params["product_id"])
    assert SupplyChainQueries.get_supplier(params["supplier_id"])
    assert SupplyChainQueries.get_warehouse(params["destination_warehouse_id"])
    assert params["quantity"] > 0
    item = SupplyChainQueries.get_inventory_item(params["destination_warehouse_id"], params["product_id"])
    assert params["quantity"] == item["reorder_point"] + item["safety_stock"] - item["quantity_available"] - item["quantity_in_transit"]


def test_resolution_planning_end_to_end(live_db, no_writes):
    """Full resolution graph (LLM when configured) on a real shortage returns a recommendation."""
    from services.resolution_service import ResolutionService

    exc = _exception_of(live_db, "INVENTORY_SHORTAGE")
    result = ResolutionService.plan_resolution({
        "exception_id": exc["id"],
        "exception_type": exc["exception_type"],
        "severity": exc["severity"],
        "root_cause": exc["description"],
        "inventory_impact": exc["description"],
        "procurement_impact": "Replenishment needed from the usual supplier.",
        "logistics_impact": "None.",
        "customer_impact": "Shortage risk for customer orders.",
        "stockout_risk": "HIGH",
    })
    assert result.recommended_option is not None
    assert result.recommended_option.action_type in (
        "REPLENISHMENT_PO", "INVENTORY_TRANSFER", "SUPPLIER_SWITCH", "EXPEDITE_PO", "WAIT_AND_MONITOR"
    )
