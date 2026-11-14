# CONTENT-0 5a — project assisted-damage policy

## Source boundary

- **VERIFIED (static #717):** the native result schema has separate
  `damageAssistedRadio` and `damageAssistedTrack` fields; see
  `docs/research/BATTLE_UI.md` and `server/gateway/src/shared/lifecycle_details.rs`.
- **VERIFIED (era source):** the official [8.9 release notes](https://worldoftanks.asia/en/content/docs/release_notes/89/)
  describe the result-screen terminology change from spotting damage to
  assistance. The [2013 spotting guide](https://worldoftanks.com/en/news/history/The_Chieftains_Guide_Concentration_Spotting/)
  describes helping allied fire through spotting and shared experience.
- **UNKNOWN:** the 0.9.1 server's exact multi-spotter damage attribution,
  rounding, spotting/track overlap, direct-shooter exclusion, disconnect,
  retention, and ramming-assist rules. Neither cited source establishes them.

## Versioned project calibration

`content0.s5a.assist-direct-shared-hp.v1` is a project rule, not a claim of
historical equivalence. At each committed HP loss, the authoritative damage
record stores both the latest direct-observation mask and the current destroyed
track authors. The scan is eligible only when its derived battle tick is not in
the future and is at most two 100 ms ticks old. This is a bounded project
freshness limit; it does not change the visibility scan or team retention.
For a penetrating hit that also kills the last crew member, direct sight is
captured before that hit resolves; track authors are captured at the HP event,
after any track transitions produced during that hit.

The direct mask includes only actors on the damage author's team that are alive,
ready, connected and directly observing the target, as of the last committed
scan, further filtered by their actual state at the HP transition. A
team-shared or retained-only row does not create a spotter. If the damage author
is in the direct mask, no spotting contributors are awarded for that HP loss.
The author never assists their own damage. Enemy-on-ally and zero loss earn no
assist. The target must be alive immediately before the transition; a lethal
transition still awards its helpers. No client coordinate or client-reported
hit participates.

For one HP loss, eligible spotters and recorded downed-track authors form one
set; one helper present in both sets is classified as track. Distribute the
actual lost integer HP equally, then assign the remainder one HP at a time in
ascending server slot order. Zero allocations are omitted. The total of all
spot+track awards is exactly the lost HP when the set is nonempty. The mask and
track authors are frozen with the HP event, so a later spot, loss, repair, death
or disconnect cannot rewrite prior credits. Damage to an enemy by shell/fire or
ram uses this same policy; if both vehicles are hurt in one ram contact, both
directional masks are captured before either HP changes. Ram physics is not
changed. Pre-P07B routes without an observation state retain the former lab
policy; no historical equivalence is implied.
Track authors remain eligible even if they died or disconnected before the HP
loss: this explicitly preserves the existing project track policy. The original
server's treatment is UNKNOWN. This exception does not make dead or disconnected
actors eligible as direct spotters.

The project battle-feed events and battle totals use the same per-harm credits;
the result projector maps those credits to native radio/track details and ledger
rows. The ledger's existing `project.ui04.battle-ledger.v1` identifies the
presentation schema, not this separate assist calculation policy.

## Verification and limits

Working directory `C:/WoT091_Content0_S5a`:

```
& ./local/run-s5a-camouflage-tests.ps1 content0_s5a_
& ./local/run-s5a-camouflage-tests.ps1 ui03_assist
& ./local/run-s5a-camouflage-tests.ps1 ui06_
```

`local/evidence/20261114-s5a-foliage-rust-01/assist-tests06.log`: 13 PASS,
including staged direct mask, actual HP transition, BW event round-trip,
simultaneous lethal ram in both directions, zero/allied ram, 101 HP allocation,
track priority, result ledger/details, and server-only bot preconditions.
`assist-legacy-regression02.log`: 3 PASS; `assist-team-score.log`: 16 PASS.
These are authored server tests, not a native-client or full-battle acceptance.
The first spotting award (`result_spots`) remains a separate existing policy.
Six-client native assist, replay across a real worker restart, and historical
agreement are **NOT_RUN/UNKNOWN**. Full gate and later changes to the shared
working tree require their own current-head verification.
