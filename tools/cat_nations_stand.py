"""CAT-NATIONS: switch a stopped BATTLE-ANY stand to the client nation order, and back.

A stand already switched by ``full_test_stand.py battle-any`` (CAT-01 219b2f07)
cannot go through ``battle-any --disable``/enable again: its
``*.before-battle-any.*`` configs and database predate later stand stages.
This tool changes the stand in place instead:

  switch   --stand S --gateway G --pilot-sources P [--dry-run]
  rollback --stand S

``switch`` (stand stopped; preflight checks run before changing live state):
  1. moves ``battle-any-resources`` aside and regenerates it for every kind the
     catalog of this checkout admits, from the stand's five-kind template
     (``battle-profiles.before-battle-any.json``) and the qualified pilot sources;
  2. copies gateway.json, bridge.json, domain.json, battle-profiles.json and
     services.ps1 to ``*.before-cat-nations.*``;
  3. writes a recovery receipt and a verified database backup, then runs
     ``cat_nations_migrate apply`` (its own online backup + receipt
     in the stand, fixture caches of the old hash moved aside);
  4. writes the new manifest (same shared physics: it must embed this checkout's
     generated-definitions.json), the CAT-01 hash into the three configs and the
     given gateway into services.ps1;
  5. adds the depot rows of the new catalogue shells (``extend_catalog_shells``)
     and verifies the database markers.
``rollback`` keeps the switched database as ``game.after-cat-nations-<time>.sqlite``,
restores the recovery backup taken by step 3 (progress after the switch is not
carried back: the old catalogue refuses the extra depot rows), moves the fixture
caches and resources back and restores the five files. On any failure after the
recovery receipt is published, inspect it and the migrator receipt before an
explicit rollback; never assume that an exception implies no database change.
Interrupted rollback may be retried while all services remain stopped.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
import full_test_stand as stand_tool  # noqa: E402
import cat_nations_migrate as migrate  # noqa: E402

OLD_CATALOG = '219b2f07021603fea1f58bc78368990ae33632bb9bf70a1443996bec65d1cb8a'
FILES = stand_tool.BATTLE_ANY_FILES
SUFFIX = '.before-cat-nations'
RECEIPT = 'cat-nations-receipt.json'
RESOURCES = 'battle-any-resources'
TEMPLATE = 'battle-profiles.before-battle-any.json'
SCHEMA = 'cat-nations-stand.v1'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def write_receipt(path, value):
    """Publish a complete recovery record before touching the live stand state."""
    path = Path(path)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as stream:
            stream.write(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def saved(stand, name):
    return stand / name.replace('.', SUFFIX + '.', 1)


def stopped_stand(path):
    stand = Path(path).resolve(strict=True)
    require(stand.is_relative_to((stand_tool.LOCAL / 'stands').resolve()), 'stopped stand below this checkout local/stands required')
    stand_tool.stand_stopped(stand)
    require(not (stand / 'domain-process.json').exists(), 'domain has a live receipt; stop it first')
    return stand


def stamp():
    return datetime.datetime.now().strftime('%Y%m%d-%H%M%S')


def switch_checks(stand, gateway, sources):
    """Everything switch needs, read-only; returns the facts it acts on."""
    import catalog_v1_data
    require((stand / 'battle-any-receipt.json').is_file(), 'stand was not switched by full_test_stand.py battle-any')
    require(not (stand / RECEIPT).exists(), 'cat-nations already switched (receipt exists); rollback first')
    taken = [p.name for p in [saved(stand, n) for n in FILES] + [stand / (RESOURCES + SUFFIX)] if p.exists()]
    require(not taken, 'saved names taken: ' + ', '.join(taken))
    present = [n for n in FILES if (stand / n).is_file()]
    require({'gateway.json', 'bridge.json', 'battle-profiles.json', 'services.ps1'} <= set(present), 'stand files missing')
    for name in ('gateway.json', 'bridge.json'):
        require(read(stand / name).get('catalog') == dict(version=1, sha256=OLD_CATALOG), name + ': catalog is not ' + OLD_CATALOG[:8])
    if 'domain.json' in present:
        require(read(stand / 'domain.json').get('catalog_sha256') == OLD_CATALOG, 'domain.json: catalog is not ' + OLD_CATALOG[:8])
    template = read(stand / TEMPLATE)
    require(template.get('version') == 3 and len(template['profiles']) == 5, TEMPLATE + ': version3 five-kind manifest required')
    current = read(stand / 'battle-profiles.json')
    physics = Path(current['shared_physics']['path'])
    require(physics.is_file() and sha(physics) == current['shared_physics']['sha256'], 'shared physics manifest changed since battle-any')
    definitions = (ROOT / 'server/physics/Profiles/generated-definitions.json').read_bytes()
    require(definitions in (physics.parent / 'bin/MapDriveWorker.dll').read_bytes(),
            'shared physics does not embed this checkout generated-definitions.json; rebuild physics')
    gateway = Path(gateway).resolve(strict=True)
    require(gateway.is_relative_to((stand_tool.LOCAL / 'build').resolve()) and gateway.name == 'sr-gateway.exe',
            'gateway must be sr-gateway.exe below this checkout local/build')
    require(catalog_v1_data.CATALOG_SHA256.encode() in gateway.read_bytes(), 'gateway does not pin the CAT-01 catalog of this checkout')
    sources = Path(sources)
    sources = (sources if sources.is_absolute() else stand_tool.LOCAL / sources).resolve(strict=True)
    require(sources.is_relative_to(stand_tool.LOCAL.resolve()), 'pilot sources below this checkout local required')
    kinds = [v['kind'] for v in catalog_v1_data.VEHICLES
             if v['kind'] not in stand_tool.LEGACY_KINDS and v['battle_admission'] != 'none']
    bridge = read(stand / 'bridge.json')
    database = Path(bridge['game_database'])
    require(database.resolve().parent == stand, 'bridge game_database must be inside the stand')
    plan = migrate.plan(database, migrate.OLD, migrate.NEW, stand / 'fixtures')
    require(plan['changes'] > 0, 'database already names the new research catalogue')
    return dict(present=present, template=template, physics=current['shared_physics'], gateway=gateway,
                sources=sources, kinds=kinds, database=database, plan=plan, catalog=catalog_v1_data.CATALOG_SHA256)


def switch(args):
    import battle_any_stand
    stand = stopped_stand(args.stand)
    facts = switch_checks(stand, args.gateway, args.pilot_sources)
    if args.dry_run:
        print(json.dumps(dict(schema=SCHEMA, command='switch', dry_run=True, stand=str(stand), kinds=facts['kinds'],
                              catalog_sha256=facts['catalog'], gateway=str(facts['gateway']),
                              shared_physics=facts['physics'], files=facts['present'],
                              migration=facts['plan']), indent=2))
        return
    resources = stand / RESOURCES
    t26 = next(p for p in facts['template']['profiles'] if p['kind'] == 't26')
    fixtures = [[str(p), str(Path(p).with_name(Path(p).name + migrate.MOVED_SUFFIX))]
                for p in facts['plan']['fixture_dirs']]
    require(all(not Path(moved).exists() for _, moved in fixtures), 'fixture backup name taken')
    # These are auxiliary copies only; a failure here must not mutate live state.
    # Once the record exists, rollback can recover even if migrate commits and
    # then raises while renaming fixtures or writing its own receipt.
    for name in facts['present']:
        shutil.copy2(stand / name, saved(stand, name))
    backup = migrate.backup(facts['database'], stand, 'stand-recovery')
    require(migrate.verify(backup, migrate.OLD)['status'] == 'PASS', 'recovery backup is not old catalogue')
    operation = uuid.uuid4().hex
    receipt = dict(schema=SCHEMA, switched='PARTIAL', at=stamp(), operation=operation,
                   stand=str(stand), kinds=facts['kinds'], catalog_sha256=facts['catalog'],
                   previous_catalog_sha256=OLD_CATALOG,
                   research_catalog=dict(previous=migrate.OLD, current=migrate.NEW),
                   gateway=str(facts['gateway']), gateway_sha256=sha(facts['gateway']),
                   shared_physics=facts['physics'], saved_files=[saved(stand, n).name for n in facts['present']],
                   database=str(facts['database']), database_backup=str(backup), backup_sha256=sha(backup),
                   fixtures_moved=fixtures, native='NOT_RUN',
                   rollback='tools/cat_nations_stand.py rollback --stand <stand>')
    write_receipt(stand / RECEIPT, receipt)
    resources.rename(stand / (RESOURCES + SUFFIX))
    generated = battle_any_stand.generate(stand_tool.LOCAL, stand / TEMPLATE, Path(t26['pool']['path']),
                                          facts['sources'] / 'qualified', facts['sources'] / 'bundles',
                                          facts['kinds'], resources)
    database = migrate.migrate(facts['database'], stand, migrate.OLD, migrate.NEW, stand / 'fixtures', 'apply')
    require(database['fixtures_moved'] == fixtures, 'migration fixture plan changed; inspect receipts before rollback')
    receipt.update(resources=generated['outputs'], database_receipt=database['receipt'])
    manifest = read(resources / 'battle-profiles-battle-any.json')
    manifest['shared_physics'] = facts['physics']
    write(stand / 'battle-profiles.json', manifest)
    catalog = dict(version=1, sha256=receipt['catalog_sha256'])
    for name in ('gateway.json', 'bridge.json'):
        value = read(stand / name)
        value['catalog'] = catalog
        write(stand / name, value)
    if 'domain.json' in facts['present']:
        value = read(stand / 'domain.json')
        value['catalog_sha256'] = catalog['sha256']
        write(stand / 'domain.json', value)
    script = (stand / 'services.ps1').read_text(encoding='utf-8')
    lines = [l for l in script.splitlines() if l.startswith('$gatewayExe = ')]
    require(len(lines) == 1, 'services.ps1 gateway line not found')
    (stand / 'services.ps1').write_text(script.replace(lines[0], "$gatewayExe = '" + str(facts['gateway']) + "'"), encoding='utf-8')
    depot = stand_tool.extend_catalog_shells(stand)
    receipt.update(switched=True, depot_migration=depot, verify=migrate.verify(facts['database'], migrate.NEW))
    write_receipt(stand / RECEIPT, receipt)
    print(json.dumps({k: receipt[k] for k in ('kinds', 'catalog_sha256', 'gateway_sha256', 'database_backup',
                                              'fixtures_moved', 'rollback')}, indent=2))


def rollback(args):
    stand = stopped_stand(args.stand)
    require((stand / RECEIPT).is_file(), 'no ' + RECEIPT + ': stand was not switched by this tool')
    receipt = read(stand / RECEIPT)
    require(receipt.get('schema') == SCHEMA and receipt.get('operation'),
            'receipt has no recovery operation id; inspect and restore manually')
    operation = receipt['operation']
    require(len(operation) == 32 and all(c in '0123456789abcdef' for c in operation), 'invalid operation id')
    backup = Path(receipt['database_backup'])
    require(backup.is_file() and backup.parent == stand, 'database backup missing: ' + str(backup))
    require(sha(backup) == receipt.get('backup_sha256'), 'database backup hash changed')
    require(migrate.verify(backup, migrate.OLD)['status'] == 'PASS', 'backup is not at the old research catalogue')
    archive_suffix = '.restored-' + operation
    def available(name):
        return (stand / name) if (stand / name).is_file() else (stand / (name + archive_suffix))
    require(all(name in [saved(stand, n).name for n in FILES] for name in receipt['saved_files']), 'invalid saved file name')
    missing = [n for n in receipt['saved_files'] if not available(n).is_file()]
    require(not missing, 'saved state missing: ' + ', '.join(missing))
    for name in receipt['saved_files']:
        require(not ((stand / name).exists() and (stand / (name + archive_suffix)).exists()),
                'saved file archive name taken: ' + name)
    original_resources = stand / (RESOURCES + SUFFIX)
    require(original_resources.is_dir() or resources_present(stand), 'saved and current resources both missing')
    resource_archive = stand / (RESOURCES + '.after-cat-nations-' + operation)
    require(not (original_resources.exists() and resources_present(stand) and resource_archive.exists()),
            'resources archive name taken')
    database = Path(receipt['database'])
    require(database.resolve().parent == stand, 'database must be inside the stand')
    archived_receipt = stand / ('cat-nations-receipt.rolled-back-%s.json' % operation)
    require(not archived_receipt.exists(), 'receipt archive name taken')
    for original, moved in receipt['fixtures_moved']:
        original, moved = Path(original), Path(moved)
        require(original.resolve().is_relative_to((stand / 'fixtures').resolve()) and
                moved == original.with_name(original.name + migrate.MOVED_SUFFIX), 'invalid fixture path')
        require(original.exists() or moved.exists(), 'fixture original and backup both missing: ' + str(original))
        aside = original.with_name(original.name + '.after-cat-nations-' + operation)
        require(not (original.exists() and moved.exists() and aside.exists()), 'fixture archive name taken: ' + str(aside))
    kept = stand / ('game.after-cat-nations-%s.sqlite' % operation)
    if not kept.exists():
        temporary = stand / ('game.after-cat-nations-%s-%s.tmp' % (operation, uuid.uuid4().hex))
        try:
            stand_tool.copy_database(database, temporary)
            os.replace(temporary, kept)
        finally:
            temporary.unlink(missing_ok=True)
    stand_tool.copy_database(backup, database)
    fixtures = []
    for original, moved in receipt['fixtures_moved']:
        original, moved = Path(original), Path(moved)
        if not moved.exists():
            require(original.exists(), 'fixture original and backup both missing: ' + str(original))
            continue  # Not moved yet, or already restored by a previous rollback attempt.
        if original.exists():
            aside = original.with_name(original.name + '.after-cat-nations-' + operation)
            require(not aside.exists(), 'fixture archive name taken: ' + str(aside))
            original.rename(aside)
            fixtures.append([str(original), str(aside)])
        moved.rename(original)
        fixtures.append([str(moved), str(original)])
    if original_resources.exists():
        if resources_present(stand):
            aside = resource_archive
            require(not aside.exists(), 'resources archive name taken')
            (stand / RESOURCES).rename(aside)
        original_resources.rename(stand / RESOURCES)
    for name in receipt['saved_files']:
        target = stand / name.replace(SUFFIX + '.', '.', 1)
        shutil.copy2(available(name), target)
    check = migrate.verify(database, migrate.OLD)
    for name in receipt['saved_files']:
        if (stand / name).exists():
            destination = stand / (name + archive_suffix)
            require(not destination.exists(), 'saved file archive name taken: ' + str(destination))
            (stand / name).rename(destination)
    (stand / RECEIPT).rename(archived_receipt)
    print(json.dumps(dict(schema=SCHEMA, switched=False, stand=str(stand), kept_database=str(kept),
                          restored_from=str(backup), fixtures=fixtures, verify=check), indent=2))


def resources_present(stand):
    return (stand / RESOURCES).is_dir()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    s = sub.add_parser('switch')
    s.add_argument('--stand', required=True)
    s.add_argument('--gateway', required=True, help='sr-gateway.exe built from this checkout, below local/build')
    s.add_argument('--pilot-sources', required=True, help='dir with qualified/ and bundles/ of every admitted kind')
    s.add_argument('--dry-run', action='store_true', help='checks and migration plan only; writes nothing')
    r = sub.add_parser('rollback')
    r.add_argument('--stand', required=True)
    args = parser.parse_args(argv)
    (switch if args.command == 'switch' else rollback)(args)


if __name__ == '__main__':
    main()
