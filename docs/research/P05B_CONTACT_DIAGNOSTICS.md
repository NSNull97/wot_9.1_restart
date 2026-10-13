# P05B — remaining contact diagnostics and native filter speed

Date:2026-10-14 local. Branch:`codex/p05b-tracked-handling`.
Starting HEAD:`2d662031889a23d40b82759578c47619e9e73b26`.
Plan:[contact diagnostics](../plans/P05B_CONTACT_DIAGNOSTICS.md).
Evidence root E:`local/evidence/20261013-p05b-tracked-handling-01/`.
This is a diagnostic continuation of P05B, not native acceptance or a new
gameplay policy. Candidate14 and its production dependencies remain unchanged.

## Original filter speed: verified static provenance

The bounded original #717 audit identifies RTTI `BW::WGVehicleFilter`, its
destruction-predictor callback and the writer of the three speed components.
Original EXE SHA256:
`86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed`.
All13 saved windows and table/RTTI/constants were independently checked against
that executable; no attach, native execution, network experiment or input.

VERIFIED: caller0x6aa5a0 is slot+0x24 of table0x17d8c88. RTTI locator0x1a718b0
points to type descriptor0x1c4b5c8. Slot+0x20 calls0x7234f0, whose writes at
0x723732/0x72374e/0x72376b update+0x2e4/+0x2e8/+0x2ec. The retained callback
0x6ae4d0 takes the magnitude of this vector. Two sample timestamps and vector
differences feed its update; for positive finite dt the real-number description
is `v_new = v_old + 4*min(dt,0.25)*(delta_vector/dt - v_old)`.
The float instruction order is documented separately, not claimed bit-exact by
this algebra. The complete intervening angular helper does not overwrite the
translation scratch values. Reset clears the same three components.

INFERRED: these vectors are position-history samples, based on layout,
derivative and filter role. Full network-decoder-to-sample provenance remains
UNKNOWN. For dt0.1 and duplicate samples, the algebra retains0.6 of the prior
speed. This is an illustration, not a new native observation or attribution of
the owner's30-to20km/h jerk. The already fixed stale gateway publication and
its real-worker cadence tests remain separate evidence.

The predictor speed is filter-derived on this path. It is not verified contact
point speed, force, accumulated work or an original-server destruction law.
Do not tune authoritative physics to conceal a native filter/network artifact.
Actual arrival timing, executed native branch, UI speed and aim require the
owner's morning run.

Evidence: `night-native-speed01/REPORT.md` and `receipt.json`
SHA`cd114b1ab7ce47ef962fe0dfe0da667e0a5decce66a84489aa45909494ce80a0`;
independent `night-native-speed-review01/receipt.json`
SHA`8ed6882092bf39cbde33c16f22221cfe5e94a46892afe7af26f100ad5c72cb35`.
Commands: `python -B -X utf8 tools/native_pe_probe.py --out <fresh-directory>
--ref 0x6aa5a0`,13 bounded windows specified in the receipt, and
`python -B -X utf8 E/night-native-speed-review01/verify_saved.py`.

## Actual wheel-only fixture: failed full window, preserved observations

The offline survey retained full3904-object/428597-triangle geometry. It found
candidate wheel-only poses using source wheel layouts, actual source speed
caps and valid suspension intervals. It did not count analytical poses as
worker runs or claim a static ray test proves Jolt settling.
`night-wheel-feasibility02/` contains the survey, exclusions and candidate
receipt. Only spawn/yaw changed for the two new actual-worker configs; all1038
catalog objects remained alive, scene0, with unchanged geometry and profiles.

The frozen `night-wheel-diagnostic02/PLAN.md` and `GO_ADDENDUM.md` allowed
exactly four sequential workers: two repeats each of MS-1/IS-7, normal180-tick
settle then30 neutral six-tick advances. No retries or post-hoc shorter gate.
All four exited0 normally, with no forced termination or cleanup error. Every
full repeat was exact. There were no fractures, prepared transitions or scene
changes. These are observations, not a passing energetic wheel-admission gate.

- MS-1: target1501 has actual published wheel-only contacts at advances1–23,
  then hull contacts at24–30. Both30-frame cases are **FAIL**. Neutral drift is
 0.192960m over3s, with six support contacts throughout. Maximum recorded
  wheel-contact linear energy41.9448J and closing0.002845m/s are insufficient
  to isolate the wheel rejection from existing energy/closing predicates.
- IS-7: target783 has no actual wheel or hull contact; both cases are
  **NOT_RUN_WHEEL_ONLY_NOT_EXERCISED**. Settling shifts the origin0.0928m and
  changes yaw0.785398→0.778973. A reconstructed ray misses the chosen triangle
  already at ready. This is an INFERRED explanation, not a native query trace.

The MS-1 reconstructed ray still intersects its triangle after hull publication
starts, consistent with the existing hull-priority contact reducer. A missing
published wheel row therefore does not prove that physical wheel contact ended.
No fixture search, geometry exclusion or retuning followed these four runs.
Energetic wheel-only isolation and the required whole-window control remain
NOT_RUN/failed; neutral no-fracture frames cannot close them.

Raw inputs, outputs, exact owned PIDs and commands:
`night-wheel-diagnostic02/run01/receipt.json`
SHA`1a111ce45b43f75721c51a8fa0669b92f2f46d77df83221da76fd00e31592ae9`.
Offline analysis:`night-wheel-diagnostic02/analysis-receipt.json`
SHA`7f8583f40ab24ba26594f2f48f7e2389ce4b00df8c6893c38c87cbec98986be2`.

## Angular corner hypothesis: actual measurement PASS

Separate earlier-publication estimates suggest sufficient IS-7 angular energy
near first hull contact, but they combine different instants and inferred box
inertia. They do not justify changing admission. `night-angular-feasibility01/`
retains those estimates with their limits.

The frozen `night-angular-diagnostic01/PLAN.md` requires a private instrumented
worker, exact121-response parity against each candidate14 baseline, two repeats
per profile, actual same-time point-velocity/tensor checks, finite bounded
records, and four sequential launches maximum. It may read native body state
but may not change physical state, contact selection or admission. Independent
pre-run review found two missing diagnostic details: other-body identity and
immediate post-Update deferred-fault checking. Both were corrected in private
build02; build01 evidence is retained. Runner review also corrected bounded
stderr, full private artifact pins, deadlines covering blocking stdin writes,
and unique callback/admission pairing. Only reviewed build02/runner03 ran.

Four sequential workers now PASS: two exact repeats per profile, all484 IPC
responses equal their retained candidate14 baselines,11200 diagnostic rows,
2880 pre/post pairs and2718 actual callback/admission pairs. Both diagnostic
repeats are byte-identical. All four children exited0/reaped, stderr empty,
no watchdog expiry, all source/dependency pins unchanged. Actual native
point-velocity and world/principal tensor reconstruction checks PASS.
Independent saved-raw review confirms these results without another launch.

| First actual contact | MS-1 | IS-7 |
|---|---:|---:|
| Advance / substep / tick |7 / 6 / 221|7 / 5 / 220|
| Pre-step COM kinetic energy, J |186.450|19.523|
| Actual callback angular energy, J |1361.890|24744.232|
| Actual manifold0 closing, m/s |0.850016|1.303131|
| Actual manifold0 normal-mode energy, J |492.154|17550.025|
| Selected prepass point closing, m/s |0.850016|1.275545|
| Selected point normal-mode energy, J |492.154|17324.644|

With r=point-COM, h=r cross n and actual world inverse inertia A, the measured
single-contact normal-mode energy is
`max(dot(v + omega cross r,n),0)^2 / (2*(inverse_mass + h^T A h))`.
It is bounded by full body kinetic energy; it is not additional energy to add
to the body, nor a guarantee that ground/other contacts allow all of it to
transfer to one obstacle. Actual and selected IS-7 rows above8000J describe the
same first impact, not two impacts. No cached-only callback rows occur here.

OBSERVED: the current project COM-only ledger rejects this IS-7 contact at
19.523J and selected COM closing0.019541m/s, while the rotating corner has
sufficient normal-mode energy under the existing8000J approximation. MS-1
never exceeds8000J at the recorded actual/selected points in this fixture.
This supports a separately specified angular fallback, not free destruction
under static pressure. Both bodies end essentially stopped; neither has a
remaining kinetic reserve that would justify breaking a fence at rest.

The preserved fixture has1037 removed IDs and one alive fence3167. It is an
isolated test, not a full-map acceptance run. Only manifold point0 and the
selected pair-query point were captured; other candidate points remain
unmeasured. The original-server angular destruction law is UNKNOWN.

Evidence: `night-angular-diagnostic01/receipt.json`, its complete commands in
`REPORT.md`, raw `run-{ms1,is7}-{1,2}/angular.jsonl` and `worker.json`, and
`contact-energy-summary.json`. Private DLL build02 SHA
`e2aadcf80cf6e90ff1ddd21a6db571198c61a83b691267d7470a347571186fac`.
Independent `night-angular-review01/postrun02-receipt.json` SHA
`f20063bdf57a12af2390bb7353aba1648245d1d353e89110efe29ea9c9cd20a8`.
Reviewer failed01 empty-group assumption is retained separately; corrected02
does not require a nonexistent cached subgroup. No worker retry was involved.

Actual commands: `python -B -X utf8 E/night-angular-diagnostic01/replay.py
--kind <ms1|is7> --repeat <1|2>` for each of the four frozen cases, followed by
`summarize_contacts.py`. Static/readback reviews and mathematical limits are
under `night-angular-review01/` and `night-angular-model-review01/`.

## Acceptance and rollback

Only diagnostic/research files are changed by this phase. Canonical worker,
gateway, catalogs, original client and A/B installations remain unchanged.
Existing candidate14 full755 and focused cadence PASS are retained evidence,
not freshly repeated tests. Static pressure, excluded compound coverage,
historical fidelity and native owner acceptance remain OPEN/NOT_RUN.

Stop/reap only exact private worker receipts; no runtime rollback is required
for these measurements. Preserve all failed runs and the unrelated P09B file.
The committed2d66203 morning binding remains historical after any new HEAD;
fresh binding/preflight must be recorded before manual launch.
Next: freeze a separate bounded angular-fence correction plan using these
measurements, then implement and test it without changing the already checked
moving-linear path. No automatic native driving or merge.
