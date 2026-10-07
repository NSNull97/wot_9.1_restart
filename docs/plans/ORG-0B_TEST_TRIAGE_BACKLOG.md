# ORG-0B — unittest triage backlog (created by ORG-0A)

**Update 2026-10-07:** assigned and repaired in
[ORG-0B execution plan](ORG-0B_TEST_REPAIR_20261007.md).
[Verified result](../evidence-index/ORG-0B.md): 2047 tests, no errors/failures,
2 skips; Python 2.7 bytecode check passed separately. Symlink capability remains
NOT_RUN. The baseline findings below are preserved as history.

This is a separate follow-up card. ORG-0A does not change code to make these
tests green and does not reinterpret them as a P03 failure.

Command run:

```powershell
python -B -X utf8 -m unittest discover -s tests -q
```

Observed result: `Ran 2028 tests in 37.112s`; `FAILED (errors=10,
skipped=4)`. Full output is preserved at
`local/evidence/20261007-org-0a-project-hygiene-01/unittest-discover-q.txt`.

## Ten errors to classify

1. `setUpClass (test_account_switch_verifier.CapturedSwitchControls)`
2. `test_frozen_protocol_sources (test_inprocess_relogin_verifier.InprocessWireParserControls.test_frozen_protocol_sources)`
3. `test_owned_wrappers_are_not_reported_as_original_entries (test_interactive_window_trace.WindowTraceTests.test_owned_wrappers_are_not_reported_as_original_entries)`
4. `test_unrelated_native_methods_and_similar_paths_are_not_reported (test_interactive_window_trace.WindowTraceTests.test_unrelated_native_methods_and_similar_paths_are_not_reported)`
5. `test_old_profile_chain_layout_is_rejected (test_profile4_chain.Profile4ChainTests.test_old_profile_chain_layout_is_rejected)`
6. `test_identity_mutation_is_rejected (test_profile4_semantic_diff.Profile4SemanticDiffTests.test_identity_mutation_is_rejected)`
7. `test_is7_mutation_is_rejected (test_profile4_semantic_diff.Profile4SemanticDiffTests.test_is7_mutation_is_rejected)`
8. `test_unexpected_ammo_mapping_mutation_is_rejected (test_profile4_semantic_diff.Profile4SemanticDiffTests.test_unexpected_ammo_mapping_mutation_is_rejected)`
9. `test_unexpected_state_shell_delta_is_rejected (test_profile4_semantic_diff.Profile4SemanticDiffTests.test_unexpected_state_shell_delta_is_rejected)`
10. `test_live_server_rejects_changed_run_pid_configuration_and_exited_process (test_retired_base_probe.ActualSourceRecheckUnitTests.test_live_server_rejects_changed_run_pid_configuration_and_exited_process)`

Verbose repeat was run only to obtain the skip identities. It again ran
2028 tests with 10 errors and 4 skips (35.760s), preserved in
`local/evidence/20261007-org-0a-project-hygiene-01/unittest-discover-v.txt`.

## Four skips recorded by the runner

| Test | Exact reason |
|---|---|
| `test_hangar_relogin_scenario.InputAndContractTests.test_project_input_boundary_compile_only_matches_pin` | `project bytecode must use Python 2.7` |
| `test_ms1_ammo_state.ActualNativeExportTests.setUpClass` | `NOT_RUN: MS1_AMMO_TEST_EXPORT must name actual closed native evidence` |
| `test_project_preferences.PreferencesSafetyTests.test_actual_guarded_write_retains_verified_current` | `SR_TEST_TEMP local directory required` |
| `test_server_layout.LayoutTests.test_linked_entries_are_refused` | `NOT_RUN: this Windows account cannot create symlinks` |

Observed error groups: three old `gateway091.rs` path errors; two undefined
`_control` errors; five uncaught `content_bundle.BundleError` errors in negative
profile tests. Their root causes and repairs are not claimed by ORG-0A.
At backlog creation ORG-0B was not started. The owner subsequently assigned it;
execution uses `codex/org-0b-test-repair` from the accepted main.
