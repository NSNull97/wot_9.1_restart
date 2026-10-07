# -*- coding: utf-8 -*-
"""Explicit #717 crew display/denial diagnostic; never quits or mutates inventory.

The caller opts in and drives advance from its existing observation callback.
Only the original carousel selection and the verified installed denial binding
are invoked. Native pixels require separate human review after file validation.
"""
import binascii
import hashlib
import json
import math
import os
import re
import struct
import time
import zlib

VERSION = 1
MAX_ADVANCES = 600
MAX_OBSERVATIONS = 3
MAX_PNG_BYTES = 16 * 1024 * 1024
EXPECTED_COMPACTS = (
    '926254dfdbc7acf5a5d0c163d57642c24105da3ab21a7255236060e9534b70b5',
    'e4c85b2b116b96eff5d68aa8df2e509370f923843def67331478e4b62309b76d',
)
EXPORT_EVIDENCE = 'local/evidence/20261005-p02-ms1-crew/native-ms1-crew-export01.json'
SCREENSHOTS = ('crew_ms1', 'crew_denied')
_scenario = None
try:
    integer_types = (int, long)
    string_types = (str, unicode)
except NameError:
    integer_types = (int,)
    string_types = (str,)


def _now():
    return time.monotonic() if hasattr(time, 'monotonic') else time.clock()


def _integer(value, lower, upper):
    if type(value) not in integer_types or not lower <= value <= upper:
        raise ValueError('bounded native integer required')
    return value


def checked_snapshot(value):
    """Compare actual probe output with the two measured native export hashes."""
    if (type(value) is not dict or len(value) > 24 or value.get('ready') is not True
            or value.get('selected_ms1') is not True or value.get('selected_inventory_id') != 1
            or value.get('tankmen_count') != 2 or value.get('ms1_assigned_ids') != [1, 2]
            or value.get('is7_assigned_count') != 0 or value.get('issues') != []
            or value.get('inventory_mutation_requested') is not False
            or value.get('selection_changed_by_observer') is not False):
        raise ValueError('actual assigned crew is not ready for this diagnostic')
    _integer(value.get('database_id'), 1, 2147483647)
    rows, vehicles = value.get('tankmen'), value.get('vehicles')
    if type(rows) is not list or len(rows) != 2 or type(vehicles) is not list or len(vehicles) != 2:
        raise ValueError('exactly two actual tankmen and vehicles required')
    for index, row in enumerate(rows):
        if (type(row) is not dict or len(row) > 32 or row.get('inventory_id') != index + 1
                or row.get('vehicle_inventory_id') != 1 or row.get('vehicle_slot_index') != index
                or row.get('is_in_tank') is not True or row.get('original_parse_repack_equal') is not True
                or row.get('compact_descr_sha256') != EXPECTED_COMPACTS[index]):
            raise ValueError('native tankman identity, assignment or compact differs from measured export')
        compact = row.get('compact_descr_hex')
        if not isinstance(compact, string_types) or re.match(r'\A[0-9a-f]{50}\Z', compact) is None:
            raise ValueError('expected twenty-five measured compact bytes')
        if hashlib.sha256(binascii.unhexlify(compact)).hexdigest() != EXPECTED_COMPACTS[index]:
            raise ValueError('native compact bytes do not match measured hash')
    for index, vehicle in enumerate(vehicles):
        if (type(vehicle) is not dict or len(vehicle) > 12 or vehicle.get('inventory_id') != index + 1
                or vehicle.get('type_compact_descr') != (3329, 7169)[index]):
            raise ValueError('original two-vehicle inventory changed')
        slots = vehicle.get('crew')
        if type(slots) is not list or len(slots) != (2, 5)[index]:
            raise ValueError('original crew capacity changed')
        for slot_index, slot in enumerate(slots):
            expected_id = slot_index + 1 if index == 0 else None
            expected_sha = EXPECTED_COMPACTS[slot_index] if index == 0 else None
            if (type(slot) is not dict or len(slot) > 8 or slot.get('slot_index') != slot_index
                    or slot.get('tankman_inventory_id') != expected_id
                    or slot.get('tankman_compact_descr_sha256') != expected_sha):
                raise ValueError('native vehicle crew references changed')
    stable = dict(value)
    stable.pop('observation_index', None)
    raw = json.dumps(stable, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False)
    if len(raw) > 32768:
        raise ValueError('crew comparison exceeds bounded record size')
    return hashlib.sha256(raw.encode('ascii')).hexdigest()


def png_evidence(path, basename):
    """Validate a complete bounded PNG container; pixel interpretation is separate."""
    size = os.path.getsize(path)
    if size > MAX_PNG_BYTES:
        raise ValueError('native screenshot exceeds byte budget')
    if size < 45:
        return None
    with open(path, 'rb') as stream:
        payload = stream.read(MAX_PNG_BYTES + 1)
    if len(payload) != size:
        raise ValueError('native screenshot changed while reading')
    if payload[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('native screenshot is not PNG')
    if payload[-12:] != b'\x00\x00\x00\x00IEND\xaeB`\x82':
        return None
    offset, chunks, image_data, dimensions = 8, 0, 0, None
    while offset < size:
        if offset + 12 > size or chunks >= 1024:
            raise ValueError('PNG chunk budget or framing exceeded')
        length = struct.unpack('>I', payload[offset:offset + 4])[0]
        end = offset + length + 12
        if end > size:
            raise ValueError('PNG chunk outside bounded file')
        kind = payload[offset + 4:offset + 8]
        body = payload[offset + 8:end - 4]
        crc = struct.unpack('>I', payload[end - 4:end])[0]
        if (zlib.crc32(kind + body) & 0xffffffff) != crc:
            raise ValueError('PNG chunk checksum mismatch')
        if chunks == 0:
            if kind != b'IHDR' or length != 13:
                raise ValueError('PNG IHDR required first')
            width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', body)
            depths = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
            if (not 1 <= width <= 16384 or not 1 <= height <= 16384
                    or depth not in depths.get(color, ())
                    or compression != 0 or filtering != 0 or interlace not in (0, 1)):
                raise ValueError('unsupported bounded PNG header')
            dimensions = [width, height]
        elif kind == b'IHDR':
            raise ValueError('duplicate PNG header')
        if kind == b'IDAT':
            image_data += length
        if kind == b'IEND' and (length != 0 or end != size or not image_data):
            raise ValueError('PNG terminator or image data invalid')
        chunks += 1
        offset = end
    return {'basename': basename, 'path': path, 'bytes': size,
            'sha256': hashlib.sha256(payload).hexdigest(), 'dimensions': dimensions,
            'png_container_valid': True, 'native_pixels_review': 'NOT_RUN'}


class _Native(object):
    def __init__(self, settings):
        from project_preferences import owned
        import Settings
        directory = settings['screenshot_dir']
        if not os.path.isabs(directory) or not os.path.isdir(directory):
            raise ValueError('existing absolute screenshot directory required')
        self.directory = owned(directory, settings['local_root'])
        if self.directory != owned(os.path.join(settings['trace_dir'], 'screenshots'), settings['local_root']):
            raise ValueError('screenshot directory differs from owned trace')
        configured = Settings.g_instance.engineConfig.readString('screenShot/path')
        if (not os.path.isabs(configured)
                or os.path.normcase(os.path.realpath(configured)) != self.directory):
            raise ValueError('native screenshot destination differs from reviewed settings')
        self.requested = set()

    def context(self):
        import BigWorld
        from ConnectionManager import connectionManager
        from gui.shared import g_itemsCache
        from gui.WindowsManager import g_windowsManager
        from gui.Scaleform.framework import ViewTypes
        from gui.Scaleform.Waiting import Waiting
        from CurrentVehicle import g_currentVehicle
        player = BigWorld.player()
        if player is None or not connectionManager.isConnected() or not g_itemsCache.isSynced():
            raise RuntimeError('diagnostic requires the real connected synced Account')
        manager = g_windowsManager.window.containerManager
        page = manager.getContainer(ViewTypes.LOBBY_SUB).getView()
        if (type(page).__name__ != 'Hangar' or page.settings.alias != 'hangar'
                or page.flashObject is None or Waiting.isVisible()):
            raise RuntimeError('original Hangar is not ready for a diagnostic action')
        carousel, crew = page.tankCarousel, page.crewPanel
        if (type(carousel).__name__ != 'TankCarousel' or type(crew).__name__ != 'Crew'
                or carousel.flashObject is None or crew.flashObject is None):
            raise RuntimeError('original carousel and crew are not Flash-bound')
        vehicle = g_itemsCache.items.getVehicle(1)
        if vehicle is None or vehicle.intCD != 3329 or vehicle.descriptor.type.name != 'ussr:MS-1':
            raise RuntimeError('actual inventory MS-1 is unavailable')
        self.carousel, self.crew = carousel, crew
        stats = g_itemsCache.items.stats
        total = g_itemsCache.items.getAccountDossier().getTotalStats()
        return {'database_id': _integer(player.databaseID, 1, 2147483647),
                'hangar_owner': id(page), 'crew_owner': id(crew),
                'selected_inventory_id': g_currentVehicle.invID,
                'resources': [stats.credits, stats.gold, stats.freeXP],
                'statistics': [total.getBattlesCount(), total.getWinsCount(),
                               total.getLossesCount(), total.getDrawsCount()]}

    def select_ms1(self):
        self.carousel.vehicleChange(1)

    def observe(self, record):
        import ms1_crew_probe
        return ms1_crew_probe.observe(record)

    def deny_unload(self, identity):
        import crew_capabilities
        from gui.Scaleform.daapi.view.lobby.hangar.Crew import Crew
        guard = crew_capabilities._guard
        if guard is None or not guard.active or type(self.crew) is not Crew:
            raise RuntimeError('verified crew denial policy must be active before diagnostic invocation')
        bindings = [row for row in guard.bindings if row[0] is Crew and row[1] == 'unloadTankman']
        if len(bindings) != 1 or Crew.__dict__['unloadTankman'] is not bindings[0][3]:
            raise RuntimeError('crew denial binding differs from installed policy')
        _integer(identity, 1, 1)
        self.crew.unloadTankman(identity)

    def _entries(self):
        names = os.listdir(self.directory)
        if len(names) > 128:
            raise ValueError('screenshot directory exceeds bounded entry count')
        return names

    def request(self, basename):
        import BigWorld
        if basename not in SCREENSHOTS or basename in self.requested:
            raise ValueError('unsupported or repeated crew screenshot basename')
        if any(name.startswith(basename + '_') for name in self._entries()):
            raise ValueError('crew screenshot basename already exists')
        self.requested.add(basename)
        BigWorld.screenShot('png', basename)

    def screenshot(self, basename):
        from project_preferences import owned
        if basename not in self.requested:
            raise RuntimeError('native screenshot was not requested')
        names = [name for name in self._entries() if re.match(
            r'\A' + re.escape(basename) + r'_[0-9]{3,10}\.png\Z', name)]
        if not names:
            return None
        if len(names) != 1:
            raise ValueError('ambiguous crew screenshot output')
        path = owned(os.path.join(self.directory, names[0]), self.directory)
        if not os.path.isfile(path) or os.path.islink(path):
            raise ValueError('native screenshot must be an owned regular file')
        return png_evidence(path, basename)


class _Scenario(object):
    def __init__(self, settings, record, native=None, clock=None):
        if not callable(record):
            raise ValueError('diagnostic recorder required')
        self.native = _Native(settings) if native is None else native
        self.record, self.clock = record, _now if clock is None else clock
        self.phase, self.advances, self.observations = 'waiting_hangar', 0, 0
        self.identity, self.fingerprint, self.ready_since = None, None, None
        self.last_time, self.completed = None, False
        self.screenshots = []
        self.emit('crew_scenario_start', expected_compact_sha256=list(EXPECTED_COMPACTS),
                  export_evidence=EXPORT_EVIDENCE, automatic_quit=False, native_pixels_review='NOT_RUN')

    def emit(self, event, **fields):
        fields.update(version=VERSION, phase=self.phase)
        self.record(event, **fields)

    def _context(self):
        current = self.native.context()
        stable = dict(current)
        stable.pop('selected_inventory_id')
        if self.identity is None:
            self.identity = stable
        elif stable != self.identity:
            raise RuntimeError('Account, original view, resources or statistics changed during crew scenario')
        return current

    def _observe(self):
        if self.observations >= MAX_OBSERVATIONS:
            raise RuntimeError('crew observation budget exhausted')
        self.observations += 1
        actual = self.native.observe(self.record)
        fingerprint = checked_snapshot(actual)
        if actual['database_id'] != self.identity['database_id']:
            raise RuntimeError('observed crew belongs to a different Account')
        if self.fingerprint is None:
            self.fingerprint = fingerprint
        elif fingerprint != self.fingerprint:
            raise RuntimeError('crew changed after denied mutation request')
        return actual

    def advance(self, observed, ready_hangar):
        if self.completed:
            return True
        if self.phase == 'error':
            raise RuntimeError('failed crew scenario cannot continue')
        self.advances += 1
        if self.advances > MAX_ADVANCES:
            raise RuntimeError('bounded crew scenario observation budget exceeded')
        now = self.clock()
        if (type(now) not in (int, float) or math.isnan(now) or math.isinf(now)
                or (self.last_time is not None and now < self.last_time)):
            raise ValueError('finite monotonic diagnostic clock required')
        self.last_time = now
        if type(ready_hangar) is not bool or type(observed) is not dict:
            raise ValueError('explicit original readiness observation required')
        if not ready_hangar:
            if self.phase not in ('waiting_hangar', 'waiting_ms1'):
                raise RuntimeError('original Hangar lost readiness during crew proof')
            self.ready_since = None
            return False
        current = self._context()
        if self.phase == 'waiting_hangar':
            self.emit('crew_scenario_action', action='select_ms1', moment='call',
                      original_handler='TankCarousel.vehicleChange', inventory_id=1)
            self.native.select_ms1()
            self.emit('crew_scenario_action', action='select_ms1', moment='return')
            self.phase, self.ready_since = 'waiting_ms1', None
            return False
        if (current['selected_inventory_id'] != 1 or observed.get('selected_inventory_id') != 1
                or observed.get('vehicle_model_loaded') is not True
                or (observed.get('vehicle') or {}).get('type_compact_descr') != 3329):
            if self.phase != 'waiting_ms1':
                raise RuntimeError('selected native MS-1 changed during crew proof')
            self.ready_since = None
            return False
        if self.phase == 'waiting_ms1':
            if self.ready_since is None:
                self.ready_since = now
            if now - self.ready_since < 2.0:
                return False
            self._observe()
            self.native.request(SCREENSHOTS[0])
            self.emit('crew_scenario_screenshot_requested', basename=SCREENSHOTS[0],
                      writer='BigWorld.screenShot', extension='png')
            self.phase = 'waiting_crew_png'
        elif self.phase in ('waiting_crew_png', 'waiting_warning_png'):
            basename = SCREENSHOTS[0] if self.phase == 'waiting_crew_png' else SCREENSHOTS[1]
            proof = self.native.screenshot(basename)
            if proof is None:
                return False
            self.screenshots.append(proof)
            self.emit('crew_scenario_screenshot', screenshot=proof)
            if self.phase == 'waiting_crew_png':
                self.emit('crew_scenario_action', action='deny_unload', moment='call',
                          callback='Crew.unloadTankman', inventory_id=1,
                          origin='explicit_diagnostic_of_installed_UI_policy')
                self.native.deny_unload(1)
                self.emit('crew_scenario_action', action='deny_unload', moment='return')
                self._observe()
                self.phase, self.ready_since = 'waiting_warning', now
            else:
                self._observe()
                self.phase, self.completed = 'complete', True
                self.emit('crew_scenario_complete', observations=self.observations,
                          screenshots=len(self.screenshots), crew_unchanged=True,
                          native_pixels_review='NOT_RUN', user_manual_acceptance='NOT_RUN',
                          automatic_quit=False, database_id=self.identity['database_id'])
                return True
        elif self.phase == 'waiting_warning':
            if now - self.ready_since >= 1.0:
                self.native.request(SCREENSHOTS[1])
                self.emit('crew_scenario_screenshot_requested', basename=SCREENSHOTS[1],
                          writer='BigWorld.screenShot', extension='png')
                self.phase = 'waiting_warning_png'
        else:
            raise RuntimeError('unsupported crew diagnostic phase')
        return False


def advance(record, settings, observed, ready_hangar):
    """Explicit opt-in caller drives this; True means data/files, not reviewed pixels."""
    global _scenario
    if _scenario is None:
        _scenario = _Scenario(settings, record)
    try:
        return _scenario.advance(observed, ready_hangar)
    except Exception as error:
        _scenario.phase = 'error'
        _scenario.emit('crew_scenario_error', error_type=type(error).__name__)
        raise


def state():
    if _scenario is None:
        return None
    return {'version': VERSION, 'phase': _scenario.phase, 'complete': _scenario.completed,
            'advances': _scenario.advances, 'observations': _scenario.observations}
