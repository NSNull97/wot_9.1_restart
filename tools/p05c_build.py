"""Build P05C component checks in a worktree, using explicit existing dependencies.

No client/resource tree is copied or linked. This is not gateway/native acceptance.
"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('component', choices=('physics', 'rust'))
    parser.add_argument('--asset-root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    asset = args.asset_root.resolve(strict=True)
    out = (ROOT / args.out).resolve()
    if not out.is_relative_to(ROOT / 'local' / 'build') or out.exists():
        raise ValueError('fresh output under this worktree local/build required')
    for path in (asset, *asset.parents, out, *out.parents):
        if path.is_symlink() or path.is_junction():
            raise ValueError('linked asset/build root refused')
    out.mkdir(parents=True)
    env = dict(os.environ)
    commands = []

    def run(name, argv):
        start = datetime.now(timezone.utc).isoformat()
        with (out / (name + '.stdout.log')).open('xb') as stdout, (out / (name + '.stderr.log')).open('xb') as stderr:
            result = subprocess.run(argv, cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr)
        commands.append({'name': name, 'argv': list(map(str, argv)), 'exit_code': result.returncode, 'started': start})
        if result.returncode:
            raise RuntimeError(name + ' failed; inspect retained logs')

    report = {'component': args.component, 'asset_root': str(asset), 'scope': 'P05C component only; gateway/native NOT_RUN'}
    try:
        if args.component == 'physics':
            dotnet = shutil.which('dotnet')
            if not dotnet or not (asset / 'nuget-packages').is_dir():
                raise ValueError('existing dotnet/NuGet dependencies absent')
            env.update(NUGET_PACKAGES=str(asset / 'nuget-packages'), DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1')
            nuget = out / 'nuget.config'
            nuget.write_text('<configuration><packageSources><clear /></packageSources></configuration>\n')
            intermediate = '-p:BaseIntermediateOutputPath=' + (out / 'obj').as_posix() + '/'
            output = '-p:OutputPath=' + (out / 'bin').as_posix() + '/'
            run('restore', [dotnet, 'restore', 'server/physics/PhysicsWorker.csproj', '--locked-mode', '--configfile', str(nuget), intermediate])
            run('build', [dotnet, 'build', 'server/physics/PhysicsWorker.csproj', '-c', 'Release', '--no-restore', intermediate, output])
            artifact = out / 'bin/MapDriveWorker.dll'
            runtime_files = [p for p in sorted((out / 'bin').rglob('*')) if p.is_file()]
            (out / 'artifacts.json').write_text(json.dumps(dict(version=1, executable='bin/MapDriveWorker.exe',
                files=[dict(path=p.relative_to(out).as_posix(), bytes=p.stat().st_size,
                            sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in runtime_files]), indent=2) + '\n')
        else:
            toolchains = asset / 'toolchains'
            rust = toolchains / 'rustup/toolchains/1.90.0-x86_64-pc-windows-gnu'
            native = rust / 'lib/rustlib/x86_64-pc-windows-gnu'
            env.update(CARGO_HOME=str(toolchains / 'cargo'), RUSTUP_HOME=str(toolchains / 'rustup'), CARGO_TARGET_DIR=str(out / 'target'),
                       CARGO_TARGET_X86_64_PC_WINDOWS_GNU_LINKER=str(native / 'bin/self-contained/x86_64-w64-mingw32-gcc.exe'),
                       RUSTFLAGS='-L native=' + str(native / 'lib/self-contained'))
            env['PATH'] = os.pathsep.join([str(toolchains / 'llvm-mingw-20250910-ucrt-x86_64/bin'), str(native / 'bin/self-contained'), str(rust / 'bin'), env.get('PATH', '')])
            cargo = str(rust / 'bin/cargo.exe')
            manifest = 'tools/p05c_scene_checks/Cargo.toml'
            run('test', [cargo, 'test', '--offline', '--manifest-path', manifest, '--', '--test-threads=1'])
            counts = re.findall(r'test result: ok\. (\d+) passed; 0 failed', (out / 'test.stdout.log').read_text())
            if not counts or sum(map(int, counts)) == 0:
                raise ValueError('nonempty passing Rust test gate required')
            report['tests_passed'] = sum(map(int, counts))
            run('build', [cargo, 'build', '--offline', '--manifest-path', manifest])
            artifact = out / 'target/debug/p05c-scene-checks.exe'
        report.update(status='PASS', artifact=str(artifact), artifact_sha256=hashlib.sha256(artifact.read_bytes()).hexdigest())
    except Exception as error:
        report.update(status='FAIL', error=type(error).__name__, message=str(error))
        raise
    finally:
        report['commands'] = commands
        sources = list((ROOT / 'server/physics').glob('*.cs')) + [ROOT / 'server/physics/PhysicsWorker.csproj', ROOT / 'server/physics/packages.lock.json']
        if args.component == 'rust':
            sources += [ROOT / 'server/gateway/src/drive/scene_worker.rs', ROOT / 'server/gateway/src/shared/scene_runtime.rs']
            sources += list((ROOT / 'server/gateway/src/drive/scene_worker').glob('*.rs'))
            sources += [p for p in (ROOT / 'tools/p05c_scene_checks').rglob('*') if p.is_file()]
        report['source_sha256'] = {str(p.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(sources)}
        (out / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report))


if __name__ == '__main__':
    main()
