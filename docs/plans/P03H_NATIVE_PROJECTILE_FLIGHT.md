# P03H — server-owned projectile flight and native tracers

Status: **PASS_OWNER_P03H_SAME_PC_SERVER_PROJECTILE_NATIVE_TRACER / ACCEPTED**.
The scoped same-PC owner gate is closed; full P03 and the next vehicle-profile
card remain open.
Base: `0273371d7e6ad9ace8e9dda24f43cc1595ac5937` (accepted P03G).
Branch: `codex/p03h-native-projectile-flight`.

## Goal and boundaries

Each accepted stock MS-1 shot creates one bounded server-owned projectile and
the corresponding original tracer in both real #717 clients. The server owns
shot identity, launch pose/velocity, monotonic flight time and termination.
Use pinned original native callbacks and shell data; no client-authored hit,
position or clock becomes authoritative. This is an explicit test_lab profile.

No armor, damage, vehicle/terrain collision acceptance, dispersion RNG,
visibility, economy or warm exit flow is included. Existing allied visibility,
bounded flat movement and approximate nominal aiming limitations persist.
Unsupported collision must be explicit, never faked as an accepted hit.

Allowed: canonical shared/battle domain and wire modules, narrow passive client
diagnostics, tests and documentation; ignored local evidence/builds and the
existing manifested `local/clients/p03f/a` and `b` copies with reversible overlays.
Read-only original #717 and prior research client. Deployed gateway unchanged.
Evidence root: `local/evidence/20261007-p03h-native-projectile-flight-01/`.

## Execution

1. Pin the original start/stop tracer callback signatures and framing, tracer
   lifetime/time semantics, shot descriptor/effects IDs, shot origin geometry,
   velocity/gravity/distance units and prediction interactions. Record facts as
   VERIFIED/OBSERVED/INFERRED/UNKNOWN with hashes and bounded static/native data.
2. Implement one projectile per accepted shot, using server angles and position,
   deterministic monotonic ballistic motion and an explicit finite lifetime/range.
   Preserve ammo/reload atomicity, bounded event history and rejection behavior.
3. Publish native start/termination in order only to ready recipients that know
   the firing vehicle; avoid stale effects on reconnect, clear expired projectiles,
   and do not leak hidden actors through generic broadcast assumptions.
4. Test trajectory, orientation/geometry, time/range bounds, ownership, duplicate
   input, multi-client routing, disconnect/rejoin and transactional publication.
   Build/test canonical and legacy entrypoints, applicable Python checks and
   actual Python 2.7.3 overlays. Native math/delivery must be independently checked.
5. Launch both original clients with the isolated gateway, inspect actual native
   callbacks/trace lifecycle and leave the smallest owner visual test (several
   aimed shots, both windows). **DONE:** both clients received the native
   tracer lifecycle and the owner confirmed that both windows saw the flight.

## Acceptance evidence

- Canonical build: 373 Rust tests PASS; legacy build: 371 Rust tests PASS.
- Full Python discovery: 2,050 tests PASS, 4 known skips; targeted passive
  observer suite: 4 tests PASS.
- Independent audit: 28,410 packets / 28,402 channel frames, 38 starts and
  38 stops for two peer slots, zero errors.
- Native traces: 19 start/stop/add/hide lifecycles per client in
  `local/evidence/20261007-p03h-native-projectile-flight-01/native-02/`.
- Owner receipt: `local/evidence/20261007-p03h-native-projectile-flight-01/owner-acceptance.json`.

The card is accepted only for the bounded same-PC MS-1 test_lab profile. Do
not read this result as hit, damage, historical physics, or IS-7/loadout
support.

Rollback: stop only launch-receipt-matched processes; restore exact overlay
ledgers and accepted P03G source/build. Preserve all evidence. No reset or
force-push. The independent full-P03 two-PC/LAN gate remains NOT_RUN.
