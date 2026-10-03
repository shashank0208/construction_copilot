"""Quick live test of the DB layer + SQL guard integration."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from copilot.db import execute_safe_query, get_schema_info

print("=" * 60)
print("TEST 1: Valid query")
print("=" * 60)
result = execute_safe_query("SELECT project_name, status, planned_budget FROM v_projects WHERE status = 'Active' LIMIT 5")
if result["success"]:
    print(f"Rows: {result['row_count']}")
    for row in result["rows"]:
        print(f"  {row}")
else:
    print(f"Error: {result['error']}")

print("\n" + "=" * 60)
print("TEST 2: Blocked — base table access")
print("=" * 60)
result = execute_safe_query("SELECT email, phone FROM resources")
print(f"Blocked: {not result['success']}")
print(f"Reason: {result['error']}")

print("\n" + "=" * 60)
print("TEST 3: Blocked — DROP")
print("=" * 60)
result = execute_safe_query("DROP TABLE projects")
print(f"Blocked: {not result['success']}")
print(f"Reason: {result['error']}")

print("\n" + "=" * 60)
print("TEST 4: Blocked — semicolon injection")
print("=" * 60)
result = execute_safe_query("SELECT 1; DELETE FROM projects")
print(f"Blocked: {not result['success']}")
print(f"Reason: {result['error']}")

print("\n" + "=" * 60)
print("TEST 5: Schema info (first 20 lines)")
print("=" * 60)
schema = get_schema_info()
for line in schema.split("\n")[:20]:
    print(line)
print("...")
