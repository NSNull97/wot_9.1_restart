"""Authored codec for source-verified USSR normal, unskilled tankman passports.

Only the two admitted vehicle types and four primary roles are supported.
The caller owns inventory identity and validates the requested vehicle seat.
No original executable code is imported or run by this module.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import struct

FORMAT = "<6BB4Hi3H"
DESCRIPTOR_BYTES = 25
DOSSIER_HEX = "420000000000"
ROLE_IDS = {"commander": 1, "driver": 3, "gunner": 4, "loader": 5}
TYPE_ROLES = {13: ("commander", "driver"),
              28: ("commander", "gunner", "driver", "loader", "loader")}
ROLE_RANK_IDS = {"commander": tuple(range(2, 11)), "driver": tuple(range(1, 10)),
                 "gunner": tuple(range(1, 10)), "loader": tuple(range(9))}
CATALOG_SOURCE = "res/scripts/item_defs/tankmen/ussr.xml"
CATALOG_BYTES = 45148
CATALOG_SHA256 = "7277417f9ffac7f742cd6b1bfce02cc7a182558fbdf7db137604323403552cee"
CATALOG_BOUNDS = {"first_name_id": 112, "last_name_id": 1036, "icon_id": 30}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def verify_catalog(original_root):
    """Read and verify the exact bounded source catalog; return only numbers."""
    from packed_xml import decode, walk
    path = Path(original_root) / CATALOG_SOURCE
    require(path.is_file() and not path.is_symlink() and path.stat().st_size == CATALOG_BYTES,
            "source catalog path/size")
    with path.open("rb") as stream:
        raw = stream.read(CATALOG_BYTES + 1)
    require(len(raw) == CATALOG_BYTES and hashlib.sha256(raw).hexdigest() == CATALOG_SHA256,
            "source catalog digest")
    rows = list(walk(decode(raw, max_bytes=65536, max_nodes=12000, max_depth=12)))
    values = dict(rows)
    # Packed XML's base64 kind preserves its DataSection string representation.
    require(values["/normalGroups[1]/men1[1]/sex[1]"] == {"base64": "male"}, "male group")
    normal = [path for path, _ in rows if re.fullmatch(r"/normalGroups\[1\]/[^/]+\[1\]", path)]
    require(normal == ["/normalGroups[1]/men1[1]"], "normal group catalog")
    result = {}
    for field, source in (("first_name_id", "firstNames"), ("last_name_id", "lastNames"), ("icon_id", "icons")):
        pattern = re.compile(r"/normalGroups\[1\]/men1\[1\]/" + source + r"\[1\]/_([0-9]+)\[1\]")
        ids = [int(match[1]) for path, _ in rows if (match := pattern.fullmatch(path))]
        require(ids == list(range(1, CATALOG_BOUNDS[field] + 1)), "exact catalog IDs")
        result[field] = ids
    names = [match[1] for path, _ in rows if (match := re.fullmatch(r"/ranks\[1\]/([^/]+)\[1\]", path))]
    require(len(names) == 11 and len(set(names)) == 11, "rank catalog")
    ranks = {role: tuple(names.index(name) for name in values["/roleRanks[1]/" + role + "[1]"].split()) for role in ROLE_IDS}
    require(ranks == ROLE_RANK_IDS, "role rank catalog")
    return {"sha256": CATALOG_SHA256, "ids": result, "rank_names": names, "role_rank_ids": ranks}


def encode_descriptor(*, vehicle_type_id, role, role_level, first_name_id, last_name_id, icon_id):
    require(type(vehicle_type_id) is int and vehicle_type_id in TYPE_ROLES, "trained vehicle type")
    require(type(role) is str and role in ROLE_IDS, "primary role")
    require(type(role_level) is int and 50 <= role_level <= 100, "qualification 50..100")
    for field, value in (("first_name_id", first_name_id), ("last_name_id", last_name_id), ("icon_id", icon_id)):
        require(type(value) is int and 1 <= value <= CATALOG_BOUNDS[field], "catalog identity " + field)
    rank, remainder = divmod(role_level - 50, 50)
    rank_word = rank | ((50 - remainder) << 5)
    return struct.pack(FORMAT, 8, vehicle_type_id, ROLE_IDS[role], role_level, 0, 0, 0,
                       first_name_id, last_name_id, icon_id, rank_word, 0, 66, 0, 0)


def decode_descriptor(raw):
    require(type(raw) is bytes and len(raw) == DESCRIPTOR_BYTES, "exact 25-byte descriptor")
    header, vehicle, role_id, level, count, last_level, flags, first, last, icon, rank_word, xp, version, blocks1, blocks2 = struct.unpack(FORMAT, raw)
    require(header == 8 and count == last_level == flags == xp == blocks1 == blocks2 == 0 and version == 66,
            "normal nation0 unskilled zero-freeXP empty-dossier descriptor")
    role = next((name for name, value in ROLE_IDS.items() if value == role_id), None)
    values = dict(vehicle_type_id=vehicle, role=role, role_level=level,
                  first_name_id=first, last_name_id=last, icon_id=icon)
    require(encode_descriptor(**values) == raw, "canonical rank/descriptor")
    return dict(values, nation_id=0, rank_id=ROLE_RANK_IDS[role][rank_word & 31],
                rank_index=rank_word & 31, levels_to_next_rank=rank_word >> 5,
                free_xp=0, skills=[], last_skill_level=0, is_female=False,
                is_premium=False, dossier_hex=DOSSIER_HEX)


def recruit_descriptor(native_id, vehicle_type_id, role, role_level=50):
    """Project allocation policy; identity is assigned by the server transaction."""
    require(type(native_id) is int and 4 <= native_id <= 16, "new native ID 4..16")
    return encode_descriptor(vehicle_type_id=vehicle_type_id, role=role, role_level=role_level,
                             first_name_id=native_id, last_name_id=native_id, icon_id=native_id)
