"""Copy exact historic PNGs into the local-only web cache, with verified provenance."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zipfile
import zlib

WEB = Path(__file__).resolve().parents[1]
ROOT = WEB.parent
PNG_MAGIC = b'\x89PNG\r\n\x1a\n'


def digest_file(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def png_dimensions(data):
    if not data.startswith(PNG_MAGIC):
        raise ValueError('Not a PNG')
    offset, dimensions, ended = 8, None, False
    while offset < len(data):
        size = struct.unpack_from('>I', data, offset)[0]
        end = offset + 12 + size
        if end > len(data):
            raise ValueError('Truncated PNG chunk')
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + size]
        if zlib.crc32(kind + payload) & 0xffffffff != struct.unpack_from('>I', data, end - 4)[0]:
            raise ValueError('PNG CRC mismatch')
        if kind == b'IHDR':
            if dimensions is not None or size != 13:
                raise ValueError('Invalid PNG header')
            dimensions = struct.unpack_from('>II', payload)
            if not all(0 < n <= 4096 for n in dimensions):
                raise ValueError('Unbounded PNG dimensions')
        if kind == b'IEND':
            ended = end == len(data)
            break
        offset = end
    if not ended or dimensions is None:
        raise ValueError('Incomplete PNG')
    return dimensions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', required=True)
    args = parser.parse_args()
    evidence = (ROOT / args.evidence).resolve()
    if not evidence.is_relative_to((ROOT / 'local/web').resolve()):
        raise ValueError('Evidence must remain within local/web')
    evidence.mkdir(parents=True, exist_ok=False)
    config = json.loads((ROOT / 'config/project.local.json').read_text(encoding='utf-8-sig'))
    research = Path(config['paths']['research_client_root']).resolve(strict=True)
    if research == Path(config['paths']['original_client_root']).resolve():
        raise ValueError('Research path must differ from original')
    if config['target']['exact_build'] != 'v.0.9.1 #717':
        raise ValueError('Unexpected client build')
    baseline = json.loads((ROOT / 'local/evidence/20261002-p00-p01/baseline/research-manifest.json').read_text(encoding='utf-8-sig'))
    relative = 'res/packages/gui.pkg'
    expected = next(row for row in baseline['files'] if row['path'].lower() == relative)
    archive = (research / relative).resolve(strict=True)
    if not archive.is_relative_to(research) or archive.is_symlink():
        raise ValueError('Invalid archive path')
    archive_hash = digest_file(archive)
    if archive_hash != expected['sha256'] or archive.stat().st_size != expected['bytes']:
        raise ValueError('Archive differs from verified baseline')
    catalog = json.loads((WEB / 'data/catalog.v1.json').read_text(encoding='utf-8'))
    destination = (ROOT / 'local/web/catalog-assets/v1').resolve()
    manifest = {'schemaVersion': 'catalog-media.v1', 'build': catalog['build'],
                'sourceArchive': relative, 'sourceArchiveSha256': archive_hash,
                'vehicles': {}, 'maps': {}, 'nations': {}}
    files, absent = [], []
    with zipfile.ZipFile(archive) as package:
        names = {entry.filename.casefold(): entry.filename for entry in package.infolist()}
        if len(names) != len(package.infolist()):
            raise ValueError('Ambiguous case-insensitive archive members')

        def extract(member, kind, record_id, image_kind):
            info = package.getinfo(member)
            if not 0 < info.file_size <= 1024 * 1024:
                raise ValueError('Unexpected image size')
            raw = package.read(info)  # ZIP CRC is also checked by zipfile.
            width, height = png_dimensions(raw)
            target = (destination / kind / f'{record_id}.png').resolve()
            if not target.is_relative_to(destination):
                raise ValueError('Invalid generated destination')
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and target.read_bytes() != raw:
                raise ValueError('Versioned image already exists with different bytes')
            target.write_bytes(raw)
            row = {'url': f'/catalog-media/v1/{kind}/{record_id}.png', 'kind': image_kind,
                   'width': width, 'height': height, 'bytes': len(raw),
                   'sha256': hashlib.sha256(raw).hexdigest(), 'member': member}
            files.append({'path': target.relative_to(ROOT).as_posix(), **row})
            return row

        for vehicle in catalog['vehicles']:
            suffix = f"{vehicle['nation']}-{vehicle['key']}.png"
            render = names.get(f'gui/maps/icons/vehicle/{suffix}'.casefold())
            contour = names.get(f'gui/maps/icons/vehicle/contour/{suffix}'.casefold())
            member = render or contour
            if member:
                manifest['vehicles'][vehicle['id']] = extract(member, 'vehicles', vehicle['id'], 'render' if render else 'contour')
            else:
                if not vehicle['archived']:
                    raise ValueError(f"Missing main-catalog image: {vehicle['id']}")
                manifest['vehicles'][vehicle['id']] = None
                absent.append({'id': vehicle['id'], 'reason': 'No matching render or contour in gui.pkg', 'archived': True})
        for arena in catalog['maps']:
            member = names.get(f"gui/maps/icons/map/{arena['id']}.png".casefold())
            if not member:
                raise ValueError(f"Missing minimap: {arena['id']}")
            manifest['maps'][arena['id']] = extract(member, 'maps', arena['id'], 'minimap')
        for nation in sorted({vehicle['nation'] for vehicle in catalog['vehicles']}):
            member = names.get(f'gui/maps/icons/filters/nations/{nation}.png'.casefold())
            if not member:
                raise ValueError(f'Missing nation flag: {nation}')
            manifest['nations'][nation] = extract(member, 'nations', nation, 'flag')

    if digest_file(archive) != archive_hash:
        raise ValueError('Source archive changed during extraction')
    output = WEB / 'data/catalog-media.v1.json'
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    report = {'status': 'PASS', 'build': catalog['build'], 'sourceArchive': relative,
              'sourceArchiveSha256': archive_hash, 'baselineMatch': True, 'sourceUnchanged': True,
              'method': 'Unmodified PNG bytes, bounded ZIP member read and PNG CRC verification',
              'fileCount': len(files), 'totalBytes': sum(row['bytes'] for row in files),
              'renderCount': sum(row['kind'] == 'render' for row in files),
              'contourCount': sum(row['kind'] == 'contour' for row in files),
              'minimapCount': sum(row['kind'] == 'minimap' for row in files),
              'flagCount': sum(row['kind'] == 'flag' for row in files),
              'missing': absent, 'manifestSha256': digest_file(output), 'files': files}
    (evidence / 'sources.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key != 'files'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
