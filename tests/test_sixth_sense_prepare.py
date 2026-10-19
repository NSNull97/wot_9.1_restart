"""Prepare seam and original #717 resources for the project Sixth Sense cue.

Reads the original client package as bounded data only; never installs or
touches a client copy. Native audio remains NOT_RUN.
"""
from pathlib import Path
import hashlib
import importlib.util
import os
import subprocess
import sys
from types import SimpleNamespace
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
spec = importlib.util.spec_from_file_location('_sixth_sense_interactive_candidate',
                                            ROOT/'tools/interactive_client.py')
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)
GUI_FEV_SHA256 = '967c482626900e0b432b6671c5e6390d382c6cf69342889fd03e25f31542e66e'
NOTIFICATIONS_SHA256 = 'e57321e6c1fb1421a0bb2543f9f2bb2cad0c07db2c3e25abd4efe5638932f324'


def original_root():
    try:
        from client_audit import config
        _, paths = config()
    except (OSError, KeyError, ValueError):
        return None
    return paths['original_client_root']


class PrepareTests(unittest.TestCase):
    def test_flag_is_listed_with_only_existing_candidates(self):
        env = dict(os.environ, PYTHONPATH=str(ROOT/'tools'))
        result = subprocess.run([sys.executable, '-B', str(ROOT/'tools/interactive_client.py'),
                                 'prepare', '--help'], env=env, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        text = b' '.join(result.stdout.split())
        self.assertIn(b'--sixth-sense-sound {enemy_sighted_for_team,gun_intuition,minimap_attention}', text)
        self.assertIn(b'not original 0.9.1', text)

    def test_module_is_compiled_once(self):
        self.assertEqual(candidate.MODULES.count('project_sixth_sense_sound'), 1)
        self.assertEqual(len(candidate.MODULES), len(set(candidate.MODULES)))

    def test_prepare_uses_the_client_validator(self):
        args = SimpleNamespace()
        self.assertIsNone(candidate.sixth_sense_option(args, True, False))
        args.sixth_sense_sound = None
        self.assertIsNone(candidate.sixth_sense_option(args, False, False))
        args.sixth_sense_sound = 'gun_intuition'
        with self.assertRaises(ValueError):
            candidate.sixth_sense_option(args, False, False)
        option = candidate.sixth_sense_option(args, True, False)
        self.assertEqual(option['event_path'], '/GUI/notifications_FX/gun_intuition')
        self.assertEqual(option['policy'], 'project_override_not_original_091')
        self.assertEqual(candidate.sixth_sense_option(args, False, True)['candidate'], 'gun_intuition')
        args.sixth_sense_sound = 'sixth_sense'
        with self.assertRaises(ValueError):
            candidate.sixth_sense_option(args, True, True)


class OriginalResourceTests(unittest.TestCase):
    """VERIFIED: the candidate event paths already exist in #717 GUI audio data."""

    def setUp(self):
        self.root = original_root()
        if self.root is None:
            self.skipTest('original #717 client not configured (NOT_RUN)')

    def test_candidates_are_paths_in_original_sound_notification_table(self):
        from packed_xml import decode
        from client_probe import to_element
        with zipfile.ZipFile(self.root/'res/packages/gui.pkg') as archive:
            info = archive.getinfo('gui/sound_notifications.xml')
            self.assertLess(info.file_size, 1024*1024)
            raw = archive.read(info)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), NOTIFICATIONS_SHA256)
        table = to_element('root', decode(raw))
        sounds = {}
        for event in table:
            for category in ('fx', 'voice'):
                node = event.find(category + '/sound')
                if node is not None and (node.text or '').strip():
                    sounds.setdefault(node.text.strip(), []).append((event.tag, category))
        policy = candidate.sixth_sense_policy()
        for name, path in policy.CANDIDATES.items():
            self.assertIn(path, sounds, name)
        # No original Sixth Sense / lamp notification exists (P07B boundary).
        self.assertFalse([tag for tag in (e.tag for e in table)
                          if 'sixth' in tag.lower() or 'lamp' in tag.lower()])
        self.assertEqual(sounds['/GUI/notifications_FX/gun_intuition'], [('gun_intuition', 'fx')])
        self.assertEqual(sounds['/GUI/notifications_FX/enemy_sighted_for_team'],
                         [('enemy_sighted_for_team', 'fx')])
        self.assertEqual(sounds['/GUI/notifications_FX/minimap_attention'],
                         [('chat_shortcut_common_fx', 'voice')])

    def test_candidate_events_are_in_the_original_gui_bank(self):
        raw = (self.root/'res/audio/gui.fev').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), GUI_FEV_SHA256)
        for name in candidate.sixth_sense_policy().CANDIDATES:
            self.assertIn(b'\0' + name.encode() + b'\0', raw, name)
        self.assertIn(b'notifications_FX\0', raw)
        for bank in ('gui_notifications_fx_intuition.fsb', 'gui_enemy_sighted_for_team.fsb',
                     'gui_notifications_fx_minimap_attention.fsb'):
            self.assertTrue((self.root/'res/audio'/bank).is_file(), bank)


if __name__ == '__main__':
    unittest.main()
