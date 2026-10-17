# P06T — explicit source map configs for extended profile authoring

Branch `codex/p06t-profile-map-source` from tested HEAD
`200dcd221fb48c019b0939046ac38c18a85061dd`. Independent worktree
`C:/wot091-map-source74/w`; the prepared primary checkout and its bindings stay
unchanged. The initial925 runtime files were copied raw-identically and their
filtered Git blobs/index tree equal the parent (receipt in external74 metadata).

## Problem and facts

VERIFIED: `p06t_extended_profiles.generate` pins two historical raw MS-1 map
configs through `MAP_PINS`. The short-C operational closure has intentional
terrain/obstacle path relocation, so its JSON bytes differ. Their remaining
fields equal the original D configs. Selecting that relocated operational
directory for raw source authoring fails the unchanged SHA check. This does not
establish a geometry or runtime regression.

## Scope and implementation

Only `tools/p06t_extended_profiles.py`, `tests/test_p06t_extended_profiles.py`
and this card's documentation. Add keyword-only `map_source=None` after the
existing positional arguments and optional CLI `--map-source`. Absence retains
the exact old `MAP_BASE` recipe. An explicit directory reads only the two fixed
filenames through the existing no-link,16KiB,unchanged `MAP_PINS` validation.
No fallback, path normalization of source JSON, resource loading, source
overwrite, dependency update or native change.

The test context may explicitly set `P06T_EXTENDED_MAP_SOURCE` and pass it to
the argument. It does not alter the default source directory or any raw pin.
Actual authoring reads the two original D configs read-only and publishes to
new strict local C output. It may retain historical D resource references in
the authored config; those outputs are not a newly qualified Jolt scene.

## Checks and acceptance

Run the existing extended-profile suite plus source-selection controls on this
branch, with actual original#717 source and explicit pinned map-source. Verify
both D raw files unchanged before/after and primary200/source925/index unchanged.
Exercise unchanged default argument recipe, wrong source SHA, oversized input,
linked source refusal, missing source and fresh-C-output boundaries. Pin all
evidence and report actual counts/skips. No Cargo, physics process, DB, network,
native client or prepared stand action is required or claimed.

Commit and push only this dependent branch for review. Do not merge into the
prepared primary/main during the overnight source freeze. Rollback: retain or
drop this separate branch; no old source config/cache/stand is rewritten.

Status at plan creation: implementation/tests NOT_RUN. Next: implement the two
bounded argument/test-context changes, then actual focused Python checks.
