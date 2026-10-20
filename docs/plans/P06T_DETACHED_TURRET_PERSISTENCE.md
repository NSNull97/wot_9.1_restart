# P06T: persistent detached turret and collision handoff

## Goal

Keep the detached turret as a visible world entity after the ballistic handoff.
It must settle on the authoritative ground sample and retain the native
collision property, including the gun, until the battle avatar is released.

## Scope

- make the flight transition from `Flying` to persistent `Resting` instead of
  expiring after the five-second visual window;
- create the detached entity with collision enabled from the first packet. This
  lets the original client's synchronous detachment confirmation hide the
  parent turret and gives the detached gun its world collider immediately;
- keep its grounded pose and collision property in later publications;
- allow the result/return gate to complete after a settled, acknowledged child
  remains in the shared scene;
- update focused Rust tests and the P06T evidence boundary.

## Checks

Run the focused `ammo_detonation`, `turret_publication`, and detached-turret
server suites, followed by the applicable P06T gateway target. Native visual
collision remains `NOT_RUN` until the next owner-controlled run.

## Rollback

Revert this card's commit. The previous TTL/leave behavior remains available in
the parent commit and no SQL/client resources are changed.
