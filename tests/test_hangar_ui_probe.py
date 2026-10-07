"""Pure observer/deadline bounds only; no fake native UI compatibility claim."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1] / 'client_patch/hangar_ui_probe.py'
SPEC = importlib.util.spec_from_file_location('hangar_ui_probe', SOURCE)
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)


def data():
    return {'achievementsList': [[] for _ in range(7)],
            'totalItemsList': [0] * 7, 'battlesCount': 0}


def award(**values):
    result = {'value': 0, 'isInDossier': False, 'isDone': False, 'isRare': False}
    result.update(values)
    return result


class AwardsSummaryTests(unittest.TestCase):
    def test_empty_catalogue_has_seven_explicit_sections(self):
        result = PROBE.summarize_awards_data(data())
        self.assertEqual((0, 7, 0, 0), (result['battles_count'], result['section_count'],
                                      result['packed_items'], result['catalog_items']))
        self.assertLess(len(json.dumps(result)), 4096)

    def test_catalogue_and_native_no_level_sentinel_are_not_earned_awards(self):
        source = data()
        source['achievementsList'][0] = [award(value=5), award()]
        source['totalItemsList'][0] = 3  # A real filter can omit an item.
        before = json.dumps(source, sort_keys=True)
        result = PROBE.summarize_awards_data(source)
        self.assertEqual((2, 3, 1, 0, 0), tuple(result[k] for k in
                         ('packed_items', 'catalog_items', 'nonzero_value_items',
                          'done_items', 'in_dossier_items')))
        self.assertEqual(before, json.dumps(source, sort_keys=True))

    def test_observed_nonzero_statistics_are_not_replaced_with_zeros(self):
        source = data()
        source['battlesCount'] = 12
        source['achievementsList'][4] = [award(value=2, isDone=True, isInDossier=True, isRare=True)]
        source['totalItemsList'][4] = 1
        result = PROBE.summarize_awards_data(source)
        self.assertEqual((12, 1, 1, 1), tuple(result[k] for k in
                         ('battles_count', 'in_dossier_items', 'done_items', 'rare_items')))

    def test_dossier_and_tooltip_payloads_are_never_traversed_or_formatted(self):
        class NeverRead:
            def __iter__(self):
                raise AssertionError('recursive GUI traversal')

            def __repr__(self):
                raise AssertionError('GUI payload formatted')

        source = data()
        item = award(description=NeverRead(), dossierCompDescr=NeverRead(), icon=NeverRead())
        item['cycle'] = item
        source['achievementsList'][0] = [item]
        source['totalItemsList'][0] = 1
        self.assertEqual(1, PROBE.summarize_awards_data(source)['packed_items'])

    def test_wrong_section_count_and_inconsistent_totals_are_rejected(self):
        source = data()
        source['achievementsList'].pop()
        with self.assertRaises(ValueError):
            PROBE.summarize_awards_data(source)
        source = data()
        source['achievementsList'][0] = [award()]
        with self.assertRaises(ValueError):
            PROBE.summarize_awards_data(source)

    def test_boolean_numeric_fields_and_nonfinite_values_are_rejected(self):
        for value in (True, None, '0', float('nan'), float('inf'), 2**54):
            source = data()
            source['achievementsList'][0] = [award(value=value)]
            source['totalItemsList'][0] = 1
            with self.subTest(value=value), self.assertRaises(ValueError):
                PROBE.summarize_awards_data(source)
        for key, value in (('battlesCount', True), ('totalItemsList', [False] * 7)):
            source = data()
            source[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                PROBE.summarize_awards_data(source)

    def test_section_total_and_scalar_container_bounds(self):
        source = data()
        source['achievementsList'][0] = [award()] * 257
        source['totalItemsList'][0] = 257
        with self.assertRaises(ValueError):
            PROBE.summarize_awards_data(source)
        source = data()
        source['totalItemsList'] = [256] * 7
        with self.assertRaises(ValueError):
            PROBE.summarize_awards_data(source)
        source = data()
        source['achievementsList'][0] = [award(isDone=1)]
        source['totalItemsList'][0] = 1
        with self.assertRaises(ValueError):
            PROBE.summarize_awards_data(source)


class DeadlineTests(unittest.TestCase):
    def test_initial_hangar_cannot_transition_early(self):
        window = PROBE.StableWindow(10, 67, 62)
        self.assertFalse(window.observe(10, True))
        self.assertFalse(window.observe(71.999, True))
        self.assertTrue(window.observe(72, True))

    def test_stability_requires_continuous_readiness(self):
        window = PROBE.StableWindow(0, 20, 2)
        self.assertFalse(window.observe(1, True))
        self.assertFalse(window.observe(2, False))
        self.assertFalse(window.observe(2.5, True))
        self.assertFalse(window.observe(4, True))
        self.assertTrue(window.observe(4.5, True))

    def test_deadline_cannot_be_extended_by_loading_or_late_success(self):
        for ready in (False, True):
            window = PROBE.StableWindow(0, 20, 2)
            window.observe(0, True)
            with self.assertRaises(RuntimeError):
                window.observe(20, ready)

    def test_backwards_or_nonfinite_clock_is_rejected(self):
        for now in (9.9, float('nan'), float('inf')):
            window = PROBE.StableWindow(10, 20, 2)
            with self.subTest(now=now), self.assertRaises(ValueError):
                window.observe(now, True)


class VehicleExportBoundsTests(unittest.TestCase):
    def test_unrequested_vehicle_is_rejected_before_native_import(self):
        with self.assertRaises(ValueError):
            PROBE.export_original_vehicle('ussr:MS-1', None, '.')

    def test_unbounded_or_arbitrary_vehicle_shape_is_rejected(self):
        for payload in (None, [], {}, {'type_name': 'ussr:IS-7', 'arbitrary': []}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                PROBE._bounded_vehicle_export(payload, '00', '00')

    def test_existing_evidence_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'original-vehicle-is7.json'
            result = PROBE._write_vehicle_export(str(path), {'bound_test_only': True})
            before = path.read_bytes()
            self.assertEqual(result['bytes'], len(before))
            with self.assertRaises(OSError):
                PROBE._write_vehicle_export(str(path), {'replaced': True})
            self.assertEqual(before, path.read_bytes())

    def test_oversized_export_is_refused_before_file_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'original-vehicle-is7.json'
            with self.assertRaises(ValueError):
                PROBE._write_vehicle_export(str(path), {'too_large': 'x' * PROBE.VEHICLE_EXPORT_MAX_BYTES})
            self.assertFalse(path.exists())


if __name__ == '__main__':
    unittest.main()
