# -*- coding: utf-8 -*-
"""Opt-in original Vehicle/world checkpoint; no entities or callbacks are made here.

The server supplies the Entity/roster. The engine runs all lifecycle methods.
Only the three previously audited services and the native screenshot writer are
invoked by this diagnostic. A PNG container is not a human pixel review or a battle.
"""
import hashlib
import os

import arena_bootstrap
import arena_entry_probe as probe
import arena_space_scenario as space
from ms1_crew_scenario import _Native as ScreenshotNative, _now

VERSION = 1
AVATAR_ID, VEHICLE_ID, SPACE_ID = space.AVATAR_ID, space.VEHICLE_ID, space.SPACE_ID
MAX_ADVANCES = 239
MAX_PENDING_NOTES = 64
MAX_TOTAL_NOTES = 128
MIN_READY_SECONDS = 2.0
MAX_READY_GAP = 3.0
MAX_PNG_ADVANCES = 15
BASENAME = 'arena_vehicle'
PARTS = ('chassis', 'hull', 'turret', 'gun')
VEHICLE_METHODS = (
    ('__init__', '__init__', 44, 1, 'ae4bc07efd1ab6a624d1e13e66d55a26bc78803a8b8d231211a4523ac91a7c73'),
    ('prerequisites', 'prerequisites', 99, 1, '63423173a417d85979804617308665cd0f4bb592fe2dd12386a5541043d9b87f'),
    ('onEnterWorld', 'onEnterWorld', 126, 2, '57a3664e46cfe307ef7ce0e483673cce0e39759925f095ec3081b0eae8f7678f'),
    ('onLeaveWorld', 'onLeaveWorld', 155, 1, 'bd0713c1983af7d45710e1a869ecb1fcd38a920c99fcf6a228e2bb41de3a0fd2'),
    ('startVisual', 'startVisual', 562, 1, '76e82690221bcc1336383f422360f44a07b724372436a86a0a5e5e1cc5ad2360'),
    ('stopVisual', 'stopVisual', 614, 1, '29cfe3f7b5134a2a959eedc0ae348fc3912d04b190466fca8f9537803f95d550'),
)
CALLBACKS = {
    'avatar': {'onEnterWorld': (388, (316,)), 'onSpaceLoaded': (535, (33,)),
               '__onInitStepCompleted': (2579, (101, 640)),
               'onLeaveWorld': (425, (948,)), 'onBecomeNonPlayer': (361, (193,))},
    'vehicle': {'__init__': (44, (129,)), 'prerequisites': (99, (18, 190)),
                'onEnterWorld': (126, (169,)), 'startVisual': (562, (407,)),
                'onLeaveWorld': (155, (48,)), 'stopVisual': (614, (177,))},
}
SOURCE_HASHES = (
    ('res/scripts/client/Vehicle.pyc', 'b81d08ca14092bb8912adb2eff20325c3dd23424868bc03164cfe6b8da50463c'),
    ('res/scripts/client/VehicleAppearance.pyc', 'aa4f0c9ac4e830209c7929bd6c3aad1c19efec316c8cc7711f8b9211c893335a'),
    ('res/scripts/client/VehicleGunRotator.pyc', 'd0105237b62447fee170cbf17984fd48437115087d6af6bf44743cc0cf68576a'),
    ('res/scripts/client/gui/Scaleform/Battle.pyc', 'aa43bc6b7e1f7ae9e2bba03fa527a9e6ce95a5d41ef23f26785b1490cd6f38de'),
)
_run = None
_arm_attempted = False
_closing = False
_finished_cleanup = False
_cleanup_errors = []


def _emit(record, event, **fields):
    fields['version'] = VERSION
    return probe._emit(record, event, fields)


def _int(value, low=0, high=0x7fffffffffffffff):
    return type(value) in probe.integer_types and low <= value <= high


def _bytes_sha(value):
    if type(value) is not bytes or not 1 <= len(value) <= 512:
        raise ValueError('bounded original compact descriptor bytes required')
    return hashlib.sha256(value).hexdigest()


def _native_flag(value):
    # Original aliases.xml BOOL is UINT8, not a proven Python PyBool getter.
    # Preserve the actual primitive/type; never coerce arbitrary truthy data.
    if type(value) not in probe.integer_types + (bool,) or value not in (0, 1):
        raise ValueError('original BOOL/UINT8 flag must be actual zero or one')
    return value


def _audit_sources():
    root = os.path.realpath(os.getcwd())
    rows = []
    for relative, expected in SOURCE_HASHES:
        path = os.path.join(root, *relative.split('/'))
        if (not os.path.realpath(path).startswith(root + os.sep) or os.path.islink(path)
                or not os.path.isfile(path) or not 1 <= os.path.getsize(path) <= 1048576):
            raise ValueError('bounded original Vehicle source required')
        with open(path, 'rb') as stream:
            raw = stream.read(1048577)
        digest = hashlib.sha256(raw).hexdigest()
        if not 1 <= len(raw) <= 1048576 or digest != expected:
            raise ValueError('original Vehicle source differs: ' + relative)
        rows.append({'relative_path': relative, 'bytes': len(raw), 'sha256': digest})
    return rows


class _Pixels(ScreenshotNative):
    def request(self, basename):
        import BigWorld
        if basename != BASENAME or basename in self.requested:
            raise ValueError('one owned native arena screenshot required')
        if self._entries():
            raise ValueError('arena screenshot directory must be fresh')
        self.requested.add(basename)
        BigWorld.screenShot('png', basename)


class _Native(space._Native):
    def __init__(self, record, settings):
        space._Native.__init__(self, record)
        self.pixels = _Pixels(settings)

    def expected_vehicle(self):
        from gui.shared import g_itemsCache
        from gui.shared.gui_items.Vehicle import Vehicle as GuiVehicle
        from items import vehicles
        value = g_itemsCache.items.getVehicle(1)
        if (not arena_bootstrap._exact_instance(value, GuiVehicle) or value.inventoryID != 1 or value.intCD != 3329
                or not arena_bootstrap._exact_instance(value.descriptor, vehicles.VehicleDescr)
                or value.descriptor.type.name != 'ussr:MS-1' or value.health != 90):
            raise RuntimeError('actual original inventory MS-1/90HP required before transition')
        return {'inventory_id': 1, 'type_compact_descr': value.intCD,
                'compact_descr_sha256': _bytes_sha(value.descriptor.makeCompactDescr()),
                'type_name': probe._text(value.descriptor.type.name, 64, 'vehicle type'),
                'health': probe._integer(value.health, 1, 10000, 'health')}

    def initialize(self):
        import Vehicle
        self.sources = _audit_sources()
        for contract in VEHICLE_METHODS:
            probe._code_contract(getattr(Vehicle.Vehicle, contract[0]), contract, 'scripts/client/Vehicle.py')
        space._Native.initialize(self)

    def vehicle(self):
        """Only primitive copies escape this call; no native references survive."""
        import Avatar
        import BigWorld
        import Vehicle
        import VehicleAppearance
        import VehicleGunRotator
        from gui.WindowsManager import g_windowsManager
        from gui.Scaleform.Battle import Battle
        from items import vehicles
        player = BigWorld.player()
        data = {'vehicle_present': False, 'owner_id': None, 'entity_id': None,
                'in_world': None, 'is_player': None, 'is_started': None,
                'health': None, 'crew_active': None, 'crew_active_python_type': None, 'position': None,
                'descriptor_sha256': None, 'public_descriptor_sha256': None,
                'avatar_descriptor_same': None, 'type_compact_descr': None,
                'type_name': None, 'public_name': None, 'team': None,
                'appearance_original': False, 'model_count': 0, 'models': [],
                'entity_model_is_chassis': False, 'roster': None,
                'battle_present': False, 'battle_original': False,
                'battle_component_present': False, 'battle_component_visible': None,
                'battle_movie_present': False, 'turret_sound_initialized': False}
        if type(player) is not Avatar.PlayerAvatar:
            return data
        vehicle = BigWorld.entity(VEHICLE_ID)
        if vehicle is not None:
            if type(vehicle) is not Vehicle.Vehicle:
                raise RuntimeError('native own Vehicle is not the original exact class')
            data.update(vehicle_present=True, owner_id=id(vehicle), entity_id=vehicle.id,
                        in_world=probe._boolean(vehicle.inWorld, 'Vehicle.inWorld'),
                        is_player=probe._boolean(vehicle.isPlayer, 'Vehicle.isPlayer'),
                        is_started=probe._boolean(vehicle.isStarted, 'Vehicle.isStarted'),
                        health=probe._integer(vehicle.health, 0, 10000, 'Vehicle.health'),
                        crew_active=_native_flag(vehicle.isCrewActive),
                        crew_active_python_type=type(vehicle.isCrewActive).__name__,
                        position=probe._position(vehicle.position, 'Vehicle.position'),
                        public_name=probe._text(vehicle.publicInfo.name, 128, 'Vehicle.publicInfo.name'),
                        team=probe._integer(vehicle.publicInfo.team, 0, 255, 'Vehicle.publicInfo.team'),
                        public_descriptor_sha256=_bytes_sha(vehicle.publicInfo.compDescr))
            descriptor = vehicle.typeDescriptor
            if descriptor is not None:
                if not arena_bootstrap._exact_instance(descriptor, vehicles.VehicleDescr):
                    raise RuntimeError('original Vehicle descriptor exact class required')
                data.update(descriptor_sha256=_bytes_sha(descriptor.makeCompactDescr()),
                            type_compact_descr=descriptor.type.compactDescr,
                            type_name=probe._text(descriptor.type.name, 64, 'type name'),
                            avatar_descriptor_same=player.vehicleTypeDescriptor is descriptor)
            appearance = vehicle.appearance
            if appearance is not None:
                if not arena_bootstrap._exact_instance(appearance, VehicleAppearance.VehicleAppearance):
                    raise RuntimeError('original VehicleAppearance exact class required')
                data['appearance_original'] = True
                descriptions = appearance.modelsDesc
                if type(descriptions) is not dict or set(descriptions) != set(PARTS):
                    raise ValueError('original four model descriptions required')
                for part in PARTS:
                    model = descriptions[part]['model']
                    data['models'].append({'part': part, 'present': model is not None,
                        'visible': None if model is None else probe._boolean(model.visible, part + '.visible')})
                data['model_count'] = sum(row['present'] for row in data['models'])
                data['entity_model_is_chassis'] = (vehicle.model is not None and
                    vehicle.model is descriptions['chassis']['model'])
        arena = getattr(player, 'arena', None)
        if arena is not None and VEHICLE_ID in arena.vehicles:
            row = arena.vehicles[VEHICLE_ID]
            descriptor = row['vehicleType']
            if not arena_bootstrap._exact_instance(descriptor, vehicles.VehicleDescr):
                raise ValueError('original roster VehicleDescr required')
            data['roster'] = {'vehicle_id': VEHICLE_ID,
                'database_id': probe._integer(row['accountDBID'], 1, 2147483647, 'roster DBID'),
                'name': probe._text(row['name'], 128, 'roster name'),
                'team': probe._integer(row['team'], 0, 255, 'roster team'),
                'alive': probe._boolean(row['isAlive'], 'roster isAlive'),
                'avatar_ready': probe._boolean(row['isAvatarReady'], 'roster isAvatarReady'),
                'descriptor_sha256': _bytes_sha(descriptor.makeCompactDescr())}
        battle = g_windowsManager.battleWindow
        if battle is not None:
            if not arena_bootstrap._exact_instance(battle, Battle):
                raise RuntimeError('original native Battle exact class required')
            data.update(battle_present=True, battle_original=True,
                        battle_component_present=battle.component is not None,
                        battle_movie_present=battle.movie is not None,
                        battle_component_visible=None if battle.component is None else
                            probe._boolean(battle.component.visible, 'Battle.component.visible'))
        rotator = getattr(player, 'gunRotator', None)
        if rotator is not None:
            sound = rotator._VehicleGunRotator__turretRotationSoundEffect
            if not arena_bootstrap._exact_instance(sound, VehicleGunRotator._PlayerTurretRotationSoundEffect):
                raise RuntimeError('original turret rotation sound class required')
            data['turret_sound_initialized'] = (
                hasattr(sound, '_PlayerTurretRotationSoundEffect__manualSound') and
                hasattr(sound, '_PlayerTurretRotationSoundEffect__gearSound'))
        return data

    def request(self):
        self.pixels.request(BASENAME)

    def screenshot(self):
        return self.pixels.screenshot(BASENAME)


class _Scenario(object):
    def __init__(self, record, native, clock=None):
        self.record, self.native, self.clock = record, native, _now if clock is None else clock
        self.advances, self.sequence = 0, 0
        self.notes, self.open_calls, self.pairs, self.seen = [], {}, [], set()
        self.note_error = None
        self.active, self.complete, self.geometry = False, False, None
        self.avatar_owner, self.vehicle_owner = None, None
        self.ready_since, self.last_ready, self.last_time = None, None, None
        self.ready_samples, self.png_requested_at = 0, None
        value, identity = native.account()
        if (value['player_is_original_account'] is not True or value['native_connected'] is not True
                or value['repository_present'] is not True or not _int(value['repository_owner_id'], 1)
                or value['entity_id'] != identity['entity_id'] or value['name'] != identity['name']
                or identity['database_id'] != 1):
            raise RuntimeError('actual connected primary Account/repository required')
        self.account, self.repository = dict(identity), value['repository_owner_id']
        self.expected = native.expected_vehicle()
        native.initialize()
        self.active = True
        _emit(record, 'arena_vehicle_armed', account=self.account, expected_vehicle=self.expected,
              repository_owner_id=self.repository, expected_avatar_id=AVATAR_ID,
              expected_vehicle_id=VEHICLE_ID, expected_space_id=SPACE_ID,
              expected_geometry=probe.GEOMETRY_PATH, max_advances=MAX_ADVANCES,
              sources=native.sources, native_entity_created_by_scenario=False,
              screenshot_basename=BASENAME, pixel_acceptance='NOT_RUN', computer_input=False)

    def _bad_note(self, reason):
        if self.note_error is None:
            self.note_error = reason
        return False

    def _queue(self, note):
        if len(self.notes) >= MAX_PENDING_NOTES or self.sequence >= MAX_TOTAL_NOTES:
            return self._bad_note('arena Vehicle callback note budget exhausted')
        self.sequence += 1
        note['sequence'] = self.sequence
        self.notes.append(note)
        return True

    def note(self, kind, phase, method, source_line, offset, call_id, owner_id, entity_id, space_id):
        if not self.active or type(method) not in probe.string_types or method not in CALLBACKS[kind]:
            return False
        if (type(phase) not in probe.string_types or phase not in ('call', 'return')
                or not _int(source_line, 1, 100000) or not _int(offset, -1, 100000)
                or not _int(call_id, 1) or not _int(owner_id, 1)
                or not _int(entity_id, 1, 2147483647)
                or space_id is not None and not _int(space_id, 0, 4294967295)):
            return self._bad_note('invalid primitive original Entity callback note')
        return self._queue(dict(kind=kind, phase=phase, method=method, source_line=source_line,
                               offset=offset, call_id=call_id, owner_id=owner_id,
                               entity_id=entity_id, space_id=space_id))

    def note_geometry(self, space_id, path):
        if not self.active:
            return False
        if not _int(space_id, 1, 4294967295) or type(path) not in probe.string_types or len(path) > 128:
            return self._bad_note('invalid geometry callback note')
        try:
            path = probe._text(path, 128, 'geometry')
        except (ValueError, UnicodeError):
            return self._bad_note('invalid geometry text')
        return self._queue(dict(kind='geometry', space_id=space_id, path=path))

    def drain(self):
        if self.note_error:
            raise RuntimeError(self.note_error)
        pending, self.notes = self.notes, []
        for note in pending:
            _emit(self.record, 'arena_vehicle_callback', **note)
            if note['kind'] == 'geometry':
                if self.geometry is not None or note['space_id'] != SPACE_ID or note['path'] != probe.GEOMETRY_PATH:
                    raise RuntimeError('foreign or duplicate native geometry mapping')
                self.geometry = note
                continue
            kind, method = note['kind'], note['method']
            line, returns = CALLBACKS[kind][method]
            if (note['source_line'] != line or note['entity_id'] != (AVATAR_ID if kind == 'avatar' else VEHICLE_ID)
                    or note['offset'] not in ((-1,) if note['phase'] == 'call' else returns)):
                raise RuntimeError('original Entity callback did not complete normally')
            if method in ('onLeaveWorld', 'onBecomeNonPlayer', 'stopVisual'):
                raise RuntimeError('original world was left before checkpoint completion')
            if note['phase'] == 'call':
                if note['call_id'] in self.seen:
                    raise RuntimeError('duplicate original Entity call ID')
                self.seen.add(note['call_id'])
                self.open_calls[note['call_id']] = note
            else:
                entry = self.open_calls.pop(note['call_id'], None)
                if entry is None or any(entry[key] != note[key] for key in
                        ('kind', 'method', 'source_line', 'owner_id', 'entity_id', 'space_id')):
                    raise RuntimeError('original Entity return has no matching entry')
                self.pairs.append({'entry': entry, 'returned': note})

    def callbacks_ready(self):
        grouped = {}
        for pair in self.pairs:
            row = pair['returned']
            owner = self.avatar_owner if row['kind'] == 'avatar' else self.vehicle_owner
            if owner is not None and row['owner_id'] != owner:
                raise RuntimeError('native callback owner differs from actual Entity')
            key = (row['kind'], row['method'])
            grouped.setdefault(key, []).append(pair)
        required = [('avatar', 'onEnterWorld'), ('avatar', 'onSpaceLoaded'),
                    ('vehicle', '__init__'), ('vehicle', 'prerequisites'),
                    ('vehicle', 'onEnterWorld'), ('vehicle', 'startVisual')]
        if any(len(grouped.get(key, [])) > 1 for key in required):
            raise RuntimeError('duplicate native initialization callback')
        if self.open_calls or self.geometry is None or any(key not in grouped for key in required):
            return False
        for key in required:
            row = grouped[key][0]['returned']
            if key[1] in ('onEnterWorld', 'onSpaceLoaded', 'startVisual') and row['space_id'] != SPACE_ID:
                return False
        loaded = grouped[('avatar', 'onSpaceLoaded')][0]
        if loaded['entry']['sequence'] <= self.geometry['sequence']:
            return False
        prerequisites = grouped[('vehicle', 'prerequisites')][0]['returned']
        if prerequisites['offset'] != 190:
            raise RuntimeError('first native Vehicle prerequisites unexpectedly reused a descriptor')
        steps = grouped.get(('avatar', '__onInitStepCompleted'), [])
        if len(steps) > 4:
            raise RuntimeError('original Avatar init-step count exceeded four')
        if len(steps) != 4:
            return False
        if [p['returned']['offset'] for p in steps] != [101, 101, 101, 640]:
            raise RuntimeError('original Avatar init steps did not complete at zero')
        return True

    def advance(self):
        if self.complete:
            return True
        if not self.active:
            raise RuntimeError('arena Vehicle scenario no longer active')
        self.advances += 1
        if self.advances > MAX_ADVANCES:
            raise RuntimeError('arena Vehicle observation budget exhausted')
        now = probe._number(self.clock(), 0, 1e10, 'diagnostic clock')
        if self.last_time is not None and now < self.last_time:
            raise RuntimeError('diagnostic clock moved backwards')
        self.last_time = now
        self.drain()
        value, vehicle = self.native.observe(), self.native.vehicle()
        _emit(self.record, 'arena_vehicle_state', advance=self.advances, observed_at=now,
              observation=value, vehicle=vehicle, callback_pairs=len(self.pairs))
        if (value['native_connected'] is not True or value['repository_present'] is not True
                or value['repository_owner_id'] != self.repository):
            raise RuntimeError('original native session/repository changed')
        if value['player_is_original_account']:
            if self.avatar_owner is not None or any(value[k] != self.account[k] for k in ('entity_id', 'name')):
                raise RuntimeError('unexpected Account replacement')
            return False
        if not value['player_present']:
            return False
        if (value['player_is_original_avatar'] is not True or value['entity_id'] != AVATAR_ID
                or value['name'] != self.account['name'] or self.avatar_owner is not None
                and value['player_owner_id'] != self.avatar_owner):
            raise RuntimeError('original Avatar identity differs')
        self.avatar_owner = value['player_owner_id']
        if value['space_id'] not in (None, SPACE_ID) or value['player_vehicle_id'] not in (None, 0, VEHICLE_ID):
            raise RuntimeError('unexpected native space/Vehicle identity')
        if value['arena_present'] and (value['arena_type_id'] != 1 or value['arena_unique_id'] != 1
                or value['geometry_path'] != probe.GEOMETRY_PATH or value['arena_vehicle_count'] not in (0, 1)):
            raise RuntimeError('unexpected local native arena/roster')
        if vehicle['vehicle_present']:
            if (vehicle['entity_id'] != VEHICLE_ID or vehicle['public_name'] != self.account['name']
                    or vehicle['health'] != self.expected['health'] or _native_flag(vehicle['crew_active']) != 1
                    or vehicle['team'] != 1 or vehicle['public_descriptor_sha256'] != self.expected['compact_descr_sha256']
                    or self.vehicle_owner is not None and vehicle['owner_id'] != self.vehicle_owner):
                raise RuntimeError('actual original Vehicle differs from the own lab seed')
            self.vehicle_owner = vehicle['owner_id']
            if vehicle['descriptor_sha256'] is not None and (
                    vehicle['descriptor_sha256'] != self.expected['compact_descr_sha256']
                    or vehicle['type_compact_descr'] != 3329 or vehicle['type_name'] != 'ussr:MS-1'):
                raise RuntimeError('native Vehicle descriptor differs from original inventory')
        roster = vehicle['roster']
        if roster is not None and (roster['database_id'] != self.account['database_id']
                or roster['name'] != self.account['name'] or roster['team'] != 1 or roster['alive'] is not True
                or roster['vehicle_id'] != VEHICLE_ID or roster['descriptor_sha256'] != self.expected['compact_descr_sha256']):
            raise RuntimeError('actual native roster does not describe the own Account/Vehicle')
        calls_ready = self.callbacks_ready()
        ready = bool(calls_ready and value['in_world'] is True and value['space_id'] == SPACE_ID
            and value['space_load_progress'] == 1.0 and value['arena_present'] is True
            and value['steps_till_init'] == 0 and value['user_sees_world'] is True
            and value['world_draw_enabled'] is True and value['vehicle_present'] is True
            and vehicle['in_world'] is True and vehicle['is_player'] is True and vehicle['is_started'] is True
            and vehicle['avatar_descriptor_same'] is True and vehicle['appearance_original'] is True
            and vehicle['model_count'] == 4 and len(vehicle['models']) == 4
            and all(row['present'] is True and row['visible'] is True for row in vehicle['models'])
            and vehicle['entity_model_is_chassis'] is True and roster is not None
            and vehicle['battle_original'] is True and vehicle['battle_component_visible'] is True
            and vehicle['battle_movie_present'] is True and vehicle['turret_sound_initialized'] is True)
        if not ready:
            if self.png_requested_at is not None:
                raise RuntimeError('native world lost readiness while screenshot was pending')
            self.ready_since = self.last_ready = None
            self.ready_samples = 0
            return False
        if self.last_ready is not None and now - self.last_ready > MAX_READY_GAP:
            raise RuntimeError('native world ready sample gap exceeded')
        if self.ready_since is None:
            self.ready_since = now
        self.last_ready, self.ready_samples = now, self.ready_samples + 1
        if self.ready_samples < 3 or now - self.ready_since < MIN_READY_SECONDS:
            return False
        if self.png_requested_at is None:
            self.native.request()
            self.png_requested_at = self.advances
            _emit(self.record, 'arena_vehicle_screenshot_requested', advance=self.advances,
                  observed_at=now, basename=BASENAME, writer='BigWorld.screenShot', pixel_acceptance='NOT_RUN')
            return False
        screenshot = self.native.screenshot()
        if screenshot is None:
            if self.advances - self.png_requested_at >= MAX_PNG_ADVANCES:
                raise RuntimeError('native arena screenshot was not written within observation budget')
            return False
        if (type(screenshot) is not dict or screenshot.get('basename') != BASENAME
                or screenshot.get('png_container_valid') is not True):
            raise ValueError('actual owned PNG container proof required')
        _emit(self.record, 'arena_vehicle_screenshot', advance=self.advances, observed_at=now, **screenshot)
        self.complete, self.active = True, False
        _emit(self.record, 'arena_vehicle_complete', advance=self.advances,
              observation_index=value['observation_index'], avatar_owner_id=self.avatar_owner,
              vehicle_owner_id=self.vehicle_owner, repository_owner_id=self.repository,
              ready_samples=self.ready_samples, ready_since=self.ready_since, observed_at=now,
              original_callback_ids=[pair['returned']['call_id'] for pair in self.pairs],
              geometry_sequence=self.geometry['sequence'], world_loaded_observed=True,
              native_pixel_acceptance='NOT_RUN', gameplay_acceptance='NOT_RUN',
              clean_teardown_acceptance='NOT_RUN', compatibility_acceptance=False)
        return True


def arm(record, settings):
    global _run, _arm_attempted
    if _arm_attempted or _closing:
        raise RuntimeError('arena Vehicle scenario already armed or closing')
    _arm_attempted = True
    _run = _Scenario(record, _Native(record, settings))


def note_avatar_call(phase, method, source_line, offset, call_id, owner_id, entity_id, space_id):
    if _run is None or _closing:
        return False
    return _run.note('avatar', phase, method, source_line, offset, call_id, owner_id, entity_id, space_id)


def note_vehicle_call(phase, method, source_line, offset, call_id, owner_id, entity_id, space_id):
    if _run is None or _closing:
        return False
    return _run.note('vehicle', phase, method, source_line, offset, call_id, owner_id, entity_id, space_id)


def note_geometry_mapped(space_id, path):
    if _run is None or _closing:
        return False
    return _run.note_geometry(space_id, path)


def advance(record):
    if _run is None or _closing:
        return False
    try:
        return _run.advance()
    except Exception as error:
        _run.active = False
        _emit(record, 'arena_vehicle_error', advance=_run.advances,
              error_type=type(error).__name__, completion=False, compatibility_acceptance=False)
        raise


def fini(record, native_cleanup):
    global _closing, _finished_cleanup
    if _finished_cleanup:
        if _cleanup_errors:
            raise RuntimeError('arena Vehicle cleanup previously failed: ' + ', '.join(_cleanup_errors))
        return
    _closing = True
    for name, function in (('before_entities', arena_bootstrap.fini_before_entities),
                           ('native_hangar_cleanup', native_cleanup),
                           ('after_entities', arena_bootstrap.fini_after_entities)):
        failed = None
        try:
            function()
        except Exception as error:
            failed = type(error).__name__
            _cleanup_errors.append(name + ':' + failed)
        try:
            _emit(record, 'arena_vehicle_cleanup', stage=name, outcome='FAIL' if failed else 'PASS', error_type=failed)
        except Exception as error:
            _cleanup_errors.append(name + ':record:' + type(error).__name__)
    _finished_cleanup = True
    if _cleanup_errors:
        raise RuntimeError('arena Vehicle cleanup failed: ' + ', '.join(_cleanup_errors))
