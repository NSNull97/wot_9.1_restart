"""Opt-in, redaction and original-return plumbing; no native acceptance claims."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import diagnostic_client_run as runner
import test_interactive_relogin_control as direct
import test_diagnostic_client_run as old_runner


class LongControlTests(unittest.TestCase):
    def setUp(self):
        import os
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'control.json'
        self.events = []
        self.module = SimpleNamespace(arm=Mock(), note_stats_return=Mock(),
            checked_expected_primary=Mock(side_effect=lambda value: value))
        self.value = {'username':'own@example.test', 'password':'  owned unit secret  ',
            'verify_long_hangar':True, 'long_hangar_expected':{'native_id':1},
            'submit_via':'python', 'quit_when':'long_hangar_observed'}
        self.namespace = {'os':os, 'json':json, '_control_done':False,
            '_settings':{'test_control':str(self.path), 'local_root':self.temp.name,
                         'endpoint':'127.0.0.1:20014'},
            'owned':lambda path, root:path,
            'record':lambda event, **fields:self.events.append((event,fields))}
        direct.trusted_functions({'consume_control'}, self.namespace)
        self.view = SimpleNamespace(onLogin=Mock(), as_setDefaultValuesS=Mock(), as_doAutoLoginS=Mock())

    def consume(self, value):
        self.path.write_text(json.dumps(value), encoding='utf8')
        with patch.dict(sys.modules, {'long_hangar_scenario':self.module}):
            self.namespace['consume_control'](self.view)

    def test_one_arm_original_submit_and_no_secret_in_public_state(self):
        self.consume(self.value)
        self.module.arm.assert_called_once_with(self.value['long_hangar_expected'])
        self.view.onLogin.assert_called_once_with(self.value['username'], self.value['password'], '127.0.0.1:20014')
        self.assertFalse(self.path.exists())
        for item in (self.events, self.namespace['_control']):
            serialized = json.dumps(item)
            self.assertNotIn(self.value['username'], serialized)
            self.assertNotIn(self.value['password'], serialized)
        self.assertNotIn('long_hangar_expected', self.namespace['_control'])

    def test_bad_modes_rejected_by_client_and_host_before_submit(self):
        cases = []
        for name in ('username','password','long_hangar_expected'):
            value = dict(self.value); del value[name]; cases.append(value)
        cases += [dict(self.value, **change) for change in (
            {'verify_long_hangar':1}, {'verify_account_switch':True},
            {'verify_inprocess_relogin':True}, {'quit_when':None},
            {'quit_when':'account_switch_observed'}, {'submit_via':'flash'},
            {'screenshot_when':'hangar'}, {'quit_after_seconds':600},
            {'alternate_username':'else@example.test'}, {'username':None})]
        for value in cases:
            with self.subTest(value_keys=sorted(value)):
                with self.assertRaises(ValueError): self.consume(value)
                self.path.write_text(json.dumps(value), encoding='utf8')
                with patch.dict(sys.modules, {'long_hangar_scenario':self.module}):
                    with self.assertRaises(ValueError): runner.control_contract(self.path)
                self.module.arm.assert_not_called()
                self.view.onLogin.assert_not_called()

    def test_schema_failure_is_not_suppressed(self):
        self.module.checked_expected_primary.side_effect = ValueError('invalid expectation')
        with self.assertRaisesRegex(ValueError,'invalid expectation'): self.consume(self.value)
        self.module.arm.assert_not_called()
        self.view.onLogin.assert_not_called()

    def test_missing_compiled_module_refused_before_client_start(self):
        case = old_runner.DiagnosticClientRunTests()
        case.setUp(); self.addCleanup(case.doCleanups)
        case.put(case.control,self.value)
        with patch.dict(sys.modules, {'long_hangar_scenario':self.module}):
            with self.assertRaisesRegex(ValueError,'long hangar requires.*compiled scenario'):
                case.prepare()

    def test_capture_reserve_refuses_insufficient_packets_or_bytes(self):
        case = old_runner.DiagnosticClientRunTests()
        case.setUp(); self.addCleanup(case.doCleanups)
        case.put(case.control,self.value)
        # The actual source/bundle gate is covered independently. This double
        # isolates the reserve decision without allocating thousands of files.
        provenance = {'modules':[{'module':'long_hangar_scenario'}]}
        for packets in ([{'bytes':16}] * 5001, [{'bytes':runner.manual.MAX_PACKET_BYTES - 1024}]):
            with patch.dict(sys.modules, {'long_hangar_scenario':self.module}), \
                    patch.object(runner,'audit_sources',return_value=provenance), \
                    patch.object(runner.manual,'manifest',return_value=(0,packets,False)):
                with self.assertRaisesRegex(ValueError,'reserved capture capacity'):
                    case.prepare()

    def test_no_expectation_without_operation_and_normal_never_arms(self):
        value = dict(self.value); del value['verify_long_hangar']; del value['quit_when']
        with self.assertRaises(ValueError): self.consume(value)
        self.consume({'username':self.value['username'], 'password':self.value['password']})
        self.module.arm.assert_not_called()

    def test_public_host_metadata_only_adds_explicit_long_flag(self):
        self.path.write_text(json.dumps(self.value), encoding='utf8')
        with patch.dict(sys.modules, {'long_hangar_scenario':self.module}):
            public = runner.control_contract(self.path)
        self.assertTrue(public['verify_long_hangar'])
        self.assertEqual(len(public), 14)
        self.assertFalse(public['alternate_credentials_present'])
        self.assertFalse(public['plaintext_recorded'])
        for forbidden in ('sha256', 'long_hangar_expected', self.value['password'], self.value['username']):
            self.assertNotIn(forbidden, json.dumps(public))
        self.path.write_text(json.dumps({'export_ms1_crew':True,'quit_when':'ms1_crew_exported'}), encoding='utf8')
        self.assertNotIn('verify_long_hangar', runner.control_contract(self.path))

    def test_profiler_passes_original_return_primitive_fields_only(self):
        namespace = {'sys':SimpleNamespace(modules={'long_hangar_scenario':self.module}),
            'time':SimpleNamespace(clock=lambda:12.5), '_control':None, '_fini':False,
            '_profile_call_id':0, '_profile_frames':{},
            'record':lambda event,**fields:self.events.append((event,fields))}
        direct.trusted_functions({'profile_calls'}, namespace)
        owner = object()
        frame = SimpleNamespace(f_code=SimpleNamespace(co_filename='scripts/client/Account.py',
            co_name='receiveServerStats',co_firstlineno=679), f_locals={'self':owner}, f_lasti=16)
        namespace['profile_calls'](frame,'call',None)
        namespace['profile_calls'](frame,'return',None)
        self.module.note_stats_return.assert_not_called()
        namespace['_control'] = {'verify_long_hangar':True}
        namespace['profile_calls'](frame,'call',None)
        namespace['profile_calls'](frame,'return',None)
        self.module.note_stats_return.assert_called_once_with(id(owner),2,679,16,12.5)
        frame.f_lasti = 7
        namespace['profile_calls'](frame,'call',None)
        namespace['profile_calls'](frame,'return',None)
        self.assertEqual(self.module.note_stats_return.call_args.args,(id(owner),3,679,7,12.5))
        namespace['_fini'] = True
        namespace['profile_calls'](frame,'call',None)
        namespace['profile_calls'](frame,'return',None)
        self.assertEqual(self.module.note_stats_return.call_count,2)
        self.assertEqual(namespace['_profile_frames'],{})

    def test_exhausted_trace_fails_only_opt_in_and_quits_natively(self):
        quits = Mock()
        namespace = {'_fini':False, '_observations':0,
            '_stream':SimpleNamespace(tell=lambda:16*1024*1024+1),
            'sys':SimpleNamespace(setprofile=Mock(),modules={}), '_settings':{},
            '_control':{'verify_long_hangar':True},
            'record':lambda event,**fields:self.events.append((event,fields)), 'quit_client':quits}
        direct.trusted_functions({'observe','observation_byte_limit'},namespace)
        namespace['observe']()
        quits.assert_called_once_with()
        self.assertEqual([event for event,_ in self.events], ['observation_limit','diagnostic_condition_failed'])
        self.events.clear(); namespace['_control'] = None
        namespace['observe']()
        self.assertEqual(quits.call_count,1)
        self.assertEqual([event for event,_ in self.events], ['observation_limit'])


if __name__ == '__main__': unittest.main()
