"""Planning arithmetic only. These tests do not measure a game server."""
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import capacity_estimate as capacity


class CapacityArithmeticTests(unittest.TestCase):
    def test_full_and_underfilled_rooms_are_separate(self):
        for share, full, planned in [('0.5', 17, 23), ('0.7', 24, 32), ('1', 34, 44)]:
            with self.subTest(share=share):
                result = capacity.estimate(battle_share=share)
                self.assertEqual(result['rooms']['minimum_full_rooms'], full)
                self.assertEqual(result['rooms']['budgeted_worker_processes'], planned)

    def test_target_five_hosts_is_conditional_arithmetic(self):
        result = capacity.estimate()
        self.assertEqual(result['status'], 'ESTIMATE_ONLY')
        self.assertEqual(result['per_host']['cpu_core_budget'], 8.4)
        self.assertEqual(result['per_host']['whole_room_limits'], {'cpu': 28, 'ram': 44, 'network': 266})
        self.assertEqual(result['fleet']['battle_hosts_minimum'], 2)
        self.assertEqual(result['fleet']['battle_hosts_n_plus_one'], 3)
        self.assertEqual(result['fleet']['total_hosts_with_battle_n_plus_one'], 5)
        self.assertEqual(result['per_room']['p99_wall_deadline_status'], 'NOT_RUN')

    def test_heavy_all_in_battle_seven_hosts(self):
        result = capacity.estimate(battle_share=1, tick_cpu_ms=20)
        self.assertEqual(result['rooms']['budgeted_worker_processes'], 44)
        self.assertEqual(result['per_host']['whole_rooms'], 14)
        self.assertEqual(result['fleet']['battle_hosts_minimum'], 4)
        self.assertEqual(result['fleet']['total_hosts_with_battle_n_plus_one'], 7)

    def test_lean_three_hosts_has_no_promised_battle_spare(self):
        result = capacity.estimate(service_hosts=1)
        self.assertEqual(result['fleet']['total_hosts_without_battle_spare'], 3)
        self.assertLess(result['per_host']['whole_rooms'], result['rooms']['budgeted_worker_processes'])

    def test_integer_packing_cannot_pool_unusable_core_fragments(self):
        # Three 0.6-core rooms, 1 usable core/host: ceil(total)=2 is wrong.
        result = capacity.estimate(ccu=90, battle_share=1, occupancy=1, transition_rooms=0,
                                   host_cores=1, reserved_cores=0, cpu_target=1, tick_cpu_ms=20)
        self.assertEqual(result['fleet']['cpu_core_equivalents_reserved'], 1.8)
        self.assertEqual(result['per_host']['whole_rooms'], 1)
        self.assertEqual(result['fleet']['battle_hosts_minimum'], 3)
        self.assertEqual(result['fleet']['battle_hosts_n_plus_one'], 4)

    def test_ram_can_dominate_cpu(self):
        result = capacity.estimate(tick_cpu_ms=5, worker_ram_gib=4)
        self.assertEqual(result['per_host']['whole_rooms'], 11)
        self.assertEqual(result['per_host']['limiting_resources'], ['ram'])

    def test_network_can_dominate_cpu(self):
        result = capacity.estimate(host_link_mbps=10)
        self.assertEqual(result['per_host']['whole_rooms'], 2)
        self.assertEqual(result['per_host']['limiting_resources'], ['network'])

    def test_n_plus_one_surviving_capacity_and_minimality(self):
        for share in ('0.5', '0.7', '1'):
            for milliseconds in (5, 10, 20):
                result = capacity.estimate(battle_share=share, tick_cpu_ms=milliseconds)
                rooms, k = result['rooms']['budgeted_worker_processes'], result['per_host']['whole_rooms']
                hosts = result['fleet']['battle_hosts_n_plus_one']
                self.assertGreaterEqual((hosts - 1) * k, rooms)
                self.assertLess((hosts - 2) * k, rooms)

    def test_zero_demand_and_zero_warm_rooms_do_not_create_spare(self):
        result = capacity.estimate(ccu=0, transition_rooms=0, service_hosts=0)
        self.assertEqual(result['fleet']['battle_hosts_n_plus_one'], 0)
        self.assertEqual(result['network']['decimal_TB_at_constant_stated_ccu'], 0)

    def test_unschedulable_is_explicit_not_division_by_zero(self):
        result = capacity.estimate(worker_ram_gib=100)
        self.assertFalse(result['fleet']['arithmetically_schedulable'])
        self.assertIsNone(result['fleet']['battle_hosts_n_plus_one'])
        self.assertEqual(result['status'], 'ESTIMATE_ONLY')

    def test_decimal_network_units(self):
        result = capacity.estimate(battle_share=1, battle_egress_kbps=50)['network']
        self.assertEqual(result['application_egress_mbps_at_stated_ccu'], 50)
        self.assertEqual(result['wire_egress_mbps_at_stated_ccu'], 62.5)
        self.assertEqual(result['wire_egress_decimal_MB_per_second'], 7.8125)
        self.assertEqual(result['minimum_aggregate_link_mbps_at_target'], 125)
        self.assertEqual(result['decimal_TB_at_constant_stated_ccu'], 20.25)

    def test_mean_ccu_changes_traffic_not_peak_host_count(self):
        base = capacity.estimate(battle_share=1)
        lower = capacity.estimate(battle_share=1, mean_ccu_fraction='.25')
        self.assertEqual(base['fleet'], lower['fleet'])
        self.assertEqual(lower['network']['decimal_TB_at_assumed_mean_ccu'], 5.0625)
        self.assertEqual(lower['network']['mean_ccu_for_traffic'], 250)

    def test_lobby_mix_is_not_counted_as_combat_traffic(self):
        network = capacity.estimate()['network']
        self.assertEqual(network['application_egress_mbps_at_stated_ccu'], 35.6)
        self.assertEqual(network['wire_egress_mbps_at_stated_ccu'], 44.5)
        self.assertEqual(network['decimal_TB_at_constant_stated_ccu'], 14.418)

    def test_serial_tick_limit_is_distinct_from_capacity(self):
        result = capacity.estimate(tick_hz=60, tick_cpu_ms=20)
        self.assertFalse(result['per_room']['serial_mean_within_deadline'])
        self.assertTrue(result['fleet']['arithmetically_schedulable'])
        self.assertTrue(any('more hosts do not fix' in text for text in result['warnings']))

    def test_decimal_edge_does_not_add_phantom_room(self):
        result = capacity.estimate(ccu=100, battle_share='.3', occupancy=1, transition_rooms=0)
        self.assertEqual(result['rooms']['budgeted_worker_processes'], 1)

    def test_cost_and_headroom_monotonicity(self):
        base = capacity.estimate()['fleet']['battle_hosts_n_plus_one']
        self.assertGreaterEqual(capacity.estimate(tick_cpu_ms=20)['fleet']['battle_hosts_n_plus_one'], base)
        self.assertGreaterEqual(capacity.estimate(cpu_target='.3')['fleet']['battle_hosts_n_plus_one'], base)

    def test_bad_inputs_fail_without_calculation(self):
        bad = [
            {'ccu': True}, {'ccu': -1}, {'ccu': '1.5'}, {'ccu': 1000001},
            {'tick_cpu_ms': float('nan')}, {'tick_cpu_ms': float('inf')},
            {'tick_cpu_ms': '1e-999999'}, {'tick_cpu_ms': '1e999999'},
            {'tick_cpu_ms': 0}, {'occupancy': 0}, {'occupancy': '1.01'},
            {'battle_share': 2}, {'cpu_target': 0}, {'ram_target': 2},
            {'net_target': 0}, {'worker_ram_gib': 0}, {'transport_factor': '.9'},
            {'reserved_cores': 16}, {'reserved_ram_gib': 64},
            {'days': 0}, {'mean_ccu_fraction': -1}, {'ccu': []}, {'extra': 1},
        ]
        for values in bad:
            with self.subTest(values=values), self.assertRaises(ValueError):
                capacity.estimate(**values)

    def test_cli_json_and_matrix_no_silent_override(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(capacity.main(['--battle-share', '1', '--tick-cpu-ms', '20']), 0)
        self.assertEqual(json.loads(output.getvalue())['fleet']['total_hosts_with_battle_n_plus_one'], 7)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            capacity.main(['--matrix', '--ccu', '5'])
        self.assertEqual(caught.exception.code, 2)

    def test_matrix_is_assumptions_and_known_traffic_points(self):
        grid = capacity.matrix()
        self.assertEqual(grid['status'], 'ESTIMATE_ONLY')
        self.assertEqual(len(grid['cpu_sensitivity']), 9)
        self.assertEqual([row['decimal_TB_at_constant_stated_ccu'] for row in grid['all_players_in_battle_network']], [8.1, 20.25, 40.5])


if __name__ == '__main__':
    unittest.main()
