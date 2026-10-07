# План карточки: game account ownership assertion

## Цель

Зафиксировать отдельный `game.account.v1` contract/API между identity
assertion и game-account owner. Будущий battle-loadout gate должен получать
проверяемую принадлежность профиля аккаунту: `account_id`, native database ID,
profile/snapshot revisions и digest профиля. Пароль, email, browser session,
fixture path и native wire IDs в assertion не попадают.

## Границы

- Pure contract + deterministic ownership builder/validator и isolated tests.
- Источник identity — уже принятый `identity.account.v1` game assertion
  (`account_id`, nickname, created_at).
- Game owner добавляет только server-owned profile metadata и SHA256 профиля.
- Arena/gateway/physics, battle worker, loadout semantics и live service wiring
  не меняются. Native compatibility остаётся отдельным adapter concern.
- Это не выдача боевого допуска и не proof владения vehicle/loadout; это узкая
  account ownership boundary, которую следующий domain contract сможет принять.

## Шаги

1. Сохранить read-only baseline identity contracts/service/tests.
2. Добавить versioned `game.account.v1` contract и builder/validator с exact
   DTO shape, bounded fields и запретом credential/session/path leakage.
3. Проверить identity/profile mismatch, digest/revision errors, forbidden extra
   fields и успешный assertion на synthetic server-owned profile.
4. Записать receipt и ограничения. Не запускать live identity, game DB или
   native client.

## Откат

Удаляются только новые contract/service/test/docs и
`local/evidence/20261006-game-account-ownership/`. Existing identity service,
live DB, gateway, battle code и previous receipts остаются без изменений.
