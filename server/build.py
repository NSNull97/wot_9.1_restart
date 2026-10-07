"""Build canonical or legacy entrypoints into fresh ignored local output only."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(out, name, value):
    with (out / name).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def command(out, label, argv, env):
    started = datetime.now(timezone.utc).isoformat()
    with (out / (label + '.stdout.log')).open('xb') as stdout, \
            (out / (label + '.stderr.log')).open('xb') as stderr:
        process = subprocess.run(argv, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                 stdout=stdout, stderr=stderr)
    save(out, label + '.command.json', {'argv': argv, 'exit_code': process.returncode,
                                      'started_utc': started,
                                      'finished_utc': datetime.now(timezone.utc).isoformat()})
    if process.returncode:
        raise RuntimeError(f'{label} failed; full logs retained')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('component', choices=('gateway', 'physics'))
    parser.add_argument('--legacy', action='store_true', help='Check old build entrypoint on the same sources')
    parser.add_argument('--test', action='store_true', help='Run gateway Rust tests before build')
    parser.add_argument('--out', required=True, help='Fresh directory below project local/build/')
    args = parser.parse_args()
    out = (ROOT / args.out).resolve()
    if not out.is_relative_to(ROOT / 'local/build') or out == ROOT / 'local/build' or out.exists():
        raise ValueError('Fresh output strictly below project local/build/ required')
    for path in (ROOT / args.out, *(ROOT / args.out).parents):
        if path == ROOT:
            break
        if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
            raise ValueError('Linked build output refused')
    if args.component == 'physics' and args.test:
        raise ValueError('--test belongs to the gateway; physics build is not a physics test')
    out.mkdir(parents=True)
    env = dict(os.environ)
    deployed = ROOT / 'local/vendor/wg-toolkit-rs/target/debug/p01-wg-probe.exe'
    deployed_hash = sha(deployed) if deployed.is_file() else None
    result = {'component': args.component, 'legacy': args.legacy,
              'deployed_gateway_before': deployed_hash,
              'deployed_artifacts_replaced': False, 'native_client': 'NOT_RUN',
              'linux': 'NOT_RUN' if os.name == 'nt' else 'Only this host build; native runtime NOT_RUN'}
    try:
        if args.component == 'gateway':
            toolchains = ROOT / 'local/toolchains'
            if os.name != 'nt':
                raise ValueError('This checked build driver uses the pinned Windows toolchain; Linux needs its own validation')
            rust = toolchains / 'rustup/toolchains/1.90.0-x86_64-pc-windows-gnu'
            native = rust / 'lib/rustlib/x86_64-pc-windows-gnu'
            cargo = rust / 'bin/cargo.exe'
            if not cargo.is_file():
                raise ValueError('Pinned Rust 1.90.0 Windows GNU toolchain missing')
            env.update(CARGO_HOME=str(toolchains / 'cargo'), RUSTUP_HOME=str(toolchains / 'rustup'),
                       CARGO_TARGET_DIR=str(out / 'target'),
                       CARGO_TARGET_X86_64_PC_WINDOWS_GNU_LINKER=str(native / 'bin/self-contained/x86_64-w64-mingw32-gcc.exe'),
                       RUSTFLAGS='-L native=' + str(native / 'lib/self-contained'))
            env['PATH'] = os.pathsep.join([str(toolchains / 'llvm-mingw-20250910-ucrt-x86_64/bin'),
                str(native / 'bin/self-contained'), str(rust / 'bin'), str(toolchains / 'cargo/bin'), env.get('PATH', '')])
            manifest = 'tools/wg_probe/Cargo.toml' if args.legacy else 'server/gateway/Cargo.toml'
            save(out, 'toolchain.json', {'cargo': str(cargo), 'cargo_sha256': sha(cargo),
                                         'rustc_sha256': sha(rust / 'bin/rustc.exe')})
            if args.test:
                command(out, 'test', [str(cargo), 'test', '--offline', '--locked', '--manifest-path', manifest], env)
                text = (out / 'test.stdout.log').read_text(encoding='utf-8')
                counts = re.findall(r'test result: ok\. (\d+) passed; 0 failed', text)
                if not counts:
                    raise ValueError('Passing Rust suite result absent')
                result['tests_passed'] = sum(map(int, counts))
            command(out, 'build', [str(cargo), 'build', '--offline', '--locked', '--manifest-path', manifest], env)
            executable = out / 'target/debug' / ('p01-wg-probe.exe' if args.legacy else 'sr-gateway.exe')
            result['built_executable_sha256'] = sha(executable)
        else:
            dotnet = shutil.which('dotnet')
            if not dotnet:
                raise ValueError('Installed .NET SDK missing')
            manifest = 'tools/map_drive_worker/MapDriveWorker.csproj' if args.legacy else 'server/physics/PhysicsWorker.csproj'
            nuget = out / 'nuget-offline.config'
            nuget.write_text('<configuration><packageSources><clear /></packageSources></configuration>\n', encoding='utf-8')
            intermediate = '-p:BaseIntermediateOutputPath=' + (out / 'obj').as_posix() + '/'
            output = '-p:OutputPath=' + (out / 'bin').as_posix() + '/'
            packages = ROOT / 'local/nuget-packages'
            if not packages.is_dir():
                raise ValueError('Previously verified project-local NuGet cache missing')
            env.update(DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1',
                       NUGET_PACKAGES=str(packages))
            command(out, 'sdk', [dotnet, '--list-sdks'], env)
            command(out, 'restore', [dotnet, 'restore', manifest, '--locked-mode', '--configfile', str(nuget), intermediate], env)
            command(out, 'build', [dotnet, 'build', manifest, '-c', 'Release', '--no-restore', intermediate, output], env)
            result['built_DLL_sha256'] = sha(out / 'bin/MapDriveWorker.dll')
            result['physics_simulation'] = 'NOT_RUN; build only'
        if deployed_hash is not None and sha(deployed) != deployed_hash:
            raise ValueError('Deployed gateway unexpectedly changed')
        result['status'] = 'PASS_ISOLATED_BUILD'
        save(out, 'result.json', result)
        print(json.dumps(result))
    except Exception as error:
        result.update(status='FAIL_ISOLATED_BUILD', exception=type(error).__name__, reason=str(error))
        save(out, 'failure.json', result)
        raise


if __name__ == '__main__':
    main()
