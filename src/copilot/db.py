"""
db.py -- Database connection and guarded query execution.

Provides:
1. get_engine() — SQLAlchemy engine for the read-only role
2. execute_safe_query() — validates SQL through sql_guard, then executes with row limit
3. get_schema_info() — returns schema metadata for the agent's system prompt
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from copilot.config import get_settings
from copilot.sql_guard import validate_sql, ALLOWED_TABLES

logger = logging.getLogger(__name__)

_engine: Engine | None = None


def get_engine(*, readonly: bool = True) -> Engine:
    """
    Get a SQLAlchemy engine.

    Args:
        readonly: If True, use the read-only connection (copilot_reader role).
                  If False, use the admin connection (for setup scripts only).
    """
    global _engine

    settings = get_settings()
    url = settings.database_url_readonly if readonly else settings.database_url

    if _engine is None or not readonly:
        _engine = create_engine(
            url,
            pool_size=3,
            max_overflow=2,
            pool_timeout=10,
            pool_recycle=300,
            echo=False,
        )
    return _engine


def execute_safe_query(
    sql: str,
    *,
    row_limit: int | None = None,
) -> dict[str, Any]:
    """
    Validate and execute a SQL query safely.

    Pipeline:
    1. Run sql_guard.validate_sql() to check the AST
    2. If safe, execute via the read-only engine with a row limit
    3. Return results as a dict with rows, columns, and metadata

    Args:
        sql: The SQL query string to validate and execute
        row_limit: Max rows to return (defaults to settings.agent_sql_row_limit)

    Returns:
        dict with keys:
        - "success": bool
        - "rows": list of dicts (column_name -> value)
        - "columns": list of column names
        - "row_count": number of rows returned
        - "truncated": True if results were capped by row_limit
        - "error": error message if not successful
        - "guard_result": the GuardResult details
    """
    settings = get_settings()
    if row_limit is None:
        row_limit = settings.agent_sql_row_limit

    # Step 1: Validate with sql_guard
    guard = validate_sql(sql)

    if not guard.is_safe:
        logger.warning("SQL BLOCKED: %s | Reason: %s", sql[:200], guard.reason)
        return {
            "success": False,
            "error": f"Query rejected by safety guard: {guard.reason}",
            "rows": [],
            "columns": [],
            "row_count": 0,
            "truncated": False,
            "guard_result": {
                "is_safe": False,
                "reason": guard.reason,
                "tables_used": guard.tables_used,
            },
        }

    # Step 2: Execute the query
    engine = get_engine(readonly=True)

    try:
        with engine.connect() as conn:
            result = conn.execute(text(guard.sql))
            columns = list(result.keys())
            all_rows = result.fetchmany(row_limit + 1)  # fetch one extra to detect truncation

            truncated = len(all_rows) > row_limit
            rows = all_rows[:row_limit]

            # Convert to list of dicts for serialization
            row_dicts = [dict(zip(columns, row)) for row in rows]

            logger.info(
                "SQL executed: %d rows returned (truncated=%s), tables=%s",
                len(row_dicts), truncated, guard.tables_used,
            )

            return {
                "success": True,
                "rows": row_dicts,
                "columns": columns,
                "row_count": len(row_dicts),
                "truncated": truncated,
                "error": None,
                "guard_result": {
                    "is_safe": True,
                    "tables_used": guard.tables_used,
                    "columns_used": guard.columns_used,
                },
            }

    except Exception as e:
        error_msg = str(e)
        # Don't leak internal details — provide a safe error message
        if "statement timeout" in error_msg.lower():
            safe_error = "Query timed out (5 second limit). Simplify the query."
        elif "permission denied" in error_msg.lower():
            safe_error = "Permission denied. You can only query the allowed views."
        else:
            safe_error = f"Database error: {error_msg[:300]}"

        logger.error("SQL execution error: %s", error_msg[:500])
        return {
            "success": False,
            "error": safe_error,
            "rows": [],
            "columns": [],
            "row_count": 0,
            "truncated": False,
            "guard_result": {
                "is_safe": True,  # guard passed, but execution failed
                "tables_used": guard.tables_used,
            },
        }


def get_schema_info() -> str:
    """
    Return a formatted schema description for the agent's system prompt.

    This tells the LLM what tables and columns exist, so it can write correct SQL.
    Only includes the allowed views (no base tables, no PII columns).
    """
    engine = get_engine(readonly=True)
    lines = ["DATABASE SCHEMA (PostgreSQL, read-only views):", ""]

    try:
        with engine.connect() as conn:
            for table_name in sorted(ALLOWED_TABLES):
                # Get column info
                result = conn.execute(text(
                    "SELECT column_name, data_type, is_nullable "
                    "FROM information_schema.columns "
                    "WHERE table_name = :tbl AND table_schema = 'public' "
                    "ORDER BY ordinal_position"
                ), {"tbl": table_name})

                cols = result.fetchall()
                if not cols:
                    continue

                # Get row count
                count_result = conn.execute(text(f"SELECT count(*) FROM {table_name}"))
                row_count = count_result.scalar()

                lines.append(f"TABLE: {table_name} ({row_count} rows)")
                lines.append("-" * 50)
                for col_name, data_type, nullable in cols:
                    null_str = "NULL" if nullable == "YES" else "NOT NULL"
                    lines.append(f"  {col_name:<30} {data_type:<20} {null_str}")
                lines.append("")

        # Get sample data (3 rows from projects to help the LLM understand the domain)
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT project_name, project_code, status, project_type, region, "
                "planned_budget, actual_cost, percent_complete "
                "FROM v_projects LIMIT 3"
            ))
            sample_rows = result.fetchall()

            if sample_rows:
                lines.append("SAMPLE DATA (v_projects, first 3 rows):")
                lines.append("-" * 50)
                cols = ["project_name", "project_code", "status", "project_type",
                        "region", "planned_budget", "actual_cost", "percent_complete"]
                for row in sample_rows:
                    lines.append("  " + " | ".join(str(v) for v in row))
                lines.append("")

    except Exception as e:
        logger.error("Error fetching schema info: %s", e)
        lines.append(f"Error fetching schema: {e}")

    return "\n".join(lines)
