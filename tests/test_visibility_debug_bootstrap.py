"""Optional diagnostics failures must not terminate or corrupt bootstrap."""
import ast
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'client_patch'))
import project_visibility_debug as debug


class Event(list):
    def __iadd__(self, callback):
        self.append(callback)
        return self
    def __isub__(self, callback):
        self.remove(callback)
        return self


class Host:
    def __init__(self): self.listeners = []
    def add(self, attach, detach, manager):
        self.listeners.append((attach, detach))
    def remove(self, attach, detach):
        self.listeners.remove((attach, detach))
        detach()


class OptionalDebugBootstrapTests(unittest.TestCase):
    def invoke(self, reason):
        source = (ROOT / 'client_patch/sr_interactive.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        helper = next(x for x in tree.body if isinstance(x, ast.FunctionDef)
                      and x.name == 'install_optional_visibility_debug')
        events = []
        ns = {'_settings': {'visibility_debug': {}},
              'record': lambda name, **fields: events.append((name, fields))}
        exec(compile(ast.Module(body=[helper], type_ignores=[]), '<trusted helper>', 'exec'), ns)
        fake = SimpleNamespace(validate_settings=lambda settings: None,
                               install=lambda *args: (_ for _ in ()).throw(reason))
        with patch.dict(sys.modules, {'project_visibility_debug': fake}):
            ns['install_optional_visibility_debug']()
        self.assertEqual(events, [('visibility_debug_unavailable', {'error_type': type(reason).__name__})])

    def test_missing_grant_and_native_contract_do_not_raise_or_quit(self):
        for error in (IOError('missing grant'), ValueError('native contract')):
            self.invoke(error)

    def test_partial_registration_is_unwound(self):
        class Arena:
            def update(self, kind, payload): pass
        original = Arena.update
        events = SimpleNamespace(onAvatarReady=Event(), onAvatarBecomeNonPlayer=Event())
        host = Host()
        engine = SimpleNamespace(callback=lambda *args: (_ for _ in ()).throw(RuntimeError('schedule failure')),
                                 cancelCallback=lambda token: None)
        modules = {'BigWorld': engine, 'GUI': SimpleNamespace(), 'Math': SimpleNamespace(),
                   'ClientArena': SimpleNamespace(ClientArena=Arena),
                   'AvatarInputHandler': SimpleNamespace(cameras=SimpleNamespace(getViewProjectionMatrix=lambda: None)),
                   'PlayerEvents': SimpleNamespace(g_playerEvents=events),
                   'gui.WindowsManager': SimpleNamespace(g_windowsManager=object()),
                   'project_battle_feed': SimpleNamespace(BATTLE=host),
                   'project_hit_indicator': SimpleNamespace(policy=lambda: object()),
                   'native_contract': SimpleNamespace(check=lambda *a: None)}
        settings = {'observer': 0, 'target': 1, 'run': '788fa1bf-8a21-4bdb-84de-a63310e390a3',
                    'grant_file': 'unused'}
        # Both pre-install errors must leave the native callback and listeners intact.
        for contract_error, grant_error in ((None, IOError('missing grant')),
                                            (ValueError('native contract'), None)):
            def check(*args):
                if contract_error: raise contract_error
            modules['native_contract'] = SimpleNamespace(check=check)
            with patch.dict(sys.modules, modules), patch.object(debug, 'read_grant', side_effect=grant_error,
                                                                  return_value=b'x' * 43):
                with self.assertRaises((IOError, ValueError)):
                    debug.install(lambda *a, **k: None, settings)
            self.assertIs(Arena.update, original)
            self.assertEqual((events.onAvatarReady, events.onAvatarBecomeNonPlayer, host.listeners), ([], [], []))
        modules['native_contract'] = SimpleNamespace(check=lambda *a: None)
        with patch.dict(sys.modules, modules), patch.object(debug, 'read_grant', return_value=b'x' * 43):
            with self.assertRaises(RuntimeError):
                debug.install(lambda *a, **k: None, settings)
        self.assertIs(Arena.update, original)
        self.assertEqual((events.onAvatarReady, events.onAvatarBecomeNonPlayer, host.listeners), ([], [], []))
        self.assertIsNone(debug._installed)


if __name__ == '__main__': unittest.main()
