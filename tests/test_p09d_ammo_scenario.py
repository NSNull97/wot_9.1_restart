"""Synthetic state-machine regression only; not native acceptance evidence."""
import copy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'client_patch'))
import p09d_ammo_scenario as S


def expected():
    return {'version': 1, 'database_id': 1, 'source_revision': 7, 'initial': [
        {'vehicle_id': 1, 'loaded': [42, 36, 18], 'depot': [78, 64, 82]},
        {'vehicle_id': 2, 'loaded': [21, 9, 0], 'depot': [79, 91, 100]}]}


def snapshot(vehicle, counts, depot):
    cd = (3329, 7169)[vehicle - 1]
    turret, gun, capacity, shells = S.ui.MOUNTS[cd]
    flat = [v for pair in zip(shells, counts) for v in pair]
    return {'supported': True, 'mount': {'vehicle_type_cd': cd, 'inventory_id': vehicle, 'turret_cd': turret,
            'gun_cd': gun, 'capacity': capacity, 'compatible_shells': list(shells)},
            'loaded': list(flat), 'layout': list(flat), 'depot': [[cd, n] for cd, n in zip(shells, depot)],
            'gui_shells': [{'shell_cd': cd, 'count': n, 'default_count': n, 'inventory_count': d}
                           for cd, n, d in zip(shells, counts, depot)]}


class FakeNative:
    def __init__(self):
        self.selected, self.view, self.scenario = 1, None, None
        self.counts = [list(v) for v in S.INITIAL]
        self.depots = [v['depot'][:] for v in expected()['initial']]
        self.actions, self.requests = [], []
        self.allow_png, self.allow_service, self.allow_render = True, True, True
        self.account = {'database_id': 1, 'resources': [100000, 0, 0], 'crew_dossier': 'unchanged'}
        self.revision = 1

    def state(self):
        return {'account': copy.deepcopy(self.account), 'selected_inventory_id': self.selected}

    def snapshot(self):
        return snapshot(self.selected, self.counts[self.selected - 1], self.depots[self.selected - 1])

    def select(self, vehicle):
        self.actions.append(('select', vehicle)); self.selected = vehicle

    def window(self):
        return self.view

    def open(self):
        self.view = object()
        if not self.allow_render:
            return
        values = self.snapshot()
        self.scenario.native_event({'method': 'as_setDataS', 'phase': 'return', 'owner_id': id(self.view),
            'flash_bound': True, 'capacity': values['mount']['capacity'], 'shells': [
                {'compactDescr': v['shell_cd'], 'count': v['count'], 'userCount': v['count'], 'inventoryCount': v['inventory_count']}
                for v in values['gui_shells']]})

    def close(self):
        self.view = None

    def request(self, name):
        self.requests.append(name)

    def screenshot(self, name):
        return {'basename': name, 'png_container_valid': True, 'unit_only': True} if self.allow_png else None

    def fill(self, vehicle, counts):
        self.actions.append(('fill', vehicle, list(counts)))
        if not self.allow_service:
            return
        shells = S.ui.MOUNTS[(3329, 7169)[vehicle - 1]][3]
        arr = [3, vehicle, 6] + [v for p in zip(shells, counts) for v in p] + [6, 0, 0, 0, 0, 0, 0]
        event = self.scenario.native_event
        event({'method':'__setAndFillLayouts_onShopSynced', 'phase':'return', 'arguments':arr})
        self.depots[vehicle - 1] = [d + a - b for d, a, b in zip(self.depots[vehicle - 1], self.counts[vehicle - 1], counts)]
        self.counts[vehicle - 1] = list(counts)
        event({'method':'_update', 'phase':'return', 'has_inventory':True, 'previous_revision':self.revision,
               'revision':self.revision + 1, 'snapshot':self.snapshot()})
        self.revision += 1
        event({'method':'onCmdResponseExt', 'phase':'call', 'requestID':200 + self.revision, 'resultID':0})
        event({'method':'_successHandler', 'phase':'return', 'code':0})
        event({'method':'onCmdResponseExt', 'phase':'return', 'requestID':200 + self.revision, 'resultID':0})
        self.view = None


class ScenarioTests(unittest.TestCase):
    def setUp(self):
        self.saved = (S._expected, S._scenario)
        S._expected, S._scenario = None, None
        S.arm(expected())
        self.native, self.events, self.time = FakeNative(), [], 0.0
        self.scenario = S._Scenario({'enable_p09d_ammo_service': True},
                                   lambda e, **f: self.events.append((e, f)), self.native, lambda: self.time)
        self.native.scenario = self.scenario

    def tearDown(self):
        S._expected, S._scenario = self.saved

    def tick(self, ready=True):
        self.time += 1.0
        return self.scenario.advance({'vehicle_model_loaded': True}, ready)

    def run_until(self, phase):
        for _ in range(150):
            if self.scenario.phase == phase:
                return
            self.tick()
        self.fail('phase never reached')

    def test_exact_seven_stages_six_original_requests_and_restoration(self):
        for _ in range(150):
            if self.tick():
                break
        self.assertTrue(self.scenario.completed)
        self.assertEqual([r for r in self.native.actions if r[0] == 'fill'],
                         [('fill', v, list(c)) for v, c, _ in S.OPERATIONS])
        self.assertEqual(self.native.counts, [list(v) for v in S.INITIAL])
        self.assertEqual(self.native.depots, [v['depot'] for v in expected()['initial']])
        self.assertEqual(set(self.native.requests), set(S.SCREENSHOTS))
        self.assertEqual(len(self.native.requests), 12)
        self.assertTrue(self.events[-1][1]['restored_initial_state'])
        self.assertFalse(self.events[-1][1]['computer_input'])

    def test_missing_native_service_result_times_out_without_next_mutation(self):
        self.native.allow_service = False
        self.run_until('wait_service')
        with self.assertRaisesRegex(RuntimeError, 'timed out'):
            for _ in range(32): self.tick()
        self.assertEqual(len([r for r in self.native.actions if r[0] == 'fill']), 1)
        self.assertFalse(self.scenario.completed)

    def test_no_render_no_mutation(self):
        self.native.allow_render = False
        self.run_until('render_operation')
        with self.assertRaisesRegex(RuntimeError, 'timed out'):
            for _ in range(32): self.tick()
        self.assertFalse(any(r[0] == 'fill' for r in self.native.actions))

    def test_png_timeout_and_login_timeout_are_failures(self):
        self.native.allow_png = False
        self.run_until('wait_png')
        with self.assertRaisesRegex(RuntimeError, 'timed out'):
            for _ in range(32): self.tick()

    def test_account_or_initial_ammo_change_is_not_accepted(self):
        self.tick(); self.native.counts[0][0] += 1
        with self.assertRaises(ValueError): self.tick()

    def test_native_success_without_update_and_rejected_processor_fail(self):
        self.native.allow_service = False
        self.run_until('wait_service')
        self.scenario.native_event({'method':'_successHandler', 'phase':'return', 'code':0})
        with self.assertRaisesRegex(RuntimeError, 'preceding actual update'): self.tick()

    def test_unrelated_refresh_cannot_replace_completed_service_identity(self):
        self.run_until('wait_service')
        self.assertTrue(self.scenario.pending['complete'])
        before = copy.deepcopy(self.scenario.pending)
        self.scenario.native_event({'method':'onCmdResponseExt', 'phase':'call', 'requestID':999, 'resultID':0})
        self.scenario.native_event({'method':'onCmdResponseExt', 'phase':'return', 'requestID':999, 'resultID':0})
        self.assertEqual(self.scenario.pending, before)
        self.assertIsNone(self.scenario.error)

    def test_schema_is_exact_and_owned_stock_bounded(self):
        for mutate in (lambda e: e.update(extra=True), lambda e: e.update(source_revision=8),
                       lambda e: e['initial'][0]['loaded'].__setitem__(0, True),
                       lambda e: e['initial'][0].update(depot=[0, 0, 0])):
            value = expected(); mutate(value)
            with self.assertRaises(ValueError): S.checked_expected(value)

    def test_disabled_feature_and_double_arm_rejected(self):
        with self.assertRaises(RuntimeError): S._Scenario({}, lambda *a, **k: None, self.native)
        with self.assertRaises(RuntimeError): S.arm(expected())

    def test_nonfinite_or_backward_clock_rejected(self):
        self.tick(); self.time = -1
        with self.assertRaises(ValueError): self.tick()


if __name__ == '__main__':
    unittest.main()
