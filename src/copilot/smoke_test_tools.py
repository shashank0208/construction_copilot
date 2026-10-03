"""
smoke_test_tools.py — Verify that the local LLM can produce valid tool calls.

This is a critical check: if the model can't emit structured tool calls,
the agent loop won't work. We test with a trivial tool before building
the full agent.

Usage:
    python -m copilot.smoke_test_tools
"""

from __future__ import annotations

import time
import json
import sys

from langchain_core.tools import tool
from copilot.llm import build_llm
from copilot.config import get_settings


@tool
def add_numbers(a: int, b: int) -> int:
    """Add two numbers together and return the result."""
    return a + b


@tool
def get_project_count() -> str:
    """Return the total number of construction projects in the database."""
    return "There are 15 projects in the database."


def run_smoke_test(model_name: str | None = None) -> dict:
    """
    Run a tool-calling smoke test.

    The agent loop requires:
    1. Model receives a question + tool definitions
    2. Model emits a tool_call (JSON with tool name and arguments)
    3. Framework executes the tool
    4. Result is appended to conversation
    5. Model uses the result to answer

    This test checks step 2: can the model emit valid tool calls?
    """
    settings = get_settings()
    model = model_name or settings.ollama_model

    print(f"\n{'='*60}")
    print(f"TOOL-CALLING SMOKE TEST")
    print(f"Model: {model}")
    print(f"{'='*60}\n")

    llm = build_llm(model=model, temperature=0.0)
    tools = [add_numbers, get_project_count]

    # Bind tools to the model — this tells the model about available tools
    llm_with_tools = llm.bind_tools(tools)

    results = {}

    # Test 1: arithmetic tool call
    print("Test 1: 'What is 17 + 28?'")
    start = time.perf_counter()
    try:
        response = llm_with_tools.invoke("What is 17 + 28?")
        elapsed = time.perf_counter() - start

        if response.tool_calls:
            tc = response.tool_calls[0]
            print(f"  ✅ Tool call: {tc['name']}({tc['args']})")
            print(f"  Latency: {elapsed:.2f}s")
            results["arithmetic"] = {
                "status": "pass",
                "tool": tc["name"],
                "args": tc["args"],
                "latency": round(elapsed, 2),
            }
        else:
            print(f"  ❌ No tool call produced")
            print(f"  Raw response: {response.content[:200]}")
            results["arithmetic"] = {"status": "fail", "reason": "no_tool_call"}
    except Exception as e:
        elapsed = time.perf_counter() - start
        print(f"  ❌ Error: {e}")
        results["arithmetic"] = {"status": "error", "reason": str(e)}

    # Test 2: domain tool call
    print("\nTest 2: 'How many projects are in the database?'")
    start = time.perf_counter()
    try:
        response = llm_with_tools.invoke("How many projects are in the database?")
        elapsed = time.perf_counter() - start

        if response.tool_calls:
            tc = response.tool_calls[0]
            print(f"  ✅ Tool call: {tc['name']}({tc['args']})")
            print(f"  Latency: {elapsed:.2f}s")
            results["domain"] = {
                "status": "pass",
                "tool": tc["name"],
                "args": tc["args"],
                "latency": round(elapsed, 2),
            }
        else:
            print(f"  ❌ No tool call produced")
            print(f"  Raw response: {response.content[:200]}")
            results["domain"] = {"status": "fail", "reason": "no_tool_call"}
    except Exception as e:
        elapsed = time.perf_counter() - start
        print(f"  ❌ Error: {e}")
        results["domain"] = {"status": "error", "reason": str(e)}

    # Test 3: should NOT call a tool (general knowledge question)
    print("\nTest 3: 'What color is the sky?' (should NOT call a tool)")
    start = time.perf_counter()
    try:
        response = llm_with_tools.invoke("What color is the sky?")
        elapsed = time.perf_counter() - start

        if not response.tool_calls:
            print(f"  ✅ Correctly did NOT call a tool")
            print(f"  Answer: {response.content[:100]}")
            results["no_tool"] = {"status": "pass", "latency": round(elapsed, 2)}
        else:
            tc = response.tool_calls[0]
            print(f"  ⚠️  Incorrectly called: {tc['name']}({tc['args']})")
            results["no_tool"] = {"status": "warn", "reason": "unnecessary_tool_call"}
    except Exception as e:
        results["no_tool"] = {"status": "error", "reason": str(e)}

    # Summary
    passed = sum(1 for r in results.values() if r["status"] == "pass")
    total = len(results)
    print(f"\n{'='*60}")
    print(f"RESULT: {passed}/{total} tests passed")

    if passed >= 2:
        print(f"✅ {model} supports tool calling — agent loop will work")
    else:
        print(f"❌ {model} has issues with tool calling")
        print(f"   Consider: llama3.1:8b, qwen2.5:7b, or mistral:7b")
    print(f"{'='*60}\n")

    return results


if __name__ == "__main__":
    model = sys.argv[1] if len(sys.argv) > 1 else None
    run_smoke_test(model)
