"""Thin overlays use their own marker, pinned into the ordinary installer plan."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import interactive_client as installer
import content0_s5a_overlay as overlay


class OverlayInstallerTests(unittest.TestCase):
    def test_checked_overlay_manifest_is_bound_to_install_plan(self):
        with tempfile.TemporaryDirectory() as temp:
            local=Path(temp).resolve();root=local/'clients'/'overlay';root.mkdir(parents=True)
            out=local/'evidence'/'install';out.mkdir(parents=True);original=local/'original';original.mkdir()
            marker=root/overlay.MARKER;marker.write_text('initial manifest')
            paths={'local_artifacts_root':local,'research_client_root':local/'old-client','original_client_root':original}
            plan={'schema_version':1,'mode':'interactive','research_root':str(root),'original_root':str(original),
                  'thin_overlay':True,'instance_mutex':'sr_test_a_mutex_',
                  'overlay_manifest_sha256':installer.sha256(marker)}
            (out/'install-plan.json').write_text(json.dumps(plan))
            with patch.object(installer,'config',return_value=({},paths)), \
                 patch.object(overlay,'checked_overlay',return_value=(root,{'instance_mutex':plan['instance_mutex']})):
                self.assertEqual(installer.load_plan(SimpleNamespace(out=str(out)))[1],root)
                marker.write_text('changed manifest')
                with self.assertRaisesRegex(ValueError,'manifest changed'):
                    installer.load_plan(SimpleNamespace(out=str(out)))
                plan['additional_research_copy']=True
                (out/'install-plan.json').write_text(json.dumps(plan))
                with self.assertRaisesRegex(ValueError,'ambiguous'):
                    installer.load_plan(SimpleNamespace(out=str(out)))


if __name__=='__main__':unittest.main()
