"""Closed #717 stock identity registry; new profiles are never battle-admitted.

Inventory identity is owner-scoped and independent of source vehicle type.
This module validates facts/candidate DTO shape, not crew/ammo ownership.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from types import MappingProxyType

from game_profile_tx import TransactionError
from p09d_ammo_projection import canonical
from p09d_ammo_store import sha, require
from p09e_research_projection import descriptor
from p04m_battle_profiles import SPECS, CATALOG_SHA256

SCHEMA = "p04m-curated-stock-pool.v1"
ROLES = ("chassis", "engine", "fuelTank", "radio", "turret", "gun")
NEW_KINDS = frozenset(("t26", "t34", "t3485"))
PINS = {
    "ms1": ("MS-1", 3329, "010d1a000e00c90000001700170000", 90, 96, 2570,
        (("commander", "gunner", "radioman", "loader"), ("driver",))),
    "is7": ("IS-7", 7169, "011c3a002400cd000b002f003a0000", 2150, 30, 14602,
        (("commander",), ("gunner",), ("driver",), ("loader",), ("loader", "radioman"))),
}
for _kind in sorted(NEW_KINDS):
    _spec = SPECS[_kind + "-stock"]
    PINS[_kind] = (_spec["resource"], _spec["type_cd"], _spec["descriptor"],
        _spec["max_hp"], _spec["capacity"], _spec["shell_cd"], _spec["crew"])
PINS = MappingProxyType(PINS)
DEFINITION_SHA256 = sha(canonical({"schema": SCHEMA, "catalog_sha256": CATALOG_SHA256,
    "stock": dict(PINS), "new_source_specs": {kind: SPECS[kind + "-stock"] for kind in sorted(NEW_KINDS)}}))
POLICY = {"id": "test_lab.p04m-stock-identity-only.v1", "definition_sha256": DEFINITION_SHA256,
    "new_battle_admission": False, "owner_acceptance": "REQUIRED", "crew_ammo_extension": "NOT_ACTIVE",
    "grants": "NONE", "legacy_battle_policy": "UNCHANGED"}
POLICY_SHA256 = sha(canonical(POLICY))


# CAT-01: with an active catalog (worker ``--catalog-sha256``) identity and
# admission come from data; the closed lists above remain the default and every
# kind present in both must agree exactly. Policy/definition hashes stay legacy.
def _catalog():
    import catalog_v1
    return catalog_v1 if catalog_v1.active() else None


def active_pins():
    c = _catalog()
    if c is None:
        return PINS
    pins = c.stock_pins()
    require(all(pins[kind] == PINS[kind] for kind in set(pins) & set(PINS)), "CAT01_CATALOG_DISAGREES")
    return MappingProxyType(pins)


def mixed_admission(kind, zero_economy):
    """Owned mixed battle admission: legacy NEW_KINDS rule or the catalog field."""
    c = _catalog()
    if c is None:
        return kind not in NEW_KINDS or zero_economy()
    value = c.admission(kind)
    return value == "always" or (value == "zero_economy_policy" and zero_economy())


def legacy_route_admitted(kind):
    """Version1 P08B route: only kinds admitted without any policy."""
    c = _catalog()
    return kind not in NEW_KINDS if c is None else c.admission(kind) == "always"


@dataclass(frozen=True)
class StockProfile:
    kind: str
    vehicle_id: str
    type_compact_id: int
    descriptor_hex: str
    max_hp: int
    capacity: int
    shell_compact_id: int
    modules: tuple[tuple[str, str], ...]
    crew_roles: tuple[tuple[str, ...], ...]

    @property
    def assembly_id(self): return self.kind + "-stock"

    @property
    def shell_definition_id(self): return "shell:" + self.assembly_id + "-ap"

    @property
    def primary_roles(self): return tuple(roles[0] for roles in self.crew_roles)


class StockRegistry:
    def __init__(self, catalog):
        require(catalog.sha256 == CATALOG_SHA256, "P04M_CATALOG_MISMATCH")
        self.catalog = catalog
        profiles = {}
        for kind, (resource, cd, encoded, hp, capacity, shell, crew) in active_pins().items():
            c = _catalog()
            # Catalog rows carry their own vehicle ID (BATTLE-ANY adds other nations).
            key = "vehicle:ussr:" + resource if c is None else c.by_kind(kind)["vehicle_id"]
            row = catalog.vehicles.get(key)
            require(row is not None and row["native_compact_id"] == cd, "P04M_DEFINITION_MISMATCH")
            modules = row["defaults"]
            require(set(modules) == set(ROLES) and descriptor(catalog, {"vehicle_id": key, "modules": modules}).hex() == encoded
                and row["hull_max_hp"] + row["turret_max_hp"][modules["turret"]] == hp
                and tuple(map(tuple, row["crew_roles"])) == crew, "P04M_DEFINITION_MISMATCH")
            if kind + "-stock" in SPECS:
                spec = SPECS[kind + "-stock"]
                require(tuple(catalog.modules[modules[role]]["native_compact_id"] for role in ROLES) == spec["module_cds"], "P04M_DEFINITION_MISMATCH")
            profiles[kind] = StockProfile(kind, key, cd, encoded, hp, capacity, shell,
                tuple((role, modules[role]) for role in ROLES), crew)
        self.profiles = MappingProxyType(profiles)
        self.by_vehicle = MappingProxyType({p.vehicle_id: p for p in profiles.values()})
        # The registry hash the gateway pins covers the legacy kinds only; generated
        # (BATTLE-ANY) kinds are bound by the activated catalog hash instead.
        self.sha256 = sha(canonical({"schema": SCHEMA, "definition_sha256": DEFINITION_SHA256,
            "profiles": [asdict(profiles[kind]) for kind in sorted(profiles) if kind in PINS]}))

    @staticmethod
    def inventory_id(account, native, kind):
        from p08b_battle_store import _uuid, _integer
        _uuid(account); _integer(native, 1)
        c = _catalog()
        if c is not None:
            legacy = {row["legacy_inventory"]["native_inventory_id"]: (row["kind"], row["legacy_inventory"]["suffix"])
                      for row in c.vehicles() if row["legacy_inventory"] is not None}
            if native in legacy:
                require(kind == legacy[native][0], "P04M_INVENTORY_MISMATCH")
                return account + ":" + legacy[native][1]
            require(kind not in {k for k, _ in legacy.values()}, "P04M_INVENTORY_MISMATCH")
            return account + ":p09e-vehicle:" + str(native)
        if native == 1:
            require(kind == "ms1", "P04M_INVENTORY_MISMATCH")
            return account + ":starter-vehicle-v1"
        if native == 2:
            require(kind == "is7", "P04M_INVENTORY_MISMATCH")
            return account + ":test-is7-v1"
        require(kind not in ("ms1", "is7"), "P04M_INVENTORY_MISMATCH")
        return account + ":p09e-vehicle:" + str(native)

    def resolve_owned(self, account, owned):
        profile = self.by_vehicle.get(owned["vehicle_id"])
        require(profile is not None, "BATTLE_PROFILE_UNSUPPORTED")
        require(owned["vehicle_inventory_id"] == self.inventory_id(account, owned["native_id"], profile.kind), "P04M_INVENTORY_MISMATCH")
        require(owned["modules"] == dict(profile.modules)
            and descriptor(self.catalog, owned).hex() == profile.descriptor_hex, "BATTLE_PROFILE_UNSUPPORTED")
        return profile

    def resolve_selected(self, aggregate, account, native):
        from p08b_battle_store import _integer
        require(aggregate["account_id"] == account, "FOREIGN_ACCOUNT"); _integer(native, 1)
        rows = [r for r in aggregate["research"]["vehicles"] if r["native_id"] == native]
        require(len(rows) == 1, "UNKNOWN_VEHICLE")
        owned = rows[0]
        require(sum(row["vehicle_id"] == owned["vehicle_inventory_id"] for row in aggregate["vehicles"]) == 1, "CORRUPT_STORE")
        return self.resolve_owned(account, owned)

    def validate_frozen_candidate(self, frozen, account):
        """Closed DTO shape only; never an admission or owned-inventory proof."""
        from p08b_battle_store import _integer
        require(type(frozen) is dict and set(frozen) == {"kind", "descriptor_hex", "native_inventory_id",
            "vehicle_inventory_id", "ap_count", "shell_definition_id", "shell_compact_id", "max_hp", "crew_ids"}, "INVALID_INPUT")
        require(type(frozen["kind"]) is str and frozen["kind"] in self.profiles, "BATTLE_PROFILE_UNSUPPORTED")
        p = self.profiles[frozen["kind"]]
        require(frozen["vehicle_inventory_id"] == self.inventory_id(account, frozen["native_inventory_id"], p.kind), "P04M_INVENTORY_MISMATCH")
        _integer(frozen["ap_count"], 1, p.capacity)
        require(frozen["descriptor_hex"] == p.descriptor_hex and type(frozen["max_hp"]) is int and frozen["max_hp"] == p.max_hp
            and type(frozen["shell_compact_id"]) is int and frozen["shell_compact_id"] == p.shell_compact_id
            and frozen["shell_definition_id"] == p.shell_definition_id, "BATTLE_PROFILE_UNSUPPORTED")
        crew = frozen["crew_ids"]
        require(type(crew) is list and len(crew) == len(p.crew_roles)
            and all(type(i) is str and i.isascii() and len(account) + 1 < len(i) <= 96 and i.startswith(account + ":") for i in crew)
            and len(set(crew)) == len(crew), "INCOMPLETE_CREW")
        return p

    def capabilities(self, aggregate):
        from p08b_battle_store import freeze_loadout
        result = []
        for owned in aggregate["research"]["vehicles"]:
            entry = {"native_inventory_id": owned["native_id"], "vehicle_inventory_id": owned["vehicle_inventory_id"],
                "kind": None, "assembly_id": None, "readiness_code": "BATTLE_PROFILE_UNSUPPORTED", "admission": False}
            try:
                known = self.by_vehicle.get(owned["vehicle_id"])
                if known is not None:
                    require(owned["vehicle_inventory_id"] == self.inventory_id(aggregate["account_id"], owned["native_id"], known.kind), "P04M_INVENTORY_MISMATCH")
                    # Primary seats belong to the owned type even when its
                    # installed modules do not form the curated stock assembly.
                    entry["kind"] = known.kind
                p = self.resolve_owned(aggregate["account_id"], owned)
                entry.update(kind=p.kind, assembly_id=p.assembly_id)
                if not legacy_route_admitted(p.kind):
                    entry["readiness_code"] = "OWNER_ACCEPTANCE_REQUIRED"
                else:
                    freeze_loadout(self.catalog, aggregate, owned["native_id"])
                    entry.update(readiness_code=None, admission=True)
            except TransactionError as error:
                if error.code not in ("BATTLE_PROFILE_UNSUPPORTED", "INCOMPLETE_CREW", "AMMUNITION_EMPTY", "AMMUNITION_UNSUPPORTED", "VEHICLE_RESERVED"):
                    raise
                entry["readiness_code"] = error.code
            result.append(entry)
        return result
