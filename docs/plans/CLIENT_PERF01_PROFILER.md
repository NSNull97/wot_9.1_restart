# CLIENT-PERF-01 — глобальный профилировщик клиента только для диагностики

Ветка `codex/client-perf-01-profiler-flag` от `codex/refactor-01-plan` (`17b5242`, R0–R5 ещё не в main: карточка трогает
те же `tools/interactive_client.py` и `client_patch/*`). Порядок владельца 03.11: REFACTOR → **CLIENT-PERF-01** → UI-PREF01.
Начато ночью 04.11 по разрешению владельца «продолжить идти по плану задач».

## Факты

- VERIFIED (аудит `codex/client-stutter-audit` `c4979a8`, `docs/research/CLIENT_STUTTER_AUDIT.md` на той ветке): наш патч
  ставит глобальный `sys.setprofile`; в бою fps 102–105 → 84, доля кадров > 33 мс примерно вдвое больше. Фризы загрузки
  (1,2–1,8 с) и ангара (5,3–5,6 с) — в основном движок, профилировщик их не создаёт.
- VERIFIED (чтение `client_patch/sr_interactive.py`): `init()` безусловно вызывает `sys.setprofile(profile_calls)`.
  `profile_calls` только пишет записи в трассу; действия от записей — лишь под файлом управления тестом (`test_control`:
  сценарии арены, карты, долгого ангара, экипажа) или при пассивной съёмке UI (`capture_ui_passive`, скриншоты подсказок).
- VERIFIED: `observe_profile` слоёв экипажа `p04f…p04k_crew_ui` и `p09d_ammo_ui` — наблюдатели доказательств: записывают
  родные команды и ответы; их `native_event` без активного сценария сразу возвращается. Поведение экипажа и БК в ангаре
  ставят обёртки, а не профилировщик. Побочно: на несовпадении эти наблюдатели бросают `RuntimeError` из профилировщика,
  то есть в родной код игры.
- OBSERVED: обычная установка владельца (`install-a-35`): `test_control` нет, `capture_ui_passive` false.

## Изменение

1. `sr_interactive.native_call_trace_wanted(settings)`: профилировщик нужен, только если задан `test_control`, включена
   `capture_ui_passive` или явно `trace_native_calls`. `init()` ставит его только тогда и пишет в трассу
   `native_call_trace` с причиной. Остальная трасса (логин, жизненный цикл, ошибки, `trace_pose_10hz`) не меняется.
2. `tools/interactive_client.py prepare --trace-native-calls` — явное включение для ручной диагностики (например, разбор боя
   с родными колбэками урона). Ключ `trace_native_calls` всегда пишется в настройки как bool; не bool — отказ при загрузке.
3. Тесты: правило (AST-извлечение функции, как `test_interactive_primitive`), флаг prepare → настройка.

## Проверки и приёмка

- Python 3: затронутые наборы; CPython 2.7.3: компиляция `sr_interactive.py` установщиком; полный Python-набор в D: = база.
- Native (владелец): установка без флага — в трассе `native_call_trace enabled=false`, игра и экипаж/БК в ангаре как раньше,
  fps в бою на повторе против прежней установки. С флагом — прежние записи `native_*_call`. NOT_RUN до утра: переустановка
  клиентов владельца — только по его команде.
- Откат: `--trace-native-calls` возвращает прежнее поведение; полный — revert ветки.
