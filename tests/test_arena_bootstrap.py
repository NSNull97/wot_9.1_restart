# -*- coding: utf-8 -*-
"""Host-only ownership/lifecycle controls; synthetic services are not native proof."""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'client_patch'))
import arena_bootstrap as bootstrap


class Box(object):
    def __init__(self, **fields):
        self.__dict__.update(fields)


class Section(object):
    def __init__(self, children=None, value=None):
        self.children = list(children or [])
        self.value = value

    def items(self):
        return list(self.children)

    def __getitem__(self, key):
        for name, child in self.children:
            if name == key:
                return child
        return None

    def readFloat(self, key):
        return float(self[key].value)

    def readString(self, key):
        return self[key].value

    def readVector4(self, key):
        parent, child = key.split('/')
        value = self[parent][child].value
        return Box(**dict(zip(('x', 'y', 'z', 'w'), value)))


def original_config_shape():
    groups = Section([(name, Section([
        ('lifeTime', Section(value=pair[0])),
        ('trianglesCount', Section(value=pair[1]))]))
        for name, pair in bootstrap.GROUPS.items()])
    textures = Section([(name, Section([('texture', Section(value=path))]))
                        for name, path in bootstrap.TEXTURES.items()])
    decal = Section([('criticalAngle', Section(value=30)), ('groups', groups),
                     ('textures', textures)])
    colors = Section([(mode, Section([(name, Section(value=bootstrap.COLORS[mode + '/' + name]))
                                     for name in ('self', 'enemy', 'friend')]))
                      for mode in ('common', 'colorBlind')])
    return Section([('decal', decal), ('silhouetteColors', colors)])


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        names = ('_load_context', '_sources', '_bindings', 'SOURCE_HASHES', '_record',
                 '_context', '_owned', '_attempted', '_before', '_after', '_errors', '_destroyed')
        self.saved = dict((name, getattr(bootstrap, name)) for name in names)
        bootstrap._record, bootstrap._context = None, None
        bootstrap._owned, bootstrap._errors, bootstrap._destroyed = {}, [], set()
        bootstrap._attempted = bootstrap._before = bootstrap._after = False
        self.events, self.calls = [], []
        self.record = lambda event, **data: self.events.append((event, data))
        self.fail_init = None
        self.fail_destroy = None
        case = self

        class Decal:
            def __init__(self, section):
                case.calls.append('decal.init')
                if case.fail_init == 'decal':
                    raise RuntimeError('synthetic decal failure')
                self.section = section

        class Edge:
            def __init__(self, section):
                case.calls.append('edge.init')
                if case.fail_init == 'edge':
                    raise RuntimeError('synthetic edge failure')
                self.section = section
                self.destroyed = False

            def destroy(self):
                case.calls.append('edge.destroy')
                if case.fail_destroy == 'edge':
                    raise RuntimeError('synthetic edge destroy failure')
                self.destroyed = True

        class Triggers:
            def __init__(self):
                case.calls.append('triggers.init')
                if case.fail_init == 'triggers':
                    raise RuntimeError('synthetic trigger failure')
                self.destroyed = False

            def destroy(self):
                case.calls.append('triggers.destroy')
                if case.fail_destroy == 'triggers':
                    raise RuntimeError('synthetic trigger destroy failure')
                self.destroyed = True

            def enable(self, value):
                case.calls.append(('triggers.enable', value))

        class Avatar(object):
            pass

        self.player = object()
        self.entities = {}
        self.opened = []
        chassis = Section([('bufferPrefs', Section()), ('textureSets', Section())])

        def open_section(path):
            self.opened.append(path)
            return chassis

        triggers = Box(TriggersManager=Triggers, g_manager=None)

        def init_triggers():
            triggers.g_manager = Triggers()

        triggers.init = init_triggers
        self.context = {
            'decal': Box(DecalMap=Decal, g_instance=None),
            'edge': Box(EdgeDetectColorController=Edge, g_instance=None),
            'triggers': triggers, 'script_config': original_config_shape(),
            'resources': Box(openSection=open_section),
            'engine': Box(player=lambda: self.player, entities=self.entities),
            'avatar_class': Avatar,
        }
        bootstrap._load_context = lambda: self.context
        bootstrap._sources = lambda root: []
        bootstrap._bindings = lambda context: None
        self.directory = tempfile.mkdtemp(prefix='arena-bootstrap-controls-')

    def tearDown(self):
        for name, value in self.saved.items():
            setattr(bootstrap, name, value)
        shutil.rmtree(self.directory)

    def phases(self, name):
        return [row for event, row in self.events if row['phase'] == name]

    def test_original_order_preserves_trigger_until_native_leave(self):
        bootstrap.init(self.record)
        trigger = self.context['triggers'].g_manager
        self.player = self.context['avatar_class']()
        self.entities[1] = self.player
        bootstrap.fini_before_entities()
        self.assertIs(self.context['triggers'].g_manager, trigger)
        self.assertTrue(trigger.destroyed)
        self.assertIsNone(self.context['edge'].g_instance)
        self.assertIsNotNone(self.context['decal'].g_instance)
        self.context['triggers'].g_manager.enable(False)
        self.player = None
        self.entities.clear()
        bootstrap.fini_after_entities()
        self.assertEqual(self.calls, ['decal.init', 'edge.init', 'triggers.init',
                                     'triggers.destroy', 'edge.destroy', ('triggers.enable', False)])
        self.assertTrue(all(getattr(self.context[key], bootstrap._slot(key)) is None
                            for key in ('triggers', 'edge', 'decal')))
        self.assertEqual([row['stage'] for row in self.phases('restore_return')],
                         ['triggers', 'edge', 'decal'])
        self.assertFalse(self.phases('ready')[0]['native_lifecycle_forced'])

    def test_service_constructors_receive_actual_validated_sections(self):
        bootstrap.init(self.record)
        self.assertIs(self.context['decal'].g_instance.section, self.context['script_config']['decal'])
        self.assertIs(self.context['edge'].g_instance.section, self.context['script_config']['silhouetteColors'])
        self.assertEqual(self.opened, ['scripts/item_defs/vehicles/common/chassis_effects.xml/decals'])

    def test_exact_old_style_instances_match_their_class_not_instance_type(self):
        bootstrap.init(self.record)
        for key, class_name in (('decal', 'DecalMap'), ('edge', 'EdgeDetectColorController'),
                                ('triggers', 'TriggersManager')):
            expected = getattr(self.context[key], class_name)
            instance = getattr(self.context[key], bootstrap._slot(key))
            self.assertTrue(bootstrap._exact_instance(instance, expected))
            self.assertIs(instance.__class__, expected)
            if sys.version_info[0] == 2:
                self.assertIs(type(expected), types.ClassType)
                self.assertIs(type(instance), types.InstanceType)
                self.assertIsNot(type(instance), expected)
        self.assertEqual(len(self.phases('init_return')), 3)
        expected_model = 'python2_old_style' if sys.version_info[0] == 2 else 'new_style'
        self.assertEqual([r['class_model'] for r in self.phases('init_return')], [expected_model] * 3)

    def test_old_style_subclass_foreign_class_and_same_name_are_rejected(self):
        expected = self.context['decal'].DecalMap
        class Child(expected):
            pass
        class Foreign:
            pass
        if sys.version_info[0] == 2:
            same_name = types.ClassType(expected.__name__, (), {})
        else:
            same_name = type(expected.__name__, (), {})
        for instance in (Child(None), Foreign(), same_name(), None, object()):
            self.assertFalse(bootstrap._exact_instance(instance, expected))

    def test_new_style_exact_only_and_spoofed_class_is_rejected(self):
        class Expected(object):
            pass
        class Child(Expected):
            pass
        class Spoof(object):
            @property
            def __class__(self):
                return Expected
        self.assertTrue(bootstrap._exact_instance(Expected(), Expected))
        self.assertFalse(bootstrap._exact_instance(Child(), Expected))
        self.assertIs(Spoof().__class__, Expected)
        self.assertFalse(bootstrap._exact_instance(Spoof(), Expected))
        old_expected = self.context['decal'].DecalMap
        class OldSpoof(object):
            @property
            def __class__(self):
                return old_expected
        self.assertFalse(bootstrap._exact_instance(OldSpoof(), old_expected))

    def test_wrong_trigger_factory_fails_and_does_not_publish_ready(self):
        class Wrong:
            def destroy(self):
                pass
        def wrong_factory():
            self.context['triggers'].g_manager = Wrong()
        self.context['triggers'].init = wrong_factory
        self.assertRaises(ValueError, bootstrap.init, self.record)
        self.assertEqual(self.phases('ready'), [])
        self.assertEqual(self.phases('init_error')[0]['error_type'], 'ValueError')

    def test_second_init_refused_and_cleanup_idempotent(self):
        bootstrap.init(self.record)
        self.assertRaises(RuntimeError, bootstrap.init, self.record)
        bootstrap.fini_before_entities()
        bootstrap.fini_after_entities()
        calls, events = list(self.calls), list(self.events)
        bootstrap.fini_before_entities()
        bootstrap.fini_after_entities()
        self.assertEqual((self.calls, self.events), (calls, events))

    def test_cleanup_before_any_init_is_passive(self):
        bootstrap.fini_before_entities()
        bootstrap.fini_after_entities()
        self.assertEqual((self.calls, self.events), ([], []))

    def test_release_before_precleanup_refused(self):
        bootstrap.init(self.record)
        self.assertRaises(RuntimeError, bootstrap.fini_after_entities)
        self.assertEqual(self.calls, ['decal.init', 'edge.init', 'triggers.init'])

    def test_release_with_avatar_player_refused_without_clearing_globals(self):
        bootstrap.init(self.record)
        trigger = self.context['triggers'].g_manager
        bootstrap.fini_before_entities()
        self.player = self.context['avatar_class']()
        self.assertRaises(RuntimeError, bootstrap.fini_after_entities)
        self.assertIs(self.context['triggers'].g_manager, trigger)
        self.assertFalse(bootstrap._after)

    def test_release_with_nonplayer_avatar_refused(self):
        bootstrap.init(self.record)
        bootstrap.fini_before_entities()
        self.entities[2] = self.context['avatar_class']()
        self.assertRaises(RuntimeError, bootstrap.fini_after_entities)
        self.entities.clear()
        bootstrap.fini_after_entities()
        self.assertTrue(bootstrap._after)

    def test_existing_singleton_not_overwritten_even_on_followup_cleanup(self):
        foreign = object()
        self.context['edge'].g_instance = foreign
        self.assertRaises(RuntimeError, bootstrap.init, self.record)
        self.assertEqual(self.calls, [])
        bootstrap.fini_before_entities()
        bootstrap.fini_after_entities()
        self.assertIs(self.context['edge'].g_instance, foreign)

    def test_avatar_before_init_is_rejected_before_constructor(self):
        self.player = self.context['avatar_class']()
        self.assertRaises(RuntimeError, bootstrap.init, self.record)
        self.assertEqual(self.calls, [])

    def test_entity_count_bound_rejects_before_constructor(self):
        self.entities.update((i, object()) for i in range(65))
        self.assertRaises(RuntimeError, bootstrap.init, self.record)
        self.assertEqual(self.calls, [])

    def test_source_failure_has_no_services_and_no_ready(self):
        def fail(root):
            raise ValueError('synthetic original source drift')
        bootstrap._sources = fail
        self.assertRaises(ValueError, bootstrap.init, self.record)
        bootstrap.fini_before_entities()
        bootstrap.fini_after_entities()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.phases('ready'), [])

    def test_context_import_failure_can_be_cleaned_without_invented_services(self):
        def fail():
            raise ImportError('synthetic unavailable module')
        bootstrap._load_context = fail
        self.assertRaises(ImportError, bootstrap.init, self.record)
        bootstrap.fini_before_entities()
        bootstrap.fini_after_entities()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.phases('restore_return'), [])

    def test_partial_initialization_restores_prior_instances(self):
        self.fail_init = 'triggers'
        self.assertRaises(RuntimeError, bootstrap.init, self.record)
        self.assertEqual(self.calls, ['decal.init', 'edge.init', 'triggers.init', 'edge.destroy'])
        self.assertTrue(all(getattr(self.context[key], bootstrap._slot(key)) is None
                            for key in ('triggers', 'edge', 'decal')))
        self.assertEqual(self.phases('ready'), [])
        self.assertEqual(self.phases('init_error')[0]['cleanup_errors'], [])

    def test_destroy_error_does_not_skip_other_service_and_remains_failure(self):
        bootstrap.init(self.record)
        self.fail_destroy = 'triggers'
        self.assertRaises(RuntimeError, bootstrap.fini_before_entities)
        self.assertIn('edge.destroy', self.calls)
        self.assertIsNone(self.context['edge'].g_instance)
        self.assertRaises(RuntimeError, bootstrap.fini_after_entities)
        self.assertEqual(len(self.phases('destroy_error')), 1)
        self.assertTrue(self.phases('after_entities_complete')[0]['errors'])

    def test_foreign_replacement_is_preserved_and_other_cleanup_runs(self):
        bootstrap.init(self.record)
        foreign = object()
        self.context['triggers'].g_manager = foreign
        self.assertRaises(RuntimeError, bootstrap.fini_before_entities)
        self.assertEqual(self.calls[-1], 'edge.destroy')
        self.assertNotIn('triggers.destroy', self.calls)
        self.assertRaises(RuntimeError, bootstrap.fini_after_entities)
        self.assertIs(self.context['triggers'].g_manager, foreign)
        self.assertIsNone(self.context['decal'].g_instance)

    def test_foreign_post_destroy_replacement_never_overwritten(self):
        bootstrap.init(self.record)
        bootstrap.fini_before_entities()
        foreign = object()
        self.context['edge'].g_instance = foreign
        self.assertRaises(RuntimeError, bootstrap.fini_after_entities)
        self.assertIs(self.context['edge'].g_instance, foreign)
        self.assertIsNone(self.context['decal'].g_instance)

    def test_config_unknown_or_duplicate_sections_refused(self):
        decal = self.context['script_config']['decal']
        decal.children[0] = ('unknown', Section(value=30))
        self.assertRaises(ValueError, bootstrap.init, self.record)
        self.assertEqual(self.calls, [])
        duplicate = Section([('a', Section()), ('a', Section())])
        self.assertRaises(ValueError, bootstrap._children, duplicate, ('a', 'b'), 'synthetic')

    def test_changed_decal_group_refused(self):
        self.context['script_config']['decal']['groups']['slow']['lifeTime'].value = 99
        self.assertRaises(ValueError, bootstrap.init, self.record)
        self.assertEqual(self.calls, [])

    def test_changed_texture_or_missing_chassis_refused(self):
        self.context['script_config']['decal']['textures']['explosion']['texture'].value = '../other.dds'
        self.assertRaises(ValueError, bootstrap._config, self.context)
        self.context['script_config'] = original_config_shape()
        self.context['resources'].openSection = lambda path: None
        self.assertRaises(ValueError, bootstrap._config, self.context)

    def test_color_float32_rounding_accepted_but_changes_nan_rejected(self):
        value = self.context['script_config']['silhouetteColors']['common']['enemy']
        value.value = (1.0, 0.07000000029802322, 0.027000000700354576, 1.0)
        config, _, _ = bootstrap._config(self.context)
        self.assertEqual(config['colors']['common/enemy'], list(value.value))
        value.value = (1.0, 0.07002, 0.027, 1.0)
        self.assertRaises(ValueError, bootstrap._config, self.context)
        value.value = (1.0, float('nan'), 0.027, 1.0)
        self.assertRaises(ValueError, bootstrap._config, self.context)

    def test_original_binding_gate_rejects_synthetic_service_code(self):
        self.assertRaises(ValueError, self.saved['_bindings'], self.context)

    def test_record_bounds_apply_to_every_event(self):
        bootstrap.init(self.record)
        bootstrap.fini_before_entities()
        bootstrap.fini_after_entities()
        for event, value in self.events:
            self.assertEqual(event, 'arena_bootstrap')
            self.assertLessEqual(len(json.dumps(value, ensure_ascii=True).encode('ascii')), 8192)
        self.assertRaises(ValueError, bootstrap._emit, 'synthetic', too_large='x' * 8192)

    def test_source_guard_checks_exact_bytes_and_bound(self):
        relative = 'source.bin'
        path = os.path.join(self.directory, relative)
        raw = b'original bytes'
        with open(path, 'wb') as stream:
            stream.write(raw)
        bootstrap.SOURCE_HASHES = ((relative, hashlib.sha256(raw).hexdigest()),)
        audit = self.saved['_sources'](self.directory)
        self.assertEqual(audit[0]['bytes'], len(raw))
        with open(path, 'wb') as stream:
            stream.write(b'changed! bytes')
        self.assertRaises(ValueError, self.saved['_sources'], self.directory)
        with open(path, 'wb') as stream:
            stream.write(b'')
        self.assertRaises(ValueError, self.saved['_sources'], self.directory)
        self.assertRaises(ValueError, self.saved['_sources'], '.')

    def test_source_path_escape_refused(self):
        bootstrap.SOURCE_HASHES = (('../outside.bin', '0' * 64),)
        self.assertRaises(ValueError, self.saved['_sources'], self.directory)


if __name__ == '__main__':
    unittest.main()
