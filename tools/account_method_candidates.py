"""Read-only Account method ordering hypotheses, checked separately with native packets."""
import argparse
from client_audit import config, output_dir, read_limited, save_json, sha256
from account_contract_probe import children, scalar
from packed_xml import decode


def run(out):
    _, paths = config()
    root = paths['research_client_root']/'res/scripts/entity_defs'
    sources = []
    def read(name):
        path = root/name
        data = read_limited(path, 1024*1024)
        sources.append({'path':str(path),'sha256':sha256(path)})
        return decode(data)
    aliases = {x['name']:x['data'] for x in children(read('alias.xml'))}
    fixed = {'UINT8':1,'INT8':1,'BOOL':1,'UINT16':2,'INT16':2,'UINT32':4,
             'INT32':4,'FLOAT32':4,'UINT64':8,'INT64':8,'FLOAT64':8,'VECTOR3':12}
    def size(node, depth=0):
        if depth > 12:raise ValueError('alias recursion')
        name = scalar(node)
        if name in fixed:return fixed[name]
        if name in aliases:return size(aliases[name],depth+1)
        if name=='FIXED_DICT':
            attrs={x['name']:x['data'] for x in children(node)}
            if attrs.get('AllowNone'):return None
            sizes=[size(next(x['data'] for x in children(p['data']) if x['name']=='Type'),depth+1)
                   for p in children(attrs.get('Properties'))]
            return None if None in sizes else sum(sizes)
        return None
    groups = {'ClientMethods':[], 'BaseMethods':[]}
    visited=set()
    def walk(name):
        if name in visited or len(visited)>24:raise ValueError('interface cycle/bound')
        visited.add(name)
        node=read(name)
        for g in children(node):
            if g['name']=='Implements':
                for x in children(g['data']):walk('interfaces/'+scalar(x['data']).lower()+'.def')
        for g in children(node):
            if g['name'] not in groups:continue
            for m in children(g['data']):
                attrs=children(m['data'])
                if g['name']=='BaseMethods' and not any(x['name']=='Exposed' for x in attrs):continue
                sizes=[size(x['data']) for x in attrs if x['name']=='Arg']
                length=None if None in sizes else sum(sizes)
                groups[g['name']].append({'name':m['name'],'stream_size':length,
                    'args':[x['data'] for x in attrs if x['name']=='Arg'],'source':name})
    walk('account.def')
    for group, rows in groups.items():
        # Hypothesis from pinned toolkit stable stream-size ordering; not asserted
        # to be the native #717 table until observed RPCs agree.
        rows.sort(key=lambda r:(r['stream_size'] is None,r['stream_size'] or 0))
        for index,row in enumerate(rows):row['candidate_exposed_id']=index
    save_json(out/'method-candidates.json',{'classification':'INFERRED, native verification required',
        'sources':sources,'tables':groups,'ordering':'implements first, stable fixed-size ascending, then variable'})
    for group, rows in groups.items():
        print(group,len(rows),[(r['name'],r['candidate_exposed_id']) for r in rows if r['name'] in ('doCmdInt3','onCmdResponse','onCmdResponseExt')])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True)
    run(output_dir(p.parse_args().out))
