"""Inspect all mip alpha values and construct alpha-preserving 2x DDS probes.

This is a local experiment, not a runtime texture loader. It preserves every
original compressed mip verbatim as levels 1..N and, for DXT3/DXT5, replicates
compressed alpha selectors/endpoints 2x in the new top level. It never assumes
what alpha means to the material/shader.
"""
from __future__ import annotations
import hashlib
import struct
from tools.visual02_dds import DDSError, inspect_dds


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def mip_report(data):
    meta = inspect_dds(data)
    if meta['format'] not in ('DXT1', 'DXT3', 'DXT5'):
        raise DDSError('VISUAL-03 supports only DXT1/DXT3/DXT5')
    header, offset, levels = bytearray(data[:128]), 128, []
    for level, size in enumerate(meta['mip_sizes']):
        width, height = max(1, meta['width'] >> level), max(1, meta['height'] >> level)
        part = data[offset:offset + size]
        h = bytearray(header)
        struct.pack_into('<II', h, 12, height, width)
        struct.pack_into('<I', h, 28, 1)
        info = inspect_dds(bytes(h) + part)
        levels.append({'level': level, 'width': width, 'height': height,
                       'bytes': size, 'sha256': _sha(part),
                       'alpha_values': info['alpha_values_top_mip']})
        offset += size
    if meta['trailing_bytes']:
        raise DDSError('DDS trailing bytes require separate analysis')
    return {'source_sha256': _sha(data), 'format': meta['format'],
            'width': meta['width'], 'height': meta['height'],
            'mip_count': meta['mip_count'], 'levels': levels,
            'alpha_semantics': 'UNKNOWN'}


def expand_alpha_block(source_top, width, height, fmt, dst_bx, dst_by):
    """Return DXT3/5 alpha data for a 4x4 destination block (nearest 2x)."""
    if fmt not in ('DXT3', 'DXT5'):
        raise DDSError('alpha-block expansion requires DXT3/5')
    src_x, src_y = min((dst_bx * 4) // 2, width - 1), min((dst_by * 4) // 2, height - 1)
    blocks_x = (width + 3) // 4
    src_index = (src_y // 4) * blocks_x + src_x // 4
    block = source_top[src_index * 16:src_index * 16 + 8]
    if len(block) != 8:
        raise DDSError('truncated source alpha block')
    bits = int.from_bytes(block, 'little')
    selectors, header = (bits, 0) if fmt == 'DXT3' else (bits >> 16, bits & 0xffff)
    width_bits = 4 if fmt == 'DXT3' else 3
    mask = (1 << width_bits) - 1
    out = 0
    for y in range(4):
        for x in range(4):
            sx = min((dst_bx * 4 + x) // 2, width - 1)
            sy = min((dst_by * 4 + y) // 2, height - 1)
            if sx // 4 != src_x // 4 or sy // 4 != src_y // 4:
                raise DDSError('destination block crosses source alpha block')
            val = (selectors >> (width_bits * ((sy % 4) * 4 + sx % 4))) & mask
            out |= val << (width_bits * (y * 4 + x))
    return (out if fmt == 'DXT3' else header | (out << 16)).to_bytes(8, 'little')


def alpha_plane(data):
    """Decode each top-mip alpha pixel for independent pixel-wise validation."""
    meta = inspect_dds(data)
    fmt, width, height = meta['format'], meta['width'], meta['height']
    if fmt not in ('DXT3', 'DXT5'):
        raise DDSError('alpha plane supports only DXT3/5')
    pixels = bytearray(width * height)
    blocks_x, blocks_y = (width + 3) // 4, (height + 3) // 4
    for by in range(blocks_y):
        for bx in range(blocks_x):
            offset = 128 + (by * blocks_x + bx) * 16
            bits = int.from_bytes(data[offset:offset + 8], 'little')
            if fmt == 'DXT3':
                selectors = bits
                palette = [x * 17 for x in range(16)]
                n = 4
            else:
                a, b = bits & 255, (bits >> 8) & 255
                selectors = bits >> 16
                palette = ([a, b] + [((7 - i) * a + i * b) // 7 for i in range(1, 7)] if a > b
                           else [a, b] + [((5 - i) * a + i * b) // 5 for i in range(1, 5)] + [0, 255])
                n = 3
            for y in range(4):
                for x in range(4):
                    px, py = bx * 4 + x, by * 4 + y
                    if px < width and py < height:
                        pixels[py * width + px] = palette[(selectors >> (n * (y * 4 + x))) & ((1 << n) - 1)]
    return bytes(pixels)


def assemble_2x(source, encoded_top):
    """Add a 2x color top while preserving original lower compressed mip bytes.

    DXT1 is accepted only when its source and encoded top are opaque. For DXT3/5
    the encoded top's alpha blocks are replaced with an exact nearest 2x expansion
    of the original alpha selectors/endpoints. No client writes are performed.
    """
    src = mip_report(source)
    top = mip_report(encoded_top)
    if (top['width'], top['height'], top['format'], top['mip_count']) != (
            src['width'] * 2, src['height'] * 2, src['format'], 1):
        raise DDSError('encoded top format, size or mip count does not match 2x source')
    if src['format'] == 'DXT1':
        if src['levels'][0]['alpha_values'] != [255] or top['levels'][0]['alpha_values'] != [255]:
            raise DDSError('DXT1 transparent top requires a separate alpha-preserving strategy')
    payload = bytearray(encoded_top[128:])
    if src['format'] in ('DXT3', 'DXT5'):
        sw, sh = src['width'], src['height']
        top_src = source[128:128 + src['levels'][0]['bytes']]
        dst_blocks_x, dst_blocks_y = (sw * 2 + 3) // 4, (sh * 2 + 3) // 4
        for by in range(dst_blocks_y):
            for bx in range(dst_blocks_x):
                offset = (by * dst_blocks_x + bx) * 16
                payload[offset:offset + 8] = expand_alpha_block(top_src, sw, sh, src['format'], bx, by)
    # Preserve the original DDS metadata, updating only fields made necessary
    # by adding the enlarged top level. The source may use a partial mip chain.
    header = bytearray(source[:128])
    struct.pack_into('<II', header, 12, src['height'] * 2, src['width'] * 2)
    struct.pack_into('<I', header, 20, len(payload))
    flags = struct.unpack_from('<I', header, 8)[0]
    struct.pack_into('<I', header, 8, flags | 0x20000)  # DDSD_MIPMAPCOUNT
    struct.pack_into('<I', header, 28, src['mip_count'] + 1)
    caps = struct.unpack_from('<I', header, 108)[0]
    struct.pack_into('<I', header, 108, caps | 0x8 | 0x400000)  # COMPLEX | MIPMAP
    result = bytes(header) + bytes(payload) + source[128:]
    result_report = mip_report(result)
    if result_report['mip_count'] != src['mip_count'] + 1:
        raise DDSError('output mip count mismatch')
    if [x['sha256'] for x in result_report['levels'][1:]] != [x['sha256'] for x in src['levels']]:
        raise DDSError('original mip bytes changed')
    if result_report['levels'][0]['alpha_values'] != src['levels'][0]['alpha_values']:
        raise DDSError('top alpha values changed')
    if src['format'] in ('DXT3', 'DXT5'):
        original, enlarged = alpha_plane(source), alpha_plane(result)
        w, h = src['width'], src['height']
        for y in range(h * 2):
            for x in range(w * 2):
                if enlarged[y * w * 2 + x] != original[(y // 2) * w + x // 2]:
                    raise DDSError('top alpha pixels are not exact nearest 2x expansion')
    return result
