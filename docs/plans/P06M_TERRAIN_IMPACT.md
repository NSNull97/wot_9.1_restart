# P06M — authoritative projectile contact with accepted map terrain

Base: main55af06f (owner-accepted P06L). Branch: codex/p06m-terrain-impact.
Evidence: local/evidence/20261010-p06m-terrain-impact-01/.

## Final acceptance

Completed on2026-10-10: owner accepted corrected native02 world effects and
explicitly confirmed the final wreck effects in both clients. Snapshot02
records13 world contacts/26 original FX pairs; snapshot03 records six later
wreck events and12 publications with no repeated damage/death. Original
callback logging for those later wreck shots reached its finite16MiB cap;
their rendered acceptance is the actual owner check, separate from server
event proof. It is not a measured late-callback PASS. Accepted P06L wreck
logic and cumulative physics remain unchanged.534 Rust tests and26 Python
checks passed; one existing privilege skip retained. Detailed report states
limits and preserves native01 failure. No mandatory owner test is pending.

## Owner test correction, same card

Native01 delivered15 terrain effects to both clients, but owner reported
missing/pass-through rocks and variable delayed rock FX. The native original
stops some tracers on static geometry before the terrain-only server does:
measured effect/server endpoints differ by up to551m. Delivery PASS does not
close spatial acceptance. **Native01 is FAIL for the intended world contact.**

Owner report extends this card to initial static obstacle geometry before
acceptance. Original ProjectileMover.__calcTrajectory uses collision mask128;
the accepted drive mesh uses18. Re-export from the same pinned original model
resources with128 and retain each triangle's original mapped material flags.
Do not substitute drive-filtered mesh as projectile geometry. A bounded BVH
must select nearest static/terrain/vehicle contact with native material FX.
Keep original physics pool unchanged. Destruction of map objects/water still
outside scope, static destructible handling explicitly provisional.
Repeat real ground, near/far rock, occluded-tank and live/wreck checks together.
Preserve failed native01 traces and source/geometry receipts.

## Objective and boundaries

Add continuous segment-versus-terrain contact to the same shared Karelia
runtime that already has accepted server physics, aim, ammo, reload, AP damage
and live/wreck effects. The first terrain surface stops the projectile before
a tank behind it can take damage. Deliver the original client's terrain-hit
presentation using a verified #717 method contract. Keep server authority and
the existing vehicle collision path; no client-reported hit is trusted.

The accepted physics pool/config and its hash-pinned exported terrain mesh
are the first source of geometry. Verify coordinates, winding/triangulation,
holes and bounds before wiring it. Record VERIFIED/OBSERVED/INFERRED/UNKNOWN.
Do not invent materials from a height value. The owner correction above adds
initial static rocks/buildings with original projectile flags. Dynamic
destructibles, water, deformation, new shell types and historical server
fidelity remain outside scope. Keep the original
client and canonical service unchanged; only approved local test copies.

## Work

1. Read pinned map export and original client FX contracts independently.
   Define bounded immutable terrain query API, geometry identity and native
   effect representation. No whole-map triangle scan per projectile tick.
2. Add strict hash/size/path/schema/coordinate validation and deterministic
   nearest terrain segment query; preserve original exported geometry.
3. Integrate earliest terrain/vehicle selection in World atomically, including
   the final short flight segment. Explicit tie/under-surface policy; no HP
   mutation or invented penetration result for terrain. Bound trace/history.
4. Encode only verified native callbacks; once-only reliable publication,
   reconnect skips historical effects. Add passive native measurements if
   needed; never manufacture local collisions to satisfy acceptance.
5. Test steep/flat/grazing/vertical/boundary/hole/miss cases, fast traversal,
   terrain-before-tank and tank-before-terrain, no repeated stop/damage/FX,
   malformed bundle limits, rollback and unchanged accepted gameplay paths.
6. Pinned Windows GNU build via server/build.py, applicable Python/layout
   checks, then sequentially launch the two approved clients to avoid the
   known simultaneous-login retry. Real terrain stop/effect and owner manual
   acceptance are required; no merge on required FAIL/NOT_RUN.

## Evidence and rollback

Keep source hashes, parser/query source and input manifests, source evidence,
test/build receipts, original native traces and server segment/contact/stop
facts. Do not publish client assets or credentials. Preserve failed attempts.
After owner acceptance: ordinary --no-ff merge, push, verify remote SHA under
the existing owner workflow. Revert the card merge for source rollback; stop
only receipt-matched test processes, restore their install ledgers and launch
accepted P06L gateway-integrated-world-p06l-05 with its original physics pool
and contact bundle. One next gate is actual native terrain-contact acceptance.
