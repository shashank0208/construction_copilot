"""
build_agent.py — Constructs the LangGraph ReAct agent.

The ReAct (Reason + Act) pattern:
1. The LLM receives the conversation so far (system prompt + user question + tool results)
2. It either:
   a) Emits a tool_call → framework executes the tool → result appended → loop back to 1
   b) Emits a text response → agent finishes (this is the final answer)
3. If the LLM errors or hits max steps, the agent returns a failure message

This module demonstrates:
- LangGraph's create_react_agent for the agent loop
- Configurable max steps (prevents infinite loops)
- Prompt strategy selection (zero_shot, few_shot, CoT, etc.)
- Token counting and latency tracking per invocation
"""

from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, BaseMessage
from langgraph.prebuilt import create_react_agent

from copilot.llm import build_llm, strip_thinking
from copilot.tools import get_all_tools
from copilot.prompts import build_system_prompt
from copilot.db import get_schema_info
from copilot.config import get_settings

logger = logging.getLogger(__name__)


# ============================================================
# Agent result dataclass
# ============================================================

@dataclass
class AgentResult:
    """Result of an agent invocation."""
    answer: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    total_steps: int = 0
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_seconds: float = 0.0
    model: str = ""
    strategy: str = ""
    temperature: float = 0.0
    error: str | None = None
    sql_queries: list[str] = field(default_factory=list)


# ============================================================
# Agent builder
# ============================================================

def build_agent(
    *,
    model: str | None = None,
    strategy: str | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    num_ctx: int | None = None,
    enable_thinking: bool | None = None,
):
    """
    Build a LangGraph ReAct agent with the construction copilot tools.

    Returns:
        A compiled LangGraph agent (CompiledGraph) ready for .invoke()
    """
    settings = get_settings()

    # Build LLM
    llm = build_llm(
        model=model,
        temperature=temperature,
        top_p=top_p,
        num_ctx=num_ctx,
        enable_thinking=enable_thinking,
    )

    # Get tools
    tools = get_all_tools()

    # Build system prompt
    _strategy = strategy or settings.prompt_strategy
    schema = get_schema_info()
    system_prompt = build_system_prompt(schema, _strategy)

    # Create the ReAct agent using LangGraph
    # This sets up the loop: LLM → tool execution → LLM → ... → final answer
    agent = create_react_agent(
        model=llm,
        tools=tools,
        prompt=system_prompt,
    )

    return agent, {
        "model": model or settings.ollama_model,
        "strategy": _strategy,
        "temperature": temperature if temperature is not None else settings.llm_temperature,
        "system_prompt_length": len(system_prompt),
    }


def run_agent(
    question: str,
    *,
    model: str | None = None,
    strategy: str | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    num_ctx: int | None = None,
    enable_thinking: bool | None = None,
    max_steps: int | None = None,
) -> AgentResult:
    """
    Run the agent on a single question and return structured results.

    This is the main entry point for the evaluation harness and CLI.

    Args:
        question: The user's natural language question
        model: Override model name
        strategy: Override prompt strategy
        temperature: Override temperature
        max_steps: Max tool-calling iterations (default from settings)

    Returns:
        AgentResult with answer, step trace, token counts, and latency
    """
    settings = get_settings()
    _max_steps = max_steps or settings.agent_max_steps

    # Build agent
    agent, meta = build_agent(
        model=model,
        strategy=strategy,
        temperature=temperature,
        top_p=top_p,
        num_ctx=num_ctx,
        enable_thinking=enable_thinking,
    )

    # Prepare input
    messages = [HumanMessage(content=question)]

    # Run with timing
    start = time.perf_counter()
    try:
        result = agent.invoke(
            {"messages": messages},
            config={"recursion_limit": _max_steps * 2 + 5},
        )
        elapsed = time.perf_counter() - start
    except Exception as e:
        elapsed = time.perf_counter() - start
        logger.error("Agent error after %.2fs: %s", elapsed, e)
        return AgentResult(
            answer=f"Agent error: {str(e)[:500]}",
            latency_seconds=round(elapsed, 2),
            model=meta["model"],
            strategy=meta["strategy"],
            temperature=meta["temperature"],
            error=str(e)[:500],
        )

    # Parse the result
    all_messages = result.get("messages", [])
    steps = []
    sql_queries = []
    total_prompt = 0
    total_completion = 0

    for msg in all_messages:
        step_info = {
            "type": type(msg).__name__,
            "content": (msg.content or "")[:500] if hasattr(msg, "content") else "",
        }

        # Track tool calls
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            step_info["tool_calls"] = []
            for tc in msg.tool_calls:
                tool_info = {"name": tc["name"], "args": tc["args"]}
                step_info["tool_calls"].append(tool_info)
                # Extract SQL queries for tracing
                if tc["name"] == "run_sql_query" and "sql" in tc["args"]:
                    sql_queries.append(tc["args"]["sql"])

        # Track token counts from response metadata
        if hasattr(msg, "response_metadata") and msg.response_metadata:
            meta_data = msg.response_metadata
            p_tokens = meta_data.get("prompt_eval_count", 0) or 0
            c_tokens = meta_data.get("eval_count", 0) or 0
            total_prompt += p_tokens
            total_completion += c_tokens
            step_info["prompt_tokens"] = p_tokens
            step_info["completion_tokens"] = c_tokens

        steps.append(step_info)

    # Extract final answer (last AI message)
    final_answer = ""
    for msg in reversed(all_messages):
        if isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
            final_answer = strip_thinking(msg.content)
            break

    if not final_answer:
        # Fallback: use the last message content
        if all_messages and hasattr(all_messages[-1], "content"):
            final_answer = strip_thinking(all_messages[-1].content or "No answer produced.")

    return AgentResult(
        answer=final_answer,
        steps=steps,
        total_steps=len([s for s in steps if "tool_calls" in s]),
        total_tokens=total_prompt + total_completion,
        prompt_tokens=total_prompt,
        completion_tokens=total_completion,
        latency_seconds=round(elapsed, 2),
        model=meta["model"],
        strategy=meta["strategy"],
        temperature=meta["temperature"],
        sql_queries=sql_queries,
    )
