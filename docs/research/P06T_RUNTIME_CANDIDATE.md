# P06T — кандидат mixed-shell, модулей, экипажа и пожара

2026-10-16. Зависимая ветка `codex/p06t-mixed-shell-damage` от сохранённого
P04M docshead `2340236a1e690e36d617130c054e2ce7e62f685e`. Предшествующий
P04M runtime483bb2b прошёл1006 gateway tests/5 старых ignored/build и сверку634
source files. Это исходная точка, а не результат проверок нового P06T.

Цель кандидата: authoritative выбор/расход исходных трёх stack, замороженный
снаряд, direct/splash/fire HP через один ledger, module/crew state и его
ограниченные последствия для управления, результаты и возврат в ангар.
Оригинальный клиент здесь только прочитан. **Native/UI/audio/ручная приёмка —
NOT_RUN; main не изменён, карточка не принята.**

## Исходные факты и явные допущения

**VERIFIED SOURCE:** закрытый каталог8 mounted guns/24 shot rows получен из
24 закреплённых оригинальных файлов #717. Семейство, compactDescr, HP/device
damage, penetration pair, speed/gravity, explosion radius, ёмкость и mounted
reload сохраняются раздельно. Например, T34-85 S54 имеет AP115 и APCR110;
MS1 HEAT raw speed354 против AP442. Эффективные speed=raw×0.8 и
gravity=raw×0.8² повторяют установленные исходные операции.
Полные таблицы и pins — [P06T_DAMAGE_SOURCE](P06T_DAMAGE_SOURCE.md),
`local/night-staging/20261016/p06t-shells01/REPORT.md`.

**VERIFIED SOURCE:**5 stock профилей дают45 max/maxRegen pairs и19 primary
crew seats; совмещённые обязанности не создают новых мест, оба заряжающих
ИС-7 остаются отдельными. Упорядоченные extra26..34: engine, ammoBay,
fuelTank, radio, leftTrack, rightTrack, gun, turretRotator, surveyingDevice.
Source caps JSON SHA256:
`3c4219c2adda799677dea310e84765bbfebca6edfa06aa3db450a7ddfb4875b5`.
Policy JSON SHA256:
`cded466bf3c21243c10c0bcee8a013ab4cffc20f31f7275d4eab1672060b3717`.
Файлы: `shared/p06t_device_source_caps.json`, `shared/p06t_device_policy.json`.

**VERIFIED STATIC, не captured native:** полный fire property имеет VAR1
envelope `a5 05 01 00 00 00 04`, снятие — `a5 04 00 00 00 00`.
Четвёрка является индексом fire в ARRAY extras, не битовой маской.
Инструкции original PE, callback размера и signed32 ARRAY count разобраны в
[P06T_FIRE_PROPERTY_ENVELOPE](P06T_FIRE_PROPERTY_ENVELOPE.md); частичные
ARRAY updates не квалифицированы. Остальные новые численные method IDs
остаются source/table inference до настоящей доставки клиенту.

**UNKNOWN HISTORICAL:** серверные внутренние hit volumes, layered armor/
spaced armor/continuation solver, распределение penetration/damage RNG,
историческая последовательность reload callbacks и полный модульный damage
algorithm. Клиентские XML/descriptor/UI predictors этого не доказывают.

## Контракты и политика кандидата

Включение явное: server `p06t_mixed_ammo=true` в profile13/P04M chain и
client prepare `--enable-p06t-mixed-ammo`. Старый v1/AP route сохраняется;
typed path не принимается через старый API случайным fallback.

`battle/armament.rs` владеет тремя количествами, current/next, clip/reload и
монотонными часами. `World::attach_owned_v2` принимает проверенный v2 Frozen
писателя; нулевой AP допускается при ненулевом другом собственном stack.
При `Shoot` immutable source Shell сохраняется в Projectile и admission
Trace. Дальнейший выбор не меняет полёт, effects, damage или source identity
уже принятого выстрела. `Replenish` не выдаёт боеприпасы.

`p06t_damage.rs` — **EXPLICIT LAB** single-plate formula:

| Семейство | Нормализация / рикошет | Прочие границы |
|---|---|---|
| AP |5°,70°; усиление при2× и overmatch3× | совместимые с прежним lab AP границы |
| APCR |2°,70°; та же lab2×/3× политика | собственные source power/damage/speed |
| HEAT |0°,85°,без overmatch | power constant; source0.05 distance field units UNKNOWN, не домыслены |
| HE/HESH |без нормализации/рикошета | strict penetration даёт source damage; иначе отдельная lab attenuation |

HE attenuation: `floor(max(0, 0.5*damage*(1-distance/radius)-1.1*armor))`.
Это придуманная закреплённая формула, а не восстановленный оригинальный
сервер. Историческая damage variance не реализована; source base фиксирован.

`geometry::Bundle::proxy_ray` заново проверяет first actual source triangle,
точку/нормаль/материал, pose digest и geometry revision. Proxy начинается в
**component-local точке настоящего контакта** и идёт до forward AABB exit.
Native `ImpactSegment.start` может стоять раньше поверхности и для этого не
используется. Тело legacy `impact_segment` сохранено неизменённым, source SHA
`64f6fc0035056b2696023619ccc3336fd8f8eb56230a2ed3af56d558c65bc3ae`;
это отдельно зафиксировано как source preservation, не как новый native gate.

`p06t_lab_proxy.rs` использует явно придуманные нормализованные AABB boxes
внутри настоящего component bound. Выбираются максимум два ближайших
device/seat hits, порядок при равенстве стабилен. Ни эти boxes, ни nearest-two
не объявляются историческими объёмами. `State` хранит только device/crew/fire
и возвращает переходы; **vehicle HP владеет исключительно World**.

`Bundle::explosion_contact` строит center→posed source-hull-center ray и
возвращает только реальный первый source triangle/material в source radius.
Это lab first-surface query, не доказательство исторического выбора ближайшей
точки взрыва. Внутренний/нулевой центр имеет ограниченный детерминированный
fallback; пересечение AABB не заменяет triangle hit. World и Trace независимо
перепроверяют actual surface, distance и terrain/static LOS. Удалённые
объекты берутся через `projectile_excluded`; self-contact offset1мм — отдельная
именованная lab policy. Авторский `los_clear=true` вне actual query не
является достаточным доказательством урона.

Отдельный gate `test_lab.p06t.plate-penetration-or-exterior-gun.v1` разрешает
device-only hit для настоящего source GunVisualMaterial25/name gun, правильной
компоненты/revision/extra gunHealth32 и nominal power выше source gun armor.
Все5 canonical bundles это связывают с исходным common vehicle.xml SHA
`599ea82e48e98bf9a00c10256030097da31ce5d5889fa03737bc3b79230d256a`.
Gun armor по порядку MS1/IS7/T26/T34/T34-85:10/60/10/20/20.
Source `vehicleDamageFactor=0` сохраняется: plate outcome Unsupported,
изменение vehicle HP равно нулю. Source chance0.33 не превращена в исторически доказанный
алгоритм; admission устройства здесь явный LAB.

## Модули, огонь, часы и единый результат

`p06t_device_state.rs` фиксирует критический порог≤половины source maxHP,
capability multipliers и bounded fire как LAB policy. Source maxRegen не
используется вместо критического порога. Source engine chance0.2/0.15 и
minFireStartingDamage21 сохранены как данные; условие ignition, burn rate и
детерминированный World SplitMix64 не заявляются историческими.
World сохраняет seed, каждый draw и причинный shot/attacker/ordinal.

Fire стартует не более чем на10 ticks с шагом1с. Повторный ignition сохраняет
первую причину и не продлевает срок. За tick предлагается ceil(maxVehicleHP/20)
с ограничением остатком настоящего HP; engine/fuel damage также именованная
LAB политика. Catch-up ограничен10 ticks. Перед новыми hits World сначала
дренирует старые fire ticks; противоположная хронология явно отклоняется.
Полный mixed World advance идёт на клоне: ошибка последнего contact/material/
Trace не оставляет частичные HP, devices, RNG или clocks.

Один `damage_events` ledger обслуживает direct/splash/fire и crew death.
Все реальные primary seats мертвы → actor inactive, даже при положительном
HP. HP не подделывается нулём. Gameplay закрывается, retained source geometry
остаётся препятствием для следующего снаряда без нового урона/смерти.
Lifecycle outcome замораживает состояние; поздние снаряды и fire ticks не
дописывают результат.

Реальные эффекты capabilities подключены к runtime: engine/tracks/driver —
IPC7 controls; turret/gunner — Aim rate; выбранный Shell — баллистический
прицел; ammoBay/loader — remaining reload; optics/commander — view range.
Сложные cruise values приводятся к допустимым25/50/100, reverse/steer fractional
policy передаёт и журналирует фактический duty pattern. Radio не имеет модели
радиопередачи в P07B; dispersion не имеет квалифицированного распределения.
Одно наличие этих полей не считается реализованным игровым эффектом.

Publication отправляет owner-only module/seat notifications, public crew/fire
и HP только через актуальные P07B epochs. Скрытый attacker не выдаётся в
private HP/device payload. Hide/reveal восстанавливает текущее состояние без
повторения старого выстрела/критического события. V2 terminal journal содержит
exact crew IDs, ordered devices с source maxima, fire counters, first death и
roster size; writer проверяет также расход каждого stack и full results.
Нет складских grants, бесплатного refill, economy reward или нового допуска
машины вследствие этого journal.

## Реально выполненные проверки

| Проверка | Фактический результат / доказательства |
|---|---|
| Pure damage/device/proxy/source snapshot |19PASS, `local/night-staging/20261016/p06t-damage01/active-checks01/` |
| Аудит оригинальных caps |10 file pins,5profiles/45devices/19seats PASS, `local/evidence/20261016-p06t-device-source02/` |
| Output boundary аудитора | outside-local output отвергнут exit2, ничего не создано; `.../p06t-damage01/audit-cli02/result.json` |
| Exterior gun source gate |5 exact bundles/common XML PASS_STATIC_SOURCE, `.../p06t-damage01/exterior-gun-audit01/result.json` |
| Focused02 | compile,63PASS/1FAIL из-за вызова legacy fire API в typed test; логи сохранены |
| Focused03 | FAIL compile нового publication fixture (enqueue return type/import), не runtime PASS |
| Focused04 |72PASS/2FAIL/0ignored; actual Jolt destroyed-engine/healthy движение PASS; обе ошибки в новых World fixtures |
| Исправления после04 | wreck comparison исключает observed clocks; gun fixture проверяет фактический launch ray, исходный strict gun gate сохранён |
| Focused05 |74PASS/0FAIL/0ignored,31.88с,buildPASS; все8 World tests PASS, включая actual gun и positive-HP crewless wreck |
| View-scale World test после05 | source240m baseline→optics120m/commander180m при target200m, focused06 PASS |
| Full01 head3a059f1 | запущен с681 source files, остановлен по найденному HE+wreck Trace edge; **NOT_PASS**, receipt сохранён |
| HE+wreck World test после05 |3 actors, HP0/HP90 inactive wreck и actual nearby splash, focused06 PASS |
| Focused06 |80PASS/1FAIL/0ignored; все10 World tests PASS, один protocol late-anchor poison FAIL; общий build gate не PASS |
| Focused07 |81PASS/0FAIL/0ignored,31.34с,buildPASS;10 World tests, source-bound wreck anchor/terminal/poisons и2 publication privacy/epoch regressions PASS |
| Focused08 |86PASS/4FAIL/0ignored; новые queue tests ошибочно наблюдали drainedoutbox вместо фактического reliable packet, build NOT_RUN |
| Focused09 |90PASS/0FAIL/0ignored/buildPASS;9 queue v1/v2 flow regressions проверяют actual reliable frame, durable cancel/replay, busyJoin и budget511/512 |
| Full02 head dc27285b |1087PASS/0FAIL/5 старых ignored/buildPASS; source-before/after681 exactPASS, `local/evidence/20261016-p06t-full02/` и `local/build/server/gateway-p06t-full02/` |
| Queue corrections после full02 | union v1/v2 reservation/duplicate guards, durable cancel→fresh callback и command512 bound; покрыты отдельным full03, не приписываются1087 |
| Full03 head9920a638 |1096PASS/0FAIL/5 старых ignored/buildPASS; source-before/after683 exactPASS, `local/evidence/20261016-p06t-full03/` и `local/build/server/gateway-p06t-full03/` |
| Full04 headc25fb84c |1100PASS/0FAIL/5 старых ignored/buildPASS,340.80с; source-before/after692 exactPASS, tag `p06t-physics-20261016-01` |
| Текущий binding/утренний native цикл | отдельный текущий startup/owner gate; native **NOT_RUN** |
| Native/UI/audio/полный утренний цикл | **NOT_RUN** |

Focused04 прошёл actual first-contact→Trace→LAB module→singleHP ledger,
T34-85 AP/APCR source difference, groundHE splash с реальной blocking triangle,
whole-World rollback, actual SQLite AP0 admission/current/airborne Shell и
fire HP ledger/terminal freeze. Wreck fixture ошибочно сравнил advancing
observed clocks; gun fixture попал настоящим выстрелом в armor_2 вместо gun,
хотя другой вспомогательный ray видел barrel. Оба FAIL сохранены честно;
focused05 прошёл оба исправленных runtime assertions без ослабления source
gate. Полные логи: `local/build/server/gateway-p06t-focused{02,03,04,05}/`.

World tests используют реальный проверенный SQLite v2 admit reply с AP0/
HEAT4/HE11; его fixture SHA
`0e293febb5e3053e34f5b543c19aa2f7420918415b22595aaa4bb16e532b2c21`.
Остальные actor loadouts/предшествующие crew casualties/engine ignition в
отдельных сценариях — явно авторские cfg(test) LAB fixtures. Ground/wall
triangles — контролируемая тестовая сцена, не native приёмка настоящей карты.
Таким образом, fire tick/ledger/terminal и wreck блокировка проверены в
production World; историческая случайность первичного внутреннего попадания
этими фикстурами не доказывается. Другой тест отдельно проходит настоящее
source exterior intersection→Trace→proxy→device mutation.

Standalone19PASS относится к закреплённому snapshot в его receipt, не
автоматически ко всем последующим изменениям Aim/geometry/World. Exact argv,
toolchains и source pins находятся в каждом result/test.command receipt.
Gateway exe focused05 SHA256:
`bb451571bb4f85b0a3222d83688701f45c858ebec838356ad14ba63eb2ac6959`.
Gateway exe focused07 SHA256:
`cd8a9f62a9d0e457186595a5a81eacad0e185fa031745ea4e56b16be177c53e3`.
Дополнительные view-range и HE+wreck World tests написаны после focused05
и не включены в74.
Каноническая команда focused gate:

```powershell
python -B -X utf8 server/build.py gateway --test --test-filter p06t_ --out local/build/server/gateway-p06t-focused05
python -B -X utf8 tools/p06t_device_source.py --original-root C:/WoT_0.9.1_RU_0717_original --out local/evidence/20261016-p06t-device-source02
```

Output directories должны быть свежими; существующие receipts не перезаписывать.
Первый пример выполнен в focused05. Full02 затем прошёл1087 tests/build и
сверку681 source files для dc27285be170e57ff12ad78babce8f5e589d3f93.
EXE full02 SHA256:
`c229d44badb5891ac5fb4502d33603d29a04253c2d29baa54000e973998efe9c`.
Этот результат не переносится на последующие queue corrections. Их отдельный
full03 прошёл1096 tests/build и сверку683 source files для
`9920a638080c9ae6c3bc5b362646a4e1b414e665`; EXE SHA
`7a334e399b39bd6fd5c1bbf8e4feff87eea6f1392582d283b58ed0aff31cbf37`.

Read-only audit после05 обнаружил отдельный дефект: World запускает HE splash
после retained-wreck contact, но Trace принимал explosion anchor только от
MixedResolution/TerrainContact, а wreck terminal требовал последний
WreckImpact. Если рядом оказывалась живая машина в radius, корректный splash
мог завершиться ошибкой Trace. Full01 остановлен, факт не скрыт зелёным74.
Новый regression запускает настоящий IS7 HE в MS1 wreck и рядом живой MS1,
для нулевого HP и положительного HP/погибшего экипажа. Контакт, explosion
center и LOS не подставляются фикстурой. Статус исправления и реального
запуска: focused06 прошёл10 World tests, в том числе обе wreck ветки и view
scale. FAIL в protocol poison8 обнаружил разрешение нового Segment между
WreckImpact и splash; focused07 прошёл81 tests/build после закрытия этого
late-anchor инварианта. Взрыв не подавляется заглушкой. Full02 прошёл1087
tests/build; отдельный full03 с queue corrections затем прошёл1096 tests/build.

Read-only queue audit после full02 отдельно обнаружил границы в смешанных
v1/v2 reservations и callbacks. Исправление должно отвергать changed Join без
неявной отмены старого резерва, не повторять durable cancel и сохранять один
finish command в bounded512 journal. Это новый scope после сохранённого full02,
отдельно проверенный full03, а не часть результата1087. Реальный writer fixture:
`tests/fixtures/p06t-queue-writer-vectors.json` SHA
`6a0dd7856242a0105864de7985ec309c4e25b76616e1a5732102201c2abf580f`;
read-only audit receipt SHA
`516cc6a6d7de378487f401109122c9d1e53a6bed2a5a7cd7e2463f50633ae90b`.

## WT/FV, границы приёмки и откат

VERIFIED SOURCE/компонент scheduler: WT E100128мм clip6/interval2с/reload60с,
150мм clip4/3с/50с; FV215b183 premium HESH — HIGH_EXPLOSIVE275/275,
а не новая физическая family. **Qualified World physics/owned admission этих
машин отсутствуют.** Нужен отдельный versioned catalogue correction полного
цикла China5→3, France3→4, UK4→5. Поправка только UK оставила бы неверный
China ID. Frozen P04M catalogue под старым SHA не меняется.
Нельзя на основании source-only scheduler назвать WT/FV playable/P06T accepted.

Свежий read-only scope audit: `local/night-staging/20261016/p06t-damage01/
wt-fv-scope01/{audit.py,result.json,REPORT.md}`, PASS_STATIC_SCOPE_ONLY.
Rehashed pinned original WT/FV XML, национальные component files и27 небольших
collision members; whole package SHA не пересчитан и не заявлен. Оригинальные
пути установлены фактически: `res/packages/vehicles_german.pkg` →
`vehicles/german/G98_Waffentrager_E100/collision/` и
`res/packages/vehicles_british.pkg` →
`vehicles/british/GB48_FV215b_183/collision/` под тем же проверенным original root.

| Реальная граница WT/FV qualification | Что требуется сверх shell scheduler |
|---|---|
| Закрытые importers | `p04m_battle_profiles.py` принимает3 USSR сборки, `vehicle_physics_profile.py` только IS7. Переиспользуются bounded readers/алгебра, не их готовые profiles/pins |
| Physics/supports | WT20 individual wheels/no groups; FV groups WD_L,W_L,WD_R,W_R. Нужна новая versioned mapping, текущая требует первые W_L/W_R; actual Jolt getter bits/inertia/contact gates обязательны |
| WT assembly identity |128=100000кг/Gun_01,150=97800кг/Gun_02 из actual mass sum; один vehicleCD16913. Нужен различимый assembly/mount либо явно только128 runtime; перепутать profiles нельзя |
| Aim | FV source yaw limits `-45 45`°; WT basic pitch `-15 5`°, rear `-7 5 37`°, explicit transition5°=.08726646rad. Original reader/PE доказаны: обе границы min/max интерполируются; default0.4rad относится только к отсутствующему transition. Текущий360° yaw и rear-only-max/constant-min не выражают это |
| Closed Rust/C# | private physical Profile/scene Kind7 прошли full04; VehicleKind/World geometries[5], resource source_profiles[5], resource manifestv3 exact5 остаются закрыты. Для World7 нужен отдельный versioned startup/resource route |
| Crew/damage | WT6 primary seats, FV5. Новый device component crew6/source caps7/policyv2: focused11 105PASS/build; full05 на9080c47 1111/5/build/695sourceexact. World/PoolCrew/terminal old5 не расширены |
| Owned/native | registry USSR-only, pool ammo closed15, v2 Frozen admission/terminal maxima закрытыMS1/IS7; нужны source descriptors, real SQLite ownership/ammo/crew proof и полный nation cycle China5→3/France3→4/UK4→5 |

WT128100000кг находится ровно на существующей inclusive mass границе;
необходимость расширять её не установлена. Из этих source фактов не следует,
что действующий контроллер, contact tolerance≤5см или native UI уже прошли
квалификацию. Полноценные WT/FV требуют отдельных actual-source import,
getter→scalarFrameProof→World/ACK и owner gates, сохраняя старые5 regressions.

**VERIFIED STATIC SOURCE, экспорт не равен qualification.** В ignored
`local/night-staging/20261016/p06t-damage01/wt-fv-source01/` подготовлены
ограниченный exporter, отдельный xyznuvtb reader, проверки и три derived JSON:
WT128, WT150 source-only, FV183. Текущие выходы `checks03-export/` и byteexact
`checks03-repeat/` содержат настоящие Hull/Turret/Gun vertices/triangles,
sparse material entries, source pivots, exact descriptors, mass sums,9 device
maxima и ordered crew6/6/5. Source profiles не содержат runtime binding:
`runtime_physics=null`, `native_binding=null`, admission/registration=false.
Небольшие JSON численных фактов не заменяют исходные collision assets.

Новый WT disk reader проверяет xyznuvtb header68/stride32 и читает только
POSITION FLOAT3 по offsets0/4/8. Остальные20 bytes остаются opaque; packed
normal DWORD не декодируется как float. Original shader XML и PE converter
подтверждены независимо, GPU destination stride28 не перепутан с disk32.
Index header72/list16-or32/groups16 проверяются отдельно. Proof:
`local/evidence/20261016-p06t-vertex01/result.json` SHA
`9855d66ec4fd9a165be872273112bf81e3c0bc6a04ed3df09f89e31ea89746f7`.
45 exact PE instruction checks/3 shader declarations/5 WT primitive bounds/
1085 triangles — STATIC_ONLY; исходный клиент не запускался.

Aim proof `local/evidence/20261016-p06t-aim01/result.json` SHA
`ad09cc66372a8ba03405128ea1f0a17c4909d622d13ed75ad7f469784e103733`
связывает source XML, original bytecode и native PE f32 limits. На native
границе min/max/sector/transition — radians; explicit XML transition5 сначала
переводится из градусов. Это доказательство source semantics, не проверка
нового runtime Aim. Nation proof
`local/evidence/20261016-p06t-nation-migration01/result.json` SHA
`0179f30b0db3954aaf45c007d67e766cf60c69dff5e027d3aed869745780e0d7`
даёт2494 bijective item IDs,776 изменённых CDs и прежние5 byte-identical
CDs/descriptors; migration/runtime пока NOT_RUN.

Свежая команда preparation gate:

```powershell
python -B -X utf8 local/night-staging/20261016/p06t-damage01/wt-fv-source01/run_checks.py checks03
```

Результат9PASS/2.274с, test runner2.007с, exact argv/stdout/stderr и source
before/after в `checks03-receipt/result.json` SHA
`f326ebb2bcfab09a515b35be42ec2ba872b31ac8361b933e967ebfc59d065787`.
Проверены actual descriptors/mass/clip6vs4/crew/devices; все original mesh
indices/materials; поздний poisoned member и wrong metadata SHA отвергнуты
до публикации; stale/outside output запрещены; экспорт повторён побайтово;
xyznuvtb badformat/count/NaN-position/index/group poisons отвергнуты, NaN bits
в opaque normal не меняют XYZ. Manifest SHA
`d02d53a52ce9e9dcfb6ed3be19108a38e986b697cf77e1435cc468894c6293c1`.

Будущая минимальная physics foundation: отдельный versioned importer и
source-profile definition/loader для WT128+FV183, новый resource manifest,
actual Jolt getter bindings и прежний scalarFrameProof/ACK. WT main W_L0/W_R0
radius0.495184987783432 и FV named W_L/W_R radius0.240187004208565 требуют
явной новой LAB support policy; старый reader policy не расширяется молча.
GunBreech material31 сохраняется как **Unsupported**, не ordinary plate.
Никаких copied native inertia bits, historical hit-volume claims или owner
admission из-за наличия geometry export.

**OBSERVED PINNED PHYSICS COMPONENT, вне core full03.** После source-only
export подготовлен отдельный ignored кандидат `extended-foundation01/`.
Новый definition/profile version2 и policy `p06t-extended-six-support-v2`
реализуют только физические WT128/FV183 names и bounded SceneManifest3.
Actual isolated C# build, source7 tests,8 negative process cases,4 map drives+
mixed6,2 handling/rest и3contact cases,3catalog/witness/ACK cases прошли.
Пять прежних профилей дают455 whole frames побайтово равных прежнему worker.
Два genuine Jolt getter профиля проверены при3 actual yaw каждый, включая
independent analytic box tensor и quaternion basis. Точные pins/commands и
ранние honest map/spawn FAILs — в
`local/night-staging/20261016/p06t-damage01/extended-foundation01/REPORT.md`.
Эти staged gates предшествовали отдельной root интеграции и не включены1096.

Финальный component02 DLL SHA
`693c458b56ec9dbeb6c40bdbf5234f23393abb802c42e15c268785a39d4874c7`.
После baselineSHA проверки всех12 файлов foundation интегрирована в
канонические C#/tools/newtest; отдельный private physical registry в Rust
имеет7 профилей, а **VehicleKind/World/owned остаются прежними5**. Новые
physical names не получают fallbackMS1 и явно Unsupported для owned World.
WT150 не зарегистрирован. Старые manifest1/2 и все5 прежних byte contracts
сохраняют свои проверки; source_profile refs старых3 не переписаны.

Каноническая команда:

```powershell
python -B -X utf8 server/build.py physics --out local/build/server/physics-p06t-extended01
```

BuildPASS; канонический DLL SHA
`39900645b1bab6819e47e140add661e7f0c5ab4c7a04992a6f5501f3881f2cfa`.
Отдельная genuine rootDLL getter requalification сохранила те же measured
численные bits/definition, изменив только qualification worker provenance.
WT profile SHA
`85c810a944828d23d42ea8691142d16dc1cfb1c73156a6c7b7f11723d4dfd777`,
FV profile SHA
`0e9eb47ba39b53592e1f7de6a302521ea8252bdb616df0d8f5dc10d2ab28b516`.
Полные canonical configs/source/getters и receipts находятся в
`local/evidence/20261016-p06t-extended01/`. Первый capture wrapper завершил
измерения, но не сохранил итоговый metadata receipt из-за отсутствующего
artifacts.json после server/build; это сохранено в root-getters03/result.json.
После отдельной генерации complete16-file artifact manifest native qualifier
повторён настоящим процессом с новыми stdout/stderr; оба profile outputs
побайтово совпали с первым capture. Ошибка metadata не скрыта успехом compiler.

На активных canonical sources выполнены7 Python projection tests и8 actual
negative process cases; rootDLL также дал455 whole frames прежних5 профилей
побайтово равных прежнему worker. Component source-freeze receipt SHA
`be5172f959444e882d91770bb574fba6ba522d808facb3a60c76779d87c0f191`
проверяет exact12 файлов, root profiles и все эти receipts.

Отдельный канонический Rust gate
`local/build/server/gateway-p06t-extended-focused01/` прошёл **4PASS/0FAIL/
0ignored/buildPASS**,12.41с. Он действительно запускает root C# IPC7 для
обоих новых profiles и mixed6, затем исходный scalarFrameProof и prepared
scene ACK; отрицательные source/config pins отвергаются до worker launch.
Другие tests проверяют manifest3/strictold rules и отсутствие owned World
kind для новых physical profiles. Это уже не Python caller ACK вместо domain
proof. Focused EXE SHA
`58d475e1a58494c61f8a7cfe3d970dfe37766a9b72206753a2a6fbb6fa3a92e5`.
Полный общий full04 прошёл **1100PASS/0FAIL/5 старых ignored/buildPASS**,
340.80с, source-before/after692 exactPASS на
`c25fb84cf81a238e7b1410ccbd453d0a44a2c45f`, tag
`p06t-physics-20261016-01`. EXE SHA
`a2f7dea23dde083978fa6215fa721dc24639de2be76fb21693baf466696b908c`.
Это закрытый software gate physical foundation. Native/UI/audio WT/FV NOT_RUN,
боевого owned допуска и реальных source World contacts этих2 машин нет.

Следующий отдельный leaf component после full04: `p06t_device_caps.rs`
сохраняет `Profile::ALL[5]` и old SOURCE_SHA256, добавляет SUPPORTED[7] и
WT128/FV source maxima/roles. Новый raw caps schema v2 SHA
`2d74a8e8f272e6305d6779d887cac44ad9794c4ec40807ddf76a5139e3db9da4`,
новый policy schema v2/revision `test_lab.p06t.devices-proxy-fire.v2` SHA
`a19115167b83e73ae80e83d578490ddbcbf81cbe759c62692fc390c732232918`.
Old raw caps/policy и первые5 typed rows сохранены. Actual source preparation
9PASS связывает7 profiles/63 devices/30 primary seats с оригинальными файлами;
`local/night-staging/20261016/p06t-damage01/seven-combat01/REPORT.md`.

`State::new(Profile)` стал fallible и отвергает новые2 под v1 без panic;
`new_v2(Profile)` явно выбирает v2 для любых7. State хранит6 crew bits, а
`crew()` возвращает прежнюю actual-length slice, поэтому не добавляет лишнее
место старым payload. Source/policy/version getters отделяют per-profile
provenance от общего v2 manifest. Текущий World по-прежнему создаёт только
v1 State для прежних5; новый constructor не даёт owned/World admission.
11 новых component tests написаны, статический63caps/30roles/JSON pin gate
PASS. Focused11: **105 PASS / 0 FAIL / 0 ignored / build PASS**,43.95с,
exe SHA `2a51a7bf8312639869213daef87d7fe5604b61f387d14d4f8c9b8acf596003d1`.
Доказательства: `local/build/server/gateway-p06t-focused11/` и
`local/evidence/20261016-p06t-device-v2-01/`. Focused10 сохранил compile FAIL:
root пропустил alias device::State::new в cancelled_terminal_state; добавлен
штатный `?`, без изменения алгоритма или ожиданий. **Full05 на9080c47 завершён:
1111PASS/0FAIL/5oldignored/buildPASS**,341.89с,695sourcefiles exact. Tag
`p06t-devices-20261016-01`; exe SHA
`26b85500cadcfbf86a60c47d3ab8574caad0670e5352d382b1c36900d5a5e599`.
Source proof: `local/evidence/20261016-p06t-full05/source-{before,after}.json`.
Новый leaf не приписывается1100. Gun31/geometry/damage/TerminalPython прежние.

Пока не реализованы ammo-bay explosion, turret detach, ремонт/восстановление
экипажа, оригинальные multi-layer penetration и historical damage variance.
Native правильность новых method IDs, всех critical/fire/HE UI/audio и
переходов сохраняет NOT_RUN до настоящей ручной проверки владельца.
Full02 и отдельный full03 source-bound regression/build прошли для своих
head. WT/FV root physical foundation не включена в1096 и отдельно проверена
full04/1100. Device v2 leaf отдельно покрыт full05/1111.
Ночное разрешение не заменяет native приёмку.

Откат: сохранённые P04M branch/source-bound binary+binding, выключенный P06T
opt-in и соответствующий прежний client patch ledger. БД откатывать целым
SQLite backup, без удаления version markers/ручного смешивания v1/v2 reserves.
Оригинальный клиент и соседние проекты не изменены; новые admission flags
T26/T34/T34-85 остаются false до owner gates.

World7/source geometry/source Aim соединены в явном temporary qualification:
focused13 **134PASS/0FAIL/0ignored/buildPASS**,159.85с, exe SHA
`1f1baccc52f5412df85bf08c19b88a9a6520ba3b58dc7b09ceed2794ca68ec3f`.
Resources4 требуют exact7 и genuine shared-only Pool4; SceneManifest3 включён
только world.extended_lab. Старые ALL5/DTO/parsers сохраняют прежние границы.
Новый CLI legacy091-p06t-curated-lab принимает только WT128/FV183; LAB БК
WT[12,6,6]/FV[4,4,4] не попадает в inventory и не создаёт owned receipt.
Подтверждены actual canonical Jolt→scalarFrameProof→World/Trace→ACK mixed6,
выход/reattach внутри ACK, source health/crew/физический SID, отсутствие refill.
Отдельные root clock-only World tests проверяют clip6/2s/fullreload и frozen
FV premium HE275; они не утверждают симуляцию кадров между clock commands.
Source exporter из tools прошёл9 Python tests; raw geometry bundles0971.../
c14b... повторились по SHA. Полный актуальный regression gate и native/UI/
audio новых машин пока NOT_RUN. GunBreech31 остаётся Unsupported.

Focused12 сохранил128PASS/6FAIL: пять были вызваны legacy ammo0 constructor
перед typed initialisation (исправлен отдельный private typed factory), один
— произвольным0.0005rad ожиданием AP/APCR вместо исходных~0.00049. Теперь
проверяется независимое low-arc уравнение с2e-6rad и строгим source порядком.
Старый legacy minimum не ослаблен; cfgtest кеширует только immutable pinned
resource Arcs, отдельные negative manifests загружаются заново.

Focused14:5actual World Aim/Shoot→whole source mesh first contact→Trace→HP/
device tests PASS/build46.54с. WTAP→FV hull560, FVAP→WT1150, frozenHESH275HE→
WT1750. Gun25module-only, WT31 реально первая открытая поверхность и по старой
policy Unsupported0 без device/RNG. Позиции явно synthetic airborne; driving,
нативные FX/UI/audio не проверялись. Proof local/evidence/20261016-p06t-world07/focused14/.

Новый opt-in `legacy091-p06t-curated-lab-v2` выбирает отдельную LABpolicy
`test_lab.p06t.unarmored-gun-breech.v2`. Exact WT/Gun01/class31/armor0/VDF1/
extraGunHealth32/chance1 факты связаны с закрытым Bundle и самостоятельным
повторным whole-mesh first-hit query в Trace до мутаций. Новый Decision
UnarmoredDevice не выдаётся за обычное penetration. Однократные nominalHP и
source deviceDamage идут в прежние ledger; Gun не поджигается/unusedroll0,
RNG не расходуется. Native visual boundary использует существующий hitFX,
внутренний damage record остаётся pierced=false. Source chance/layer/angle/
continuation исторического сервера UNKNOWN; это выбранная лабораторная формула.
Старые CLI/Trace API/default Unsupported31 сохранены. Новые9tests проверяют
actual World1150HP/Gun240→0, source witness poisoning, replay/late/capacity и
полный откат при позднем переполнении deviceledger. Focused15 весьP06T:
149PASS/0FAIL/0ignored/buildPASS171.93с, exeSHA
5281f6e87dbf8deb2c336355020f592d132955de078ebee5a965a768ea65e1bf.
После него добавлен один resource/template/reset gate, будет проверен full06.

Отдельно перенесены11 self-contained tools/tests OwnedV3: native encodingV2,
Registry7/foreign source passports/terminalv3, current projection и atomic SQL
cutover/crew/ammo/reserve/result/restart. Старый semanticcatalog/rows/pins не
переписаны, activated-owner old mutations fenced, остальные owners oldwriter
сохраняют. Fresh realC/D через canonical migrations и source research/buy
прошли135.88с, source/projection/SQLite26cases и оба own primitive CPython2.7.3
checks PASS. WT/FV ammo0, новыхgrants нет. Proof local/evidence/20261016-p06t-owned-v3-01/.
Ревью затем воспроизвело actualWAL falseCORRUPT_STORE и никогда не существовавшую
пару revisionR/generationG2. Scoped DEFERRED read snapshot исправляет обе,
не закрывая чужую writerTX; полный29PASS48.856с. OldRED и GREEN сохранены в
local/evidence/20261016-p06t-owned-read-snapshot01/. Factory/HTTP/nativev3/
cacheACK/ownedWTammo не подключены и остаются отдельными software gates.

Full06 на0f1db4035849ed4fe7b78adee7a2d49bc6a2cb4c завершён:
**1162PASS/0FAIL/5oldignored/buildPASS**,469.71с,725sourcefiles before/after exact.
Tag p06t-world-seven-20261016-01, exeSHA
2c88bb43bec1e757fd7a884ae3af100408ff8f9a3dde2e72e39acfdb9249c0f4.
Actual extended-01 startup WT128/FV183 с7source resources/explicitLABv2 и
ownstop PASS; исходные106core/client inputs unchanged. Newoverlay prepare/
install/native/restoreapply NOT_RUN; sourcebyteaudit725/6readonlygates PASS.
Proof full06/ и extended-01/startup-root01.json. P06T не принята и не main.

Единственный следующий рекомендуемый шаг: по ночному разрешению открыть
отдельную зависимую ветку P10B от сохранённого software результата, сохраняя
оба утренних стенда и обязательную native приёмку P06T.
