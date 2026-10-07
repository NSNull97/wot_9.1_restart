# -*- coding: utf-8 -*-
"""Pure bounded-reader controls. Synthetic objects never prove compatibility."""
import hashlib
import os
import shutil
import sys
import tempfile
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'client_patch'))
import arena_entry_probe as probe


class Box(object):
    def __init__(self, **fields):
        self.__dict__.update(fields)


class SyntheticAccount(object):
    pass


class SyntheticAvatar(object):
    def userSeesWorld(self):
        return self._PlayerAvatar__stepsTillInit == 0


class SyntheticArena(object):
    pass


class SyntheticArenaType(object):
    pass


class SyntheticVehicle(object):
    pass


class ProbeTests(unittest.TestCase):
    def setUp(self):
        names = ('Account', 'Avatar', 'ArenaType', 'BigWorld', 'ResMgr',
                 'ConnectionManager', 'ClientArena', 'Vehicle')
        self.modules = dict((name, types.ModuleType(name)) for name in names)
        self.previous = dict((name, sys.modules.get(name)) for name in names)
        sys.modules.update(self.modules)
        self.saved = dict((name, getattr(probe, name)) for name in
                          ('_audit_avatar_bindings', '_source_hashes', 'SOURCE_HASHES',
                           '_export_requested', '_provenance_checked', '_observations'))
        probe._audit_avatar_bindings = lambda cls: None
        probe._export_requested, probe._provenance_checked, probe._observations = False, False, 0
        self.directory = tempfile.mkdtemp(prefix='arena-probe-pure-')
        self.account = SyntheticAccount()
        self.account.id, self.account.databaseID, self.account.name = 7, 1, u'Тест'
        self.player = self.account
        self.avatar = SyntheticAvatar()
        self.avatar.id, self.avatar.name = 11, u'Тест'
        self.avatar.spaceID, self.avatar.inWorld = 100, True
        self.avatar.position = Box(x=1.0, y=2.0, z=3.0)
        self.avatar._PlayerAvatar__stepsTillInit = 4
        self.avatar._PlayerAvatar__isSpaceInitialized = False
        self.avatar.playerVehicleID = 0
        self.arena_type = SyntheticArenaType()
        self.arena_type.id, self.arena_type.geometryID, self.arena_type.gameplayID = 1, 1, 0
        self.arena_type.geometryName, self.arena_type.geometry = '01_karelia', 'spaces/01_karelia'
        self.arena_type.gameplayName, self.arena_type.name = 'ctf', u'Original map name'
        self.arena_type.boundingBox = (Box(x=-500.0, y=-500.0), Box(x=500.0, y=500.0))
        self.arena_type.weatherPresets = [{'rnd_range': (0, 1)}]
        self.arena = SyntheticArena()
        self.arena.arenaType, self.arena.arenaUniqueID, self.arena.vehicles = self.arena_type, 1001, {}
        self.avatar.arena = self.arena
        self.repository = Box()
        self.entities = {}
        self.modules['Account'].PlayerAccount = SyntheticAccount
        self.modules['Account'].g_accountRepository = self.repository
        self.modules['Avatar'].PlayerAvatar = SyntheticAvatar
        self.modules['ArenaType'].ArenaType = SyntheticArenaType
        self.modules['ArenaType'].g_cache = {1: self.arena_type}
        self.modules['ClientArena'].ClientArena = SyntheticArena
        self.modules['Vehicle'].Vehicle = SyntheticVehicle
        self.modules['BigWorld'].player = lambda: self.player
        self.modules['BigWorld'].entity = lambda identifier: self.entities.get(identifier)
        self.modules['BigWorld'].worldDrawEnabled = lambda: False
        self.modules['BigWorld'].spaceLoadStatus = lambda: 0.5
        self.opened = []
        def section(name):
            self.opened.append(name)
            return Box()
        self.modules['ResMgr'].openSection = section
        self.modules['ConnectionManager'].connectionManager = Box(isConnected=lambda: True)
        self.events = []
        self.record = lambda event, **data: self.events.append((event, data))

    def tearDown(self):
        for name, value in self.saved.items():
            setattr(probe, name, value)
        for name, value in self.previous.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value
        shutil.rmtree(self.directory)

    def test_resource_reader_preserves_identity_and_does_not_claim_loaded(self):
        before = dict(self.account.__dict__)
        data = probe._collect_resources()
        self.assertEqual(before, self.account.__dict__)
        self.assertEqual(data['account_before'], data['account_after'])
        self.assertEqual(self.opened, ['spaces/01_karelia/space.settings'])
        self.assertEqual(data['arena_type_id'], 1)
        self.assertFalse(data['arena_loaded_proven'])
        self.assertFalse(data['public_project_name_approved'])

    def test_resource_reader_rejects_wrong_candidate(self):
        self.arena_type.gameplayID = 2
        self.assertRaises(ValueError, probe._collect_resources)

    def test_resource_reader_rejects_missing_geometry(self):
        self.modules['ResMgr'].openSection = lambda name: None
        self.assertRaises(RuntimeError, probe._collect_resources)

    def test_resource_reader_rejects_non_account_and_missing_repository(self):
        self.player = self.avatar
        self.assertRaises(RuntimeError, probe._collect_resources)
        self.player = self.account
        self.modules['Account'].g_accountRepository = None
        self.assertRaises(RuntimeError, probe._collect_resources)

    def test_resource_reader_detects_identity_change_during_read(self):
        def mutate(name):
            self.account.databaseID += 1
            return Box()
        self.modules['ResMgr'].openSection = mutate
        self.assertRaises(RuntimeError, probe._collect_resources)

    def test_resource_reader_rejects_changed_bounds_and_weather(self):
        self.arena_type.boundingBox[0].x = float('nan')
        self.assertRaises(ValueError, probe._collect_resources)
        self.arena_type.boundingBox[0].x = -500.0
        self.arena_type.weatherPresets.append({})
        self.assertRaises(ValueError, probe._collect_resources)

    def test_export_source_failure_never_sets_success_and_no_retry(self):
        def fail(root):
            raise ValueError('synthetic source error')
        probe._source_hashes = fail
        self.assertRaises(ValueError, probe.export, self.record)
        self.assertFalse(probe._provenance_checked)
        self.assertEqual(self.events, [])
        self.assertRaises(RuntimeError, probe.export, self.record)

    def test_export_once_and_only_then_observation(self):
        self.assertRaises(RuntimeError, probe.observe, self.record)
        probe._source_hashes = lambda root: []
        probe.export(self.record)
        self.assertTrue(probe._provenance_checked)
        observed = probe.observe(self.record)
        self.assertTrue(observed['player_is_original_account'])
        self.assertEqual(self.events[0][0], 'arena_entry_resources')
        self.assertEqual(self.events[1][0], 'arena_entry_observation')
        self.assertRaises(RuntimeError, probe.export, self.record)

    def test_base_avatar_reports_missing_cell_properties_not_zero(self):
        self.player = self.avatar
        del self.avatar.spaceID
        del self.avatar.playerVehicleID
        del self.avatar._PlayerAvatar__stepsTillInit
        data = probe._collect_observation()
        self.assertIsNone(data['space_id'])
        self.assertIsNone(data['player_vehicle_id'])
        self.assertIsNone(data['steps_till_init'])
        self.assertIsNone(data['user_sees_world'])
        self.assertEqual(data['unavailable'], ['spaceID', 'position_without_space',
            'steps_till_init', 'space_load_without_space', 'playerVehicleID'])
        self.assertEqual(data['acceptance'], 'OBSERVATION_ONLY')

    def test_avatar_counter_zero_does_not_invent_vehicle_or_space(self):
        self.player = self.avatar
        self.avatar._PlayerAvatar__stepsTillInit = 0
        data = probe._collect_observation()
        self.assertTrue(data['user_sees_world'])
        self.assertFalse(data['space_initialized'])
        self.assertFalse(data['world_draw_enabled'])
        self.assertFalse(data['vehicle_present'])
        self.assertEqual(data['acceptance'], 'OBSERVATION_ONLY')

    def test_measured_base_avatar_none_space_is_unavailable_not_id_zero(self):
        self.player = self.avatar
        self.avatar.spaceID = None
        data = probe._collect_observation()
        self.assertTrue(data['player_is_original_avatar'])
        self.assertIsNone(data['space_id'])
        self.assertEqual(data['unavailable'], ['spaceID', 'position_without_space',
                                              'space_load_without_space'])
        self.assertIsNone(data['position'])
        self.assertIsNone(data['space_load_progress'])
        self.assertEqual(data['acceptance'], 'OBSERVATION_ONLY')
        self.assertFalse(data['user_sees_world'])
        self.assertFalse(data['space_initialized'])

    def test_nullable_space_does_not_accept_invalid_integer_values(self):
        self.player = self.avatar
        for invalid in (True, False, -1, 1.0, '0', 4294967296):
            self.avatar.spaceID = invalid
            self.assertRaises(ValueError, probe._collect_observation)

    def test_measured_none_exception_does_not_relax_other_native_properties(self):
        self.player = self.avatar
        self.avatar.position = None
        self.assertRaises(AttributeError, probe._collect_observation)
        self.avatar.position = Box(x=1.0, y=2.0, z=3.0)
        self.avatar.inWorld = None
        self.assertRaises(ValueError, probe._collect_observation)

    def test_no_space_does_not_invoke_spatial_getters(self):
        calls = []
        class SpatialAvatar(SyntheticAvatar):
            @property
            def position(self):
                calls.append('position')
                raise RuntimeError('synthetic spatial getter must remain strict')
        avatar = SpatialAvatar()
        avatar.__dict__.update(self.avatar.__dict__)
        avatar.spaceID = None
        self.modules['Avatar'].PlayerAvatar = SpatialAvatar
        self.player = avatar
        def load_status():
            calls.append('spaceLoadStatus')
            raise RuntimeError('synthetic no-space engine call')
        self.modules['BigWorld'].spaceLoadStatus = load_status
        data = probe._collect_observation()
        self.assertEqual(calls, [])
        self.assertIsNone(data['position'])
        self.assertIsNone(data['space_load_progress'])
        avatar.spaceID = 100
        self.assertRaises(RuntimeError, probe._collect_observation)
        self.assertEqual(calls, ['position'])

    def test_real_space_load_getter_failure_is_not_suppressed(self):
        self.player = self.avatar
        def fail():
            raise RuntimeError('synthetic failing native load status')
        self.modules['BigWorld'].spaceLoadStatus = fail
        self.assertRaises(RuntimeError, probe._collect_observation)

    def test_getter_counter_disagreement_rejected(self):
        self.player = self.avatar
        self.avatar.userSeesWorld = lambda: True
        self.assertRaises(ValueError, probe._collect_observation)

    def test_vehicle_readback_does_not_construct_entity(self):
        self.player = self.avatar
        self.avatar.playerVehicleID = 20
        data = probe._collect_observation()
        self.assertFalse(data['vehicle_present'])
        vehicle = SyntheticVehicle()
        vehicle.inWorld, vehicle.typeDescriptor = True, Box()
        self.entities[20] = vehicle
        data = probe._collect_observation()
        self.assertTrue(data['vehicle_is_original'])
        self.assertTrue(data['vehicle_in_world'])
        self.assertEqual(list(self.entities.keys()), [20])

    def test_native_null_player_is_not_an_avatar(self):
        self.player = None
        data = probe._collect_observation()
        self.assertFalse(data['player_present'])
        self.assertFalse(data['player_is_original_avatar'])
        self.assertIsNone(data['entity_id'])

    def test_arena_list_bound_rejects_excess_instead_of_truncating(self):
        self.player = self.avatar
        self.arena.vehicles = dict((i, {}) for i in range(65))
        self.assertRaises(ValueError, probe._collect_observation)

    def test_invalid_native_position_is_not_masked(self):
        self.player = self.avatar
        self.avatar.position.y = float('inf')
        self.assertRaises(ValueError, probe._collect_observation)

    def test_real_getter_error_propagates_instead_of_becoming_missing(self):
        class InvalidAvatar(SyntheticAvatar):
            @property
            def spaceID(self):
                raise RuntimeError('synthetic real getter failure')
        avatar = InvalidAvatar()
        avatar.id, avatar.name = 11, 'test'
        self.modules['Avatar'].PlayerAvatar = InvalidAvatar
        self.player = avatar
        self.assertRaises(RuntimeError, probe._collect_observation)

    def test_observation_budget_exhaustion_is_failure_not_pass(self):
        probe._provenance_checked = True
        probe._observations = probe.MAX_OBSERVATIONS - 1
        row = probe.observe(self.record)
        self.assertEqual(row['observation_index'], probe.MAX_OBSERVATIONS)
        self.assertRaises(RuntimeError, probe.observe, self.record)
        self.assertEqual(len(self.events), 1)

    def test_primitive_bounds_reject_boolean_id_and_nonfinite(self):
        self.assertRaises(ValueError, probe._integer, True, 0, 10, 'ID')
        self.assertRaises(ValueError, probe._number, float('nan'), 0, 10, 'number')
        self.assertRaises(ValueError, probe._number, float('inf'), 0, 10, 'number')
        self.assertRaises(ValueError, probe._boolean, 1, 'flag')

    def test_payload_budget_counts_encoded_unicode_and_no_partial_record(self):
        self.assertRaises(ValueError, probe._emit, self.record, 'synthetic', {'text': u'Ё' * 2000})
        self.assertEqual(self.events, [])
        probe._emit(self.record, 'synthetic', {'text': u'Ё' * 100})
        self.assertEqual(self.events[0][1]['text'], u'Ё' * 100)

    def test_source_bytes_and_traversal_guard(self):
        path = os.path.join(self.directory, 'source.pyc')
        raw = b'explicitly-synthetic-source'
        with open(path, 'wb') as stream:
            stream.write(raw)
        probe.SOURCE_HASHES = (('source.pyc', hashlib.sha256(raw).hexdigest()),)
        self.assertEqual(probe._source_hashes(self.directory)[0]['bytes'], len(raw))
        with open(path, 'wb') as stream:
            stream.write(b'changed')
        self.assertRaises(ValueError, probe._source_hashes, self.directory)
        probe.SOURCE_HASHES = (('../escape.pyc', '0' * 64),)
        self.assertRaises(ValueError, probe._source_hashes, self.directory)

    def test_callback_pin_checks_filename_line_argument_count_and_code(self):
        def example(self):
            return 7
        code = getattr(example, 'func_code', getattr(example, '__code__', None))
        contract = ('unused', code.co_name, code.co_firstlineno, code.co_argcount,
                    hashlib.sha256(code.co_code).hexdigest())
        name = code.co_filename.replace('\\', '/')
        probe._code_contract(example, contract, name)
        for index, value in ((1, 'other'), (2, code.co_firstlineno + 1),
                             (3, code.co_argcount + 1), (4, '0' * 64)):
            altered = list(contract)
            altered[index] = value
            self.assertRaises(ValueError, probe._code_contract, example, altered, name)
        self.assertRaises(ValueError, probe._code_contract, example, contract, 'wrong.py')


if __name__ == '__main__':
    unittest.main()
