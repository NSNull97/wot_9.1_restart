# P03L — integrated physics lane alignment

## Goal

Keep the two-client `legacy091-integrated-lab` profile on the same terrain
coordinates that its map-drive workers simulate. The previous bridge translated
worker X/Z to the old shared-lab lanes after the worker had already settled on
Karelia. That preserved separated client coordinates but moved the vehicles to
different terrain heights; the server then published the original worker Y and
the native clients rendered airborne tanks.

## Scope

- add a bounded, hash-pinned worker spawn override for X/Z only;
- start one worker at each server-owned shared-lab lane coordinate;
- keep worker Y, yaw, pitch, roll, velocity and contacts authoritative;
- retain the existing ordinary map-drive profile and its pool unchanged;
- add offline IPC and bridge tests for the per-lane spawn contract;
- use an isolated physics worker pool for the integrated profile.

No client resources, canonical service, collision/damage rules, penetration,
HP/module/crew damage, or historical-physics claim are part of this card.

## Evidence and acceptance

- Rust gateway tests and C# worker build pass;
- both workers report settled contacts at their requested X/Z coordinates;
- a bounded worker stress run records real displacement, pitch/roll and
  contacts through gas, steering and braking phases;
- integrated gateway logs show per-slot spawn overrides and no X/Z bridge
  correction larger than the worker settle tolerance;
- the startup gate must continue ACK/heartbeat/retry processing while workers
  settle, and defer only the native arena reset until both workers are ready;
- fresh two-client screenshots show tracks on the imported Karelia terrain;
- owner manual physics acceptance remains required for driving over slopes,
  braking pitch, obstacles and long-run stability.

## Rollback

Stop the integrated research stand and launch it with the previous
`gateway-integrated-world-09` build and ordinary `pool.json`. Revert this single
card's source/build harness changes; the canonical service and original client
copies remain untouched.
