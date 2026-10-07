"""Independent native GUI evidence: normal entry, tooltip/Awards, exit and relogin.

The historical controlled-entry verifier is imported unchanged. This module does
not launch a client, alter fixtures, suppress errors or deserialize client objects.
Generated unit inputs test rejection logic only, never native compatibility.
"""
import argparse
import copy
from datetime import datetime
import math
from pathlib import Path, PureWindowsPath
import re
import struct
import zlib

import verify_unified_entry as entry
from client_audit import ROOT, config, output_dir, read_limited, save_json
from verify_hangar import EXE_SHA, digest, local_file, require, reviewed_screenshot
from py27_static import inspect, opcode_table
from packed_xml import decode as decode_packed_xml, walk as walk_packed_xml


SCHEMA = 1
TOOL = 'verify_hangar_ui'
STAGES = ('music', 'messenger', 'post_processing', 'native_entities', 'native_spaces',
          'gui_personality', 'area_destructibles', 'vibration', 'battle_replay', 'predefined_hosts')
SOURCE_NAMES = ('sr_interactive', 'project_auth', 'project_preferences', 'hangar_bootstrap')
OPTIONAL_SOURCE_NAMES = ('hangar_ui_probe', 'hangar_capabilities')
FAILURES = (ValueError, KeyError, OSError, TypeError, IndexError, UnicodeError,
            AttributeError, OverflowError, RecursionError, struct.error)
TOOLTIP = 'scripts/client/gui/Scaleform/framework/ToolTip.py'
TOOLTIP_META = 'scripts/client/gui/Scaleform/framework/entities/abstract/ToolTipMgrMeta.py'
AWARDS = 'scripts/client/gui/Scaleform/daapi/view/lobby/profile/ProfileAwards.py'
SECTION_META = 'scripts/client/gui/Scaleform/daapi/view/meta/ProfileSectionMeta.py'
PROFILE_SECTION = 'scripts/client/gui/Scaleform/daapi/view/lobby/profile/ProfileSection.py'
UI_SOURCES = {
    TOOLTIP: '93b44d6c3cf47e32eca5f035442db2e245af5fab3f23475823348b1b5ff91e04',
    TOOLTIP_META: '242f5b79ba1e198170fdcf5645a84a289af12a825eae3ac756618ace1182e89f',
    AWARDS: 'a541cfacf22e1188e9f9ea5f8240869871c22a3f150a235d489959009d744eed',
    SECTION_META: '69f8304325486819ce8f1b3c95ee2bb5fa14dbf686087541220b3601c9e31b6b',
    PROFILE_SECTION: 'c53f0ff21d029f6a1ead2582fa16c4443a5dc967be81a0d0e4d1e431b1752c2f',
}
UI_RETURNS = ((TOOLTIP, 'onCreateComplexTooltip', 65, 28),
              (TOOLTIP, '__genComplexToolTip', 73, 117),
              (TOOLTIP_META, 'as_showS', 33, 30),
              (AWARDS, '_sendAccountData', 16, 266),
              (SECTION_META, 'as_responseDossierS', 55, 30),
              (PROFILE_SECTION, '__receiveDossier', 30, 356),
              (PROFILE_SECTION, 'setActive', 69, 22))
PROFILE_STEPS = (('profileSummaryPage', 'ProfileSummaryPage', 0, 'summary'),
                 ('profileAwards', 'ProfileAwards', 1, 'awards'),
                 ('profileStatistics', 'ProfileStatistics', 2, 'statistics'),
                 ('profileAwards', 'ProfileAwards', 1, 'awards'),
                 ('profileSummaryPage', 'ProfileSummaryPage', 0, 'summary'),
                 ('hangar', 'Hangar', None, 'hangar'))
AWARDS_COUNTERS = ('packed_items', 'catalog_items', 'in_dossier_items',
                   'done_items', 'rare_items', 'nonzero_value_items')
AMMUNITION_SOURCE = 'scripts/client/gui/Scaleform/daapi/view/lobby/hangar/AmmunitionPanel.py'
AMMUNITION_SHA = '54d139dd4280314111ce509c15360da8d932cfbc356b30d40c1d9ca96c3addc8'
CATALOG_GENERATOR_SHA = 'ac60b6ea2be39eaa59327ef1eefb935595e8111ff13a12720ed3a3ebf02c7e79'
CATALOG_XML = {
    'ms-1.xml': 'a494bf04d29da7d066fd6923dbb75a79b947559a52405298c494a943c4b0c535',
    'components/chassis.xml': '37f8abc432f36e789dcacbeb12e15c8d56f6c21c3a8d717d87c5e23d070c8618',
    'components/turrets.xml': '2a5927fc6bd030056c25fdca4cf70543b001560d03274b0661389ed2e80c5537',
    'components/guns.xml': '889fe1564987566478c474ddfef21cbc7742d23bebd19f6a200c59bfafd7d87b',
    'components/engines.xml': '196e52561bd04d2d4e5838442f62704456f4b901627248e04b2c9bd37d32f60d',
    'components/radios.xml': '099292b8b5f5e250b2cd506419d18620f4f2504950776b54983bc303b2ca201a',
}
CATALOG_COMPONENTS = (
    ('chassis', 2, 'components/chassis.xml', 'T-18', 'ms-1.xml', '/chassis[1]/T-18[1]/price[1]'),
    ('turret', 3, 'components/turrets.xml', 'T-18_Standart', 'ms-1.xml', '/turrets0[1]/T-18_Standart[1]/price[1]'),
    ('gun', 4, 'components/guns.xml', '_37mm_Gochkins', 'components/guns.xml', '/shared[1]/_37mm_Gochkins[1]/price[1]'),
    ('engine', 5, 'components/engines.xml', 'MS-1', 'components/engines.xml', '/shared[1]/MS-1[1]/price[1]'),
    ('radio', 7, 'components/radios.xml', 'Alarm_flags', 'components/radios.xml', '/shared[1]/Alarm_flags[1]/price[1]'),
)


def result(condition, **detail):
    return {'status': 'PASS' if condition else 'FAIL', **detail}


def aggregate(checks):
    return {'status': entry.status_checks(checks), 'checks': checks}


def native_error_events(rows):
    """Return positions/types only; never copy possible credentials in tracebacks."""
    return [{'line': i + 1, 'event': row['event'], 'elapsed_seconds': row['elapsed_seconds']}
            for i, row in enumerate(rows)
            if row['event'].endswith(('_error', '_exception')) or row.get('outcome') == 'FAIL'
            or row['event'] == 'observation_limit']


def entry_mode(plan, rows, mode):
    settings = plan.get('settings', {})
    init = [r for r in rows if r['event'] == 'init']
    submitted = [r for r in rows if r['event'] == 'project_login_submit']
    control = [r for r in rows if r['event'] in ('diagnostic_login_submit', 'test_control_consumed', 'quit_requested')]
    common = (plan.get('mode') == 'interactive' and plan.get('normal_auto_login') is False
              and plan.get('normal_auto_quit') is False and len(init) == 1
              and len(submitted) == 1 and submitted[0].get('source') == 'original_LoginView.onLogin')
    if mode == 'normal':
        valid = (common and 'test_control' in settings and settings['test_control'] is None
                 and init[0].get('control_configured') is False and not control)
        return result(valid, mode=mode, observed_original_submissions=len(submitted),
                      diagnostic_control_events=len(control),
                      scope='No one-shot/autologin/autoquit. Physical keyboard input requires separate human evidence.')
    require(mode == 'controlled', 'unknown native entry mode')
    submitted_control = [r for r in control if r['event'] == 'diagnostic_login_submit']
    consumed = [r for r in control if r['event'] == 'test_control_consumed']
    source = submitted_control[0].get('source') if submitted_control else None
    valid = (common and type(settings.get('test_control')) is str and bool(settings['test_control'])
             and init[0].get('control_configured') is True and len(submitted_control) == 2
             and [r.get('phase') for r in submitted_control] == ['begin', 'return']
             and all(r.get('source') == source for r in submitted_control)
             and (source == 'original_LoginView.onLogin' or
                  (source == 'original_LoginPageMeta.as_doAutoLoginS'
                   and all(r.get('submit_via') == 'flash' for r in submitted_control)))
             and len(consumed) == 1 and consumed[0].get('input_removed') is True
             and consumed[0].get('credentials_present') is True)
    return result(valid, mode=mode, entry=source,
                  scope='Explicit controlled original LoginView submission; never evidence of physical typing.')


def lifecycle(rows, outcome, require_module_policy=False):
    """Engine fini and real process exit, without requiring a diagnostic quit call."""
    begins = [(i, r) for i, r in enumerate(rows) if r['event'] == 'fini_enter']
    ends = [(i, r) for i, r in enumerate(rows) if r['event'] == 'fini']
    cleanup = [(i, r) for i, r in enumerate(rows) if r['event'] == 'hangar_cleanup']
    repositories = [(i, r) for i, r in enumerate(rows) if r['event'] == 'account_repository_closed']
    stages = STAGES[:6] + ('module_capabilities',) + STAGES[6:] if require_module_policy else STAGES
    exact = len(begins) == len(ends) == len(repositories) == 1
    ordered = (exact and begins[0][0] < repositories[0][0] < ends[0][0]
               and [r.get('stage') for _, r in cleanup] == list(stages)
               and all(begins[0][0] < i < repositories[0][0] and r.get('outcome') == 'PASS' for i, r in cleanup))
    native_exit = (outcome.get('client_started') is True and type(outcome.get('exit_code')) is int
                   and outcome['exit_code'] == 0 and outcome.get('timed_out') is False
                   and outcome.get('forced_stop', False) is False and not outcome.get('capture_error')
                   and outcome.get('exe_sha256') == EXE_SHA)
    errors = native_error_events(rows)
    after = [r for r in errors if begins and r['line'] - 1 >= begins[0][0]]
    checks = {
        'engine_cleanup_order': result(bool(ordered), expected_stages=list(stages),
                                       observed_stages=[r.get('stage') for _, r in cleanup]),
        'native_process_exit': result(native_exit, exit_code=outcome.get('exit_code'),
                                     timed_out=outcome.get('timed_out'), forced_stop=outcome.get('forced_stop', False)),
        'no_trace_errors_during_or_after_fini': result(not after, errors=after),
    }
    callbacks = [r for r in rows if r['event'] == 'connection_callback']
    connected = [r for r in callbacks if r.get('stage') == 1 and r.get('status') == 'LOGGED_ON'
                 and r.get('native_connected') is True and r.get('after_fini') is False]
    before_fini = [r for r in callbacks if begins and r['elapsed_seconds'] < begins[0][1]['elapsed_seconds']]
    checks['original_connected_until_fini'] = result(
        len(connected) == 1 and exact and before_fini == connected
        and all(r.get('original_callback') == 'ConnectionManager.connectionWatcher' for r in callbacks),
        callbacks=callbacks)
    return aggregate(checks)


def module_policy_evidence(rows):
    """Verify own explicit availability policy, never an economic success."""
    policies = [(i, r) for i, r in enumerate(rows) if r['event'] == 'capability_policy']
    require(len(policies) == 2 and [r.get('phase') for _, r in policies] == ['install', 'restore'],
            'module policy install/restore lifecycle incomplete')
    start_index, start = policies[0]
    end_index, end = policies[1]
    require(start.get('module_changes_available') is False and start.get('module_details_available') is True
            and start.get('audited_source') == AMMUNITION_SOURCE and start.get('audited_pyc_sha256') == AMMUNITION_SHA
            and end.get('original_binding_restored') is True, 'module policy audit or binding restoration mismatch')
    original = config()[1]['original_client_root'] / 'res' / (AMMUNITION_SOURCE + 'c')
    require(digest(read_limited(original, 1024 * 1024)) == AMMUNITION_SHA, 'module policy original source hash changed')
    initialization = [(i, r) for i, r in enumerate(rows)
                      if r['event'] == 'hangar_bootstrap_step' and r.get('stage') == 'module_capabilities']
    cleanup = [(i, r) for i, r in enumerate(rows)
               if r['event'] == 'hangar_cleanup' and r.get('stage') == 'module_capabilities']
    require(len(initialization) == 2 and [r.get('phase') for _, r in initialization] == ['begin', 'return']
            and initialization[0][0] < start_index < initialization[1][0] < end_index
            and len(cleanup) == 1 and end_index < cleanup[0][0] and cleanup[0][1].get('outcome') == 'PASS',
            'module policy does not belong to original bootstrap/cleanup window')
    actions = [(i, r) for i, r in enumerate(rows) if r['event'] in ('capability_denied', 'capability_notice')]
    require(len(actions) <= 256 and len(actions) % 2 == 0, 'module denial/notice bound or missing return')
    invocations = []
    for offset in range(0, len(actions), 2):
        (index, denied), (notice_index, notice) = actions[offset:offset + 2]
        require(start_index < index < notice_index < end_index and denied['event'] == 'capability_denied'
                and denied.get('capability') == 'module_changes'
                and denied.get('action') in ('remove', 'install_or_purchase')
                and denied.get('origin') == 'project_test_service_policy' and denied.get('original_mutation_called') is False
                and notice['event'] == 'capability_notice' and notice.get('capability') == 'module_changes'
                and notice.get('phase') == 'return' and notice.get('channel') == 'original_SystemMessages_Warning',
                'module denial is not followed by its original warning return')
        invocations.append({'action': denied['action'], 'elapsed_seconds': denied['elapsed_seconds'],
                            'notice_return_seconds': notice['elapsed_seconds']})
    return {'status': 'PASS', 'original_source': str(original), 'original_sha256': AMMUNITION_SHA,
            'invocation': {'status': 'PASS' if invocations else 'NOT_RUN', 'observed': invocations,
                           'scope': 'Own UI denial and original warning return only; not a purchase, server authorization or pixel proof.'}}


def compiled_sources(install, plan):
    """Bind compiler metadata and bytes to the immutable installed file hashes."""
    sources = plan.get('sources')
    require(type(sources) is list and len(SOURCE_NAMES) <= len(sources) <= len(SOURCE_NAMES) + len(OPTIONAL_SOURCE_NAMES),
            'compiled source list shape')
    names = {r.get('path') for r in sources}
    required = {'client_patch/' + name + '.py' for name in SOURCE_NAMES}
    optional = {'client_patch/' + name + '.py' for name in OPTIONAL_SOURCE_NAMES}
    require(len(names) == len(sources) and required <= names <= required | optional,
            'unknown or missing personality source')
    evidence = []
    for source in sources:
        name = Path(source['path']).stem
        require(re.fullmatch(r'[0-9a-f]{64}', source.get('sha256', '')) is not None, 'source digest shape')
        metadata = entry.json_data(local_file(install, source['metadata'], 16384))
        compiled = local_file(install, source['compiled'], 1024 * 1024)
        relative = 'res_mods/0.9.1/scripts/client/' + name + '.pyc'
        installed = [r for r in plan['files'] if r.get('path') == relative]
        require(len(installed) == 1 and installed[0].get('runtime_mutable') is False, 'compiled source install ambiguity')
        require(metadata.get('source') == name + '.py' and metadata.get('source_sha256') == source['sha256']
                and metadata.get('source_executed') is False and metadata.get('magic') == '03f30d0a'
                and metadata.get('compiler', '').startswith('2.7.3 '), 'compiler source/runtime metadata mismatch')
        require(compiled[:4] == bytes.fromhex('03f30d0a') and digest(compiled) == metadata.get('pyc_sha256')
                == installed[0].get('installed_sha256'), 'compiled/installed personality hash mismatch')
        evidence.append({'source': source['path'], 'source_sha256': source['sha256'],
                         'installed_file': relative, 'pyc_sha256': digest(compiled)})
    return {'status': 'PASS', 'sources': evidence,
            'scope': 'Frozen plan/compiler/installed-byte chain; historical sources need not match current working files.'}


def native_common(install, plan, outcome, rows, trace_info, mode):
    # Reuse unchanged low-level checks. Controlled-only conclusions from the old
    # report are deliberately not copied or rewritten as successes.
    old = entry.native_common(install, plan, outcome, rows, trace_info)['checks']
    inherited = ('legacy_service_dialog_policy', 'native_runtime', 'original_login_view',
                 'native_errors', 'process_restore', 'installed_code_unchanged_during_run')
    checks = {name: old[name] for name in inherited}
    checks['entry_mode'] = entry_mode(plan, rows, mode)
    require_policy = any(r.get('path') == 'client_patch/hangar_capabilities.py' for r in plan.get('sources', []))
    checks['engine_lifecycle'] = lifecycle(rows, outcome, require_policy)
    checks['compiled_sources'] = compiled_sources(install, plan)
    if require_policy:
        checks['module_policy'] = module_policy_evidence(rows)
    else:
        require(not any(r['event'] in ('capability_policy', 'capability_denied', 'capability_notice') for r in rows),
                'module policy events without a compiled audited policy source')
    return {**aggregate(checks), 'trace': trace_info}


def screenshot_images(install, plan, local_root):
    folder = entry.owned(plan['settings']['screenshot_dir'], local_root, True)
    paths = list(folder.iterdir())
    require(len(paths) <= 16, 'GUI screenshot count bound')
    images = []
    for path in sorted(paths):
        require(path.is_file() and path.suffix.lower() == '.png', 'unmeasured screenshot type')
        data = local_file(folder, path.name, 20 * 1024 * 1024)
        require(len(data) >= 33 and data[:16] == b'\x89PNG\r\n\x1a\n\0\0\0\rIHDR', 'native PNG header')
        width, height = struct.unpack_from('>II', data, 16)
        require(640 <= width <= 8192 and 480 <= height <= 8192
                and zlib.crc32(data[12:29]) == int.from_bytes(data[29:33], 'big'), 'native PNG dimensions/CRC')
        images.append({'file': 'screenshots/' + path.name, 'path': str(path), 'sha256': digest(data),
                       'bytes': len(data), 'width': width, 'height': height})
    return images


def hangar_visual(install, images):
    path = install / 'visual-review.json'
    if not path.exists():
        return {'status': 'NOT_RUN', 'reason': 'Actual native Hangar PNG visual review absent'}
    raw = read_limited(path, 16384)
    review = entry.json_data(raw)
    return result(reviewed_screenshot(images, review), review=review, review_sha256=digest(raw),
                  scope='Root inspection of the hash-bound native PNG; file existence alone proves no displayed content.')


def profile_snapshot(expected):
    return {'account_id': expected['account_id'], 'native_database_id': expected['native_id'],
            'nickname': expected['name'], 'snapshot_revision': 1,
            'fixture_manifest_sha256': expected['manifest_sha256'],
            'fixture_files': {name: {'sha256': digest(data), 'bytes': len(data)} for name, data in expected['raw'].items()},
            'resources': expected['resources'], 'statistics': expected['manifest']['statistics'],
            'vehicle': expected['vehicle']}


def mounted_catalog_sources(source, native):
    """Independently check the five measured MS-1 XML nodes, never generate data."""
    vehicle = native['vehicle']
    descriptor = bytes.fromhex(vehicle['compact_descr_hex'])
    require(vehicle['type_name'] == 'ussr:MS-1' and vehicle['type_compact_descr'] == 3329
            and len(descriptor) == 15 and descriptor[:2] == b'\x01\x0d' and descriptor[-1] == 0,
            'unmeasured mounted catalogue vehicle/descriptor')
    ids = dict(zip(('chassis', 'engine', 'fuelTank', 'radio', 'turret', 'gun'), struct.unpack('<6H', descriptor[2:14])))
    rows = source.get('mounted_module_price_sources')
    require(type(rows) is list and len(rows) == 5 and {r.get('component') for r in rows} == {r[0] for r in CATALOG_COMPONENTS},
            'mounted catalogue provenance count/names')
    original = config()[1]['original_client_root'].resolve()
    directory = original / 'res/scripts/item_defs/vehicles/ussr'
    resources, evidence, prices = {}, [], {}

    def xml(relative):
        if relative not in resources:
            path = (directory / relative).resolve(strict=True)
            require(path.is_relative_to(original), 'mounted XML path escapes original client')
            raw = read_limited(path, 2 * 1024 * 1024)
            require(digest(raw) == CATALOG_XML[relative], 'mounted original XML hash changed')
            resources[relative] = (path, dict(walk_packed_xml(decode_packed_xml(raw, max_bytes=2 * 1024 * 1024))))
        return resources[relative]

    for kind, type_id, id_file, name, price_file, price_node in CATALOG_COMPONENTS:
        row = next(r for r in rows if r['component'] == kind)
        compact = (ids[kind] << 8) | type_id
        require(type(row.get('compact_descr')) is int and row['compact_descr'] == compact
                == vehicle['components'][kind]['compact_descr'], 'mounted price reference differs from native installed module')
        id_source, price_source = row.get('id_source'), row.get('price_source')
        require(type(id_source) is dict and type(price_source) is dict, 'mounted source metadata shape')
        records = []
        for metadata, relative, node, value in ((id_source, id_file, '/ids[1]/' + name + '[1]', ids[kind]),
                                               (price_source, price_file, price_node, 0)):
            path, values = xml(relative)
            require(type(metadata.get('file')) is str and Path(metadata['file']).resolve(strict=True) == path
                    and metadata.get('sha256') == CATALOG_XML[relative] and metadata.get('node') == node
                    and type(metadata.get('source_value')) is int and metadata['source_value'] == value
                    and type(values.get(node)) is int and values[node] == value, 'mounted XML node/value provenance mismatch')
            records.append({'file': str(path), 'sha256': CATALOG_XML[relative], 'node': node, 'value': value})
        _, price_values = xml(price_file)
        require(price_source.get('gold_child_present') is False and price_node + '/gold[1]' not in price_values,
                'mounted display price currency mismatch')
        prices[compact] = (0, 0)  # Verified original XML amount, not a trading capability.
        evidence.append({'component': kind, 'compact_descr': compact, 'sources': records})
    return prices, evidence


def catalog_shop_delta(before, after, prices):
    require(type(before) is dict and type(before.get(b'rev')) is int and before[b'rev'] == 1
            and type(after) is dict and type(after.get(b'rev')) is int and after[b'rev'] == 2,
            'catalogue upgrade must preserve domain snapshot and change shop revision1 to2')
    require(type(prices) is dict and len(prices) == 5 and set(prices) == {6658, 5891, 5892, 3589, 7}
            and all(entry.same_literal(v, (0, 0)) for v in prices.values()), 'unmeasured mounted catalogue delta')
    wanted = copy.deepcopy(before)
    wanted[b'rev'] = 2
    require(wanted[b'items'][b'itemPrices'] == {3329: (0, 0)} and wanted[b'items'][b'notInShopItems'] == [3329],
            'catalogue baseline is not the measured vehicle-only unavailable shop')
    wanted[b'items'][b'itemPrices'].update(prices)
    wanted[b'items'][b'notInShopItems'].extend(sorted(prices))
    require(entry.same_literal(wanted, after), 'catalogue changes extend beyond five mounted display references')


def catalog_identity_inputs(registration, credentials, case, fixture, baseline):
    # The old verifier checks the actual immutable r1. No altered copy or changed
    # decoder is passed to it; the independently checked delta becomes the exact
    # expected stream afterwards. A fresh account without r1 is outside this card.
    require(fixture != baseline, 'catalogue upgrade must use a separate fixture directory')
    expected, password, identity = entry.identity_inputs(registration, credentials, case, baseline)
    manifest_raw = local_file(fixture, 'manifest.json', 65536)
    manifest = entry.json_data(manifest_raw)
    old_manifest = expected['manifest']
    require(type(manifest) is dict and len(manifest) == 16
            and set(manifest) == set(old_manifest) | {'compatibility_catalog_revision'}
            and type(manifest.get('compatibility_catalog_revision')) is int and manifest['compatibility_catalog_revision'] == 2,
            'unknown compatibility catalogue manifest schema/version')
    changing = {'files', 'generator', 'native_descriptors', 'compatibility_catalog_revision'}
    require(all(manifest[k] == old_manifest[k] for k in set(old_manifest) - changing), 'catalogue altered profile/domain metadata')
    require(manifest.get('generator', {}).get('sha256') == CATALOG_GENERATOR_SHA, 'unmeasured catalogue generator version')
    require(local_file(fixture, 'profile-input.json', 65536) == local_file(baseline, 'profile-input.json', 65536),
            'catalogue upgrade changed stable profile input')
    compatibility_raw = local_file(fixture, 'compatibility.json', 65536)
    compatibility = entry.json_data(compatibility_raw)
    old_compatibility = entry.json_data(local_file(baseline, 'compatibility.json', 65536))
    require(type(compatibility) is dict and set(compatibility) == set(old_compatibility) | {'compatibility_catalog_revision'}
            and type(compatibility.get('compatibility_catalog_revision')) is int and compatibility['compatibility_catalog_revision'] == 2
            and all(compatibility[k] == old_compatibility[k] for k in set(old_compatibility) - {'compatibility_catalog_revision'}),
            'catalogue upgrade changed stable native identity mapping')
    files = manifest.get('files')
    require(type(files) is list and len(files) == 3 and {r.get('file') for r in files} == set(expected['raw']),
            'catalogue fixture file set')
    raw = {}
    for item in files:
        data = local_file(fixture, item['file'], entry.MAX_RAW)
        require(type(item.get('bytes')) is int and item['bytes'] == len(data) and item.get('sha256') == digest(data),
                'catalogue fixture bytes/hash mismatch')
        entry.literal(data)
        raw[item['file']] = data
    require(all(raw[name] == expected['raw'][name] for name in ('state.bin', 'dossier.bin')),
            'catalogue upgrade mutated player state or dossier')
    source = manifest.get('native_descriptors')
    require(type(source) is dict and set(source) == set(old_manifest['native_descriptors']) | {'mounted_module_price_sources'}
            and all(source.get(k) == old_manifest['native_descriptors'][k] for k in ('bytes', 'sha256', 'reference_price_source')),
            'catalogue native vehicle provenance changed')
    native_path = entry.owned(source['file'], config()[1]['local_artifacts_root'])
    native_raw = read_limited(native_path, entry.MAX_RAW)
    require(len(native_raw) == source['bytes'] and digest(native_raw) == source['sha256'], 'catalogue native descriptor hash mismatch')
    prices, evidence = mounted_catalog_sources(source, entry.json_data(native_raw))
    catalog_shop_delta(entry.literal(expected['raw']['shop.bin']), entry.literal(raw['shop.bin']), prices)
    delta = {'status': 'PASS', 'baseline': str(baseline), 'baseline_manifest_sha256': expected['manifest_sha256'],
             'state_and_dossier_byte_identical': True, 'profile_input_byte_identical': True, 'native_identity_mapping_unchanged': True,
             'shop_revision': 2, 'account_snapshot_revision': 1, 'native_resource_provenance': evidence,
             'scope': 'Only five mounted UI display references added. Purchases/installation remain unavailable; not native rendering proof.'}
    expected = {**expected, 'manifest': manifest, 'manifest_sha256': digest(manifest_raw), 'raw': raw}
    identity = {**identity, 'fixture_manifest_sha256': digest(manifest_raw), 'compatibility_sha256': digest(compatibility_raw),
                'compatibility_catalog': delta}
    return expected, password, identity


def session_status(report):
    """A clean auth/data/exit session is distinct from complete GUI coverage."""
    names = ('wire', 'backend', 'native_common', 'native_hangar', 'visual')
    return entry.status_checks({**report.get('checks', {}), **{name: report.get(name, {'status': 'NOT_RUN'}) for name in names}})


def compiled_snapshot(report):
    compiled = report['native_common']['checks']['compiled_sources']
    rows = compiled.get('sources')
    require(compiled.get('status') == 'PASS' and type(rows) is list and 4 <= len(rows) <= 6,
            'paired run compiled-source evidence incomplete')
    result = {}
    for row in rows:
        source, sha, pyc = row.get('source'), row.get('source_sha256'), row.get('pyc_sha256')
        require(type(source) is str and source not in result and type(sha) is str and type(pyc) is str
                and re.fullmatch('[0-9a-f]{64}', sha) is not None and re.fullmatch('[0-9a-f]{64}', pyc) is not None,
                'paired compiled-source identity/hash shape')
        result[source] = (sha, pyc, row['installed_file'])
    return result


def relogin(previous_path, report, local_root):
    if previous_path is None:
        return {'status': 'NOT_RUN', 'reason': 'A single process cannot prove exit/relogin identity persistence'}
    previous_path = entry.owned(previous_path, local_root)
    raw = read_limited(previous_path, 8 * 1024 * 1024)
    previous = entry.json_data(raw)
    require(previous.get('schema_version') == SCHEMA and previous.get('tool') == TOOL, 'unknown previous UI report schema')
    require(previous.get('install') != report['install'], 'relogin must use a separate captured client run')
    previous_install = entry.owned(previous['install'], local_root, True)
    require(digest(local_file(previous_install, 'install-plan.json', 256 * 1024))
            == previous['checks']['installation_plan']['sha256'], 'previous installation evidence changed')
    previous_trace = entry.owned(previous['native_common']['trace']['path'], local_root)
    require(digest(read_limited(previous_trace, 17 * 1024 * 1024)) == previous['native_common']['trace']['sha256']
            and digest(local_file(previous_install, 'wire/capture.json', 8 * 1024 * 1024)) == previous['wire']['capture_sha256'],
            'previous native trace/capture evidence changed')
    require(previous.get('session_status') == 'PASS' and report.get('session_status') == 'PASS'
            and session_status(previous) == session_status(report) == 'PASS',
            'relogin requires two complete clean sessions, including actual Hangar review')
    for key in ('wire', 'backend', 'native_common', 'native_hangar'):
        require(previous.get(key, {}).get('status') == 'PASS' and report.get(key, {}).get('status') == 'PASS',
                'relogin requires both native auth/data/clean-exit runs: ' + key)
    require(previous.get('identity_snapshot') == report.get('identity_snapshot'), 'relogin identity or server profile changed')
    require(compiled_snapshot(previous) == compiled_snapshot(report), 'relogin compiled source or bytecode version differs')
    before, after = previous['process'], report['process']
    start, finish = datetime.fromisoformat(after['started_utc']), datetime.fromisoformat(before['finished_utc'])
    require(start.tzinfo is not None and finish.tzinfo is not None and start >= finish, 'relogin process windows overlap/unbound')
    require(previous['wire']['capture_sha256'] != report['wire']['capture_sha256'], 'reused wire corpus is not a relogin')
    if previous['process']['gateway_run'] == report['process']['gateway_run']:
        require(previous['backend']['session_id'] != report['backend']['session_id'], 'same live gateway session reused')
    return {'status': 'PASS', 'previous_report': str(previous_path), 'previous_report_sha256': digest(raw),
            'account_id': report['identity_snapshot']['account_id'],
            'native_database_id': report['identity_snapshot']['native_database_id'],
            'compiled_sources_equal': True, 'previous_gui_status': previous.get('gui', {}).get('status', 'NOT_RUN'),
            'scope': 'Two clean native sessions with identical compiled sources preserve UUID/native identity and exact snapshot. This does not promote unperformed GUI actions.'}


def card_gui(report, previous_path, local_root):
    current = report['gui']
    if current['status'] in ('PASS', 'FAIL'):
        return {'status': current['status'], 'coverage': 'current_run',
                'scope': 'Current GUI failure cannot be replaced by an earlier success.'}
    if previous_path is None or report['relogin']['status'] != 'PASS':
        return {'status': 'NOT_RUN', 'coverage': 'none', 'reason': 'No current complete GUI proof or verified earlier paired run'}
    previous_path = entry.owned(previous_path, local_root)
    raw = read_limited(previous_path, 8 * 1024 * 1024)
    require(digest(raw) == report['relogin']['previous_report_sha256'], 'previous report changed during verification')
    previous = entry.json_data(raw)
    if previous.get('session_status') != 'PASS' or previous.get('gui', {}).get('status') != 'PASS':
        return {'status': 'NOT_RUN', 'coverage': 'none', 'reason': 'Previous paired run has no clean complete GUI proof'}
    require(compiled_snapshot(previous) == compiled_snapshot(report), 'paired GUI coverage source version differs')
    require(previous['identity_snapshot'] == report['identity_snapshot'], 'paired GUI identity/profile differs')
    return {'status': 'PASS', 'coverage': 'previous_paired_run', 'previous_report': str(previous_path),
            'previous_report_sha256': digest(raw),
            'scope': 'The earlier clean run exercised GUI on identical source/identity. Current GUI remains NOT_RUN.'}


def original_ui_contracts():
    """Inspect original bytecode as bounded data, never import its code objects."""
    opcode = read_limited(ROOT / 'local/vendor/cpython-2.7.18/opcode.py', 32768)
    require(digest(opcode) == 'acfe212847ecb81ca28bdab976a3caacff3568b45a9e8ca78d6957f9f3ef4884',
            'historical opcode source hash')
    table = opcode_table(opcode.decode('utf8'))
    original = config()[1]['original_client_root'] / 'res'
    contracts, files = {}, []
    for source, sha in UI_SOURCES.items():
        path = original / (source + 'c')
        data = read_limited(path, 1024 * 1024)
        require(digest(data) == sha, 'original GUI source hash mismatch: ' + source)
        records = inspect(data, table)
        for record in records:
            method = record['qualified_name'].split('.')[-1]
            key = (record['source_filename'], method, record['firstlineno'])
            require(key not in contracts, 'ambiguous original GUI code identity')
            contracts[key] = {op['offset'] for op in record['instructions'] if op['opname'] == 'RETURN_VALUE'}
        for filename, method, line, offset in UI_RETURNS:
            if filename == source:
                require(offset in contracts.get((filename, method, line), set()), 'original GUI return offset mismatch')
                if source in (TOOLTIP_META, SECTION_META):
                    matching = [r for r in records if r['qualified_name'].split('.')[-1] == method and r['firstlineno'] == line]
                    ops = matching[0]['instructions']
                    index = next(i for i, op in enumerate(ops) if op['offset'] == offset)
                    require(index > 0 and ops[index - 1]['opname'] == 'CALL_FUNCTION'
                            and any(op.get('value') == 'flashObject' for op in ops[:index]), 'GUI render branch is not Flash-bound')
        files.append({'path': str(path), 'sha256': sha})
    return contracts, {'status': 'PASS', 'opcode_sha256': digest(opcode), 'sources': files,
                       'required_returns': [{'source': s, 'method': m, 'source_line': l, 'offset': o}
                                            for s, m, l, o in UI_RETURNS]}


def bounded_plain(value, depth=0, budget=None):
    """A diagnostic truncation marker is not evidence of the omitted GUI data."""
    if budget is None:
        budget = [4096]
    budget[0] -= 1
    if depth > 12 or budget[0] < 0:
        return False
    if value is None or type(value) in (bool, int):
        return True
    if type(value) is float:
        return math.isfinite(value)
    if type(value) is str:
        return len(value) <= 4096
    if type(value) is list:
        return len(value) <= 256 and all(bounded_plain(v, depth + 1, budget) for v in value)
    if type(value) is dict:
        return (len(value) <= 256 and 'truncated' not in value and 'unsupported_type' not in value
                and all(type(k) is str and len(k) <= 4096 and bounded_plain(v, depth + 1, budget)
                        for k, v in value.items()))
    return False


def profiled_pairs(rows, event_name, contracts, sources):
    """Validate original call identity/stack pairing before interpreting its fields."""
    selected = [(i, r) for i, r in enumerate(rows) if r['event'] == event_name and r.get('source') in sources]
    require(len(selected) <= 10000, 'GUI method observation count bound')
    stack, seen, pairs, last = [], set(), [], 0
    for index, row in selected:
        key = (row.get('source'), row.get('method'), row.get('source_line'))
        require(key in contracts, 'unknown original GUI method/source/line')
        call_id, owner = row.get('call_id'), row.get('owner_id')
        require(type(call_id) is int and 0 < call_id < 1000000 and type(owner) is int and owner > 0,
                'missing/bad profiled call identity')
        if row.get('phase') == 'call':
            require(row.get('offset') == -1 and call_id > last and call_id not in seen and len(stack) < 256,
                    'duplicate/out-of-order GUI call ID or nesting overflow')
            seen.add(call_id)
            last = call_id
            stack.append((index, row))
        else:
            require(row.get('phase') == 'return' and stack, 'unmatched original GUI return')
            call_index, call = stack.pop()
            require(call_id == call['call_id'] and owner == call['owner_id']
                    and key == (call['source'], call['method'], call['source_line']), 'GUI return belongs to another call/receiver')
            require(row.get('offset') in contracts[key], 'original GUI method did not reach a normal RETURN_VALUE')
            pairs.append({'call': call, 'returned': row, 'begin': call_index, 'end': index})
    require(not stack, 'original GUI calls missing completion')
    return pairs


def inside(parent, child):
    return (parent['begin'] < child['begin'] < child['end'] < parent['end']
            and parent['call']['owner_id'] == child['call']['owner_id'])


def tooltip_evidence(rows, contracts):
    pairs = profiled_pairs(rows, 'native_tooltip_call', contracts, {TOOLTIP, TOOLTIP_META})
    outer = [p for p in pairs if p['call']['source'] == TOOLTIP and p['call']['method'] == 'onCreateComplexTooltip']
    if not outer:
        return {'status': 'NOT_RUN', 'reason': 'Original complex-tooltip call/return not observed', 'displays': []}
    positive, no_display = [], []
    for parent in outer:
        call, returned = parent['call'], parent['returned']
        arguments = call.get('arguments')
        require(type(arguments) is dict and set(arguments) == {'tooltipId', 'stateType'}
                and bounded_plain(arguments) and arguments == returned.get('arguments'), 'complex-tooltip arguments incomplete/changed')
        require(type(arguments['tooltipId']) is str, 'original complex tooltip received non-string/None ID')
        generators = [p for p in pairs if p['call']['source'] == TOOLTIP
                      and p['call']['method'] == '__genComplexToolTip' and inside(parent, p)]
        require(len(generators) == 1, 'complex-tooltip generator call absent/ambiguous')
        generator = generators[0]
        ga = generator['call'].get('arguments')
        require(type(ga) is dict and set(ga) == {'tooltipId', 'stateType', 'tooltipType'}
                and bounded_plain(ga) and ga == generator['returned'].get('arguments')
                and all(ga[k] == arguments[k] for k in arguments), 'complex-tooltip nested arguments differ')
        shown = [p for p in pairs if p['call']['source'] == TOOLTIP_META and p['call']['method'] == 'as_showS'
                 and inside(generator, p) and p['returned']['offset'] == 30]
        if not arguments['tooltipId'] or not shown:
            no_display.append(call['call_id'])
            continue
        require(len(shown) == 1 and returned['offset'] == 28 and generator['returned']['offset'] == 117,
                'complex-tooltip normal display branch/coverage')
        show = shown[0]
        sa = show['call'].get('arguments')
        require(type(sa) is dict and set(sa) == {'tooltipData', 'linkage'} and bounded_plain(sa)
                and sa == show['returned'].get('arguments') and type(sa['tooltipData']) is str
                and bool(sa['tooltipData']) and sa['linkage'] == ga['tooltipType'], 'tooltip render arguments absent/empty/changed')
        require(all(r.get('owner_class') == 'ToolTip' and r.get('flash_bound') is True
                    and r.get('fini_started') is False for p in (parent, generator, show) for r in (p['call'], p['returned'])),
                'tooltip display was not on a live bound original receiver')
        positive.append({'call_id': call['call_id'], 'generator_call_id': generator['call']['call_id'],
                         'show_call_id': show['call']['call_id'], 'tooltip_id': arguments['tooltipId'],
                         'state_type': arguments['stateType'], 'linkage': sa['linkage'],
                         'rendered_bytes_utf8': len(sa['tooltipData'].encode('utf8')),
                         'rendered_data_sha256': digest(sa['tooltipData'].encode('utf8')),
                         'call_seconds': call['elapsed_seconds'], 'return_seconds': returned['elapsed_seconds']})
    return {'status': 'PASS' if positive else 'NOT_RUN', 'displays': positive,
            'empty_or_no_display_call_ids': no_display,
            'scope': 'Original nonempty complex-tooltip generation and bound Flash invocation, pending pixel review.'}


def awards_data(data):
    if not bounded_plain(data):
        return {'status': 'NOT_RUN', 'reason': 'Awards payload omitted/truncated; callback completion cannot prove its contents'}
    require(type(data) is dict and set(data) == {'achievementsList', 'totalItemsList', 'battlesCount'}, 'Awards data keys')
    blocks, totals, battles = data['achievementsList'], data['totalItemsList'], data['battlesCount']
    require(type(battles) is int and battles == 0 and type(blocks) is list and len(blocks) == 7
            and type(totals) is list and len(totals) == 7, 'Awards zero-battle native seven-section shape')
    require(all(type(block) is list and len(block) <= 256 for block in blocks)
            and all(type(value) is int and 0 <= value <= 256 for value in totals), 'Awards section count bounds')
    require(all(len(block) <= total for block, total in zip(blocks, totals)), 'Awards filtered block exceeds native total')
    require(all(type(item) is dict for block in blocks for item in block), 'Awards catalogue item type')
    sections = []
    for index, (block, total) in enumerate(zip(blocks, totals)):
        section = {key: 0 for key in AWARDS_COUNTERS}
        section.update(index=index, packed_items=len(block), catalog_items=total)
        for item in block:
            for field, key in (('isInDossier', 'in_dossier_items'), ('isDone', 'done_items'), ('isRare', 'rare_items')):
                require(type(item.get(field)) is bool, 'Awards original item boolean absent')
                section[key] += int(item[field])
            value = item.get('value')
            require(type(value) in (int, float) and math.isfinite(value) and abs(value) <= 9007199254740991,
                    'Awards original item numeric value bound')
            section['nonzero_value_items'] += int(value != 0)
        sections.append(section)
    projected = {'version': 1, 'battles_count': battles, 'section_count': 7, 'sections': sections,
                 **{key: sum(section[key] for section in sections) for key in AWARDS_COUNTERS}}
    summary = awards_summary(projected)
    raw = entry.json.dumps(data, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')
    require(len(raw) <= 65536, 'Awards diagnostic payload byte bound')
    return {'status': 'PASS', 'battles_count': battles, 'block_lengths': [len(block) for block in blocks],
            'total_items_list': totals, 'data_sha256': digest(raw), 'summary': summary['summary'],
            'scope': 'Original catalogue may be nonempty for zero battles; no fabricated earned achievements inferred.'}


def awards_summary(value):
    """Validate the measured original-data projection without walking tooltip text."""
    require(type(value) is dict and set(value) == set(AWARDS_COUNTERS) | {'version', 'battles_count', 'section_count', 'sections'},
            'Awards summary v1 fields')
    require(type(value['version']) is int and value['version'] == 1
            and type(value['battles_count']) is int and value['battles_count'] == 0
            and type(value['section_count']) is int and value['section_count'] == 7
            and type(value['sections']) is list and len(value['sections']) == 7, 'Awards summary version/battles/sections')
    for index, section in enumerate(value['sections']):
        require(type(section) is dict and set(section) == set(AWARDS_COUNTERS) | {'index'}
                and type(section['index']) is int and section['index'] == index, 'Awards summary section identity')
        require(all(type(section[k]) is int and 0 <= section[k] <= 256 for k in AWARDS_COUNTERS), 'Awards summary section bounds')
        require(section['packed_items'] <= section['catalog_items']
                and all(section[k] <= section['packed_items'] for k in AWARDS_COUNTERS[2:]), 'Awards summary count relation')
    require(all(type(value[k]) is int and 0 <= value[k] <= 1024
                and value[k] == sum(section[k] for section in value['sections']) for k in AWARDS_COUNTERS),
            'Awards summary aggregate count mismatch')
    require(value['in_dossier_items'] == value['done_items'] == 0, 'fresh own profile unexpectedly contains earned/done awards')
    encoded = entry.json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode('ascii')
    return {'status': 'PASS', 'summary': value, 'summary_sha256': digest(encoded),
            'scope': 'Bounded projection of original Awards data. Nonzero values can be NO_LVL=5 and are not treated as earned.'}


def awards_evidence(rows, contracts, expected):
    pairs = profiled_pairs(rows, 'native_profile_call', contracts, {AWARDS, SECTION_META})
    outer = [p for p in pairs if p['call']['source'] == AWARDS and p['call']['method'] == '_sendAccountData']
    if not outer:
        return {'status': 'NOT_RUN', 'reason': 'Original ProfileAwards._sendAccountData not observed', 'renders': []}
    renders = []
    for parent in outer:
        nested = [p for p in pairs if p['call']['source'] == SECTION_META and p['call']['method'] == 'as_responseDossierS'
                  and inside(parent, p)]
        require(len(nested) == 1, 'Awards receiver did not invoke its own dossier Flash response')
        response = nested[0]
        require(parent['returned']['offset'] == 266 and response['returned']['offset'] == 30, 'Awards original/Flash render return offset')
        for pair in (parent, response):
            for row in (pair['call'], pair['returned']):
                state = row.get('owner_state')
                require(row.get('owner_class') == 'ProfileAwards' and row.get('flash_bound') is True
                        and type(state) is dict and state.get('isActive') is True and state.get('_userID') is None
                        and state.get('_databaseID') == expected['native_id'] and state.get('_userName') == expected['name'],
                        'Awards receiver inactive or belongs to a different native player')
        call, returned = response['call'], response['returned']
        require(call.get('type') == returned.get('type') == '#profile:profile/dropdown/labels/all', 'Awards battles-type binding')
        if 'awards_summary' in call or 'awards_summary' in returned:
            require('awards_summary' in call and call['awards_summary'] == returned.get('awards_summary'),
                    'Awards compact projection changed during original Flash callback')
            data = awards_summary(call['awards_summary'])
        else:
            require('data' in call and call['data'] == returned.get('data'), 'Awards Flash payload changed during callback')
            data = awards_data(call['data'])
        renders.append({'call_id': parent['call']['call_id'], 'response_call_id': call['call_id'],
                        'native_database_id': expected['native_id'], 'owner_id': call['owner_id'], 'data': data,
                        'call_seconds': parent['call']['elapsed_seconds'], 'return_seconds': parent['returned']['elapsed_seconds']})
    return {'status': entry.status_checks({str(r['call_id']): r['data'] for r in renders}), 'renders': renders,
            'scope': 'Actual original Awards receiver and its nested Flash callback; Summary is never substituted.'}


def scenario_observation(row, expected, specification):
    alias, owner_class, selected_index, _ = specification
    observation = row.get('observation')
    require(type(observation) is dict and observation.get('alias') == alias
            and observation.get('database_id') == expected['native_id']
            and observation.get('observed_ready') is True and observation.get('waiting_visible') is False
            and observation.get('owner_class') == owner_class and observation.get('flash_bound') is True
            and type(observation.get('owner_id')) is int and observation['owner_id'] > 0,
            'profile scenario original view/identity/binding')
    if alias == 'hangar':
        require(observation.get('vehicle_model_loaded') is True, 'scenario Hangar lacks loaded vehicle')
    else:
        require(type(observation.get('selected_index')) is int and observation['selected_index'] == selected_index
                and all(observation.get(k) is True for k in ('is_active', 'own_user_id', 'same_database_id', 'same_name')),
                'profile scenario selected section/own player mismatch')
    return observation


def native_image_match(images, shot):
    """#717 reports a lowercased Windows path; hash/size remain exact gates."""
    require(type(shot) is dict and type(shot.get('path')) is str
            and 1 <= len(shot['path']) <= 2048 and '\x00' not in shot['path'],
            'native screenshot path shape')
    path = PureWindowsPath(shot['path'])
    require(path.is_absolute() and '..' not in path.parts, 'native screenshot path scope')
    return [r for r in images if PureWindowsPath(r['path']) == path
            and r['sha256'] == shot.get('sha256') and r['bytes'] == shot.get('bytes')]


def scenario_awards_delivery(awards, observed, action_seconds, ready_seconds, previous_steps):
    rendered = [r for r in awards.get('renders', []) if r['owner_id'] == observed['owner_id']
                and r['call_seconds'] < r['return_seconds'] <= ready_seconds and r['data']['status'] == 'PASS']
    fresh = [r['call_id'] for r in rendered if action_seconds <= r['call_seconds']]
    if fresh:
        return fresh, 'new_original_callback'
    # ProfileSection.__receiveDossier returns normally without another send when
    # __needUpdate is false. Reusing that original receiver does not prove a new
    # callback: bind to its earlier successful delivery in this same scenario.
    previous_ids = {call_id for step in previous_steps if step['alias'] == 'profileAwards'
                    and step['owner_id'] == observed['owner_id'] for call_id in step['awards_call_ids']}
    cached = [r['call_id'] for r in rendered if r['call_id'] in previous_ids and r['return_seconds'] < action_seconds]
    require(bool(cached), 'profile Awards step lacks original data delivery for this receiver')
    return cached, 'same_original_receiver_cache'


def profile_scenario(rows, images, expected, awards):
    selected = [(i, r) for i, r in enumerate(rows) if r['event'].startswith('profile_scenario_')]
    if not selected:
        return {'status': 'NOT_RUN', 'reason': 'Six-step original Profile navigation regression not observed'}
    by_kind = {}
    allowed = {'profile_scenario_start', 'profile_scenario_action', 'profile_scenario_view_ready',
               'profile_scenario_screenshot_requested', 'profile_scenario_screenshot', 'profile_scenario_complete'}
    previous = -1
    for index, row in selected:
        require(row['event'] in allowed, 'profile scenario failed/cancelled/unknown event')
        require(type(row.get('version')) is int and row['version'] == 1
                and type(row.get('step_index')) is int and 0 <= row['step_index'] <= 6
                and row.get('database_id') == expected['native_id'], 'profile scenario version/step/player')
        elapsed = row.get('scenario_elapsed')
        require(type(elapsed) in (int, float) and math.isfinite(elapsed) and previous <= elapsed <= 180,
                'profile scenario time order/bound')
        previous = elapsed
        by_kind.setdefault(row['event'], []).append((index, row))
    expected_counts = {'profile_scenario_start': 1, 'profile_scenario_action': 12, 'profile_scenario_view_ready': 7,
                       'profile_scenario_screenshot_requested': 6, 'profile_scenario_screenshot': 6, 'profile_scenario_complete': 1}
    require({key: len(value) for key, value in by_kind.items()} == expected_counts, 'incomplete/duplicate original Profile scenario')
    start_index, start = by_kind['profile_scenario_start'][0]
    end_index, end = by_kind['profile_scenario_complete'][0]
    require(start_index == selected[0][0] and end_index == selected[-1][0] and start.get('step_index') == 0
            and start.get('phase') == 'initial_hangar' and start.get('alias') == 'hangar'
            and start.get('original_ui_only') is True and start.get('no_automatic_quit') is True
            and type(start.get('initial_hangar_seconds')) is int and 60 <= start['initial_hangar_seconds'] <= 65
            and start.get('max_seconds') == 180 and start.get('aliases') == [s[0] for s in PROFILE_STEPS],
            'profile scenario start does not declare bounded original UI path')
    require(end.get('phase') == 'complete' and end.get('step_index') == 6 and end.get('alias') == 'hangar'
            and end.get('original_ui_only') is True and end.get('automatic_quit') is False and end.get('screenshots') == 6,
            'profile scenario terminal state incomplete')
    ready = by_kind['profile_scenario_view_ready']
    require([r['step_index'] for _, r in ready] == list(range(7)), 'profile scenario stable-view order')
    initial_index, initial = ready[0]
    scenario_observation(initial, expected, ('hangar', 'Hangar', None, 'hangar'))
    require(start_index < initial_index and type(initial.get('stable_seconds')) in (int, float)
            and 60 <= initial['stable_seconds'] <= 67 and initial['elapsed_seconds'] - start['elapsed_seconds'] >= 60,
            'profile scenario initial stable Hangar duration')
    screenshots, last_index = [], initial_index
    for step, specification in enumerate(PROFILE_STEPS, 1):
        alias, owner_class, selected_index, suffix = specification
        actions = [(i, r) for i, r in by_kind['profile_scenario_action'] if r['step_index'] == step]
        require(len(actions) == 2 and [r.get('moment') for _, r in actions] == ['call', 'return'], 'profile action pair')
        action_index, action = actions[0]
        return_index, action_return = actions[1]
        ready_index, view = ready[step]
        request_index, request = by_kind['profile_scenario_screenshot_requested'][step - 1]
        image_index, screenshot = by_kind['profile_scenario_screenshot'][step - 1]
        require(last_index < action_index < return_index < ready_index < request_index < image_index < end_index,
                'profile step event ordering')
        require(all(row['step_index'] == step and row.get('alias') == alias for row in (action, action_return, view, request, screenshot)),
                'profile step alias identity')
        if step == 1:
            require(action.get('action') == 'open_profile' and action.get('original_handler') == 'LobbyHeader.menuItemClick',
                    'profile entry bypassed original lobby')
        elif step == 6:
            require(action.get('action') == 'close_profile' and action.get('original_handler') == 'ProfilePage.onCloseProfile',
                    'profile exit bypassed original page')
        else:
            require(action.get('action') == 'select_section'
                    and action.get('original_flash_setter') == 'ProfileHeaderButtonBar.selectedIndex'
                    and action.get('selected_index') == selected_index
                    and action.get('previous_index') == PROFILE_STEPS[step - 2][2], 'profile tab selection bypassed original Flash')
        observed = scenario_observation(view, expected, specification)
        captured = scenario_observation(screenshot, expected, specification)
        require(observed['owner_id'] == captured['owner_id'], 'profile view changed between readiness and screenshot')
        minimum = 5 if step == 6 else 2
        require(type(view.get('stable_seconds')) in (int, float) and minimum <= view['stable_seconds'] < 20
                and image_index > ready_index and screenshot['elapsed_seconds'] - action['elapsed_seconds'] < 20,
                'profile step stability/deadline')
        basename = 'profile_ui_%02d_%s' % (step, suffix)
        require(request.get('basename') == basename and request.get('writer') == 'BigWorld.screenShot'
                and request.get('extension') == 'png', 'profile screenshot is not original native writer')
        shot = screenshot.get('screenshot')
        require(type(shot) is dict and shot.get('basename') == basename and shot.get('visual_review') == 'NOT_RUN',
                'profile native screenshot metadata')
        matches = native_image_match(images, shot)
        require(len(matches) == 1 and re.fullmatch('screenshots/' + re.escape(basename) + r'_[0-9]{3,10}\.png', matches[0]['file']),
                'profile screenshot file/hash/size mismatch')
        linked, delivery = [], None
        if alias == 'profileAwards':
            linked, delivery = scenario_awards_delivery(awards, observed, action['elapsed_seconds'],
                                                        view['elapsed_seconds'], screenshots)
        screenshots.append({'step_index': step, 'alias': alias, 'owner_id': observed['owner_id'],
                            'screenshot': matches[0], 'awards_call_ids': linked, 'awards_delivery': delivery,
                            'stable_seconds': view['stable_seconds']})
        last_index = image_index
    return {'status': 'PASS', 'screenshots': screenshots,
            'elapsed_seconds': end['elapsed_seconds'] - start['elapsed_seconds'],
            'scope': 'Explicit original Flash navigation regression, six actual native images; no claim of physical mouse input.'}


def observed_profile_return(rows, expected, awards):
    """Read actual views around original Awards delivery; never operate the UI."""
    if not awards.get('renders'):
        return {'status': 'NOT_RUN', 'reason': 'No original own Awards delivery to correlate with displayed Profile views'}
    require(not any(r['event'].startswith('profile_scenario_') or r['event'] == 'diagnostic_open_profile' for r in rows),
            'manual view coverage contains an automatic Profile transition')
    samples = [(i, r) for i, r in enumerate(rows) if r['event'] == 'native_hangar']
    fini = [i for i, r in enumerate(rows) if r['event'] == 'fini_enter']
    require(len(fini) == 1, 'observed Profile lifecycle lacks unique engine fini')

    def view(sample, kind):
        views = sample.get('views', {})
        main, sub = views.get('main'), views.get('lobby_sub')
        ready = (type(main) is dict and main.get('class_name') == 'LobbyView' and main.get('alias') == 'lobby'
                 and main.get('flash_bound') is True and type(sub) is dict and sub.get('class_name') == kind
                 and sub.get('alias') == ('profile' if kind == 'ProfilePage' else 'hangar') and sub.get('flash_bound') is True
                 and sample.get('window_class') == 'AppEntry' and sample.get('native_connected') is True
                 and sample.get('items_cache_synced') is True and sample.get('waiting_visible') is False
                 and sample.get('resources') == expected['resources'] and sample.get('statistics') == expected['manifest']['statistics'])
        return ready and (kind != 'Hangar' or (sample.get('vehicle_model_loaded') is True
                         and sample.get('selected_inventory_id') == expected['vehicle']['inventory_id']))

    correlations = []
    for rendered in awards['renders']:
        if rendered['data']['status'] != 'PASS':
            continue
        profile = [(i, r) for i, r in samples if rendered['return_seconds'] <= r['elapsed_seconds'] <= rendered['return_seconds'] + 3
                   and i < fini[0] and view(r, 'ProfilePage')]
        before = [(i, r) for i, r in samples if r['elapsed_seconds'] < rendered['call_seconds'] and view(r, 'Hangar')]
        after = [(i, r) for i, r in samples if profile and profile[0][0] < i < fini[0] and view(r, 'Hangar')]
        if profile and before and after:
            correlations.append({'awards_call_id': rendered['call_id'], 'owner_id': rendered['owner_id'],
                                 'hangar_before_line': before[-1][0] + 1, 'profile_line': profile[0][0] + 1,
                                 'hangar_return_line': after[0][0] + 1,
                                 'profile_seconds': profile[0][1]['elapsed_seconds'],
                                 'hangar_return_seconds': after[0][1]['elapsed_seconds']})
    return {'status': 'PASS' if correlations else 'NOT_RUN', 'observations': correlations,
            'scope': 'Passive bound original ProfilePage/Awards and subsequent ready Hangar. Physical actions require the separate human-attested visual review.'}


def gui_visual_review(install, images, trace_sha256, tooltip, awards, require_human_actions=False):
    path = install / 'visual-review-ui.json'
    if not path.exists():
        return {'status': 'NOT_RUN', 'reason': 'Actual tooltip and Awards PNG review absent'}
    raw = read_limited(path, 32768)
    review = entry.json_data(raw)
    require(review.get('schema_version') == 1 and review.get('reviewer') == 'root_visual_inspection'
            and review.get('status') in ('PASS', 'FAIL') and review.get('trace_sha256') == trace_sha256,
            'GUI review schema/reviewer/native trace identity mismatch')
    if require_human_actions:
        attestation = review.get('human_attestation')
        require(type(attestation) is dict and attestation.get('source') == 'direct_user_message'
                and attestation.get('trace_sha256') == trace_sha256
                and type(attestation.get('statement')) is str and 1 <= len(attestation['statement']) <= 2048
                and type(attestation.get('actions')) is list
                and {'hover_tooltip', 'open_awards', 'return_to_hangar'} <= set(attestation['actions'])
                and len(attestation['actions']) <= 8, 'manual GUI lacks specific human action attestation')
    summaries = []
    sources = ('root_computer_input', 'original_flash_scenario', 'human_attested')
    for field, observed, flags in (
            ('tooltip_reviews', tooltip.get('displays', []), ('tooltip_visible', 'matches_target', 'text_readable')),
            ('awards_reviews', awards.get('renders', []), ('awards_tab_visible', 'native_catalog_visible', 'player_identity_visible'))):
        reviews = review.get(field)
        require(type(reviews) is list and 1 <= len(reviews) <= 8, 'GUI review required image count')
        ids = set()
        for item in reviews:
            call_id, shot = item.get('call_id'), item.get('screenshot')
            require(type(call_id) is int and call_id not in ids and any(r['call_id'] == call_id for r in observed),
                    'review is not linked to a measured original rendered GUI call')
            ids.add(call_id)
            require(type(shot) is dict and any(r['file'] == shot.get('file') and r['sha256'] == shot.get('sha256') for r in images),
                    'GUI review PNG/hash mismatch')
            require(item.get('trigger_source') in sources, 'GUI review action origin absent/unknown')
            require(not require_human_actions or item.get('trigger_source') == 'human_attested',
                    'manual GUI review cites an automatic action origin')
            require(type(item.get('findings')) is dict and all(item['findings'].get(k) is True for k in flags),
                    'GUI review does not confirm all required pixel findings')
            summaries.append({'kind': field, 'call_id': call_id, 'screenshot': shot, 'trigger_source': item['trigger_source']})
    return result(review['status'] == 'PASS', review_sha256=digest(raw), screenshots=summaries,
                  scope='Actual root-reviewed pixels tied to this native trace and the completed original callbacks.')


def gui_evidence(rows, expected, images, install, trace_sha256):
    contracts, source_report = original_ui_contracts()
    checks = {'original_bytecode': source_report}
    for name, function in (('tooltip_callbacks', lambda: tooltip_evidence(rows, contracts)),
                           ('awards_callbacks', lambda: awards_evidence(rows, contracts, expected))):
        try:
            checks[name] = function()
        except FAILURES as error:
            checks[name] = {'status': 'FAIL', 'error_type': type(error).__name__, 'error': str(error)}
    scripted = any(r['event'].startswith('profile_scenario_') for r in rows)
    key = 'profile_scenario' if scripted else 'observed_profile_return'
    try:
        checks[key] = (profile_scenario(rows, images, expected, checks['awards_callbacks']) if scripted else
                       observed_profile_return(rows, expected, checks['awards_callbacks']))
    except FAILURES as error:
        checks[key] = {'status': 'FAIL', 'error_type': type(error).__name__, 'error': str(error)}
    try:
        checks['gui_visual_review'] = gui_visual_review(install, images, trace_sha256,
                                                       checks['tooltip_callbacks'], checks['awards_callbacks'], not scripted)
    except FAILURES as error:
        checks['gui_visual_review'] = {'status': 'FAIL', 'error_type': type(error).__name__, 'error': str(error)}
    return aggregate(checks)


def verify(args):
    local_root = config()[1]['local_artifacts_root']
    report = {'schema_version': SCHEMA, 'tool': TOOL, 'status': 'NOT_RUN', 'session_status': 'NOT_RUN',
              'scope': 'Native local GUI entry, Tooltip/Awards, clean exit and optional paired relogin; no arena/economy.',
              'mode': args.mode, 'case': args.case, 'checks': {}}
    for name in ('wire', 'backend', 'native_common', 'native_hangar', 'visual', 'gui', 'relogin', 'card_gui'):
        report[name] = {'status': 'NOT_RUN'}
    stage = 'inputs'
    try:
        install = entry.owned(args.install, local_root, True)
        report['install'] = str(install)
        registration = entry.owned(args.registration, local_root)
        credentials = entry.owned(args.credentials, local_root)
        fixture = entry.owned(args.fixture, local_root, True)
        private_key = entry.owned(args.private_key, local_root)
        if getattr(args, 'catalog_baseline', None):
            baseline = entry.owned(args.catalog_baseline, local_root, True)
            expected, password, identity = catalog_identity_inputs(registration, credentials, args.case, fixture, baseline)
        else:
            expected, password, identity = entry.identity_inputs(registration, credentials, args.case, fixture)
        identity.pop('email', None)  # Native equality is checked privately by the reused wire parser.
        report['checks']['website_fixture_identity'] = identity
        report['identity_snapshot'] = profile_snapshot(expected)
        plan_raw = local_file(install, 'install-plan.json', 256 * 1024)
        plan = entry.json_data(plan_raw)
        outcome = entry.read_json(install / 'native-outcome.json', 65536)
        require(outcome.get('plan_sha256') == digest(plan_raw), 'native outcome/plan hash mismatch')
        runtime_settings = entry.json_data(local_file(install, 'postrun/sr_interactive_settings.json', 16384))
        require(runtime_settings == plan['settings'], 'postrun/plan settings differ')
        report['checks']['installation_plan'] = {'status': 'PASS', 'sha256': digest(plan_raw)}
        report['process'] = {k: outcome.get(k) for k in ('client_pid', 'started_utc', 'finished_utc', 'gateway_run')}
        run = entry.owned(outcome['gateway_run'], local_root, True)
        expected_digest = read_limited(run.parent / 'client-digest.bin', 16)
        require(len(expected_digest) == 16, 'expected client digest length')
        stage = 'native_common'
        rows, trace_info = entry.runtime_rows(install, plan, outcome, local_root)
        report[stage] = native_common(install, plan, outcome, rows, trace_info, args.mode)
        stage = 'wire'
        report[stage] = entry.wire(install, private_key, expected, password, expected_digest)
        del password
        stage = 'backend'
        report[stage] = entry.backend_binding(install, outcome, report['wire'], expected, local_root)
        stage = 'native_hangar'
        report[stage] = entry.native_hangar(rows, report['wire'], expected, args.min_ready_seconds)
        stage = 'visual'
        images = screenshot_images(install, plan, local_root)
        report[stage] = {**hangar_visual(install, images), 'screenshots': images}
        stage = 'gui'
        report[stage] = gui_evidence(rows, expected, images, install, trace_info['sha256'])
        report['session_status'] = session_status(report)
        stage = 'relogin'
        report[stage] = relogin(args.previous_report, report, local_root)
        stage = 'card_gui'
        report[stage] = card_gui(report, args.previous_report, local_root)
    except FAILURES as error:
        failed = {'status': 'FAIL', 'error_type': type(error).__name__, 'error': str(error)}
        if stage in report:
            report[stage] = failed
        else:
            report['checks'][stage] = failed
    if report['gui']['status'] == 'FAIL':
        report['card_gui'] = {'status': 'FAIL', 'coverage': 'current_run',
                              'scope': 'A current GUI failure cannot be replaced or downgraded by an earlier success.'}
    report['session_status'] = session_status(report)
    report['status'] = entry.status_checks({'session': {'status': report['session_status']},
                                            'card_gui': report['card_gui'], 'relogin': report['relogin']})
    report['verifier_sources'] = [{'file': str(ROOT / 'tools' / name),
                                 'sha256': digest(read_limited(ROOT / 'tools' / name, 256 * 1024))}
        for name in ('verify_hangar_ui.py', 'verify_unified_entry.py', 'verify_hangar.py', 'verify_redirect_capture.py',
                     'verify_baseapp_capture.py', 'verify_channel_capture.py', 'py27_static.py', 'packed_xml.py')]
    report['limitations'] = ['Physical typing/clicks require separate input evidence; native handler invocation alone cannot prove them.',
                            'GUI pixels require an actual hash-bound visual review, not file existence.',
                            'No arena, unsupported economic command success, general protocol or arbitrary GUI coverage is claimed.']
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('install', 'registration', 'credentials', 'case', 'private-key', 'fixture', 'out'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--mode', choices=('normal', 'controlled'), default='normal')
    parser.add_argument('--min-ready-seconds', type=float, default=60)
    parser.add_argument('--previous-report')
    parser.add_argument('--catalog-baseline', help='Unmodified earlier r1 fixture for the independently verified mounted catalogue2 delta')
    args = parser.parse_args()
    require(1 <= args.min_ready_seconds <= 1800, 'ready duration outside bounded acceptance policy')
    out = output_dir(args.out)
    report = verify(args)
    save_json(out / 'hangar-ui-verification.json', report)
    print(entry.json.dumps({'status': report['status'], 'session_status': report['session_status'],
                            'out': str(out)}, ensure_ascii=False))
    raise SystemExit(0 if report['status'] == 'PASS' else 1)


if __name__ == '__main__':
    main()
