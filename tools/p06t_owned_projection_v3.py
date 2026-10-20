"""Explicit seven-profile/full-cache candidate, read-only and no publication.

The default path retains the old strict crew validator. The explicit ignored
OwnedV3Store supplies its separately validated current roster, including actual
foreign recruits. Neither projection path creates crew or ammunition.
"""
from copy import deepcopy
from p06t_owned_registry_v3 import *
from p09d_ammo_projection import encode
from p04m_pool_crew import native_crew
from p04m_pool_store import SHELL_ROWS
from p09c_ammo_catalog import SHELLS
from p09e_research_projection import garage_record


def build_caches(source, snapshot, catalog, encoding, registry, *, cache_generation, crew_validator=None):
    canonical_uuid(cache_generation)
    require(snapshot['account_id'] == source.profile['account_id'], 'FOREIGN_ACCOUNT')
    require(catalog.sha256 == SEMANTIC_SHA256 and encoding.sha256 == ENCODING_SHA256, 'SOURCE_MISMATCH')
    # A v3 current roster uses an explicit configured validator; there is no
    # fallback from failed old validation to a permissive foreign decoder.
    crew_inventory, assigned = (native_crew if crew_validator is None else crew_validator)(snapshot['crew_inventory'])
    state = deepcopy(source.trees['state.bin']); state['rev'] = 1
    research = snapshot['research']; inventory = state['inventory']
    require(len(research['vehicles']) <= research['garage_slots'] <= 8, 'GARAGE_BOUND')
    inventory[8] = crew_inventory
    for kind in range(2, 8):
        inventory[kind] = {encoding.encode(key): quantity for key, quantity in research['depot'].items()
            if catalog.modules[key]['native_compact_id'] & 15 == kind}
    records = {}
    by_inventory = {}
    for owned in research['vehicles']:
        native = owned['native_id']; integer(native, 1, 2**31-1)
        require(native not in records and owned['vehicle_inventory_id'] not in by_inventory, 'INVENTORY_SOURCE_MISMATCH')
        record = garage_record(catalog, owned)
        record['compDescr'] = encoding.encode_assembly(owned['vehicle_id'], owned['modules'])
        if native in assigned:
            record['crew'] = assigned[native]
        records[native] = record; by_inventory[owned['vehicle_inventory_id']] = owned
    shells = {key: shell.native_compact_id for key, shell in SHELLS.items()}
    for p in registry.profiles.values():
        for key, shot in zip(p.shell_ids, p.shots):
            require(key not in shells or shells[key] == shot[0], 'SHELL_SOURCE_MISMATCH')
            shells[key] = shot[0]
    inventory[10] = {shells[key]: quantity for key, quantity in snapshot['depot'].items()}
    for ammunition in snapshot['ammunition']:
        owned = by_inventory[ammunition['vehicle_id']]; profile = registry.by_vehicle[owned['vehicle_id']]
        require(ammunition['mount_id'] == profile.assembly_id and set(ammunition['loaded']) == set(profile.shell_ids), 'AMMUNITION_UNSUPPORTED')
        require(all(owned['modules'][role] == dict(profile.modules)[role] for role in ('turret', 'gun')), 'AMMUNITION_CONFIGURATION_UNSUPPORTED')
        rows = [value for key, shot in zip(profile.shell_ids, profile.shots) for value in (shot[0], integer(ammunition['loaded'][key], 0, profile.capacity))]
        require(sum(rows[1::2]) <= profile.capacity, 'AMMUNITION_UNSUPPORTED')
        native = owned['native_id']; record = records[native]
        record['shells'] = rows
        record['shellsLayout'] = {(encoding.encode(owned['modules']['turret']), encoding.encode(owned['modules']['gun'])): rows}
    fields = tuple(next(iter(records.values())))
    inventory[1] = {field: {native: row[field] for native, row in records.items()} for field in fields}
    locks = {}
    for vehicle in snapshot['vehicles']:
        require(vehicle['vehicle_id'] in by_inventory, 'INVENTORY_SOURCE_MISMATCH')
        if vehicle['state'] == 'reserved':
            require(type(vehicle['battle_id']) is str and vehicle['battle_id'], 'RESERVATION_MISMATCH')
            locks[by_inventory[vehicle['vehicle_id']]['native_id']] = 1
        else:
            require(vehicle['state'] == 'available' and vehicle['battle_id'] is None, 'RESERVATION_MISMATCH')
    require(len(locks) <= 1, 'RESERVATION_MISMATCH'); inventory[1]['lock'] = locks
    known = set(research['unlocked'])
    incomplete = {row['vehicle_id'] for row in catalog.unlocks if row['item_id'] not in known}
    stats = state['stats']
    stats.update(unlocks=sorted(encoding.encode(key) for key in known), eliteVehicles=sorted(encoding.encode(key) for key in catalog.vehicles if key not in incomplete),
        slots=research['garage_slots'], freeVehiclesLeft=research['garage_slots']-len(research['vehicles']),
        freeTMenLeft=snapshot['crew_inventory']['free_recruitment_left'], battlesTillCaptcha=1)
    old_by_cd = {item.legacy_cd: item for item in encoding.items.values()}
    stats['vehTypeXP'] = {encoding.encode(old_by_cd[key].resource_id, expected_kind='vehicle'): value for key, value in stats['vehTypeXP'].items()}
    for owned in research['vehicles']:
        stats['vehTypeXP'].setdefault(encoding.encode(owned['vehicle_id']), 0)
    shop = deepcopy(source.trees['shop.bin']); shop['rev'] = SHOP_REVISION
    shop['items']['itemPrices'] = {encoding.encode(key): (0, row['historical_price']['amount'] if row['historical_price']['currency'] == 'gold' else 0)
        for key, row in list(catalog.vehicles.items())+list(catalog.modules.items())}
    shop['items']['notInShopItems'] = sorted(encoding.encode(key) for key, row in catalog.vehicles.items()
        if row['not_in_shop'] or set(row['tags']) & {'secret', 'observer', 'event_battles', 'special'})
    # This source field is explicitly a set/list of native vehicle CDs. Do not
    # recursively replace arbitrary integers elsewhere in the shop.
    gold_vehicles = shop['items']['vehiclesToSellForGold']
    require(type(gold_vehicles) in (list, set, tuple), 'SHOP_SOURCE_UNSUPPORTED')
    shop['items']['vehiclesToSellForGold'] = type(gold_vehicles)(encoding.encode(old_by_cd[key].resource_id, expected_kind='vehicle') for key in gold_vehicles)
    shop['tankmanCost'] = [dict(credits=0, gold=0, isPremium=premium) for premium in (False, False, True)]
    dossier = deepcopy(source.trees['dossier.bin'])
    require(type(dossier) is tuple and len(dossier) == 2 and dossier[0] == 1 and type(dossier[1]) is list, 'DOSSIER_SOURCE_UNSUPPORTED')
    for row in dossier[1]:
        require(type(row) is tuple and len(row) == 3 and row[0] in old_by_cd and old_by_cd[row[0]].kind == 'vehicle'
            and old_by_cd[row[0]].native_cd == row[0] and type(row[2]) is bytes and len(row[2]) <= 1024, 'DOSSIER_REBUILD_REQUIRED')
    files = {name: encode(value, 32768, max_nodes=32768) for name, value in [('state.bin', state), ('shop.bin', shop), ('dossier.bin', dossier)]}
    # Every dossier key above was proven unchanged by the source encoding.
    # Retain its already audited payload bytes, including the opaque dossier.
    files['dossier.bin'] = source.raw['dossier.bin']
    binding = OwnerBinding(snapshot['account_id'], source.profile['native_database_id'], snapshot['revision'], cache_generation, registry.sha256)
    binding.validate()
    manifest = dict(version=3, schema=SCHEMA, policy_sha256=POLICY_SHA256, **as_binding(binding),
        semantic_catalog_sha256=SEMANTIC_SHA256, wire_revision=1, shop_revision=SHOP_REVISION,
        full_cache_required=True, files={name: dict(bytes=len(raw), sha256=sha(raw)) for name, raw in files.items()},
        foreign_crew_writer='NOT_IMPLEMENTED' if crew_validator is None else 'OWNED_V3_CANDIDATE', battle_admission=False)
    return dict(files=files, binding=binding, manifest=manifest, state=state, shop=shop, dossier=dossier)


def as_binding(binding):
    return dict(account_id=binding.account_id, native_database_id=binding.native_database_id,
        snapshot_revision=binding.snapshot_revision, cache_generation=binding.cache_generation,
        registry_sha256=binding.registry_sha256, encoding_sha256=binding.encoding_sha256)
