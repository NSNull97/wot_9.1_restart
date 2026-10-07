# Game account ownership assertion

Добавлен отдельный `game.account.v1` contract для следующего domain gate.
`server/identity/ownership.mjs` принимает уже проверенный game assertion из
`identity.account.v1` и server-owned profile metadata, затем возвращает строго
ограниченный `ownership/assert` DTO:

- `account_id`, `nickname`, `created_at`;
- `native_database_id`;
- `profile_version`, `snapshot_revision`, `profile_sha256`;
- `ruleset`, `identity_contract`, `ownership_source`.

Builder сверяет UUID, ник и creation timestamp identity/profile, ограничивает
profile bytes 8192 байтами и считает SHA256 локально. Contract validator
отвергает лишние поля, email, password, browser session token и fixture path.

Проверены четыре isolated Node tests: успешная сборка/разбор, mismatch subject,
границы profile bytes и contract leakage/extra fields. Существующие пять
identity/account tests тоже прошли. Native gateway, arena, physics, battle
worker, live identity DB и клиент не запускались и не менялись.

Это assertion принадлежности game profile аккаунту. Он не является разрешением
на бой, не содержит loadout или vehicle reservation и не доказывает native
совместимость. Следующий domain contract может принять этот assertion и отдельно
решить правила loadout; native wire/client compatibility остаются адаптером.
