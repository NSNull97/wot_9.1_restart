"""Source-bound mutable MS-1 crew assignment projection; no client execution."""
from __future__ import annotations

import json

from p04d_crew_projection import CrewProjectionSource, DESCRIPTOR_PINS, shop_policy, sha
from p09d_ammo_projection import ProjectionSource, canonical, encode, MAX_UPDATE

SCHEMA = "p04f-native-crew-transfer.v1"
POLICY = {"schema": SCHEMA, "target": "v.0.9.1 #717 RU", "command": 105,
          "vehicle_native_inventory_id": 1, "compatible_seats": {"commander": 0, "driver": 1},
          "unload_tankman_id": -1, "unload_whole_crew_slot": -1,
          "vacant_seat": None, "barracks_vehicle_id": -1,
          "crew_bound": 16, "barracks_bound": 16, "role_level": 100, "skills": [],
          "recruitment": "retained-one-free100-MS1-driver-fixed-passport",
          "no_change": "reject-without-revision-or-ledger",
          "policy_scope": "explicit-project-test_lab", "battle_admission": "DISABLED"}
POLICY_SHA256 = sha(canonical(POLICY))


def require(ok, message):
    if not ok:
        raise ValueError(message)


def native_crew(value):
    require(type(value) is dict and set(value) == {"policy_sha256", "free_recruitment_left",
        "next_native_id", "configuration_revision", "members"}, "crew projection fields")
    require(value["policy_sha256"] == POLICY_SHA256, "crew policy digest")
    free, revision, next_id = (value[k] for k in ("free_recruitment_left", "configuration_revision", "next_native_id"))
    require(type(free) is int and free in (0, 1), "free recruitment quota")
    require(type(revision) is int and 2 - free <= revision < 2**31, "configuration revision")
    members = value["members"]
    require(type(members) is list and len(members) == 3 - free, "retained inventory/quota binding")
    require(type(next_id) is int and next_id == len(members) + 1, "server ID allocator binding")
    descriptors, vehicles, seats, seen = {}, {}, [None, None], set()
    fields = {"native_id", "crew_id", "role", "descriptor_hex", "vehicle_native_id", "seat"}
    for number, row in enumerate(members, 1):
        require(type(row) is dict and set(row) == fields, "crew member fields")
        require(type(row["native_id"]) is int and row["native_id"] == number, "stable inventory IDs")
        require(type(row["crew_id"]) is str and 1 <= len(row["crew_id"]) <= 96
                and row["crew_id"].isascii() and row["crew_id"] not in seen, "crew domain identity")
        seen.add(row["crew_id"])
        role = "commander" if number == 1 else "driver"
        require(row["role"] == role and type(row["descriptor_hex"]) is str
                and len(row["descriptor_hex"]) == 50, "source-bound crew role/descriptor")
        raw = bytes.fromhex(row["descriptor_hex"])
        require(raw.hex() == row["descriptor_hex"] and sha(raw) == DESCRIPTOR_PINS[role], "source descriptor digest")
        vehicle, seat = row["vehicle_native_id"], row["seat"]
        require(type(vehicle) is int and vehicle in (-1, 1), "crew vehicle assignment")
        if vehicle == -1:
            require(seat is None, "barracks seat")
        else:
            expected = 0 if role == "commander" else 1
            require(type(seat) is int and seat == expected and seats[seat] is None, "unique compatible seat")
            seats[seat] = number
        descriptors[number], vehicles[number] = raw, vehicle
    require(sum(v == -1 for v in vehicles.values()) <= POLICY["barracks_bound"], "barracks capacity")
    return {"compDescr": descriptors, "vehicle": vehicles}, seats


def update_delta(crew, wire_revision, *, recruit=False):
    require(type(wire_revision) is int and 1 <= wire_revision < 2**31 - 1, "wire revision bound")
    inventory, seats = native_crew(crew)
    changed = {"vehicle": inventory["vehicle"]}
    value = {"prevRev": wire_revision, "rev": wire_revision + 1,
             "inventory": {8: changed, 1: {"crew": {1: seats}}}}
    if recruit:
        require(crew["free_recruitment_left"] == 0, "recruit requires consumed quota")
        changed["compDescr"] = {3: inventory["compDescr"][3]}
        value["stats"] = {"freeTMenLeft": 0}
    return encode(value, MAX_UPDATE)


class CrewTransferProjectionSource(CrewProjectionSource):
    def state(self, aggregate, layouts):
        value = ProjectionSource.state(self, aggregate, layouts)
        inventory, seats = native_crew(aggregate["crew_inventory"])
        value["inventory"][8] = inventory
        value["inventory"][1]["crew"][1] = seats
        value["stats"]["freeTMenLeft"] = aggregate["crew_inventory"]["free_recruitment_left"]
        return value

    def fixture_files(self, profile, aggregate, layouts):
        files = ProjectionSource.fixture_files(self, profile, aggregate, layouts)
        state = files["state.bin"]
        files["shop.bin"] = encode(shop_policy(self.trees["shop.bin"]))
        crew = aggregate["crew_inventory"]
        manifest = json.loads(files["manifest.json"])
        manifest.update(fixture_version=7, profile_version=7, crew_policy_sha256=POLICY_SHA256)
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
            command=105, vehicle_inventory_id=1, free_recruitment_left=crew["free_recruitment_left"],
            configuration_revision=crew["configuration_revision"], battle=False)
        files["crew-transfer.json"] = canonical(metadata)
        return files
