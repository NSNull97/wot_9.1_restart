# P06N — one authoritative destructible fixture

Owner accepted P06M and authorized this next card. Base main7f2a0f2; branch
codex/p06n-destructible-state. Goal: one original Karelia obstacle destroyed by
an authoritative projectile contact, with native state shared by both clients
and consistent subsequent movement/projectile geometry. Owner accepted native02
on 2026-10-12: destroyed in both windows, passage free; cumulative check works.
**Acceptance: PASS_OWNER_AND_SERVER_CUMULATIVE_TEST_LAB.** Tested source
3bb677076d2d9915449754bd32e415bea4303421; current hashes in candidate-native02.json.

## Source and identity

VERIFIED resource fixture: instance1513, chunk[-5,-5], original chunk31354,
spaces/01_karelia/fffbfffbo.chunk model[2], mle009_BoxCamouflage. HP15 is from
original destructibles.xml; intact n_wood_0 kind73 has42 triangles in both
accepted meshes. The two sets of vertex coordinates are byte-identical.
Projectile span[88749,88791); physics span[171814,171856). Destroyed d_wood_0
kind87 flags255 is excluded by both original masks18 and128. Visual debris
can remain after collision removal.

OBSERVED and source-bound in both original clients: native itemIndex1, not
the source model ordinal2. Original filename/matrix getters and five of six
bounded rays agree exactly with source position and matrix. The sixth ray
correctly meets another nearer surface. Observer never mutates gameplay or
supplies authoritative hit decisions. Identity01 failed before login because
the one-shot control allowlist was incomplete; identity02 corrected it.

VERIFIED native contract: AreaDestructibles client type3; four ALL_CLIENTS
arrays, no ClientMethods. destroyedFragiles property0x9f uses VAR1 framing,
then signed32LE array count and packedUINT16 (nativeIndex<<8)|shotDamage.
Initial creation restores full state without the transient break effect;
live setter acts on set difference. Original decayEffect may run on initial
state. Entity0x09100007, alias2, position[-450,0,-450] identifies chunk31354.

## Implementation and limits

- shared/destructible.rs and model.rs: typed one-time scene0→1 transition;
  contact/triangle/material/shot/tick binding and transactional rollback.
- shared/impact.rs: dynamic scene identity in queries, one typed transition;
  MAX_EVENTS36041 retains bounded full-ammo trace.
- shared/obstacles.rs and terrain.rs: exclude all selected instance faces
  during BVH traversal, before nearest selection; ground is unchanged.
- physics/Program.cs and CheckedInput.cs: split only the selected42 triangles
  into an independent Jolt body, typed idempotent removal, source pins.
- drive/worker.rs: IPC2 opt-in with generation/descriptor/scene/sequence ACK;
  legacy IPC1 remains available without the removal descriptor.
- shared/server.rs, mod.rs, destructible_wire.rs and main.rs: explicit
  --destructible-test-lab option, native area lifecycle/ACK, state catch-up,
  staged world commit after initialized workers acknowledge removal.
- client_patch/destructible_probe.py, sr_interactive.py and installer:
  versioned bounded passive identity and original callback observation.

Policy test_lab-karelia-fragile-ap-v1 is explicitly APPROXIMATE: a stock AP
contact applies30 damage to HP15 and terminates this first shell. Historical
resistance, continuation, impulse and full-map destruction are UNKNOWN and
not implemented. Only this one source-pinned object can change state.

During the short removal barrier, native transport/ACK/keepalive continues,
commands stay in the existing bounded queue, and no candidate world/impact
is published. Pending movement replies are consumed before staging. Partial
worker failure or changed session membership fails the battle closed; cloned
World rollback is not claimed to undo an external Jolt mutation. A worker
which has never initialized is not a participant; it must restore scene1
before supplying a pose or allowing native entry. Reconnect restoration is
per slot, so it does not stop survivor input. Worker generations increase.

## Evidence and checks

Evidence root: local/evidence/20261010-p06n-destructible-01/.

| Check | Result and exact evidence |
|---|---|
| Original resources | resource-contract/resource-contract01.json; SHA837e51e1b6fdd13b64a09949542e79f4c6b55dea69e50329335b3cb3e9c451db |
| Native source/PE contract | native-contract/contract01.json; SHA75bee50824733750d8d547c95daae275a9b22dd6359a98405ac7d1d9d7be490d |
| Two native identity oracles | native-contract/identity-native02.json; SHA59a9316085b313693a5775ca503fd112b50dcc119cfc948fb3aef2e7ad0bf13b |
| Private physics removal/negative IPC | boundary/worker-ipc01/receipt.json; SHAf63d6cd72fbb28183993274685a398f16df873463ddd9a336bb4103819be7b76 |
| New root physics build/near fixture | near-physics-root01/receipt.json; SHAa969758bd99a6b1adda8b597b8a18ac10d5744af46c50dd66c3f8bdafe85a10c |
| Gateway01 | 553 Rust PASS; isolated source candidate before review fixes |
| Gateway02 | 557 Rust PASS; before additional cold reconnect edge fix |
| Gateway03 | 556 PASS/1 FAIL: new test did not initialize its manually polled worker pose cache; retained |
| Gateway04 | 557 Rust PASS, final server candidate; SHA9e3adc3426cdc7052221f40a5ae038367cb00c32426b4af09f262ece9ccfe8b8 |
| Python focused source/control | 27 PASS after fixed-ID observer regression; earlier layout group30 PASS/1 existing Windows privilege skip |
| Native01 initial area/physics | Both original onEnterWorld return, chunk31354/empty state; both workers settled with6 contacts |
| Native01 periodic observer | FAIL: total engine entities exceeded old16 cap; preserved, explicitly stopped for observer repair |
| Native02 entry/destruction | 21/21 log checks PASS; audit-native02-entry.json SHA f4acdcdecb95859e0579b78c49c4cd61ed5e79853c25e8f1cf11b0f9310b1da3 |
| Native02 cumulative regression | PASS; cumulative-native02-audit01/receipt.json SHA c989364f41ad76c5bd85ae98f9122a0bca8dced7c314970a94139c47143364d1 |
| Native destruction and driving passage | OBSERVED owner: destroyed in both windows, passage free; owner-destroyed-native02.png SHA c0a86028460b6b653addfdfa433961e0787a1053f5b1c6bf047a0688c24e164c |
| Native reconnect after destruction | NOT_RUN; worker restoration/state encoding tested, rendered re-entry is outside accepted manual slice |

Root physics build: local/build/server/physics-integrated-p06n-01,
DLL SHAe97d6e0bc82757fb240c1b7a4eab1c80b38a97a536250286cfe1f36d01029c2b.
Near pool SHA9eafc00640aefe28f8d62cb6e11e316374b1292a894b09bb4a31204a1fa9552f.
Only spawn changes relative to accepted map parameters: origin[-398.25,58,-414],
yaw0, runtime lane offsets±4m. Both settled with six wheel contacts. Identical
private driving inputs stop at intact crate z−408.1968 versus reach z−346.02783
after removal. This is real Jolt evidence, not native rendered acceptance.

Agent worktree tests retain earlier missing fixture/linker failures in their
own build outputs. Canonical root full suite is the integration gate. First
Python observer test attempt had3 missing-global fixture errors; evaluating
source path before the opt-in guard fixed this, and the focused suite passed.

Native01 later exposed a separate observer assumption: total engine entities
are not restricted to the two fixture Vehicles. Both clients exceeded16 and
stopped periodic observe() scheduling; profile callbacks continued. Exact
extra entity classes/cause are UNKNOWN, not evidence of a leak or particles.
Original Avatar.updateVehicleHealth/ProjectileMover bytecode verifies
BigWorld.entities.get(ID). The repaired observer performs exactly two fixed
Vehicle ID lookups, validates present entity type/ID, and records total count
without enumeration. A regression mapping with1000 unrelated entities rejects
values()/iteration and verifies only those two lookups. This changes passive
diagnostics only; final gateway04 remains the tested server binary.

Native02 launch receipts/install ledgers are under the evidence root. The
server uses gateway04/pool-near; sequential clients enter the same cumulative
integrated profile. Stop-native01 records explicit process identity/hash/time
checks and termination for repair, not a gameplay crash. A first stop attempt
compared a local DateTime against UTC and refused to stop; rollback/prepare
also refused while clients remained active. Normalizing both UTC values fixed
the guard; only then were the ledgers restored and native02 installed.

## Accepted native02 result

VERIFIED within pinned complete-line prefixes: both workers acknowledge
removal before the single scene0→1 commit (shot3), then both native clients
receive destroyedFragiles=[257]. Original __destroyFragile and effect callbacks
return normally in both clients. The repaired observer continues with17 total
native entities and exactly two observed Vehicles; no observation errors.

Independent cumulative prefix (06:24:30 UTC) contains15 admitted shots,
ammo20→19 on A and20→6 on B; shots5/9/11 reduce A HP90→60→30→0.
Shots12/13 hit the wreck with zero damage and armorResisted in both clients.
Each client has15 tracer returns,5 vehicle impact returns,3 HP changes and9
world effect returns (actual terrain shots7/10/15). Survivor B moves27.15m
after death with24 active inputs;520 server aim pairs and27 native packed
angles confirm continuing aim. Repeated-shot intervals are at least2.628s.
All relevant callbacks pair once; neither trace cap nor errors/stderr occurred
inside these saved prefixes. Later live tails are not implicitly adjudicated.

OBSERVED owner separately confirmed the crate change/passage in both windows,
provided a destroyed-object screenshot, then answered that ground/live/wreck
effects, HP/reload and survivor control all work. Physics, ammo and aiming use
the same cumulative integrated runtime; the near-object pool changes spawn
only. This closes this single-object card, not historical/full-map destruction.

## Reproduction and rollback

All builds use the pinned driver, fresh ignored output:

```powershell
python -B -X utf8 server/build.py physics --out local/build/server/physics-integrated-p06n-01
python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-integrated-world-p06n-04
python -B -X utf8 local/evidence/20261010-p06n-destructible-01/near-physics-root01/audit.py
python -B -X utf8 -m unittest tests.test_shared_lab_control tests.test_shared_client_copy tests.test_interactive_window_trace tests.test_interactive_primitive tests.test_interactive_license_policy
python -B -X utf8 local/evidence/20261010-p06n-destructible-01/start_stand.py server --run native02 --build gateway-integrated-world-p06n-04 --profile integrated-lab --pool local/build/server/physics-integrated-p06n-01/pool-near.json --geometry local/evidence/20261010-p06j-contact-materials-01/ms1-contact.json --ap-test-lab --terrain-test-lab --destructible-test-lab
python -B -X utf8 local/evidence/20261010-p06n-destructible-01/start_stand.py a --run native02
# Wait for SESSION_ACTIVE before starting B.
python -B -X utf8 local/evidence/20261010-p06n-destructible-01/start_stand.py b --run native02
```

Native launch uses this evidence root's prepare_stand.py for slots a/b, then
start_stand.py server with --profile integrated-lab, the accepted contact
bundle, --ap-test-lab --terrain-test-lab --destructible-test-lab and the new
pool-near.json. Start A, wait for SESSION_ACTIVE, then B. Exact launch receipts
pin executable, command, pool/config and log paths. No original client writes.
After host restart, stale service ownership was verified and recovered through
tools/local_server.py recover; a separately receipted owned identity bridge
was restarted for this test. No shutdown is scheduled.

Rollback: close only receipted owned clients/gateway; use interactive_client.py
rollback with their install ledgers. Return to main7f2a0f2 and accepted
gateway-integrated-world-p06m-05 with physics-integrated-lane-01/pool.json and
the same P06J contact bundle/AP/terrain flags. Previous files/pools are retained.
After acceptance, merge the P06N branch into main with --no-ff and push under
the owner's standing workflow. Check unchanged candidate runtime hashes and
publication allowlist before merging; save actual main/remote SHA receipt.

One next recommended card: generalize this source-bound fragile-object table
to multiple same-kind Karelia crates, preserving per-object identities,
acknowledged geometry changes and cumulative gameplay. Native reconnect is
still an explicit unverified coverage item; do not claim rendered restoration.
