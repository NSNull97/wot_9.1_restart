# P06J — measured contact materials, before damage

Base: accepted cumulative P06I `b4ddd02`, cleanup `e238ffb`.
Branch: `codex/p06j-contact-materials`.

## Goal and scope

Bind the nearest server-computed MS-1 contact to the actual #717 component
material record: native material kind, descriptor armor value and explicitly
verified loader defaults/overrides. Keep component identity, triangle/query,
raw winding normal and source provenance. The result describes a contacted
surface; it is not a penetration, ricochet, screen traversal or HP verdict.

Use only configured research resources and approved isolated a/b client copies.
Original client, canonical service, account data and modern 1.45 data are outside
the mutation scope. Accepted physics/aim/RMB/ammo/reload/tracer behavior remains
the cumulative runtime baseline. Retain old bundle/export for rollback.

## Work

1. Independently audit #717 material loader, common defaults and active MS-1
   overrides. Separate static VERIFIED from OBSERVED effective native values;
   preserve missing fields rather than inventing defaults.
2. Capture a bounded read-only effective-material oracle from both actual clients
   using the accepted runtime. No gameplay properties or damage are changed.
3. Export a versioned hash-pinned material binding with the measured geometry;
   validate every referenced triangle/group/material before battle startup.
4. Add one typed nearest-contact classification to the atomic trace/world update,
   binding it to the exact retained intersection and immutable material catalog.
   Unknown/mismatched records fail closed; zero armor and factor0 are explicit
   source facts, not automatic damage outcomes. Terminal stays unresolved.
5. Test importer mutations/path limits, material/component coverage, trace order,
   duplicate/replayed classification, rollback and full-ammunition bounds.
   Independently compare computed classifications against native material data
   and the preserved accepted native01 contacts.
6. Build through pinned driver, check layout and record exact evidence. If changes
   remain source/diagnostic metadata only with unchanged gameplay/wire output,
   owner visual acceptance from P06I remains applicable; no fictitious new manual
   PASS. Any gameplay or wire behavior change requires a new real-client check.

## Acceptance

- Complete component-specific material coverage of the pinned mesh.
- Independent effective native material observation agrees with the export.
- No arbitrary material/normal/armor input can replace the retained nearest hit.
- Classification order/capacity/replay and world rollback tests PASS.
- Full pinned gateway suite, focused Python suite and source layout PASS.
- Existing captured contacts classified with source/material revision and no
  damage application. Native tracer endpoints/gameplay unchanged by this step.

Required FAIL/NOT_RUN leaves the card on its branch. P06D complete
classification/outcome/replay/damage acceptance is not silently closed.

## Evidence and rollback

Fresh evidence: `local/evidence/20261010-p06j-contact-materials-01/`.
Keep capture bounded and stop own diagnostic processes after the oracle is
recorded. Preserve EXE/test receipts after build; disposable intermediates can
be cleaned only after checks using a verified exact-path manifest.
Rollback: revert the card merge; restore the passive observer through its
install ledger on closed isolated copies; run accepted P06I gateway03 with its
original v1 bundle and accepted physics pool. No canonical deployment here.
