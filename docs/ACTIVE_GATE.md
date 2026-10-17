# Текущие ворота: P05C — смешанный контакт и полные перевороты

Утренняя mixed native проверка AИС7/BМС1: загрузка, управление и возврат
обоих работают; приёмка контакта НЕ пройдена. Владелец наблюдает зависание
МС1 у ИС7 и остановку уже движущегося ИС7 при переходе flat→slope с толкаемым
МС1. Полные перевороты явно разрешены владельцем. VERIFIED ограничитель
BattleTank PI/3; причина потери тяги UNKNOWN до actual замера.
Ветка `codex/p05c-mixed-contact-handling` от2dcd5b9; [план](plans/P05C_MIXED_CONTACT_HANDLING.md).
Предыдущий Core/retest120 и оба own клиента остановлены exact receipts.
Актуальные SQL141/53, active0, снаряды/склад сохранены. Новая физика/native
NOT_RUN; main прежний. Никакой подмены source/power/friction для приёмки.

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
