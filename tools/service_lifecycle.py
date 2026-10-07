"""Compatibility import. Edit server/control/lifecycle.py, not this file."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from server.control import lifecycle as implementation
sys.modules[__name__] = implementation
