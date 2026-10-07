"""Apply owner-approved artwork replacements, preserving the historical catalog."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request
from PIL import Image

WEB = Path(__file__).resolve().parents[1]
ROOT = WEB.parent
LOCAL = ROOT / 'local/web'
MAX_BYTES = 8 * 1024 * 1024


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def image_metadata(raw):
    if not 0 < len(raw) <= MAX_BYTES or not raw.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('Invalid PNG payload')
    with Image.open(io.BytesIO(raw)) as image:
        if not 600 <= image.width <= 4096 or not 1 <= image.height <= 4096:
            raise ValueError('Unexpected image dimensions')
        image.verify()
    with Image.open(io.BytesIO(raw)) as image:
        if 'A' not in image.getbands():
            raise ValueError('Transparent alpha required')
        alpha = image.getchannel('A')
        bounds = alpha.getbbox()
        if not bounds or alpha.getextrema()[0] != 0:
            raise ValueError('Empty image or nontransparent background')
        # Inspect only: original PNG bytes are copied without image processing.
        x, y = max(0, bounds[0] - 10), max(0, bounds[1] - 10)
        right, bottom = min(image.width, bounds[2] + 10), min(image.height, bounds[3] + 10)
        return {'width': image.width, 'height': image.height, 'viewBox': [x, y, right-x, bottom-y],
                'bytes': len(raw), 'sha256': digest(raw)}


def local_file(relative):
    path = (ROOT / relative).resolve(strict=True)
    if not path.is_relative_to(LOCAL.resolve()):
        raise ValueError('Source must stay in local/web')
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('Source too large')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', required=True)
    args = parser.parse_args()
    evidence = (ROOT / args.evidence).resolve()
    if not evidence.is_relative_to(LOCAL.resolve()):
        raise ValueError('Evidence must stay in local/web')
    evidence.mkdir(parents=True, exist_ok=False)
    catalog_path = WEB / 'data/catalog.v1.json'
    before = digest(catalog_path.read_bytes())
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    ids = {vehicle['id'] for vehicle in catalog['vehicles']}
    choices = json.loads((WEB / 'data/art-donors.v1.json').read_text(encoding='utf-8'))
    modern = json.loads((WEB / 'data/catalog-modern.v1.json').read_text(encoding='utf-8'))
    native = json.loads((WEB / 'data/catalog-media.v1.json').read_text(encoding='utf-8'))
    if choices['schemaVersion'] != 'art-donors.v1' or choices['statsBuild'] != catalog['build']:
        raise ValueError('Unexpected donor configuration')
    cache = LOCAL / 'catalog-assets/official-current'
    output_dir = LOCAL / 'catalog-assets/v3/vehicles'
    cache.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {'schemaVersion': 'catalog-art-overrides.v1', 'statsBuild': catalog['build'],
                'generatedAt': datetime.now(timezone.utc).isoformat(), 'vehicles': {}}
    sources, prepared = [], []
    for vehicle_id, choice in choices['vehicles'].items():
        if vehicle_id not in ids or not re.fullmatch('[a-z0-9-]+', vehicle_id):
            raise ValueError('Unknown target vehicle')
        record = {'vehicleId': vehicle_id, **choice}
        if choice['action'] == 'keep':
            original = local_file(f'local/web/catalog-assets/v1/vehicles/{vehicle_id}.png').read_bytes()
            if digest(original) != native['vehicles'][vehicle_id]['sha256']:
                raise ValueError('Retained original hash mismatch')
            sources.append({**record, 'status': 'KEPT', 'sha256': digest(original)})
            continue
        if choice['action'] == 'catalog':
            donor = modern['vehicles'][choice['donorVehicleId']]
            raw = local_file(f"local/web/catalog-assets/v2/vehicles/{choice['donorVehicleId']}.png").read_bytes()
            if digest(raw) != donor['sha256']:
                raise ValueError('Donor catalog hash mismatch')
            record.update({key: donor[key] for key in ['modelId', 'sourceUrl']})
        elif choice['action'] == 'official':
            model, url = choice['modelId'], choice['sourceUrl']
            parsed = urllib.parse.urlparse(url)
            if (not re.fullmatch('[a-z0-9_-]+', model) or parsed.scheme != 'https'
                    or parsed.netloc not in ['na-wotp.wgcdn.co', 'eu-wotp.wgcdn.co']
                    or parsed.path != f'/dcont/tankopedia_images/{model}/{model}_image.png'
                    or parsed.query or parsed.fragment):
                raise ValueError('Unapproved image source')
            cached = cache / f'{model}.png'
            if cached.exists():
                raw = local_file(cached.relative_to(ROOT)).read_bytes()
                record['cache'] = True
            else:
                with urllib.request.urlopen(url, timeout=25) as response:
                    if response.url != url:
                        raise ValueError('Unexpected image redirect')
                    raw = response.read(MAX_BYTES + 1)
                    record.update({'httpStatus': response.status, 'contentType': response.headers.get('Content-Type'),
                                   'etag': response.headers.get('ETag'), 'lastModified': response.headers.get('Last-Modified')})
                image_metadata(raw)
                cached.write_bytes(raw)
        elif choice['action'] == 'upscale':
            raw = local_file(choice['sourceFile']).read_bytes()
            original = local_file(choice['sourceOriginal']).read_bytes()
            if digest(original) != native['vehicles'][vehicle_id]['sha256']:
                raise ValueError('Upscale reference hash mismatch')
            record.update({'sourceOriginalSha256': digest(original),
                           'promptSha256': digest(local_file(choice['promptFile']).read_bytes())})
        else:
            raise ValueError('Unknown action')
        meta = image_metadata(raw)
        prepared.append((output_dir / f'{vehicle_id}.png', raw))
        art = {**meta, 'url': f'/catalog-media/v3/vehicles/{vehicle_id}.png',
               'kind': 'upscaled-render' if choice['action'] == 'upscale' else 'modern-render',
               'ownerChoice': choice['choice']}
        for key in ['donorName', 'donorVehicleId', 'modelId', 'sourceUrl', 'sourcePage',
                    'tool', 'sourceOriginalSha256', 'promptSha256']:
            if key in record:
                art[key] = record[key]
        manifest['vehicles'][vehicle_id] = art
        sources.append({**record, **meta, 'status': 'PASS'})
    if digest(catalog_path.read_bytes()) != before:
        raise ValueError('Historical catalog changed during artwork preparation')
    for target, raw in prepared:
        target.write_bytes(raw)
    manifest_path = WEB / 'data/catalog-art-overrides.v1.json'
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    report = {'status': 'PASS', 'overrides': len(prepared), 'catalogSha256Unchanged': before,
              'manifestSha256': digest(manifest_path.read_bytes()), 'sources': sources}
    (evidence / 'sources.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key != 'sources'}))


if __name__ == '__main__':
    main()
