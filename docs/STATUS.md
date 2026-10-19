# Состояние проекта

**19 октября, native regression FAIL:** контакт IS-7/IS-7, затем IS-7/MS-1
закрывает бой в `p06t_publication.rs:99:106`. Корректный ram HP не находился
в projectile journal. Оба failure сохранены, процесс сервера жив, durable
возврат обоих подтверждён; snapshot A/B137/59, IS-7 ammo30 сохранён.
Ветка исправления `codex/p05c-ram-health-publication`: красная регрессия
1PASS/4ожидаемыхFAIL. HP/death/Results8/terminal интеграция в работе;
зелёный/full/native gate пока NOT_RUN. Авторитетные физические коробки в двух
снимках имеют пересечение7,3мм/0мм; владелец уточнил визуальный артефакт при
сбросе. Solver не перенастраивается. Main не изменён.

**19 октября: идёт фактический full-polygon native-прогон.** Ветка
`codex/nightly-full-polygon-20261018`; canonical gateway full03 (исторически
1670/0/5) запущен со свежей physics DLL `27760442` после actual IPC7 smoke
100 advances/2 actors PASS. Взята latest actual БД successor-03 (A/B131/53,
grants0), а не устаревшая sealed-05. Оба клиента загрузили LoginView и,
по подтверждению владельца, настоящие ангары. Подготовка пары IS-7 через
обслуживание 15/5/10 подтверждена владельцем и durable service обоих;
общий бой и READY обоих есть в логе. Управление PENDING OWNER,
damage/turret/Results8 на этом запуске NOT_RUN. Начальные553 advances:
wait≤5,805мс/lag≤91,243мс, затем diagnostic512KiB cap (частичный trace).
Main `ffce8cb` не изменён. Map-wide importer, purchased native>=3
battle readiness, отдельный звук лампы и P10B этим стендом не закрыты.
[Запуск, доказательства, матрица и откат](research/FULL_POLYGON_NATIVE_20261019.md).

Ниже — сохранённые сведения предыдущих карточек; они не заменяют текущую
native-приёмку.

**P06T successor fixes on `codex/p06t-loss-writer-observability`:** current
head `0ffa971` includes `bd204a9` persistent detached-turret presentation and
`9dfaa33` module identity retention. A detached turret now stays in `Resting`
after the authoritative ground clamp, is created with the native collision
property already enabled (so the original client's detachment confirmation can
hide the parent turret), and is released with the old battle world. The packed
Results8 contract remains aggregate-only, while the server-side facts retain
`AmmoBay` extra index `27` and reject forged device/index mismatches. Focused
checks passed: turret publication `8/0`, flight settle `1/0`, module identity
projection `1/0`, and module/fire packing `1/0`. Isolated executable
`local/build/server/gateway-p06t-current-focused08/debug/deps/` is built; its
full `p06t_` run was intentionally not used as a gate because it enters long
scene tests and was stopped after the targeted checks. Native visual collision,
parent-turret disappearance, and audio remain **NOT_RUN** until the next owner
run. The server still has no separate Jolt body for the detached child.

**P06T damaged-module recovery:** ветка `codex/p06t-damaged-module-recovery` добавляет
ограниченное восстановление engine/fuel tank из `Destroyed` до source
`maxRegenHealth`, отдельный `repair` transition с публикацией исторических code
`18/19` по итоговой condition, и контрольные проверки steering/cruise после
восстановления. После исправления relocatable pinned GNU driver focused gate
`p06t_` дал **215 PASS / 0 FAIL / 0 ignored**, build PASS, executable SHA-256
`303a9cb8e9dd08abe3da2e0e6efccb0bfcae3229dd31722dc3eec4087a624a4a`. Первый
targeted recovery smoke тоже PASS: `1/0/0`, SHA-256
`d20e471fe25f8990c2a54d257a57007da48ad6a7513a2165d649c38ea1d11356`. Receipts:
`local/build/server/gateway-p06t-recovery-fixed01` и
`local/build/server/gateway-p06t-recovery-focused-pass02`. Native/UI/audio и
двухклиентский replay **NOT_RUN**; карточка остаётся в ветке до владельческого
native-прогона.

**P07B audio follow-up:** владелец подтвердил геометрию/LOS/переворот и
визуальную лампу, но не услышал отдельного звука. Статическая проверка #717
показала: `updateVehicleMiscStatus` и `battle.swf` запускают только визуальный
timeline; в исходном `gui.fev`/`sound_notifications.xml` нет отдельного
Sixth-Sense/lamp event. Это VERIFIED original-path behavior, а не потеря
серверного `0x47` payload. `onScoutEvent` оставлен отдельным enemy-spotted
voice/FX callback и не подменяет лампу. Project-owned audio override — отдельная
ветка/карточка, NOT_IMPLEMENTED/NOT_RUN. [Граница](research/P07B_AUDIO_BOUNDARY_20261018.md).

**P07B: canonical full gate готов, native owner gate открыт.** Изолированная
ветка `codex/p07b-full-gate-temp`, head
`9ec193289b7afd67d5340056b5b6e5f02474a10b`, содержит оригинальный засвет без
маскировки: шесть габаритных точек, два observer points, геометрические лучи,
team publication и постоянное базовое 6-е чувство с проектной задержкой
3000 ms. Canonical Windows GNU gate: **1649 PASS / 0 FAIL / 5 ignored**,
build PASS, executable SHA-256
`cd9d9b01eb779d7768bc568e36d41048c5591d2fd9cc7927db0cb82e696dc0ed`.
Successor `core-loss4/p05c-contact132` source-bound без SQL/client mutation:
binding SHA-256
`8a5fa98ee8b1ef488e20b2a8d0ab82d12cf9698dfd1b5269fe231da0e2664cd7`, freeze
SHA-256 `4a67c6fdb0c630689956387251ceb38924b55de04352bfc6a4481a76df9e7428`;
`check` и read-only `check-clients` PASS. Native/UI/audio/control/two-client
пока `NOT_RUN`. Ручная матрица габаритных точек, лучей, переворота,
постоянного 6-го чувства и приватности записана в
`docs/research/P07B_FULL_GATE_20261017.md`. Отрыв башки и потеря загруженного
БК остаются отдельным P06T damage gate.

**P05C: `codex/p05c-mixed-contact-handling` от2dcd5b9, приёмка FAIL/open.**
Contact129: владелец принял перевороты/столкновения, захват/правильные итоги
и оба ангара; затем сам закрыл окна. SQL144/56, active0, БК/склад сохранены,
grants0; exact129 gateway/bridge STOPPED, FAILED0. Три замечания остаются
до нового native: rollover-засвет, powered-turn разгон, откат ИС7 под W.
Конкретный replay2961–3044: VERIFIED17циклов reversal brake на непрерывномW;
causal latevariant с byteexactprefix≤2940 убирает reset и возвращает подъём.
Это measured frozenreplay/intervention; originalnative attribution ограничена,
остальные остановки/точный deliveredgroundtorque UNKNOWN.

Исторический parent **bc5c1c6/physics05: full02 1632PASS/0FAIL/5ignored,
buildPASS/source941exact**. Current06 добавляет новый rawintent reversal
flag: sharedtrue/legacydefaultfalse, прежний arm/exit−0.5м/с. Ранее world-up
LOS и powered loss>4м/с сохранены. Physics06canonical25rawexactPASS.
Production-linked proof50061cfa: driverlogic520assert/530Apply (synthetic
metrics,0worldupdates), отдельно core72actualworlds, strict ramp24/8/0/0,
powered128PASS. Legacy03build25exactPASS; P05B06 обоих9×2 quality/replayPASS,
3780publicframes/metrics/streams byteexact04==05==06. Source35before/afterexact.
**Full03 PASS (1632/0/5, build/source-after exact); contact130 source-bound launch/hangars PASS, native gameplay NOT_RUN. Mainffce8cb прежний.**
Далее finalsourcecommit/full03 → свежий boundstand130 без grants из actual
БД → manual mixed приёмка. [Отчёт](research/P05C_MIXED_CONTACT_HANDLING.md).
Старые physics04 proofs/replayFAIL сохранены: math47870, fullroll4/4,
P05B9×2×2, currentpolicy slopes4/4PASS; diagnostic slope6PASS/2controlFAIL.
Runtime6119019/full01 source938 и contact129 остаются историческими;
их PASS не переименован в current06 приёмку. Будущий
[RULESET-01](plans/RULESET01_SCOPE.md) только фиксирует требования.

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

**P06T Results8 writer repair (2026-10-18):** ветка
`codex/p06t-loss-writer-observability`, head `39eb92f`. Python results validator
теперь принимает bounded authoritative `crits`/`fire` module facts, поэтому
естественный ammo-loss `finish` не отбрасывается как `INVALID_INPUT` после
публикации P06T module details. Focused Python 1/0 и Rust 13+3/0 прошли с
target на D; receipt и SHA записаны в
`docs/research/P06T_RESULTS_VALIDATOR_20261018.md`. Focused gates PASS; canonical
suite после фикса запущен и дал 1653 PASS / 3 FAIL / 5 ignored, но не принят из-за
трёх successor-stand composition failures; standalone executable build
`B3B318B22867E35F2EEF76CE5D9553B2B1B0975CA609E924B241BF00CD7EA46A` прошёл;
native death/return остаётся
**NOT_RUN**; main не менялся.

**P06T native exit follow-up (2026-10-18):** свежий двухклиентский прогон на
successor `p06t-successor-20261018-03` подтвердил: один клиент получил
`P06T_TURRET_NATIVE Enter/Create`, но не прислал ACK DetachedTurret; через
20 секунд старый путь закрывал сессию с `native_turret_unconfirmed` до
постановки Results8. Второй клиент того же боя получил `Leave`, Results8 и
вернулся в ангар. Узкий source fix оставляет terminal result/handoff
проходимыми после bounded turret-ACK timeout; detached child доживает до
обычного старого-world handoff и не блокирует `Esc -> В ангар`. Focused
regression `p06t_unacked_turret_does_not_block_terminal_result_after_bounded_timeout`
и `p06t_turret_ready_ignores_unrelated_window_pending_after_child_ack`
проходят `1/0` каждый; turret publication suite остаётся `8/0`. Readiness
больше не зависит от постороннего `Window` pending, поэтому возврат не ждёт
полный timeout при уже подтверждённой башне. Новый executable
`local/build/server/gateway-p06t-exitfix-focused01/.../sr-gateway.exe` SHA-256
`C7638CD06B83DB5D234D72C472B606E80A3996186B43D16EBD507D9A417E2799`.
Native повторный прогон после фикса ещё **NOT_RUN**; текущий live стенд не
перезапускался во время владельческого боя.


**Current checkpoint:** full03 PASS 1632/0/5 and source-after exact; contact130 sealed/bound from actual SQL144/56 with grants0, services and both native hangar launches PASS. Client gameplay and native P05C acceptance remain NOT_RUN pending owner manual scenario. Evidence receipt: `local/evidence/20261017-morning-core01/contact130-preflight-completion.json` SHA256 `84145bed0503b5637349b784423040ea27f9fbad9522cb893bd9ff8c04317d29`.


## Contact130 native observation

Owner observed a normal full rollover: inverted MS-1 retained mutual visibility with IS-7. This is a native PASS for the rollover LOS regression only (owner receipt `contact130-owner-feedback-visibility.json`, SHA256 `cf1c0f79663275538e818e6d9172351a13fe881d3c707159a7045467397f0865`). The same live battle later ended with `SHARED_BATTLE_FAILED` reason `shared scene worker deadline` at the server worker deadline; the manual run is therefore interrupted and P05C overall remains open. Failure receipt: `local/evidence/20261017-morning-core01/contact130-worker-deadline-failure.json` SHA256 `59324a31e4dc3e0173cf193bec6e269413d38b4a9f8fd8e725feed6255fde582`. Native powered-turn/hill and full battle-return acceptance remain NOT_RUN/INCOMPLETE.


### Contact130 failure reasons

The live run emitted two fail-closed reasons in order: `integrated drive logical deadline lag exceeds500ms; fail closed`, then `shared scene worker deadline`. Both clients still committed loss results and returned to hangars. The authoritative extract records the last world snapshot (IS-7 speed `-4.7230258` with `Input { throttle: -1, steer: 1 }`; MS-1 stationary) but this late state is not attributed to the owner's earlier W hill episode without matching input semantics. Receipt `local/evidence/20261017-morning-core01/contact130-failure-reasons.json` SHA256 `02a5e37d52753a3a455f012aadd559e7e700ec9d24cdbbc958ae41a44af52fde`; extract SHA256 `7857780049a518066e5180bd1a1e8ff088d61697fc3d53a7fa8f68559a3432a5`.


### Worker deadline classification

Read-only diagnosis separates this from physics acceptance. Battle `1842779300997493393` failed first because the shared main loop exceeded the 500 ms logical-drive lag while no worker reply was pending. Battle `1842779300997493394` then failed because a pending scene-worker advance exceeded the 500 ms IPC/world-step reply deadline. CPU/OS scheduling duration is not recorded, so runtime overload/latency remains UNKNOWN. Keep both fail-closed guards unchanged; the next card is a bounded worker-cadence diagnostic with per-advance wall timing, child stderr/CPU and scheduler receipts, not a silent timeout relaxation or P05C physics retune.

### STAB worker cadence branch

Ветка `codex/stab-worker-cadence` (`88114709a1062b6dfb4e821e8a99a0eed26e1e4f`)
подготовила opt-in bounded receipts для IPC7 `scene_worker::Worker` и
`BatchRuntime`: каждый advance/reply, logical scheduler lag, обе fail-closed
deadline ветви, bounded stderr и Windows CPU sample. Env
`WOT091_STAB_DIAGNOSTICS_DIR` выключен по умолчанию; guards
`REPLY_TIMEOUT=500ms`/`MAX_LAG=500ms` не менялись. Три cadence unit tests
прошли; отдельный canonical executable build прошёл через retained local
toolchain overlay (exe SHA256
`558564bac82fccc9416f151c5f47dd544bdbe915647251d9aaccf35dca61945f`). Полный
suite на canonical checkout дал `1587 passed / 48 failed / 5 ignored`: FAIL
сосредоточен на отсутствующих старых physics/fixture artifacts и не является
основанием для P05C PASS. Ветка и новый stand остаются вне `main`.

Свежий successor `local/stands/morning-p05c-contact-20261017-05/core-loss4`
подготовлен с tag `p05c-contact132`, run `p05c-contact132-01` и отдельным
`WOT091_STAB_DIAGNOSTICS_DIR`; receipt
`local/evidence/20261017-stab-worker-cadence/contact132/successor-stand.json`
SHA256 `9a78b79dd671ddad0a471079de50e0d4491fc417b4bbda898a15d93d1c682891`.
Services, native/UI, two-PC и actual cadence receipts пока `NOT_RUN`.
Cadence unit receipt `local/evidence/20261017-stab-worker-cadence/contact132/cadence-unit-evidence.json`
SHA256 `bc0cb64dca7440633c1d0b8dc36475e7e4b4ec252bae732664fda9053ae3fae5`
фиксирует 3/0/0. Точечный actual IPC7 Worker gate прошёл 1/0/0 и записал
600 `advance_dispatched`, 620 replies и CPU samples в четыре bounded JSONL;
receipt `local/evidence/20261017-stab-worker-cadence/contact132/native-cadence-evidence.json`
SHA256 `e29e8d224b9683f1e3e657d57b793f3590ebb830be0efa3b47c5d659091e4f98`.
Этот тест напрямую гоняет Worker, поэтому `scheduler_lag` BatchRuntime и
native/UI остаются `NOT_RUN` до successor прогона.

## P07B original spotting successor (current card)

Ветка `codex/p07b-original-spotting-successor` собрана от текущего P05C/STAB head и содержит P07B implementation `a7506983f8efad3165e9a7f8d971ce380501a556`: шесть source visibility points, два observer points, authoritative geometric LOS, no-camo ruleset и candidate Sixth Sense publication. Старый P07B AoI остаётся базовым слоем. После cherry-pick focused tests и canonical full gate должны быть перепроверены на этом descendant; native/UI/audio остаются NOT_RUN до ручного прогона.

**Nightly full-polygon integration (2026-10-18):** branch codex/nightly-full-polygon-20261018 is source-bound to the P06T exit-fix head. Generic map-agnostic dynamic-destruction contract is present in dynamic_destructible.rs; its native map catalog/import/publication remains NOT_RUN. P06T focused gate on the pre-integration head: 221 PASS / 0 FAIL / 0 ignored, executable SHA-256 d27ac3288fcb1c3e449efdf1953b319951dbdf7528b53fd1017d50e431b85f6a. The full polygon gate will be rerun after ram/map sources settle; main remains unchanged.

**Nightly full-polygon integration:** generic dynamic destruction contract and pinned GNU linker path are carried on this branch. The map-agnostic contract is source/test complete, while per-map catalog import, renderer/native publication and rubble collision remain NOT_RUN. P06T pre-integration focused gate was 221/0/0 with executable SHA d27ac3288fcb1c3e449efdf1953b319951dbdf7528b53fd1017d50e431b85f6a; it will be rerun after ram wiring.

**Nightly polygon ram/destruction integration:** authoritative ram source and map-agnostic dynamic destruction contract are carried on codex/nightly-full-polygon-20261018; native collision damage and per-map catalog/import remain NOT_RUN pending the sealed morning stand.


Nightly full polygon 2026-10-19: branch codex/nightly-full-polygon-20261018, head 356c21a, main untouched. Canonical sequential gate 1670 PASS / 0 FAIL / 5 ignored; executable SHA-256 04f2c94262a2f9bb973cac7840f54e4885cfdbbf85fbeae126f98ea5e3208bdd. Fresh D-only successor-05 is prepared with SQLite quick/integrity ok, ports 20330/20331/3691; native/UI/audio/control/two-PC remain NOT_RUN. See docs/research/NIGHTLY_FULL_POLYGON_20261019.md and local/evidence/20261019-nightly-full-polygon/receipt.json.
