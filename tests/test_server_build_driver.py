"""Acceptance accounting only; these checks do not launch Cargo or a worker."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('server_build_driver', ROOT/'server/build.py')
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)


class BuildTestAccounting(unittest.TestCase):
    def test_empty_filter_and_ignored_only_run_cannot_pass(self):
        for output in ('', 'running 0 tests\ntest result: ok. 0 passed; 0 failed; 0 ignored; 755 filtered out;',
                       'test result: ok. 0 passed; 0 failed; 1 ignored; 755 filtered out;'):
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, 'Nonempty'):
                build.test_counts(output)

    def test_nonempty_gate_can_have_empty_doc_test_target(self):
        self.assertEqual(build.test_counts('test result: ok. 25 passed; 0 failed; 1 ignored; 730 filtered out;\n'
                                          'test result: ok. 0 passed; 0 failed; 0 ignored; 0 filtered out;'), (25, 1))

    def test_failed_target_is_not_hidden_by_a_successful_target(self):
        for output in ('test result: FAILED. 1 passed; 1 failed; 0 ignored; 0 filtered out;',
                       'test result: ok. 1 passed; 0 failed; 0 ignored; 0 filtered out;\n'
                       'test result: FAILED. 0 passed; 1 failed; 0 ignored; 0 filtered out;'):
            with self.subTest(output=output), self.assertRaises(ValueError):
                build.test_counts(output)

    def test_retained_actual_full_gateway_log_preserves_its_count(self):
        output = (ROOT/'local/build/server/gateway-p05b-night-final14/test.stdout.log').read_text(encoding='utf-8')
        self.assertEqual(build.test_counts(output), (755, 0))

    def test_retained_actual_isolated_gate_preserves_its_count(self):
        output = (ROOT/'local/build/server/gateway-p05b-cadence-real04/test.stdout.log').read_text(encoding='utf-8')
        self.assertEqual(build.test_counts(output), (1, 0))


if __name__ == '__main__':
    unittest.main()
