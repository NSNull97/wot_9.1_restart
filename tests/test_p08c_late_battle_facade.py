"""Actual SQLite source receipts; authored final facts, no World/native claim."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

import test_p08c_late_results as old
from p08b_battle_service import battle_service

class BattleFacadeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed=json.loads(old.SEED.read_bytes());cls.catalog=old.load_catalog(seed['original'])

    def test_different_run_same_arena_finish_atomic_refusal_and_fresh_arena_natural_finish(self):
        for loss in (False,True):
            with self.subTest(loss=loss):
                f=old.Scenario(self.catalog,loss);self.addCleanup(f.close)
                finals=[f.final(0),f.final(1)];f.finish(0,finals[0]);f.finish(1,finals[1],f.result(finals))
                append=f.append_request(finals);self.assertEqual(f.call(append)['status'],'appended')
                store=f.stores[0];run='918a034b-cba0-426a-85e9-a1a095aa0162';serial=0
                def call(operation,**extra):
                    nonlocal serial
                    serial+=1
                    value=dict(version=4 if loss else 2,operation=operation,account_id=old.ACCOUNTS[0],
                        native_database_id=f.public(store)['native_database_id'],command_key='late:facade:'+str(serial),
                        expected_revision=store.read_profile(old.ACCOUNTS[0])['revision'],run_id=run,**extra)
                    if loss:value['contract']='p06t-ammo-rack-loss.v1'
                    return battle_service(store,value,authenticated_account_id=old.ACCOUNTS[0])
                self.assertEqual(call('run_open')['status'],'ready')
                receipt=call('admit',battle_id=run+':'+f.arena,native_inventory_id=1)['reservation']
                def finish(receipt,natural):
                    final=deepcopy(finals[0]);value=dict(battle_id=receipt['battle_id'],native_inventory_id=1,
                        reservation_id=receipt['reservation_id'],remaining_ammunition=final['remaining_ammunition'],
                        terminal_hp=final['terminal_hp'],terminal_state_json=old.canonical(final['terminal_state']).decode('utf8'),
                        reason='battle_finished' if natural is not None else 'cancelled')
                    if loss:value.update(fired_ammunition=final['fired_ammunition'],lost_ammunition=final['lost_ammunition'],loss_event=None)
                    if natural is not None:value['results_json']=old.canonical(natural).decode('utf8')
                    return call('finish',**value)
                before=f.old_tables()
                denied=finish(receipt,f.result(finals));self.assertEqual(denied['status'],'rejected');self.assertEqual(denied['code'],'RESULT_MISMATCH')
                self.assertEqual(f.old_tables(),before)
                self.assertEqual(store.connection.execute('SELECT status FROM p06t_reservation WHERE account_id=? AND reservation_id=?',(old.ACCOUNTS[0],receipt['reservation_id'])).fetchone()[0],'active')
                self.assertEqual(f.query()[1]['results_json'],json.loads(append['seal_json'])['results_json'])
                self.assertEqual(finish(receipt,None)['status'],'finished')
                f.arena='9007199254740994'
                receipt=call('admit',battle_id=run+':'+f.arena,native_inventory_id=1)['reservation']
                natural=f.result(finals);response=finish(receipt,natural);self.assertEqual(response['status'],'finished')
                read=store.results_loss if loss else store.results_mixed
                query=dict(version=4 if loss else 2,operation='query',account_id=old.ACCOUNTS[0],native_database_id=f.public(store)['native_database_id'],command_key='late:facade:query',arena_id=f.arena)
                if loss:query['contract']='p06t-ammo-rack-loss.v1'
                self.assertEqual(json.loads(read(query,authenticated_account_id=old.ACCOUNTS[0])['results_json']),natural)

if __name__=='__main__':unittest.main()
