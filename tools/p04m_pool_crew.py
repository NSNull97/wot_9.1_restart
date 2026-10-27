"""Versioned source-bound pool crew contracts; no inventory grants.

Old F-K codecs and policies stay frozen. Native inventory IDs are supplied by
the owner's server-authored vehicle map, never used as source type IDs.
``CrewContract`` (v1, lifetime 16) stays the default; ``CrewContractV2``
(lifetime 192) is selected only by an account's stored migration marker.
Seat roles come from the CAT-01 catalog when a worker activated it, otherwise
from the equal legacy stock registry.
"""
from copy import deepcopy
import json
import struct

from game_profile_tx import TransactionError
from p09d_ammo_projection import canonical, encode, MAX_UPDATE
from p09d_ammo_store import sha, require
from p04d_crew_projection import DESCRIPTOR_PINS
from p04h_crew_store import recruit_identity
from p04h_tankman_descriptor import CATALOG_BOUNDS, ROLE_RANK_IDS as OLD_RANKS, FORMAT, DOSSIER_HEX
from p04i_tankman_descriptor import (decode_descriptor as old_decode, encode_descriptor as old_encode,
    learn_skill, SKILL_NAMES, SKILLS_BY_ROLE, LEARNABLE_SKILLS)
from p04m_stock_registry import PINS, DEFINITION_SHA256
from p04k_crew_projection import BarracksRecruitmentProjectionSource

SCHEMA = "p04m-pool-crew.v1"
CAPACITY = 16
ROLE_IDS = {"commander": 1, "radioman": 2, "driver": 3, "gunner": 4, "loader": 5}
RANKS = dict(OLD_RANKS, radioman=tuple(range(9)))
POLICY = {"schema": SCHEMA, "definition_sha256": DEFINITION_SHA256, "capacity": CAPACITY,
    "recruitment": "actual-owned-vehicle-free50-server-allocator-no-migration-grants",
    "allocator": "retained-monotonic-lifetime16-no-retirement-refund", "passports": "source-USSR-normal-types13-28-18-0-10",
    "assignment": "actual-owned-type-primary-seat-match-combined-roles-retained",
    "learning": "retained-legacy-zero-XP-contract-new50-unqualified", "battle_admission": "NEW_TYPES_DISABLED"}
POLICY_SHA256 = sha(canonical(POLICY))
MEMBER_FIELDS = {"native_id", "crew_id", "role", "descriptor_hex", "vehicle_native_id", "seat"}
# Original Barracks capacity (stats.berths of the published native account):
# at most this many unassigned tankmen, independent of the lifetime allocator.
BERTHS = 16
V2_SCHEMA = "p04m-pool-crew.v2"
# 192 keeps every identity and freeTMenLeft value in one pickle BININT1 byte,
# so the gateway/bridge byte codecs keep their exact shape.
V2_CAPACITY = 192
V2_POLICY = dict(POLICY, schema=V2_SCHEMA, capacity=V2_CAPACITY, berths=BERTHS,
    allocator="retained-monotonic-lifetime192-no-retirement-refund",
    passports="source-USSR-normal-modulo-names112-surnames1036-icons30-v1-identical-1-16",
    seat_roles="catalog-v1-when-active-else-equal-stock-registry")
V2_POLICY_SHA256 = sha(canonical(V2_POLICY))


def pins():
    """Stock seat/role pins: CAT-01 catalog when this worker activated it."""
    import catalog_v1
    if not catalog_v1.active():
        return PINS
    value = catalog_v1.stock_pins()
    require(all(value[kind] == PINS[kind] for kind in set(value) & set(PINS)), "CAT01_CATALOG_DISAGREES")
    return value


def profile_for_type(type_id, nation_id=0):
    """Stock profile of a trained vehicle type; type IDs repeat across nations."""
    require(type(type_id) is int and 0 <= type_id <= 255 and type(nation_id) is int, "RECRUIT_SELECTION_UNSUPPORTED")
    rows = [(kind, pin) for kind, pin in pins().items() if pin[1] >> 8 == type_id and (pin[1] >> 4) & 15 == nation_id]
    require(len(rows) == 1, "RECRUIT_SELECTION_UNSUPPORTED")
    return rows[0]


_PASSPORTS = None


def nation_passports(nation_id):
    """BATTLE-ANY: exact sorted ID sets of one nation's normal passport group
    (`config/catalog/tankman_passports.v1.json`, pinned #717 sources). USSR
    equals the P04H CATALOG_BOUNDS, so its passports stay byte-identical."""
    global _PASSPORTS
    if _PASSPORTS is None:
        import tankman_passports
        tankman_passports.check()
        table = json.loads(tankman_passports.TABLE.read_bytes())
        _PASSPORTS = {row["nation_id"]: {key: tuple(v for a, b in row[source]["ranges"] for v in range(a, b + 1))
                                         for key, source in (("first_name_id", "first_names"), ("last_name_id", "last_names"), ("icon_id", "icons"))}
                      for row in table["nations"]}
        require(_PASSPORTS[0] == {key: tuple(range(1, bound + 1)) for key, bound in CATALOG_BOUNDS.items()}, "CORRUPT_STORE")
    require(type(nation_id) is int and nation_id in _PASSPORTS, "RECRUIT_SELECTION_UNSUPPORTED")
    return _PASSPORTS[nation_id]


def unskilled(*, vehicle_type_id, role, role_level, first_name_id, last_name_id, icon_id, nation_id=0):
    _, pin = profile_for_type(vehicle_type_id, nation_id)
    require(role in {roles[0] for roles in pin[6]}, "RECRUIT_SELECTION_UNSUPPORTED")
    require(type(role_level) is int and 50 <= role_level <= 100, "RECRUIT_SELECTION_UNSUPPORTED")
    ids = nation_passports(nation_id)
    for key, value in (("first_name_id", first_name_id), ("last_name_id", last_name_id), ("icon_id", icon_id)):
        require(type(value) is int and value in ids[key], "INVALID_INPUT")
    rank, remainder = divmod(role_level - 50, 50)
    # Header 8 + (nation << 4): P04H VERIFIED descriptor encoding.
    return struct.pack(FORMAT, 8 + (nation_id << 4), vehicle_type_id, ROLE_IDS[role], role_level, 0, 0, 0,
        first_name_id, last_name_id, icon_id, rank | ((50 - remainder) << 5), 0, 66, 0, 0)


def decode(raw):
    require(type(raw) is bytes and 25 <= len(raw) <= 100, "INVALID_INPUT")
    if raw[0] == 8 and raw[1] in (13, 28) and raw[2] != 2:
        # Retained P04I MS-1/IS-7 descriptors: header 8 is nation 0 by construction.
        return dict(old_decode(raw), nation_id=0)
    require(len(raw) == 25, "INVALID_INPUT")
    header, trained, role, level, count, last, flags, first, surname, icon, rank, xp, version, one, two = struct.unpack(FORMAT, raw)
    require(header & 15 == 8 and count == last == flags == xp == one == two == 0 and version == 66, "INVALID_INPUT")
    role = next((key for key, value in ROLE_IDS.items() if value == role), None)
    value = dict(vehicle_type_id=trained, role=role, role_level=level,
        first_name_id=first, last_name_id=surname, icon_id=icon, nation_id=header >> 4)
    require(unskilled(**value) == raw, "INVALID_INPUT")
    return dict(value, rank_index=rank & 31, rank_id=RANKS[role][rank & 31],
        levels_to_next_rank=rank >> 5, free_xp=0, skills=[], last_skill_level=0,
        is_female=False, is_premium=False, dossier_hex=DOSSIER_HEX)


def base_descriptor(decoded):
    return unskilled(**{key: decoded[key] for key in ("vehicle_type_id", "role", "role_level", "first_name_id", "last_name_id", "icon_id", "nation_id")})


def name_ids(identity, nation_id=0):
    """Source name/surname/icon IDs: the (identity-1)-th member (modulo count) of
    the nation's exact ID set. USSR sets are 1..N, so this equals the v1 passport
    `(identity-1) % N + 1` byte for byte; other nations index their own sets."""
    ids = nation_passports(nation_id)
    return tuple(ids[key][(identity - 1) % len(ids[key])] for key in ("first_name_id", "last_name_id", "icon_id"))


def passport(identity, type_id, role, capacity=CAPACITY, nation_id=0):
    require(type(identity) is int and type(capacity) is int and 4 <= identity <= capacity, "FREE_RECRUITMENT_EXHAUSTED")
    first, last, icon = name_ids(identity, nation_id)
    return unskilled(vehicle_type_id=type_id, role=role, role_level=50,
        first_name_id=first, last_name_id=last, icon_id=icon, nation_id=nation_id)


def vehicles(value):
    rows = value["vehicles"]; stock = pins()
    require(type(rows) is list and 2 <= len(rows) <= len(stock), "CORRUPT_STORE")
    result = {}
    seen = set()
    for row in rows:
        require(type(row) is dict and set(row) == {"native_inventory_id", "vehicle_inventory_id", "kind"}, "CORRUPT_STORE")
        kind, native = row["kind"], row["native_inventory_id"]
        require(type(kind) is str and kind in stock and type(native) is int and 1 <= native < 2**31
            and native not in result and kind not in seen, "CORRUPT_STORE")
        expected = value["account_id"] + (":starter-vehicle-v1" if native == 1 else ":test-is7-v1" if native == 2 else ":p09e-vehicle:" + str(native))
        require(row["vehicle_inventory_id"] == expected and (native not in (1, 2) or kind == ("ms1" if native == 1 else "is7"))
            and (kind not in ("ms1", "is7") or native == (1 if kind == "ms1" else 2)), "CORRUPT_STORE")
        result[native] = kind; seen.add(kind)
    require(rows == sorted(rows, key=lambda row: row["native_inventory_id"]) and result.get(1) == "ms1" and result.get(2) == "is7", "CORRUPT_STORE")
    return result


def native_crew(value, contract=None):
    contract = CrewContract if contract is None else contract
    capacity = contract.CAPACITY
    require(type(value) is dict and set(value) == {"policy_sha256", "account_id", "vehicles", "free_recruitment_left",
        "next_native_id", "configuration_revision", "members", "retired_members"}
        and value["policy_sha256"] == contract.POLICY_SHA256, "CORRUPT_STORE")
    from p08b_battle_store import _uuid
    _uuid(value["account_id"])
    types = vehicles(value); stock = pins()
    require(type(value["next_native_id"]) is int and 4 <= value["next_native_id"] <= capacity + 1
        and type(value["free_recruitment_left"]) is int and value["free_recruitment_left"] == capacity + 1 - value["next_native_id"]
        and type(value["configuration_revision"]) is int and 2 <= value["configuration_revision"] < 2**31, "CORRUPT_STORE")
    seats = {native: [None] * len(stock[kind][6]) for native, kind in types.items()}
    descriptors, assigned, used, identities = {}, {}, set(), set()
    for group in ("members", "retired_members"):
        rows = value[group]
        require(type(rows) is list and len(rows) <= capacity, "CORRUPT_STORE")
        previous = 0
        for row in rows:
            require(type(row) is dict and set(row) == MEMBER_FIELDS, "CORRUPT_STORE")
            identity = row["native_id"]
            require(type(identity) is int and previous < identity <= capacity and identity not in used
                and type(row["crew_id"]) is str and row["crew_id"] not in identities
                and row["crew_id"].startswith(value["account_id"] + ":") and len(row["crew_id"]) <= 96, "CORRUPT_STORE")
            encoded = row["descriptor_hex"]
            require(type(encoded) is str and 50 <= len(encoded) <= 100, "CORRUPT_STORE")
            try: raw = bytes.fromhex(encoded); decoded = decode(raw)
            except (ValueError, TypeError, KeyError, IndexError) as error: raise TransactionError("CORRUPT_STORE") from error
            require(raw.hex() == encoded and decoded["role"] == row["role"] and decoded["free_xp"] == decoded["last_skill_level"] == 0
                and len(decoded["skills"]) <= 1 and all(skill in LEARNABLE_SKILLS for skill in decoded["skills"])
                and (not decoded["skills"] or decoded["role_level"] == 100), "CORRUPT_STORE")
            base = base_descriptor(decoded)
            if identity <= 3:
                require(row["role"] == ("commander" if identity == 1 else "driver") and sha(base) == DESCRIPTOR_PINS[row["role"]], "CORRUPT_STORE")
            else:
                require(row["crew_id"] == recruit_identity(value["account_id"], identity)
                    and base == passport(identity, decoded["vehicle_type_id"], row["role"], capacity, decoded["nation_id"]), "CORRUPT_STORE")
            vehicle, seat = row["vehicle_native_id"], row["seat"]
            require(type(vehicle) is int and (vehicle == -1 or vehicle in types), "CORRUPT_STORE")
            if vehicle == -1: require(seat is None, "CORRUPT_STORE")
            else:
                roles = stock[types[vehicle]][6]
                require(type(seat) is int and 0 <= seat < len(roles) and roles[seat][0] == row["role"], "CORRUPT_STORE")
                if group == "members":
                    require(seats[vehicle][seat] is None, "CORRUPT_STORE"); seats[vehicle][seat] = identity
            if group == "members": descriptors[identity], assigned[identity] = raw, vehicle
            previous = identity; used.add(identity); identities.add(row["crew_id"])
    require(used == set(range(1, value["next_native_id"])), "CORRUPT_STORE")
    return {"compDescr": descriptors, "vehicle": assigned}, seats


def delta(before, after, revision, operation, contract=None):
    native_crew(before, contract); inv, seats = native_crew(after, contract)
    require(type(revision) is int and 1 <= revision < 2**31 - 1, "INVALID_INPUT")
    old = {row["native_id"]: row for row in before["members"]}; new = {row["native_id"]: row for row in after["members"]}
    removed = set(old) - set(new)
    changed = {n: row["vehicle_native_id"] for n, row in new.items()
        if n not in old or any(row[k] != old[n][k] for k in ("vehicle_native_id", "seat"))}
    descriptions = {n: inv["compDescr"][n] for n, row in new.items() if n not in old or row["descriptor_hex"] != old[n]["descriptor_hex"]}
    for n in removed: changed[n] = None; descriptions[n] = None
    affected = {r["vehicle_native_id"] for n in set(changed) | removed for r in [old.get(n), new.get(n)] if r is not None} - {-1}
    columns = {}; value = {"prevRev": revision, "rev": revision + 1, "inventory": {8: columns}}
    if changed: columns["vehicle"] = changed
    if descriptions: columns["compDescr"] = descriptions
    if affected: value["inventory"][1] = {"crew": {native: seats[native] for native in sorted(affected)}}
    if operation in ("recruit", "recruit_barracks"): value["stats"] = {"freeTMenLeft": after["free_recruitment_left"]}
    return encode(value, MAX_UPDATE)


class CrewContract:
    SCHEMA, POLICY_SHA256, COMMAND_RESULT_BOUND = SCHEMA, POLICY_SHA256, 32768
    SOURCE = BarracksRecruitmentProjectionSource
    COMMAND, RECRUIT_COMMAND = "p04m.crew_transfer.v1", "p04m.recruit_assign.v1"
    LEARN_COMMAND, DISMISS_COMMAND, BARRACKS_COMMAND = "p04m.learn_skill.v1", "p04m.dismiss.v1", "p04m.recruit_barracks.v1"
    CAPACITY, BERTHS, PROFILE_BOUND = CAPACITY, BERTHS, 16384

    @classmethod
    def native_crew(cls, value):
        return native_crew(value, cls)

    @classmethod
    def commands(cls):
        return (cls.COMMAND, cls.RECRUIT_COMMAND, cls.LEARN_COMMAND, cls.DISMISS_COMMAND, cls.BARRACKS_COMMAND)

    @classmethod
    def operation_command(cls, operation):
        result = {"transfer": cls.COMMAND, "recruit": cls.RECRUIT_COMMAND, "learn": cls.LEARN_COMMAND,
            "dismiss": cls.DISMISS_COMMAND, "recruit_barracks": cls.BARRACKS_COMMAND}
        require(operation in result, "UNSUPPORTED_CREW_OPERATION"); return result[operation]

    @classmethod
    def validate_operation_layout(cls, layout, operation):
        cls.operation_command(operation)
        require(type(layout) is list and len(layout) == (4 if operation in ("recruit", "recruit_barracks") else 3)
            and all(type(v) is int and -2**31 <= v < 2**31 for v in layout), "INVALID_INPUT")
        if operation in ("recruit", "recruit_barracks"):
            require(layout[0] == 3 and layout[3] == 0, "RECRUIT_SELECTION_UNSUPPORTED")

    @classmethod
    def operation_vehicles(cls, before, layout, *, operation):
        cls.validate_operation_layout(layout, operation)
        by_id = {r["native_id"]: r for r in before["members"]}
        if operation == "recruit_barracks": return ()
        if operation == "recruit":
            require(layout[1] in vehicles(before), "UNKNOWN_VEHICLE")
            return (layout[1],)
        if operation in ("learn", "dismiss"):
            require(layout[0] in by_id, "UNKNOWN_TANKMAN"); rows = (by_id[layout[0]]["vehicle_native_id"],)
        else:
            require(layout[0] in vehicles(before), "UNKNOWN_VEHICLE")
            require(layout[2] == -1 or layout[2] in by_id, "UNKNOWN_TANKMAN")
            rows = (layout[0], -1 if layout[2] == -1 else by_id[layout[2]]["vehicle_native_id"])
        return tuple(sorted(set(rows) - {-1}))

    @classmethod
    def plan_operation(cls, before, layout, *, operation, account_id):
        cls.validate_operation_layout(layout, operation); native_crew(before, cls); stock = pins()
        require(before["account_id"] == account_id, "FOREIGN_ACCOUNT")
        require(before["configuration_revision"] < 2**31 - 1, "REVISION_EXHAUSTED")
        result = deepcopy(before); types = vehicles(result); rows = result["members"]; by_id = {r["native_id"]: r for r in rows}
        if operation in ("recruit", "recruit_barracks"):
            identity = result["next_native_id"]
            require(identity <= cls.CAPACITY and result["free_recruitment_left"] > 0, "FREE_RECRUITMENT_EXHAUSTED")
            require(sum(r["vehicle_native_id"] == -1 for r in rows) < cls.BERTHS, "BARRACKS_FULL")
            if operation == "recruit":
                vehicle, seat = layout[1:3]
                require(vehicle in types and 0 <= seat < len(stock[types[vehicle]][6]), "RECRUIT_SELECTION_UNSUPPORTED")
                kind = types[vehicle]; role = stock[kind][6][seat][0]
                for row in rows:
                    if row["vehicle_native_id"] == vehicle and row["seat"] == seat: row.update(vehicle_native_id=-1, seat=None)
            else:
                matches = [k for k, pin in stock.items() if pin[1] == layout[1]]
                require(len(matches) == 1, "RECRUIT_SELECTION_UNSUPPORTED"); kind = matches[0]
                role = next((key for key, value in ROLE_IDS.items() if value == layout[2]), None)
                require(role in {r[0] for r in stock[kind][6]}, "RECRUIT_SELECTION_UNSUPPORTED")
                vehicle, seat = -1, None
            raw = passport(identity, stock[kind][1] >> 8, role, cls.CAPACITY, (stock[kind][1] >> 4) & 15)
            rows.append(dict(native_id=identity, crew_id=recruit_identity(account_id, identity), role=role,
                descriptor_hex=raw.hex(), vehicle_native_id=vehicle, seat=seat))
            result.update(next_native_id=identity + 1, free_recruitment_left=cls.CAPACITY - identity)
        elif operation == "transfer":
            vehicle, seat, identity = layout
            require(vehicle in types and -1 <= seat < len(stock[types[vehicle]][6]) and (seat != -1 or identity == -1), "TRANSFER_SELECTION_UNSUPPORTED")
            require(identity == -1 or identity in by_id, "UNKNOWN_TANKMAN")
            if identity != -1: require(by_id[identity]["role"] == stock[types[vehicle]][6][seat][0], "INCOMPATIBLE_CREW_ROLE")
            for row in rows:
                if row["native_id"] == identity or (row["vehicle_native_id"] == vehicle and (seat == -1 or row["seat"] == seat)):
                    row.update(vehicle_native_id=-1, seat=None)
            if identity != -1: by_id[identity].update(vehicle_native_id=vehicle, seat=seat)
        else:
            require(layout[0] in by_id, "UNKNOWN_TANKMAN"); row = by_id[layout[0]]
            if operation == "dismiss":
                require(layout[1:] == [0, 0], "DISMISS_SELECTION_UNSUPPORTED")
                rows.remove(row); result["retired_members"] = sorted(result["retired_members"] + [row], key=lambda r: r["native_id"])
            else:
                require(layout[2] == 0, "LEARN_SELECTION_UNSUPPORTED")
                try:
                    decoded = decode(bytes.fromhex(row["descriptor_hex"]))
                    require(decoded["vehicle_type_id"] in (13, 28), "SKILL_SELECTION_UNSUPPORTED")
                    roles = (row["role"],) if row["vehicle_native_id"] == -1 else stock[types[row["vehicle_native_id"]]][6][row["seat"]]
                    allowed = frozenset().union(*(SKILLS_BY_ROLE[role] for role in roles)) & LEARNABLE_SKILLS
                    row["descriptor_hex"] = old_encode(learn_skill(decoded, SKILL_NAMES.get(layout[1]), allowed)).hex()
                except (ValueError, TypeError, KeyError) as error: raise TransactionError("SKILL_SELECTION_UNSUPPORTED") from error
        require(result != before, "NO_CONFIGURATION_CHANGE")
        result["configuration_revision"] += 1; native_crew(result, cls); return result

    @classmethod
    def operation_response(cls, request, revision, crew, *, operation, before_crew):
        value = dict(status={"transfer": "transferred", "recruit": "recruited", "recruit_barracks": "recruited", "learn": "learned", "dismiss": "dismissed"}[operation],
            account_id=request["account_id"], native_database_id=request["native_database_id"], command_key=request["command_key"],
            revision=revision, wire_revision=request["wire_revision"] + 1,
            update_hex=delta(before_crew, crew, request["wire_revision"], operation, cls).hex(), replayed=False, result_code=0)
        if operation == "recruit_barracks":
            row = next(r for r in crew["members"] if r["native_id"] == before_crew["next_native_id"])
            value.update(tankman_inventory_id=row["native_id"], tankman_descriptor_hex=row["descriptor_hex"])
        return value


class CrewContractV2(CrewContract):
    """Lifetime 192 allocator; same seats, roles, passports 1..16 and berths."""
    SCHEMA, POLICY_SHA256, COMMAND_RESULT_BOUND = V2_SCHEMA, V2_POLICY_SHA256, 262144
    COMMAND, RECRUIT_COMMAND = "p04m.crew_transfer.v2", "p04m.recruit_assign.v2"
    LEARN_COMMAND, DISMISS_COMMAND, BARRACKS_COMMAND = "p04m.learn_skill.v2", "p04m.dismiss.v2", "p04m.recruit_barracks.v2"
    CAPACITY, PROFILE_BOUND = V2_CAPACITY, 65536


CONTRACTS = (CrewContract, CrewContractV2)


def contract_for_command(command, code="CORRUPT_STORE"):
    rows = [contract for contract in CONTRACTS if command in contract.commands()]
    require(len(rows) == 1, code); return rows[0]


def contract_for_crew(value):
    """The contract that owns one stored crew aggregate (by its policy hash)."""
    rows = [contract for contract in CONTRACTS if type(value) is dict and value.get("policy_sha256") == contract.POLICY_SHA256]
    require(len(rows) == 1, "CORRUPT_STORE"); return rows[0]
