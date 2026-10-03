"""
runner.py — Evaluation grid runner.

Runs the agent over the gold set with configurable:
- Models (qwen3:4b, qwen2.5:3b, qwen3.5:9b)
- Prompt strategies (zero_shot, few_shot, chain_of_thought, structured, best)
- Temperatures (0.0, 0.3, 0.7)

Outputs:
- JSONL traces per run (one line per question with full agent trace)
- Summary CSV with aggregated metrics per configuration
- Console summary table

Usage:
    # Run single config (fast, ~10 min)
    python -m evals.runner --model qwen3:4b --strategy few_shot --temperature 0.0

    # Run specific categories only
    python -m evals.runner --model qwen3:4b --strategy few_shot --categories simple_agg,must_refuse

    # Run full grid (slow, ~hours)
    python -m evals.runner --full-grid
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import yaml

# Add src/ to path
_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from copilot.agent.build_agent import run_agent
from evals.scorers import score_answer

logger = logging.getLogger(__name__)

# ============================================================
# Paths
# ============================================================
EVALS_DIR = Path(__file__).resolve().parent
GOLD_SET_PATH = EVALS_DIR / "gold_set.yaml"
RESULTS_DIR = _ROOT / "results"


def load_gold_set(
    path: Path = GOLD_SET_PATH,
    categories: list[str] | None = None,
) -> list[dict]:
    """Load gold set, optionally filtering by category."""
    with open(path, "r", encoding="utf-8") as f:
        gold = yaml.safe_load(f)

    if categories:
        gold = [q for q in gold if q.get("category") in categories]

    return gold


def run_evaluation(
    *,
    model: str = "qwen3:4b",
    strategy: str = "few_shot",
    temperature: float = 0.0,
    categories: list[str] | None = None,
    max_questions: int | None = None,
) -> dict:
    """
    Run the agent over the gold set and score results.

    Returns:
        dict with 'traces' (list of per-question results) and 'summary' (aggregated metrics)
    """
    gold = load_gold_set(categories=categories)
    if max_questions:
        gold = gold[:max_questions]

    config_name = f"{model}__{strategy}__t{temperature}"
    print(f"\n{'='*70}")
    print(f"EVALUATION: {config_name}")
    print(f"Questions: {len(gold)}")
    print(f"{'='*70}")

    traces = []
    total_start = time.perf_counter()

    for i, q in enumerate(gold, 1):
        qid = q["id"]
        question = q["question"]
        category = q["category"]

        print(f"\n[{i}/{len(gold)}] ({category}) {question[:60]}...", end=" ", flush=True)

        # Run agent
        try:
            result = run_agent(
                question,
                model=model,
                strategy=strategy,
                temperature=temperature,
            )
            result_dict = asdict(result)
        except Exception as e:
            print(f"ERROR: {e}")
            result_dict = {
                "answer": f"Error: {e}",
                "steps": [],
                "total_steps": 0,
                "total_tokens": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "latency_seconds": 0,
                "model": model,
                "strategy": strategy,
                "temperature": temperature,
                "error": str(e),
                "sql_queries": [],
            }

        # Score
        scores = score_answer(result_dict, q)

        # Build trace entry
        trace = {
            "id": qid,
            "question": question,
            "category": category,
            "config": config_name,
            "model": model,
            "strategy": strategy,
            "temperature": temperature,
            "answer": result_dict.get("answer", "")[:1000],
            "sql_queries": result_dict.get("sql_queries", []),
            "total_steps": result_dict.get("total_steps", 0),
            "total_tokens": result_dict.get("total_tokens", 0),
            "prompt_tokens": result_dict.get("prompt_tokens", 0),
            "completion_tokens": result_dict.get("completion_tokens", 0),
            "latency_seconds": result_dict.get("latency_seconds", 0),
            "error": result_dict.get("error"),
            **scores,
        }
        traces.append(trace)

        status = "PASS" if scores["correct"] else "FAIL"
        print(f"{status} ({result_dict.get('latency_seconds', 0):.1f}s, {result_dict.get('total_steps', 0)} steps)")

    total_elapsed = time.perf_counter() - total_start

    # Compute summary
    summary = _compute_summary(traces, config_name, total_elapsed)

    return {"traces": traces, "summary": summary}


def _compute_summary(traces: list[dict], config_name: str, total_elapsed: float) -> dict:
    """Aggregate per-question scores into a summary."""
    n = len(traces)
    if n == 0:
        return {}

    correct = sum(1 for t in traces if t["correct"])
    exec_ok = sum(1 for t in traces if t["execution_ok"])
    pattern_match = sum(1 for t in traces if t["pattern_match"])

    # Category breakdown
    categories = {}
    for t in traces:
        cat = t["category"]
        if cat not in categories:
            categories[cat] = {"total": 0, "correct": 0}
        categories[cat]["total"] += 1
        if t["correct"]:
            categories[cat]["correct"] += 1

    # Refusal metrics (precision/recall)
    refusal_cats = {"must_refuse", "destructive", "sensitive"}
    should_refuse = [t for t in traces if t["category"] in refusal_cats]
    should_not_refuse = [t for t in traces if t["category"] not in refusal_cats and t["category"] != "ambiguous"]

    true_pos_refusal = sum(1 for t in should_refuse if t.get("refusal_correct", False))
    false_neg_refusal = len(should_refuse) - true_pos_refusal

    # False positive: refused when should have answered
    from evals.scorers import _is_refusal
    false_pos_refusal = sum(1 for t in should_not_refuse if _is_refusal(t.get("answer", "")))

    refusal_precision = true_pos_refusal / (true_pos_refusal + false_pos_refusal) if (true_pos_refusal + false_pos_refusal) > 0 else 0
    refusal_recall = true_pos_refusal / (true_pos_refusal + false_neg_refusal) if (true_pos_refusal + false_neg_refusal) > 0 else 0

    # Token and latency stats
    latencies = [t["latency_seconds"] for t in traces if t["latency_seconds"] > 0]
    tokens = [t["total_tokens"] for t in traces if t["total_tokens"] > 0]
    steps_list = [t["total_steps"] for t in traces]

    summary = {
        "config": config_name,
        "model": traces[0]["model"],
        "strategy": traces[0]["strategy"],
        "temperature": traces[0]["temperature"],
        "total_questions": n,
        "correct": correct,
        "accuracy_pct": round(correct / n * 100, 1),
        "execution_ok_pct": round(exec_ok / n * 100, 1),
        "pattern_match_pct": round(pattern_match / n * 100, 1),
        "refusal_precision": round(refusal_precision * 100, 1),
        "refusal_recall": round(refusal_recall * 100, 1),
        "avg_steps": round(sum(steps_list) / n, 1),
        "avg_tokens": round(sum(tokens) / len(tokens), 0) if tokens else 0,
        "avg_latency_s": round(sum(latencies) / len(latencies), 1) if latencies else 0,
        "total_time_s": round(total_elapsed, 1),
        "categories": {
            cat: f"{v['correct']}/{v['total']} ({round(v['correct']/v['total']*100)}%)"
            for cat, v in sorted(categories.items())
        },
    }

    return summary


def save_results(results: dict, output_dir: Path = RESULTS_DIR) -> tuple[Path, Path]:
    """Save traces to JSONL and summary to CSV."""
    output_dir.mkdir(parents=True, exist_ok=True)

    config = results["summary"].get("config", "unknown").replace(":", "_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # JSONL traces
    jsonl_path = output_dir / f"{config}__{timestamp}.jsonl"
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for trace in results["traces"]:
            # Make JSON-serializable
            safe_trace = {k: v for k, v in trace.items()}
            f.write(json.dumps(safe_trace, default=str, ensure_ascii=False) + "\n")

    # Summary CSV (append mode)
    csv_path = output_dir / "summary.csv"
    summary = results["summary"]
    is_new = not csv_path.exists()

    flat_summary = {k: v for k, v in summary.items() if k != "categories"}
    # Add category details as separate columns
    for cat, val in summary.get("categories", {}).items():
        flat_summary[f"cat_{cat}"] = val

    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(flat_summary.keys()))
        if is_new:
            writer.writeheader()
        writer.writerow(flat_summary)

    return jsonl_path, csv_path


def print_summary(summary: dict) -> None:
    """Print a formatted summary to console."""
    print(f"\n{'='*70}")
    print(f"RESULTS: {summary.get('config', '?')}")
    print(f"{'='*70}")
    print(f"  Accuracy:          {summary.get('accuracy_pct', 0)}%  ({summary.get('correct', 0)}/{summary.get('total_questions', 0)})")
    print(f"  Execution OK:      {summary.get('execution_ok_pct', 0)}%")
    print(f"  Pattern Match:     {summary.get('pattern_match_pct', 0)}%")
    print(f"  Refusal Precision: {summary.get('refusal_precision', 0)}%")
    print(f"  Refusal Recall:    {summary.get('refusal_recall', 0)}%")
    print(f"  Avg Steps:         {summary.get('avg_steps', 0)}")
    print(f"  Avg Tokens:        {summary.get('avg_tokens', 0)}")
    print(f"  Avg Latency:       {summary.get('avg_latency_s', 0)}s")
    print(f"  Total Time:        {summary.get('total_time_s', 0)}s")
    print(f"\n  Category Breakdown:")
    for cat, val in summary.get("categories", {}).items():
        print(f"    {cat:<20} {val}")
    print(f"{'='*70}")


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Run evaluation harness")
    parser.add_argument("--model", default="qwen3:4b")
    parser.add_argument("--strategy", default="few_shot")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--categories", default=None, help="Comma-separated categories to test")
    parser.add_argument("--max-questions", type=int, default=None)
    parser.add_argument("--full-grid", action="store_true", help="Run all model x strategy x temp combos")
    parser.add_argument("--no-save", action="store_true", help="Don't save results to files")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)

    cats = args.categories.split(",") if args.categories else None

    if args.full_grid:
        models = ["qwen3:4b", "qwen2.5:3b"]
        strategies = ["zero_shot", "few_shot", "chain_of_thought", "best"]
        temperatures = [0.0, 0.3, 0.7]

        for model in models:
            for strategy in strategies:
                for temp in temperatures:
                    results = run_evaluation(
                        model=model, strategy=strategy, temperature=temp,
                        categories=cats, max_questions=args.max_questions,
                    )
                    print_summary(results["summary"])
                    if not args.no_save:
                        jsonl, csv_path = save_results(results)
                        print(f"  Saved: {jsonl}")
    else:
        results = run_evaluation(
            model=args.model, strategy=args.strategy, temperature=args.temperature,
            categories=cats, max_questions=args.max_questions,
        )
        print_summary(results["summary"])
        if not args.no_save:
            jsonl, csv_path = save_results(results)
            print(f"  Traces: {jsonl}")
            print(f"  Summary: {csv_path}")


if __name__ == "__main__":
    main()
