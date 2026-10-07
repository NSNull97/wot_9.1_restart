# Identity/account boundary — 2026-10-06

## Цель

Сделать первый рабочий срез разделения сайта, авторизации и игрового backend:
регистрация → вход на сайт → проверка тех же credentials game-role → сохранённый
account_id, ник и профиль. Целевой продукт остаётся настоящей native-сетевой
инфраструктурой с боями 15×15; этот отчёт закрывает только account boundary.

## Что изменено

- server/contracts/identity.mjs — envelope identity.account.v1, версии, операции,
  error/status mapping и bounded response validation.
- server/contracts/identity_client.mjs — loopback HTTP client с role isolation,
  content-length/deadline/contract checks и явным IdentityError.
- server/identity/security.mjs — самостоятельная identity-owned email/nickname/
  password policy, scrypt v1 и token helpers. Legacy web/src/security.mjs
  frozen; credentials не копируются между runtime DB.
- server/identity/schema.mjs — append-only schema migration v1 с accounts,
  sessions, rate_limits, schema_migrations.
- server/identity/account_service.mjs — отдельный loopback writer. Portal role
  owns registration/login/profile/session; game role owns only credentials/verify.
- server/layout.json — records the new contracts and identity account service
  ownership without changing native IDs or old relocation receipts.
- web/src/account_portal.mjs, web/src/account_server.mjs — opt-in portal;
  old web/src/server.mjs и старые imports не менялись. New portal displays
  not_connected for game state and never opens game tables.
- tests/identity_boundary.test.mjs, tests/account_portal.test.mjs — isolated
  staging tests.
- server/README.md, docs/plans/INFRASTRUCTURE_BOUNDARIES.md, docs/STATUS.md.

## Фактические проверки

Команды:

    node --check server/contracts/identity.mjs
    node --check server/contracts/identity_client.mjs
    node --check server/identity/security.mjs
    node --check server/identity/schema.mjs
    node --check server/identity/account_service.mjs
    node --check web/src/account_portal.mjs
    node --check web/src/account_server.mjs
    node --check tests/identity_boundary.test.mjs
    node --check tests/account_portal.test.mjs
    node --test tests/identity_boundary.test.mjs tests/account_portal.test.mjs
    python -B -X utf8 server/check_layout.py
    python -B -X utf8 server/manage.py status --config local/server/service.json

Реально выполнено:

- PASS: 5 изолированных Node tests. Регистрация в fresh SQLite, явный
  повторный login сайта, profile update/read, один UUID через game-role,
  сохранение после service restart.
- PASS: неверный пароль даёт invalid_credentials/401 для portal и game;
  неверная роль — forbidden/403; старый contract — contract_mismatch/409;
  неподдерживаемая PRAGMA user_version отклоняется до listener; после остановки
  identity портал даёт 503 без guest/fake account.
- PASS: source layout check — 44 server files, 22 preserved relocations,
  remote/Linux readiness остаётся NOT_RUN.
- PASS: read-only server/manage.py status сохранил живые supervisor/identity/
  gateway и сайт отдельного владельца; active config/EXE/DLL/client/live DB не
  переключались.

Receipts, snapshots и audit:

- local/evidence/20261006-infrastructure-boundaries/source-before.json
- local/evidence/20261006-infrastructure-boundaries/before-files.json
- local/evidence/20261006-infrastructure-boundaries/runtime-before.json
- local/evidence/20261006-infrastructure-boundaries/audit-initial/findings.md
- local/evidence/20261006-infrastructure-boundaries/result.json
- local/evidence/20261006-server-layout/final-audit-02/result.json — parent
  source-layout receipt, SHA256 64640f29fbf1a502a318e110c34f89fd76440c6ada2afdbb131c8dc9cda03b6f.

All new DBs and service tokens were created under ignored
local/staging/identity-boundary/ and removed by tests. A freshly timestamped
local/web/runtime/portal.sqlite-wal was observed while the owned site remained
alive; no test opened, copied, migrated or wrote that live database. Process
status and this distinction are recorded in the evidence receipt.

## Границы и неподтверждённое

The new identity service is an accepted HTTP/account boundary. It does not switch
the native gateway: current server/identity/service.mjs and Rust gateway still
use the legacy frozen bridge until a separate migration. HTTP tests do not prove
native compatibility, two real clients, battle simulation, historical physics,
or 15×15. Linux build/ABI, remote login, public transport threat model and load
capacity remain NOT_RUN. Legacy users with nullable email still require an
explicit bind/migration card; this service creates only fresh accounts.

The content/encoder generators still depend on checked client resources and
evidence paths. They remain frozen for the next versioned server-content export;
old profile validators and provenance are not rewritten here.

## Откат и приёмка

Before hashes and the after receipt are under
local/evidence/20261006-infrastructure-boundaries/. Rollback is a guarded
filesystem restore of only files listed in those manifests, after verifying the
working tree has no later changes. Do not use git restore because the project
started untracked. Since the live service was never switched, no runtime config,
EXE, DLL, client tree or live DB rollback is required. Remove the opt-in source
files only after closing any opt-in process; preserve evidence and parent
source-layout receipts.

Приёмка: PASS_IDENTITY_BOUNDARY for isolated registration/login/game account
verification and persistence. Native compatibility and battle acceptance:
NOT_RUN.

Единственный следующий шаг: versioned server content/encoder export with a
portable provenance manifest, retaining existing profile1/profile4 validators and
proving byte/ID equivalence before any game profile writer is switched.
