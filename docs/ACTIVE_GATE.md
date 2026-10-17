# Текущие ворота: P05C — смешанный контакт и полные перевороты

Ветка `codex/p05c-mixed-contact-handling` от2dcd5b9;
[план](plans/P05C_MIXED_CONTACT_HANDLING.md). Runtime6119019/physics04:
canonical1628PASS/0FAIL/5oldignored, build/source938 exact, actual2/6PASS.
Component fullroll/math/P05B обоих/авторские склоны PASS, прежние контрольные
FAIL и ограничения replay сохранены.

Contact129 mixed8303176210728121358: владелец подтвердил перевороты,
столкновения, захват с правильными итогами у обоих и загрузку обоих ангаров.
Окна закрыл сам. Лог: Capture/base2=100, winner1, durableFinish144/56,
2native returns/2HangarReturned/1reset; FAILED0. После reset2client_disconnect
при закрытии окон не считать вылетом. Current SQL144/56, active0; БК/склад
сохранены, grants0. Оба native absent, gateway/bridge exact129 STOPPED.

Приёмка P05C остаётся FAIL: при перевороте МС1 пропадает взаимный засвет;
ИС7 продолжает разгоняться в powered turn; на пригорке останавливается и
отказывается ехать. Root cause пригорка UNKNOWN. Code sight clearance+0.5
вращается вниз при roofroll VERIFIED; точное пересечение земли в native
эпизоде INFERRED (original log без chassisYPR/LOS hit). Прежняя P05B matrix
не проверяла потерю разгона powered turn. Текущая работа: LOS regression,
matched-start actualJolt turning и stall/control audit, затем source-bound
проверки. Новые исправления native NOT_RUN до нового ручного прогона.
Main прежний. [Доказательства/границы](research/P05C_MIXED_CONTACT_HANDLING.md).
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
