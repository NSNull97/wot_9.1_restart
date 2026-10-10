# P06L — explicit approximate AP outcomes, health and impact delivery

Base: P06K merge `67da292`. Branch: `codex/p06l-ap-test-lab`.
Evidence: `local/evidence/20261010-p06l-ap-resolver-01/`.

## Owner decision and objective

On 2026-10-10 the owner explicitly selected: «Рабочий test_lab:
неподтверждённые правила явно помечать как приближение, затем уточнять».
Implement one working end-to-end stock MS-1/AP hit on the cumulative accepted
physics/aim/ammo/reload runtime. Server contact -> explicit approximate
single-plate outcome -> authoritative HP -> native impact/health callbacks to
both clients. This is not historical_091 fidelity acceptance.

## Contract and boundaries

- Opt-in named `test_lab-ms1-ap-single-plate-v1`, fidelity `approximate`.
  Native server CLI requires explicit `--ap-test-lab` with integrated physics
  and the verified contact bundle. Old modes retain their accepted behavior.
- Source values: stock AP37 mm, nominal power34/27, max720, damage30, HP90.
  Explicit project approximation: straight muzzle-to-contact range, nominal
  power formula extrapolated past500 until720; fixed nominal damage/no RNG;
  homogenization1; AP normalization5 degrees, >=2x factor1.4*caliber/armor;
  >=3x disables ricochet, otherwise incidence>=70 ricochets; equality at
  penetration threshold resists. These choices are versioned, not claimed as
  recovered server code. Old developer statements may support subsets only.
- Supported positive single plate Hull/Turret armor with vehicle factor1 and
  guaranteed material contact. Gun, screens, missing/zero armor and other
  unsupported material cases are explicit no-damage results. No modules,
  crew, HE/APCR/HEAT, projectile terrain, multilayer continuation or external
  post-ricochet flight. Friendly fire explicitly enabled for the two allied
  test actors; no economy or persistence.
- Use server intersection and direction, orientation-independent plane angle;
  do not claim winding is an outward normal. World clone transaction includes
  outcome, health and trace. One outcome per shot. Preserve before/after HP;
  death blocks new movement/aim/fire input, no client authority or HP reset on
  reconnect. Remaining live projectiles may finish.
- Native IDs and codecs stay in wire layer. Packed local hit segment is a
  documented inverse of the observed decoder, validated against native hits;
  original sender rounding remains unknown. Reliable per-peer cursors commit
  with queued output. Reconnect publishes current health without replaying
  old effects. No fake outcome is sent for unsupported contacts.

## Work and acceptance

1. Pin rule/provenance table and expose approximation in logs/receipts.
2. Pure resolver boundary tests: perpendicular/oblique, caliber/angle/threshold
   boundaries, invalid/unknown materials, deterministic repeats, no RNG claim.
3. Integrate health/outcome/trace atomically; rollback errors, once-only damage,
   death/rejoin guards, dropped/retried/late publications and two peer health.
4. Verify native health/effect layouts from #717 defs/decoder, encode bounds,
   component transforms and measured BSP bbox; no original client mutations.
5. Run the single fresh pinned Rust build/test and focused applicable Python
   checks. Launch approved copies with the accepted physics pool and collect
   actual native calls/health. Manual rendered effects/death/physics acceptance
   is required; leave card on branch until owner confirms.

No original client, canonical service, saved accounts/garage, outside games or
other repositories are mutation targets. Agent changes use separate existing
worktrees and disjoint files. Original assets and credentials remain local.

Rollback: stop only receipt-identified test processes; restore isolated-copy
install ledgers; use accepted P06J/P06K code with AP opt-in absent, accepted
P06J contact bundle and physics-integrated-lane-01 pool. Revert card commits
if needed. Required native/owner NOT_RUN leaves this branch unmerged.
