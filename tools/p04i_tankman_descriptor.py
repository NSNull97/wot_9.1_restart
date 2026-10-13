"""Bounded authored #717 normal-USSR descriptor and integer XP domain.

The cumulative table is source-derived and checked with owned CPython2.7.3;
runtime progression uses integers and never executes original client code.
This module does not award XP or expose a network XP command.
"""
from __future__ import annotations

from copy import deepcopy
import struct

from p04h_tankman_descriptor import (ROLE_IDS, TYPE_ROLES, ROLE_RANK_IDS,
    CATALOG_BOUNDS, DOSSIER_HEX, verify_catalog, require)

SKILL_IDS = {
    'repair': 6, 'fireFighting': 7, 'camouflage': 8, 'brotherhood': 9,
    'commander_tutor': 16, 'commander_eagleEye': 17, 'commander_sixthSense': 18,
    'commander_expert': 19, 'commander_universalist': 20,
    'driver_virtuoso': 28, 'driver_smoothDriving': 29, 'driver_badRoadsKing': 30,
    'driver_rammingMaster': 31, 'driver_tidyPerson': 32,
    'gunner_gunsmith': 37, 'gunner_sniper': 38, 'gunner_smoothTurret': 39, 'gunner_rancorous': 40,
    'loader_pedant': 46, 'loader_desperado': 47, 'loader_intuition': 48,
    'radioman_inventor': 53, 'radioman_finder': 54, 'radioman_retransmitter': 55, 'radioman_lastEffort': 56,
}
SKILL_NAMES = {value: name for name, value in SKILL_IDS.items()}
COMMON_SKILLS = frozenset(('repair', 'fireFighting', 'camouflage', 'brotherhood'))
SKILLS_BY_ROLE = {role: COMMON_SKILLS | frozenset(name for name in SKILL_IDS if name.startswith(role + '_'))
                 for role in ('commander', 'driver', 'gunner', 'loader', 'radioman')}
LEARNABLE_SKILLS = frozenset(SKILL_IDS) - {'commander_sixthSense'}
MAX_SKILLS = len(SKILL_IDS)
MAX_FREE_XP = 2_000_000_000
MAX_DESCRIPTOR_BYTES = 25 + MAX_SKILLS
# Integer cumulative source table; avoids host libm/round differences at runtime.
XP_COSTS = (0,50,102,157,214,274,337,403,472,544,620,699,782,869,960,1055,1155,1259,1368,1483,
    1603,1729,1861,1999,2143,2294,2452,2618,2791,2973,3163,3362,3570,3788,4017,4256,4507,
    4769,5044,5332,5633,5948,6278,6624,6986,7365,7762,8178,8613,9069,9546,10046,10570,11118,
    11692,12293,12922,13581,14271,14994,15751,16543,17373,18242,19152,20105,21103,22148,23242,
    24387,25586,26842,28157,29534,30976,32486,34067,35723,37457,39272,41173,43164,45248,47431,
    49716,52109,54615,57239,59987,62864,65877,69032,72335,75794,79416,83209,87181,91340,95695,100255,105030)
FIELDS = frozenset(('vehicle_type_id', 'role', 'role_level', 'first_name_id', 'last_name_id',
    'icon_id', 'rank_index', 'levels_to_next_rank', 'free_xp', 'skills', 'last_skill_level'))
PASSPORT_FIELDS = ('vehicle_type_id', 'role', 'first_name_id', 'last_name_id', 'icon_id')


def integer(value, low, high, name):
    require(type(value) is int and low <= value <= high, name)


def encode_descriptor(value):
    require(type(value) is dict and set(value) == FIELDS, 'descriptor fields')
    integer(value['vehicle_type_id'], 0, 255, 'vehicle type')
    require(value['vehicle_type_id'] in TYPE_ROLES and value['role'] in ROLE_IDS, 'verified type/role')
    integer(value['role_level'], 50, 100, 'qualification')
    for key, bound in CATALOG_BOUNDS.items(): integer(value[key], 1, bound, 'catalog ' + key)
    maximum_rank = len(ROLE_RANK_IDS[value['role']]) - 1
    integer(value['rank_index'], 0, maximum_rank, 'rank')
    integer(value['levels_to_next_rank'], 0, 2047, 'next rank')
    require((value['levels_to_next_rank'] == 0) == (value['rank_index'] == maximum_rank), 'maximum rank counter')
    integer(value['free_xp'], 0, MAX_FREE_XP, 'free XP')
    skills = value['skills']
    require(type(skills) is list and len(skills) <= MAX_SKILLS
        and all(type(name) is str and name in SKILL_IDS for name in skills)
        and len(set(skills)) == len(skills), 'ordered unique active skills')
    integer(value['last_skill_level'], 0, 100, 'last skill level')
    require(bool(skills) or value['last_skill_level'] == 0, 'empty last skill level')
    require(not skills or value['role_level'] == 100, 'skill qualification')
    prefix = bytes((8, value['vehicle_type_id'], ROLE_IDS[value['role']], value['role_level'], len(skills)))
    middle = bytes(SKILL_IDS[name] for name in skills) + bytes((value['last_skill_level'],))
    rank = value['rank_index'] | (value['levels_to_next_rank'] << 5)
    suffix = struct.pack('<B4Hi', 0, value['first_name_id'], value['last_name_id'], value['icon_id'], rank, value['free_xp'])
    return prefix + middle + suffix + bytes.fromhex(DOSSIER_HEX)


def decode_descriptor(raw):
    require(type(raw) is bytes and 25 <= len(raw) <= MAX_DESCRIPTOR_BYTES, 'descriptor byte bound')
    header, vehicle, role, level, count = raw[:5]
    require(header == 8 and count <= MAX_SKILLS and len(raw) == 25 + count, 'descriptor length/header')
    names = [SKILL_NAMES.get(index) for index in raw[5:5 + count]]
    require(all(name is not None for name in names), 'active skill index')
    flags, first, last, icon, rank, xp = struct.unpack('<B4Hi', raw[6 + count:19 + count])
    require(flags == 0 and raw[19 + count:].hex() == DOSSIER_HEX, 'normal flags/unchanged empty dossier')
    value = dict(vehicle_type_id=vehicle, role=next((name for name, index in ROLE_IDS.items() if index == role), None),
        role_level=level, first_name_id=first, last_name_id=last, icon_id=icon, rank_index=rank & 31,
        levels_to_next_rank=rank >> 5, free_xp=xp, skills=names, last_skill_level=raw[5 + count])
    require(encode_descriptor(value) == raw, 'canonical descriptor')
    return value


def skill_levels(value):
    encode_descriptor(value)
    return [{'skill_id': name, 'level': value['last_skill_level'] if index == len(value['skills']) - 1 else 100}
            for index, name in enumerate(value['skills'])]


def total_xp(value):
    encode_descriptor(value)
    count = len(value['skills'])
    return value['free_xp'] + XP_COSTS[value['role_level']] + (XP_COSTS[value['last_skill_level']] * 2**count
        + sum(XP_COSTS[100] * 2**index for index in range(1, count)) if count else 0)


def level_up_cost(level, sequence):
    integer(level, 0, 99, 'level')
    integer(sequence, 0, MAX_SKILLS, 'skill sequence')
    return 2**sequence * (XP_COSTS[level + 1] - XP_COSTS[level])


def _advance_rank(value):
    if value['levels_to_next_rank'] == 0: return
    value['levels_to_next_rank'] -= 1
    if value['levels_to_next_rank'] == 0:
        maximum = len(ROLE_RANK_IDS[value['role']]) - 1
        value['rank_index'] = min(value['rank_index'] + 1, maximum)
        value['levels_to_next_rank'] = 0 if value['rank_index'] == maximum else 50


def add_xp(value, xp):
    """Pure calculation for trusted future awards; not a persistence/network API."""
    encode_descriptor(value)
    integer(xp, 0, MAX_FREE_XP, 'trusted nonnegative XP')
    result = deepcopy(value)
    result['free_xp'] = min(MAX_FREE_XP, result['free_xp'] + xp)
    fields = [('role_level', 0)] + ([('last_skill_level', len(result['skills']))] if result['skills'] else [])
    for field, sequence in fields:
        while result[field] < 100:
            cost = level_up_cost(result[field], sequence)
            if result['free_xp'] < cost: break
            result['free_xp'] -= cost
            result[field] += 1
            _advance_rank(result)
    encode_descriptor(result)
    return result


def learn_skill(value, name, allowed_skills):
    encode_descriptor(value)
    require(type(name) is str and name in LEARNABLE_SKILLS and name in allowed_skills, 'skill eligibility')
    require(value['role_level'] == 100 and (not value['skills'] or value['last_skill_level'] == 100), 'unfinished qualification/skill')
    require(name not in value['skills'], 'duplicate skill')
    result = deepcopy(value)
    result['skills'].append(name)
    result['last_skill_level'] = 0
    return add_xp(result, 0)
