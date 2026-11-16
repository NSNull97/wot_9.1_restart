"""Generate the module loadouts used by active test_lab bots from pinned #717 data.

Run `python -B -X utf8 -m tools.bot_top_loadouts --original <client>`.
Pass `--check` to verify the committed result without writing a file.
"""

import argparse
import hashlib
import json
from pathlib import Path

from tools import test_vehicles
from tools.destructible_catalog import read
from tools.p09e_research_catalog import (
    KINDS, PIN_PATH, TARGET, child, children, identifier, load_catalog, number, scalar,
)
from tools.packed_xml import decode


ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "config/test_lab"
OUTPUT = LAB / "bot_top_loadouts.v1.json"
SCHEMA = "wot091-bot-top-loadouts.v1"
POLICY = "native-module-level-and-order.v1"
LEVEL_ORDER = ("gun", "turret", "chassis", "engine", "radio")
BRANCHES = {"chassis": "chassis", "engine": "engines", "radio": "radios"}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def module_levels(source, vehicle):
    """Resolve source levels from each actual native mount and component."""
    nation = vehicle["nation"]
    raw = source(vehicle["source"])
    prefix = f"res/scripts/item_defs/vehicles/{nation}/components/"

    def definition(kind, name, node):
        if scalar(node) != "shared":
            return node
        common = source(prefix + KINDS[kind][1] + ".xml")
        return child(child(common, "shared"), name)

    levels = {}
    for kind, branch in BRANCHES.items():
        for name, node in children(child(raw, branch)):
            key = identifier(kind, nation, name)
            levels[key] = number(child(definition(kind, name, node), "level"), key + " level")

    gun_levels = {}
    for position in range(len(vehicle["turret_positions"])):
        for turret, node in children(child(raw, f"turrets{position}")):
            turret_id = identifier("turret", nation, turret)
            base = definition("turret", turret, node)
            levels[turret_id] = number(child(base, "level"), turret_id + " level")
            for gun, contents in children(child(node, "guns", child(base, "guns"))):
                gun_id = identifier("gun", nation, gun)
                gun_levels[turret_id, gun_id] = number(
                    child(definition("gun", gun, contents), "level"), gun_id + " level",
                )
    return levels, gun_levels


def build_rank(vehicle, build, levels, gun_levels):
    modules = build["modules"]
    turret, gun = modules["turret"], modules["gun"]
    native_order = (
        vehicle["turret_guns"][turret].index(gun),
        *(vehicle["compatible"][kind].index(modules[kind]) for kind in (*LEVEL_ORDER[1:], "fuelTank")),
    )
    # Fuel tanks have no native module level. Their positional order breaks a tie only.
    level_order = (gun_levels[turret, gun], *(levels[modules[kind]] for kind in LEVEL_ORDER[1:]))
    return level_order, native_order


def preferred_build(vehicle, builds, qualified, stock_label, levels, gun_levels):
    """Choose an existing compatible descriptor, including stock when it is already top."""
    eligible = [row for row in builds if row["status"] == "generated" and row.get("required_suspension") is None
                and (row["label"] in qualified or (row["stock"] and row["label"] == stock_label))]
    if not any(row["stock"] and row["label"] == stock_label for row in eligible):
        raise ValueError(f"Missing generated stock build for {vehicle['vehicle_id']}")
    return max(eligible, key=lambda row: build_rank(vehicle, row, levels, gun_levels))["label"]


def generate(original):
    original = Path(original)
    catalog = load_catalog(original, cache_dir=None)
    if catalog.sha256 != test_vehicles.research_sha256():
        raise ValueError("Unexpected #717 research catalog")
    source_manifest = read(PIN_PATH, 256 * 1024)
    source_cache = {}

    def source(relative):
        if relative not in source_cache:
            pin = catalog.document["sources"][relative]
            raw = read(original / relative, pin["bytes"], pin["sha256"])
            if len(raw) != pin["bytes"]:
                raise ValueError(f"Native source length changed: {relative}")
            source_cache[relative] = decode(raw)
        return source_cache[relative]

    builds_raw = read(LAB / "battle_builds.v1.json", 32 * 1024 * 1024)
    stock_raw = read(LAB / "battle_profiles.v1.json", 16 * 1024 * 1024)
    qualification_raw = read(LAB / "battle_qualification.v1.json", 16 * 1024 * 1024)
    builds, stock, qualifications = map(json.loads, (builds_raw, stock_raw, qualification_raw))
    if (builds["schema"] != "wot091-battle-builds.v1" or stock["schema"] != "wot091-battle-profiles.v1"
            or qualifications["schema"] != "wot091-battle-qualification.v1" or builds["target"] != TARGET
            or builds["research_catalog_sha256"] != test_vehicles.TEST_LAB_RESEARCH_SHA256
            or builds["profile_table_sha256"] != sha(stock_raw)):
        raise ValueError("Unexpected test_lab battle catalog or qualification table")
    qualified = {row["kind"] for row in qualifications["profiles"]}
    test_only = {row["vehicle_id"] for row in test_vehicles.load()[0]["vehicles"]}

    by_vehicle = {}
    for row in stock["vehicles"]:
        vehicle_id = row["vehicle_id"]
        if row["status"] != "generated" or vehicle_id in test_only:
            continue
        vehicle = catalog.vehicles[vehicle_id]
        levels, gun_levels = module_levels(source, vehicle)
        by_vehicle[vehicle_id] = preferred_build(
            vehicle, builds["vehicles"][vehicle_id]["builds"], qualified, row["kind"], levels, gun_levels,
        )

    result = {
        "schema": SCHEMA, "target": TARGET, "policy": POLICY,
        "source": {
            "native_catalog_sha256": test_vehicles.BASE_RESEARCH_SHA256,
            "native_source_manifest_lf_sha256": sha(source_manifest.replace(b"\r\n", b"\n")),
            "battle_builds_sha256": sha(builds_raw), "battle_profiles_sha256": sha(stock_raw),
            "battle_qualification_sha256": sha(qualification_raw),
        },
        "by_vehicle": by_vehicle,
    }
    return (json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("ascii")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--check", action="store_true", help="Verify the committed table byte for byte")
    args = parser.parse_args()
    raw = generate(args.original)
    if args.check:
        if OUTPUT.read_bytes() != raw:
            parser.exit(1, "bot top loadouts differ from the generated table\n")
    else:
        OUTPUT.write_bytes(raw)
    print(f"bot top loadouts: {len(json.loads(raw)['by_vehicle'])} vehicles, SHA-256 {sha(raw)}")


if __name__ == "__main__":
    main()
