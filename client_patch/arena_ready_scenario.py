# -*- coding: utf-8 -*-
"""Opt-in original #717 PREBATTLE observation; no RPC, input, GUI or clock writes.

The server owns the phase/deadline. Original Python/Flash callbacks execute
themselves; the profiler queues only copied primitives. Pixels and transport
are independently reviewed after the process exits normally.
"""
import hashlib
import os

import arena_bootstrap
import arena_entry_probe as probe
import arena_vehicle_scenario as vehicle
from ms1_crew_scenario import _Native as ScreenshotNative, _now

VERSION = 1
MAX_ADVANCES = 239
MAX_TIMER_PENDING, MAX_TIMER_NOTES = 256, 2048
MIN_COUNTDOWN_SECONDS, MIN_DISTINCT_SECONDS = 6.0, 3
MAX_GAP, MAX_PNG_ADVANCES = 3.0, 15
SCREENSHOTS = ('arena_ready_early', 'arena_ready_late')
TIMER_METHODS = {
    '__onSetArenaTime': (835, (47,)), '__setArenaTime': (841, (27, 127, 1045)),
    '__callEx': (940, (23,)), 'call': (125, (62,)),
    'afterCreate': (319, (1606,)), 'beforeDelete': (485, (717,)),
}
GUI_METHODS = (
    ('_Battle__onSetArenaTime', '__onSetArenaTime', 835, 1, '2cca4b95e150025697b993d7fab714670996c2ec1664f0a205edffca33d970c9'),
    ('_Battle__setArenaTime', '__setArenaTime', 841, 1, '1153f0c83fb9d88e5ad9ecda512af973bc0aaae5461a937c63622edfd776fafa'),
    ('_Battle__callEx', '__callEx', 940, 3, '0b23873c9a9040425d318c32697e67263e78c7f8fe381dbd506c5ca7379da02f'),
    ('afterCreate', 'afterCreate', 319, 1, '50092d5867b0b6d3f60223bb31f7d809b08323a42eb32819919d610fadb33109'),
    ('beforeDelete', 'beforeDelete', 485, 1, '7bba4fb2c4bb5fa21fbe691dda2845d30af2ea794faa66657097861c3d0a75a1'),
)
LIGHT_METHODS = (
    ('__init__', '__init__', 30, 1, '5e9110dbdeddb277c56954019375478a08c753003de6bae983b12924c40e0181'),
    ('start', 'start', 65, 1, '5f9f1e7340f6c1f772cec45e190f99b8c17e3da4ff7605286371809136463171'),
    ('destroy', 'destroy', 70, 1, '2f29476baa7a1643d91e5a225858912f4efe455c4ee3fd5851b07ee8385874b4'),
    ('isEnabled', 'isEnabled', 82, 1, 'cd191e3a1561de10795069d3df295b7eaff3f51c14695fba12bee31648826dce'),
)
SOURCE_HASHES = (
    ('res/scripts/client/gui/Scaleform/Battle.pyc', 'aa43bc6b7e1f7ae9e2bba03fa527a9e6ce95a5d41ef23f26785b1490cd6f38de'),
    ('res/scripts/client/gui/Scaleform/Flash.pyc', '059aad4f6ed0d3ce5b82e8a819dd0f0181e403ef25c803bfc7e452a621495dc4'),
    ('res/scripts/client/LightFx/LightManager.pyc', '1cab41ea55634ec05081bdb81902bd8dd781851b7b68042636ccc914d4d4a348'),
    ('res/scripts/client/game.pyc', '2f2057748cbbbaefe21c5fd434cc1492bd08521f705f43832e45e493af6896c1'),
)
_run = _native = None
_arm_attempted = _closing = _finished_cleanup = False
_cleanup_errors = []


def _emit(record, event, **fields):
    fields['version'] = VERSION
    return probe._emit(record, event, fields)


def _audit_sources():
    root, rows = os.path.realpath(os.getcwd()), []
    for relative, expected in SOURCE_HASHES:
        path = os.path.join(root, *relative.split('/'))
        if (not os.path.realpath(path).startswith(root + os.sep) or os.path.islink(path)
                or not os.path.isfile(path) or not 1 <= os.path.getsize(path) <= 1048576):
            raise ValueError('bounded original countdown source required')
        with open(path, 'rb') as stream:
            raw = stream.read(1048577)
        digest = hashlib.sha256(raw).hexdigest()
        if not 1 <= len(raw) <= 1048576 or digest != expected:
            raise ValueError('original countdown source hash differs: ' + relative)
        rows.append({'relative_path': relative, 'bytes': len(raw), 'sha256': digest})
    return rows


def _bindings():
    from gui.Scaleform.Battle import Battle
    from gui.Scaleform.Flash import Flash
    from LightFx import LightManager
    for row in GUI_METHODS:
        probe._code_contract(getattr(Battle, row[0]), row, 'scripts/client/gui/Scaleform/Battle.py')
    probe._code_contract(Flash.call, ('call', 'call', 125, 3,
        '774d6c5ec04c35ae5e6c929f29e9246e0d0abe98d7ee7a510154a005946ba035'),
        'scripts/client/gui/Scaleform/Flash.py')
    for row in LIGHT_METHODS:
        probe._code_contract(getattr(LightManager.LightManager, row[0]), row,
                             'scripts/client/LightFx/LightManager.py')


class _Pixels(ScreenshotNative):
    def request(self, basename):
        import BigWorld
        if basename not in SCREENSHOTS or basename in self.requested:
            raise ValueError('unsupported or repeated countdown screenshot')
        names = self._entries()
        if any(not any(name.startswith(prefix + '_') and name.endswith('.png')
                       for prefix in self.requested) for name in names):
            raise ValueError('countdown screenshot directory has an unowned file')
        if any(name.startswith(basename + '_') for name in names):
            raise ValueError('countdown screenshot must not overwrite a file')
        self.requested.add(basename)
        BigWorld.screenShot('png', basename)


class _Native(vehicle._Native):
    def __init__(self, record, settings):
        vehicle.space._Native.__init__(self, record)
        self.pixels, self.light, self.light_module = _Pixels(settings), None, None

    def initialize(self):
        sources = _audit_sources()
        _bindings()
        vehicle._Native.initialize(self)
        self.countdown_sources = sources
        from LightFx import LightManager
        if LightManager.g_instance is not None:
            raise RuntimeError('countdown refuses an existing LightManager singleton')
        self.light_module = LightManager
        _emit(self.record, 'arena_ready_light', phase='init_begin')
        self.light = LightManager.LightManager()
        if not arena_bootstrap._exact_instance(self.light, LightManager.LightManager):
            raise RuntimeError('LightManager constructor returned a foreign class')
        LightManager.g_instance = self.light
        self.light.start()
        _emit(self.record, 'arena_ready_light', phase='init_return', owner_id=id(self.light),
              enabled=probe._boolean(self.light.isEnabled(), 'LightManager.isEnabled'),
              enabled_assigned_by_diagnostic=False)

    def light_fini(self):
        if self.light is None:
            return
        _bindings()
        if self.light_module.g_instance is not self.light:
            raise RuntimeError('owned LightManager singleton was replaced')
        _emit(self.record, 'arena_ready_light', phase='destroy_begin', owner_id=id(self.light))
        self.light.destroy()
        self.light_module.g_instance = None
        _emit(self.record, 'arena_ready_light', phase='destroy_return', owner_id=id(self.light))
        self.light = self.light_module = None

    def timer(self):
        import Avatar
        import BigWorld
        import BattleReplay
        from gui.WindowsManager import g_windowsManager
        from gui.Scaleform.Battle import Battle
        player, battle = BigWorld.player(), g_windowsManager.battleWindow
        result = {'present': False}
        if type(player) is not Avatar.PlayerAvatar or battle is None:
            return result
        if not arena_bootstrap._exact_instance(battle, Battle):
            raise RuntimeError('original Battle instance required')
        arena = player.arena
        if arena is None or battle._Battle__arena is not arena:
            raise RuntimeError('original timer belongs to another arena')
        if self.light is None or self.light_module.g_instance is not self.light:
            raise RuntimeError('original PREBATTLE service no longer owned')
        server_time = probe._number(BigWorld.serverTime(), -1e9, 1e9, 'native serverTime')
        end = probe._number(arena.periodEndTime, -1e9, 1e9, 'periodEndTime')
        return dict(present=True, owner_id=id(battle), arena_owner_id=id(arena),
            period=probe._integer(arena.period, 0, 4, 'period'),
            period_end_time=end, period_length=probe._number(arena.periodLength, 0, 3600, 'periodLength'),
            period_additional_info_is_none=arena.periodAdditionalInfo is None,
            server_time=server_time, native_time=probe._number(BigWorld.time(), 0, 1e10, 'native time'),
            remaining_exact=end-server_time, remaining_seconds=max(0, int(end-server_time)),
            timer_visible=probe._boolean(battle._Battle__isTimerVisible, 'original timer visible'),
            replay_playing=probe._boolean(BattleReplay.g_replayCtrl.isPlaying, 'replay isPlaying'),
            replay_recording=probe._boolean(BattleReplay.g_replayCtrl.isRecording, 'replay isRecording'),
            movie_present=battle.movie is not None)

    def request(self, basename):
        self.pixels.request(basename)

    def screenshot(self, basename):
        return self.pixels.screenshot(basename)


def _data_copy(method, phase, data):
    """Do not retain frames, lists or arbitrary rich original GUI objects."""
    if type(data) is not dict:
        raise ValueError('timer data must be an exact dictionary')
    if method in ('afterCreate', 'beforeDelete') or method == '__setArenaTime' and phase == 'call':
        if data:
            raise ValueError('unexpected timer entry data')
        return {}
    if method == '__setArenaTime':
        if set(data) != set(('period', 'remaining_exact', 'remaining_seconds')):
            raise ValueError('unexpected original timer locals')
        if all(value is None for value in data.values()):
            return dict(data)
        return dict(period=probe._integer(data['period'], 0, 4, 'timer period'),
            remaining_exact=probe._number(data['remaining_exact'], -1e9, 1e9, 'timer exact'),
            remaining_seconds=probe._integer(data['remaining_seconds'], 0, 3600, 'timer integer'))
    if method == '__onSetArenaTime':
        if set(data) != set(('period_args',)):
            raise ValueError('period callback arguments required')
        args = data['period_args']
        if type(args) not in (list, tuple) or len(args) != 4 or args[3] is not None:
            raise ValueError('bounded own native period tuple required')
        return {'period_args': [probe._integer(args[0], 0, 4, 'period'),
            probe._number(args[1], -1e9, 1e9, 'period end'),
            probe._number(args[2], 0, 3600, 'period length'), None]}
    if set(data) != set(('method_name', 'args', 'parent_call_id', 'parent_owner_id')):
        raise ValueError('exact original Flash projection required')
    prefix = 'battle.' if method == 'call' else ''
    name = probe._text(data['method_name'], 64, 'Flash method')
    if name not in (prefix + 'timerBig.setTimer', prefix + 'timerBar.setTotalTime'):
        raise ValueError('unsupported countdown Flash method')
    if type(data['args']) not in (list, tuple) or not 1 <= len(data['args']) <= 3:
        raise ValueError('bounded original Flash args required')
    args = []
    for value in data['args']:
        if type(value) in probe.string_types:
            args.append(probe._text(value, 256, 'Flash text'))
        else:
            args.append(probe._integer(value, 0, 3600, 'Flash remaining seconds'))
    return {'method_name': name, 'args': args,
        'parent_call_id': probe._integer(data['parent_call_id'], 1, 2147483647, 'parent call'),
        'parent_owner_id': probe._integer(data['parent_owner_id'], 1, 0x7fffffffffffffff, 'parent owner')}


class _Scenario(vehicle._Scenario):
    def __init__(self, record, native, clock=None):
        # Reuse the frozen Entity callback matcher; retain no Entity/UI refs.
        self.record, self.native, self.clock = record, native, _now if clock is None else clock
        self.advances, self.sequence = 0, 0
        self.notes, self.open_calls, self.pairs, self.seen = [], {}, [], set()
        self.note_error = None
        self.active, self.complete, self.geometry = False, False, None
        self.avatar_owner = self.vehicle_owner = None
        self.ready_since = self.last_ready = self.last_time = None
        self.ready_samples = 0
        self.timer_notes, self.timer_open, self.timer_seen = [], {}, set()
        self.timer_count, self.timer_error, self.timer_pairs, self.ticks = 0, None, [], []
        self.period_event, self.timer_identity, self.first, self.pending_png = None, None, None, None
        self.last_server_time = None
        self.screenshots, self.png_advance = [], None
        value, identity = native.account()
        if (value['player_is_original_account'] is not True or value['native_connected'] is not True
                or value['repository_present'] is not True or not vehicle._int(value['repository_owner_id'], 1)
                or value['entity_id'] != identity['entity_id'] or value['name'] != identity['name']
                or identity['database_id'] != 1):
            raise RuntimeError('actual connected own primary Account required')
        self.account, self.repository = dict(identity), value['repository_owner_id']
        self.expected = native.expected_vehicle()
        native.initialize()
        self.active = True
        _emit(record, 'arena_ready_armed', account=self.account, expected_vehicle=self.expected,
            repository_owner_id=self.repository, expected_avatar_id=vehicle.AVATAR_ID,
            expected_vehicle_id=vehicle.VEHICLE_ID, expected_space_id=1,
            sources=native.sources, countdown_sources=native.countdown_sources,
            max_advances=MAX_ADVANCES, minimum_seconds=MIN_COUNTDOWN_SECONDS,
            screenshot_basenames=list(SCREENSHOTS), native_entity_created_by_scenario=False,
            clock_modified=False, gui_invoked=False, computer_input=False)

    def note_timer(self, phase, method, line, offset, call_id, owner_id, data):
        if not self.active or type(method) not in probe.string_types or method not in TIMER_METHODS:
            return False
        try:
            if phase not in ('call', 'return') or type(phase) not in probe.string_types:
                raise ValueError('original callback phase required')
            if len(self.timer_notes) >= MAX_TIMER_PENDING or self.timer_count >= MAX_TIMER_NOTES:
                raise ValueError('timer callback note budget exhausted')
            copied = _data_copy(method, phase, data)
            row = dict(phase=phase, method=method, source_line=probe._integer(line, 1, 100000, 'line'),
                offset=probe._integer(offset, -1, 100000, 'offset'),
                call_id=probe._integer(call_id, 1, 2147483647, 'call ID'),
                owner_id=probe._integer(owner_id, 1, 0x7fffffffffffffff, 'owner ID'), data=copied,
                noted_at=probe._number(self.clock(), 0, 1e10, 'diagnostic note clock'))
            self.timer_count += 1
            row['sequence'] = self.timer_count
            self.timer_notes.append(row)
            return True
        except (ValueError, TypeError, UnicodeError) as error:
            if self.timer_error is None:
                self.timer_error = 'invalid passive timer note: ' + type(error).__name__
            return False

    def drain_timer(self):
        if self.timer_error:
            raise RuntimeError(self.timer_error)
        pending, self.timer_notes = self.timer_notes, []
        for note in pending:
            _emit(self.record, 'arena_ready_timer_callback', **note)
            method, call_id = note['method'], note['call_id']
            line, returns = TIMER_METHODS[method]
            if note['source_line'] != line or note['offset'] not in ((-1,) if note['phase'] == 'call' else returns):
                raise RuntimeError('original timer callback did not return normally')
            if method == 'beforeDelete':
                raise RuntimeError('Battle destroyed before countdown completed')
            if note['phase'] == 'call':
                if call_id in self.timer_seen:
                    raise RuntimeError('duplicate timer callback identity')
                self.timer_seen.add(call_id)
                if method in ('__callEx', 'call'):
                    parent = self.timer_open.get(note['data']['parent_call_id'])
                    if (parent is None or parent['method'] != ('__setArenaTime' if method == '__callEx' else '__callEx')
                            or parent['owner_id'] != note['owner_id']
                            or note['data']['parent_owner_id'] != note['owner_id']):
                        raise RuntimeError('timer Flash callback has no original same-owner parent')
                self.timer_open[call_id] = note
                continue
            entry = self.timer_open.pop(call_id, None)
            if entry is None or any(entry[k] != note[k] for k in ('method', 'source_line', 'owner_id')):
                raise RuntimeError('timer return has no exact original entry')
            pair = {'entry': entry, 'returned': note}
            if method in ('__callEx', 'call'):
                old, new = entry['data'], note['data']
                name = old['method_name'] if method == 'call' else 'battle.' + old['method_name']
                if (any(old[k] != new[k] for k in ('method_name', 'parent_call_id', 'parent_owner_id'))
                        or new['args'] != [name] + old['args']):
                    raise RuntimeError('original Flash args mutation differs from pinned call')
                children = [p for p in self.timer_pairs if p['entry']['method'] == 'call'
                            and p['entry']['data']['parent_call_id'] == call_id]
                if method == '__callEx' and (len(children) != 1 or
                        children[0]['entry']['data']['args'] != old['args'] or
                        children[0]['returned']['data']['args'] != new['args']):
                    raise RuntimeError('original timer bridge lacks matching Flash invocation')
            elif method == '__onSetArenaTime':
                if entry['data'] != note['data']:
                    raise RuntimeError('original period callback arguments changed')
                if note['data']['period_args'][0] == 2:
                    if self.period_event is not None:
                        raise RuntimeError('duplicate PREBATTLE event')
                    self.period_event = note
            elif method == '__setArenaTime' and note['offset'] == 1045 and note['data']['period'] == 2:
                data = note['data']
                children = [p for p in self.timer_pairs if p['entry']['method'] == '__callEx'
                            and p['entry']['data']['parent_call_id'] == call_id]
                by_name = dict((p['entry']['data']['method_name'], p) for p in children)
                if len(children) != 2 or set(by_name) != set(('timerBig.setTimer', 'timerBar.setTotalTime')):
                    raise RuntimeError('PREBATTLE timer lacks both original Flash updates')
                big = by_name['timerBig.setTimer']['entry']['data']['args']
                bar = by_name['timerBar.setTotalTime']['entry']['data']['args']
                if (data['remaining_seconds'] != max(0, int(data['remaining_exact'])) or
                        len(big) != 2 or type(big[0]) not in probe.string_types or
                        big[1] != data['remaining_seconds'] or bar != [data['remaining_seconds']]):
                    raise RuntimeError('original calculated countdown and Flash values differ')
                if len(self.ticks) >= 128:
                    raise RuntimeError('countdown tick budget exhausted')
                if self.ticks and (note['owner_id'] != self.ticks[-1]['owner_id'] or
                        data['remaining_seconds'] > self.ticks[-1]['remaining_seconds']):
                    raise RuntimeError('native countdown owner changed or integer increased')
                self.ticks.append(dict(call_id=call_id, owner_id=note['owner_id'],
                    noted_at=note['noted_at'], remaining_exact=data['remaining_exact'],
                    remaining_seconds=data['remaining_seconds'],
                    flash_call_ids=[p['returned']['call_id'] for p in children]))
            self.timer_pairs.append(pair)

    def world_ready(self, value, current):
        if (value['native_connected'] is not True or value['repository_present'] is not True
                or value['repository_owner_id'] != self.repository):
            raise RuntimeError('original session/repository changed')
        if value['player_is_original_account']:
            if self.avatar_owner is not None or any(value[k] != self.account[k] for k in ('entity_id', 'name')):
                raise RuntimeError('unexpected Account replacement')
            return False
        if not value['player_present']:
            return False
        if (value['player_is_original_avatar'] is not True or value['entity_id'] != vehicle.AVATAR_ID
                or value['name'] != self.account['name'] or self.avatar_owner is not None
                and value['player_owner_id'] != self.avatar_owner):
            raise RuntimeError('original Avatar identity changed')
        self.avatar_owner = value['player_owner_id']
        if value['space_id'] not in (None, 1) or value['player_vehicle_id'] not in (None, 0, vehicle.VEHICLE_ID):
            raise RuntimeError('unexpected space or own Vehicle')
        if value['arena_present'] and (value['arena_type_id'] != 1 or value['arena_unique_id'] != 1
                or value['geometry_path'] != probe.GEOMETRY_PATH or value['arena_vehicle_count'] not in (0, 1)):
            raise RuntimeError('unexpected native arena')
        if current['vehicle_present']:
            if (current['entity_id'] != vehicle.VEHICLE_ID or current['public_name'] != self.account['name']
                    or current['health'] != self.expected['health'] or vehicle._native_flag(current['crew_active']) != 1
                    or current['team'] != 1 or current['public_descriptor_sha256'] != self.expected['compact_descr_sha256']
                    or self.vehicle_owner is not None and current['owner_id'] != self.vehicle_owner):
                raise RuntimeError('original own Vehicle identity changed')
            self.vehicle_owner = current['owner_id']
            if current['descriptor_sha256'] is not None and (current['descriptor_sha256'] != self.expected['compact_descr_sha256']
                    or current['type_compact_descr'] != 3329 or current['type_name'] != 'ussr:MS-1'):
                raise RuntimeError('original own Vehicle descriptor changed')
        roster = current['roster']
        if roster is not None and (roster['database_id'] != self.account['database_id'] or roster['name'] != self.account['name']
                or roster['team'] != 1 or roster['alive'] is not True or roster['vehicle_id'] != vehicle.VEHICLE_ID
                or roster['descriptor_sha256'] != self.expected['compact_descr_sha256']):
            raise RuntimeError('original roster differs from own account')
        return bool(self.callbacks_ready() and value['in_world'] is True and value['space_id'] == 1
            and value['space_load_progress'] == 1.0 and value['arena_present'] is True
            and value['steps_till_init'] == 0 and value['user_sees_world'] is True
            and value['world_draw_enabled'] is True and value['vehicle_present'] is True
            and current['in_world'] is True and current['is_player'] is True and current['is_started'] is True
            and current['avatar_descriptor_same'] is True and current['appearance_original'] is True
            and current['model_count'] == 4 and len(current['models']) == 4
            and all(row['present'] is True and row['visible'] is True for row in current['models'])
            and current['entity_model_is_chassis'] is True and roster is not None
            and current['battle_original'] is True and current['battle_component_visible'] is True
            and current['battle_movie_present'] is True and current['turret_sound_initialized'] is True)

    def advance(self):
        if self.complete:
            return True
        if not self.active:
            raise RuntimeError('failed countdown cannot continue')
        self.advances += 1
        if self.advances > MAX_ADVANCES:
            raise RuntimeError('countdown observation budget exhausted')
        now = probe._number(self.clock(), 0, 1e10, 'diagnostic clock')
        if self.last_time is not None and now < self.last_time:
            raise RuntimeError('diagnostic clock moved backwards')
        self.last_time = now
        self.drain()
        self.drain_timer()
        value, current, timer = self.native.observe(), self.native.vehicle(), self.native.timer()
        ready = self.world_ready(value, current)
        _emit(self.record, 'arena_ready_state', advance=self.advances, observed_at=now,
            observation=value, vehicle=current, timer=timer, world_ready=ready)
        if not ready:
            if self.first is not None:
                raise RuntimeError('world lost readiness during countdown')
            self.ready_since = self.last_ready = None
            self.ready_samples = 0
            return False
        if self.last_ready is not None and now - self.last_ready > MAX_GAP:
            raise RuntimeError('ready countdown observation gap exceeded')
        if self.ready_since is None:
            self.ready_since = now
        self.last_ready, self.ready_samples = now, self.ready_samples + 1
        if not timer.get('present') or timer['period'] != 2:
            if self.first is not None or timer.get('period', 0) > 2:
                raise RuntimeError('PREBATTLE was lost or active BATTLE unexpectedly began')
            return False
        if (timer['period_length'] != 30.0 or timer['period_additional_info_is_none'] is not True
                or timer['replay_playing'] is not False or timer['movie_present'] is not True
                or timer['timer_visible'] is not True or not 1 < timer['remaining_seconds'] <= 30
                or timer['remaining_seconds'] != max(0, int(timer['remaining_exact']))):
            raise RuntimeError('actual native countdown differs from explicit preparation policy')
        if current['roster']['avatar_ready'] is not True:
            raise RuntimeError('original arena roster has not accepted own Avatar readiness')
        identity = [timer['owner_id'], timer['arena_owner_id'], timer['period_end_time'], timer['period_length']]
        if self.timer_identity is None:
            self.timer_identity = identity
        elif self.timer_identity != identity:
            raise RuntimeError('native countdown deadline or owner changed')
        if self.last_server_time is not None and timer['server_time'] < self.last_server_time:
            raise RuntimeError('native server clock moved backwards')
        self.last_server_time = timer['server_time']
        if self.period_event is None or self.period_event['owner_id'] != timer['owner_id']:
            return False
        if self.period_event['data']['period_args'] != [2, timer['period_end_time'], 30.0, None]:
            raise RuntimeError('period listener and observed native arena differ')
        if not self.ticks or self.timer_open:
            return False
        tick = self.ticks[-1]
        if (tick['owner_id'] != timer['owner_id'] or now - tick['noted_at'] > MAX_GAP
                or not 0 <= tick['remaining_seconds'] - timer['remaining_seconds'] <= 2):
            raise RuntimeError('actual original Flash countdown is stale or differs')
        if self.ready_samples < 3 or now - self.ready_since < 2.0:
            return False
        if self.first is None:
            self.first = {'observed_at': now, 'timer': dict(timer), 'tick': dict(tick)}
            self._request(SCREENSHOTS[0], now, timer, tick)
            return False
        if timer['server_time'] < self.first['timer']['server_time']:
            raise RuntimeError('native server clock moved backwards')
        if self.pending_png is not None:
            screenshot = self.native.screenshot(self.pending_png)
            if screenshot is None:
                if self.advances - self.png_advance >= MAX_PNG_ADVANCES:
                    raise RuntimeError('native countdown screenshot budget exhausted')
                return False
            if (type(screenshot) is not dict or screenshot.get('basename') != self.pending_png
                    or screenshot.get('png_container_valid') is not True):
                raise RuntimeError('actual owned PNG proof required')
            self.screenshots.append(screenshot)
            _emit(self.record, 'arena_ready_screenshot', advance=self.advances, observed_at=now, **screenshot)
            self.pending_png = None
            if len(self.screenshots) == 2:
                self.complete, self.active = True, False
                _emit(self.record, 'arena_ready_complete', advance=self.advances, observed_at=now,
                    began_at=self.first['observed_at'], avatar_owner_id=self.avatar_owner,
                    vehicle_owner_id=self.vehicle_owner, timer_owner_id=timer['owner_id'],
                    first_tick_call_id=self.first['tick']['call_id'], last_tick_call_id=tick['call_id'],
                    period=2, period_end_time=timer['period_end_time'], screenshots=2,
                    countdown_observed=True, server_authority_acceptance='NOT_RUN',
                    native_pixel_acceptance='NOT_RUN', active_battle_acceptance='NOT_RUN',
                    clean_teardown_acceptance='NOT_RUN', compatibility_acceptance=False)
                return True
        selected = [row for row in self.ticks if row['noted_at'] >= self.first['tick']['noted_at']]
        if any(row['owner_id'] != timer['owner_id'] or row['remaining_seconds'] <= 1 for row in selected):
            raise RuntimeError('countdown tick identity or positive range changed')
        counts = [row['remaining_seconds'] for row in selected]
        if any(right > left for left, right in zip(counts, counts[1:])):
            raise RuntimeError('original countdown increased unexpectedly')
        if (len(self.screenshots) == 1 and self.pending_png is None and
                now - self.first['observed_at'] >= MIN_COUNTDOWN_SECONDS and
                tick['noted_at'] - self.first['tick']['noted_at'] >= MIN_COUNTDOWN_SECONDS and
                timer['server_time'] - self.first['timer']['server_time'] >= MIN_COUNTDOWN_SECONDS and
                len(set(counts)) >= MIN_DISTINCT_SECONDS and counts[0] - counts[-1] >= 3):
            self._request(SCREENSHOTS[1], now, timer, tick)
        return False

    def _request(self, basename, now, timer, tick):
        self.native.request(basename)
        self.pending_png, self.png_advance = basename, self.advances
        _emit(self.record, 'arena_ready_screenshot_requested', advance=self.advances, observed_at=now,
            basename=basename, timer=timer, tick_call_id=tick['call_id'], writer='BigWorld.screenShot',
            pixel_acceptance='NOT_RUN')


def arm(record, settings):
    global _run, _native, _arm_attempted
    if _arm_attempted or _closing:
        raise RuntimeError('countdown scenario already armed or closing')
    _arm_attempted = True
    _native = _Native(record, settings)
    _run = _Scenario(record, _native)


def note_avatar_call(phase, method, line, offset, call_id, owner_id, entity_id, space_id):
    if _run is None or _closing:
        return False
    return _run.note('avatar', phase, method, line, offset, call_id, owner_id, entity_id, space_id)


def note_vehicle_call(phase, method, line, offset, call_id, owner_id, entity_id, space_id):
    if _run is None or _closing:
        return False
    return _run.note('vehicle', phase, method, line, offset, call_id, owner_id, entity_id, space_id)


def note_geometry_mapped(space_id, path):
    if _run is None or _closing:
        return False
    return _run.note_geometry(space_id, path)


def note_timer_call(phase, method, line, offset, call_id, owner_id, data):
    if _run is None or _closing:
        return False
    return _run.note_timer(phase, method, line, offset, call_id, owner_id, data)


def advance(record):
    if _run is None or _closing:
        return False
    try:
        return _run.advance()
    except Exception as error:
        _run.active = False
        _emit(record, 'arena_ready_error', advance=_run.advances, error_type=type(error).__name__,
            completion=False, compatibility_acceptance=False)
        raise


def fini(record, native_cleanup):
    """Try every original cleanup, then report all failures; never swallow one."""
    global _closing, _finished_cleanup
    if _finished_cleanup:
        if _cleanup_errors:
            raise RuntimeError('countdown cleanup previously failed: ' + ', '.join(_cleanup_errors))
        return
    _closing = True
    stages = [('before_entities', arena_bootstrap.fini_before_entities),
              ('native_hangar_cleanup', native_cleanup), ('after_entities', arena_bootstrap.fini_after_entities)]
    if _native is not None:
        stages.append(('light_after_native', _native.light_fini))
    for name, function in stages:
        failed = None
        try:
            function()
        except Exception as error:
            failed = type(error).__name__
            _cleanup_errors.append(name + ':' + failed)
        try:
            _emit(record, 'arena_ready_cleanup', stage=name, outcome='FAIL' if failed else 'PASS', error_type=failed)
        except Exception as error:
            _cleanup_errors.append(name + ':record:' + type(error).__name__)
    _finished_cleanup = True
    if _cleanup_errors:
        raise RuntimeError('countdown cleanup failed: ' + ', '.join(_cleanup_errors))
