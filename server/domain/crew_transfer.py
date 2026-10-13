"""Pure assignment transition over trusted owned records and vehicle seat roles.

This has no protocol IDs, nation/tank rules, database, pricing or native policy.
The caller establishes ownership, verified seat roles and specialization policy.
"""
from dataclasses import dataclass, replace


class AssignmentError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class Assignment:
    tankman_id: int
    role: str
    vehicle_id: int
    seat: int | None


def _require(ok, code):
    if not ok:
        raise AssignmentError(code)


def transfer_assignments(owned_members, target_vehicle_id, seat_roles, slot, tankman_id, barracks_capacity):
    """Return new records without mutating input; -1/-1 unloads the whole vehicle."""
    _require(type(owned_members) in (list, tuple) and 1 <= len(owned_members) <= 256, "CREW_BOUND")
    _require(type(target_vehicle_id) is int and 1 <= target_vehicle_id < 2**31, "UNKNOWN_VEHICLE")
    _require(type(barracks_capacity) is int and 0 <= barracks_capacity <= 256, "BARRACKS_BOUND")
    _require(type(seat_roles) in (list, tuple) and 1 <= len(seat_roles) <= 32, "SEAT_ROLES_BOUND")
    for roles in seat_roles:
        _require(type(roles) in (set, frozenset) and 1 <= len(roles) <= 16
            and all(type(role) is str and 1 <= len(role) <= 32 and role.isascii() for role in roles), "SEAT_ROLES_BOUND")
    seen, assigned = set(), set()
    for row in owned_members:
        _require(type(row) is Assignment and type(row.tankman_id) is int
            and 1 <= row.tankman_id < 2**31 and row.tankman_id not in seen, "INVALID_OWNED_CREW")
        _require(type(row.role) is str and 1 <= len(row.role) <= 32 and row.role.isascii(), "INVALID_OWNED_CREW")
        _require(type(row.vehicle_id) is int and (row.vehicle_id == -1 or 1 <= row.vehicle_id < 2**31), "INVALID_OWNED_CREW")
        if row.vehicle_id == -1:
            _require(row.seat is None, "INVALID_OWNED_CREW")
        else:
            _require(type(row.seat) is int and 0 <= row.seat < 32
                and (row.vehicle_id, row.seat) not in assigned, "DUPLICATE_CREW_ASSIGNMENT")
            assigned.add((row.vehicle_id, row.seat))
            if row.vehicle_id == target_vehicle_id:
                _require(row.seat < len(seat_roles) and row.role in seat_roles[row.seat], "INCOMPATIBLE_CREW_ROLE")
        seen.add(row.tankman_id)
    _require(type(slot) is int and -1 <= slot < len(seat_roles)
        and type(tankman_id) is int and (tankman_id == -1 or tankman_id in seen)
        and (slot != -1 or tankman_id == -1), "TRANSFER_SELECTION_UNSUPPORTED")
    target = next((row for row in owned_members if row.tankman_id == tankman_id), None)
    _require(target is None or target.role in seat_roles[slot], "INCOMPATIBLE_CREW_ROLE")
    current = [row for row in owned_members if row.vehicle_id == target_vehicle_id and (slot == -1 or row.seat == slot)]
    _require(not (target is None and not current) and not (target is not None and current == [target]), "NO_ASSIGNMENT_CHANGE")
    result = tuple(replace(row, vehicle_id=target_vehicle_id, seat=slot) if row == target else
        replace(row, vehicle_id=-1, seat=None) if row in current else row for row in owned_members)
    _require(sum(row.vehicle_id == -1 for row in result) <= barracks_capacity, "BARRACKS_FULL")
    return result
