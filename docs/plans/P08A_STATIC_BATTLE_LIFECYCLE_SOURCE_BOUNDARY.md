# P08A — static battle lifecycle source boundary

Дата карточки: 2026-10-08. Ветка: `codex/p08a-static-battle-lifecycle-source-boundary`.

## Цель

Зафиксировать узкий, hash-bound статический срез lifecycle деклараций #717 для
`PlayerAccount`, `PlayerAvatar`, `ClientArena` и `Vehicle`. Это подготовка
исследования P08: она связывает уже прочитанные P00/P01 артефакты с будущим
native battle lifecycle, но не добавляет серверные callbacks, wire IDs,
таймеры, звук или пользовательский UI.

Карточка считается закрытой только для **source boundary**. Она не объявляет,
что клиент вошёл в бой, создал arena или воспроизвёл десять боёв.

## Источники и ограничения

Единственный входной комплект — локальная квитанция
`local/evidence/20261002-p00-p01/` для проверенного World of Tanks 0.9.1
#717. Главный lifecycle-файл имеет SHA-256
`f4b8e847513258fff543f46b3efa5c41d3b191df91863a30e04a54fd8220fbcf` и размер
17049 байт. Сопутствующие статические контракты: `summary/contracts.json`
(SHA-256 `c9bd0893dfdb1ec6c09de9af200b04eb19b6dd08f71b97f40b32bb831a70a6e5`),
`summary/resource-facts.json` (SHA-256
`817a9c01dd7b367c8d2b54be517f44c08720b3a508bddca0d8f0436f069c5d71`),
`summary/sources.json` (SHA-256
`67a4d82108d821a3a39614ba9b3a278cbf8330b4329d6c6e5e9b5cc8ef53eb9a`).

Это статический Python/DEF/bytecode-derived manifest, а не packet capture.
Числовые wire IDs, порядок entity streams, native timing и реальные
side-effects из одного списка имён не выводятся.

## VERIFIED_STATIC: объявления и наблюдаемые точки перехода

| Область | Закреплённые декларации | Что можно утверждать |
|---|---|---|
| Account | `PlayerAccount.onBecomePlayer`, `onBecomeNonPlayer`, `showGUI` (`scripts/client/Account.py`) | В клиентском account proxy существуют вход в player-состояние, выход и переход к GUI; имена и исходные строки закреплены манифестом. |
| Avatar | `PlayerAvatar.onBecomePlayer`, `onBecomeNonPlayer`, `onEnterWorld`, `onLeaveWorld`, `onSpaceLoaded`, `vehicle_onEnterWorld`, `vehicle_onLeaveWorld`, `updateArena`, `moveVehicle`, `shoot` (`scripts/client/Avatar.py`) | В Avatar-классе статически присутствуют player/world/space/vehicle lifecycle и игровые command entry points; `shoot` и `moveVehicle` — только названия/ссылки исходного манифеста. |
| Vehicle | `Vehicle.onEnterWorld`, `onLeaveWorld`, `set_health`, `onHealthChanged` (`scripts/client/Vehicle.py`) | Vehicle имеет статические вход/выход world и обработчики health; они не доказывают серверное применение урона или синхронизацию. |
| Arena | В `summary/contracts.json` присутствует entity-контракт `arena` с декларациями `onVehicleCreated`, `onCreateVehicleFailure`, `setAvatarReady`, `removeAvatar`, `sendArenaStateTo`, `stopByFailure`, `reuse`, а также свойствами `state`, `typeID`, `roundLength`, `roster`, `geometry_cell`, `gameplayID`. | Схема #717 описывает arena-side lifecycle surface и поля состояния. Имена/типы — static only; фактический порядок вызовов и заполнение payload не измерены. |
| Avatar ↔ arena | `PlayerAvatar.onEnterWorld` содержит статические ссылки на `ClientArena`, `arenaUniqueID`, `arenaTypeID`, `arenaBonusType`, `arenaGuiType`, `arenaExtraData`; `onLeaveWorld` содержит `onLeaveArena`, очистку vehicle/projectile/arena ресурсов. | Есть измеряемые точки связки Avatar и arena в декомпилированном клиентском коде. Это не доказательство успешной native arena сессии. |
| Vehicle ↔ Avatar | `vehicle_onEnterWorld`/`vehicle_onLeaveWorld` и `Vehicle.onEnterWorld`/`onLeaveWorld` присутствуют в одном hash-bound manifest. | Статический срез показывает две стороны жизненного цикла; серверный ownership, roster admission и удалённое отображение остаются отдельными проверками. |

## VERIFIED_STATIC: границы доверия

- Манифест фиксирует `source_filename`, имя функции, строку и набор
  обнаруженных имён/ссылок. Это проверяемый факт о входном артефакте.
- `summary/contracts.json` фиксирует декларации entity methods/properties и
  типы аргументов; у этих записей `wire_id` остаётся `UNKNOWN`, поэтому IDs
  нельзя назначать по алфавиту или по порядку файла.
- Существующие P01 доказательства подтверждают только diagnostic native
  login/rejection. Они не превращают статические lifecycle names в успешный
  Account → Avatar → Arena → Vehicle run.

## UNKNOWN / NOT_RUN

Следующие пункты намеренно остаются открытыми и не могут быть закрыты этой
карточкой:

1. **UNKNOWN:** числовые wire IDs, stream/entity method order, flags,
   serializer details, ACK/sequence и fragment boundaries.
2. **NOT_RUN:** настоящий native `Account → Avatar → ClientArena → Vehicle`
   переход с успешным входом в бой; callback order и payload values.
3. **NOT_RUN:** native battle HUD/UI, звук/FX, ready/countdown и timer
   semantics; наличие локальных callback names не заменяет визуальную или
   слуховую приёмку.
4. **NOT_RUN:** повторяемый сценарий десяти боёв, rejoin/leave, reconnect,
   vehicle death и battle result lifecycle.
5. **UNKNOWN:** серверная authority/visibility, roster ownership, damage/HP,
   equipment/ammo/crew admission и соответствие remote vehicle lifecycle.
6. **UNKNOWN:** соответствие static `shoot`/`moveVehicle` фактическому wire
   payload; P03/P06 evidence закрывает только свои узкие ранее принятые
   контракты.

## Безопасность и откат

Карточка read-only: не запускает оригинальную или research копию клиента, не
меняет deployed service, database, gateway или runtime. Откат — удалить только
три документа этой карточки либо сделать `git revert` её merge-коммита;
локальная исходная квитанция не модифицируется.

## Следующий gate

Единственный следующий шаг после этой статической границы — owner-gated
native capture с сохранением исходной последовательности событий и raw
payload. Сначала нужен один короткий Account/Avatar/Arena/Vehicle проход;
десять боёв, UI/audio/timer и battle authority проверяются только после
успешной минимальной трассы.
