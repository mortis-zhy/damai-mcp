"""Pytest fixtures shared across all tests."""
from __future__ import annotations

import sys
from pathlib import Path

# Add src to sys.path so tests can `import damai_mcp` without installing
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

