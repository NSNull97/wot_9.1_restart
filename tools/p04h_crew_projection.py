"""Bounded roster recruitment projection for the pinned 0.9.1 client."""
from __future__ import annotations

from p04g_crew_projection import SEAT_ROLES, CrossVehicleCrewProjectionSource
from p04f_crew_projection import canonical, sha, require
from p04d_crew_projection import DESCRIPTOR_PINS
from p09d_ammo_projection import encode, MAX_UPDATE
from p04h_tankman_descriptor import decode_descriptor, recruit_descriptor, TYPE_ROLES

SCHEMA = "p04h-native-crew-recruitment.v1"
PROFILE_VERSION = 9
ROLE_LEVEL = 50
CAPACITY = 16
POLICY = {
    "schema": SCHEMA, "target": "v.0.9.1 #717 RU", "command": 309,
    "transfer_command": 105,
    "vehicles": {"1": {"type_compact_id": 3329, "trained_type_id": 13, "roles_by_slot": list(SEAT_ROLES[1])},
                 "2": {"type_compact_id": 7169, "trained_type_id": 28, "roles_by_slot": list(SEAT_ROLES[2])}},
    "source_binding": "required-original-717-P04H-static-audit-and-retained-source-bundle",
    "migration": "accepted-profile8-three-identities-descriptors-preserved-once-only-quota13",
    "retained_crew_identities": [1, 2, 3], "new_identity_range": [4, 16],
    "identity_format": "account_id:recruit-crew:native_id",
    "passport": "source-normal-male-firstNameID-lastNameID-iconID-equal-native_id",
    "role_level": ROLE_LEVEL, "retained_role_level": 100,
    "skills": [], "free_xp": 0, "empty_dossier_hex": "420000000000",
    "crew_bound": CAPACITY, "barracks_bound": CAPACITY,
    "free_quota": "16-minus-retained-and-new-member-count", "cost_index": 0,
    "price": {"credits": 0, "gold": 0}, "shop_revision": 3,
    "primary_role_match_required": True, "trained_type": "requested-target-vehicle",
    "transfer_specialization": "preserve-descriptor-and-dossier",
    "unload_tankman_id": -1, "unload_whole_crew_slot": -1,
    "vacant_seat": None, "barracks_vehicle_id": -1,
    "occupied_seat": "displace-to-barracks",
    "reserved_source_or_target": "reject",
    "no_change": "reject-without-revision-or-ledger",
    "policy_scope": "explicit-project-test_lab", "battle_admission": "DISABLED",
}
POLICY_SHA256 = sha(canonical(POLICY))


def native_crew(value):
    require(type(value) is dict and set(value) == {"policy_sha256", "free_recruitment_left",
        "next_native_id", "configuration_revision", "members"}, "crew projection fields")
    require(value["policy_sha256"] == POLICY_SHA256, "crew policy digest")
    members = value["members"]
    require(type(members) is list and 3 <= len(members) <= CAPACITY, "bounded roster")
    require(type(value["free_recruitment_left"]) is int and value["free_recruitment_left"] == CAPACITY - len(members), "quota/count binding")
    require(type(value["next_native_id"]) is int and value["next_native_id"] == len(members) + 1, "allocator/count binding")
    require(type(value["configuration_revision"]) is int and 2 <= value["configuration_revision"] < 2**31, "configuration revision")
    seats = {vehicle: [None] * len(roles) for vehicle, roles in SEAT_ROLES.items()}
    descriptors, assignments, identities = {}, {}, set()
    for number, row in enumerate(members, 1):
        require(type(row) is dict and set(row) == {"native_id", "crew_id", "role", "descriptor_hex", "vehicle_native_id", "seat"}, "member fields")
        require(type(row["native_id"]) is int and row["native_id"] == number, "ordered stable IDs")
        require(type(row["crew_id"]) is str and 1 <= len(row["crew_id"]) <= 96 and row["crew_id"].isascii()
            and row["crew_id"] not in identities, "domain identity")
        identities.add(row["crew_id"])
        require(type(row["descriptor_hex"]) is str and len(row["descriptor_hex"]) == 50, "descriptor bound")
        raw = bytes.fromhex(row["descriptor_hex"])
        require(raw.hex() == row["descriptor_hex"], "canonical descriptor hex")
        decoded = decode_descriptor(raw)
        require(type(row["role"]) is str and row["role"] == decoded["role"], "primary role binding")
        if number <= 3:
            role = "commander" if number == 1 else "driver"
            require(row["role"] == role and sha(raw) == DESCRIPTOR_PINS[role], "retained descriptor pin")
        else:
            require(row["role"] in TYPE_ROLES[decoded["vehicle_type_id"]]
                and raw == recruit_descriptor(number, decoded["vehicle_type_id"], row["role"], ROLE_LEVEL), "new passport policy")
        vehicle, seat = row["vehicle_native_id"], row["seat"]
        require(type(vehicle) is int and (vehicle == -1 or vehicle in seats), "owned vehicle")
        if vehicle == -1:
            require(seat is None, "barracks seat")
        else:
            require(type(seat) is int and 0 <= seat < len(seats[vehicle]) and SEAT_ROLES[vehicle][seat] == row["role"]
                and seats[vehicle][seat] is None, "unique compatible seat")
            seats[vehicle][seat] = number
        descriptors[number], assignments[number] = raw, vehicle
    return {"compDescr": descriptors, "vehicle": assignments}, seats


def update_delta(crew, wire_revision, *, recruit=False, before_crew=None):
    require(type(wire_revision) is int and 1 <= wire_revision < 2**31 - 1, "wire revision bound")
    inventory, seats = native_crew(crew)
    native_crew(before_crew)
    old = {row["native_id"]: row for row in before_crew["members"]}
    added = [row["native_id"] for row in crew["members"] if row["native_id"] not in old]
    require(len(added) == int(recruit), "new identity count")
    changed = {row["native_id"]: row["vehicle_native_id"] for row in crew["members"]
        if row["native_id"] not in old or any(row[key] != old[row["native_id"]][key] for key in ("vehicle_native_id", "seat"))}
    require(bool(changed), "assignment change required")
    columns = {"vehicle": changed}
    value = {"prevRev": wire_revision, "rev": wire_revision + 1,
             "inventory": {8: columns, 1: {"crew": seats}}}
    if recruit:
        columns["compDescr"] = {added[0]: inventory["compDescr"][added[0]]}
        value["stats"] = {"freeTMenLeft": crew["free_recruitment_left"]}
    return encode(value, MAX_UPDATE)


class RosterRecruitmentProjectionSource(CrossVehicleCrewProjectionSource):
    PROFILE_VERSION = PROFILE_VERSION
    POLICY_SHA256 = POLICY_SHA256
    METADATA_FILE = "crew-roster.json"
    project_crew = staticmethod(native_crew)

    def metadata(self, profile, aggregate, state):
        value = super().metadata(profile, aggregate, state)
        value.update(command=309, transfer_command=105, role_level=ROLE_LEVEL)
        return value
