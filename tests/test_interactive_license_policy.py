"""Read-only resource generation checks; no install, launch, or consent simulation."""
import hashlib
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from client_audit import config
from interactive_client import interactive_resource_overrides


class LegacyDialogPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, paths = config()
        cls.original = paths['original_client_root']
        cls.version_before = (cls.original / 'version.xml').read_bytes()
        cls.version_hash = hashlib.sha256(cls.version_before).hexdigest()

    def tearDown(self):
        self.assertEqual((self.original / 'version.xml').read_bytes(), self.version_before)

    def test_default_preserves_original_dialog(self):
        payloads, evidence = interactive_resource_overrides(self.original)
        self.assertNotIn('version.xml', payloads)
        self.assertFalse(evidence['legacy_service_dialog']['disabled'])
        self.assertFalse(evidence['legacy_service_dialog']['owner_requested'])
        self.assertNotIn('diagnostic_license_dialog', evidence)

    def test_owner_request_works_without_control_and_only_changes_flag(self):
        payloads, evidence = interactive_resource_overrides(
            self.original, disable_legacy_license_dialog=True)
        self.assertEqual(set(payloads), {'version.xml', 'res_mods/0.9.1/scripts_config.xml',
                                        'res_mods/0.9.1/gui/gui_settings.xml'})
        expected = ET.fromstring(self.version_before)
        expected.find('showLicense').text = '0'
        actual = ET.fromstring(payloads['version.xml'])
        self.assertEqual(ET.tostring(actual), ET.tostring(expected))
        metadata = evidence['legacy_service_dialog']
        self.assertEqual(metadata['before_sha256'], self.version_hash)
        self.assertEqual(metadata['showLicense_before'], 3)
        self.assertEqual(metadata['showLicense_after'], 0)
        self.assertTrue(metadata['owner_requested'])
        self.assertTrue(metadata['disabled'])
        self.assertFalse(metadata['user_agreement_recorded'])
        self.assertFalse(metadata['license_files_modified'])
        self.assertFalse(metadata['account_int_settings_modified'])
        self.assertNotIn('diagnostic_license_dialog', evidence)

    def test_old_diagnostic_flag_still_requires_control_even_with_owner_flag(self):
        for owner_flag in (False, True):
            with self.assertRaises(ValueError):
                interactive_resource_overrides(self.original,
                    disable_legacy_license_dialog=owner_flag,
                    diagnostic_no_license_dialog=True, has_control=False)

    def test_old_diagnostic_with_control_retains_its_metadata(self):
        payloads, evidence = interactive_resource_overrides(
            self.original, diagnostic_no_license_dialog=True, has_control=True)
        self.assertEqual(ET.fromstring(payloads['version.xml']).findtext('showLicense'), '0')
        self.assertIn('diagnostic_license_dialog', evidence)
        self.assertFalse(evidence['legacy_service_dialog']['owner_requested'])
        self.assertFalse(evidence['diagnostic_license_dialog']['user_agreement_recorded'])

    def test_both_flags_with_control_use_explicit_owner_metadata(self):
        payloads, evidence = interactive_resource_overrides(self.original,
            disable_legacy_license_dialog=True, diagnostic_no_license_dialog=True, has_control=True)
        self.assertIn('version.xml', payloads)
        self.assertTrue(evidence['legacy_service_dialog']['owner_requested'])
        self.assertTrue(evidence['legacy_service_dialog']['disabled'])
        self.assertNotIn('diagnostic_license_dialog', evidence)


if __name__ == '__main__':
    unittest.main()
