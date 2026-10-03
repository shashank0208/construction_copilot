"""
llm.py — Factory for ChatOllama (local) and optional hosted-API models.

Demonstrates LLM primitives: temperature, top_p, context window (num_ctx),
timeout, and Qwen3 thinking mode control.

Usage:
    from copilot.llm import build_llm
    llm = build_llm()                          # default: ChatOllama with qwen3:4b
    llm = build_llm(model="qwen2.5:3b")       # override model
    llm = build_llm(provider="openai")          # hosted fallback (reads key from env)
"""

from __future__ import annotations

import re
import time
import logging
from typing import Any

from langchain_ollama import ChatOllama
from langchain_core.messages import BaseMessage, AIMessage
from langchain_core.language_models.chat_models import BaseChatModel

from copilot.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Qwen3 thinking mode: strip <think>...</think> blocks from responses
# ---------------------------------------------------------------------------

_THINK_PATTERN = re.compile(r"<think>.*?</think>", re.DOTALL)


def strip_thinking(text: str) -> str:
    """Remove Qwen3 <think>...</think> reasoning blocks from output."""
    return _THINK_PATTERN.sub("", text).strip()


# ---------------------------------------------------------------------------
# LLM Factory
# ---------------------------------------------------------------------------

def build_llm(
    *,
    model: str | None = None,
    provider: str | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    num_ctx: int | None = None,
    timeout: int | None = None,
    enable_thinking: bool | None = None,
) -> BaseChatModel:
    """
    Build a chat model instance.

    Parameters use settings from .env as defaults; pass explicit values to override.
    
    The agent loop works like this:
    1. The model receives messages (system prompt + user question + tool results)
    2. It either emits a tool call (JSON with tool name + args) or a final text answer
    3. The framework (LangGraph) executes the tool and appends the result
    4. Repeat until the model gives a final answer or the step limit is hit

    Args:
        model:     Ollama model name (e.g. "qwen3:4b", "qwen2.5:3b")
        provider:  "ollama" (default), "openai", or "google" for hosted fallback
        temperature: Sampling temperature (0.0 = deterministic, higher = more random)
        top_p:     Nucleus sampling cutoff (0.9 = consider top 90% probability mass)
        num_ctx:   Context window size in tokens (how much text the model can see)
        timeout:   Request timeout in seconds
        enable_thinking: Whether to allow Qwen3's <think> reasoning blocks

    Returns:
        A LangChain BaseChatModel ready for tool binding and agent use.
    """
    settings = get_settings()

    # Resolve parameters: explicit args > env settings > defaults
    _provider = provider or settings.hosted_api_provider or "ollama"
    _model = model or settings.ollama_model
    _temperature = temperature if temperature is not None else settings.llm_temperature
    _top_p = top_p if top_p is not None else settings.llm_top_p
    _num_ctx = num_ctx if num_ctx is not None else settings.llm_num_ctx
    _timeout = timeout if timeout is not None else settings.llm_timeout
    _enable_thinking = (
        enable_thinking if enable_thinking is not None else settings.llm_enable_thinking
    )

    if _provider == "ollama":
        return _build_ollama(
            model=_model,
            temperature=_temperature,
            top_p=_top_p,
            num_ctx=_num_ctx,
            timeout=_timeout,
            enable_thinking=_enable_thinking,
            base_url=settings.ollama_base_url,
        )
    elif _provider == "openai":
        return _build_openai(
            model=settings.hosted_model_name or "gpt-4o-mini",
            temperature=_temperature,
            top_p=_top_p,
            timeout=_timeout,
        )
    elif _provider == "google":
        return _build_google(
            model=settings.hosted_model_name or "gemini-2.0-flash",
            temperature=_temperature,
            top_p=_top_p,
            timeout=_timeout,
        )
    else:
        raise ValueError(f"Unknown provider: {_provider!r}. Use 'ollama', 'openai', or 'google'.")


def _build_ollama(
    *,
    model: str,
    temperature: float,
    top_p: float,
    num_ctx: int,
    timeout: int,
    enable_thinking: bool,
    base_url: str,
) -> ChatOllama:
    """
    Build a ChatOllama model for local inference via Ollama.
    
    Key LLM primitives configured here:
    - temperature: Controls randomness. 0.0 = greedy/deterministic, 1.0 = more creative
    - top_p: Nucleus sampling. Model considers tokens whose cumulative probability ≤ top_p
    - num_ctx: Context window. Max number of tokens (prompt + response) the model can handle
    - num_predict: Max tokens to generate in the response
    """
    logger.info(
        "Building ChatOllama: model=%s, temp=%.2f, top_p=%.2f, num_ctx=%d, thinking=%s",
        model, temperature, top_p, num_ctx, enable_thinking,
    )

    # Qwen3 thinking mode: use /no_think suffix in system prompts when disabled
    # The model_kwargs are passed directly to the Ollama API
    model_kwargs: dict[str, Any] = {}
    if not enable_thinking:
        # Setting think=False tells Ollama to suppress <think> blocks
        model_kwargs["think"] = False

    return ChatOllama(
        model=model,
        base_url=base_url,
        temperature=temperature,
        top_p=top_p,
        num_ctx=num_ctx,
        num_predict=2048,  # max output tokens
        timeout=timeout,
        **model_kwargs,
    )


def _build_openai(
    *,
    model: str,
    temperature: float,
    top_p: float,
    timeout: int,
) -> BaseChatModel:
    """Build a hosted OpenAI model. Key is read from OPENAI_API_KEY env var — never hardcoded."""
    settings = get_settings()
    if not settings.openai_api_key:
        raise ValueError(
            "OPENAI_API_KEY not set. Set it in .env or as an environment variable."
        )
    # Lazy import: only needed if user explicitly chooses openai provider
    from langchain_openai import ChatOpenAI  # type: ignore

    logger.info("Building ChatOpenAI: model=%s, temp=%.2f", model, temperature)
    return ChatOpenAI(
        model=model,
        api_key=settings.openai_api_key,
        temperature=temperature,
        top_p=top_p,
        timeout=timeout,
    )


def _build_google(
    *,
    model: str,
    temperature: float,
    top_p: float,
    timeout: int,
) -> BaseChatModel:
    """Build a hosted Google model. Key is read from GOOGLE_API_KEY env var — never hardcoded."""
    settings = get_settings()
    if not settings.google_api_key:
        raise ValueError(
            "GOOGLE_API_KEY not set. Set it in .env or as an environment variable."
        )
    from langchain_google_genai import ChatGoogleGenerativeAI  # type: ignore

    logger.info("Building ChatGoogleGenerativeAI: model=%s, temp=%.2f", model, temperature)
    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=settings.google_api_key,
        temperature=temperature,
        top_p=top_p,
        timeout=timeout,
    )
