# P02 — Tactical Steel UI: bounded hangar pipeline audit

Статус: **DOCS-ONLY / IMPLEMENTATION BLOCKED**  
Дата: 2026-10-08 (Asia/Yekaterinburg)  
Ветка: `codex/p02-hangar-tactical-ui-audit`

## Цель

Проверить, каким реальным UI-пайплайном пользуется клиент World of Tanks
0.9.1 #717 RU, и подготовить узкую, проверяемую карточку для Tactical Steel
ангара. Скриншот пользователя используется только как наблюдение текущего
экрана; он не является макетом и не доказывает наличие какого-либо API.

## Границы этой карточки

- Только read-only исследование и документы.
- Оригинальная копия клиента не трогается.
- Исследовательская копия не устанавливает новый UI и не меняет `.pyc`, SWF,
  GFX, `.pkg`, сервер, протокол, fixture или аккаунт.
- Не создаётся HTML, web-приложение, Unity-сцена или офлайн-ангара.
- Не вводятся `HangarViewModel`/`HangarController` как фиктивные классы до
  подтверждения реальной границы данных и событий.

## Рабочие шаги

1. Зафиксировать входы: хеш приклеенного запроса и PNG, client manifest,
   версию/регион и допустимые корни клиента.
2. Сопоставить native Hangar controller, `LobbyView`, `HangarMeta`,
   `TankCarouselMeta` и hangar child panels по bounded bytecode records.
3. Сопоставить вызовы обновления с уже существующими кэшами/событиями:
   `g_currentVehicle`, `g_itemsCache`, `g_clientUpdateManager`,
   `g_playerEvents`, prequeue/event bus и Flash `as_*` callbacks.
4. Проверить наличие UI payload в GUI index: `hangar.swf`, `TankCarousel.swf`,
   `carousels.swf`, `crew.swf`, `AmmunitionPanel.swf`, `vehicleInfo.swf`,
   `lobby.swf`, `LobbyMenu.swf` и `inventory.swf`.
5. Разделить VERIFIED/OBSERVED/INFERRED/UNKNOWN и записать, что нужно для
   безопасного replacement-пилота.
6. Остановить карточку до owner-gated native replacement и screenshot/click
   acceptance.

## Критерии готовности карточки

- Есть hash-bound отчёт с путями к контроллерам и GUI index.
- Указаны существующие точки входа/обновления и сохранённые действия UI.
- Для прямого SWF/GFX редактирования явно указаны ограничения и откат.
- Нет заявлений о работающем Tactical Steel UI без native запуска и PNG.
- Один следующий шаг: owner-gated replacement одного существующего Flash
  компонента после отдельного разрешения на P02.

## Evidence

- `local/evidence/20261008-p02-tactical-ui-audit-01/summary.json`
- P00/P01 GUI index: `local/evidence/20261002-p00-p01/static/gui-index.json`
- Static Hangar records: `local/evidence/20261004-p02-hangar/data-agent/hangar-populate/`
- Static carousel records: `local/evidence/20261004-p02-hangar/data-agent/carousel-static/`
- Native hangar history: `local/evidence/20261004-p02-hangar/`

## Откат

Для этой карточки откат runtime не нужен: изменяются только tracked docs и
ignored evidence receipt. Git-откат — `git revert <commit>` после review; не
использовать `reset --hard` и не менять original/research client вручную.

