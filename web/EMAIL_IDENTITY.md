# Почта для входа, ник для игры

Контракт владельца от 2026-10-04: «только ник, вход через почту только».
`users.id` остаётся единым доменным UUID сайта и игры. Имя пути fixture — UUID,
native database ID — прежнее стабильное отображение в слое совместимости.

## Поля и канонизация

| Поле | Значение |
|---|---|
| `users.email` | Единственный идентификатор входа; nullable только у прежних аккаунтов |
| `users.username` | UNIQUE канонический ключ ника, нижний регистр |
| `users.display_nickname` | NFC ник с сохранённым регистром, например `Танкист_Ёж` |
| `users.display_name` | Отдельное редактируемое личное имя веб-профиля |
| `game_profiles.profile_json.username` | Историческое имя поля schema1; значение — неизменяемый отображаемый ник |

Ник принимает ASCII латиницу, русские `А–Я/а–я/Ёё`, цифры `0–9` и `_`.
Это конечный алфавит, не обещание поддержки всех Unicode или всех кириллических
языков. После удаления обычных ASCII пробелов по краям принимаются 3–24
Unicode scalars, максимум48 UTF-8 B. Допускаются ровно четыре NFD пары:
`Е/е + U+0308`, `И/и + U+0306`; они приводятся к NFC. Другие combining marks,
whitespace, control, bidi, emoji и неподдержанные буквы отклоняются.
Введённый регистр отображается, уникальность проверяется по отдельному lowerkey.
`Ёжик`, `ёжик`, `Е◌̈жик` занимают один ключ; `Ежик` — другой.
Визуально похожие латинские и кириллические буквы не объединяются в один ключ
и не транслитерируются; сочетание разрешённых букв в одном нике допустимо.
SQLite `NOCASE` не используется для Unicode. Изменение игрового ника этой
карточкой не реализовано; редактирование display_name его не меняет.

Email должен быть ASCII **до** нормализации. По краям удаляются только
`U+0009..U+000D` и `U+0020`, затем ASCII lower. Длина результата≤254 B,
ровно один`@`, local part1..64. Допустимые dot-atom символы local part:
буквы`a-z`, цифры и `.!#$%&'*+/=?^_`, backtick, `{|}~-`.
Запрещены крайние точки и`..`. Domain содержит минимум два label длиной1..63,
только ASCII буквы/цифры/дефис с буквенно-цифровыми концами. Последний label
содержит хотя бы одну букву. DNS, SMTP, доставка/подтверждение почты, quoted
local parts, IP literals и SMTPUTF8 отсутствуют. Адрес нужен как идентификатор;
владение почтовым ящиком этой версией не подтверждается.

Пароль не нормализуется и не обрезается: точные15..128 Unicode scalars,
≤512 UTF-8 B, прежний scrypt verifier. Пробелы и кириллица пароля значимы.

## HTTP

Регистрация`POST /register`: `csrf,email,nickname,password,password_confirm`,
необязательный`display_name` (при отсутствии равен display nickname).
Вход`POST /login`: только`csrf,email,password`. Передача старого`username`
поля отвергается400; попытка использовать ник в email не авторизует.

`GET /api/profile` возвращает`web-profile.v2` для собственной сессии:
`id,username,nickname,email,displayName,bio,createdAt,updatedAt`.
`GET /api/game` продолжает`web-game-read.v1`; почты там нет.
Служебный bridge принимает строго`{email,password}` и возвращает ровно
`{account_id,native_database_id,name,fixture_dir}`. `name` — display nickname.
Успешный ответ доверенного loopback bridge связывает email с UUID; gateway
сверяет UUID/nativeID/ник с immutable fixture metadata, не сравнивает ник с email.

## Миграция прежних аккаунтов

При единственном владельце DB сайт применяет`002_email_nickname.sql` внутри
транзакции. До schema1→2 делает целостную SQLite snapshot через`VACUUM INTO`
рядом с БД: `portal.sqlite.pre-v2-<UUID>.sqlite`. Она учитывает WAL; копирование
одного работающего `.sqlite` файла для отката не равно этой операции.

Существующие UUID, username, password hashes, dates и sessions сохраняются;
новый display_nickname равен старому username, email остаётсяNULL.
Bridge открывает БД readonly и требует schema2; сам миграций не выполняет.
Повторный старт schema2 не делает новый backup и не повторяет преобразование.
Data-agent применял это только в`local/web/tests/`; основной runtime мигрирует
согласованным перезапуском владельца сайта, отдельно от тестовой приёмки.

Сохранившаяся web session может выполнить`POST /account/email` с полями
`csrf,email,current_password`. Проверяются CSRF/Origin и текущий password hash;
максимум5 попыток за15мин. ПривязкаNULL→email разрешена, повтор того же адреса
идемпотентен; чужой адрес или замена уже другого адреса отклоняется409.
Пароль, UUID, ник и game profile эта операция не меняет.

Когда действующей сессии нет, локальный владелец может явно привязать адрес
к существующему UUID. Подготовить внутри`local/` небольшой JSON с ровно полями
`account_id,email`; не записывать пароль. Уже мигрированная БД обязательна:

```powershell
node web/scripts/assign-email.mjs --database local/web/runtime/portal.sqlite --input local/explicit-email-binding.json
```

Инструмент не создаёт аккаунт, не угадывает адрес, не перезаписывает существующий
другой email и не печатает входные поля. Выбор UUID и адреса — явная операция
владельца, а не автоматическая часть миграции.

## Сохранённый игровой снимок и откат

Game profile schema1, UUID/r1, nativeID, ресурсы, statistics и creation date
не мигрируют и не пересоздаются. Старый измеренный генератор SHA-256
`bf026f98e6ccfb84bc2bde4720d9837863beae662a2f4600ad80e78356b040f4`
разрешён вместе с текущим source SHA. Bridge проверяет native descriptor hash,
profile source hash и JSON equality, все три payload hash/length и identity
metadata. Несовпадение даёт503 и требует явного исследования; регенерации или
сброса данных по ошибке нет. Новые никнеймы хранятся в profile-input и
compatibility metadata; email туда не попадает.

Откат schema2: остановить владельца сайта и bridge/gateway, сохранить текущую
schema2 БД и её WAL/SHM целиком отдельным архивом, вернуть согласованную schema1
snapshot **при остановленных процессах** и соответствующий старый код.
Свежие регистрации/email bindings после snapshot нужно предварительно сохранить:
обратной миграции этих новых данных нет. Старые r1/game DB не удалять.
Клиентский install/restore выполняется отдельным root-инструментом.

Ограничение rollback evidence: exact source snapshot непосредственно перед
email-stage для app/store/security/game-adapter не сохранён, stage-only source
rollback **NOT_AVAILABLE**. Root хранит exact исходный baseline всей карточки
P02 unified account; полный откат к нему доступен с schema1 DB snapshot и
сохранением game DB/r1 для исследования. Before-копии трёх EJS, старого
hangar_state.py и account_state_probe.py сохранены отдельно, но не заменяют
недостающий полный stage-only baseline.

## Проверка

```powershell
node --test --test-concurrency=1 --test-reporter=tap web/tests/email-nickname.test.mjs web/tests/game-adapter.test.mjs
npm.cmd --prefix web run check
npm.cmd --prefix web test
python -m py_compile tools/hangar_state.py tools/account_state_probe.py
```

58/58 изолированных HTTP/SQLite тестов PASS, включая новые реально отрендеренные
формы регистрации/входа/привязки, настоящий legacy encoder,
необычный сохранённый баланс43210/7/9, отсутствие изменения r1 и отказ при
нарушении profile-source hash. Evidence:
`local/evidence/20261004-p02-unified-account/data-agent/email-tests-02.tap`.
EJS формы применены после подтверждённой root остановки обоих прежних website
runtime. Data-agent не запускал сайты и не мигрировал primary DB.
Native email+кириллический вход данным HTTP-тестом **NOT_RUN**; отдельную
приёмку настоящим EXE и управляемые runtime запуски выполняет root.
