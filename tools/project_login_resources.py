"""Targeted project login captions; preserve all original localization keys.

The derived MO is an ignored install artifact only. Original resource/catalog
contents are never committed or distributed by this tool.
"""
import hashlib
import io
import gettext
import struct

CHANGES = {
    'login/login': 'Почта:',
    'login/status/invalid_login': 'Введите почту, указанную при регистрации на сайте.',
    'login/status/invalid_password': 'Пароль: от 15 до 128 символов. Пробелы сохраняются.',
    'login/status/LOGIN_REJECTED_INVALID_PASSWORD': 'Неверная почта или пароль.',
    'login/status/LOGIN_REJECTED_NO_SUCH_USER': 'Неверная почта или пароль.',
}


def project_menu(raw):
    if len(raw) > 8*1024*1024 or len(raw) < 28:
        raise ValueError('localization source size outside bound')
    endian = '<' if raw[:4] == b'\xde\x12\x04\x95' else '>' if raw[:4] == b'\x95\x04\x12\xde' else None
    if not endian:
        raise ValueError('unrecognized MO magic')
    magic,revision,count,originals,translations,_,_ = struct.unpack_from(endian+'7I',raw)
    if revision != 0 or not 1 <= count <= 50000:
        raise ValueError('unmeasured MO version/count')
    def table(base,index):
        length,offset = struct.unpack_from(endian+'2I',raw,base+index*8)
        if offset+length >= len(raw) or raw[offset+length] != 0:
            raise ValueError('invalid MO string boundary')
        return raw[offset:offset+length]
    entries = [(table(originals,i),table(translations,i)) for i in range(count)]
    mapping = dict(entries)
    if len(mapping) != count:
        raise ValueError('duplicate MO original strings')
    changes = []
    for key,value in CHANGES.items():
        encoded = key.encode('utf8')
        if encoded not in mapping:
            raise ValueError('unmeasured localization key: '+key)
        changes.append({'key':key,'before':mapping[encoded].decode('utf8'),'after':value})
        mapping[encoded] = value.encode('utf8')
    pairs = sorted(mapping.items())
    original_table=[];translated_table=[];strings=bytearray()
    start=28+16*count
    for original,translation in pairs:
        original_table.append((len(original),start+len(strings)));strings.extend(original+b'\0')
    for original,translation in pairs:
        translated_table.append((len(translation),start+len(strings)));strings.extend(translation+b'\0')
    result=(struct.pack('<7I',0x950412de,0,count,28,28+8*count,0,0)+
            b''.join(struct.pack('<2I',*entry)for entry in original_table+translated_table)+bytes(strings))
    translated = gettext.GNUTranslations(io.BytesIO(result))
    for key,value in CHANGES.items():
        if translated.gettext(key) != value:
            raise ValueError('generated MO translation verification failed')
    return result,{'source':'res/text/LC_MESSAGES/menu.mo','source_sha256':hashlib.sha256(raw).hexdigest(),
                   'output_sha256':hashlib.sha256(result).hexdigest(),'entry_count':count,
                   'changes':changes,'stable_keys_preserved':True}
