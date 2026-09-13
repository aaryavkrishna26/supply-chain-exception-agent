"""
Investigation Service providing a clean interface for executing
LangGraph-based agentic supply-chain investigations.
"""

import logging
from typing import Any, Dict, List, Optional
from models.schemas import InvestigationResult
from database.queries.exceptions import ExceptionQueries

logger = logging.getLogger("investigation_service")


class InvestigationService:

    @staticmethod
    def investigate(exception_id_or_code: str, max_steps: int = 4) -> InvestigationResult:
        """
        Execute an agentic investigation for a given exception using LangGraph.
        Loads the exception from Supabase, runs the dynamic tool loop, performs root cause
        and cross-functional business impact analysis, and returns a structured InvestigationResult.
        """
        logger.info(f"Starting agentic investigation for exception: {exception_id_or_code}")

        # Resolve exception id if code was passed
        exc = ExceptionQueries.get_exception(exception_id_or_code)
        if not exc:
            raise ValueError(f"Exception '{exception_id_or_code}' not found in Supabase.")

        initial_state = {
            "exception_id": exc["id"],
            "max_steps": max_steps,
            "step_count": 0,
            "tools_used": [],
            "investigation_steps": [],
            "gathered_context": {},
            "tool_results": {},
            "root_cause": None,
            "evidence": [],
            "business_impact": None,
            "confidence": 0.90,
            "investigation_complete": False,
            "next_action": None,
            "result": None,
        }

        # Run LangGraph state machine
        from agents.investigation_agent import investigation_graph
        final_state = investigation_graph.invoke(initial_state)

        result_dict = final_state.get("result")
        if not result_dict:
            raise RuntimeError("Investigation completed without generating structured result.")

        return InvestigationResult.model_validate(result_dict)

    @staticmethod
    def get_audit_trail(exception_id: str) -> List[Dict[str, Any]]:
        """Retrieve full audit log steps for an exception."""
        exc = ExceptionQueries.get_exception(exception_id)
        if not exc:
            return []
        return exc.get("audit_logs", [])
