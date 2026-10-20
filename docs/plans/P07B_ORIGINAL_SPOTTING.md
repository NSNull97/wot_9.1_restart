# P07B — original #717 spotting, no camouflage

Isolated card branch `codex/p07b-original-spotting-restart`, based on
`bc5c1c626b453406c8149f7fb6d1937953c1ab20`. The primary P05C checkout and
live stand remain untouched.

## Scope

- Use the permitted #717 client only as a read-only source boundary.
- Keep the six original `visibilityCheckPoints`, two observer declarations and
  the 9.0 dynamic gunner target point distinct from project transforms.
- Use mounted source view ranges; keep maximum distance, proximity shortcut,
  cadence, retention, radio sharing and full-roll server transform as explicit
  policy/UNKNOWN where the source does not establish them.
- Make the server derive recipient-specific interest from authoritative poses
  and geometric LOS. Hidden actors do not enter snapshots, late requests,
  effects, vehicle impacts or results payloads.
- Stage the original Sixth Sense callback with the owner-required always-owned
  commander rule. The candidate callback ID and native UI/audio remain
  owner-gated until a native run.

## Checks

1. Run the bounded static source reader and retain its small receipt.
2. Run pure spotting, actual World/terrain and publication/packet tests.
3. Run the focused `p07b` Rust filter with the pinned Windows GNU toolchain,
   without starting a service, client, port, database or live stand.
4. Commit the implementation and research ledger. Native/two-client/UI/audio
   acceptance remains a separate owner gate.

## Explicit exclusions

Camouflage, bushes as coefficients, equipment, a new skill/economy system,
client patching, bots, public hosting and historical server behavior guessed
from modern WoT/Lesta/Blitz are outside this card.
