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
import stat
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(out, name, value):
    with (out / name).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def test_counts(text):
    """A successful empty Cargo filter is not evidence of a passing gate."""
    counts = re.findall(r'test result: ok\. (\d+) passed; 0 failed', text)
    if not counts or sum(map(int, counts)) == 0 or 'test result: FAILED.' in text:
        raise ValueError('Nonempty passing Rust suite result absent')
    ignored = re.findall(r'test result: ok\. \d+ passed; 0 failed; (\d+) ignored', text)
    return sum(map(int, counts)), sum(map(int, ignored))


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


# This opt-in relocates compiler intermediates only; final artifacts stay local/build.
MAX_TEMP_EXECUTABLE_BYTES = 256 * 1024 * 1024


def no_reparse(path):
    """Check lexical ancestors before resolving Windows junctions or symlinks."""
    path = Path(path).absolute()
    for current in (path, *path.parents):
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Linked or reparse build path refused: ' + str(current))
    return path


def checked_output(root, raw):
    # Preserve the old fresh local/build boundary, including lexical link checks.
    out = (root / raw).resolve()
    if not out.is_relative_to(root / 'local/build') or out == root / 'local/build' or out.exists():
        raise ValueError('Fresh output strictly below project local/build/ required')
    for path in (root / raw, *(root / raw).parents):
        if path == root:
            break
        if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
            raise ValueError('Linked build output refused')
    return out


def check_temp_selector(component, legacy, selected):
    if selected and (component != 'gateway' or legacy):
        raise ValueError('--cargo-temp-target requires canonical gateway without --legacy')


def allocate_temp_target(out):
    parent = Path(tempfile.gettempdir()).absolute()
    if not re.fullmatch(r'[A-Za-z]:', parent.drive):
        raise ValueError('Default OS temporary root must be a local Windows drive directory')
    parent = no_reparse(parent).resolve(strict=True)
    if not parent.is_dir():
        raise ValueError('Default OS temporary root must be a directory')
    if parent.drive.lower() == out.drive.lower():
        raise ValueError('--cargo-temp-target requires default OS temp on another drive')
    target = Path(tempfile.mkdtemp(prefix='wot091-cargo-', dir=parent))
    metadata = {'schema': 'wot091-cargo-temp-target.v1',
                'default_os_temp': str(parent), 'target': str(target),
                'created_utc': datetime.now(timezone.utc).isoformat(),
                'retained_for_audit': True, 'automatic_delete': False,
                'source': 'tempfile.gettempdir(); fresh mkdtemp; no caller path'}
    # Save into both owned directories immediately. Failure retains all bytes.
    try:
        save(target, 'wot091-build-origin.json', {'output': str(out), **metadata})
        save(out, 'cargo-temp-target.json', metadata)
        no_reparse(target)
        if target.parent != parent or not target.is_dir() or not target.name.startswith('wot091-cargo-'):
            raise ValueError('Fresh OS target directory identity changed')
    except Exception as error:
        raise RuntimeError('Temporary target retained after setup failure: ' + str(target)) from error
    return target, metadata


def temp_environment(env):
    # Deliberately omit PATH and the ambient environment: they can contain secrets.
    keys = ('CARGO_HOME', 'RUSTUP_HOME', 'CARGO_TARGET_DIR',
            'CARGO_TARGET_X86_64_PC_WINDOWS_GNU_LINKER', 'RUSTFLAGS',
            'CARGO_INCREMENTAL', 'RUST_TEST_THREADS',
            'CARGO_PROFILE_DEV_DEBUG', 'CARGO_PROFILE_TEST_DEBUG')
    return {key: env[key] for key in keys if key in env}


def copy_verified_executable(source, destination, target_root):
    source, destination, target_root = map(Path, (source, destination, target_root))
    if source != target_root / 'debug/sr-gateway.exe':
        raise ValueError('Only canonical Cargo debug gateway executable may be exported')
    for path in (target_root, source, destination):
        no_reparse(path)
    info = source.stat()
    if not stat.S_ISREG(info.st_mode) or not 2 <= info.st_size <= MAX_TEMP_EXECUTABLE_BYTES:
        raise ValueError('Temporary executable must be a bounded regular file')
    if destination.exists() or destination.parent.exists():
        raise ValueError('Fresh final target/debug output required')
    before_sha, before_size = sha(source), info.st_size
    with source.open('rb') as stream:
        if stream.read(2) != b'MZ':
            raise ValueError('Temporary Windows executable header missing')
    destination.parent.mkdir(parents=True, exist_ok=False)
    copied = 0
    with source.open('rb') as incoming, destination.open('xb') as outgoing:
        while chunk := incoming.read(64 * 1024):
            copied += len(chunk)
            if copied > MAX_TEMP_EXECUTABLE_BYTES:
                raise ValueError('Temporary executable grew beyond copy limit')
            outgoing.write(chunk)
        outgoing.flush()
        os.fsync(outgoing.fileno())
    for path in (source, destination):
        no_reparse(path)
    after_sha, output_sha = sha(source), sha(destination)
    if (source.stat().st_size != before_size or destination.stat().st_size != before_size
            or copied != before_size or before_sha != after_sha or before_sha != output_sha):
        raise ValueError('Temporary source/output executable hash or size mismatch; files retained')
    return {'schema': 'wot091-cargo-temp-copy.v1', 'source': str(source),
            'destination': str(destination), 'bytes': copied,
            'source_sha256_before': before_sha, 'source_sha256_after': after_sha,
            'output_sha256': output_sha, 'verified_equal': True,
            'temporary_target_retained': True, 'automatic_delete': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('component', choices=('gateway', 'physics'))
    parser.add_argument('--legacy', action='store_true', help='Check old build entrypoint on the same sources')
    parser.add_argument('--test', action='store_true', help='Run gateway Rust tests before build')
    parser.add_argument('--test-filter', help='Run only the named gateway test filter; records targeted scope explicitly')
    parser.add_argument('--run-ignored', action='store_true',
                        help='Run exactly one named ignored gateway test in isolation; requires --test --test-filter')
    parser.add_argument('--cargo-temp-target', action='store_true',
                        help='Canonical gateway only: retain a fresh target in default OS temp on another drive; copy verified exe to --out')
    parser.add_argument('--out', required=True, help='Fresh directory below project local/build/')
    args = parser.parse_args()
    check_temp_selector(args.component, args.legacy, args.cargo_temp_target)
    out = checked_output(ROOT, args.out)
    if args.component == 'physics' and args.test:
        raise ValueError('--test belongs to the gateway; physics build is not a physics test')
    if args.test_filter and not args.test:
        raise ValueError('--test-filter requires --test')
    if args.run_ignored and (args.component != 'gateway' or not args.test or not args.test_filter):
        raise ValueError('--run-ignored requires gateway --test --test-filter')
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
            target = out / 'target'
            if args.cargo_temp_target:
                target, result['cargo_temp_target'] = allocate_temp_target(out)
            env.update(CARGO_HOME=str(toolchains / 'cargo'), RUSTUP_HOME=str(toolchains / 'rustup'),
                       CARGO_TARGET_DIR=str(target),
                       CARGO_TARGET_X86_64_PC_WINDOWS_GNU_LINKER=str(native / 'bin/self-contained/x86_64-w64-mingw32-gcc.exe'),
                       RUSTFLAGS='-L native=' + str(native / 'lib/self-contained'))
            env['PATH'] = os.pathsep.join([str(toolchains / 'llvm-mingw-20250910-ucrt-x86_64/bin'),
                str(native / 'bin/self-contained'), str(rust / 'bin'), str(toolchains / 'cargo/bin'), env.get('PATH', '')])
            manifest = 'tools/wg_probe/Cargo.toml' if args.legacy else 'server/gateway/Cargo.toml'
            save(out, 'toolchain.json', {'cargo': str(cargo), 'cargo_sha256': sha(cargo),
                                         'rustc_sha256': sha(rust / 'bin/rustc.exe')})
            if args.cargo_temp_target:
                save(out, 'cargo-temp-environment.json', temp_environment(env))
            if args.test:
                test_argv = [str(cargo), 'test', '--offline', '--locked', '--manifest-path', manifest]
                if args.test_filter:
                    test_argv.append(args.test_filter)
                if args.run_ignored:
                    test_argv.extend(['--', '--ignored', '--exact', '--test-threads=1'])
                command(out, 'test', test_argv, env)
                text = (out / 'test.stdout.log').read_text(encoding='utf-8')
                result['tests_passed'], result['tests_ignored'] = test_counts(text)
                if args.run_ignored and (result['tests_passed'] != 1 or result['tests_ignored'] != 0):
                    raise ValueError('Isolated ignored gate requires exactly one passing test and no ignored tests')
                result['tests_scope'] = args.test_filter or 'full gateway suite'
                if args.run_ignored:
                    result['tests_execution'] = 'isolated ignored exact test; one test thread'
            command(out, 'build', [str(cargo), 'build', '--offline', '--locked', '--manifest-path', manifest], env)
            executable = out / 'target/debug' / ('p01-wg-probe.exe' if args.legacy else 'sr-gateway.exe')
            if args.cargo_temp_target:
                copied = copy_verified_executable(target / 'debug/sr-gateway.exe', executable, target)
                save(out, 'cargo-temp-copy.json', copied)
                result['cargo_temp_target']['copy_receipt_sha256'] = sha(out / 'cargo-temp-copy.json')
                result['cargo_temp_target']['environment_receipt_sha256'] = sha(out / 'cargo-temp-environment.json')
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
        result['status'] = 'PASS_ISOLATED_BUILD_TARGETED' if args.test_filter else 'PASS_ISOLATED_BUILD'
        save(out, 'result.json', result)
        print(json.dumps(result))
    except Exception as error:
        result.update(status='FAIL_ISOLATED_BUILD', exception=type(error).__name__, reason=str(error))
        save(out, 'failure.json', result)
        raise


if __name__ == '__main__':
    main()
