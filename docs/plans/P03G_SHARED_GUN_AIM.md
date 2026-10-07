# P03G — authoritative shared turret/gun aiming

Status: NATIVE_PATH_PASS_OWNER_PENDING; continuous-aim owner acceptance NOT_RUN.
Base: `8709b07151cdf4c8238ae918044e1b34855bfb6d` (accepted P03F).
Branch: `codex/p03g-shared-gun-aim`.

## Goal and boundaries

Both real #717 clients see the other MS-1's turret and gun follow its aiming
intent. The server owns current angles, speed/limits and publication; native
input supplies only an untrusted target/intent, never authoritative pose/time.
Keep local prediction and original network commands/filters. No projectile,
hit/damage, enemy visibility, terrain physics or inventory changes.

Allowed: shared gateway modules, bounded codecs, minimal documented compatibility
initialization/passive diagnostics, relevant tests/tools/docs; ignored local
evidence/builds and existing manifested `local/clients/p03f/a` and `b` copies.
Read-only original #717 and prior research copy; deployed gateway untouched.
Evidence root: `local/evidence/20261007-p03g-shared-gun-aim-01/`.

## Execution

1. Pin original method/field layouts, aiming startup, native input semantics,
   gun-angle serializer, geometry/pivots and MS-1 rates/limits. Preserve actual
   native samples and distinguish VERIFIED/OBSERVED/INFERRED/UNKNOWN.
2. Decode whole native envelopes into bounded domain intents with ownership and
   readiness checks. Add server time driven yaw/pitch and finite rate/limit
   rules. Explicitly label any test_lab approximation not proven historical.
3. Publish current native angles only after entity creation; provide current
   state on rejoin. Preserve reliable shot ordering, ammo/reload and atomicity.
   Do not accumulate stale angle updates for slow peers.
4. Test malformed/late/nonfinite/wrong-owner inputs, wraparound, finite limits,
   time/rate bounds, recipient creation gating and rejoin state. Run canonical
   and legacy builds, layout, applicable Python checks and pinned 2.7 compilation.
5. Launch both real clients, inspect original input/property/filter reception,
   then leave one owner check: turn/elevate in each window and observe the other,
   including repeated shots. Keep the branch unmerged until mandatory evidence.

Rollback: stop only receipt-matched stand processes; restore exact client
overlay manifests and accepted P03F build08. Preserve copies and all evidence.
Source rollback is a reviewed revert; no reset/force-push. Full P03 two-PC repeat
remains open independently of this same-PC aiming card.
