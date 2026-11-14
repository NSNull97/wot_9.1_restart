"""Authoritative equipment slots, owned stock and journaled native hangar commands."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import struct

from content0_equipment_catalog import ENHANCED_SUSPENSIONS, MANIFEST_SHA256, SLOT_COUNT, live_items
from destructible_catalog import json_value
from p09d_ammo_store import require, sha
from p09d_ammo_projection import canonical

TABLE = "content0_artefacts_v1"
COMMAND = "content0.artefacts.v1"
MAX_STATE_BYTES = 32768
MAX_STOCK = 1_000_000
EMPTY_SLOTS = (0,) * SLOT_COUNT
FIELDS = ("devices", "consumables", "layout")
SCHEMA_VERSION = 1
OPTDEV = 9
EQUIPMENT = 11


def _empty_vehicle():
    return {field: list(EMPTY_SLOTS) for field in FIELDS}


def _item(cd, kind):
    require(type(cd) is int, "ARTEFACT_SLOT_INVALID")
    item = live_items().get(cd)
    require(item is not None and item.kind == kind, "ARTEFACT_UNSUPPORTED")
    return item


def _slots(slots, kind):
    require(type(slots) in (list, tuple) and len(slots) == SLOT_COUNT, "ARTEFACT_SLOT_INVALID")
    require(all(type(cd) is int for cd in slots), "ARTEFACT_SLOT_INVALID")
    mounted = [_item(cd, kind) for cd in slots if cd != 0]
    require(len({item.compact_id for item in mounted}) == len(mounted), "ARTEFACT_DUPLICATE")
    require(sum(item.compact_id in ENHANCED_SUSPENSIONS for item in mounted) <= 1, "ARTEFACT_CONFLICT")
    for index, item in enumerate(mounted):
        require(not any(item.tags & other.incompatible_tags or other.tags & item.incompatible_tags
                        for other in mounted[index + 1:]), "ARTEFACT_CONFLICT")
    return list(slots)


def validate_installed_devices(catalog, owned, slots):
    """Check source compatibility and the complete equipped chassis load."""
    from p09e_research_store import assembly
    mounted = [_item(cd, OPTDEV) for cd in _slots(slots, OPTDEV) if cd]
    vehicle = catalog.vehicles[owned["vehicle_id"]]
    require(all(item.compatible(vehicle) for item in mounted), "ARTEFACT_INCOMPATIBLE")
    suspension = next((item.compact_id for item in mounted if item.compact_id in ENHANCED_SUSPENSIONS), None)
    args = {"suspension": suspension} if suspension is not None else {}
    definition = assembly(catalog, owned["vehicle_id"], owned["modules"], **args)
    weight = sum(item.weight_grams for item in mounted)
    weight_percent = sum(item.weight_percent for item in mounted)
    base = definition["mass_grams"]
    require(100 * (base + weight) + base * weight_percent <= 100 * definition["max_load_grams"], "CHASSIS_OVERLOAD")


def validate_installed_consumables(catalog, vehicle_id, slots):
    desired = _slots(slots, EQUIPMENT)
    if any(desired):
        vehicle = catalog.vehicles[vehicle_id]
        require(all(live_items()[cd].compatible(vehicle) for cd in desired if cd), "ARTEFACT_INCOMPATIBLE")
    return desired


def _validate_state(state, owned_ids=None):
    require(type(state) is dict and set(state) == {"catalog_sha256", "depot", "vehicles"}
            and state["catalog_sha256"] == MANIFEST_SHA256
            and type(state["depot"]) is dict and type(state["vehicles"]) is dict, "CORRUPT_ARTEFACT_STORE")
    supported = {str(cd) for cd in live_items()}
    for cd, count in state["depot"].items():
        require(cd in supported and type(count) is int and 1 <= count <= MAX_STOCK,
                "CORRUPT_ARTEFACT_STORE")
    for vehicle_id, slots in state["vehicles"].items():
        require(type(vehicle_id) is str and vehicle_id and len(vehicle_id) <= 128
                and (owned_ids is None or vehicle_id in owned_ids) and type(slots) is dict
                and set(slots) == set(FIELDS)
                and all(type(slots[field]) is list for field in FIELDS)
                and any(any(layout) for layout in slots.values()), "CORRUPT_ARTEFACT_STORE")
        _slots(slots["devices"], OPTDEV)
        _slots(slots["consumables"], EQUIPMENT)
        _slots(slots["layout"], EQUIPMENT)
    return state


def read_state(connection, account, owned_ids=None):
    if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)).fetchone() is None:
        return None
    row = connection.execute(f"SELECT state_json,state_sha256 FROM {TABLE} WHERE account_id=?", (account,)).fetchone()
    if row is None:
        return None
    raw, digest = row
    require(type(raw) is str and raw.isascii() and len(raw) <= MAX_STATE_BYTES
            and sha(raw.encode("ascii")) == digest, "CORRUPT_ARTEFACT_STORE")
    state = _validate_state(json_value(raw.encode("ascii"), limit=MAX_STATE_BYTES, nodes=12000, depth=8), owned_ids)
    require(canonical(state).decode("ascii") == raw, "CORRUPT_ARTEFACT_STORE")
    return state


def save_state(connection, account, state):
    raw = canonical(_validate_state(state))
    require(len(raw) <= MAX_STATE_BYTES, "PROFILE_TOO_LARGE")
    require(connection.execute(f"UPDATE {TABLE} SET state_json=?,state_sha256=? WHERE account_id=?",
                               (raw.decode("ascii"), sha(raw), account)).rowcount == 1, "ARTEFACTS_UNAVAILABLE")


def battle_loadout(connection, account, vehicle_inventory_id):
    state = read_state(connection, account)
    row = (state["vehicles"].get(vehicle_inventory_id) if state is not None else None) or _empty_vehicle()
    return tuple(row["devices"]), tuple(row["consumables"])


def consume_battle(connection, account, vehicle_inventory_id, original_consumables, used_slots):
    original = _slots(original_consumables, EQUIPMENT)
    require(type(used_slots) in (list, tuple)
            and all(type(slot) is int and 0 <= slot < SLOT_COUNT and original[slot] for slot in used_slots)
            and len(set(used_slots)) == len(used_slots), "ARTEFACT_SLOT_INVALID")
    state = read_state(connection, account)
    row = (state["vehicles"].get(vehicle_inventory_id) if state is not None else None) or _empty_vehicle()
    require(row["consumables"] == original, "ARTEFACT_BATTLE_LOADOUT_MISMATCH")
    if used_slots:
        require(state is not None, "CORRUPT_ARTEFACT_STORE")
        for slot in used_slots:
            row["consumables"][slot] = 0
        _set_vehicle(state, vehicle_inventory_id, row)
        save_state(connection, account, state)


def _set_vehicle(state, vehicle_id, row):
    if any(any(slots) for slots in row.values()):
        state["vehicles"][vehicle_id] = row
    else:
        state["vehicles"].pop(vehicle_id, None)


def _stock(state, cd, change, *, allow_purchase=False):
    key = str(cd)
    count = state["depot"].get(key, 0) + change
    require(count >= 0 or allow_purchase, "INSUFFICIENT_STOCK")
    require(count <= MAX_STOCK, "DEPOT_OVERFLOW")
    if count > 0:
        state["depot"][key] = count
    else:
        state["depot"].pop(key, None)


def _device(state, catalog, owned, cd, slot, paid_removal, *, buy, allow_purchase):
    require(type(slot) is int and 0 <= slot < SLOT_COUNT, "ARTEFACT_SLOT_INVALID")
    if cd:
        _item(cd, OPTDEV)
    vehicle_id = owned["vehicle_inventory_id"]
    row = state["vehicles"].get(vehicle_id, _empty_vehicle())
    previous = row["devices"][slot]
    require(previous != cd, "ARTEFACT_NO_CHANGE")
    # The flag buys preservation of a non-removable device (free on this stand).
    require(not paid_removal or allow_purchase, "PAID_OR_SLOT_OPERATION_UNSUPPORTED")
    require(not paid_removal or (previous and not live_items()[previous].removable),
            "PAID_OR_SLOT_OPERATION_UNSUPPORTED")
    row["devices"][slot] = cd
    validate_installed_devices(catalog, owned, row["devices"])
    if previous and (live_items()[previous].removable or paid_removal):
        _stock(state, previous, 1)
    if cd and not buy:
        _stock(state, cd, -1)
    _set_vehicle(state, vehicle_id, row)


def _consumables(state, vehicle_id, desired, *, allow_purchase):
    desired = _slots(desired, EQUIPMENT)
    row = state["vehicles"].get(vehicle_id, _empty_vehicle())
    delta = Counter(cd for cd in row["consumables"] if cd)
    delta.subtract(cd for cd in desired if cd)
    for cd, change in delta.items():
        _stock(state, cd, change, allow_purchase=allow_purchase)
    row.update(consumables=desired, layout=desired.copy())
    _set_vehicle(state, vehicle_id, row)


def _owned(research, native_id):
    vehicle = next((r for r in research["vehicles"] if r["native_id"] == native_id), None)
    require(vehicle is not None, "UNOWNED_VEHICLE")
    return vehicle


def plan_maintenance(aggregate, native_id, equipment_layout, *, allow_purchase, catalog=None):
    """Honor #717 CMD108's optional six-int consumable sub-layout atomically."""
    if not equipment_layout:
        return None
    require(type(equipment_layout) in (list, tuple) and len(equipment_layout) == 2 * SLOT_COUNT
            and all(type(cd) is int and -(2**31) < cd < 2**31 and type(count) is int and count == bool(cd)
                    for cd, count in zip(equipment_layout[::2], equipment_layout[1::2])), "ARTEFACT_SLOT_INVALID")
    desired = [abs(cd) for cd in equipment_layout[::2]]
    before = aggregate.get("artefacts")
    if before is None:
        require(not any(desired), "ARTEFACTS_UNAVAILABLE")
        return None
    _validate_state(before)
    vehicle = _owned(aggregate["research"], native_id)
    if catalog is not None:
        desired = validate_installed_consumables(catalog, vehicle["vehicle_id"], desired)
    after = deepcopy(before)
    _consumables(after, vehicle["vehicle_inventory_id"], desired, allow_purchase=allow_purchase)
    return after if after != before else None


def _plan(before, catalog, owned, command, args, *, allow_purchase):
    require(before is not None, "ARTEFACTS_UNAVAILABLE")
    after = deepcopy(_validate_state(before))
    target = owned and owned["vehicle_inventory_id"]
    if command == 302:
        _, cd, count, _ = args
        require(allow_purchase, "PURCHASE_UNSUPPORTED")
        require(cd in live_items(), "ARTEFACT_UNSUPPORTED")
        _stock(after, cd, count)
    elif command == 102:
        _, _, cd, slot, paid = args
        _device(after, catalog, owned, cd, slot, paid, buy=False, allow_purchase=allow_purchase)
    elif command == 104:
        desired = validate_installed_consumables(catalog, owned["vehicle_id"], args[1:])
        _consumables(after, target, desired, allow_purchase=False)
    elif command == 308:
        _, cd, _, slot, paid, _ = args
        require(allow_purchase, "PURCHASE_UNSUPPORTED")
        if cd & 15 == OPTDEV:
            _device(after, catalog, owned, cd, slot, paid, buy=True, allow_purchase=allow_purchase)
        else:
            _item(cd, EQUIPMENT)
            require(not paid and type(slot) is int and 0 <= slot < SLOT_COUNT, "ARTEFACT_SLOT_INVALID")
            row = after["vehicles"].get(target, _empty_vehicle())
            desired = row["consumables"].copy()
            require(desired[slot] != cd, "ARTEFACT_NO_CHANGE")
            desired[slot] = cd
            desired = validate_installed_consumables(catalog, owned["vehicle_id"], desired)
            _stock(after, cd, 1)
            _consumables(after, target, desired, allow_purchase=False)
    else:
        raise ValueError("invalid artefact command")
    return after


def installed_descriptor(plain, slots, *, historical_device_order=False):
    devices = _slots(slots, OPTDEV)
    require(type(plain) is bytes and len(plain) >= 15 and plain[-1] == 0, "CORRUPT_ARTEFACT_STORE")
    # #717 shifts the mask left per slot and prepends each LE device.id[1].
    mask = sum(1 << (SLOT_COUNT - 1 - slot) for slot, cd in enumerate(devices) if cd)
    words = devices if historical_device_order else reversed(devices)
    return plain[:-1] + bytes((mask,)) + b"".join(struct.pack("<H", cd >> 8) for cd in words if cd)


def projection_parts(before, after, research, *, catalog=None, historical_device_order=False):
    from p09e_research_projection import descriptor
    if before is None or after is None:
        return []
    parts = []
    for cd in sorted(set(before["depot"]) | set(after["depot"]), key=int):
        previous, current = before["depot"].get(cd, 0), after["depot"].get(cd, 0)
        if previous != current:
            parts.append({"inventory": {int(cd) & 15: {int(cd): current}}})
    for vehicle in research["vehicles"]:
        key, native = vehicle["vehicle_inventory_id"], vehicle["native_id"]
        previous = before["vehicles"].get(key, _empty_vehicle())
        current = after["vehicles"].get(key, _empty_vehicle())
        changed = {}
        if previous["devices"] != current["devices"]:
            require(catalog is not None, "CORRUPT_ARTEFACT_STORE")
            changed["compDescr"] = {native: installed_descriptor(descriptor(catalog, vehicle), current["devices"],
                                                                 historical_device_order=historical_device_order)}
        if previous["consumables"] != current["consumables"]:
            changed["eqs"] = {native: current["consumables"]}
        if previous["layout"] != current["layout"]:
            changed["eqsLayout"] = {native: current["layout"]}
        if changed:
            parts.append({"inventory": {1: changed}})
    return parts


def projection_updates(before, after, research, wire_revision, *, catalog=None, historical_device_order=False):
    from p09e_research_projection import chained_updates
    first = {"prevRev": wire_revision, "rev": wire_revision + 1}
    parts = projection_parts(before, after, research, catalog=catalog, historical_device_order=historical_device_order)
    return chained_updates(first, parts, wire_revision, 4)


def activate(store, account):
    """Enable #717 artefacts for this drained zero-economy owner."""
    require(account == store.pool_account and store.pool_active()
            and getattr(store, "mixed_active", lambda: False)()
            and getattr(store, "loss_active", lambda: False)() and store.zero_economy(account),
            "ARTEFACTS_UNAVAILABLE")
    live_items()
    connection = store.connection
    connection.execute("BEGIN IMMEDIATE")
    try:
        aggregate = store.read_profile(account)
        require(all(v["state"] == "available" for v in aggregate["vehicles"]), "VEHICLE_RESERVED")
        revision = aggregate["revision"]
        if "artefacts" in aggregate:
            connection.commit()
            return {"status": "active", "revision": revision, "catalog_sha256": MANIFEST_SHA256}
        require(revision < 2**31 - 1, "REVISION_EXHAUSTED")
        connection.execute(f"""CREATE TABLE IF NOT EXISTS {TABLE}(
            account_id TEXT PRIMARY KEY REFERENCES game_snapshot(account_id),
            state_json TEXT NOT NULL, state_sha256 TEXT NOT NULL)""")
        raw = canonical({"catalog_sha256": MANIFEST_SHA256, "depot": {}, "vehicles": {}})
        connection.execute(f"INSERT INTO {TABLE} VALUES (?,?,?)", (account, raw.decode("ascii"), sha(raw)))
        previous = connection.execute("SELECT profile_json FROM game_profiles WHERE account_id=?", (account,)).fetchone()[0]
        store._save_crew_projection(account, revision + 1, previous)
        store.read_profile(account)
        store._failpoint("before_commit")
        connection.commit()
        return {"status": "activated", "revision": revision + 1, "catalog_sha256": MANIFEST_SHA256}
    except Exception:
        connection.rollback()
        raise


def service(store, request, *, authenticated_account_id):
    account, key = request["account_id"], request["command_key"]
    require(account == authenticated_account_id == store.pool_account, "FOREIGN_ACCOUNT")
    connection = store.connection
    connection.execute("BEGIN IMMEDIATE")
    try:
        aggregate = store.read_profile(account)
        require("artefacts" in aggregate, "ARTEFACTS_UNAVAILABLE")
        public = connection.execute("SELECT native_id,profile_json FROM game_profiles WHERE account_id=?", (account,)).fetchone()
        require(request["native_database_id"] == public["native_id"], "FOREIGN_ACCOUNT")
        command, args = request["command"], request["arguments"]
        bound = sha(canonical({"request": request, "catalog": MANIFEST_SHA256, "version": SCHEMA_VERSION}))
        ledger = connection.execute("SELECT * FROM game_command_ledger WHERE account_id=? AND command_id=?",
                                    (account, key)).fetchone()
        replay = ledger is not None
        if replay:
            require(ledger["command_type"] == COMMAND and ledger["payload_sha256"] == bound, "DUPLICATE_PAYLOAD_MISMATCH")
            raw = ledger["result_json"].encode("ascii")
            require(len(raw) <= 2 * MAX_STATE_BYTES and sha(raw) == ledger["p09c_result_sha256"], "CORRUPT_ARTEFACT_STORE")
            proof = json_value(raw, limit=2 * MAX_STATE_BYTES, nodes=12000, depth=10)
            require(set(proof) == {"before", "after_sha256", "owned", "allow_purchase", "response"}
                    and type(proof["allow_purchase"]) is bool, "CORRUPT_ARTEFACT_STORE")
            before, owned, allow_purchase = proof["before"], proof["owned"], proof["allow_purchase"]
            require(ledger["source_revision"] == request["expected_revision"]
                    and ledger["destination_revision"] == ledger["source_revision"] + 1 <= aggregate["revision"],
                    "CORRUPT_ARTEFACT_STORE")
        else:
            require(aggregate["revision"] == request["expected_revision"], "STALE_REVISION")
            require(aggregate["revision"] < 2**31 - 1, "REVISION_EXHAUSTED")
            require(all(v["state"] == "available" for v in aggregate["vehicles"]), "VEHICLE_RESERVED")
            before, allow_purchase = aggregate["artefacts"], store.zero_economy(account)
            native = args[1] if command == 102 else args[0] if command == 104 else args[2] if command == 308 else None
            owned = _owned(aggregate["research"], native) if native is not None else None
        after = _plan(before, store.catalog, owned, command, args, allow_purchase=allow_purchase)
        research = {"vehicles": [owned] if owned else []}
        updates = projection_updates(before, after, research, request["wire_revision"], catalog=store.catalog)
        response = {"status": "researched", "account_id": account, "native_database_id": request["native_database_id"],
                    "command_key": key, "revision": request["expected_revision"] + 1,
                    "wire_revision": request["wire_revision"] + len(updates),
                    "update_hex": updates[0].hex(), "replayed": False, "result_code": 0}
        if len(updates) > 1:
            response["extra_update_hex"] = [raw.hex() for raw in updates[1:]]
        expected = {"before": before, "after_sha256": sha(canonical(after)), "owned": owned,
                    "allow_purchase": allow_purchase, "response": response}
        if replay:
            if expected != proof:
                # Historical ledgers hashed the old wire bytes. Reproduce that proof before returning corrected bytes.
                old_updates = projection_updates(before, after, research, request["wire_revision"],
                                                 catalog=store.catalog, historical_device_order=True)
                old_response = dict(response, update_hex=old_updates[0].hex(),
                                    wire_revision=request["wire_revision"] + len(old_updates))
                old_response.pop("extra_update_hex", None)
                if len(old_updates) > 1:
                    old_response["extra_update_hex"] = [raw.hex() for raw in old_updates[1:]]
                expected = dict(expected, response=old_response)
            require(expected == proof, "CORRUPT_ARTEFACT_STORE")
            connection.commit()
            return dict(response, replayed=True)
        save_state(connection, account, after)
        store._failpoint("after_artefact_state")
        store._save_crew_projection(account, response["revision"], public["profile_json"])
        raw = canonical(expected)
        require(len(raw) <= 2 * MAX_STATE_BYTES, "PROFILE_TOO_LARGE")
        connection.execute("INSERT INTO game_command_ledger VALUES (?,?,?,?,?,?,?,?)",
                           (account, key, COMMAND, bound, aggregate["revision"], response["revision"],
                            raw.decode("ascii"), sha(raw)))
        require(store.read_profile(account)["artefacts"] == after, "CORRUPT_ARTEFACT_STORE")
        store._failpoint("before_commit")
        connection.commit()
        return response
    except Exception:
        connection.rollback()
        raise
