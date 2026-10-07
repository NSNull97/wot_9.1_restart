# P06A — BALLISTICS_SPEC / DAMAGE_SPEC boundary (MS-1 AP first)

Status: **PASS_DOCS_ONLY_BOUNDARY / P06_NATIVE_NOT_RUN**.

Card: `P06A_BALLISTICS_CONTRACT`
Branch: `codex/p06a-ballistics-contract`
Base: `cff9c97` (`Merge P05A offline harness status`)
Target build: original WoT `v.0.9.1 #717`, RU.

This card fixes the smallest useful P06 boundary: one server-authoritative
MS-1 configuration with the stock AP shell selected first. It defines the
separation between shot admission, projectile flight, surface intersection and
damage. It does not implement a solver, native callbacks, armor, damage,
modules, crew, or client changes. The companion evidence index is
[`docs/evidence-index/P06A.md`](../evidence-index/P06A.md).

## Why this boundary exists

Roadmap P06 requires the order **admissibility → server direction → projectile
movement → surface intersection → material/normal → outcome → modules/crew/HP →
event**. P03E already accepts native fire, ammunition consumption and reload;
P03H accepts a bounded native tracer/projectile presentation. Neither card
accepts an impact, penetration, armor result or HP change. P06A closes the
contract gap without pretending that the missing physics has been researched.

The native `vehicle_shoot` call (`0x88`) remains an input trigger only. The
server decides whether a shot exists, assigns its identity and owns all later
state. A callback, screenshot, client clock, client position, client HP or
client hit result is never authoritative.

## Pinned scope and evidence

| Item | Status | Pin / meaning |
|---|---|---|
| Target client | **VERIFIED** | `v.0.9.1 #717` RU; [`CLIENT_AUDIT`](../research/CLIENT_AUDIT.md), EXE SHA-256 `86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed` |
| MS-1 vehicle chain | **VERIFIED** | vehicle type `3329`, inventory `1`, turret `5891`, gun `5892`; [`P02_MS1_AMMO`](../research/P02_MS1_AMMO.md) and the pinned native export |
| First shell | **VERIFIED** | AP compact ID `2570` (`_37mm_UBRT1`), native panel rows `2570:20`, `2826:0`, `3082:0`; native export SHA-256 `683daac81143a9d7edfbe671870ba163db088c54f5101fa52e077f596ebbfc74` |
| Fire/reload boundary | **VERIFIED** | P03E accepted five server-owned AP decrements and five completed reload callbacks; see [`P03E_BATTLE_FIRE_RELOAD`](P03E_BATTLE_FIRE_RELOAD.md) |
| Projectile presentation | **VERIFIED for its narrow card** | P03H delivered bounded server-owned tracer/projectile start/stop to two same-PC clients; it explicitly excludes hit and damage; see [`P03H_NATIVE_PROJECTILE_FLIGHT`](../research/P03H_NATIVE_PROJECTILE_FLIGHT.md) |
| Stock AP flight inputs | **VERIFIED static for the P03H lab profile** | P03H records raw speed `442`, projectile factor `0.8`, effective speed `353.6 m/s`, gravity `6.2784 m/s²`, range `720 m`; this is a pinned presentation/flight input, not proof of the historical hit solver |
| AP penetration and damage | **UNKNOWN / NOT_RUN** | No accepted #717 source/trace in the current card proves nominal penetration, damage roll, normalization, spaced-armour handling or module/crew effects for shell `2570` |
| Armor and collision surfaces | **UNKNOWN / NOT_RUN** | Geometry import and P04/P05 diagnostics do not establish the vehicle hit mesh/material/normal contract for this shot |
| Dispersion/RNG | **UNKNOWN / NOT_RUN** | Full pre-9.6 distribution is explicitly unknown in [`04_RULESET_091`](../04_RULESET_091.md) |

The numbers above are intentionally limited to values already pinned by the
project. A missing value blocks the corresponding historical outcome; it is not
filled with a modern wiki value or a plausible default.

## BALLISTICS_SPEC boundary

### 1. Typed stages

The eventual domain implementation must expose these conceptual stages. Names
are a contract vocabulary, not a request to add runtime classes in this card.

1. **Shot admission** — validate authenticated shooter, selected MS-1/gun/shell
   mapping, reload state and available AP. Consume exactly one server-owned AP
   round only when the complete admission transaction can be committed.
2. **Server launch** — obtain the authoritative gun pose and server monotonic
   time. Native aim/shot messages may request a shot; they cannot supply the
   final origin, direction, velocity, clock or RNG outcome.
3. **Trajectory** — advance a finite projectile state in server time. Samples
   carry a monotonic sequence/tick, finite position/velocity and the ruleset
   revision used for the step. The implementation may use continuous or
   bounded segment integration, but a discrete client collision callback is not
   an accepted substitute.
4. **Surface intersection** — test each bounded trajectory segment against
   server-owned terrain/vehicle surfaces. Return zero or more ordered
   candidates; a duplicate triangle/contact must collapse to one physical
   surface event for the same shot and segment.
5. **Hit classification** — resolve the candidate's material, outward normal,
   thickness and relation to screens/hull/interior. If the needed surface data
   is unavailable, return an explicit unavailable/unknown result and stop the
   gameplay chain.
6. **Terminal event** — emit one immutable terminal result (`miss`, `blocked`,
   `hit`, `invalid` or an explicit unavailable status) keyed by the shot
   identity. Damage is a separate stage and cannot be inferred from a tracer
   stop.

### 2. Units and finite-state invariants

The historical ruleset must pin units before a native acceptance run. The
P03H lab values use metres, seconds, metres/second and metres/second². The
contract requires:

- finite, non-NaN position, velocity, gravity and time values;
- non-decreasing server tick/time and strictly increasing per-shot sample
  sequence;
- bounded segment length, lifetime, range and event history;
- one terminal transition per shot (`flight → terminal`), with no updates after
  terminal state;
- a fixed ruleset revision on every sample and terminal event;
- no client-authored coordinate, timestamp, hit, HP or RNG field in an
  authoritative input path.

Exact tick width, step size, interpolation policy and historical dispersion
formula remain **UNKNOWN** until a separate source-and-test card pins them.

### 3. Missing-solver policy

A build that has fire/reload but lacks a verified trajectory or surface solver
must not manufacture a hit. It may:

- reject the shot before admission with `BALLISTICS_UNAVAILABLE` (and leave
  ammo untouched); or
- admit the shot, consume one round, advance only the explicitly supported
  flight boundary, then terminate as `UNAVAILABLE`/`MISS` according to the
  configured test-lab policy.

The chosen policy must be visible in the receipt and ruleset revision. It must
never emit `penetrated`, `damage`, `module`, `crew` or `destroyed` without a
verified impact chain.

## DAMAGE_SPEC boundary

Damage begins only after a server-owned surface intersection and a resolved
material/normal. The AP-first contract is:

```
AP shot → impact surface → angle/normal + effective thickness
         → penetration rule → damage rule → module/crew/HP effects → event
```

Each arrow is a separately testable boundary. The following inputs are
required before `hit` or `damage` can be accepted:

- exact target entity and server transform at impact;
- hit surface/material identity, local transform and outward normal;
- armour thickness and any ordered screen/hull/interior layers;
- AP shell identity and a ruleset-pinned penetration/damage distribution;
- ruleset-defined module/crew mapping and a single damage application token.

No whole-tank armour fallback, guessed thickness, modern formula, or client
crosshair result may satisfy these requirements. A track-only contact, screen,
non-penetration and hull penetration must be distinct outcomes. Duplicate
geometry intersections and duplicate network commands must not create two
independent damage applications.

For shell `2570`, nominal penetration and damage numbers are deliberately
`UNKNOWN`; therefore this card cannot accept an AP hit, penetration or HP
change. The 275 mm FV215b HESH and six-round 128 mm WT E 100 anchors remain
separate future configurations from [`04_RULESET_091`](../04_RULESET_091.md)
and are outside this MS-1 AP boundary.

## Server-authoritative shot identity and idempotency

A shot identity is allocated by the server inside the battle scope. The native
shot number used for tracer presentation is an adapter value; it does not give
the client authority to choose or replay gameplay state. The concrete integer
width and wire encoding are intentionally unpinned here (**UNKNOWN**), while
the required semantics are fixed:

- identity scope includes battle, firing entity and a server monotonic shot
  sequence (or an equivalent opaque server token);
- the first admissible request creates exactly one ledger entry and exactly one
  ammo-consumption side effect;
- a retry with the same identity and byte-equivalent admissibility payload
  returns the existing receipt/state and performs no second consumption,
  projectile, hit or damage effect;
- reuse of an identity with a conflicting shell, gun, pose, target or ruleset
  is rejected as `SHOT_ID_REUSE_CONFLICT` and never mutates state;
- stale, unknown or cross-battle identities are rejected without looking up or
  revealing hidden target state;
- every terminal event carries the identity and a reason code, and the ledger
  is bounded by battle/session lifetime plus an explicit retention limit;
- reconnect/retry delivery can repeat a transport frame, but gameplay
  application remains once-only.

Idempotency is a server ledger/invariant, not a client-side de-duplication hint.
The ledger size, retention duration and exact reason-code serialization require
implementation and load tests; they are **NOT_RUN** in P06A.

## Native adapter boundary

The adapter may translate the already accepted `0x88` fire trigger and existing
reload/ammo callbacks into a typed domain request. It must not:

- trust client coordinates, crosshair, local timer, HP or hit response;
- expose a speculative hit/damage RPC simply because a method ID appears in a
  decompiled table;
- send a damage event before the domain terminal result exists;
- broadcast hidden impact data to clients that are not entitled to observe it.

Native tracer `showTracer`/`stopTracer` remains presentation-only until a later
card proves the complete surface and damage chain. No native hit/damage callback
is claimed by this document.

## Verification matrix for the next implementation card

| Invariant | Offline contract test | Native/owner gate | P06A result |
|---|---|---|---|
| one AP round per accepted identity | required | existing P03E receipt is fire/reload only | **NOT_RUN here** |
| duplicate identity is side-effect free | required | native retry/reconnect capture | **NOT_RUN** |
| monotonic finite trajectory samples | required | two-client visual flight only after solver | **NOT_RUN** |
| continuous/segment surface intersection | required | terrain + vehicle fixture on #717 | **NOT_RUN** |
| exact material/normal/armour layer | required | native hit trace + geometry correlation | **NOT_RUN** |
| AP penetration and damage | required | owner HP/module/crew receipt | **NOT_RUN** |
| one terminal result and one damage token | required | duplicate packet/reconnect capture | **NOT_RUN** |
| historical 0.9.1 fidelity | source/statistical tests | independent #717 evidence | **UNKNOWN** |

A future implementation card may add a bounded offline solver only after it pins
shell and surface inputs. It must preserve the unavailable path and produce
receipts that distinguish synthetic checks from native compatibility.

## Acceptance, limits and rollback

**Actual checks for this docs-only card:** `git diff --check`; required-term
inspection with `rg`; no server, client, native process, database, physics
runtime or deployed artifact was started. This is a documentation boundary,
not a P06 runtime acceptance.

**Acceptance status:** `PASS_DOCS_ONLY_BOUNDARY`; P06 ballistics, armor, hit,
damage, module, crew and native acceptance remain **NOT_RUN**.

**Rollback:** remove the two docs files from this branch, or revert the single
card commit after review. No client, deployed server, ignored local evidence or
runtime state is touched.

**Single next step:** pin the exact #717 MS-1 AP penetration/damage and armor
surface inputs from a read-only source/trace, then implement one bounded offline
AP trajectory/hit checker with the idempotency invariants above. Do not start a
native damage test before that checker has an honest unavailable path.
