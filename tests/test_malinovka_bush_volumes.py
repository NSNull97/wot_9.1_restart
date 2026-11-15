import json
import math
import unittest

from tools.malinovka_bush_volumes import CALIBRATION, parse_calibration, volume


class BushVolumeTests(unittest.TestCase):
    def setUp(self):
        self.cal = parse_calibration(CALIBRATION.read_bytes())
        self.resource = "speedtree/02_Malinovka/Bush.spt"
        self.setting = self.cal["resources"][self.resource]

    def row(self, matrix):
        return {"chunk": [-2, 3], "speedtree_index": 1, "resource": self.resource,
                "seed": 1, "transform": matrix}

    def test_rotation_scale_and_aabb_contain_ellipsoid(self):
        # Rotate and scale, with a sheared third basis: never replace it by
        # an axis-aligned ellipsoid of the same projected radii.
        shape = [0, 0, 2, 0, 3, 0, -4, 0, 1, 3, 4, 5]
        v = volume(self.row(shape), self.setting)
        self.assertEqual(v["center_world"], [-197, 6.4, 305])
        self.assertEqual(v["basis_world_rows"], [[0, 0, 2], [0, 2.4000000000000004, 0], [-4, 0, 1]])
        expected = [4, 2.4, math.sqrt(5)]
        for actual, bound in zip(v["aabb_half_extents_world"], expected):
            self.assertAlmostEqual(actual, bound)
        for u in ((1,0,0), (0,1,0), (0,0,1), (1/math.sqrt(3),)*3):
            for j in range(3):
                delta = sum(u[i] * v["basis_world_rows"][i][j] for i in range(3))
                self.assertLessEqual(abs(delta), expected[j] + 1e-12)

    def test_singular_and_nonfinite_transforms_are_rejected(self):
        with self.assertRaises(ValueError):
            volume(self.row([0] * 12), self.setting)
        with self.assertRaises(ValueError):
            volume(self.row([float("nan")] * 12), self.setting)

    def test_bad_and_duplicate_calibration_values_rejected(self):
        altered = json.loads(CALIBRATION.read_bytes())
        altered["resources"][self.resource]["radii_local"][0] = 0
        with self.assertRaises(ValueError):
            parse_calibration(json.dumps(altered).encode())
        with self.assertRaises(ValueError):
            parse_calibration(b'{"schema":1,"schema":2}')


if __name__ == "__main__":
    unittest.main()
