"""Stand-only test vehicles (config/test_vehicles.json), off unless the stand flag is set.

Owner order 2026-11-04: T-62A (T), a copy of the 0.9.1 T-62A with tier 11 and
1000 mm armour, for checks where damage to the own vehicle gets in the way.
It is TEST_LAB data, never presented as a historical vehicle.

Owner 2026-11-05: the test vehicles are switched on per stand (flag test_lab,
environment WOT091_TEST_LAB=1 for Python/Node, gateway/physics builds with
--test-lab). Without the flag every catalogue is the main one (374 client
vehicles, research 1f6b20d1). With it p09e_research_catalog.load_catalog applies
research_overlay after the client document and the generated test_lab variants
under config/test_lab/ are used. The vehicles are out of the client tree and
shop (tools/test_vehicle_client.py).
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "config/test_vehicles.json"
SCHEMA = "wot091-test-vehicles.v1"
MAX_BYTES = 16 * 1024
VEHICLE_KEYS = {"vehicle_id", "base_vehicle_id", "resource_name", "base_resource_name", "native_type_id", "tier",
                "label", "description", "chassis", "turret", "armor_mm", "armored_parts", "tracks"}
KIND_CODE = {"chassis": 2, "turret": 3}
ENV = "WOT091_TEST_LAB"
TEST_LAB_DIR = ROOT / "config/test_lab"
# Research catalogue identity of each mode (p09e document semantic SHA-256).
BASE_RESEARCH_SHA256 = "1f6b20d1ba564e00186fed77a3da74c3bd9b135f0db30ffdef740fd5888ced80"
TEST_LAB_RESEARCH_SHA256 = "646b61935ed5a5111296a26258663d1910a4a03152fa399ef28bce227cf12492"


class TestVehicleError(ValueError):
    pass


def enabled(environ=None):
    """The stand flag: WOT091_TEST_LAB unset/"0" = main catalogues, "1" = test_lab."""
    value = (os.environ if environ is None else environ).get(ENV)
    require(value in (None, "0", "1"), ENV + " must be 0 or 1")
    return value == "1"


def research_sha256(environ=None):
    return TEST_LAB_RESEARCH_SHA256 if enabled(environ) else BASE_RESEARCH_SHA256


def require(ok, message):
    if not ok:
        raise TestVehicleError(message)


def load(path=SPEC_PATH):
    raw = Path(path).read_bytes()
    require(0 < len(raw) <= MAX_BYTES, "test vehicle spec size")
    spec = json.loads(raw)
    require(type(spec) is dict and set(spec) == {"schema", "classification", "vehicles"}
            and spec["schema"] == SCHEMA and spec["classification"].startswith("TEST_LAB_STAND_ONLY"), "spec shape")
    require(type(spec["vehicles"]) is list and 1 <= len(spec["vehicles"]) <= 4, "spec vehicle count")
    for v in spec["vehicles"]:
        require(type(v) is dict and set(v) == VEHICLE_KEYS, "spec vehicle keys")
        require(v["vehicle_id"] == "vehicle:" + v["base_vehicle_id"].split(":")[1] + ":" + v["resource_name"],
                "same-nation vehicle id")
        require(type(v["native_type_id"]) is int and 0 <= v["native_type_id"] <= 255, "native type id")
        require(type(v["tier"]) is int and 1 <= v["tier"] <= 11, "tier bound")
        require(type(v["armor_mm"]) is int and 1 <= v["armor_mm"] <= 2000, "armour bound")
        require(v["armored_parts"] == ["hull", "turret", "gun"] and v["tracks"] == "base", "armour layout")
        for part in ("chassis", "turret"):
            m = v[part]
            require(type(m) is dict and set(m) == {"base", "name", "id"} and type(m["id"]) is int
                    and 0 <= m["id"] <= 254, "module spec: " + part)
    # Line endings follow the checkout (core.autocrlf); the pin is over LF bytes.
    return spec, hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()


def _module_id(nation, kind, name):
    return "module:" + nation + ":" + kind + ":" + name


def research_overlay(document, spec=None, spec_sha256=None):
    """Return a new research document with every test vehicle derived from its base."""
    if spec is None:
        spec, spec_sha256 = load()
    require(type(spec_sha256) is str and len(spec_sha256) == 64, "spec hash required")
    doc = copy.deepcopy(document)
    for v in spec["vehicles"]:
        base = doc["vehicles"].get(v["base_vehicle_id"])
        require(base is not None and base["resource_name"] == v["base_resource_name"], "base vehicle absent")
        require(v["vehicle_id"] not in doc["vehicles"], "test vehicle already in catalogue")
        nation, nation_id = base["nation"], base["nation_id"]
        compact = (v["native_type_id"] << 8) + (nation_id << 4) + 1
        require(all(x["native_compact_id"] != compact for x in doc["vehicles"].values()), "vehicle id collision")
        rename = {}
        for part in ("chassis", "turret"):
            m = v[part]
            old, new = _module_id(nation, part, m["base"]), _module_id(nation, part, m["name"])
            row = doc["modules"].get(old)
            require(row is not None and new not in doc["modules"], "module base/collision: " + part)
            module_compact = (m["id"] << 8) + (nation_id << 4) + KIND_CODE[part]
            require(all(x["native_compact_id"] != module_compact for x in doc["modules"].values()), "module id collision")
            doc["modules"][new] = dict(row, module_id=new, resource_name=m["name"], native_compact_id=module_compact)
            rename[old] = new

        def swap(value):
            if isinstance(value, str):
                for old, new in rename.items():
                    value = value.replace(old, new)
                return value
            if isinstance(value, list):
                return [swap(x) for x in value]
            if isinstance(value, dict):
                return {swap(k): swap(x) for k, x in value.items()}
            return value

        # The server keeps the base tier (battle rules, matchmaking); the spec tier is the
        # client label only (tools/test_vehicle_client.py, `level/11` = XI).
        row = swap(copy.deepcopy(base))
        row.update(vehicle_id=v["vehicle_id"], resource_name=v["resource_name"], native_compact_id=compact,
                   not_in_shop=False, acquisition_allowed=True, unsupported_reason=None,
                   source=base["source"], test_lab=v["label"])
        doc["vehicles"][v["vehicle_id"]] = row
        for item in [v["vehicle_id"]] + sorted(row["default_unlocks"]):
            if item not in doc["initial_unlocked"]:
                doc["initial_unlocked"].append(item)
    doc["sources"] = dict(doc["sources"], test_vehicles_sha256=spec_sha256)
    return doc
