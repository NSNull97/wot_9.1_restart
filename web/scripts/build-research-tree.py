"""Extract module research edges from the pinned research client; never execute client code."""
import argparse
import gettext
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
WEB = Path(__file__).resolve().parents[1]
ROOT = WEB.parent
spec = importlib.util.spec_from_file_location('catalog_builder', WEB / 'scripts/build-catalog.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', required=True)
    args = parser.parse_args()
    evidence = (ROOT / args.evidence).resolve()
    if not evidence.is_relative_to((ROOT / 'local/web').resolve()):
        raise ValueError('Evidence must stay in local/web')
    evidence.mkdir(parents=True, exist_ok=False)
    config = json.loads((ROOT / 'config/project.local.json').read_text(encoding='utf-8-sig'))
    research = Path(config['paths']['research_client_root']).resolve(strict=True)
    if research == Path(config['paths']['original_client_root']).resolve() or config['target']['exact_build'] != 'v.0.9.1 #717':
        raise ValueError('Wrong research client')
    baseline = {row['path'].lower(): row for row in json.loads((ROOT / 'local/evidence/20261002-p00-p01/baseline/research-manifest.json').read_text(encoding='utf-8-sig'))['files']}
    facts_bytes = (WEB / 'data/catalog.v1.json').read_bytes()
    facts = json.loads(facts_bytes)
    sources, translations, special_refs, warnings = {}, {}, [], []

    def read(relative):
        path = (research / relative).resolve(strict=True)
        if not path.is_relative_to(research) or path.is_symlink() or path.stat().st_size > 16 * 1024 * 1024:
            raise ValueError('Unbounded source')
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        expected = baseline.get(relative.lower())
        if not expected or digest != expected['sha256'] or len(raw) != expected['bytes']:
            raise ValueError(f'Baseline mismatch: {relative}')
        sources[relative] = {'sha256': digest, 'bytes': len(raw), 'baselineMatch': True}
        return raw

    def xml(relative):
        return builder.convert(builder.decode(read(relative)))

    def label(reference, fallback):
        if not isinstance(reference, str) or not reference.startswith('#'):
            return fallback
        domain, key = reference[1:].split(':', 1)
        if domain not in translations:
            translations[domain] = gettext.GNUTranslations(io.BytesIO(read(f'res/text/lc_messages/{domain}.mo')))
        value = translations[domain].gettext(key).strip()
        if key not in translations[domain]._catalog or not value or value == '?empty?':
            warnings.append({'reference': reference, 'fallback': fallback})
            return fallback
        return value

    def price(value):
        if value is None:
            return None
        if isinstance(value, dict) and 'gold' in value:
            return {'amount': builder.number(value.get('$', value['gold'])), 'currency': 'gold'}
        return {'amount': builder.number(value), 'currency': 'credits'}

    trees, prices = {}, {}
    for nation in builder.NATIONS:
        prefix = f'res/scripts/item_defs/vehicles/{nation}'
        listing = xml(f'{prefix}/list.xml')
        components = {kind: xml(f'{prefix}/components/{kind}.xml') for kind in ['guns', 'engines', 'radios']}
        native_vehicles = {v['key']: v for v in facts['vehicles'] if v['nation'] == nation}
        for key, info in listing.items():
            prices[native_vehicles[key]['id']] = price(info.get('price'))
        for vehicle in native_vehicles.values():
            raw = xml(vehicle['source'])
            nodes, node_by_key, pending_edges = [], {}, []

            def add(kind, key, data, turret_key=None):
                if data == 'shared' or (isinstance(data, dict) and data.get('$') == 'shared'):
                    data = builder.merged(components[kind + 's']['shared'][key], data)
                if not isinstance(data, dict):
                    raise ValueError(f'Unknown {kind}: {vehicle["id"]}/{key}')
                identity = (kind, key)
                if identity not in node_by_key:
                    node = {'id': f'{kind}-{sum(n["kind"] == kind for n in nodes)}', 'kind': kind, 'key': key,
                            'name': label(data.get('userString'), key.lstrip('_')), 'level': builder.number(data.get('level')),
                            'price': price(data.get('price')), 'weightKg': builder.number(data.get('weight'))}
                    if kind == 'chassis':
                        node.update(maxLoadKg=builder.number(data.get('maxLoad')), rotation=builder.number(data.get('rotationSpeed')),
                                    terrainResistance=builder.numbers(data.get('terrainResistance')))
                    elif kind == 'engine':
                        node.update(power=builder.number(data.get('power')), fireChance=builder.number(data.get('fireStartingChance')))
                    elif kind == 'radio':
                        node.update(range=builder.number(data.get('distance')))
                    elif kind == 'gun':
                        node['turrets'] = []
                    node_by_key[identity] = node
                    nodes.append(node)
                node = node_by_key[identity]
                if turret_key and turret_key not in node['turrets']:
                    node['turrets'].append(turret_key)
                unlocks = data.get('unlocks') or {}
                if not isinstance(unlocks, dict):
                    raise ValueError(f'Unknown unlock section: {vehicle["id"]}/{key}')
                for target_kind, entries in unlocks.items():
                    for entry in entries if isinstance(entries, list) else [entries]:
                        if not isinstance(entry, dict) or '$' not in entry or target_kind not in ['chassis', 'engine', 'radio', 'turret', 'gun', 'vehicle']:
                            raise ValueError(f'Unknown unlock: {vehicle["id"]}/{key}: {entry!r}')
                        target_key = entry['$']
                        # Packed XML kind5 exposes its original base64 textual representation.
                        # Accept it only if it resolves exactly to an enumerated module/vehicle below.
                        if isinstance(target_key, dict) and set(target_key) == {'base64'}:
                            special_refs.append({'vehicle': vehicle['id'], 'kind': target_kind, 'target': target_key['base64']})
                            target_key = target_key['base64']
                        if not isinstance(target_key, str):
                            raise ValueError('Non-text research reference')
                        xp = builder.number(entry.get('cost'))
                        if xp is None or xp < 0 or xp != int(xp):
                            raise ValueError('Invalid research XP')
                        edge = (node['id'], target_kind, target_key, xp)
                        if edge not in pending_edges:
                            pending_edges.append(edge)

            for key, data in raw.get('chassis', {}).items():
                add('chassis', key, data)
            for kind in ['engine', 'radio']:
                for key, data in raw.get(kind + 's', {}).items():
                    add(kind, key, data)
            for key, data in raw.get('turrets0', {}).items():
                add('turret', key, data)
                for gun_key, gun in data.get('guns', {}).items():
                    add('gun', gun_key, gun, key)
            edges = []
            for source, kind, key, xp in pending_edges:
                if kind == 'vehicle' and (kind, key) not in node_by_key:
                    target = native_vehicles.get(key)
                    if not target:
                        raise ValueError(f'Unknown next vehicle {nation}/{key}')
                    node = {'id': 'vehicle-' + target['id'], 'kind': kind, 'key': key, 'name': target['name'],
                            'level': target['tier'], 'vehicleId': target['id'], 'price': prices[target['id']]}
                    node_by_key[(kind, key)] = node
                    nodes.append(node)
                target = node_by_key.get((kind, key))
                if not target:
                    raise ValueError(f'Unresolved research target {vehicle["id"]}: {kind}/{key}')
                edges.append({'from': source, 'to': target['id'], 'xp': xp})
            trees[vehicle['id']] = {'price': prices[vehicle['id']], 'nodes': nodes, 'edges': edges, 'source': vehicle['source']}

    for relative, recorded in sources.items():
        if hashlib.sha256((research / relative).read_bytes()).hexdigest() != recorded['sha256']:
            raise ValueError(f'Source changed: {relative}')
    if (WEB / 'data/catalog.v1.json').read_bytes() != facts_bytes:
        raise ValueError('Historical catalog changed')
    result = {'schemaVersion': 'catalog-research.v1', 'build': facts['build'], 'factsSha256': hashlib.sha256(facts_bytes).hexdigest(), 'vehicles': trees}
    output = WEB / 'data/catalog-research.v1.json'
    output.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    summary = {'status': 'PASS', 'vehicles': len(trees), 'nodes': sum(len(t['nodes']) for t in trees.values()),
               'edges': sum(len(t['edges']) for t in trees.values()), 'sourceCount': len(sources), 'sources': sources,
               'specialReferences': special_refs, 'warnings': warnings, 'outputSha256': hashlib.sha256(output.read_bytes()).hexdigest(),
               'factsSha256': result['factsSha256']}
    (evidence / 'sources.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in summary.items() if key not in ['sources', 'warnings', 'specialReferences']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
