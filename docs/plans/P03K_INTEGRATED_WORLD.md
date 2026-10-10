# P03K — integrated two-client worker-world foundation

## Goal

Provide one manual two-client battle profile that keeps the accepted shared
battle transport, synchronized aim/fire/ammo/tracer path, and the accepted
P05 map-drive worker physics in the same authoritative world. The server owns
each actor pose; worker responses are imported into the shared battle snapshot
and published to both authenticated clients.

## Scope

- add an explicit legacy091-integrated-lab gateway command and launcher path;
- keep legacy091-shared-lab as the flight-only diagnostic profile;
- start one hash-bound P05 worker per actor on the pinned map pool;
- publish worker position, full yaw/pitch/roll and speed through the existing shared entity path;
- preserve the existing server-owned ammo/reload/projectile trace;
- add focused contract tests for worker pose import, two actor ownership and
  fail-closed worker errors;
- no native collision geometry, BSP2 intersection, penetration, HP/module/crew
  damage, historical physics equivalence, or client resource changes.

## Acceptance

- Rust gateway suite and source-layout gate pass;
- integrated command requires explicit pool and capture paths;
- two worker slots are independently owned and their state cannot cross;
- worker X/Z retain the two-client lane offsets, while worker Y, full direction
  and speed replace bounded shared kinematics only in the integrated profile;
  worker Y is published verbatim from the accepted map-drive frame;
- startup does not publish a mixed frame while either worker is still settling;
- worker startup, timeout and malformed state fail the session instead of
  publishing a synthetic pose;
- existing shared-lab and map-drive commands remain behaviorally unchanged.

## Evidence

Store targeted tests, full Rust output, layout output and an isolated build
receipt below local/evidence/20261009-p03k-integrated-world-01/.
Native gameplay capture remains NOT_RUN until the owner manually tests the new
integrated profile.

## Rollback

Revert the single P03K merge commit. Existing canonical service and client
copies are not restarted by the card; the new integrated profile is opt-in
until manual capture.
