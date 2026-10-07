"""Fetch current official tank art by verified model identity; never import modern stats."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request
from PIL import Image

sys.dont_write_bytecode = True
WEB = Path(__file__).resolve().parents[1]
ROOT = WEB.parent
spec = importlib.util.spec_from_file_location('catalog_builder', WEB / 'scripts/build-catalog.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
CDN = 'https://na-wotp.wgcdn.co/dcont/tankopedia_images'
SOURCE_PAGE = 'https://worldoftanks.com/en/tankopedia/16913-G98_Waffentrager_E100/'
MAX_BYTES = 8 * 1024 * 1024


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', required=True)
    args = parser.parse_args()
    evidence = (ROOT / args.evidence).resolve()
    if not evidence.is_relative_to((ROOT / 'local/web').resolve()):
        raise ValueError('Evidence path must remain in local/web')
    evidence.mkdir(parents=True, exist_ok=False)
    config = json.loads((ROOT / 'config/project.local.json').read_text(encoding='utf-8-sig'))
    research = Path(config['paths']['research_client_root']).resolve(strict=True)
    if research == Path(config['paths']['original_client_root']).resolve():
        raise ValueError('Research and original must be separate')
    baseline = {row['path'].lower(): row for row in json.loads((ROOT / 'local/evidence/20261002-p00-p01/baseline/research-manifest.json').read_text(encoding='utf-8-sig'))['files']}
    catalog = json.loads((WEB / 'data/catalog.v1.json').read_text(encoding='utf-8'))
    aliases = json.loads((WEB / 'data/modern-art-aliases.v1.json').read_text(encoding='utf-8'))['aliases']
    records, sources = [], []
    for vehicle in catalog['vehicles']:
        path = (research / vehicle['source']).resolve(strict=True)
        if not path.is_relative_to(research) or path.stat().st_size > 16 * 1024 * 1024:
            raise ValueError('Invalid vehicle source')
        raw = path.read_bytes()
        sha256 = hashlib.sha256(raw).hexdigest()
        expected = baseline[vehicle['source'].lower()]
        if sha256 != expected['sha256'] or len(raw) != expected['bytes']:
            raise ValueError('Vehicle source differs from baseline')
        node = builder.convert(builder.decode(raw))
        model_ids = sorted({chassis['models']['undamaged'].split('/')[2].lower() for chassis in node['chassis'].values()})
        if len(model_ids) != 1 or not re.fullmatch('[a-z0-9_-]+', model_ids[0]):
            raise ValueError(f"Ambiguous model identity: {vehicle['id']}: {model_ids}")
        alias = aliases.get(vehicle['id'])
        records.append({'id': vehicle['id'], 'name': vehicle['name'], 'archived': vehicle['archived'],
                        'historicalModelId': model_ids[0], 'modelId': alias['modelId'] if alias else model_ids[0], 'alias': alias})
        sources.append({'path': vehicle['source'], 'sha256': sha256, 'baselineMatch': True})
    cache = ROOT / 'local/web/catalog-assets/official-current'
    cache.mkdir(parents=True, exist_ok=True)

    def download(model_id):
        url = f'{CDN}/{model_id}/{model_id}_image.png'
        target = cache / f'{model_id}.png'
        result = {'modelId': model_id, 'sourceUrl': url}
        if target.exists():
            raw = target.read_bytes()
            result['cache'] = True
        else:
            try:
                with urllib.request.urlopen(url, timeout=25) as response:
                    if not response.url.startswith(CDN + '/'):
                        raise ValueError('Unexpected CDN redirect')
                    raw = response.read(MAX_BYTES + 1)
                    result.update({'httpStatus': response.status, 'contentType': response.headers.get('Content-Type'),
                                   'lastModified': response.headers.get('Last-Modified'), 'etag': response.headers.get('ETag')})
            except urllib.error.HTTPError as error:
                return {**result, 'status': 'UNAVAILABLE', 'httpStatus': error.code}
            except (urllib.error.URLError, TimeoutError) as error:
                return {**result, 'status': 'FETCH_ERROR', 'error': str(error)}
        if not 0 < len(raw) <= MAX_BYTES or not raw.startswith(b'\x89PNG\r\n\x1a\n'):
            return {**result, 'status': 'INVALID_IMAGE'}
        with Image.open(io.BytesIO(raw)) as image:
            image.verify()
        with Image.open(io.BytesIO(raw)) as image:
            if image.width < 600 or image.width > 4096 or image.height > 4096:
                return {**result, 'status': 'LOW_RESOLUTION', 'width': image.width, 'height': image.height}
            if 'A' not in image.getbands():
                return {**result, 'status': 'MISSING_ALPHA'}
            # Inspect alpha bounds only. Never crop or rewrite source PNG bytes.
            bounds = image.getchannel('A').getbbox()
            if not bounds:
                return {**result, 'status': 'EMPTY_IMAGE'}
            pad = 10
            x, y = max(0, bounds[0] - pad), max(0, bounds[1] - pad)
            right, bottom = min(image.width, bounds[2] + pad), min(image.height, bounds[3] + pad)
            result.update({'width': image.width, 'height': image.height, 'viewBox': [x, y, right - x, bottom - y]})
        target.write_bytes(raw)
        return {**result, 'status': 'PASS', 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}

    downloads = {}
    model_ids = sorted({row['modelId'] for row in records})
    with ThreadPoolExecutor(max_workers=3) as pool:
        tasks = {pool.submit(download, model): model for model in model_ids}
        for future in as_completed(tasks):
            result = future.result()
            downloads[result['modelId']] = result
            if len(downloads) % 25 == 0:
                print(f'Checked {len(downloads)}/{len(model_ids)} official image resources', flush=True)
    manifest = {'schemaVersion': 'catalog-modern.v1', 'statsBuild': catalog['build'],
                'retrievedAt': datetime.now(timezone.utc).isoformat(), 'sourcePage': SOURCE_PAGE, 'vehicles': {}}
    unavailable = []
    for record in records:
        result = downloads[record['modelId']]
        if result['status'] != 'PASS':
            unavailable.append({**record, 'result': result})
            continue
        destination = ROOT / 'local/web/catalog-assets/v2/vehicles' / f"{record['id']}.png"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((cache / f"{record['modelId']}.png").read_bytes())
        manifest['vehicles'][record['id']] = {key: result[key] for key in ['modelId', 'sourceUrl', 'width', 'height', 'viewBox', 'bytes', 'sha256']}
        manifest['vehicles'][record['id']].update({'url': f"/catalog-media/v2/vehicles/{record['id']}.png", 'kind': 'modern-render'})
        if record['alias']:
            manifest['vehicles'][record['id']]['identityAlias'] = record['alias']
    output = WEB / 'data/catalog-modern.v1.json'
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    report = {'status': 'PASS' if not unavailable else 'PARTIAL', 'matched': len(manifest['vehicles']),
              'mainMatched': sum(row['id'] in manifest['vehicles'] for row in records if not row['archived']),
              'catalogSha256Unchanged': hashlib.sha256((WEB / 'data/catalog.v1.json').read_bytes()).hexdigest(),
              'manifestSha256': hashlib.sha256(output.read_bytes()).hexdigest(),
              'sourcePage': SOURCE_PAGE, 'retrievedAt': manifest['retrievedAt'],
              'unavailable': unavailable, 'downloads': list(downloads.values()), 'identitySources': sources}
    (evidence / 'sources.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key not in ['downloads','identitySources']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
