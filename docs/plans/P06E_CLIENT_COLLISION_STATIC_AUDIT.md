# P06E bounded client-collision static recheck

## Goal

Make the existing P06E source observation reproducible without executing the
#717 client. The verifier binds the accepted bytecode receipt and its summary,
checks bounded JSON input, and measures the complete eight-method collision
call chain. The added eighth shape is `collideDynamicAndStatic`, the wrapper
that joins the dynamic and static segment paths.

## Scope

- Read only `local/evidence/20261007-p03h-native-projectile-flight-01/bytecode.json`
  and `local/evidence/20261008-p06e-client-collision-research-01/summary.json`.
- Require their pinned SHA-256 values and the seven original summary method
  pins.
- Hash exactly eight source entries, including the dynamic/static wrapper.
- Reject duplicate keys, non-finite values, excessive depth/items, path escapes,
  symlinks and mutated receipts.

No client bytecode is imported or executed. No gateway, server, physics worker,
database, deployed service or research/original client is started or changed.

## Checks

```text
python -B -X utf8 -m unittest tests.test_p06e_client_collision_static_audit
python -B -X utf8 tools/p06e_client_collision_static_audit.py \
  --bytecode local/evidence/20261007-p03h-native-projectile-flight-01/bytecode.json \
  --summary local/evidence/20261008-p06e-client-collision-research-01/summary.json \
  --out local/evidence/20261008-p06e-static-audit-01/receipt.json
```

## Acceptance boundary

`PASS_STATIC_CLIENT_COLLISION_BOUNDARY_RECHECK` confirms only source hashes and
method shapes. It does not establish BSP2 traversal, transforms, penetration,
damage, module/crew effects, native server callbacks or client/server solver
equivalence. Those remain `UNKNOWN/NOT_RUN` pending one owner-gated server-owned
impact capture through the P06D receipt gate.
