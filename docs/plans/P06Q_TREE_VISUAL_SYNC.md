# P06Q tree visual/state synchronisation follow-up

## Goal

Close the native-gate gap recorded by `manualtree02`: the server publishes
authoritative `fallenTrees`, while the owner reports that the original client
does not visibly fall the contacted trees. Preserve the accepted P06Q server
authority and the original client files.

## Scope

- add bounded observation of the original `AreaDestructibles.set_fallenTrees`
  callback to the owned diagnostic client patch;
- retain the exact cumulative packed `UINT32` values and chunk/entity identity
  in the runtime evidence, without changing gameplay or fabricating a fall;
- use the callback evidence to distinguish a wire-delivery problem from an
  original-client resource/index/rendering problem;
- keep the owner-controlled visual gate separate from automated acceptance;
- prepare a separate server-loss network-drop smoke after the callback probe.

## Verification

- static Python tests for the callback observer and bounded value handling;
- targeted gateway wire tests remain green;
- one owned two-client runtime probe may be used only to observe the callback;
- no original client binary/resource is modified.

## Rollback

Revert the client-patch/plan commit and restore the two installation ledgers.
The observer is diagnostic-only and must not mutate `AreaDestructibles`, tree
matrices, collision bodies, or the server state.
