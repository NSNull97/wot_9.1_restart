"""Synthetic parser/provenance negatives, not a substitute for native traces."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools import client_marker_oracle as tool


def synthetic_event():
    row = {"event": tool.EVENT, "schema": 1, "status": "PASS_NATIVE_CALLS",
           "method_code_sha256": tool.METHOD_SHA, "method_filename": tool.METHOD_FILE,
           "method_firstlineno": 2772, "source": tool.METHOD_SOURCE,
           "observer_mutated_gameplay": False, "server_penetration_verdict": False,
           "own_position_before": [0.0, 0.0, 0.0], "own_position_after": [0.0, 0.0, 0.0],
           "selected_shot_before": copy.deepcopy(tool.PROFILE), "selected_shot_after": copy.deepcopy(tool.PROFILE),
           "samples": []}
    cases = [(d, a, None) for d in tool.DISTANCES for a in (0.0, 8.0, 16.0, 18.0)]
    cases += [(d, None, ratio) for d in (100.0, 300.0, 500.0, 719.99) for ratio in tool.THRESHOLDS]
    for index, (distance, armor, threshold) in enumerate(cases):
        if threshold is not None:
            armor = tool.nominal_power(distance) * threshold / 100.0
        row["samples"].append({"case_id": index, "requested_distance": distance, "measured_distance": distance,
            "hit_point": [distance, 0.0, 0.0], "armor": armor, "threshold_input_ratio": threshold,
            "callback": {"name": "Crosshair.setMarkerType", "args": [tool.expected_label(distance, armor)]}})
    return row


class ClientMarkerOracleTests(unittest.TestCase):
    def assert_bad(self, mutate, pattern):
        row = synthetic_event()
        mutate(row)
        with self.assertRaisesRegex(tool.AuditError, pattern):
            tool.validate_event(row, "a")

    def test_explicit_original_formula_boundaries(self):
        self.assertEqual([tool.nominal_power(d) for d in (0, 100, 300, 500, 600, 720)],
                         [34, 34, 30.5, 27, 25.25, 0])
        self.assertAlmostEqual(tool.nominal_power(719.99), 23.150175)
        self.assertEqual(tool.expected_label(100.0, 30.6), "great_pierced")
        self.assertEqual(tool.expected_label(100.0, 30.7), "little_pierced")
        self.assertEqual(tool.expected_label(100.0, 51.0), "not_pierced")
        self.assertEqual(tool.expected_label(720.0, 0.0), "not_pierced")

    def test_synthetic_fixture_is_bounded_and_omits_raw_coordinates(self):
        result = tool.validate_event(synthetic_event(), "a")
        self.assertEqual(len(result), 60)
        self.assertEqual(set(result[0]), {"client", "case_id", "distance", "armor", "label",
                                          "distance_bits", "armor_bits"})
        self.assertEqual(result[0]["distance_bits"], "0000000000000000")
        self.assertEqual(result[1]["armor_bits"], "4020000000000000")  # original input 8.0
        self.assertEqual(result[4]["distance_bits"], "4059000000000000")  # original input 100.0
        for sample in result:
            self.assertRegex(sample["distance_bits"], r"^[0-9a-f]{16}$")
            self.assertRegex(sample["armor_bits"], r"^[0-9a-f]{16}$")

    def test_drift_and_wrong_profile_are_rejected(self):
        self.assert_bad(lambda r: r["own_position_after"].__setitem__(0, 0.001), "drift")
        self.assert_bad(lambda r: r["selected_shot_after"].__setitem__("shell_compact_descriptor", 2571), "profile")
        self.assert_bad(lambda r: r["selected_shot_before"].__setitem__("piercing_power", [34, 28]), "profile")
        self.assert_bad(lambda r: r["selected_shot_before"].__setitem__("damage_randomization", False), "numeric")

    def test_method_and_authority_provenance_rejected(self):
        for key, value in (("method_code_sha256", "0" * 64), ("method_firstlineno", 2773),
                           ("method_filename", "replacement.py"), ("source", "translated predictor")):
            self.assert_bad(lambda r, k=key, v=value: r.__setitem__(k, v), "provenance")
        self.assert_bad(lambda r: r.__setitem__("observer_mutated_gameplay", 0), "boundary")
        self.assert_bad(lambda r: r.__setitem__("server_penetration_verdict", True), "boundary")
        self.assert_bad(lambda r: r.__setitem__("status", "FAIL"), "did not pass")
        self.assert_bad(lambda r: r.__setitem__("error", "observer failure"), "did not pass")

    def test_callback_label_mismatch_is_not_rewritten_to_expected(self):
        self.assert_bad(lambda r: r["samples"][0]["callback"].__setitem__("args", ["not_pierced"]), "formula")
        self.assert_bad(lambda r: r["samples"][0]["callback"].__setitem__("name", "Other.call"), "callback")
        self.assert_bad(lambda r: r["samples"][0]["callback"].__setitem__("args", []), "callback")

    def test_case_count_order_ray_and_input_boundaries_rejected(self):
        self.assert_bad(lambda r: r["samples"].pop(), "60")
        self.assert_bad(lambda r: r["samples"][1].__setitem__("case_id", 0), "case id")
        self.assert_bad(lambda r: r["samples"][0].__setitem__("armor", -1), "numeric")
        self.assert_bad(lambda r: r["samples"][0].__setitem__("armor", 10 ** 500), "numeric")
        self.assert_bad(lambda r: r["samples"][0].__setitem__("measured_distance", float("nan")), "numeric")
        self.assert_bad(lambda r: r["samples"][0]["hit_point"].__setitem__(1, 1), "ray")
        self.assert_bad(lambda r: r["samples"][0].__setitem__("requested_distance", 10), "requested")
        self.assert_bad(lambda r: r["samples"][36].__setitem__("armor", 30), "threshold")

    def test_duplicate_keys_nonfinite_truncated_depth_and_line_bounds(self):
        for data, pattern in ((b'{"event":1,"event":2}', "duplicate"), (b'{"v":NaN}', "non-finite"),
                              (b'{"v":1e999}', "non-finite"), (b'{"v":', "malformed"),
                              (b'[]', "object"), (b'\xff', "UTF-8"),
                              (("[" * 18 + "0" + "]" * 18).encode(), "depth")):
            with self.assertRaisesRegex(tool.AuditError, pattern):
                tool.parse_line(data)
        with self.assertRaisesRegex(tool.AuditError, "line size"):
            tool.parse_line(b" " * (tool.MAX_LINE_BYTES + 1))

    def _trace(self, directory, pid, extra=()):
        path = Path(directory) / ("native-%d-123456.jsonl" % pid)
        rows = [{"event": "init", "pid": pid}, synthetic_event(), *extra]
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        return path

    def test_two_trace_identity_and_append_only_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            a, b = self._trace(directory, 11), self._trace(directory, 12)
            report, fixture = tool.audit(a, b)
            self.assertEqual(len(fixture["samples"]), 120)
            self.assertEqual(report["owner_acceptance"], "NOT_RUN")
            target = Path(directory) / "fresh"
            tool.write_outputs(target, report, fixture)
            self.assertEqual(json.loads((target / "fixture.json").read_text())["samples"], fixture["samples"])
            with self.assertRaisesRegex(tool.AuditError, "fresh"):
                tool.write_outputs(target, report, fixture)
            with self.assertRaisesRegex(tool.AuditError, "distinct trace paths"):
                tool.audit(a, a)
            b.write_bytes(a.read_bytes())
            with self.assertRaisesRegex(tool.AuditError, "pid mismatch"):
                tool.audit(a, b)

    def test_duplicate_event_observer_error_pid_drift_and_size_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            for extra, pattern in (([synthetic_event()], "one oracle"),
                                   ([{"event": "shared_collision_oracle_failed"}], "observer failure"),
                                   ([{"event": "other", "pid": 999}], "pid drift")):
                path = self._trace(directory, 11, extra)
                with self.assertRaisesRegex(tool.AuditError, pattern):
                    tool.read_trace(path, "a")
            path = self._trace(directory, 11)
            with mock.patch.object(tool, "MAX_TRACE_BYTES", 100):
                with self.assertRaisesRegex(tool.AuditError, "size bound"):
                    tool.read_trace(path, "a")

    def test_missing_event_same_pid_different_paths_and_copied_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            a = self._trace(directory, 11)
            b = Path(directory) / "second.jsonl"
            b.write_bytes(a.read_bytes())
            with self.assertRaisesRegex(tool.AuditError, "duplicate trace contents"):
                tool.audit(a, b)
            b.write_bytes(a.read_bytes() + b'{"event":"other"}\n')
            with self.assertRaisesRegex(tool.AuditError, "distinct client pids"):
                tool.audit(a, b)
            b.write_bytes(b'{"event":"other"}\n')
            with self.assertRaisesRegex(tool.AuditError, "one oracle"):
                tool.read_trace(b, "b")

    def test_two_different_traces_without_resolved_pids_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            a, b = Path(directory) / "first.jsonl", Path(directory) / "second.jsonl"
            event = json.dumps(synthetic_event()).encode("utf-8") + b"\n"
            a.write_bytes(event)
            b.write_bytes(event + b'{"event":"other"}\n')
            with self.assertRaisesRegex(tool.AuditError, "both client pids must be resolved"):
                tool.audit(a, b)
            known = self._trace(directory, 11)
            with self.assertRaisesRegex(tool.AuditError, "both client pids must be resolved"):
                tool.audit(known, b)


if __name__ == "__main__":
    unittest.main()
