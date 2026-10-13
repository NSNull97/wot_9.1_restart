# P05B — moving fence contact, candidate14

Date:2026-10-13. Branch:`codex/p05b-tracked-handling`.
Starting checkpoint:`9f384fa`; implementation plan:`cd6dc50`.
Evidence root E:`local/evidence/20261013-p05b-tracked-handling-01/`.
Status: scoped automatic checks and final gateway755/755 PASS;
actual wheel-only fixture and native owner acceptance NOT_RUN. Static pressure
FAIL/OPEN. This remains the existing P05B card; full acceptance is not claimed.

## Problem and contract

OBSERVED in retained candidate08 source-geometry runs: moving side contact
with fence3167 has enough total linear energy but less than8000J normal
energy; MS-1/IS-7 can snag without removal. Original #717 client prediction
uses total speed, but its predicate is not proof of the historical server's
resistance or energy loss. The chosen correction extends the existing explicit
8000J test_lab policy; it does not claim a historical material constant.

Domain6 / worker7 select `test_lab-fence-total-energy-v1`. All1038 original
source/native identities, geometry spans, HP, projectile masks and119 chunks
are unchanged. Only403 existing movement-fragile fence sections select
`ram_response=total_linear`;626 trees and9 whole fragiles keep `normal_linear`.
Both catalogs explicitly bind this discriminator; domain derives8000J from
the policy and the worker stores it. An exact7-resource scope guard narrows
the new domain policy, while original exporter admission still uses verified
material/geometry contracts rather than a filename heuristic.

Actual hull callback is mandatory. Raw and shared remaining velocity both
need incoming normal speed>=0.1m/s, total speed<=25m/s and sufficient energy.
A fence consumes8000J from total linear energy with a radial velocity change;
ordinary objects preserve the previous normal-only operator. Every substep
has one shared shadow velocity, unique bounded receipts and ordered mixed
debits. The same operators run on actual post-solver velocity, so an unrelated
wall's stop is not refunded. IPC5 envelope remains; exact catalog hash/version
binds the new semantics. Wheel-only, query-only, separating and zero COM speed
do not independently authorize destruction. Both-worker ACK barrier remains.

## Evidence completed so far

- `night-fence-python01/result.json`:119 affected Python tests PASS, zero
  skips. Initial receipt's generic PASS_WITH_RECORDED_SKIP label was inaccurate;
  retained log and explicit result correct it without rewriting the first file.
- `night-fence-export01/catalog/`: fresh source export and existing passive
  join,1038 objects/403 fences/119 chunks. `projection-receipt.json` verifies
  unchanged identities/geometry. `legacy-byte-proof.json` proves all six
  prior domain3–5/worker4–6 exported files remain byte-identical. Two prior
  native-slot captures were identical and deduplicated; no fresh native probe.
- `night-fence-components04/`:162 focused C# checks, including83 retained
  old-policy/prepass checks. Out-of-bound random stimulus39.664m/s caused a
  retained harness failure; corrected generation stays inside25m/s and
  checks10000 vectors with the unchanged4J float-accounting property.
- `night-fence-worker01/completion.json`:59 targeted Rust worker tests PASS.
 93 scalar and2 mixed-order real C# output witnesses match total-mode f32
  bits exactly. Legacy normal tolerance remains unchanged. Catalog/schema,
  single-ULP forged debit, mixed budget, exhaustion and wall-zero negatives pass.
- `ram-regression/candidate14-new-{canonical01,oblique01,wall01}/`:22 paired
  cases PASS,44 owned workers exited0. `night-fence-review01/receipt.json`
  independently checks7760 IPC headers, exact contact identity, ACK ordering,
  strict8000J admission,28 total stage vectors and44 normal stage vectors.
- `ram-regression/candidate14-old-{canonical01,oblique01,wall01}/`:20 paired
  old-policy cases PASS. All states/contacts/fractures match13 byte-for-byte.
 16 non-wall configs/ACKs also match;4 walls require only validated identical
  geometry's absolute-path/config-hash normalization. No state/time normalization.
- `night-fence-moving01/run01/receipt.json`:8 paired cases PASS. Both profiles
  at private3/6m/s caps break3167, receive both ACKs and fully pass. Four
  parallel/away controls produce no contacts/removals. Every positive first
  normal energy is below8000J, demonstrating the total policy is exercised.
- `night-fence-handling14/parity13-14.json`:32 coast+6 grip runs,19 repeats,
 5710 frames. No contacts/fractures. States/commands match13 except explicit
  catalog/scene hashes; diagnostics are byte-identical.
- `night-fence-chain14/run01/receipt.json`: clear source chain3166/3167 passes
  with both masses, ordered radial spending and full-body passage. Pivot
  controls retain114 actual hull-contact frames per profile without free
  destruction. Static pressure therefore remains an unresolved behavior,
  not a repaired feature. Rest controls without contact prove no pressure claim.

The new ram harness's frozen mass-comparison field has a documented analysis
defect: total incoming speeds were compared with normal-speed debits. The
independent review corrects this using total-speed debit: MS-1 loses0.6399015m/s
versus IS-7's0.0395116m/s at incoming speeds differing by0.00395m/s (existing
match limit0.1m/s). Related old field labels are not repeated as normal-energy
facts. This correction uses retained runs; no runtime rerun is implied.

## Bindings, commands and limits

Fresh full gateway:`gateway-p05b-night-final14`,755 PASS/0 failed/0 ignored.
EXE SHA256:`a4fa2d75e088c87b5d3c4335d265921a5d95a9d457a62099af5bc6bf9af2a005`.
`gateway14-source-before.json` pins99 server files before the gate;
`night14-checkpoint.json` verifies them afterwards and ties the receipts together.
Layout check99 source files/22 relocations PASS. New source-profile gateway
test validates radial receipts, prepared-state blocking, delayed second ACK,
atomic domain/trace commit and actual fresh-worker restoration for both tanks.
Final source-profile first normal energies: MS-1≈577J, IS-7≈8111J. Private3/6m/s
side cases separately establish the below-normal-threshold admission difference.

Test-fixture failures remain under `night-fence-sharedtests02/03`: the first
exit waiter mishandled an already-reaped process; the next seed omitted impact
history and correctly failed scene-revision validation. Corrected04 seeded
private initial removals through bounded domain transactions and passed6/6.
No runtime rule was relaxed. The final full755 includes these tests.

`night-fence-components04/completion14.json` records66 actual-worker launches
owned by that subtask:38 handling,16 chain/control and12 wheel-search launches.
The12 search launches include4 rejected settle fixtures and8 completed runs;
no qualifying wheel-only contact was found. Actual wheel-only is NOT_RUN,
distinct from verified unit/domain rejection of the wheel contact kind. These
are additional to root ram/side/gateway groups; do not sum overlapping checks.
New stationary fixtures do retain30 actual hull frames at near-zero speed per
profile with no removal. That verifies no free break, not desired pressure damage.

Candidate14 DLL:`6c159df6a3d1d7e79cd4268417875a95f3d88366fc3c49b1afef5b3d185a8fb4`.
Complete16-file artifact manifest:
`952f57ef6300f9c60b3444a1a75d14e9ea5f6ebaa101f6537bae92d893994e61`.
Source/build receipt:`night-fence-components04/source-build14.json`.
Domain manifest:`9f54f371441a825c4d3f0dbd975e82a8c9644470d63188421a130e6639918165`.
Worker catalog:`9c40f5bdeb8b77364805f31f18a9c6943a811630f7676fd10c6ec55d8ec5fd5e`.
TrackedHandling source stays byte-identical to13.

Commands actually executed include:

```powershell
python -B -X utf8 server/build.py physics --out local/build/server/physics-p05b-candidate14
python -B -X utf8 server/build.py gateway --test --test-filter map_drive_worker091:: --out local/build/server/gateway-p05b-fence-focused01
python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-p05b-night-final14
python -B -X utf8 tools/compound_destructible_catalog.py --out local/evidence/20261013-p05b-tracked-handling-01/night-fence-export01/catalog --moving-fence-response --native-export local/evidence/20261013-p06r-compound-01/native-probe/runtime-a-fenceids01/destructible-catalog-46736.json --native-sha256 ca420c2ca560457f87acc10b1449f262d0f8a1ec3c4eb163e9bde2ed1f6cc5ab
```

All six ram invocations, affected Python modules, paired side/chain/control
commands and exact configs are recorded in their receipts. Modified runtime:
physics CheckedInput/FractureResponse/Program; gateway worker catalog/fracture,
shared fragiles and narrow server projection/contact diagnostics. Added tests
and exporter flag are listed by the final Git checkpoint; unrelated P09B is
excluded. No client, live DB, original copy, installation or native input changed.

Limits: isolated source-object fixtures deliberately seed other objects removed;
this is not proof of prior destruction or a whole native battle. Source-profile
gateway integration is separate from private3/6m/s cap tests. Historical
resistance, stationary pressure, excluded houses/barrels/logs/compound coverage,
cross-platform determinism and all-substep zero-speed behavior remain UNKNOWN
or OPEN. No new drift/boost control is introduced.

Rollback: select preserved candidate13/gateway13 and domain5/worker6 catalogs,
or revert only this bounded phase's commit after receipt-owned stand cleanup.
Stand remains stopped/restored; owner gate keeps the card out of main.
Next: continue the existing cadence evidence task using bounded actual workers
before morning owner testing. No pending partial runtime mutation remains here.
