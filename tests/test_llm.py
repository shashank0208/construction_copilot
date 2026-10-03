"""
test_llm.py — Unit tests for the LLM factory and utilities.

These tests use mocks — NO running LLM or Ollama needed.
They verify configuration loading, parameter passing, and thinking mode stripping.
"""

from __future__ import annotations

import os
import pytest
from unittest.mock import patch, MagicMock

# --- Tests for strip_thinking ---

from copilot.llm import strip_thinking


class TestStripThinking:
    """Test Qwen3 <think> block removal."""

    def test_removes_single_think_block(self):
        text = "<think>Let me reason about this...</think>The answer is 42."
        assert strip_thinking(text) == "The answer is 42."

    def test_removes_multiline_think_block(self):
        text = (
            "<think>\nStep 1: Consider the question\n"
            "Step 2: Think harder\n</think>\nHello!"
        )
        assert strip_thinking(text) == "Hello!"

    def test_removes_multiple_think_blocks(self):
        text = "<think>first</think>A<think>second</think>B"
        assert strip_thinking(text) == "AB"

    def test_no_think_block_unchanged(self):
        text = "Just a normal response without thinking."
        assert strip_thinking(text) == text

    def test_empty_think_block(self):
        text = "<think></think>Result"
        assert strip_thinking(text) == "Result"

    def test_empty_string(self):
        assert strip_thinking("") == ""

    def test_only_think_block(self):
        text = "<think>all thinking, no answer</think>"
        assert strip_thinking(text) == ""


# --- Tests for build_llm configuration ---

class TestBuildLlm:
    """Test that build_llm passes correct parameters to ChatOllama."""

    @patch("copilot.llm.ChatOllama")
    @patch("copilot.llm.get_settings")
    def test_default_parameters(self, mock_settings, mock_chat_ollama):
        """build_llm() with no args should use settings defaults."""
        settings = MagicMock()
        settings.hosted_api_provider = None
        settings.ollama_model = "qwen3:4b"
        settings.ollama_base_url = "http://localhost:11434"
        settings.llm_temperature = 0.0
        settings.llm_top_p = 0.9
        settings.llm_num_ctx = 8192
        settings.llm_timeout = 120
        settings.llm_enable_thinking = False
        mock_settings.return_value = settings

        from copilot.llm import build_llm
        build_llm()

        mock_chat_ollama.assert_called_once()
        call_kwargs = mock_chat_ollama.call_args
        assert call_kwargs.kwargs["model"] == "qwen3:4b"
        assert call_kwargs.kwargs["temperature"] == 0.0
        assert call_kwargs.kwargs["top_p"] == 0.9
        assert call_kwargs.kwargs["num_ctx"] == 8192
        assert call_kwargs.kwargs["think"] is False  # thinking disabled

    @patch("copilot.llm.ChatOllama")
    @patch("copilot.llm.get_settings")
    def test_override_parameters(self, mock_settings, mock_chat_ollama):
        """Explicit args should override settings."""
        settings = MagicMock()
        settings.hosted_api_provider = None
        settings.ollama_model = "qwen3:4b"
        settings.ollama_base_url = "http://localhost:11434"
        settings.llm_temperature = 0.0
        settings.llm_top_p = 0.9
        settings.llm_num_ctx = 8192
        settings.llm_timeout = 120
        settings.llm_enable_thinking = False
        mock_settings.return_value = settings

        from copilot.llm import build_llm
        build_llm(model="qwen2.5:3b", temperature=0.7, num_ctx=4096)

        call_kwargs = mock_chat_ollama.call_args
        assert call_kwargs.kwargs["model"] == "qwen2.5:3b"
        assert call_kwargs.kwargs["temperature"] == 0.7
        assert call_kwargs.kwargs["num_ctx"] == 4096

    @patch("copilot.llm.ChatOllama")
    @patch("copilot.llm.get_settings")
    def test_thinking_enabled(self, mock_settings, mock_chat_ollama):
        """When thinking is enabled, think kwarg should not be False."""
        settings = MagicMock()
        settings.hosted_api_provider = None
        settings.ollama_model = "qwen3:4b"
        settings.ollama_base_url = "http://localhost:11434"
        settings.llm_temperature = 0.0
        settings.llm_top_p = 0.9
        settings.llm_num_ctx = 8192
        settings.llm_timeout = 120
        settings.llm_enable_thinking = True
        mock_settings.return_value = settings

        from copilot.llm import build_llm
        build_llm()

        call_kwargs = mock_chat_ollama.call_args
        # When thinking is enabled, 'think' should NOT be passed as False
        assert "think" not in call_kwargs.kwargs or call_kwargs.kwargs.get("think") is not False

    @patch("copilot.llm.get_settings")
    def test_invalid_provider_raises(self, mock_settings):
        """Unknown provider should raise ValueError."""
        settings = MagicMock()
        settings.hosted_api_provider = None
        mock_settings.return_value = settings

        from copilot.llm import build_llm
        with pytest.raises(ValueError, match="Unknown provider"):
            build_llm(provider="invalid_provider")

    @patch("copilot.llm.get_settings")
    def test_openai_without_key_raises(self, mock_settings):
        """OpenAI provider without API key should raise ValueError."""
        settings = MagicMock()
        settings.hosted_api_provider = None
        settings.openai_api_key = None
        settings.hosted_model_name = None
        settings.llm_temperature = 0.0
        settings.llm_top_p = 0.9
        settings.llm_timeout = 120
        mock_settings.return_value = settings

        from copilot.llm import build_llm
        with pytest.raises(ValueError, match="OPENAI_API_KEY not set"):
            build_llm(provider="openai")


# --- Tests for Settings ---

class TestSettings:
    """Test that Settings loads from environment correctly."""

    def test_default_values(self):
        """Settings should have sensible defaults."""
        from copilot.config import Settings
        # Use a fresh instance without .env file
        s = Settings(
            _env_file=None,
            database_url="postgresql://test:test@localhost/test",
        )
        assert s.llm_temperature >= 0.0
        assert s.llm_temperature <= 2.0
        assert s.agent_max_steps >= 1
        assert s.agent_sql_row_limit >= 1

    def test_env_override(self):
        """Environment variables should override defaults."""
        from copilot.config import Settings
        with patch.dict(os.environ, {"OLLAMA_MODEL": "test-model:1b"}):
            s = Settings(_env_file=None)
            assert s.ollama_model == "test-model:1b"
