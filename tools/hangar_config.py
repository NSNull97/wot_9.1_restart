"""Resource overrides for the bounded native hangar experiment; no remote URLs."""
import hashlib
import xml.etree.ElementTree as ET
from client_audit import package_read, read_limited
from packed_xml import decode


def overrides(root, diagnostic_no_license_dialog=False):
    from client_probe import to_element
    scripts_raw = read_limited(root/'res/scripts_config.xml')
    gui_raw = package_read(root, 'res/packages/gui.pkg', 'gui/gui_settings.xml')
    scripts = to_element('scripts_config.xml', decode(scripts_raw))
    login = scripts.find('login')
    if login is None or scripts.find('csisUrl') is None:
        raise ValueError('unrecognized original endpoint configuration')
    login.clear()
    host = ET.SubElement(login, 'host')
    for key, value in (('name', 'Steel Frontier local laboratory'),
                       ('url', '127.0.0.1:20014'), ('url_token', '127.0.0.1:20014'),
                       ('public_key_path', 'p01_login.pubkey'), ('periphery_id', '0')):
        ET.SubElement(host, key).text = value
    scripts.find('csisUrl').text = ''
    gui = to_element('gui_settings.xml', decode(gui_raw))
    disabled = []
    for setting in gui.iter():
        if setting.findtext('type', '').lower() == 'url':
            disabled.append(setting.findtext('name', '<unnamed>'))
            setting.text = ''
            if setting.find('value') is not None:
                setting.find('value').text = ''
    def set_boolean(name, value):
        matches = [s for s in gui.iter() if s.findtext('name') == name]
        if len(matches) != 1:
            raise ValueError('expected one original GUI setting: '+name)
        s = matches[0]
        target = s.find('value')
        if target is None:
            target = s
        target.text = 'true' if value else 'false'
    for name in ('voiceChat', 'roaming'):
        set_boolean(name, False)
    for name in ('loginRssFeed', 'movingText'):
        groups = [s for s in gui.iter() if s.findtext('name') == name]
        if len(groups) != 1:
            raise ValueError('expected one original GUI group: '+name)
        shows = [s for s in groups[0].iter() if s.findtext('name') == 'show']
        if len(shows) != 1:
            raise ValueError('expected one group show flag: '+name)
        target = shows[0].find('value')
        if target is None:
            target = shows[0]
        target.text = 'false'
    if not disabled:
        raise ValueError('URL isolation did not find original URL settings')
    result = {
        'res_mods/0.9.1/scripts_config.xml': ET.tostring(scripts, encoding='utf-8', xml_declaration=True),
        'res_mods/0.9.1/gui/gui_settings.xml': ET.tostring(gui, encoding='utf-8', xml_declaration=True),
    }
    evidence = {'scripts_source': 'res/scripts_config.xml', 'scripts_sha256': hashlib.sha256(scripts_raw).hexdigest(),
                'gui_source': 'res/packages/gui.pkg!gui/gui_settings.xml', 'gui_sha256': hashlib.sha256(gui_raw).hexdigest(),
                'empty_url_settings': disabled, 'rss': False, 'voice': False, 'roaming': False,
                'allowed_login': '127.0.0.1:20014'}
    if diagnostic_no_license_dialog:
        version_raw = read_limited(root/'version.xml', 16384)
        version = ET.fromstring(version_raw)
        field = version.find('showLicense')
        if field is None or field.text.strip() != '3' or version.findtext('version', '').strip() != 'v.0.9.1 #717':
            raise ValueError('unmeasured version/license configuration')
        field.text = '0'
        result['version.xml'] = ET.tostring(version, encoding='utf-8', xml_declaration=True)
        evidence['diagnostic_license_dialog'] = {'source': 'version.xml', 'before_sha256':hashlib.sha256(version_raw).hexdigest(),
            'showLicense_before':3, 'showLicense_after':0, 'user_agreement_recorded':False,
            'scope':'temporary unattended laboratory only; no user acceptance is claimed'}
    return result, evidence
