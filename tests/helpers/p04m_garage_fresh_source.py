"""Closed TEST context: retain original source pins, attest separate C path publication.

No SQL, allocation, source/destination override CLI, publication or writes.
"""
from pathlib import Path
import hashlib
import json
import stat

ORIGINAL_ROOT=Path('D:/WoT_9.1_Server')
SHORT_ROOT=Path('C:/wot091-night-20261017-01/w')
ALLOCATION=Path('C:/Users/NSNull/AppData/Local/Temp/wot091-night-workspace-kcadgetk/short-workspace01/allocation.json')
ALLOCATION_SHA='677765e23e8de12beb02bfb1b57574e7f528bfe27d872582371f6037db89199e'
CONTEXT=ALLOCATION.parents[1]/'dependencies-short02/resource-context.json'
CONTEXT_SHA='a44579f46813ab449ee8107880e50ff11d1d7a68775abbd764683e6aed1a79bc'
SPECS=(
 ('local/evidence/20261016-p06t-owned01/seed01/seed.json','56ecea1b3548a13efbac9d3870ee27fa96dc639557b124bd608a0abbcffe0e4b','f4c7f9174b208e9c42d6668cf7796a9026693c1ebea87bbd0eeeadd581f2debf'),
 ('local/night-staging/20261016/p10b-selection-http01/seed01/seed.json','50d4c10623d94b63a50621650429b34beffdbc48dee2176028e2f62b07da3287','a04216d90e8e9e8b379fc2d34a0fed9f400e373d8d4c591d723bb00a1accc2cf'),
)
def need(value,code):
    if not value:raise ValueError(code)
def plain(value):
    p=Path(value);need(p.is_absolute()and '..'not in p.parts and not str(p).startswith(('\\\\','//')),'C33_ABSOLUTE_LOCAL')
    for q in(p,*p.parents):
        try:s=q.lstat()
        except FileNotFoundError:continue
        need(not stat.S_ISLNK(s.st_mode)and not(getattr(s,'st_file_attributes',0)&0x400),'C33_REPARSE')
    return p.resolve(strict=True)
def read(path,maximum):
    p=plain(path);need(p.is_file()and 0<p.stat().st_size<=maximum,'C33_BOUNDED_INPUT');raw=p.read_bytes();need(len(raw)<=maximum,'C33_INPUT_GROWTH');return raw
def digest(raw):return hashlib.sha256(raw).hexdigest()
def unique(items):
    d={}
    for k,v in items:need(k not in d and len(d)<4096,'C33_DUPLICATE_OR_BOUND');d[k]=v
    return d
def parse(raw):return json.loads(raw,object_pairs_hook=unique)
def original_root(runtime_root):
    root=plain(runtime_root);need(root in(ORIGINAL_ROOT,SHORT_ROOT),'C33_CLOSED_ROOT')
    if root==SHORT_ROOT:
        raw=read(ALLOCATION,4096);need(digest(raw)==ALLOCATION_SHA,'C33_ALLOCATION_PIN');a=parse(raw)
        need(a['schema']=='wot091-fresh-short-workspace.v1'and Path(a['workspace'])==root and Path(a['source_root'])==ORIGINAL_ROOT
             and a['source_head']=='3675a486e3cadee5fd08277dee97e32a7d909a02'and a['old_data_touched']is False,'C33_ALLOCATION_IDENTITY')
    return ORIGINAL_ROOT
def derive_metadata(raw,runtime_root):
    """Independent exact-token recipe. No historical hash is recomputed/relabelled."""
    need(Path(runtime_root)in(ORIGINAL_ROOT,SHORT_ROOT),'C33_CLOSED_ROOT')
    value=parse(raw);out=dict(value)
    for key in('database','bundle'):
        source=Path(value[key]);relative=source.relative_to(ORIGINAL_ROOT)
        need(relative.parts and relative.parts[0]=='local'and '..'not in relative.parts,'C33_METADATA_RUNTIME_SCOPE')
        changed=str(Path(runtime_root)/relative)
        token=json.dumps(value[key],ensure_ascii=False).encode('utf-8');replacement=json.dumps(changed,ensure_ascii=False).encode('utf-8')
        need(raw.count(token)==1,'C33_METADATA_TOKEN_COUNT');raw=raw.replace(token,replacement);out[key]=changed
    need(parse(raw)==out,'C33_METADATA_RECIPE');return raw
def validate_metadata_bytes(original,current,runtime_root):
    need(Path(runtime_root)in(ORIGINAL_ROOT,SHORT_ROOT),'C33_CLOSED_ROOT')
    expected=original if Path(runtime_root)==ORIGINAL_ROOT else derive_metadata(original,runtime_root)
    need(current==expected,'C33_DERIVED_METADATA_BYTES');return parse(current)
def context_seed(index,runtime_root):
    need(type(index)is int and index in(0,1),'C33_INDEX');root=plain(runtime_root);source=original_root(root)
    rel,original_sha,db_sha=SPECS[index];original_path=source/rel;original=read(original_path,65536)
    need(digest(original)==original_sha,'C33_ORIGINAL_METADATA_PIN');metadata_path=root/rel;current=read(metadata_path,65536)
    data=validate_metadata_bytes(original,current,root);db=plain(data['database']);need(db==metadata_path.with_name('game.sqlite'),'C33_DB_SIBLING')
    need(digest(read(db,16*1024*1024))==db_sha,'C33_CONTEXT_DB_PIN')
    if root==SHORT_ROOT:
        context=read(CONTEXT,1024*1024);need(digest(context)==CONTEXT_SHA,'C33_RESOURCE_CONTEXT_PIN');row=parse(context)['files'][rel]
        need(row['source_sha256']==original_sha and row['sha256']==digest(current)and Path(row['path'])==metadata_path
             and Path(row['source'])==original_path and row['kind']=='seed'and set(row['changes'])=={'/database','/bundle'},'C33_CONTEXT_SEED_LINEAGE')
    return data,dict(path=str(metadata_path),sha256=digest(current),original_sha256=original_sha,
        derivation='original-source'if root==ORIGINAL_ROOT else'short-c-runtime-paths.v1')
