# Состояние проекта — утро17 октября2026

**Текущая P05C ветка `codex/p05c-mixed-contact-handling` от2dcd5b9.**
Mixed AИС7/BМС1: native загрузка/управление/возврат OBSERVED, контакт FAIL:
подвешивание МС1 и остановка движущегося ИС7 на переходе flat→slope.
Владелец разрешил полный переворот. BattleTank PI/3 VERIFIED; причина тяги
UNKNOWN. Core120/оба own клиента штатно остановлены до source edits.
SQL141/53, active0, БК/склад сохранены. Новая физика/native NOT_RUN;
[план](plans/P05C_MIXED_CONTACT_HANDLING.md). Main прежний.

Основной checkout C:/wot091-night-20261017-01/w; исходный D сохранён.
Ночная ветка codex/build-legacy-entrypoints, runtime64767ec, tested checkpoint200dcd2;
финальный descendant меняет только документацию. Mainffce8cb не менялся.

**Canonical gateway1619PASS/0FAIL/5old ignored, buildPASS, source925 raw exact;
7настоящихHTTP/SQLite compositions одного full запечатаны.**
Loss4/БК-loss, Hold5, поздние итоги, Fresh, склад и legacy описаны в
[ночном отчёте](research/NIGHT_20261017_REPORT.md). Новые selection5-reader/CLI/
HTTP935, portability68, map-source74 и own Python2.7 pin90 — отдельные ветки.

**Python06:FAIL —3338tests_run,3232success,12FAIL,45ERROR,90SKIP.**
Focused72:FAIL; targeted88:181success/1ERROR и4classSKIP. Старые FAIL сохранены;
исправления и восстановленные inputs не объявлены повторным полнымPASS.
Isolated68:41PASS;74:11PASS+CLI projection;90:realPy2.7 target1PASS,
Py3 module54PASS/3SKIP. Selection HTTP:Node15/Python18/derivedHold3PASS.

СвежиеCore/rooms/Hold/LAB C03 data contexts подготовлены без grants.
Четыре служебных режима actualBOUND/health/8ownstops PASS83; ownLAN69
Login/RunOpen4/firstBase PASS и2ownstops, это не дваПК. Privateauth95:
Core/rooms/Hold6HTTP200/6ownstops; server-onlyLAB99 genuinefixtures/2HTTP200/
2ownstops/Job0. НовыйnativeLABlauncher отсутствует; старый89authFAIL сохранён.
[Утренние команды](research/NIGHT_20261017_MORNING.md) сохранены как исходный план.
Actual Core утро: V7 rollback/V8 prepare+install обоих, auth/дваангара PASS;
guard11416PASS, launcher1179PASS и actual preflight A/B. Владелец подтвердил
queue cancel→общий бой→управление/красные маркеры обоих, сервер — READY×2/30с.
[Живая приёмка](research/MORNING_20261017_CORE_ACCEPTANCE.md): шаг1PASS,
шаг2: расход4снарядов/SQLitePASS, ручной возвратFAIL — выброс обоих.
ActualA[0,47,47]/B[0,49,45],rev134/46,active0. Core остановлен по ownreceipts:
reset опережает asyncFinish/Leaving→mod303→2157аварийных snapshots/103MB.
Зависимая ветка codex/stab01-core-return-reset, runtime19ba479:
full03 **1628PASS/0FAIL/5old ignored +buildPASS/source925 exact**, early14PASS.
Reset barrier, contained-input ACK и results retirement исправлены. Старые
full01FAIL/full02ABORTED сохранены; test-only budgets210/360с, production
deadlines прежние. Runtime checkpoint19ba479 опубликован/сверён; main не менялся.
Свежий Core retest120: два общихбоя/управление/возвраты PASS владельца и native.
A вручную вышел в первом, B во втором; peer каждыйраз получил naturalForfeit.
4terminal Finished, 2reset, faults/disconnect0, active0; revisions139/51,
loadedA[0,46,46]/B[0,48,44], depot прежний. STAB Core regression принят,
остальная зависимая ночная цепочка внеmain. Следующий Core случай — AИС7/BМС1
без выстрелов перед разрушающим БК-тестом на AМС1 (сохранить armedB).
Невидимый shooter подавляет cross-peer FX VERIFIED; anonymous FX UNFIXED.
Actual observer121 PASS/EVENT_BOUND: writer+fresh7–8с, warm sync~0.4с;
второй игрок дополнительно ждёт writer. Leaf/общийCPU UNKNOWN; fix не заявлен.

Остальные новые native/UI/звук/шесть живых клиентов/дваПК/публичный хостинг
NOT_RUN. Training+Hold5 закрыт; crash доFinal —aborted_restart из frozen reserve,
per-shotWAL нет. Причина микролага UNKNOWN; rustfmt закреплённой версии отсутствует.
Оборудование/слоты/продажа/P04L не подключены к новому writer.
После09:00 ночную реализацию не продолжать без нового задания; владелец уже
запустил Core manual. Непринятая цепочка остаётся вне main.
