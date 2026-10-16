"""Original #717 DetachedTurret source/PE contract, inert read-only data.

This proves source mapping, not actual native creation or a server flight model.
No ignored generated table or producer serializer is a test dependency.
"""
import hashlib
import json
import os
from pathlib import Path
import struct
import unittest

from tools import py27_static
from tools.packed_xml import decode

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = Path(os.environ.get("P06T_ORIGINAL_CLIENT", "C:/WoT_0.9.1_RU_0717_original"))
PINS = {
    "res/scripts/entities.xml": "5613d3affa600b80a2c04418cc5bc8549dd7e0ecf77c04efee11fb42e4061004",
    "res/scripts/entity_defs/vehicle.def": "08dc1e6be577f80a04bf813ca046550201a3c4e673dad1540c5f1c6a047d1297",
    "res/scripts/entity_defs/detachedturret.def": "136692d723ee2eb3efb5e047e419b2cc81d770ecf5d02c54da26f18a77c6e14d",
    "res/scripts/entity_defs/alias.xml": "14d5fcce8d979de6c24c50b3ff94d3ddf464f4ad27f2ef68c063407b4bbbc746",
    "res/scripts/client/detachedturret.pyc": "9408f90a3806869005f2aab7850f70e284b09f6d3fa7e1625ec1137cd84e7de6",
    "res/scripts/client/vehicle.pyc": "b81d08ca14092bb8912adb2eff20325c3dd23424868bc03164cfe6b8da50463c",
    "res/scripts/client/vehicleappearance.pyc": "aa4f0c9ac4e830209c7929bd6c3aad1c19efec316c8cc7711f8b9211c893335a",
    "res/scripts/common/constants.pyc": "1c07c2e6a956dcfef95c4020954b4ca39efd77844d328cded935307a6515eebd",
}
EXE_SHA = "86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed"


def children(node):
    return node.get("children", []) if isinstance(node, dict) else []


def scalar(node):
    if isinstance(node, dict) and "base64" in node:
        return node["base64"]
    if isinstance(node, dict) and "value" in node:
        return scalar(node["value"])
    return node


class DetachedTurretContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        paths = [ORIGINAL / path for path in PINS]
        if not all(path.is_file() for path in paths):
            raise unittest.SkipTest("NOT_RUN: original #717 detached-turret sources unavailable")
        opcode = ROOT / "local/vendor/cpython-2.7.3/opcode.py"
        if not opcode.is_file():
            raise unittest.SkipTest("NOT_RUN: pinned CPython2 opcode table unavailable")
        raw = opcode.read_bytes()
        if hashlib.sha256(raw).hexdigest() != "acfe212847ecb81ca28bdab976a3caacff3568b45a9e8ca78d6957f9f3ef4884":
            raise AssertionError("opcode source changed")
        table = py27_static.opcode_table(raw.decode("utf8"))
        cls.schemas, cls.methods = {}, {}
        for path, pin in PINS.items():
            raw = (ORIGINAL / path).read_bytes()
            if not 0 < len(raw) <= 2 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != pin:
                raise AssertionError("original source changed: " + path)
            if path.endswith(".pyc"):
                cls.methods[path] = py27_static.inspect(raw, table)
            else:
                cls.schemas[path] = decode(raw)

    def method(self, path, name, line=None):
        found = [m for m in self.methods["res/scripts/" + path]
                 if m["qualified_name"].endswith(name) and (line is None or m["firstlineno"] == line)]
        self.assertEqual(len(found), 1)
        return found[0]

    def test_original_all44_definitions_and_client_scripts_assign_type8_not_xml42(self):
        entries = children(self.schemas["res/scripts/entities.xml"])
        self.assertEqual(len(entries), 44)
        self.assertEqual(entries[42]["name"], "DetachedTurret")
        client_types, schema_pins = [], []
        for entry in entries:
            name = entry["name"]
            self.assertTrue(name.isidentifier())
            relative = "res/scripts/entity_defs/" + name.lower() + ".def"
            raw = (ORIGINAL / relative).read_bytes()
            self.assertLessEqual(len(raw), 2 * 1024 * 1024)
            schema_pins.append([relative, hashlib.sha256(raw).hexdigest()])
            definition = decode(raw)
            self.assertFalse([r for r in children(definition) if r["name"] == "ClientName"])
            present = [suffix for suffix in (".py", ".pyc", ".pyo", ".pyd")
                       if (ORIGINAL / "res/scripts/client" / (name + suffix)).is_file()]
            if present:
                client_types.append((name, len(client_types)))
        self.assertEqual(hashlib.sha256(json.dumps(schema_pins, separators=(",", ":")).encode()).hexdigest(),
                         "a0740f1ac235239c2d13af8db742a5a5203471c6cad7344e03b9763f97ef1aaf")
        self.assertEqual(client_types, [("Account", 0), ("Avatar", 1), ("Vehicle", 2),
            ("AreaDestructibles", 3), ("OfflineEntity", 4), ("Flock", 5),
            ("FlockExotic", 6), ("Login", 7), ("DetachedTurret", 8)])

    def test_original_pe_pins_client_presence_index_and_generic_create_paths(self):
        path = ORIGINAL / "WorldOfTanks.exe"
        if not path.is_file():
            self.skipTest("NOT_RUN: pinned #717 PE unavailable")
        raw = path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), EXE_SHA)
        nt = struct.unpack_from("<I", raw, 0x3c)[0]
        self.assertEqual(raw[nt:nt + 4], b"PE\x00\x00")
        count = struct.unpack_from("<H", raw, nt + 6)[0]
        optional_size = struct.unpack_from("<H", raw, nt + 20)[0]
        optional = nt + 24
        self.assertEqual(struct.unpack_from("<H", raw, optional)[0], 0x10b)
        imagebase = struct.unpack_from("<I", raw, optional + 28)[0]
        self.assertEqual(imagebase, 0x400000)
        sections = optional + optional_size
        def read(va, length):
            rva = va - imagebase
            for i in range(count):
                size, address, disk_size, disk_offset = struct.unpack_from("<IIII", raw, sections + 40 * i + 8)
                if address <= rva and rva + length <= address + min(size, disk_size):
                    start = disk_offset + rva - address
                    return raw[start:start + length]
            self.fail("unmapped PE source range")
        # Examined original EntityDescriptionMap/parser/script detection/client
        # rank assignment and factory paths; these are source anchors, not mocks.
        for va, length, pin in [
            (0xdccaf0, 1376, "504c221be80262f65e54d1a06bcb92d9d4bf654f033ec55974b857bca2a949b4"),
            (0xdcd4c0, 160, "dea973c333d8acefcc4d0b3a21b7aacafca8b6fd9c800e6c18f2498dee7868a5"),
            (0xdc84c0, 100, "38a75a8977177ffe43150b593deaaa1fdbffa6b14601536b7b292387ebd09768"),
            (0xdca7c0, 100, "9d99ed0073d7369442f687fbdf034b3018e67fb5bce567c3d63510aed115963e"),
            (0xdcce51, 32, "3d3c7d7b5b6199a67c3ec39aa43932a39ebf8de6efeca91b9b398bcd8515e50d"),
            (0xdcb3b0, 320, "42a5cde5a9674542bcaa9ab71bbd531bc0125bf83b1139311f84ae9459b9edbf"),
            (0x5bf5f7, 64, "43b33420896d1a6f0036cd29ed06bee363c31d051f221bfe3998ef5d793b39d2"),
            (0xd6dfe0, 192, "b61b0ddb5231e85ef616109570112b8679b61ba4e8a4d4336754032e8624fc7c"),
            (0xd6dd70, 224, "ea65ca1ccc23d9727c44d410616b37ee01ed6efb18f7eca1c2be2649a770f462"),
        ]:
            self.assertEqual(hashlib.sha256(read(va, length)).hexdigest(), pin)

    def test_original_four_detached_properties_and_vehicle_explosion_fixed8(self):
        aliases = {r["name"]: r["data"] for r in children(self.schemas["res/scripts/entity_defs/alias.xml"])}
        self.assertEqual(aliases["OBJECT_ID"], "INT32")
        def width(value):
            value = scalar(value)
            if value in aliases:
                return width(aliases[value])
            return {"BOOL": 1, "UINT8": 1, "INT16": 2, "INT32": 4,
                    "FLOAT32": 4, "VECTOR3": 12, "STRING": None, "ARRAY": None}[value]
        turret = {r["name"]: r["data"] for r in children(self.schemas["res/scripts/entity_defs/detachedturret.def"])}
        properties = []
        for prop in children(turret["Properties"]):
            fields = {r["name"]: r["data"] for r in children(prop["data"])}
            if scalar(fields["Flags"]) == "ALL_CLIENTS":
                properties.append((prop["name"], width(fields["Type"])))
        properties.sort(key=lambda r: (r[1] is None, r[1] or 0))
        self.assertEqual(properties, [("isUnderWater", 1), ("isCollidingWithWorld", 1),
                                      ("vehicleID", 4), ("vehicleCompDescr", None)])
        self.assertNotIn("velocity", [p[0] for p in properties])
        vehicle = {r["name"]: r["data"] for r in children(self.schemas["res/scripts/entity_defs/vehicle.def"])}
        methods = []
        for method in children(vehicle["ClientMethods"]):
            sizes = [width(r["data"]) for r in children(method["data"]) if r["name"] == "Arg"]
            methods.append((method["name"], None if None in sizes else sum(sizes)))
        methods.sort(key=lambda r: (r[1] is None, r[1] or 0))
        self.assertEqual(methods[:3], [("showShooting", 1), ("onHealthChanged", 7), ("showAmmoBayExplosion", 8)])
        self.assertEqual(0x3b + methods.index(("showAmmoBayExplosion", 8)), 0x3d)

    def test_original_special_health_confirmation_and_fx_do_not_forge_physical_turret(self):
        health = self.method("common/constants.pyc", ".VEHICLE_HEALTH")
        ops = {r["offset"]: r for r in health["instructions"]}
        self.assertEqual([(ops[n]["value"]) for n in (6, 9, 12, 15)], [-1, "EXPLODED", -2, "TURRET_DETACHED"])
        detached = self.method("client/vehicle.pyc", ".Vehicle.<lambda>", 37)
        self.assertTrue({"health", "TURRET_DETACHED", "_Vehicle__turretDetachmentConfirmed"} <= set(detached["names"]))
        sync = self.method("client/detachedturret.pyc", ".SynchronousDetachment._onCallbackTick")
        self.assertTrue({"isTurretDetachmentConfirmationNeeded", "confirmTurretDetachment"} <= set(sync["names"]))
        transfer = self.method("client/detachedturret.pyc", ".SynchronousDetachment.transferInputs")
        self.assertTrue({"hullPosition", "turretPositions", "transferInputAsVehicle"} <=
                        set(transfer["names"]) | {r.get("value") for r in transfer["instructions"]
                                                if isinstance(r.get("value"), str)})
        explosion = self.method("client/vehicle.pyc", ".Vehicle.showAmmoBayExplosion")
        self.assertFalse(any(r.get("value") == "projectedTurretSpeed" for r in explosion["instructions"]))
        self.assertFalse({"health", "DetachedTurret", "createEntity"} & set(explosion["names"]))
        self.assertIn("onShowAmmoBayExplosion", explosion["names"])
        enter = self.method("client/detachedturret.pyc", ".DetachedTurret.onEnterWorld")
        self.assertTrue({"model", "_DetachedTurret__gunModel", "_DetachedTurret__detachConfirmationTimer"} <= set(enter["names"]))


if __name__ == "__main__":
    unittest.main()
