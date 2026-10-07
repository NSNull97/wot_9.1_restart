# Единый аккаунт сайта и игры — P02

Дата: 2026-10-04. Это узкая реализация карточки
`docs/plans/P02_unified_account_entry.md`. Регистрация и проверка пароля имеют
один источник: существующую таблицу `users` сайта. Доменный `account_id`
**равен `users.id`**, а не связывается с ним отдельной пользовательской операцией.

**VERIFIED:** актуальная изолированная серия HTTP/SQLite — 58/58 PASS;
проверены email-only вход, миграция schema1→2, кириллический ник, две регистрации, вход на сайт теми же
паролями, вход через внутренний игровой интерфейс, отсутствие записей профиля
при неверном пароле, изоляция аккаунтов и перезапуск bridge с прежними ID/данными.
Это не самостоятельное доказательство совместимости с EXE: интегральную native
приёмку ведёт root в отчёте текущей карточки.

## Границы данных

`src/store.mjs:openIdentityReader` открывает веб-БД только для чтения, с
`query_only=ON`. Он не запускает миграции, не создаёт сессии, не переписывает
хеши и не меняет `last_login_at`. Проверка использует **тот же**
`security.mjs:verifyPassword`, что и обычная форма сайта: scrypt
`N=131072,r=8,p=1`, максимум две одновременные KDF-операции. Unicode и пробелы
пароля сохраняются. Вход допускает только ASCII email; ник хранится отдельно.
Точные правила, миграция и привязка прежнего аккаунта — [EMAIL_IDENTITY.md](EMAIL_IDENTITY.md).

Отдельная SQLite `game.sqlite` содержит только `game_meta`, `game_profiles`
и ограниченные счётчики попыток `game_limits`; паролей и их копий там нет.
`game_profiles.account_id` — уникальный UUID из `users`, `native_id` — стабильный
положительный signed32 ID слоя совместимости. Первый успешный игровой вход
создаёт профиль версии 1 и публикует неизменяемый каталог `UUID/r1` атомарным
переименованием. Повторный вход проверяет сохранённые метаданные и SHA-256
payloads, затем использует тот же каталог. Несовпадение исходных descriptors
при перезапуске отклоняется: для смены версии требуется отдельная миграция.

Начальный профиль — **test_lab**, а не историческая экономика: 100000 кредитов,
0 золота, 0 свободного опыта, одна выданная MS-1 из проверенного native descriptor,
без экипажа и боекомплекта. Бои/победы/поражения/ничьи равны нулю: это новый игрок,
история не придумана. Эти ресурсы и snapshot revision сохраняются в game DB;
неизменяемый стартовый инвентарь определяется версией профиля и сохраняется
в его payloads. Покупки, продажи, бои, прогресс и запись игровых данных через
сайт отсутствуют. Native slot/berth prices — явно недоступные тестовые
справочные значения, а не бесплатные работающие операции.

## Служебный интерфейс

Bridge слушает **только `127.0.0.1`**. Его нельзя публиковать через внешний
reverse proxy. Host должен в точности совпадать с `127.0.0.1:<port>`, Origin
заголовок отклоняется. Исключая `/health`, требуется
`Authorization: Bearer <secret>`; secret — ровно 43 base64url-символа из
локального файла, без перевода строки. Credentials, хеши, cookie и этот ключ
не выводятся в журналы и не передаются через argv.

| Запрос | Ответ |
|---|---|
| `GET /health` | `200 {"status":"ok","scope":"game-identity-bridge"}`; без ключа |
| `POST /internal/native/login` | JSON строго с полями `email`, `password`; в 200 ровно `account_id`, `native_database_id`, `name`, `fixture_dir` |
| `GET /internal/accounts/{UUID}/overview` | Собственная read model либо `unlinked`; требуется служебный ключ |

`name` — сохранённый NFC ник с исходным регистром (`users.display_nickname`).
Почта в ответ, игровой снимок и native payloads не попадает. `display_name`
веб-профиля остаётся отдельным редактируемым личным именем.
`fixture_dir` — абсолютный путь внутри `local/`, содержащий `state.bin`,
`shop.bin`, `dossier.bin`, `manifest.json`, `compatibility.json` и проверяемую
JSON-модель. Rust проверяет привязку ответа и metadata к одному account ID.

Неверный или неизвестный пароль: `401 {"error":"invalid_credentials"}` без
account ID, ID игры или данных профиля. Недействительный ключ/Host/Origin —
403; неверная форма — 400; избыточное тело — 413; превышение попыток — 429;
занятость, ошибка генерации или недоступность — 503. Отказ не выдаёт фиктивный
успех. Отдельный GET отсутствующего UUID возвращает 404.

Ограничения: headers ≤4096 B, JSON login ≤2048 B, обязательно Content-Length,
нет chunked/compressed входа; пароль ≤512 UTF-8 B и соответствует политике
сайта. Одновременно максимум 16 TCP-соединений, 4 обрабатываемых запроса,
2 KDF и 2 генератора. На запрос отведено 4.5 s, socket/request timeout 5 s;
генератор — 2.5 s и ≤16 KiB вывода. Глобально 60 попыток/мин,
10 на каноническую почту/15 мин; таблица счётчиков ≤1024 строк. Счётчики
сохраняются при перезапуске. Каждый raw pickle ≤16 KiB/4096 nodes/depth16;
кодер разрешает только примитивы и не выполняет incoming pickle.

## Запуск и read adapter сайта

Bridge запускается через supervisor `tools/local_server.py`. Для отдельной
диагностики после создания веб-БД:

```powershell
node web/src/game-adapter.mjs --config local/evidence/20261004-p02-unified-account/service-test/bridge.json
```

Конфигурация — JSON версии 1 с ровно следующими ключами:

```json
{
  "version": 1,
  "port": 20020,
  "web_database": "<absolute local path to portal.sqlite>",
  "game_database": "<absolute local path to game.sqlite>",
  "fixture_root": "<absolute local directory>",
  "native_descriptors": "<absolute local verified native-descriptors.json>",
  "python_executable": "<absolute installed Python 3 executable>",
  "token_file": "<absolute local secret file>"
}
```

Все пути, кроме установленного Python, остаются внутри `local/`; уход через
symlink/junction проверяется. Самостоятельно копировать credentials в эту
конфигурацию не нужно. Стартовый JSON stdout:
`{"event":"game_bridge_ready","host":"127.0.0.1","port":20020,"pid":...}`.
Путь конфигурации и занятые порты выбирает supervisor; не запускайте второй
bridge поверх работающего процесса.

Для сайта интеграция включается серверными переменными окружения:

```powershell
$env:GAME_BRIDGE_ORIGIN = 'http://127.0.0.1:20020'
$env:GAME_BRIDGE_TOKEN_FILE = '<absolute local secret file>'
```

Сайт берёт UUID **только из проверенной собственной сессии**, затем запрашивает
overview через bridge; ID из query браузера игнорируется. Cookie и пароль
браузера этому GET не передаются. HTTP origin закреплён на numeric loopback,
redirect запрещён, ответ ограничен 32768 B и 2.5 s; ID, версия, test_lab
schema, ресурсы, техника и нулевая статистика валидируются.

| `state` | Что означает |
|---|---|
| `not_connected` | Для этого процесса сайта bridge не настроен |
| `unlinked` | Тот же аккаунт существует, но первого успешного игрового входа ещё нет; отдельная привязка не нужна |
| `ready` | Есть постоянный собственный снимок профиля; это не утверждение о текущем подключении EXE |
| `unavailable` | Ошибка/таймаут/невалидный ответ; вместо игровых данных возвращается null |

Кабинет честно показывает все четыре состояния. При `ready` видны собственный
ник, ресурсы, MS-1, нули нового игрока и revision/time снимка. Public-дизайн,
каталог и владелец процесса3091 сохраняются; координированный перезапуск
для миграции выполняет root/сессия сайта, а не data agent.

## Dossier и повторная проверка

`tools/hangar_state.py --profile` принимает только серверную snapshot schema,
не credentials. Он меняет в проверенном fresh account dossier исключительно
`total.creationTime`: UTC seconds из `users.created_at`. Для #717 descriptor
строго проверяется версия 80, header `<35H` (70 B), блок total index11 длиной
18 B и нулевой остаток после creationTime. Записанный формат total —
`creationTime:I,lastBattleTime:I,battleLifeTime:I,treesCut:H,mileage:I`.
Бои и остальные поля descriptor не изменяются. Другая версия, непустой dossier
или выдуманная ненулевая статистика отклоняется.

```powershell
node --test --test-concurrency=1 web/tests/game-adapter.test.mjs
npm.cmd --prefix web run check
npm.cmd --prefix web test
python tools/hangar_state.py --out local/evidence/<fresh-output> --native-descriptors local/evidence/20261004-p02-hangar/native-descriptors.json --profile <absolute local server-owned profile-input.json>
```

Без проверенных локальных descriptors интеграционный Node-тест отмечается
NOT_RUN/skip. Данные клиента не добавляются в Git. Evidence текущих HTTP-тестов:
`local/evidence/20261004-p02-unified-account/data-agent/email-tests-02.tap`;
статическое доказательство layout — соседние `dossier-format/`, `dossier-records/`
и прежний `20261004-p02-hangar/data-agent/dossier-zero/`. Старый диагностический
fixture без `--profile` сохранил все три исходных SHA-256; см. `default-regression/`.

Откат: supervisor останавливает только свои процессы; убрать две GAME_BRIDGE
переменные у управляемого сайта, вернуть изменённый source из baseline этой
карточки. Сохранённую game DB и fixtures следует оставить в `local/` для
исследования или отдельно архивировать. Миграцию `users` выполняет только
процесс сайта; bridge её не изменяет. Для schema2 обратный переход требует
сохранённой schema1 SQLite snapshot, подробности в EMAIL_IDENTITY.md.
Клиентские изменения имеют отдельный rollback root.

UNKNOWN/NOT_RUN в рамках этих HTTP-тестов: игровой бой, запись прогресса,
production экономика, интернет-развёртывание, смена версии существующего
профиля и настоящая native сессия. Единственный следующий шаг этого среза —
войти зарегистрированным аккаунтом через research EXE и сопоставить UUID,
native creation, серверные payloads и реальные данные ангара/профиля.
