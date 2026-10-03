"""
conftest.py — Shared pytest fixtures and configuration.

Adds the src/ directory to sys.path so 'copilot' is importable.
"""

import sys
from pathlib import Path

# Add src/ to path so we can import copilot.*
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
