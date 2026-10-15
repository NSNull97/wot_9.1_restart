# P09E same-account research writer and explicit native UI policy

2026-10-13, Asia/Yekaterinburg. Implementation in the isolated P09E C: worktree.
No shared database, client installation, root checkout or live process was changed.

## Result and boundary

`tools/p09e_research_store.py` extends the accepted
`NativeCrossVehicleCrewStore` in the same `game.sqlite`. New tank ownership is
written to the existing `game_vehicle`, all commands use the existing
`game_command_ledger`, and research/crew/ammunition share `game_snapshot.revision`.
No additional account registry or independent profile database is created.
Migration is explicit, requires an accepted profile 8, validates the retained
source bundle, verifies the exact MS-1/IS-7 stock descriptors and produces profile 9.
Old writers reject the extended snapshot rather than discarding research state.

The `test_lab.research.free-credit-xp.v1` policy zeros only credit and XP costs.
Historical prices and per-index XP remain in the immutable source catalogue and
command results. Gold transactions, crew creation, equipment, consumables,
fuel-tank replacement, tank selling and slot expansion are unsupported.
Source `stats.slots=3` is retained: the existing two vehicles leave one free slot.

Research requires the parent vehicle to be researched and the exact source
prerequisite closure to be unlocked. Ownership is separate from research.
Purchasing a tank installs its source stock components and creates no crew or
ammunition. Installing a component consumes an owned depot item and returns the
replaced component to the depot. A turret and its selected gun can change in
one transaction. Source compatibility, turret/gun pair and chassis maximum load
are validated against the sum of hull and installed component masses.

The migration retains the accepted account's source unlocks and adds only the
seven visible credit tier-1 research roots with their source defaults. This is
an explicit **project starting policy**, not proof of the original server's new
account grants. It grants no additional tank ownership or higher-tier path;
the previously accepted IS-7 grant is retained without unlocking its ancestors.

Every inventory projection, including new vehicles, has `battle_admission=false`.
Catalogue existence and correct numeric component values do not establish a
working battle profile. Current crew operations retain their accepted MS-1/IS-7
scope. Ammunition service is available only for their exact supported turret/gun
pairs; compatible chassis, engine or radio changes retain that ammunition contract.
Changing either turret or gun requires an empty loaded magazine/loadout. Generic
shell support and crew allocation for newly purchased tanks remain unavailable.

## Transaction and adapter contract

`ResearchStore.execute(request, authenticated_account_id=...)` accepts exactly
`account_id`, `command_key`, `expected_revision`, `operation`, and `payload`.
IDs, counts, component lists and integer types are bounded; booleans do not pass
integer validation. The account is supplied by the authenticated server caller.

| Operation | Payload |
| --- | --- |
| `research` | `vehicle_id`, source `unlock_index` |
| `buy_vehicle` | `vehicle_id` |
| `buy_module` | `module_id`, `count` (1–100) |
| `install`, `buy_equip` | `vehicle_inventory_id`, `modules` (bounded component IDs) |

The native adapter owns compact descriptors and command IDs. The domain writer
does not embed native command numbers in assembly rules. Native response creation
uses a trusted `prepare_response(before_aggregate, after_aggregate, result)` hook
inside the same transaction. `native_binding` hashes the original native request.
Any projection failure rolls back ownership, depot, revision, public profile and
ledger together. Replay verifies the request binding and result hash, recomputes
the original legal transition, and regenerates the original response before
returning `replayed=true`. A retry does not purchase another tank/module.

Review found that the first journal format duplicated research state three times
for native commands. A legitimate completed research graph and growing depot
could therefore exceed the existing 256 KiB JSON limit. Journal
`p09e-research-journal.v2` retains one before-state, the deterministic after-state
hash, and the native aggregate context with research excluded. Replay rebuilds
the transition, checks the after-state hash and regenerates the exact response.
The retained first-format journals remain readable without rewriting history.
The total JSON limit stays 256 KiB; native context is separately bounded to
16 KiB and the prepared native response to 4 KiB.

VERIFIED source-bound stress fixture: all 2,042 reachable researched items,
1,717 purchasable module types at quantity 1,000,000 and the largest third stock
vehicle require 152,879 bytes of research JSON. Selecting the longest compatible
component ID for every owned slot gives a conservative 152,886-byte upper bound
for that fixture, even without asserting that those components form a legal
assembly. The compact native purchase journal is tested below 170,000 bytes;
purchase, restart and deterministic replay succeed inside the unchanged bound.
The saturated quantities are isolated test setup, not a runtime grant API or
evidence of interaction with the actual client. Bound evidence is recorded in
`local/evidence/20261013-p09e-research-01/review02/json-bounds.json`.
Independent verification through the actual service CLI also passed: native
command 302 committed a purchase, a fresh process replayed it without another
mutation, and fixture publication/republication succeeded. That journal was
155,427 bytes and the projected native state 22,385 bytes. Evidence is
`local/evidence/20261013-p09e-research-01/review03/receipt.json`; it explicitly
distinguishes the synthetic saturated starting fixture from actual native UI.

`game_profiles.inventory` contains all owned vehicles with their current modules,
source-derived health, and battle-disabled status. The complete research graph
and module depot live in the aggregate; `game_profiles.research` is a compact
version/policy/catalogue/slot/count summary. This preserves the accepted crew
writer's 16 KiB public-profile reader after research state grows beyond 20 KiB.

## Reversible client entry

`tools/interactive_client.py prepare --enable-research-service` requires an
explicit isolated copy, ammunition service, recruitment, transfer and cross-vehicle
crew flags, with no arena/shared-lab mode. Preparing, installing or launching a
client was **NOT_RUN** in this task; only argument handling and source were tested.
`sr_interactive.py` checks the same dependency chain at runtime.

`hangar_bootstrap.py` installs `p09e_research_policy` before `items.init`, while the
original descriptor converter is still auditable. It restores historical costs
after original GUI disposal. The existing module capability guard allows only
the original audited callback for module types 2, 3, 4, 5 and 7, with bounded
decimal IDs, slot zero, matching old/new component kinds and no removal request.
Equipment, consumables, fuel and malformed selections retain an explicit denial.
Battle and unsupported window guards stay active. The original asynchronous
processor wrapper is called unchanged; the guard does not fabricate a purchase
response or alter Account callbacks.

VERIFIED static source pins, read without executing the client bytecode:

| Original source / code object | Binding |
| --- | --- |
| `res/scripts/client/gui/scaleform/daapi/view/lobby/hangar/ammunitionpanel.pyc` | 11651 bytes; SHA-256 `54d139dd4280314111ce509c15360da8d932cfbc356b30d40c1d9ca96c3addc8` |
| `AmmunitionPanel.setVehicleModule`, line 240, five arguments | Code SHA-256 `02f79342b691d6c512bd441feb8d9239cf820f9044269f9f040f151ad9a09377`; original code converts `newId`/`oldId` using `int` |
| `res/scripts/common/adisp.pyc` | 6035 bytes; SHA-256 `1617360ad43af170406e3a755da38f1e823f219a1579d5730d85729740318f23` |
| `process.wrapper`, line 138 | Code SHA-256 `3814ec7ed28deee153a088aa3def670d9cbce6ecc2bdd286e85165a2f3c9f701`; flags 31; closure `func`, `stepCallback` |

The opt-in runtime audit checks both wrapper and enclosed generator code, source
filename, argument/name/constant shape, and the original `None` step callback.
This static binding is **VERIFIED**; actual Flash invocation/ordering remains
**UNKNOWN / NOT_RUN** until the owner native gate.

## Verification and evidence

Initial evidence directory: `local/evidence/20261013-p09e-research-01/store-client-01/`.
`python.log` captures the store/client suite before the journal capacity fix.
`compile/*.json` binds each
of four compiled client files to its source and compiled hashes, the actual
CPython 2.7.3 executable, and `source_executed=false`.
That scoped run: **99 tests PASS in 101.180 seconds, zero skips** (21 real-source
store tests and 78 client-policy/regression tests). Four actual CPython 2.7.3
compiles PASS; `git diff --check` PASS. The scoped receipt is `receipt.json`.

The journal-fix rerun and receipt are recorded separately in
`local/evidence/20261013-p09e-research-01/store-journal-02/`: **23 store tests
PASS in 99.270 seconds, zero skips**, including capacity, restart/replay and
retained-journal compatibility. The client sources did not change during this
fix; their retained compilation bindings still apply. `git diff --check` PASS.

Commands run from the P09E worktree, with only read access to the accepted fixture
and project configuration:

```powershell
$env:P04D_TEST_BUNDLE='C:\Users\NSNull\.codex\worktrees\crew-equipment-snapshot\WoT_9.1_Server\local\p04d\source-bundle-05'
$env:WOT091_CONFIG='D:\WoT_9.1_Server\config\project.local.json'
python -m unittest tests.test_p09e_research_store tests.test_p09e_client_control tests.test_hangar_capabilities tests.test_hangar_window_capabilities tests.test_battle_capabilities tests.test_p04g_crew_control tests.test_p09e_research_policy -v
# Journal capacity fix, all 23 store tests including retained-journal replay:
python -m unittest tests.test_p09e_research_store -v
$env:PYTHONDONTWRITEBYTECODE='1'
# Repeated for hangar_bootstrap, sr_interactive, hangar_capabilities, p09e_research_policy:
& 'D:/WoT_9.1_Server/local/toolchains/python-2.7.3-x86/python.exe' -B tools/compile_probe27.py --source client_patch/hangar_bootstrap.py --out local/evidence/20261013-p09e-research-01/store-client-01/compile/hangar_bootstrap.pyc --metadata local/evidence/20261013-p09e-research-01/store-client-01/compile/hangar_bootstrap.json
python tools/interactive_client.py prepare --help
git diff --check
```

The real SQLite tests cover migration rollback, wrong prerequisites, zero-cost
source prices, duplicate/replayed purchases, restart, two concurrent connections,
reserved vehicles, module conservation, wrong turret/gun pair, chassis overload,
malformed commands, hidden/gold types, shared crew/ammunition, native projection
failure rollback, and rehashed impossible ledger transitions. Client tests use
isolated callback boundaries and are not native UI evidence. Actual CPython 2.7.3
compilation passed for all four files without executing their source.

Acceptance remains **AUTOMATIC_IMPLEMENTATION / NATIVE_NOT_RUN**. No merge is
authorized by these automatic tests alone. Rollback is to revert this card and
retain evidence; test databases are disposable isolated copies. A later deployed
profile 9 must be restored from its pre-migration backup before an older writer
is used; dropping tables or copying a test database over the live database is not
a rollback procedure.

The next step is the owner's native research/purchase/install/relogin gate after
2026-10-14 09:00 Asia/Yekaterinburg, on a separately prepared explicit research
stand with its own database and client copy.
