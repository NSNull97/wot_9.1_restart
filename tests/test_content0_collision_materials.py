"""CONTENT-0 2.5b: collision sources of the 13 refused #717 vehicles (test_lab generator rules).

Device/crew material kinds, `nodefullVisual` collision models and a duplicate unrelated XML child are
accepted only by the test_lab variant; main keeps the MS-1 kind set and the strict bindings.
Research: docs/research/CONTENT0_COLLISION_MATERIALS.md.
"""
import copy
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT), str(ROOT / "tools")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import battle_any_profiles as generator
import ms1_contact_bundle as materials
from p04m_battle_profiles import ProfileError as SourceError, _effective
ProfileError = generator.ProfileError

ORIGINAL = Path(os.environ.get("WOT091_ORIGINAL_ROOT", "C:/WoT_0.9.1_RU_0717_original"))
IDENTITY = [1., 0., 0., 0., 1., 0., 0., 0., 1., 0., 0., 0.]


def section(*children, value=""):
    return {"value": value, "children": [{"name": n, "data": d} for n, d in children]}


def leaf(value, *children):
    return section(*children, value=value)


def visual(**extra):
    v = {"/node[1]/identifier[1]": "Scene Root", "/node[1]/transform[1]": list(IDENTITY),
         "/renderSet[1]/treatAsWorldSpaceObject[1]": False,
         "/boundingBox[1]/min[1]": "-1 -0.5 -3", "/boundingBox[1]/max[1]": "1 0.8 3"}
    v.update(extra)
    return v


class KindTables(unittest.TestCase):
    def test_device_kinds_disjoint_from_ms1_set_and_tracks_excluded(self):
        self.assertFalse(set(materials.DEVICE_KINDS) & set(materials.EXPECTED_KINDS))
        self.assertEqual(set(materials.DEVICE_KINDS), set(materials.DEVICE_EXTRAS))
        self.assertEqual(sorted(materials.DEVICE_KINDS.values()), [21, 22, 26, 29, 30, 41, 42, 43, 44, 45, 46, 47, 48])
        self.assertNotIn("leftTrack", materials.ALL_KINDS)
        self.assertEqual(materials.ALL_KINDS, {**materials.EXPECTED_KINDS, **materials.DEVICE_KINDS})

    def test_gateway_device_names_equal_generator_table(self):
        source = (ROOT / "server/gateway/src/shared/materials.rs").read_text(encoding="utf-8")
        body = source[source.index("fn device_kind_name"):]
        body = body[:body.index("_=>return None")]
        for name, kind in materials.DEVICE_KINDS.items():
            self.assertIn('%d=>"%s"' % (kind, name), body)

    def test_main_takes_the_device_kinds_since_the_transfer(self):
        # CONTENT-0 main transfer (owner 12.11): main and test_lab share the device/crew kinds.
        self.assertIs(generator.KINDS, materials.ALL_KINDS)


class ActiveArmor(unittest.TestCase):
    def defaults(self):
        base = {"kind": 0, "armor": 0, "extra_is_none": False, "damageKind": 1, "vehicleDamageFactor": 0.0,
                "useArmorHomogenization": False, "useHitAngle": False, "useAntifragmentationLining": False,
                "mayRicochet": False, "collideOnceOnly": True, "chanceToHitByProjectile": 0.33,
                "chanceToHitByExplosion": 0.15, "continueTraceIfNoHit": True}
        armor = dict(base, armor=None, extra_is_none=True, damageKind=0, vehicleDamageFactor=1.0,
                     chanceToHitByProjectile=1.0, chanceToHitByExplosion=1.0)
        return {"armor_1": dict(armor, kind=1), "commander": dict(base, kind=41)}

    def test_crew_role_record_only_with_device_kinds(self):
        # T40/Object263/DickerMax hull, M10 turret: `<commander>0<vehicleDamageFactor>1.0</...></commander>`.
        node = section(("armor_1", 50), ("commander", leaf(0, ("vehicleDamageFactor", 1.0))))
        with self.assertRaisesRegex(SourceError, "active armor kind bound"):
            _effective(node, self.defaults())
        result = _effective(node, self.defaults(), materials.ALL_KINDS)
        self.assertEqual(result["commander"]["armor"], 0.0)
        self.assertEqual(result["commander"]["vehicleDamageFactor"], 1.0)
        self.assertEqual(result["commander"]["damageKind"], 1)
        self.assertEqual(result["armor_1"]["armor"], 50.0)
        materials._validate_effective(result["commander"], 41)

    def test_duplicate_unrelated_child_tolerated_needed_section_unique(self):
        armor = section(("armor_1", 60), ("gun", 30))
        gun = section(("maxAmmo", 68), ("armor", armor), ("animateEmblemSlots", True), ("animateEmblemSlots", False))
        node = section(("turrets0", section(("IS-85", section(("guns", section(("_85mm_D-5T", gun))))))))
        path = ("turrets0", "IS-85", "guns", "_85mm_D-5T")
        # One rule for main and test_lab since the CONTENT-0 main transfer (owner 12.11).
        for flag in (False, True):
          with mock.patch.object(generator, "TEST_LAB", flag):
            self.assertIs(generator.active_armor(node, path), armor)
        with mock.patch.object(generator, "TEST_LAB", True):
            twice = copy.deepcopy(node)
            twice["children"][0]["data"]["children"][0]["data"]["children"][0]["data"]["children"][0]["data"]["children"].append(
                {"name": "armor", "data": armor})
            with self.assertRaisesRegex(ProfileError, "missing/duplicate armor"):
                generator.active_armor(twice, path)
            with self.assertRaisesRegex(ProfileError, "missing/duplicate armor"):
                generator.active_armor(section(("turrets0", section(("IS-85", section(("guns", section(
                    ("_85mm_D-5T", section(("maxAmmo", 1)))))))))), path)


class VisualBinding(unittest.TestCase):
    STEM = "vehicles/german/G58_VK4502P/collision/Hull"

    def test_nodeless_binding_unchanged(self):
        for lab in (False, True):
            with mock.patch.object(generator, "TEST_LAB", lab):
                self.assertIsNone(generator.visual_binding({"/nodelessVisual[1]": self.STEM}, visual(), self.STEM))
                with self.assertRaisesRegex(ProfileError, "binding"):
                    generator.visual_binding({"/nodelessVisual[1]": self.STEM + "x"}, visual(), self.STEM)
                with self.assertRaisesRegex(ProfileError, "binding"):
                    generator.visual_binding({}, visual(), self.STEM)

    def test_nodefull_only_test_lab_scene_root_render_set(self):
        model = {"/nodefullVisual[1]": self.STEM}
        bound = visual(**{"/renderSet[1]/node[1]": "Scene Root", "/node[1]/node[1]/identifier[1]": "collision"})
        # nodefullVisual on main too since the CONTENT-0 main transfer (owner 12.11).
        with mock.patch.object(generator, "TEST_LAB", False):
            self.assertEqual(generator.visual_binding(model, bound, self.STEM), [[-1., -.5, -3.], [1., .8, 3.]])
        with mock.patch.object(generator, "TEST_LAB", True):
            box = generator.visual_binding(model, bound, self.STEM)
            self.assertEqual(box, [[-1., -.5, -3.], [1., .8, 3.]])
            self.assertTrue(generator.inside_box({"min": [-1., -.5, -3.0005], "max": [1., .8, 3.]}, box))
            self.assertFalse(generator.inside_box({"min": [-1., -.5, -3.01], "max": [1., .8, 3.]}, box))
            with self.assertRaisesRegex(ProfileError, "binding"):
                generator.visual_binding({**model, "/nodelessVisual[1]": self.STEM}, bound, self.STEM)
            for poison in ({"/renderSet[1]/node[1]": "hull"}, {"/renderSet[1]/node[2]": "hull"},
                           {"/renderSet[2]": ""}, {"/node[2]": ""}):
                with self.assertRaisesRegex(ProfileError, "nodefull render set binding"):
                    generator.visual_binding(model, {**bound, **poison}, self.STEM)
            with self.assertRaisesRegex(ProfileError, "nonidentity visual root"):
                generator.visual_binding(model, {**bound, "/node[1]/transform[1]": IDENTITY[:9] + [0., 1., 0.]}, self.STEM)


@unittest.skipUnless(ORIGINAL.is_dir(), "original #717 client copy absent")
class CommonDeviceRecords(unittest.TestCase):
    def test_common_vehicle_xml_device_records(self):
        src = generator.Sources(ORIGINAL)
        kinds = src.member(materials.MISC_REL, materials.KINDS_MEMBER)
        self.assertEqual(generator.pin(kinds), materials.MEMBER_PINS[materials.KINDS_KEY])
        mapping = materials._kind_mapping(generator.decode(kinds, max_bytes=generator.MAX_MEMBER))
        loader = materials._loader_defaults(src.file(materials.LOADER_REL))
        common = generator.decode(src.file(materials.COMMON_REL), max_bytes=generator.MAX_MEMBER)
        self.assertEqual(generator.pin(src.file(materials.COMMON_REL)), materials.FILE_PINS[materials.COMMON_REL])
        main = materials._common_materials(common, mapping, loader)
        every = materials._common_materials(common, mapping, loader, materials.ALL_KINDS)
        self.assertEqual(set(main), set(materials.EXPECTED_KINDS))
        self.assertEqual({k: every[k] for k in main}, main)
        for name, kind in materials.DEVICE_KINDS.items():
            record = every[name]
            materials._validate_effective(dict(record, armor=0), kind)
            self.assertEqual((record["kind"], record["armor"], record["extra_is_none"], record["damageKind"]), (kind, 0, False, 1))
            crew = kind >= 41
            self.assertEqual(record["vehicleDamageFactor"], 0.0 if crew else 1.0, name)
            self.assertEqual((record["chanceToHitByProjectile"], record["chanceToHitByExplosion"]),
                             (0.33, 0.15) if crew else (0.27, 0.27) if name == "ammoBay" else (0.45, 0.45), name)
            self.assertEqual(record["continueTraceIfNoHit"], crew, name)
            self.assertTrue(record["collideOnceOnly"])
            self.assertFalse(record["useHitAngle"] or record["mayRicochet"] or record["useArmorHomogenization"])


if __name__ == "__main__":
    unittest.main()
