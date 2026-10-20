"""Prepare/install/rollback the explicit local interactive client compatibility.

Only install/rollback mutate the configured research copy, under the actual
native instance mutex. prepare is reviewable and never touches either client.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

from client_audit import ROOT, config, output_dir, read_limited, save_json, sha256
from client_probe import to_element
from packed_xml import decode
from hangar_config import overrides

MODULES = ('sr_interactive', 'collision_oracle', 'destructible_probe', 'destructible_catalog_probe', 'project_auth', 'project_preferences', 'hangar_bootstrap', 'hangar_ui_probe', 'hangar_capabilities', 'crew_capabilities', 'ms1_crew_probe', 'ms1_crew_scenario', 'hangar_limits_scenario', 'hangar_windows_scenario', 'hangar_relogin_scenario', 'account_switch_scenario', 'long_hangar_scenario', 'ms1_ammo_probe', 'ms1_ammo_scenario', 'arena_entry_probe', 'arena_bootstrap', 'arena_space_scenario', 'arena_vehicle_scenario', 'arena_ready_scenario', 'arena_movement_scenario', 'map_drive_scenario', 'map_drive_client', 'map_drive_acceptance')
LOGS = ('python.log', 'Influx_PS.log', 'Influx_PS.bak')
MODULES += ('p09d_ammo_ui', 'p09d_ammo_scenario')
MODULES += ('p04d_crew_ui',)
MODULES += ('p04f_crew_ui',)
MODULES += ('p04g_crew_ui',)
MODULES += ('p04h_crew_ui', 'p04i_crew_ui', 'p04j_crew_ui', 'p04k_crew_ui')
MODULES += ('p09e_research_policy',)
MODULES += ('project_network',)
MODULES += ('project_sixth_sense_sound',)
MODULES += ('project_player_kill_marker',)


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def local_path(value, paths):
    path = (ROOT / value).resolve()
    if not path.is_relative_to(paths['local_artifacts_root']) or path == paths['local_artifacts_root']:
        raise ValueError('artifact path must be strictly inside configured local/')
    # Resolve rejects a junction escape; reject any links even when aimed inside.
    for part in (path, *path.parents):
        if part == paths['local_artifacts_root']:
            break
        if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
            raise ValueError('linked artifact path refused')
    return path


def target(root, relative):
    original = root / relative
    path = original.resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError('client target escapes research copy')
    for part in (original, *original.parents):
        if part == root:
            break
        if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
            raise ValueError('linked client target refused')
    return path


def catalog_probe_settings(value, paths, shared_lab, control):
    if value is None:
        return None
    if not shared_lab or control is None:
        raise ValueError('catalog preprocessing requires shared lab and explicit control')
    path = local_path(value, paths)
    module_spec = importlib.util.spec_from_file_location(
        '_catalog_spec_validator', ROOT/'client_patch/destructible_catalog_probe.py')
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    payload = read_limited(path, module.MAX_SPEC_BYTES)
    module.validate_spec_payload(payload)
    return {'path': str(path), 'sha256': digest(payload)}


def file_hash(path):
    if not path.exists():
        return None
    if not path.is_file():
        raise ValueError('expected regular file: ' + str(path))
    return sha256(path)


def xml_bytes(element):
    return ET.tostring(element, encoding='utf-8', xml_declaration=True)


def interactive_resource_overrides(root, disable_legacy_license_dialog=False,
                                   diagnostic_no_license_dialog=False, has_control=False):
    if diagnostic_no_license_dialog and not has_control:
        raise ValueError('diagnostic license dialog override requires explicit one-shot control')
    disabled = disable_legacy_license_dialog or diagnostic_no_license_dialog
    payloads, evidence = overrides(root, disabled)
    legacy = dict(evidence.get('diagnostic_license_dialog', {}))
    legacy.update(owner_requested=bool(disable_legacy_license_dialog), disabled=bool(disabled),
                  user_agreement_recorded=False, license_files_modified=False,
                  account_int_settings_modified=False)
    if disable_legacy_license_dialog:
        evidence.pop('diagnostic_license_dialog', None)
        legacy['scope'] = 'owner requested legacy service dialog disabled; no acceptance is claimed'
    elif not disabled:
        legacy['scope'] = 'original legacy service dialog retained'
    evidence['legacy_service_dialog'] = legacy
    return payloads, evidence


def network_options(args, profile13, mixed_ammo):
    path = Path(__file__).resolve().parents[1] / 'client_patch/project_network.py'
    spec = importlib.util.spec_from_file_location('_project_network_prepare', path)
    policy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(policy)
    return policy.prepare_options(args.endpoint, getattr(args, 'network_policy', None),
                                  args.registration_url, profile13, mixed_ammo)


def sixth_sense_policy():
    path = Path(__file__).resolve().parents[1] / 'client_patch/project_sixth_sense_sound.py'
    spec = importlib.util.spec_from_file_location('_project_sixth_sense_prepare', path)
    policy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(policy)
    return policy


def sixth_sense_option(args, profile13, map_drive):
    # Project policy (not original #717): absent option keeps the silent original lamp.
    return sixth_sense_policy().prepare_option(getattr(args, 'sixth_sense_sound', None),
                                               profile13, map_drive)


def apply_registration(gui, evidence, options):
    registration = [node for node in gui.iter() if node.findtext('name') == 'registrationURL']
    if len(registration) != 1:
        raise ValueError('unmeasured registration URL setting')
    field = registration[0].find('value')
    if field is None:
        field = registration[0]
    field.text = options['registration_url']
    evidence.update(allowed_login=options['endpoint'], public_name='Стальной рубеж',
                    remember_password=False, registration_url=options['registration_url'],
                    token_login_enabled=False)
    if options.get('network_policy') is not None:
        evidence.update(network_policy=options['network_policy'], registration_enabled=False,
                        registration_scope='precreated_project_accounts_only')
        if 'registrationURL' not in evidence['empty_url_settings']:
            raise ValueError('LAN registration must retain the existing empty-URL guard')
    else:
        evidence['empty_url_settings'] = [name for name in evidence['empty_url_settings']
                                        if name != 'registrationURL']


def prepare(args):
    _, paths = config()
    out = local_path(args.out, paths)
    if out.exists() and any(out.iterdir()):
        raise ValueError('prepare requires an empty output directory')
    root, original = paths['research_client_root'], paths['original_client_root']
    copy_info = None
    if getattr(args, 'research_copy', None):
        from shared_client_copy import checked_copy
        root, copy_info = checked_copy(args.research_copy, paths)
    shared_lab = bool(getattr(args, 'enable_shared_lab', False))
    profile13_battle = getattr(args, 'enable_profile13_battle', False)
    if type(profile13_battle) is not bool:
        raise ValueError('Explicit boolean profile13 battle option required')
    p06t_mixed_ammo = getattr(args, 'enable_p06t_mixed_ammo', False)
    if (type(p06t_mixed_ammo) is not bool or p06t_mixed_ammo and not profile13_battle):
        raise ValueError('P06T mixed ammunition requires explicit profile13 battle option')
    training_rooms = getattr(args, 'enable_training_rooms', False)
    if type(training_rooms) is not bool or training_rooms and not profile13_battle:
        raise ValueError('Training rooms require explicit profile13 battle option')
    ammo_service = bool(getattr(args, 'enable_p09d_ammo_service', False))
    recruitment = bool(getattr(args, 'enable_crew_recruitment', False))
    transfer = bool(getattr(args, 'enable_crew_transfer', False))
    cross_vehicle = bool(getattr(args, 'enable_cross_vehicle_crew', False))
    roster = bool(getattr(args, 'enable_roster_recruitment', False))
    progression = bool(getattr(args, 'enable_crew_progression', False))
    dismissal = bool(getattr(args, 'enable_crew_dismissal', False))
    barracks = bool(getattr(args, 'enable_barracks_recruitment', False))
    if barracks and not dismissal:
        raise ValueError('P04K Barracks recruitment requires all earlier explicit hangar services')
    if dismissal and not progression:
        raise ValueError('P04J dismissal requires all earlier explicit hangar services')
    research_service = bool(getattr(args, 'enable_research_service', False))
    if profile13_battle and (copy_info is None or shared_lab or args.enable_map_drive
            or not all((ammo_service, recruitment, transfer, cross_vehicle, roster,
                        progression, dismissal, barracks, research_service))):
        raise ValueError('Profile13 battle requires isolated full research/crew/ammunition hangar; map-drive and shared lab are excluded')
    if ammo_service and (shared_lab or args.enable_map_drive):
        raise ValueError('P09D ammunition service is restricted to the native hangar')
    if recruitment and (copy_info is None or not ammo_service or shared_lab or args.enable_map_drive):
        raise ValueError('P04D recruitment requires an explicit isolated copy and P09D native hangar service')
    if transfer and (copy_info is None or not recruitment or not ammo_service or shared_lab or args.enable_map_drive):
        raise ValueError('P04F transfer requires isolated native hangar with recruitment and ammunition service')
    if cross_vehicle and not transfer:
        raise ValueError('P04G cross-vehicle crew requires all previous explicit hangar services')
    if progression and not roster:
        raise ValueError('P04I progression requires all earlier explicit hangar services')
    if roster and not cross_vehicle:
        raise ValueError('P04H roster recruitment requires all previous explicit hangar services')
    if research_service and (copy_info is None or not barracks or not ammo_service
                             or shared_lab or args.enable_map_drive):
        raise ValueError('P09E research requires an explicit isolated native P04K barracks hangar')
    if shared_lab and (copy_info is None or not args.enable_map_drive):
        raise ValueError('Shared lab requires an explicit isolated copy and native arena services')
    network = network_options(args, profile13_battle, p06t_mixed_ammo)
    sixth_sense = sixth_sense_option(args, profile13_battle, bool(args.enable_map_drive))
    endpoint = network['endpoint']
    public = local_path(args.public_key, paths)
    public_payload = read_limited(public, 4096)
    if not public_payload.startswith(b'-----BEGIN PUBLIC KEY-----') or b'PRIVATE' in public_payload:
        raise ValueError('expected public-only PEM key')
    profile = local_path(args.profile_dir, paths)
    runtime = local_path(args.trace_dir, paths)
    control = local_path(args.test_control, paths) if args.test_control else None
    if control and (control == public or control.is_relative_to(root)):
        raise ValueError('control must be a dedicated ignored local file')
    if args.diagnostic_no_license_dialog and not control:
        raise ValueError('diagnostic license dialog override requires explicit one-shot control')
    catalog_spec = catalog_probe_settings(getattr(args, 'destructible_catalog_spec', None),
                                          paths, shared_lab, control)
    disable_dialog = args.disable_legacy_license_dialog or args.diagnostic_no_license_dialog
    checked_originals = ['res/engine_config.xml', 'paths.xml', 'res/text/LC_MESSAGES/menu.mo',
                         'res/text/LC_MESSAGES/system_messages.mo']
    if disable_dialog:
        checked_originals.append('version.xml')
    for relative in checked_originals:
        if file_hash(root/relative) != file_hash(original/relative):
            raise ValueError('research configuration differs from original; inspect before prepare: '+relative)
    out.mkdir(parents=True, exist_ok=True)
    bundle = out/'bundle'
    bundle.mkdir()
    compiler = local_path(args.compiler, paths)
    compiled = out/'compiled'
    compiled.mkdir()
    payloads, resource_evidence = interactive_resource_overrides(
        root, args.disable_legacy_license_dialog, args.diagnostic_no_license_dialog,
        has_control=control is not None)
    if dismissal:
        from p04j_dismissal_flash import application_display_payload, APPLICATION_TARGET
        payloads[APPLICATION_TARGET], resource_evidence['crew_dismissal_flash'] = application_display_payload(original)
        resource_evidence['crew_dismissal_flash']['tool_sha256'] = sha256(ROOT/'tools/p04j_dismissal_flash.py')
    scripts_path = 'res_mods/0.9.1/scripts_config.xml'
    scripts = ET.fromstring(payloads[scripts_path])
    host = scripts.find('login/host')
    for key, value in (('name','Стальной рубеж'), ('url',endpoint), ('url_token',''),
                       ('public_key_path','sr_local.pubkey'), ('periphery_id','0')):
        host.find(key).text = value
    payloads[scripts_path] = xml_bytes(scripts)
    gui_path = 'res_mods/0.9.1/gui/gui_settings.xml'
    gui = ET.fromstring(payloads[gui_path])
    for name in ('rememberPassVisible',):
        matches = [node for node in gui.iter() if node.findtext('name') == name]
        if len(matches) != 1:
            raise ValueError('unmeasured GUI flag: ' + name)
        field = matches[0].find('value')
        if field is None:
            field = matches[0]
        field.text = 'false'
    apply_registration(gui, resource_evidence, network)
    payloads[gui_path] = xml_bytes(gui)
    from project_login_resources import project_menu
    localized,localization_evidence = project_menu(read_limited(root/'res/text/LC_MESSAGES/menu.mo',8*1024*1024))
    # Original helpers.i18n resolves the DIRECTORY "text" once, then standard
    # gettext loads every domain from that one directory. A menu-only res_mods
    # text directory shadows all other domains (measured Auth05 failure).
    # Replace only research's existing menu catalog with verified backup;
    # leave directory resolution and every other original catalog untouched.
    payloads['res/text/LC_MESSAGES/menu.mo'] = localized
    localization_evidence['target'] = 'res/text/LC_MESSAGES/menu.mo'
    localization_evidence['directory_resolution_preserved'] = True
    resource_evidence['project_login_localization'] = localization_evidence
    from project_greeting_resources import project_greeting
    greeting, greeting_evidence = project_greeting(
        read_limited(root/'res/text/LC_MESSAGES/system_messages.mo', 8*1024*1024))
    payloads['res/text/LC_MESSAGES/system_messages.mo'] = greeting
    greeting_evidence['target'] = 'res/text/LC_MESSAGES/system_messages.mo'
    greeting_evidence['directory_resolution_preserved'] = True
    resource_evidence['project_greeting_localization'] = greeting_evidence
    engine = to_element('engine_config.xml', decode(read_limited(root/'res/engine_config.xml')))
    engine.find('personality').text = 'sr_interactive'
    engine.find('preferences').text = str(profile/'sr_preferences.xml').replace('\\','/')
    search_paths_raw = read_limited(root/'paths.xml', 65536)
    search_paths = ET.fromstring(search_paths_raw)
    search_list = search_paths.find('Paths')
    if search_list is None or not search_list.findall('Path'):
        raise ValueError('unmeasured original resource search path format')
    own_path = ET.Element('Path')
    own_path.text = str(profile).replace('\\','/')
    search_list.insert(0, own_path)
    payloads['paths.xml'] = xml_bytes(search_paths)
    resource_evidence['preferences_search_path'] = {'source':'paths.xml', 'before_sha256':digest(search_paths_raw),
                                                    'prepended_owned_directory':str(profile)}
    screenshot_dir = runtime/'screenshots'
    shot = engine.find('screenShot')
    if shot is None:
        raise ValueError('original screenshot configuration absent')
    for name, value in (('path',str(screenshot_dir).replace('\\','/')+'/'), ('extension','png'), ('name','screenshot')):
        field = shot.find(name)
        if field is None:
            field = ET.SubElement(shot, name)
        field.text = value
    payloads['res/engine_config.xml'] = xml_bytes(engine)
    payloads['res_mods/0.9.1/sr_local.pubkey'] = public_payload
    settings = {'schema_version':1, 'endpoint':endpoint, 'profile_dir':str(profile),
                'trace_dir':str(runtime), 'screenshot_dir':str(screenshot_dir),
                'local_root':str(paths['local_artifacts_root']), 'preferences_resource':'sr_preferences.xml',
                'test_control':str(control) if control else None,
                'capture_hangar':bool(args.capture_hangar or args.capture_ui_passive),
                'capture_ui_passive':bool(args.capture_ui_passive),
                'enable_map_drive':bool(args.enable_map_drive)}
    if network.get('network_policy') is not None:
        settings['network_policy'] = network['network_policy']
    if ammo_service:
        settings['enable_p09d_ammo_service'] = True
    if recruitment:
        settings['enable_crew_recruitment'] = True
    if transfer:
        settings['enable_crew_transfer'] = True
    if cross_vehicle:
        settings['enable_cross_vehicle_crew'] = True
    if roster:
        settings['enable_roster_recruitment'] = True
    if progression:
        settings['enable_crew_progression'] = True
    if dismissal:
        settings['enable_crew_dismissal'] = True
    if barracks:
        settings['enable_barracks_recruitment'] = True
    if research_service:
        settings['enable_research_service'] = True
    if shared_lab:
        settings['enable_shared_lab'] = True
    if profile13_battle:
        settings['enable_profile13_battle'] = True
    if p06t_mixed_ammo:
        settings['enable_p06t_mixed_ammo'] = True
    if training_rooms:
        settings['enable_training_rooms'] = True
    if catalog_spec is not None:
        settings['destructible_catalog_spec'] = catalog_spec
    if sixth_sense is not None:
        settings['sixth_sense_sound'] = sixth_sense['candidate']
        resource_evidence['project_sixth_sense_sound'] = sixth_sense
    if getattr(args, 'player_kill_marker', False):
        # Owner order 2026-10-20: keep the player's killing hit/explosion colour.
        if not profile13_battle:
            raise ValueError('--player-kill-marker requires --enable-profile13-battle')
        settings['player_kill_marker'] = True
    sample = getattr(args, 'sixth_sense_sample', None)
    if sample is not None:
        # Owner order 2026-10-20: the gun_intuition bank carries the owner's lamp
        # sample (res_mods override, ledgered/rolled back like every payload).
        if sixth_sense is None or sixth_sense['candidate'] != 'gun_intuition':
            raise ValueError('--sixth-sense-sample requires --sixth-sense-sound gun_intuition')
        import fsb5_lamp
        bank = 'audio/gui_notifications_fx_intuition.fsb'
        source_bank = read_limited(original/'res'/bank, 1024*1024)
        if file_hash(root/'res'/bank) != digest(source_bank):
            raise ValueError('research copy lamp bank differs from original')
        payload = fsb5_lamp.build(source_bank, fsb5_lamp.decode_source(sample))
        # engine_config <soundMgr><mediaPath>audio</mediaPath> resolves to the
        # first audio directory: a res_mods/0.9.1/audio holding one bank made
        # FMOD miss every other project (owner run 2026-10-20: silent hangar and
        # battle). Replace the research copy's own bank in place, with backup.
        payloads['res/'+bank] = payload
        resource_evidence['project_sixth_sense_sample'] = {
            'source_sha256':sha256(Path(sample)), 'source_bytes':Path(sample).stat().st_size,
            'original_bank_sha256':digest(source_bank), 'bank':'res/'+bank,
            'bank_sha256':digest(payload), 'tool_sha256':sha256(ROOT/'tools/fsb5_lamp.py'),
            'format':'FSB5 v1 mono IMA ADPCM 48 kHz', 'provenance':'owner-supplied file; not committed',
            'native_audio_check':'NOT_RUN'}
    payloads['sr_interactive_settings.json'] = (json.dumps(settings, ensure_ascii=True, indent=2)+'\n').encode()
    sources = []
    for module in MODULES:
        source = ROOT/'client_patch'/f'{module}.py'
        pyc = compiled/f'{module}.pyc'
        metadata = compiled/f'{module}.json'
        subprocess.run([str(compiler), str(ROOT/'tools/compile_interactive27.py'),
                        '--source',str(source), '--out',str(pyc), '--metadata',str(metadata)],
                       check=True, capture_output=True, timeout=30)
        payloads[f'res_mods/0.9.1/scripts/client/{module}.pyc'] = read_limited(pyc)
        sources.append({'path':source.relative_to(ROOT).as_posix(), 'sha256':sha256(source),
                        'compiled':str(pyc.relative_to(out)), 'metadata':str(metadata.relative_to(out))})
    entries = []
    overwrite_allowed = {'res/engine_config.xml', 'paths.xml', 'res/text/LC_MESSAGES/menu.mo',
                         'res/text/LC_MESSAGES/system_messages.mo'}
    if disable_dialog:
        overwrite_allowed.add('version.xml')
    if 'project_sixth_sense_sample' in resource_evidence:
        overwrite_allowed.add(resource_evidence['project_sixth_sense_sample']['bank'])
    for relative, payload in sorted(payloads.items()):
        current = target(root, relative)
        before = file_hash(current)
        if before is not None and relative not in overwrite_allowed:
            raise ValueError('new compatibility target already exists: '+relative)
        artifact = bundle/relative
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(payload)
        entries.append({'path':relative, 'before_sha256':before, 'installed_sha256':digest(payload),
                        'bytes':len(payload), 'runtime_mutable':False})
    for relative in LOGS:
        entries.append({'path':relative, 'before_sha256':file_hash(target(root,relative)),
                        'installed_sha256':None, 'runtime_mutable':True})
    for directory in (profile, runtime, screenshot_dir):
        directory.mkdir(parents=True, exist_ok=True)
    if control and any(screenshot_dir.iterdir()):
        raise ValueError('acceptance screenshot directory must be empty')
    plan = {'schema_version':1, 'mode':'interactive', 'prepared_utc':datetime.now(timezone.utc).isoformat(),
            'research_root':str(root), 'original_root':str(original), 'files':entries, 'sources':sources,
            'settings':settings, 'resources':resource_evidence, 'client_write_performed':False,
            'preferences_contract':'exact native invalid prefix checked before GUI; owned bounded DataSection XML persistence',
            'normal_auto_login':False, 'normal_auto_quit':False,
            'native_acceptance':'NOT_RUN', 'command':sys.argv}
    if copy_info is not None:
        plan['additional_research_copy'] = True
        plan['instance_mutex'] = copy_info['instance_mutex']
    save_json(out/'install-plan.json', plan)
    print(json.dumps({'status':'PREPARED','plan':str(out/'install-plan.json'),'client_write_performed':False},ensure_ascii=False))


def load_plan(args):
    _, paths = config()
    out = local_path(args.out, paths)
    plan = json.loads(read_limited(out/'install-plan.json', 1024*1024))
    root = paths['research_client_root']
    if plan.get('additional_research_copy') is True:
        from shared_client_copy import checked_copy
        root, copy_info = checked_copy(plan['research_root'], paths)
        if plan.get('instance_mutex') != copy_info['instance_mutex']:
            raise ValueError('Research copy mutex differs from manifest')
    if plan['schema_version'] != 1 or Path(plan['research_root']) != root or Path(plan['original_root']) != paths['original_client_root']:
        raise ValueError('install plan roots/schema changed')
    return out, root, plan


def install(args):
    from instance_mutex import control
    out, root, plan = load_plan(args)
    if (out/'patch-ledger.json').exists():
        raise ValueError('installation already attempted; use its ledger and rollback')
    with control(plan['instance_mutex']) if plan.get('additional_research_copy') else control() as mutex:
        for entry in plan['files']:
            if file_hash(target(root,entry['path'])) != entry['before_sha256']:
                raise ValueError('client changed since reviewed prepare: '+entry['path'])
            if not entry['runtime_mutable'] and file_hash(out/'bundle'/entry['path']) != entry['installed_sha256']:
                raise ValueError('prepared artifact hash changed')
        new_dirs = set()
        for entry in plan['files']:
            current = target(root,entry['path'])
            if entry['before_sha256'] is not None:
                backup = out/'backup'/entry['path']
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(current, backup)
                if sha256(backup) != entry['before_sha256']:
                    raise ValueError('backup verification failed')
            if not entry['runtime_mutable']:
                parent = current.parent
                while parent != root:
                    if not parent.exists():
                        new_dirs.add(parent.relative_to(root).as_posix())
                    parent = parent.parent
        ledger = dict(plan, installed_utc=datetime.now(timezone.utc).isoformat(), mutex=mutex,
                      new_dirs=sorted(new_dirs), plan_sha256=sha256(out/'install-plan.json'))
        save_json(out/'patch-ledger.json',ledger)
        # Durable before hashes and verified backups exist before any mutation.
        for entry in plan['files']:
            if entry['runtime_mutable']:
                continue
            current = target(root,entry['path'])
            current.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(out/'bundle'/entry['path'],current)
            if sha256(current) != entry['installed_sha256']:
                raise ValueError('installed artifact verification failed')
        save_json(out/'install.json',{'status':'PASS','files':len(plan['files']), 'client_exe_modified':False})
    print(json.dumps({'status':'INSTALLED','ledger':str(out/'patch-ledger.json')}))


def rollback(args):
    from instance_mutex import control
    out, root, plan = load_plan(args)
    ledger = json.loads(read_limited(out/'patch-ledger.json',1024*1024))
    if ledger['plan_sha256'] != sha256(out/'install-plan.json'):
        raise ValueError('prepared plan changed since installation')
    with control(plan['instance_mutex']) if plan.get('additional_research_copy') else control():
        if (out/'restore.json').exists():
            changed = [e['path'] for e in ledger['files'] if file_hash(target(root,e['path'])) != e['before_sha256']]
            if changed:
                raise ValueError('already restored but files changed afterwards; preserving: '+', '.join(changed))
            print(json.dumps({'status':'ALREADY_RESTORED','restore':str(out/'restore.json')}))
            return
        for entry in ledger['files']:
            now = file_hash(target(root,entry['path']))
            if not entry['runtime_mutable'] and now not in (entry['before_sha256'],entry['installed_sha256']):
                raise ValueError('unexpected client edit; rollback refuses overwrite: '+entry['path'])
            if entry['before_sha256'] is not None and file_hash(out/'backup'/entry['path']) != entry['before_sha256']:
                raise ValueError('rollback backup hash mismatch')
        restored = []
        for entry in reversed(ledger['files']):
            entry = dict(entry)
            current = target(root,entry['path'])
            entry['postrun_sha256'] = file_hash(current)
            if current.is_file():
                post = out/'postrun'/entry['path']
                if post.exists():
                    if file_hash(post) != entry['postrun_sha256']:
                        raise ValueError('partial rollback postrun evidence differs; preserve for inspection')
                else:
                    post.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(current,post)
            if entry['before_sha256'] is not None:
                current.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(out/'backup'/entry['path'],current)
            elif current.exists():
                current.unlink()
            if file_hash(current) != entry['before_sha256']:
                raise ValueError('rollback hash verification failed')
            restored.append(entry)
        for relative in sorted(ledger['new_dirs'],key=lambda p:len(Path(p).parts),reverse=True):
            directory = target(root,relative)
            if directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()
        save_json(out/'restore.json',{'status':'PASS','files':restored,
                                     'preserved_local_profile':plan['settings']['profile_dir']})
    print(json.dumps({'status':'RESTORED','restore':str(out/'restore.json')}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command',required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('--out',required=True)
    prep.add_argument('--research-copy', help='Explicit manifested additional copy below local/clients/')
    prep.add_argument('--enable-shared-lab', action='store_true', help='Initialize original arena services before server-assigned laboratory entry')
    prep.add_argument('--public-key',required=True)
    prep.add_argument('--endpoint',default='127.0.0.1:20014')
    prep.add_argument('--network-policy', choices=('lan-test-v1',),
                      help='Explicit private LAN test; pre-created own accounts only, registration disabled')
    prep.add_argument('--registration-url', default=None)
    prep.add_argument('--profile-dir',required=True)
    prep.add_argument('--trace-dir',required=True)
    prep.add_argument('--test-control')
    prep.add_argument('--destructible-catalog-spec',
                      help='Pinned local identity preprocessing specification; requires opt-in control/shared lab')
    prep.add_argument('--enable-map-drive', action='store_true',
                      help='Explicit test_lab native battle-button travel; no automatic input or quit')
    prep.add_argument('--enable-profile13-battle', action='store_true',
                      help='Owned stock MS-1/IS-7 AP-only battle entry from the full isolated profile13 hangar')
    prep.add_argument('--enable-p06t-mixed-ammo', action='store_true',
                      help='Explicit P06T source-three-stack entry; requires --enable-profile13-battle and server v2 admission')
    prep.add_argument('--enable-training-rooms', action='store_true',
                      help='Explicit P10B native training context; requires isolated profile13 hangar and server rooms')
    prep.add_argument('--sixth-sense-sound', choices=sorted(sixth_sense_policy().CANDIDATES),
                      help='Project policy, not original 0.9.1: one existing GUI FX cue when '
                           'the Sixth Sense lamp lights; requires a battle mode; off by default')
    prep.add_argument('--player-kill-marker', action='store_true',
                      help='Project policy, not original 0.9.1: a kill by the player keeps the player-coloured '
                           'marker colour (its crew-inactive refresh keeps the player as source); requires profile13 battle')
    prep.add_argument('--sixth-sense-sample',
                      help='Owner-supplied lamp sound file (decoded with local ffmpeg) replacing the '
                           'gun_intuition bank via res_mods; requires --sixth-sense-sound gun_intuition')
    prep.add_argument('--enable-p09d-ammo-service', action='store_true',
                      help='Native maintenance for the two source-bound MS-1 and IS-7 mounts')
    prep.add_argument('--enable-crew-recruitment', action='store_true',
                      help='One test_lab free100 MS-1 driver; requires isolated copy and P09D native hangar service')
    prep.add_argument('--enable-crew-transfer', action='store_true',
                      help='Original MS-1 crew transfer callbacks; requires explicit recruitment and ammunition service')
    prep.add_argument('--enable-roster-recruitment', action='store_true', help='Enable the explicit profile9 free50 roster policy; requires all earlier crew services')
    prep.add_argument('--enable-crew-progression', action='store_true', help='Enable profile10 native PersonalCase and first-skill selection; requires all previous crew services')
    prep.add_argument('--enable-crew-dismissal', action='store_true', help='Enable profile11 sparse crew and original dismissal confirmation; requires progression')
    prep.add_argument('--enable-barracks-recruitment', action='store_true', help='Enable profile12 original Barracks free50 recruitment; requires dismissal')
    prep.add_argument('--enable-cross-vehicle-crew', action='store_true',
                      help='Original MS-1/IS-7 crew callbacks; requires transfer, recruitment and ammunition service')
    prep.add_argument('--enable-research-service', action='store_true',
                      help='Explicit P09E zero-credit/XP research policy; requires isolated cross-vehicle crew/ammo hangar')
    prep.add_argument('--capture-hangar', action='store_true',
                      help='One passive native Hangar PNG; no login, input or UI transitions')
    prep.add_argument('--capture-ui-passive', action='store_true',
                      help='Bounded PNGs after actual user tooltip/Awards events; no input or UI transitions')
    prep.add_argument('--compiler',default='local/toolchains/cpython-2.7.3-x86/python.exe')
    prep.add_argument('--diagnostic-no-license-dialog',action='store_true')
    prep.add_argument('--disable-legacy-license-dialog',action='store_true',
                      help='owner-requested legacy service dialog disable; does not record agreement')
    prep.set_defaults(function=prepare)
    for name, function in (('install',install),('rollback',rollback)):
        command = sub.add_parser(name)
        command.add_argument('--out',required=True)
        command.set_defaults(function=function)
    args = parser.parse_args()
    args.function(args)


if __name__ == '__main__':
    main()
