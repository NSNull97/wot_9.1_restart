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
input. Any parser change requires a separate reviewed change after the exact
record is identified.
