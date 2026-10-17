"""Source-bound display component tests; no SQL/client/UI/purchase claim."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest
import sys

# Standalone/discover tests must not depend on a previous module's sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import py27_static as static
from p04w_shell_display import SOURCE_ROWS,SOURCE_PATH,SOURCE_SHA256,verified_source_prices,add_shell_display_references
from p09d_ammo_projection import ProjectionSource,encode
from p09e_research_catalog import load_catalog
import p09e_research_projection as actual_projection

ROOT=Path(static.__file__).resolve().parents[1]
ORIGINAL=Path('C:/WoT_0.9.1_RU_0717_original')
STOCK=(2570,2826,3082,14602,14858,15114)
# Captured from genuine pre-change projection e5a4cf8247f8a950ddcf004f951976bb8e6e8e505d7a4a2bb28e428d0c0b55c1; no baseline code copy.
PRE_DISPLAY_SHOP_SHA256='68ae754bf4a61cc457d1568b361aea756a0785b35ad4b0fce3ca0efd68f05f8f'
PRE_DISPLAY_SHOP_BYTES=23096
CATALOG_SHA256='b6baecd204444d1e894253fa6c19c61478993b8ae87c71373633989d3a8ee460'
PINS={
 'client/gui/scaleform/daapi/view/lobby/store/__init__.pyc':'2b7ae6505786cdd420cd0f6875db104099df16b571b0f2245ffbb7e7d8360ba4',
 'client/gui/scaleform/daapi/view/lobby/store/inventory.pyc':'584b67eed9573b3adc4ca9cda80c120974aa9703d66b0d4ed8ea16ba39df3c54',
 'client/gui/scaleform/daapi/view/lobby/store/shop.pyc':'9596ac788041dd26d184ac3be37801eddae6ae9ef811f5c35897cac89063d110',
 'client/gui/shared/utils/requesters/itemsrequester.pyc':'41e5e9bacbb68e89202116bd267c6cd9fceeda4edb0ed605c7b87cc9315c0c44',
 'client/gui/shared/utils/requesters/__init__.pyc':'1e2ab64ad9bc08308fec05f295f4a58a087c8ea970672b9ac6ec2da4b1e055a9',
 'client/account_helpers/shop.pyc':'84aa30eb5b1862ac4fbb08557b67ad36dabc9b90cc1d083a29e0e12040127b6d',
}
def digest(raw):return hashlib.sha256(raw).hexdigest()
def source(path):
    p=ORIGINAL/'res/scripts'/path
    if p.is_symlink()or any(x.is_symlink()for x in p.parents):raise ValueError('ORIGINAL_LINK')
    raw=p.read_bytes()
    if len(raw)>65536 or digest(raw)!=PINS[path]:raise ValueError('ORIGINAL_PIN')
    return raw
def method(module,name,line=None):
    matches=[row for row in module if row['qualified_name']==name and(line is None or row['firstlineno']==line)]
    if len(matches)!=1:raise ValueError('EXACT_SOURCE_METHOD')
    return {row['offset']:row for row in matches[0]['instructions']}
def op(t,offset,name,value=None,arg=None):
    row=t[offset]
    if row['opname']!=name or(value is not None and row.get('value')!=value)or(arg is not None and row.get('arg')!=arg):
        raise AssertionError((offset,row,name,value,arg))

class ShellDisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        opcode=(ROOT/'local/vendor/cpython-2.7.3/opcode.py').read_bytes()
        if len(opcode)!=5474 or digest(opcode)!='acfe212847ecb81ca28bdab976a3caacff3568b45a9e8ca78d6957f9f3ef4884':raise ValueError('OPCODE_PIN')
        table=static.opcode_table(opcode.decode('ascii'))
        cls.modules={name:static.inspect(source(name),table)for name in PINS}
        cls.shell_raw=(ORIGINAL/SOURCE_PATH).read_bytes()
        cls.catalog=load_catalog(ORIGINAL)
        cls.bundle=ROOT/'local/stands/p09e-main-01/source-bundle-05'
        cls.base=ProjectionSource(cls.bundle)
        if cls.base.bundle_sha256!='d99f2ba765e39d096cf2d0858c9864ed897a36eb9c4ea6972a15385e2355b2db':raise ValueError('EXACT_BUNDLE')
        if cls.catalog.sha256!=CATALOG_SHA256:raise ValueError('EXACT_CATALOG')
        # Resolves the actual promoted project module in normal tests; candidate
        # runs select its unchanged frozen production module on sys.path.
        cls.projection=actual_projection

    def test_original_warehouse_uses_shop_enumerator_before_count_filter(self):
        t=method(self.modules['client/gui/scaleform/daapi/view/lobby/store/inventory.pyc'],'<module>.Inventory.requestTableData')
        op(t,160,'LOAD_GLOBAL','g_itemsCache');op(t,166,'LOAD_ATTR','getItems');op(t,178,'CALL_FUNCTION',arg=3)
        t=method(self.modules['client/gui/shared/utils/requesters/itemsrequester.pyc'],'<module>.ItemsRequester.getItems')
        op(t,16,'LOAD_FAST','ShopDataParser');op(t,25,'LOAD_ATTR','getItemsData');op(t,92,'LOAD_ATTR','getItemsIterator')
        t=method(self.modules['client/gui/shared/utils/requesters/__init__.pyc'],'<module>.ShopDataParser.getItemsIterator')
        op(t,79,'LOAD_FAST','intCD');op(t,82,'LOAD_FAST','prices');op(t,85,'COMPARE_OP',arg=6)
        op(t,88,'POP_JUMP_IF_FALSE',arg=73);op(t,122,'YIELD_VALUE')
        t=method(self.modules['client/gui/shared/utils/requesters/__init__.pyc'],'<module>.ShopDataParser.getPrices')
        op(t,9,'LOAD_CONST','itemPrices')

    def test_original_hidden_shop_but_not_inventory_flag(self):
        t=method(self.modules['client/gui/scaleform/daapi/view/lobby/store/__init__.pyc'],'<module>.Store._getRequestParameters')
        op(t,3,'LOAD_ATTR','EMPTY')
        t=method(self.modules['client/gui/scaleform/daapi/view/lobby/store/shop.pyc'],'<module>.Shop._getRequestParameters')
        op(t,79,'LOAD_ATTR','HIDDEN');op(t,82,'UNARY_INVERT');op(t,83,'BINARY_OR')
        t=method(self.modules['client/gui/scaleform/daapi/view/lobby/store/inventory.pyc'],'<module>.Inventory._getRequestParameters')
        self.assertFalse(any(row.get('value')=='HIDDEN'for row in t.values()))
        op(t,1400,'LOAD_ATTR','INVENTORY')
        t=method(self.modules['client/gui/shared/utils/requesters/itemsrequester.pyc'],'<module>.REQ_CRITERIA.<lambda>',116)
        op(t,3,'LOAD_ATTR','inventoryCount');op(t,9,'COMPARE_OP',arg=4)

    def test_original_fresh_account_requests_and_full_stream_replaces_same_revision(self):
        m=self.modules['client/account_helpers/shop.pyc']
        t=method(m,'<module>.Shop.onAccountBecomePlayer');op(t,21,'LOAD_ATTR','synchronize');op(t,24,'CALL_FUNCTION',arg=0)
        t=method(m,'<module>.Shop');op(t,42,'LOAD_CONST');self.assertIsNone(t[42]['value']);op(t,48,'MAKE_FUNCTION',arg=1)
        t=method(m,'<module>.Shop.__sendSyncRequest');op(t,16,'LOAD_ATTR','_Shop__getCacheRevision');op(t,76,'LOAD_ATTR','CMD_SYNC_SHOP')
        t=method(m,'<module>.Shop.__onSyncDataReceived');op(t,14,'LOAD_FAST','data');op(t,20,'STORE_ATTR','_Shop__cache')

    def test_exact_six_historical_xml_prices(self):
        self.assertEqual(verified_source_prices(self.shell_raw),{2570:(0,0),2826:(0,1),3082:(8,0),14602:(1118,0),14858:(0,12),15114:(978,0)})
        self.assertEqual(tuple(row[0]for row in SOURCE_ROWS),STOCK)
        self.assertTrue(all(cd&255==10 for cd in STOCK))

    def test_bad_source_missing_wrong_id_cross_nation_and_byte_tamper_refused(self):
        for wrong in(b'',self.shell_raw[:-1],self.shell_raw+b'\0',bytes([self.shell_raw[0]^1])+self.shell_raw[1:]):
            with self.assertRaises(ValueError):verified_source_prices(wrong)
        # Runtime never takes a caller-supplied ID/nation/price allowlist.
        self.assertNotIn(2570+16,{row[0]for row in SOURCE_ROWS})
        self.assertNotIn(1034,{row[0]for row in SOURCE_ROWS})

    def test_source_bundle_has_no_shell_reference_and_candidate_preserves_other_branches(self):
        self.assertTrue(set(STOCK).isdisjoint(self.base.trees['shop.bin']['items']['itemPrices']))
        original=deepcopy(self.base.trees['shop.bin'])
        changed=add_shell_display_references(original)
        self.assertEqual(original,self.base.trees['shop.bin'])
        self.assertEqual(set(changed['items']['itemPrices'])-set(original['items']['itemPrices']),set(STOCK))
        self.assertTrue(set(STOCK)<=set(changed['items']['notInShopItems']))
        for cd in STOCK:del changed['items']['itemPrices'][cd]
        changed['items']['notInShopItems']=[cd for cd in changed['items']['notInShopItems']if cd not in STOCK]
        self.assertEqual(changed,original)

    def test_projection_actual_shop_tree_retains_revision_and_vehicle_module_policy(self):
        new=self.projection.shop_tree(self.catalog,self.base.trees['shop.bin'])
        self.assertEqual(new['rev'],5)
        expected={row['native_compact_id']:
            (0,row['historical_price']['amount']if row['historical_price']['currency']=='gold'else 0)
            for row in(*self.catalog.vehicles.values(),*self.catalog.modules.values())}
        self.assertTrue(set(STOCK).isdisjoint(expected))
        self.assertEqual(set(new['items']['itemPrices']),set(expected)|set(STOCK))
        for cd,price in expected.items():self.assertEqual(new['items']['itemPrices'][cd],price)
        shell_prices={row[0]:row[3]for row in SOURCE_ROWS}
        self.assertEqual({cd:new['items']['itemPrices'][cd]for cd in STOCK},shell_prices)
        old_hidden=sorted(v['native_compact_id']for v in self.catalog.vehicles.values()
            if v['not_in_shop']or set(v['tags'])&{'secret','observer','event_battles','special'})
        self.assertTrue(set(STOCK).isdisjoint(old_hidden))
        self.assertEqual(new['items']['notInShopItems'],old_hidden+list(STOCK))
        stripped=deepcopy(new)
        for cd in STOCK:del stripped['items']['itemPrices'][cd]
        stripped['items']['notInShopItems']=stripped['items']['notInShopItems'][:-len(STOCK)]
        restored=encode(stripped,32768,max_nodes=32768)
        self.assertEqual(len(restored),PRE_DISPLAY_SHOP_BYTES)
        self.assertEqual(digest(restored),PRE_DISPLAY_SHOP_SHA256)
        self.assertLessEqual(len(encode(new,32768,max_nodes=32768)),32768)
        # A changed pre-existing branch must break the independent byte pin;
        # this does not compare two imports of the promoted implementation.
        stripped['rev']=6
        self.assertNotEqual(digest(encode(stripped,32768,max_nodes=32768)),PRE_DISPLAY_SHOP_SHA256)

    def test_authored_depot_ap_heat_he_counts_unchanged_by_display_and_unowned_absent(self):
        # AUTHORED counts test only the real projection and source-derived
        # enumeration rule; it is not SQL/native ownership acceptance.
        depot={'shell:ms1-stock-ap':7,'shell:ms1-stock-heat':4,'shell:ms1-stock-he':10}
        aggregate={'depot':depot};before=deepcopy(aggregate)
        state=self.base.state(aggregate,{})
        counts=state['inventory'][10]
        self.assertEqual(counts,{2570:7,2826:4,3082:10})
        shop=add_shell_display_references(self.base.trees['shop.bin'])
        warehouse={cd:counts[cd]for cd in STOCK if cd in shop['items']['itemPrices']and counts.get(cd,0)>0}
        self.assertEqual(warehouse,counts);self.assertEqual(aggregate,before)
        self.assertEqual({cd:n for cd,n in warehouse.items()if cd not in shop['items']['notInShopItems']},{})
        self.assertEqual([cd for cd in STOCK if {}.get(cd,0)>0],[])
        self.assertFalse(any(cd in warehouse for cd in(1034,2570+16,14602,14858,15114)))

    def test_conflicting_prices_and_malformed_hidden_rows_refuse_without_mutation(self):
        for wrong in((1,0),(False,0),(0,),None,'0'):
            shop=deepcopy(self.base.trees['shop.bin']);shop['items']['itemPrices'][2570]=wrong;before=deepcopy(shop)
            with self.assertRaises(ValueError):add_shell_display_references(shop)
            self.assertEqual(shop,before)
        for wrong in([True],[2570,2570],None):
            shop=deepcopy(self.base.trees['shop.bin']);shop['items']['notInShopItems']=wrong
            with self.assertRaises(ValueError):add_shell_display_references(shop)

if __name__=='__main__':unittest.main()
