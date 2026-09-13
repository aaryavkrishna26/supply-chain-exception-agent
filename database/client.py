"""
Database client connection and query execution layer.
Primary and sole source of truth backend: Supabase hosted PostgreSQL.
"""

import os
import logging
import importlib
from typing import Any, Dict, List, Optional
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text, Engine

# Load environment variables from .env
load_dotenv()

logger = logging.getLogger(__name__)

# Flexible environment variable resolution supporting all standard Supabase aliases
def get_env_var(*keys: str, default: str = "") -> str:
    for k in keys:
        val = os.getenv(k, "").strip()
        if val:
            return val
    return default

SUPABASE_URL = get_env_var("SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = get_env_var("SUPABASE_KEY", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY")
SUPABASE_DB_URL = get_env_var("SUPABASE_DB_URL", "DATABASE_URL", "POSTGRES_URL", "SUPABASE_DATABASE_URL", "SUPABASE_POSTGRES_URL")


class ConfigurationError(RuntimeError):
    """Raised when required Supabase/PostgreSQL configuration is missing or invalid."""
    pass


class DatabaseClient:
    _instance: Optional["DatabaseClient"] = None

    def __init__(self, db_url: Optional[str] = None):
        # Refresh environment on init if not already set
        load_dotenv()
        self.db_url = db_url or get_env_var("SUPABASE_DB_URL", "DATABASE_URL", "POSTGRES_URL", "SUPABASE_DATABASE_URL", "SUPABASE_POSTGRES_URL")
        self.supabase_url = get_env_var("SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_URL")
        self.supabase_key = get_env_var("SUPABASE_KEY", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY")
        
        self.engine: Optional[Engine] = None
        self.supabase = None
        self.is_connected = False
        self._init_connection()

    @classmethod
    def get_instance(cls, db_url: Optional[str] = None) -> "DatabaseClient":
        if cls._instance is None or db_url is not None:
            cls._instance = DatabaseClient(db_url)
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset singleton instance."""
        cls._instance = None

    def _init_connection(self):
        """Initialize database connections (Supabase REST client + PostgreSQL SQLAlchemy engine)."""
        is_placeholder_url = not self.db_url or "your-project-ref" in self.db_url or "your-db-password" in self.db_url
        
        if is_placeholder_url:
            if not self.supabase_url or not self.supabase_key or "your-project-ref" in self.supabase_url:
                raise ConfigurationError(
                    "Missing Supabase PostgreSQL configuration.\n"
                    "Please save .env with valid credentials:\n"
                    "  SUPABASE_DB_URL=postgresql://postgres.<project-ref>:<password>@aws-0-us-east-1.pooler.supabase.com:6543/postgres\n"
                    "  SUPABASE_URL=https://<project-ref>.supabase.co\n"
                    "  SUPABASE_KEY=<your-supabase-key>\n"
                    "Refer to .env.example for details."
                )

        # 1. Initialize Supabase REST client if configured
        if self.supabase_url and self.supabase_key and not "your-project-ref" in self.supabase_url:
            try:
                supabase_pkg = importlib.import_module("supabase")
                create_client_fn = getattr(supabase_pkg, "create_client")
                self.supabase = create_client_fn(self.supabase_url, self.supabase_key)
                logger.info("Supabase REST client initialized successfully.")
            except Exception as e:
                logger.warning(f"Note: Supabase REST client initialization: {e}")
                self.supabase = None

        # 2. Initialize PostgreSQL SQLAlchemy Engine
        try:
            self.engine = create_engine(
                self.db_url,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=10,
            )
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1;"))
            self.is_connected = True
            logger.info("Supabase PostgreSQL engine connected successfully.")
        except Exception as e:
            self.is_connected = False
            raise RuntimeError(
                f"Failed to connect to Supabase PostgreSQL database.\n"
                f"Underlying error: {e}\n"
                f"Please verify your SUPABASE_DB_URL / DATABASE_URL and network access."
            ) from e

    def test_connection(self) -> Dict[str, Any]:
        """Test active database connectivity and return status details."""
        status = {
            "connected": False,
            "backend": "postgresql",
            "is_supabase_connected": self.supabase is not None,
            "error": None
        }
        if self.engine:
            try:
                with self.engine.connect() as conn:
                    result = conn.execute(text("SELECT 1;")).scalar()
                    if result == 1:
                        status["connected"] = True
            except Exception as e:
                status["error"] = str(e)
        return status

    def execute_query(self, sql: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Execute a SELECT query and return results as list of dictionaries."""
        if not self.engine:
            raise RuntimeError("Database engine is not initialized. Check Supabase connection settings.")
        
        with self.engine.connect() as conn:
            stmt = text(sql)
            result = conn.execute(stmt, params or {})
            if result.returns_rows:
                columns = result.keys()
                return [dict(zip(columns, row)) for row in result.fetchall()]
            return []

    def execute_statement(self, sql: str, params: Optional[Dict[str, Any]] = None) -> int:
        """Execute an INSERT/UPDATE/DELETE/DDL statement and return affected rows."""
        if not self.engine:
            raise RuntimeError("Database engine is not initialized. Check Supabase connection settings.")
        
        with self.engine.begin() as conn:
            stmt = text(sql)
            result = conn.execute(stmt, params or {})
            return result.rowcount if hasattr(result, "rowcount") else 0

    def execute_many(self, sql: str, params_list: List[Dict[str, Any]]) -> int:
        """Execute the same INSERT/UPDATE statement for many parameter sets in one round-trip."""
        if not self.engine:
            raise RuntimeError("Database engine is not initialized. Check Supabase connection settings.")
        if not params_list:
            return 0

        with self.engine.begin() as conn:
            stmt = text(sql)
            result = conn.execute(stmt, params_list)
            return result.rowcount if hasattr(result, "rowcount") else len(params_list)

    def initialize_schema(self, schema_file: Optional[str] = None):
        """Apply the PostgreSQL DDL schema directly to the database."""
        if not schema_file:
            schema_file = str(Path(__file__).resolve().parent / "schema.sql")
        
        with open(schema_file, "r", encoding="utf-8") as f:
            ddl_content = f.read()

        if not self.engine:
            raise RuntimeError("Database engine is not initialized.")

        with self.engine.begin() as conn:
            conn.execute(text(ddl_content))
        
        logger.info("PostgreSQL database schema initialized successfully.")


# Global helper functions
def get_db() -> DatabaseClient:
    return DatabaseClient.get_instance()
