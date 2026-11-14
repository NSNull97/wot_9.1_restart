"""Thin overlay pure path and source-inventory checks; no client is launched."""
import sys
import hashlib
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import content0_s5a_overlay as overlay


def paths(package_count=62):
    values=['./res_mods/0.9.1']+['./res/packages/pkg_%02d.pkg'%i for i in range(package_count)]+['./res','./res_bw']
    tree=ET.Element('root');container=ET.SubElement(tree,'Paths')
    for value in values:ET.SubElement(container,'Path').text=value
    return ET.tostring(tree)


class ThinOverlayTests(unittest.TestCase):
    def test_standalone_cli_can_import_its_tools_package(self):
        for name in ('content0_s5a_overlay.py','content0_s5a_overlay_launch.py'):
            result=subprocess.run([sys.executable,str(ROOT/'tools'/name),'--help'],cwd=ROOT,
                                  capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_original_locale_directory_case_matches_installer_targets(self):
        root=Path('X:/fixture')
        self.assertEqual(overlay.canonical_original_relative(root/'res/text/lc_messages/menu.mo',root),
                         'res/text/LC_MESSAGES/menu.mo')

    def test_scripts_are_copied_only_if_original_and_verified_source_match(self):
        with tempfile.TemporaryDirectory() as temp:
            original=Path(temp);folder=original/'res/scripts/client';folder.mkdir(parents=True)
            source=folder/'native.pyc';source.write_bytes(b'verified')
            digest=hashlib.sha256(b'verified').hexdigest()
            pins={'res/scripts/client/native.pyc':digest}
            files,evidence=overlay.script_payloads(original,pins,audit_pins={})
            self.assertEqual(files,{'res/scripts/client/native.pyc':b'verified'})
            self.assertEqual(evidence['files'],1)
            source.write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError,'differs'):
                overlay.script_payloads(original,pins,audit_pins={})
            source.write_bytes(b'verified');pins['res/scripts/client/missing.pyc']=digest
            with self.assertRaisesRegex(ValueError,'inventory differ'):
                overlay.script_payloads(original,pins,audit_pins={})

    def test_search_paths_never_include_old_source_profile_or_mods(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);root=base/'new-overlay';source=base/'old-client'
            result=ET.fromstring(overlay.build_paths(paths(),root,source))
            rows=[node.text for node in result.find('Paths')]
            self.assertEqual(rows[:2],[(root/'profile').as_posix(),(root/'res_mods/0.9.1').as_posix()])
            self.assertEqual(rows[-3:],[(root/'res').as_posix(),(source/'res').as_posix(),(source/'res_bw').as_posix()])
            self.assertEqual(rows[2],(source/'res/packages/pkg_00.pkg').as_posix())
            self.assertNotIn((source/'res_mods/0.9.1').as_posix(),rows)
            self.assertNotIn((source/'profile').as_posix(),rows)
            self.assertEqual(len(rows),67)

    def test_refuses_extra_missing_duplicate_or_escaping_package(self):
        for raw in (paths(61),paths(63),paths().replace(b'pkg_01.pkg',b'pkg_00.pkg'),
                    paths().replace(b'./res/packages/pkg_01.pkg',b'../../other.pkg'),
                    paths().replace(b'./res_mods/0.9.1',b'E:/foreign/profile')):
            with self.subTest(raw=raw[:100]):
                with self.assertRaises(ValueError):overlay.parse_paths(raw)

    def test_loose_source_inventory_detects_edits_and_reparse_points(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d);(source/'res/packages').mkdir(parents=True);(source/'res_bw').mkdir()
            file=source/'res/a.txt';file.write_bytes(b'first')
            (source/'res/packages/a.pkg').write_bytes(b'package')
            (source/'res/packages/shared_content.prefetch').write_bytes(b'prefetch')
            before=overlay.loose_files(source)
            self.assertEqual(set(before),{'res/a.txt','res/packages/shared_content.prefetch'})
            file.write_bytes(b'second');self.assertNotEqual(before,overlay.loose_files(source))
            link=source/'res/alias'
            try:link.symlink_to(file)
            except OSError:self.skipTest('symlink creation unavailable')
            with self.assertRaises(Exception):overlay.loose_files(source)

    def test_rollback_preflight_preserves_unknown_or_edited_files(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for folder in ('profile','runtime','res_mods/0.9.1'):(root/folder).mkdir(parents=True,exist_ok=True)
            (root/overlay.MARKER).write_bytes(b'marker')
            (root/'paths.xml').write_bytes(b'original')
            data={'immutable':{},'baseline':{'paths.xml':hashlib.sha256(b'original').hexdigest()}}
            allowed,_=overlay.rollback_inventory(root,data)
            self.assertEqual(allowed,{overlay.MARKER,'paths.xml'})
            (root/'profile/own-data').write_bytes(b'keep')
            with self.assertRaisesRegex(ValueError,'unrecognized'):
                overlay.rollback_inventory(root,data)
            self.assertEqual((root/'profile/own-data').read_bytes(),b'keep')
            (root/'profile/own-data').unlink();(root/'paths.xml').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'rollback required'):
                overlay.rollback_inventory(root,data)
            self.assertEqual((root/'paths.xml').read_bytes(),b'changed')


if __name__=='__main__':unittest.main()
