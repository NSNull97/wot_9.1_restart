# P05C/P04M follow-up matrix — worker guards

This card prepares the automatic checks that must run before the next native
owner test.  It is based on the P05C/P07B-compatible source tree and keeps the
P04M vehicles source-bound.  It does not change the P07B visibility path, does
not enable a new vehicle for owner admission, and does not claim native/UI
acceptance.

## What is covered

`tools/p05c_followup_matrix.py` describes a bounded matrix for `ms1`, `is7`,
`t26`, `t34`, and `t3485`.  The `pairwise` filter contains all 25 ordered
pairs, while `all` adds one five-actor roster and one six-actor roster with a
duplicate medium profile.  Every case has explicit slots, source profile
paths, a scenario ID, and `worker_result=native=NOT_RUN` until a real worker or
native receipt is attached.

The scenario IDs keep the observed slope and contact problems visible in the
receipt schema:

- straight, powered left/right turn, and braking while turning on flat ground;
- powered turn on an uphill slope in both directions;
- downhill brake/turn;
- low-speed IS-7 push of a parked MS-1 up a slope and release/recovery;
- head-on and oblique contact;
- a stationary-target ram guard.

Profile validation accepts the legacy MS-1/IS-7 handling shape and the
qualified P04M shape.  For T-26/T-34/T-34-85 it requires `battle_admission=false`,
the P04M policy, six support points, finite bounded motion values, and matching
kind identity.  A missing profile produces `NOT_RUN_MISSING_PROFILES`; it never
creates a synthetic profile.

## Guard boundaries

The handling receipt guard checks sequence, finite body telemetry, slope grade,
and wheel-contact count.  It returns `NOT_RUN` for an empty or absent worker
sample.  The implementation intentionally does not turn a guessed speed or
yaw threshold into a pass; terrain/controller quality remains a real worker
gate.

When a worker actually publishes its control channel, two conservative
anti-regression checks are applied: forward input may not produce a sustained
reverse sample beyond 0.2 m/s, and a steer input must produce at least 1°/s of
yaw response.  Missing controls remain `NOT_RUN`; these checks are intended to
catch the observed uphill rollback/dead-steering symptom, not to replace a
vehicle-quality or native acceptance threshold.

The ram receipt guard checks bounded event shape, distinct attacker/victim
slots, one event per impact ID, non-negative impulse/damage, and zero damage
for a resting contact below the relative-speed threshold.  The software-only
P05C implementation now applies the explicit `test_lab-tank-ram-energy-v1`
policy in the authoritative World, records both source-bound health changes,
and re-arms a pair only after a separation frame.  Native/UI/owner damage
presentation remains `NOT_RUN`.

## Actual verification

```powershell
python -B -X utf8 -m py_compile tools/p05c_followup_matrix.py tests/test_p05c_followup_matrix.py
python -B -X utf8 -m unittest discover -s tests -p 'test_p05c_followup_matrix.py' -v
python -B -X utf8 tools/p05c_followup_matrix.py --out local/evidence/20261018-p05c-followup-matrix/definition.json --filter all
```

The checked source-tree run produced `PASS_MATRIX_PROFILE_GUARDS`, 270 bounded
cases (27 rosters × 10 scenarios), and a receipt under
`local/evidence/20261018-p05c-followup-matrix/`.  This is a static source and
matrix gate only: worker physics, native/UI, two-PC, and owner acceptance are
`NOT_RUN`.

Rollback is a revert of this card's commit.  The only next step is to bind the
case IDs to a real IPC7 worker receipt, first preserving the existing
`-1 km/h` slope rollback as a regression fixture, then implement the ram domain
contract and repeat the same filters before any new `battle_admission=true`.
