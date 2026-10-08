# P06B static source audit

## Goal

Turn the original ignored one-off MS-1 AP source check into a bounded,
repeatable gate. The gate binds the exact #717 source files, the four Packed
XML field sets, the `vehicles_russian.pkg` hash and the nine MS-1 collision
members to the existing P06B receipt. It remains a read-only source audit.

## Scope and safety

- Read only `WoT_0.9.1_RU_0717_original` and the existing ignored evidence.
- Reject duplicate/non-finite/oversized JSON before inspecting the receipt.
- Re-decode only bounded Packed XML and package members; never execute client
  bytecode and never derive a penetration or damage formula.
- Keep native hit, penetration, HP/module/crew and server-runtime claims
  `UNKNOWN`/`NOT_RUN`.

## Acceptance

`tools/p06b_source_audit.py` validates the frozen source pins, re-hashes the
original files and package, re-reads the four XML sources, checks each collision
member against the package and local evidence, and verifies the research report
contains every hash and boundary marker. `tests/test_p06b_source_audit.py`
provides synthetic positive and fail-closed parser/receipt cases.

## Rollback

Revert the single card commit and remove the ignored recheck JSON. No client,
server or deployed service state is changed.
