# Серверные исходники Стального рубежа

Это основное место серверного кода. Здесь лежат исходники, манифесты зависимостей
и инструкции; результаты сборки, рабочие настройки и данные находятся в `local/`.
Текущая структура не является готовым пакетом для удалённого развёртывания.

```text
server/
  manage.py             управление собственной локальной службой
  build.py              сборка в отдельный свежий local/build/ каталог
  check_layout.py       проверка структуры и единственного источника кода
  layout.json           перемещения, старые точки входа, общие зависимости
  control/              конфигурация, жизненный цикл, владение процессами
  identity/service.mjs  точка запуска авторизации общего аккаунта
  identity/account_service.mjs  opt-in владелец account_id, credentials и sessions
  contracts/                 versioned typed identity boundary
  gateway/
    Cargo.toml          пакет sr-gateway
    src/
      main.rs           обычная точка входа
      session.rs        серверная сессия
      protocol/         login, redirect, baseapp, channel, reliable, transport, capture
      account/          model, hangar, identity
      arena/            codec, control, vehicle, ready, movement
      battle/           domain loadout and profile4 ownership adapter
      drive/            model, worker, world, service
  physics/              PhysicsWorker.csproj, Program.cs, CheckedInput.cs
```

Названия файлов описывают назначение. Не добавлять к ним `P01`, `P02`, `091`,
`v2`, даты экспериментов, `final`, `new` или `copy`. Версия протокола относится
к контрактам совместимости; версии данных — к схемам и манифестам; история —
к Git и доказательствам. Внутренние старые Rust module aliases сохранены для
переноса без изменения поведения. Сетевые ID, исходные ресурсы и ключи
локализации этим правилом не переименовываются.

Проверка и обычное управление из `D:\WoT_9.1_Server`:

```powershell
python -B -X utf8 server/check_layout.py
python -B -X utf8 server/manage.py status --config local/server/service.json
```

Если собственный backend остановлен и сайт уже работает:

```powershell
python -B -X utf8 server/manage.py start --config local/server/service.json --map-drive local/server/map-drive/pool.json
```

Остановка и восстановление подтверждённо устаревшего состояния:

```powershell
python -B -X utf8 server/manage.py stop --config local/server/service.json
python -B -X utf8 server/manage.py recover --config local/server/service.json
```

Не удалять supervisor lock вручную. Старые команды `tools/local_server.py`
используют ту же реализацию. Историческая `init` ещё читает исследовательский
capture и создаёт локальную конфигурацию со старым закреплённым executable;
переезд рабочей конфигурации к новой сборке требует отдельной проверки.

Сборка не заменяет работающие binaries. Каждый `--out` должен быть новым;
повторно использовать существующий каталог нельзя. Например:

```powershell
python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-check-03
python -B -X utf8 server/build.py physics --out local/build/server/physics-check-03
```

Gateway создаёт `sr-gateway.exe`. Проект физики называется `PhysicsWorker.csproj`;
assembly пока сохраняет имя `MapDriveWorker` для действующего IPC/loader.
`--legacy` проверяет старую Cargo/MSBuild точку сборки на тех же исходниках.
Драйвер использует уже закреплённые локальные caches, offline/locked restore
и Windows toolchain. Полные команды, stdout/stderr, хеши и результаты сохраняются
в `--out`. Linux сборка и native Linux запуск пока **NOT_RUN**.

Границы остальных папок:

- `web/` — сайт. Общая реализация identity пока frozen здесь; зависимости явно
  перечислены в `layout.json`, а не скопированы в сервер второй раз.
- `tools/` — исследования, извлечение данных, диагностика и старые точки входа.
- `client_patch/` — адаптер исследовательского клиента.
- `tests/`, `docs/` — тесты и документация.
- `local/` — конфигурация, БД, секреты, контент, caches, сборки и доказательства;
  каталог исключён из Git.

Не помещать реальные `.env`, keys, tokens, service configs, БД, дампы,
клиентские ресурсы, `bin/`, `obj/`, `target/`, `node_modules/` в `server/`.
`check_layout.py` проверяет известные нарушения структуры, но не доказывает
отсутствие произвольного секрета внутри исходника и не является deploy allowlist.

## Opt-in identity boundary

`server/identity/account_service.mjs` — отдельный loopback-only процесс с
versioned контрактом `identity.account.v1`. Он владеет только account UUID,
email/password hashes, nickname, profile и browser sessions. Портал-срез
запускается через `web/src/account_server.mjs` и использует
`server/contracts/identity_client.mjs`; он не импортирует `web/src/app.mjs`,
`store.mjs`, `security.mjs` или `game-adapter.mjs` и не читает игровые таблицы.

Это staged стенд в `local/staging/identity-boundary/`, а не переключение текущего
сайта/identity/gateway. Для локальной проверки используются только свежие
тестовые SQLite и токены из процесса:

```powershell
node --test tests/identity_boundary.test.mjs tests/account_portal.test.mjs
```

Новый service принимает `POST /identity/v1/{operation}` только с loopback,
точным `Content-Length`, ролью `portal` или `game` и соответствующим service
token. `game` получает только `account_id`, ник и `created_at` через
`credentials/verify`; пароль, email, browser session и игровые fixtures ему не
отдаются. Неверный contract, credentials, роль или недоступный сервис дают
явную ошибку; портал не создаёт гостя при аварии identity.

Подробности, ограничения, результаты и откат: [SOURCE_LAYOUT](../docs/SOURCE_LAYOUT.md).
Контракт worker: [physics/README](physics/README.md).
