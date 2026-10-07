# P03F follow-up — neutral initial turret and gun orientation

Status: PASS_NATIVE_AND_OWNER_NEUTRAL_INITIAL_POSE. Same `codex/p03f-two-client-world` card.
Owner also confirmed remote sound. [Final receipt](../evidence-index/P03F_GUN_POSE.md).
Owner reports visible remote shots on build07, then clarifies that the neighbour's
turret is rotated 180 degrees and its gun appears fully elevated. The screenshots
show different battle times (57:51 and 57:26). The confirmed cause is the zero
packed-angle creation seed, which decodes to `(-pi, minimum pitch)`, not `(0,0)`.
The initial broader dynamic-aim investigation was narrowed after this clarification.

## Scope and plan

1. Preserve build07 shot delivery and owner-visible result in its own checkpoint.
   Keep sound confirmation distinct from visible confirmation.
2. Pin original #717 `decodeGunAngles`, actual equipped MS-1 gun pitch limits,
   creation property index and a correctly encoded neutral `(0,0)` value.
3. Replace only the shared-lab creation seed; add passive native angle readings.
   Preserve frozen older diagnostic contracts and current fire/reload.
4. Check exact native seed and decoded neutral tolerance, run both builds and
   affected tests, install the two manifested copies and launch a fresh stand.
5. Verify real native property/decoded angles in both clients and leave one owner
   check of the neighbour's forward-facing turret and level gun. Dynamic turret
   tracking is still unsupported and is not silently claimed by this seed fix.

Permitted paths: canonical gateway, minimal passive client diagnostics, relevant
tests/docs and `local/` evidence/builds/two manifested client copies. Original
client read-only; deployed service, other research copy and garage data untouched.
No tracer, damage, terrain physics, enemy visibility or deep client adapter.

Evidence: `local/evidence/20261007-p03f-two-client-world-01/aim-01/`.
Prior shot proof: [receipt](../evidence-index/P03F_SHOT_CUE.md).
Rollback: reviewed revert of this follow-up, prior isolated build07, exact
manifested overlay rollback after stopping only receipt-matched processes.
Do not remove local evidence or rewrite prior negative results.
