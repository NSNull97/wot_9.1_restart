# Текущая карточка — BUILD-TEMP: место для ночных сборок

Ветка `codex/build-temp-cargo-target` от P06T checkpoint4786c2a. На D
осталось0.44GiB, на C64GiB. Явный opt-in `gateway --cargo-temp-target`
создаёт только новые Cargo intermediates в default OS temp другого диска;
проверенный exe экспортируется в свежий обычный D output. Ничего не удаляется.
План [BUILD_TEMP_TARGET](plans/BUILD_TEMP_TARGET.md).11 Python guards PASS;
actual canonical C-target full1188PASS/0FAIL/5oldignored/buildPASS на0e970b7,
713rawsourceexact; actual C→D exe SHA совпал, обе папки сохранены.
Evidence `local/evidence/20261016-build-temp01/source-after.json`/`actual-copy.json`.
Автоматический checkpoint завершён; далее новая P08B composition ветка.
Mainffce8cb и native приёмка не меняются.

## Сохранённый P06T: детонация и потеря БК

Явная задача владельца 2026-10-16: при сносе БК машина гибнет/отрывается башня,
все оставшиеся loaded снаряды теряются. Это правило нашего проекта.
Ветка `codex/p06t-ammo-rack-detonation` от сохранённого P08C checkpoint1e87e1b.
План [P06T_AMMO_RACK_DETONATION](plans/P06T_AMMO_RACK_DETONATION.md).
Runtime ed67531: full1188PASS/0FAIL/5oldignored/buildPASS;712rawsourceexact.
Focused143PASS; writerSQL12+old15/actualHTTP1/Web13PASS0skip. Новый loss-01
source-bound binding-loss01 и actual startup5profiles/DETONATION_BOUND PASS.
Два own UDP→v4RunOpen PASS; copied A129/B43/ammo unchanged/active0;
startup-loss02 службы ownSTOP, native UI/Base attach NOT_RUN.
Native/UI/отрыв башни/ammo-loss NOT_RUN, в main не сливать. Автоматический
checkpoint сохранён; следующая ночная работа — P08B restart/CAS composition.
Факты [P06T_AMMO_RACK_LOSS](research/P06T_AMMO_RACK_LOSS.md).
Новый frozen versioned contract обязателен; старые результаты не пересчитывать.
Mainffce8cb, ночные ветки и предыдущие доказательства сохраняются.

## Сохранённая приёмка natural P08C

Ветка `codex/p08c-natural-results-return`, runtime46d5c20. План
[P08C_NATURAL_RESULTS_RETURN](plans/P08C_NATURAL_RESULTS_RETURN.md).
Owner подтвердил: захват снялся, мышь работает, личные итоги верные, оба
вернулись. Actual arena2975833524010313505: Elimination/B winner, AHP0/BHP90;
B5HE/90damage/1kill/1spot. Оба BattleFinished/result committed/Avatar100/
actual Account1500/acked/natural return/hangar PASS. Dead routed bind A
отработал без reject; faults/idle_timeout0. A126/B41, ammoA[0,0,4]/B[0,3,4],active0.

Canonical full46d5c20:1136PASS/5oldignored/buildPASS/689rawsourceexact;
original64static/Python7PASS. Result-only independent wire9474packets PASS.
Optional autoaim checker03: B2nonzero requests/callback/ACK/ownaim/heartbeat PASS;
A лишь cancel0, nonzero wire coverage NOT_RUN. Owner управление обоих подтверждено.
Полноценный auto-tracking явно недоступен. Checker02 ложная коллизия ACK seq
исправлена только в новом ignored03; оригинальный FAIL сохранён.

Evidence `local/evidence/20261016-p08c-autoaim-acceptance01/acceptance02.json`.
Полная P08C/родительские карточки ещё не приняты: capture/timeout/draw/repeat/
early-leaver fullresult остаются открыты. Mainffce8cb и ночные ветки сохранены.
Own morning-autoaim01 оставлен работающим, оба клиента вернулись в ангары.

Новая явная задача владельца: детонация БК/гибель/башня и правило проекта
«снесли БК — потерял все оставшиеся снаряды». После этого checkpoint — отдельная
зависимая ветка/план P06T; прошлые результаты и расход не переписывать.

## Сохранённый предшествующий core checkpoint

**P06T — типы снарядов, критические повреждения и пожар**, зависимая ветка
`codex/p06t-mixed-shell-damage` после автоматически проверенного P04M.
Source-bound БК3/current/next, frozen shell и v2writer, явный laboratory
solver/module proxy/fire policy подключены. Full02 на dc27285:
1087PASS/0FAIL/5oldignored/buildPASS,681sourcefiles before/after exact.
Actual World/Trace/geometry/LOS, scene-controls, owner publication,
SQLite/HTTP и client CPython2.7.3 проверены автоматически. Mixed-01 actual
startup/5resources и два own UDP→v2run_open PASS, own services остановлены.
После full02 исправлен old-only queue reservation/cancel guard, implicit
cancel при busyJoin и commandbudget: focused09 **90PASS/0ignored/buildPASS**,
включая9 новых actual-writer/native reliable flow regressions. Нужен full03.
Full01 прерван из-за HE+wreck anchor bug, regression PASS в focused07/full02.
Native/UI/audio NOT_RUN; WT/FV пока source/scheduler-only,
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
