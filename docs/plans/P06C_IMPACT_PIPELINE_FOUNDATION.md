# P06C — server-owned impact capture foundation

Status: **PASS_CAPTURE_FOUNDATION / NATIVE_IMPACT_NOT_RUN**.

This card adds the bounded server-side trace boundary needed before a real
P06C two-MS-1 capture. It records only facts the current server already owns:
admission, launch geometry, bounded flight segments and range expiry. It does
not classify a surface, infer armor thickness, apply penetration, mutate HP or
send a damage callback. Those stages remain unavailable until the pinned
collision payloads and a native controlled capture establish their runtime
meaning.

## Scope

- keep the accepted P03J runtime and deployed service unchanged;
- attach a bounded, typed trace to the shared laboratory world;
- record server tick, shot identity, ammunition transition and projectile
  launch/segment/terminal facts with finite values;
- keep intersection/classification/damage/replay deliberately absent; no
  synthetic rows are emitted, so a future receipt cannot be presented as a hit;
- cover clock regression, event bounds, duplicate terminal rows and the
  unavailable terminal policy with Rust tests.

## Acceptance

The foundation is accepted only as `PASS_CAPTURE_FOUNDATION` with
`native_impact_status=NOT_RUN`. A real P06C receipt still requires the owner
gate in [P06C](P06C_CONTROLLED_IMPACT_CAPTURE.md), including a fixed target,
intersection/material/normal/thickness, terminal classification, HP/module
state and replay controls.

## Rollback

Revert this branch commit. Do not replace the deployed gateway or alter either
client copy. The existing `main` service remains the P03J build throughout.

## Single next step

Use the trace with a separate, owner-gated two-MS-1 capture after the runtime
collision boundary is implemented from measured #717 evidence. Keep
penetration and damage disabled until that receipt is complete.
