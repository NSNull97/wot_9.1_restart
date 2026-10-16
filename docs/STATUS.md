# Состояние проекта — 2026-10-16

Короткое текущее состояние. Полная история карточек до этой даты удалена из рабочего
дерева и доступна в git: `git show 1eaff5e:docs/STATUS.md` (а также удалённые
`docs/plans/`, `docs/evidence-index/`, `docs/archive/`, `MASTER_PLAN.md`).
Следующий шаг — [ACTIVE_GATE](ACTIVE_GATE.md), порядок — [IMPLEMENTATION_ORDER](IMPLEMENTATION_ORDER.md),
практика — [DEV_NOTES](DEV_NOTES.md), факты — [research/INDEX](research/INDEX.md).

Текущая NET-02 в `codex/net-02-private-lan` от P10B6c6b7b7/e55ba01:
explicit RFC1918 native Login/Base + /32 allowlist, privateHTTP loopback,
client lan-test-v1/original transport. Focused17PASS/build; CPythonauth6/
network9/training15/mapdrive61PASS/3oldhostskips, host64+14+59/prepare5/web7PASS.
Full01/608bb23 **1414PASS/5ignored/buildPASS/794rawexact**,542.04с; tag
net02-private-lan-20261016-01. Actual ownhost Login/Base/room/Ready/Leave PASS,
45.391с;NET C44/D45/БКunchanged/active0,sourceP10B43/44 unchanged,ownstop PASS;
native/twoPC/firewall/hosting NOT_RUN; layoutcheck FAIL на прежнем cache.
[План](plans/NET-02.md), [факты/границы](research/NET02_PRIVATE_LAN.md).

STAB-01 принята/mainffce8cb: runtime0574ab0/854tests/5ignored/buildPASS,
actual error containment и owner два manualleave/repeat/управление. Ошибка боя
не закрывает сервер/сессии. [Факты](research/STAB01_BATTLE_STABILITY.md).

P08B в `codex/p08b-profile13-battle`, runtime5c08ef5/893tests/5ignored/buildPASS;
writer28/Web7+18/client314/CPython81PASS. Owner оба ангара16ББ/repeat;
actual два цикла18→16→14,8shots/4manualleave, queuecancel/requeue PASS.
Actual crash active14→recovery один aborted_restart/возврат14, прежние7finished
unchanged, оба native hangar/cache/model/AP14. Owner postrestart/mutation
warmN→full1/refusal/ИС7 NOT_RUN до утра; в main не слита.
[Факты и ограничения](research/P08B_PROFILE13_BATTLE.md).

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

P10B в `codex/p10b-native-training-room`,docs6c6b7b7/runtimee55ba01:
**1397PASS/5oldignored/buildPASS/785sourceexact**,tag p10b-host-20261016-02.
Actual Session/Host/Controller/Preparing/Finished интеграция и clean-env CLI1/
HTTP3 PASS. Minimumsocket room-startup02: обе Ready через настоящие HTTP/SQL,
комната/стороны/отказы/выход/повтор, без reserve/mutation PASS. Phase2
room-durable01: Admit2→launchcommit→оба disconnect до Worldstart→Finished2,
exact SQL journals/Frozen/CAS, повторный Login/комната PASS. C43/D44,
БК[0,4,10]/active0; свои службы остановлены. Native/UI/Avatar/Worldstart/6clients
NOT_RUN. CoreV7 сохранён. Новый client_v2 helper10PASS отдельно перенесён;
positivebind/install/native NOT_RUN. [План](plans/P10B.md),
[утренний сценарий и evidence](NIGHT_REPORT_20261016.md).

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

Последний полный прогон main: gateway 854 passed / 5 ignored (STAB-01); Python client/control
194 PASS, CPython2.7.3 61 PASS / 3 host-only skips; Python P09E 75,
регрессия P04/P09D 216, web P09E 5/5 (P09E-M). Доказательства — `local/evidence/2026101[45]-*`.

