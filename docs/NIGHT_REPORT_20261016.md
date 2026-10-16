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

Текущая ветка продолжает P06T WT/FV physical foundation: `c25fb84`,4actual
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
| P10B | active ветки реализации ещё нет | Только ignoreddomain/nativecodec/aliases component33PASS, originalsource staticproof | Productionroom/selectedteamvector/own404causalbarrier/nativeNOT_RUN |
| NET-02 | active ветки реализации ещё нет | Только исходный preflight/report | LANbind/allowlist/redirect/firewall/2ПК/hostingNOT_RUN |

Первый боевой тест ещё не подготовлен: программные P06T/P10B/NET-02 gates
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
