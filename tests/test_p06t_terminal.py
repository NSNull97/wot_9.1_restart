"""Generic validator unit tests with an explicitly SYNTHETIC lab policy.

These do not establish source device maxima, runtime damage or native behaviour.
The independently pinned actual component policy is required for integration.
"""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from p06t_terminal import TerminalPolicy
from p09d_ammo_projection import canonical
from p09d_ammo_store import sha
from game_profile_tx import TransactionError


class TerminalTests(unittest.TestCase):
    def setUp(self):
        self.document=dict(schema="p06t-terminal-policy.v1",policy_revision="test_lab.synthetic-terminal.v1",
            profiles={kind:dict(max_hp=90,crew_count=2,devices=[dict(extra_index=203,max_health=17),dict(extra_index=7,max_health=29)])for kind in ("ms1","is7")})
        self.policy=TerminalPolicy(self.document,expected_sha256=sha(canonical(self.document)))
        self.frozen=dict(kind="ms1",max_hp=90,crew_ids=["actual-owner:crew1","actual-owner:crew2"])
        self.value=dict(policy_revision=self.document["policy_revision"],roster_size=2,crew_active=True,
            crew=[dict(crew_id=identity,alive=True)for identity in self.frozen["crew_ids"]],
            devices=[dict(extra_index=203,health=13,max_health=17),dict(extra_index=7,health=0,max_health=29)],
            fire=dict(active=False,ticks=7,damage=11),death=dict(reason=-1,killer_slot=None,tick=0))

    def validate(self,value=None,**extra):
        return self.policy.validate(canonical(self.value if value is None else value).decode("ascii"),frozen=self.frozen,terminal_hp=23,**extra)

    def bad(self,fn):
        with self.assertRaises(TransactionError):fn()

    def test_pinned_policy_required_and_defensive_copy(self):
        self.bad(lambda:TerminalPolicy(self.document,expected_sha256="0"*64))
        for change in ({"policy_revision":"unversioned"},{"schema":"v1"},{"extra":True}):
            doc=dict(self.document,**change);self.bad(lambda:TerminalPolicy(doc,expected_sha256=sha(canonical(doc))))
        self.document["profiles"]["ms1"]["devices"][0]["max_health"]=999
        self.assertEqual(self.validate(),self.value)

    def test_actual_crew_identity_order_and_boolean_fields_are_required(self):
        for mutate in (lambda v:v["crew"].reverse(),lambda v:v["crew"][0].update(crew_id="foreign:crew"),
            lambda v:v["crew"][0].update(alive=1),lambda v:v.update(crew_active=1),
            lambda v:v["crew"].pop(),lambda v:v.update(roster_size=True)):
            bad=deepcopy(self.value);mutate(bad);self.bad(lambda:self.validate(bad))

    def test_device_health_maximum_index_and_exact_policy_order(self):
        for mutate in (lambda v:v["devices"].reverse(),lambda v:v["devices"][0].update(health=18),
            lambda v:v["devices"][0].update(max_health=18),lambda v:v["devices"][0].update(extra_index=26),
            lambda v:v["devices"].append(dict(v["devices"][0])),lambda v:v["devices"][0].update(health=True)):
            bad=deepcopy(self.value);mutate(bad);self.bad(lambda:self.validate(bad))

    def test_positive_hull_HP_all_crew_dead_is_preserved_with_explicit_death(self):
        value=deepcopy(self.value);value["crew_active"]=False
        for row in value["crew"]:row["alive"]=False
        value["death"]=dict(reason=0,killer_slot=1,tick=42)
        self.assertEqual(self.validate(value)["death"],value["death"])
        value["crew_active"]=True;self.bad(lambda:self.validate(value))

    def test_results_roster_killer_and_live_death_semantics(self):
        self.assertEqual(self.validate(results=dict(participants=[{},{}])),self.value)
        self.bad(lambda:self.validate(results=dict(participants=[{}, {}, {}])))
        value=deepcopy(self.value);value["death"].update(reason=0,killer_slot=1)
        self.bad(lambda:self.validate(value))
        value["crew_active"]=False;value["death"]["killer_slot"]=2;self.bad(lambda:self.validate(value))
        raw=canonical(self.value).decode("ascii")
        self.bad(lambda:self.policy.validate(raw,frozen=self.frozen,terminal_hp=0))

    def test_input_budget_duplicates_float_and_extra_fields_reject(self):
        self.bad(lambda:self.policy.validate("x"*8193,frozen=self.frozen,terminal_hp=23))
        raw=canonical(self.value).decode("ascii").replace('"roster_size":2','"roster_size":2,"roster_size":2')
        self.bad(lambda:self.policy.validate(raw,frozen=self.frozen,terminal_hp=23))
        value=dict(self.value,unknown=True);self.bad(lambda:self.validate(value))
        value=deepcopy(self.value);value["fire"]["ticks"]=0.5;self.bad(lambda:self.validate(value))


if __name__=="__main__":unittest.main(verbosity=2)
