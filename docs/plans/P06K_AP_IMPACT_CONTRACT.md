# P06K — source-backed AP impact contract

Base: accepted cumulative P06J merge `92ed46e`.
Branch: `codex/p06k-ap-impact-contract`.
Evidence: `local/evidence/20261010-p06k-ap-impact-contract-01/`.

## Objective

Close the next AP-first boundary: establish the actual #717 shell parameters,
angle/distance/ricochet calculation available in the pinned client and the
evidence needed before converting a measured contact into an outcome. Implement
and verify the supported calculation rather than inventing missing historical
server behavior. Distinguish a client predictor from an authoritative damage
resolver. A missing distribution/order/layer rule stays explicit and must not
be turned into an arbitrary penetration or HP change.

## Work and limits

1. Inspect original loader/control flow and relevant native interfaces with
   bounded readers; pin sources. Correlate shell2570, stock gun5892 and P06J
   material records. Record VERIFIED/OBSERVED/INFERRED/UNKNOWN separately.
2. Establish exact formula inputs and ordering where source-backed, including
   angle conventions, distance dependence and limits. Independently review
   raw winding/entry-exit assumptions and special/absent component materials.
3. Build the narrow verified computation and its reproducible source contract.
   If the client exposes an original predictor, measure bounded inputs directly
   in both approved native copies; do not call that server RNG equivalence.
4. Test boundary angles/distances/caliber ratios, zero/absent armor, finite
   values, revisions, reproducibility and rejection of unsupported cases.
   Bind any runtime diagnostic only to the retained nearest server intersection,
   preserving atomic rollback and accepted integrated gameplay/wire.
5. Record the exact native impact-effect callback contract for the subsequent
   outcome event. Do not emit a false penetration/ricochet merely to get sparks.
6. Apply appropriate checks, update STATUS/ACTIVE_GATE/research and save exact
   evidence. Any runtime gameplay/wire change needs its own native/owner gate;
   source/calculation-only acceptance must say what it does not implement.

Approved mutations: project source/tests/docs, new ignored local evidence and,
only if required for measurement, passive observer through isolated a/b install
ledgers. Original client, canonical service, account storage and physics pool
are not mutation targets. No live external-server experiments or modern rules.
Use only pinned isolated build driver, no broad cache recreation.

## Acceptance and rollback

Required: exact source contract; independently checked implementation for the
supported subset; meaningful negative/boundary tests; no fabricated outcome;
required native measurements actually captured; applicable current-head checks.
FAIL/required NOT_RUN leaves the card on its branch. Damage/P06D acceptance
cannot be closed by the narrow calculation alone.

Rollback: revert card merge, restore any passive observer ledger while clients
are closed, use accepted `gateway-integrated-world-p06j-01` with its contact
bundle and accepted `physics-integrated-lane-01/pool.json`.

## Research-driven scope resolution — 2026-10-10

The pinned client contains a nominal marker predictor, not the authoritative
AP solver. Its original method ignores hitAngleCos; the release AP resource
omits normalizationAngle/ricochetAngle and the loader reads those only outside
the release-client branch. This is a finding, not permission to invent values.
P06K therefore implements the exact stock client diagnostic as an isolated pure
module, with original-method native measurements. It does not add a contact
adapter, trace outcome, native effect, RNG draw or HP mutation. Existing terminal
`UnresolvedCollision` remains unchanged. No redundant approximation of angles,
caliber ratios or layer handling is introduced just to satisfy a planned test.

Required narrow-card gates: static source pins, pure-calculation boundaries,
two actual native oracle captures, independent audit and native-derived Rust
fixtures, bounded-input negative tests, pinned build and layout. Historical
AP angle/RNG/layer tests remain UNKNOWN/NOT_RUN for the subsequent resolver;
P06D and owner gameplay acceptance are not closed by this card. The user was
told about this boundary during work. Native callback delivery and rendered
impact effects also remain NOT_RUN.
