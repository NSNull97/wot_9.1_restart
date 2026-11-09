"""Module volumes from penetration-zone skins (tools/module_volumes.py)."""
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import module_volumes as mv  # noqa: E402

PAINT = (70, 70, 50)
BOX = [[-1.0, 0.0, -3.0], [1.0, 1.0, 3.0]]


def rows(points, axis):
    return [(p, axis) for p in points]


def grid(x, y0, y1, z0, z1, n=4):
    return [(x, y0 + (y1 - y0) * i / (n - 1), z0 + (z1 - z0) * j / (n - 1)) for i in range(n) for j in range(n)]


class Classify(unittest.TestCase):
    def test_legend_colours_are_marks_only_where_the_client_differs(self):
        for colour, kind in (((220, 30, 220), 'ammo'), ((40, 230, 40), 'engine'), ((30, 130, 220), 'fuel'), ((230, 230, 30), 'crew')):
            self.assertEqual(mv.classify(colour, PAINT), kind)
            self.assertIsNone(mv.classify(colour, colour), 'the client has the same colour')

    def test_paint_red_and_dark_pixels_are_not_marks(self):
        for colour in ((110, 110, 90), (230, 30, 30), (40, 5, 40)):
            self.assertIsNone(mv.classify(colour, PAINT), colour)


class Dds(unittest.TestCase):
    @staticmethod
    def dxt1(colour, width=4, height=4):
        header = bytearray(128)
        header[:4] = b'DDS '
        struct.pack_into('<2I', header, 12, height, width)
        header[84:88] = b'DXT1'
        return bytes(header) + struct.pack('<HHI', colour, colour, 0) * (((width + 3) // 4) * ((height + 3) // 4))

    def test_solid_block_decodes(self):
        width, height, plane = mv.decode_dds(self.dxt1(0xF800))
        self.assertEqual((width, height, tuple(plane[3][9:12])), (4, 4, (255, 0, 0)))

    def test_refuses_truncated_or_oversized_or_foreign(self):
        good = self.dxt1(1)
        for bad in (good[:130], b'XXXX' + good[4:], good[:84] + b'ATI2' + good[88:]):
            with self.assertRaises(mv.VolumeError):
                mv.decode_dds(bad)
        huge = bytearray(good)
        struct.pack_into('<2I', huge, 12, 8192, 8192)
        with self.assertRaises(mv.VolumeError):
            mv.decode_dds(bytes(huge))


class Volumes(unittest.TestCase):
    def test_clusters_split_by_link_distance_largest_first(self):
        near = rows(grid(0.9, 0.2, 0.6, -2.5, -2.0, 5), 0)
        far = rows(grid(0.9, 0.2, 0.3, 2.0, 2.1, 3), 0)
        groups = mv.clusters(near + far)
        self.assertEqual([len(g) for g in groups], [25, 9])

    def test_side_mark_runs_through_the_width_and_roof_mark_through_the_height(self):
        side = mv.face_boxes(rows(grid(0.9, 0.2, 0.6, -2.5, -2.0), 0), BOX)
        self.assertEqual(side, [[[-1.0, 0.2, -2.5], [1.0, 0.6, -2.0]]])
        roof = [(p, 1) for p in ((x / 10, 0.95, z / 10) for x in range(4) for z in range(4))]
        self.assertEqual(mv.face_boxes(roof, BOX), [[[0.0, 0.0, 0.0], [0.3, 1.0, 0.3]]])

    def test_front_and_rear_marks_go_half_a_metre_inward(self):
        rear = [((x / 10, y / 10, -2.9), 2) for x in range(4) for y in range(4)]
        self.assertEqual(mv.face_boxes(rear, BOX), [[[0.0, 0.0, -2.9], [0.3, 0.3, -2.4]]])
        front = [((x / 10, y / 10, 2.9), 2) for x in range(4) for y in range(4)]
        self.assertEqual(mv.face_boxes(front, BOX), [[[0.0, 0.0, 2.4], [0.3, 0.3, 2.9]]])

    def test_a_face_with_too_few_points_makes_no_box(self):
        self.assertEqual(mv.face_boxes(rows(grid(0.9, 0.2, 0.6, 0, 1, 2), 0), BOX), [])

    def test_boxes_stay_inside_the_component(self):
        front = [((x / 10, y / 10, 2.9), 2) for x in range(4) for y in range(4)]
        narrow = [[-1.0, 0.0, 2.7], [1.0, 1.0, 3.0]]
        self.assertEqual(mv.face_boxes(front, narrow)[0][0][2], 2.7)

    def test_icons_of_one_seat_on_both_sides_are_one_crew_member(self):
        left = [[[-1.0, 0.3, -1.0], [1.0, 0.8, -0.3]]]
        right = [[[-1.0, 0.35, -0.9], [1.0, 0.75, -0.4]]]
        other = [[[-1.0, 0.3, 0.5], [1.0, 0.8, 1.0]]]
        merged = mv.merge_seats([left, right, other])
        self.assertEqual([len(m) for m in merged], [2, 1])


if __name__ == '__main__':
    unittest.main()
