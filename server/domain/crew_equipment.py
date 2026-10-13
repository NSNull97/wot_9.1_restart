"""Isolated server-owned crew / optional-device configuration boundary.

Inputs come from the account/configuration authority, never directly from a
client packet. The separately supplied binding must be read under the same
reservation/revision as the record. SHA256 binds bytes; it is not authentication.
No database, native serialization, inventory grants or battle wiring live here.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import re


FORMAT = "crew-equipment-input.v1"
SNAPSHOT_FORMAT = "crew-equipment-snapshot.v1"
POLICY = "test_lab.crew-equipment.717.v1"
MAX_BYTES = 8192
MAX_DEPTH = 8
MAX_NODES = 256
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9:._-]{0,127}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")

# These are source observations, not redistributed resources. Reproducible
# source audit and bytecode offsets: docs/research/P04B_CREW_EQUIPMENT_SNAPSHOT.md.
SOURCE_PINS = (
    ("res/scripts/item_defs/vehicles/ussr/MS-1.xml", "a494bf04d29da7d066fd6923dbb75a79b947559a52405298c494a943c4b0c535"),
    ("res/scripts/item_defs/vehicles/ussr/IS-7.xml", "8d55fa4657a88f1436cd164afe11bade875a906fa7b97256f1fb2f803b09c10d"),
    ("res/scripts/item_defs/vehicles/common/optional_devices.xml", "f24f01573b3848df1a5051752a2e5f937857e7062b78a4dd1812194486c843c6"),
    ("res/scripts/common/items/vehicles.pyc", "805240e4b59d8a75950dbb97b41c17867606e7e96d7ff0c8d7b05312b83ae8b6"),
    ("res/scripts/common/items/artefacts.pyc", "aedbfc161d7f0b2b78f376540811a0b4113736757982d03bceb4e6f4cccac49c"),
    ("res/scripts/common/items/__init__.pyc", "587ba137fee1b7de77ce81d5e963185ba20267c54d157ce8699a76f2f0d11176"),
    ("res/scripts/common/items/_xml.pyc", "86d408fa983b6a74c7475930f5e651253fe0135dbde22467b30e9cee4224cf1b"),
    ("res/scripts/common/nations.pyc", "34392915b0d2a70a3df0b8151e0fdbb9cb58aad6a708ffc85843c45c596a4562"),
    ("res/scripts/item_defs/vehicles/ussr/list.xml", "167a637d725a233d42e52bd7d5bac00b9af45c0ef225163ab578e202454f5138"),
)


@dataclass(frozen=True)
class VehicleDefinition:
    definition_id: str
    type_compact_descr: int
    tag: str
    seats: tuple[tuple[str, ...], ...]


VEHICLES = (
    VehicleDefinition("vehicle:ms1", 3329, "lightTank",
                      (("commander", "gunner", "radioman", "loader"), ("driver",))),
    VehicleDefinition("vehicle:is7", 7169, "heavyTank",
                      (("commander",), ("gunner",), ("driver",), ("loader",), ("loader", "radioman"))),
)


@dataclass(frozen=True)
class DeviceDefinition:
    definition_id: str
    source_id: int
    vehicle_id: str | None
    attribute: str
    operation: str
    value: Fraction
    weight_kg: int

    @property
    def compact_descr(self) -> int:
        return self.source_id * 256 + 249  # optionalDevice9; NONE nation15.


DEVICES = (
    DeviceDefinition("optional_device:improvedVentilation_class1", 17, "vehicle:ms1",
                     "crewLevelIncrease", "add", Fraction(5), 100),
    DeviceDefinition("optional_device:improvedVentilation_class3", 19, "vehicle:is7",
                     "crewLevelIncrease", "add", Fraction(5), 200),
    DeviceDefinition("optional_device:enhancedAimDrives", 25, None,
                     "gunAimingTimeFactor", "multiply", Fraction(91, 100), 100),
    DeviceDefinition("optional_device:coatedOptics", 5, None,
                     "circularVisionRadiusFactor", "multiply", Fraction(11, 10), 0),
)


class ConfigurationError(ValueError):
    """Invalid, unbound or explicitly unsupported configuration."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ConfigurationError(message)


def _identifier(value, label):
    _require(type(value) is str and _ID.fullmatch(value) is not None, label + ": bounded ID required")


def _digest(value, label):
    _require(type(value) is str and _SHA.fullmatch(value) is not None, label + ": SHA256 required")


def _integer(value, label, lower, upper):
    _require(type(value) is int and lower <= value <= upper, label + ": integer outside bounds")


def _keys(value, fields, label):
    _require(type(value) is dict and set(value) == set(fields), label + ": exact fields required")


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _ratio(value: Fraction) -> dict:
    return {"numerator": value.numerator, "denominator": value.denominator}


def policy_document() -> dict:
    """Fresh copy; the versioned release contains only this closed rules subset."""
    return {
        "policy": POLICY, "target": "v.0.9.1 #717 RU", "optional_device_slots": 3,
        "crew_policy": "healthy-correctly-trained-100-no-skills-no-consumables",
        "arithmetic": "exact-source-decimal-rational; native-bit-equivalence-UNKNOWN",
        "weight_policy": "final-total-must-not-exceed-upstream-verified-max-load",
        "sources": [{"id": name, "sha256": digest} for name, digest in SOURCE_PINS],
        "vehicles": [{"id": v.definition_id, "type_compact_descr": v.type_compact_descr,
                      "tag": v.tag, "seats": v.seats} for v in VEHICLES],
        "devices": [{"id": d.definition_id, "source_id": d.source_id,
                     "compact_descr": d.compact_descr, "vehicle_id": d.vehicle_id,
                     "attribute": d.attribute, "operation": d.operation,
                     "value": _ratio(d.value), "weight_kg": d.weight_kg} for d in DEVICES],
    }


POLICY_SHA256 = hashlib.sha256(canonical(policy_document())).hexdigest()


@dataclass(frozen=True)
class MassBudget:
    """Already verified by the component/import authority, not by this module.

    Integers in grams avoid implicit float rounding. The evidence digest binds
    the upstream mass audit, including hull/chassis/engine/fuel/radio/turret/gun.
    Base mass MUST exclude optional devices. Unknown/missing mass is rejected.
    """
    component_configuration_sha256: str
    evidence_sha256: str
    base_mass_grams: int
    max_load_grams: int


@dataclass(frozen=True)
class TrustedBinding:
    """Pass from authenticated server state, never construct from candidate JSON."""
    account_id: str
    vehicle_inventory_id: str
    configuration_revision: int
    configuration_sha256: str
    component_configuration_sha256: str
    policy_sha256: str
    mass_budget: MassBudget | None = None


@dataclass(frozen=True)
class ConfigurationSnapshot:
    """Canonical bytes are immutable; decoded consumer views are fresh copies."""
    canonical_bytes: bytes

    def __post_init__(self):
        _require(type(self.canonical_bytes) is bytes, "immutable snapshot bytes required")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()

    def as_dict(self) -> dict:
        return json.loads(self.canonical_bytes)


def _read(raw: bytes) -> dict:
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES, "input: bytes outside bounds")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            _require(key not in result, "duplicate JSON key")
            result[key] = value
        return result

    def reject_number(value):
        raise ConfigurationError("floating-point/non-finite input unsupported")

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                           parse_float=reject_number, parse_constant=reject_number)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as error:
        raise ConfigurationError("input is not bounded integer UTF-8 JSON: " + str(error)) from error
    count = 0

    def bounded(item, depth):
        nonlocal count
        count += 1
        _require(depth <= MAX_DEPTH and count <= MAX_NODES, "JSON depth/node bound")
        if type(item) is dict:
            for child in item.values():
                bounded(child, depth + 1)
        elif type(item) is list:
            for child in item:
                bounded(child, depth + 1)

    bounded(value, 0)
    return value


def build_snapshot(raw: bytes, *, binding: TrustedBinding) -> ConfigurationSnapshot:
    """Validate a complete server record and freeze only proven static modifiers.

    This does not authorize battle admission. Consumers must separately verify
    reservation, current revision, mounted component identity and ammo/service
    gates. No snapshot here includes a final historical reload/view/aim value.
    """
    _require(type(binding) is TrustedBinding, "trusted server binding required")
    _identifier(binding.account_id, "binding.account_id")
    _identifier(binding.vehicle_inventory_id, "binding.vehicle_inventory_id")
    _integer(binding.configuration_revision, "binding.configuration_revision", 1, 2**63 - 1)
    _digest(binding.configuration_sha256, "binding.configuration_sha256")
    _digest(binding.component_configuration_sha256, "binding.component_configuration_sha256")
    _require(binding.policy_sha256 == POLICY_SHA256, "unsupported policy digest")
    data = _read(raw)
    _require(hashlib.sha256(raw).hexdigest() == binding.configuration_sha256, "configuration digest mismatch")
    _keys(data, ("format", "policy", "account_id", "vehicle_inventory_id", "vehicle_definition_id",
                 "configuration_revision", "component_configuration_sha256", "crew", "optional_devices"), "input")
    _require(data["format"] == FORMAT and data["policy"] == POLICY, "unsupported format/policy")
    _integer(data["configuration_revision"], "configuration_revision", 1, 2**63 - 1)
    for field in ("account_id", "vehicle_inventory_id", "configuration_revision", "component_configuration_sha256"):
        _require(data[field] == getattr(binding, field), "binding mismatch: " + field)
    _identifier(data["vehicle_definition_id"], "vehicle_definition_id")
    vehicle = next((v for v in VEHICLES if v.definition_id == data["vehicle_definition_id"]), None)
    _require(vehicle is not None, "unsupported vehicle")

    crew = data["crew"]
    _require(type(crew) is list and len(crew) == len(vehicle.seats), "complete crew required")
    seen_ids, seen_seats = set(), set()
    crew_rows = []
    for row in crew:
        _keys(row, ("crew_id", "seat", "role", "role_level", "trained_vehicle_definition_id",
                    "vehicle_inventory_id", "healthy", "skills"), "crew")
        _identifier(row["crew_id"], "crew_id")
        _integer(row["seat"], "seat", 0, len(vehicle.seats) - 1)
        _require(row["crew_id"] not in seen_ids and row["seat"] not in seen_seats, "duplicate crew/seat")
        seen_ids.add(row["crew_id"])
        seen_seats.add(row["seat"])
        roles = vehicle.seats[row["seat"]]
        _require(row["role"] == roles[0], "crew primary role mismatch")
        _require(row["vehicle_inventory_id"] == binding.vehicle_inventory_id, "foreign crew assignment")
        _require(row["trained_vehicle_definition_id"] == vehicle.definition_id, "unsupported crew retraining")
        _integer(row["role_level"], "role_level", 100, 100)
        _require(row["healthy"] is True, "injured crew unsupported")
        _require(type(row["skills"]) is list and not row["skills"], "crew skills unsupported")
        crew_rows.append({"crew_id": row["crew_id"], "seat": row["seat"], "roles": roles,
                          "base_role_level": 100})
    crew_rows.sort(key=lambda row: row["seat"])

    slots = data["optional_devices"]
    _require(type(slots) is list and len(slots) == 3, "exactly three optional-device slots required")
    installed, operations, seen_devices = [], [], set()
    attributes = {"crewLevelIncrease": Fraction(0), "gunAimingTimeFactor": Fraction(1),
                  "circularVisionRadiusFactor": Fraction(1)}
    added_mass_grams = 0
    for slot, device_id in enumerate(slots):
        if device_id is None:
            installed.append(None)
            continue
        _identifier(device_id, "optional_device")
        device = next((d for d in DEVICES if d.definition_id == device_id), None)
        _require(device is not None, "unsupported optional device")
        _require(device_id not in seen_devices, "duplicate optional device")
        seen_devices.add(device_id)
        _require(device.vehicle_id is None or device.vehicle_id == vehicle.definition_id,
                 "incompatible optional device")
        old = attributes[device.attribute]
        attributes[device.attribute] = old + device.value if device.operation == "add" else old * device.value
        added_mass_grams += device.weight_kg * 1000
        installed.append({"definition_id": device_id, "source_id": device.source_id,
                          "compact_descr": device.compact_descr, "weight_grams": device.weight_kg * 1000})
        operations.append({"slot": slot, "definition_id": device_id, "attribute": device.attribute,
                           "operation": device.operation, "operand": _ratio(device.value),
                           "before": _ratio(old), "after": _ratio(attributes[device.attribute])})

    mass = binding.mass_budget
    _require(not seen_devices or mass is not None, "installed devices require an upstream verified mass budget")
    mass_result = None
    if mass is not None:
        _require(type(mass) is MassBudget, "typed mass budget required")
        _digest(mass.evidence_sha256, "mass.evidence_sha256")
        _require(mass.component_configuration_sha256 == binding.component_configuration_sha256,
                 "mass budget component binding mismatch")
        _integer(mass.base_mass_grams, "mass.base_mass_grams", 1, 1_000_000_000)
        _integer(mass.max_load_grams, "mass.max_load_grams", 1, 1_000_000_000)
        total = mass.base_mass_grams + added_mass_grams
        _require(total <= mass.max_load_grams, "equipment exceeds maximum load")
        mass_result = {"source": "trusted-component-authority", "evidence_sha256": mass.evidence_sha256,
                       "base_mass_grams": mass.base_mass_grams, "max_load_grams": mass.max_load_grams,
                       "optional_device_mass_grams": added_mass_grams, "total_mass_grams": total}

    payload = {
        "format": SNAPSHOT_FORMAT, "policy": POLICY, "policy_sha256": POLICY_SHA256,
        "classification": "VERIFIED", "verification_scope": "static-rules-and-isolated-domain-validation",
        "runtime_ready": False, "runtime_acceptance": "NOT_RUN",
        "account_id": binding.account_id, "vehicle_inventory_id": binding.vehicle_inventory_id,
        "vehicle_definition_id": vehicle.definition_id, "vehicle_type_compact_descr": vehicle.type_compact_descr,
        "configuration_revision": binding.configuration_revision,
        "configuration_sha256": binding.configuration_sha256,
        "component_configuration_sha256": binding.component_configuration_sha256,
        "crew": crew_rows, "optional_devices": installed, "operations_in_slot_order": operations,
        "static_modifiers": {key: _ratio(value) for key, value in sorted(attributes.items())},
        "mass_check": mass_result, "sources": policy_document()["sources"],
        "unknown": ["crew-to-battle-characteristic-formula", "native-floating-point-bit-equivalence",
                    "final-reload-aim-vision-characteristics", "runtime-and-native-integration"],
        "unsupported": ["perks", "training", "injuries", "consumables", "other-optional-devices",
                        "economy", "inventory-grants", "battle-admission"],
    }
    return ConfigurationSnapshot(canonical(payload))
