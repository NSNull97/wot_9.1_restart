# -*- coding: utf-8 -*-
"""Explicit ordinary test-service drive, preserving native input and lifetime.

This installed feature is separate from every one-shot diagnostic. It never
quits, creates an Entity, moves a vehicle, changes a clock, fills ammunition,
accepts a dialog, or calls an undecorated queue method. The server remains the
authority. Two previously owned FightButton bindings are layered here. A
separate fail-closed guard blocks the original external CAPTCHA image fetch.
"""
import hashlib
import os
import threading
import types

VERSION = 3
MS1_SHA256 = '4122429c052f5c8eb2ebeae456c775b1a368a007cf37bae8af7b3f87ff064c5c'
SHELLS = (2570, 20, 2826, 0, 3082, 0)
LIGHT_SOURCE = 'scripts/client/LightFx/LightManager.py'
LIGHT_SHA256 = '1cab41ea55634ec05081bdb81902bd8dd781851b7b68042636ccc914d4d4a348'
LIGHT_METHODS = (
    ('__init__', '__init__', 30, 1, '5e9110dbdeddb277c56954019375478a08c753003de6bae983b12924c40e0181'),
    ('start', 'start', 65, 1, '5f9f1e7340f6c1f772cec45e190f99b8c17e3da4ff7605286371809136463171'),
    ('destroy', 'destroy', 70, 1, '2f29476baa7a1643d91e5a225858912f4efe455c4ee3fd5851b07ee8385874b4'),
    ('isEnabled', 'isEnabled', 82, 1, 'cd191e3a1561de10795069d3df295b7eaff3f51c14695fba12bee31648826dce'),
)
CAPTCHA_SOURCE = 'scripts/client/account_helpers/captcha/reCAPTCHA.py'
CAPTCHA_SHA256 = '80603d41c5f7265192d69d594a8f0b3efc507a6c5ece2ddae8a03a0df19bfa56'
CAPTCHA_CODE_SHA256 = '30c326393a17c5e291b87c8bf8d07d5610bcf52409e41018eb646839714a7def'
CAPTCHA_CHAIN_SOURCES = (
    ('scripts/client/account_helpers/captcha/__init__.py',
     '5901de5110588945031846935062721d156531524a4446d75d3837af750924a0'),
    ('scripts/client/gui/game_control/captcha_control.py',
     '09ac1aa482c7394d7790a26a04281af870a3da71ef397c2c4de35865736eb334'),
    ('scripts/client/gui/Scaleform/daapi/view/dialogs/CaptchaDialog.py',
     'fb2df2f6a6ba434c40f095034521c0b828c55870d60d236cdb078880f14c9529'),
)
MAX_CAPTCHA_BLOCK_RECORDS = 32
CAPTCHA_ERROR = 'external legacy CAPTCHA is unavailable for this test service'
ERROR_NOTICE = (u'Тестовая поездка недоступна: не удалось подготовить родные службы клиента. '
                u'Вход на карту не отправлен. Подробности записаны в журнал.')
_controller = None
_captcha_guard = None
_attempted = _closing = _closed = False
_cleanup_errors = []
try:
    integer_types = (int, long)
    string_types = (str, unicode)
except NameError:
    integer_types = (int,)
    string_types = (str,)


def _emit(record, event, **fields):
    fields['version'] = VERSION
    record(event, **fields)


def _click_fields(map_id, action_name):
    """Bounded primitive DAAPI callback evidence; never render arbitrary objects."""
    fields = dict(map_id_type=type(map_id).__name__[:64],
                  action_name_type=type(action_name).__name__[:64])
    if map_id is None or type(map_id) is bool:
        fields['map_id_value'] = map_id
    elif type(map_id) in integer_types + (float,) and -65535 <= map_id <= 65535:
        fields['map_id_value'] = map_id
    else:
        fields['map_id_value'] = None
    if type(action_name) in string_types:
        fields['action_name_length'] = min(len(action_name), 65536)
        if len(action_name) <= 64 and all(char in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-' for char in action_name):
            fields['action_name_value'] = action_name
        else:
            fields['action_name_value'] = None
    else:
        fields['action_name_length'] = None
        fields['action_name_value'] = None
    return fields


def _integer(value, low, high, field):
    if type(value) not in integer_types or not low <= value <= high:
        raise ValueError('bounded native integer required: ' + field)
    return value


def _bool(value, field):
    if type(value) is not bool:
        raise ValueError('native boolean required: ' + field)
    return value


def _flat(value):
    if type(value) not in (list, tuple) or len(value) != 6:
        raise ValueError('native mounted shell layout must contain six integers')
    return tuple(_integer(v, -65535, 65535, 'shell layout') for v in value)


def _raw_sha(value):
    if type(value) is not bytes or not 1 <= len(value) <= 512:
        raise ValueError('native compact descriptor bytes required')
    return hashlib.sha256(value).hexdigest()


def _audit_sources(policy):
    rows = []
    root = os.path.normcase(os.path.realpath(os.getcwd()))
    for relative, expected in (
            ('res/' + policy.BATTLE_SOURCE[:-3] + '.pyc', policy.BATTLE_PYC_SHA256),
            ('res/' + LIGHT_SOURCE[:-3] + '.pyc', LIGHT_SHA256),
            ('res/' + CAPTCHA_SOURCE[:-3] + '.pyc', CAPTCHA_SHA256)) + tuple(
                ('res/' + source[:-3] + '.pyc', digest)
                for source, digest in CAPTCHA_CHAIN_SOURCES):
        path = os.path.join(root, *relative.split('/'))
        if (not os.path.normcase(os.path.realpath(path)).startswith(root + os.sep)
                or os.path.islink(path) or not os.path.isfile(path)
                or not 1 <= os.path.getsize(path) <= 1048576):
            raise ValueError('bounded original ordinary-drive source required')
        with open(path, 'rb') as stream:
            raw = stream.read(1048577)
        if len(raw) > 1048576 or hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('ordinary-drive original source hash mismatch')
        rows.append({'relative_path': relative, 'bytes': len(raw), 'sha256': expected})
    return rows


def _audit_originals(policy, guard):
    if type(guard) is not policy._BattleGuard or not guard.active:
        raise RuntimeError('exact installed hangar battle policy required')
    expected_names = set(row[0] for row in policy.BATTLE_METHODS)
    if set(guard.originals) != expected_names:
        raise RuntimeError('native battle original method set changed')
    for name, line, args, defaults, digest in policy.BATTLE_METHODS:
        function = guard.originals[name]
        if type(function) is not types.FunctionType:
            raise TypeError('original battle function required')
        code = getattr(function, 'func_code', getattr(function, '__code__', None))
        actual_defaults = getattr(function, 'func_defaults', getattr(function, '__defaults__', None))
        if (code.co_filename != policy.BATTLE_SOURCE or code.co_firstlineno != line
                or code.co_argcount != len(args) or code.co_varnames[:len(args)] != args
                or code.co_flags & 12 or actual_defaults != defaults
                or hashlib.sha256(code.co_code).hexdigest() != digest):
            raise RuntimeError('original #717 battle callback differs: ' + name)


def _audit_captcha(function):
    if type(function) is not types.FunctionType:
        raise TypeError('original CAPTCHA function descriptor required')
    code = getattr(function, 'func_code', getattr(function, '__code__', None))
    defaults = getattr(function, 'func_defaults', getattr(function, '__defaults__', None))
    if (code.co_filename != CAPTCHA_SOURCE or code.co_name != 'getImageSource'
            or code.co_firstlineno != 44 or code.co_argcount != 2
            or code.co_varnames[:3] != ('self', 'key', 'args')
            or code.co_flags != 71 or defaults is not None
            or hashlib.sha256(code.co_code).hexdigest() != CAPTCHA_CODE_SHA256):
        raise RuntimeError('original #717 external CAPTCHA callback differs')


def _load_captcha_class():
    # Pinned factory/module construction only selects/imports this class.
    # The first HTTP operation is inside the guarded getImageSource body.
    from account_helpers.captcha import CAPTCHA_API_CLASS
    from account_helpers.captcha.reCAPTCHA import reCAPTCHA
    if (CAPTCHA_API_CLASS is not reCAPTCHA
            or reCAPTCHA.__module__ != 'account_helpers.captcha.reCAPTCHA'
            or reCAPTCHA.__name__ != 'reCAPTCHA'):
        raise RuntimeError('unsupported native CAPTCHA provider')
    return reCAPTCHA


class _CaptchaGuard(object):
    """Block the exact HTTP front door; never fabricate an image or answer."""
    def __init__(self, captcha_class, record):
        self.captcha_class, self.record = captcha_class, record
        self.original = captcha_class.__dict__.get('getImageSource')
        _audit_captcha(self.original)
        self.active = self.installed = self.attempted = False
        self.blocked_calls = 0
        self.calls_exhausted = False
        self.lock = threading.Lock()
        owner = self

        def blocked(self, key, *args):
            # Never inspect, hash, stringify or retain the arguments. Saved
            # late bound methods also fail, and can never delegate to HTTP.
            owner.block()

        self.replacement = blocked

    def require_ready(self):
        if (not self.active or not self.installed
                or self.captcha_class.__dict__.get('getImageSource') is not self.replacement):
            raise RuntimeError('external CAPTCHA guard ownership lost')
        if self.blocked_calls or self.calls_exhausted:
            raise RuntimeError(CAPTCHA_ERROR)

    def block(self):
        # The original image worker is a Thread. Bound its diagnostics and
        # shared fault latch; a failed log write cannot clear that latch.
        with self.lock:
            publish = not self.calls_exhausted
            if self.blocked_calls < MAX_CAPTCHA_BLOCK_RECORDS:
                self.blocked_calls += 1
            else:
                self.calls_exhausted = True
            count, exhausted = self.blocked_calls, self.calls_exhausted
        if publish:
            _emit(self.record, 'blocked_external_captcha', source=CAPTCHA_SOURCE,
                  method='getImageSource', source_line=44, blocked_calls=count,
                  count_exhausted=exhausted, original_called=False,
                  http_started=False, arguments_recorded=False,
                  enqueue_success_claimed=False)
        raise RuntimeError(CAPTCHA_ERROR)

    def install(self):
        if self.attempted:
            raise RuntimeError('external CAPTCHA guard install already attempted')
        self.attempted = True
        if self.captcha_class.__dict__.get('getImageSource') is not self.original:
            raise RuntimeError('refusing a foreign CAPTCHA descriptor')
        _audit_captcha(self.original)
        setattr(self.captcha_class, 'getImageSource', self.replacement)
        self.active = self.installed = True
        _emit(self.record, 'map_drive_client_captcha_guard', phase='install',
              source=CAPTCHA_SOURCE, source_sha256=CAPTCHA_SHA256,
              code_sha256=CAPTCHA_CODE_SHA256, blocked_calls=0,
              original_called=False, external_http_allowed=False)

    def restore(self):
        if not self.installed:
            return
        if self.captcha_class.__dict__.get('getImageSource') is not self.replacement:
            raise RuntimeError('refusing to overwrite a foreign CAPTCHA descriptor')
        setattr(self.captcha_class, 'getImageSource', self.original)
        self.installed = self.active = False
        _emit(self.record, 'map_drive_client_captcha_guard', phase='restore',
              source=CAPTCHA_SOURCE, original_descriptor_restored=True,
              blocked_calls=self.blocked_calls, count_exhausted=self.calls_exhausted)


class _Services(object):
    """Original process services, not per-arena state. Keep partial ownership."""
    def __init__(self, record):
        self.record = record
        self.attempted = self.initialized = False
        self.bootstrap = self.light_module = self.light = None

    def _audit_light(self):
        from arena_entry_probe import _code_contract
        for row in LIGHT_METHODS:
            _code_contract(getattr(self.light_module.LightManager, row[0]), row, LIGHT_SOURCE)

    def initialize(self):
        if self.initialized:
            return
        if self.attempted:
            raise RuntimeError('ordinary arena service initialization already failed')
        self.attempted = True
        import arena_bootstrap
        from LightFx import LightManager
        self.bootstrap, self.light_module = arena_bootstrap, LightManager
        self._audit_light()
        if LightManager.g_instance is not None:
            raise RuntimeError('ordinary drive refuses a pre-existing LightManager')
        arena_bootstrap.init(self.record)
        _emit(self.record, 'map_drive_client_light', phase='init_begin')
        self.light = LightManager.LightManager()
        if not arena_bootstrap._exact_instance(self.light, LightManager.LightManager):
            raise RuntimeError('foreign original LightManager instance')
        LightManager.g_instance = self.light
        self.light.start()
        _emit(self.record, 'map_drive_client_light', phase='init_return', owner_id=id(self.light),
              enabled=_bool(self.light.isEnabled(), 'LightManager.isEnabled'), enabled_assigned=False)
        self.initialized = True

    def before_entities(self):
        if self.bootstrap is not None:
            self.bootstrap.fini_before_entities()

    def after_entities(self):
        if self.bootstrap is not None:
            self.bootstrap.fini_after_entities()

    def destroy_light(self):
        if self.light is None:
            return
        self._audit_light()
        if self.light_module.g_instance is not self.light:
            raise RuntimeError('ordinary owned LightManager was replaced')
        _emit(self.record, 'map_drive_client_light', phase='destroy_begin', owner_id=id(self.light))
        self.light.destroy()
        self.light_module.g_instance = None
        _emit(self.record, 'map_drive_client_light', phase='destroy_return', owner_id=id(self.light))
        self.light = None
        self.initialized = False


class _Native(object):
    def context(self):
        import Account
        import Avatar
        import BigWorld
        player = BigWorld.player()
        kind = ('none' if player is None else 'account' if type(player) is Account.PlayerAccount
                else 'avatar' if type(player) is Avatar.PlayerAvatar else 'other')
        return dict(player_kind=kind, player_owner_id=None if player is None else id(player),
                    entity_id=None if player is None else _integer(player.id, 1, 2147483647, 'entity ID'))

    def eligibility(self):
        import Account
        import BigWorld
        from ConnectionManager import connectionManager
        from CurrentVehicle import g_currentVehicle
        from gui.shared import g_itemsCache
        player = BigWorld.player()
        if type(player) is not Account.PlayerAccount or not connectionManager.isConnected():
            return {'allowed': False, 'reason': 'no_connected_account', 'queued': False}
        database_id = getattr(player, 'databaseID', None)
        # Original Account.onBecomePlayer sets None before showGUI assigns the
        # real ID. The native header may update during this legitimate gap.
        if database_id is None:
            return {'allowed': False, 'reason': 'account_identity_pending', 'queued': False}
        if _integer(database_id, 1, 2147483647, 'databaseID') != 1:
            return {'allowed': False, 'reason': 'unsupported_account', 'queued': False}
        queued = _bool(player.isInRandomQueue, 'isInRandomQueue')
        # Cancelling a real existing queue must not require entry readiness.
        if queued:
            return {'allowed': True, 'reason': 'original_dequeue', 'queued': True}
        if not g_itemsCache.isSynced() or not g_currentVehicle.isPresent():
            return {'allowed': False, 'reason': 'inventory_not_ready', 'queued': False}
        item, items = g_currentVehicle.item, g_itemsCache.items
        if (_integer(g_currentVehicle.invID, 1, 2147483647, 'selected ID') != 1
                or item.invID != 1 or item.intCD != 3329):
            return {'allowed': False, 'reason': 'unsupported_vehicle', 'queued': False}
        if _raw_sha(item.descriptor.makeCompactDescr()) != MS1_SHA256:
            return {'allowed': False, 'reason': 'unsupported_configuration', 'queued': False}
        inventory = items.inventory.getCacheValue(1, {})
        if type(inventory) is not dict or len(inventory) > 32:
            raise ValueError('bounded original vehicle inventory required')
        for key in ('compDescr', 'repair', 'shells', 'shellsLayout'):
            if type(inventory.get(key)) is not dict or not 1 <= len(inventory[key]) <= 8:
                raise ValueError('bounded original inventory column required: ' + key)
        if _raw_sha(inventory['compDescr'].get(1)) != MS1_SHA256:
            raise RuntimeError('original GUI descriptor and inventory disagree')
        repair = inventory['repair'].get(1)
        if type(repair) not in (list, tuple) or len(repair) != 2:
            raise ValueError('original repair tuple required')
        repair = tuple(_integer(v, 0, 2147483647, 'repair') for v in repair)
        crew = item.crew
        if type(crew) not in (list, tuple) or len(crew) != 2:
            raise ValueError('two original MS1 crew slots required')
        crew_ids = []
        for slot, pair in enumerate(crew):
            if type(pair) not in (list, tuple) or len(pair) != 2 or pair[0] != slot:
                raise ValueError('original ordered crew slot/Tankman pairs required')
            man = pair[1]
            if man is None:
                crew_ids.append(None)
            else:
                if man.vehicleInvID != 1 or man.vehicleSlotIdx != slot:
                    raise RuntimeError('original crew assignment getters disagree')
                crew_ids.append(_integer(man.invID, 1, 2147483647, 'tankman ID'))
        layouts = inventory['shellsLayout'].get(1)
        if type(layouts) is not dict or len(layouts) > 8:
            raise ValueError('bounded mounted shell layouts required')
        raw_shells = _flat(inventory['shells'].get(1))
        raw_layout = _flat(layouts.get((5891, 5892)))
        shells = item.shells
        if type(shells) not in (list, tuple) or len(shells) != 3:
            raise ValueError('three native mounted shell getters required')
        gui = tuple((_integer(s.intCD, 1, 65535, 'shell CD'),
                     _integer(s.count, 0, 96, 'shell count'),
                     _integer(s.defaultCount, 0, 96, 'default shell count')) for s in shells)
        ready = _bool(g_currentVehicle.isReadyToFight(), 'isReadyToFight')
        load = _bool(g_currentVehicle.isAutoLoadFull(), 'isAutoLoadFull')
        equip = _bool(g_currentVehicle.isAutoEquipFull(), 'isAutoEquipFull')
        allowed = (repair == (0, 90) and crew_ids == [1, 2] and raw_shells == SHELLS
                   and raw_layout == SHELLS and gui == ((2570, 20, 20), (2826, 0, 0), (3082, 0, 0))
                   and ready and load and equip)
        if BigWorld.player() is not player or g_currentVehicle.item is not item:
            raise RuntimeError('native Account or selected item changed during entry check')
        return dict(allowed=allowed, reason='supported_ms1' if allowed else 'unsupported_crew_ammo_readiness',
                    queued=False)


class _Controller(object):
    """Exact descriptor ownership; isolated dependencies are unit-test seams."""
    def __init__(self, guard, native, services, record, captcha_guard):
        if not callable(record):
            raise TypeError('ordinary drive recorder must be callable')
        self.captcha_guard = captcha_guard
        self.guard, self.native, self.services, self.record = guard, native, services, record
        self.button_class = guard.button_class
        self.originals = dict(guard.originals)
        self.previous = dict(guard.replacements)
        if set(self.previous) != set(('fightClick', '_FightButton__disableFightButton')):
            raise RuntimeError('exact existing battle guard bindings required')
        self.installed, self.active = [], False
        self.last_context = None
        self.click_records = 0
        owner = self

        def fight(self, mapID=None, actionName=''):
            owner._require_owned()
            native_map_id = mapID
            # Verified #717 Flash random-battle callback: float 0.0, ''.
            # Original native RPC requires INT32; retain the native handler.
            if type(mapID) is float and mapID == 0.0:
                mapID = 0
            if owner.click_records < 32:
                owner.click_records += 1
                fields = _click_fields(native_map_id, actionName)
                fields['normalized_random_map'] = type(native_map_id) is float and type(mapID) is int
                _emit(owner.record, 'map_drive_client_click', **fields)
            if (mapID is not None and (type(mapID) not in integer_types or mapID != 0)
                    or type(actionName) not in string_types or actionName != ''):
                return owner.previous['fightClick'](self, mapID, actionName)
            state = owner.native.eligibility()
            if not state['allowed']:
                _emit(owner.record, 'map_drive_client_denied', reason=state['reason'], original_callback_called=False)
                return owner.previous['fightClick'](self, mapID, actionName)
            if not state['queued']:
                try:
                    owner.services.initialize()
                except Exception as error:
                    _emit(owner.record, 'map_drive_client_init_error', error_type=type(error).__name__, enqueue_called=False)
                    owner.guard.messages.pushMessage(ERROR_NOTICE, type=owner.guard.messages.SM_TYPE.Warning)
                    raise
                # Event or initialization callbacks may have changed selection.
                state = owner.native.eligibility()
                if not state['allowed'] or state['queued']:
                    raise RuntimeError('native entry state changed during arena service initialization')
            _emit(owner.record, 'map_drive_client_action', phase='begin',
                  action='dequeue' if state['queued'] else 'enqueue', original_ammo_check_preserved=True)
            result = owner.originals['fightClick'](self, mapID, actionName)
            _emit(owner.record, 'map_drive_client_action', phase='return',
                  action='dequeue' if state['queued'] else 'enqueue', server_success_claimed=False)
            return result

        def disable(self, isDisabled, toolTip):
            owner._require_owned()
            if owner.native.eligibility()['allowed']:
                # Preserve original readiness, tooltip and original Flash call.
                return owner.originals['_FightButton__disableFightButton'](self, isDisabled, toolTip)
            return owner.previous['_FightButton__disableFightButton'](self, isDisabled, toolTip)

        self.replacements = (('fightClick', fight), ('_FightButton__disableFightButton', disable))

    def _require_owned(self):
        self.captcha_guard.require_ready()
        if not self.active or not self.guard.active:
            raise RuntimeError('ordinary drive callback outside owned policy lifetime')
        for name, replacement in self.replacements:
            if self.button_class.__dict__.get(name) is not replacement:
                raise RuntimeError('ordinary drive descriptor was replaced: ' + name)
        if self.button_class.__dict__.get('update') is not self.originals['update']:
            raise RuntimeError('original FightButton update was replaced')

    def install(self):
        self.captcha_guard.require_ready()
        if self.active or self.installed or not self.guard.active:
            raise RuntimeError('ordinary drive requires one installed battle guard')
        for name, previous in self.previous.items():
            if self.button_class.__dict__.get(name) is not previous:
                raise RuntimeError('refusing foreign ordinary-drive binding: ' + name)
        if self.button_class.__dict__.get('update') is not self.originals['update']:
            raise RuntimeError('native update binding changed')
        for name, replacement in self.replacements:
            setattr(self.button_class, name, replacement)
            self.installed.append((name, replacement))
        self.active = True
        _emit(self.record, 'map_drive_client_policy', phase='install', ordinary=True,
              bindings=[name for name, _ in self.replacements], native_input_unchanged=True,
              original_ammo_check_preserved=True, automatic_quit=False)

    def restore(self):
        if not self.installed:
            return
        # A failed second setattr or diagnostic write can leave a partial
        # overlay. Restore exactly our descriptors even after a CAPTCHA fault.
        for name, replacement in self.installed:
            if self.button_class.__dict__.get(name) is not replacement:
                raise RuntimeError('ordinary drive descriptor was replaced: ' + name)
        for name, _ in reversed(self.installed):
            setattr(self.button_class, name, self.previous[name])
        self.installed, self.active = [], False
        _emit(self.record, 'map_drive_client_policy', phase='restore', previous_policy_restored=True)

    def observe(self):
        self._require_owned()
        context = self.native.context()
        context['arena_services_initialized'] = self.services.initialized
        if context != self.last_context:
            _emit(self.record, 'map_drive_client_lifetime', **context)
            self.last_context = dict(context)  # Primitives only; never retain an Entity.
        return context


def init(record):
    """Root invokes only for an explicitly installed ordinary service feature."""
    global _controller, _captcha_guard, _attempted
    if _attempted:
        raise RuntimeError('ordinary drive initialization already attempted')
    if not callable(record):
        raise TypeError('ordinary drive recorder required')
    _attempted = True
    import hangar_capabilities as policy
    guard = policy._battle_guard
    _audit_originals(policy, guard)
    sources = _audit_sources(policy)
    _captcha_guard = _CaptchaGuard(_load_captcha_class(), record)
    _controller = _Controller(guard, _Native(), _Services(record), record, _captcha_guard)
    try:
        _emit(record, 'map_drive_client_provenance', sources=sources,
              original_method_code_sha256=dict((r[0], r[4]) for r in policy.BATTLE_METHODS),
              captcha_method_code_sha256=CAPTCHA_CODE_SHA256)
        _captcha_guard.install()  # Must precede enabling the original button.
        _controller.install()
    except Exception as error:
        failures = []
        for name, restore in (('policy', _controller.restore), ('captcha', _captcha_guard.restore)):
            try:
                restore()
            except Exception as cleanup_error:
                failures.append(name + ':' + type(cleanup_error).__name__)
        if failures:
            raise RuntimeError('ordinary policy install and restore failed: ' +
                               type(error).__name__ + ', ' + ', '.join(failures))
        raise


def is_active():
    return _controller is not None and _controller.active and not _closing


def observe(record):
    if not is_active():
        return {'player_kind': 'inactive', 'arena_services_initialized': False}
    if record is not _controller.record:
        raise RuntimeError('ordinary drive recorder changed')
    return _controller.observe()


def fini(record, native_cleanup):
    """Final EXE shutdown only. Never invoke this when returning to Account."""
    global _closing, _closed
    if not callable(native_cleanup) or not callable(record):
        raise TypeError('original native cleanup and recorder required')
    if _closed:
        if _cleanup_errors:
            raise RuntimeError('ordinary cleanup previously failed: ' + ', '.join(_cleanup_errors))
        return
    if _closing:
        raise RuntimeError('reentrant ordinary cleanup')
    _closing = True
    stages = []
    if _controller is not None:
        stages += [('policy_restore', _controller.restore),
                   ('arena_before_entities', _controller.services.before_entities)]
    stages.append(('native_entities', native_cleanup))
    if _controller is not None:
        stages += [('arena_after_entities', _controller.services.after_entities),
                   ('light', _controller.services.destroy_light)]
    if _captcha_guard is not None:
        # Keep the guard throughout original entity/UI destruction.
        stages.append(('captcha_restore', _captcha_guard.restore))
    try:
        for name, function in stages:
            outcome, error_type = 'PASS', None
            try:
                function()
            except Exception as error:
                _cleanup_errors.append(name + ':' + type(error).__name__)
                outcome, error_type = 'FAIL', type(error).__name__
            try:
                _emit(record, 'map_drive_client_cleanup', stage=name, outcome=outcome, error_type=error_type)
            except Exception as error:
                # A failed log write must not skip original native destruction.
                # Preserve this failure for the final raised cleanup outcome.
                _cleanup_errors.append(name + ':record:' + type(error).__name__)
    finally:
        _closed = True
    if _cleanup_errors:
        raise RuntimeError('ordinary cleanup failed: ' + ', '.join(_cleanup_errors))
