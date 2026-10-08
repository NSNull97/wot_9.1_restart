import json
import os
from pathlib import Path
import tempfile
import unittest

from tools.nation_dumper_static_audit import (
    NationDumperAuditError,
    audit,
    inspect_nested_shape,
    inspect_shape,
    parse_json,
)


ROOT = Path(os.environ.get("WOT091_ROOT", Path(__file__).resolve().parents[1])).resolve()
DISASSEMBLY = ROOT / (
    "local/evidence/20261007-native-tree-filter-01/bytecode/"
    "client__gui__scaleform__daapi__view__lobby__techtree__dumpers.json"
)


class NationDumperStaticAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        required = [DISASSEMBLY]
        required.extend(ROOT / f"WoT_0.9.1_RU_0717_{name}/res/scripts/client/"
                        "gui/scaleform/daapi/view/lobby/techtree/dumpers.pyc"
                        for name in ("original", "research"))
        if not all(path.is_file() for path in required):
            raise unittest.SkipTest("ignored NationObjDumper evidence/client copy unavailable")
        cls.records = parse_json(DISASSEMBLY.read_bytes())

    def test_real_envelope_and_vehicle_fields(self):
        report = audit(root=ROOT, disassembly=DISASSEMBLY)
        self.assertEqual(report["status"], "PASS_STATIC_NATION_DUMPER_OUTPUT")
        self.assertEqual(report["shape"]["envelope_fields"],
                         ["nodes", "displaySettings", "scrollIndex"])
        self.assertEqual(report["shape"]["vehicle_fields"], [
            "id", "state", "type", "nameString", "primaryClass", "level",
            "longName", "iconPath", "smallIconPath", "earnedXP", "shopPrice",
            "displayInfo", "unlockProps",
        ])
        self.assertEqual(report["native_account_shop_payload"], "NOT_RUN")
        nested = report["nested_shape"]
        self.assertEqual(nested["unlockProps"]["output_arity"], 4)
        self.assertEqual([field["name"] for field in nested["unlockProps"]["format_fields"]],
                         ["parentID", "unlockIdx", "xpCost", "topIDs"])
        self.assertEqual(nested["displayInfo"]["line_key"], "lines")
        self.assertEqual(nested["serializer_or_wire"], "NOT_RUN")

    def test_field_source_mutation_is_rejected(self):
        records = json.loads(json.dumps(self.records))
        row = next(item for item in records
                   if item.get("qualified_name") == "<module>.NationObjDumper._getVehicleData")
        instruction = next(item for item in row["instructions"] if item.get("offset") == 95)
        instruction["value"] = "wrong-id"
        with self.assertRaises(NationDumperAuditError):
            inspect_shape(records)

    def test_nested_format_constant_mutation_is_rejected(self):
        records = json.loads(json.dumps(self.records))
        row = next(item for item in records
                   if item.get("qualified_name") == "<module>.NationXMLDumper")
        row["constants"][4] = "<displayInfo-mutated>"
        with self.assertRaises(NationDumperAuditError):
            inspect_nested_shape(records)

    def test_nested_display_info_access_mutation_is_rejected(self):
        records = json.loads(json.dumps(self.records))
        row = next(item for item in records
                   if item.get("qualified_name") ==
                   "<module>.NationXMLDumper.__buildDisplayInfo")
        instruction = next(item for item in row["instructions"]
                           if item.get("value") == "lines")
        instruction["value"] = "rows"
        with self.assertRaises(NationDumperAuditError):
            inspect_nested_shape(records)

    def test_duplicate_json_key_is_rejected(self):
        with self.assertRaises(NationDumperAuditError):
            parse_json(b'[{"qualified_name":"x","qualified_name":"y"}]')

    def test_nonfinite_depth_and_oversize_are_rejected(self):
        with self.assertRaises(NationDumperAuditError):
            parse_json(b'[{"value":NaN}]')
        nested = "0"
        for _ in range(26):
            nested = "[" + nested + "]"
        with self.assertRaises(NationDumperAuditError):
            parse_json(("[" + nested + "]").encode("ascii"))
        with self.assertRaises(NationDumperAuditError):
            parse_json(json.dumps([{}] * 257).encode("utf-8"))

    def test_path_escape_is_rejected(self):
        with self.assertRaises(NationDumperAuditError):
            audit(root=ROOT, disassembly=Path(tempfile.gettempdir()) / DISASSEMBLY.name)


if __name__ == "__main__":
    unittest.main()
