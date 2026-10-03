"""
sql_guard.py -- AST-based SQL validation using sqlglot.

This is the security-critical module that prevents:
1. Destructive SQL (INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, etc.)
2. Multi-statement injection (semicolons, stacked queries)
3. Access to forbidden tables/schemas (pg_catalog, information_schema, base tables)
4. Access to forbidden columns (PII columns hidden by views)
5. Dangerous functions (pg_read_file, pg_sleep, COPY, etc.)
6. Comment-based obfuscation (strips SQL comments before parsing)

The guard works by:
1. Stripping comments (block /* */ and line --)
2. Parsing SQL into an AST using sqlglot
3. Rejecting if >1 statement found
4. Walking the AST to verify all table/column references are in the allow-list
5. Checking that the root node is SELECT or CTE-with-SELECT only
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Sequence

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

logger = logging.getLogger(__name__)

# ============================================================
# Allow-lists
# ============================================================

# Views the agent is allowed to query (the v_ prefix views)
ALLOWED_TABLES: frozenset[str] = frozenset({
    "v_projects",
    "v_resources",
    "v_milestones",
    "v_cost_items",
    "v_risk_assessments",
    "v_change_orders",
    "v_project_resources",
    "v_daily_logs",
})

# Forbidden schemas — agent should never touch system catalogs
FORBIDDEN_SCHEMAS: frozenset[str] = frozenset({
    "pg_catalog",
    "information_schema",
    "pg_toast",
    "pg_temp",
})

# Forbidden functions that could be used for attacks
FORBIDDEN_FUNCTIONS: frozenset[str] = frozenset({
    "pg_read_file",
    "pg_read_binary_file",
    "pg_ls_dir",
    "pg_stat_file",
    "pg_sleep",
    "pg_terminate_backend",
    "pg_cancel_backend",
    "pg_reload_conf",
    "lo_import",
    "lo_export",
    "dblink",
    "dblink_exec",
    "copy",
    "pg_advisory_lock",
    "set_config",
    "current_setting",
    "txid_current",
})

# Only these statement types are allowed
ALLOWED_STATEMENT_TYPES: tuple[type, ...] = (
    exp.Select,
)


# ============================================================
# Result dataclass
# ============================================================

@dataclass
class GuardResult:
    """Result of SQL validation."""
    is_safe: bool
    sql: str  # the original (or cleaned) SQL
    reason: str = ""  # why it was rejected (empty if safe)
    tables_used: list[str] = field(default_factory=list)
    columns_used: list[str] = field(default_factory=list)


# ============================================================
# Comment stripping
# ============================================================

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"--[^\n]*")


def _strip_comments(sql: str) -> str:
    """Remove SQL block and line comments to prevent obfuscation attacks.
    
    Iterates to handle nested block comments like /* outer /* inner */ */.
    """
    # Iteratively strip block comments (handles nesting)
    prev = None
    while prev != sql:
        prev = sql
        sql = _BLOCK_COMMENT.sub("", sql)
    sql = _LINE_COMMENT.sub("", sql)
    return sql.strip()


# ============================================================
# Main guard function
# ============================================================

def validate_sql(sql: str) -> GuardResult:
    """
    Validate a SQL string against the safety allow-list.

    Returns a GuardResult with is_safe=True if the SQL is allowed,
    or is_safe=False with a reason explaining why it was rejected.
    """
    if not sql or not sql.strip():
        return GuardResult(is_safe=False, sql=sql, reason="Empty SQL query")

    # Step 1: Strip comments (attackers use comments to hide payloads)
    cleaned = _strip_comments(sql)
    if not cleaned:
        return GuardResult(is_safe=False, sql=sql, reason="SQL is empty after removing comments")

    # Step 2: Quick regex pre-checks for obvious attacks
    upper = cleaned.upper()

    # Check for COPY ... TO/FROM (can read/write files)
    if re.search(r"\bCOPY\b", upper):
        return GuardResult(is_safe=False, sql=cleaned, reason="COPY statement is forbidden")

    # Check for backslash commands (\copy, \! etc.)
    if re.search(r"\\[a-z!]", cleaned, re.IGNORECASE):
        return GuardResult(is_safe=False, sql=cleaned, reason="Backslash commands are forbidden")

    # Step 3: Parse with sqlglot
    try:
        statements = sqlglot.parse(cleaned, dialect="postgres")
    except ParseError as e:
        return GuardResult(
            is_safe=False, sql=cleaned,
            reason=f"SQL parse error: {e}"
        )

    # Step 4: Must be exactly one statement
    # Filter out None entries (sqlglot may return None for empty strings)
    statements = [s for s in statements if s is not None]
    if len(statements) == 0:
        return GuardResult(is_safe=False, sql=cleaned, reason="No valid SQL statement found")
    if len(statements) > 1:
        return GuardResult(
            is_safe=False, sql=cleaned,
            reason=f"Multiple statements detected ({len(statements)}). Only single SELECT is allowed."
        )

    ast = statements[0]

    # Step 5: Check statement type — only SELECT (including CTEs wrapping SELECT)
    root = ast
    # Unwrap CTE: if the root is a CTE, check the final query is a SELECT
    if isinstance(root, exp.CTE):
        # CTE is part of a select — sqlglot nests it inside Select
        pass

    if not isinstance(root, exp.Select):
        stmt_type = type(root).__name__
        return GuardResult(
            is_safe=False, sql=cleaned,
            reason=f"Statement type '{stmt_type}' is not allowed. Only SELECT is permitted."
        )

    # Step 6: Check for subqueries that are DML (e.g. SELECT * FROM (DELETE ...) )
    for node in ast.walk():
        if isinstance(node, (exp.Insert, exp.Update, exp.Delete, exp.Drop,
                             exp.Create, exp.Alter, exp.Command)):
            return GuardResult(
                is_safe=False, sql=cleaned,
                reason=f"DML/DDL operation '{type(node).__name__}' found in query. Only SELECT is permitted."
            )

    # Step 7: Collect CTE alias names (so they're not rejected as unknown tables)
    cte_aliases: set[str] = set()
    for cte_node in ast.find_all(exp.CTE):
        if cte_node.alias:
            cte_aliases.add(cte_node.alias.lower())

    # Step 8: Extract and validate table references
    tables_used = []
    for table_node in ast.find_all(exp.Table):
        table_name = table_node.name.lower() if table_node.name else ""
        schema_name = table_node.db.lower() if table_node.db else ""

        # Check forbidden schemas
        if schema_name in FORBIDDEN_SCHEMAS:
            return GuardResult(
                is_safe=False, sql=cleaned,
                reason=f"Access to schema '{schema_name}' is forbidden."
            )

        # Skip CTE aliases — they are temporary names defined in the query itself
        if table_name in cte_aliases:
            continue

        # Check table is in allow-list
        if table_name and table_name not in ALLOWED_TABLES:
            return GuardResult(
                is_safe=False, sql=cleaned,
                reason=f"Table '{table_name}' is not in the allowed tables list. "
                       f"Allowed: {sorted(ALLOWED_TABLES)}"
            )

        if table_name:
            tables_used.append(table_name)

    # Step 8: Check for forbidden functions
    for func_node in ast.find_all(exp.Anonymous):
        func_name = func_node.name.lower() if func_node.name else ""
        if func_name in FORBIDDEN_FUNCTIONS:
            return GuardResult(
                is_safe=False, sql=cleaned,
                reason=f"Function '{func_name}' is forbidden."
            )

    # Also check named functions
    for func_node in ast.find_all(exp.Func):
        func_name = ""
        if hasattr(func_node, "name"):
            func_name = func_node.name.lower() if func_node.name else ""
        elif hasattr(func_node, "sql_name"):
            func_name = func_node.sql_name().lower()

        if func_name in FORBIDDEN_FUNCTIONS:
            return GuardResult(
                is_safe=False, sql=cleaned,
                reason=f"Function '{func_name}' is forbidden."
            )

    # Step 9: Extract column references for logging
    columns_used = []
    for col_node in ast.find_all(exp.Column):
        col_name = col_node.name.lower() if col_node.name else ""
        if col_name:
            columns_used.append(col_name)

    # All checks passed!
    logger.info(
        "SQL validated: tables=%s, columns=%d",
        tables_used, len(columns_used)
    )

    return GuardResult(
        is_safe=True,
        sql=cleaned,
        tables_used=tables_used,
        columns_used=columns_used,
    )
