"""Build a reproducible allowlisted public demo without identity/game data."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[2]


def build(destination):
    destination = destination.resolve()
    destination.relative_to((ROOT / 'local/web').resolve())
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / 'steel-front-demo.tar.gz'
    if archive.exists():
        raise SystemExit('Archive already exists; use a new output directory.')
    files = [ROOT / 'web/package.json', ROOT / 'web/package-lock.json']
    files += [ROOT / 'web/src' / name for name in ('demo-app.mjs', 'demo-server.mjs', 'catalog.mjs', 'research.mjs')]
    files += [ROOT / 'web/views' / name for name in ('home.ejs', 'error.ejs', 'vehicles.ejs', 'vehicle.ejs', 'maps.ejs', 'map.ejs')]
    for directory, suffixes in (
        ('web/views/partials', {'.ejs'}),
        ('web/public', {'.css', '.svg', '.png', '.woff', '.woff2'}),
        ('web/data', {'.json'}),
        ('local/web/catalog-assets', {'.png'}),
    ):
        files += [path for path in (ROOT / directory).rglob('*') if path.is_file() and path.suffix in suffixes]
    records = []
    for path in sorted(set(files)):
        if path.is_symlink() or not path.is_file():
            raise SystemExit(f'Not a regular allowed file: {path.name}')
        path.resolve().relative_to(ROOT.resolve())
        relative = path.relative_to(ROOT).as_posix()
        if any(part in {'runtime', 'server', 'node_modules', '.git'} for part in path.relative_to(ROOT).parts):
            raise SystemExit('Forbidden runtime data path')
        data = path.read_bytes()
        records.append({'path': relative, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    with tarfile.open(archive, 'w:gz', compresslevel=3) as bundle:
        for record in records:
            path = ROOT / record['path']
            metadata = bundle.gettarinfo(str(path), arcname=record['path'])
            metadata.uid = metadata.gid = 0
            metadata.uname = metadata.gname = ''
            metadata.mode = 0o644
            with path.open('rb') as source:
                bundle.addfile(metadata, source)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    manifest = {'schemaVersion': 'catalog-demo-release.v1', 'archive': archive.name,
                'sha256': digest, 'bytes': archive.stat().st_size, 'files': records,
                'accountsIncluded': False, 'gameRuntimeIncluded': False}
    (destination / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'archive': str(archive), 'sha256': digest, 'bytes': manifest['bytes'], 'files': len(records)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args().output)
