"""Read pinned #717 consumables resources and bytecode without loading the client."""
import argparse
import gettext
import io
import json
from pathlib import Path

from damage_wire_source_audit import schema_tables
from packed_xml import decode, walk
from p06t_shell_catalog import no_links, require, sha
from py27_static import disassemble, opcode_table, parse_pyc, records


PINS = {
    "res/scripts/entity_defs/alias.xml": (5987, "14d5fcce8d979de6c24c50b3ff94d3ddf464f4ad27f2ef68c063407b4bbbc746"),
    "res/scripts/entity_defs/avatar.def": (7450, "38cf983d6ea1fcaf1bbca25fd18567fed5abc3b2e07fbe14b168f46fa883f74d"),
    "res/scripts/entity_defs/vehicle.def": (5588, "08dc1e6be577f80a04bf813ca046550201a3c4e673dad1540c5f1c6a047d1297"),
    "res/scripts/entity_defs/interfaces/chat.def": (876, "3f8f0f6d14e21ece8db54af467235110eaf495b04ab404434fd69eaf66270f3d"),
    "res/scripts/client/avatar.pyc": (83656, "c13cd58a4c5d766dfd3c5f47ae7be50c962aee6c7f8cf25b4341322381f21e0e"),
    "res/scripts/common/constants.pyc": (34396, "1c07c2e6a956dcfef95c4020954b4ca39efd77844d328cded935307a6515eebd"),
    "res/scripts/item_defs/vehicles/common/equipments.xml": (4626, "d98e409abe78ed3278d033bfb5340a8897b5dc69e6881901bab70f6746eef461"),
    "res/text/lc_messages/artefacts.mo": (18986, "87e24105b2794fa64363ee72ff0554e38173c94c4df1be485c83a2a94f690c8a"),
}
AVATAR = "res/scripts/client/avatar.pyc"
CONSTANTS = "res/scripts/common/constants.pyc"
EQUIPMENT = "res/scripts/item_defs/vehicles/common/equipments.xml"
ITEMS = ("handExtinguishers", "autoExtinguishers", "smallMedkit", "largeMedkit", "smallRepairkit", "largeRepairkit")
METHOD_PINS = {
    "onEquipmentButtonPressed": "946ce4f9a827aeec0b4ff054d6bbe5b661087269b106b14663fce4e5d9a29de7",
    "updateVehicleAmmo": "f7e524fed66ff748ad8554082064ee8e865d21def71b18f5856f5037d18b98ba",
    "__processVehicleEquipments": "649d377097528f7a0e5d5640a38340ba2f980ab36d4c772e96ebf3c9236840e9",
    "__processEmptyVehicleEquipment": "88d1af26d03b7e20f64a56863a74b61007f8de877f1b9b83de87d0d15c67c5d2",
}


def pinned(path, size, digest):
    path = no_links(path)
    require(path.is_file() and path.stat().st_size == size, "source size: " + str(path))
    raw = path.read_bytes()
    require(sha(raw) == digest, "source pin: " + str(path))
    return raw


def evidence(original, opcode):
    payloads = {name: pinned(original / name, *pin) for name, pin in PINS.items()}
    opcode = no_links(opcode)
    require(opcode.is_file() and opcode.stat().st_size < 32768, "opcode table size")
    opcode_bytes = opcode.read_bytes()
    require(sha(opcode_bytes) == "620c2ea086354a4e3b445578d6fa005e944bfdddaf0791b19e1e9856ab41b7cf",
            "CPython 2.7.3 installed opcode table pin")
    table = opcode_table(opcode_bytes.decode("ascii"))
    parsed = {name.rsplit(".", 1)[-1]: record for name, record in records(parse_pyc(payloads[AVATAR]))
              if name.startswith("<module>.PlayerAvatar.") and name.split(".")[-1] in METHOD_PINS}
    require(set(METHOD_PINS) == set(parsed), "consumable client methods")
    for name, record in parsed.items():
        require(sha(record["code"]) == METHOD_PINS[name], "consumable bytecode: " + name)
    parsed["VEHICLE_SETTING"] = dict(records(parse_pyc(payloads[CONSTANTS])))["<module>.VEHICLE_SETTING"]
    expected = {
        "VEHICLE_SETTING": [(24, "LOAD_CONST", 16), (27, "STORE_NAME", "ACTIVATE_EQUIPMENT")],
        "onEquipmentButtonPressed": [
            (196, "LOAD_CONST", "Health"), (220, "LOAD_ATTR", "extrasDict"), (237, "LOAD_ATTR", "index"),
            (240, "LOAD_CONST", 16), (243, "BINARY_LSHIFT", None), (247, "LOAD_ATTR", "id"),
            (250, "LOAD_CONST", 1), (254, "BINARY_ADD", None), (291, "LOAD_CONST", 65536),
            (793, "LOAD_CONST", 65536), (916, "LOAD_ATTR", "base"),
            (919, "LOAD_ATTR", "vehicle_changeSetting"), (925, "LOAD_ATTR", "ACTIVATE_EQUIPMENT"),
            (928, "LOAD_FAST", "param"), (931, "CALL_FUNCTION", 2),
        ],
        "updateVehicleAmmo": [(0, "LOAD_FAST", "compactDescr"),
                              (9, "LOAD_ATTR", "_PlayerAvatar__processEmptyVehicleEquipment")],
        "__processVehicleEquipments": [(15, "LOAD_ATTR", "_PlayerAvatar__findIndexInEquipment"),
                                       (114, "LOAD_ATTR", "setItemQuantityInSlot"), (232, "LOAD_ATTR", "addEquipmentSlot")],
    }
    for name, entries in expected.items():
        actual = {(row["offset"], row["opname"], row.get("value", row.get("arg")))
                  for row in disassemble(parsed[name], table) if row["offset"] in {entry[0] for entry in entries}}
        require(actual == set(entries), "original consumable instructions: " + name)
    methods = schema_tables(payloads)[0]["avatar"]
    for group, name, wire_id, args in (
        ("BaseMethods", "vehicle_changeSetting", 0x8d, ["UINT8", "INT32"]),
        ("ClientMethods", "updateVehicleAmmo", 0x44, ["INT32", "UINT16", "UINT8", "INT16"]),
    ):
        match = next(row for row in methods[group] if row["name"] == name)
        require((match["candidate_wire_id"], match["args"]) == (wire_id, args), "native method " + name)
    items = dict(walk(decode(payloads[EQUIPMENT], max_bytes=8192)))
    require(tuple(items[f"/{name}[1]/id[1]"] for name in ITEMS) == tuple(range(len(ITEMS))), "source equipment IDs")
    config = {"autoExtinguishers": {"fireStartingChanceFactor": 0.9, "autoactivate": True},
              "smallMedkit": {"repairAll": False, "bonusValue": 0},
              "largeMedkit": {"repairAll": True, "bonusValue": 0.30},
              "smallRepairkit": {"repairAll": False, "bonusValue": 0},
              "largeRepairkit": {"repairAll": True, "bonusValue": 0.10}}
    for name, params in config.items():
        for key, value in params.items():
            raw = items[f"/{name}[1]/script[1]/{key}[1]"]
            if isinstance(value, float):
                raw = float(raw)
            require(raw == value, "source equipment configuration: " + name + "/" + key)
    translation = gettext.GNUTranslations(io.BytesIO(payloads["res/text/lc_messages/artefacts.mo"]))
    require(all("Используется однократно" in translation.gettext(name + "/onUse") for name in ITEMS), "once-use text")
    require("+15%" in translation.gettext("largeMedkit/always"), "large medkit description")
    require("+10%" in translation.gettext("largeRepairkit/always"), "large repair kit description")
    return {"status": "PASS_STATIC_ONLY", "native_client": "NOT_RUN", "source_pins": PINS,
            "method_pins": METHOD_PINS, "instructions": expected, "source_configuration": config,
            "activation": {"record": 0x8d, "setting": 16, "low_word": "item ID",
                           "high_word": "target extra or 1 for untargeted activation"},
            "owner_callback": {"record": 0x44, "quantity": "one or zero", "zero_compact": "empty slot"},
            "unknown": "large-medkit XML bonus 0.30 differs from client localization +15%; original server computation unavailable"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", required=True, type=Path)
    parser.add_argument("--opcode", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(evidence(args.original, args.opcode), indent=2))


if __name__ == "__main__":
    main()
