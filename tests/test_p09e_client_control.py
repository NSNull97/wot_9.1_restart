"""Opt-in bootstrap and capability policy tests; no native/UI claim."""
import ast
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "client_patch"))
import interactive_client as installer
import hangar_bootstrap as bootstrap
from tests import test_hangar_capabilities as prior


class ResearchCapabilityTests(unittest.TestCase):
    setUp = prior.CapabilityTests.setUp
    record = prior.CapabilityTests.record

    def activate(self):
        self.guard = prior.POLICY._ModuleChangeGuard(self.Panel, self.Messages, self.record, True)
        self.guard.install()
        self.addCleanup(self.guard.restore)

    def test_original_callback_receives_only_five_module_types_and_exact_arguments(self):
        self.activate()
        for compact in (6658, 5891, 5892, 3589, 7):
            args = (str(compact), 0, None, False)
            self.Panel().setVehicleModule(*args)
            self.assertEqual(self.mutations[-1], args)
        self.assertEqual(len(self.mutations), 5)
        self.assertEqual(self.notices, [])
        records = [value for event, value in self.records if event == "research_module_callback"]
        self.assertEqual(len(records), 5)
        self.assertTrue(all(row["authority"] == "server" for row in records))

    def test_equipment_removal_fuel_malformed_crosskind_and_nonzero_slots_still_denied(self):
        self.activate()
        forbidden = [("9", 0, None, False), ("8", 0, None, False), ("51462", 0, None, False),
                     ("5892", 0, "5892", True), ("5892", 0, "9", False), ("5892", 1, None, False),
                     ("5892", False, None, False), (True, 0, None, False), ("+5892", 0, None, False),
                     ("5892 " , 0, None, False), ("5892", 0, None, 0), ("999999999999", 0, None, False)]
        for args in forbidden: self.Panel().setVehicleModule(*args)
        self.assertEqual(self.mutations, [])
        self.assertEqual(len(self.notices), len(forbidden))

    def test_original_exception_is_not_converted_into_fake_success(self):
        def broken(*args): raise ValueError("native processor failed")
        self.Panel.setVehicleModule = broken
        self.activate()
        with self.assertRaisesRegex(ValueError, "native processor failed"):
            self.Panel().setVehicleModule("5892", 0, None, False)

    def test_optin_does_not_weaken_original_binding_audit(self):
        with self.assertRaisesRegex(RuntimeError, "wrapper mismatch"):
            prior.POLICY._audit_module_class(self.Panel)
        with self.assertRaises(ValueError):
            prior.POLICY._ModuleChangeGuard(self.Panel, self.Messages, self.record, "true")


class ResearchBootstrapTests(unittest.TestCase):
    def test_bad_feature_dependencies_rejected_before_engine_imports(self):
        for option in (True, "yes", 1):
            with self.assertRaises(ValueError):
                bootstrap.init([], lambda *a, **k: None, enable_research_service=option)
        self.assertIsNone(bootstrap._record)

    def test_runtime_settings_require_research_dependency_chain_and_no_arena(self):
        tree = ast.parse((ROOT / "client_patch/sr_interactive.py").read_text(encoding="utf-8-sig"))
        guards = []
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_runtime" for t in node.targets): break
            if isinstance(node, ast.If): guards.append(node)
        code = compile(ast.Module(body=guards, type_ignores=[]), "trusted-repository-settings-guards", "exec")
        valid = dict(enable_research_service=True, enable_cross_vehicle_crew=True,
                     enable_crew_transfer=True, enable_crew_recruitment=True, enable_p09d_ammo_service=True)
        exec(code, {"_settings": valid})
        exec(code, {"_settings": {}})
        for key in valid:
            for bad in (False, "true"):
                if key == "enable_research_service" and bad is False: continue
                with self.assertRaises(ValueError): exec(code, {"_settings": dict(valid, **{key: bad})})
        for key in ("enable_map_drive", "enable_shared_lab"):
            with self.assertRaises(ValueError): exec(code, {"_settings": dict(valid, **{key: True})})

    def test_research_policy_is_installed_before_items_and_restored_after_gui(self):
        source = (ROOT / "client_patch/hangar_bootstrap.py").read_text(encoding="utf-8-sig")
        self.assertLess(source.index("_step('research_cost_policy'"), source.index("_step('items'"))
        self.assertLess(source.index("close('gui_personality'"), source.index("close('research_cost_policy'"))
        self.assertIn("enable_research_service=_settings.get('enable_research_service') is True",
                      (ROOT / "client_patch/sr_interactive.py").read_text(encoding="utf-8-sig"))

    def test_installer_requires_explicit_copy_all_services_and_hangar(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            paths = dict(local_artifacts_root=base, original_client_root=base / "original", research_client_root=base / "other")
            for copy, cross, ammo, recruit, transfer, shared, arena in ((None, True, True, True, True, False, False),
                    ("copy", False, True, True, True, False, False), ("copy", True, False, True, True, False, False),
                    ("copy", True, True, False, True, False, False), ("copy", True, True, True, False, False, False),
                    ("copy", True, True, True, True, True, False), ("copy", True, True, True, True, False, True)):
                args = SimpleNamespace(out=str(base / "prepare"), research_copy=copy, enable_research_service=True,
                    enable_p09d_ammo_service=ammo, enable_crew_recruitment=recruit, enable_cross_vehicle_crew=cross,
                    enable_crew_transfer=transfer, enable_shared_lab=shared, enable_map_drive=arena)
                with patch.object(installer, "config", return_value=({}, paths)), \
                        patch("shared_client_copy.checked_copy", return_value=(base / "own-copy", {"owned": True})):
                    with self.assertRaises(ValueError): installer.prepare(args)
                self.assertFalse((base / "prepare").exists())
        self.assertEqual(installer.MODULES.count("p09e_research_policy"), 1)
        self.assertEqual(len(installer.MODULES), len(set(installer.MODULES)))


if __name__ == "__main__": unittest.main()
