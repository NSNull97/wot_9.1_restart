"""P09E client audits accept the actual #717 objects under CPython 2.7.3.

The Python 3 unit tests only see synthetic classes, so an expectation mismatch
(an empty list instead of the empty tuple constant) stopped the first real
client launch. This loads the original code object without executing it.
"""
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from client_audit import config

PROBE = r'''
import marshal, sys, types
sys.path.insert(0, sys.argv[2])
import p09e_research_policy as policy
stream = open(sys.argv[1], 'rb'); stream.read(8); module = marshal.load(stream)
vehicle = [c for c in module.co_consts if isinstance(c, types.CodeType) and c.co_name == 'VehicleType'][0]
code = [c for c in vehicle.co_consts if isinstance(c, types.CodeType)
        and c.co_name == '__convertAndValidateUnlocksDescrs'][0]
cls = type('VehicleType', (object,), {policy.METHOD: types.FunctionType(code, {})})
policy._audit_class(cls)
changed = types.CodeType(code.co_argcount, code.co_nlocals, code.co_stacksize, code.co_flags, code.co_code,
    code.co_consts[:-1] + ([],), code.co_names, code.co_varnames, code.co_filename, code.co_name,
    code.co_firstlineno, code.co_lnotab)
try:
    policy._audit_class(type('VehicleType', (object,), {policy.METHOD: types.FunctionType(changed, {})}))
except ValueError:
    print('AUDIT_PASS_AND_MUTATION_REJECTED')
'''


MODULE_PROBE = r'''
import marshal, sys, types
def load(path):
    stream = open(path, 'rb'); stream.read(8); return marshal.load(stream)
root = sys.argv[1]
adisp = types.ModuleType('adisp')
exec(load(root + '/res/scripts/common/adisp.pyc'), adisp.__dict__)
sys.modules['adisp'] = adisp
sys.path.insert(0, sys.argv[2])
import hangar_capabilities as policy
panel = load(root + '/res/scripts/client/gui/Scaleform/daapi/view/lobby/hangar/AmmunitionPanel.pyc')
body = [c for c in panel.co_consts if isinstance(c, types.CodeType) and c.co_name == 'AmmunitionPanel'][0]
method = [c for c in body.co_consts if isinstance(c, types.CodeType) and c.co_name == 'setVehicleModule'][0]
policy._audit_module_class(type('AmmunitionPanel', (object,), {'setVehicleModule': adisp.process(types.FunctionType(method, {}))}))
other = adisp.process(types.FunctionType(method, {}), lambda *args: None)
try:
    policy._audit_module_class(type('AmmunitionPanel', (object,), {'setVehicleModule': other}))
except RuntimeError:
    print('MODULE_AUDIT_PASS_AND_FOREIGN_CALLBACK_REJECTED')
'''


class NativeConverterAuditTests(unittest.TestCase):
    def test_actual_original_converter_passes_and_mutated_constant_fails(self):
        python = ROOT / 'local/toolchains/cpython-2.7.3-x86/python.exe'
        if not python.is_file():
            self.skipTest('NOT_RUN: pinned CPython 2.7.3 toolchain absent')
        _, paths = config()
        pyc = paths['original_client_root'] / 'res/scripts/common/items/vehicles.pyc'
        result = subprocess.run([str(python), '-E', '-s', '-B', '-c', PROBE, str(pyc), str(ROOT / 'client_patch')],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertEqual(result.stdout.strip(), 'AUDIT_PASS_AND_MUTATION_REJECTED')

    def test_actual_adisp_module_wrapper_passes_and_foreign_step_callback_fails(self):
        python = ROOT / 'local/toolchains/cpython-2.7.3-x86/python.exe'
        if not python.is_file():
            self.skipTest('NOT_RUN: pinned CPython 2.7.3 toolchain absent')
        _, paths = config()
        # Executes only the original pure-Python adisp module (functools); no engine code.
        result = subprocess.run([str(python), '-E', '-s', '-B', '-c', MODULE_PROBE, str(paths['original_client_root']),
                                 str(ROOT / 'client_patch')], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertEqual(result.stdout.strip(), 'MODULE_AUDIT_PASS_AND_FOREIGN_CALLBACK_REJECTED')


if __name__ == '__main__':
    unittest.main()
