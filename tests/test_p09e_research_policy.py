"""Reversible cost-policy controls, not original native UI acceptance."""
import types
import unittest

from client_patch import p09e_research_policy as p
from tools import p09e_native_research_audit as audit


class ResearchCostPolicyTests(unittest.TestCase):
    def fixture(self, cached=True):
        class Vehicle:
            def convert(self, source):
                return source
        setattr(Vehicle,p.METHOD,Vehicle.__dict__['convert'])
        item=Vehicle(); item.id=(0,13); item.unlocksDescrs=[(10,6658),(20,6148,5891,6658)]
        cache=types.SimpleNamespace()
        setattr(cache,p.CACHE_FIELD,{item.id:item} if cached else {})
        events=[]
        guard=p._ResearchCostGuard(Vehicle,cache,lambda event,**kw:events.append((event,kw)),Vehicle.__dict__[p.METHOD])
        return Vehicle,item,guard,events

    def test_historical_row_tails_and_exact_objects_restore(self):
        cls,item,guard,events=self.fixture(); original=item.unlocksDescrs
        guard.install()
        self.assertEqual(item.unlocksDescrs,[(0,6658),(0,6148,5891,6658)])
        self.assertEqual(original,[(10,6658),(20,6148,5891,6658)])
        fresh=cls(); fresh.id=(0,14); source=[(500,5892,6658)]
        fresh.unlocksDescrs=getattr(fresh,p.METHOD)(source)
        self.assertEqual(fresh.unlocksDescrs,[(0,5892,6658)])
        guard.restore()
        self.assertIs(item.unlocksDescrs,original); self.assertIs(fresh.unlocksDescrs,source)
        self.assertIs(cls.__dict__[p.METHOD],guard.original)
        self.assertEqual([row[1]['phase'] for row in events],['install','restore'])

    def test_early_cache_absent_and_future_construction(self):
        cls,item,guard,_=self.fixture(False); guard.cache=None; guard.install()
        source=[(100,6148,5891)]; item.unlocksDescrs=getattr(item,p.METHOD)(source)
        self.assertEqual(item.unlocksDescrs,[(0,6148,5891)])
        guard.restore(); self.assertIs(item.unlocksDescrs,source)

    def test_third_party_binding_and_descriptor_mutation_block_rollback(self):
        cls,item,guard,_=self.fixture(); guard.install()
        replacement=lambda *args: []
        setattr(cls,p.METHOD,replacement)
        with self.assertRaisesRegex(RuntimeError,'binding changed'): guard.restore()
        setattr(cls,p.METHOD,guard.replacement)
        item.unlocksDescrs.append((0,1234))
        with self.assertRaisesRegex(RuntimeError,'descriptor changed'): guard.restore()
        self.assertIs(cls.__dict__[p.METHOD],guard.replacement)

    def test_entire_cache_validation_precedes_any_mutation(self):
        cls,item,guard,_=self.fixture(); original=item.unlocksDescrs
        invalid=cls(); invalid.id=(0,14); invalid.unlocksDescrs=[('not XP',1234)]
        getattr(guard.cache,p.CACHE_FIELD)[invalid.id]=invalid
        with self.assertRaises(ValueError): guard.install()
        self.assertIs(item.unlocksDescrs,original); self.assertIs(cls.__dict__[p.METHOD],guard.original)

    def test_loaded_or_unknown_tree_refused(self):
        name='gui.Scaleform.daapi.view.lobby.techtree.techtree_dp'
        for value in [None,True,1,'False']:
            provider=types.SimpleNamespace(_TechTreeDataProvider__loaded=value)
            with self.assertRaises(ValueError): p._require_unloaded_tree({name:types.SimpleNamespace(g_techTreeDP=provider)})
        p._require_unloaded_tree({name:types.SimpleNamespace(g_techTreeDP=types.SimpleNamespace(_TechTreeDataProvider__loaded=False))})
        p._require_unloaded_tree({})

    def test_malformed_and_oversized_unlock_rows_rejected(self):
        for rows in [(),[(True,1234)],[(0,)],[(0,False)],[(0,-1)],[(0,1234)]*257,[(0,1234,0x1000000)]]:
            with self.assertRaises(ValueError): p.zero_xp_rows(rows)

    def test_runtime_pin_matches_source_audit_and_requires_native_code(self):
        self.assertEqual(p.AUDITED_PYC_SHA256,audit.SOURCE_PINS['common/items/vehicles.pyc'][1])
        self.assertEqual(p.CONVERTER_CODE_SHA256,audit.CONVERTER_CODE_SHA256)
        cls,_,_,_=self.fixture()
        with self.assertRaises(ValueError): p._audit_class(cls)
        with self.assertRaises(ValueError): p.init(lambda *a,**kw:None,'unapproved')


if __name__ == '__main__': unittest.main()
