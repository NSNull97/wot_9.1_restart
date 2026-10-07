"""Extract the five original class badges without modifying their pixels."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import zipfile

sys.dont_write_bytecode = True
WEB = Path(__file__).resolve().parents[1]
ROOT = WEB.parent
spec = importlib.util.spec_from_file_location('catalog_media', WEB / 'scripts/extract-catalog-media.py')
media = importlib.util.module_from_spec(spec)
spec.loader.exec_module(media)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', required=True)
    args = parser.parse_args()
    evidence = (ROOT / args.evidence).resolve()
    if not evidence.is_relative_to((ROOT / 'local/web').resolve()):
        raise ValueError('Evidence must remain in local/web')
    evidence.mkdir(parents=True, exist_ok=False)
    config = json.loads((ROOT / 'config/project.local.json').read_text(encoding='utf-8-sig'))
    research = Path(config['paths']['research_client_root']).resolve(strict=True)
    if research == Path(config['paths']['original_client_root']).resolve() or config['target']['exact_build'] != 'v.0.9.1 #717':
        raise ValueError('Unexpected client')
    archive = (research / 'res/packages/gui.pkg').resolve(strict=True)
    if not archive.is_relative_to(research) or archive.is_symlink():
        raise ValueError('Invalid source path')
    baseline = json.loads((ROOT / 'local/evidence/20261002-p00-p01/baseline/research-manifest.json').read_text(encoding='utf-8-sig'))
    expected = next(row for row in baseline['files'] if row['path'].lower() == 'res/packages/gui.pkg')
    archive_hash = media.digest_file(archive)
    if archive_hash != expected['sha256'] or archive.stat().st_size != expected['bytes']:
        raise ValueError('Source archive differs from baseline')
    manifest = {'schemaVersion': 'catalog-class-icons.v1', 'build': '0.9.1 #717',
                'sourceArchive': 'res/packages/gui.pkg', 'sourceArchiveSha256': archive_hash, 'classes': {}}
    with zipfile.ZipFile(archive) as package:
        for kind in ['lightTank', 'mediumTank', 'heavyTank', 'AT-SPG', 'SPG']:
            member = f'gui/maps/icons/filters/tanks/{kind}.png'
            info = package.getinfo(member)
            if not 0 < info.file_size < 65536:
                raise ValueError('Unexpected PNG size')
            raw = package.read(info)
            width, height = media.png_dimensions(raw)
            target = (ROOT / f'local/web/catalog-assets/v1/classes/{kind}.png').resolve()
            if not target.is_relative_to((ROOT / 'local/web/catalog-assets').resolve()):
                raise ValueError('Invalid cache path')
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and target.read_bytes() != raw:
                raise ValueError('Existing icon has different bytes')
            target.write_bytes(raw)
            manifest['classes'][kind] = {'url': f'/catalog-media/v1/classes/{kind}.png',
                'width': width, 'height': height, 'bytes': len(raw),
                'sha256': hashlib.sha256(raw).hexdigest(), 'member': member}
    if media.digest_file(archive) != archive_hash:
        raise ValueError('Source archive changed')
    (WEB / 'data/catalog-class-icons.v1.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    report = {'status': 'PASS', 'baselineMatch': True, 'sourceUnchanged': True,
              'method': 'Exact client PNG bytes; ZIP/PNG CRC and archive SHA-256 verified', **manifest}
    (evidence / 'sources.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': 'PASS', 'icons': len(manifest['classes']), 'dimensions': [width, height]}))


if __name__ == '__main__':
    main()
