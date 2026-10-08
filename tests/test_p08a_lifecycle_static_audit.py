import json
import os
from pathlib import Path
import tempfile
import unittest

from tools.p08a_lifecycle_static_audit import LifecycleAuditError, audit


ROOT = Path(os.environ.get("WOT091_ROOT", Path(__file__).resolve().parents[1])).resolve()
BASE = ROOT / "local/evidence/20261002-p00-p01/summary"
PATHS = {
    "lifecycle": BASE / "lifecycle-static.json",
    "contracts": BASE / "contracts.json",
    "resource_facts": BASE / "resource-facts.json",
    "sources": BASE / "sources.json",
}


def _run(**overrides):
    args = {"root": ROOT, **PATHS}
    args.update(overrides)
    return audit(**args)


class P08ALifecycleStaticAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not all(path.is_file() for path in PATHS.values()):
            raise unittest.SkipTest("ignored P00/P01 lifecycle evidence unavailable")

    def test_real_hash_bound_lifecycle_boundary(self):
        report = _run()
        self.assertEqual(report["status"], "PASS_STATIC_SOURCE_BOUNDARY_ONLY")
        self.assertEqual(report["schema"], "p08a-lifecycle-static-audit.v1")
        self.assertEqual(report["source_manifest"]["count"], 20)
        self.assertEqual(report["contracts"]["arena"]["properties"]["gameplayID"]["type"], "UINT16")
        self.assertEqual(report["contracts"]["vehicle"]["CellMethods"]["shoot"]["args"], ["FLOAT32"])
        self.assertEqual(report["native_lifecycle"], "NOT_RUN")

    def test_lifecycle_shape_mutation_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path = Path(temp) / "lifecycle.json"
            value = json.loads(PATHS["lifecycle"].read_text(encoding="utf-8"))
            value["avatar"][0]["source_filename"] = "scripts/client/other.py"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(LifecycleAuditError):
                _run(lifecycle=path)

    def test_contract_shape_mutation_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path = Path(temp) / "contracts.json"
            value = json.loads(PATHS["contracts"].read_text(encoding="utf-8"))
            method = next(item for item in value["definitions"]["vehicle"]["CellMethods"]
                          if item["name"] == "shoot")
            method["args"] = ["INT32"]
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(LifecycleAuditError):
                _run(contracts=path)

    def test_source_manifest_mutation_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path = Path(temp) / "sources.json"
            value = json.loads(PATHS["sources"].read_text(encoding="utf-8"))
            value[0]["bytes"] += 1
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(LifecycleAuditError):
                _run(sources=path)

    def test_duplicate_json_key_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path = Path(temp) / "lifecycle.json"
            path.write_text('{"account":[],"account":[]}', encoding="utf-8")
            with self.assertRaises(LifecycleAuditError):
                _run(lifecycle=path)

    def test_nonfinite_json_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            path = Path(temp) / "lifecycle.json"
            path.write_text('{"account":[{"x":NaN}]}', encoding="utf-8")
            with self.assertRaises(LifecycleAuditError):
                _run(lifecycle=path)

    def test_depth_and_item_bounds_are_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            deep = Path(temp) / "deep.json"
            value = "{}"
            for _ in range(66):
                value = "[" + value + "]"
            deep.write_text(value, encoding="utf-8")
            with self.assertRaises(LifecycleAuditError):
                _run(lifecycle=deep)
            many = Path(temp) / "many.json"
            many.write_text(json.dumps([{} for _ in range(100_001)]), encoding="utf-8")
            with self.assertRaises(LifecycleAuditError):
                _run(lifecycle=many)

    def test_path_escape_is_rejected(self):
        outside = Path(tempfile.gettempdir()) / "p08a-lifecycle-outside.json"
        with self.assertRaises(LifecycleAuditError):
            _run(lifecycle=outside)


if __name__ == "__main__":
    unittest.main()
