"""Bounded original #717 research/shop command adapter (no sockets or pickle).

Argument signatures come from Account.def and account_helpers/{Stats,Shop,
Inventory}.pyc. Method-byte attribution is retained as a source inference for
these command families until a P09E native capture exists. A decoded command
is a request, never an ownership or purchase authorization.
"""
from __future__ import annotations

from dataclasses import dataclass
import struct

from game_profile_tx import TransactionError

INT3_METHOD = 0x8E
INT4_METHOD = 0x90
INT_ARRAY_METHOD = 0x97
UNLOCK, EQUIP, BUY_VEHICLE, BUY_ITEM, BUY_AND_EQUIP = 201, 101, 301, 302, 308
MAX_BUNDLE = 512
MAX_COMMANDS = 16


def require(condition, code="INVALID_NATIVE_REQUEST"):
    if not condition:
        raise TransactionError(code)


@dataclass(frozen=True)
class NativeRequest:
    request_id: int
    command: int
    arguments: tuple[int, ...]


def decode(method: int, payload: bytes) -> NativeRequest:
    """Decode one complete VAR2 payload; reject unsupported shape and suffixes."""
    require(type(method) is int and type(payload) is bytes and 4 <= len(payload) <= 32)
    request_id, command = struct.unpack_from("<hh", payload)
    require(1 <= request_id <= 32767)
    if method == INT3_METHOD:
        require(command in (UNLOCK, EQUIP) and len(payload) == 20)
        arguments = struct.unpack_from("<qii", payload, 4)
    elif method == INT4_METHOD:
        require(command in (BUY_VEHICLE, BUY_ITEM) and len(payload) == 24)
        arguments = struct.unpack_from("<qiii", payload, 4)
    elif method == INT_ARRAY_METHOD:
        require(command == BUY_AND_EQUIP and len(payload) == 32)
        require(struct.unpack_from("<I", payload, 4)[0] == 6)
        arguments = struct.unpack_from("<6i", payload, 8)
    else:
        raise TransactionError("UNSUPPORTED_NATIVE_METHOD")
    return NativeRequest(request_id, command, arguments)


def decode_bundle(body: bytes) -> tuple[NativeRequest, ...]:
    """Validate the entire envelope before the caller can apply any command.

This accepts research/shop commands only. A live gateway must combine this with
its existing typed account decoder and defer writes until channel commit.
"""
    require(type(body) is bytes and 0 < len(body) <= MAX_BUNDLE)
    cursor, rows, ids = 0, [], set()
    while cursor < len(body):
        require(len(rows) < MAX_COMMANDS and len(body) - cursor >= 3)
        method, size = struct.unpack_from("<BH", body, cursor)
        end = cursor + 3 + size
        require(end <= len(body))
        row = decode(method, body[cursor + 3:end])
        require(row.request_id not in ids, "DUPLICATE_NATIVE_REQUEST")
        ids.add(row.request_id)
        rows.append(row)
        cursor = end
    return tuple(rows)


def validate_selection(request: NativeRequest, *, shop_revision: int) -> None:
    """Validate supported command options, retaining catalogue/state checks downstream.

The sole zero-cost exception is credits/XP. Gold conversion, paid removal,
crew and shell auto-purchase must never become free by a generic cost override.
"""
    require(type(request) is NativeRequest and type(shop_revision) is int and 0 < shop_revision < 2**31)
    a = request.arguments
    require(type(request.request_id) is int and 0 < request.request_id <= 32767
            and type(request.command) is int and type(a) is tuple
            and len(a) == {UNLOCK: 3, EQUIP: 3, BUY_VEHICLE: 4, BUY_ITEM: 4, BUY_AND_EQUIP: 6}.get(request.command)
            and all(type(v) is int for v in a))
    if request.command == UNLOCK:
        require(0 < a[0] < 2**31 and 0 <= a[1] < 4096 and a[2] == 0)
    elif request.command == EQUIP:
        require(0 < a[0] < 2**31 and 0 < a[1] < 2**31 and 0 <= a[2] < 2**31)
    elif request.command == BUY_VEHICLE:
        require(a[0] == shop_revision, "SHOP_REVISION_MISMATCH")
        require(0 < a[1] < 2**31)
        # Original Shop.buyVehicle sets the CREW/SHELLS flags; VehicleBuyer
        # sends tariff -1 exactly when no crew is bought.
        require(a[2:] == (0, -1), "AUTOBUY_CREW_SHELLS_UNSUPPORTED")
    elif request.command == BUY_ITEM:
        require(a[0] == shop_revision, "SHOP_REVISION_MISMATCH")
        require(0 < a[1] < 2**31 and 1 <= a[2] <= 100)
        require(a[3] == 0, "GOLD_CONVERSION_UNSUPPORTED")
    elif request.command == BUY_AND_EQUIP:
        require(a[0] == shop_revision, "SHOP_REVISION_MISMATCH")
        require(0 < a[1] < 2**31 and 0 < a[2] < 2**31 and 0 <= a[5] < 2**31)
        require(a[3] == 0 and a[4] == 0, "PAID_OR_SLOT_OPERATION_UNSUPPORTED")
    else:
        raise TransactionError("UNSUPPORTED_NATIVE_COMMAND")


def domain_request(request: NativeRequest, *, catalog, aggregate, account_id,
                   command_key, expected_revision, shop_revision):
    """Translate source-native IDs once at the boundary, using owned state only."""
    validate_selection(request, shop_revision=shop_revision)
    vehicle_ids = {v["native_compact_id"]: k for k, v in catalog.vehicles.items()}
    module_ids = {v["native_compact_id"]: k for k, v in catalog.modules.items()}
    owned_ids = {v["native_id"]: v["vehicle_inventory_id"] for v in aggregate["research"]["vehicles"]}
    def resolve(mapping, key, code):
        require(key in mapping, code)
        return mapping[key]
    a = request.arguments
    if request.command == UNLOCK:
        operation = "research"
        payload = {"vehicle_id": resolve(vehicle_ids, a[0], "UNKNOWN_VEHICLE"), "unlock_index": a[1]}
    elif request.command == BUY_VEHICLE:
        operation = "buy_vehicle"
        payload = {"vehicle_id": resolve(vehicle_ids, a[1], "UNKNOWN_VEHICLE")}
    elif request.command == BUY_ITEM:
        operation = "buy_module"
        payload = {"module_id": resolve(module_ids, a[1], "UNKNOWN_MODULE"), "count": a[2]}
    else:
        operation = "install" if request.command == EQUIP else "buy_equip"
        vehicle, module, gun = (a[0], a[1], a[2]) if request.command == EQUIP else (a[2], a[1], a[5])
        selected = resolve(module_ids, module, "UNKNOWN_MODULE")
        parts = [selected]
        if gun:
            require(catalog.modules[selected]["kind"] == "turret", "UNEXPECTED_GUN_SELECTION")
            selected_gun = resolve(module_ids, gun, "UNKNOWN_MODULE")
            require(catalog.modules[selected_gun]["kind"] == "gun", "INVALID_GUN_SELECTION")
            parts.append(selected_gun)
        payload = {"vehicle_inventory_id": resolve(owned_ids, vehicle, "UNOWNED_VEHICLE"), "modules": parts}
    return {"account_id": account_id, "command_key": command_key,
            "expected_revision": expected_revision, "operation": operation, "payload": payload}
