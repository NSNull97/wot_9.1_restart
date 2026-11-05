# Состояние проекта

Снимок 2026-11-04, main `5816c24`. Только действующее: история разделов, прежние NOT_RUN и снимки карточек —
`git show 8bda1b9:docs/STATUS.md` (сокращено в REFACTOR-01 R2). Порядок карточек — [IMPLEMENTATION_ORDER](IMPLEMENTATION_ORDER.md).

## Сейчас: SHELL-01 — броня целиком (не начата)

SHELLS-R принята 04.11: исследование снарядов в main, конфигурация владельца Shell Mechanics 2.0
([SHELL_MECH](research/SHELL_MECH.md); конфигурация владельца — [Shell Mechanics 2.0](decisions/SHELL_MECHANICS_2_0.md), заменяет v1). Следующая — SHELL-01: ходовая и все
слои Hull/Turret/Gun/Chassis по порядку вдоль луча, материалы «нет записи / armor 0 / factor 0», проверка калибра 182.9.
Закон урона пока прежний (одна пластина LAB без разброса).

REFACTOR-01: R0–R5 и R7 в main 04.11; R6 (модули шлюза) — после PG-01 по решению владельца 04.11, `rustfmt` — решить на R6.

После REFACTOR (порядок владельца 03.11): CLIENT-PERF-01 → UI-PREF01 → снаряды (сначала SHELLS-R) → PG-01 и NET-02/LOAD-200
→ контент (все машины, карты, разрушаемость).

## Принято владельцем и в main

| Дата | Карточки |
|---|---|
| 05.11 | TESTVEH-01: отдельный тестовый Т-62А (Т) (подпись XI, броня 1000 мм, вне дерева и магазина) включается флагом стенда `test_lab`; main-каталоги без изменений |
| 05.11 | BOT-02: боты не стреляют через союзника, доворачивают корпус (ПТ/САУ), меняют позицию при нехватке УВН/УГН, правило застревания по прогрессу (проектная политика `project.bot02.fire-line-hull-reposition.v1`) |
| 05.11 | TRACK-01: починка всех модулей кроме БК (возвращаются повреждёнными, код 18), сбитые гусеницы видны на модели (extras 30/31), повреждённая гусеница не ограничивает подвижность |
| 04.11 | SHELLS-R: исследование снарядов перенесено и сверено с main, проектная политика снарядов v1 (решения 1–8) |
| 04.11 | UI-PREF01: настройки клиента (графика, FOV) сохраняются между запусками, свой файл на клиент; REFACTOR R7 |
| 04.11 | CLIENT-PERF-01: глобальный профилировщик клиента только в диагностике |
| 03.11 | BATTLE-UI: UI-01…06 (настройки, индикатор обстрела, лента и история боя, итоги, уши, маркеры), CRASH-01 |
| 01.11 | PERF-02 (тир X и остаток, MALINOVKA-STEP), LATE-BOTS, LATE-NOTICE-01, CAT-NATIONS-02 |
| 31.10 | IMPACT-01, CAT-NATIONS |
| 29.10 | BW-01 + INPUT-01 + TURRET-01, 15×15-интеграция, AV-01, NET-01, POSTMORTEM-01 |
| 28.10 | MM-01, BOT-01, BATTLE-ANY, SPAWN-15 |
| 25–27.10 | CREW-ANY, DOM-01, GW-01, ARENA-01 |
| 20–21.10 | FULL-TEST, BRIDGE-01 + LOGIN-01, CAT-01, MAPS-01 + MAPS-02 |
| до 19.10 | STAB-01, P08B/P08C, P05C, P07B, P04M, P06T, P04W |

Факты, нужные дальше:

- UI-PREF01 (владелец 04.11 проверил a и b: графика и FOV сохраняются после перезапуска): `prepare --native-preferences
  <относительный путь>` — файл настроек пишет сам движок (`engine_config <preferences>`, путь от
  `%APPDATA%/Wargaming.net/WorldOfTanks`, только внутри `GAYmDev Studio/SteelFrontier`); при первой установке Python-часть
  прежнего профиля переносится в `scriptsPreferences` один раз, пароли и токены отвергаются. Клиенты a `install-a-38`
  (`preferences-a.xml`), b `install-b-17` (`preferences-b.xml`). В `%APPDATA%/Wargaming.net/WorldOfTanks/` (современный клиент)
  наши клиенты не пишут. Без флага — прежний режим. План — `docs/plans/UI_PREF01_NATIVE_PREFERENCES.md` в git на `a960537`.
- CLIENT-PERF-01 (владелец 04.11, стенд -12, клиент a `install-a-36`: «фпс в районе 90-100 держится», прежде 84 в аудите):
  `sys.setprofile(profile_calls)` ставится только при `test_control`, `capture_ui_passive` или `prepare --trace-native-calls`;
  в трассе `native_call_trace`. Диагностика родных вызовов в бою — только с этим флагом. План — `docs/plans/CLIENT_PERF01_PROFILER.md`
  в git на `4182d0f`. Фризы загрузки и ангара (движок, аудит `codex/client-stutter-audit`) не решены — CLIENT-PERF-02…05.
- BATTLE-UI включён по умолчанию; откат `--native-vehicle-markers`, `--hit-indicator off`, `--no-battle-feed`,
  `--no-battle-history`. Шлюз: `battle_events {version 1, feed, history}`, `int_user_settings`, `results_ledger`, `team_score`.
  Иконки классов и событий — локальная копия Lesta (`local/ui-borrowed/`, не в Git).
- LATE-BOTS (`late_bots`): старый Domain не читает seal v2 — откат требует стратегии БД
  (`docs/plans/LATE_BOTS.md` в git на `8bda1b9`).
- Уведомления о боях — только с LATE-BOTS и `p08c_late_notice_experimental` (сейчас false).

## Проверки базы

- Канонический gate в D: (`4e46418`): 1993 PASS / 2 FAIL / 21 ignored. Два FAIL `scene_worker::tests_p04m` — базовые.
- Полный Python-набор в D: (`10f10e5`) 3961 тест, 94 FAIL/ERROR, построчно равен main (`E:/WoT091_Verify_20261031/pyD-*.fails`); сравнивать только
  в D:. Два ERROR `test_server_build_driver` — журналы сборок, потерянные при чистке 24.10.
- `python -B -X utf8 server/check_layout.py` — PASS. Web `npm test` — 85 PASS / 27 FAIL, как на main `05c102a`.

## Открыто

- Счётчик боя со значками классов по порядку ТТ, СТ, ПТ, ЛТ, арта (полосы HP в оригинале нет); урон поверх соседних маркеров.
- CRASH-01: вылетов больше нет (OBSERVED), причина UNKNOWN. Разовые тихие закрытия клиента — INFERRED память 32-битного клиента.
- P10B (комната на N игроков) и NET-02 (два ПК, хостинг) не приняты; PG-01 — эксперимент (`codex/pg-01-dual-store`, `07759e9`), не в main.
- Не сделано: коллизия ствола оторванной башни; ёмкость экипажа > 16 за время аккаунта; бой на машинах без профиля
  физики/брони; разрушаемость всех объектов всех карт; P04L сброс навыков (`codex/p04l-native-skill-reset`, WIP).
- Причина пауз главного цикла шлюза — UNKNOWN (каждая пишется `SHARED_DRIVE_LAG_RESYNC`); микролаг клиента — CLIENT-PERF-01.
- Сборки `--legacy` сломаны.
- Отложено владельцем 05.11 (физика): сбитая гусеница — только поворот на месте со скоростью в половину базового поворота
  ходовой (правило проекта; в 0.9.1 машина обездвижена). Черновик `local/backlog/destroyed-track-pivot-20261105.patch`,
  не применён; нужна пересборка физики. TRACK-01 `c58fda3` (без штрафа за повреждённую гусеницу) в бою не проверен.

## Стенд

- Флаг стенда `test_lab` (TESTVEH-01): `WOT091_TEST_LAB=1` для Python, моста и Domain; `build.py gateway|physics --test-lab`;
  клиент `--test-vehicle-label`. Тестовый вариант в `config/test_lab/` и привязках `*_test_lab`: исследования `646b6193`,
  CAT-01 `bedd6d49`. На сервере уровень Т-62А (Т) — 10, «XI» только в клиенте. У самого T62A_T нет таблицы брони ходовой.
- `full-test-20261105-13` (test_lab): сводка `integrate/testlab-stand` (main + SHELL-02, не в main), шлюз
  `gateway-testlab-integ-release-1cec6d82`, физика `physics-testlab-20261105b`, клиент a `install-a-42`.
- `full-test-20261031-12`: сводка `7f10dac`, шлюз `gateway-integ-release-7f10dac`, клиент a `install-a-40`.
  Порты у стендов одинаковые. Запуск и откат — `local/handoff/HANDOFF.md`.
