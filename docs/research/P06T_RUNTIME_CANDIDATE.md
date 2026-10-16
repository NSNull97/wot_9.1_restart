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
| Новый view-scale World test после05 | source240m baseline→optics120m/commander180m при target200m, **NOT_RUN** до полного gate |
| Полный gateway / новые bindings | **NOT_RUN / PENDING** до отдельного сохранённого результата |
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
Дополнительный view-range World test написан после focused05 и не включён в74.
Каноническая команда focused gate:

```powershell
python -B -X utf8 server/build.py gateway --test --test-filter p06t_ --out local/build/server/gateway-p06t-focused05
python -B -X utf8 tools/p06t_device_source.py --original-root C:/WoT_0.9.1_RU_0717_original --out local/evidence/20261016-p06t-device-source02
```

Output directories должны быть свежими; существующие receipts не перезаписывать.
Первый пример выполнен в focused05; полный regression/build gate конечного
head с дополнительным view-range test ещё требуется.

## WT/FV, границы приёмки и откат

VERIFIED SOURCE/компонент scheduler: WT E100128мм clip6/interval2с/reload60с,
150мм clip4/3с/50с; FV215b183 premium HESH — HIGH_EXPLOSIVE275/275,
а не новая физическая family. **Qualified World physics/owned admission этих
машин отсутствуют.** У FV также нужен отдельный versioned catalogue correction
для original UK nationID5; frozen P04M catalogue под старым SHA не меняется.
Нельзя на основании source-only scheduler назвать WT/FV playable/P06T accepted.

Пока не реализованы ammo-bay explosion, turret detach, ремонт/восстановление
экипажа, оригинальные multi-layer penetration и historical damage variance.
Native правильность новых method IDs, всех critical/fire/HE UI/audio и
переходов сохраняет NOT_RUN до настоящей ручной проверки владельца.
Полный source-bound gateway regression/build gate текущего конечного head
ещё требуется; ночное разрешение не заменяет эту приёмку.

Откат: сохранённые P04M branch/source-bound binary+binding, выключенный P06T
opt-in и соответствующий прежний client patch ledger. БД откатывать целым
SQLite backup, без удаления version markers/ручного смешивания v1/v2 reserves.
Оригинальный клиент и соседние проекты не изменены; новые admission flags
T26/T34/T34-85 остаются false до owner gates.

Единственный следующий рекомендуемый шаг: полный canonical source-before/
after/build gate конечного P06T head, включая новый view-range World test,
перед подготовкой утреннего стенда.
