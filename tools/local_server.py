"""Compatibility entrypoint. Edit server/control/service.py, not this file."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from server.control import service as implementation

if __name__ == '__main__':
    implementation.main()
else:
    # Preserve imports and patch.object semantics of existing research tests.
    sys.modules[__name__] = implementation
