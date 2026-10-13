# P04B — crew and installed-device configuration snapshot

Date: 2026-10-13. Base: accepted main
`90c7a1d92a67be2acf2d02ab9a5720a377c9f2c8`.
Branch: `codex/p04b-crew-equipment-snapshot`; separate managed worktree.

## Goal and boundary

Validate server-owned MS-1 / IS-7 crew seats and a narrowly source-proven set
of installed optional devices, producing an immutable, versioned configuration
snapshot with deterministic modifiers and provenance. Reuse the existing
bounded resource readers; do not recreate P02 crew grants or P04 content import.
Optional devices are installed equipment, not consumable `ITEM_TYPES.equipment`.

P02 already delivered two native MS-1 tankmen and cached relogin. P03I and
the profile4 adapter do not prove IS-7 crew issuance, installed-device effects,
or this snapshot's runtime integration. No new tankmen are granted here.

## Work

1. Pin #717 source hashes, MS-1/IS-7 seats/roles, optional-device IDs, three
   slots, compatibility and the exact order of any admitted coefficients.
   Record VERIFIED / OBSERVED / INFERRED / UNKNOWN separately.
2. Implement a namespaced domain component and a source-audit tool. Accept
   trusted owner/revision/configuration bindings separately from candidate
   data; reject unknown fields, stale/foreign bindings and unsupported rules.
3. Support only the complete healthy, correctly trained, no-perk crew policy
   justified by sources. Do not invent missing formulas or mass/collision data.
   Return exact rational modifiers, never a guessed final combat characteristic.
4. Test positive MS-1/IS-7 configurations, role/seat/identity mismatches,
   duplicate/foreign devices, unsupported effects, malformed/bounded input,
   immutability and deterministic canonical output. Run source hash checks
   against the configured original read-only and existing regression suites.
5. Update research, evidence index and STATUS. Preserve a verified commit and
   handoff; no main merge/push during the owner's parallel integration.

## Allowed writes and acceptance

Only this worktree: new `server/domain/crew_equipment*`, new namespaced
`tools/crew_equipment*`, `tests/test_crew_equipment*`, this plan/research/index,
and an additive STATUS entry. All generated data under its ignored `local/`.
Main checkout, live DB, native client installations, shared loadout, ammo,
service, gateway, physics and transport are excluded.

`PASS_ISOLATED_CREW_EQUIPMENT_SNAPSHOT` requires genuine automated domain tests,
hash-pinned source verification and no unsupported combination represented as
supported. Native/UI, runtime wiring and live IS-7 grants are NOT_RUN and a
separate integration gate. The consumer must reserve the same account,
vehicle, configuration revision and snapshot digest before battle.

Rollback: revert this card's commit; no live or external data needs rollback.
