"""Actual IPC7/catalog8 prepare/ACK gates; physical component, no domain result."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from p05c_shared_scene_probe import Process, control, dump, sha


def scene_hash(catalog_hash, ids):
    raw = b'wot091-fragile-scene-v3\0' + bytes.fromhex(catalog_hash) + struct.pack('<I', len(ids))
    raw += b''.join(struct.pack('<I', value) for value in ids)
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset-root', type=Path, required=True)
    parser.add_argument('--worker', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    root = args.asset_root.resolve(strict=True)
    out = args.out.resolve()
    if out.exists() or not out.is_relative_to(root):
        raise ValueError('fresh explicit owned evidence required')
    out.mkdir(parents=True)
    catalog = root / 'evidence/20261013-p05b-tracked-handling-01/night-angular-export01/catalog/physics-removals.json'
    chash = sha(catalog)
    configs = {kind: root / f'evidence/20261014-p05b-handling-fixes-01/pools-{kind}-c17/05_prohorovka-{kind}-handling-config.json' for kind in ['ms1', 'is7']}
    results = []

    def run(name, count, reject=None):
        rows = []
        for slot in range(count):
            kind = 'ms1' if slot % 2 == 0 else 'is7'
            rows.append(dict(slot=slot, kind=kind, config=dict(path=str(configs[kind]), sha256=sha(configs[kind])),
                             spawn_origin=[-209 + (slot % 2) * 8, 6.046776865530075, 458 - (slot // 2) * 12], spawn_yaw=0))
        path = out / (name + '-scene.json')
        dump(path, dict(version=1, profile='test_lab', policy='p05c-shared-scene-v1', map='05_prohorovka', actors=rows,
                       catalog=dict(path=str(catalog), sha256=chash)))
        hash = sha(path)
        process = Process([args.worker, '--battle-scene', path, '--scene-sha256', hash, '--local-root', root, '--generation', '1'], out / name)
        header = dict(version=7, generation=1, manifest_sha256=hash, catalog_sha256=chash)
        removed = []
        process.send(dict(header, op='restore_scene', advance_seq=0, scene_version=0, removed_object_ids=[], scene_sha256=scene_hash(chash, [])))
        ready = process.receive()
        assert ready['event'] == 'ready' and len(ready['actors']) == count
        prepared, claims_count, repeated_acks = 0, 0, 0
        failed = False
        try:
            for seq in range(1, 151):
                advance = dict(header, op='advance', seq=seq, ticks=6, scene_version=len(removed), scene_sha256=scene_hash(chash, removed),
                               inputs=[dict(slot=i, **control(1)) for i in range(count)])
                process.send(advance)
                frame = process.receive()
                assert frame['seq'] == seq and frame['tick'] == 180 + seq * 6
                claims = frame['fracture_claims']
                receipts = [(row['slot'], r) for row in frame['actors'] for r in row['state']['fractures']]
                assert len(claims) == len(receipts)
                assert len({r['object_id'] for r in claims}) == len(claims)
                assert {(r['slot'], r['object_id'], r['substep']) for r in claims} == {(slot, r['object_id'], r['substep']) for slot, r in receipts}
                if claims:
                    prepared += 1
                    claims_count += len(claims)
                    assert frame['event'] == 'prepared'
                    next_removed = sorted(set(removed) | {r['object_id'] for r in claims})
                    if reject == 'advance-before-ack':
                        advance['seq'] += 1
                        process.send(advance)
                        failed = True
                        break
                    ids = removed if reject == 'omitted-claim' else next_removed
                    sync = dict(header, op='sync_removed', advance_seq=seq, scene_version=len(ids), removed_object_ids=ids, scene_sha256=scene_hash(chash, ids))
                    process.send(sync)
                    if reject:
                        failed = True
                        break
                    ack = process.receive()
                    assert ack['event'] == 'scene_synced' and ack['tick'] == frame['tick'] and ack['advance_seq'] == seq
                    assert ack['removed_object_ids'] == next_removed and ack['scene_sha256'] == scene_hash(chash, next_removed)
                    process.send(sync)
                    assert process.receive() == ack
                    repeated_acks += 1
                    removed = next_removed
                else:
                    assert frame['event'] == 'state'
            assert prepared > 0, 'route did not exercise actual catalog body fracture'
            if reject:
                assert failed, 'negative gate was not exercised'
            results.append(dict(case=name, status='PASS', actors=count, prepared_frames=prepared, global_claims=claims_count,
                                committed_removed_ids=removed, repeated_exact_acks=repeated_acks, rejection=reject))
        finally:
            process.close(expected=1 if failed else 0)

    try:
        run('full-scene-mixed-two', 2)
        run('full-scene-mixed-six', 6)
        run('advance-before-ack', 2, 'advance-before-ack')
        run('omitted-claim', 2, 'omitted-claim')
        status = 'PASS_REAL_CATALOG_PREPARE_ACK'
    except Exception as error:
        status = 'FAIL'
        results.append(dict(case='exception', type=type(error).__name__, message=str(error)))
        raise
    finally:
        dump(out / 'result.json', dict(status=status, tests=results, worker_sha256=sha(args.worker), catalog_sha256=chash,
            scope='actual physical catalog8 component; caller deliberately acknowledges without domain mutation',
            domain_scalar_proof_gate='NOT_RUN', native='NOT_RUN'))
        print(json.dumps(dict(status=status, cases=len(results), evidence=str(out))))


if __name__ == '__main__':
    main()
