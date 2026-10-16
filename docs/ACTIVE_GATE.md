# Текущая карточка — 2026-10-16

**P10B — родная тренировочная комната на N игроков**, ветка
`codex/p10b-native-training-room` от P06T docsheadb9239e3, runtimebase0f1db40.
Прямое ночное разрешение позволяет продолжить без ожидания ручной приёмки
предыдущих карточек; обязательный nativeNOT_RUN не разрешает main merge.

P06T сохранён: coretag9920a63/full03=1096PASS/683exact; physicalc25/full04=
1100PASS/692exact; devices9080/full05=1111PASS/695exact. Последний полный
World7 gate0f1db40/full06: **1162PASS/0FAIL/5oldignored/buildPASS**,469.71с,
725sourceexact, tag p06t-world-seven-20261016-01. Actual extended-01 WT/FV
startup7resources/LABv2/ownstop PASS,106 core/clientinputs unchanged. Native/
UI/audio/новыйoverlay NOT_RUN. CoreV7 установлен и сохранён для утра.
OwnedV3 component29SQL/source/2CPythonPASS; live factory/cacheACK/newWTstock
не подключены. P06T не принята и не main.

P10B сохранённый componenttag `p10b-components-20261016-01`,36d57a0:
**1341PASS/0FAIL/5oldignored/buildPASS**,501.62с,775sourceinputs exact
до/после. ActualSession/Controller/Window transaction, TeamPlan/World/actual
scene3v1+1v3, boundedaliases/streams200/201, strictread-onlyselection,
serialreserve/compensation и Finishedhook проверены применимой автоматикой.
HTTP03=3PASS/0skip77.768s; CPython2.7.3=76PASS/3oldhostskips.

После full03 подключён liveHost: actualSession receive, readonlyReady worker,
serialPreparing/launch, durableFinished и общий серверный цикл. Selected/bench
disconnect удерживает происхождение до компенсации; ошибки garage/results
проходят ту же границу закрытия. WarmAccount того же Session читает List/Preview
без освобождения Battle claim. CheckedReady rebase/Results isolation сохранены.
Full04 на9b5fc6d/tag p10b-host-20261016-01: **1394PASS/0FAIL/5oldignored/
buildPASS**,533.65с,784runtimefiles exact. Новый stand02 actualstartup5resources/
ownstop PASS; source-restore audit784/changes0 PASS. Actualsocket два Login/Base/
Account/run_open PASS, но оба Ready получили отказ: **live readiness FAIL**.
Actual directworker подтвердил ModuleNotFoundError: tools за0.124с; прежний
HTTP harness маскировал отсутствующий ROOT bootstrap через PYTHONPATH. C39/D40,
БК unchanged, активных резервов0. Bootstrap исправлен: actualCLI из чужого cwd
без PYTHONPATH=1PASS; actual clean-env HTTP suite=3PASS/0skip82.740с на production
adapter/worker, источники before/after exact. HTTP-ошибка теперь сохраняет status
и только closed denial code. Full05 наe55ba01/tag p10b-host-20261016-02:
**1397PASS/0FAIL/5oldignored/buildPASS**,535.18с,785runtimefiles exact.
Actual minimumsocket room-startup02 PASS: два Login/Base/Account/run_open,
две реальные HTTP/SQL Ready, Create/Join/Assign/refusal/Leave/recreate;
C40/D41, БК[0,4,10] unchanged, активных резервов0.
Actual phase2 room-durable01 PASS: обе Ready→два durable Admit→launchcommit
при Account→оба ordinarydisconnect за5.750мс после callback→безопасный
training_prestart_disconnect до Worldstart→два actual Finished. ExactSQL
Admit/Finish/Frozen/CAS/journal цепочки проверены; C43/D44, активных резервов0,
HP90/БК unchanged, свежие Login и новая комната в том же процессе PASS.
Собственные gateway/bridge остановлены по receipts. Native/UI/управление,
Avatar/Worldstart и шесть клиентов NOT_RUN; main не менялся. Failedsocket/full04
сохраняются отдельно. Ночной автоматический checkpoint позволяет следующую
зависимую ветку NET-02; P10B не принята владельцем и не разрешена к merge.
OneactiveWorld,2..6 бойцов,≤3 на стороне, map4/Прохоровка, one-shotroom LABpolicy.

План [P10B](plans/P10B.md), originalsource
[контракт](research/P10B_NATIVE_ROOM_CONTRACT.md), порядок
[IMPLEMENTATION_ORDER](IMPLEMENTATION_ORDER.md). Утренний самостоятельный отчёт —
[NIGHT_REPORT_20261016](NIGHT_REPORT_20261016.md), матрица и прямое разрешение —
[NIGHT_20261016](plans/NIGHT_20261016.md). Практика/разрешённые пути —
[DEV_NOTES](DEV_NOTES.md). Нативные номера методов INFERRED до наблюдения,
родной клиент/original не изменять. Текущие служебные интерфейсы loopbackonly.

Старые карточки и ветки сохранены отдельно. STAB-01 в mainffce8cb принят
владельцем; P08B/P08C/P05C/P07B/P04M/P06T остаются на зависимых ветках с
утренними обязательными gates. Первый боевой тест ещё не подготовлен до
production P10B/NET-02 и nativeприёмки; хвост не начинать раньше вехи.
