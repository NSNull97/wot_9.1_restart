# P09E — source-bound research, purchase and installation

2026-10-13, Asia/Yekaterinburg. Branch `codex/p09e-tank-module-research`.
Accepted base `626867c758c32b189a77a7a7a2fe9ff29837e11b` (P04G).

**Acceptance: SCOPED_AUTOMATIC_PASS / FULL_REGRESSION_INCOMPLETE / OWNER_NATIVE_NOT_RUN.** Required owner
native/UI verification is after **2026-10-14 09:00 Asia/Yekaterinburg**. The card
stays on its branch; it is not accepted or merged into main by automatic tests.

## Goal and actual behavior

Implement the #717 historical tank/module research graph, separate ownership,
purchasing and compatible installation. The explicit versioned `test_lab` policy
zeros XP and credit costs only. Historical prices, per-index XP, prerequisites,
component parameters and gold prices remain in the source catalogue. The server
validates each transition and owns inventory; no unlock-all or client-side grants.

The existing account and `game.sqlite` are reused: explicit profile8-to9 migration,
shared `game_vehicle`, aggregate revision, reservation boundary and command ledger.
Transactions bind authenticated identity, source catalogue, request and revision.
Identical retries survive restart without duplicate purchases. Response generation
occurs before commit, so an unencodable native reply rolls back the operation.

The read-only catalogue contains **374 vehicle types, 2,120 module types and
2,062 indexed research edges**; 290 types pass the ordinary visible credit purchase
filter. A catalogue entry is neither ownership nor evidence of battle readiness.
Seven visible tier-1 roots and their stock modules form the documented project
starting policy. Existing MS-1/IS-7 ownership is preserved; higher-tier ancestors
are not granted. Source three garage slots leave one further purchase available.

## Paths and changed files

Only this managed worktree and its ignored local output were written:
`C:/Users/NSNull/.codex/worktrees/p09e-tank-module-research/WoT_9.1_Server`.
Read-only original: `C:/WoT_0.9.1_RU_0717_original`.
Read-only accepted source bundle:
`C:/Users/NSNull/.codex/worktrees/crew-equipment-snapshot/WoT_9.1_Server/local/p04d/source-bundle-05`.
No client resources were copied into this worktree. Root checkout, live stores,
installations and processes were not modified. Ephemeral loopback HTTP test
servers and isolated SQLite workers belong solely to automatic test runs.

- `tools/p09e_research_catalog.py`, `p09e_source_pins.json`: bounded packed-XML
  import, original unlock order/closure, costs, stock parts, compatibility, masses,
  gun data, hit points and crew roles; 426 original file pins.
- `tools/p09e_research_store.py`: transactional migration/research/purchase/install,
  depot conservation, source assembly validation and durable replay.
- `tools/p09e_native_commands.py`, `p09e_research_projection.py`,
  `p09e_research_service.py`, `p09e_research_harness.py`: original command adapter,
  shop/state/update projection and isolated end-to-end harness. The small hook in
  `tools/p09d_ammo_projection.py` preserves the old default encoder bounds.
- `server/gateway/src/account/research_service.rs` and bounded integration in
  `ammo_service.rs`, `ammo_session.rs`, `crew_transfer.rs`, `hangar.rs`, `identity.rs`,
  `server/gateway/src/{main,session}.rs`: opt-in profile9 transport, shared ordered
  queue, update-before-success and original primitive serialization limits.
- `web/src/{p09e-research,p04d-crew,game-adapter}.mjs`: authenticated loopback route,
  explicit configuration dependencies and public projection of all owned vehicles.
- `client_patch/p09e_research_policy.py`, `hangar_bootstrap.py`,
  `hangar_capabilities.py`, `sr_interactive.py`, `tools/interactive_client.py`:
  reversible XP policy and audited original module callback guard.
- `tools/p09e_native_research_audit.py`, `tests/test_p09e_*.py`,
  `web/tests/p09e-{research,bridge}.test.mjs`, plan/research reports/STATUS: evidence,
  positive cases, malformed input, rollback, concurrency and persistence checks.

## Evidence and reproducible commands

Evidence root E is `local/evidence/20261013-p09e-research-01/` in the owned worktree.
Client bytecode, resources, compiled outputs, private SQLite stores and raw logs
remain ignored local evidence, not tracked source or redistributable content.
The final scoped receipt records actual counts and current source bindings.
`E/final-binding.json` binds the saved card commit, all changed source hashes,
deduplicated passing tests and the still-open full/native gates. It confirms that
the tested source bytes match the committed worktree; it does not replace logs.
Detailed source contracts are in [P09E_NATIVE_SOURCE](../research/P09E_NATIVE_SOURCE.md)
and [P09E_STORE_AND_CLIENT](../research/P09E_STORE_AND_CLIENT.md).

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:WOT091_CONFIG='D:\WoT_9.1_Server\config\project.local.json'
$env:P04D_TEST_BUNDLE='C:\Users\NSNull\.codex\worktrees\crew-equipment-snapshot\WoT_9.1_Server\local\p04d\source-bundle-05'
$env:P09D_TEST_BUNDLE=$env:P04D_TEST_BUNDLE
$env:P04F_TEST_BUNDLE=$env:P04D_TEST_BUNDLE
$env:P04G_TEST_BUNDLE=$env:P04D_TEST_BUNDLE
python -B -X utf8 -m unittest -v tests.test_p09e_research_catalog tests.test_p09e_research_store tests.test_p09e_research_projection tests.test_p09e_native_commands tests.test_p09e_native_research_audit tests.test_p09e_research_policy tests.test_p09e_client_control
node --test --test-concurrency=1 web/tests/p09e-research.test.mjs web/tests/p09e-bridge.test.mjs
python -B -X utf8 tools/p09e_research_harness.py --bundle $env:P04D_TEST_BUNDLE --original C:/WoT_0.9.1_RU_0717_original --out local/evidence/20261013-p09e-research-01/automatic-flow-fresh
python -B -X utf8 server/build.py gateway --test --out local/build/p09e-gateway-fresh
python -B -X utf8 server/check_layout.py --out local/evidence/20261013-p09e-research-01/layout-fresh.json
git diff --check
```

Each output path above must be fresh. The canonical Rust driver uses own C:
build dependencies/target directory; it does not start a gateway service. Exact
commands, additional affected regressions and environment are retained with logs.

| Gate | Evidence under E | Interpretation |
| --- | --- | --- |
| Source catalogue / historical crosscheck | `catalog/run03/` | All 526 health sums, 3,625 module occurrences and 2,062 edges match accepted historical data; no differences |
| Native static contract | `native-source/` | Original code audited without execution; new wire observations remain NOT_RUN |
| Actual SQLite and native-shaped operations | `automatic-flow*/receipt.json` | Research → buy module → install → research next tank → buy → close/reopen/replay; unchanged money |
| Real isolated HTTP bridge | `final-automatic01/node-scoped.log` | New five P09E Node tests PASS; HTTP → Python → same SQLite, identity rejection and restart replay |
| Store/client regression and CPython2.7.3 | `store-client-01/`, `store-journal-02/` | 78 current client/regression tests and23 current store tests PASS; four actual client compilations, not client execution |
| Existing garage regression | `regression01/`, `review05-web-metadata/` |123 Python legacy store/projection tests PASS; recovered13 Node HTTP/catalogue regressions PASS |
| Independent capacity review | `review01/`, `review02/` | Retained initial journal/state limit failures, repaired bounds and exhaustive update sizing |
| Gateway scoped build/tests | `local/build/p09e-gateway-research02/result.json` (outside E), `native-source/gateway-boundary-tests01/` | 11 research tests/build PASS;95 affected account/CLI boundary tests PASS (overlapping sets) |
| Large actual Python fixture → Rust loader | `native-source/gateway-large-fixture02/` | 22385-byte state,22992-byte shop,92-byte dossier; all metadata checks PASS, inputs unchanged |
| Full Rust attempt | `local/build/p09e-gateway-full02/failure.json` (outside E), `native-source/full-rust-failure-classification01.json` |568 PASS /172 FAIL /0 ignored; missing private prerequisites |
| Existing read-only profile4 fixture recovery | `review04-rust-fixtures/` | Five failed prerequisite cases pass through their existing CWD selector;167 still unavailable |
| Owner/native UI, capture, pixels, fresh client login | **NOT_RUN** | Mandatory outstanding acceptance |

The current Python evidence contains **257 distinct passing tests**, deduplicated
by fully qualified unittest identity:123 legacy store/projection tests,23 current
P09E store tests,78 unchanged client/control regressions, and48 final P09E
catalogue/projection/codec/policy/control tests with15 overlapping identities.
No Python skip is counted as a pass. The earlier99-test store/client run includes
21 store tests before the journal repair; those are superseded by the23-test run.

The full Rust result is not a product-code PASS:158 failures reference absent
historical files under the compiled worktree root,9 require pinned physics-worker
fixtures,5 require a portable profile4 bundle. The latter five were rerun using
the module's existing read-only CWD lookup and passed. The other167 cannot use
that selector. No test was disabled, no foreign worker root was substituted and
no client resources were copied to disguise missing prerequisites.

Current Node evidence contains **25 distinct passing tests**, including all five
new P09E tests and13 recovered legacy HTTP/catalogue tests. **16 historical
native-export prerequisites remain skipped/NOT_RUN**, not passes. This is the
declared affected scope, not the full website suite.

The first broadened Node run lacked own npm dependencies; `npm ci --ignore-scripts`
installed the exact existing lockfile under the owned worktree without changing
dependencies. A subsequent broader run recorded12 passing tests,16 skipped
historical native-fixture tests and2 module-load failures for absent generated
web catalogue metadata. The five new P09E tests all passed in that run. Independent
recovery materialized only six existing release-pinned generated JSON catalogues
and a bounded bundle-pinned native descriptor JSON under ignored owned paths;
no original bytecode, client resource files, artwork or executable was copied.
A later13-test run first exposed a missing owned generator config (5PASS/8FAIL).
Providing the existing verified read-only client paths and redirecting artifacts
to owned local storage produced **13/13PASS,0skips** with no product/test edits.
All attempts and metadata/config provenance are in `review05-web-metadata/`.
Neither skipped historical native exports nor new HTTP tests establish actual
client UI compatibility.

Other retained failed attempts include early fixture expectation/import mistakes,
a corrected private-constant reference in a Rust test, and an incorrect test
executable selection that exited with usage before starting any service. Their
scope is recorded in the source reports and raw logs, not hidden as final PASS.

## Knowledge categories and resolved review findings

**VERIFIED:** original file hashes and packed source graph, command wrapper
signatures, descriptor serialization, primitive pickle handling, client cache
`set.update` semantics, exact XP converter code and original module callback.
Catalogue SHA-256 is
`b6baecd204444d1e894253fa6c19c61478993b8ae87c71373633989d3a8ee460`.
Policy SHA-256 is
`46875923affb6bd307ad4d35397880fae1dd16fb1992ae2bfbfed607d132361c`.
Source 128-mm Waffenträger magazine6 and 150-mm magazine4 remain distinct.

**OBSERVED:** isolated automatic SQLite/HTTP/restart behavior on this Windows
worktree, CPython2.7.3 compilation and actual Rust tests. No new native UI session
has been observed. Worker timings on three fresh fixture calls were1.85–1.92s;
these observations are not a latency guarantee on another machine.

**INFERRED:** native method IDs for these specific new wrapper calls until a fresh
capture confirms them; original server elite eligibility is unavailable. Project
elite eligibility means every listed unlock target is researched. The original
client's nonempty-graph `isElite` requires `stats.eliteVehicles`, so full login
and incremental cache updates explicitly publish this server-derived set.

**UNKNOWN:** actual Flash purchase options, research-window interactions, all
visual feedback and method attribution in a new real client session. The ordinary
source GUI uses CMD302 then CMD101. CMD308 has a verified wrapper but no found
GUI caller; supported slot0 is a project subset, not an observed native default.

Independent review reproduced a legitimate large-account journal exceeding the
old256KiB bound and native state exceeding16KiB. Research state/shop now have
explicit32KiB and32,768-node limits; legacy modes retain their bounds. The
conservative all-catalog depot with quantities1,000,000, all unlocks and all
elites fits this limit. Journal repair preserves bounded replay without storing
three duplicate research snapshots. These failures were not reclassified as
successful tests; their reproducers remain under E.

Review also bounded all1,157 reachable research steps,1,196 single-target elite
closures,1,873 vehicle/default closures and917 turret/gun changes. Every update
fits240bytes; largest conservative vehicle/default/elite closure217bytes.

## Limits and rollback

All mutable profile9 vehicles are `battle_admission=false`, including retained
MS-1/IS-7. Neither the full tank catalogue nor module stat changes establish a
working combat runtime. The separately accepted battle profiles are not changed.
Unverified assemblies require a separate future battle card.

Gold, selling, slot expansion, equipment/consumables, fuel-tank replacement and
automatic crew/shell purchase are unavailable. Tank purchase admits flags0 and
crew tariff0 only. Old crew commands retain their MS-1/IS-7 scope and no extra
recruitment grant. Old ammunition support requires the exact original turret/gun
pair; other supported component changes preserve it. Before changing turret or
gun, unload ammunition. New vehicles start without crew or shells.

No preparation/install/client/service deployment was performed. Revert the card
commit to roll back code. A profile9 database cannot be opened with an older writer:
restore its verified pre-migration backup, never drop extension tables by hand.
Retain evidence; do not replace a live database with these isolated fixtures.

**One next step:** after the specified morning time, run the owner native checklist
in [P09E_NATIVE_HANDOFF](../research/P09E_NATIVE_HANDOFF.md) on a separately prepared
stand, capture original requests/updates/UI and persistence, then evaluate acceptance.
