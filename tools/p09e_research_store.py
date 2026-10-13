"""Opt-in historical research on the accepted P04G account/transaction owner.

This writer extends the SAME game.sqlite, game_vehicle and command ledger.
It does not create accounts or activate itself in the bridge. New configurations
are garage-only until their complete runtime profile is separately accepted.
"""
from __future__ import annotations

from copy import deepcopy
import json
import re
import struct

from game_profile_tx import TransactionError, _bounded_id, _revision, _decode_object
from p04g_crew_store import NativeCrossVehicleCrewStore
from p09d_ammo_store import NativeAmmoStore, require, sha, REQUEST_FIELDS as AMMO_REQUEST_FIELDS
from p09d_ammo_projection import canonical, update_delta
from p09c_ammo_catalog import SHELLS

SCHEMA = "p09e-tank-module-research.v1"
JOURNAL_SCHEMA = "p09e-research-journal.v2"
POLICY = {"id": "test_lab.research.free-credit-xp.v1", "mode": "test_lab",
          "xp": 0, "credits": 0, "gold": "UNSUPPORTED",
          "battle_admission": False, "initial_research": "retained-source-unlocks-plus-visible-credit-tier1-roots.v1"}
POLICY_SHA256 = sha(canonical(POLICY))
MAX_STATE = 256 * 1024
MAX_NATIVE_RESPONSE = 4096
MAX_NATIVE_CONTEXT = 16 * 1024
MAX_OWNED = 256
MAX_ITEMS = 8192
MAX_QUANTITY = 1000000
ROLES = frozenset(("chassis", "engine", "fuelTank", "radio", "turret", "gun"))
REQUEST_FIELDS = {"account_id", "command_key", "expected_revision", "operation", "payload"}


def _json(raw):
    require(type(raw) is str and len(raw) <= MAX_STATE, "CORRUPT_STORE")
    # Bound depth BEFORE parsing, including malicious on-disk JSON.
    depth, quoted, escaped = 0, False, False
    for char in raw:
        if quoted:
            if escaped: escaped = False
            elif char == "\\": escaped = True
            elif char == '"': quoted = False
        elif char == '"': quoted = True
        elif char in "[{":
            depth += 1
            require(depth <= 12, "CORRUPT_STORE")
        elif char in "]}": depth -= 1
    # Existing P09B decoder rejects duplicate fields and non-finite numbers.
    return _decode_object(raw, "P09E")


def _encode(value):
    raw = canonical(value)
    require(len(raw) <= MAX_STATE, "PROFILE_TOO_LARGE")
    return raw.decode("ascii")


def _number(value, lower=0, upper=2**31 - 1):
    require(type(value) is int and lower <= value <= upper)
    return value


def _identity(value):
    return _bounded_id(value, "item_id")


def validate_request(request, authenticated_account_id):
    _bounded_id(authenticated_account_id, "authenticated_account_id")
    require(type(request) is dict and set(request) == REQUEST_FIELDS)
    _bounded_id(request["account_id"], "account_id")
    require(request["account_id"] == authenticated_account_id, "FOREIGN_ACCOUNT")
    _bounded_id(request["command_key"], "command_key")
    _revision(request["expected_revision"])
    operation, payload = request["operation"], request["payload"]
    require(type(operation) is str and type(payload) is dict)
    if operation == "research":
        require(set(payload) == {"vehicle_id", "unlock_index"})
        _identity(payload["vehicle_id"]); _number(payload["unlock_index"], 0, 4095)
    elif operation == "buy_vehicle":
        require(set(payload) == {"vehicle_id"}); _identity(payload["vehicle_id"])
    elif operation == "buy_module":
        require(set(payload) == {"module_id", "count"})
        _identity(payload["module_id"]); _number(payload["count"], 1, 100)
    elif operation in ("install", "buy_equip"):
        require(set(payload) == {"vehicle_inventory_id", "modules"})
        _identity(payload["vehicle_inventory_id"])
        require(type(payload["modules"]) is list and 1 <= len(payload["modules"]) <= 6)
        for item in payload["modules"]: _identity(item)
        require(len(set(payload["modules"])) == len(payload["modules"]))
    else:
        raise TransactionError("UNSUPPORTED_OPERATION")
    require(len(canonical(request)) <= 4096)
    return deepcopy(request)


def assembly(catalog, vehicle_id, modules):
    """Source-bound compatibility and full dry mass; no battle-readiness claim."""
    require(vehicle_id in catalog.vehicles, "UNKNOWN_VEHICLE_TYPE")
    vehicle = catalog.vehicles[vehicle_id]
    require(not vehicle.get("unsupported_reason"), "UNSUPPORTED_CONFIGURATION")
    require(type(modules) is dict and set(modules) == ROLES, "INCOMPLETE_CONFIGURATION")
    for role, item in modules.items():
        require(item in catalog.modules and catalog.modules[item]["kind"] == role
                and item in vehicle["compatible"][role], "INCOMPATIBLE_MODULE")
    require(modules["turret"] in vehicle["gun_turrets"].get(modules["gun"], ()), "INCOMPATIBLE_TURRET_GUN")
    mass = vehicle["hull_mass_grams"]
    require(type(mass) is int and mass >= 0, "SOURCE_MASS_UNKNOWN")
    for item in modules.values():
        value = vehicle.get("module_mass_grams", {}).get(item, catalog.modules[item]["mass_grams"])
        require(type(value) is int and value >= 0, "SOURCE_MASS_UNKNOWN")
        mass += value
    maximum = vehicle.get("module_max_load_grams", {}).get(modules["chassis"], catalog.modules[modules["chassis"]]["max_load_grams"])
    require(type(maximum) is int and maximum > 0, "SOURCE_LOAD_UNKNOWN")
    require(mass <= maximum, "CHASSIS_OVERLOAD")
    return {"mass_grams": mass, "max_load_grams": maximum, "battle_admission": False}


def _price(record):
    price = record["historical_price"]
    require(type(price) is dict and set(price) == {"amount", "currency"}
            and type(price["amount"]) is int and price["amount"] >= 0, "SOURCE_PRICE_UNKNOWN")
    require(price["currency"] == "credits", "GOLD_PURCHASE_UNSUPPORTED")
    return deepcopy(price)


def _available_type(vehicle):
    require(not vehicle.get("unsupported_reason"), "UNSUPPORTED_CONFIGURATION")
    # Imported catalogue determines visibility/acquisition rather than guessed
    # names or current Tankopedia data. Missing proof remains unavailable.
    require(vehicle.get("acquisition_allowed") is True, "VEHICLE_ACQUISITION_UNSUPPORTED")


def _default_unlocks(catalog, vehicle_id):
    vehicle = catalog.vehicles[vehicle_id]
    values = set(vehicle.get("default_unlocks", ())) | set(vehicle["defaults"].values())
    require(values <= (set(catalog.modules) | set(catalog.vehicles)), "CORRUPT_CATALOG")
    return values


def plan(catalog, state, operation, payload, *, account_id, reserved=(), loaded=()):
    """Pure bounded transition, also re-executed when replaying the journal."""
    value = deepcopy(state)
    unlocked, depot = set(value["unlocked"]), value["depot"]
    details = {}
    if operation == "research":
        vehicle_id = payload["vehicle_id"]
        require(vehicle_id in catalog.vehicles, "UNKNOWN_VEHICLE_TYPE")
        require(vehicle_id in unlocked, "VEHICLE_NOT_RESEARCHED")
        edges = [r for r in catalog.unlocks if r["vehicle_id"] == vehicle_id and r["native_index"] == payload["unlock_index"]]
        require(len(edges) == 1, "UNKNOWN_UNLOCK")
        edge = edges[0]
        require(set(edge["prerequisite_ids"]) <= unlocked, "MISSING_PREREQUISITE")
        item = edge["item_id"]
        if item in catalog.vehicles: _available_type(catalog.vehicles[item])
        require(item not in unlocked, "ALREADY_RESEARCHED")
        unlocked.add(item)
        if item in catalog.vehicles: unlocked.update(_default_unlocks(catalog, item))
        details = {"item_id": item, "historical_xp": edge["historical_xp"]}
    elif operation == "buy_vehicle":
        vehicle_id = payload["vehicle_id"]
        require(vehicle_id in catalog.vehicles, "UNKNOWN_VEHICLE_TYPE")
        vehicle = catalog.vehicles[vehicle_id]
        price = _price(vehicle)
        _available_type(vehicle)
        require(vehicle_id in unlocked, "VEHICLE_NOT_RESEARCHED")
        require(not any(r["vehicle_id"] == vehicle_id for r in value["vehicles"]), "VEHICLE_ALREADY_OWNED")
        require(len(value["vehicles"]) < min(MAX_OWNED, value["garage_slots"]), "GARAGE_LIMIT")
        native = value["next_native_id"]
        require(type(native) is int and 1 <= native < 2**31 - 1, "INVENTORY_ID_EXHAUSTED")
        inventory_id = account_id + ":p09e-vehicle:" + str(native)
        _identity(inventory_id)
        modules = deepcopy(vehicle["defaults"])
        assembly(catalog, vehicle_id, modules)
        value["vehicles"].append({"vehicle_inventory_id": inventory_id, "native_id": native,
                                  "vehicle_id": vehicle_id, "modules": modules, "runtime_supported": False})
        value["next_native_id"] += 1
        details = {"vehicle_inventory_id": inventory_id, "historical_price": price}
    elif operation == "buy_module":
        item, count = payload["module_id"], payload["count"]
        require(item in catalog.modules, "UNKNOWN_MODULE")
        require(catalog.modules[item]["kind"] != "fuelTank", "INTERNAL_COMPONENT_UNSUPPORTED")
        require(item in unlocked, "MODULE_NOT_RESEARCHED")
        price = _price(catalog.modules[item])
        require(depot.get(item, 0) + count <= MAX_QUANTITY, "DEPOT_OVERFLOW")
        depot[item] = depot.get(item, 0) + count
        details = {"module_id": item, "count": count, "historical_price": price}
    elif operation in ("install", "buy_equip"):
        inventory_id = payload["vehicle_inventory_id"]
        owned = next((r for r in value["vehicles"] if r["vehicle_inventory_id"] == inventory_id), None)
        require(owned is not None, "UNKNOWN_VEHICLE")
        require(inventory_id not in reserved, "VEHICLE_RESERVED")
        installed = dict(owned["modules"])
        seen = set()
        for item in payload["modules"]:
            require(item in catalog.modules, "UNKNOWN_MODULE")
            role = catalog.modules[item]["kind"]
            require(role != "fuelTank", "INTERNAL_COMPONENT_UNSUPPORTED")
            require(role not in seen, "DUPLICATE_MODULE_SLOT")
            seen.add(role)
            installed[role] = item
        metrics = assembly(catalog, owned["vehicle_id"], installed)
        changes = {role: item for role, item in installed.items() if item != owned["modules"][role]}
        require(changes, "NO_CONFIGURATION_CHANGE")
        require(not (set(changes) & {"turret", "gun"} and inventory_id in loaded), "UNLOAD_AMMUNITION_REQUIRED")
        bought = []
        for role, item in changes.items():
            if depot.get(item, 0) < 1 and operation == "buy_equip":
                require(item in unlocked, "MODULE_NOT_RESEARCHED")
                bought.append({"module_id": item, "historical_price": _price(catalog.modules[item])})
                depot[item] = 1
            require(depot.get(item, 0) >= 1, "MODULE_NOT_OWNED")
            depot[item] -= 1
            old = owned["modules"][role]
            require(depot.get(old, 0) < MAX_QUANTITY, "DEPOT_OVERFLOW")
            depot[old] = depot.get(old, 0) + 1
        owned["modules"] = installed
        owned["runtime_supported"] = False
        details = {"vehicle_inventory_id": inventory_id, "modules": changes, "purchased": bought, **metrics}
    else:
        raise TransactionError("UNSUPPORTED_OPERATION")
    value["unlocked"] = sorted(unlocked)
    value["depot"] = {key: count for key, count in sorted(depot.items()) if count}
    value["vehicles"].sort(key=lambda row: row["native_id"])
    require(len(value["unlocked"]) <= MAX_ITEMS and len(value["depot"]) <= MAX_ITEMS, "INVENTORY_LIMIT")
    return value, details


class ResearchStore(NativeCrossVehicleCrewStore):
    """Explicit migration plus one writer for research, crew and old stock ammo."""

    def __init__(self, path, catalog, *, failpoint=None):
        super().__init__(path, failpoint=failpoint)
        self.catalog = catalog
        self._allow_preresearch = False

    def _contract(self):
        # Crew policy remains the accepted P04G contract, never the research
        # schema nor this subclass's independent native projection.
        return NativeCrossVehicleCrewStore

    def _research_schema(self):
        return self.connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='p09e_schema'").fetchone() is not None

    def initialize(self):
        super().initialize()
        require(self._research_schema() or self._allow_preresearch, "P09E_MIGRATION_REQUIRED")
        if self._research_schema():
            row = self.connection.execute("SELECT version,catalog_sha256,policy_sha256 FROM p09e_schema").fetchall()
            require([tuple(r) for r in row] == [(SCHEMA, self.catalog.sha256, POLICY_SHA256)], "UNSUPPORTED_RESEARCH_SCHEMA")

    def _base_ids(self, account):
        return {r["inventory_id"] for r in _json(self._import(account)["base_json"])["inventory"]}

    def _research(self, account):
        row = self.connection.execute("SELECT * FROM p09e_research WHERE account_id=?", (account,)).fetchone()
        require(row is not None, "P09E_ACCOUNT_MIGRATION_REQUIRED")
        require(type(row["base_revision"]) is int and row["base_revision"] >= 9
                and type(row["base_profile_sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", row["base_profile_sha256"]), "CORRUPT_STORE")
        state = _json(row["state_json"])
        require(sha(row["state_json"].encode("ascii")) == row["state_sha256"], "CORRUPT_STORE")
        require(set(state) == {"schema", "policy", "catalog_sha256", "unlocked", "depot", "vehicles", "next_native_id", "garage_slots"}
                and state["schema"] == SCHEMA and state["policy"] == POLICY
                and state["catalog_sha256"] == self.catalog.sha256, "CORRUPT_STORE")
        require(type(state["unlocked"]) is list and len(state["unlocked"]) <= MAX_ITEMS
                and all(type(x) is str for x in state["unlocked"])
                and state["unlocked"] == sorted(set(state["unlocked"]))
                and set(state["unlocked"]) <= set(self.catalog.vehicles) | set(self.catalog.modules), "CORRUPT_STORE")
        require(type(state["depot"]) is dict and len(state["depot"]) <= MAX_ITEMS
                and all(k in self.catalog.modules and type(v) is int and 1 <= v <= MAX_QUANTITY for k, v in state["depot"].items()), "CORRUPT_STORE")
        require(type(state["vehicles"]) is list and 2 <= len(state["vehicles"]) <= MAX_OWNED, "CORRUPT_STORE")
        require(type(state["garage_slots"]) is int and len(state["vehicles"]) <= state["garage_slots"] <= MAX_OWNED, "CORRUPT_STORE")
        seen_id, seen_type, seen_native = set(), set(), set()
        for item in state["vehicles"]:
            require(type(item) is dict and set(item) == {"vehicle_inventory_id", "native_id", "vehicle_id", "modules", "runtime_supported"}, "CORRUPT_STORE")
            _identity(item["vehicle_inventory_id"]); _number(item["native_id"], 1)
            require(item["vehicle_inventory_id"] not in seen_id and item["vehicle_id"] not in seen_type
                    and item["native_id"] not in seen_native and item["runtime_supported"] is False
                    and item["vehicle_id"] in state["unlocked"], "CORRUPT_STORE")
            assembly(self.catalog, item["vehicle_id"], item["modules"])
            if item["native_id"] > 2:
                require(item["vehicle_inventory_id"] == account + ":p09e-vehicle:" + str(item["native_id"]), "CORRUPT_STORE")
            else:
                require(self.catalog.vehicles[item["vehicle_id"]]["native_compact_id"] == (3329 if item["native_id"] == 1 else 7169), "CORRUPT_STORE")
            seen_id.add(item["vehicle_inventory_id"]); seen_type.add(item["vehicle_id"]); seen_native.add(item["native_id"])
        require(type(state["next_native_id"]) is int and max(seen_native) < state["next_native_id"] <= 2**31 - 1, "CORRUPT_STORE")
        require(state["vehicles"] == sorted(state["vehicles"], key=lambda r: r["native_id"]), "CORRUPT_STORE")
        require({r["vehicle_inventory_id"] for r in state["vehicles"][:2]} == self._base_ids(account)
                and [r["native_id"] for r in state["vehicles"][:2]] == [1, 2], "CORRUPT_STORE")
        return state

    def _snapshot(self, account, revision, vehicles):
        if not self._research_schema():
            return super()._snapshot(account, revision, vehicles)
        rows = list(vehicles)
        require(2 <= len(rows) <= MAX_OWNED, "CORRUPT_STORE")
        base_ids = self._base_ids(account)
        raw, _ = super()._snapshot(account, revision, [r for r in rows if r[0] in base_ids])
        value = _json(raw)
        research = self._research(account)
        require({r[0] for r in rows} == {r["vehicle_inventory_id"] for r in research["vehicles"]}, "CORRUPT_STORE")
        value["vehicles"] = [{"vehicle_id": vehicle, "state": state, "battle_id": battle} for vehicle, state, battle in sorted(rows)]
        value["research"] = research
        raw = _encode(value)
        return raw, sha(raw.encode("ascii"))

    def _project_profile(self, account, aggregate):
        value = super()._project_profile(account, aggregate)
        if "research" not in aggregate: return value
        state = aggregate["research"]
        # Original two entries retain their IDs/crew/ammo; all new vehicles are
        # actual inventory entries with no manufactured crew or ammunition.
        by_id = {r["inventory_id"]: r for r in value["inventory"]}
        for item in state["vehicles"]:
            entry = by_id.get(item["vehicle_inventory_id"])
            if entry is None:
                entry = {"inventory_id": item["vehicle_inventory_id"], "vehicle_definition_id": item["vehicle_id"],
                         "crew_assigned": False, "ammunition_count": 0, "vehicle_xp": 0}
                value["inventory"].append(entry)
            vehicle = self.catalog.vehicles[item["vehicle_id"]]
            entry["health"] = vehicle["hull_max_hp"] + vehicle["turret_max_hp"][item["modules"]["turret"]]
            entry.update(research_vehicle_id=item["vehicle_id"], modules=deepcopy(item["modules"]), battle_admission=False)
        # The complete graph/depot projection belongs to game_snapshot. Keep
        # game_profiles bounded for the accepted crew writer's 16 KiB reader.
        value.update(profile_version=9, research={key: deepcopy(state[key]) for key in
                     ("schema", "policy", "catalog_sha256", "garage_slots")})
        value["research"].update(unlocked_count=len(state["unlocked"]), depot_types=len(state["depot"]))
        _encode(value)
        return value

    def _verified_snapshot(self, row, account):
        if not self._research_schema(): return super()._verified_snapshot(row, account)
        self.initialize()
        revision = _revision(row["revision"])
        rows = self.connection.execute("SELECT vehicle_id,state,battle_id FROM game_vehicle WHERE account_id=? ORDER BY vehicle_id LIMIT ?", (account, MAX_OWNED + 1)).fetchall()
        raw, digest = self._snapshot(account, revision, [tuple(r) for r in rows])
        require(row["snapshot_json"] == raw and row["snapshot_sha256"] == digest, "CORRUPT_STORE")
        aggregate = _json(raw)
        expected = self._project_profile(account, aggregate)
        public = self.connection.execute("SELECT native_id,profile_json FROM game_profiles WHERE account_id=?", (account,)).fetchone()
        require(public is not None and public["native_id"] == expected["native_database_id"]
                and _json(public["profile_json"]) == expected, "CORRUPT_STORE")
        layouts = self.layouts(account)
        for ammo in aggregate["ammunition"]:
            native = 1 if ammo["mount_id"] == "ms1-stock" else 2
            require({abs(layouts[native][i]): layouts[native][i + 1] for i in (0, 2, 4)}
                    == {SHELLS[key].native_compact_id: count for key, count in ammo["loaded"].items()}, "CORRUPT_STORE")
        return aggregate

    def _save_aggregate(self, account, revision):
        rows = self.connection.execute("SELECT vehicle_id,state,battle_id FROM game_vehicle WHERE account_id=? ORDER BY vehicle_id LIMIT ?", (account, MAX_OWNED + 1)).fetchall()
        raw, digest = self._snapshot(account, revision, [tuple(r) for r in rows])
        require(self.connection.execute("UPDATE game_snapshot SET revision=?,snapshot_json=?,snapshot_sha256=? WHERE account_id=?", (revision, raw, digest, account)).rowcount == 1, "UNKNOWN_ACCOUNT")
        return _json(raw)

    def _save_crew_projection(self, account, revision, before):
        aggregate = self._save_aggregate(account, revision)
        self._failpoint("after_snapshot_update")
        raw = _encode(self._project_profile(account, aggregate))
        require(self.connection.execute("UPDATE game_profiles SET profile_json=? WHERE account_id=? AND profile_json=?", (raw, account, before)).rowcount == 1, "STALE_PROFILE")
        self._failpoint("after_profile_projection")

    def _save_snapshot(self, account, revision):
        # P09C invokes this hook inside its existing ammo transaction. Avoid its
        # 16-vehicle query bound without changing the accepted two ammo mounts.
        request = self._native_request
        require(request is not None, "UNSUPPORTED_WRITER")
        before = self.connection.execute("SELECT profile_json FROM game_profiles WHERE account_id=?", (account,)).fetchone()[0]
        native, layout = request["layout"][1], request["layout"][3:9]
        self.connection.execute("UPDATE p09d_native_layout SET layout_json=? WHERE account_id=? AND native_vehicle_id=?", (json.dumps(layout), account, native))
        self._save_crew_projection(account, revision, before)
        aggregate = self.read_profile(account)
        response = dict(status="serviced", account_id=account, native_database_id=request["native_database_id"], command_key=request["command_key"], revision=revision,
                        wire_revision=request["wire_revision"] + 1, update_hex=update_delta(native, layout, aggregate["depot"], request["wire_revision"]).hex(), replayed=False, result_code=0)
        raw = canonical(response)
        self.connection.execute("INSERT INTO p09d_native_command VALUES (?,?,?,?,?)", (account, request["command_key"], sha(canonical(request)), raw.decode("ascii"), sha(raw)))

    def service(self, request, *, authenticated_account_id):
        # P09C mounts bind the exact turret/gun shell set and capacity. Other
        # compatible source modules do not change that ammunition contract.
        require(type(request) is dict and set(request) == AMMO_REQUEST_FIELDS and type(request.get("layout")) is list and len(request["layout"]) == 16)
        require(request.get("account_id") == authenticated_account_id, "FOREIGN_ACCOUNT")
        _bounded_id(request["command_key"], "command_key")
        replay = self.connection.execute("SELECT 1 FROM game_command_ledger WHERE account_id=? AND command_id=?", (authenticated_account_id, request["command_key"])).fetchone() is not None
        require(request["layout"][0] == 4 or (replay and request["layout"][0] == 3), "SHOP_REVISION_MISMATCH")
        profile = self.read_profile(authenticated_account_id)
        native = request["layout"][1]
        owned = next((r for r in profile["research"]["vehicles"] if r["native_id"] == native), None)
        require(replay or (owned is not None and all(owned["modules"][role] == self.catalog.vehicles[owned["vehicle_id"]]["defaults"][role]
                for role in ("turret", "gun"))), "AMMUNITION_CONFIGURATION_UNSUPPORTED")
        return super().service(request, authenticated_account_id=authenticated_account_id)

    @staticmethod
    def _validate_layout(layout):
        require(type(layout) is list and len(layout) == 16 and type(layout[0]) is int and layout[0] in (3, 4), "SHOP_REVISION_MISMATCH")
        return NativeAmmoStore._validate_layout([3, *layout[1:]])

    def migrate_research(self, source, *, account_id, policy):
        _bounded_id(account_id, "account_id")
        require(policy == POLICY, "EXPLICIT_TEST_LAB_POLICY_REQUIRED")
        require(type(self.catalog.sha256) is str and re.fullmatch(r"[0-9a-f]{64}", self.catalog.sha256), "VERIFIED_CATALOG_REQUIRED")
        require(isinstance(source, NativeCrossVehicleCrewStore.SOURCE), "VERIFIED_SOURCE_REQUIRED")
        require(source.profile["account_id"] == account_id, "FOREIGN_ACCOUNT")
        c = self.connection
        c.execute("BEGIN IMMEDIATE")
        self._allow_preresearch = True
        try:
            super().initialize()
            require(self._import(account_id)["bundle_sha256"] == source.bundle_sha256, "MIGRATION_SOURCE_CHANGED")
            if self._research_schema():
                self.initialize()
                if c.execute("SELECT 1 FROM p09e_research WHERE account_id=?", (account_id,)).fetchone():
                    profile = self.read_profile(account_id)
                    c.commit()
                    return {"status": "already_migrated", "revision": profile["revision"]}
                raise TransactionError("P09E_MULTIACCOUNT_MIGRATION_UNSUPPORTED")
            base = self.read_profile(account_id)
            before = c.execute("SELECT profile_json FROM game_profiles WHERE account_id=?", (account_id,)).fetchone()[0]
            require(_json(before)["profile_version"] == 8 and len(base["vehicles"]) == 2, "ACCEPTED_PROFILE8_REQUIRED")
            require(all(row["state"] == "available" for row in base["vehicles"]), "VEHICLE_RESERVED")
            require(base["revision"] < 2**31 - 1, "REVISION_EXHAUSTED")
            by_cd = {r["native_compact_id"]: key for key, r in self.catalog.vehicles.items()}
            require(3329 in by_cd and 7169 in by_cd, "REQUIRED_RUNTIME_TYPES_MISSING")
            native_state = source.trees["state.bin"]
            slots = _number(native_state["stats"]["slots"], 2, MAX_OWNED)
            require(all(v == [0, 0, 0] for v in native_state["inventory"][1]["eqs"].values()), "EQUIPMENT_MASS_UNSUPPORTED")
            by_item_cd = {row["native_compact_id"]: key for key, row in self.catalog.modules.items()}
            by_item_cd.update(by_cd)
            source_unlocked = native_state["stats"]["unlocks"]
            require(all(cd in by_item_cd for cd in source_unlocked), "SOURCE_UNLOCK_UNKNOWN")
            # Project starting policy, selected from pinned visible tier1 roots.
            # This grants research access to each nation, never tank ownership.
            owned, unlocked = [], {by_item_cd[cd] for cd in source_unlocked} | set(self.catalog.initial_unlocked)
            for native, cd in ((1, 3329), (2, 7169)):
                vehicle_id = by_cd[cd]
                vehicle = self.catalog.vehicles[vehicle_id]
                assembly(self.catalog, vehicle_id, vehicle["defaults"])
                source_descriptor = bytes([1, cd >> 8]) + struct.pack("<6H", *(self.catalog.modules[vehicle["defaults"][role]]["native_compact_id"] >> 8 for role in ("chassis", "engine", "fuelTank", "radio", "turret", "gun"))) + b"\x00"
                require(source_descriptor == native_state["inventory"][1]["compDescr"][native], "BASE_CONFIGURATION_MISMATCH")
                inventory_id = _json(before)["inventory"][native - 1]["inventory_id"]
                owned.append({"vehicle_inventory_id": inventory_id, "native_id": native, "vehicle_id": vehicle_id,
                              "modules": deepcopy(vehicle["defaults"]), "runtime_supported": False})
                unlocked.add(vehicle_id); unlocked.update(_default_unlocks(self.catalog, vehicle_id))
            state = {"schema": SCHEMA, "policy": POLICY, "catalog_sha256": self.catalog.sha256,
                     "unlocked": sorted(unlocked), "depot": {}, "vehicles": owned, "next_native_id": 3, "garage_slots": slots}
            c.execute("CREATE TABLE p09e_schema(version TEXT PRIMARY KEY,catalog_sha256 TEXT NOT NULL,policy_sha256 TEXT NOT NULL)")
            c.execute("CREATE TABLE p09e_research(account_id TEXT PRIMARY KEY REFERENCES game_snapshot(account_id),state_json TEXT NOT NULL,state_sha256 TEXT NOT NULL,base_revision INTEGER NOT NULL,base_profile_sha256 TEXT NOT NULL)")
            c.execute("INSERT INTO p09e_schema VALUES (?,?,?)", (SCHEMA, self.catalog.sha256, POLICY_SHA256))
            raw = _encode(state)
            c.execute("INSERT INTO p09e_research VALUES (?,?,?,?,?)", (account_id, raw, sha(raw.encode("ascii")), base["revision"], sha(before.encode("ascii"))))
            self._failpoint("after_research_schema")
            self._save_crew_projection(account_id, base["revision"] + 1, before)
            self._failpoint("before_research_migration_commit")
            self.read_profile(account_id)
            c.commit()
            return {"status": "migrated", "revision": base["revision"] + 1, "policy": POLICY}
        except Exception:
            c.rollback()
            raise
        finally:
            self._allow_preresearch = False

    def execute(self, request, *, authenticated_account_id, prepare_response=None, native_binding=None):
        request = validate_request(request, authenticated_account_id)
        require((prepare_response is None and native_binding is None) or
                (callable(prepare_response) and type(native_binding) is str and re.fullmatch(r"[0-9a-f]{64}", native_binding)), "INVALID_NATIVE_PROJECTION")
        self.initialize()
        account, key = request["account_id"], request["command_key"]
        command = SCHEMA + ":" + request["operation"]
        payload_sha = sha(canonical({"request": request, "catalog_sha256": self.catalog.sha256, "policy_sha256": POLICY_SHA256, "native_binding": native_binding}))
        c = self.connection
        c.execute("BEGIN IMMEDIATE")
        try:
            profile = self.read_profile(account)
            ledger = c.execute("SELECT * FROM game_command_ledger WHERE account_id=? AND command_id=?", (account, key)).fetchone()
            if ledger is not None:
                require(ledger["command_type"] == command and ledger["payload_sha256"] == payload_sha, "DUPLICATE_PAYLOAD_MISMATCH")
                result = self._replay(ledger, request, profile, prepare_response=prepare_response)
                c.commit()
                return result
            revision = profile["revision"]
            require(revision == request["expected_revision"], "STALE_REVISION")
            require(revision < 2**31 - 1, "REVISION_EXHAUSTED")
            reserved = [r["vehicle_id"] for r in profile["vehicles"] if r["state"] != "available"]
            loaded = [r["vehicle_id"] for r in profile["ammunition"] if any(r["loaded"].values())]
            before = profile["research"]
            after, details = plan(self.catalog, before, request["operation"], request["payload"], account_id=account, reserved=reserved, loaded=loaded)
            new_ids = {r["vehicle_inventory_id"] for r in after["vehicles"]} - {r["vehicle_inventory_id"] for r in before["vehicles"]}
            for vehicle_id in new_ids:
                c.execute("INSERT INTO game_vehicle VALUES (?,?,'available',NULL)", (account, vehicle_id))
            self._failpoint("after_research_vehicle_insert")
            raw = _encode(after)
            c.execute("UPDATE p09e_research SET state_json=?,state_sha256=? WHERE account_id=?", (raw, sha(raw.encode("ascii")), account))
            self._failpoint("after_research_state")
            public_before = c.execute("SELECT profile_json FROM game_profiles WHERE account_id=?", (account,)).fetchone()[0]
            self._save_crew_projection(account, revision + 1, public_before)
            response = self._response_research(request, revision + 1, details)
            native = None
            if prepare_response is not None:
                final = self.read_profile(account)
                require(final == self._next_aggregate(profile, after, revision + 1), "CORRUPT_STORE")
                native = prepare_response(deepcopy(profile), deepcopy(final), deepcopy(response))
                require(type(native) is dict and native.get("replayed") is False and len(canonical(native)) <= MAX_NATIVE_RESPONSE, "INVALID_NATIVE_PROJECTION")
            native_context = None
            if native is not None:
                native_context = {k: v for k, v in profile.items() if k != "research"}
                require(len(canonical(native_context)) <= MAX_NATIVE_CONTEXT, "INVALID_NATIVE_PROJECTION")
            # Persist one research snapshot. The complete after-state is
            # deterministically reproduced and hash-checked on replay, and
            # native context refers to the same before-state instead of
            # storing a third copy of the growing unlock/depot inventory.
            journal = {"schema": JOURNAL_SCHEMA, "before": before, "after_sha256": sha(canonical(after)),
                       "reserved": reserved, "loaded": loaded, "response": response,
                       "native_context": native_context, "native_response": native}
            raw = _encode(journal)
            c.execute("INSERT INTO game_command_ledger VALUES (?,?,?,?,?,?,?,?)", (account, key, command, payload_sha, revision, revision + 1, raw, sha(raw.encode("ascii"))))
            self._failpoint("after_research_ledger")
            self.read_profile(account)
            self._failpoint("before_commit")
            c.commit()
            return native if native is not None else response
        except Exception:
            c.rollback()
            raise

    @staticmethod
    def _response_research(request, revision, details):
        return {"status": "applied", "account_id": request["account_id"], "command_key": request["command_key"],
                "operation": request["operation"], "source_revision": request["expected_revision"], "revision": revision,
                "effective_xp": 0, "effective_credits": 0, "replayed": False, "details": details}

    @staticmethod
    def _next_aggregate(before, research, revision):
        value = deepcopy(before)
        value.update(revision=revision, research=deepcopy(research))
        existing = {r["vehicle_id"] for r in value["vehicles"]}
        for owned in research["vehicles"]:
            if owned["vehicle_inventory_id"] not in existing:
                value["vehicles"].append({"vehicle_id": owned["vehicle_inventory_id"], "state": "available", "battle_id": None})
        value["vehicles"].sort(key=lambda r: r["vehicle_id"])
        return value

    def _replay(self, row, request, profile, *, prepare_response=None):
        journal = _json(row["result_json"])
        require(sha(row["result_json"].encode("ascii")) == row["p09c_result_sha256"], "CORRUPT_STORE")
        legacy = journal.get("schema") == SCHEMA
        require((legacy and set(journal) == {"schema", "before", "after", "reserved", "loaded", "response", "native_before", "native_response"})
                or (journal.get("schema") == JOURNAL_SCHEMA and set(journal) == {"schema", "before", "after_sha256", "reserved", "loaded", "response", "native_context", "native_response"}), "CORRUPT_STORE")
        source, destination = row["source_revision"], row["destination_revision"]
        require(type(source) is int and source == request["expected_revision"] and destination == source + 1 and destination <= profile["revision"], "CORRUPT_STORE")
        try:
            after, details = plan(self.catalog, journal["before"], request["operation"], request["payload"], account_id=request["account_id"], reserved=journal["reserved"], loaded=journal["loaded"])
            response = self._response_research(request, destination, details)
            require((after == journal["after"] if legacy else sha(canonical(after)) == journal["after_sha256"])
                    and response == journal["response"], "CORRUPT_STORE")
            if prepare_response is not None:
                if legacy:
                    before = journal["native_before"]
                else:
                    context = journal["native_context"]
                    require(type(context) is dict and "research" not in context
                            and len(canonical(context)) <= MAX_NATIVE_CONTEXT, "CORRUPT_STORE")
                    before = {**context, "research": journal["before"]}
                require(type(before) is dict and before["research"] == journal["before"] and before["revision"] == source
                        and before["account_id"] == request["account_id"], "CORRUPT_STORE")
                final = self._next_aggregate(before, after, destination)
                native = prepare_response(before, final, response)
                require(type(native) is dict and native == journal["native_response"] and native.get("replayed") is False, "CORRUPT_STORE")
                response = native
            else:
                require(journal["native_before" if legacy else "native_context"] is None and journal["native_response"] is None, "CORRUPT_STORE")
        except (KeyError, TypeError, ValueError, TransactionError) as error:
            raise TransactionError("CORRUPT_STORE", "invalid replay transition") from error
        return {**response, "replayed": True}
