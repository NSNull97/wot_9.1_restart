# P06Q transport announcement chunking

## Goal

Make the P06Q native shared route carry the full Prohorovka fragile catalog
without exceeding the reliable transport limits.  The catalog has 117 area
chunks, while one reliable body is limited to 512 bytes and the per-session
window holds at most eight pending bodies.

## Scope

- split the shared announcement into bounded reliable bodies;
- stage vehicle and area creation requests and release them as ACKs free window
  capacity;
- keep duplicate and malformed request envelopes atomic;
- add regression coverage for the full 117-chunk session shape.

The native owner gate remains separate: this card proves the server transport
contract and bounded private smoke only.  It does not claim manual client
acceptance.

## Verification

- targeted gateway unit tests for bounded announcement bodies and staged
  creation requests;
- existing shared catalog/session tests;
- bounded private two-client smoke with the 117-chunk manifest, followed by a
  controlled stop and receipt inspection.

## Rollback

Revert the source and documentation commit for this card.  No client files or
external services are modified by the implementation.
