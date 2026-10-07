"""One-shot local login permission shape; no mock native-game acceptance."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


class SharedControlTests(unittest.TestCase):
    def test_aim_receipt_pairs_original_callbacks_without_gameplay_writes_or_private_locals(self):
        source = Path(__file__).resolve().parents[1] / 'client_patch/sr_interactive.py'
        tree = ast.parse(source.read_bytes())
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                     and node.name == 'profile_calls']
        calls = []
        namespace = dict(_settings={'enable_shared_lab': True}, _control=None,
                         _profile_call_id=0, _profile_frames={},
                         primitive=lambda value, **kwargs: value,
                         record=lambda event, **fields: calls.append((event, fields)))
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), 'exec'), namespace)
        for method, name in [('set_gunAnglesPacked', 'Vehicle'), ('updateTargetingInfo', 'Avatar')]:
            instance = SimpleNamespace(id=152043525, gunAnglesPacked=32895)
            frame = SimpleNamespace(f_code=SimpleNamespace(co_filename='scripts/client/'+name+'.py',
                co_name=method, co_firstlineno=1), f_lasti=0,
                f_locals={'self': instance, 'turretYaw': 0.25, 'gunPitch': -0.1,
                          'private': object()})
            before = vars(instance).copy()
            namespace['profile_calls'](frame, 'call', None)
            namespace['profile_calls'](frame, 'return', None)
            self.assertEqual(vars(instance), before)
        self.assertEqual([event for event, _ in calls], ['native_shared_aim_call'] * 4)
        self.assertEqual(calls[2][1]['targeting'][:2], [0.25, -0.1])
        self.assertEqual(calls[0][1]['gun_angles_packed'], 32895)
        self.assertTrue(all('private' not in str(fields) for _, fields in calls))
        self.assertFalse(namespace['_profile_frames'])
        for value in [False, 1, None]:
            namespace['_settings']['enable_shared_lab'] = value
            namespace['profile_calls'](frame, 'call', None)
        self.assertEqual(len(calls), 4)

    def test_passive_shot_receipt_reads_only_bounded_original_handler_fields(self):
        source = Path(__file__).resolve().parents[1] / 'client_patch/sr_interactive.py'
        tree = ast.parse(source.read_bytes())
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                     and node.name == 'profile_calls']
        calls = []
        namespace = dict(_settings={'enable_shared_lab': True}, _control=None,
                         _profile_call_id=0, _profile_frames={},
                         primitive=lambda value, **kwargs: value,
                         record=lambda event, **fields: calls.append((event, fields)))
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), 'exec'), namespace)
        instance = SimpleNamespace(id=152043525, isStarted=True, isPlayer=False)
        frame = SimpleNamespace(f_code=SimpleNamespace(co_filename='scripts/client/Vehicle.py',
            co_name='showShooting', co_firstlineno=1), f_lasti=0,
            f_locals={'self': instance, 'burstCount': 1, 'isPredictedShot': False,
                      'unrelated_private_value': 'must not be copied'})
        namespace['profile_calls'](frame, 'call', None)
        frame.f_lasti = 183
        namespace['profile_calls'](frame, 'return', None)
        self.assertEqual([event for event, _ in calls], ['native_shared_shooting_call'] * 2)
        for _, fields in calls:
            self.assertEqual(fields['entity_id'], 152043525)
            self.assertEqual(fields['burstCount'], 1)
            self.assertIs(fields['isPredictedShot'], False)
            self.assertIs(fields['is_player'], False)
            self.assertNotIn('must not be copied', str(fields))
        self.assertFalse(namespace['_profile_frames'])
        namespace['_settings'] = {}
        namespace['profile_calls'](frame, 'call', None)
        self.assertEqual(len(calls), 2)

    def test_passive_tracer_and_mover_receipts_keep_fixed_arguments_only(self):
        source = Path(__file__).resolve().parents[1] / 'client_patch/sr_interactive.py'
        tree = ast.parse(source.read_bytes())
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                     and node.name == 'profile_calls']
        calls = []
        namespace = dict(_settings={'enable_shared_lab': True}, _control=None,
                         _profile_call_id=0, _profile_frames={}, _shared_vector=lambda value: list(value),
                         primitive=lambda value, **kwargs: value,
                         record=lambda event, **fields: calls.append((event, fields)))
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), 'exec'), namespace)
        avatar = SimpleNamespace(id=152043524, playerVehicleID=152043525)
        show = SimpleNamespace(f_code=SimpleNamespace(co_filename='scripts/client/Avatar.py',
            co_name='showTracer', co_firstlineno=1683), f_lasti=0,
            f_locals={'self': avatar, 'shooterID': 152043523, 'shotID': 7, 'effectsIndex': 2,
                      'refStartPoint': (1., 2., 3.), 'velocity': (0., 1., 353.6),
                      'gravity': 6.2784, 'maxShotDist': 720., 'private': object()})
        namespace['profile_calls'](show, 'call', None)
        namespace['profile_calls'](show, 'return', None)
        stop = SimpleNamespace(f_code=SimpleNamespace(co_filename='scripts/client/Avatar.py',
            co_name='stopTracer', co_firstlineno=1716), f_lasti=0,
            f_locals={'self': avatar, 'shotID': 7, 'endPoint': (4., 5., 6.), 'private': object()})
        namespace['profile_calls'](stop, 'call', None)
        namespace['profile_calls'](stop, 'return', None)
        self.assertEqual([event for event, _ in calls], ['native_shared_tracer_call'] * 4)
        self.assertEqual(calls[0][1]['effectsIndex'], 2)
        self.assertEqual(calls[0][1]['refStartPoint'], [1., 2., 3.])
        self.assertNotIn('private', str(calls))
        mover = SimpleNamespace()
        add = SimpleNamespace(f_code=SimpleNamespace(co_filename='scripts/client/ProjectileMover.py',
            co_name='add', co_firstlineno=74), f_lasti=0,
            f_locals={'self': mover, 'shotID': 7, 'effectsDescr':
                      {'projectile': ('objects/a.model', 'objects/b.model', object())},
                      'gravity': 6.2784, 'refStartPoint': (1., 2., 3.),
                      'refVelocity': (0., 1., 353.6), 'startPoint': (1., 2., 3.),
                      'maxDistance': 720., 'isOwnShoot': False,
                      'tracerCameraPos': object()})
        namespace['profile_calls'](add, 'call', None)
        namespace['profile_calls'](add, 'return', None)
        self.assertEqual([event for event, _ in calls[-2:]], ['native_shared_projectile_mover_call'] * 2)
        self.assertEqual(calls[-1][1]['projectile_models'], ['objects/a.model', 'objects/b.model'])

    def test_only_explicit_shared_install_accepts_login_only_control(self):
        source = Path(__file__).resolve().parents[1] / 'client_patch/sr_interactive.py'
        tree = ast.parse(source.read_bytes())
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                     and node.name == 'shared_login_control']
        self.assertEqual(len(functions), 1)
        namespace = {}
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), 'exec'), namespace)
        check = namespace['shared_login_control']
        control = {'username': 'owned@example.invalid', 'password': 'unit-only', 'submit_via': 'python'}
        self.assertTrue(check(control, {'enable_shared_lab': True}))
        for settings in ({}, {'enable_shared_lab': False}, {'enable_shared_lab': 1}):
            self.assertFalse(check(control, settings))
        for extra in ('quit_after_seconds', 'probe_map_drive', 'screenshot_when', 'ui_scenario'):
            self.assertFalse(check(dict(control, **{extra: None}), {'enable_shared_lab': True}))
        self.assertFalse(check(dict(control, submit_via='flash'), {'enable_shared_lab': True}))


if __name__ == '__main__':
    unittest.main()
