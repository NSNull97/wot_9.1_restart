import json
import os
from pathlib import Path
import tempfile
import unittest

from tools.training_room_static_audit import TrainingRoomAuditError, audit


ROOT = Path(os.environ.get("WOT091_ROOT", Path(__file__).resolve().parents[1])).resolve()
ACCOUNT = ROOT / "local/evidence/20261002-p00-p01/decoded/res__scripts__entity_defs__account.def.json"
PREBATTLE = ROOT / "local/evidence/20261002-p00-p01/decoded/res__scripts__entity_defs__prebattle.def.json"
MANIFEST = ROOT / "local/evidence/20261002-p00-p01/baseline/original-content-manifest.json"


class TrainingRoomStaticAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not all(path.is_file() for path in (ACCOUNT, PREBATTLE, MANIFEST)):
            raise unittest.SkipTest("ignored P00/P01 training-room evidence unavailable")

    def test_real_contract_and_manifest(self):
        report = audit(root=ROOT, account_def=ACCOUNT, prebattle_def=PREBATTLE, manifest=MANIFEST)
        self.assertEqual(report["status"], "PASS_STATIC_TRAINING_ROOM_CONTRACT")
        self.assertEqual(report["build"], "v.0.9.1 #717")
        self.assertEqual(report["account"]["base_methods"]["createTraining"]["args"],
                         ["INT32", "INT32", "BOOL", "STRING"])
        self.assertEqual(report["prebattle"]["base_methods"]["setPlayerReady"]["args"][-2:],
                         ["ARRAY<INT32>", "ARRAY<INT32>"])
        self.assertEqual(report["native_request_bytes"], "NOT_RUN")

    def test_account_shape_mutation_is_rejected(self):
        value = json.loads(ACCOUNT.read_text(encoding="utf-8"))
        pending = [value]
        while pending:
            item = pending.pop()
            if isinstance(item, dict):
                if item.get("name") == "createTraining":
                    item["data"]["children"][0]["data"] = "UINT64"
                    break
                pending.extend(item.values())
            elif isinstance(item, list):
                pending.extend(item)
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path = Path(temp) / "account.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(TrainingRoomAuditError):
                audit(root=ROOT, account_def=path, prebattle_def=PREBATTLE, manifest=MANIFEST)

    def test_manifest_digest_mutation_is_rejected(self):
        value = json.loads(MANIFEST.read_text(encoding="utf-8"))
        row = next(item for item in value if item["path"] == "res/scripts/entity_defs/prebattle.def")
        row["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path = Path(temp) / "manifest.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(TrainingRoomAuditError):
                audit(root=ROOT, account_def=ACCOUNT, prebattle_def=PREBATTLE, manifest=path)

    def test_duplicate_json_key_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path = Path(temp) / "manifest.json"
            path.write_text('{"x":1,"x":2}', encoding="utf-8")
            with self.assertRaises(TrainingRoomAuditError):
                audit(root=ROOT, account_def=ACCOUNT, prebattle_def=PREBATTLE, manifest=path)

    def test_nonfinite_json_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path = Path(temp) / "manifest.json"
            path.write_text("NaN", encoding="utf-8")
            with self.assertRaises(TrainingRoomAuditError):
                audit(root=ROOT, account_def=ACCOUNT, prebattle_def=PREBATTLE, manifest=path)

    def test_path_escape_is_rejected(self):
        with self.assertRaises(TrainingRoomAuditError):
            audit(root=ROOT, account_def=Path(tempfile.gettempdir()) / ACCOUNT.name,
                  prebattle_def=PREBATTLE, manifest=MANIFEST)


if __name__ == "__main__":
    unittest.main()
