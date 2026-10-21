"""CAT-01 single catalog for Python domain workers, behind an explicit flag.

The legacy closed lists (``p04m_stock_registry.PINS``/``NEW_KINDS``,
``p04m_pool_store.SHELL_ROWS``) stay the default. A worker started with
``--catalog-sha256 <hash>`` activates this module once; the hash must equal the
committed ``config/catalog/catalog.v1.json`` bytes and the generated
``catalog_v1_data`` binding, otherwise the worker refuses to start.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import catalog_v1_data as data

CATALOG_PATH = Path(__file__).resolve().parents[1] / "config/catalog/catalog.v1.json"
MAX_BYTES = 256 * 1024
_active = None


class CatalogMismatch(ValueError):
    """The requested, committed and generated catalog hashes differ."""


def _tuples(value):
    if isinstance(value, dict):
        return {k: _tuples(v) for k, v in value.items()}
    if isinstance(value, list):
        return tuple(_tuples(v) for v in value)
    return value


def activate(expected_sha256):
    """Bind this process to one catalog; repeated activation must name the same hash."""
    global _active
    raw = CATALOG_PATH.read_bytes()
    if not 0 < len(raw) <= MAX_BYTES:
        raise CatalogMismatch("catalog size bound")
    digest = hashlib.sha256(raw).hexdigest()
    if not (type(expected_sha256) is str and expected_sha256 == digest == data.CATALOG_SHA256):
        raise CatalogMismatch("catalog hash differs from this worker build")
    document = json.loads(raw)
    if document.get("schema") != data.SCHEMA or _tuples(document["vehicles"]) != data.VEHICLES:
        raise CatalogMismatch("generated Python binding differs from catalog bytes")
    if _active is not None and _active != digest:
        raise CatalogMismatch("worker already bound to another catalog")
    _active = digest
    return digest


def active():
    return _active is not None


def deactivate_for_tests():
    global _active
    _active = None


def vehicles():
    if _active is None:
        raise CatalogMismatch("catalog v1 not active")
    return data.VEHICLES


def by_kind(kind):
    return next((v for v in vehicles() if v["kind"] == kind), None)


def stock_pins():
    """Same shape as the legacy ``p04m_stock_registry.PINS`` rows."""
    return {v["kind"]: (v["resource_name"], v["native_compact_id"], v["descriptor_hex"], v["max_hp"],
                        v["ammo_capacity"], v["shells"][0]["native_compact_id"],
                        tuple(tuple(seat["roles"]) for seat in v["crew"]))
            for v in vehicles()}


def shell_rows():
    """Same shape as the legacy ``p04m_pool_store.SHELL_ROWS`` rows, for every kind."""
    return {v["kind"]: tuple((s["suffix"], s["resource_name"], s["family"], s["item_id"]) for s in v["shells"])
            for v in vehicles()}


def admission(kind):
    """``always`` | ``zero_economy_policy`` | ``none``; unknown kinds are ``none``."""
    row = by_kind(kind)
    return "none" if row is None else row["battle_admission"]


def legacy_inventory(kind):
    row = by_kind(kind)
    return None if row is None else row["legacy_inventory"]
