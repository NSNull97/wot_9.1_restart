# P06Q native tree fall path diagnostic

## Goal

Locate the remaining native visual tree-fall failure after the gateway has
published the original packed `fallenTrees` values and the client has entered
`AreaDestructibles.set_fallenTrees`.

## Scope

- observe the original `AreaDestructibles` methods `__destroyDestructible`,
  `__dropDestructible`, and `__launchFallEffect` with bounded scalar arguments;
- preserve the existing read-only observer contract; do not replace methods,
  synthesize animation, or mutate client/resource state;
- use the existing owned diagnostic trace to distinguish missing descriptors,
  wrong native index/packed data, and animator/effect path gaps;
- keep the owner-controlled two-client visual gate separate from automated
  acceptance.

## Verification

- static observer regression tests and Python compilation;
- inspect the existing `treeobserve05` trace and, if needed, run one bounded
  private diagnostic smoke; no native owner input is automated.

## Rollback

Revert the diagnostic observer and this plan. Restore any temporary diagnostic
installation ledgers; no original client binary or resource is changed.
