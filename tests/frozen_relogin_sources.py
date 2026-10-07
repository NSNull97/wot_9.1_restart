"""Read actual archived source bytes for historical verifier regressions only.

The frozen validators target the 2026-10-05 gateway, not today's canonical
server/layout.json modules. Tests explicitly patch their reader with this
fixture; it never changes source pins, writes old paths, or enables a live run.
Missing, oversized and changed archive files still fail the original checks.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    ROOT / 'tools/wg_probe/src/gateway091.rs': ROOT / (
        'local/evidence/20261005-p02-inprocess-relogin/gui/gateway-review-01/'
        'frozen-01/sources/tools__wg_probe__src__gateway091.rs'),
    ROOT / 'tools/wg_probe/src/capture091.rs': ROOT / (
        'local/evidence/20261005-p02-ms1-crew/wire/contract-01/'
        'sources/tools/wg_probe/src/capture091.rs'),
}


def historical_source_reader(read_limited):
    def read(path, maximum):
        return read_limited(SOURCES.get(path, path), maximum)
    return read
