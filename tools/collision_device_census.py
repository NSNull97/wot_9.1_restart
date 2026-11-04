"""Census of device materials in every #717 vehicle collision visual (read-only).

Question (SHELL-02): do the client's hull/turret/gun collision models carry internal
device volumes (engine, ammoBay, fuelTank, radio, turretRotator, crew roles) that could
replace the invented LAB module boxes? Every `*/collision/*.visual` of the seven
vehicle packages is read as packed XML; each primitive group's `materialKind` is
mapped through the pinned `material_kinds.xml`. Nothing is executed or modified.

Command: `python -B -X utf8 tools/collision_device_census.py --original C --out local/evidence/<fresh>/census.json`
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
import re
import sys

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
for directory in (ROOT, TOOLS):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))
import battle_any_profiles as profiles
import ms1_contact_bundle as materials
from packed_xml import decode
from vehicle_physics_profile import no_links, owned

SCHEMA = "wot091-collision-device-census.v1"
DEVICE_NAMES = ("engine", "ammoBay", "fuelTank", "radio", "turretRotator", "commander", "driver",
                "radioman_1", "radioman_2", "gunner_1", "gunner_2", "loader_1", "loader_2")
MAX_VISUALS = 8192
NATION_OF_PACKAGE = {"russian": "ussr", "german": "germany", "american": "usa", "french": "france",
                     "british": "uk", "chinese": "china", "japan": "japan"}


def folder_nation(member):
    return member.split("/")[1]
KIND_PATH = re.compile(r"/renderSet\[1\]/geometry\[1\]/primitiveGroup\[([0-9]+)\]/material\[1\]/materialKind\[1\]")


def census(original):
    src = profiles.Sources(original)
    kinds_raw = src.member(materials.MISC_REL, materials.KINDS_MEMBER)
    profiles.require(kinds_raw is not None and profiles.pin(kinds_raw) == materials.MEMBER_PINS[materials.KINDS_KEY],
                     "material kinds pin differs")
    mapping = materials._kind_mapping(decode(kinds_raw, max_bytes=profiles.MAX_MEMBER))
    by_id = {v: k for k, v in mapping.items()}
    devices = {mapping[name] for name in DEVICE_NAMES}
    registry = {r["vehicle_id"]: r for r in json.loads(profiles.TABLE.read_bytes())["vehicles"]}
    parts, visuals, with_devices = collections.Counter(), 0, []
    for folder, package in sorted(profiles.PACKAGE_FOLDERS.items()):
        archive, index = src.archive("res/packages/" + package)
        for name in sorted(index):
            if not (name.endswith(".visual") and "/collision/" in name):
                continue
            visuals += 1
            profiles.require(visuals <= MAX_VISUALS, "collision visual bound")
            vf = profiles.flat(src.member("res/packages/" + package, name))
            part = name.rsplit("/", 1)[-1].split(".")[0]
            found = collections.Counter()
            for key, value in vf.items():
                if KIND_PATH.fullmatch(key) and isinstance(value, int):
                    parts[(part.split("_")[0].lower(), by_id.get(value, str(value)))] += 1
                    if value in devices:
                        found[by_id[value]] += 1
            if found:
                # Package folder `R59_A44` names catalogue resource `A44`; every hit must map.
                folder, nation = name.split("/")[2], NATION_OF_PACKAGE[folder_nation(name)]
                matches = [vid for vid, r in registry.items() if r["nation"] == nation
                           and (folder == r["resource"] or folder.endswith("_" + r["resource"]))]
                profiles.require(len(matches) == 1, "device visual without exactly one catalogue vehicle: " + name)
                with_devices.append(dict(member=package + "!" + name, device_groups=dict(sorted(found.items())),
                                         battle_profiles=[dict(vehicle_id=v, status=registry[v]["status"],
                                                               refusal=registry[v].get("refusal")) for v in sorted(matches)]))
    return dict(schema=SCHEMA, target="v.0.9.1 #717 RU", collision_visuals=visuals,
                material_groups_by_part=[dict(part=p, material=m, groups=n) for (p, m), n in sorted(parts.items())],
                visuals_with_device_groups=with_devices,
                battle_registry_vehicles_with_device_groups=sorted(
                    {b["vehicle_id"] for v in with_devices for b in v["battle_profiles"] if b["status"] == "generated"}),
                source_pins=src.pins(), client_bytecode_executed=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--original", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    local = no_links(ROOT / "local").resolve(strict=True)
    out = owned(local, Path(args.out).absolute())
    profiles.require(not out.exists() and out.parent.is_dir(), "fresh output with existing parent required")
    result = census(args.original)
    with out.open("xb") as stream:
        stream.write(profiles.canonical(result) + b"\n")
    print(json.dumps(dict(collision_visuals=result["collision_visuals"],
                          visuals_with_device_groups=len(result["visuals_with_device_groups"]),
                          battle_registry_vehicles_with_device_groups=result["battle_registry_vehicles_with_device_groups"]),
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
