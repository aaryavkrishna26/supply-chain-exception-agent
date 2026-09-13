"""
Audit Logging Service for recording agent steps, tool executions, and human decisions.
"""

import uuid
import logging
from typing import Any, Dict, Optional
from database.client import get_db
from database.queries.exceptions import ExceptionQueries

logger = logging.getLogger("audit_service")


class AuditService:

    @staticmethod
    def log_step(
        exception_id: Optional[str],
        agent_step: str,
        tool_called: Optional[str] = None,
        input_payload: Optional[Dict[str, Any]] = None,
        output_payload: Optional[Dict[str, Any]] = None,
        decision: Optional[str] = None,
        human_approval_status: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> str:
        """Record an audit trail entry in the database."""
        log_id = f"AUD-{uuid.uuid4().hex[:8].upper()}"
        record = {
            "id": log_id,
            "exception_id": exception_id,
            "agent_step": agent_step,
            "tool_called": tool_called,
            "input_payload": input_payload or {},
            "output_payload": output_payload or {},
            "decision": decision,
            "human_approval_status": human_approval_status,
            "notes": notes,
        }
        try:
            ExceptionQueries.record_audit_log(record)
            logger.info(f"[AUDIT] {agent_step} | Exception: {exception_id} | Tool: {tool_called}")
        except Exception as e:
            logger.error(f"Failed to record audit log: {e}")
        return log_id
