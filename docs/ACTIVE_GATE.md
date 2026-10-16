# Текущая карточка — 2026-10-16

**P06T — типы снарядов, критические повреждения и пожар**, зависимая ветка
`codex/p06t-mixed-shell-damage` после автоматически проверенного P04M.
Source-bound БК3/current/next, frozen shell и v2writer, явный laboratory
solver/module proxy/fire policy подключены. Focused05:74PASS/0FAIL/0ignored/
buildPASS. Actual World/Trace/geometry/LOS, scene-controls, owner publication,
SQLite/HTTP и client CPython2.7.3 проверены автоматически. Полный final source
gate ещё NOT_RUN. Native/UI/audio NOT_RUN; WT/FV пока source/scheduler-only,
полная карточка не принята. План [P06T](plans/P06T.md),
[факты и ограничения](research/P06T_RUNTIME_CANDIDATE.md).

Full02 runtime483bb2b:1006PASS/5oldignored/buildPASS,634sourcefiles before/after
совпадают. Focused31, Python17+1/old28, finalWeb10/legacyWeb12 PASS.
Pool-01 A109/B26 подготовлен без grants; оба MS1AP14. Normal/qbindings на
проверенный full02 созданы, CLIstartup/stop PASS. Native
NOT_RUN, новые3 admissionfalse. [Реализация и proof](research/P04M_FIVE_PROFILES.md).

P04M сохранён отдельной веткой, nativeNOT_RUN/new3admissionfalse.
Полная постановка и приёмка P06T — пункт 7 в
[IMPLEMENTATION_ORDER](IMPLEMENTATION_ORDER.md). Боевой стенд и команды — в
[DEV_NOTES](DEV_NOTES.md). Состояние проекта — [STATUS](STATUS.md).

Предыдущий план — [P04M](plans/P04M.md), ночное разрешение и утренняя матрица —
[NIGHT_20261016](plans/NIGHT_20261016.md). Продолжать по порядку без ожидания
ручных проверок; сохранять NOT_RUN и отдельные зависимые ветки до приёмки.

STAB-01 принята на runtime `0574ab0`: изоляция ошибки, оба native-возврата и
повторный бой. Факты и ограничения — [исследование STAB-01](research/STAB01_BATTLE_STABILITY.md).
Lab-only временная машина не реализует выбор/резерв машины профиля13.
P08B ветка `codex/p08b-profile13-battle`: writer/Web/client проверки
пройдены, gateway893 PASS/5 ignored и сборка PASS на `5c08ef5`;
Native-fix03: оба ангара с корректным расходом и повторный общий бой подтверждены
владельцем. Реальный crash с active reserve/recovery/оба native ангараAP14 PASS;
owner postrestart/mutation smoke отложен до утра. В main карточка не слита.
Факты и явная test_lab policy — [исследование P08B](research/P08B_PROFILE13_BATTLE.md).

P08C runtime8c96580:919gateway PASS/5ignored/build PASS; дополнительный test-only
e1c1911 targeted1PASS/build. Native/UI/audio/итоги NOT_RUN до утра. Ветка
codex/p08c-battle-lifecycle сохранена, main не изменён.

P05C runtime019ed2f: полный gateway940PASS/5ignored/buildPASS и exact source
before/after602files. Actual mixed2/6 scene/ACK/parked bodies PASS; native mixed
таран/6клиентов NOT_RUN. Ветка codex/p05c-shared-physics сохранена, не main.

P07B runtime8fecb9d:975gatewayPASS/5ignored/buildPASS,607sourcefiles before/after
совпадают; actual terrain/static LOS и packet absence/epoch gates PASS. Native
исчезновение/повторный засвет NOT_RUN; ветка сохранена, не main.
