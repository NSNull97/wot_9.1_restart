"""SHELL-01 chassis armour export: refusal rules, track materials, committed table.

Unit inputs are synthetic XML-node/flat-map fixtures; they check our reader's
bounds and refusals, not the original server's armour behaviour.
"""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import chassis_armor_export as export  # noqa: E402

ORIGINAL = Path("C:/WoT_0.9.1_RU_0717_original")
CHASSIS = "Chassis_X"
PREFIX = "/chassis[1]/" + CHASSIS + "[1]/armor[1]"


def common():
    base = dict(armor=None, extra=None, damage_kind=1, auto_damage_kind=True, vehicleDamageFactor=0.0,
                chanceToHitByProjectile=1.0, chanceToHitByExplosion=1.0, useArmorHomogenization=False,
                useHitAngle=False, useAntifragmentationLining=False, mayRicochet=False, collideOnceOnly=True,
                continueTraceIfNoHit=False)
    return {"leftTrack": dict(base, kind=23, extra="leftTrackHealth"),
            "rightTrack": dict(base, kind=24, extra="rightTrackHealth")}


def flat(**extra):
    vf = {PREFIX: "", PREFIX + "/leftTrack[1]": 40, PREFIX + "/rightTrack[1]": 40}
    vf.update(extra)
    return vf


def node(name, children):
    return {"value": "", "children": [{"name": k, "data": v} for k, v in children]}


def common_node(**changes):
    fields = dict(vehicleDamageFactor="0.0", useArmorHomogenization=False, useHitAngle=False,
                  useAntifragmentationLining=False, mayRicochet=False, collideOnceOnly=True,
                  damageKind={"base64": "auto"}, chanceToHitByProjectile="1.0", chanceToHitByExplosion="1.0",
                  continueTraceIfNoHit=False)
    tracks = []
    for track, extra in (("leftTrack", "leftTrackHealth"), ("rightTrack", "rightTrackHealth")):
        row = dict(fields, extra=extra)
        row.update(changes.get(track, {}))
        tracks.append((track, node(track, row.items())))
    return node("root", [("materials", node("materials", tracks))])


class LocalTrackTests(unittest.TestCase):
    def test_listed_tracks_get_local_armor_and_keep_common_flags(self):
        result = export.local_tracks(flat(), CHASSIS, common())
        self.assertEqual({k: v["armor"] for k, v in result.items()}, {"leftTrack": 40.0, "rightTrack": 40.0})
        self.assertTrue(result["leftTrack"]["auto_damage_kind"])
        self.assertEqual(result["rightTrack"]["vehicleDamageFactor"], 0.0)

    def test_missing_track_has_no_material_record(self):
        vf = flat()
        del vf[PREFIX + "/rightTrack[1]"]
        self.assertEqual(set(export.local_tracks(vf, CHASSIS, common())), {"leftTrack"})

    def test_supported_override_is_applied(self):
        vf = flat(**{PREFIX + "/leftTrack[1]/vehicleDamageFactor[1]": "0.5"})
        self.assertEqual(export.local_tracks(vf, CHASSIS, common())["leftTrack"]["vehicleDamageFactor"], 0.5)

    def test_refusals(self):
        cases = {
            "repeated armor": flat(**{"/chassis[1]/" + CHASSIS + "[1]/armor[2]": ""}),
            "repeated track": flat(**{PREFIX + "/leftTrack[2]": 10}),
            "hull material on chassis": flat(**{PREFIX + "/armor_1[1]": 10}),
            "unsupported override": flat(**{PREFIX + "/leftTrack[1]/extra[1]": "x"}),
            "deep override": flat(**{PREFIX + "/leftTrack[1]/a[1]/b[1]": 1}),
            "bad child path": flat(**{PREFIX + "/left-track[1]": 1}),
            "empty armor": {PREFIX: ""},
        }
        for label, vf in cases.items():
            with self.subTest(label), self.assertRaises(export.Refused):
                export.local_tracks(vf, CHASSIS, common())

    def test_other_repeated_chassis_children_do_not_matter(self):
        # M103: two drivingWheels children in the chassis section.
        vf = flat(**{"/chassis[1]/" + CHASSIS + "[1]/drivingWheels[1]": "a",
                     "/chassis[1]/" + CHASSIS + "[1]/drivingWheels[2]": "b"})
        self.assertEqual(len(export.local_tracks(vf, CHASSIS, common())), 2)


class CommonTrackTests(unittest.TestCase):
    mapping = {"leftTrack": 23, "rightTrack": 24}

    def test_auto_damage_kind_is_device_and_flagged(self):
        result = export.common_tracks(common_node(), self.mapping, dict(export.DAMAGE_KINDS))
        self.assertEqual((result["leftTrack"]["damage_kind"], result["leftTrack"]["auto_damage_kind"]), (1, True))
        self.assertIsNone(result["rightTrack"]["armor"])

    def test_device_damage_kind_is_not_flagged_auto(self):
        tree = common_node(leftTrack={"damageKind": "device"})
        result = export.common_tracks(tree, self.mapping, dict(export.DAMAGE_KINDS))
        self.assertEqual((result["leftTrack"]["damage_kind"], result["leftTrack"]["auto_damage_kind"]), (1, False))

    def test_refusals(self):
        for label, tree in {"unknown damage kind": common_node(leftTrack={"damageKind": "spall"}),
                            "wrong extra": common_node(rightTrack={"extra": "leftTrackHealth"}),
                            "fraction above one": common_node(leftTrack={"vehicleDamageFactor": "1.5"})}.items():
            with self.subTest(label), self.assertRaises(ValueError):
                export.common_tracks(tree, self.mapping, dict(export.DAMAGE_KINDS))


class CommittedTableTests(unittest.TestCase):
    def setUp(self):
        self.table = json.loads(export.TABLE.read_bytes())
        self.rows = {r["vehicle_id"]: r for r in self.table["vehicles"]}

    def test_committed_table_is_consistent(self):
        self.assertEqual(export.check()["status"], "PASS_CHASSIS_TABLE")

    def test_every_battle_generated_vehicle_has_a_chassis_bundle(self):
        profiles = json.loads(export.PROFILES_TABLE.read_bytes())["vehicles"]
        missing = [r["vehicle_id"] for r in profiles
                   if r["status"] == "generated" and self.rows[r["vehicle_id"]]["status"] != "generated"]
        self.assertEqual(missing, [])

    def test_source_track_armor_of_known_vehicles(self):
        expected = {"vehicle:germany:Waffentrager_E100": 40.0, "vehicle:uk:GB48_FV215b_183": 25.0,
                    "vehicle:ussr:MS-1": 5.0, "vehicle:usa:M103": 20.0}
        for vehicle, armor in expected.items():
            with self.subTest(vehicle):
                self.assertEqual([(m["name"], m["armor"]) for m in self.rows[vehicle]["materials"]],
                                 [("leftTrack", armor), ("rightTrack", armor)])

    def test_tampered_identity_fails_check(self):
        bad = copy.deepcopy(self.table)
        bad["vehicles"][0]["identity"]["type_compact_id"] += 1
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "table.json"
            path.write_bytes(json.dumps(bad).encode())
            with self.assertRaises(ValueError):
                export.check(path)


@unittest.skipUnless((ORIGINAL / "res/scripts/common/items/vehicles.pyc").is_file(), "original client not present")
class LoaderTests(unittest.TestCase):
    def test_damage_kind_table_read_from_original_loader(self):
        raw = (ORIGINAL / "res/scripts/common/items/vehicles.pyc").read_bytes()
        self.assertEqual(export.damage_kind_loader(raw), {"armor": 0, "device": 1, "auto": 1})


if __name__ == "__main__":
    unittest.main()
