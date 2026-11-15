"""Operator build selection is explicit and never enables remote diagnostics."""
from types import SimpleNamespace
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'tools'))
from interactive_client import visibility_debug_options


class VisibilityDebugInstallTests(unittest.TestCase):
    def test_only_explicit_loopback_copy_and_distinct_slots_enable_it(self):
        local={'endpoint':'127.0.0.1:20370'}
        self.assertIsNone(visibility_debug_options(SimpleNamespace(),False,local,None))
        run='788fa1bf-8a21-4bdb-84de-a63310e390a3';account='6dfe50ca-84c6-4ad4-9ffa-19f22f92a563'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();grant=root/'grant';grant.write_bytes(b'x'*43);paths={'local_artifacts_root':root}
            args=SimpleNamespace(visibility_debug=[2,3],visibility_debug_run=run,visibility_debug_account=account,visibility_debug_grant_file=str(grant))
            self.assertEqual(visibility_debug_options(args,True,local,{'slot':'a'},paths),
                             {'observer':2,'target':3,'run':run,'account':account,'grant_file':str(grant)})
            args.visibility_debug_pair_keys=True
            self.assertTrue(visibility_debug_options(args,True,local,{'slot':'a'},paths)['pair_hotkeys'])
            with self.assertRaises(ValueError):visibility_debug_options(SimpleNamespace(visibility_debug_pair_keys=True),False,local,None)
            args.visibility_debug_pair_keys=False
            for profile,network,copy in ((False,local,{'slot':'a'}),(True,local,None),
                                         (True,{'endpoint':'10.0.0.1:20370','network_policy':'lan-test-v1'},{'slot':'a'})):
                with self.assertRaises(ValueError):visibility_debug_options(args,profile,network,copy,paths)
            for pair in ([0,0],[0,6],[-1,0],[True,1],[0]):
                args.visibility_debug=pair
                with self.assertRaises(ValueError):visibility_debug_options(args,True,local,{'slot':'a'},paths)
            args.visibility_debug=[0,1]
            for value in (None,'bad','788FA1BF-8A21-4BDB-84DE-A63310E390A3'):
                args.visibility_debug_run=value
                with self.assertRaises(ValueError):visibility_debug_options(args,True,local,{'slot':'a'},paths)
            args.visibility_debug_run=run;grant.write_bytes(b'bad')
            with self.assertRaises(ValueError):visibility_debug_options(args,True,local,{'slot':'a'},paths)
            with self.assertRaises(ValueError):visibility_debug_options(SimpleNamespace(visibility_debug_run=run),True,local,{'slot':'a'},paths)


if __name__ == '__main__': unittest.main()
