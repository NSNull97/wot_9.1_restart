# -*- coding: utf-8 -*-
"""CREW-ANY: the one table of vehicles the crew/ammunition windows serve.

Default (flag off): every caller passes its accepted MS-1/IS-7 pins and gets
them back unchanged, so the frozen P04D-P04K/P09D behaviour is byte-identical.
With ``prepare --crew-any`` (requires ``--catalog-v1``) sr_interactive calls
``enable(catalog_v1_hints)`` once before the guards install: the windows then
serve every owned vehicle whose compact descriptor is a CAT-01 catalog kind,
after checking it against the client's own vehicle type (seats, roles, class,
gun, shells, maxAmmo). These are UI hints only; the server validates every
crew/ammunition command against its own catalog and stored contract.

Catalog-mode roster snapshots carry ``vehicles`` (owned inventory ID ->
[compact ID, type ID, class, primary roles]) and ``crews`` (inventory ID ->
seat list) instead of the legacy ``ms1_crew``/``is7_crew`` fields.
"""

LEGACY_FIELDS = ((1, 'ms1_crew'), (2, 'is7_crew'))
# Server pool crew contract v2 lifetime bound (tools/p04m_pool_crew.py). The
# client only bounds its readback with it; the quota is the server's
# freeTankmenLeft and the 16 Barracks berths stay the original stats.berths.
CATALOG_MAX_TANKMEN = 192
MAX_OWNED = 256
ROLES = ('commander', 'gunner', 'radioman', 'driver', 'loader')
HINT_FIELDS = set(('ammo_capacity', 'battle_admission', 'client_ui', 'crew_roles', 'descriptor_sha256', 'gun_compact_id',
                   'kind', 'max_hp', 'native_compact_id', 'primary_roles', 'seats', 'shell_compact_ids',
                   'turret_compact_id', 'type_id', 'vehicle_class'))
SCHEMA = 'wot091-server-catalog.v1'
_kinds = None
_sha256 = None

try:
    _INTEGER = (int, long)
except NameError:
    _INTEGER = (int,)


def _int(value, low, high):
    if type(value) not in _INTEGER or not low <= value <= high:
        raise ValueError('crew vehicle integer bound')
    return value


def enable(hints):
    """Bind the generated CAT-01 hints once; any malformed row refuses the flag."""
    global _kinds, _sha256
    if _kinds is not None:
        raise RuntimeError('CREW-ANY vehicle table already enabled')
    if getattr(hints, 'SCHEMA', None) != SCHEMA or len(getattr(hints, 'CATALOG_SHA256', '')) != 64:
        raise ValueError('CAT-01 client hints required')
    rows = hints.VEHICLES
    if type(rows) is not tuple or not 1 <= len(rows) <= 64:
        raise ValueError('bounded CAT-01 client hints required')
    kinds = {}
    for row in rows:
        if type(row) is not dict or set(row) != HINT_FIELDS:
            raise ValueError('exact CAT-01 client hint row required')
        seats = _int(row['seats'], 1, 8)
        roles = row['crew_roles']
        if (type(roles) is not tuple or len(roles) != seats
                or any(type(seat) is not tuple or not seat or any(role not in ROLES for role in seat) for seat in roles)
                or tuple(seat[0] for seat in roles) != tuple(row['primary_roles'])):
            raise ValueError('CAT-01 crew seats/roles differ')
        shells = row['shell_compact_ids']
        if type(shells) is not tuple or len(shells) != 3 or len(set(shells)) != 3:
            raise ValueError('CAT-01 three-shell hint required')
        for value in shells + (row['turret_compact_id'], row['gun_compact_id']):
            _int(value, 1, 65535)
        identity = _int(row['native_compact_id'], 1, 65535)
        if identity in kinds:
            raise ValueError('duplicate CAT-01 compact descriptor')
        kinds[identity] = dict(row, type_id=_int(row['type_id'], 0, 255), ammo_capacity=_int(row['ammo_capacity'], 1, 10000))
    _kinds, _sha256 = kinds, hints.CATALOG_SHA256
    return _sha256


def disable():
    """Tests and cleanup only."""
    global _kinds, _sha256
    _kinds = _sha256 = None


def enabled():
    return _kinds is not None


def catalog_sha256():
    return _sha256


def max_tankmen(legacy):
    return legacy if _kinds is None else CATALOG_MAX_TANKMEN


def digits(legacy=2):
    """Decimal digits of a Flash-supplied tankman identity string."""
    return legacy if _kinds is None else 3


def owned_bound(legacy):
    """Raw inventory dictionary bound (garage of up to 256 slots when enabled)."""
    return legacy if _kinds is None else MAX_OWNED


def nation_of(compact_id):
    """Nation of a vehicle compact descriptor: bits 4..7 (BATTLE-ANY: type IDs repeat across nations)."""
    return (compact_id >> 4) & 15


def kind_by_type(type_id, nation_id=0):
    """Catalog row for one trained/recruit (nation, vehicle type ID), or None."""
    rows = [row for row in (_kinds or {}).values()
            if row['type_id'] == type_id and nation_of(row['native_compact_id']) == nation_id]
    return rows[0] if len(rows) == 1 else None


def trained_types(legacy):
    return legacy if _kinds is None else tuple(sorted(row['type_id'] for row in _kinds.values()))


def trained_pairs():
    """(nation, vehicle type ID) of every catalog kind; a tankman is trained for one pair."""
    return tuple(sorted((nation_of(row['native_compact_id']), row['type_id']) for row in (_kinds or {}).values()))


def primary_roles(legacy):
    return legacy if _kinds is None else ROLES


def mounts(legacy):
    """P09D MOUNTS shape: compact ID -> (turret, gun, capacity, shells)."""
    if _kinds is None:
        return legacy
    return dict((identity, (row['turret_compact_id'], row['gun_compact_id'], row['ammo_capacity'], tuple(row['shell_compact_ids'])))
                for identity, row in _kinds.items())


def snapshot_fields(legacy):
    if _kinds is None:
        return legacy
    return (set(legacy) - set(field for _, field in LEGACY_FIELDS)) | set(('vehicles', 'crews'))


def _entry(row):
    return (row['native_compact_id'], row['type_id'], row['vehicle_class'], tuple(row['primary_roles']))


def vehicles(legacy, snapshot=None):
    """Inventory ID -> (compact ID, type ID, class, primary roles)."""
    if _kinds is None:
        return legacy
    if snapshot is not None:
        return checked_vehicles(snapshot.get('vehicles') if type(snapshot) is dict else None)
    return live_vehicles()


def checked_vehicles(value):
    if type(value) is not dict or len(value) > MAX_OWNED:
        raise ValueError('bounded owned catalog vehicle map required')
    result = {}
    for identity, entry in value.items():
        _int(identity, 1, 2147483647)
        if type(entry) not in (tuple, list) or len(entry) != 4:
            raise ValueError('exact owned catalog vehicle entry required')
        row = _kinds.get(entry[0]) if type(entry[0]) in _INTEGER else None
        if row is None or tuple(entry[:3]) != _entry(row)[:3] or tuple(entry[3]) != _entry(row)[3]:
            raise ValueError('owned vehicle differs from the CAT-01 catalog')
        result[identity] = _entry(row)
    return result


def combined(legacy, vehicle, slot, snapshot=None):
    """Source combined roles of one seat (PersonalCase skill eligibility)."""
    if _kinds is None:
        return legacy[vehicle][slot]
    return _kinds[vehicles(None, snapshot)[vehicle][0]]['crew_roles'][slot]


def crew_items(value):
    """[(inventory ID, seat list)] of a roster snapshot in either shape."""
    if _kinds is None:
        return [(vehicle, value[field]) for vehicle, field in LEGACY_FIELDS]
    crews = value['crews']
    if type(crews) is not dict or set(crews) != set(value['vehicles']):
        raise ValueError('owned crews and vehicles differ')
    return sorted(crews.items())


def crew_of(value, vehicle):
    if _kinds is None:
        return value[dict(LEGACY_FIELDS)[vehicle]]
    return value['crews'][vehicle]


def vehicle_id(value, snapshot=None):
    """A served vehicle inventory ID (legacy: 1 or 2)."""
    if _kinds is None:
        if type(value) not in _INTEGER or not 1 <= value <= 2:
            raise ValueError('source-bound native vehicle required')
        return value
    if type(value) not in _INTEGER or value not in vehicles(None, snapshot):
        raise ValueError('owned catalog vehicle required')
    return value


def _checked_item(identity, item):
    row = _kinds.get(getattr(item, 'intCD', None))
    if row is None:
        return None
    desc = item.descriptor
    roles = desc.type.crewRoles
    if (item.invID != identity or tuple(tuple(seat) for seat in roles) != row['crew_roles']
            or desc.type.compactDescr != row['native_compact_id'] or row['native_compact_id'] >> 8 != row['type_id']):
        raise ValueError('client vehicle type differs from the CAT-01 catalog')
    return _entry(row)


def live_vehicles():
    """Owned catalog vehicles from the synced original inventory cache."""
    from gui.shared import g_itemsCache
    if _kinds is None:
        raise RuntimeError('CREW-ANY table is not enabled')
    items = g_itemsCache.items
    owned = items.inventory.getCacheValue(1, {})
    if type(owned) is not dict:
        raise ValueError('original vehicle inventory cache required')
    descriptors = owned.get('compDescr', {})
    if type(descriptors) is not dict or len(descriptors) > MAX_OWNED:
        raise ValueError('bounded original owned vehicle cache required')
    result = {}
    for identity in sorted(descriptors):
        _int(identity, 1, 2147483647)
        item = items.getVehicle(identity)
        if item is None:
            raise ValueError('owned vehicle missing from original items cache')
        entry = _checked_item(identity, item)
        if entry is not None:
            result[identity] = entry
    return result


def live_crews(table):
    """Seat lists of the owned catalog vehicles, sorted by seat index (#717
    Vehicle.crew is (seat, Tankman) in TANKMEN_ROLES_ORDER, not seat order)."""
    from gui.shared import g_itemsCache
    result = {}
    for identity, entry in sorted(table.items()):
        vehicle = g_itemsCache.items.getVehicle(identity)
        crew = sorted(vehicle.crew, key=lambda pair: pair[0])
        if [pair[0] for pair in crew] != list(range(len(entry[3]))):
            raise ValueError('original vehicle crew slots differ')
        result[identity] = [None if member is None else member.invID for slot, member in crew]
    return result


def assignments(value):
    """Recompute rows' (vehicle, slot) from the seat lists (expectation helper)."""
    for row in value['tankmen']:
        row['vehicle_inventory_id'], row['slot'] = -1, -1
        for owner, crew in crew_items(value):
            if row['inventory_id'] in crew:
                row['vehicle_inventory_id'], row['slot'] = owner, crew.index(row['inventory_id'])
