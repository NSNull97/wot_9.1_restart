"""Owned control/lifetime logic only; isolated doubles never prove native relogin."""
import ast
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

SOURCE = Path(__file__).resolve().parents[1] / 'client_patch/sr_interactive.py'


def trusted_functions(names, namespace):
    tree = ast.parse(SOURCE.read_bytes())
    found = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert len(found) == len(names)
    exec(compile(ast.Module(body=found, type_ignores=[]), str(SOURCE), 'exec'), namespace)


class ReloginControlTests(unittest.TestCase):
    def setUp(self):
        import os
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'control.json'
        self.events = []
        self.namespace = {'os':os, 'json':json, '_control_done':False,
            '_settings': {'test_control':str(self.path), 'local_root':self.temp.name, 'endpoint':'127.0.0.1:20014'},
            'owned':lambda path, root: path,
            'record':lambda event, **fields: self.events.append((event, fields))}
        trusted_functions({'consume_control'}, self.namespace)
        self.module = SimpleNamespace(arm=Mock(), clear_credentials=Mock())
        self.view = SimpleNamespace(onLogin=Mock(), as_setDefaultValuesS=Mock(), as_doAutoLoginS=Mock())
        self.value = {'verify_inprocess_relogin':True, 'quit_when':'inprocess_relogin_observed',
                      'username':'own@example.test', 'password':'owned-unit-secret-987', 'submit_via':'python'}

    def consume(self, value):
        self.path.write_text(json.dumps(value), encoding='utf8')
        with patch.dict(sys.modules, {'hangar_relogin_scenario':self.module}):
            self.namespace['consume_control'](self.view)

    def test_only_explicit_control_arms_once_then_original_login_and_consumes_file(self):
        self.consume(self.value)
        self.assertFalse(self.path.exists())
        self.module.arm.assert_called_once_with(self.value['username'], self.value['password'])
        self.view.onLogin.assert_called_once_with(self.value['username'], self.value['password'], '127.0.0.1:20014')
        self.assertNotIn(self.value['username'], json.dumps(self.events))
        self.assertNotIn(self.value['password'], json.dumps(self.events))
        self.namespace['consume_control'](self.view)
        self.assertEqual(self.view.onLogin.call_count, 1)

    def test_normal_control_does_not_import_or_arm_relogin(self):
        value = dict(self.value)
        del value['verify_inprocess_relogin']
        del value['quit_when']
        self.consume(value)
        self.module.arm.assert_not_called()
        self.view.onLogin.assert_called_once()

    def test_missing_credentials_and_mixed_modes_rejected_before_any_submit(self):
        cases = [{'verify_inprocess_relogin':True, 'quit_when':'inprocess_relogin_observed'}]
        for extra in ({'quit_when':None}, {'quit_when':'hangar_windows_observed'},
                      {'verify_hangar_windows':True}, {'verify_inprocess_relogin':1},
                      {'submit_via':'flash'}, {'quit_after_seconds':60}, {'screenshot_when':'hangar'}):
            cases.append(dict(self.value, **extra))
        for value in cases:
            with self.subTest(keys=list(value)):
                with self.assertRaises(ValueError):
                    self.consume(value)
                self.module.arm.assert_not_called()
                self.view.onLogin.assert_not_called()
                self.view.as_doAutoLoginS.assert_not_called()

    def test_secret_cleanup_skips_normal_module_and_clears_loaded_diagnostic(self):
        namespace = {'sys':SimpleNamespace(modules={})}
        trusted_functions({'clear_relogin_credentials'}, namespace)
        namespace['clear_relogin_credentials']()
        namespace['sys'].modules['hangar_relogin_scenario'] = self.module
        namespace['clear_relogin_credentials']()
        self.module.clear_credentials.assert_called_once_with()


class ReloginPassiveTraceTests(unittest.TestCase):
    def test_connection_result_is_passive_opt_in_and_excludes_server_message(self):
        events = []
        scenario = SimpleNamespace(note_login_result=Mock())
        namespace = {'sys':SimpleNamespace(modules={'hangar_relogin_scenario':scenario}),
                     '_fini':False, '_control':None,
                     'record':lambda event, **fields: events.append((event, fields))}
        trusted_functions({'connection_status'}, namespace)
        manager = SimpleNamespace(connectionManager=SimpleNamespace(isConnected=lambda:False))
        with patch.dict(sys.modules, {'ConnectionManager':manager}):
            namespace['connection_status'](1, 'LOGIN_REJECTED_SERVER_NOT_READY', 'private-server-message', False)
            scenario.note_login_result.assert_not_called()
            namespace['_control'] = {'verify_inprocess_relogin':True}
            namespace['connection_status'](1, 'LOGIN_REJECTED_SERVER_NOT_READY', 'private-server-message', False)
            scenario.note_login_result.assert_called_once_with(1, 'LOGIN_REJECTED_SERVER_NOT_READY')
            namespace['_fini'] = True
            namespace['connection_status'](1, 'LOGIN_REJECTED_SERVER_NOT_READY', 'private-server-message', False)
            self.assertEqual(scenario.note_login_result.call_count, 1)
        self.assertNotIn('private-server-message', json.dumps(events))
        self.assertEqual(len(events), 3)

    def test_exact_lifecycle_targets_record_no_credential_locals(self):
        events = []
        namespace = {'_profile_call_id':0, '_profile_frames':{},
                     'record':lambda event, **fields: events.append((event, fields))}
        trusted_functions({'profile_calls'}, namespace)
        targets = [('scripts/client/gui/Scaleform/AppEntry.py', 'logoff'),
                   ('scripts/client/gui/Scaleform/framework/application.py', 'disconnect'),
                   ('scripts/client/gui/Scaleform/framework/application.py', 'logoff'),
                   ('scripts/client/gui/Scaleform/framework/application.py', 'logOff'),
                   ('scripts/client/ConnectionManager.py', 'disconnect'),
                   ('scripts/client/Account.py', '_delAccountRepository')]
        for source, name in targets:
            frame = SimpleNamespace(f_code=SimpleNamespace(co_filename=source, co_name=name, co_firstlineno=1),
                f_lasti=0, f_locals={'self':object(), 'password':'never-emit-unit-secret', 'username':'private@example.test'})
            namespace['profile_calls'](frame, 'call', None)
            namespace['profile_calls'](frame, 'return', None)
        self.assertEqual(len(events), 12)
        self.assertEqual({event for event, fields in events}, {'native_logoff_call'})
        self.assertNotIn('never-emit-unit-secret', json.dumps(events))
        self.assertNotIn('private@example.test', json.dumps(events))
        self.assertEqual(namespace['_profile_frames'], {})


if __name__ == '__main__':
    unittest.main()
