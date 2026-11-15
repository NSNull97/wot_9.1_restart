"""Build the pinned VISUAL-03 alpha/mip probe in local evidence only.

Client packages are read-only. The three outputs must be explicitly installed
by the separate installer; the current client and its overrides are not read
or modified by this command.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import subprocess
import time
import zipfile
from pathlib import Path

from tools.destructible_catalog import no_links
from tools.visual02_paths import safe_evidence_output
from tools.visual03_mips import assemble_2x, mip_report

ASSETS = (
    ('vehicles/russian/R11_MS-1/MS-1.dds', 'd418c63aa7891034dbf34a2c26191cc8fc012cc385880811251ca12fda9d94c3', 'BC1_UNORM', ['MS-1', 'Observer']),
    ('vehicles/russian/tracks/MS-1_track.dds', '755f040c3a09ed2298dad38b01c0da8da5a359239689d7f6eae0feda1cef22ac', 'BC2_UNORM', ['MS-1', 'Observer', 'SU-18']),
    ('vehicles/russian/tracks/SU-14_track.dds', '25647b5f88ad718b5568f97006f8c18fcb4d6233b532277788358ee12bc12a0d', 'BC3_UNORM', ['SU-8', 'SU-14', 'SU-14-1', 'T-127']),
)
TOOLS = Path('D:/WoT_9.1_Server/local/upscale-kv1s-tools')
MAX_SOURCE = 16 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_pinned(z, path, expected):
    info = z.getinfo(path)
    if not 0 < info.file_size <= MAX_SOURCE or info.file_size > max(1024, info.compress_size * 2000):
        raise ValueError('archive size/compression bound: ' + path)
    data = z.read(info)
    if len(data) != info.file_size or digest(data) != expected:
        raise ValueError('source SHA/size mismatch: ' + path)
    return data


def write_new(path, data):
    safe = safe_evidence_output(path)
    with safe.open('xb') as f:
        f.write(data)


def run(args, log, cwd):
    started = time.monotonic()
    result = subprocess.run([str(x) for x in args], cwd=cwd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=600, check=False)
    log.append({'argv': [str(x) for x in args], 'seconds': round(time.monotonic() - started, 3),
                'exit_code': result.returncode, 'output': result.stdout.decode('utf-8', 'replace')[-12000:]})
    if result.returncode:
        raise RuntimeError('tool returned non-zero: ' + str(args[0]))


def build(client, out):
    root = no_links(client).resolve(strict=True)
    package = no_links(root / 'res/packages/vehicles_russian.pkg')
    if not package.is_file():
        raise ValueError('pinned vehicle package missing')
    out = safe_evidence_output(out)
    out.mkdir(parents=False, exist_ok=False)
    out = safe_evidence_output(out)
    (out / 'source').mkdir()
    (out / 'work').mkdir()
    (out / 'out').mkdir()
    texconv = no_links(TOOLS / 'texconv.exe').resolve(strict=True)
    network = no_links(TOOLS / 'realesrgan/realesrgan-ncnn-vulkan.exe').resolve(strict=True)
    models = no_links(TOOLS / 'realesrgan/models').resolve(strict=True)
    magick_name = shutil.which('magick')
    if not magick_name:
        raise ValueError('ImageMagick magick not found')
    magick = no_links(magick_name).resolve(strict=True)
    for path in (texconv, network, magick, models / 'realesrgan-x4plus.param', models / 'realesrgan-x4plus.bin'):
        if not path.is_file():
            raise ValueError('required tool/model missing: ' + str(path))
    log, entries = [], []
    try:
        with zipfile.ZipFile(package) as z:
            for resource, expected, fmt, uses in ASSETS:
                data = read_pinned(z, resource, expected)
                before = mip_report(data)
                stem = Path(resource).stem
                source_dir, work = out / 'source', out / 'work' / stem
                work.mkdir()
                src = source_dir / (stem + '.dds')
                write_new(src, data)
                run([texconv, '-ft', 'png', '-m', '1', '-o', work, src], log, out)
                decoded = work / (stem + '.png')
                rgb, ai4, ai2, base2, rgb2 = (work / (stem + suffix) for suffix in
                    ('-rgb.png', '-ai4.png', '-ai2.png', '-base2.png', '-rgb2.png'))
                width, height = before['width'] * 2, before['height'] * 2
                run([magick, decoded, '-alpha', 'off', rgb], log, out)
                run([network, '-i', rgb, '-o', ai4, '-n', 'realesrgan-x4plus', '-s', '4', '-t', '256', '-m', models, '-f', 'png'], log, out)
                run([magick, ai4, '-filter', 'Lanczos', '-resize', f'{width}x{height}!', ai2], log, out)
                run([magick, rgb, '-filter', 'Lanczos', '-resize', f'{width}x{height}!', base2], log, out)
                run([magick, base2, ai2, '-define', 'compose:args=20,80', '-compose', 'blend', '-composite', rgb2], log, out)
                run([texconv, '-m', '1', '-f', fmt, '-o', work, rgb2], log, out)
                rgb_dds = work / (stem + '-rgb2.dds')
                result = assemble_2x(data, rgb_dds.read_bytes())
                after = mip_report(result)
                target = out / 'out' / (stem + '.dds')
                write_new(target, result)
                entries.append({'resource': resource, 'source_sha256': expected,
                                'output': 'out/' + target.name, 'output_sha256': digest(result),
                                'source_mips': before['mip_count'], 'output_mips': after['mip_count'],
                                'source_width': before['width'], 'source_height': before['height'],
                                'format': before['format'], 'source_levels': before['levels'],
                                'output_levels': after['levels'], 'shared_with': uses,
                                'new_top_alpha': 'exact_nearest_2x' if fmt != 'BC1_UNORM' else 'opaque',
                                'old_mips': 'bitwise_identical', 'alpha_semantics': 'UNKNOWN'})
        manifest = {'schema': 'wot091-visual03-batch.v1', 'target': 'v.0.9.1 #717 RU',
                    'source_client': str(root), 'source_package': str(package),
                    'colour_policy': '80% original Lanczos + 20% x4plus AI, no global recolour',
                    'limits': ['runtime loading and filtering NOT_RUN', 'shader alpha semantics UNKNOWN',
                               'shared textures affect all listed vehicles'],
                    'tool_sha256': {'texconv': digest(texconv.read_bytes()), 'realesrgan': digest(network.read_bytes()),
                                    'model': digest((models / 'realesrgan-x4plus.bin').read_bytes()),
                                    'model_param': digest((models / 'realesrgan-x4plus.param').read_bytes()),
                                    'magick': digest(magick.read_bytes())}, 'assets': entries}
        write_new(out / 'build-log.json', (json.dumps(log, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
        write_new(out / 'manifest.json', (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
        return manifest
    except BaseException:
        if not (out / 'build-log.failed.json').exists():
            write_new(out / 'build-log.failed.json', (json.dumps(log, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
        raise


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--client', type=Path, required=True)
    p.add_argument('--out-dir', type=Path, required=True)
    a = p.parse_args()
    manifest = build(a.client, a.out_dir)
    print(json.dumps({'output': str(a.out_dir), 'assets': len(manifest['assets']),
                      'outputs': {x['resource']: x['output_sha256'] for x in manifest['assets']}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
