# Состояние проекта

Снимок 2026-11-03, main `05c102a`. Только действующее: история разделов, прежние NOT_RUN и снимки карточек —
`git show 8bda1b9:docs/STATUS.md` (сокращено в REFACTOR-01 R2). Порядок карточек — [IMPLEMENTATION_ORDER](IMPLEMENTATION_ORDER.md).

## Сейчас: REFACTOR-01 — очистка и порядок в исходниках

Ветка `codex/refactor-01-plan`, [план](plans/REFACTOR01_PLAN.md) утверждён владельцем 03.11. Поведение не меняется.
R0–R5 влиты в main 04.11 (`0bfa63c`, владелец: «Да, влить»); R6/R7 ждут решений.

- R0 `8bda1b9`: `check_layout.py` с правилом имён (437 имён-долгов в `server/layout.json`, список только сокращается)
  входит в полный gate; карта привязок к байтам — `local/evidence/20261103-refactor01-r0/pin-map.json`.
- R1 (вне исходников): ветки 370 → 20, рабочие деревья 108 → 28; невлитые — в бандле
  `local/archive/branches-20261103/unmerged-82.bundle`, `local/` удалённых деревьев — `local/archive/worktrees-20261103/`.
- R2: удалены планы принятых карточек, отчёты-снимки и `web/*_PLAN|REPORT.md` (решение владельца «Удалить»), STATUS сокращён.
- R3: удалены 18 разовых скриптов без ссылок из кода. R4: общие `tools/gui_atlas.py`, `tools/swf_bitmap.py`,
  `client_patch/native_contract.py` вместо копий (1851 полезная нагрузка UI побайтно та же). R5: 28 свободных от привязок файлов
  названы по смыслу.
- R6 (модули шлюза) и R7 (клиентский патч) не начаты: пересекаются с PG-01, кандидатом PERF-02 и UI-PREF01 — решения владельца
  в списке «На утро» [плана](plans/REFACTOR01_PLAN.md).

После REFACTOR (порядок владельца 03.11): CLIENT-PERF-01 → UI-PREF01 → снаряды (сначала SHELLS-R) → PG-01 и NET-02/LOAD-200
→ контент (все машины, карты, разрушаемость).

## Принято владельцем и в main

| Дата | Карточки |
|---|---|
| 03.11 | BATTLE-UI: UI-01…06 (настройки, индикатор обстрела, лента и история боя, итоги, уши, маркеры), CRASH-01 |
| 01.11 | PERF-02 (тир X и остаток, MALINOVKA-STEP), LATE-BOTS, LATE-NOTICE-01, CAT-NATIONS-02 |
| 31.10 | IMPACT-01, CAT-NATIONS |
| 29.10 | BW-01 + INPUT-01 + TURRET-01, 15×15-интеграция, AV-01, NET-01, POSTMORTEM-01 |
| 28.10 | MM-01, BOT-01, BATTLE-ANY, SPAWN-15 |
| 25–27.10 | CREW-ANY, DOM-01, GW-01, ARENA-01 |
| 20–21.10 | FULL-TEST, BRIDGE-01 + LOGIN-01, CAT-01, MAPS-01 + MAPS-02 |
| до 19.10 | STAB-01, P08B/P08C, P05C, P07B, P04M, P06T, P04W |

Факты, нужные дальше:

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

## Стенд

`full-test-20261031-12`: шлюз `local/build/server/gateway-uiblock-release-30a6185`, физика `physics-bti-d03969e`,
клиент `install-a-35`. Запуск и откат — `local/handoff/HANDOFF.md`.
