"""PHYS-01: per-vehicle 0.9.1 movement characteristics for the physics worker.

A projection of the battle profile tables (main and test_lab): chassis terrain
resistance for hard, medium and soft ground and `rotationIsAroundCenter`. The
tables hold these values from the client's vehicle XML; this file adds nothing.
The profile definitions and their pinned hashes are not touched.

    python -B -X utf8 tools/phys01_characteristics.py build
    python -B -X utf8 tools/phys01_characteristics.py check
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLES = (ROOT / "config/catalog/battle_profiles.v1.json", ROOT / "config/test_lab/battle_profiles.v1.json")
OUT = ROOT / "server/physics/Profiles/reference-characteristics.json"
POLICY = "phys01-reference-characteristics-v1"

BUILD_TABLES = (ROOT / "config/catalog/battle_builds.v1.json", ROOT / "config/test_lab/battle_builds.v1.json")
MAX_ROWS = 16384


def stage1_builds():
    """CONTENT-0 3.3 stage 1: (vehicle row of the build table, stock build, build) of every generated non-stock
    build that keeps the stock turret, gun and fuel tank (the builds the domain admits, tools/content0_builds.py)."""
    for path in BUILD_TABLES:
        for vehicle_id, v in json.loads(path.read_bytes())["vehicles"].items():
            stock = [e for e in v["builds"] if e["stock"]]
            if len(stock) != 1:
                raise ValueError(vehicle_id + ": stock build")
            s = stock[0]["modules"]
            for e in v["builds"]:
                m = e["modules"]
                if (not e["stock"] and e["status"] == "generated"
                        and (m["turret"], m["gun"], m["fuelTank"]) == (s["turret"], s["gun"], s["fuelTank"])):
                    yield v, stock[0], e


def canonical(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")


def build():
    rows = {}
    for path in TABLES:
        for r in json.loads(path.read_text(encoding="utf-8"))["vehicles"]:
            m = r.get("movement")
            if not m:
                continue
            resistance = m["terrain_resistance"]
            around = m["rotation_is_around_center"]
            if (len(resistance) != 3 or not all(isinstance(x, (int, float)) and .3 <= x <= 10 for x in resistance)
                    or not isinstance(around, bool)):
                raise ValueError(r["vehicle_id"] + ": terrain resistance/rotation source bounds")
            row = dict(vehicle=r["vehicle_id"], terrain_resistance=[float(x) for x in resistance],
                       rotation_is_around_center=around)
            for kind in {r.get("existing_kind"), r.get("kind"), r["nation"] + "-" + r["resource"]} - {None}:
                # The test_lab table repeats main rows; a repeated kind must carry the same facts.
                if rows.setdefault(kind, row) != row:
                    raise ValueError(kind + ": tables disagree")
    # CONTENT-0 3.3: a build moves on its own chassis (the build table copies the chassis movement from the client).
    for v, _, e in stage1_builds():
        m = v["chassis"][e["modules"]["chassis"]]["movement"]
        row = dict(vehicle=v["vehicle_id"], terrain_resistance=[float(x) for x in m["terrain_resistance"]],
                   rotation_is_around_center=m["rotation_is_around_center"])
        if (not all(.3 <= x <= 10 for x in row["terrain_resistance"]) or len(row["terrain_resistance"]) != 3
                or not isinstance(row["rotation_is_around_center"], bool)):
            raise ValueError(e["label"] + ": terrain resistance/rotation source bounds")
        if rows.setdefault(e["label"], row) != row:
            raise ValueError(e["label"] + ": tables disagree")
    if not 1 <= len(rows) <= MAX_ROWS:
        raise ValueError("characteristics row count")
    return canonical(dict(version=1, policy=POLICY, source="battle_profiles.v1 movement (client vehicle XML)",
                          vehicles=[dict(kind=k, **rows[k]) for k in sorted(rows)]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("build", "check"))
    args = parser.parse_args(argv)
    raw = build()
    if args.command == "build":
        OUT.write_bytes(raw)
    elif not OUT.is_file() or OUT.read_bytes() != raw:
        print(json.dumps(dict(status="FAIL_PHYS01_CHARACTERISTICS", reason="file differs from the profile tables")))
        return 2
    print(json.dumps(dict(status="PASS_PHYS01_CHARACTERISTICS", rows=raw.count(b'"kind"'), bytes=len(raw))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
