"""Prepare/install/rollback the explicit local interactive client compatibility.

Only install/rollback mutate the configured research copy, under the actual
native instance mutex. prepare is reviewable and never touches either client.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
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

MODULES = ('sr_interactive', 'project_auth', 'project_preferences', 'hangar_bootstrap', 'hangar_ui_probe', 'hangar_capabilities', 'crew_capabilities', 'ms1_crew_probe', 'ms1_crew_scenario', 'hangar_limits_scenario', 'hangar_windows_scenario', 'hangar_relogin_scenario', 'account_switch_scenario', 'long_hangar_scenario', 'ms1_ammo_probe', 'ms1_ammo_scenario', 'arena_entry_probe', 'arena_bootstrap', 'arena_space_scenario', 'arena_vehicle_scenario', 'arena_ready_scenario', 'arena_movement_scenario', 'map_drive_scenario', 'map_drive_client', 'map_drive_acceptance')
LOGS = ('python.log', 'Influx_PS.log', 'Influx_PS.bak')


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


def prepare(args):
    _, paths = config()
    out = local_path(args.out, paths)
    if out.exists() and any(out.iterdir()):
        raise ValueError('prepare requires an empty output directory')
    root, original = paths['research_client_root'], paths['original_client_root']
    endpoint = args.endpoint
    if not re.fullmatch(r'127\.0\.0\.1:([0-9]{1,5})', endpoint) or not 1024 <= int(endpoint.rsplit(':', 1)[1]) <= 65535:
        raise ValueError('endpoint must be numeric IPv4 loopback with unprivileged port')
    if not re.fullmatch(r'http://127\.0\.0\.1:[0-9]{1,5}/register',args.registration_url):
        raise ValueError('registration URL must be the owned numeric loopback /register route')
    if not 1024 <= int(args.registration_url.split(':')[2].split('/')[0]) <= 65535:
        raise ValueError('registration port outside unprivileged range')
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
    registration = [node for node in gui.iter() if node.findtext('name') == 'registrationURL']
    if len(registration) != 1:
        raise ValueError('unmeasured registration URL setting')
    field = registration[0].find('value')
    if field is None:
        field = registration[0]
    field.text = args.registration_url
    payloads[gui_path] = xml_bytes(gui)
    resource_evidence.update(allowed_login=endpoint, public_name='Стальной рубеж', remember_password=False,
                             registration_url=args.registration_url, token_login_enabled=False)
    resource_evidence['empty_url_settings'] = [name for name in resource_evidence['empty_url_settings'] if name != 'registrationURL']
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
    save_json(out/'install-plan.json', plan)
    print(json.dumps({'status':'PREPARED','plan':str(out/'install-plan.json'),'client_write_performed':False},ensure_ascii=False))


def load_plan(args):
    _, paths = config()
    out = local_path(args.out, paths)
    plan = json.loads(read_limited(out/'install-plan.json', 1024*1024))
    root = paths['research_client_root']
    if plan['schema_version'] != 1 or Path(plan['research_root']) != root or Path(plan['original_root']) != paths['original_client_root']:
        raise ValueError('install plan roots/schema changed')
    return out, root, plan


def install(args):
    from instance_mutex import control
    out, root, plan = load_plan(args)
    if (out/'patch-ledger.json').exists():
        raise ValueError('installation already attempted; use its ledger and rollback')
    with control() as mutex:
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
    with control():
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
    prep.add_argument('--public-key',required=True)
    prep.add_argument('--endpoint',default='127.0.0.1:20014')
    prep.add_argument('--registration-url',default='http://127.0.0.1:3092/register')
    prep.add_argument('--profile-dir',required=True)
    prep.add_argument('--trace-dir',required=True)
    prep.add_argument('--test-control')
    prep.add_argument('--enable-map-drive', action='store_true',
                      help='Explicit test_lab native battle-button travel; no automatic input or quit')
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
