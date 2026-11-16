import copy
from pathlib import Path
import unittest
from tempfile import TemporaryDirectory
from tools.content0_s5a_configure import config_rows, rewrite, restrict_directory, create_secret

class ConfigurationTests(unittest.TestCase):
    def test_isolates_ports_secrets_and_account(self):
        source=Path('C:/synthetic/source/local/stands/original');stand=Path('C:/synthetic/new/local/stands/isolated')
        rows={'source':str(source), 'domain':{'accounts':[]},
              'bridge':{'ammunition_service':{'account_id':'old'},'battle_service':{},'pool_service':{},'mixed_service':{},'ammo_loss_service':{},'late_result_service':{}},
              'gateway':{'bots':{'policy':'project.bot01.route-hold-visible-aim.v1','human_places':1,'seed':1},'matchmaker':{},'late_bots':{}}}
        before=copy.deepcopy(rows);operator='b9155283-ebb0-4fdd-85b4-f5a8d00cdcd1';ports={'domain':20001,'bridge':20002,'guard':20003,'login':20004,'base':20005}
        domain,bridge,gateway=config_rows(rows,stand,operator,ports)
        self.assertEqual(rows,before);self.assertEqual(domain['accounts'][0]['account_id'],operator);self.assertEqual(Path(domain['database']),stand/'operator-clean-01/game.sqlite')
        self.assertEqual(bridge['battle_service']['accounts'],[operator]);self.assertTrue(bridge['domain_service']['camouflage_v1'])
        self.assertEqual(gateway['visibility_debug_operator'],operator);self.assertEqual(len(gateway['fixed_scout_v1']['seats']),4)
        self.assertEqual(gateway['fixed_scout_v1']['events'],[]);self.assertNotIn('matchmaker',gateway);self.assertNotIn('late_bots',gateway)
        self.assertEqual(len({domain['secret_file'],domain['camouflage_guard']['secret_file'],bridge['token_file'],gateway['visibility_debug_grant_file']}),4)
    def test_private_directory_and_unique_secrets(self):
        with TemporaryDirectory() as name:
            directory=Path(name)/'private';directory.mkdir();restrict_directory(directory)
            one=create_secret(directory/'one');two=create_secret(directory/'two')
            self.assertEqual(len(one.read_bytes()),43);self.assertNotEqual(one.read_bytes(),two.read_bytes())
            with self.assertRaises(FileExistsError):create_secret(one)
    def test_maps_source_local_and_code_paths_to_checkout(self):
        source=Path('C:/synthetic/source/local/stands/original');local=source.parent.parent;stand=Path('C:/synthetic/new/local/stands/isolated')
        self.assertEqual(Path(rewrite(str(source/'game.sqlite'),source,stand,local)),stand/'game.sqlite')
        self.assertEqual(Path(rewrite(str(local/'stands/p09e-main-01/source-bundle-05'),source,stand,local)),stand/'support/bundle')
        self.assertEqual(Path(rewrite(str(local/'evidence/data.bin'),source,stand,local)),stand/'resources/evidence/data.bin')
