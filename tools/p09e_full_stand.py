"""Bounded source-bound planner for a purchased P09E garage vehicle.

The research writer owns a purchased vehicle, its source component assembly and
the garage projection.  It does not yet own the native contracts needed to put
that *new* inventory id into the accepted crew, ammunition or optional-device
writers.  This module makes that boundary executable: it prepares the verified
garage/loadout portion and returns an explicit NOT_RUN report for the services
that still lack a verified contract.  It never changes SQLite and never opens
battle admission.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

from game_profile_tx import TransactionError
from p09e_research_projection import garage_record
from p09e_research_store import assembly


SCHEMA = "p09e-full-stand-preparation.v1"
MAX_BYTES = 16 * 1024
MAX_CREW_SEATS = 8
MAX_EQUIPMENT_SLOTS = 3
SUPPORTED_CREW_NATIVE_IDS = (1, 2)
SUPPORTED_AMMO_NATIVE_IDS = (1, 2)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def sha(value):
    return hashlib.sha256(value).hexdigest()


def require(value, code="INVALID_FULL_STAND"):
    if not value:
        raise TransactionError(code)


def _bounded_text(value, code):
    require(type(value) is str and 1 <= len(value) <= 256 and "\x00" not in value, code)
    return value


def _vehicle(catalog, owned):
    """Validate the exact P09E owned-row shape without widening it."""
    require(type(owned) is dict and set(owned) == {
        "vehicle_inventory_id", "native_id", "vehicle_id", "modules", "runtime_supported"
    }, "CORRUPT_VEHICLE_ROW")
    inventory_id = _bounded_text(owned["vehicle_inventory_id"], "CORRUPT_VEHICLE_ID")
    require(type(owned["native_id"]) is int and owned["native_id"] >= 3,
            "BASE_VEHICLE_NOT_A_PURCHASE")
    require(owned["runtime_supported"] is False, "RUNTIME_PROFILE_ALREADY_QUALIFIED")
    vehicle_id = _bounded_text(owned["vehicle_id"], "CORRUPT_VEHICLE_TYPE")
    require(vehicle_id in catalog.vehicles, "UNKNOWN_VEHICLE_TYPE")
    modules = deepcopy(owned["modules"])
    # assembly validates role set, compatibility, turret/gun pairing, mass and
    # source bounds.  The result is the only source of loadout metrics here.
    metrics = assembly(catalog, vehicle_id, modules)
    definition = catalog.vehicles[vehicle_id]
    roles = definition.get("crew_roles")
    require(type(roles) is list and 1 <= len(roles) <= MAX_CREW_SEATS
            and all(type(role) is str and role for role in roles)
            and len(set(roles)) == len(roles), "SOURCE_CREW_ROLES_UNKNOWN")
    return inventory_id, vehicle_id, modules, metrics, roles


def _unsupported(service, reason, *, native_ids=()):
    return {"status": "NOT_RUN", "service": service, "reason": reason,
            "supported_native_ids": list(native_ids)}


def prepare(catalog, owned, *, crew_ids=(), ammo=(), equipment=(), request_battle=False):
    """Prepare a deterministic garage-only full-stand report.

    ``owned`` must be a purchased P09E row (native id >= 3).  The returned
    report contains a verified module/loadout projection and explicit guards for
    crew, ammunition and equipment.  Non-empty service inputs are rejected
    rather than treated as a fake assignment.  ``request_battle`` is likewise a
    hard refusal: this card does not qualify a purchased vehicle for battle.
    """
    if request_battle:
        raise TransactionError("UNVERIFIED_RUNTIME_PROFILE")
    inventory_id, vehicle_id, modules, metrics, roles = _vehicle(catalog, owned)
    require(type(crew_ids) in (list, tuple) and len(crew_ids) == 0,
            "UNSUPPORTED_NEW_VEHICLE_CREW")
    require(type(ammo) in (list, tuple) and len(ammo) == 0,
            "UNSUPPORTED_NEW_VEHICLE_AMMO")
    require(type(equipment) in (list, tuple) and len(equipment) == 0,
            "UNSUPPORTED_NEW_VEHICLE_EQUIPMENT")
    garage = garage_record(catalog, {"vehicle_id": vehicle_id, "modules": modules})
    report = {
        "schema": SCHEMA,
        "status": "PREPARED_GARAGE_ONLY_NOT_NATIVE",
        "vehicle": {
            "vehicle_inventory_id": inventory_id,
            "vehicle_id": vehicle_id,
            "native_id": owned["native_id"],
            "modules": modules,
            "runtime_supported": False,
        },
        "loadout": {
            # The native descriptor is binary; the report is JSON evidence and
            # therefore carries its canonical hex spelling.
            "compDescr_hex": garage["compDescr"].hex(),
            "repair": garage["repair"],
            "mass_grams": metrics["mass_grams"],
            "max_load_grams": metrics["max_load_grams"],
        },
        "crew": {
            **_unsupported("p04k-native-barracks-recruitment.v1",
                           "new_inventory_id_not_in_verified_native_crew_contract",
                           native_ids=SUPPORTED_CREW_NATIVE_IDS),
            "roles": roles,
            "slots": [None] * len(roles),
        },
        "ammunition": {
            **_unsupported("p09d-native-ammo.v1",
                           "new_inventory_id_has_no_verified_ammo_mount",
                           native_ids=SUPPORTED_AMMO_NATIVE_IDS),
            "loaded": [],
            "capacity": None,
        },
        "equipment": {
            **_unsupported("optional-device-writer",
                           "no_verified_native_optional-device_purchase_contract"),
            "slots": [0] * MAX_EQUIPMENT_SLOTS,
        },
        "battle": {
            "status": "BLOCKED_UNVERIFIED_PROFILE",
            "battle_admission": False,
            "reason": "p09e_policy_keeps_purchased_vehicle_out_of_battle",
        },
    }
    raw = canonical(report)
    require(len(raw) <= MAX_BYTES, "FULL_STAND_REPORT_TOO_LARGE")
    report["report_sha256"] = sha(raw)
    return report


def report_digest(report):
    """Digest a report while excluding its self-referential digest field."""
    value = deepcopy(report)
    value.pop("report_sha256", None)
    return sha(canonical(value))


__all__ = ["SCHEMA", "prepare", "report_digest", "canonical"]

