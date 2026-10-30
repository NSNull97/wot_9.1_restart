# Generated source aim controller and wire bounds

On the isolated integrated synthetic hybrid run, the generated FV215b (183)
reached turret yaw `0.8092823` while its pinned source envelope ends at
`0.7853982` radians. The actual bot step refused the invalid state; the original
FAIL is retained at `E:/WoT091_Hybrid_Validation_20261030/WoT_9.1_Server/local/test-runs/hybrid-late-physics-composition/run-306056-1793371909115308800/phase-a.stderr.log`.

VERIFIED: the generated row has a source yaw envelope, but the two controllers
selected source math only for the closed WT/FV kinds. Use the presence of an
representable source envelope for controller and wire selection, without changing the
`is_extended` policy used for admission, enabling extra vehicles, changing the
wire format or relaxing invalid-state rejection. Legacy kinds have no source
envelope and retain their former controller and wire path.

The existing wire format checks and quantizes basic pitch range before the
source check. Six qualified generated vehicles have sector-dependent pitch
outside that basic range. This change refuses a battle manifest containing any
of those six during resource loading, before that gateway accepts players or
reserves an owner. The aim controller and wire encoder also reject them before mutation;
it does not invent or expand the wire range. Their native wire compatibility,
and native aim/render generally, remain UNKNOWN. A PASS for the 12-profile
synthetic hybrid does not certify all 227 profiles or a real network client.
An owner selection absent from a supplied manifest has not been proven to be
rejected before its writer reservation; do not claim that broader guarantee.

Verification on exact head: generated FV bounds and both controller paths,
invalid state atomicity and wire rejection, legacy and existing extended aim
regressions, and the real HTTP/SQLite + BW/Jolt synthetic hybrid. All tests are
NOT_RUN until executed. No merge/push or real stand/client writes. Roll back by
reverting this isolated change as a whole; it performs no data migration.
