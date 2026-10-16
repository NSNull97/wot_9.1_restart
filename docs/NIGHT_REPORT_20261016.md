# Ночная реализация 2026-10-16 — рабочий утренний отчёт

Цель: пройти утверждённый порядок без ожидания ручных проверок, сохранить код,
автоматические доказательства и воспроизводимый стенд. Оригинал #717 read-only.
Main/origin остаются `ffce8cb660e9e6af6872aa4a5de444f461bc73fe`; непринятые
карточки в main не сливались. Этот отчёт обновляется по фактическим результатам.

**Готовый для утренней ручной проверки core:** tag `p06t-core-20261016-01`,
runtime `9920a638080c9ae6c3bc5b362646a4e1b414e665`, полный1096PASS/5oldignored/
buildPASS,683sourcefiles before/after exact. Оба настоящих клиента загрузили
hangar/cache/model по трассе; UI/управление/бой этого core ещё NOT_RUN.
V7 установлен в обе исследовательские копии, свои процессы остановлены.

Сохранённый P06T WT/FV physical foundation: `c25fb84`,4actual
RustIPC/scalar/ACK tests/buildPASS, canonicalphysics/Python/negative/legacy
PASS. **Full04:1100PASS/0FAIL/5oldignored/buildPASS**,692sourcefiles before/after
exact,340.80с; tag `p06t-physics-20261016-01`. Crew6/sourcecaps7/policyv2
подключены отдельным компонентом: focused11 **105PASS/0ignored/buildPASS**,
43.95с. Full05 на9080c47: **1111PASS/5oldignored/buildPASS**,341.89с,
695sourcefiles before/after exact; tag `p06t-devices-20261016-01`.
После full05 интеграция VehicleKind7/World LAB/геометрии/наведения сохранена
в09ebe8a;
focused13 **134PASS/0ignored/buildPASS**,159.85с. Exe SHA
`1f1baccc52f5412df85bf08c19b88a9a6520ba3b58dc7b09ceed2794ca68ec3f`.
Focused14:5actual first-contact World tests PASS/build,46.54с: WT→FV560HP,
FV→WT1150HP, frozen HE HESH275→WT1750HP, gun25module-only, exposed31Unsupported.
Synthetic airborne poses отделены от native driving. Полный общий regression/source gate этого слоя теперь закрыт full06. Owned новых машин
не подключён; temporary LAB ammo не считается своим складом.

Новый explicit LABv2 class31 resolver прошёл focused15: **149PASS/0FAIL/
0ignored/buildPASS**,171.93с, включая9 новых source-witness/actualWorld/
rollback tests и отдельный CLI. Старый Unsupported31 default сохранён.
Перенесён OwnedV3 authority component11files: actual freshC/D135.88с,
26tests/2CPython PASS, затем исправлены две actual WAL read races и весь
29tests PASS48.856с. Live router/cacheACK/ownedWTammo ещё не подключены.
Дополнительный template/reset gate прошёл: full06 **1162PASS/0FAIL/5oldignored/
buildPASS**,469.71с/725sourceexact. Runtime0f1db4035849ed4fe7b78adee7a2d49bc6a2cb4c,
tag p06t-world-seven-20261016-01, exeSHA
2c88bb43bec1e757fd7a884ae3af100408ff8f9a3dde2e72e39acfdb9249c0f4.

## Сохранённые ветки и приёмка

| Карточка | Ветка / сохранённый head | Проверенный runtime и реальные автоматические результаты | Не закрыто |
|---|---|---|---|
| STAB-01 | main `ffce8cb` | `0574ab0`,854gateway/5ignored/build; owner manualleave обоих/repeat/управление | Причина редких physics deadlines остаётся отдельным долгом |
| P08B | `codex/p08b-profile13-battle` / `c7999e6` | `5c08ef5`,893/5/build; writer28/Web7+18; owner18→16→14,8shots/4manualleave/2cycles; queuecancel/requeue; actualcrash/recovery/AP14/nativehangars | Owner postrestart/mutation warmN→full1, native refusal/ИС7 |
| P08C | `codex/p08c-battle-lifecycle` / `2ef781f` | `8c96580`,919/5/build; writer10+18/HTTP5 | Countdown/capture/death/victory/draw/results UI/audio на native |
| P05C | `codex/p05c-shared-physics` / `9f2df41` | `019ed2f`,940/5/build/602sourceexact; actual sharedscene2/6/mixed/scalar/ACK/detach | Native mixedcontact/6clients, ramHP не реализован |
| P07B | `codex/p07b-server-visibility` / `e711844` | `8fecb9d`,975/5/build/607sourceexact; realterrain/staticLOS/packetabsence/epochs | Nativehide/respot; bush/camo/radio/delay отсутствуют |
| P04M | `codex/p04m-five-battle-profiles` / `2340236` | `483bb2b`,1006/5/build/634sourceexact; source/actualJolt/new3/ownedcrew+ammo/Web10/Python17+1+28 | Native3newqualification, admissionfalse |
| P06T | `codex/p06t-mixed-shell-damage` / см. текущий git | core `9920a63`:1096/5/build/683 exact; Python21+old28/Web4+old25unique/client2.7.3 9+20+61PASS/4hostskips; physical `c25fb84`:1100/5/build/692 exact; devices `9080c47`:1111/5/build/695 exact | Новый бой/UI/audio/critical/fire, WT/FV native qualification, owned router/cacheACK/stock |
| P10B | `codex/p10b-native-training-room` / foundation `95ceb73` | Actual hangar decoder shim + bounded domain/codecs/aliases:51PASS/0ignored/buildPASS. TeamPlan/actualscene3v1+1v3/list-preview/auth-floor/selection35PASS/build; rootSQL9PASS | Actual Session/Registry transaction, selection HTTP/writer saga, native room NOT_RUN |
| NET-02 | active ветки реализации ещё нет | Только исходный preflight/report | LANbind/allowlist/redirect/firewall/2ПК/hostingNOT_RUN |

Первый боевой тест ещё не подготовлен: программные P10B/NET-02 gates
не закончены. Указание не ждать ручные проверки не превращает их в PASS.

## Что изменено и проверено

P06T core: source-bound24shells/8mounts, три стека/current/next/clip/reload,
frozen projectile, APCR/HEAT/HE LAB solver, actual mesh/terrain LOS splash,
module/crew proxy/fire и единый HP/death ledger; version2reserve/result/restart
с атомарным расходом каждого типа и owner/public publication epochs.
Ключевые файлы: `server/gateway/src/battle/{armament,profile13_v2}.rs`,
`server/gateway/src/shared/{p06t_world,p06t_damage,p06t_device_state,
p06t_publication,model,impact,profile13_queue,profile13_dispatch_v2}.rs`,
`tools/p06t_mixed_{store,projection}.py`, `tools/p06t_terminal.py`,
`web/src/p06t-mixed.mjs`, VERSION7 clientpatch и соответствующие тесты.
Полный список: `git diff --name-only 2340236..p06t-core-20261016-01`.

После исходного core найдены и исправлены HE→wreck→splash Trace anchor,
hidden-primary explosion privacy, duplicate/changedJoin/Cancelv2 и commandbudget.
Новый Join при исчерпании бюджета получает отказ, последняя команда оставлена
для durablefinish. Девять regressions проверяют фактические reliable packets,
actual SQLitecancel/replay и rollback ACK/compound, не только временный outbox.

WT128/FV183 physical foundation: новый versioned importer
`tools/p06t_extended_profiles.py`/sourcepins; `server/physics/ExtendedVehicleProfiles.cs`,
`ExtendedProfileQualification.cs`/отдельные definitions; узкие C# dispatch changes;
Rust physicalKind/Profile7/SceneManifest3 и два измеренных qualifiedprofileJSON.
Новые4теста в `server/gateway/src/drive/scene_worker/tests_p06t_extended.rs`.
`VehicleKind::ALL`, World и owned admission остаются5; физическая квалификация
новых двух машин не открывает им боевой допуск. Старые manifests1/2 строгие.

Реальные physical gates:2profiles×3yaw actualgetters+analyticbox/tensorbasis;
7Python source tests;8negative actual worker starts withoutREADY; flat5/map5/
catalog3component checks; старые5×91=455полных кадров побайтово равны. Контакт
WT/FV max0.0125918м при неизменном допуске0.05м, STOPdrift0. Rustпроверил151
кадр WT,151FV и906actorframes mixed6 прежним scalarFrameProof/final_motion
до реального ACK. Повреждения битов/тензора/последней строки отвергаются.

Честные промежуточные FAIL сохранены: corefull01прерван по HE+wreckbug;
focused08новые тесты неверно наблюдали drainedoutbox (86PASS/4FAIL), focused09
усилен actualpacket и прошёл90. Physicalmap01/customspawnmap02 не прошли;
finalmap03 с realcatalog/lane прошёл, допуски не менялись. Metadatawrapper
первого rootgettercapture исправлен и genuinequalification повторена.

## Доказательства и команды

Все пути доказательств ниже — внутри D:/WoT_9.1_Server, данные остаются local:

- `local/evidence/20261016-p06t-full03/source-{before,after}.json` и
  `local/build/server/gateway-p06t-full03/{result.json,test.stdout.log}`.
- `local/evidence/20261016-p06t-queue03/` — actualwriterfixture/freeze/failure;
  `local/evidence/20261016-p06t-owned01/` — Python/HTTP/Web receipts.
- `local/evidence/20261016-p06t-extended01/` — canonicalrootgetters/source7/
  negative8/455legacy/actualRustbridge. `component-freeze.json`
  SHA`be5172f959444e882d91770bb574fba6ba522d808facb3a60c76779d87c0f191`.
- `local/evidence/20261016-p06t-full04/` и
  `local/build/server/gateway-p06t-full04/` — отдельный общий gate1100PASS/
  5ignored/build/692sourceexact наc25fb84. ExecutableSHA
  `a2f7dea23dde083978fa6215fa721dc24639de2be76fb21693baf466696b908c`.
- `local/evidence/20261016-p06t-full05/` и
  `local/build/server/gateway-p06t-full05/` — 1111PASS/5ignored/build/695 exact
  на9080c47. Exe SHA `26b85500cadcfbf86a60c47d3ab8574caad0670e5352d382b1c36900d5a5e599`.
  Компонент63devices/30seats/crew6/v2policy отдельно зафиксирован в
  `local/evidence/20261016-p06t-device-v2-01/component-freeze.json`.
- `local/stands/night-battle-20261016-01/mixed-01/runs/native-p06t01/native-hangar-observed.json`,
  SHA`cc201b1e2099c3f76c75ac0092e1d307790e8c23b3c873eccaaca6911306784d`.

Каноническая сборка из чистого сохранённого runtime (всегда свежий out):

```powershell
$env:RUST_TEST_THREADS='1'
python -B -X utf8 server/build.py gateway --test --out local/build/server/NEW_FULL
python -B -X utf8 server/build.py physics --out local/build/server/NEW_PHYSICS
```

Фактический core executableSHA
`7a334e399b39bd6fd5c1bbf8e4feff87eea6f1392582d283b58ed0aff31cbf37`.
Physical canonical DLLSHA
`39900645b1bab6819e47e140add661e7f0c5ab4c7a04992a6f5501f3881f2cfa`.
Exact argv/toolchains/inputs/process exits/receipt hashes сохранены у каждого
прогона; новый каталог не заменяет старые результаты.

## Единый утренний сценарий

Полные commands/stop/rollback находятся в
`local/stands/night-battle-20261016-01/mixed-01/MORNING-core.md`.
Сначала сохранить возможный WIP и выбрать проверенный tag; установка V7 уже
есть, повторять install не надо. Ниже fresh run ещё NOT_RUN:

```powershell
git switch --detach p06t-core-20261016-01
python -B -X utf8 local/stands/night-battle-20261016-01/mixed-01/run.py services --run morning-mixed01 --binding binding-p06t02.json --visibility-v1 --p06t-mixed-ammo
python -B -X utf8 local/stands/night-battle-20261016-01/mixed-01/verify_startup.py --run morning-mixed01
python -B -X utf8 local/stands/night-battle-20261016-01/mixed-01/run.py client --run morning-mixed01 --slot a
# После actual SESSION_ACTIVE A:
python -B -X utf8 local/stands/night-battle-20261016-01/mixed-01/run.py client --run morning-mixed01 --slot b
```

Исходный pool-01 сохранён, mixed-01 отдельная БД без grants: A112/B29, оба
МС1[AP0,HEAT4,HE10], reserves0. Оба nativebootсостояния OBSERVED по трассе;
визуальные элементы и игровые действия ими не подтверждаются.

1. Ангары/БК, Aочередь→отмена→снова, затем Bjoin. Countdown30с не расходуетБК.
2. После старта оба едут/поворачивают/наводят; каждым ровно1HEAT+1HE в землю,
   оба вручную Esc→ангар. Ожидается[AP0,HEAT3,HE9] total12. Повторный общий бой.
3. Отдельные natural capture/victory/draw/death/results→ангар→повтор/relogin;
   штатный таймер900с. HE splash/LOS/critical/fire/crewdeath и UI/audio наблюдать.
4. Contact/parkedwreck и hide/respot; mixedИС7/MS1 по родительскомуMORNING.md.
   Новые3 P04M — отдельные temporaryqualification, admissionfalse. Sixnative
   ещё требует дополнительных настоящих аккаунтов/окон, synthetic6не заменяет.

Перед любым новым native run не использовать diagnosticlogin_smoke в том же
run: он создаёт собственные pending sessions. Служебные интерфейсы loopback.

## Ограничения, откат и следующий шаг

Приёмка P06T **не закрыта**: WT/FV source/scheduler/physics не заменяют World/
crew6/Aim/owned/native integration; GunBreech31 покаUnsupported. LAB proxy/fire/
penetration/LOS не объявляются историческим serveralgorithm. Не реализованы
ammoBayexplosion/turretdetach/repair/исторический разброс урона; native UI/audio
новых эффектов NOT_RUN. Legacy/Pythonwhole/rustfmt хвост не закрывался.

Все свои native-p06t01 clientB/A/gateway/bridge остановлены через PID receipts.
Откат последней foundation — чистый checkout coretag и его matchingbinding.
Откат P06T целиком — rollback новых clientledgers, сохранённые P04M branch/
binary/sourcebinding и целый pool-01 backup; без schema downgrade/ручного
смешивания таблиц. Main остался прежним, original не изменён.

Единственный следующий рекомендуемый **software** шаг: подключать source-bound
WT/FV combat/crew6/Aim/encoding к World с
новыми versioned contracts. Ручной сценарий выполняется утром независимо.

## Закреплённый World7 и отдельный extended стенд

Full06 proof: `local/evidence/20261016-p06t-full06/source-{before,after}.json`;
component receipt: `local/evidence/20261016-p06t-world-seven-01/component-freeze.json`.
Повторение: `RUST_TEST_THREADS=1 python -B -X utf8 server/build.py gateway --test
--out local/build/server/<fresh>`; новый output обязателен. Полный прогон занял
469.71с tests, compilers запускались отдельно штатным build.py.

`local/stands/night-battle-20261016-01/extended-01/MORNING-extended.md` теперь
содержит точный full06 runtime/source restore и дальнейшие overlay команды.
Root actual bind/start/ownstop WT128 и FV183 PASS: оба загрузили7 genuine
resources и explicit LABv2, UDP20142/20143. Proof `startup-root01.json` в стенде.
Сверены107 runtime resource files,106 исходных core/client/ledger/config inputs
после запусков byteexact. Клиенты/coreV7 не менялись, новых grants/DB/identity нет.
Both gateways STOPPED. Source restore audit725/6closed readonly helper gates
PASS; применение на checkout NOT_RUN. Реальная подготовка нового overlay
пока NOT_RUN: prepare корректно отказывает уже установленным coreV7 targets.
Сначала ручной core test, затем точный rollback ledger и штатный prepare/install
по prospective argv; обхода installed-target guard нет. Повторять core install
или existing extended bind не нужно.

P06T native/UI/audio и новые owned WT/FV admission остаются NOT_RUN, main не
изменён. По ночному разрешению после сохранения этого автоматического результата
следующая реализация — отдельная зависимая ветка P10B. Текущий first combat test
всё ещё не готов до production P10B/NET-02 и общей ручной приёмки.


## Текущий P10B checkpoint

Foundation95ceb73 включает native ingress17commands, bounded domain, monotonic
aliases и actualhangarshim; focused01=51PASS/0FAIL/0ignored/buildPASS. Изменённые
файлы находятся в `server/gateway/src/training/`, регистрация — `main.rs`, shim —
`account/hangar.rs`. Default старых режимов сохранён, живая room route ещё закрыта.

Следующий слой добавляет immutable TeamPlan с выбранными сторонами и qualified
spawn lanes при неизменном actor identity slot, outgoing list200/preview201 через
существующий hangarstream helper, generation floor после retired auth. Исходный
floor bug воспроизведён:3RED, fixed17PASS прямым rustc. Actual selection reader
отдельно прошёл9SQL tests/0skip47.671s и выдал4 writer-vectors MS1/IS7; incoming
Frozen/paths не принимаются. Он ещё не HTTP route. Actual saga6SQL cases PASS,
Rust bridge не подключён. Client VERSION8/training guard исследуется отдельно.

Focused02 остановился на неверном имени enum в новом тесте. Focused03=29PASS/
3FAIL/0ignored: тесты не вызывали advance_lifecycle, export требовал harness env.
Эти результаты сохранены, ожидание actual scene fracture/ACK не ослаблено.
Focused04 выявил boundedradius/clock ошибки новых тестов; focused05 — ненужный
serde derive (в проекте процедурные macros не включены). Исправлены тестовые
границы и явный strict Stamp parser без новых dependencies. Focused06:
35PASS/0FAIL/0ignored/buildPASS, actualscene3v1+1v3/realfractureACK и4actualSQL
writer-vectors. Root повторил promoted selector SQL:9PASS/0skip47.204s.
Full P10B gate ещё NOT_RUN.
Own native/service processes core/extended остановлены; установленные coreV7
и оба сохранённых source tags не менялись. Main merge не выполнялся.

P10B follow-up: actual Session collector preserves full compound-frame order,
legacy decoder once, ACK/history rollback and deferred outbox offsets. Actual
Session fixed streams200/201 use all body ACKs, independent prior/suffix frames,
monotonic preview aliases, and existing warm Account generation as separate
callback origin. AuthLease remains actualSession.id; Account generation changes
on warm return. Default old routes do not activate these helpers.

Saga now issues its own exact Inspect task after drain; denial revision40 fences
old no-reservation39. Opaque parsed Selection cannot be constructed/mutated by
other runtime modules. Actual saved6SQL/40DTO corpus +4selection samples test
strict codec and scheduling; Fresh in Rust scheduling tests is explicitly an
authored cache fixture. Focused11=64PASS/build; focused12=65PASS/build includes
warm-origin fence (exe615651f23b46a71bf3dfc63571e66d01e2ea07594088f7589f4dfbf8d0a30443).
Focused10 tested54/build but an unused worker module was added between test/build;
it is not treated as an immutable source gate. Source-stable focused11/12 replace
that limitation. Fresh owned selection HTTP client/job compiled, endpoint itself
is not yet connected; candidate actualHTTP3PASS/0skip74.091s remains separate.

Client VERSION8/enable_training_rooms delegates original native PRB callbacks,
preserves original tooltip/readiness and initializes original arena services.
Root actual CPython2.7.3:79total=76PASS/3previoushost-onlyskips; hostnew15PASS.
No prepare/install/client launch. All core/extended installed clients preserved.
Actual wholeTable+Registry publication, live writer coordinator and native room
remain NOT_RUN. Next work remains P10B; NET-02/tail have not started.

P10B full02 на1df690a: **1269PASS/0FAIL/5oldignored/buildPASS**,760 runtime
inputs до/после exact; exe cb7af11cdc37530141bbb5377d7ae9a7982696b25ce06c7f8bef33014f432efb.
Путь evidence `local/evidence/20261016-p10b-full02`. Затем promoted actual
Controller/native publication, Ready preservation across side/settings, HTTP
selection route, Session callback namespace12tests и optional durable Finished
hook5actualSessiontests. Focused17=110PASS/0FAIL/0ignored/buildPASS, exe
bab99d06157427dff339a5545315c5077373e660c10f190d47a7e5103411bf13.
Evidence `local/evidence/20261016-p10b-components02`. Новые helpers ещё не
соединены с live serverloop; флаг training_rooms определён, не активирован
на стенде. Full этого последующего head и native room NOT_RUN. Сохранены
отдельно предыдущие compile/test FAIL; они не обозначены как PASS.

P10B wholeSession receiver теперь проверен10actualSession/Window tests: full
compound ACK/namespace/latepeer rollback, ordering, busyfixedstreams и warm origin.
Повторный402 отзывает прежний ReadyRef+teamvotes до следующего411; selective
completion держится до atomicnativepublication. Focused19=122PASS/build.
Atomiclaunch/Preparing serialdriver и training-only nullInspect Fresh собраны:
focused21=137PASS/0FAIL/0ignored/buildPASS; exe
d12ee9bf2fec876f7c0ebc2f6af1e0befac1d8ff9fcc96ad924345e7062ccb5d.
ActualHTTP03 повторил3PASS/0skip77.768s; main remoteffce8cb сверён и не менялся.
Компонентные launch/driver tests используют strict savedSQL DTO и явно
authored cache/run seam; живой HTTP→Rust→room→launch ещё NOT_RUN. Rootсоединяет
serverloop и сохраняет native/UI/control NOT_RUN.

Current sealedP10Bfull03/36d57a0 (tag p10b-components-20261016-01):1341PASS/
5oldignored/buildPASS,501.62s,775exact sourceinputs. Subsequentfocused22=
164PASS/0FAIL/0ignored/buildPASS,exe6f64381dabe0a38202efb636ed026ca177dd52d2c9681588c2bee292b569da8e.
Includes actualquery-onlySQLprojectedC/D readiness8 tests (no grants/reserves),
simultaneousReady policy6, actualResults/queue-isolation12 andBusylaunchcallback.
These are component checks; actualserverloop Host and retained Preparing
selected/bench disconnect handling are the current integration work. Native
room/start/return NOT_RUN; no new client overlay/standdeployment.

P10B integration checkpoint: actual liveHost/serverloop connected, retained
Preparing selected/bench metadata and common garage/results retirement boundary
added. Warm exactSession Account List/Preview retains Battle claims. Focused24
compiled and ran190:189PASS/1FAIL/0ignored; one new test expected a departed selected
member to remain after compensated abort. Corrected to exact surviving creator,
without production policy relaxation. Four service-routing checks passed. Full04
of the corrected committed runtime remains required. Fresh lightweight C/D
room stand is prepared separately; native overlays/clients are untouched.
