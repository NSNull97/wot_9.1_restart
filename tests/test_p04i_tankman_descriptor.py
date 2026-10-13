"""Source-index, independent byte layout and XP boundary/domain checks."""
from copy import deepcopy
import math
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from p04i_tankman_descriptor import (decode_descriptor, encode_descriptor, learn_skill, add_xp,
    total_xp, skill_levels, level_up_cost, SKILL_IDS, SKILLS_BY_ROLE, XP_COSTS, MAX_FREE_XP)
from p04h_tankman_descriptor import recruit_descriptor

COMMANDER = bytes.fromhex('080d0164000000010001000100410600000000420000000000')
DRIVER = bytes.fromhex('080d0364000000020002000200410600000000420000000000')


class DescriptorProgressionTests(unittest.TestCase):
    def test_existing_native_passports_and_independent_firstskill_byte_insertion(self):
        for raw, name, index in ((COMMANDER, 'commander_tutor', 16), (DRIVER, 'driver_smoothDriving', 29)):
            before = decode_descriptor(raw)
            self.assertEqual(encode_descriptor(before), raw)
            after = learn_skill(before, name, SKILLS_BY_ROLE[before['role']])
            self.assertEqual(encode_descriptor(after), raw[:4] + bytes((1,index,0)) + raw[6:])
            self.assertEqual((after['free_xp'], after['last_skill_level'], total_xp(after)), (0,0,105030))
            self.assertEqual(skill_levels(after), [{'skill_id':name,'level':0}])
            self.assertEqual(before['skills'], [])

    def test_pinned_integer_table_matches_source_formula_and_known_totals(self):
        independently = [0]
        for level in range(1,101): independently.append(independently[-1] + int(math.floor(50.0 * 100.0**((level-1)/100.0) + 0.5)))
        self.assertEqual(tuple(independently), XP_COSTS)
        self.assertEqual((XP_COSTS[50], XP_COSTS[100],level_up_cost(0,1),level_up_cost(0,2)), (9546,105030,100,200))

    def test_role_and_firstskill_exact_boundary_rank_and_unspent_xp(self):
        recruit = decode_descriptor(recruit_descriptor(4,13,'driver'))
        below = add_xp(recruit,499)
        self.assertEqual((below['role_level'],below['free_xp']), (50,499))
        up = add_xp(below,1)
        self.assertEqual((up['role_level'],up['free_xp'],up['levels_to_next_rank']), (51,0,49))
        trained = add_xp(recruit,XP_COSTS[100]-XP_COSTS[50])
        self.assertEqual((trained['role_level'],trained['free_xp'],trained['rank_index'],trained['levels_to_next_rank']), (100,0,1,50))
        selected = learn_skill(trained,'repair',SKILLS_BY_ROLE['driver'])
        self.assertEqual(add_xp(selected,99)['last_skill_level'],0)
        self.assertEqual(add_xp(selected,100)['last_skill_level'],1)
        self.assertEqual(add_xp(selected,100)['free_xp'],0)
        full = add_xp(selected,2*XP_COSTS[100])
        self.assertEqual((full['last_skill_level'],full['free_xp'],full['rank_index']), (100,0,3))
        next_skill = learn_skill(full,'camouflage',SKILLS_BY_ROLE['driver'])
        self.assertEqual(skill_levels(next_skill),[{'skill_id':'repair','level':100},{'skill_id':'camouflage','level':0}])
        self.assertEqual(add_xp(next_skill,199)['last_skill_level'],0)
        self.assertEqual(add_xp(next_skill,200)['last_skill_level'],1)

    def test_xp_saturation_never_creates_automatic_skill_and_rejects_clientlike_numbers(self):
        value = decode_descriptor(COMMANDER)
        result = add_xp(add_xp(value,MAX_FREE_XP),MAX_FREE_XP)
        self.assertEqual((result['free_xp'],result['skills']), (MAX_FREE_XP,[]))
        for bad in (True,-1,1.0,MAX_FREE_XP+1,'100'):
            with self.assertRaises(ValueError): add_xp(value,bad)

    def test_skill_catalog_policy_and_qualification_rejections(self):
        value = decode_descriptor(COMMANDER)
        for skill in ('commander_sixthSense','gunner_woodHunter','driver_virtuoso','missing'):
            with self.assertRaises(ValueError): learn_skill(value,skill,SKILLS_BY_ROLE['commander'])
        hired=decode_descriptor(recruit_descriptor(4,28,'gunner'))
        with self.assertRaises(ValueError):learn_skill(hired,'repair',SKILLS_BY_ROLE['gunner'])
        chosen=learn_skill(value,'repair',SKILLS_BY_ROLE['commander'])
        for skill in ('repair','camouflage'):
            with self.assertRaises(ValueError):learn_skill(chosen,skill,SKILLS_BY_ROLE['commander'])

    def test_malformed_variable_descriptor_ids_counts_levels_rank_xp_and_dossier(self):
        good=encode_descriptor(learn_skill(decode_descriptor(COMMANDER),'repair',SKILLS_BY_ROLE['commander']))
        bad=[good[:-1],good+b'0',b'',bytearray(good),b'0'*1000]
        for offset in (0,1,2,3,4,5,6,7,14,19,20,22,24):
            raw=bytearray(good);raw[offset]=255;bad.append(bytes(raw))
        for index in (0,1,18,41,61,255):
            raw=bytearray(good);raw[5]=index
            if index==18:
                # The codec recognizes historical Sixth Sense; project learning
                # policy rejects it independently rather than corrupting its ID.
                self.assertEqual(decode_descriptor(bytes(raw))['skills'],['commander_sixthSense'])
            else:bad.append(bytes(raw))
        for raw in bad:
            with self.subTest(raw=raw),self.assertRaises(ValueError):decode_descriptor(raw)

    def test_all_admitted_source_skill_indices_are_distinct_and_reserved_41_absent(self):
        self.assertEqual(len(SKILL_IDS),25)
        self.assertEqual(len(set(SKILL_IDS.values())),25)
        self.assertNotIn(41,SKILL_IDS.values())
        for name,index in SKILL_IDS.items():
            value=decode_descriptor(COMMANDER);value['skills']=[name]
            self.assertEqual(encode_descriptor(value)[5],index)
