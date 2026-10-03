"""
test_sql_guard.py -- 30+ unit tests for the SQL security guard.

Tests cover:
- Valid SELECT queries (must pass)
- DML/DDL rejection (INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE)
- Multi-statement injection
- Forbidden table access (base tables, system catalogs)
- Forbidden function calls
- Comment-based obfuscation attacks
- Encoding and whitespace tricks
- CTE (WITH) queries
- Subquery attacks

NO running database needed — these tests only validate the AST parser.
"""

from __future__ import annotations

import pytest
import sys
from pathlib import Path

# Add src/ to path
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from copilot.sql_guard import validate_sql, GuardResult


# ============================================================
# Helper
# ============================================================

def assert_safe(sql: str, msg: str = "") -> GuardResult:
    result = validate_sql(sql)
    assert result.is_safe, f"Expected SAFE but got BLOCKED: {result.reason}. {msg}"
    return result


def assert_blocked(sql: str, msg: str = "") -> GuardResult:
    result = validate_sql(sql)
    assert not result.is_safe, f"Expected BLOCKED but got SAFE. {msg}"
    return result


# ============================================================
# VALID QUERIES — must pass
# ============================================================

class TestValidQueries:
    """Queries that SHOULD be allowed."""

    def test_simple_select(self):
        assert_safe("SELECT * FROM v_projects")

    def test_select_with_where(self):
        assert_safe("SELECT project_name FROM v_projects WHERE status = 'Active'")

    def test_select_with_join(self):
        assert_safe(
            "SELECT p.project_name, r.risk_score "
            "FROM v_projects p JOIN v_risk_assessments r ON p.project_id = r.project_id"
        )

    def test_select_with_aggregation(self):
        assert_safe(
            "SELECT project_type, COUNT(*), AVG(planned_budget) "
            "FROM v_projects GROUP BY project_type"
        )

    def test_select_with_subquery(self):
        assert_safe(
            "SELECT * FROM v_projects WHERE project_id IN "
            "(SELECT project_id FROM v_risk_assessments WHERE risk_score > 15)"
        )

    def test_select_with_cte(self):
        assert_safe(
            "WITH high_risk AS ("
            "  SELECT project_id, MAX(risk_score) as max_risk "
            "  FROM v_risk_assessments GROUP BY project_id"
            ") SELECT p.project_name, hr.max_risk "
            "FROM v_projects p JOIN high_risk hr ON p.project_id = hr.project_id"
        )

    def test_select_with_limit(self):
        assert_safe("SELECT * FROM v_daily_logs ORDER BY log_date DESC LIMIT 10")

    def test_select_with_window_function(self):
        assert_safe(
            "SELECT project_name, planned_budget, "
            "ROW_NUMBER() OVER (ORDER BY planned_budget DESC) as rank "
            "FROM v_projects"
        )

    def test_select_with_case(self):
        assert_safe(
            "SELECT project_name, "
            "CASE WHEN actual_cost > planned_budget THEN 'Over' ELSE 'Under' END as budget_status "
            "FROM v_projects"
        )

    def test_select_count_star(self):
        assert_safe("SELECT COUNT(*) FROM v_milestones")

    def test_select_multiple_tables(self):
        r = assert_safe(
            "SELECT p.project_name, c.cost_category, c.actual_amount "
            "FROM v_projects p JOIN v_cost_items c ON p.project_id = c.project_id"
        )
        assert "v_projects" in r.tables_used
        assert "v_cost_items" in r.tables_used

    def test_select_with_having(self):
        assert_safe(
            "SELECT project_id, SUM(actual_amount) as total "
            "FROM v_cost_items GROUP BY project_id HAVING SUM(actual_amount) > 100000"
        )


# ============================================================
# DML / DDL REJECTION — must be blocked
# ============================================================

class TestDMLDDLRejection:
    """Destructive operations must be blocked."""

    def test_insert(self):
        r = assert_blocked("INSERT INTO v_projects (project_name) VALUES ('evil')")
        assert "Insert" in r.reason or "not allowed" in r.reason.lower()

    def test_update(self):
        r = assert_blocked("UPDATE v_projects SET status = 'Cancelled'")
        assert "Update" in r.reason or "not allowed" in r.reason.lower()

    def test_delete(self):
        r = assert_blocked("DELETE FROM v_projects WHERE project_id = 1")
        assert "Delete" in r.reason or "not allowed" in r.reason.lower()

    def test_drop_table(self):
        r = assert_blocked("DROP TABLE v_projects")
        assert "Drop" in r.reason or "not allowed" in r.reason.lower()

    def test_alter_table(self):
        assert_blocked("ALTER TABLE v_projects ADD COLUMN evil TEXT")

    def test_truncate(self):
        assert_blocked("TRUNCATE v_projects")

    def test_create_table(self):
        assert_blocked("CREATE TABLE evil (id INT)")


# ============================================================
# MULTI-STATEMENT INJECTION — must be blocked
# ============================================================

class TestMultiStatementInjection:
    """Stacked queries must be detected and blocked."""

    def test_semicolon_injection(self):
        assert_blocked("SELECT 1; DROP TABLE v_projects")

    def test_select_then_delete(self):
        assert_blocked("SELECT * FROM v_projects; DELETE FROM projects")

    def test_select_then_insert(self):
        assert_blocked(
            "SELECT * FROM v_projects; INSERT INTO projects (project_name) VALUES ('hacked')"
        )


# ============================================================
# FORBIDDEN TABLE ACCESS — must be blocked
# ============================================================

class TestForbiddenTableAccess:
    """Access to base tables and system catalogs must be blocked."""

    def test_base_table_projects(self):
        r = assert_blocked("SELECT * FROM projects")
        assert "not in the allowed" in r.reason.lower()

    def test_base_table_resources(self):
        assert_blocked("SELECT email, phone FROM resources")

    def test_pg_catalog(self):
        assert_blocked("SELECT * FROM pg_catalog.pg_tables")

    def test_information_schema(self):
        assert_blocked("SELECT * FROM information_schema.tables")

    def test_pg_roles(self):
        assert_blocked("SELECT * FROM pg_roles")

    def test_pg_shadow(self):
        assert_blocked("SELECT * FROM pg_shadow")

    def test_pg_authid(self):
        assert_blocked("SELECT * FROM pg_authid")


# ============================================================
# FORBIDDEN FUNCTIONS — must be blocked
# ============================================================

class TestForbiddenFunctions:
    """Dangerous functions must be detected and blocked."""

    def test_pg_sleep(self):
        assert_blocked("SELECT pg_sleep(10)")

    def test_pg_read_file(self):
        assert_blocked("SELECT pg_read_file('/etc/passwd')")


# ============================================================
# COMMENT OBFUSCATION — must be blocked
# ============================================================

class TestCommentObfuscation:
    """Attacks hidden in SQL comments must be caught."""

    def test_block_comment_hiding_drop(self):
        # After stripping comments, "DROP TABLE" should be visible
        assert_blocked("SELECT 1; /* comment */ DROP TABLE v_projects")

    def test_line_comment_bypass(self):
        assert_blocked("SELECT 1; -- comment\nDROP TABLE v_projects")

    def test_sequential_block_comments(self):
        # Multiple sequential block comments should all be stripped
        r = validate_sql("/* comment1 */ /* comment2 */ SELECT * FROM v_projects")
        assert r.is_safe

    def test_comment_inside_query(self):
        # Comment in middle of query should be stripped cleanly
        r = validate_sql("SELECT * /* this is ignored */ FROM v_projects")
        assert r.is_safe


# ============================================================
# EDGE CASES
# ============================================================

class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_empty_string(self):
        r = assert_blocked("")
        assert "empty" in r.reason.lower()

    def test_whitespace_only(self):
        assert_blocked("   \n\t  ")

    def test_only_comments(self):
        assert_blocked("-- just a comment")

    def test_copy_command(self):
        assert_blocked("COPY projects TO '/tmp/data.csv'")

    def test_backslash_command(self):
        assert_blocked("\\! rm -rf /")

    def test_select_from_nonexistent_view(self):
        r = assert_blocked("SELECT * FROM v_nonexistent")
        assert "not in the allowed" in r.reason.lower()

    def test_case_insensitive_table_check(self):
        # Table names should be lowered before checking
        assert_safe("SELECT * FROM V_PROJECTS")

    def test_tables_used_tracking(self):
        r = assert_safe("SELECT * FROM v_projects p JOIN v_risk_assessments r ON p.project_id = r.project_id")
        assert "v_projects" in r.tables_used
        assert "v_risk_assessments" in r.tables_used

    def test_select_into_blocked(self):
        # SELECT INTO creates a new table — should be caught
        result = validate_sql("SELECT * INTO new_table FROM v_projects")
        # This may be parsed as Create or as Select — either way, 'new_table' is not allowed
        # Accept either outcome as long as it's blocked
        assert not result.is_safe
