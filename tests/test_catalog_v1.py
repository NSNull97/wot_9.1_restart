"""CAT-01 contract: one catalog, one hash, every consumer and every retained list agree."""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT), str(ROOT / "tools"), str(ROOT / "client_patch")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import catalog_build
import catalog_v1
import catalog_v1_data
import catalog_v1_hints
import p04m_stock_registry as registry

CATALOG = ROOT / "config/catalog/catalog.v1.json"
ORIGINAL = Path(os.environ.get("WOT091_ORIGINAL_ROOT", "C:/WoT_0.9.1_RU_0717_original"))


def literal(path, name, names=None):
    """Exact module-level literal of a Python 2/3 client or tool file, never executed."""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
            source = ast.unparse(node.value)
            for key, value in (names or {}).items():
                source = re.sub(r"\b%s\b" % key, repr(value), source)
            return ast.literal_eval(source)
    raise AssertionError("%s not found in %s" % (name, path))


LEGACY_KINDS = ["ms1", "is7", "t26", "t34", "t3485"]
# BATTLE-ANY stage 3 pilot (owner 2026-10-27): generated rows, admission "always".
PILOT_KINDS = ["ussr-KV1", "usa-M4_Sherman", "germany-Waffentrager_E100", "japan-Chi_Ri"]


def document():
    return json.loads(CATALOG.read_bytes())


class CatalogBindingContract(unittest.TestCase):
    def tearDown(self):
        catalog_v1.deactivate_for_tests()

    def test_generated_bindings_equal_committed_catalog_and_share_one_hash(self):
        digest, doc = catalog_build.check_bindings()
        self.assertEqual(digest, hashlib.sha256(CATALOG.read_bytes()).hexdigest())
        kinds = [v["kind"] for v in doc["vehicles"]]
        self.assertEqual(kinds, LEGACY_KINDS + PILOT_KINDS)
        self.assertEqual(catalog_v1_data.CATALOG_SHA256, digest)
        self.assertEqual([v["kind"] for v in catalog_v1_data.VEHICLES], kinds)
        self.assertEqual(catalog_v1_hints.CATALOG_SHA256, digest)
        self.assertEqual([v["kind"] for v in catalog_v1_hints.VEHICLES], kinds)
        rust = (ROOT / "server/gateway/src/shared/vehicle_catalog.rs").read_text(encoding="ascii")
        self.assertEqual(re.findall(r'pub const CATALOG_SHA256:&str="([0-9a-f]{64})";', rust), [digest])
        self.assertEqual(re.findall(r'Vehicle\{kind:"([A-Za-z0-9_-]+)"', rust), kinds)
        node = subprocess.run(["node", "--input-type=module", "-e",
            "const m=await import(process.argv[1]);process.stdout.write(JSON.stringify("
            "{sha:m.CATALOG_SHA256,kinds:m.CATALOG_VEHICLES.map(v=>v.kind),vehicles:m.CATALOG_VEHICLES}))",
            (ROOT / "web/src/catalog-v1.mjs").as_uri()], capture_output=True, text=True, timeout=60, check=True)
        js = json.loads(node.stdout)
        self.assertEqual((js["sha"], js["kinds"]), (digest, kinds))
        self.assertEqual(js["vehicles"], doc["vehicles"])

    def test_catalog_is_canonical_and_battle_admission_is_a_closed_data_field(self):
        raw = CATALOG.read_bytes()
        self.assertEqual(raw, catalog_build.canonical(json.loads(raw)) + b"\n")
        for v in document()["vehicles"]:
            self.assertIn(v["battle_admission"], ("always", "zero_economy_policy", "none"))
            self.assertEqual(v["descriptor_sha256"], hashlib.sha256(bytes.fromhex(v["descriptor_hex"])).hexdigest())
            self.assertEqual(v["type_id"], v["native_compact_id"] >> 8)
            for s in v["shells"]:
                self.assertEqual(s["native_compact_id"], (s["item_id"] << 8) + (v["nation_id"] << 4) + 10)

    def test_python_activation_refuses_a_foreign_hash(self):
        self.assertFalse(catalog_v1.active())
        with self.assertRaises(catalog_v1.CatalogMismatch):
            catalog_v1.activate("0" * 64)
        self.assertFalse(catalog_v1.active())
        catalog_v1.activate(catalog_v1_data.CATALOG_SHA256)
        self.assertTrue(catalog_v1.active())

    def test_builder_rejects_unknown_admission_value(self):
        raw = json.loads((ROOT / "config/catalog/server_profiles.v1.json").read_bytes())
        raw["vehicles"][2]["battle_admission"] = "yes"
        path = ROOT / "local/test-runs/cat01-profiles-bad.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(raw))
        with self.assertRaises(catalog_build.CatalogBuildError):
            catalog_build.load_profiles(path)


class CatalogEqualsRetainedLists(unittest.TestCase):
    """Old closed lists stay until owner acceptance; drift between them fails here."""

    def setUp(self):
        catalog_v1.activate(catalog_v1_data.CATALOG_SHA256)
        self.by_kind = {v["kind"]: v for v in document()["vehicles"]}

    def tearDown(self):
        catalog_v1.deactivate_for_tests()

    def test_python_registry_pins_and_pool_shell_rows(self):
        from p04m_pool_store import SHELL_ROWS
        pins = catalog_v1.stock_pins()
        self.assertEqual(dict(registry.PINS), {k: pins[k] for k in LEGACY_KINDS})
        self.assertEqual(sorted(set(pins) - set(registry.PINS)), sorted(PILOT_KINDS))
        rows = catalog_v1.shell_rows()
        self.assertEqual({k: rows[k] for k in SHELL_ROWS}, SHELL_ROWS)
        self.assertEqual(set(registry.NEW_KINDS), {k for k, v in self.by_kind.items()
                                                   if v["battle_admission"] == "zero_economy_policy"})

    def test_p04m_battle_specs(self):
        from p04m_battle_profiles import SPECS
        for kind in registry.NEW_KINDS:
            spec, v = SPECS[kind + "-stock"], self.by_kind[kind]
            roles = ("chassis", "engine", "fuelTank", "radio", "turret", "gun")
            self.assertEqual((spec["resource"], spec["type_cd"], spec["descriptor"], spec["max_hp"], spec["capacity"],
                              spec["shell"], spec["shell_cd"], spec["crew"],
                              spec["module_cds"]),
                             (v["resource_name"], v["native_compact_id"], v["descriptor_hex"], v["max_hp"],
                              v["ammo_capacity"], v["shells"][0]["resource_name"], v["shells"][0]["native_compact_id"],
                              tuple(tuple(c["roles"]) for c in v["crew"]),
                              tuple(v["modules"][r]["native_compact_id"] for r in roles)))

    def test_p09c_ammo_catalog_for_legacy_mounts(self):
        from p09c_ammo_catalog import MOUNTS, SHELLS
        for kind in ("ms1", "is7"):
            v, mount = self.by_kind[kind], MOUNTS[kind + "-stock"]
            self.assertEqual((mount.vehicle_native_compact_id, mount.turret_native_compact_id, mount.gun_native_compact_id,
                              mount.capacity, mount.shell_ids),
                             (v["native_compact_id"], v["modules"]["turret"]["native_compact_id"],
                              v["modules"]["gun"]["native_compact_id"], v["ammo_capacity"],
                              tuple(s["shell_definition_id"] for s in v["shells"])))
            for s in v["shells"]:
                shell = SHELLS[s["shell_definition_id"]]
                self.assertEqual((shell.resource_name, shell.kind, shell.item_id, shell.native_compact_id),
                                 (s["resource_name"], s["family"], s["item_id"], s["native_compact_id"]))

    def test_device_caps_source(self):
        caps = json.loads((ROOT / "server/gateway/src/shared/p06t_device_source_caps.json").read_bytes())
        for row in caps["profiles"]:
            v = self.by_kind[row["profile"][:-len("-stock")]]
            self.assertEqual([(d["max_health"], d["max_regen_health"]) for d in row["devices"]],
                             [(d["max_health"], d["max_regen_health"]) for d in v["devices"]])
            self.assertEqual(row["vehicle_max_health"], v["max_hp"])

    def test_client_battle_button_table(self):
        legacy = literal(ROOT / "client_patch/map_drive_client.py", "PROFILE13_VEHICLES",
                         {"MS1_SHA256": literal(ROOT / "client_patch/map_drive_client.py", "MS1_SHA256")})
        tree = ast.parse((ROOT / "client_patch/map_drive_client.py").read_text(encoding="utf-8"))
        func = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "catalog_profile13_vehicles")
        scope = {}
        exec(compile(ast.Module(body=[func], type_ignores=[]), "map_drive_client.py", "exec"), scope)
        table = scope["catalog_profile13_vehicles"](catalog_v1_hints)
        self.assertEqual({k: table[k] for k in legacy}, legacy)
        self.assertEqual(set(table) - set(legacy), {self.by_kind[k]["native_compact_id"] for k in PILOT_KINDS})

    def test_client_crew_and_ammo_ui_tables_are_the_catalog_ui_subset(self):
        crew = {v["legacy_inventory"]["native_inventory_id"]: v for v in self.by_kind.values()
                if v["client_ui"]["crew"] and v["legacy_inventory"] is not None}
        expected = {n: (v["native_compact_id"], v["type_id"], v["vehicle_class"], tuple(c["roles"][0] for c in v["crew"]))
                    for n, v in crew.items()}
        for name in ("p04h_crew_ui.py", "p04i_crew_ui.py"):
            self.assertEqual(literal(ROOT / "client_patch" / name, "VEHICLES"), expected, name)
            self.assertEqual(literal(ROOT / "client_patch" / name, "MAX_TANKMEN"), 16)
        self.assertEqual(literal(ROOT / "client_patch/p04g_crew_ui.py", "ROLES"), {n: e[3] for n, e in expected.items()})
        ammo = {v["native_compact_id"]: (v["modules"]["turret"]["native_compact_id"], v["modules"]["gun"]["native_compact_id"],
                                         v["ammo_capacity"], tuple(s["native_compact_id"] for s in v["shells"]))
                for v in self.by_kind.values() if v["client_ui"]["ammo"]}
        self.assertEqual(literal(ROOT / "client_patch/p09d_ammo_ui.py", "MOUNTS"), ammo)


class AdmissionIsData(unittest.TestCase):
    def tearDown(self):
        catalog_v1.deactivate_for_tests()

    def test_legacy_and_catalog_admission_agree(self):
        kinds = [v["kind"] for v in catalog_v1_data.VEHICLES] + ["wt-e100-128", "kv1"]
        legacy = {(k, z): registry.mixed_admission(k, lambda z=z: z) for k in kinds[:5] for z in (False, True)}
        legacy_route = {k: registry.legacy_route_admitted(k) for k in kinds[:5]}
        catalog_v1.activate(catalog_v1_data.CATALOG_SHA256)
        self.assertEqual({(k, z): registry.mixed_admission(k, lambda z=z: z) for k in kinds[:5] for z in (False, True)}, legacy)
        self.assertEqual({k: registry.legacy_route_admitted(k) for k in kinds[:5]}, legacy_route)
        for k in kinds[5:]:
            # BATTLE-ANY pilot rows are admitted by data (owner 2026-10-27); others are unknown.
            self.assertEqual(registry.mixed_admission(k, lambda: False), k in PILOT_KINDS, k)
            self.assertEqual(registry.legacy_route_admitted(k), k in PILOT_KINDS, k)
        pins = dict(registry.active_pins())
        self.assertEqual({k: pins[k] for k in LEGACY_KINDS}, dict(registry.PINS))

    def test_changing_the_data_field_changes_admission_without_code(self):
        catalog_v1.activate(catalog_v1_data.CATALOG_SHA256)
        rows = tuple(dict(v, battle_admission="none") if v["kind"] == "t34" else
                     dict(v, battle_admission="always") if v["kind"] == "t26" else v
                     for v in catalog_v1_data.VEHICLES)
        with mock.patch.object(catalog_v1_data, "VEHICLES", rows):
            self.assertFalse(registry.mixed_admission("t34", lambda: True))
            self.assertTrue(registry.mixed_admission("t26", lambda: False))
            self.assertTrue(registry.legacy_route_admitted("t26"))
            self.assertFalse(registry.mixed_admission("t3485", lambda: False))
            self.assertTrue(registry.mixed_admission("t3485", lambda: True))

    def test_catalog_that_disagrees_with_a_retained_pin_is_refused(self):
        catalog_v1.activate(catalog_v1_data.CATALOG_SHA256)
        rows = tuple(dict(v, max_hp=v["max_hp"] + 1) if v["kind"] == "t34" else v for v in catalog_v1_data.VEHICLES)
        with mock.patch.object(catalog_v1_data, "VEHICLES", rows):
            with self.assertRaises(Exception) as caught:
                registry.active_pins()
            self.assertIn("CAT01_CATALOG_DISAGREES", str(caught.exception))

    def test_inventory_binding_is_identical_in_both_modes(self):
        account = "0f1e2d3c-4b5a-4968-8776-655443322110"
        cases = [(n, k) for n in (1, 2, 3, 9) for k in ("ms1", "is7", "t26", "t34", "t3485")]

        def run():
            out = {}
            for n, k in cases:
                try: out[(n, k)] = registry.StockRegistry.inventory_id(account, n, k)
                except Exception as error: out[(n, k)] = type(error).__name__ + getattr(error, "code", "")
            return out
        legacy = run()
        catalog_v1.activate(catalog_v1_data.CATALOG_SHA256)
        self.assertEqual(run(), legacy)


@unittest.skipUnless((ORIGINAL / "WorldOfTanks.exe").is_file(), "NOT_RUN: pinned original client absent")
class CatalogFromPinnedClient(unittest.TestCase):
    def tearDown(self):
        catalog_v1.deactivate_for_tests()

    def test_rebuild_from_pinned_client_equals_committed_catalog(self):
        self.assertEqual(catalog_build.catalog_bytes(catalog_build.build_document(ORIGINAL)), CATALOG.read_bytes())

    def test_stock_registry_is_identical_in_both_modes(self):
        from p09e_research_catalog import load_catalog
        research = load_catalog(ORIGINAL)
        legacy = registry.StockRegistry(research)
        catalog_v1.activate(catalog_v1_data.CATALOG_SHA256)
        current = registry.StockRegistry(research)
        self.assertEqual({k: current.profiles[k] for k in LEGACY_KINDS}, dict(legacy.profiles))
        self.assertEqual(sorted(set(current.profiles) - set(legacy.profiles)), sorted(PILOT_KINDS))
        for kind in PILOT_KINDS:
            self.assertEqual(current.profiles[kind].vehicle_id, catalog_v1.by_kind(kind)["vehicle_id"])
        # The gateway-pinned registry hash covers the legacy kinds only.
        self.assertEqual(current.sha256, legacy.sha256)


if __name__ == "__main__":
    unittest.main()
