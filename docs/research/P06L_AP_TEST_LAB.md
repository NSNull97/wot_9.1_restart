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

## Repaired candidate

Code commit`6751c6f`, build`gateway-integrated-world-p06l-03`:
**485/485 Rust PASS**, executableSHA256
`9f5416ac2fff3f0877600c160165700759a8d7737ce9213bb85f194f5b2fcf45`.
New regressions retain the actual bad VAR2 fragment, measured postmortem
bind+following keepalive and survivor physics/aim/flight with a disconnected
peer. Python26 PASS/1 existing symlink skip; final source layout66/22 PASS.
`impact-wire-source-contract03.json` supersedes the incorrect VAR2 claim
using16 pinned PE windows and6 actual encrypted packet fragments.

Native02 launch commands (owned credentials are consumed internally):

```
python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-integrated-world-p06l-03
python -B -X utf8 local/evidence/20261010-p06l-ap-resolver-01/prepare_stand.py --slot a --run native02
python -B -X utf8 local/evidence/20261010-p06l-ap-resolver-01/prepare_stand.py --slot b --run native02
python -B -X utf8 local/evidence/20261010-p06l-ap-resolver-01/start_stand.py server --run native02 --profile integrated-lab --build gateway-integrated-world-p06l-03 --pool local/build/server/physics-integrated-lane-01/pool.json --geometry local/evidence/20261010-p06j-contact-materials-01/ms1-contact.json --ap-test-lab
python -B -X utf8 local/evidence/20261010-p06l-ap-resolver-01/start_stand.py a --run native02
python -B -X utf8 local/evidence/20261010-p06l-ap-resolver-01/start_stand.py b --run native02
```

Both native clients and accepted workers reached the shared battle.
Current install ledgers:`install-a-native02`, `install-b-native02`.

Independent native02 audit:
`independent-native02-impact-audit01.json`, SHA256
`e6e77e4dbcc8e9ab8c4ae9a17914001bd1c798ff13d443364d37f0d4c8cba0dc`.
Three penetrations produced six original `showDamageFromShot` normal
returns520, each with one decoded point and effect`armorHit`. A/B decoded
points match exactly; both clients show targetHP90→60→30→0. Each has370
snapshots; both remain in the world for at least248s after death. Surviving
actor moves6.37m and changes gun aim1.226rad in both native observations.
Server records4955 post-death snapshots,820 aim commands and8 move commands.
The measured own postmortem bind is explicitly accepted. Channel rejects,
session closures, stderr and native diagnostic errors are all zero in this
pinned prefix. Startup marker oracles now pass in both clients.

Packed-point raw comparison is NOT_RECORDED: the native input is
`PyArrayDataInstance`, not a Python list. Outcome and local points are checked
from the original decoder's returned facts instead. Native callback completion
does not establish rendered/audio owner acceptance. No post-death shot was
observed in this prefix. **Remaining gate: owner's rendered result and one
survivor shot after death in a new direction.** Candidate stays unmerged.

## Owner native02 acceptance and wreck-impact correction

Owner: «щас вроде бы все корректно, эффекты тоже есть, хотя от уничтоженного
танка нету», clarified as «Нет эффекта попадания, если стрелять в уже
уничтоженный танк». This accepts the previous survivor/impact checks but
reports a distinct wreck-hit gap, not a missing destruction explosion.
Owner also confirmed personally closing both clients at the end of the run.

`independent-native02-owner-followup01.json`,
SHA`7fda90ff4086e1dd54ed716127d36baae8570d7ecd10956eff6489c82ca60b23`,
pins the completed gameplay prefix5902474bytes. Shots4..11 changed origin and
direction and completed in both clients before the first rejected message.
Shots6..10 contact dead Hull armor1/2;10 native tracer endpoints match within
1e-4, but no impact callbacks are sent. Raw audit02 still retains late
retry_exhausted/channel_state/base_route errors after the completed gameplay;
owner closure is OBSERVED context, not proof of the exact native exit cause.

Cause: model.rs gated all impact events on target.health>0. Contact and tracer
stop already worked on the retained mesh. Source receipts
`wreck-effect-source-contract01.json`, `wreck-native-codec-contract02.json`
and additive03 pin original #717 pyc/function hashes. VERIFIED: the native
effect is added before isAlive's return397; original descriptor hitTester/bbox
is reused on an HP0 vehicle, while current appearance supplies attachment
matrices. Code1 maps to armorResisted without hasDamaged; code2 asserts actual
penetration-no-damage and is not neutral. Neither source proves historical
authoritative wreck penetration rules.

Correction in domain commit`e64cf57` and root integration`f405c17`:

- `shared/model.rs`: typed ImpactOutcome::Ap or WreckBlocked. Wreck contact
  creates a valid native segment, stops the projectile and keeps HP0→0 and
  the dead actor unchanged; live AP resolver is not called.
- `shared/impact.rs`: separate WreckImpact/TestLabWreckImpact bound to shot,
  target pose and nearest material; invalid health, duplicate, order or
  capacity errors roll back. Same25800 event budget, not an extra AP event.
- `shared/server.rs`: log SHARED_WRECK_IMPACT; native code1 publication uses
  existing atomic cursors/queues. HP/death/roster require actual HP reduction,
  so wreck effects cannot trigger them. Reconnect does not replay old hits.
- `shared/geometry.rs`: document ordinary attached HP0 descriptor reuse.

Policy `test_lab-ms1-wreck-block-v1` deliberately blocks AP on the retained
attached Hull/Turret/Gun geometry. It is an approximate laboratory policy;
exploded or detached parts are excluded. Static API support for all three
components is not native acceptance of each component. The first manual gate
targets Hull; Turret/Gun wreck-specific native measurement remains NOT_RUN.

Build04 failed compilation on a root error-type conversion, before running
tests. Build05 corrects it and passes **493/493 Rust tests**, including8 new
checks for wreck identity/health/rollback/full-budget and two-client once-only
publication/no repeated death/reconnect. Executable SHA256:
`80595efc05f206cd0449524213040ac06c38e930d98e40078f512ffbf6c54845`.
Layout66sources/22relocations PASS. Python production code is unchanged from
the previous26 PASS/1 existing skip; the new ignored wreck auditor separately
passed8 controls, including real frozen native02 and synthetic negative cases.
These auditor controls do not replace a new real-client wreck shot.

Commands:

```
python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-integrated-world-p06l-05
python -B -X utf8 server/check_layout.py --out local/evidence/20261010-p06l-ap-resolver-01/source-layout-wreck.json
python -B -X utf8 local/evidence/20261010-p06l-ap-resolver-01/prepare_stand.py --slot a --run native03
python -B -X utf8 local/evidence/20261010-p06l-ap-resolver-01/prepare_stand.py --slot b --run native03
python -B -X utf8 local/evidence/20261010-p06l-ap-resolver-01/start_stand.py server --run native03 --profile integrated-lab --build gateway-integrated-world-p06l-05 --pool local/build/server/physics-integrated-lane-01/pool.json --geometry local/evidence/20261010-p06j-contact-materials-01/ms1-contact.json --ap-test-lab
python -B -X utf8 local/evidence/20261010-p06l-ap-resolver-01/start_stand.py a --run native03
python -B -X utf8 local/evidence/20261010-p06l-ap-resolver-01/start_stand.py b --run native03
```

Native02 server was stopped by exact PID/executable receipt after both client
processes were absent; native02 install ledgers rolled back. Current native03
ledgers are install-a-native03/install-b-native03; rollback uses those ledgers
and the earlier accepted P06J runtime as documented above. Alternatively the
P06L native02 candidate build03 retains owner-accepted live impacts but its
known missing wreck FX. Current card remains unmerged, native wreck result
and rendered owner acceptance pending. One next step: destroy a tank and hit
its Hull twice more; collect code1/armorResisted/return397 and HP0 in both
clients without repeating health/death callbacks.

## Final scoped acceptance — 2026-10-10

Owner confirmed native03: «отлично! работает!». Full card acceptance is
**PASS_OWNER_NATIVE_AP_AND_WRECK_TEST_LAB**, scoped to the actual completed
gameplay checks and the declared approximate rules. P06/historical fidelity,
complete ballistics and all-session startup reliability are not claimed.

`independent-native03-wreck-scoped-followup01.json`, SHA256
`99fab4c52609a38d68f56f228aa40ab00758e4b404c94ffcca539f7777160ae9`,
records three AP hits and two wreck hits. Both clients process the latter via
original return397, code1/armorResisted, HP0; decoded points match exactly.
All10 tracer endpoints match server contacts within1e-4. Each client has
exactly3 health changes/1 zero-health callback, with no repeat death. Both
remain present147.8s after death. Selected native traces and completed battle
contain no errors. This run only moved~0.1m; full driving acceptance remains
the prior native02 owner/trace gate, not a new broad driving claim.

Startup evidence is explicitly not green: simultaneous login caused an
initial server-not-ready rejection for clientA. The earlier A process13980
later reported logged-on but produced no shared snapshots. It was stopped
using exact PID/path verification and restarted sequentially as12532.
The orphan session2 expired at tick1000 before the completed battle; the
selected A became session3/slot1, B remained session1/slot0. The fixed snapshot
boundary is the second SHARED_READY (session3), line1282/byte134745. Full
`independent-native03-wreck-audit01.json` retains FAIL_NUMERIC_WRECK_AUDIT
for that earlier session close. The scoped followup reads the same pinned
prefix and preserves failed launch/stop receipts; it does not omit a failure
during the accepted battle. Concurrent-login reliability is an open existing
startup limitation, not an unimplemented impact-card criterion.

Commands completing this acceptance:

```
python -B -X utf8 local/evidence/20261010-p06l-ap-resolver-01/independent_native_wreck_auditor_checks.py
python -B -X utf8 local/evidence/20261010-p06l-ap-resolver-01/independent_native_wreck_auditor.py --run native03 --out independent-native03-wreck-audit01.json --a-launch-receipt launch-a-native03retry.json
python -B -X utf8 local/evidence/20261010-p06l-ap-resolver-01/independent_native_wreck_scoped_followup.py
```

No runtime source changed after the493-test build. Final summary pins these
sources and evidence. Rollback remains exact-process stop + native03 install
ledger restore + accepted P06J runtime; Git rollback after merge is a revert
of the P06L merge. One next recommended card: server projectile collision
with terrain, built on this accepted cumulative physics/aim/ammo/hit/HP path.
