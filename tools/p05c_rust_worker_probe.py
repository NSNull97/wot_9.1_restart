"""Execute the Rust IPC7 client against the actual pinned Jolt producer."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset-root', type=Path, required=True)
    parser.add_argument('--checker', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--physics-evidence', type=Path, required=True)
    parser.add_argument('--catalog-evidence', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists() or not out.is_relative_to(args.asset_root.resolve()):
        raise ValueError('fresh owned evidence directory required')
    out.mkdir(parents=True)
    results = []
    try:
        cases = [(args.physics_evidence, case, False) for case in ['mixed-headon', 'six-independent', 'ms1-turn-release', 'is7-turn-release']]
        if args.catalog_evidence:
            cases.extend((args.catalog_evidence, case, True) for case in ['full-scene-mixed-two', 'full-scene-mixed-six'])
        for directory, case, physical_acks in cases:
            scene = directory / (case + '-scene.json')
            command = [str(args.checker.resolve()), str(args.asset_root.resolve()), str(scene.resolve()),
                       hashlib.sha256(scene.read_bytes()).hexdigest(), str(args.artifacts.resolve())]
            if physical_acks:
                command.append('--physical-acks')
            with (out / (case + '.stdout.log')).open('xb') as stdout, (out / (case + '.stderr.log')).open('xb') as stderr:
                result = subprocess.run(command, stdout=stdout, stderr=stderr, stdin=subprocess.DEVNULL, timeout=90)
            text = (out / (case + '.stdout.log')).read_text()
            passed = result.returncode == 0 and 'P05C_PASS batches=120' in text and 'P05C_SHUTDOWN EOF_exit0_reaped=true' in text
            results.append(dict(case=case, status='PASS' if passed else 'FAIL', argv=command, exit_code=result.returncode, output=text))
            if not passed:
                raise AssertionError(case + ' failed actual Rust/Jolt IPC; inspect logs')
        status = 'PASS_REAL_RUST_JOLT_IPC'
    except Exception:
        status = 'FAIL'
        raise
    finally:
        (out / 'result.json').write_text(json.dumps(dict(status=status, tests=results, native='NOT_RUN',
            checker_sha256=hashlib.sha256(args.checker.read_bytes()).hexdigest(), artifacts_sha256=hashlib.sha256(args.artifacts.read_bytes()).hexdigest()), indent=2) + '\n')
        print(json.dumps(dict(status=status, cases=len(results), evidence=str(out))))


if __name__ == '__main__':
    main()
