# -*- coding: utf-8 -*-
"""Owned local preferences for #717; never call the native AppData writer.

Native savePreferences ignores the Python path getter. The measured engine
prefixes even an absolute path; require that exact invalid Windows path before
redirecting Python caches and persisting the original DataSection ourselves.
"""
import hashlib
import os
import re
import xml.etree.ElementTree as ET

try:
    text_type = unicode
except NameError:
    text_type = str

MAX_BYTES = 4 * 1024 * 1024


def owned(path, root):
    path = os.path.normcase(os.path.realpath(path))
    root = os.path.normcase(os.path.realpath(root))
    if not path.startswith(root.rstrip('\\/') + os.sep):
        raise ValueError('path escapes owned local directory')
    return path


def serialize(section):
    count = [0]

    def node(name, data, depth):
        count[0] += 1
        if depth > 32 or count[0] > 8192 or not re.match(r'\A[A-Za-z_][A-Za-z0-9_.-]*\Z', name):
            raise ValueError('preferences tree exceeds bounded XML schema')
        result = ET.Element(name)
        value = data.asString
        if not isinstance(value, text_type):
            value = value.decode('utf8', 'strict')
        # LoginDataLoader's actual secrets. Remember-password is disabled in
        # GUI config too; a non-empty secret is an error, never written to disk.
        if name.lower() in ('password', 'pwd', 'token2') and value.strip():
            raise ValueError('secret field in preferences refused')
        if value:
            result.text = value
        for child_name, child in data.items():
            result.append(node(child_name, child, depth + 1))
        return result

    payload = ET.tostring(node('preferences.xml', section, 0), encoding='utf-8')
    if len(payload) > MAX_BYTES:
        raise ValueError('preferences XML too large')
    ET.fromstring(payload)
    return payload


def guarded_write(path, payload):
    temporary = path + '.project-pending'
    if os.path.exists(temporary):
        raise ValueError('unfinished preferences write exists; preserve for inspection')
    with open(temporary, 'wb') as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    # Both renames target absent files. Keep the preceding contents until the
    # replacement is verified; a crash leaves explicit recovery evidence.
    # This two-rename transaction is not claimed as one atomic Windows replace.
    previous = path + '.project-previous'
    if os.path.exists(previous):
        raise ValueError('unfinished previous preferences write exists')
    existed = os.path.exists(path)
    if existed:
        os.rename(path, previous)
    os.rename(temporary, path)
    with open(path, 'rb') as stream:
        actual = stream.read(MAX_BYTES + 1)
    if actual != payload:
        raise IOError('owned preferences verification failed')
    if existed:
        os.remove(previous)


def install(args, settings, record):
    import BigWorld
    import ResMgr
    import Settings
    directory = owned(settings['profile_dir'], settings['local_root'])
    if not os.path.isdir(directory):
        raise ValueError('prepared local profile directory missing')
    if settings.get('preferences_resource') != 'sr_preferences.xml':
        raise ValueError('unexpected owned preferences resource name')
    path = os.path.join(directory, settings['preferences_resource'])
    path_bytes = path.encode('utf8')
    actual = BigWorld.wg_getPreferencesFilePath()
    required = b'Wargaming.net/WorldOfTanks/' + path_bytes.replace(b'\\', b'/')
    if isinstance(actual, text_type):
        actual = actual.encode('utf8')
    record('preferences_probe', native_path=actual, required_native_path=required,
           owned_path=path, native_writer_used=False)
    if actual.lower() != required.lower():
        raise ValueError('unmeasured native preferences path; refusing GUI and credentials')
    if not os.path.exists(path):
        guarded_write(path, serialize(args[2]))
    elif os.path.getsize(path) > MAX_BYTES:
        raise ValueError('owned preferences file too large')
    with open(path, 'rb') as stream:
        existing = stream.read(MAX_BYTES + 1)
    if b'<!DOCTYPE' in existing.upper() or b'<!ENTITY' in existing.upper():
        raise ValueError('preferences entity declarations refused')
    ET.fromstring(existing)
    # #717 openSection did not resolve an absolute filename in UI-only02.
    # Installer prepends this owned directory in the backed-up paths.xml;
    # lookup is consequently through the original resource-search contract.
    section = ResMgr.openSection(settings['preferences_resource'].encode('ascii'))
    if section is None:
        raise ValueError('native ResMgr could not load owned preferences XML')
    BigWorld.wg_getPreferencesFilePath = lambda: path_bytes

    class LocalSettings(Settings.Settings):
        def save(self):
            payload = serialize(self.userPrefs)
            guarded_write(path, payload)
            record('preferences_local_save', path=path, bytes=len(payload),
                   sha256=hashlib.sha256(payload).hexdigest(), writer='owned_DataSection_XML',
                   native_writer_used=False)

    Settings.g_instance = LocalSettings(args[0], args[1], section)
    # Native C++ internal writer still has the measured invalid path. Python
    # callers use the same real local persistence as Settings.save().
    BigWorld.savePreferences = Settings.g_instance.save
    Settings.g_instance.save()
    record('preferences_local_ready', path=path, class_name=type(section).__name__,
           native_writer_used=False, credentials_allowed=True)
    return Settings.g_instance
