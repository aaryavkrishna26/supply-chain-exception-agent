"""
LangGraph Agentic Investigation Workflow for Supply Chain Exceptions.
Dynamically executes an iterative investigation loop:
Load Exception -> Decide Next Step -> Execute Tool -> Observe -> Loop/Conclude
-> Root Cause Analysis -> Business Impact Analysis -> Final Pydantic Result.
"""

import json
import logging
from typing import Any, Dict, List, Optional, TypedDict
from datetime import datetime, timezone

from langgraph.graph import StateGraph, START, END

from database.queries.exceptions import ExceptionQueries
from models.schemas import InvestigationResult, InvestigationStep, BusinessImpact
from services.audit_service import AuditService
from tools import INVESTIGATION_TOOLS
from agents.llm_factory import AutonomousInvestigationReasoner, compact_for_prompt, get_llm
from agents.prompts import (
    DECIDE_NEXT_STEP_PROMPT,
    ROOT_CAUSE_ANALYSIS_PROMPT,
    BUSINESS_IMPACT_ANALYSIS_PROMPT
)

logger = logging.getLogger("investigation_agent")


class InvestigationState(TypedDict):
    exception_id: str
    exception: Dict[str, Any]
    gathered_context: Dict[str, Any]
    investigation_steps: List[Dict[str, Any]]
    tools_used: List[str]
    tool_results: Dict[str, Any]
    root_cause: Optional[str]
    evidence: List[str]
    business_impact: Optional[Dict[str, Any]]
    confidence: float
    investigation_complete: bool
    step_count: int
    max_steps: int
    next_action: Optional[Dict[str, Any]]
    result: Optional[Dict[str, Any]]


# -----------------------------------------------------------------------------
# GRAPH NODES
# -----------------------------------------------------------------------------

def load_exception_node(state: InvestigationState) -> Dict[str, Any]:
    """Fetch exception record from Supabase and initialize context."""
    exc_id = state["exception_id"]
    exc = ExceptionQueries.get_exception(exc_id)
    if not exc:
        raise ValueError(f"Exception with ID or code '{exc_id}' not found in Supabase.")

    AuditService.log_step(
        exception_id=exc["id"],
        agent_step="INVESTIGATION_STARTED",
        tool_called=None,
        input_payload={"exception_id": exc_id},
        output_payload={"title": exc["title"], "category": exc["category"], "severity": exc["severity"]},
        decision=f"Commenced agentic investigation for exception {exc['id']} ({exc['exception_code']})"
    )

    return {
        "exception": exc,
        "gathered_context": {
            "initial_exception": {
                "id": exc["id"],
                "code": exc["exception_code"],
                "category": exc["category"],
                "type": exc["exception_type"],
                "severity": exc["severity"],
                "order_id": exc.get("order_id"),
                "shipment_id": exc.get("shipment_id"),
                "purchase_order_id": exc.get("purchase_order_id"),
                "warehouse_id": exc.get("warehouse_id"),
                "product_id": exc.get("product_id"),
                "title": exc.get("title"),
                "description": exc.get("description"),
            }
        },
        "investigation_steps": [],
        "tools_used": [],
        "tool_results": {},
        "step_count": 0,
        "max_steps": state.get("max_steps", 6),
        "confidence": 0.90,
        "investigation_complete": False
    }


def decide_next_step_node(state: InvestigationState) -> Dict[str, Any]:
    """
    LLM evaluates gathered evidence against open questions and chooses next action
    (either call a tool or conclude investigation).
    """
    step_count = state["step_count"] + 1
    max_steps = state["max_steps"]
    tools_used = state["tools_used"]
    gathered_context = state["gathered_context"]
    exception = state["exception"]

    llm = get_llm()
    decision = None

    if llm:
        try:
            prompt = DECIDE_NEXT_STEP_PROMPT.format(
                exception_json=json.dumps(compact_for_prompt(exception), default=str),
                gathered_context_json=json.dumps(compact_for_prompt(gathered_context), default=str),
                tools_used=tools_used,
                step_count=step_count,
                max_steps=max_steps
            )
            response = llm.invoke(prompt)
            content = response.content
            # Extract json from markdown block if needed
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            decision = json.loads(content)
        except Exception as e:
            logger.warning(f"Remote LLM decide_next_step failed, falling back to autonomous reasoner: {e}")
            decision = None

    if not decision:
        decision = AutonomousInvestigationReasoner.decide_next_step(
            exception=exception,
            gathered_context=gathered_context,
            tools_used=tools_used,
            step_count=step_count,
            max_steps=max_steps
        )

    # Validate decision
    tool_name = decision.get("tool_name")
    if decision.get("action") == "call_tool" and (not tool_name or tool_name not in INVESTIGATION_TOOLS):
        decision["action"] = "conclude"

    return {
        "step_count": step_count,
        "next_action": decision
    }


# Argument names an LLM commonly uses for each real tool parameter.
_ARG_ALIASES = {
    "po_id": ("purchase_order_id", "po_number", "id"),
    "order_id": ("order_number", "id"),
    "shipment_id": ("shipment_number", "id"),
    "supplier_id": ("supplier", "supplier_code", "id"),
    "product_id": ("product", "sku", "id"),
    "warehouse_id": ("warehouse", "id"),
    "carrier_id": ("carrier", "id"),
}


def _normalise_tool_input(tool_func, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Map aliased arguments onto the tool's real parameters and drop unknown ones,
    so `get_purchase_order(purchase_order_id=...)` works instead of failing."""
    import inspect

    params = inspect.signature(tool_func).parameters
    given = dict(tool_input or {})
    fixed = {k: v for k, v in given.items() if k in params}
    for name in params:
        if name in fixed:
            continue
        for alias in _ARG_ALIASES.get(name, ()):
            if alias in given:
                fixed[name] = given[alias]
                break
    return fixed


def execute_tool_node(state: InvestigationState) -> Dict[str, Any]:
    """Execute the selected tool against live Supabase data and record observations."""
    next_action = state["next_action"]
    tool_name = next_action["tool_name"]
    tool_input = next_action.get("tool_input", {})
    thought = next_action.get("thought", "")

    tool_func = INVESTIGATION_TOOLS[tool_name]
    tool_input = _normalise_tool_input(tool_func, tool_input)
    try:
        raw_result = tool_func(**tool_input)
    except Exception as e:
        logger.error(f"Error executing tool {tool_name} with input {tool_input}: {e}")
        raw_result = {"error": str(e)}

    # Summary of tool result for step trace
    if isinstance(raw_result, dict):
        summary = f"Retrieved record: {raw_result.get('id', raw_result.get('name', 'OK'))}"
    elif isinstance(raw_result, list):
        summary = f"Retrieved {len(raw_result)} candidate records."
    else:
        summary = str(raw_result)[:100]

    step_info = {
        "step_number": state["step_count"],
        "thought": thought,
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_output_summary": summary,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


    AuditService.log_step(
        exception_id=state["exception"]["id"],
        agent_step="INVESTIGATION_TOOL_CALLED",
        tool_called=tool_name,
        input_payload=tool_input,
        output_payload={"summary": summary},
        decision=thought
    )

    new_gathered = dict(state["gathered_context"])
    new_gathered[tool_name] = raw_result

    new_tools_used = list(state["tools_used"])
    if tool_name not in new_tools_used:
        new_tools_used.append(tool_name)

    new_steps = list(state["investigation_steps"])
    new_steps.append(step_info)

    new_tool_results = dict(state["tool_results"])
    new_tool_results[tool_name] = raw_result

    return {
        "gathered_context": new_gathered,
        "tools_used": new_tools_used,
        "investigation_steps": new_steps,
        "tool_results": new_tool_results
    }


def analyze_root_cause_node(state: InvestigationState) -> Dict[str, Any]:
    """Perform contextual cross-functional reasoning to isolate the root cause."""
    exception = state["exception"]
    gathered_context = state["gathered_context"]

    llm = get_llm()
    rc_result = None

    if llm:
        try:
            prompt = ROOT_CAUSE_ANALYSIS_PROMPT.format(
                exception_json=json.dumps(compact_for_prompt(exception), default=str),
                gathered_context_json=json.dumps(compact_for_prompt(gathered_context), default=str)
            )
            response = llm.invoke(prompt)
            lines = [ln.strip("- *") for ln in response.content.split("\n") if ln.strip()]
            rc_result = {
                "root_cause": lines[0] if lines else "Root cause established through evidence.",
                "evidence": lines[1:5] if len(lines) > 1 else ["Substantiated by database queries."]
            }
        except Exception as e:
            logger.warning(f"Remote LLM analyze_root_cause failed, falling back to autonomous reasoner: {e}")
            rc_result = None

    if not rc_result:
        rc_result = AutonomousInvestigationReasoner.synthesize_root_cause(
            exception=exception,
            gathered_context=gathered_context
        )

    AuditService.log_step(
        exception_id=exception["id"],
        agent_step="ROOT_CAUSE_ANALYZED",
        tool_called=None,
        input_payload={"tools_used": state["tools_used"]},
        output_payload=rc_result,
        decision=f"Root cause determined: {rc_result['root_cause']}"
    )

    return {
        "root_cause": rc_result["root_cause"],
        "evidence": rc_result["evidence"]
    }


def analyze_business_impact_node(state: InvestigationState) -> Dict[str, Any]:
    """Quantify multi-dimensional impact across inventory, procurement, logistics, customer, and stockout risk."""
    exception = state["exception"]
    gathered_context = state["gathered_context"]

    llm = get_llm()
    impact_result = None

    if llm:
        try:
            prompt = BUSINESS_IMPACT_ANALYSIS_PROMPT.format(
                exception_json=json.dumps(compact_for_prompt(exception), default=str),
                gathered_context_json=json.dumps(compact_for_prompt(gathered_context), default=str)
            )
            response = llm.invoke(prompt)
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            impact_result = json.loads(content)
        except Exception as e:
            logger.warning(f"Remote LLM analyze_business_impact failed, falling back to autonomous reasoner: {e}")
            impact_result = None

    if not impact_result:
        impact_result = AutonomousInvestigationReasoner.synthesize_business_impact(
            exception=exception,
            gathered_context=gathered_context
        )

    AuditService.log_step(
        exception_id=exception["id"],
        agent_step="BUSINESS_IMPACT_ANALYZED",
        tool_called=None,
        input_payload={"root_cause": state["root_cause"]},
        output_payload=impact_result,
        decision=f"Evaluated business impact: stockout risk {impact_result['stockout_risk']}"
    )

    return {
        "business_impact": impact_result
    }


def synthesize_result_node(state: InvestigationState) -> Dict[str, Any]:
    """Construct and validate final structured Pydantic InvestigationResult."""
    exc = state["exception"]
    gathered = state["gathered_context"]
    impact = state["business_impact"] or {}

    # Extract relevant entities
    relevant_suppliers = []
    if "get_supplier" in gathered and gathered["get_supplier"]:
        relevant_suppliers.append(gathered["get_supplier"])
    if "find_alternative_supplier" in gathered and gathered["find_alternative_supplier"]:
        relevant_suppliers.extend(gathered["find_alternative_supplier"][:2])

    relevant_warehouses = []
    if "get_warehouse" in gathered and gathered["get_warehouse"]:
        relevant_warehouses.append(gathered["get_warehouse"])
    if "find_available_inventory" in gathered and gathered["find_available_inventory"]:
        for inv in gathered["find_available_inventory"][:4]:
            relevant_warehouses.append({
                "warehouse_id": inv.get("warehouse_id"),
                "warehouse_name": inv.get("warehouse_name"),
                "city": inv.get("warehouse_city"),
                "quantity_available": inv.get("quantity_available"),
                "product_id": inv.get("product_id")
            })

    relevant_shipments = []
    if "get_delivery_status" in gathered and gathered["get_delivery_status"]:
        relevant_shipments.append(gathered["get_delivery_status"])
    elif "get_shipment" in gathered and gathered["get_shipment"]:
        relevant_shipments.append(gathered["get_shipment"])

    # Convert raw steps to Pydantic InvestigationStep
    typed_steps = []
    for s in state["investigation_steps"]:
        typed_steps.append(InvestigationStep(
            step_number=s["step_number"],
            thought=s["thought"],
            tool_name=s["tool_name"],
            tool_input=s["tool_input"],
            tool_output_summary=s["tool_output_summary"],
            timestamp=datetime.fromisoformat(s["timestamp"]) if isinstance(s["timestamp"], str) else s["timestamp"]
        ))

    result_model = InvestigationResult(
        exception_id=exc["id"],
        exception_type=exc["exception_type"],
        severity=exc["severity"],
        root_cause=state["root_cause"] or "Investigated and root cause determined.",
        evidence=state["evidence"],
        inventory_impact=impact.get("inventory_impact", "Inventory analyzed."),
        procurement_impact=impact.get("procurement_impact", "Procurement analyzed."),
        logistics_impact=impact.get("logistics_impact", "Logistics analyzed."),
        customer_impact=impact.get("customer_impact", "Customer impact analyzed."),
        stockout_risk=impact.get("stockout_risk", "MEDIUM"),
        relevant_suppliers=relevant_suppliers,
        relevant_warehouses=relevant_warehouses,
        relevant_shipments=relevant_shipments,
        investigation_steps=typed_steps,
        tools_used=state["tools_used"],
        confidence=state["confidence"],
        investigation_complete=True
    )

    # Update exception record in Supabase
    impact_summary = (
        f"Stockout Risk: {result_model.stockout_risk} | "
        f"Customer: {result_model.customer_impact} | "
        f"Inventory: {result_model.inventory_impact}"
    )
    ExceptionQueries.update_exception_status(
        exception_id=exc["id"],
        status="INVESTIGATING",
        root_cause=result_model.root_cause,
        business_impact=impact_summary
    )

    AuditService.log_step(
        exception_id=exc["id"],
        agent_step="INVESTIGATION_COMPLETED",
        tool_called=None,
        input_payload={"steps_count": len(state["investigation_steps"]), "tools_used": state["tools_used"]},
        output_payload={"root_cause": result_model.root_cause, "confidence": result_model.confidence},
        decision="Investigation finalized and persisted to Supabase."
    )

    return {
        "result": result_model.model_dump(),
        "investigation_complete": True
    }


# -----------------------------------------------------------------------------
# CONDITIONAL ROUTING
# -----------------------------------------------------------------------------

def should_continue(state: InvestigationState) -> str:
    """Route to tool execution or proceed to synthesis based on agent decision."""
    next_action = state.get("next_action") or {}
    if next_action.get("action") == "call_tool" and state.get("step_count", 0) < state.get("max_steps", 6):
        return "execute_tool"
    return "analyze_root_cause"


# -----------------------------------------------------------------------------
# GRAPH COMPILATION
# -----------------------------------------------------------------------------

def create_investigation_graph():
    """Build and compile the LangGraph agent state machine."""
    workflow = StateGraph(InvestigationState)

    # Add Nodes
    workflow.add_node("load_exception", load_exception_node)
    workflow.add_node("decide_next_step", decide_next_step_node)
    workflow.add_node("execute_tool", execute_tool_node)
    workflow.add_node("analyze_root_cause", analyze_root_cause_node)
    workflow.add_node("analyze_business_impact", analyze_business_impact_node)
    workflow.add_node("synthesize_result", synthesize_result_node)

    # Add Edges
    workflow.add_edge(START, "load_exception")
    workflow.add_edge("load_exception", "decide_next_step")

    # Conditional branching from decide_next_step
    workflow.add_conditional_edges(
        "decide_next_step",
        should_continue,
        {
            "execute_tool": "execute_tool",
            "analyze_root_cause": "analyze_root_cause"
        }
    )

    # Tool loops back to decide_next_step
    workflow.add_edge("execute_tool", "decide_next_step")

    # Synthesis pipeline
    workflow.add_edge("analyze_root_cause", "analyze_business_impact")
    workflow.add_edge("analyze_business_impact", "synthesize_result")
    workflow.add_edge("synthesize_result", END)

    return workflow.compile()


investigation_graph = create_investigation_graph()
