# P04K — original Barracks recruitment, free50

Baseline main `32aa2fc2e77e652bc6eccbce5ef404a06711943c`, branch
`codex/p04k-native-barracks-recruitment`. One independently verifiable card
within the owner's continuing complete-crew request. Physical owner input is
deferred until after2026-10-14 09:00 Asia/Yekaterinburg. Actual native callbacks,
wire, database and inspected pixels are mandatory before this card's merge.

## Result and source boundary

Open the original Barracks from the native header, hire new50% tankmen directly
into it through original CMD303, retain native lists/filter/count behavior and
preserve assignments through fresh login. Ordinary skill selection still
requires100% primary qualification; base Sixth Sense remains the owner's
always-active unlearned exception, with actual combat effect still outstanding.
Paid recruitment and berth expansion remain unavailable; no prices are invented.

Read-only #717 sources and ignored research under
`local/evidence/20261013-crew-complete-research-01/` establish the request and
callback: `barracks303-store-contract01/`, `client/barracks-next01/` and
`next-small-card01/`. The complete store proposal is adopted below except where
new source/native evidence requires a documented explicit amendment before use.
Original source auditor must pin exact bytes/methods independently.

CMD303 uses doCmdInt4,24-byte `<hhqiii>` body, layout
`[shopRevision,vehicleTypeCompactDescr,primaryRoleIndex,costIndex]`.
Current exact projected shop is revision3/SHA256
`b55573c5b14fbbc034fbc2091d9e381645926c67e561ab46917ecd3d6965129a`.
Shop revision is independent of account/configuration/wire revisions.
Allowed types3329(MS1 primary commander1/driver3),7169(IS7 commander1/driver3/
gunner4/loader5), cost0 only. Unknown bits/types/roles/nations/costs reject,
without coercing Boolean/float values or treating vehicle inventory IDs as types.
Original callback expects ext.tmanInvID and ext.tmanCompDescr.

## Authoritative contract

Profile12, schema `p04k-native-barracks-recruitment.v1`; new command type
`p04k.recruit_barracks.v1`, route `crew-recruit-barracks`, CLI `recruit-barracks`,
domain operation `recruit_barracks`. Metadata `crew-barracks.json` retains14
primitive fields, command303/transfer105, role_level50, vehicle_count2.
The canonical policy binds exact source audit and shop revision/digest before
native activation. Preserve source audit/policy reproducibility in tests.

Reuse the sole inherited BEGIN IMMEDIATE/CAS/ledger writer and H descriptor /
identity codec. A successful303 allocates the next unused identity once,
creates an unassigned member(-1/None), decrements free quota, advances aggregate,
configuration and connection wire revision. It changes no existing seat,
passport, descriptor, skill, XP, balance, ammo, vehicle or retired provenance.
Lifetime16/free_left=17-nextID remains explicit test_lab policy, not historical
daily behavior. Require one authoritative free berth, quota and allocator bound;
there is no requested target instance and no invented reservation on a vehicle.

Strict request fields remain account_id/native_database_id/command_key/
expected_revision/wire_revision/layout. Exact retry returns the immutable
original result even after transfer/learning/retirement; cross-operation key
collisions reject. Explicit frozen J historical replay is added ahead of I/H/G/F/D.
Retirement journal contract resolution admits only known frozen J or K contracts;
default J behavior and historical bytes must remain exact. No second SQL writer.

For303 alone, bridge reply is existing9 primitives plus tankman_inventory_id
and tankman_descriptor_hex. Success status=recruited, result_code0, ID4..16,
exact50 lowercase hex chars. Rejection uses ID0/empty descriptor and update,
unchanged revisions, existing failure semantics. The response is reconstructed
and validated from immutable before/after ledger data and exact request; no
arbitrary JSON extension or client-serialized object is accepted. All old
operations retain their original nine-field reply.

Delta contains only new tankman compDescr/vehicle and stats.freeTMenLeft with
prevRev/rev; unchanged vehicle crew arrays are omitted. Gateway sends bounded
data-only native Account.update before correlated onCmdResponseExt with exact
two-field ext `{tmanInvID,new descriptor}`. Actual original parse/repack,
callback and wire framing are required, authored encoder examples insufficient.

Migration J11→K12 is explicit and atomic, binds exact predecessor policy/source
and saved base profile/crew provenance, increments shared revision once and
preserves configuration/allocator/quota/member/tombstone/old-ledger bytes.
Version guards close old writers; repeat activation is idempotent, no quota refill.
Shop fixture admission checks actual bytes at projection and gateway loading.

## Native UI and ownership

Keep original header→LOAD_BARRACKS and original list/count/filter construction.
Extend only the explicit unseated RecruitWindow context(currentVehicleId=-1,
slotNone/-1), source-proven selector callbacks and existing free50 choice mask.
The unsupported berth-purchase action must be visibly unavailable via a
source-proven public surface. Freeze that exact surface after pending source
research, before implementation; no guessed Flash fields or new resource patch.

Only this crew worktree, ignored runtime/evidence and owned
`local/clients/p04d-b` are writable. Original
`C:/WoT_0.9.1_RU_0717_original` is read-only. Primary P05 and other stands untouched.
Root owns Rust gateway/web, plan/status, native services and Git. Store agent
owns K projection/store, minimal inherited writer hooks and tests. Client agent
owns K UI/control/install, capabilities and tests. Source agent owns K source
audit, independent native verifier/tests/research and source UI findings.
No concurrent branch switching; no agent launches native services independently.

## Ordered implementation and acceptance

1. Freeze source audit, policy hash, exact UI surface and typed response contract.
2. Implement narrow migration/planner/response hooks; verify all historic replay,
   reservations of existing operations, concurrent303/309 allocation, duplicate
   keys, quota exhaustion, malformed/stale/foreign input and failure rollback.
3. Add strict web/gateway admission and bounded ext encoding; test real bridge
   HTTP/SQLite and update-before-success, malformed/contradictory reply mutants.
4. Compile actual CPython2.7.3, inspect original Barracks/recruit controls, run
   two exact original303 hires and fresh native login. Inspect pixels and verify
   original callbacks, encrypted wire, cache, descriptors and complete DB.
5. Current-source applicable suites, independent verification, installed-source
   bindings, cleanup and rollback all PASS; update evidence/status, ordinary
   no-ff merge/push and remote SHA. Continue the complete-crew objective.

Frozen scenario: immutable accepted J55/config45/quota5/next12,retired3/5,
MS1[4,11],IS7[6,7,8,10,9],9 active/2 barracks. Migration→K56/config45.
Original303 IS7gunner12 `[3,7169,4,0]`, then MS1commander13 `[3,3329,1,0]`.
Final58/config47/quota3/next14,11 active/4 barracks; both seats arrays unchanged.
Original filtering must not corrupt total or barracks counts. Fresh services/
client preserve final DB except operational rate-limit rows and emit no mutations.
Smaller synthetic berth capacity may test its predicate; full16-barracks with
remaining lifetime quota is unreachable and must not be claimed as native coverage.

Evidence: `local/evidence/20261014-p04k-native-barracks-01/`.
Rollback: restore owned install ledger and frozen J database with matching
J source/config; never downgrade a progressed DB by changing only markers.
Revert the accepted K merge with matching database restoration.
Status: PASS_NATIVE_BARRACKS_RECRUITMENT_CURRENT_SOURCE. Native05/06 and
independent wire/persistence/relogin/pixels pass; physical owner input NOT_RUN.
Next step: separate original free first-skill reset/reselection card.

## Frozen source/UI refinement

Canonical source audit SHA256
`ef2239aed04ed2dd29608ee305d2028863f162631454e91388358f579fbcd7c1`;
canonical policy SHA256
`e9a12e9000cc255679d5dad6d744943f325ae1982c5a21060a5996f62c433fd7`.
Original empty-card callback supplies(None,True). Berth-purchase card is a
separate appended row; source-proven public form.tankmenTileList.getRendererAt,
renderer.enabled and descrField.text/price/actionPrice/countField allow visible
unavailability without modifying the native list or inventing a tariff.
The original UNLOCKED selectors use stats.unlocks; the already accepted source
state contains both3329/7169, so no unlock mutation is required.
J evidence-index command transcription is corrected in this card: dismiss19
did not use --activate (that helper permits activation only in preflight).
No J runtime or original evidence is changed by that documentation correction.

## Native01 findings and bounded correction

Actual native01 committed only the first303: revision56→57, new gunner12.
The original Shop callback matched the updated native inventory. Then the
recycled Barracks renderer failed restoration. Preserve that partial DB/trace;
fresh attempts start from immutable K56 with an explicit restore receipt.
The initial progress statement of no mutation was corrected after full review.

The old Barracks inventory parser additionally requires the full vehicle map
`lock`: original requesters/__init__.pyc SHA256
`1e2ab64ad9bc08308fec05f295f4a58a087c8ea970672b9ac6ec2da4b1e055a9`,
InventoryParser.parseVehicles178 uses `data['lock'].get(id,0)`.
Add this original field in K full-state projection for the available owned
vehicles (empty map means original default0). Keep D–J historical projections,
all existing maps, authoritative reservation checks and303 delta unchanged.
This is a source-proven initial synchronization completeness correction;
canonical policy/source audit stays frozen. Bind the supplemental parser audit,
new projection source/tests and final real native run separately.

## Final native acceptance

Native05/06 complete the frozen scenario at revision58/config47/quota3/next14.
Original getData plus current logical input and renderer.index are the accepted
functional readback; raw provider/property divergences remain observations.
Native01–04 failures and reset receipts are preserved. Initial/fresh CMD100
full-state synchronization, exact303 wire/update/callbacks,29 unchanged fresh
login tables,14 inspected PNGs and37 compiled installed modules per run pass.
Six installs restored and18 owned process instances ended. See the evidence
index for commands, current-source test union and explicitly deferred scope.
