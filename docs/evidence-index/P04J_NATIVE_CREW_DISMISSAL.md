# P04J — native dismissal and sparse persistent crew

Status: **PASS_NATIVE_DISMISSAL_SPARSE_CREW_CURRENT_SOURCE**. Branch
`codex/p04j-native-crew-dismissal`, baseline main
`a5ca87e8c9e149051f2065046361e81269677cd6`. Tested no-ff integration receipts are under `acceptance-final/`; no whole-crew acceptance.
Owner manual tests remain after09:00 on2026-10-14 Asia/Yekaterinburg.

## Goal and implemented boundaries

Enable original CMD306 confirmation for a learned barracks member and a seated
50% recruit, followed by hiring and retained transfers. The same authoritative
SQLite writer preserves historical receipts, uses sparse active identities and
immutable retired-member provenance, never reuses an ID and never refunds the
test quota on dismissal. Ordinary learning still requires100% primary
qualification; Sixth Sense remains the owner's unlearned base exception.

The frozen six-command oracle starts J49/config39 and ends55/config45,
retired3/5, newdriver11, MS1[4,11], IS7[6,7,8,10,9], quota5, nextID12.
The immutable pre-run expectation matches actual native19 and fresh-login20 exactly.

## Files and evidence

Changed components: J source audit, projection, store and independent verifier;
narrow inherited writer hooks; gateway dismissal dispatch/configuration/FIFO;
web authenticated route and sparse overview; client original-dialog compatibility
and opt-in install/control; associated tests, plan and research documentation.
The measured authentication prerequisite also changes pending-attempt equality
in session.rs and synchronizes its shared/server.rs consumer. No shared physics
or deployed primary P05 state changed.

Ignored evidence base:
`local/evidence/20261013-p04j-native-dismissal-01/`.

| Gate | Actual final result | Evidence |
|---|---|---|
| Sparse writer and historical replay |621 distinct PASS; four final installer-binding checks PASS|`store/final-receipt02.json`, `store/binding-recheck03.json`, `store/cli01/receipt.json`|
| Rust suite / isolated gateway |744 PASS, current source and executable bound|`rust/receipt03.json`, `local/build/server/gateway-p04j03/result.json`|
| Web suite |106 PASS, no failures/skips; executable closure independently bound|`web/full-web05.json`, `web/full-web05-binding02.json`, `store/web-source-closure-review01.json`|
| Client Python / actual CPython2.7.3 |439+42 PASS;13 compile checks and Unicode execution PASS|`client/run-09/receipt.json`|
| Independent source/native verifier |82 PASS;18 adverse independent checks PASS|`independent-native/unit07/receipt.json`, `store/full-verifier-review07.json`|
| Applicable Python union |1176 collected:1175 PASS and one existing Windows symlink NOT_RUN; collection is not a new rerun|`python-test-union-final01.json`, `acceptance-final/layout-count-correction01.json`|
| Layout and whitespace |96 source files /22 relocations;7 checks PASS, one symlink permission skip; diff PASS|`layout-final02.json`, `layout-tests-final02.log`, `diff-final02.log`|
| Original confirmation and cancellations |PASS, current18 source,27 tables unchanged|`independent-native/preflight18-final03/receipt.json`|
| Six mutations and fresh native login |PASS exact wire, original callbacks, persistence, descriptors and inspected pixels|`independent-native/final01/receipt.json`|
| Owned installation/process cleanup |20 restores PASS;60 original process instances ended; ports/control clear|`native-cleanup-final01.json`|
| Physical owner input |NOT_RUN|Owner's deferred morning gate|

Final independent native receipt SHA256:
`5702396068316b88461b7d16e0595f4ab8eb68890a0004ccb12a47ab3ed640c1`.
Native19 client9180 and native20 client31988 exit0. Wire requests226..231 are
306/306/309/105/105/105; inventory deltas113/112/166/104/99/97 bytes precede
their correlated success. J49→55/config39→45, quota6→5, next11→12;
all balances, ammunition and surviving identities/skills stay unchanged.

Actual mandatory images were inspected by root: five preflight18, nine
scenario19 and two relogin20. Three additional scenario hire/transfer/unload
images were also inspected. Independent verification binds all18 scenario
PNGs and two relogin PNGs; hashing is not substituted for visual inspection.
Use `native-run20/root-pixels-corrected.json`: the IS-7 is fully crewed but
retains its expected incomplete-ammunition warning, not a battle-ready claim.
The earlier ambiguous pixel wording is preserved and superseded explicitly.

Web full05 used a test-only inherited NODE_OPTIONS observer to retain bounded
stderr of failed real Python workers. It did not change inputs, deadlines,
outputs, retries or dispatch; no failed worker diagnostics were emitted.
The broad source enumeration included a concurrently edited standalone native
verifier which the web suite does not import or execute; that exclusion is
explicit in binding02 and the independent46-module/44-Python-worker closure review. Earlier transient worker failures remain preserved with
cause UNKNOWN; they are not silently reclassified as passing runs.

## Preserved native failures and prerequisite repair

Native01 timed out after an original event swallowed/truncated a diagnostic
exception. Native02/03 exited normally with public Flash model readback null;
03 verified the patched Application bytes through ResMgr. Native04 failed
before reaching the crew UI: a pending login retry was rejected as identity_busy.
Only its own identified client was stopped; `owned-stop.json` records this.

Independent in-memory decryption of OWNED04 packets proved identical complete
plaintext, key, nonce, credentials and digest, but new randomized RSA ciphertext
and request ID. No secrets or secret hashes were emitted. Pending equality now
uses exact bounded fields with a per-job random salt, retaining key/nonce/peer,
real worker authentication and post-auth UUID/retirement guards. A regression
uses actual randomized RSA encryption/decryption, and tests changed credentials,
field boundaries, digest, key, nonce, peer and a real worker rejection.

Native05 used a bounded one-request loopback latency fixture which forwarded
the actual bridge result unchanged after1.4 seconds. The real client sent two
retries; the gateway accepted them as pending duplicates and entered Account.
The original reply request ID was retained. The proxy exited and gateway config
was restored to its normal endpoint. Independent final auth receipt is separate
from crew UI acceptance. UI05 still reported null model and exited normally.

Subsequent source investigation identified the registered child movie
`dismissTankmanDialog.swf` and its own duplicate class definitions. Reading
Application.swf through ResMgr did not prove the actual dialog used that class.
The resulting child-only hypothesis was tested in06/07/08 and subsequently
superseded by measured Application ownership in09/10/11 below. Registration
alone does not determine class ownership in the shared ApplicationDomain.

Native06/07 loaded the exact patched child movie but the original Python
populate callback received `PyGFxValue - Failed to invoke method as_tankMan.`
The compiler-shaped coerce instruction added for07 did not fix the failure.
The bounded failure readback and inspected07 PNG show original window chrome,
buttons and input, with model null and empty portrait/name/question. The
original exception was preserved/rethrown; both clients exited normally. This
is a failed initialization experiment, not a confirmed type-conversion cause.

Native08 was explicitly DIAGNOSTIC_ONLY: the registered child's entire setter
was replaced with a source-bound returnvoid/NOP body, with all metadata and
other bytes unchanged. Invocation still failed before any model-sent event.
The owned installation was restored and27 tables remained unchanged. Original
LoaderManager creates a LoaderContext using the current ApplicationDomain;
both resources define the same qualified classes. At that point ownership was
still unproven. Neither no-op diagnostic is eligible for product acceptance.

Native09 Application-only returnvoid returns without the former exception.
Native10's one-method argument marker reads `[object Object]` in the original
question field. Native11 restores the exact original Application v2 candidate
with an unmodified child resource: primitive fields and inspected PNG contain
the actual member's name, portrait,100% and Repair0, with protected input and
disabled submit. The typed Python getter nevertheless returnsNone. The old
diagnostic stopped prematurely and is not a completed confirmation scenario;
its replacement must verify actual rendered primitives and unchanged original
InputChecker/button behavior, explicitly declaring typed readback unavailable.
The final production transformation is Application v2 only, with the original
child resource; diagnostic no-op/marker modes have been removed from the tool.

Native12 passes original rendered widget checks but correct text0 does not
enable submit in that same-tick scripted sequence. Native13 measures both
original Meta setters receiving string `0` with DAAPI ready. Their immediate
Flash readback remains empty, while a later frame correctly reads `0`.
The actual original window focuses the submit button; the input focus is0,
and the conservative diagnostic exits before emitting any key event.
The verified public UIComponent.focused setter is the next normal input route;
it changes focus, not control values or validation. Actual original native
sendUserInput callback and button state remain mandatory. Wrong100 must reject,
correct0 must enable; Python must not supply the validation Boolean.
Native14 proves delayed focus1 but stops before key dispatch because the
diagnostic used absent Keys.KEY_LEFT. Native15 fixes the exact source symbol
to KEY_LEFTARROW. Actual engine constants are203 and28 for left/return;
the original source's37/13 mapping belongs to a different Flash key layer.
Both real key down/up events are handled. Original sendUserInput reports false
for100 and true for0, with no Python-supplied validation Boolean. The later
combined button/validation-state assertion still fails; its individual values
were not recorded in15. A separate bounded observation of the original
as_invalidUserTextS setter and both fields is required before diagnosing why.
Despite its misleading name, original isInvalidUserText stores the acceptance
Boolean without inversion; source explicitly enables the button on true.
All fifteen owned installs are restored;27 tables are unchanged per run.

## Final native resolution and preserved limits

Post-integration count correction during K: the final layout log already says
`OK (skipped=1)`. The union collector counted that discovered case as executed
PASS. Correct aggregate is1175 PASS/1 platform NOT_RUN, not1176 PASS. The
immutable old receipt is retained and explicitly superseded on this count by
`acceptance-final/layout-count-correction01.json`. The skipped pre-existing
symlink-permission case is separate from the passing layout checker and from
every mandatory J native/writer/protocol gate; no runtime gate is waived.

Native16 observes original accepted callback/Meta true and white enabled pixels
while reflected public Boolean getters stay false. Raw observations are kept
under `raw_boolean_observations`, with explicit unavailable effective-state
readback; no value is overwritten. The underlying engine behavior is UNKNOWN.
Native17 passes the revised preflight, then actual sr.record routing review
finds a missing confirmation-button event. That production integration is
fixed and tested through the actual router; native18 repeats on current source.

The original input receives public focus, then source-bound engine key events.
Wrong100 triggers original invalid callback and Enter emits no button/CMD306.
Correct0 triggers original accepted callback; actual native Enter reaches the
original button callback and CMD306. Python does not submit or supply a
validation Boolean. The final resource transformation changes one measured
Application.swf model-construction prefix, preserving the complete confirmation
suffix and the original child movie. Full source details and earlier failed
experiments are in the [research report](../research/P04J_NATIVE_CREW_DISMISSAL.md).

Verifier unit06 passed its tests but independent mutants found three oracle
gaps; final unit07 closes checker attribution and exact numeric engine Return
checks, including legitimate asynchronous callback ordering. Preflight final02
failed while19 was installed; final03 passes after all actual restores. These
failed receipts remain immutable. The initial cleanup PID-only check found an
old PID reused by a later unrelated node_repl.exe; exact path/start-time audit
resolved this without terminating it. A date-conversion error in that audit
helper and a test-ID collection import-path error were corrected before final
receipts; neither changed runtime or converted a failed run to PASS.

## Commands, limits and rollback

Executed commands include (exact native verifier arguments are in research):

```powershell
python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-p04j03
python -B -X utf8 local/p04j/run-web.py --run 05 --full
python -B -X utf8 local/evidence/20261013-p04j-native-dismissal-01/client/run_checks.py run-09
python -B -X utf8 local/p04j/prepare-native.py --run 19 --mode dismiss
pwsh -NoProfile -File local/p04j/services.ps1 -Action start -Run 19
python -B -X utf8 local/p04d/run-native.py --install local/evidence/20261013-p04j-native-dismissal-01/native-install19 --out local/evidence/20261013-p04j-native-dismissal-01/native-run19
python -B -X utf8 tools/interactive_client.py rollback --out local/evidence/20261013-p04j-native-dismissal-01/native-install19
pwsh -NoProfile -File local/p04j/services.ps1 -Action stop -Run 19
python -B -X utf8 local/p04j/final-checks.py
pwsh -NoProfile -File local/p04j/check-cleanup.ps1
```

Exact environments, original outcomes and latency fixture are in receipts.
Reproduction needs new evidence names and an isolated frozen starting DB;
do not replay positive mutations against the progressed final database.
Historical numeric tariff rows and daily quota remain UNKNOWN; lifetime16
is explicitly test_lab. Full XP awards/progression, retraining/reset, paid
recruitment, personalization, remaining barracks/bulk operations and combat
perks are not accepted by this card. Static future research under
`local/evidence/20261013-crew-complete-research-01/` is not runtime proof.

Rollback restores the owned install from its ledger and the immutable pre-J
database with matching I source/config. Never downgrade a progressed database
or resurrect retired IDs in place. Revert the accepted J merge with
`git revert -m 1 <J-main-merge>` plus matching DB restoration. Original client
and primary P05 remain untouched.

One next step: original Barracks recruitment through CMD303 under the accepted
free50 policy, retaining native filters/counts and durable sparse allocation.
The complete-crew request continues.
