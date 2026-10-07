"""Arithmetic planning model; does not benchmark or configure any server.

All CPU, memory and traffic costs below are assumptions until measured with
representative native battles. Integer room packing and decimal units are
calculated exactly with Fraction; rounded JSON values are for display only.
"""
import argparse
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import json
import re


DEFAULTS = {
    'ccu': 1000, 'battle_share': '0.7', 'slots': 30, 'occupancy': '0.8',
    'transition_rooms': 2, 'tick_hz': 30, 'tick_cpu_ms': 10,
    'worker_ram_gib': 1, 'host_cores': 16, 'reserved_cores': 2,
    'cpu_target': '0.6', 'host_ram_gib': 64, 'reserved_ram_gib': 8,
    'ram_target': '0.8', 'host_link_mbps': 1000, 'net_target': '0.5',
    'battle_egress_kbps': 50, 'lobby_egress_kbps': 2,
    'transport_factor': '1.25', 'service_hosts': 2,
    'days': 30, 'mean_ccu_fraction': 1,
}
INTEGER_FIELDS = {
    'ccu', 'slots', 'transition_rooms', 'host_cores', 'reserved_cores',
    'service_hosts',
}
ZERO_ALLOWED = {
    'ccu', 'battle_share', 'transition_rooms', 'reserved_cores',
    'reserved_ram_gib', 'service_hosts', 'lobby_egress_kbps',
    'mean_ccu_fraction',
}
FRACTION_FIELDS = {
    'battle_share', 'occupancy', 'cpu_target', 'ram_target', 'net_target',
    'mean_ccu_fraction',
}


def _number(name, value):
    if type(value) not in (int, float, str):
        raise ValueError('%s must be a finite decimal, not bool/object' % name)
    raw = str(value)
    if len(raw) > 32 or not re.fullmatch(
            r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', raw):
        raise ValueError('%s has invalid decimal syntax' % name)
    try:
        decimal = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError('%s has invalid decimal syntax' % name) from exc
    # Bound the exponent before constructing Fraction (including tiny input).
    if not decimal.is_finite() or abs(decimal.as_tuple().exponent) > 18:
        raise ValueError('%s exceeds decimal precision bounds' % name)
    if decimal < 0 or decimal > 1000000:
        raise ValueError('%s outside [0,1000000]' % name)
    result = Fraction(decimal)
    if result == 0 and name not in ZERO_ALLOWED:
        raise ValueError('%s must be positive' % name)
    if name in FRACTION_FIELDS and result > 1:
        raise ValueError('%s must be <= 1' % name)
    if name in INTEGER_FIELDS and result.denominator != 1:
        raise ValueError('%s must be an integer' % name)
    return result


def _ceil(value):
    return -(-value.numerator // value.denominator)


def _floor(value):
    return value.numerator // value.denominator


def _display(value):
    if isinstance(value, Fraction):
        return int(value) if value.denominator == 1 else round(float(value), 9)
    if isinstance(value, dict):
        return {key: _display(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_display(item) for item in value]
    return value


def estimate(**overrides):
    """Return a serializable estimate. No files, network, processes or DB I/O.

    A worker's CPU cost is total CPU-ms (summed over its threads) per complete
    logic step, including physics and amortized replication. It is NOT p99
    wall time. Every reserved room conservatively gets a full-room budget.
    """
    unknown = set(overrides) - set(DEFAULTS)
    if unknown:
        raise ValueError('unknown assumptions: %s' % ','.join(sorted(unknown)))
    values = dict(DEFAULTS, **overrides)
    a = {key: _number(key, value) for key, value in values.items()}
    if a['reserved_cores'] >= a['host_cores']:
        raise ValueError('reserved_cores must leave usable physical cores')
    if a['reserved_ram_gib'] >= a['host_ram_gib']:
        raise ValueError('reserved_ram_gib must leave usable RAM')
    if a['transport_factor'] < 1:
        raise ValueError('transport_factor must be >= 1')

    battle_players = a['ccu'] * a['battle_share']
    lobby_players = a['ccu'] - battle_players
    packed_rooms = _ceil(battle_players / (a['slots'] * a['occupancy']))
    rooms = packed_rooms + int(a['transition_rooms'])
    cpu_per_room = a['tick_hz'] * a['tick_cpu_ms'] / 1000
    cpu_budget = (a['host_cores'] - a['reserved_cores']) * a['cpu_target']
    ram_budget = (a['host_ram_gib'] - a['reserved_ram_gib']) * a['ram_target']
    net_budget = a['host_link_mbps'] * a['net_target']
    full_room_mbps = a['slots'] * a['battle_egress_kbps'] * a['transport_factor'] / 1000
    limits = {
        'cpu': _floor(cpu_budget / cpu_per_room),
        'ram': _floor(ram_budget / a['worker_ram_gib']),
        'network': _floor(net_budget / full_room_mbps),
    }
    room_limit = min(limits.values())
    feasible = rooms == 0 or room_limit > 0
    active_hosts = (_ceil(Fraction(rooms, room_limit)) if rooms else 0) if feasible else None
    spare_hosts = (active_hosts + 1 if rooms else 0) if feasible else None
    payload_mbps = (battle_players * a['battle_egress_kbps'] +
                    lobby_players * a['lobby_egress_kbps']) / 1000
    wire_mbps = payload_mbps * a['transport_factor']
    seconds = a['days'] * 86400
    # Decimal TB, 1 Mbit = 10^6 bits; eight bits per byte, not eight MiB.
    traffic_tb = wire_mbps * 1000000 / 8 * seconds / 1000000000000
    warnings = [
        'ESTIMATE_ONLY: no combat performance or capacity has been measured.',
        'CPU-ms is aggregate compute; p95/p99 wall-tick deadlines require separate measurement.',
        'N+1 counts battle hosts only; live battle recovery and service/DB HA are not implied.',
        'Network is legitimate egress only; ingress, PPS, loss and DDoS remain unmeasured.',
        'Monthly traffic holds battle mix constant and scales by mean CCU / stated CCU.',
    ]
    serial_mean_fits = a['tick_cpu_ms'] <= 1000 / a['tick_hz']
    if not serial_mean_fits:
        warnings.append('If the whole step is serial, mean CPU time already exceeds its wall deadline; more hosts do not fix this.')
    if not feasible:
        warnings.append('UNSCHEDULABLE_ASSUMPTIONS: one full room exceeds a host budget.')
    return _display({
        'version': 1, 'status': 'ESTIMATE_ONLY', 'assumptions': a,
        'rooms': {
            'players_in_battle': battle_players, 'players_in_lobby': lobby_players,
            'minimum_full_rooms': _ceil(battle_players / a['slots']),
            'occupied_rooms': packed_rooms, 'transition_rooms': int(a['transition_rooms']),
            'budgeted_worker_processes': rooms,
        },
        'per_room': {
            'cpu_core_equivalents': cpu_per_room,
            'ram_gib': a['worker_ram_gib'], 'full_room_wire_egress_mbps': full_room_mbps,
            'wall_deadline_ms': 1000 / a['tick_hz'],
            'serial_mean_within_deadline': serial_mean_fits,
            'p99_wall_deadline_status': 'NOT_RUN',
        },
        'per_host': {
            'cpu_core_budget': cpu_budget, 'ram_gib_budget': ram_budget,
            'legitimate_wire_egress_mbps_budget': net_budget,
            'whole_room_limits': limits, 'whole_rooms': room_limit,
            'limiting_resources': [key for key, value in limits.items() if value == room_limit],
        },
        'fleet': {
            'arithmetically_schedulable': feasible,
            'cpu_core_equivalents_reserved': rooms * cpu_per_room,
            'ram_gib_reserved': rooms * a['worker_ram_gib'],
            'battle_hosts_minimum': active_hosts, 'battle_hosts_n_plus_one': spare_hosts,
            'separate_service_hosts': int(a['service_hosts']),
            'total_hosts_without_battle_spare': None if active_hosts is None else active_hosts + int(a['service_hosts']),
            'total_hosts_with_battle_n_plus_one': None if spare_hosts is None else spare_hosts + int(a['service_hosts']),
            'battle_slots_after_one_host_failure': None if spare_hosts is None else max(0, spare_hosts - 1) * room_limit,
        },
        'network': {
            'application_egress_mbps_at_stated_ccu': payload_mbps,
            'wire_egress_mbps_at_stated_ccu': wire_mbps,
            'wire_egress_decimal_MB_per_second': wire_mbps / 8,
            'minimum_aggregate_link_mbps_at_target': wire_mbps / a['net_target'],
            'decimal_TB_at_constant_stated_ccu': traffic_tb,
            'decimal_TB_at_assumed_mean_ccu': traffic_tb * a['mean_ccu_fraction'],
            'mean_ccu_for_traffic': a['ccu'] * a['mean_ccu_fraction'],
        },
        'warnings': warnings,
    })


def matrix():
    """Small sensitivity grid; every row remains an assumption, not a test run."""
    cpu_rows = []
    for share in ('0.5', '0.7', '1'):
        for milliseconds in (5, 10, 20):
            row = estimate(battle_share=share, tick_cpu_ms=milliseconds)
            cpu_rows.append({
                'battle_share': row['assumptions']['battle_share'],
                'tick_cpu_ms': milliseconds,
                'rooms': row['rooms']['budgeted_worker_processes'],
                'rooms_per_host': row['per_host']['whole_rooms'],
                'battle_hosts_n_plus_one': row['fleet']['battle_hosts_n_plus_one'],
                'total_hosts_with_two_service_hosts': row['fleet']['total_hosts_with_battle_n_plus_one'],
            })
    network_rows = []
    for kbps in (20, 50, 100):
        row = estimate(battle_share=1, battle_egress_kbps=kbps)
        network_rows.append(dict({'kbps_per_combat_player': kbps}, **row['network']))
    return {'version': 1, 'status': 'ESTIMATE_ONLY', 'base_assumptions': estimate()['assumptions'],
            'cpu_sensitivity': cpu_rows, 'all_players_in_battle_network': network_rows}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matrix', action='store_true', help='fixed documented sensitivity grid; no overrides')
    for key in DEFAULTS:
        parser.add_argument('--' + key.replace('_', '-'), default=None)
    args = vars(parser.parse_args(argv))
    use_matrix = args.pop('matrix')
    overrides = {key: value for key, value in args.items() if value is not None}
    if use_matrix and overrides:
        parser.error('--matrix uses the fixed documented assumptions; omit other flags')
    try:
        result = matrix() if use_matrix else estimate(**overrides)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
