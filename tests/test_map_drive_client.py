# -*- coding: utf-8 -*-
"""Ordinary policy/lifetime regression; mocks do not prove native drive."""
import copy
import hashlib
import json
import os
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'client_patch'))
import hangar_capabilities as old
import map_drive_client as module


class Messages(object):
    class SM_TYPE(object):
        Warning = 'warning'
    g_instance = object()
    def __init__(self):
        self.calls = []
    def pushMessage(self, text, **fields):
        self.calls.append((text, fields))


class Native(object):
    def __init__(self):
        self.state = {'allowed': True, 'reason': 'supported_ms1', 'queued': False}
        self.current = {'player_kind': 'account', 'player_owner_id': 1, 'entity_id': 1}
        self.failure = None
        self.checked = 0
    def eligibility(self):
        self.checked += 1
        if self.failure:
            raise self.failure
        return dict(self.state)
    def context(self):
        return dict(self.current)


class Services(object):
    def __init__(self):
        self.initialized = False
        self.calls = []
        self.error_at = set()
        self.after_init = None
    def initialize(self):
        if self.initialized:
            return
        self.calls.append('init')
        if 'init' in self.error_at:
            raise ValueError('init test failure')
        self.initialized = True
        if self.after_init:
            self.after_init()
    def before_entities(self):
        self.calls.append('before')
        if 'before' in self.error_at:
            raise ValueError('before test failure')
    def after_entities(self):
        self.calls.append('after')
        if 'after' in self.error_at:
            raise ValueError('after test failure')
    def destroy_light(self):
        self.calls.append('light')
        if 'light' in self.error_at:
            raise ValueError('light test failure')
        self.initialized = False


class ReadyCaptcha(object):
    """Isolated policy seam, not proof of the native HTTP guard."""
    def require_ready(self):
        return None


class OrdinaryPolicyTests(unittest.TestCase):
    def setUp(self):
        self.saved = (module._controller, module._attempted, module._closing,
                      module._closed, module._cleanup_errors, module._captcha_guard)
        module._controller = None
        module._attempted = module._closing = module._closed = False
        module._cleanup_errors = []
        module._captcha_guard = None
        self.events, self.messages = [], Messages()
        class FightButton(object):
            def __init__(self):
                self.calls, self.disables = [], []
                self.dialog_accepted = False
                self.ammo_check_calls = 0
            def fightClick(self, mapID=None, actionName=''):
                # The unchanged native entry is responsible for the checks.
                self.ammo_check_calls += 1
                self.calls.append((mapID, actionName))
                return self.dialog_accepted
            def __disableFightButton(self, isDisabled, toolTip):
                self.disables.append((isDisabled, toolTip))
                return 'original disable result'
            def update(self):
                return 'original update'
        self.cls, self.button = FightButton, FightButton()
        self.guard = old._BattleGuard(self.cls, self.messages, self.record)
        self.guard.install()
        self.previous = dict(self.guard.replacements)
        self.native, self.services = Native(), Services()
        self.ctl = module._Controller(self.guard, self.native, self.services, self.record, ReadyCaptcha())
        self.ctl.install()
        module._controller = self.ctl
    def record(self, event, **fields):
        self.events.append(dict(fields, event=event))
    def tearDown(self):
        # Simulated foreign replacements must be returned explicitly by tests.
        self.ctl.restore()
        self.guard.restore()
        (module._controller, module._attempted, module._closing,
         module._closed, module._cleanup_errors, module._captcha_guard) = self.saved
    def test_native_defaults_and_return_preserved_no_dialog_acceptance(self):
        self.assertFalse(self.button.fightClick())
        self.assertEqual(self.button.calls, [(None, '')])
        self.assertEqual(self.button.ammo_check_calls, 1)
        self.assertFalse(self.button.dialog_accepted)
        self.assertEqual(self.services.calls, ['init'])
    def test_native_disabled_and_tooltip_arguments_preserved(self):
        tooltip = object()
        self.assertEqual(self.button._FightButton__disableFightButton(True, tooltip), 'original disable result')
        self.assertEqual(self.button.disables, [(True, tooltip)])
        self.assertEqual(self.services.calls, [])
        self.assertIs(self.cls.__dict__['update'], self.guard.originals['update'])
    def test_ineligible_uses_existing_explicit_denial(self):
        self.native.state['allowed'] = False
        self.assertIsNone(self.button.fightClick(0, ''))
        self.assertEqual(self.button.calls, [])
        self.assertEqual(self.services.calls, [])
        self.assertEqual(self.messages.calls[-1][0], old.BATTLE_NOTICE)
        self.button._FightButton__disableFightButton(False, 'unused')
        self.assertEqual(self.button.disables[-1], (True, old.BATTLE_TOOLTIP))
    def test_nonrandom_ids_action_types_cannot_delegate(self):
        for args in ((1, ''), (-1, ''), (True, ''), (False, ''), (1.0, ''),
                     (float('nan'), ''), (float('inf'), ''), (-float('inf'), ''),
                     (0, 'other'), (0, None), (0, 'x'*10000)):
            self.assertIsNone(self.button.fightClick(*args))
        self.assertEqual(self.button.calls, [])
        self.assertEqual(self.native.checked, 0)
        self.assertEqual(self.services.calls, [])
        self.assertTrue(all(len(json.dumps(e)) < 4096 for e in self.events))
    def test_verified_flash_float_zero_calls_original_with_exact_integer_zero(self):
        self.assertFalse(self.button.fightClick(0.0, ''))
        self.assertEqual([(0, '')], self.button.calls)
        self.assertIs(type(self.button.calls[0][0]), int)
        self.assertEqual(1, self.button.ammo_check_calls)
        self.assertFalse(self.button.dialog_accepted)
        self.assertEqual(['init'], self.services.calls)
        click = next(e for e in self.events if e['event'] == 'map_drive_client_click')
        self.assertEqual('float', click['map_id_type'])
        self.assertIs(type(click['map_id_value']), float)
        self.assertTrue(click['normalized_random_map'])
    def test_normalized_flash_call_reaches_strict_original_rpc_integer_seam(self):
        # A strict isolated downstream seam catches float==int false positives.
        # No native handler or RPC is executed by this unit test.
        rpc_calls = []
        original = self.ctl.originals['fightClick']
        def strict_rpc(map_id):
            if type(map_id) is not int:
                raise TypeError('INT32 map argument required by original RPC seam')
            rpc_calls.append(map_id)
        def original_handler(button, mapID=None, actionName=''):
            self.assertIs(button, self.button)
            self.assertEqual('', actionName)
            strict_rpc(mapID)
            return 'strict original handler result'
        self.ctl.originals['fightClick'] = original_handler
        try:
            self.assertEqual('strict original handler result', self.button.fightClick(0.0, ''))
        finally:
            self.ctl.originals['fightClick'] = original
        self.assertEqual([0], rpc_calls)
        self.assertIs(type(rpc_calls[0]), int)
    def test_arity_strict_before_native_entry(self):
        with self.assertRaises(TypeError):
            self.button.fightClick(0, '', 1)
        with self.assertRaises(TypeError):
            self.button.fightClick(unknown=True)
        self.assertEqual(self.button.calls, [])
    def test_entry_rechecks_after_services_selection_change(self):
        self.services.after_init = lambda: self.native.state.update(allowed=False)
        with self.assertRaises(RuntimeError):
            self.button.fightClick()
        self.assertEqual(self.button.calls, [])
        self.assertEqual(self.native.checked, 2)
    def test_stale_enabled_state_cannot_enqueue(self):
        self.button._FightButton__disableFightButton(False, 'ready')
        self.native.state['allowed'] = False
        self.button.fightClick()
        self.assertEqual(self.button.calls, [])
    def test_failed_services_warn_raise_never_enqueue(self):
        self.services.error_at.add('init')
        with self.assertRaises(ValueError):
            self.button.fightClick()
        self.assertEqual(self.button.calls, [])
        self.assertEqual(self.messages.calls[-1][0], module.ERROR_NOTICE)
        self.assertFalse(any(e['event']=='map_drive_client_action' for e in self.events))
    def test_original_dequeue_not_blocked_on_entry_readiness(self):
        self.native.state.update(queued=True, reason='original_dequeue')
        self.button.fightClick(0, '')
        self.assertEqual(self.services.calls, [])
        self.assertEqual(self.button.calls, [(0, '')])
        self.assertEqual(self.events[-1]['action'], 'dequeue')
    def test_warm_return_reuses_services_without_entity_references(self):
        self.button.fightClick()
        self.ctl.observe()
        self.native.current.update(player_kind='avatar', player_owner_id=2)
        self.ctl.observe()
        self.native.current.update(player_kind='account', player_owner_id=3)
        self.ctl.observe()
        self.button.fightClick()
        self.assertEqual(self.services.calls, ['init'])
        self.assertEqual(len(self.button.calls), 2)
        self.assertEqual(self.ctl.last_context['player_kind'], 'account')
        self.assertTrue(all(type(v) in (str, int, bool, type(None)) for v in self.ctl.last_context.values()))
    def test_observer_has_no_per_arena_budget_or_autoquit(self):
        before = len(self.events)
        for _ in range(1000):
            self.ctl.observe()
        self.assertEqual(len(self.events), before+1)
        self.assertEqual(self.services.calls, [])
    def test_owned_binding_restored_then_prior_policy_restorable(self):
        late = self.button.fightClick
        self.ctl.restore()
        for name, value in self.previous.items():
            self.assertIs(self.cls.__dict__[name], value)
        with self.assertRaises(RuntimeError):
            late()
        self.guard.restore()
        self.assertIs(self.cls.__dict__['fightClick'], self.guard.originals['fightClick'])
    def test_foreign_descriptor_never_overwritten(self):
        own = self.cls.__dict__['fightClick']
        foreign = lambda *args: None
        self.cls.fightClick = foreign
        with self.assertRaises(RuntimeError):
            self.ctl.restore()
        self.assertIs(self.cls.__dict__['fightClick'], foreign)
        self.cls.fightClick = own
    def test_original_update_foreign_change_rejects_callback(self):
        original = self.cls.__dict__['update']
        self.cls.update = lambda self: None
        with self.assertRaises(RuntimeError):
            self.button.fightClick()
        self.cls.update = original
        self.assertEqual(self.button.calls, [])
    def test_cleanup_order_and_exact_once_native_shutdown(self):
        self.button.fightClick()
        def native_cleanup():
            self.assertIs(self.cls.__dict__['fightClick'], self.previous['fightClick'])
            self.assertEqual(self.services.calls, ['init', 'before'])
            self.services.calls.append('native')
        module.fini(self.record, native_cleanup)
        module.fini(self.record, native_cleanup)
        self.assertEqual(self.services.calls, ['init', 'before', 'native', 'after', 'light'])
        self.assertFalse(module.is_active())
    def test_cleanup_attempts_every_stage_and_retains_all_errors(self):
        self.services.error_at.update(('before', 'after', 'light'))
        def native_cleanup():
            self.services.calls.append('native')
            raise ValueError('native failed')
        with self.assertRaises(RuntimeError):
            module.fini(self.record, native_cleanup)
        self.assertEqual(self.services.calls, ['before','native','after','light'])
        self.assertEqual(len(module._cleanup_errors),4)
        self.assertEqual(len([e for e in self.events if e['event']=='map_drive_client_cleanup' and e['outcome']=='FAIL']),4)
    def test_failed_cleanup_record_still_attempts_native_and_all_services(self):
        def record(event,**fields):
            if event=='map_drive_client_cleanup':raise IOError('disk full test')
        with self.assertRaises(RuntimeError):
            module.fini(record,lambda:self.services.calls.append('native'))
        self.assertEqual(self.services.calls,['before','native','after','light'])
        self.assertEqual(len(module._cleanup_errors),5)
    def test_unarmed_functions_are_passive(self):
        module._controller = None
        self.assertFalse(module.is_active())
        self.assertEqual(module.observe(self.record), {'player_kind':'inactive','arena_services_initialized':False})
        self.assertEqual(self.button.calls, [])
    def test_uninitialized_final_shutdown_still_invokes_native(self):
        module._controller = None
        calls=[]
        module.fini(self.record, lambda:calls.append('native'))
        self.assertEqual(calls,['native'])
    def test_audit_rejects_unpinned_native_lookalike(self):
        with self.assertRaises(RuntimeError):
            module._audit_originals(old,self.guard)
    def test_entry_getter_error_not_hidden_as_native_success(self):
        self.native.failure=ValueError('actual observer error')
        with self.assertRaises(ValueError):self.button.fightClick()
        self.assertEqual(self.button.calls,[])


class CaptchaGuardTests(unittest.TestCase):
    def setUp(self):
        self.events, self.original_calls = [], []
        calls = self.original_calls
        class reCAPTCHA(object):
            def getImageSource(self, key, *args):
                calls.append((key, args))
                raise AssertionError('original HTTP front door must never run')
        self.cls = reCAPTCHA
        self.original = reCAPTCHA.__dict__['getImageSource']
        self.audit = module._audit_captcha
        def isolated_audit(function):
            if function is not self.original:
                raise RuntimeError('isolated exact function identity differs')
        # Native bytecode is never executed in unit tests. Its independent
        # static pin check below is separate from these binding/lifetime tests.
        module._audit_captcha = isolated_audit
        self.guard = module._CaptchaGuard(self.cls, self.record)
    def record(self, event, **fields):
        self.events.append(dict(fields, event=event))
    def tearDown(self):
        if self.guard.installed:
            self.cls.getImageSource = self.guard.replacement
            self.guard.record = self.record
            self.guard.restore()
        module._audit_captcha = self.audit
    def test_blocks_without_original_or_argument_rendering(self):
        class Secret(object):
            def __repr__(self):raise AssertionError('argument must not be rendered')
            def __str__(self):raise AssertionError('argument must not be rendered')
        self.guard.install()
        with self.assertRaises(RuntimeError):self.cls().getImageSource(Secret(), Secret())
        self.assertEqual(self.original_calls, [])
        event = self.events[-1]
        self.assertEqual(event['event'], 'blocked_external_captcha')
        self.assertEqual(event['blocked_calls'], 1)
        self.assertFalse(event['http_started'])
        self.assertFalse(event['original_called'])
        self.assertFalse(event['arguments_recorded'])
        self.assertFalse(event['enqueue_success_claimed'])
        self.assertLess(len(json.dumps(event)), 1024)
        with self.assertRaises(RuntimeError):self.guard.require_ready()
    def test_installed_signature_accepts_exact_native_varargs_and_keyword_key(self):
        self.guard.install()
        for operation in (lambda:self.cls().getImageSource('private', 'regex'),
                          lambda:self.cls().getImageSource(key='private')):
            with self.assertRaises(RuntimeError):operation()
        with self.assertRaises(TypeError):self.cls().getImageSource()
        with self.assertRaises(TypeError):self.cls().getImageSource('private', unknown=True)
        self.assertEqual(self.guard.blocked_calls, 2)
        self.assertNotIn('private', json.dumps(self.events))
    def test_log_failure_remains_latched_and_does_not_delegate(self):
        self.guard.install()
        def broken_record(event, **fields):raise IOError('test disk full')
        self.guard.record = broken_record
        with self.assertRaises(IOError):self.cls().getImageSource('secret')
        self.assertEqual(self.guard.blocked_calls, 1)
        with self.assertRaises(RuntimeError):self.guard.require_ready()
        self.assertEqual(self.original_calls, [])
    def test_counter_and_records_are_bounded_but_late_calls_always_fail(self):
        self.guard.install()
        for _ in range(module.MAX_CAPTCHA_BLOCK_RECORDS + 10):
            with self.assertRaises(RuntimeError):self.cls().getImageSource('secret')
        rows = [e for e in self.events if e['event']=='blocked_external_captcha']
        self.assertEqual(len(rows), module.MAX_CAPTCHA_BLOCK_RECORDS + 1)
        self.assertEqual(self.guard.blocked_calls, module.MAX_CAPTCHA_BLOCK_RECORDS)
        self.assertTrue(rows[-1]['count_exhausted'])
        self.assertEqual(self.original_calls, [])
    def test_exact_restore_late_saved_binding_still_blocks(self):
        self.guard.install()
        late = self.cls().getImageSource
        self.guard.restore()
        self.assertIs(self.cls.__dict__['getImageSource'], self.original)
        with self.assertRaises(RuntimeError):late('secret')
        self.assertEqual(self.original_calls, [])
        with self.assertRaises(RuntimeError):self.guard.install()
    def test_foreign_preinstall_or_restore_descriptor_never_overwritten(self):
        foreign = lambda *args: None
        self.cls.getImageSource = foreign
        with self.assertRaises(RuntimeError):self.guard.install()
        self.assertIs(self.cls.__dict__['getImageSource'], foreign)
        self.cls.getImageSource = self.original
        self.guard = module._CaptchaGuard(self.cls, self.record)
        self.guard.install()
        self.cls.getImageSource = foreign
        with self.assertRaises(RuntimeError):self.guard.require_ready()
        with self.assertRaises(RuntimeError):self.guard.restore()
        self.assertIs(self.cls.__dict__['getImageSource'], foreign)
    def test_original_audit_rejects_similar_unpinned_function_and_method(self):
        with self.assertRaises(RuntimeError):self.audit(self.original)
        with self.assertRaises(TypeError):self.audit(self.cls().getImageSource)
        with self.assertRaises(TypeError):self.audit(staticmethod(self.original))
    def test_install_record_failure_retains_exact_rollback_ownership(self):
        def failed(event, **fields):raise IOError('install record failed')
        self.guard.record = failed
        with self.assertRaises(IOError):self.guard.install()
        self.assertTrue(self.guard.installed)
        self.assertIs(self.cls.__dict__['getImageSource'], self.guard.replacement)
        self.guard.record = self.record
        self.guard.restore()
        self.assertIs(self.cls.__dict__['getImageSource'], self.original)


class CaptchaLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.policy = OrdinaryPolicyTests('test_unarmed_functions_are_passive')
        self.policy.setUp()
        self.policy.ctl.restore()
        module._controller = None
        self.captcha = CaptchaGuardTests('test_blocks_without_original_or_argument_rendering')
        self.captcha.setUp()
        self.saved = {name:getattr(module, name) for name in
                      ('_audit_originals','_audit_sources','_load_captcha_class','_Native','_Services')}
        self.previous_battle = old._battle_guard
        old._battle_guard = self.policy.guard
        module._audit_originals = lambda policy, guard: None
        module._audit_sources = lambda policy: []
        module._load_captcha_class = lambda: self.captcha.cls
        module._Native = lambda: self.policy.native
        module._Services = lambda record: self.policy.services
    def tearDown(self):
        if module._controller is not None:
            module._controller.record = self.policy.record
            module._controller.restore()
        if module._captcha_guard is not None:
            module._captcha_guard.record = self.policy.record
            module._captcha_guard.restore()
        for name,value in self.saved.items():setattr(module,name,value)
        old._battle_guard = self.previous_battle
        self.captcha.tearDown()
        self.policy.tearDown()
    def test_guard_installs_before_button_and_remains_through_native_cleanup(self):
        module.init(self.policy.record)
        rows = self.policy.events
        guard_index = next(i for i,e in enumerate(rows) if e['event']=='map_drive_client_captcha_guard')
        policy_index = next(i for i,e in enumerate(rows) if e['event']=='map_drive_client_policy' and e['phase']=='install' and i>guard_index)
        self.assertLess(guard_index,policy_index)
        def cleanup():
            module._captcha_guard.require_ready()
            self.assertIs(self.policy.cls.__dict__['fightClick'], self.policy.previous['fightClick'])
        module.fini(self.policy.record,cleanup)
        self.assertIs(self.captcha.cls.__dict__['getImageSource'],self.captcha.original)
        self.assertEqual([e['stage'] for e in rows if e['event']=='map_drive_client_cleanup'],
                         ['policy_restore','arena_before_entities','native_entities','arena_after_entities','light','captcha_restore'])
        self.assertEqual(rows[-2]['blocked_calls'],0)
    def test_unexpected_worker_fetch_latches_main_observer_and_button(self):
        module.init(self.policy.record)
        with self.assertRaises(RuntimeError):self.captcha.cls().getImageSource('private')
        with self.assertRaises(RuntimeError):module.observe(self.policy.record)
        with self.assertRaises(RuntimeError):self.policy.button.fightClick()
        self.assertEqual(self.policy.button.calls,[])
        self.assertEqual(self.captcha.original_calls,[])
        module.fini(self.policy.record,lambda:None)
        self.assertIs(self.captcha.cls.__dict__['getImageSource'],self.captcha.original)
    def test_failed_button_install_restores_both_even_when_policy_log_fails(self):
        def record(event,**fields):
            if event=='map_drive_client_policy':raise IOError('policy write failed')
        with self.assertRaises(RuntimeError):module.init(record)
        self.assertIs(self.captcha.cls.__dict__['getImageSource'],self.captcha.original)
        self.assertIs(self.policy.cls.__dict__['fightClick'],self.policy.previous['fightClick'])
        self.assertFalse(module._captcha_guard.active)
    def test_guard_install_failure_never_enables_button(self):
        def record(event,**fields):
            if event=='map_drive_client_captcha_guard' and fields['phase']=='install':
                raise IOError('guard write failed')
        with self.assertRaises(IOError):module.init(record)
        self.assertFalse(module._controller.active)
        self.assertIs(self.captcha.cls.__dict__['getImageSource'],self.captcha.original)
        self.assertIs(self.policy.cls.__dict__['fightClick'],self.policy.previous['fightClick'])
    def test_partial_overlay_can_restore_without_active_latch(self):
        ctl=self.policy.ctl
        name,replacement=ctl.replacements[0]
        setattr(ctl.button_class,name,replacement)
        ctl.installed=[(name,replacement)];ctl.active=False
        ctl.restore()
        self.assertIs(ctl.button_class.__dict__[name],ctl.previous[name])
    def test_native_cleanup_error_still_restores_captcha_last(self):
        module.init(self.policy.record)
        def failed():raise ValueError('original cleanup failed')
        with self.assertRaises(RuntimeError):module.fini(self.policy.record,failed)
        self.assertIs(self.captcha.cls.__dict__['getImageSource'],self.captcha.original)
        self.assertIn('native_entities:ValueError',module._cleanup_errors)


class Box(object):
    def __init__(self, **kwargs):self.__dict__.update(kwargs)


class NativeEligibilityTests(unittest.TestCase):
    def setUp(self):
        self.saved={}
        class PlayerAccount(object):pass
        self.player=PlayerAccount();self.player.databaseID=1;self.player.isInRandomQueue=False;self.player.id=1
        # The byte constant is independently bound to the real native MS1 hash.
        compact=bytes(bytearray.fromhex('010d17001700020000000100170000'))
        self.real_compact=compact
        self.old_sha=module.MS1_SHA256
        module.MS1_SHA256=hashlib.sha256(compact).hexdigest()
        self.item=Box(invID=1,intCD=3329,descriptor=Box(makeCompactDescr=lambda:compact),
            crew=[(i,Box(invID=i+1,vehicleInvID=1,vehicleSlotIdx=i)) for i in range(2)],
            shells=[Box(intCD=c,count=n,defaultCount=n) for c,n in ((2570,20),(2826,0),(3082,0))])
        self.inventory={'compDescr':{1:compact},'repair':{1:(0,90)},'shells':{1:list(module.SHELLS)},'shellsLayout':{1:{(5891,5892):list(module.SHELLS)}}}
        self.current=Box(item=self.item,invID=1,isPresent=lambda:True,isReadyToFight=lambda:True,
                         isAutoLoadFull=lambda:True,isAutoEquipFull=lambda:True)
        self.cache=Box(isSynced=lambda:True,items=Box(inventory=Box(getCacheValue=lambda *args:self.inventory)))
        for name, attrs in {
                'gui':dict(__path__=[]),
                'Account':dict(PlayerAccount=PlayerAccount),
                'BigWorld':dict(player=lambda:self.player),
                'ConnectionManager':dict(connectionManager=Box(isConnected=lambda:True)),
                'CurrentVehicle':dict(g_currentVehicle=self.current),
                'gui.shared':dict(g_itemsCache=self.cache)}.items():
            self.saved[name]=sys.modules.get(name)
            fake=types.ModuleType(name);fake.__dict__.update(attrs);sys.modules[name]=fake
        self.native=module._Native()
    def tearDown(self):
        module.MS1_SHA256=self.old_sha
        for name,value in self.saved.items():
            if value is None:del sys.modules[name]
            else:sys.modules[name]=value
    def test_actual_getter_shape_allowed_with_no_mutation(self):
        before=copy.deepcopy(self.inventory)
        self.assertTrue(self.native.eligibility()['allowed'])
        self.assertEqual(self.inventory,before)
    def test_secondary_and_is7_denied(self):
        self.player.databaseID=2
        self.assertFalse(self.native.eligibility()['allowed'])
    def test_original_pre_showgui_database_id_none_is_not_ready(self):
        self.player.databaseID=None
        self.assertEqual(self.native.eligibility(),dict(allowed=False,reason='account_identity_pending',queued=False))
        del self.player.databaseID
        self.assertEqual(self.native.eligibility()['reason'],'account_identity_pending')
        self.player.databaseID=1.0
        with self.assertRaises(ValueError):self.native.eligibility()
        self.player.databaseID=1;self.current.invID=2
        self.assertFalse(self.native.eligibility()['allowed'])
    def test_crew_missing_or_wrong_assignment(self):
        self.item.crew[1]=(1,None)
        self.assertFalse(self.native.eligibility()['allowed'])
        self.item.crew[1]=(1,Box(invID=2,vehicleInvID=2,vehicleSlotIdx=1))
        with self.assertRaises(RuntimeError):self.native.eligibility()
    def test_counts_layout_and_damage_each_reject(self):
        self.inventory['shells'][1][1]=19
        self.assertFalse(self.native.eligibility()['allowed'])
        self.inventory['shells'][1][1]=20;self.inventory['shellsLayout'][1][(5891,5892)][1]=19
        self.assertFalse(self.native.eligibility()['allowed'])
        self.inventory['shellsLayout'][1][(5891,5892)][1]=20;self.inventory['repair'][1]=(1,90)
        self.assertFalse(self.native.eligibility()['allowed'])
    def test_gui_count_disagreement_never_eligible(self):
        self.item.shells[0].count=19
        self.assertFalse(self.native.eligibility()['allowed'])
    def test_native_readiness_and_layout_checks_not_overridden(self):
        for name in ('isReadyToFight','isAutoLoadFull','isAutoEquipFull'):
            original=getattr(self.current,name);setattr(self.current,name,lambda:False)
            self.assertFalse(self.native.eligibility()['allowed'])
            setattr(self.current,name,original)
    def test_queue_cancel_does_not_require_synced_inventory(self):
        self.player.isInRandomQueue=True;self.cache.isSynced=lambda:False
        self.assertEqual(self.native.eligibility(),dict(allowed=True,reason='original_dequeue',queued=True))
    def test_unbounded_column_and_bool_integer_rejected(self):
        self.inventory['compDescr']={i:self.real_compact for i in range(9)}
        with self.assertRaises(ValueError):self.native.eligibility()
        self.inventory['compDescr']={1:self.real_compact};self.inventory['shells'][1][1]=True
        with self.assertRaises(ValueError):self.native.eligibility()
    def test_descriptor_mismatch_fails_before_queue(self):
        self.inventory['compDescr'][1]=b'foreign'
        with self.assertRaises(RuntimeError):self.native.eligibility()


class SourceBoundaryTests(unittest.TestCase):
    def test_no_quit_input_or_position_assignment(self):
        import ast
        with open(os.path.join(ROOT,'client_patch','map_drive_client.py'),'rb') as f:tree=ast.parse(f.read())
        forbidden={'quit','handleKeyEvent','handleMouseEvent','moveVehicle','setStaticTransform','screenShot','clearAllSpaces'}
        calls=[n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)]
        self.assertFalse(set(calls)&forbidden)
        assigned=[n.attr for n in ast.walk(tree) if isinstance(n,ast.Attribute) and isinstance(n.ctx,ast.Store)]
        self.assertFalse(set(assigned)&{'position','target','serverTime','isInRandomQueue'})
    @unittest.skipIf(sys.version_info[0]<3,'host-only safe Python2 static decoder')
    def test_source_pins_match_original_without_importing_original(self):
        sys.path.insert(0,os.path.join(ROOT,'tools'))
        from pathlib import Path
        from client_audit import config,read_limited
        from py27_static import parse_pyc,records,text
        original=config()[1]['original_client_root']
        specs=[('res/'+old.BATTLE_SOURCE[:-3]+'.pyc',old.BATTLE_PYC_SHA256,old.BATTLE_METHODS),
               ('res/'+module.LIGHT_SOURCE[:-3]+'.pyc',module.LIGHT_SHA256,module.LIGHT_METHODS)]
        for path,digest,wanted in specs:
            raw=read_limited(original/path,1048576)
            self.assertEqual(hashlib.sha256(raw).hexdigest(),digest)
            found={}
            for q,c in records(parse_pyc(raw)):
                for row in wanted:
                    # Private attribute is mangled but original co_name is not.
                    name=row[0].replace('_FightButton','') if path.endswith('FightButton.pyc') else row[1]
                    expected_class='FightButton' if path.endswith('FightButton.pyc') else 'LightManager'
                    if q=='<module>.'+expected_class+'.'+name:
                        found[row[0]]=hashlib.sha256(c['code']).hexdigest()
            self.assertEqual(found,{r[0]:r[-1] for r in wanted})

    @unittest.skipIf(sys.version_info[0]<3,'host-only safe Python2 static decoder')
    def test_exact_captcha_sources_and_first_http_boundary_without_execution(self):
        sys.path.insert(0,os.path.join(ROOT,'tools'))
        from client_audit import config,read_limited
        from py27_static import parse_pyc,records,text,opcode_table,disassemble
        from pathlib import Path
        original=config()[1]['original_client_root']
        table=opcode_table(read_limited(Path(ROOT)/'local/vendor/cpython-2.7.3/opcode.py',32768).decode('utf8'))
        decoded={}
        for source,digest in ((module.CAPTCHA_SOURCE,module.CAPTCHA_SHA256),)+module.CAPTCHA_CHAIN_SOURCES:
            raw=read_limited(original/('res/'+source[:-3]+'.pyc'),1048576)
            self.assertEqual(hashlib.sha256(raw).hexdigest(),digest)
            decoded[source]={q:c for q,c in records(parse_pyc(raw))}
        code=decoded[module.CAPTCHA_SOURCE]['<module>.reCAPTCHA.getImageSource']
        self.assertEqual(hashlib.sha256(code['code']).hexdigest(),module.CAPTCHA_CODE_SHA256)
        self.assertEqual((code['firstlineno'],code['argcount'],code['flags']),(44,2,71))
        self.assertEqual(tuple(text(v) for v in code['varnames'][:3]),('self','key','args'))
        ins={i['offset']:i for i in disassemble(code,table)}
        for load,call in ((122,128),(286,292)):
            self.assertEqual(ins[load]['value'],'urlopen')
            self.assertEqual(ins[call]['opname'],'CALL_FUNCTION')
        self.assertEqual([i['offset'] for i in ins.values() if i.get('value')=='urlopen'],[122,286])
        self.assertEqual(ins[443]['opname'],'RETURN_VALUE')
        safe_methods={
            module.CAPTCHA_SOURCE:('<module>','<module>.reCAPTCHA'),
            module.CAPTCHA_CHAIN_SOURCES[0][0]:('<module>','<module>._BASE_CAPTCHA_API','<module>._CAPTCHA_API_FACTORY'),
            module.CAPTCHA_CHAIN_SOURCES[1][0]:('<module>.CaptchaController.getPublicKey','<module>.CaptchaController.getCaptchaRegex','<module>.CaptchaController.getImageSource'),
            module.CAPTCHA_CHAIN_SOURCES[2][0]:('<module>.CaptchaImageWorker.__init__','<module>.CaptchaImageWorker.run','<module>.CaptchaDialog.generateImageName','<module>.CaptchaDialog.getImageSource')}
        for source,names in safe_methods.items():
            for name in names:
                used={text(v) for v in decoded[source][name]['names']}
                self.assertFalse(used & {'urlopen','urlretrieve','socket','requests'})
        controller=decoded[module.CAPTCHA_CHAIN_SOURCES[1][0]]['<module>.CaptchaController.getImageSource']
        self.assertEqual([i['offset'] for i in disassemble(controller,table) if i['opname']=='CALL_FUNCTION'],[15,24,27])


class ServiceLifetimeTests(unittest.TestCase):
    def setUp(self):
        self.events=[];self.calls=[];self.fail=None
        self.saved={name:sys.modules.get(name) for name in ('arena_bootstrap','LightFx')}
        calls=self.calls;owner=self
        class LightManager(object):
            def __init__(self):calls.append('light_init')
            def start(self):
                calls.append('light_start')
                if owner.fail=='start':raise ValueError('original start failed')
            def isEnabled(self):return False
            def destroy(self):calls.append('light_destroy')
        self.lightmod=Box(LightManager=LightManager,g_instance=None)
        lightfx=types.ModuleType('LightFx');lightfx.LightManager=self.lightmod
        bootstrap=types.ModuleType('arena_bootstrap')
        bootstrap._exact_instance=lambda instance,cls:type(instance) is cls
        bootstrap.init=lambda record:calls.append('arena_init')
        bootstrap.fini_before_entities=lambda:calls.append('arena_before')
        bootstrap.fini_after_entities=lambda:calls.append('arena_after')
        sys.modules['arena_bootstrap']=bootstrap;sys.modules['LightFx']=lightfx
        self.service=module._Services(lambda event,**fields:self.events.append(dict(fields,event=event)))
        # The separate static test proves original method hashes. These tests
        # exercise ownership/partial lifetime with intentionally isolated stubs.
        self.service._audit_light=lambda:None
    def tearDown(self):
        for name,value in self.saved.items():
            if value is None:del sys.modules[name]
            else:sys.modules[name]=value
    def test_original_init_start_once_even_multiple_entries(self):
        self.service.initialize();self.service.initialize()
        self.assertEqual(self.calls,['arena_init','light_init','light_start'])
        self.assertTrue(self.service.initialized)
        self.assertFalse(self.events[-1]['enabled'])
        self.assertFalse(self.events[-1]['enabled_assigned'])
    def test_partial_light_start_failure_retains_cleanup_and_cannot_reinit(self):
        self.fail='start'
        with self.assertRaises(ValueError):self.service.initialize()
        self.assertIs(self.lightmod.g_instance,self.service.light)
        with self.assertRaises(RuntimeError):self.service.initialize()
        self.service.before_entities();self.service.after_entities();self.service.destroy_light()
        self.assertEqual(self.calls,['arena_init','light_init','light_start','arena_before','arena_after','light_destroy'])
        self.assertIsNone(self.lightmod.g_instance)
    def test_preexisting_singleton_never_overwritten(self):
        foreign=object();self.lightmod.g_instance=foreign
        with self.assertRaises(RuntimeError):self.service.initialize()
        self.assertIs(self.lightmod.g_instance,foreign)
        self.assertEqual(self.calls,[])
    def test_replaced_singleton_not_destroyed(self):
        self.service.initialize();foreign=object();self.lightmod.g_instance=foreign
        with self.assertRaises(RuntimeError):self.service.destroy_light()
        self.assertIs(self.lightmod.g_instance,foreign)
        self.assertNotIn('light_destroy',self.calls)


if __name__=='__main__':unittest.main()
