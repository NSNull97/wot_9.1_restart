# P06T — module damage in personal results

Status: `IMPLEMENTED_FOCUSED`, native replay `NOT_RUN`.

The fresh P06T native run completed ammo-bay loss, turret detachment, both
results streams, and return to both hangars. The owner reported that the battle
outcome was correct but the results' module-damage section did not mention the
ammo bay or fuel tank. The server journal already owns these transitions in
`World::device_events`, but the Results8 projection only consumed shots,
contacts, impacts, vehicle damage, splash, and spotting. Consequently
`lifecycle_details::Target.crits` and `Target.fire` stayed at zero while the
participant HP/damage/kills remained correct.

The fix keeps the original packed details schema. A condition-changing device
or crew transition increments `crits`; a fire start increments `fire`. Fire
ticks and repeated unchanged module health do not create duplicate counters;
device condition transitions caused by a fire tick are not counted as a new
critical hit.
The counters are validated (`crits <= 192`, `fire <= 10`) and the normal
cross-ledger validation still applies. No module identity or numeric module HP
is invented in the result packet.

Changed files:

- `server/gateway/src/shared/lifecycle_details.rs`
- `server/gateway/src/shared/lifecycle_result.rs`
- focused detail and wire tests

Focused evidence:

- `local/build/server/gateway-p06t-module-focused03`: 2 passed
- `local/build/server/gateway-p06t-module-focused05`: 1 passed

The current native run log was inspected at
`local/stands/morning-p05c-contact-20261017-05/core-loss4/runs/p05c-contact132-01/gateway.stdout.log`.
Native re-run after integration is required to confirm the original client
renders the non-zero packed counters.
