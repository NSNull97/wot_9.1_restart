"""client_patch/native_contract.py: the one check of the exact #717 method a module wraps."""
import hashlib
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'client_patch'))

import native_contract


def sample(self, value):
    return value + 1


def spread(self, *values):
    return values


def facts(function):
    code = getattr(function, 'func_code', getattr(function, '__code__', None))
    return (code.co_filename.replace('\\', '/'), code.co_name, code.co_firstlineno,
            tuple(code.co_varnames[:code.co_argcount]), hashlib.sha256(code.co_code).hexdigest())


class NativeContract(unittest.TestCase):
    def test_the_exact_method_passes(self):
        native_contract.check(sample, *(facts(sample) + ('sample host',)))

    def test_any_difference_refuses_with_the_module_wording(self):
        filename, name, line, args, digest = facts(sample)
        for changed in ((filename + 'x', name, line, args, digest), (filename, 'other', line, args, digest),
                        (filename, name, line + 1, args, digest), (filename, name, line, ('self',), digest),
                        (filename, name, line, ('self', 'other'), digest), (filename, name, line, args, '0' * 64)):
            with self.assertRaises(RuntimeError) as caught:
                native_contract.check(sample, *(changed + ('sample host',)))
            self.assertEqual('original #717 sample host differs: ' + changed[1], str(caught.exception))
        with self.assertRaises(RuntimeError):
            native_contract.check(None, filename, name, line, args, digest, 'sample host')

    def test_star_arguments_refuse_unless_flags_are_off(self):
        contract = facts(spread) + ('spread host',)
        with self.assertRaises(RuntimeError):
            native_contract.check(spread, *contract)
        native_contract.check(spread, *contract, **{'flags': False})


if __name__ == '__main__':
    unittest.main()
