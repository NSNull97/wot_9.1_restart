# Состояние проекта — 2026-10-16

Короткое текущее состояние. Полная история карточек до этой даты удалена из рабочего
дерева и доступна в git: `git show 1eaff5e:docs/STATUS.md` (а также удалённые
`docs/plans/`, `docs/evidence-index/`, `docs/archive/`, `MASTER_PLAN.md`).
Следующий шаг — [ACTIVE_GATE](ACTIVE_GATE.md), порядок — [IMPLEMENTATION_ORDER](IMPLEMENTATION_ORDER.md),
практика — [DEV_NOTES](DEV_NOTES.md), факты — [research/INDEX](research/INDEX.md).

STAB-01 принята на runtime `0574ab0`: 854 gateway tests PASS / 5 ignored,
сборка PASS; инъекция ошибки с настоящими workers и следующий бой PASS.
Native-fix07: два ручных native_leave с завершённым warm-возвратом; оба клиента
повторно входят, движение/наведение/стрельба подтверждены владельцем. Реальные
deadline faults закрывают только текущий бой, gateway и сессии сохраняются.
История исправлений, границы проверки и evidence —
[STAB-01](research/STAB01_BATTLE_STABILITY.md). Следующая карточка — P08B.

P08B в работе в `codex/p08b-profile13-battle`, в main не слита. Изолированные
owner+writer28, новый Web7, Web-регрессия18 и client/control проверки PASS;
gateway893 PASS/5 ignored и сборка PASS на runtime `5c08ef5`.
Свежая двухаккаунтная БД профиля13 сохраняет A. Первый native запуск поймал
неверный bool-контракт isCrewFull до reserve; исправлен на native seat count,
client314 PASS и CPython2.7.3 81 PASS/4 host-only skips. Исправлена корреляция
latest verified login retry. Native-fix03: владелец подтвердил оба ангара с16ББ
и повторный общий бой; трасса/БД подтверждают два полных цикла18→16→14 у обоих,
8 выстрелов, 4 manual_leave/committed результата, 0 world faults. Настоящие
native queue→cancel→requeue подтверждены владельцем. Gateway аварийно остановлен
с active резервом14ББ; новый run сделал один aborted_restart/возврат14,
7 прежних finished не изменились, оба native ангара loaded/cache/model/AP14.
Owner postrestart и mutation/warmN→full1 smoke отложены до утра по указанию
владельца 2026-10-16; карточка пока не принята и в main не слита.
Native-fix02: общий бой, 4 выстрела и 2 manual_leave с committed AP18 PASS по
трассе/БД; owner сообщил black return. Причина — legacy shop cache limit16448,
native profile13 прислал23107. Лимит привязан к research fixture32832; текущий
повтор — `local/stands/p08b-profile13-01/native-fix03/`, текущий AP14 у обоих.
[Факты и ограничения P08B](research/P08B_PROFILE13_BATTLE.md).

Ночное задание 2026-10-16 разрешает продолжать следующие карточки по порядку
без ожидания ручных gates. Автоматические результаты и native NOT_RUN разделяются;
непринятые карточки остаются в отдельных зависимых ветках. План и утренняя матрица —
[NIGHT_20261016](plans/NIGHT_20261016.md).

P08C candidate в codex/p08c-battle-lifecycle: authoritative waiting/countdown/
battle/capture/outcome, opposite teams, original result stream и atomic fullresult
writer реализованы. Full runtime8c96580: gateway919 PASS/5 прежних ignored,
build PASS (gateway-p08c-full01), writer10/P08B18, real HTTP/static contract5 PASS.
Native/UI/audio NOT_RUN, main не изменён. [Факты P08C](research/P08C_BATTLE_CYCLE.md).

P05C в codex/p05c-shared-physics: actual one-scene компонент2/6/mixed/контакт/
repeatability/sceneACK PASS (отдельный component, не native). Core mixed Actor/Trace/AP
и native bounds собраны; six02:7PASS/0ignored/buildPASS. Исправлен реальный конфликт
ID/alias третьей машины с AreaDestructibles. Actual gateway↔Jolt2/6, scene ACK,
detach в ACK-окне и frozen outcome PASS. Runtime019ed2f: полный gateway940PASS/
5ignored/buildPASS, source-before/after602files совпадают. Native mixed/6 NOT_RUN;
ветка сохранена, main не изменён. [Физика](research/P05C_SHARED_PHYSICS.md),
[передача клиенту](research/P05C_NATIVE_TRANSPORT.md).

P07B candidate `codex/p07b-server-visibility`, runtime8fecb9d: серверный range/LOS,
native AoI и reliable epochs, фильтр Create/pose/HP/aim/fire/terminal реализованы.
Focused23 и полный975PASS/5ignored/buildPASS;607files source before/after PASS.
Actual source geometry Прохоровки/360LOS PASS; native исчезновение/засвет NOT_RUN.
Стенд bound с visibility_v1=true; в main не слито. [Факты](research/P07B_SERVER_VISIBILITY.md).

P04M в `codex/p04m-five-battle-profiles`: пять source-bound
боевых видов, общий IPC7 и getter bits новых машин, броня/AP/наведение и БК160
реализованы. Focused04:26PASS/0ignored/buildPASS, включая настоящий Jolt→Rust
FrameProof и coupled World/Trace/sceneACK новых3/mixed6; C#contacts/repeatability
PASS. Companion05:5PASS/build и два actual SQLite303/309→Rust tests PASS.
Owned crew/ammo реализованы; Python17+1/старая P08B/results28/legacyWeb12 PASS.
FinalWeb06:10PASS, secondaryskill и scoped HTTP deadlines исправлены.
Full02 runtime483bb2b:1006PASS/5oldignored/buildPASS,634sourcefiles before/after
совпадают; executable5376778a…2c4e. Изолированный pool-01 stand A109/B26
подготовлен без grants, normal/qbindings full02 созданы, CLIstartup/stop PASS,
оба MS1AP14/A IS7AP19, исходная БД побайтно сохранена. Новые3 admissionfalse,
native/UI NOT_RUN; main не изменён. [План](plans/P04M.md).

P06T в `codex/p06t-mixed-shell-damage`: source frozen shell/БК3/current/next/
clip/reload, APCR/HEAT/HE LAB solver, actual geometry/LOS splash, module/crew/
fire и HP/death ledger соединены с v2reserve/result/restart/publication.
Core tag9920a63/full03:1096PASS/5oldignored/build/683sourceexact. Python21/
old28/Web4+old25/client2.7.3 9+20+61PASS/4hostskips. Mixed-01/V7 INSTALLED,
actual startup/5resources/ownUDPwriter и оба native hangar/cache/model boot
OBSERVED; A112/B29/MS1[0,4,10]/reserves0, свои процессы STOPPED. UI/бой NOT_RUN.
Full04 physical c25fb84:1100PASS/5ignored/build/692exact; Python7/negative8/
455oldframesexact, actual canonicalJoltIPC7→scalarFrameProof→ACK4PASS.
Full05 devices9080c47:1111PASS/5ignored/build/695exact; caps7/crew6/policyv2.
Новый World7/Aim/geometry/temporary LAB сохранён09ebe8a/1a6b93f; focused13
134PASS/build, focused14 actualhit5PASS/build. Explicit LABv2 source31/Trace/
Gun ledger/CLI focused15 **149PASS/0FAIL/0ignored/buildPASS**,171.93с.
OwnedV3 component11files: fresh actualC/D135.88с/26sourceSQL/2CPythonPASS;
реальные WAL read races воспроизведены и исправлены, весь29tests PASS48.856с.
Factory/router/cacheACK/ownedWTammo не подключены. Full06 на0f1db40:
**1162PASS/5oldignored/buildPASS**,469.71с/725exact; world-seven tag сохранён.
Extended-01 actual WT/FV startup7resources/LABv2/ownstop PASS,106 coreinputs
unchanged; newoverlay/native NOT_RUN. Непринятые gates в main не сливались.
[Реализация и ограничения](research/P06T_RUNTIME_CANDIDATE.md).

P10B начат в `codex/p10b-native-training-room` от P06Tbase0f1db40; production
foundation focused01=51PASS/0ignored/buildPASS, actualhangarshim/defaultclosed.
TeamPlan/Session/writer saga и native ещё NOT_RUN. План [P10B](plans/P10B.md).

## Принято владельцем на настоящем клиенте #717

- Вход и аккаунт: собственная авторизация, перезаход, ангар на реальном клиенте 0.9.1.
- Бой двух клиентов на Прохоровке (MS-1 и ИС-7, однородные пары): движение, стрельба
  бронебойными, урон и смерть, разрушение ящиков, падение деревьев, цепочки заборов,
  таран объектов. Управление P05B (2026-10-14): поворот при отпущенном газе, смена W/S,
  разгон, круиз 25/50 %, пробел как в оригинале.
- Ангар профиля 13 (P09E-M, 2026-10-15): экипаж P04K сохранён при миграции и
  переводится; исследование модулей и танков за 0 по историческим связям; покупка танка
  без экипажа и БК; установка модулей; сохранение после перезахода.
- NET-01 (2026-10-15): сессия переживает блокировку клиента при обновлении ангара (до 30 с).
- ACC-01 (2026-10-15): неподдерживаемая покупка слота даёт ошибку, а не зависание.
- STAB-01 (2026-10-15): ошибка боя изолирована, ручной возврат обоих в ангар и
  повторный бой с рабочими управлением/наведением/стрельбой; account channels сохраняются.

## Есть в main, вручную не проверено

- Экипаж P04D–P04K: найм (в том числе в казарму), обучение и навыки, увольнение,
  личное дело — проверены автоматически и частично вручную (переводы на профиле 13).
- Боекомплект P09D: выгрузка/загрузка/пополнение из своего склада; покупки снарядов нет.
- Найм в казарму и перезаход именно на профиле 13 — только автоматически.

## В main ещё не реализовано и известные дефекты

- Ангар и бой — разные режимы gateway: из ангара профиля 13 в бой не попасть (P08B).
- Цикла боя нет: отсчёта, захвата, победы, итогов (P08C). Видимости нет (P07B).
- Наблюдаются deadline faults физики >500 мс: бой корректно закрывается, но причина
  задержек ещё не устранена. Пассивный native observer обрывает снимки при ещё
  пустом vehicleTypeDescriptor; игровая приёмка STAB-01 подтверждена отдельно.
- Физика — отдельный процесс на танк, танки не сталкиваются друг с другом (P05C).
- В бою только MS-1 и ИС-7; снаряды — только бронебойные (P04M, P06T).
- Экипаж и БК при покупке танка, покупка слота, продажа, оборудование — недоступны.
- Микролаг клиента ~150 мс раз в 10 с; обновление ангара после исследований +3,9 с.
- `--legacy` сборки сломаны; полный Python-набор — 19 падений окружения.

## Последние карточки

| Карточка | Main | Суть |
|---|---|---|
| ACC-01 | `1eaff5e` | `RES_NOT_AVAILABLE` на неподдерживаемые команды аккаунта из списка по байткоду |
| P09E-M | `b5b8b79` | Исследования и покупка как профиль 13 поверх P04K; ревизия магазина 5 → 3 для экипажа |
| NET-01 | `b676f51` | Таймаут доставки интерактивной сессии по времени (30 с) вместо 5 попыток |
| P05B | `caf0b0b` | Управление MS-1/ИС-7, круиз, гонка тика выстрела |

Последний полный прогон: gateway 854 passed / 5 ignored (STAB-01); Python client/control
194 PASS, CPython2.7.3 61 PASS / 3 host-only skips; Python P09E 75,
регрессия P04/P09D 216, web P09E 5/5 (P09E-M). Доказательства — `local/evidence/2026101[45]-*`.
