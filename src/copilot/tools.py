"""
tools.py -- LangChain tools for the Construction Risk Copilot agent.

Defines the tools that the LLM can call via the ReAct agent loop:
1. list_tables      — List all available database views
2. get_table_schema — Get column details for a specific view
3. run_sql_query    — Validate and execute a read-only SQL query
4. ask_clarification — Request more information from the user

Each tool has a clear docstring that the LLM reads to decide when to call it.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.tools import tool

from copilot.db import execute_safe_query, get_schema_info, get_engine, ALLOWED_TABLES

logger = logging.getLogger(__name__)


@tool
def list_tables() -> str:
    """List all available database tables (views) that you can query.

    Call this first to see what data is available.
    Returns the table names and their descriptions.
    """
    table_descriptions = {
        "v_projects": "Construction projects with budget, schedule, status, type, region",
        "v_resources": "Workers, equipment, materials, subcontractors with rates",
        "v_milestones": "Schedule milestones per project with planned/actual dates",
        "v_cost_items": "Itemized costs per project with planned vs actual amounts",
        "v_risk_assessments": "Risk register: probability, impact, risk_score, mitigation",
        "v_change_orders": "Scope changes with cost and schedule impact",
        "v_project_resources": "Resource assignments with hours and utilization",
        "v_daily_logs": "Daily site reports: weather, workers, delays, safety",
    }

    lines = ["Available tables (views):"]
    for table in sorted(ALLOWED_TABLES):
        desc = table_descriptions.get(table, "")
        lines.append(f"  - {table}: {desc}")

    return "\n".join(lines)


@tool
def get_table_schema(table_name: str) -> str:
    """Get the column names, data types, and sample data for a specific table.

    Args:
        table_name: Name of the table/view to inspect (e.g. 'v_projects')

    Call this to understand the structure of a table before writing SQL.
    """
    table_name = table_name.strip().lower()

    if table_name not in ALLOWED_TABLES:
        return (
            f"Error: '{table_name}' is not an allowed table. "
            f"Allowed tables: {sorted(ALLOWED_TABLES)}"
        )

    engine = get_engine(readonly=True)
    lines = [f"Schema for {table_name}:", ""]

    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            # Get columns
            result = conn.execute(text(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_name = :tbl AND table_schema = 'public' "
                "ORDER BY ordinal_position"
            ), {"tbl": table_name})

            cols = result.fetchall()
            lines.append(f"{'Column':<30} {'Type':<20} {'Nullable'}")
            lines.append("-" * 60)
            for col_name, data_type, nullable in cols:
                lines.append(f"{col_name:<30} {data_type:<20} {nullable}")

            # Get row count
            count_result = conn.execute(text(f"SELECT count(*) FROM {table_name}"))
            row_count = count_result.scalar()
            lines.append(f"\nTotal rows: {row_count}")

            # Sample rows (3)
            sample_result = conn.execute(text(f"SELECT * FROM {table_name} LIMIT 3"))
            sample_cols = list(sample_result.keys())
            sample_rows = sample_result.fetchall()

            if sample_rows:
                lines.append(f"\nSample data (first 3 rows):")
                lines.append(" | ".join(sample_cols))
                lines.append("-" * 60)
                for row in sample_rows:
                    lines.append(" | ".join(str(v) for v in row))

    except Exception as e:
        lines.append(f"Error: {e}")

    return "\n".join(lines)


@tool
def run_sql_query(sql: str) -> str:
    """Execute a read-only SQL query against the construction database.

    IMPORTANT RULES:
    - Only SELECT statements are allowed (no INSERT, UPDATE, DELETE, DROP)
    - Only query the allowed views: v_projects, v_resources, v_milestones,
      v_cost_items, v_risk_assessments, v_change_orders, v_project_resources, v_daily_logs
    - Results are limited to 200 rows maximum
    - Queries have a 5-second timeout

    Args:
        sql: A valid PostgreSQL SELECT query

    Returns:
        Query results formatted as a table, or an error message if the query
        was rejected by the safety guard or failed to execute.
    """
    result = execute_safe_query(sql)

    if not result["success"]:
        return f"Error: {result['error']}"

    # Format results as a readable table
    rows = result["rows"]
    columns = result["columns"]

    if not rows:
        return "Query returned 0 rows."

    lines = []

    # Header
    lines.append(" | ".join(columns))
    lines.append("-" * min(len(lines[0]), 120))

    # Rows
    for row in rows:
        values = [str(row.get(col, "")) for col in columns]
        lines.append(" | ".join(values))

    # Footer
    lines.append(f"\n({result['row_count']} rows returned)")
    if result["truncated"]:
        lines.append("NOTE: Results were truncated. Add LIMIT or WHERE clauses to narrow down.")

    return "\n".join(lines)


@tool
def ask_clarification(question: str) -> str:
    """Ask the user for clarification when a question is ambiguous.

    Use this when you need more information to write an accurate SQL query.
    For example, if the user asks about 'risk' but doesn't specify whether
    they mean budget risk, schedule risk, or safety risk.

    Args:
        question: The clarifying question to ask the user

    Returns:
        A message indicating the question was asked (user will respond in the next turn)
    """
    # In the agent loop, this creates a pause point.
    # The Streamlit UI will intercept this and show the question to the user.
    return f"CLARIFICATION NEEDED: {question}"


def get_all_tools() -> list:
    """Return all tools for the agent."""
    return [list_tables, get_table_schema, run_sql_query, ask_clarification]
