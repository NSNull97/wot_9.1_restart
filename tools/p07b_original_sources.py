"""Bounded read-only source ledger for P07B spotting (#717, 0.9.1).

The reader consumes the permitted original client and already-retained evidence
as bytes/data.  It never imports or executes client modules, starts a process,
or copies client resources.  The output is a small JSON receipt suitable for a
C: evidence directory.
"""

from __future__ import print_function

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


MAX_FILE = 16 * 1024 * 1024
MAX_PYC = 1024 * 1024
MAX_OUTPUT = 2 * 1024 * 1024
SCHEMA = "p07b-original-spotting-source-ledger.v1"

# These are exactly the six static rows from the retained P07A source boundary.
STATIC_PINS = [
    ("res/scripts/entity_defs/avatar.def", 7450,
     "38cf983d6ea1fcaf1bbca25fd18567fed5abc3b2e07fbe14b168f46fa883f74d"),
    ("res/scripts/entity_defs/vehicle.def", 5588,
     "08dc1e6be577f80a04bf813ca046550201a3c4e673dad1540c5f1c6a047d1297"),
    ("res/scripts/entity_defs/arena.def", 3036,
     "e50906f11e0fcbf1f5b41e105353689ca4b9e3cdb1768b7ac41edab7f3c2f4fc"),
    ("res/scripts/client/avatar.pyc", 83656,
     "c13cd58a4c5d766dfd3c5f47ae7be50c962aee6c7f8cf25b4341322381f21e0e"),
    ("res/scripts/client/vehicle.pyc", 24119,
     "b81d08ca14092bb8912adb2eff20325c3dd23424868bc03164cfe6b8da50463c"),
    ("res/scripts/client/clientarena.pyc", 12823,
     "30b21bb0e386b909d162f127b79b86e5da1aeecb65e9c6700b2b50f435dbd455"),
]

# Seven source-mounted profiles used by the current closed laboratory.  These
# are base circularVisionRadius values; they are not an effective spotting
# calculation (crew, equipment and camouflage are intentionally absent).
RANGE_SPECS = [
    ("ms1", "ussr/ms-1.xml", "T-18_Standart", 23, 240),
    ("is7", "ussr/is-7.xml", "IS-7", 47, 400),
    ("t26", "ussr/t-26.xml", "T-26_cylindrical", 30, 280),
    ("t34", "ussr/t-34.xml", "T-34_mod_1940", 0, 240),
    ("t3485", "ussr/t-34-85.xml", "T-34-85", 17, 350),
    ("wt-e100-128", "germany/waffentrager_e100.xml",
     "Turret_1_Waffentrager_E100", 134, 420),
    ("fv215b-183", "uk/gb48_fv215b_183.xml",
     "Turret_1_GB48_FV215b_183", 69, 400),
]

# Exactly seven dynamic observations.  The first two are schema declarations;
# the rest are inert bytecode/evidence observations used by the UI contract.
DYNAMIC_IDS = (
    "avatar.client_updateVehicleMiscStatus",
    "avatar.base_updateVehicleMiscStatus",
    "constants.VEHICLE_MISC_STATUS_IS_OBSERVED_BY_ENEMY",
    "client_avatar.PlayerAvatar_updateVehicleMiscStatus",
    "client_battle.Battle_showSixthSenseIndicator",
    "client_battle.Battle_afterCreate_sixthSenseDuration",
    "gui_settings.sixthSenseDuration",
)


def _fail(message):
    raise ValueError(message)


def _safe_root(value, label):
    p = Path(value).expanduser().resolve(strict=True)
    if not p.is_dir():
        _fail("{} is not a directory: {}".format(label, p))
    return p


def _under(path, root):
    try:
        path.resolve(strict=True).relative_to(root.resolve(strict=True))
        return True
    except (OSError, ValueError):
        return False


def _read(root, relative, limit=MAX_FILE):
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts:
        _fail("source path escapes original root: {}".format(relative))
    path = (root / rel).resolve(strict=True)
    if not _under(path, root):
        _fail("source path escapes original root: {}".format(relative))
    if not path.is_file():
        _fail("source is not a regular file: {}".format(relative))
    size = path.stat().st_size
    if size > limit:
        _fail("source exceeds bounded reader limit: {} ({} bytes)".format(relative, size))
    data = path.read_bytes()
    if len(data) != size:
        _fail("source changed while reading: {}".format(relative))
    return path, data


def _pin(root, relative, expected_size, expected_sha):
    path, data = _read(root, relative, MAX_PYC if relative.endswith(".pyc") else MAX_FILE)
    digest = hashlib.sha256(data).hexdigest()
    if len(data) != expected_size or digest != expected_sha:
        _fail("hash/size pin mismatch for {}: {} {}".format(relative, len(data), digest))
    return {"path": relative, "bytes": len(data), "sha256": digest}


def _load_tools(script_root):
    tools = script_root / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    try:
        import packed_xml  # pylint: disable=import-error
        import py27_static  # pylint: disable=import-error
    except ImportError as exc:
        _fail("bounded helper modules unavailable: {}".format(exc))
    return packed_xml, py27_static


def _pyc_records(data, py27_static):
    # parse_pyc/records return plain data structures and never execute code.
    try:
        root = py27_static.parse_pyc(data)
        return list(py27_static.records(root))
    except Exception as exc:
        _fail("bounded pyc parse failed: {}".format(exc))


def _as_text(value, py27_static):
    value = py27_static.text(value)
    return value


def _find_record(records, suffix, py27_static):
    for name, code in records:
        if str(_as_text(name, py27_static)).endswith(suffix):
            return code
    _fail("bytecode record not found: {}".format(suffix))


def _rows(packed_xml, data):
    try:
        return dict(packed_xml.walk(packed_xml.decode(data)))
    except Exception as exc:
        _fail("bounded packed XML parse failed: {}".format(exc))


def _normal(value, py27_static):
    value = _as_text(value, py27_static)
    if isinstance(value, dict) and set(value) == {"base64"}:
        return "base64:" + value["base64"]
    return value


def _method_args(rows, prefix):
    values = []
    for index in range(1, 32):
        key = prefix + "/Arg[{}]".format(index)
        if key not in rows:
            break
        value = rows[key]
        if isinstance(value, dict) and set(value) == {"base64"}:
            value = value["base64"]
        values.append(value)
    return values


def _evidence_gui_duration(evidence_root):
    if evidence_root is None:
        return None
    candidates = [
        Path("20261005-p02-map-drive/bind01-prepare/bundle/res_mods/0.9.1/gui/gui_settings.xml"),
        Path("20261005-p02-map-drive/bind01-prepare/postrun/res_mods/0.9.1/gui/gui_settings.xml"),
    ]
    for relative in candidates:
        path = (evidence_root / relative).resolve()
        if not _under(path, evidence_root) or not path.is_file():
            continue
        if path.stat().st_size > MAX_FILE:
            _fail("GUI settings evidence exceeds bound")
        raw = path.read_bytes()
        match = re.search(rb"<name>sixthSenseDuration</name>\s*<type>int</type>\s*<value>(\d+)</value>", raw)
        if match:
            return {"path": str(relative).replace("\\", "/"),
                    "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                    "sixthSenseDuration_ms": int(match.group(1))}
    return None


def build_receipt(original_root, script_root, evidence_root=None):
    packed_xml, py27_static = _load_tools(script_root)

    static_sources = [_pin(original_root, rel, size, sha) for rel, size, sha in STATIC_PINS]
    if len(static_sources) != 6:
        _fail("static source count changed")

    # Read all seven source-mounted turret rows and bind each row to a turret
    # ID from the corresponding original components table.
    components = {}
    for rel in ("ussr/components/turrets.xml", "germany/components/turrets.xml",
                "uk/components/turrets.xml"):
        _, raw = _read(original_root / "res/scripts/item_defs/vehicles", rel)
        components[rel] = _rows(packed_xml, raw)
    mounted = []
    for label, rel, turret, turret_id, expected_radius in RANGE_SPECS:
        _range_path, raw = _read(original_root / "res/scripts/item_defs/vehicles", rel)
        rows = _rows(packed_xml, raw)
        base = "/turrets0[1]/{}[1]".format(turret)
        radius = rows.get(base + "/circularVisionRadius[1]")
        if radius != expected_radius:
            _fail("unexpected circularVisionRadius for {}: {}".format(label, radius))
        component_rel = rel.split("/", 1)[0] + "/components/turrets.xml"
        component_rows = components[component_rel]
        observed_id = component_rows.get("/ids[1]/{}[1]".format(turret))
        if observed_id != turret_id:
            _fail("unexpected turret id for {}: {}".format(label, observed_id))
        mounted.append({
            "id": label,
            "source": "res/scripts/item_defs/vehicles/" + rel,
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "turret": turret,
            "turret_id": turret_id,
            "circularVisionRadius_m": radius,
            "classification": "VERIFIED_STATIC_BASE_RADIUS",
        })

    avatar_def_path, avatar_def = _read(original_root, "res/scripts/entity_defs/avatar.def")
    vehicle_def_path, vehicle_def = _read(original_root, "res/scripts/entity_defs/vehicle.def")
    arena_def_path, arena_def = _read(original_root, "res/scripts/entity_defs/arena.def")
    avatar_rows = _rows(packed_xml, avatar_def)
    vehicle_rows = _rows(packed_xml, vehicle_def)
    arena_rows = _rows(packed_xml, arena_def)
    client_prefix = "/ClientMethods[1]/updateVehicleMiscStatus[1]"
    base_prefix = "/BaseMethods[1]/updateVehicleMiscStatus[1]"
    expected_args = ["OBJECT_ID", "UINT8", "INT32", "FLOAT32"]
    if _method_args(avatar_rows, client_prefix) != expected_args:
        _fail("avatar ClientMethods updateVehicleMiscStatus schema changed")
    if _method_args(avatar_rows, base_prefix) != expected_args:
        _fail("avatar BaseMethods updateVehicleMiscStatus schema changed")

    avatar_pyc_path, avatar_pyc = _read(original_root, "res/scripts/client/avatar.pyc", MAX_PYC)
    vehicle_items_path, vehicle_items_pyc = _read(original_root, "res/scripts/common/items/vehicles.pyc", MAX_PYC)
    if vehicle_items_path.stat().st_size != 125668 or hashlib.sha256(vehicle_items_pyc).hexdigest() != "805240e4b59d8a75950dbb97b41c17867606e7e96d7ff0c8d7b05312b83ae8b6":
        _fail("common/items/vehicles.pyc support pin mismatch")
    battle_pyc_path, battle_pyc = _read(original_root, "res/scripts/client/gui/scaleform/battle.pyc", MAX_PYC)
    constants_pyc_path, constants_pyc = _read(original_root, "res/scripts/common/constants.pyc", MAX_PYC)
    gui_settings_pyc_path, gui_settings_pyc = _read(original_root, "res/scripts/client/gui/guisettings.pyc", MAX_PYC)
    avatar_update = _find_record(_pyc_records(avatar_pyc, py27_static), "PlayerAvatar.updateVehicleMiscStatus", py27_static)
    if avatar_update["firstlineno"] != 1266:
        _fail("unexpected updateVehicleMiscStatus line")
    names = set(_as_text(x, py27_static) for x in avatar_update["names"])
    if not {"IS_OBSERVED_BY_ENEMY", "showSixthSenseIndicator"}.issubset(names):
        _fail("Sixth Sense status callback names missing")
    battle_records = _pyc_records(battle_pyc, py27_static)
    battle_show = _find_record(battle_records, "Battle.showSixthSenseIndicator", py27_static)
    if "sixthSenseIndicator.show" not in [_normal(x, py27_static) for x in battle_show["consts"]]:
        _fail("Sixth Sense UI call missing")
    battle_after = _find_record(battle_records, "Battle.afterCreate", py27_static)
    after_names = set(_as_text(x, py27_static) for x in battle_after["names"])
    after_constants = set(_normal(x, py27_static) for x in battle_after["consts"])
    if "sixthSenseDuration" not in after_names or "sixthSenseIndicator.setDuration" not in after_constants:
        _fail("Sixth Sense duration binding missing")
    constants = _find_record(_pyc_records(constants_pyc, py27_static), "VEHICLE_MISC_STATUS", py27_static)
    const_values = [_normal(x, py27_static) for x in constants["consts"]]
    const_names = [_normal(x, py27_static) for x in constants["names"]]
    if "IS_OBSERVED_BY_ENEMY" not in const_names or 1 not in const_values:
        _fail("IS_OBSERVED_BY_ENEMY enum value missing")
    gui_root = _find_record(_pyc_records(gui_settings_pyc, py27_static), "<module>", py27_static)
    if "sixthSenseDuration" not in [_normal(x, py27_static) for x in gui_root["consts"]]:
        _fail("sixthSenseDuration setting name missing")

    gui_evidence = _evidence_gui_duration(evidence_root)
    if gui_evidence is None:
        _fail("retained gui_settings.xml evidence with sixthSenseDuration=2000 not found")
    if gui_evidence["sixthSenseDuration_ms"] != 2000:
        _fail("unexpected sixthSenseDuration evidence value")

    point_code = _find_record(_pyc_records(vehicle_items_pyc, py27_static), "VehicleDescr.__updateAttributes", py27_static)
    point_names = set(_as_text(x, py27_static) for x in point_code["names"])
    point_constants = set(_normal(x, py27_static) for x in point_code["consts"])
    required_point_names = {
        "hullPosition", "turretPositions", "gunPosition", "visibilityCheckPoints",
        "observerPosOnChassis", "observerPosOnTurret",
    }
    point_symbols = point_names | point_constants
    if point_code["firstlineno"] != 1462 or not required_point_names.issubset(point_symbols):
        _fail("original visibility point builder record changed")
    if not {"hitTester", "bbox"}.issubset(point_symbols) or "hullPosition" not in point_constants:
        _fail("original visibility point geometry inputs missing")

    dynamic = [
        {"id": DYNAMIC_IDS[0], "source": "res/scripts/entity_defs/avatar.def",
         "method": "ClientMethods.updateVehicleMiscStatus", "args": expected_args, "bytes": 13,
         "classification": "VERIFIED_STATIC_DECLARATION"},
        {"id": DYNAMIC_IDS[1], "source": "res/scripts/entity_defs/avatar.def",
         "method": "BaseMethods.updateVehicleMiscStatus", "args": expected_args, "bytes": 13,
         "classification": "VERIFIED_STATIC_DECLARATION"},
        {"id": DYNAMIC_IDS[2], "source": "res/scripts/common/constants.pyc",
         "enum": "VEHICLE_MISC_STATUS.IS_OBSERVED_BY_ENEMY", "value": 1,
         "classification": "VERIFIED_STATIC_BYTECODE"},
        {"id": DYNAMIC_IDS[3], "source": "res/scripts/client/avatar.pyc",
         "method": "PlayerAvatar.updateVehicleMiscStatus", "line": 1266,
         "calls": "Battle.showSixthSenseIndicator(True)", "classification": "VERIFIED_STATIC_BYTECODE"},
        {"id": DYNAMIC_IDS[4], "source": "res/scripts/client/gui/scaleform/battle.pyc",
         "method": "Battle.showSixthSenseIndicator", "call": "sixthSenseIndicator.show",
         "classification": "VERIFIED_STATIC_BYTECODE"},
        {"id": DYNAMIC_IDS[5], "source": "res/scripts/client/gui/scaleform/battle.pyc",
         "method": "Battle.afterCreate", "call": "sixthSenseIndicator.setDuration",
         "setting": "sixthSenseDuration", "classification": "VERIFIED_STATIC_BYTECODE"},
        {"id": DYNAMIC_IDS[6], "source": gui_evidence["path"],
         "setting": "sixthSenseDuration", "value_ms": 2000,
         "sha256": gui_evidence["sha256"], "classification": "VERIFIED_STATIC_EVIDENCE"},
    ]
    if len(dynamic) != 7:
        _fail("dynamic observation count changed")

    # Observer callbacks are source declarations; they do not prove that a
    # native server actually invokes them.  That remains a later native gate.
    observers = [
        {"source": "res/scripts/entity_defs/vehicle.def",
         "method": "CellMethods.onObservedByEnemy", "args": ["OBJECT_ID", "BOOL"],
         "classification": "VERIFIED_STATIC_DECLARATION"},
        {"source": "res/scripts/entity_defs/arena.def",
         "method": "CellMethods.notifyVehicleOnObservationByEnemy", "args": ["OBJECT_ID", "BOOL"],
         "classification": "VERIFIED_STATIC_DECLARATION"},
        {"source": "res/scripts/entity_defs/avatar.def",
         "method": "CellMethods.receiveVisibilityInfo", "args": ["ARRAY<OBJECT_ID>", "ARRAY<FLOAT32>", "ARRAY<FLOAT32>"],
         "classification": "VERIFIED_STATIC_DECLARATION"},
    ]
    if _method_args(vehicle_rows, "/CellMethods[1]/onObservedByEnemy[1]") != ["OBJECT_ID", "BOOL"]:
        _fail("vehicle observer declaration changed")
    if _method_args(arena_rows, "/CellMethods[1]/notifyVehicleOnObservationByEnemy[1]") != ["OBJECT_ID", "BOOL"]:
        _fail("arena observer declaration changed")
    visibility_prefix = "/CellMethods[1]/receiveVisibilityInfo[1]"
    if _method_args(avatar_rows, visibility_prefix) != ["ARRAY", "ARRAY", "ARRAY"]:
        _fail("avatar receiveVisibilityInfo declaration changed")
    if avatar_rows.get(visibility_prefix + "/Arg[1]/of[1]") != "OBJECT_ID":
        _fail("avatar receiveVisibilityInfo target array changed")
    if avatar_rows.get(visibility_prefix + "/Arg[2]/of[1]") != "FLOAT32":
        _fail("avatar receiveVisibilityInfo first float array changed")
    if avatar_rows.get(visibility_prefix + "/Arg[3]/of[1]") != "FLOAT32":
        _fail("avatar receiveVisibilityInfo second float array changed")

    return {
        "schema": SCHEMA,
        "status": "PASS_STATIC_P07B_ORIGINAL_SOURCE_LEDGER",
        "native_visibility": "NOT_RUN",
        "client_execution": False,
        "counts": {"static_sources": 6, "dynamic_observations": 7, "observers": len(observers), "mounted_profiles": 7},
        "static_sources": static_sources,
        "dynamic_observations": dynamic,
        "observers": observers,
        "mounted_base_ranges": mounted,
        "point_contract": {
            "source": "res/scripts/common/items/vehicles.pyc",
            "method": "VehicleDescr.__updateAttributes",
            "line": 1462,
            "classification": "VERIFIED_STATIC_POINT_FORMULAS",
            "counts": {"visibility_check_points": 6, "observer_positions": 2},
            "visibility_check_points": [
                "Vector3(0, hullPos.y + turretLocalTopY, 0)",
                "hullPos + gunPosOnHull",
                "hullPos + Vector3(0, hullLocalCenterY, hullBboxMax.z)",
                "hullPos + Vector3(0, hullLocalCenterY, hullBboxMin.z)",
                "hullPos + Vector3(hullBboxMax.x, gunPosOnHull.y, hullLocalCenterZ)",
                "hullPos + Vector3(hullBboxMin.x, gunPosOnHull.y, hullLocalCenterZ)",
            ],
            "observer_positions": {
                "observerPosOnChassis": "Vector3(0, hullPos.y + turretLocalTopY, 0)",
                "observerPosOnTurret": "turret.gunPosition",
            },
            "target_point_transforms": "UNKNOWN",
            "hull_yaw_pitch_roll_transform": "UNKNOWN",
        },
        "observer_points": [
            {"name": "hull_or_turret_sight_point", "count": 1, "classification": "INFERRED_SERVER_INPUT", "transform": "UNKNOWN"},
            {"name": "gun_or_dynamic_sight_point", "count": 1, "classification": "INFERRED_SERVER_INPUT", "transform": "UNKNOWN"},
        ],
        "sixth_sense": {
            "owner_policy": "always active commander base capability; no learning gate",
            "delay_seconds": 3,
            "delay_ms": 3000,
            "delay_classification": "OWNER_OVERRIDE_NOT_SOURCE_VERIFIED",
            "event_code": 1,
            "event_name": "VEHICLE_MISC_STATUS.IS_OBSERVED_BY_ENEMY",
            "event_classification": "VERIFIED_STATIC_BYTECODE",
            "updateVehicleMiscStatus_args_bytes": 13,
            "ui_duration_ms": 2000,
            "audio": "UNKNOWN_NATIVE_NOT_RUN",
        },
        "unknowns": {
            "maximum_detection": "UNKNOWN",
            "proximity_shortcut": "UNKNOWN",
            "scan_cadence": "UNKNOWN",
            "visibility_hold": "UNKNOWN",
            "radio_team_transfer": "UNKNOWN",
            "point_transforms_yaw_pitch_roll": "UNKNOWN",
            "native_callback_wire_ids": "UNKNOWN",
            "native_ui_audio_control": "NOT_RUN",
            "camouflage_and_bush_coefficients": "OUT_OF_SCOPE",
        },
        "source_files_read": [
            str(avatar_def_path), str(vehicle_def_path), str(arena_def_path),
            str(avatar_pyc_path), str(battle_pyc_path), str(constants_pyc_path),
            str(gui_settings_pyc_path), str(vehicle_items_path),
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-root", required=True, help="read-only #717 root")
    parser.add_argument("--out", required=True, help="new small JSON receipt on C:")
    parser.add_argument("--evidence-root", help="retained evidence root (read-only)")
    args = parser.parse_args(argv)
    original = _safe_root(args.original_root, "original root")
    script_root = Path(__file__).resolve().parents[1]
    evidence = _safe_root(args.evidence_root, "evidence root") if args.evidence_root else None
    out = Path(args.out).expanduser().absolute()
    if out.drive.upper() != "C:":
        _fail("receipt output must be on C: (got {})".format(out))
    if out.exists():
        _fail("refusing to overwrite existing receipt: {}".format(out))
    if out.parent.exists() and not out.parent.is_dir():
        _fail("receipt parent is not a directory")
    out.parent.mkdir(parents=True, exist_ok=True)
    receipt = build_receipt(original, script_root, evidence)
    encoded = (json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(encoded) > MAX_OUTPUT:
        _fail("receipt exceeds bounded output limit")
    with out.open("xb") as stream:
        stream.write(encoded)
    print(json.dumps({"status": receipt["status"], "out": str(out),
                      "sha256": hashlib.sha256(encoded).hexdigest(),
                      "counts": receipt["counts"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, OSError, ValueError) as exc:
        print("FAIL: {}".format(exc), file=sys.stderr)
        raise SystemExit(2)
