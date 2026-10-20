# P06T — damaged module recovery

## Цель

Закрыть три подтверждённых дефекта native global-heavy прогона на текущем P06T runtime:
выбитый engine не возвращается из `Destroyed`, fuel tank после завершения fire не
возвращается в рабочее повреждённое состояние, а restored engine не даёт нормальный
управляющий steering path.

## Подтверждённые границы

- VERIFIED source: `CAPS[*].regen` — закреплённые `maxRegenHealth`; это целевое
  здоровье восстановления, не новый critical threshold.
- VERIFIED source: #717 `DAMAGE_INFO_CODES`: `DEVICE_REPAIRED_TO_CRITICAL=18`,
  `DEVICE_REPAIRED=19`, `FIRE_STOPPED=35`.
- OBSERVED native: после engine/fuel destruction recovery transition не приходит;
  post-fire state остаётся `Destroyed`, а управление остаётся в stopped/jerky path.
- UNKNOWN: точные исторические repair timers, crew modifiers и server RNG. В этой
  карточке используется bounded LAB delay 1000 ms, явно не выдаваемый за исторический
  алгоритм.

## План изменений

1. `p06t_device_state.rs`: хранить bounded repair deadline/cause для engine и fuel
   tank; при переходе в zero ставить deadline; после deadline и только при живом,
   незамороженном actor поднимать здоровье до source `regen` и журналировать
   `Change::Device { repair: true }`; repair не продлевает fire и не считается новым
   critical-hit.
2. `p06t_publication.rs` и `lifecycle_result.rs`: публиковать/проецировать repair
   как code 18 (`Critical`) либо 19 (`Normal`), не увеличивать `crits` и не
   раскрывать лишние module identities.
3. `server_scene_runtime_p06t_tests.rs` и `p06t_device_v2_tests.rs`: узкие тесты для
   engine/fuel recovery и steering/control после восстановления; сохранить старые
   v1/v2 и terminal freeze assertions.
4. Обновить `docs/STATUS.md` короткой записью с фактическим focused gate и native/UI
   `NOT_RUN`; сохранить evidence в новой `local/build` папке (локальные файлы не
   коммитить). Для pinned GNU driver закрепить relocatable `-B` и порядок PATH,
   чтобы bundled `ld.exe` не уступал место llvm-mingw shell wrapper.

## Проверки и критерий

- Focused Rust filter `p06t_`: **215 PASS / 0 FAIL / 0 ignored**, build PASS;
  targeted recovery smoke: **1 PASS / 0 FAIL / 0 ignored**.
- Узкие тесты показывают: zero → regen, fire заканчивается без terminal freeze,
  repair event имеет `repair=true`, restored engine выдаёт steer и валидный cruise.
- Native/UI/audio/manual replay остаются NOT_RUN до владельческого прогона.

## Откат и ограничения

Откат — revert карточечного commit либо возврат на parent `8c911e7`; не откатывать
SQLite и не трогать original client. Если focused/build FAIL, карточка остаётся в
ветке и не merge'ится.
