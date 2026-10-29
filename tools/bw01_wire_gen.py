"""BW-01: generate `crate::bw_wire::Wire` impls next to the types an arena step
ships between the gateway and its Battle Worker process.

Usage (from the repository root):
  python -B -X utf8 tools/bw01_wire_gen.py apply            # (re)write every listed impl
  python -B -X utf8 tools/bw01_wire_gen.py add FILE TYPE... # list and write more types

Each impl destructures the type exhaustively, so a field added later without a
codec is a compile error, not a silently dropped value. The impl sits right
after its type (same module, private fields reachable) between marker comments;
`apply` replaces an existing marked impl in place. Types with hand-written
impls are not listed here. Sources keep their own line endings (LF/CRLF).
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'server/gateway/src'
LIST = ROOT / 'tools/bw01_wire_types.json'
BEGIN = '// BW-01 wire codec (tools/bw01_wire_gen.py): '
END = '// end BW-01 wire codec'


def strip_comments(text):
    out, i, n = [], 0, len(text)
    while i < n:
        if text.startswith('//', i):
            j = text.find('\n', i)
            i = n if j < 0 else j
        elif text.startswith('/*', i):
            j = text.find('*/', i + 2)
            i = n if j < 0 else j + 2
        elif text[i] == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == '\\' else 1
            out.append(text[i:j + 1])
            i = j + 1
        elif text[i] == "'" and i + 2 < n and (text[i + 2] == "'" or (text[i + 1] == '\\' and text.find("'", i + 2) - i <= 5)):
            j = text.find("'", i + 2)
            out.append(text[i:j + 1])
            i = j + 1
        else:
            out.append(text[i])
            i += 1
    return ''.join(out)


def split_top(text, sep=','):
    parts, depth, cur = [], 0, []
    for k, ch in enumerate(text):
        if ch in '([{<':
            depth += 1
        elif ch in ')]}':
            depth -= 1
        elif ch == '>' and not (k > 0 and text[k - 1] == '-'):
            depth -= 1
        if ch == sep and depth == 0:
            parts.append(''.join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append(''.join(cur))
    return [p.strip() for p in parts if p.strip()]


def matching(text, start):
    """Index of the bracket closing the one at `start` (comments stripped)."""
    open_ch = text[start]
    close = {'{': '}', '(': ')', '<': '>', '[': ']'}[open_ch]
    depth = 0
    for k in range(start, len(text)):
        ch = text[k]
        if ch == open_ch:
            depth += 1
        elif ch == close and not (close == '>' and text[k - 1] == '-'):
            depth -= 1
            if depth == 0:
                return k
    raise ValueError('unbalanced')


ATTR = re.compile(r'^\s*#\[(?:[^\[\]]|\[[^\]]*\])*\]\s*', re.S)


def take_attrs(text):
    attrs = []
    while True:
        m = ATTR.match(text)
        if not m:
            return attrs, text.strip()
        a = m.group(0).strip()
        if a.startswith('#[cfg'):
            attrs.append(a)
        text = text[m.end():]


VIS = re.compile(r'^pub(\s*\([^)]*\))?\s+')


def fields_named(body):
    out = []
    for part in split_top(body):
        attrs, part = take_attrs(part)
        part = VIS.sub('', part)
        name = part.split(':', 1)[0].strip()
        out.append((attrs, name))
    return out


def fields_tuple(body):
    return [take_attrs(part)[0] for part in split_top(body)]


def find_item(src, name):
    """(start, end, kind, generics, shape, body) of `struct|enum name` in src."""
    clean = strip_comments(src)
    # strip_comments keeps string/char contents but drops comments; positions
    # differ, so locate in the original with the same pattern and verify.
    pat = re.compile(r'(?m)^[ \t]*(?:#\[[^\n]*\]\s*)*(?:pub(?:\([^)]*\))?\s+)?(struct|enum)\s+' + re.escape(name) + r'\b')
    hits = list(pat.finditer(src))
    if len(hits) != 1:
        raise ValueError(f'{name}: {len(hits)} definitions')
    m = hits[0]
    kind = m.group(1)
    i = m.end()
    generics = ''
    j = i
    while src[j] in ' \t\r\n':
        j += 1
    if src[j] == '<':
        k = matching(src, j)
        generics = src[j + 1:k]
        j = k + 1
    while src[j] in ' \t\r\n':
        j += 1
    if src.startswith('where', j):
        raise ValueError(f'{name}: where clause')
    if src[j] == ';':
        return m.start(), j + 1, kind, generics, 'unit', ''
    # Find the body bracket ignoring comments inside it.
    k = j
    body_open = src[k]
    if body_open not in '({':
        raise ValueError(f'{name}: body')
    depth = 0
    in_line = in_block = False
    q = k
    while True:
        ch = src[q]
        if in_line:
            if ch == '\n':
                in_line = False
        elif in_block:
            if src.startswith('*/', q):
                in_block = False
                q += 1
        elif src.startswith('//', q):
            in_line = True
        elif src.startswith('/*', q):
            in_block = True
        elif ch in '({[':
            depth += 1
        elif ch in ')}]':
            depth -= 1
            if depth == 0:
                break
        q += 1
    body = strip_comments(src[k + 1:q])
    end = q + 1
    if body_open == '(':
        # tuple struct ends with ';'
        semi = src.index(';', end)
        end = semi + 1
    shape = 'named' if body_open == '{' else 'tuple'
    if kind == 'enum':
        shape = 'enum'
    return m.start(), end, kind, generics, shape, body


def generic_parts(generics):
    params, args = [], []
    for p in split_top(generics):
        p = p.split('=', 1)[0].strip()
        if p.startswith("'"):
            params.append(p)
            args.append(p.split(':', 1)[0].strip())
        elif p.startswith('const '):
            params.append(p)
            args.append(p[6:].split(':', 1)[0].strip())
        else:
            name, _, bound = p.partition(':')
            name = name.strip()
            bound = (bound.strip() + '+' if bound.strip() else '') + 'crate::bw_wire::Wire'
            params.append(f'{name}:{bound}')
            args.append(name)
    return params, args


def pat_named(fields):
    return ','.join(f'{" ".join(a)+" " if a else ""}{n}' for a, n in fields)


def gen_impl(name, kind, generics, shape, body):
    params, args = generic_parts(generics)
    head = f'impl{"<"+",".join(params)+">" if params else ""} crate::bw_wire::Wire for {name}{"<"+",".join(args)+">" if args else ""}'
    W = 'use crate::bw_wire::Wire as W;'
    if shape == 'unit':
        put, get = '', 'Ok(Self)'
    elif shape == 'named':
        fs = fields_named(body)
        put = f'let Self{{{pat_named(fs)}}}=self;' + ''.join(f'{" ".join(a)} W::put({n},bw_o);' if a else f'W::put({n},bw_o);' for a, n in fs)
        get = 'Ok(Self{' + ','.join(f'{" ".join(a)+" " if a else ""}{n}:W::get(bw_i)?' for a, n in fs) + '})'
    elif shape == 'tuple':
        fs = fields_tuple(body)
        if any(fs):
            raise ValueError(f'{name}: cfg on tuple field')
        vs = [f'f{k}' for k in range(len(fs))]
        put = f'let Self({",".join(vs)})=self;' + ''.join(f'W::put({v},bw_o);' for v in vs)
        get = 'Ok(Self(' + ','.join('W::get(bw_i)?' for _ in vs) + '))'
    else:
        arms_put, arms_get = [], []
        for tag, variant in enumerate(split_top(body)):
            attrs, variant = take_attrs(variant)
            if attrs:
                raise ValueError(f'{name}: cfg on variant')
            variant = variant.split('=', 1)[0].strip()
            vm = re.match(r'(\w+)\s*(.*)$', variant, re.S)
            vname, rest = vm.group(1), vm.group(2).strip()
            if not rest:
                arms_put.append(f'Self::{vname}=>bw_o.tag({tag}),')
                arms_get.append(f'{tag}=>Ok(Self::{vname}),')
            elif rest.startswith('('):
                n = len(split_top(rest[1:-1]))
                vs = [f'f{k}' for k in range(n)]
                arms_put.append(f'Self::{vname}({",".join(vs)})=>{{bw_o.tag({tag});' + ''.join(f'W::put({v},bw_o);' for v in vs) + '}')
                arms_get.append(f'{tag}=>Ok(Self::{vname}(' + ','.join('W::get(bw_i)?' for _ in vs) + ')),')
            else:
                fs = fields_named(rest[1:-1])
                if any(a for a, _ in fs):
                    raise ValueError(f'{name}: cfg on variant field')
                arms_put.append(f'Self::{vname}{{{pat_named(fs)}}}=>{{bw_o.tag({tag});' + ''.join(f'W::put({n},bw_o);' for _, n in fs) + '}')
                arms_get.append(f'{tag}=>Ok(Self::{vname}{{' + ','.join(f'{n}:W::get(bw_i)?' for _, n in fs) + '}),')
        if not arms_put:
            put, get = 'match *self {}', 'crate::bw_wire::variant(bw_i.tag()?)'
        else:
            put = 'match self {' + ''.join(arms_put) + '}'
            get = 'match bw_i.tag()? {' + ''.join(arms_get) + 't=>crate::bw_wire::variant(t)}'
    wp, wg = (W if 'W::' in put else ''), (W if 'W::' in get else '')
    return (f'{head} {{\n    fn put(&self,bw_o:&mut crate::bw_wire::Enc){{{wp}{put}}}\n'
            f'    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{{{wg}{get}}}\n}}')


def apply_one(path, name):
    raw = path.read_bytes()
    crlf = b'\r\n' in raw
    src = raw.decode('utf-8').replace('\r\n', '\n')
    marker = BEGIN + name + '\n'
    if marker in src:
        a = src.index(marker)
        b = src.index(END, a) + len(END) + 1
        src = src[:a] + src[b:]
        if src[a - 1:a] == '\n' and src[a - 2:a] == '\n\n':
            pass
    start, end, kind, generics, shape, body = find_item(src, name)
    impl = gen_impl(name, kind, generics, shape, body)
    block = '\n' + marker + impl + '\n' + END
    # Insert right after the item; keep the rest of the line (usually newline).
    src = src[:end] + block + src[end:]
    out = src.replace('\n', '\r\n') if crlf else src
    path.write_bytes(out.encode('utf-8'))


def load():
    return json.loads(LIST.read_text(encoding='utf-8')) if LIST.exists() else []


def main(argv):
    items = load()
    if argv[:1] == ['add']:
        rel = argv[1]
        for name in argv[2:]:
            if [rel, name] not in items:
                items.append([rel, name])
            apply_one(SRC / rel, name)
        LIST.write_text(json.dumps(sorted(items), indent=0).replace('\n', '\n') + '\n', encoding='utf-8')
    elif argv[:1] == ['apply']:
        for rel, name in items:
            apply_one(SRC / rel, name)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
