"""Generate the bounded MS-1 hangar fixture using server-content.v1 only.

This is an isolated replacement probe for the client-reading part of
``hangar_state.py``.  It intentionally reuses the frozen primitive fixture and
encoder functions, while all descriptor/profile/resource reads come through a
validated bundle.  It never imports project config, opens SQLite, or resolves
an installed client path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

from content_bundle import Bundle
from hangar_state import (FIXTURE_VERSION, bounded_hex, bounded_int, encode_data,
                          fixture, json_tree, self_test)
from packed_xml import decode as decode_packed_xml, walk as walk_packed_xml

ROOT = Path(__file__).resolve().parents[1]
MAX_OUTPUT = 16 * 1024 * 1024


def content_id(relative: str) -> str:
    return "client/" + relative


def descriptor(bundle: Bundle, descriptor_id: str = "inputs/native-ms1"):
    value = bundle.read_json(descriptor_id)
    if not isinstance(value, dict) or not isinstance(value.get("vehicle"), dict):
        raise ValueError("descriptor object with vehicle is required")
    vehicle = value["vehicle"]
    compact = bounded_hex(vehicle["compact_descr_hex"], "vehicle descriptor", 1024)
    if not 15 <= len(compact) <= 1024:
        raise ValueError("vehicle descriptor length")
    compact_id = bounded_int(vehicle["type_compact_descr"], "vehicle type ID", 1, 0xFFFFFF)
    if compact_id & 15 != 1 or compact_id & 0xFF != compact[0] or compact_id >> 8 != compact[1]:
        raise ValueError("vehicle integer/byte descriptor IDs disagree")
    name = vehicle["type_name"]
    if not isinstance(name, str) or not re.fullmatch(r"[a-z_]{1,24}:[A-Za-z0-9_-]{1,64}", name):
        raise ValueError("vehicle resource name outside bounded path syntax")
    hp = bounded_int(vehicle["max_health"], "vehicle max health", 1, 10000)
    roles = vehicle["crew_roles"]
    if not isinstance(roles, list) or not 1 <= len(roles) <= 8:
        raise ValueError("native crew roles absent")
    for role_set in roles:
        if (not isinstance(role_set, list) or not 1 <= len(role_set) <= 8
                or any(not isinstance(role, str) or not 1 <= len(role) <= 32 for role in role_set)):
            raise ValueError("native crew role shape invalid")
    dossier = bounded_hex(value["account_dossier_hex"], "account dossier", 4096)
    if not dossier:
        raise ValueError("native new-account dossier descriptor absent")
    components_raw = vehicle.get("components", {})
    if not isinstance(components_raw, dict) or len(components_raw) > 8:
        raise ValueError("native component list invalid")
    components = {}
    for key, component in components_raw.items():
        if not isinstance(key, str):
            raise ValueError("native component name invalid")
        if isinstance(component, dict):
            component = component["compact_descr"]
        components[key] = bounded_int(component, "native component ID", 1, 0xFFFFFF)

    def xml(relative: str):
        raw = bundle.read(content_id(relative))
        return dict(walk_packed_xml(decode_packed_xml(raw))), hashlib.sha256(raw).hexdigest()

    nation, vehicle_name = name.split(":", 1)
    list_values, list_sha = xml(f"res/scripts/item_defs/vehicles/{nation}/list.xml")
    prefix = "/" + vehicle_name + "[1]"
    if list_values.get(prefix + "/id[1]") != compact_id >> 8:
        raise ValueError("vehicle list and descriptor IDs disagree")
    price_node = prefix + "/price[1]"
    price = bounded_int(list_values.get(price_node), "client reference price", 0, (1 << 31) - 1)
    reference_price = (0, price) if price_node + "/gold[1]" in list_values else (price, 0)
    source = {"content_id": content_id(f"res/scripts/item_defs/vehicles/{nation}/list.xml"),
              "sha256": list_sha, "node": price_node, "source_value": price}
    normalized = {"type_name": name, "type_compact_descr": compact_id,
                  "compact_descr_hex": compact.hex(), "max_health": hp,
                  "crew_roles": roles, "components": components,
                  "account_dossier_hex": dossier.hex(), "reference_price": reference_price}

    if name != "ussr:MS-1":
        raise ValueError("portable catalog revision 2 is scoped to verified MS-1")
    if len(compact) != 15 or compact[0] != 1 or compact[14] != 0:
        raise ValueError("mounted catalogue requires measured MS-1 descriptor")
    ids = dict(zip(("chassis", "engine", "fuelTank", "radio", "turret", "gun"),
                   struct.unpack("<6H", compact[2:14])))
    type_ids = {"chassis": 2, "turret": 3, "gun": 4, "engine": 5, "fuelTank": 6, "radio": 7}
    for kind in type_ids:
        if components.get(kind) != (ids[kind] << 8) | type_ids[kind]:
            raise ValueError(f"mounted component ID differs for {kind}")
    files = {"chassis": "chassis", "turret": "turrets", "gun": "guns",
             "engine": "engines", "radio": "radios"}
    parsed = {}
    for kind, filename in files.items():
        rel = f"res/scripts/item_defs/vehicles/ussr/components/{filename}.xml"
        values, sha = xml(rel)
        matches = [(node, value) for node, value in values.items()
                   if re.fullmatch(r"/ids\[1\]/[A-Za-z0-9_.-]{1,96}\[1\]", node)
                   and isinstance(value, int) and value == ids[kind]]
        if len(matches) != 1:
            raise ValueError(f"mounted component XML ID is absent or ambiguous: {kind}")
        node, _ = matches[0]
        parsed[kind] = (node[len("/ids[1]/"):-3], values, sha)
    vehicle_values, vehicle_sha = xml("res/scripts/item_defs/vehicles/ussr/ms-1.xml")
    names = {kind: value[0] for kind, value in parsed.items()}
    local_nodes = {
        "chassis": "/chassis[1]/" + names["chassis"] + "[1]",
        "turret": "/turrets0[1]/" + names["turret"] + "[1]",
        "gun": "/turrets0[1]/" + names["turret"] + "[1]/guns[1]/" + names["gun"] + "[1]",
        "engine": "/engines[1]/" + names["engine"] + "[1]",
        "radio": "/radios[1]/" + names["radio"] + "[1]",
    }
    prices = {}
    price_sources = []
    for kind in ("chassis", "turret", "gun", "engine", "radio"):
        node = local_nodes[kind]
        values, sha = vehicle_values, vehicle_sha
        if node not in values:
            raise ValueError(f"mounted component absent from MS-1 definition: {kind}")
        if node + "/price[1]" not in values:
            if values[node] != "shared":
                raise ValueError(f"unmeasured component inheritance: {kind}")
            values, sha = parsed[kind][1], parsed[kind][2]
            node = "/shared[1]/" + names[kind] + "[1]"
        pnode = node + "/price[1]"
        amount = bounded_int(values.get(pnode), "mounted reference price", 0, (1 << 31) - 1)
        prices[components[kind]] = (0, amount) if pnode + "/gold[1]" in values else (amount, 0)
        price_sources.append({"component": kind, "content_id": content_id(
            "res/scripts/item_defs/vehicles/ussr/ms-1.xml"), "sha256": sha,
            "node": pnode, "source_value": amount})
    normalized["mounted_module_prices"] = prices
    return normalized, {"content_id": descriptor_id, "reference_price_source": source,
                        "mounted_module_price_sources": price_sources}


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> dict:
    bundle = Bundle(args.bundle)
    profile_id = args.profile_id
    profile_content_id = f"fixtures/{profile_id}/profile-input.json"
    profile = bundle.read_json(profile_content_id)
    if not isinstance(profile, dict):
        raise ValueError("profile input must be an object")
    native, descriptor_source = descriptor(bundle, args.descriptor_id)
    model, compatibility, trees = fixture(native, profile, catalog_version=2)
    payloads = {name: encode_data(tree) for name, tree in trees.items()}
    checks = self_test()
    out = Path(args.out).resolve()
    local_root = (ROOT / "local").resolve(strict=True)
    if not out.is_relative_to(local_root):
        raise ValueError("portable output must remain inside local/")
    if out.exists():
        raise FileExistsError(f"append-only output already exists: {out}")
    out.mkdir(parents=True)
    for name, raw in payloads.items():
        (out / name).write_bytes(raw)
    write_json(out / "fixture.json", model)
    write_json(out / "compatibility.json", compatibility)
    write_json(out / "payloads.json", {name: json_tree(tree) for name, tree in trees.items()})
    write_json(out / "encoder-tests.json", checks)
    bundle_manifest_raw = (bundle.root / "manifest.json").read_bytes()
    report = {"fixture_version": FIXTURE_VERSION, "ruleset": "test_lab",
              "generator": {"file": "tools/portable_hangar_state.py",
                            "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
              "bundle_manifest_sha256": hashlib.sha256(bundle_manifest_raw).hexdigest(),
              "profile_content_id": profile_content_id, "profile_sha256": hashlib.sha256(
                  bundle.read(profile_content_id)).hexdigest(),
              "descriptor": descriptor_source, "native_compatibility": "NOT_RUN",
              "files": [{"file": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
                        for name, raw in payloads.items()]}
    write_json(out / "manifest.json", report)
    return {"status": "PASS_PORTABLE_MS1_GENERATION", "output": str(out),
            "payloads": report["files"], "bundle_manifest_sha256": report["bundle_manifest_sha256"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--profile-id", default="profile1")
    parser.add_argument("--descriptor-id", default="inputs/native-ms1")
    args = parser.parse_args()
    print(json.dumps(run(args), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
