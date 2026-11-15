import unittest

from tools.malinovka_bush_audit import selected_row


class MalinovkaBushAuditTests(unittest.TestCase):
    def test_selected_origin_uses_chunk_transform_and_excludes_tree(self):
        matrix = [1, 0, 0, 0, 1, 0, 0, 0, 1, 3, 4, 5]
        fields = {"/spt[1]": "speedtree/02_Malinovka/Bush.spt", "/seed[1]": 1,
                  "/transform[1]": matrix}
        row = selected_row((-2, 3), 7, fields)
        self.assertEqual(row["world_origin"], [-197, 4, 305])
        self.assertEqual(row["speedtree_index"], 7)
        fields["/spt[1]"] = "speedtree/02_Malinovka/Spruce.spt"
        self.assertIsNone(selected_row((-2, 3), 7, fields))

    def test_invalid_selected_transform_fails(self):
        fields = {"/spt[1]": "speedtree/02_Malinovka/Bush.spt", "/seed[1]": 1,
                  "/transform[1]": [float("nan")] * 12}
        with self.assertRaises(ValueError):
            selected_row((0, 0), 1, fields)


if __name__ == "__main__":
    unittest.main()
