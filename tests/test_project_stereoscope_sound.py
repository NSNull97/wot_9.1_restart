import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'client_patch'))
from project_stereoscope_sound import CLIP_SECONDS, Cue, EVENT_PATH, validate_settings


class Sound(object):
    def __init__(self):
        self.stops = 0

    def stop(self):
        self.stops += 1


class StereoscopeSoundTests(unittest.TestCase):
    def setUp(self):
        self.sounds = []
        self.now = 0.0

        def play(event):
            self.assertEqual(event, EVENT_PATH)
            sound = Sound()
            self.sounds.append(sound)
            return sound

        self.cue = Cue(play, lambda sound, end: sound.stop(), lambda: self.now)

    def test_first_false_is_silent_and_each_activation_plays_once(self):
        self.assertEqual(self.cue.update(12, False, False), 'unchanged')
        self.assertEqual(self.cue.update(12, True, False), 'played')
        self.assertEqual(self.cue.update(12, True, False), 'unchanged')
        self.assertEqual(self.cue.update(12, False, False), 'deactivated')
        self.assertEqual(self.sounds[0].stops, 1)
        self.assertEqual(self.cue.update(12, False, False), 'unchanged')
        self.assertEqual(self.cue.update(12, True, False), 'played')
        self.assertEqual(len(self.sounds), 2)

    def test_hidden_activation_does_not_play_late_and_new_arena_is_independent(self):
        self.assertEqual(self.cue.update(12, True, True), 'muted')
        self.assertEqual(self.cue.update(12, True, False), 'unchanged')
        self.assertEqual(self.sounds, [])
        self.assertEqual(self.cue.update(13, True, False), 'played')
        self.assertEqual(self.cue.update(14, True, False), 'played')
        self.assertEqual(self.sounds[0].stops, 1)

    def test_setting_requires_explicit_battle_mode(self):
        self.assertFalse(validate_settings({}))
        with self.assertRaises(ValueError):
            validate_settings({'stereoscope_sound': True})
        self.assertTrue(validate_settings({'stereoscope_sound': True, 'enable_p06t_mixed_ammo': True}))

    def test_an_expired_cue_is_left_alone_on_deactivation_and_cleanup(self):
        self.cue.update(12, True, False)
        self.now = CLIP_SECONDS
        self.assertEqual(self.cue.update(12, False, False), 'deactivated')
        self.assertEqual(self.sounds[0].stops, 0)
        self.cue.update(12, True, False)
        self.now += 1.0
        self.cue.stop()
        self.assertEqual(self.sounds[1].stops, 0)
