# P03D — battle ammo panel rows

Дата: 2026-10-07, Asia/Yekaterinburg.

## Цель

Передать родному клиенту все три доказанные строки боекомплекта МС-1 в
`Avatar.updateVehicleAmmo`, чтобы battle HUD получил AP, кумулятивный и
фугасный слоты. Фактическая серверная загрузка остаётся `2570:20`, а два
остальных типа передаются с количеством `0`.

## Основания и классификация

- **VERIFIED_STATIC:** `Avatar.updateVehicleAmmo` — entity method `0x13,0x44`
  с аргументами `INT32, UINT16, UINT8, INT16`, 9 байт аргументов.
- **VERIFIED_NATIVE_HANGAR:** закреплённый экспорт МС-1 содержит строки
  `2570:20`, `2826:0`, `3082:0`, порядок совпадает с `native_default_ammo`
  и GUI callback `as_setAmmoS`.
- **VERIFIED_NATIVE_HANGAR:** `equipment`/`consumables` в compatibility
  input отсутствуют; trace содержит `[[], [], []]` для обоих трёхслотовых
  типов. Фальшивые предметы не добавляются.
- **OBSERVED:** после предыдущей карточки клиент показывает только AP
  `2570:20` в бою.
- **OWNER_OBSERVED:** один `updateVehicleAmmo` на каждую shell row создал
  видимую battle ammo panel: `2570:20`, `2826:0`, `3082:0`.
- **UNKNOWN:** можно ли выбирать zero-count rows и нужен ли отдельный battle
  message для equipment; текущий MS-1 input equipment/consumables не содержит.

## Объём

1. Расширить bounded native ammo codec фиксированной панелью из трёх строк.
2. Добавить все три 11-байтовых entity methods после существующего binding,
   сохранив префикс, порядок и атомарную reliable enqueue.
3. Обновить route/unit проверки для `155 = 122 + 3*11` байт и порядка
   `2570:20`, `2826:0`, `3082:0`.
4. Собрать свежий изолированный gateway и сохранить receipt.

Оборудование, расходники, fire/reload, переключение типов и live deployed
gateway в эту карточку не входят.

## Приёмка

Offline source/tests/build/evidence — `PASS`. Один owner-driven вход на МС-1
показал все три ammo slots на native battle HUD: `PASS_OWNER_NATIVE_AMMO_PANEL_HUD`.
Этот owner run не проверял выбор zero-count rows, fire/reload/consumption,
physics или отдельное equipment-сообщение.

## Откат

Вернуть изменённые source-файлы по свежему source-manifest карточки и удалить
только новый isolated build/evidence. Deployed gateway, original client,
research client, БД и текущий supervisor не трогать.
