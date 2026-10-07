# -*- coding: utf-8 -*-
"""Credential boundary tests; explicitly not native engine compatibility tests."""
import os
import sys
import unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'client_patch'))
import project_auth as auth


class CredentialBoundaryTests(unittest.TestCase):
    def test_exact_unicode_and_edge_spaces_survive_legacy_strip(self):
        original = u'  пароль нового игрока  '
        value = auth.ExactPassword(original)
        self.assertEqual(value.strip(), original.encode('utf8'))
        self.assertIs(value.strip(), value)
        self.assertTrue(auth.valid_password(value.strip()))

    def test_astral_unicode_scalar_count(self):
        self.assertTrue(auth.valid_password(u'\U0001f642' * 128))
        self.assertFalse(auth.valid_password(u'\U0001f642' * 129))
        self.assertEqual(len(auth.password_bytes(u'\U0001f642' * 128)), 512)

    def test_length_and_no_normalization(self):
        self.assertFalse(auth.valid_password('x'*14))
        self.assertTrue(auth.valid_password('x'*15))
        self.assertTrue(auth.valid_password('x'*128))
        self.assertFalse(auth.valid_password('x'*129))
        self.assertNotEqual(auth.password_bytes(u'\u00e9'*15), auth.password_bytes(u'e\u0301'*15))
        self.assertFalse(auth.valid_password(b'\xff'*15))

    def test_project_email_contract(self):
        self.assertTrue(auth.valid_email(' \tPlayer.Tag+Lab@EXAMPLE.COM\r\n'))
        self.assertEqual(auth.canonical_email(' \tPlayer.Tag+Lab@EXAMPLE.COM\r\n'),
                         'player.tag+lab@example.com')
        self.assertTrue(auth.valid_email("!#$%&'*+/=?^_`{|}~-@a.example"))
        self.assertTrue(auth.valid_email('a@a.a1'))
        for value in ('player_012', 'a@localhost', 'a@127.0.0.1', '.a@example.com',
                      'a.@example.com', 'a..b@example.com', 'a@-example.com',
                      'a@example-.com', 'a@exa_mple.com', 'a@b..com',
                      'a@b.com.', 'a\nb@example.com', 'a@b@example.com',
                      u'игрок@example.com', u'a@пример.рф',
                      u'\u00a0a@example.com', u'a@example.com\u2003'):
            self.assertFalse(auth.valid_email(value), repr(value))

    def test_email_exact_length_boundaries(self):
        email254 = 'a'*64 + '@' + 'b'*63 + '.' + 'c'*63 + '.' + 'd'*61
        self.assertEqual(len(email254), 254)
        self.assertTrue(auth.valid_email(email254))
        self.assertFalse(auth.valid_email(email254+'d'))
        self.assertFalse(auth.valid_email('a'*65+'@example.com'))
        self.assertFalse(auth.valid_email('a@'+'b'*64+'.example'))
        self.assertFalse(auth.valid_email(b'\xff@example.com'))

    def test_original_secret_debug_line_is_redacted(self):
        logged = []
        log = auth.credential_safe_logger(lambda *args, **kwargs: logged.append(args))
        log('url: 127.0.0.1:20014; login: USER; pass: SECRET; name: None; token: TOKEN')
        log('ordinary connection event', 1)
        self.assertEqual(logged[0], ('Project login requested; credential fields redacted',))
        self.assertNotIn('SECRET', repr(logged))
        self.assertNotIn('TOKEN', repr(logged))
        self.assertEqual(logged[1], ('ordinary connection event', 1))


if __name__ == '__main__':
    unittest.main()
