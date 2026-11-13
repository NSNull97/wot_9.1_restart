"""CONTENT-0 3.3: the domain's view of the embedded build table (`config/<catalog|test_lab>/battle_builds.v1.json`).

The gateway seats any generated build from the same pinned table. Step 3 stage 1 admitted the builds with the stock
turret and gun; step 4 (owner 13.11) admits every generated build: a build keeps the stock mount when its turret x gun
pair is the stock one, otherwise the mount of its own pair (`mounts()`: capacity and ordered shells of the client's
turret/gun XML, copied by the build table). Hit points, device maxima and crew are the build's own.
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
STAGE = "content0-4-every-generated-build"
MAX_MOUNTS = 4096
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


def _table():
    path = _path()
    if ("table", path) in _CACHE:
        return _CACHE[("table", path)]
    sha256, size = _pin()
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) != size or len(raw) > MAX_BYTES or hashlib.sha256(raw).hexdigest() != sha256:
        raise BuildTableError("build table differs from its pin")
    table = json.loads(raw)
    if table.get("schema") != SCHEMA:
        raise BuildTableError("build table schema")
    _CACHE[("table", path)] = table
    return table


def pair(modules):
    """The mount key of a configuration: `<turret id>/<gun id>` (the build table's `mounts` key)."""
    return modules["turret"] + "/" + modules["gun"]


def devices_of(v, m):
    """The terminal policy's ordered device maxima (extra index 26.., the gateway Entry caps order) of configuration
    ``m`` of build-table vehicle ``v``."""
    caps = (v["engines"][m["engine"]]["device"], v["hull"]["ammo_bay"], v["fuel_tanks"][m["fuelTank"]]["device"],
            v["radios"][m["radio"]]["device"], v["chassis"][m["chassis"]]["track"], v["chassis"][m["chassis"]]["track"],
            v["mounts"][pair(m)]["device"], v["turrets"][m["turret"]]["rotator"], v["turrets"][m["turret"]]["surveying"])
    return tuple((26 + i, cap["max_health"]) for i, cap in enumerate(caps))


def mounts():
    """{(vehicle id, turret id, gun id): mount} of every turret x gun pair of the build table (cached per mode):
    capacity (`max_ammo`) and the ordered shells (suffix, resource, family, item ID, native compact ID, gold flag)."""
    path = _path()
    if ("mounts", path) in _CACHE:
        return _CACHE[("mounts", path)]
    result = {}
    for vehicle_id, v in _table()["vehicles"].items():
        for key, m in v["mounts"].items():
            turret, _, gun = key.partition("/")
            shots, suffixes = m["shots"], m["shell_suffixes"]
            capacity = m["gun"]["max_ammo"]
            if (not turret or not gun or len(shots) != len(suffixes) or not 1 <= len(shots) <= 3 or len(set(suffixes)) != len(suffixes)
                    or type(capacity) is not int or not 1 <= capacity <= 4000):
                raise BuildTableError(vehicle_id + ": mount " + key)
            result[(vehicle_id, turret, gun)] = MappingProxyType(dict(capacity=capacity, shells=tuple(
                (suffix, s["resource"], s["family"], s["item_id"], s["compact_descr"], bool(s["premium_gold_flag"]))
                for suffix, s in zip(suffixes, shots)), dispersion_radius_m=m["gun"]["shot_dispersion_radius"]))
    if not 1 <= len(result) <= MAX_MOUNTS:
        raise BuildTableError("mount count")
    _CACHE[("mounts", path)] = result = MappingProxyType(result)
    return result


def load():
    """{descriptor hex: build} of every generated non-stock build (cached per mode)."""
    path = _path()
    if path in _CACHE:
        return _CACHE[path]
    table = _table()
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
            if m["fuelTank"] != s["fuelTank"] or e["descriptor_hex"] in builds or pair(m) not in v["mounts"]:
                raise BuildTableError(vehicle_id + ": build identity")
            stock_pair = (m["turret"], m["gun"]) == (s["turret"], s["gun"])
            if stock_pair and e["max_hp"] != stock["max_hp"]:
                raise BuildTableError(vehicle_id + ": build of the stock pair with other hit points")
            devices = devices_of(v, m)
            builds[e["descriptor_hex"]] = MappingProxyType(dict(label=e["label"], vehicle_id=vehicle_id,
                stock_kind=v["hull"]["kind"], modules=MappingProxyType(dict(m)), max_hp=e["max_hp"], mass_kg=e["mass_kg"],
                stock_pair=stock_pair, devices=devices, crew_count=len(v["hull"]["crew_seats"])))
    _CACHE[path] = result = MappingProxyType(builds)
    return result


def stock_kind(kind):
    """The stock kind of a build label (`<kind>--<8 hex>`); a stock kind is itself."""
    if type(kind) is str and "--" in kind:
        base, _, digest = kind.rpartition("--")
        if base and len(digest) == 8 and all(c in "0123456789abcdef" for c in digest):
            return base
    return kind
