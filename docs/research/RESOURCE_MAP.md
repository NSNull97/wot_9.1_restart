# RESOURCE_MAP — локальные ресурсы 0.9.1 #717

Run: `20261002-p00-p01`. Все client extraction outputs находятся в исключённом
из Git `local/evidence/20261002-p00-p01/`. Никакие клиентские ресурсы в код
исследовательских утилит не встроены.

## Контейнеры и скрипты

VERIFIED: **62 `.pkg`** читаются стандартным ZIP directory reader; индексы
с именами, размерами, compression и CRC — `static/*-index.json`. Суммарный
размер файлов `.pkg`: 13 851 315 910 байт. Чтение индекса не означает, что
каждый архивный payload был распакован и проверен: такой полный тест — NOT_RUN.
SHA-256 самих архивов есть в полном исходном manifest.

Ресурсы схем/танков лежат свободными файлами в `res/scripts/`; XML/DEF часто
имеют Packed XML magic `45 4e a1 62`, а не текстовый XML. Парсер ограничивает
размер, словарь, глубину, число узлов и offsets; сохраняет порядок и повторные
теги. Type 5 хранится как восстановленная base64-строка, не как исполняемый объект.
Декодированы 70 файлов. `decoded/sources.json` связывает каждый output с
размером и SHA-256 исходника. Отдельно toolkit прочитал реальные T-34-85.xml
и account.def — `wg-resources/`, с exit 0.

## Один обычный танк

VERIFIED: `res/scripts/item_defs/vehicles/ussr/t-34-85.xml` прочитан целиком.
Он содержит hull, chassis, turrets0, guns, armor и ссылки на отдельные
models/hitTester. Часть модулей ссылается на shared definitions; это ещё не
готовый разрешитель всех возможных конфигураций машины. Результаты:
`decoded/res__scripts__item_defs__vehicles__ussr__t-34-85.xml.json`,
`summary/resource-facts.json`, хеши в соответствующих `sources.json`.

## Целевые исторические значения

| Проверенная цепочка | Фактическое значение | Доказательство |
|---|---|---|
| `germany/waffentrager_e100.xml` → `turrets0/Turret_1_Waffentrager_E100/guns/_128mm_K44_2_L61/clip/count` | **6**, clip/rate 30 | SHA-256 `6d8de10ed31cb908738ca9b32935aacfe01fec78d47239dadbd86713cba052e2` |
| Тот же танк → `_150mm_Rohr_L38/clip/count` | **4**, clip/rate 20 | Тот же файл и отдельная ветвь модуля |
| `uk/gb48_fv215b_183.xml` → guns `_183mm_AT_Gun` → `uk/components/guns.xml` → shots `_183mm_HESH/piercingPower` | **`275 275`** | guns.xml SHA-256 `4214df566a69b23e92f339f0a157bb89145a41a90ea7ce1db7762496342028cd` |
| `uk/components/shells.xml` → `_183mm_HESH` | id 82, `price/gold` существует, kind HIGH_EXPLOSIVE | `summary/resource-facts.json`, `summary/sources.json` |

Статус строк: VERIFIED как данные конкретной конфигурации. 275 — целевой
номинал, не гарантированный исход попадания. Время/семантика clip/rate,
серверная формула пробития, RNG и распределение до 9.6 этими числами не доказаны.
Значение 6 не распространяется на 150-мм орудие.

## Collision hull Т-34-85

Источник: `res/packages/vehicles_russian.pkg` →
`vehicles/russian/R07_T-34-85/collision/Hull.primitives` и `Hull.visual`.
Архивный payload имеет собственный SHA-256 в `geometry/sources.json`.

VERIFIED/OBSERVED результат `tools/geometry_spike.py`:

- Primitive container `65 4e a1 42`, секции indices, vertices, bsp2, bsp2_materials.
- `xyznuv`, **301 вершина**, измеренный stride **32**, **594 индекса / 198 треугольников**.
- **16 групп**; проверены диапазоны индексов, конечность координат и нормалей.
- Bounds: min `(-1.28827095, -0.63848382, -2.90602779)`, max
  `(1.28114104, 0.74434966, 2.97122526)`; совпадают с `.visual` до `1e-5`.
- 15 имён armor сопоставлены с `hull/armor` дескриптора. Пример: первая
  группа `armor_4` → 40. Последняя `surveyingDevice` не объявлена бронеплитой,
  её семантика остаётся UNKNOWN.

Доказательство: `geometry/collision-mesh.json`, `hull-visual.json`, `sources.json`.
Это геометрический анализ collision-ресурса; реальный трассировщик попаданий,
BSP2, оси/единицы в запущенном клиенте, pivots всех модулей и сложные
составные попадания не проверены.

**FAIL toolkit compatibility:** на том же реальном payload штатный
`wgtk::model::primitive::Vertices` прочитал **7292 из 9700 байт**, оставив
**2408**. 301 × (32 − 24) = 2408. Подтверждено исполняемым `p01-wg-probe geometry`;
`wg-geometry.log`. Без исправления и дополнительных данных этот импортёр
нельзя использовать как готовый importer старой геометрии.

## Один фрагмент Прохоровки

VERIFIED: пакет `05_prohorovka.pkg` содержит `space.settings`, `.chunk` и
вложенные ZIP `.cdata`. Прочитаны `spaces/05_prohorovka/00000000o.chunk`
и `00000000o.cdata`. `space.settings`: terrain version 200, heightMapSize 64,
bounds minX/minY −6, maxX/maxY 5.

Chunk даёт реальные ссылки на объекты и матрицы transform; cdata содержит
18 элементов, включая `terrain2/heights`, heights1–5 и normals. Заголовок
heights начинается `hmp\0`, следующие два little-endian uint32 — 69/69.
INFERRED: эти поля задают размеры height image с border; полная интерпретация
height encoding здесь не реализована. Превращать эти байты в произвольный
heightfield было бы необоснованно.

Evidence: `geometry/chunk.json`, `space-settings.json`, `cdata-members.json`;
пути и хеши исходных members — `geometry/sources.json`. Проезжаемость, стенки,
мосты, разрушаемость, коллизии terrain в физике — NOT_RUN.

Стабильные client paths/IDs не переименовывались; публичные названия будут
отдельными данными согласно [NAMING](../NAMING.md).
