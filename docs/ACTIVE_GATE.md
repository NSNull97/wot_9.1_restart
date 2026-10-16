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
Focused24:189PASS/1FAIL/0ignored; единственная ошибка — новое ожидание теста,
которое оставляло отключённого бойца в комнате после abort. Исправлено на точный
оставшийся состав, production semantics не ослаблены. Full04 текущего head пока
NOT_RUN. Native/UI/управление и live RustHTTP→room→launch NOT_RUN; main не менялся.
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
