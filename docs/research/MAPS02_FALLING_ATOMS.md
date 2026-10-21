# MAPS-02 — fallingAtoms (столбы, фонари, знаки): статическое исследование

2026-10-21. Ветка `codex/maps-02-falling-atoms` от `codex/maps-01-map-pipeline`
(`0c144ac`). Только чтение оригинального клиента `C:/WoT_0.9.1_RU_0717_original`;
байткод — `marshal` + `dis` проектного CPython 2.7.3, код клиента **не исполнялся**.
Рантайм, стенды и клиенты не менялись. Native-проверка — **NOT_RUN**.
План реализации: [plans/MAPS02_FALLING_ATOMS.md](../plans/MAPS02_FALLING_ATOMS.md).

Доказательства (игнорируемые): `local/evidence/20261021-maps02-research01/`
- `sources.json` — размеры/SHA-256 источников и выходов;
  `areadestructibles.pyc` `3bc2f5c3…`, `destructiblescache.pyc` `be64966a…`,
  `vehicle.pyc` `b81d08ca…`, `destructibles.xml` `bd39e304…`, `WorldOfTanks.exe` `86f5e351…`;
- `*.dis` — полный дизассемблер трёх модулей (`dis27.py`);
- `falling_atoms.json` — 73 записи `fallingAtoms` из `destructibles.xml` (`fa.py`);
- `prohorovka-falling-atom-index.json` — сверка статического индекса с native-экспортами.

## 1. Путь клиента (VERIFIED, байткод `AreaDestructibles.py`)

1. `AreaDestructibles.onEnterWorld:815` — **первым** обрабатывает `fallenColumns`:
   `frozenset` запоминается, для каждого значения вызывается
   `orderDestructibleDestroy(chunkID, DESTR_TYPE_FALLING_ATOM, fallData, False)`.
   Значит начальное состояние/rejoin восстанавливает упавшие столбы **без анимации**.
2. `set_fallenColumns:893` — разность `curr − prev` → тот же вызов с `isNeedAnimation=True`.
   Удаление из массива ничего не «поднимает»: обратного пути у клиента нет.
3. `orderDestructibleDestroy:199` — если чанк ещё не загружен, запись кладётся в
   `__destructiblesWaitDestroy` до `onChunkLoad`; иначе `__destroyDestructible`.
4. `__destroyDestructible:291`, ветка `DESTR_TYPE_FALLING_ATOM`:
   `decodeFallenColumn(data) → (destrIndex, fallDirYaw, fallSpeed)`;
   `pitchConstr, collisionFlags = BigWorld.wg_getDestructibleFallPitchConstr(space, chunk,
   destrIndex, fallDirYaw)` — **угол упора считает сам клиент** (native); при `None` —
   `π/2`. Затем `__dropDestructible`. В отличие от деревьев и фрагилов, для столба
   **не** вызывается `FMOD.lightSoundRemove`.
5. `__dropDestructible:658`: останавливает lifetime-эффект; при анимации —
   `fractureEffect` в направлении yaw; `useEffectsOnTouchDown = (collisionFlags & 8) or
   pitchConstr > radians(87)`; для falling atom касание земли даёт
   `touchdownEffect` + `touchdownBreakEffect` либо просто `__touchDown`
   (`fashion.isDestroyed = True`, если у модели есть damaged-материал).
   Без анимации — сразу `__touchDown`. Далее `_DestructiblesAnimator.showFall`.
6. `showFall:966` (параметры из `desc`, масштаб `s = |M·(0,1,0)|`):
   `height·s`, `mass·s³`, `springStiffnes·s²`, `springResist·s²`, `airResist·s²`,
   `buryDepth·s`, `springAngle`; начальная угловая скорость
   `pitchSpeed = (fallSpeed + 1) · 0.45` рад/с; момент инерции `m·h²/3`.
   Поворот: `preRot = M_без_переноса · Ry(−yaw)`, затем `RotateX(pitch)`, затем
   `postRot = Ry(yaw)`. Без анимации поза покоя решается native
   `wg_solveDestructibleFallPitch(G·m, 0.5·h·k, pitchConstr − springAngle, …)`.
7. `__moveBody:1080` — интеграция шагом ≤1/60 с: гравитационный момент
   `0.5·h·G·m·sin(pitch)`, сопротивление воздуха, пружина упора после
   `pitch + springAngle > pitchConstr`; остановка при `|ω|+|τ| < π/500` или через 8 с.
   `__positionBodyModel` опускает модель на `buryDepth·sin(pitch)` и пишет матрицу через
   `wg_setDestructibleMatrix`. `__detectPitchConstraint` в Python определён, но
   вызовов в модуле нет (VERIFIED: ссылок кроме определения нет).
8. `isDestructibleBroken(itemIndex, matKind, DESTR_TYPE_FALLING_ATOM)` ищет индекс в
   `fallenColumns` — так клиент узнаёт, что столб уже упал.

Направление: эффекты строятся с `dir = (sin yaw, 0, cos yaw)` (`__launchFallEffect:736`) —
**VERIFIED**, что yaw — мировой азимут падения в той же конвенции, что
`atan2(vx, vz)` у деревьев P06Q. INFERRED: верх столба уходит именно в эту сторону
(знак `RotateX` в BigWorld не проверялся отдельно; визуально — owner native).

## 2. Кодирование (VERIFIED, `DestructiblesCache.py`)

```
encodeFallenColumn(destrIndex, fallYaw, fallSpeed):
    fallSpeed = int(fallSpeed); clamp 0..3
    discreteYaw = int(64.0 * (fallYaw + PI) / PI_2) % 64      # PI = math.pi, PI_2 = 2·PI
    return destrIndex << 8 | (discreteYaw << 2 | fallSpeed & 3)
decodeFallenColumn(d): (d >> 8, ((d & 255) >> 2) / 64.0 · PI_2 − PI, (d & 255) & 3)
```

`destrIndex` не маскируется: при индексе >255 значение не влезет в `UINT16`, сервер
обязан ограничить индекс 0..255 сам. Шаг yaw — 5,625°.
Константы типов: `TREE=0, FALLING_ATOM=1, FRAGILE=2, STRUCTURE=3`.

**Клиенту достаточно массива `fallenColumns: ARRAY<UINT16>`** (VERIFIED по всем
потребителям): угол упора, флаги касания, поза покоя, эффекты и материалы клиент
получает сам из своих ресурсов и native-запросов. Pitch, высоту, скорость, время
падения сервер не передаёт. Отдельных ClientMethods у `AreaDestructibles` нет (P06N).

## 3. Индекс свойства 0xa0

- VERIFIED (`areadestructibles.def`, декодирован в P06O/P06P/P06R): порядок
  ALL_CLIENTS-свойств — `destroyedModules`, `destroyedFragiles`, `fallenColumns`,
  `fallenTrees`; все четыре — переменного размера, stable-sort их не переставляет.
- VERIFIED (P06T, PE): ID property-сообщения = `158 + индекс client property`.
- OBSERVED native: индекс 1 = `0x9f` (P06N, владелец PASS), индекс 3 = `0xa1`
  (P06Q, `set_fallenTrees` в трассе клиента, владелец: деревья падают). Пустой массив в
  позиции 2 при создании сущности принимается обоими клиентами (все native-прогоны
  P06N…MAPS-01).
- **INFERRED (сильно):** `fallenColumns` = `0xa0`, VAR1, `i32` count + `u16`.
  Native-трасс с непустым `fallenColumns` в `local/evidence` **нет** (поиск по всем
  JSON/логам) — подтвердит owner native MAPS-02.
- Граница: VAR1 ≤ 255 байт → не более 125 столбов на area; фактически максимум на чанк
  по 44 картам — **34** (OBSERVED, пакеты MAPS-01).

## 4. Параметры `destructibles.xml` (VERIFIED, `__readFallingAtom`, `_readDestructiblePhysicParams`)

`physicParams` — ровно 7 float по порядку:
`mass, height, springAngle, springStiffnes, springResist, airResist, buryDepth`.
Потребитель — **только клиентский аниматор** (п. 1.6–1.7); на сервер-правило не влияют.
В 0.9.1 два набора: столбы `400 2…12 0.03 300000 10000 0 0.02…0.1` и знаки/фонари
`200 2.5…6 0.03 150000 10000 0 0.05` (`airResist = 0` у всех 73).

- `health` (int, 3…27) — эталонное HP; масштабированное
  `scaledDestructibleHealth(s, h) = int(ceil(s²·h))` (VERIFIED).
- `kineticDamageCorrection` (float, по умолчанию 0.0) — задан у одной записи
  (`mle024_ObstacleRail`, 2). Потребитель — `Vehicle._isDestructibleMayBeBroken` (п. 5).
- `preferredTiltDirections` — читается (градусы → нормализация в (−180,180], добавление
  `max−360`, `min+360`, в радианы), но **ни у одной** записи 0.9.1 его нет (имени нет
  даже в словаре packed-XML) и клиентских потребителей нет. INFERRED: серверная
  подсказка выбора yaw; для 0.9.1 неактуально — реализация должна отвергать каталог с ним.
- Глобальные: `unitVehicleMass = 35000`, `maxHpForShootingThrough = 19`,
  `defaultLifetimeEffectChance = 1.0`. `maxHpForShootingThrough` и
  `projectilePiercingPowerReduction` в клиентских модулях не используются (VERIFIED по
  поиску строк) — серверные параметры, смысл INFERRED по имени.
- Эффекты `fractureEffect`/`touchdownEffect`/`touchdownBreakEffect`/`lifetimeEffect`
  читаются только при `IS_CLIENT`.

Состав 73 записей: столбы `env414_Pole` 9, `rw604_Rwsign` 8, фонари/знаки/часы/
светофоры, `gaf023_ForgedFence` 1 и др.

## 5. Клиентский предикат разрушения тараном (VERIFIED формула, роль INFERRED)

`Vehicle._isDestructibleMayBeBroken(chunkID, itemIndex, matKind, itemFilename,
itemScale, vehSpeed)` (строка 664):

```
если уже сломан (isDestructibleBroken) → True
m = typeDescriptor.physics['weight']
E = 0.5 · m · vehSpeed² · 0.00015
не structure: E *= (m / unitVehicleMass) ** kineticDamageCorrection ; ref = desc.health
structure:   ref = modules[matKind].health
return scaledDestructibleHealth(itemScale, ref) < E
```

Имя функции есть строкой в `WorldOfTanks.exe` и нигде в Python-модулях не вызывается →
INFERRED: её вызывает native-движок при контакте машины со статикой (предсказание,
можно ли проехать сквозь объект). Какую скорость (полную, нормальную, относительную)
движок передаёт как `vehSpeed` — **UNKNOWN**. Совпадает ли серверный закон 0.9.1 с этим
клиентским предсказанием — **UNKNOWN**; это лучший доступный ресурсный ориентир.
Пример (`kdc = 0`, `s = 1`, столб HP 18; массы профилей сервера): ИС-7 68 190 кг —
`v > 1,88 м/с` (6,8 км/ч); МС-1 4 691 кг — `v > 7,15 м/с` (25,7 км/ч, при пределе МС-1 8 м/с).

## 6. Геометрия у сервера (OBSERVED, пакеты MAPS-01)

- 5328 экземпляров `fallingAtoms` на 34 из 44 карт (Химмельсдорф 534, Прохоровка 71,
  Малиновка 18). У **5228** — 0 треугольников и в физике (маска 18), и в снарядной
  геометрии (маска 128): их BSP есть (у `env414_Pole1` 10 треугольников,
  `n_wood_0`, flags `18819 = 0x4983`), но материал содержит биты 2 и 128, которые
  исключают оригинальные запросы движения (`wg_collideSegment(...,18)`) и снаряда
  (`ProjectileMover`, маска 128). Значит в оригинальном клиенте столбы **не блокируют**
  ни танк, ни трассер — это триггеры, а не препятствия (вывод из VERIFIED масок).
- 100 экземпляров с блокирующей физикой — все `gaf023_ForgedFence`. Это смешанный
  случай (блокирует до падения?) — UNKNOWN, в MAPS-02 исключается с причиной.
- **OBSERVED native-индекс:** для Прохоровки все 71 столб статического индекса MAPS-01
  совпали по (чанк, индекс, имя) с пятью записанными native-экспортами P06P
  (47/47 в 44 чанках и 71/71 в 117 чанках, 0 пропусков). Малиновка — INFERRED
  (`static-chunk-order-v1`), native-подтверждение NOT_RUN.

## 7. Серверный закон 0.9.1 (UNKNOWN)

`areadestructibles.def` объявляет CellMethods `damageDestructible`,
`damageDestructibleAndMoveProjectile`, `smartDestroy` (OBSERVED в .def, тела на сервере
отсутствуют). Когда сервер роняет столб (таран, снаряд, сплэш, другой падающий объект),
как выбирает yaw и `fallSpeed`, теряет ли снаряд пробитие — **UNKNOWN**. Любое правило
MAPS-02 — явная `test_lab`-политика.

## Итог по категориям

| Факт | Статус |
|---|---|
| Клиенту нужен только `fallenColumns` UINT16, pitch считает сам | VERIFIED (байткод) |
| Формула encode/decode, шаг yaw 64, скорость 0..3, `ω0=(s+1)·0.45` | VERIFIED |
| Rejoin/initial — без анимации, live — разность множеств | VERIFIED |
| 7 `physicParams` = mass, height, springAngle, springStiffnes, springResist, airResist, buryDepth | VERIFIED |
| `preferredTiltDirections` в 0.9.1 нет ни у одной записи | VERIFIED |
| Клиентский предикат тарана с `kineticDamageCorrection` | VERIFIED формула; роль INFERRED |
| Property `0xa0` | INFERRED (сильно); native NOT_RUN |
| Столбы не блокируют движение/снаряд (маски 18/128) | INFERRED из VERIFIED масок и флагов |
| Static-индекс столбов Прохоровки = native | OBSERVED 71/71 |
| Серверное правило падения | UNKNOWN |

## 8. Реализация (коммит `6c44fa2`, решения владельца D1–D4 от 2026-10-21)

Политика `test_lab-falling-atom-client-break-predicate-v1`: формула п. 5 с `|v|` корпуса
(pre-step скорость Jolt) и hash-bound массой профиля; `yaw = atan2(vx, vz)`; корзины
скорости как у деревьев P06Q; горизонтальная скорость < 0,1 м/с — падения нет.
Выстрел, сплэш и падение от других объектов не реализованы (D2).

Цепочка: `map_package.py triggers` → `compound_destructible_catalog.py --static-index
--falling-atoms` (domain v8 / worker v9, триггер-буферы рядом с каталогом) → воркер IPC7
создаёт статические sensor-тела и сообщает `column_contacts` → gateway решает
(`fragiles::State::column_contact`), трасса воспроизводит, сцена коммитится после ACK
воркера (sensor удаляется) → `fallenColumns` 0xa0 обоим клиентам; создание area на входе
и при rejoin несёт полный массив (`area_create_full`).

Доказательства: `local/evidence/20261021-maps02-impl01/`.

| Проверка | Результат |
|---|---|
| Реэкспорт K/P после рефакторинга `load_geometry` | все файлы пакетов побайтно = MAPS-01 final01, `regression` PASS (`regress01.log`) |
| Триггеры | Прохоровка 71 / 756 треуг., Малиновка 18 / 224, Химмельсдорф 534 / 29 731, Кампания 96 / 3 572; детерминизм — тест |
| Каталог Прохоровки v8/v9 | 71 столб, 0 исключений; manifest `61ce7951…`, worker `efd83118…`; остальные 1038 строк = v7/v8 static (worker `41c0d9cc…`) |
| Каталог Малиновки v8/v9 | 18 столбов; manifest `61dd9a23…`, worker `a1de056a…`; индекс INFERRED |
| D3 на Кампании | 73 допущено, 23 `gaf023_ForgedFence` — `falling_atom_blocking_geometry_unknown` |
| Реальный Jolt IPC7 (`probe02/receipt.json`) | ИС-7 на столбы 50/128/200: один контакт на столб, ~7,9 м/с, движение побитно = контрольному прогону без датчиков, `sync_removed` ACK, после удаления не сообщается — PASS |
| Gateway, точечно | wire/домен/реальный каталог/реальный кадр воркера/World-атомарность — 11 новых тестов PASS; кадр столба 50 → `0x4a82` |
| Python | `tests/test_falling_atoms.py` 10/10 PASS; связанные наборы — 2 сбоя окружения, те же на базе MAPS-01 |
| Полный gateway gate (worktree, `gateway-maps02-full02`) | 1423 PASS / 281 FAIL / 5 ignored; набор FAIL идентичен базе MAPS-01 (1414/281/5, окружение: фикстуры канонического корня) |
| Native (владелец) | **NOT_RUN** |
