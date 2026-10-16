"""Bounded read-only qualification of the exact five #717 device-cap profiles.

The generated JSON is source evidence, not permission to admit vehicles or a
claim that original internal volumes/server damage algorithms are known.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import packed_xml

ROOT = Path(__file__).resolve().parents[1]
CAPS = ROOT / "server/gateway/src/shared/p06t_device_source_caps.json"
CAPS_SHA256 = "3c4219c2adda799677dea310e84765bbfebca6edfa06aa3db450a7ddfb4875b5"
POLICY = ROOT / "server/gateway/src/shared/p06t_device_policy.json"
POLICY_SHA256 = "cded466bf3c21243c10c0bcee8a013ab4cffc20f31f7275d4eab1672060b3717"
VEHICLES = ("ms-1", "is-7", "t-26", "t-34", "t-34-85")
DEVICE_FILES = ("engines", None, "fueltanks", "radios", None, None, "guns", None, None)


def require(value: bool, reason: str) -> None:
    if not value:
        raise ValueError(reason)


def pinned_json(path: Path, digest: str) -> dict:
    raw = path.read_bytes()
    require(len(raw) <= 65536 and hashlib.sha256(raw).hexdigest() == digest, "P06T closed definition pin")
    value = json.loads(raw)
    require(type(value) is dict, "P06T source object")
    return value


def qualify(original_root: Path) -> dict:
    original_root = original_root.resolve(strict=True)
    caps = pinned_json(CAPS, CAPS_SHA256)
    policy = pinned_json(POLICY, POLICY_SHA256)
    require(policy["source_caps_sha256"] == CAPS_SHA256, "P06T policy/source binding")
    require(caps["schema"] == "p06t-device-source-caps.v1" and len(caps["profiles"]) == 5, "P06T source schema")
    trees = {}
    checked = {}
    for relative, pin in caps["source_pins"].items():
        path = (original_root / relative).resolve(strict=True)
        require(path.is_relative_to(original_root), "P06T source path outside original root")
        require(path.stat().st_size == pin["bytes"] and path.stat().st_size <= 1048576, "P06T source size pin")
        raw = path.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == pin["sha256"], "P06T original source SHA pin")
        trees[relative] = dict(packed_xml.walk(packed_xml.decode(raw, max_bytes=1048576)))
        checked[relative] = pin
    prefix = "res/scripts/item_defs/vehicles/"
    common = trees[prefix + "common/vehicle.xml"]
    require(common["/miscParams[1]/minFireStartingDamage[1]"] == caps["min_fire_starting_damage"] == 21,
            "P06T minFireStartingDamage source")
    extra_names = [p.rsplit("/", 1)[-1].split("[")[0] for p in common if p.startswith("/extras[1]/") and p.count("/") == 2]
    require(extra_names[25:34] == ["engineHealth", "ammoBayHealth", "fuelTankHealth", "radioHealth", "leftTrackHealth",
                                "rightTrackHealth", "gunHealth", "turretRotatorHealth", "surveyingDeviceHealth"], "P06T device extra order")
    for index, row in enumerate(caps["profiles"]):
        vehicle = trees[prefix + "ussr/" + VEHICLES[index] + ".xml"]
        require(len(row["devices"]) == 9 and len(row["crew"]) in (2, 3, 4, 5), "P06T module/seat count")
        for device_index, device in enumerate(row["devices"]):
            source_file = DEVICE_FILES[device_index]
            tree = vehicle if source_file is None else trees[prefix + "ussr/components/" + source_file + ".xml"]
            source = device["source_prefix"]
            require(tree[source + "/maxHealth[1]"] == device["max_health"]
                    and tree[source + "/maxRegenHealth[1]"] == device["max_regen_health"], "P06T device health source")
            require(device["extra_index"] == 26 + device_index, "P06T device extra identity")
        engine_source = row["devices"][0]["source_prefix"]
        engine_tree = trees[prefix + "ussr/components/engines.xml"]
        chance = float(engine_tree[engine_source + "/fireStartingChance[1]"])
        require(math.isfinite(chance) and 0 <= chance <= 1 and chance == row["engine_fire_starting_chance"], "P06T engine fire source")
        crew_paths = [p for p in vehicle if p.startswith("/crew[1]/") and p.count("/") == 2]
        primary = [p.rsplit("/", 1)[-1].split("[")[0] for p in crew_paths]
        require(primary == [seat["roles"][0] for seat in row["crew"]], "P06T source primary crew order")
        for seat, path in zip(row["crew"], crew_paths):
            raw = vehicle[path]
            # Packed DataSection binary-as-text strings are retained by the
            # bounded inspector as a base64 field. Its original readString
            # spelling is already bound by the accepted P04M/P06T source audit.
            spelling = raw if type(raw) is str else raw.get("base64") if type(raw) is dict else None
            require(type(spelling) is str and spelling.split() == seat["roles"][1:], "P06T combined crew duties source")
        require(row["crew"] == policy["profiles"][index]["crew"], "P06T policy crew binding")
    return {"schema": "p06t-device-source-qualification.v1", "status": "PASS_STATIC_SOURCE", "source_pins": checked,
            "source_caps_sha256": CAPS_SHA256, "policy_sha256": POLICY_SHA256, "profiles": 5, "devices": 45, "crew_seats": 19,
            "original_execution": "NOT_RUN", "internal_volumes": "UNKNOWN", "historical_server_solver": "UNKNOWN",
            "runtime_world_native_ui_audio": "NOT_RUN", "admission_authorized": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="Fresh owned evidence directory")
    args = parser.parse_args()
    output = args.out.resolve()
    if not output.is_relative_to((ROOT / "local").resolve()) or output == (ROOT / "local").resolve():
        parser.error("P06T evidence output must be under this repository's owned local directory")
    require(not output.exists(), "P06T evidence output must be fresh")
    output.mkdir(parents=True)
    try:
        result = qualify(args.original_root)
    except (ValueError, OSError, KeyError, TypeError) as error:
        result = {"status": "FAIL_STATIC_SOURCE", "reason": str(error), "admission_authorized": False}
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "receipt": str(output / "result.json")}))
    return 0 if result["status"] == "PASS_STATIC_SOURCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
