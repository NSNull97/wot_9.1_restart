"""Source-bound MS-1/IS-7 assignment projection with retained trained passports."""
from __future__ import annotations

from p04f_crew_projection import (CrewTransferProjectionSource, canonical, sha,
    project_native_crew, assignment_delta)

SCHEMA = "p04g-native-cross-vehicle-crew.v1"
PROFILE_VERSION = 8
SEAT_ROLES = {1: ("commander", "driver"),
              2: ("commander", "gunner", "driver", "loader", "loader")}
POLICY = {
    "schema": SCHEMA, "target": "v.0.9.1 #717 RU", "command": 105,
    "vehicles": {"1": {"type_compact_id": 3329, "roles_by_slot": list(SEAT_ROLES[1])},
                 "2": {"type_compact_id": 7169, "roles_by_slot": list(SEAT_ROLES[2])}},
    "source_binding": "required-original-717-P04G-static-audit-and-retained-source-bundle",
    "specialization": "preserve-original-MS1-trained-type13-descriptors-and-dossiers",
    "crew_identities": [1, 2, 3], "primary_role_match_required": True,
    "unload_tankman_id": -1, "unload_whole_crew_slot": -1,
    "vacant_seat": None, "barracks_vehicle_id": -1,
    "crew_bound": 16, "barracks_bound": 16, "role_level": 100, "skills": [],
    "migration": "accepted-profile7-three-identities-no-creation",
    "recruitment": "retained-exhausted-one-free100-MS1-driver-quota",
    "reserved_source_or_target": "reject",
    "no_change": "reject-without-revision-or-ledger",
    "policy_scope": "explicit-project-test_lab", "battle_admission": "DISABLED",
}
POLICY_SHA256 = sha(canonical(POLICY))


def native_crew(value):
    return project_native_crew(value, policy_sha256=POLICY_SHA256,
        seat_roles=SEAT_ROLES, required_members=3)


def update_delta(crew, wire_revision, *, recruit=False):
    if recruit:
        raise ValueError("G retains exhausted recruitment quota")
    return assignment_delta(crew, wire_revision, projector=native_crew, recruit=recruit)


class CrossVehicleCrewProjectionSource(CrewTransferProjectionSource):
    PROFILE_VERSION = PROFILE_VERSION
    POLICY_SHA256 = POLICY_SHA256
    METADATA_FILE = "crew-cross-transfer.json"
    project_crew = staticmethod(native_crew)

    def metadata(self, profile, aggregate, state):
        value = super().metadata(profile, aggregate, state)
        del value["vehicle_inventory_id"]
        value["vehicle_count"] = 2
        return value
