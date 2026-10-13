# P06Q — bounded channel-state rejection diagnostic

## Goal

Capture the bounded decrypted body of a rejected native base frame so the
second-client `channel_state` drop can be mapped to an exact method record.

## Scope

- Add opt-in server logging controlled by `SR_DIAGNOSTIC_CHANNEL_HEX`.
- Log only the rejected frame sequence, length, and at most 1024 body bytes.
- Keep parser behaviour unchanged; do not accept unknown records from the log.
- Run focused gateway tests and one receipt-backed private two-client smoke.
- Stop and restore both owned client installations after the smoke.

## Acceptance boundary

This card diagnoses a transport rejection. It does not claim native tree
visual acceptance, network reconnect acceptance, or owner-controlled manual
input. Any parser change requires a separately described implementation step
after the exact record is identified.

## Measured first-READY fix — 2026-10-13

`treeobserve08` captured both clients rejecting six fixed seven-byte area
requests followed by the owned 33-byte READY compound, before either
`SHARED_READY`. The existing mixed parser covers Driving only; Entities
rejects the entire 75-byte payload as non-multiple-of-seven.

Within the existing P06Q branch, split only the contiguous request prefix and
validate any suffix with `wire::ready`. Stage requests and enqueue the existing
binding before flushing creates to preserve its reliable-window slot. Keep
own-vehicle ACK, announced areas, duplicate rejection and Session rollback.
Cover both slots, both captured area ranges, malformed/foreign/truncated
READY, duplicate/future requests, missing own ACK, retry and backpressure.
Remove the temporary raw-body logger after preserving local evidence: it also
contained the connection token. Build and run a bounded two-client check;
tree acceptance remains separate.
