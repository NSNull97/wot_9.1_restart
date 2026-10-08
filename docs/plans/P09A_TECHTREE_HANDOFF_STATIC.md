# P09A — static TechTree handoff boundary

Status: **PASS_STATIC_TECHTREE_HANDOFF_SOURCE / native payload NOT_RUN**.

## Goal

Close one read-only seam before the owner-gated native research-tree capture:
record what the inspected #717 `TechTree.pyc` methods do at the Scaleform
boundary. This card does not decode a packet, infer account/shop fields, or
change the gateway.

## Pinned observation

The hash-bound disassembly shows that `requestNationTreeData` populates the
Scaleform available-nations and selected-nation fields, then returns `True`.
`getNationTreeData(nationName)` rejects a name absent from `nations.INDICES`,
selects the corresponding nation index, calls `NationTreeData.load(index)`, and
returns `NationTreeData.dump()`. This identifies the native handoff boundary;
it does not establish the bytes or source of the account/shop data consumed by
`NationTreeData.load`.

## Bounded implementation

`tools/techtree_handoff_audit.py` reads a generated disassembly JSON and the
hash-pinned research-copy `TechTree.pyc`. It verifies method signatures and
instruction subsequences with strict bounded JSON parsing, duplicate-key and
non-finite rejection, path containment and the expected #717 source SHA. It
never executes bytecode or starts a client/service.

The receipt is written only to ignored local evidence. The verifier has
positive and negative tests for the real shape, method mutation, duplicate
JSON keys and path escape.

## Gates left open

The account/shop payload, native callback bytes, rendered tree screenshot,
server correlation, unowned control, stale-payload behavior and IS-7 battle
admission remain **NOT_RUN**. The next manual step is still one bounded
research-copy capture tying the payload, `requestNationTreeData`/`getNationTreeData`
handoff and USSR screen to one account/revision.

## Rollback

Revert this docs/tool/test commit and remove the ignored receipt directory.
No client, fixture, database or deployed service is changed.
