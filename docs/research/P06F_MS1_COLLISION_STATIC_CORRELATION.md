# P06F MS-1 collision static correlation

Дата проверки: 2026-10-09. Источник — только hash-pinned research copy клиента
v.0.9.1 #717 RU. Аудит `tools/p06f_ms1_collision_static_audit.py` прочитал
активный `ms-1.xml` и девять collision members из
`res/packages/vehicles_russian.pkg`.

Подтверждено статически: descriptor links `Hull`, `Turret_01`, `Gun_02`,
observed Packed XML shape, identity visual transform, `Scene Root`, material
kind/armor mapping, finite `xyznuv` vertices, index/group bounds and measured
visual/model/primitive bounds. Mesh sizes are Hull 436 vertices/258 triangles,
Turret_01 311/218 and Gun_02 146/90. Hull and gun bounds match within 1e-4;
Turret_01 retains the observed Y-min mismatch (primitive starts near zero while
visual/model min Y is -0.364419), without an invented transform correction.

Evidence: `local/evidence/20261009-p06f-ms1-collision-static-01/receipt.json`;
status `PASS_STATIC_MS1_COLLISION_CORRELATION`. The descriptor/package/member
SHA-256 values in that receipt are the acceptance pins.

Negative controls cover descriptor/package/member mutation, path and symlink
guards, malformed primitive bytes, non-finite vertices, invalid group ranges,
unknown materials, mismatched bounds, incomplete member sets and missing package
metadata. These controls exercise fail-closed static validation only.

`runtime_axes_status=UNKNOWN`, `bsp2_status=UNKNOWN`,
`native_server_hit_status=NOT_RUN`, and `native_damage_status=NOT_RUN` remain
explicit. No client bytecode, client, gateway, deployed service, collision
solver, projectile trace or gameplay state was executed or changed.
