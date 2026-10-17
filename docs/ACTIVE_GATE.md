# Текущие ворота: P05C — смешанный контакт и полные перевороты

Ветка `codex/p05c-mixed-contact-handling` от2dcd5b9;
[план](plans/P05C_MIXED_CONTACT_HANDLING.md). Исторический parent bc5c1c6/
physics05: full02 завершён1632PASS/0FAIL/5oldignored, buildPASS/source941
exact. Этот PASS не относится к новому physics06. Текущий physics06:
canonical build25raw exactPASS, intent reversal сохраняет порог−0.5м/с,
sharedopt-in включён/legacy defaultfalse; full03 **PASS: 1632/0/5, build/source-after exact**.

Contact129 mixed8303176210728121358: владелец подтвердил перевороты,
столкновения, захват с правильными итогами у обоих и загрузку обоих ангаров.
Окна закрыл сам. Лог: Capture/base2=100, winner1, durableFinish144/56,
2native returns/2HangarReturned/1reset; FAILED0. После reset2client_disconnect
при закрытии окон не считать вылетом. Current SQL144/56, active0; БК/склад
сохранены, grants0. Оба native absent, gateway/bridge exact129 STOPPED.

Приёмка P05C остаётся FAIL по трём замечаниям contact129: потеря взаимного
засвета при перевороте МС1, разгон ИС7 в powered turn, откат около−1км/ч
под W+поворотами на пригорке. Для сохранённого physics04 replay окна
2961–3044 причина измерена:17циклов reversal brake при непрерывном W
сбрасывают motor/RPM. Causal variant с теми же controls и byteexactprefix
до2940 убирает повторный brake, возвращает uphill progress без retune.
Атрибуция исходного native эпизода ограничена frozenreplay/intervention;
новая native проверка не проведена. Ранние peer-support окна — другой случай.

Current06 включает world-up LOS, measured powered loss выше4м/с и reversal
brake только для нового rawthrottle intent; удержанный W после выхода при
прежних−0.5м/с не перевооружает тормоз от скатывания. Production-linked
proof50061cfa: synthetic driverlogic520assert/530Apply отдельно от72actual
Jolt worlds; strict ramp24runs/8exercised/0notEx/0unmatched; powered128PASS,
P05B обоих9×2 quality/replayPASS, publicstreams04==05==06 byteexact.
35rawfiles before/after exact; legacy03build25exactPASS (simulationNOT_RUN).
Native130 source-bound launch и два ангара PASS; LOS/новое управление **NOT_RUN**. Mainffce8cb прежний.
Следующий шаг: finalsourcecommit → full03 → source-bound stand130 из actual
SQL144/56 либо более поздней БД без grants → единый ручной mixed сценарий.
[Доказательства/границы](research/P05C_MIXED_CONTACT_HANDLING.md).
Будущий [RULESET-01](plans/RULESET01_SCOPE.md): требования к общим настройкам,
тимдамагу/чату записаны; текущие игровые defaults не менялись.

## Сохранённый Core checkpoint

Ночное задание владельца до04:00UTC/09:00Екатеринбурга: основной runtime64767ec,
tested checkpoint200dcd2, ветка codex/build-legacy-entrypoints, source925.
Canonical gateway1619PASS/0FAIL/5прежних ignored +buildPASS;7HTTP/SQL compositions.
Полный Python06 остаётсяFAIL; исправления и новые кандидаты в отдельных ветках.
Mainffce8cb сохранён. [Отчёт](research/NIGHT_20261017_REPORT.md),
[точный утренний запуск](research/NIGHT_20261017_MORNING.md).

Core/rooms/Hold подготовлены раздельными C03 SQLite. Утром по команде владельца
Core запущен с новым launcher117: rollback V7 обоих, prepare/install V8 обоих,
actual private auth и два настоящих ангара PASS. Владелец подтвердил отмену
очереди, общий бой, движение/наведение и красные маркеры обоих; сервер подтвердил
READY обоих и отсчёт30с. Это PASS первого сценария, не приёмка всей цепочки.
Шаг2FAIL: после4выстрелов manualEsc выбросил обоих. Остатки в SQLite верны:
A[0,47,47]/B[0,49,45], revisions134/46, active reservations0.
Причина VERIFIED: reset очищает world до завершения Leaving/asyncFinish,
publication обращается к oldslot в новом пустом world;2157повторов/103MB snapshot.
Все4own процесса штатно остановлены. Исправление в зависимой ветке
`codex/stab01-core-return-reset`; [план](plans/STAB01_CORE_RETURN_RESET.md).
Runtime19ba479: full03 1628PASS/0FAIL/5old ignored, buildPASS/source925 exact;
early14PASS. Reset barrier +contained ingress/retirement исправлены; прежние
full01FAIL/full02ABORTED сохранены. Test-only budgets210/360с, production
deadlines прежние. Runtime checkpoint19ba479 опубликован/сверён, main прежний.
Свежий Core retest120 из actualCDB134/46, loadedA[0,47,47]/B[0,49,45], grants0;
оба auth/native launch/два настоящихангара каждого PASS. Два общихбоя теперь
приняты владельцем: Amanual/Bnatural, затем Bmanual/Anatural, управление обоих
работает. Native/SQLite подтверждают4Finished,2reset,faults0,active0;
loadedA[0,46,46]/B[0,48,44],rev139/51,depot unchanged. STAB Core regressionPASS;
main остаётся прежним из-за непринятой зависимой ночной цепочки.
Следующий ручной Core случай — AИС7/BМС1, без выстрелов, затем БК-жертва AМС1;
не обнулять БК B до остальных вооружённых проверок (у BИС7 loaded0).
[Живая утренняя приёмка](research/MORNING_20261017_CORE_ACCEPTANCE.md).
Новые остальные native/UI/звук/шесть клиентов/дваПК NOT_RUN. LAB99: genuine
fixtures и2privateHTTP200 PASS; нового native launcher нет. Старый89 не ретегать.
Training+Hold5 и owned admission новых LAB машин закрыты.

После09:00 новые ночные изменения не начинать. Утренняя команда владельца на
Core запуск и ручную проверку получена; продолжать этот сценарий по шагам.
Не запускать WoT по одному времени или heartbeat. Непринятые карточки вне main.


## Current full03/contact130 checkpoint

Full03 actual canonical gate PASS: 1632 tests passed, 5 ignored, build PASS; source-after SHA256 `a41a462e0f58669303389c27026940c56d048aa99e690077808f7ce17316b5dc`; executable SHA256 `dffeeb03acdfb3cec591410f5885dc1cfca69118a1cc7cc75e0d295c69d09d45`. Final physics06 artifact `cff138e72f0172ea98751884027f880e2ad5592665087b1f8cc6b77710b6aa4d`.

Fresh contact130 was source-bound to HEAD `b3cffd559aea2c79be7eca4640134607718e5c0f`; capture-origin, data preparation, publish, bind, checks, client checks and sealed operator packet all PASS. Actual two own clients and gateway/bridge are live; two consecutive native hangar samples per client PASS. Native battle/LOS/physics/manual control remains NOT_RUN until owner interaction.


## Contact130 native observation

Owner observed a normal full rollover: inverted MS-1 retained mutual visibility with IS-7. This is a native PASS for the rollover LOS regression only. The same live battle later ended with `SHARED_BATTLE_FAILED` reason `shared scene worker deadline` at the server worker deadline; the manual run is therefore interrupted and P05C overall remains open. Failure receipt: `local/evidence/20261017-morning-core01/contact130-worker-deadline-failure.json` SHA256 `59324a31e4dc3e0173cf193bec6e269413d38b4a9f8fd8e725feed6255fde582`. Native powered-turn/hill and full battle-return acceptance remain NOT_RUN/INCOMPLETE.


### Contact130 failure reasons

The live run emitted two fail-closed reasons in order: `integrated drive logical deadline lag exceeds500ms; fail closed`, then `shared scene worker deadline`. Both clients still committed loss results and returned to hangars. The authoritative extract records the last world snapshot (IS-7 speed `-4.7230258` with `Input { throttle: -1, steer: 1 }`; MS-1 stationary) but this late state is not attributed to the owner's earlier W hill episode without matching input semantics. Receipt `local/evidence/20261017-morning-core01/contact130-failure-reasons.json` SHA256 `02a5e37d52753a3a455f012aadd559e7e700ec9d24cdbbc958ae41a44af52fde`; extract SHA256 `7857780049a518066e5180bd1a1e8ff088d61697fc3d53a7fa8f68559a3432a5`.
