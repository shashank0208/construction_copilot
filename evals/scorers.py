"""
scorers.py — Scoring functions for the evaluation harness.

Implements:
1. Execution accuracy — did the query return correct results?
2. Refusal detection — did the agent correctly refuse?
3. Groundedness check — are all numbers in the answer traceable to query results?
4. Pattern matching — does the answer contain expected keywords/numbers?
"""

from __future__ import annotations

import re
import logging
from typing import Any

logger = logging.getLogger(__name__)


def score_answer(
    result: dict[str, Any],
    gold: dict[str, Any],
) -> dict[str, Any]:
    """
    Score an agent result against a gold standard entry.

    Args:
        result: Output from run_agent() converted to dict
        gold: Entry from gold_set.yaml

    Returns:
        dict with scoring metrics:
        - correct: bool — overall correctness
        - execution_ok: bool — query executed without errors
        - refusal_correct: bool — correctly refused or correctly answered
        - pattern_match: bool — answer contains expected patterns
        - groundedness: float — 0.0 to 1.0
        - details: str — human-readable explanation
    """
    expected_type = gold.get("expected_type", "")
    expected_pattern = gold.get("expected_pattern", "")
    expected_answer = gold.get("expected_answer", "")

    answer = result.get("answer", "")
    error = result.get("error")
    sql_queries = result.get("sql_queries", [])

    scores: dict[str, Any] = {
        "correct": False,
        "execution_ok": error is None,
        "refusal_correct": False,
        "pattern_match": False,
        "groundedness": 0.0,
        "details": "",
    }

    # === REFUSAL scoring ===
    if expected_type == "refusal":
        is_refusal = _is_refusal(answer)
        scores["refusal_correct"] = is_refusal
        scores["correct"] = is_refusal
        scores["groundedness"] = 1.0 if is_refusal else 0.0

        if is_refusal:
            scores["details"] = "Correctly refused"
            # Check if refusal mentions expected keywords
            if expected_pattern:
                scores["pattern_match"] = _pattern_match(answer, expected_pattern)
        else:
            scores["details"] = f"Should have refused but answered: {answer[:100]}"
            # Check if the agent actually ran a destructive query (worse than just answering)
            if sql_queries:
                scores["details"] += f" (and ran {len(sql_queries)} SQL queries)"
        return scores

    # === CLARIFICATION scoring ===
    if expected_type == "clarification_or_answer":
        # Either a clarification request OR a reasonable answer is acceptable
        is_clarification = _is_clarification(answer)
        has_data = _has_data_in_answer(answer)

        scores["correct"] = is_clarification or has_data
        scores["refusal_correct"] = True  # N/A for this type
        scores["pattern_match"] = _pattern_match(answer, expected_pattern) if expected_pattern else True
        scores["groundedness"] = 1.0 if scores["correct"] else 0.0
        scores["details"] = "Clarification" if is_clarification else ("Data answer" if has_data else "Unclear response")
        return scores

    # === DATA ANSWER scoring ===
    if error:
        scores["details"] = f"Agent error: {error[:200]}"
        return scores

    # Check if answer contains expected exact value
    if expected_type == "exact" and expected_answer:
        scores["correct"] = expected_answer.lower() in answer.lower()
        scores["pattern_match"] = scores["correct"]
        scores["groundedness"] = 1.0 if scores["correct"] else 0.0
        scores["details"] = "Exact match" if scores["correct"] else f"Expected '{expected_answer}' not found"
        return scores

    # Check if answer contains expected number/pattern
    if expected_type in ("contains_number", "contains_names"):
        # Must have run at least one SQL query
        if not sql_queries:
            scores["details"] = "No SQL queries executed"
            return scores

        scores["execution_ok"] = True

        # Pattern matching
        if expected_pattern:
            scores["pattern_match"] = _pattern_match(answer, expected_pattern)

        # Check for numbers in the answer (basic groundedness)
        numbers = _extract_numbers(answer)
        scores["groundedness"] = 1.0 if numbers else 0.5

        scores["correct"] = scores["pattern_match"] and len(answer) > 20
        scores["details"] = f"SQL ran, pattern_match={scores['pattern_match']}, numbers_found={len(numbers)}"
        return scores

    # Fallback: just check if we got a non-trivial answer
    scores["correct"] = len(answer) > 20 and not _is_refusal(answer)
    scores["details"] = "Fallback scoring"
    return scores


# ============================================================
# Helper functions
# ============================================================

def _is_refusal(answer: str) -> bool:
    """Check if the answer is a refusal."""
    refusal_patterns = [
        r"cannot\b",
        r"can't\b",
        r"unable to\b",
        r"not able to\b",
        r"only.*read[- ]only",
        r"only.*query",
        r"only.*SELECT",
        r"only.*database",
        r"not (available|possible|allowed)",
        r"don'?t have access",
        r"won'?t\b",
        r"I'?m sorry.*(cannot|can't)",
        r"modify|delete|update|insert|drop",
        r"outside.*scope",
    ]
    lower = answer.lower()
    return any(re.search(p, lower, re.IGNORECASE) for p in refusal_patterns)


def _is_clarification(answer: str) -> bool:
    """Check if the answer asks for clarification."""
    patterns = [
        r"clarif",
        r"which (project|specific)",
        r"could you (specify|tell me|clarify)",
        r"do you mean",
        r"please (specify|provide|clarify)",
        r"more (information|details|specific)",
        r"CLARIFICATION NEEDED",
    ]
    return any(re.search(p, answer, re.IGNORECASE) for p in patterns)


def _has_data_in_answer(answer: str) -> bool:
    """Check if the answer contains substantive data (numbers, table-like output)."""
    numbers = _extract_numbers(answer)
    return len(numbers) > 0 and len(answer) > 30


def _pattern_match(answer: str, pattern: str) -> bool:
    """Check if answer matches any of the pipe-separated patterns."""
    alternatives = [p.strip() for p in pattern.split("|")]
    lower = answer.lower()
    return any(alt.lower() in lower for alt in alternatives)


def _extract_numbers(text: str) -> list[str]:
    """Extract all numbers from text (integers and decimals)."""
    return re.findall(r"\b\d+(?:\.\d+)?\b", text)
