# P06C — controlled MS-1 AP impact capture plan

Status: **PASS_PLAN_ONLY / P06_NATIVE_HIT_NOT_RUN**.

Card: `P06C_CONTROLLED_IMPACT_CAPTURE`
Base: `ebf0957` (`Merge P06B status`)
Target: original WoT `v.0.9.1 #717` RU, two isolated MS-1 peers, local test stand only.

This card prepares the exact evidence gate for the first authoritative impact
capture. It does not start the original client, alter the deployed service,
implement a penetration formula, or claim a hit. The static source closure in
[P06B](../research/P06B_MS1_AP_SOURCE_SPIKE.md) supplies identities and mesh
labels; this plan specifies the runtime record needed to correlate them.

## Purpose and stopping rule

The next experiment must separate three things that have so far been observed
only together: native tracer presentation, server trajectory, and gameplay
impact. A visible tracer, a client-side crosshair result, a changed screenshot,
or a client HP callback is insufficient. The capture is accepted only when the
server can account for the complete ordered chain:

```text
admitted shot → server launch → bounded segment → surface candidate
→ material/normal/thickness → terminal reason → one damage token (if any)
```

If any link is absent, malformed, client-authored, or ambiguous, the run is
recorded as `NOT_RUN_INCOMPLETE_CAPTURE` and the gameplay solver remains
unavailable. Do not fill missing values with the literal `34 27`, `30`, `50`,
or a modern wiki formula.

## Fixed fixture

- Ruleset: #717 RU, one explicit revision string/hash in every row.
- Shooter and target: two authenticated local MS-1 entities with different
  inventory/entity IDs; target held at one fixed pose for the first pair.
- Selected components: `T-18_Standart`, `_37mm_Gochkins`, shell compact `2570`
  (`_37mm_UBRT1`, AP), as pinned in P06B.
- Target groups: one known `armor_1` group and one known `armor_8` group from
  the active Hull/Turret_01 descriptors. The fixture must state how the aim ray
  was aligned to each group; a screenshot alone is not alignment proof.
- Environment: one pinned map/config/geometry revision, server launch pose,
  server monotonic start tick, and no moving target for this first capture.
- Replays: submit the same shot identity once more after the first terminal
  result, then submit a conflicting payload under that identity as a negative
  control.

The target must not be selected by client display name or screen coordinate.
The capture records server entity IDs and the source/profile revision used for
both entities.

## Required server-owned receipt

The ignored receipt should be JSONL or an equivalent bounded JSON document. It
must contain a manifest row and one ordered row for each stage. Every numeric
field is finite, bounded, and expressed in the pinned unit system; every row
carries `ruleset_revision`, `battle_id`, `shot_id`, `server_tick` and a strictly
increasing `sequence`.

| Stage | Required fields | Forbidden authority |
|---|---|---|
| `admission` | shooter/target entity IDs, vehicle/gun/shell IDs, ammo before/after, reload state, accepted/rejected reason | client ammo/HP/timer |
| `launch` | server origin/direction, server tick/time, velocity, gravity, range/lifetime bounds, pose revision | client origin/direction/clock |
| `segment` | start/end, tick interval, sequence, finite velocity/position, map/geometry revision | client projectile position |
| `intersection` | candidate order, triangle ID, mesh/group, material label, outward normal, parametric `t`, local/world transform revision | client crosshair/hit marker |
| `classification` | effective thickness input, screen/hull/interior order, angle/normal relation, terminal/continuation decision | guessed armor fallback |
| `damage` | one damage token, target HP/module/crew before/after, penetration/damage rule revision, result reason | client HP or callback alone |
| `replay` | same-identity result, conflict result, side-effect counters, ledger retention decision | client de-duplication |

Raw native frames and screenshots may be attached as supporting evidence, but
only the server receipt can close the gate. Hidden target data must not be sent
to the non-entitled peer merely to make the capture easier.

## Acceptance matrix

| Invariant | Required result | If absent |
|---|---|---|
| AP admission | exactly one accepted `2570` or explicit rejection with ammo unchanged | `NOT_RUN_INCOMPLETE_CAPTURE` |
| deterministic launch | finite server-owned pose and fixed ruleset revision | `NOT_RUN_INCOMPLETE_CAPTURE` |
| ordered intersection | one first candidate plus any ordered continuation; duplicate triangle collapsed | `NOT_RUN_INCOMPLETE_CAPTURE` |
| material correlation | group/material maps to the pinned active descriptor | `NOT_RUN_INCOMPLETE_CAPTURE` |
| normal/thickness | values are server computed and unit-pinned | `NOT_RUN_INCOMPLETE_CAPTURE` |
| terminal state | exactly one immutable terminal reason | `NOT_RUN_INCOMPLETE_CAPTURE` |
| damage application | zero or one token, with before/after target state | keep hit/damage `NOT_RUN` |
| replay idempotency | same identity has no second ammo/projectile/damage side effect; conflict rejected | keep solver unavailable |
| native correlation | client tracer/event references the same server `shot_id` | presentation-only |

A clean miss or non-penetration is useful evidence. It is accepted as a
terminal result only if the server still records the intersection and reason;
`MISS` inferred from a disappearing tracer is not accepted.

## Negative controls and bounds

The capture must include at least these controls in the same receipt:

1. duplicate transport delivery with the original payload;
2. same identity with a different shell or target;
3. stale identity from a previous battle;
4. an out-of-bounds or non-finite segment field rejected before geometry;
5. a target group label that is not present in the active profile.

Parsers and verifiers must cap file size, row count, nesting depth, segment
count, coordinate magnitude and retained ledger entries. They must reject
NaN/Infinity, duplicate terminal rows, sequence rollback, cross-battle IDs,
unknown profile revisions, and client-authored authority fields. No unsafe
object deserialization is permitted.

## Owner/manual gate

The first controlled capture requires a real local run with the isolated native
clients and a fixed target pose. It cannot be proven by unit tests, the P03H
tracer receipt, a synthetic worker, or a screenshot. When the owner is awake,
the run should be executed from a disposable copy and stopped immediately if
the receipt lacks the server intersection fields above. Preserve the original
and research clients and the deployed gateway hashes before and after the run.

## Acceptance, rollback, and next step

**Acceptance for this card:** `PASS_PLAN_ONLY`; no runtime or native impact is
accepted. Checks are documentation readability, required-term inspection and
`git diff --check`.

**Rollback:** revert this one docs-only commit. No client, ignored evidence,
service state, database or deployed artifact is changed.

**Single next step:** implement a bounded receipt verifier for this exact
schema, run it against a deliberately incomplete receipt to prove fail-closed
behaviour, then wait for the owner-gated two-MS-1 native capture. Do not add
penetration, damage or HP mutation code before the verifier can distinguish
missing evidence from a real server-owned impact.
