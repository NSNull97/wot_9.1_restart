import json
import os
from pathlib import Path
import tempfile
import unittest

from tools.techtree_handoff_audit import TechTreeHandoffError, audit


ROOT = Path(os.environ.get("WOT091_ROOT", Path(__file__).resolve().parents[1])).resolve()
DISASSEMBLY = ROOT / (
    "local/evidence/20261007-native-tree-filter-01/bytecode/"
    "client__gui__scaleform__daapi__view__lobby__techtree__techtree.json"
)


class TechTreeHandoffAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        required = [DISASSEMBLY]
        required.extend(ROOT / f"WoT_0.9.1_RU_0717_{name}/res/scripts/client/"
                        "gui/scaleform/daapi/view/lobby/techtree/TechTree.pyc"
                        for name in ("original", "research"))
        if not all(path.is_file() for path in required):
            raise unittest.SkipTest("ignored TechTree evidence/client copy unavailable")

    def test_real_static_handoff_shape(self):
        report = audit(root=ROOT, disassembly=DISASSEMBLY)
        self.assertEqual(report["status"], "PASS_STATIC_TECHTREE_HANDOFF_SOURCE")
        self.assertEqual(report["source_sha256"],
                         "d3fca045cb1fd478a6eb306adfda08ce019795e926574ed943b31946f0dcfb42")
        self.assertEqual(report["source_copies"]["original"], report["source_sha256"])
        self.assertEqual(report["source_copies"]["research"], report["source_sha256"])
        self.assertTrue(report["methods"]["requestNationTreeData"]["sets_available_nations"])
        self.assertTrue(report["methods"]["getNationTreeData"]["loads_nation_data"])
        self.assertEqual(report["native_account_payload"], "NOT_RUN")

    def test_unknown_flow_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path = Path(temp) / "techtree.json"
            value = json.loads(DISASSEMBLY.read_text(encoding="utf-8"))
            row = next(item for item in value if item.get("qualified_name") ==
                       "<module>.TechTree.getNationTreeData")
            row["varnames"] = ["self", "nationName"]
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(TechTreeHandoffError):
                audit(root=ROOT, disassembly=path)

    def test_duplicate_json_key_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path = Path(temp) / "techtree.json"
            path.write_text('[{"qualified_name":"x","qualified_name":"y"}]', encoding="utf-8")
            with self.assertRaises(TechTreeHandoffError):
                audit(root=ROOT, disassembly=path)

    def test_path_escape_is_rejected(self):
        with self.assertRaises(TechTreeHandoffError):
            audit(root=ROOT, disassembly=Path(tempfile.gettempdir()) / DISASSEMBLY.name)


if __name__ == "__main__":
    unittest.main()
