# P04M — пять боевых профилей и версия собственного гаража

2026-10-16, ветка `codex/p04m-five-battle-profiles`, зависимая от checked P07B.
Разрешение продолжать без ночных ручных вопросов — `docs/plans/NIGHT_20261016.md`.
Эта запись дополняется итоговым source gate; до него статус **CANDIDATE**.

## Источники и границы

**VERIFIED SOURCE:** оригинальный #717, read-only
`C:\WoT_0.9.1_RU_0717_original`. Исходное исследование —
[пул stock-сборок](P04M_POOL_SOURCE.md), importer/spec —
`tools/p04m_battle_profiles.py`. Новые resource payloads/пакеты в git не включены.
Профили МС-1/ИС-7 сохраняют прежние schema/byte pins; три новые сборки читаются
по отдельным точным SHA до JSON parsing. Все численные данные относятся к этим
конкретным stock-модулям, не к любому орудию или топовой конфигурации машины.

| Вид | Type CD | HP | Масса, кг | Штатный БК | Stock AP CD | Обзор, м |
|---|---:|---:|---:|---:|---:|---:|
| МС-1 | 3329 | 90 | 4691 | 96 | 2570 | 240 |
| ИС-7 | 7169 | 2150 | 68190 | 30 | 14602 | 400 |
| Т-26 | 4609 | 150 | 9302 | 160 | 1034 | 280 |
| Т-34 | 1 | 400 | 27940 | 77 | 7178 | 240 |
| Т-34-85 | 2561 | 670 | 32370 | 68 | 7946 | 350 |

Т-34 имеет дополнительный задний сектор `-17/1/42`, Т-26/Т-34-85 — нет.
Mounted пределы Т-34-85 `-22/7` перекрывают shared gun `-26/8`.
Sparse armor IDs сохранены: у Т-34-85 отсутствуют Hull14/Gun3; Gun6 с нулевой
бронёй отличается от отсутствующей записи материала. AP использует профиль
стрелявшего орудия и настоящий material catalog цели без подстановки ИС-7.
Новые visual bounds — исходные факты, **UNKNOWN** как native hitTester bbox.

**OBSERVED COMPONENT:** Windows x64, закреплённый JoltPhysicsSharp2.22.0,
настоящие native body getters/матрицы инерции. **INFERRED TEST_LAB:** шесть
опор, преобразование engine/controller, box collider и AP reference resolver.
Это версионированная серверная физика, не реконструкция исторического сервера.
У Т-26 четыре source радиуса групп колёс; выбранная support policy не объявляет
один из них единственным историческим радиусом машины.

## Реализация и проверенная граница

Closed registry5 объединяет descriptor/HP/массу/броню/орудие/наведение/обзор.
Manifest v1/v2 сохраняет ровно старые2 вида; v3 требует все5 и общий IPC7 worker.
Scene v1 старых машин остаётся прежним. Scene v2 передаёт `source_profile` для
каждого actor: null у старых и pinned qualified profile у новых. Геометрия,
config и native binding выбираются по собственному виду каждого actor.

Сцены с новой машиной используют четыре collision substeps на прежний такт60Гц,
со старой сценой — один. Нативный Discrete режим сохранён; испытанный CCD не
дал нужного контакта. Предел проникновения OBB50мм не ослаблялся. Т-26 в ранних
кандидатах дал7.63см; финальные максимумы1.29/13.57/.80мм. Старые182frames и
новые2091 повторных frames совпали побитово в пределах закреплённой сборки.
Межплатформенная детерминированность **NOT_RUN**.

World/Trace/fragiles/native tracer budgets поддерживают160 снарядов на машину,
до960 на6 акторов. Старые двухвидовые и legacy96 конструкторы сохраняют свои
границы. Временная лаборатория выдаёт ровно20AP новым видам только в своей
непостоянной сцене; собственные боеприпасы не создаются этим механизмом.

Actual C#06→IPC7→оригинальный Rust FrameProof: четыре случая,600batches,
1359 scalar actor frames,10 native receipts/witnesses,8 prepared ACK и29 отказов
на подменённых настоящих кадрах. С coupled root worker:120batches, один процесс,
четыре typed contacts/scene transitions, три staged ACK; выход Т-26 во время
prepare и возврат того же физического тела сохраняют состояние и БК.

## Собственность, экипаж и БК

`PoolStore` — явная opt-in версия над тем же SQLite writer. Сохраняются frozen
F–K proof/политики, исходные строки/балансы и прежние command receipts. Новый
current snapshot/crew codec имеет отдельные schema/policy hashes. Транзакционная
перестройка CHECK экипажа сохраняет строки всех владельцев и не активирует
других владельцев. Миграция при active reservation запрещена; failpoints
откатывают DDL/строки/проекцию целиком. Бесплатных боеприпасов и машин нет.

Настоящий native inventory ID разрешается через owned research row. У ночного
A номер3 — Объект261; никакой замены его на Т-26 нет. В изолированных tests
номер3 получали разные реально купленные виды. Неподдержанный вид остаётся
явно недоступным. У известного вида с нештатными модулями сохраняется тип для
операций экипажа. БК проверяется по фактически установленным source turret+gun;
боевой допуск по-прежнему требует всей точной сборки. Это позволяет выгрузить
и снова загрузить свой БК после законной смены ходовой. Смена орудия при
загруженном БК отклоняется; после выгрузки новое неподдержанное орудие не
получает старые снаряды. Этот полный SQLite/publish/reopen цикл прошёл тест.

Штатные primary seats: Т-26 commander/driver/gunner; Т-34
commander/radioman/driver/loader; Т-34-85 commander/gunner/radioman/driver/loader.
Combined roles сохранены source-фактами. Квота16 — прежний lifetime allocator
без возврата при увольнении; расширение пула её не увеличивает. Все пять
полных экипажей одновременно требуют19 мест, поэтому такая выдача не сделана.
Новый hire — исходный проектный free50 контракт; обучение новых типов вне
проверенного codec явно недоступно. Старые навыки/история сохраняются.

Новые9 shell rows начинаются с нулевого склада, купленные машины с пустым БК.
Загрузка/выгрузка использует только собственный склад и общий command ledger.
Новый `p04m-pool.json` связывает владельца/database/revision/state SHA с пятью
закреплёнными hashes и6-полевыми capabilities. Gateway opt-in `p04m_pool=true`
открывает отдельные CMD108/309/105/303 проверки, включая радиста и БК160.
Старые wire codecs и literal P08B policy не расширены под прежним hash.

Реальные Python SQLite→Rust vectors выявили разный порядок полей CMD303:
Pool writer `vehicle→compDescr`, старый P04K `compDescr→vehicle`. Новый bound
codec проверен по настоящему ответу; старый сохранён. Привязка проекции
обновляется после durable мутаций и возврата из боя; внутри Session::receive
внешнего I/O нет, malformed compound откатывается целиком.

## Фактически выполненные gates и evidence

- Source importer11 и old contact23 PASS;
  `local/evidence/20261016-p04m-source-import01/`.
- C# component getter/maps/handling/contact/negatives/legacy/catalog/ACK/repeat PASS;
  `local/evidence/20261016-p04m-physics01/component06-receipt.json`.
- Canonical focused04 **26PASS/0ignored/buildPASS**,97.98s;
  `local/build/server/gateway-p04m-focused04/result.json`.
- Canonical companion05 **5PASS/buildPASS**; отдельно exact binary filter
  actual SQLite303/309 **2PASS**;
  `local/evidence/20261016-p04m-runtime01/actual-native-vectors05/result.json`.
- Python: новые registry/source/SQLite **17PASS**,260.677s; дополнительный
  actual chassis/ammo regression **1PASS**,45.153s; старые P08B/results
  **28PASS**,198.583s. Source/log pins и сохранённые сбои:
  `local/evidence/20261016-p04m-writer01/writer-freeze06.json`.
- Interim focused03 binary regression989PASS/2FAIL/5ignored: оба FAIL вызваны
  пропущенной CARGO_TARGET_DIR в ручном runner. Оба затем exact rerun PASS с
  нужным окружением; это не canonical/current-source full gate. Логи сохранены
  в runtime01/interim-full01 и interim-env-repair01, production не ослаблялся.
- Новый полный gateway/source gate, окончательная Python/Web/HTTP матрица и
  SHA коммита дописываются после заморозки компонентов: пока **NOT_RUN**.

Команды: `python -B -X utf8 tools/p04m_battle_profiles.py --original
C:\WoT_0.9.1_RU_0717_original --out local/evidence/20261016-p04m-source-import01`;
`python -B -X utf8 server/build.py gateway --test --test-filter p04m_ --out
local/build/server/gateway-p04m-focused04`, `RUST_TEST_THREADS=1`.
Повторный запуск требует нового output; сохранённые receipts не переписывать.

## Native, откат и дальнейший шаг

У новых3 **battle_admission=false / OWNER_ACCEPTANCE_REQUIRED**. Native
управление, модели, hit effects, звук, гаражные операции и owner gate **NOT_RUN**.
В main карточка не слита. Новый явный `legacy091-curated-lab KEY DIGEST GATEWAY
TEMPLATES CAPTURE KIND` использует общий worker и старые frozen account fixtures
для временной квалификации выбранного типа. Он не резервирует собственную
машину, не меняет её БК и не открывает admission. Обычный profile13 маршрут
продолжает требовать настоящий owned writer receipt.

Утренние два overlays подготовлены CPython2.7.3 без install/launch:
`local/stands/night-battle-20261016-01/qualification-02/`. Runner qualification.py
требует финальный canonical runtime binding и собственные точные pins; actual
native запуск пока не выполнялся. Повторять prepare поверх evidence нельзя.

Откат runtime — вернуться на сохранённую P07B ветку после сохранения P04M WIP;
main ffce8cb не менялся. SQLite opt-in не откатывать удалением marker: восстановить
полный isolated backup до миграции. Клиентские установки — только patch-ledger
rollback. Единственный следующий шаг текущего кандидата — закончить полный
source-bound автоматический gate, затем перейти к P06T отдельной веткой;
ручная квалификация каждой новой машины остаётся в утренней матрице.
