# P03I runtime review boundary

Status: **PASS_STATIC_RUNTIME_REVIEW / NATIVE_PROFILE_HANDOFF_NOT_RUN**.

This report is a read-only review of the mixed runtime/client work in commits
`4b66ce3` and `cae2c3b` on `codex/p03i-vehicle-profile-loadout`, compared with
the current `main` (`6ed8424`, including the P03I docs-only merges). The review
does not import those commits, change runtime code, change fixtures, launch a
client, or alter `STATUS.md`/`ACTIVE_GATE.md`.

The reviewed branch is not based on the current main: `ba0d5ce` is not an
ancestor of `cae2c3b`. A whole-branch merge would also carry unrelated stale
deletions of later P04/P05/P06/P09 documents, tools and tests. The runtime
findings below are therefore a review boundary, not a merge recommendation.

## What the two runtime commits contain

`4b66ce3` adds a typed `VehicleProfile` boundary and a read-only native
catalogue observer. The profile carries account and vehicle identity, native
type/turret/gun descriptors, health, shell rows, selected shell, reload,
crew readiness and explicit equipment availability. It validates bounded IDs,
module IDs, shell counts, finite ballistic values, selected ammunition and
crew readiness before battle admission. The MS-1 constructor is backed by the
hash-pinned r4 fixture projection. The IS-7 constructor preserves the observed
mounted catalogue (type `7169`, turret `12035`, gun `14852`, health `2150`,
capacity `30`, reload `13.7 s`, shell descriptors `14602/14858/15114`) but has
zero ammunition and `0/5` crew, so it fails closed.

The same commit threads the selected shell's speed, gravity and range through
the bounded projectile tracer, and threads profile descriptor/health/shell
rows/reload through the shared wire encoders. `sr_interactive.py` reads local
#717 resources and records descriptor, module, shell and pure aiming samples;
it explicitly does not assign a vehicle, crew or ammunition and does not call
the queue.

`cae2c3b` makes the profile part of an actor and preserves it across detach and
rejoin. Authenticated primary admission uses the exact hash-pinned r4 MS-1
fixture. The second laboratory client uses the explicit, versioned
`legacy091-shared-lab-ms1.v1` grant, bound to one account/name/database,
absolute fixture directory and five exact file hashes. The grant constructs a
temporary MS-1 identity and does not write the empty r1 fixture. Admission,
rejoin and profile source are logged; ammo and reload polling use the actor's
profile. A synthetic ready IS-7 unit test checks domain propagation only.

## Evidence classification

| Finding | Status | Limit |
|---|---|---|
| MS-1 and IS-7 descriptors/modules/shell catalogue are equal in two native clients | `PASS_STATIC_NATIVE_CATALOG` | Mounted catalogue only; ownership, loadout and queue are not established |
| Primary r4 MS-1 profile binds account, modules, crew `2/2` and AP `2570 × 20` | `PASS_AUTHENTICATED_PROFILE_BINDING` | One authenticated fixture and one selected MS-1; no selected-vehicle handoff |
| Secondary two-client lab session uses a distinct temporary MS-1 profile | `OBSERVED_SHARED_LAB_GRANT` | Test-lab policy only; it is not garage ownership or general profile selection |
| Canonical/legacy gateway unit suites and source layout pass | `PASS_ISOLATED_BUILD` | Build/unit/layout evidence does not establish native wire or battle compatibility |
| Profile-driven projectile/wire code compiles and passes synthetic tests | `PASS_DOMAIN_ONLY` | No native IS-7 battle, impact or callback evidence |
| Native garage selection can show an IS-7 model in the hangar | `OBSERVED_NATIVE_GARAGE_SELECTION` | Existing receipt records `battle_handoff=NOT_RUN`; the manual gesture is `UNKNOWN` |
| Native selection-to-battle, live CMD700 body and callbacks | `NOT_RUN` | Owner-gated capture is required |

The static catalogue observation is recorded in
`local/evidence/20261007-p03i-vehicle-profile-loadout-01/native-profile-04/native-catalog-01.json`.
It reports `crew_assignment_verified=false` and
`inventory_loadout_verified=false`. The authenticated profile/binding receipt
is `native-profile-05/profile-binding-06.json`; the independent transport
prefix audit is `native-profile-05/capture-audit-profile06.json`.

## Runtime blockers and risks

1. **Native admission gate is open.** No ordinary random-battle click has been
   captured through the real client. Static research fixes request `202`,
   command `700`, an `INT64` selected vehicle and two `INT32` values, but the
   live body, mask/arena values, callback framing/order and server correlation
   are still `NOT_RUN`. The reviewed code does not decode or admit CMD700.

2. **The production path is still MS-1-only.** `prepare_shared_ms1` admits
   the authenticated primary MS-1 or the hard-coded secondary MS-1 grant. The
   IS-7 profile is descriptive and intentionally fails with no shell/crew;
   there is no server-owned IS-7 crew or ammunition grant, reservation,
   consumption transaction or selection resolver.

3. **Profile parameterization is incomplete.** The profile drives shell
   trajectory values and several HUD/vehicle fields, but the wire binding
   still emits fixed MS-1 aiming/rate constants. `VehicleProfile` does not
   carry the native gun aiming/rotation/pitch fields needed to claim IS-7
   visual or aiming parity. The wire module's own boundary comment still says
   its encoders are for two MS-1 actors.

4. **The temporary grant is embedded in runtime admission.** Account name,
   database, absolute fixture shape and hashes are deliberate lab controls,
   not a general garage service. Merging this path as a product profile loader
   would silently turn a test grant into policy.

5. **Legacy and bounded-storage semantics need a fresh review before any
   cherry-pick.** `MAX_SHOTS` grows to `CAPACITY × 30` while legacy tests still
   expect `CAPACITY × MS1_INITIAL_AMMO` (`40`). The MS-1 compatibility wrapper
   for shot callbacks now rejects `ammo_remaining >= 20` whereas its old bound
   was `>= 96`; normal post-shot `19` is covered, but the old wrapper is no
   longer a byte-for-byte domain boundary for all previously accepted inputs.

6. **The client patch is diagnostic only.** The observer hashes and reads
   bounded local resources, then records pure catalogue/aim samples. It does
   not prove garage ownership, crew assignment, equipment or battle admission.
   Its compiled overlay and native run must remain receipt-matched and
   reversible; it must not be used as a substitute for the owner capture.

7. **The branch cannot be merged wholesale.** Besides the runtime files, its
   history is based on an older main and would remove later tracked research
   and bounded tools. Any future runtime experiment needs a new branch from
   current main, a reviewed selective port, and a new canonical/legacy build.

## Safe follow-up and stopping rule

The safe material to carry forward is documentation of the static catalogue,
the explicit fail-closed IS-7 boundary, and the profile06 receipts. The
runtime commits remain unmerged. The single next gate is an owner-gated
native MS-1 random-battle click that preserves the decrypted Account body,
request/envelope fields, selected inventory ID, callback and server identity
correlation. Only after that capture and a separate hash-pinned IS-7 crew and
shell grant should an IS-7 runtime profile be reconsidered.

No hit, damage, armour, equipment modifiers, LAN behavior or native physics is
closed by this review. Rollback is deleting the two docs in this card or
reverting its single commit; no runtime/deployed/original-client rollback is
needed.
