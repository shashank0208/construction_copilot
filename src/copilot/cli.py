"""
cli.py — Simple CLI to chat with the LLM and print token counts + latency.

Usage:
    python -m copilot.cli "What is 2+2?"
    python -m copilot.cli --model qwen2.5:3b "Hello"
    python -m copilot.cli --thinking  "Explain gravity"

Demonstrates:
- Model instantiation with configurable parameters
- Token counting (prompt and completion)
- Latency measurement
- Qwen3 thinking mode toggle
"""

from __future__ import annotations

import argparse
import sys
import time

from copilot.config import get_settings
from copilot.llm import build_llm, strip_thinking


def main() -> None:
    parser = argparse.ArgumentParser(description="Chat with the local LLM")
    parser.add_argument("question", nargs="?", help="Question to ask")
    parser.add_argument("--model", default=None, help="Model name override")
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--top-p", type=float, default=None)
    parser.add_argument("--num-ctx", type=int, default=None)
    parser.add_argument("--thinking", action="store_true", help="Enable Qwen3 thinking")
    args = parser.parse_args()

    if not args.question:
        print("Usage: python -m copilot.cli 'your question here'")
        sys.exit(1)

    settings = get_settings()

    # Build the LLM with provided or default parameters
    llm = build_llm(
        model=args.model,
        temperature=args.temperature,
        top_p=args.top_p,
        num_ctx=args.num_ctx,
        enable_thinking=args.thinking,
    )

    print(f"Model:       {args.model or settings.ollama_model}")
    print(f"Temperature: {args.temperature if args.temperature is not None else settings.llm_temperature}")
    print(f"Top-p:       {args.top_p if args.top_p is not None else settings.llm_top_p}")
    print(f"Num-ctx:     {args.num_ctx or settings.llm_num_ctx}")
    print(f"Thinking:    {args.thinking}")
    print(f"Question:    {args.question}")
    print("-" * 60)

    # Invoke and measure
    start = time.perf_counter()
    response = llm.invoke(args.question)
    elapsed = time.perf_counter() - start

    # Extract content and strip thinking if disabled
    raw_content = response.content or ""
    display_content = raw_content if args.thinking else strip_thinking(raw_content)

    # Token counts from response metadata (Ollama provides these)
    meta = response.response_metadata or {}
    prompt_tokens = meta.get("prompt_eval_count", "N/A")
    completion_tokens = meta.get("eval_count", "N/A")
    model_name = meta.get("model", "unknown")

    print(f"\n{'='*60}")
    print(f"RESPONSE:")
    print(f"{'='*60}")
    print(display_content)
    print(f"{'='*60}")
    print(f"Model:             {model_name}")
    print(f"Prompt tokens:     {prompt_tokens}")
    print(f"Completion tokens: {completion_tokens}")
    print(f"Latency:           {elapsed:.2f}s")
    if isinstance(completion_tokens, int) and elapsed > 0:
        print(f"Speed:             {completion_tokens / elapsed:.1f} tok/s")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
