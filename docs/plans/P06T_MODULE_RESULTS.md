# P06T module counters in personal results

## Goal

Carry committed module and fire transitions into the existing #717
`VehicleInteractionDetails` packed details so the native results screen can
show critical module damage and fire counts. This card does not change damage
authority, module HP, ammo loss, turret detachment, or native audio.

## Root cause

`lifecycle_result::project_details` projected shots, contacts, impacts, damage,
splash, and spotting, but ignored `World::device_events`. `Target::crits` and
`Target::fire` were therefore always zero in Results8 packed details. The
results DTO still had correct HP, damage, and kill totals, which explains why
the owner saw the battle outcome while the module section stayed empty.

## Change

Project condition-changing device/crew transitions as `crits` and fire-start
transitions as `fire`, while retaining the source `extra_index` (AmmoBay=27) in
the typed pre-pack fact. The packed contract remains the original 24-byte target
row; module names and HP are not added. Counters are bounded and validated.

## Verification

Focused Rust tests only; native is intentionally not run for this card.

```text
gateway-p06t-module-focused03: 2 passed, 0 failed
gateway-p06t-module-focused05: 1 passed, 0 failed
```

The canonical full gate and the linked native P06T run remain external evidence
and must be repeated on the successor after this branch is integrated.
