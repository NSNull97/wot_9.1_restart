"""Exact #717 Application display-model compatibility; original stays read-only.

Only the native as_tankMan model-init prefix and its size/stack metadata
change. Original confirmation, rendering, input and disposal remain intact.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import zipfile
import zlib

MAX_BYTES = 16 * 1024 * 1024
SOURCE_BYTES = 1258376

def _u30(value: int) -> bytes:
    if type(value) is not int or not 0 <= value < 1 << 30:
        raise ValueError('bounded U30 integer required')
    result = bytearray()
    while value >= 128:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _body(raw: bytes) -> bytes:
    if type(raw) is not bytes or not 8 <= len(raw) <= MAX_BYTES or raw[:3] != b'CWS':
        raise ValueError('bounded original compressed dismissal movie required')
    declared = int.from_bytes(raw[4:8], 'little')
    if not 8 <= declared <= MAX_BYTES:
        raise ValueError('SWF expansion outside pinned bounds')
    stream = zlib.decompressobj()
    body = stream.decompress(raw[8:], declared + 1)
    if (not stream.eof or stream.unused_data or stream.unconsumed_tail
            or len(body) != declared - 8):
        raise ValueError('SWF compressed stream or declared length differs')
    return body


APPLICATION_MEMBER = 'gui/flash/Application.swf'
APPLICATION_TARGET = 'res_mods/0.9.1/gui/flash/Application.swf'
APPLICATION_DISPLAY_QNAMES = (('nationID', 3800), ('tankmanName', 11051), ('tankmanIcon', 19359),
    ('roleIcon', 9342), ('roleLevel', 6318), ('skillsCount', 19360), ('lastSkill', 19361),
    ('lastSkillLevel', 13266), ('preLastSkill', 19362), ('hasNewSkill', 6325),
    ('newSkillsCount', 15826), ('lastNewSkillLevel', 19363))
APPLICATION_NEW = b'\x60' + _u30(518) + b'\x42\x00' + b''.join(
    b'\x2a\xd1\x66' + _u30(index) + b'\x61' + _u30(index)
    for _, index in APPLICATION_DISPLAY_QNAMES)


def transform_application_display(raw: bytes) -> tuple[bytes, dict]:
    """Construct the original display model in the measured parent domain."""
    if (type(raw) is not bytes or len(raw) != SOURCE_BYTES
            or digest(raw) != '8c53f7cf510a3b328ee114307613c8f1416beb3360b587b6b158bb7d8ac02b62'):
        raise ValueError('exact audited Application movie required')
    body = _body(raw)
    method = body[2631489:2631634]
    if (digest(body) != '5a778e0889fbb5e8b73380cd040990342deb54073176f0119d413e1492392b01'
            or digest(method) != '9f35526bcb6052e7bdcbd7386051d9009e5eb46fcecb6a691a6dab99a6009fb5'
            or body.count(method) != 1):
        raise ValueError('Application display method identity differs')
    old = bytes.fromhex('608604d146a2bd0101')
    transformed = method[:10] + APPLICATION_NEW + method[19:]
    patches = [(45441, bytes.fromhex('c49b3100'), bytes.fromhex('2a9c3100')),
        (2631483, b'\x03', b'\x04'), (2631487, bytes.fromhex('9101'), bytes.fromhex('f701')),
        (2631499, old, APPLICATION_NEW)]
    if any(body[offset:offset + len(left)] != left for offset, left, _ in patches):
        raise ValueError('Application display method metadata differs')
    result_body = body
    for offset, left, right in reversed(patches):
        result_body = result_body[:offset] + right + result_body[offset + len(left):]
    restored = result_body
    for offset, left, right in reversed(patches):
        if restored[offset:offset + len(right)] != right:
            raise ValueError('Application display inverse patch differs')
        restored = restored[:offset] + left + restored[offset + len(right):]
    if (restored != body or digest(transformed) != '0454b2bc5c13583154dc206ad4755ba611c52c61e6de47b3161b611b20fa13e4'
            or digest(result_body) != 'f6ab81c4efa07ebc3015bbd3c6624d0097182c35dd5b7ee962dd0cab30f67a4a'):
        raise ValueError('Application display change exceeds the exact prior v2 candidate')
    result = raw[:4] + struct.pack('<I', len(result_body) + 8) + zlib.compress(result_body, 9)
    if _body(result) != result_body or digest(result) != '592c5c8c6ef71f49b49003c64833d3338dd1323e6fd7f3f477466d2acc5c8fa9':
        raise ValueError('Application display artifact differs from pinned v2')
    return result, dict(schema='p04j-dismissal-flash-transform.v2', target=APPLICATION_TARGET,
        source_member=APPLICATION_MEMBER, source_sha256=digest(raw), source_bytes=len(raw),
        installed_sha256=digest(result), installed_bytes=len(result),
        original_body_sha256=digest(body), transformed_body_sha256=digest(result_body),
        method_index=13017, method='DismissTankmanDialog.as_tankMan',
        original_method_sha256=digest(method), transformed_method_sha256=digest(transformed),
        method_offset_in_body=2631489, method_bytes=145, transformed_method_bytes=247,
        patch_offset_in_method=10, patch_bytes=9, replacement_bytes=len(APPLICATION_NEW),
        original_hex=old.hex(), replacement_hex=APPLICATION_NEW.hex(),
        metadata_patches=[dict(body_offset=offset, original_hex=left.hex(), replacement_hex=right.hex())
                          for offset, left, right in patches[:-1]],
        native_model_constructor='SkillDropModel', native_constructor_coercion=False,
        display_fields=[name for name, _ in APPLICATION_DISPLAY_QNAMES],
        max_stack_before=3, max_stack_after=4, original_local_count=2,
        source_argument='actual_primitive_display_fields', typed_object_bridge=False,
        original_confirmation_unchanged=True, original_layout_disposal_unchanged=True,
        all_other_uncompressed_bytes_unchanged=True, branch_offsets_unchanged=True,
        inverse_exact_original_body=True, body_size_delta=102,
        supplied_tariff_rows=False, native_acceptance='NOT_RUN')


def _read_payload(client: Path, member: str, source_bytes: int) -> bytes:
    package = client / 'res/packages/gui.pkg'
    # Bound metadata allocation before ZipFile reads the central directory.
    size = package.stat().st_size
    if not 22 <= size <= 700 * 1024 * 1024:
        raise ValueError('GUI package size outside bounded original archive')
    with package.open('rb') as stream:
        start = max(0, size - 65557)
        stream.seek(start)
        tail = stream.read(65557)
    offset = tail.rfind(b'PK\x05\x06')
    if offset < 0 or len(tail) - offset < 22:
        raise ValueError('bounded ordinary ZIP end record required')
    signature, disk, central_disk, count_disk, count, central_size, central_offset, comment = struct.unpack_from('<4s4H2IH', tail, offset)
    if (disk or central_disk or count != count_disk or not 1 <= count <= 8192
            or central_size > MAX_BYTES or central_offset + central_size != start + offset
            or offset + 22 + comment != len(tail)):
        raise ValueError('GUI package metadata bounds or layout differs')
    with zipfile.ZipFile(package) as archive:
        rows = [row for row in archive.infolist() if row.filename == member]
        if len(rows) != 1 or rows[0].file_size != source_bytes or rows[0].compress_size > MAX_BYTES:
            raise ValueError('exact unique bounded dismissal movie archive member required')
        with archive.open(rows[0]) as stream:
            raw = stream.read(MAX_BYTES + 1)
    return raw


def application_display_payload(client: Path) -> tuple[bytes, dict]:
    return transform_application_display(_read_payload(client, APPLICATION_MEMBER, 1258376))
