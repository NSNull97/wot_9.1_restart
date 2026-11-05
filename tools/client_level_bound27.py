# Python 2.7.3 (client toolchain): rebuild items/vehicles.pyc with _readLevel upper bound 10 -> 11.
# Used by tools/test_vehicle_client.py; reads a local original pyc, writes a derived file. Nothing else changes.
import marshal, sys, types, hashlib
src, dst = sys.argv[1], sys.argv[2]
raw = open(src, 'rb').read()
header, code = raw[:8], marshal.loads(raw[8:])
hits = []
def rebuild(c):
    consts = []
    for k in c.co_consts:
        if isinstance(k, types.CodeType):
            k = rebuild(k)
        consts.append(k)
    if c.co_name == '_readLevel':
        if tuple(consts) != (None, 'level', 1, 10):
            raise SystemExit('unexpected _readLevel constants %r' % (tuple(consts),))
        consts[3] = 11
        hits.append(c.co_name)
    return types.CodeType(c.co_argcount, c.co_nlocals, c.co_stacksize, c.co_flags, c.co_code, tuple(consts),
                          c.co_names, c.co_varnames, c.co_filename, c.co_name, c.co_firstlineno, c.co_lnotab,
                          c.co_freevars, c.co_cellvars)
new = rebuild(code)
if hits != ['_readLevel']:
    raise SystemExit('expected exactly one _readLevel, got %r' % hits)
out = header + marshal.dumps(new)
open(dst, 'wb').write(out)
print('%s %s %d -> %d bytes' % (hashlib.sha256(raw).hexdigest()[:16], hashlib.sha256(out).hexdigest()[:16], len(raw), len(out)))
