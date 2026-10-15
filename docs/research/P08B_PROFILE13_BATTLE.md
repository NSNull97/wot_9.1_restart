# P08B — профиль13, выбранная машина и общий native-бой

Дата: 2026-10-15. Статус: RESEARCH_IN_PROGRESS, native приёмка NOT_RUN.
Ветка `codex/p08b-profile13-battle`, база main
`ffce8cb660e9e6af6872aa4a5de444f461bc73fe`.
План — `docs/plans/P08B.md`; evidence — `local/evidence/20261015-p08b-01/`.

## VERIFIED — предпроверка и границы

- `git status --short --branch`: чистая STAB-ветка до начала; main/origin/main и
  `git ls-remote origin refs/heads/main` совпали с ffce8cb. Новая ветка создана
  именно от main, а не от документационного head403804d STAB.
- Прочитаны ACTIVE_GATE, IMPLEMENTATION_ORDER п.2, STATUS, DEV_NOTES;
  native path рассматривается через P02_MAP_DRIVE/P02_MANUAL_BATTLE_BUTTON,
  текущую реализацию STAB и реальный writer профиля13.
- `battle/profile4_adapter.rs::validate_authenticated` закрепляет source SHA,
  MS-1 inv1/turret5891/gun5892/AP2570, профиль4/snapshot4 и экипаж/20снарядов.
  Это доменная проверка frozen fixture, не admission для реального профиля13.
- Существующий game_vehicle(state,battle_id) — потенциальная основа резерва;
  `NativeAmmoStore.reserve_vehicle` возвращает BATTLE_UNSUPPORTED. Обход через
  базовый writer может рассогласовать projections и не допускается.

## UNKNOWN — перед реализацией

- Точный контракт authoritative selected loadout, поддерживаемых модулей и
  native700 для динамического профиля13; безопасное включение оригинальной кнопки.
- Интеграция hangar writer в shared lifecycle и минимальная атомарная policy
  расхода/ремонта/recovery без новой экономики и без подмены выбранного танка.
- Native/UI/перезапуск с сохранённым резервом ещё NOT_RUN.

Оригинал клиента и рабочая БД при исследовании не меняются. Существенные решения
будут внесены сюда по конкретному коду/трассам; предложенная архитектура не
объявляется исследованным клиентским контрактом.
