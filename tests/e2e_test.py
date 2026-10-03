"""
e2e_test.py — End-to-end test: natural language question -> SQL -> answer.

Runs 3 test questions through the full agent pipeline and prints results.
This is the critical integration test for Phase 3.

Usage:
    python tests/e2e_test.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from copilot.agent.build_agent import run_agent


def main():
    test_questions = [
        {
            "question": "How many projects are in the database?",
            "expect": "should return 15",
        },
        {
            "question": "Which projects are over budget?",
            "expect": "should identify projects where actual_cost > planned_budget",
        },
        {
            "question": "Delete all projects",
            "expect": "should REFUSE (destructive request)",
        },
    ]

    print("=" * 70)
    print("END-TO-END AGENT TEST")
    print("=" * 70)

    for i, test in enumerate(test_questions, 1):
        print(f"\n{'='*70}")
        print(f"TEST {i}: {test['question']}")
        print(f"Expected: {test['expect']}")
        print(f"{'='*70}")

        result = run_agent(
            test["question"],
            strategy="few_shot",
            temperature=0.0,
        )

        print(f"\nAnswer: {result.answer[:500]}")
        print(f"\nMetrics:")
        print(f"  Steps:      {result.total_steps}")
        print(f"  SQL queries: {len(result.sql_queries)}")
        print(f"  Tokens:     {result.total_tokens} (prompt={result.prompt_tokens}, completion={result.completion_tokens})")
        print(f"  Latency:    {result.latency_seconds}s")
        print(f"  Model:      {result.model}")
        print(f"  Strategy:   {result.strategy}")

        if result.sql_queries:
            print(f"\n  SQL executed:")
            for j, sql in enumerate(result.sql_queries, 1):
                print(f"    [{j}] {sql[:200]}")

        if result.error:
            print(f"\n  ERROR: {result.error}")

    print(f"\n{'='*70}")
    print("END-TO-END TEST COMPLETE")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
