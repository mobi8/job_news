"""Pytest configuration - add src/ to path for module imports."""

import sys
from pathlib import Path

# Add src/ to Python path so tests can import modules
src_path = str(Path(__file__).parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)
