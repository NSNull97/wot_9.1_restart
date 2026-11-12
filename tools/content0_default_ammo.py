"""CONTENT-0: the 0.9.1 default ("base") ammunition of every catalogue vehicle's stock gun.

The original window option "Загрузить базовый боекомплект" sets BUY_VEHICLE_FLAG.SHELLS (16)
and the client prices/displays `gun.defaultAmmo`, i.e. `items.vehicles.getDefaultAmmoForGun`
of the mounted gun descriptor (VERIFIED in `common/items/vehicles.pyc` `_getAmmoForGun` line 2908):

    for shot in gun['shots']:                       # source order of components/guns.xml
        count = int(shot['defaultPortion'] * maxAmmo / clip + 0.5) * clip
        if current + count > maxAmmo: count = maxAmmo - current
        current += count
    if not ammo: [first shell, maxAmmo]             # (a gun always has shots in the catalogue)

`defaultPortion` is read by `_readShot` (line 4473) from the shot section, absent = 0.0. The
catalogue does not carry it, so this tool reads the pinned original `components/guns.xml` of
each nation (bounded packed-XML reader, never executing client code) and writes a committed,
canonical table `config/catalog/default_ammo.v1.json` keyed by catalogue kind. Mounted maxAmmo
and clip come from the committed test_lab battle profiles (a superset of the main catalogue).

Run:  python -X utf8 -B tools/content0_default_ammo.py --original C:/WoT_0.9.1_RU_0717_original [--check]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
for directory in (ROOT, TOOLS):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

SCHEMA = "wot091-default-ammo.v1"
TABLE = ROOT / "config/catalog/default_ammo.v1.json"
CATALOG = ROOT / "config/test_lab/catalog.v1.json"
PROFILES = ROOT / "config/test_lab/battle_profiles.v1.json"
MAX_TABLE = 512 * 1024
MAX_SHOTS = 8


class DefaultAmmoError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise DefaultAmmoError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=1) + "\n").encode("ascii")


def default_counts(max_ammo, clip, portions):
    """`_getAmmoForGun(gunDescr, None)` of 0.9.1, same float order as CPython 2.7."""
    require(type(max_ammo) is int and 1 <= max_ammo <= 10000 and type(clip) is int and 1 <= clip <= 1000, "maxAmmo/clip bound")
    require(1 <= len(portions) <= MAX_SHOTS and all(type(p) is float and 0.0 <= p <= 1.0 for p in portions), "portion bound")
    result, current = [], 0
    for portion in portions:
        count = int(portion * max_ammo / clip + 0.5) * clip
        if current + count > max_ammo:
            count = max_ammo - current
        current += count
        result.append(count)
    return result


def _portion(value, where):
    require(value is None or type(value) in (int, float, str), "defaultPortion type: " + where)
    if value is None:
        return 0.0
    try:
        number = float(value.strip() if type(value) is str else value)
    except ValueError as error:
        raise DefaultAmmoError("defaultPortion text: " + where) from error
    require(0.0 <= number <= 1.0, "defaultPortion range: " + where)
    return number


def build(original):
    from battle_any_profiles import Sources, PREFIX
    src = Sources(original)
    catalog = json.loads(CATALOG.read_bytes())
    profiles = {row["vehicle_id"]: row for row in json.loads(PROFILES.read_bytes())["vehicles"]}
    vehicles = {}
    for v in catalog["vehicles"]:
        kind, nation = v["kind"], v["nation"]
        gun = v["modules"]["gun"]["module_id"].split(":")[-1]
        g = profiles.get(v["vehicle_id"], {}).get("gun")
        require(type(g) is dict and g.get("resource") == gun and g.get("max_ammo") == v["ammo_capacity"], "profile gun differs: " + kind)
        clip = g["clip_count"]
        guns = src.xml(PREFIX + nation + "/components/guns.xml")
        prefix = "/shared[1]/" + gun + "[1]/shots[1]/"
        names = [k[len(prefix):-3] for k in guns if k.startswith(prefix) and k.count("/") == 4]
        by_resource = {s["resource_name"]: s for s in v["shells"]}
        require(len(names) == len(set(names)) and set(names) == set(by_resource), "catalogue shells differ from guns.xml shots: " + kind)
        portions = [_portion(guns.get(prefix + name + "[1]/defaultPortion[1]"), kind + "/" + name) for name in names]
        counts = default_counts(v["ammo_capacity"], clip, portions)
        vehicles[kind] = {"vehicle_id": v["vehicle_id"], "gun": gun, "max_ammo": v["ammo_capacity"], "clip": clip,
                          "shots": [{"resource": name, "native_compact_id": by_resource[name]["native_compact_id"],
                                     "default_portion": portion, "default_count": count}
                                    for name, portion, count in zip(names, portions, counts)]}
    pins = src.pins()
    return {"schema": SCHEMA, "version": 1, "target": "WoT 0.9.1 RU #717",
            "classification": "VERIFIED_STATIC: _getAmmoForGun/_readShot of common/items/vehicles.pyc; guns.xml pinned below",
            "sources": {"files": pins["files"], "catalog_sha256": sha(CATALOG.read_bytes()), "battle_profiles_sha256": sha(PROFILES.read_bytes())},
            "vehicles": dict(sorted(vehicles.items()))}


_LOADED = None


def table():
    """The committed table, canonical bytes required; rows are rechecked against the algorithm."""
    global _LOADED
    if _LOADED is None:
        raw = TABLE.read_bytes()
        require(0 < len(raw) <= MAX_TABLE, "default ammo table bound")
        document = json.loads(raw)
        require(type(document) is dict and document.get("schema") == SCHEMA and raw == canonical(document), "default ammo table not canonical")
        for kind, row in document["vehicles"].items():
            shots = row["shots"]
            require(type(shots) is list and [s["default_count"] for s in shots]
                    == default_counts(row["max_ammo"], row["clip"], [s["default_portion"] for s in shots]), "default ammo row: " + kind)
        _LOADED = document
    return _LOADED


def default_ammo(kind):
    """{native shell compact ID: default count} of one catalogue kind, or None when unknown."""
    row = table()["vehicles"].get(kind)
    if row is None:
        return None
    return row["max_ammo"], {s["native_compact_id"]: s["default_count"] for s in row["shots"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--original", required=True)
    parser.add_argument("--check", action="store_true", help="compare with the committed table instead of writing it")
    args = parser.parse_args()
    raw = canonical(build(args.original))
    if args.check:
        require(TABLE.read_bytes() == raw, "committed default ammo table differs from the client sources")
        print("default ammo table matches: " + sha(raw))
        return
    TABLE.write_bytes(raw)
    print("wrote %s %d bytes sha256 %s" % (TABLE.relative_to(ROOT).as_posix(), len(raw), sha(raw)))


if __name__ == "__main__":
    main()
