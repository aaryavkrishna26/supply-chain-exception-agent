"""
Exception, Resolution Option, Action, and Audit Log query methods.
"""

import json
from typing import Any, Dict, List, Optional
from database.client import get_db


class ExceptionQueries:

    @staticmethod
    def create_exception(data: Dict[str, Any]) -> str:
        db = get_db()
        sql = """
            INSERT INTO exceptions (
                id, exception_code, category, exception_type, severity, status,
                order_id, shipment_id, purchase_order_id, warehouse_id, product_id,
                title, description, detected_at, estimated_financial_loss
            ) VALUES (
                :id, :exception_code, :category, :exception_type, :severity, :status,
                :order_id, :shipment_id, :purchase_order_id, :warehouse_id, :product_id,
                :title, :description, CURRENT_TIMESTAMP, :estimated_financial_loss
            )
        """
        db.execute_statement(sql, data)
        return data["id"]

    @staticmethod
    def get_exception(exception_id_or_code: str) -> Optional[Dict[str, Any]]:
        db = get_db()
        sql = "SELECT * FROM exceptions WHERE id = :val OR exception_code = :val"
        results = db.execute_query(sql, {"val": exception_id_or_code})
        if not results:
            return None
        exc = results[0]
        # Include resolution options if present
        options = db.execute_query("SELECT * FROM resolution_options WHERE exception_id = :eid", {"eid": exc["id"]})
        exc["resolution_options"] = options
        # Include audit logs
        logs = db.execute_query("SELECT * FROM audit_logs WHERE exception_id = :eid ORDER BY created_at ASC", {"eid": exc["id"]})
        exc["audit_logs"] = logs
        return exc

    @staticmethod
    def list_exceptions(
        category: Optional[str] = None,
        status: Optional[str] = None,
        severity: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        db = get_db()
        clauses = []
        params = {}
        if category:
            clauses.append("category = :category")
            params["category"] = category
        if status:
            clauses.append("status = :status")
            params["status"] = status
        if severity:
            clauses.append("severity = :severity")
            params["severity"] = severity

        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM exceptions {where_clause} ORDER BY detected_at DESC"
        return db.execute_query(sql, params)

    @staticmethod
    def update_exception_status(exception_id: str, status: str, root_cause: Optional[str] = None, business_impact: Optional[str] = None):
        db = get_db()
        params: Dict[str, Any] = {"id": exception_id, "status": status}
        set_clauses = ["status = :status", "updated_at = CURRENT_TIMESTAMP"]
        
        if root_cause is not None:
            set_clauses.append("root_cause = :root_cause")
            params["root_cause"] = root_cause
        if business_impact is not None:
            set_clauses.append("business_impact = :business_impact")
            params["business_impact"] = business_impact
        if status == "RESOLVED":
            set_clauses.append("resolved_at = CURRENT_TIMESTAMP")

        sql = f"UPDATE exceptions SET {', '.join(set_clauses)} WHERE id = :id"
        db.execute_statement(sql, params)

    @staticmethod
    def add_resolution_option(data: Dict[str, Any]) -> str:
        db = get_db()
        if isinstance(data.get("parameters"), dict):
            data["parameters"] = json.dumps(data["parameters"])
        sql = """
            INSERT INTO resolution_options (
                id, exception_id, option_name, action_type, description,
                estimated_cost, expected_time_hours, inventory_impact, customer_impact,
                operational_risk, feasibility, confidence_score, reasoning,
                is_recommended, is_selected, parameters
            ) VALUES (
                :id, :exception_id, :option_name, :action_type, :description,
                :estimated_cost, :expected_time_hours, :inventory_impact, :customer_impact,
                :operational_risk, :feasibility, :confidence_score, :reasoning,
                :is_recommended, :is_selected, :parameters
            )
        """
        db.execute_statement(sql, data)
        return data["id"]

    @staticmethod
    def record_action(data: Dict[str, Any]) -> str:
        db = get_db()
        if isinstance(data.get("payload"), dict):
            data["payload"] = json.dumps(data["payload"])
        sql = """
            INSERT INTO actions (
                id, exception_id, resolution_option_id, action_type,
                executed_by, execution_status, payload, result_message, executed_at
            ) VALUES (
                :id, :exception_id, :resolution_option_id, :action_type,
                :executed_by, :execution_status, :payload, :result_message, CURRENT_TIMESTAMP
            )
        """
        db.execute_statement(sql, data)
        return data["id"]

    @staticmethod
    def record_audit_log(data: Dict[str, Any]) -> str:
        db = get_db()
        if isinstance(data.get("input_payload"), dict):
            data["input_payload"] = json.dumps(data["input_payload"])
        if isinstance(data.get("output_payload"), dict):
            data["output_payload"] = json.dumps(data["output_payload"])
        sql = """
            INSERT INTO audit_logs (
                id, exception_id, agent_step, tool_called,
                input_payload, output_payload, decision, human_approval_status, notes, created_at
            ) VALUES (
                :id, :exception_id, :agent_step, :tool_called,
                :input_payload, :output_payload, :decision, :human_approval_status, :notes, CURRENT_TIMESTAMP
            )
        """
        db.execute_statement(sql, data)
        return data["id"]

    @staticmethod
    def get_resolution_option(option_id: str) -> Optional[Dict[str, Any]]:
        db = get_db()
        sql = "SELECT * FROM resolution_options WHERE id = :id"
        rows = db.execute_query(sql, {"id": option_id})
        if not rows:
            return None
        opt = rows[0]
        if isinstance(opt.get("parameters"), str):
            try:
                opt["parameters"] = json.loads(opt["parameters"])
            except Exception:
                pass
        return opt

    @staticmethod
    def list_resolution_options(exception_id: str) -> List[Dict[str, Any]]:
        db = get_db()
        sql = "SELECT * FROM resolution_options WHERE exception_id = :eid ORDER BY is_recommended DESC, estimated_cost ASC"
        options = db.execute_query(sql, {"eid": exception_id})
        for opt in options:
            if isinstance(opt.get("parameters"), str):
                try:
                    opt["parameters"] = json.loads(opt["parameters"])
                except Exception:
                    pass
        return options

    @staticmethod
    def mark_resolution_option_selected(option_id: str):
        db = get_db()
        opt = ExceptionQueries.get_resolution_option(option_id)
        if not opt:
            raise ValueError(f"Resolution option {option_id} not found.")
        # Unselect all other options for this exception
        db.execute_statement(
            "UPDATE resolution_options SET is_selected = FALSE WHERE exception_id = :eid",
            {"eid": opt["exception_id"]}
        )
        # Select this option
        db.execute_statement(
            "UPDATE resolution_options SET is_selected = TRUE WHERE id = :id",
            {"id": option_id}
        )

    @staticmethod
    def has_action_for_option(option_id: str) -> bool:
        """Check whether an action has already succeeded for this resolution option to prevent duplicate execution."""
        db = get_db()
        sql = "SELECT id FROM actions WHERE resolution_option_id = :oid AND execution_status = 'SUCCESS'"
        rows = db.execute_query(sql, {"oid": option_id})
        return len(rows) > 0

    @staticmethod
    def get_action(action_id: str) -> Optional[Dict[str, Any]]:
        db = get_db()
        sql = "SELECT * FROM actions WHERE id = :id"
        rows = db.execute_query(sql, {"id": action_id})
        if not rows:
            return None
        action = rows[0]
        if isinstance(action.get("payload"), str):
            try:
                action["payload"] = json.loads(action["payload"])
            except Exception:
                pass
        return action

    @staticmethod
    def get_actions_for_exception(exception_id: str) -> List[Dict[str, Any]]:
        db = get_db()
        sql = "SELECT * FROM actions WHERE exception_id = :eid ORDER BY executed_at DESC"
        actions = db.execute_query(sql, {"eid": exception_id})
        for act in actions:
            if isinstance(act.get("payload"), str):
                try:
                    act["payload"] = json.loads(act["payload"])
                except Exception:
                    pass
        return actions

    @staticmethod
    def list_all_audit_logs(limit: int = 100, exception_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve audit logs joined with exception metadata for the audit dashboard."""
        db = get_db()
        if exception_id:
            sql = """
                SELECT a.*, e.exception_code, e.title as exception_title, e.category as exception_category, e.severity as exception_severity
                FROM audit_logs a
                LEFT JOIN exceptions e ON a.exception_id = e.id
                WHERE a.exception_id = :eid
                ORDER BY a.created_at DESC
                LIMIT :limit
            """
            logs = db.execute_query(sql, {"eid": exception_id, "limit": limit})
        else:
            sql = """
                SELECT a.*, e.exception_code, e.title as exception_title, e.category as exception_category, e.severity as exception_severity
                FROM audit_logs a
                LEFT JOIN exceptions e ON a.exception_id = e.id
                ORDER BY a.created_at DESC
                LIMIT :limit
            """
            logs = db.execute_query(sql, {"limit": limit})

        for log in logs:
            if isinstance(log.get("input_payload"), str):
                try:
                    log["input_payload"] = json.loads(log["input_payload"])
                except Exception:
                    pass
            if isinstance(log.get("output_payload"), str):
                try:
                    log["output_payload"] = json.loads(log["output_payload"])
                except Exception:
                    pass
        return logs

    @staticmethod
    def update_exception_purchase_order(exception_id: str, purchase_order_id: str):
        """Link an exception to an existing purchase order."""
        db = get_db()
        db.execute_statement(
            "UPDATE exceptions SET purchase_order_id = :poid, updated_at = CURRENT_TIMESTAMP WHERE id = :id",
            {"poid": purchase_order_id, "id": exception_id}
        )

    @staticmethod
    def update_resolution_option_parameters(option_id: str, parameters: Dict[str, Any]):
        """Update the parameters payload of a resolution option in database."""
        db = get_db()
        payload = json.dumps(parameters) if isinstance(parameters, dict) else parameters
        db.execute_statement(
            "UPDATE resolution_options SET parameters = :params WHERE id = :id",
            {"params": payload, "id": option_id}
        )


