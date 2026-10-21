# MAPS-02 — падающие объекты (fallingAtoms): план карточки

Статус: **одобрено владельцем 2026-10-21 (D1–D4 как рекомендовано); реализовано в
коммите `6c44fa2`**, native-проверка владельца — NOT_RUN. Отклонения от плана ниже:
триггеры — отдельная команда `map_package.py triggers` (пакеты MAPS-01 и пины реестра
не меняются); `destructible_catalog.py` не менялся (kDC/tilt читает
`compound_destructible_catalog.py` из `parse_definitions`); Python-тесты — один файл
`tests/test_falling_atoms.py`; проба воркера — `tools/falling_atom_scene_probe.py`.
Поддерживается только IPC7 battle scene (профиль 13); одиночный drive-воркер каталог
v9 отвергает.
Ветка `codex/maps-02-falling-atoms` поверх `codex/maps-01-map-pipeline` (`0c144ac`);
слияние — только после слияния MAPS-01 и native-приёмки владельца.
Факты и категории: [research/MAPS02_FALLING_ATOMS.md](../research/MAPS02_FALLING_ATOMS.md).

## Цель

Таран столба/фонаря/знака на карте реестра роняет его один раз; оба клиента видят
падение в сторону движения танка; танк не тормозит (как у оригинала — объект не
блокирует движение); повторный заход в бой показывает объект уже лежащим.
Серверное состояние остаётся авторитетным: сервер решает, упал ли объект, и публикует
только `fallenColumns`.

## Что известно и что берётся как test_lab

- VERIFIED: клиенту нужен только `fallenColumns: ARRAY<UINT16>`
  `= idx<<8 | yaw64<<2 | speed`; pitch/упор/эффекты клиент считает сам.
- INFERRED (сильно): property ID `0xa0`; native NOT_RUN.
- VERIFIED: столбы исключены оригинальными масками 18/128 → у сервера сейчас **нет**
  их геометрии ни в физике, ни в снарядах. Для обнаружения тарана нужен отдельный
  **неблокирующий триггер** из исходного BSP столба.
- UNKNOWN: серверный закон 0.9.1. Предлагаемая политика
  `test_lab-falling-atom-client-break-predicate-v1` использует VERIFIED клиентскую
  формулу `Vehicle._isDestructibleMayBeBroken`:
  падает, если `ceil(s²·health) < 0.5·m·|v|²·0.00015·(m/35000)^kineticDamageCorrection`,
  где `s = |M·(0,1,0)|` экземпляра, `m` — hash-bound масса машины из дескриптора
  воркера (та же, что у тарана деревьев), `|v|` — линейная скорость корпуса на подшаге
  контакта (выбор проекта: какую скорость подаёт native — UNKNOWN).
  `yaw = atan2(vx, vz)`; при горизонтальной скорости < 0,1 м/с падения нет.
  `fallSpeed`: `|v| ≥ 8 → 3, ≥ 4 → 2, ≥ 1 → 1, иначе 0` (как у деревьев P06Q, test_lab).
  Колесо/гусеница и корпус — одинаково (триггер не различает, выбор проекта).
- Снаряды, сплэш, падение от другого объекта, «подъём» — **не реализуются** и явно
  недоступны (см. D2).

## Решения владельца (нужны до кода)

| # | Вопрос | Рекомендация |
|---|---|---|
| D1 | Правило тарана | клиентский предикат (выше), а не фиксированные 8000 Дж деревьев |
| D2 | Выстрел по столбу в MAPS-02 | нет; отдельная карточка (нужен триггер в снарядном запросе gateway и решение о потере пробития; `maxHpForShootingThrough=19` — только INFERRED) |
| D3 | `gaf023_ForgedFence` (100 шт., есть блокирующая физика) | исключить с причиной; смешанный случай UNKNOWN |
| D4 | Формат | каталог v8 = v7 + строки `kind: falling_atom`, выпускается только с флагом; v7-выходы и принятые каталоги Карелии/Прохоровки побайтно прежние |

## Изменения (точный список файлов)

### Экспорт и каталог (Python)
1. `tools/map_package.py` — новый буфер триггеров: треугольники BSP только для
   экземпляров `fallingAtoms`, отброшенные масками 18/128, в мировых координатах;
   файлы `physics/falling-atom-triggers.vertices.f32`, `.triangles.u32` и раздел
   манифеста `falling_atom_triggers` (instance_id, first_triangle, count, sha256).
   Базовые буферы рельефа/физики/снарядов **не меняются** (регрессия Карелии/Прохоровки).
   Пределы: ≤ 64 треугольника на экземпляр, ≤ 65 536 всего, конечные координаты в
   границах карты; пустой BSP → причина исключения.
2. `tools/compound_destructible_catalog.py` — `KINDS += ('falling_atom',)`, флаг
   `--falling-atoms` → каталог `version: 8`, `ram_policy` для строк falling_atom =
   `test_lab-falling-atom-client-break-predicate-v1`; поля строки:
   `scale`, `health`, `scaled_health`, `kinetic_damage_correction`,
   `trigger_first_triangle`, `trigger_triangle_count`, `native_index` (static,
   0..255). Причины исключения: `falling_atom_blocking_geometry_unknown` (D3),
   `falling_atom_no_trigger_geometry`, `falling_atom_index_over_255`,
   `falling_atom_preferred_tilt_unsupported`, `area_column_limit_125`.
   Воркер-файл `physics-removals.json` v9: строки `kind: falling_atom` со ссылкой на
   буфер триггеров по SHA-256.
3. `tools/destructible_catalog.py` — чтение `kineticDamageCorrection` (по умолчанию
   0.0, как `__readFallingAtom`) и отказ при `preferredTiltDirections`.

### Физика (C#, воркер)
4. `server/physics/CheckedInput.cs` — версия каталога 9: kind `falling_atom`,
   загрузка и проверка буфера триггеров (размеры, SHA, спан на экземпляр).
5. `server/physics/BattleScene.cs` — статические **sensor**-тела триггеров
   (`IsSensor = true` с создания, движение танка не меняется); в `Contact` новая ветка:
   первый контакт корпуса с триггером за тик → запись
   `(slot, object_id, substep, pre_velocity)`, не более 16 на тик на танк;
   удаление sensor-тела по существующему removal-дескриптору (тот же ACK-барьер).
6. `server/physics/Program.cs` — сериализация `column_contacts` в ответе тика
   (ограниченный массив), без изменения прочих полей для каталогов ≤ v8.

### Gateway (Rust)
7. `server/gateway/src/shared/destructible_wire.rs` — `FALLEN_COLUMNS = 0xa0`;
   `encode_fallen_column(idx:u8, yaw, speed)` (int-усечение, clamp 0..3,
   `trunc(64·(yaw+π)/2π).rem_euclid(64)`, отказ на не-finite);
   `checked_columns` (≤ 125, строго возрастающие); `area_update_columns`;
   `area_create_state(area, chunk, fragiles, columns, trees)` — свойство 2 больше не
   всегда пустое.
8. `server/gateway/src/shared/fragiles.rs` — `ObjectKind::FallingAtom`, разбор v8
   (поля выше; `material_kind`/спаны проверяются по триггеру, не по маскам 18/128);
   `State.fallen_columns`; `column_contact(...)` с политикой D1, идемпотентно
   (упавший/уничтоженный → `None`), без ram-proof (sensor не меняет движение);
   v7 по-прежнему отвергает `falling_atom`; `native_fallen_columns(chunk)`;
   `scene_version`/`historical_scene_hash`/`removed_ids` учитывают столбы.
9. `server/gateway/src/shared/model.rs` — `ColumnContactInput`,
   `apply_column_contacts` в том же тике, что и `apply_vehicle_contacts`.
10. `server/gateway/src/shared/server_scene_runtime.rs` — разбор и границы
    `column_contacts` ответа воркера.
11. `server/gateway/src/shared/server.rs` (публикация рядом с `:1944`) — кэш
    `column_areas`, `area_update_columns` обоим сессиям после ACK-коммита, лог
    `SHARED_COLUMN_PUBLICATION battle= session= chunk= entity= fallen_columns= scene_version=`.
12. `server/gateway/src/shared/mod.rs` (`:915`) — начальное/повторное создание area с
    `native_fallen_columns`.

### Тесты
13. `server/gateway/src/shared/destructible_wire.rs` (tests) — goldens
    `encode_fallen_column` (0, ±π, π/2, 3.2, скорость −4/99, не-finite), конверт
    `[0x12, id, 0xa0, len, count, …, 0x13]`, 125/126, дубли/порядок, create-state со
    всеми тремя массивами.
14. `server/gateway/src/shared/fragiles_tests.rs` — порог для масс MS-1/ИС-7 и
    HP 18/26, `s≠1`, `kdc=2`, yaw/скорость, повтор, вертикальная скорость, v7 отвергает
    falling_atom, хэш сцены.
15. Новый `server/gateway/src/shared/server_falling_atom_real_tests.rs` — реальный
    пакет Прохоровки: контакт → ACK → коммит → публикация 0xa0 обоим → rejoin.
16. `tests/test_destructible_wire_columns.py` — независимая от Rust Python-реализация
    формулы из байткода (клиентский код не исполняется) сверяет goldens п. 13.
17. `tests/test_compound_destructible_catalog.py`, `tests/test_map_package.py`,
    `tests/test_destructible_catalog.py` — v7 и базовые буферы побайтно прежние;
    v8 Прохоровки: 71 falling_atom, индексы = static; Химмельсдорф — ForgedFence
    исключён с причиной; детерминизм буфера триггеров; отказ при tilt-направлениях.
18. `tools/map_physics_probe.py` — сценарий «наезд на столб»: ровно один контакт,
    скорость/поза танка побитно как без триггера.

### Документы
19. `docs/research/MAPS02_FALLING_ATOMS.md` (результаты), `docs/STATUS.md`,
    `docs/research/INDEX.md`; этот план удаляется после слияния.

## Проверки

- `python -B -X utf8 -m unittest tests.test_map_package tests.test_compound_destructible_catalog tests.test_destructible_catalog tests.test_destructible_wire_columns`
- `python -B -X utf8 tools/map_package.py regression` (Карелия/Прохоровка побайтно)
- `python -B -X utf8 server/build.py physics --out local/build/server/physics-maps02-01`
- `python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-maps02-01`
- Канонический полный gate на чистом дереве (правило canonical-gate) — FAIL-набор не шире базы.

## Что нужно стенду для native-проверки

- Физика из этой ветки: `python -B -X utf8 server/build.py physics --out local/build/server/<новый>`
  (в worktree собрана `physics-maps02-01`, DLL `04308d80…`); gateway — из этой же ветки.
- Каталог профиля 13: `local/evidence/20261021-maps02-impl01/catalogs/05_prohorovka/manifest.json`,
  SHA256 `61ce7951421091427a122e1c3875481f4053f3a6b9c910cb98195a644daff6d6` (рядом worker v9
  `efd83118…` и два файла `falling-atom-triggers.*`). Карта `05_prohorovka`, пулы Прохоровки.
- Только IPC7 battle scene (профиль 13); старый одиночный drive-путь каталог v9 отвергает.
- Логи: `SHARED_COLUMN_FALL` (решение домена), `P05C_SCENE_COMMIT`, `SHARED_COLUMN_PUBLICATION`.
- Проверенные цели: столбы 50, 128, 200 (проба `probe02`, спавн — в `receipt.json`).

## Native-проверка владельца (после одобрения и PASS выше)

Новый стенд `local/stands/maps02-<дата>-01` из одного checkout этой ветки (стенд
`full-test-20261020-06` и клиенты `local/clients/p03f/*` не трогаем; клиенты для
проверки — отдельная установка через `tools/interactive_client.py prepare`).
Карта — **Прохоровка** (индексы столбов OBSERVED native); Малиновка — второй прогон
(индекс INFERRED). Пул MS-1/ИС-7, каталог v8.

| # | Действие | Ожидание |
|---|---|---|
| 1 | ИС-7 медленно (< 5 км/ч) упирается в столб | столб стоит, танк проходит сквозь (как у оригинала) |
| 2 | ИС-7 на 15+ км/ч в столб | столб падает **один раз** в сторону движения, у обоих клиентов; скорость не падает |
| 3 | MS-1 на ~15 км/ч / на полном ходу (≥ 27 км/ч) | стоит / падает (порог ≈ 25,7 км/ч для `env414_Pole1`, HP 18) |
| 4 | Повторный наезд на лежащий столб | ничего, без новой публикации |
| 5 | B выходит из боя и возвращается (rejoin) | столб лежит без анимации падения |
| 6 | Лог сервера | `SHARED_COLUMN_PUBLICATION` по одному на падение и сессию, без `SHARED_BATTLE_FAILED` |

Звук/эффекты падения сверяются только визуально владельцем; native без запуска — NOT_RUN.

## Ограничения и откат

Нет падения от снаряда/сплэша/других объектов; закон 0.9.1 не заявляется; угол
упора и поза — клиентские; `gaf023_ForgedFence` и прочие исключения — статические.
Откат: профили без каталога v8 работают как прежде (v7 и буферы не меняются);
вернуть ветку `codex/maps-01-map-pipeline`, собрать физику/gateway оттуда.
