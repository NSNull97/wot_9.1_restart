"""One measured #717 greeting override; derived catalogs belong only in local/.

This module parses scalar MO tables, never imports or executes client resources.
The installer owns before-hash checks, backups, installation and rollback.
"""
import hashlib
import struct


SOURCE = 'res/text/LC_MESSAGES/system_messages.mo'
SOURCE_SHA256 = 'c48a1f5d461c865c0e6b1ee8f9ec2afee21f29ca1fde5badd240aa566ba36992'
SOURCE_BYTES = 102680
ENTRY_COUNT = 656
KEY = b'connected'
GREETING = 'Добро пожаловать на сервер «%s»!'
MAX_MO_BYTES = 1024 * 1024
MAX_ENTRIES = 1024
MAX_STRING_BYTES = 4096
MAX_HASH_SLOTS = 2048
MAGIC = 0x950412DE


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _bounded_bytes(raw):
    _require(type(raw) is bytes, 'MO input must be immutable bytes')
    _require(28 <= len(raw) <= MAX_MO_BYTES, 'MO byte length outside bound')


def _catalog(raw):
    """Read only the measured little-endian, nonplural revision-zero format."""
    _bounded_bytes(raw)
    magic, revision, count, originals, translations, hash_count, hash_offset = struct.unpack_from('<7I', raw)
    _require(magic == MAGIC and revision == 0, 'unmeasured MO magic or revision')
    _require(1 <= count <= MAX_ENTRIES, 'MO entry count outside bound')
    _require(hash_count <= MAX_HASH_SLOTS, 'MO hash-table count outside bound')
    regions = [(0, 28)]
    for base in (originals, translations):
        _require(base >= 28 and base % 4 == 0 and base + count * 8 <= len(raw), 'MO descriptor table outside bounds')
        regions.append((base, base + count * 8))
    if hash_count:
        _require(hash_offset >= 28 and hash_offset % 4 == 0
                 and hash_offset + hash_count * 4 <= len(raw), 'MO hash table outside bounds')
        regions.append((hash_offset, hash_offset + hash_count * 4))
        _require(all(struct.unpack_from('<I', raw, hash_offset + i * 4)[0] <= count for i in range(hash_count)),
                 'MO hash entry outside catalog')
    else:
        _require(hash_offset == 0, 'MO absent hash table has nonzero offset')
    regions.sort()
    _require(all(a[1] <= b[0] for a, b in zip(regions, regions[1:])), 'overlapping MO tables')
    strings_begin = max(end for _, end in regions)

    def string_at(table, index):
        length, offset = struct.unpack_from('<2I', raw, table + index * 8)
        _require(length <= MAX_STRING_BYTES and offset >= strings_begin
                 and offset + length < len(raw), 'MO string outside bounds')
        _require(raw[offset + length] == 0, 'MO string lacks terminator')
        data = raw[offset:offset + length]
        _require(b'\0' not in data, 'unmeasured plural or embedded NUL string')
        try:
            data.decode('utf8')
        except UnicodeDecodeError as error:
            raise ValueError('MO string is not UTF-8') from error
        return data

    pairs = tuple((string_at(originals, i), string_at(translations, i)) for i in range(count))
    keys = [key for key, _ in pairs]
    _require(keys == sorted(set(keys)), 'MO keys duplicate or are not sorted')
    _require(keys[0] == b'', 'MO metadata entry missing')
    return pairs


def _encode(pairs):
    """Deterministic scalar catalog writer; all data validation is bounded."""
    _require(type(pairs) in (tuple, list) and 1 <= len(pairs) <= MAX_ENTRIES, 'MO entry count outside bound')
    _require(all(type(row) is tuple and len(row) == 2 and all(type(v) is bytes for v in row) for row in pairs),
             'MO entries must be byte pairs')
    _require(all(len(v) <= MAX_STRING_BYTES and b'\0' not in v for row in pairs for v in row),
             'MO output string outside bounds')
    keys = [key for key, _ in pairs]
    _require(keys == sorted(set(keys)) and keys[0] == b'', 'MO output keys invalid')
    count = len(pairs)
    size = 28 + count * 16 + sum(len(value) + 1 for row in pairs for value in row)
    _require(size <= MAX_MO_BYTES, 'MO output byte length outside bound')
    tables, strings = [], bytearray()
    start = 28 + count * 16
    for column in (0, 1):
        for row in pairs:
            value = row[column]
            tables.append(struct.pack('<2I', len(value), start + len(strings)))
            strings.extend(value)
            strings.append(0)
    result = struct.pack('<7I', MAGIC, 0, count, 28, 28 + count * 8, 0, 0) + b''.join(tables) + bytes(strings)
    _require(_catalog(result) == tuple(pairs), 'MO writer changed catalog data')
    return result


def _one_placeholder(value):
    _require(type(value) is bytes and value.count(b'%s') == 1 and b'%' not in value.replace(b'%s', b''),
             'greeting must contain exactly one positional %s')


def _replace_connected(pairs):
    targets = [value for key, value in pairs if key == KEY]
    _require(len(targets) == 1, 'measured connected key absent or duplicate')
    replacement = GREETING.encode('utf8')
    _one_placeholder(targets[0])
    _one_placeholder(replacement)
    return tuple((key, replacement if key == KEY else value) for key, value in pairs)


def project_greeting(raw):
    """Return (derived MO bytes, evidence) for the exact measured source only."""
    _bounded_bytes(raw)
    source_sha = hashlib.sha256(raw).hexdigest()
    _require(len(raw) == SOURCE_BYTES and source_sha == SOURCE_SHA256, 'system_messages source SHA/size differs from measured #717')
    original = _catalog(raw)
    _require(len(original) == ENTRY_COUNT, 'measured system_messages entry count differs')
    changed = _replace_connected(original)
    payload = _encode(changed)
    parsed = _catalog(payload)
    _require([key for key, _ in original] == [key for key, _ in parsed], 'stable localization keys changed')
    differences = [(before, after) for before, after in zip(original, parsed) if before != after]
    _require(len(differences) == 1 and differences[0][0][0] == differences[0][1][0] == KEY,
             'localization changed outside connected')
    before = differences[0][0][1]
    return payload, {
        'policy_version': 1,
        'source': SOURCE,
        'source_sha256': source_sha,
        'source_bytes': len(raw),
        'output_sha256': hashlib.sha256(payload).hexdigest(),
        'output_bytes': len(payload),
        'entry_count': len(parsed),
        'changes': [{'key': KEY.decode('ascii'), 'before': before.decode('utf8'), 'after': GREETING}],
        'stable_keys_preserved': True,
        'unchanged_values': ENTRY_COUNT - 1,
        'metadata_preserved': original[0] == parsed[0],
        'placeholder': {'kind': 'positional_string', 'token': '%s', 'count': 1},
        'native_render': 'NOT_RUN',
        'scope': 'One localized value only; no resource installation or client execution.',
    }
