"""Bounded, read-only DDS metadata and top-mip alpha inspection.

This module deliberately does not infer whether alpha is transparency or packed
material data.  A caller must establish texture roles from material bindings.
Only legacy 2D DDS formats needed for the #717 resource census are supported.
"""
from __future__ import annotations

import struct

MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_DIMENSION = 8192
MAX_PIXELS = 8192 * 8192
_DDSD_PITCH = 0x8
_DDPF_ALPHAPIXELS = 0x1
_DDPF_FOURCC = 0x4
_DDPF_RGB = 0x40
_DDSCAPS2_CUBEMAP_OR_VOLUME = 0xFE00 | 0x200000
_SELECTOR_MASK = tuple(sum({1 << ((n >> (3 * j)) & 7) for j in range(4)})
                       for n in range(4096))
_NIBBLE_MASK = tuple(sum({1 << ((n >> (4 * j)) & 15) for j in range(4)})
                     for n in range(65536))


class DDSError(ValueError):
    """Invalid, truncated, unsafe, or unsupported DDS input."""


def _require(ok, message):
    if not ok:
        raise DDSError(message)


def _contiguous(mask):
    if not mask:
        return True
    mask >>= (mask & -mask).bit_length() - 1
    return mask & (mask + 1) == 0


def _valid_pixels(width, height, bx, by):
    return [4 * y + x for y in range(min(4, height - by * 4))
            for x in range(min(4, width - bx * 4))]


def _values(mask):
    return [i for i in range(256) if (mask >> i) & 1]


def inspect_dds(data: bytes) -> dict:
    """Inspect one bounded DDS payload; raise DDSError on unsupported inputs.

    Alpha values are exact decoded values used by pixels in the *top* mip only.
    Results describe stored channels, never their purpose.  All declared mip
    levels must fit in the payload, though trailing bytes are reported, not
    interpreted.  Alpha in lower mip levels is not inspected.
    """
    _require(isinstance(data, (bytes, bytearray, memoryview)), "DDS must be bytes")
    _require(128 <= len(data) <= MAX_FILE_BYTES, "DDS size outside bounds")
    view = memoryview(data)
    _require(view[:4] == b"DDS ", "invalid DDS magic")
    _require(struct.unpack_from("<I", view, 4)[0] == 124, "invalid DDS header size")
    _require(struct.unpack_from("<I", view, 76)[0] == 32, "invalid pixel-format size")
    flags = struct.unpack_from("<I", view, 8)[0]
    height, width = struct.unpack_from("<II", view, 12)
    pitch = struct.unpack_from("<I", view, 20)[0]
    depth = struct.unpack_from("<I", view, 24)[0]
    mip_raw = struct.unpack_from("<I", view, 28)[0]
    caps2 = struct.unpack_from("<I", view, 112)[0]
    pf_flags = struct.unpack_from("<I", view, 80)[0]
    fourcc = bytes(view[84:88])
    _require(0 < width <= MAX_DIMENSION and 0 < height <= MAX_DIMENSION,
             "DDS dimensions outside bounds")
    _require(width * height <= MAX_PIXELS, "DDS pixel count outside bounds")
    _require(depth <= 1 and not (caps2 & _DDSCAPS2_CUBEMAP_OR_VOLUME),
             "DDS cubemap or volume unsupported")
    mips = mip_raw or 1
    _require(mips <= max(width, height).bit_length(), "invalid mip count")

    masks = None
    raw_bpp = None
    if pf_flags & _DDPF_FOURCC:
        _require(fourcc in (b"DXT1", b"DXT3", b"DXT5"), "unsupported DDS FourCC")
        fmt = fourcc.decode("ascii")
        unit_bytes = 8 if fmt == "DXT1" else 16
        storage = {"DXT1": "DXT1_1BIT_CONDITIONAL", "DXT3": "DXT3_EXPLICIT_4BIT",
                   "DXT5": "DXT5_INTERPOLATED_8BIT"}[fmt]
    else:
        _require(bool(pf_flags & _DDPF_RGB), "unsupported raw DDS pixel format")
        bits, red, green, blue, alpha = struct.unpack_from("<IIIII", view, 88)
        _require(bits in (16, 24, 32), "unsupported raw RGB bit depth")
        masks = (red, green, blue, alpha)
        _require(all(_contiguous(mask) and mask < (1 << bits) for mask in masks),
                 "invalid channel masks")
        _require(all(masks[i] & masks[j] == 0 for i in range(4) for j in range(i + 1, 4)),
                 "overlapping channel masks")
        _require(all(masks[:3]), "missing RGB mask")
        _require(bool(pf_flags & _DDPF_ALPHAPIXELS) == bool(alpha), "inconsistent alpha flag and mask")
        raw_bpp = bits // 8
        if flags & _DDSD_PITCH:
            _require(pitch == width * raw_bpp, "padded raw pitch unsupported")
            # The header specifies only the top row's pitch; lower-level row
            # alignment cannot be established without a format-specific rule.
            _require(mips == 1, "raw pitched mip chain unsupported")
        fmt = f"RGB{bits}"
        storage = "RAW_MASK" if alpha else "NONE"

    sizes = []
    for level in range(mips):
        w, h = max(1, width >> level), max(1, height >> level)
        size = ((w + 3) // 4) * ((h + 3) // 4) * unit_bytes if raw_bpp is None else w * h * raw_bpp
        sizes.append(size)
    _require(128 + sum(sizes) <= len(view), "DDS mip chain truncated")
    top = view[128:128 + sizes[0]]

    # Values are represented by a bit set, so no image-sized buffer is made.
    observed = 0
    if fmt == "DXT1":
        block_x = (width + 3) // 4
        for n, (c0, c1, picks) in enumerate(struct.iter_unpack("<HHI", top)):
            if c0 > c1:
                observed |= 1 << 255
                continue
            punch = (picks & (picks >> 1)) & 0x55555555
            bx, by = n % block_x, n // block_x
            if bx * 4 + 4 <= width and by * 4 + 4 <= height:
                used = punch.bit_count()
                count = 16
            else:
                valid = _valid_pixels(width, height, bx, by)
                used = sum((picks >> (2 * i) & 3) == 3 for i in valid)
                count = len(valid)
            if used:
                observed |= 1
            if used < count:
                observed |= 1 << 255
            if observed == 1 | (1 << 255):
                break
    elif fmt == "DXT3":
        block_x = (width + 3) // 4
        for n, (alpha64, _) in enumerate(struct.iter_unpack("<QQ", top)):
            bx, by = n % block_x, n // block_x
            if bx * 4 + 4 <= width and by * 4 + 4 <= height:
                code = (_NIBBLE_MASK[alpha64 & 65535] | _NIBBLE_MASK[(alpha64 >> 16) & 65535] |
                        _NIBBLE_MASK[(alpha64 >> 32) & 65535] | _NIBBLE_MASK[alpha64 >> 48])
            else:
                code = 0
                for i in _valid_pixels(width, height, bx, by):
                    code |= 1 << ((alpha64 >> (4 * i)) & 15)
            for value in range(16):
                if code & (1 << value):
                    observed |= 1 << (value * 17)
            if all(observed & (1 << (17 * j)) for j in range(16)):
                break
    elif fmt == "DXT5":
        block_x = (width + 3) // 4
        for n, (alpha64, _) in enumerate(struct.iter_unpack("<QQ", top)):
            a, b = alpha64 & 255, (alpha64 >> 8) & 255
            indices = alpha64 >> 16
            palette = ([a, b] + [((7 - i) * a + i * b) // 7 for i in range(1, 7)] if a > b
                       else [a, b] + [((5 - i) * a + i * b) // 5 for i in range(1, 5)] + [0, 255])
            bx, by = n % block_x, n // block_x
            if bx * 4 + 4 <= width and by * 4 + 4 <= height:
                code = (_SELECTOR_MASK[indices & 4095] | _SELECTOR_MASK[(indices >> 12) & 4095] |
                        _SELECTOR_MASK[(indices >> 24) & 4095] | _SELECTOR_MASK[indices >> 36])
            else:
                code = 0
                for i in _valid_pixels(width, height, bx, by):
                    code |= 1 << ((indices >> (3 * i)) & 7)
            for selector in range(8):
                if code & (1 << selector):
                    observed |= 1 << palette[selector]
            if observed == (1 << 256) - 1:
                break
    elif masks[3]:
        alpha = masks[3]
        shift = (alpha & -alpha).bit_length() - 1
        maximum = alpha >> shift
        for offset in range(0, len(top), raw_bpp):
            sample = int.from_bytes(top[offset:offset + raw_bpp], "little")
            observed |= 1 << (((sample & alpha) >> shift) * 255 // maximum)
    else:
        observed = 1 << 255

    return {
        "width": width, "height": height, "format": fmt, "mip_count": mips,
        "mip_sizes": sizes, "payload_size": len(view),
        "trailing_bytes": len(view) - 128 - sum(sizes),
        "pixel_format_flags": pf_flags, "raw_masks": list(masks) if masks else None,
        "alpha_storage": storage, "alpha_values_top_mip": _values(observed),
        "alpha_semantics": "UNKNOWN",
    }
