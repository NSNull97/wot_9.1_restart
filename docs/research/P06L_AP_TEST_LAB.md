# P06L — approximate AP damage on the cumulative native runtime

Owner decision, 2026-10-10: «Рабочий test_lab: неподтверждённые правила явно
помечать как приближение, затем уточнять». Branch `codex/p06l-ap-test-lab`,
base P06K merge `67da292`. This authorizes an explicit approximate profile;
it does not establish historical 0.9.1 server fidelity.

## Contract and provenance

`test_lab-ms1-ap-single-plate-v1`, `historical_fidelity=approximate`, requires
the integrated physics route, pinned P06J contact bundle and the explicit
`--ap-test-lab` CLI flag. Ordinary modes retain their previous behavior.
Stock MS-1/AP only; two allied temporary actors with explicit lab friendly
fire. No garage/economy persistence or original-client modifications.

| Fact or rule | Status / scope |
| --- | --- |
| MS-1 stock AP2570:37 mm, nominal power34/27, damage30, range720, vehicleHP90 | VERIFIED pinned #717 resources; P06K source audit |
| Component armor and special flags, exact nearest triangle and full pose | VERIFIED P06I/P06J source/native measurements; unchanged geometry bundle |
| Angle uses abs(dot) against triangle winding | Explicit approximate plane policy; outward normal/entry vs exit UNKNOWN |
| Nominal power:34 through100m, linear34→27 through500m, extrapolated to720m | Explicit approximate use of client marker law; straight origin-to-contact range |
| AP normalization5°, >=2 calibers boost1.4×ratio, >=3 no ricochet; otherwise>=70° ricochet | Versioned test_lab choices; not a recovered server algorithm |
| Strict power>effective armor; homogenization1; fixed30 damage, no RNG | Explicit approximation; historical distribution/order/equalities UNKNOWN |
| Positive ordinary hull/turret plates only | Unsupported guns, screens, zero/missing/special material have explicit no-damage result |
| Native component bounds and transforms | VERIFIED original .visual and actual hitTester.bbox agree bitwise at float32; vertex min/max differs |
| Packed visual endpoint nearest-byte rounding | INFERRED inverse of original decoder; actual sender rounding UNKNOWN |

Historical research is retained in `historical-rules-research.json`. The 2012
original developer article supports parts of the caliber/ricochet concepts;
archived community wiki contains useful formulas and known contradictions.
Neither is presented as the exact #717 authoritative implementation.

## Implementation

- `shared/ap.rs`: pure bounded resolver, no wire IDs, no HP mutation.
- `shared/model.rs`: authoritative health, atomic contact/outcome/HP/terminal
  transaction, one outcome per shell; death blocks new drive/aim/fire;
  already-fired projectiles finish. Rejoin preserves HP and ammo.
- `shared/impact.rs`: typed outcome links the exact nearest material record,
  shooter, target, pose revision and before/after HP. Bounded25800 events.
- `shared/geometry.rs`: native bbox and inverse full component transform;
  line-preserving clipping and local first-surface verification.
- `shared/impact_wire.rs`: original Vehicle impact, health-property then
  health callback, separate own Avatar health/postmortem callback.
- `shared/server.rs`, `shared/mod.rs`, `shared/wire.rs`, `main.rs`: opt-in,
  reliable per-peer cursors, current health on creation/rejoin, no stale FX
  replay, bounded queues and source-side logging of approximate outcomes.
- `client_patch/sr_interactive.py`: passive original callback observations,
  decoded native hit points and health; bounded startup oracle waits for two
  started vehicles. No damage/position/callback fabrication.

## First actual native run and defects found

`native01`, gateway `gateway-integrated-world-p06l-02`, SHA256
`82fe57880233b61e3aea51abd199ae9f738f2fc33227d7f20e502a4d1b6fc755`:
**482/482 Rust PASS**, but native acceptance **FAIL**. Owner's real shots
produced3 server penetrations and6 peer publications. Both real clients
reported targetHP90→60→30→0. Vehicle health callbacks returned at original
offset170; damaged Avatar's own callbacks returned at439. Owner confirmed
HP loss/destruction, then reported disconnect and a frozen survivor.

Independent audit corroborated the defects:

1. No original `showDamageFromShot` invocation despite emitted packets.
   Exact #717 PE analysis established a one-byte variable client method
   length. The first encoder incorrectly used two bytes. Extra00 shifted
   arguments, making ARRAY count265 instead of1; trailing02/13 was consumed
   as a different harmless fixed message, so health still worked. Native
   method-size callback `dd0880` returns-1; `ee3480` negates the result and
   stores lengthParam1; `ee3660` dispatches to byte reader `ee369d`. Corrected
   encoder uses VAR1, while inner ARRAY retains its verified signed32 count.
   Health success alone did not prove impact delivery.
2. Original postmortem Cell `Avatar.bindToVehicle` arrived as standalone
   `0d08000000000005001009`. Server only recognized it inside the startup
   compound. Rejection of reliable5596 poisoned later empty keepalives and
   eventually caused `retry_exhausted`. The exact stock postmortem caller and
   original `.def` semantics were recovered. Own dead-camera rebind is now
   admitted without changing gameplay ownership or state.
3. Integrated physics dispatch kept accepting commands after peer retirement,
   but a two-active-sessions guard prevented the world clock from advancing.
   Thus eight later shots reused one origin/velocity; snapshots and tracer
   stops ceased. Disconnected actors now retain a stationary server pose,
   while the surviving actor continues simulation. A regression validates
   motion, aim, flight and rejection of a forged parked pose.

The first native run was stopped using exact receipt PID/executable matches.
Its failed evidence is retained, not overwritten or called PASS.

## Checks, commands, evidence and rollback

Pinned Windows GNU Rust1.90.0 build driver only:

```
python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-integrated-world-p06l-02
python -B -X utf8 server/check_layout.py --out local/evidence/20261010-p06l-ap-resolver-01/source-layout.json
python -B -X utf8 -m unittest tests.test_interactive_window_trace tests.test_interactive_primitive tests.test_interactive_relogin_control tests.test_server_layout
```

Build01 had480 PASS and2 faulty new test assertions; build02 corrected those
assertions and passed482. Python26 PASS/1 pre-existing Windows symlink
privilege skip; layout66 source files/22 relocations. These checks predate the
native01 defect repairs; final build/native results must be recorded separately.

Evidence root: `local/evidence/20261010-p06l-ap-resolver-01/`.
Wire source audit: `local/evidence/20261010-p06l-ap-resolver-rules-01/`.
`independent-native-impact-audit01.json` and `followup01.json` pin the failed
prefix with byte lengths and hashes. UI input attempt was NOT_RUN: two WGC
timeouts, no automated clicks or shots. User supplied real input instead.

Launch uses this evidence root's `prepare_stand.py` / `start_stand.py`, two
approved copies `local/clients/p03f/a,b`, accepted physics pool
`local/build/server/physics-integrated-lane-01/pool.json`, unchanged contact
`local/evidence/20261010-p06j-contact-materials-01/ms1-contact.json`.
Credentials remain in the established owned one-shot files, absent from argv.

Rollback: stop only receipt-matched clients/test gateway; run
`tools/interactive_client.py rollback --out <install-ledger-directory>` for
the current a/b ledgers; launch the accepted P06J runtime with the same pool
and contact bundle, AP flag absent. Revert P06L commits as one card if needed.
Canonical service and original client are untouched.

Limitations: no projectile terrain collision, layered armor, module/crew
damage, random damage/penetration, external ricochet continuation, battle
results or persistence. Death is ordinaryHP0, not ammunition explosion.
Reconnect retains laboratory lane rebase, including a dead actor. Worker
braking may complete one already-dispatched step after death. Native death
and continued survivor behavior require actual repeated owner acceptance.

Current gate: **repair native01 defects, repeat native destruction and
survivor motion/aim, then owner acceptance**. Keep the card on its branch
until this gate passes; historical_091 and P06D are not declared complete.
