"""Own generated primitive files only; pinned CPython2.7.3 compatibility check.

This is not a loader for requests or arbitrary pickle files. The parent writes
fresh files, hashes and exact assertions, then starts this isolated subprocess.
Every instruction is whitelisted before cPickle loads the trusted output.
No client code, bytecode or engine modules are imported or executed.
"""
from __future__ import print_function
import cPickle
import hashlib
import json
import os
import pickletools
import sys

assert sys.version_info[:3] == (2, 7, 3)
root=os.path.realpath(sys.argv[1])
with open(os.path.join(root,'cache-check.json'),'rb')as stream:
    raw=stream.read(8193)
assert len(raw)<=8192
assert hashlib.sha256(raw).hexdigest()==sys.argv[2]
expected=json.loads(raw)
assert set(expected)==set(('kind','descriptor_hex','nation_id','seat_count','free_left','next_native_id','files','shell_ids'))
allowed=set(('PROTO','EMPTY_DICT','MARK','BININT1','BININT2','BININT','BINFLOAT','SHORT_BINSTRING','BINSTRING',
    'NONE','NEWTRUE','NEWFALSE','SETITEMS','EMPTY_LIST','APPENDS','TUPLE','EMPTY_TUPLE','STOP'))
trees={}
for name in ('state.bin','shop.bin','dossier.bin'):
    with open(os.path.join(root,name),'rb')as stream:raw=stream.read(32769)
    assert 4<=len(raw)<=32768
    assert hashlib.sha256(raw).hexdigest()==expected['files'][name]['sha256']
    operations=list(pickletools.genops(raw));assert len(operations)<=32768
    assert all(op.name in allowed for op,arg,pos in operations)
    assert operations[0][0].name=='PROTO'and operations[0][1]==2
    assert operations[-1][0].name=='STOP'and operations[-1][2]==len(raw)-1
    trees[name]=cPickle.loads(raw)
state=trees['state.bin'];inventory=state['inventory'];own=inventory[1]
assert state['rev']==1
assert own['compDescr'][3].encode('hex')==expected['descriptor_hex']
assert own['crew'][3]==range(4,4+expected['seat_count'])
assert state['stats']['freeTMenLeft']==expected['free_left']
assert own['shells'][1]==[2570,0,2826,4,3082,10]
assert own['shells'][3]==[n for cd in expected['shell_ids']for n in(cd,0)]
assert all(inventory[10][cd]==0 for cd in expected['shell_ids'])
for n in range(4,expected['next_native_id']):
    passport=inventory[8]['compDescr'][n]
    assert type(passport)is str and len(passport)==25 and ord(passport[0])==(expected['nation_id']<<4|8)
    assert ord(passport[3])==50 and inventory[8]['vehicle'][n]==3
assert trees['shop.bin']['rev']==6
assert len(trees['shop.bin']['items']['itemPrices'])==2494
assert type(trees['dossier.bin'])is tuple and trees['dossier.bin'][0]==1
print(json.dumps(dict(status='PASS_CPYTHON273_OWN_PRIMITIVE_OUTPUT_ONLY',kind=expected['kind'],
    seats=expected['seat_count'],native='NOT_RUN',original_execution=False),sort_keys=True))
