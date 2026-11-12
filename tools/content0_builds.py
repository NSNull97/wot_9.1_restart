"""CONTENT-0 3.3: the domain's view of the embedded build table (`config/<catalog|test_lab>/battle_builds.v1.json`).

The gateway seats any generated build from the same pinned table; the domain admits, in stage 1, the builds that
keep the stock turret and gun (other chassis, engine or radio): their mount, shells, capacity, crew and hit points
are the stock ones, only the label, descriptor and physics differ. Other builds stay `BATTLE_PROFILE_UNSUPPORTED`
until step 4 (shells of the mounted gun) — explicit, never seated with the stock profile.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import MappingProxyType

import test_vehicles

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 32 * 1024 * 1024
SCHEMA = "wot091-battle-builds.v1"
STAGE = "content0-3.3-stage1-stock-turret-gun"
_CACHE = {}


class BuildTableError(ValueError):
    pass


def _path():
    return (test_vehicles.TEST_LAB_DIR if test_vehicles.enabled() else ROOT / "config" / "catalog") / "battle_builds.v1.json"


def _pin():
    if test_vehicles.enabled():
        import battle_builds_data_test_lab as data
    else:
        import battle_builds_data as data
    return data.BUILDS_SHA256, data.BUILDS_BYTES


def load():
    """{descriptor hex: build} of every generated non-stock stage-1 build (cached per mode)."""
    path = _path()
    if path in _CACHE:
        return _CACHE[path]
    sha256, size = _pin()
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) != size or len(raw) > MAX_BYTES or hashlib.sha256(raw).hexdigest() != sha256:
        raise BuildTableError("build table differs from its pin")
    table = json.loads(raw)
    if table.get("schema") != SCHEMA:
        raise BuildTableError("build table schema")
    builds = {}
    for vehicle_id, v in table["vehicles"].items():
        stock = [e for e in v["builds"] if e["stock"]]
        if len(stock) != 1:
            raise BuildTableError(vehicle_id + ": stock build")
        stock = stock[0]
        for e in v["builds"]:
            if e["stock"] or e["status"] != "generated":
                continue
            m, s = e["modules"], stock["modules"]
            if (m["turret"], m["gun"], m["fuelTank"]) != (s["turret"], s["gun"], s["fuelTank"]):
                continue
            if e["max_hp"] != stock["max_hp"] or e["descriptor_hex"] in builds:
                raise BuildTableError(vehicle_id + ": stage-1 build identity")
            builds[e["descriptor_hex"]] = MappingProxyType(dict(label=e["label"], vehicle_id=vehicle_id,
                stock_kind=v["hull"]["kind"], modules=MappingProxyType(dict(m)), max_hp=e["max_hp"], mass_kg=e["mass_kg"]))
    _CACHE[path] = result = MappingProxyType(builds)
    return result


def stock_kind(kind):
    """The stock kind of a build label (`<kind>--<8 hex>`); a stock kind is itself."""
    if type(kind) is str and "--" in kind:
        base, _, digest = kind.rpartition("--")
        if base and len(digest) == 8 and all(c in "0123456789abcdef" for c in digest):
            return base
    return kind
