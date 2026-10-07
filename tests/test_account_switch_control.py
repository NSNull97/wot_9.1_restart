"""Owned input/lifetime guards only; doubles never establish native isolation."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import diagnostic_client_run as runner
import test_interactive_relogin_control as direct
import test_diagnostic_client_run as old_runner


class SwitchControlTests(unittest.TestCase):
    def setUp(self):
        import os
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'control.json'
        self.events = []
        self.module = SimpleNamespace(arm=Mock(), clear_credentials=Mock(),
            checked_expected_accounts=Mock(side_effect=lambda value:value), note_login_result=Mock())
        # Deliberately tiny validator double: this test proves delegation and
        # secret lifetime, while the actual schema has its separate pure tests.
        self.expected = [{'native_id':1}, {'native_id':2}]
        self.value = {'username':'primary@example.test','password':'  primary unit secret  ',
            'alternate_username':'second@example.test','alternate_password':'  второй unit secret  ',
            'account_switch_expected':self.expected,'verify_account_switch':True,
            'submit_via':'python','quit_when':'account_switch_observed'}
        self.namespace = {'os':os,'json':json,'_control_done':False,
            '_settings':{'test_control':str(self.path),'local_root':self.temp.name,'endpoint':'127.0.0.1:20014'},
            'owned':lambda path, root:path,
            'record':lambda event, **fields:self.events.append((event,fields))}
        direct.trusted_functions({'consume_control'},self.namespace)
        self.view = SimpleNamespace(onLogin=Mock(),as_setDefaultValuesS=Mock(),as_doAutoLoginS=Mock())

    def consume(self, value):
        self.path.write_text(json.dumps(value,ensure_ascii=False),encoding='utf8')
        with patch.dict(sys.modules,{'account_switch_scenario':self.module}):
            self.namespace['consume_control'](self.view)

    def check_redaction(self, value):
        serialized = json.dumps(value,ensure_ascii=False)
        for key in ('username','password','alternate_username','alternate_password'):
            self.assertNotIn(self.value[key],serialized)

    def test_actual_first_submit_and_one_arm_preserve_passwords_then_consume_control(self):
        self.consume(self.value)
        self.module.checked_expected_accounts.assert_called_once_with(self.expected)
        self.module.arm.assert_called_once_with(
            {'username':self.value['username'],'password':self.value['password']},
            {'username':self.value['alternate_username'],'password':self.value['alternate_password']},self.expected)
        self.view.onLogin.assert_called_once_with(self.value['username'],self.value['password'],'127.0.0.1:20014')
        self.assertFalse(self.path.exists())
        self.check_redaction(self.events)
        self.check_redaction(self.namespace['_control'])
        self.assertNotIn('account_switch_expected',self.namespace['_control'])
        self.namespace['consume_control'](self.view)
        self.assertEqual(self.module.arm.call_count,1)

    def test_missing_alternate_or_expectations_and_wrong_modes_fail_before_arm(self):
        cases = []
        for key in ('username','password','alternate_username','alternate_password','account_switch_expected'):
            value = dict(self.value); del value[key]; cases.append(value)
        cases += [dict(self.value,**changes) for changes in (
            {'verify_account_switch':1},{'verify_inprocess_relogin':True},
            {'quit_when':None},{'quit_when':'inprocess_relogin_observed'},
            {'submit_via':'flash'},{'screenshot_when':'hangar'},{'quit_after_seconds':60},
            {'alternate_username':' PRIMARY@EXAMPLE.TEST '},{'alternate_password':['not-text']},
            {'username':None})]
        for value in cases:
            with self.subTest(keys=list(value)):
                with self.assertRaises(ValueError):self.consume(value)
                self.module.arm.assert_not_called()
                self.view.onLogin.assert_not_called()

    def test_expected_validator_failure_is_not_ignored(self):
        self.module.checked_expected_accounts.side_effect = ValueError('bounded expectations rejected')
        with self.assertRaisesRegex(ValueError,'bounded expectations'):self.consume(self.value)
        self.module.arm.assert_not_called()
        self.view.onLogin.assert_not_called()

    def test_alternate_fields_require_explicit_switch_and_normal_does_not_arm(self):
        for key in ('alternate_username','alternate_password','account_switch_expected'):
            value = {'username':self.value['username'],'password':self.value['password'],key:self.value[key]}
            with self.assertRaises(ValueError):self.consume(value)
        self.consume({'username':self.value['username'],'password':self.value['password']})
        self.module.arm.assert_not_called()
        self.module.checked_expected_accounts.assert_not_called()

    def test_runner_metadata_is_redacted_and_bad_expectations_rejected(self):
        self.path.write_text(json.dumps(self.value,ensure_ascii=False),encoding='utf8')
        with patch.dict(sys.modules,{'account_switch_scenario':self.module}):
            result = runner.control_contract(self.path)
            self.assertTrue(result['verify_account_switch'])
            self.assertTrue(result['alternate_credentials_present'])
            self.assertEqual(result['quit_when'],'account_switch_observed')
            self.check_redaction(result)
            self.module.checked_expected_accounts.side_effect = ValueError('bounded expectations rejected')
            with self.assertRaisesRegex(ValueError,'bounded expectations'):runner.control_contract(self.path)

    def test_runner_rejects_same_canonical_account_and_alternate_without_operation(self):
        cases = [dict(self.value,alternate_username=' PRIMARY@EXAMPLE.TEST '),
                 dict(self.value,alternate_password=None),dict(self.value,verify_inprocess_relogin=True)]
        normal = {'export_ms1_crew':True,'quit_when':'ms1_crew_exported'}
        cases.extend(dict(normal,**{key:self.value[key]}) for key in
                     ('alternate_username','alternate_password','account_switch_expected'))
        for value in cases:
            self.path.write_text(json.dumps(value),encoding='utf8')
            with self.assertRaises(ValueError):runner.control_contract(self.path)

    def test_compiled_scenario_is_required_before_any_client_spawn(self):
        case = old_runner.DiagnosticClientRunTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        case.put(case.control,self.value)
        with patch.dict(sys.modules,{'account_switch_scenario':self.module}):
            with self.assertRaisesRegex(ValueError,'account switch requires.*compiled scenario'):
                case.prepare()

    def test_passive_callback_ignores_normal_fini_and_server_message(self):
        events = []
        namespace = {'sys':SimpleNamespace(modules={'account_switch_scenario':self.module}),
            '_control':None,'_fini':False,'record':lambda event,**fields:events.append((event,fields))}
        direct.trusted_functions({'connection_status'},namespace)
        manager = SimpleNamespace(connectionManager=SimpleNamespace(isConnected=lambda:False))
        with patch.dict(sys.modules,{'ConnectionManager':manager}):
            namespace['connection_status'](1,'LOGGED_ON','do-not-log-server-message',False)
            self.module.note_login_result.assert_not_called()
            namespace['_control'] = {'verify_account_switch':True}
            namespace['connection_status'](1,'LOGGED_ON','do-not-log-server-message',False)
            self.module.note_login_result.assert_called_once_with(1,'LOGGED_ON')
            namespace['_fini'] = True
            namespace['connection_status'](1,'LOGGED_ON','do-not-log-server-message',False)
            self.assertEqual(self.module.note_login_result.call_count,1)
        self.assertNotIn('do-not-log-server-message',json.dumps(events))

    def test_cleanup_never_imports_scenario_in_normal_use(self):
        namespace = {'sys':SimpleNamespace(modules={})}
        direct.trusted_functions({'clear_account_switch_credentials'},namespace)
        namespace['clear_account_switch_credentials']()
        namespace['sys'].modules['account_switch_scenario'] = self.module
        namespace['clear_account_switch_credentials']()
        self.module.clear_credentials.assert_called_once_with()


if __name__ == '__main__':unittest.main()
