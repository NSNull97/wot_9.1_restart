"""Bounded CMD309 project-policy projection on the verified profile4 source.

The descriptor is a fixed test passport, not a tankman inventory identity.
Native/runtime acceptance is established separately by actual client evidence.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

from p09d_ammo_projection import ProjectionSource, canonical, encode, SHOP_REVISION, MAX_UPDATE


SCHEMA = "p04d-native-crew.v1"
POLICY = {"schema": SCHEMA, "target": "v.0.9.1 #717 RU", "command": 309,
          "vehicle_native_inventory_id": 1, "slot": 1, "tariff_index": 0,
          "role": "driver", "role_level": 100, "skills": [], "credits_cost": 0,
          "gold_cost": 0, "free_recruitment_quota": 1, "crew_bound": 16, "barracks_bound": 16,
          "passport": "fixed-verified-P02-driver-descriptor", "policy_scope": "explicit-project-test_lab",
          "paid_recruitment": "UNSUPPORTED", "battle_admission": "DISABLED"}
POLICY_SHA256 = hashlib.sha256(canonical(POLICY)).hexdigest()
DESCRIPTOR_PINS = {
    "commander": "926254dfdbc7acf5a5d0c163d57642c24105da3ab21a7255236060e9534b70b5",
    "driver": "e4c85b2b116b96eff5d68aa8df2e509370f923843def67331478e4b62309b76d",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def native_crew(value):
    """Validate the closed one-recruit inventory and return native primitive maps."""
    require(type(value) is dict and set(value) == {"policy_sha256", "free_recruitment_left",
        "next_native_id", "configuration_revision", "members"}, "crew projection fields")
    require(value["policy_sha256"] == POLICY_SHA256, "crew policy digest")
    free, revision, next_id = (value[k] for k in ("free_recruitment_left", "configuration_revision", "next_native_id"))
    require(type(free) is int and free in (0, 1), "free recruitment quota")
    require(type(revision) is int and revision == 2 - free, "vehicle configuration revision")
    members = value["members"]
    require(type(members) is list and 2 <= len(members) <= 16 and len(members) == 3 - free, "crew count/quota binding")
    require(type(next_id) is int and next_id == len(members) + 1, "server ID allocator binding")
    descriptors, vehicles, seats, seen = {}, {}, [None, None], set()
    fields = {"native_id", "crew_id", "role", "descriptor_hex", "vehicle_native_id", "seat"}
    for number, row in enumerate(members, 1):
        require(type(row) is dict and set(row) == fields, "crew member fields")
        require(type(row["native_id"]) is int and row["native_id"] == number, "stable contiguous inventory IDs")
        require(type(row["crew_id"]) is str and 1 <= len(row["crew_id"]) <= 96
                and row["crew_id"] not in seen and row["crew_id"].isascii(), "crew domain identity")
        seen.add(row["crew_id"])
        role = "commander" if number == 1 else "driver"
        require(row["role"] == role and type(row["descriptor_hex"]) is str
                and len(row["descriptor_hex"]) == 50, "source-bound crew role/descriptor")
        raw = bytes.fromhex(row["descriptor_hex"])
        require(raw.hex() == row["descriptor_hex"] and sha(raw) == DESCRIPTOR_PINS[role], "source descriptor digest")
        assigned = number in (1, len(members))
        expected_vehicle, expected_seat = (1, 0 if number == 1 else 1) if assigned else (-1, None)
        require(type(row["vehicle_native_id"]) is int and row["vehicle_native_id"] == expected_vehicle,
                "crew vehicle assignment")
        require(row["seat"] is None if expected_seat is None else
                type(row["seat"]) is int and row["seat"] == expected_seat, "crew seat assignment")
        descriptors[number], vehicles[number] = raw, expected_vehicle
        if assigned:
            seats[expected_seat] = number
    return {"compDescr": descriptors, "vehicle": vehicles}, seats


def update_delta(crew, wire_revision):
    require(type(wire_revision) is int and 1 <= wire_revision < 2**31 - 1, "wire revision bound")
    inventory, seats = native_crew(crew)
    require(crew["free_recruitment_left"] == 0, "recruit result requires consumed quota")
    # Only changed maps are sent; original commander1 is retained by merge.
    changed = {"compDescr": {3: inventory["compDescr"][3]}, "vehicle": {2: -1, 3: 1}}
    value = {"prevRev": wire_revision, "rev": wire_revision + 1,
             "inventory": {8: changed, 1: {"crew": {1: seats}}}, "stats": {"freeTMenLeft": 0}}
    return encode(value, MAX_UPDATE)


def shop_policy(shop):
    """Expose verified free tariff row0; paid-row getters must be gated by UI."""
    result = deepcopy(shop)
    result["tankmanCost"] = [{}]
    return result


class CrewProjectionSource(ProjectionSource):
    def __init__(self, bundle_root):
        super().__init__(bundle_root)
        source = self.trees["state.bin"]
        require(source["inventory"][1]["crew"] == {1: [1, 2], 2: [None] * 5}, "exact imported crew seats")
        inv = source["inventory"][8]
        require(set(inv) == {"compDescr", "vehicle"} and inv["vehicle"] == {1: 1, 2: 1}
                and set(inv["compDescr"]) == {1, 2}, "exact imported tankman inventory")
        require(source["stats"]["berths"] == 16, "imported test barracks bound")
        self.descriptors = {}
        for native_id, role in ((1, "commander"), (2, "driver")):
            raw = inv["compDescr"][native_id]
            require(type(raw) is bytes and len(raw) == 25 and sha(raw) == DESCRIPTOR_PINS[role], "original tankman descriptor")
            self.descriptors[role] = raw.hex()

    def state(self, aggregate, layouts):
        value = super().state(aggregate, layouts)
        inventory, seats = native_crew(aggregate["crew_inventory"])
        value["inventory"][8] = inventory
        value["inventory"][1]["crew"][1] = seats
        value["stats"]["freeTMenLeft"] = aggregate["crew_inventory"]["free_recruitment_left"]
        return value

    def fixture_files(self, profile, aggregate, layouts):
        files = super().fixture_files(profile, aggregate, layouts)
        state = files["state.bin"]
        files["shop.bin"] = encode(shop_policy(self.trees["shop.bin"]))
        crew = aggregate["crew_inventory"]
        manifest = json.loads(files["manifest.json"])
        manifest.update(fixture_version=6, profile_version=6, crew_policy_sha256=POLICY_SHA256)
        manifest["files"] = [{"file": name, "bytes": len(files[name]), "sha256": sha(files[name])}
                             for name in ("state.bin", "shop.bin", "dossier.bin")]
        manifest["shop_policy"] = {"source_shop_sha256": sha(self.raw["shop.bin"]),
                                   "projected_shop_sha256": sha(files["shop.bin"]), "policy_sha256": POLICY_SHA256}
        files["manifest.json"] = canonical(manifest)
        compatibility = json.loads(files["compatibility.json"])
        compatibility["crew_mapping"] = [{"crew_id": row["crew_id"], "native_inventory_id": row["native_id"],
            "native_vehicle_inventory_id": row["vehicle_native_id"], "slot_index": row["seat"]}
            for row in crew["members"]]
        files["compatibility.json"] = canonical(compatibility)
        metadata = dict(version=1, account_id=profile["account_id"], native_database_id=profile["native_database_id"],
            revision=aggregate["revision"], wire_revision=1, policy_sha256=POLICY_SHA256, state_sha256=sha(state),
            command=309, vehicle_inventory_id=1, slot=1, tariff_index=0,
            free_recruitment_left=crew["free_recruitment_left"], configuration_revision=crew["configuration_revision"], battle=False)
        files["crew-service.json"] = canonical(metadata)
        return files
