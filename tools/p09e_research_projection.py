"""Server-authored #717 shop/account projection for the explicit research lab.

Only primitive data is encoded. Growing unlock sets carry newly added items in
updates, as consumed by original Stats.synchronize; no client objects are loaded.
"""
from __future__ import annotations

from copy import deepcopy
import json

from p04g_crew_projection import CrossVehicleCrewProjectionSource
from p09d_ammo_projection import encode, canonical
from p09e_native_research_audit import plain_vehicle_descriptor
from p09e_research_store import POLICY_SHA256
from game_profile_tx import TransactionError
import hashlib

SHOP_REVISION = 4
MAX_SHOP = 32768
MAX_STATE = 32768
MAX_UPDATE = 240
MAX_NODES = 32768


def sha(raw): return hashlib.sha256(raw).hexdigest()


def require(value, code="INVALID_RESEARCH_PROJECTION"):
    if not value: raise TransactionError(code)


def item_cd(catalog, key):
    row = catalog.vehicles.get(key) or catalog.modules.get(key)
    require(row is not None)
    return row["native_compact_id"]


def descriptor(catalog, vehicle):
    parts = vehicle["modules"]
    cd = lambda k: item_cd(catalog, parts[k])
    return plain_vehicle_descriptor(item_cd(catalog, vehicle["vehicle_id"]),
        cd("chassis"), cd("engine"), cd("fuelTank"), cd("radio"), [(cd("turret"), cd("gun"))])


def elite_ids(catalog, unlocked):
    """Project rule: all listed research targets known; original server is absent.

    #717 Vehicle consumes stats.eliteVehicles for nonempty unlock graphs. Empty
    graphs are already elite in that original constructor. Keep the eligibility
    derivation explicit instead of pretending the UI calculates it for us.
    """
    known = set(unlocked)
    incomplete = {row["vehicle_id"] for row in catalog.unlocks if row["item_id"] not in known}
    return {item_cd(catalog, key) for key in catalog.vehicles if key not in incomplete}


def garage_record(catalog, vehicle):
    definition = catalog.vehicles[vehicle["vehicle_id"]]
    health = definition["hull_max_hp"] + definition["turret_max_hp"][vehicle["modules"]["turret"]]
    require(type(health) is int and health > 0)
    seats = definition["crew_roles"]
    require(type(seats) is list and 1 <= len(seats) <= 8)
    return {"compDescr": descriptor(catalog, vehicle), "repair": (0, health),
        "crew": [None] * len(seats), "settings": 0, "shells": [],
        "shellsLayout": {}, "eqs": [0, 0, 0], "eqsLayout": [0, 0, 0]}


def shop_tree(catalog, source_shop):
    shop = deepcopy(source_shop)
    shop["rev"] = SHOP_REVISION
    # Source gold remains source gold. Only ordinary credit transactions are
    # admitted by the store. Removing a price is not a security boundary.
    shop["items"]["itemPrices"] = {row["native_compact_id"]:
        (0, row["historical_price"]["amount"] if row["historical_price"]["currency"] == "gold" else 0)
        for row in (*catalog.vehicles.values(), *catalog.modules.values())}
    shop["items"]["notInShopItems"] = sorted(v["native_compact_id"]
        for v in catalog.vehicles.values() if v["not_in_shop"] or set(v["tags"]) & {"secret", "observer", "event_battles", "special"})
    return shop


class ResearchProjectionSource(CrossVehicleCrewProjectionSource):
    def __init__(self, bundle_root, catalog):
        super().__init__(bundle_root)
        self.catalog = catalog

    def encode_state(self, state):
        return encode(state, MAX_STATE, max_nodes=MAX_NODES)

    def state(self, aggregate, layouts):
        state = super().state(aggregate, layouts)
        research, inv = aggregate["research"], state["inventory"]
        state["stats"]["unlocks"] = sorted(item_cd(self.catalog, k) for k in research["unlocked"])
        state["stats"]["eliteVehicles"] = sorted(elite_ids(self.catalog, research["unlocked"]))
        state["stats"]["slots"] = research["garage_slots"]
        for kind in range(2, 8):
            inv[kind] = {item_cd(self.catalog, k): n for k, n in research["depot"].items()
                         if self.catalog.modules[k]["native_compact_id"] & 15 == kind}
        for vehicle in research["vehicles"]:
            native = vehicle["native_id"]
            if native not in (1, 2):
                for key, value in garage_record(self.catalog, vehicle).items(): inv[1][key][native] = value
            else:
                inv[1]["compDescr"][native] = descriptor(self.catalog, vehicle)
                inv[1]["repair"][native] = garage_record(self.catalog, vehicle)["repair"]
                defaults = self.catalog.vehicles[vehicle["vehicle_id"]]["defaults"]
                if any(vehicle["modules"][k] != defaults[k] for k in ("turret", "gun")):
                    # The old P09D ammunition adapter has no source-bound layout
                    # for this new mount. Installation already required an empty
                    # gun; do not advertise the old gun's preferred shell list.
                    inv[1]["shells"][native] = []
                    inv[1]["shellsLayout"][native] = {}
            state["stats"]["vehTypeXP"].setdefault(item_cd(self.catalog, vehicle["vehicle_id"]), 0)
        return state

    def fixture_files(self, profile, aggregate, layouts):
        files = super().fixture_files(profile, aggregate, layouts)
        files["state.bin"] = encode(self.state(aggregate, layouts), MAX_STATE, max_nodes=MAX_NODES)
        files["shop.bin"] = encode(shop_tree(self.catalog, self.trees["shop.bin"]), MAX_SHOP, max_nodes=MAX_NODES)
        state_sha = sha(files["state.bin"])
        manifest = json.loads(files["manifest.json"])
        manifest.update(fixture_version=9, profile_version=9, research_policy_sha256=POLICY_SHA256,
                        research_catalog_sha256=self.catalog.sha256)
        manifest["files"] = [{"file": k, "bytes": len(files[k]), "sha256": sha(files[k])}
                             for k in ("state.bin", "shop.bin", "dossier.bin")]
        manifest["shop_policy"].update(projected_shop_sha256=sha(files["shop.bin"]))
        files["manifest.json"] = canonical(manifest)
        compatibility = json.loads(files["compatibility.json"])
        compatibility["research_mapping"] = [{"vehicle_inventory_id": v["vehicle_inventory_id"],
            "native_inventory_id": v["native_id"], "vehicle_id": v["vehicle_id"],
            "type_compact_id": item_cd(self.catalog, v["vehicle_id"]), "battle": False}
            for v in aggregate["research"]["vehicles"]]
        files["compatibility.json"] = canonical(compatibility)
        for name in ("ammo-service.json", "crew-cross-transfer.json"):
            metadata = json.loads(files[name]); metadata["state_sha256"] = state_sha
            files[name] = canonical(metadata)
        files["research-service.json"] = canonical(dict(version=1, account_id=profile["account_id"],
            native_database_id=profile["native_database_id"], revision=aggregate["revision"],
            wire_revision=1, policy_sha256=POLICY_SHA256, catalog_sha256=self.catalog.sha256,
            state_sha256=state_sha, shop_sha256=sha(files["shop.bin"]),
            commands=[101, 201, 301, 302, 308], battle=False))
        return files


def update_delta(catalog, before, after, wire_revision):
    require(type(wire_revision) is int and 1 <= wire_revision < 2**31 - 1)
    delta = {"prevRev": wire_revision, "rev": wire_revision + 1}
    unlocked = sorted(set(after["unlocked"]) - set(before["unlocked"]))
    if unlocked: delta["stats"] = {"unlocks": [item_cd(catalog, k) for k in unlocked]}
    elites = sorted(elite_ids(catalog, after["unlocked"]) - elite_ids(catalog, before["unlocked"]))
    if elites: delta.setdefault("stats", {})["eliteVehicles"] = elites
    inv = {}
    for key in sorted(set(before["depot"]) | set(after["depot"])):
        previous, current = before["depot"].get(key, 0), after["depot"].get(key, 0)
        if previous != current:
            cd = item_cd(catalog, key)
            inv.setdefault(cd & 15, {})[cd] = current
    by_id = {v["native_id"]: v for v in before["vehicles"]}
    for vehicle in after["vehicles"]:
        native = vehicle["native_id"]
        if native not in by_id:
            for key, value in garage_record(catalog, vehicle).items(): inv.setdefault(1, {}).setdefault(key, {})[native] = value
        elif vehicle["modules"] != by_id[native]["modules"]:
            inv.setdefault(1, {}).setdefault("compDescr", {})[native] = descriptor(catalog, vehicle)
            if vehicle["modules"]["turret"] != by_id[native]["modules"]["turret"]:
                inv[1].setdefault("repair", {})[native] = garage_record(catalog, vehicle)["repair"]
            if any(vehicle["modules"][k] != by_id[native]["modules"][k] for k in ("turret", "gun")):
                inv[1].setdefault("shells", {})[native] = []
                inv[1].setdefault("shellsLayout", {})[native] = {}
    if inv: delta["inventory"] = inv
    return encode(delta, MAX_UPDATE)
