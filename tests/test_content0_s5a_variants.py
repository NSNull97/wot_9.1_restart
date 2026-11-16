import copy,unittest
from tools.content0_s5a_variants import variants
class VariantTests(unittest.TestCase):
    def test_only_bot_net_flags_change(self):
        seats=[{'kind':'human','net':False}]+[{'kind':k,'net':True,'crew_percent':100} for k in ('china-Ch17_WZ131_1_WZ132','france-AMX_13_75','usa-T71')]
        base={'fixed_scout_v1':{'version':1,'seats':seats,'events':[]},'identity':'keep'};before=copy.deepcopy(base);out=variants(base)
        self.assertEqual(base,before);self.assertEqual([x['net'] for x in out['net-off']['fixed_scout_v1']['seats']],[False]*4)
        self.assertEqual([x['net'] for x in out['net-on']['fixed_scout_v1']['seats']],[False,True,True,True]);self.assertEqual(out['net-off']['identity'],'keep')
        bad=copy.deepcopy(base);bad['fixed_scout_v1']['seats'][0]['net']=True
        with self.assertRaises(ValueError):variants(bad)
