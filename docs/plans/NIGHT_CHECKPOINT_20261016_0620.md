# Ночной checkpoint — 2026-10-16, 06:20+05

Продолжает0610. Root D:/WoT_9.1_Server, branch
codex/p06t-mixed-shell-damage, HEADdc27285be170e57ff12ad78babce8f5e589d3f93.
Main/originffce8cb unchanged. Owner разрешил ночью без ручных вопросов;
native/UI/audio NOT_RUN, непринятые карточки не main.

## Завершено после0610

Full02 **1087PASS/0FAIL/5oldignored/buildPASS**,328.88с tests, executableSHA
c229d44badb5891ac5fb4502d33603d29a04253c2d29baa54000e973998efe9c.
Source-before/after **681 files exact**, source-after PASS_CURRENT_SOURCE_FULL_GATE
в local/evidence/20261016-p06t-full02/. Session34806 завершена0.
Это подтверждает dc27285, НЕ последующее исправление очереди ниже.

Mixed-01 binding-p06t.json создан на exactfull02/dc27285. run.py bind --build
принимает basename gateway-p06t-full02 или absolute, НЕ relative local/build/...
Actual services startup-p06t01:5source resources/P06T policies/BOUND PASS;
verify_startup.py readinessSHA867f82fecdcebd69809d79745381c7786bb4c87df0f0693770b8ec30c006a9b5.
Два synthetic own UDP corpus-derived Login→redirect20131→v2run_open→SQLite
PASS; A110→111/B27→28, БК[AP0,HEAT4,HE10] неизменен, reserves0.
Login receipts SHA A563f11679e69bef8f91a2dbeb593b94abbfc2965caf7f3e8ba99be40ecffd627,
B a318b226fbf2e31dc4b26913ceaf18762750ed2050b9b6d2fb25179631f99d6d.
Оба своих gateway/bridge STOPPED через ownreceipt; nativeclients не запускались.
Это auth/startup proof, НЕ native queue/combat/UI. Утренний запуск обязан свежим
run (диагностические pending sessions не переносить).

## ВАЖНО: новый реальный V2 queue bug, исправление в работе

Root после full02 нашла old-only reservation/pending_return checks в
shared/profile13_queue.rs: повторный Join мог менять frozen selection,
busy не видел v2; Cancel мог отправить false раньше durable return.
dispatch_v2 start не исключал уже зарезервированный slot.
Writer p08b_writer_research сейчас ВЛАДЕЕТ этими3active файлами:
profile13_queue.rs, profile13_session.rs, profile13_dispatch_v2.rs +newtests/fixture.
Не дублировать правки. Protocolagent получил read-only независимый аудит.
Новый queuefix ещё НЕ проверен/НЕ закоммичен. После FROZEN canonical focused08,
commit, NEW full03/source-before-after. Старый binding-p06t.json исторический
и sourceguard теперь обязан отказывать. Новый versioned binding-p06t02.json
только на exactfull03; повторить startup/auth/ownstop. Старые proof не менять.

## Другие агенты/подготовка

night_p05c_plan: ONLYignored WT128/WT150/FV183 exporter/sourceadapter в
local/night-staging/20261016/p06t-damage01/wt-fv-scope01/. Первые7testsPASS;
интегрирует подтверждённый xyznuvtb reader. Production не меняет.
night_p08c_protocol vertexproof завершён:
local/evidence/20261016-p06t-vertex01/result.json
SHA9855d66ec4fd9a165be872273112bf81e3c0bc6a04ed3df09f89e31ea89746f7.
Actual3shaderXML/45PEinstructions/5WTprimitive+visual/1085tri/6mutationrejects
PASS_STATIC_ONLY. Diskheader68/stride32/XYZ FLOAT3 offsets0,4,8;
remaining20Bopaque (неfloat8); indices list/list32 width2/4,header72/group16.
WT gun labels gun25 и gunBreech31; SourceClass31 пока не поддержан, не подделывать
обычной бронёй. WT/FV ещё source-only, без qualified physics/owned/native.
Aimproof/nationoverlay/limitations сохранены в0610/0550 checkpoint.

## Следующие действия

1. Дождаться queuefix FROZEN; focused08; inspect independent audit.
2. Обновить короткие docs, commit; clean source-before→full03→source-after.
3. NEW binding+startup/auth+stop; можно установить подготовленныеVERSION7
   overlays в проверенные local/clients/p03f/a,b (старые ledgers уже restored).
4. Обновить mixed-01/MORNING.md (сейчас prepared-only устарел) и общую матрицу
   точными новым head/build/revisions/commands/rollback. Не давать local hyperlinks.
5. Продолжать WT/FV software qualification, затем P10B/NET02 по порядку.
   Не объявлять всю ночную задачу завершённой; главные native gates утром.

Source SCOPES server/tools/client_patch/web/src/tests/web/tests. Во время нового
full нельзя править runtime/HEAD до source-after. Docs/ignored staging можно
писать без commits. Canonical RUST_TEST_THREADS=1 python -B -X utf8
server/build.py gateway --test --out local/build/server/gateway-p06t-full03.
Fresh output only. Все неудачные/прерванные proof сохранять.
