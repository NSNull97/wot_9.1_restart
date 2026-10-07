"""Parser controls only; synthetic inputs never prove native IS-7 compatibility."""
import pathlib
import struct
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'tools'))
from verify_unified_entry import client_requests, dossier_cache_policy


def packet(version=0, changed=0, third=0, request=223, command=600):
    return b'\x8e\x14\0' + struct.pack('<hhqii', request, command, version, changed, third)


class DossierCursorTests(unittest.TestCase):
    context = {'version': 1, 'last_change_time': 1791125440, 'vehicle_type_compact_descr': 7169}

    def test_legacy_default_remains_zero_only(self):
        self.assertEqual(client_requests(packet())[0]['revision'], 0)
        self.assertEqual(client_requests(packet(), None)[0]['command'], 600)
        with self.assertRaises(ValueError):
            client_requests(packet(1, self.context['last_change_time']))

    def test_exact_granted_and_empty_cache_are_the_only_accepted_cursors(self):
        for version, time in [(0, 0), (1, self.context['last_change_time'])]:
            row, = client_requests(packet(version, time), self.context)
            self.assertEqual((row['kind'], row['command'], row['revision'], row['last_change_time']),
                             ('sync', 600, version, time))

    def test_wrong_future_stale_version_time_and_reserved_are_rejected(self):
        time = self.context['last_change_time']
        for version, changed, third in [(0, time, 0), (1, 0, 0), (2, time, 0), (-1, time, 0),
                                         (1, time - 1, 0), (1, time + 1, 0), (1, -1, 0),
                                         (1, time, 1), (1, time, -1), (2 ** 63 - 1, time, 0)]:
            with self.subTest(cursor=(version, changed, third)), self.assertRaises(ValueError):
                client_requests(packet(version, changed, third), self.context)

    def test_context_never_extends_other_methods(self):
        for command in [100, 300, 301, 505, 601]:
            with self.subTest(command=command), self.assertRaises(ValueError):
                client_requests(packet(1, self.context['last_change_time'], command=command), self.context)

    def test_context_rejects_bool_extra_missing_or_foreign_vehicle(self):
        for value in [{}, [], {'version': True, 'last_change_time': 1, 'vehicle_type_compact_descr': 7169},
                      dict(self.context, version=0), dict(self.context, last_change_time=0),
                      dict(self.context, last_change_time=2147483648),
                      dict(self.context, vehicle_type_compact_descr=2), dict(self.context, extra=0)]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                dossier_cache_policy(value)

    def test_truncation_length_request_id_and_count_bounds_remain(self):
        good = packet(1, self.context['last_change_time'])
        for n in range(1, len(good)):
            with self.subTest(length=n), self.assertRaises(ValueError):
                client_requests(good[:n], self.context)
        for bad in [b'\x8e\x15\0' + good[3:], packet(1, self.context['last_change_time'], request=0),
                    packet(1, self.context['last_change_time'], request=-1), good * 17, b'x' * 513]:
            with self.assertRaises(ValueError):
                client_requests(bad, self.context)


if __name__ == '__main__':
    unittest.main()
