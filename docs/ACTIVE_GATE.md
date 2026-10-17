# Текущие ворота: утренняя native-приёмка 17 октября

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
Следующий шаг: regression/full новогоhead→новыйstand из actualCDB→ручной retest.
Full01 на25ac184:1624PASS/1FAIL/5old ignored, все6новых STAB регрессий PASS;
FAIL — measured actual4Hold watchdog180с, послеFinal4/all-finalSQL. Старый FAIL
сохранён. Incoming03 исправляет review contained-input ACK/results retirement;
Full02 compilePASS/early13PASS+1newHold fixtureFAIL; полный ownSTOP/ABORTED,
артефакты сохранены. Fixture04 test-only peer departure hook; full03 PENDING.
Test-only budgets210/360с, production deadlines прежние.
[Живая утренняя приёмка](research/MORNING_20261017_CORE_ACCEPTANCE.md).
Новые остальные native/UI/звук/шесть клиентов/дваПК NOT_RUN. LAB99: genuine
fixtures и2privateHTTP200 PASS; нового native launcher нет. Старый89 не ретегать.
Training+Hold5 и owned admission новых LAB машин закрыты.

После09:00 новые ночные изменения не начинать. Утренняя команда владельца на
Core запуск и ручную проверку получена; продолжать этот сценарий по шагам.
Не запускать WoT по одному времени или heartbeat. Непринятые карточки вне main.
