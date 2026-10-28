"""BATTLE-ANY read-only access to the generated battle profile table.

The table (`config/catalog/battle_profiles.v1.json`) is bound by exact bytes to
the generated `battle_any_data.TABLE_SHA256`; any other bytes refuse to load.
Stage 1: no runtime layer consumes a generated row and no row grants admission;
`readiness()` therefore answers the wire code every parser already understands.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import MappingProxyType

import battle_any_data as data

TABLE_PATH = Path(__file__).resolve().parents[1] / "config/catalog/battle_profiles.v1.json"
MAX_BYTES = 4 * 1024 * 1024
_table = None


class TableMismatch(ValueError):
    """The committed table bytes differ from the generated binding."""


def table():
    global _table
    if _table is None:
        raw = TABLE_PATH.read_bytes()
        if not 0 < len(raw) <= MAX_BYTES or len(raw) != data.TABLE_BYTES:
            raise TableMismatch("battle profile table size")
        if hashlib.sha256(raw).hexdigest() != data.TABLE_SHA256:
            raise TableMismatch("battle profile table SHA-256 differs from binding")
        value = json.loads(raw)
        if value["schema"] != data.SCHEMA:
            raise TableMismatch("battle profile table schema")
        _table = MappingProxyType({row["vehicle_id"]: row for row in value["vehicles"]})
    return _table


def profile(vehicle_id):
    """The generated row of a stock assembly, or None for an unknown vehicle."""
    return table().get(vehicle_id)


def readiness(vehicle_id):
    """(admission, readiness_code, refusal) of a catalogue vehicle; never admits in stage 1."""
    row = profile(vehicle_id)
    if row is None:
        return False, "BATTLE_PROFILE_UNSUPPORTED", "UNKNOWN_VEHICLE_PROFILE"
    return row["battle_admission"], row["readiness_code"], row["refusal"]
