# P02 — единый аккаунт сайта и native-вход в «Стальной рубеж»

Дата: 2026-10-04. Проект GAYmDev Stutio. План:
`docs/plans/P02_unified_account_entry.md`.

**Узкая приёмка общей email-учётки и серверных данных ангара — PASS.**
Основной сайт и настоящий клиент используют одну запись пользователя; два
primary аккаунта, русский ник, restart/relogin и обычная форма без autologin
проверены. Владелец отдельно подтвердил собственный ручной ввод и вход.
Финальная research-установка оставлена, original не изменён; полный audit PASS.

**Полный GUI — FAIL; полный P02 PARTIAL, P03 NOT_STARTED.** В Normal20
сохранены семь ошибок original ToolTip и одна ошибка нашего observer.
Observer исправлен и покрыт тестами. В последнем Email22 wire/identity/ангар
PASS, но после начала fini снова возник original ToolTip `len(None)`, поэтому
общий Email22 **FAIL**. Он не переименован в успешную native-регрессию.
Предыдущие Email17/18/19 остаются PASS своих измеренных сценариев.
Исторический username-вход не подменяет нынешний email-only контракт.

В этом документе `E` означает
`local/evidence/20261004-p02-unified-account/`, `H` —
`local/evidence/20261004-p02-hangar/`. Все эти файлы, клиентские ресурсы,
credentials, базы, ключи и трассы находятся в исключённом из Git `local/`.
Пути evidence ниже относительны к корню проекта, если не начинаются с `E/` или
`H/`. Секретные значения не включены в отчёт.

## Цель, границы и категории доказательств

Владелец разрешил следующий срез после штатного ангара: регистрация на своём
сайте и вход тем же аккаунтом через исследовательский EXE на собственный
сервер. Позднее уточнил: **«только ник, вход через почту только»**. Учтено
отдельное явное решение **«Отключить старый диалог»** соглашения прежнего
сервиса; это не трактуется как согласие пользователя с какими-либо условиями.

Основной путь остаётся NATIVE_PRIMARY: original LoginView, native login,
Account, синхронизация и отображение родного ангара. Внутренний HTTP bridge
соединяет два собственных серверных компонента и не заменяет клиентский
протокол. Арена, бой, покупки, продажа, прогресс, восстановление пароля,
почтовая доставка, полноценный лаунчер и интернет-развёртывание вне карточки.
Внешние игровые серверы для экспериментов не используются.

- **VERIFIED** — конкретный source/hash, проверка или native evidence.
- **OBSERVED** — измерение одного указанного запуска, без обобщения на другие.
- **INFERRED** — явно ограниченный вывод из измерений.
- **UNKNOWN / NOT_RUN** — соответствующего доказательства нет.

HTTP/SQLite тест не доказывает native совместимость. Контролируемое заполнение
оригинальной Flash-формы не является доказательством физического ввода всей
строки пользователем с клавиатуры. Передача полного ника в Account/header
не доказывает, что вся строка одновременно помещается в узком заголовке.

## Исходное состояние и владение файлами

Закреплён клиент `v.0.9.1 #717`, RU, compatibility `ru_0.9.1_2`, Python 2.7.3
x86. EXE SHA-256:
`86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed`.
Источник проверки билда — предыдущие CLIENT_AUDIT/P02_HANGAR и manifests;
издательская аутентичность остаётся UNKNOWN. EXE этой карточкой не патчится.

До реализации root сохранила 206 исходных файлов и локальный конфиг:

| Артефакт | SHA-256 / назначение |
|---|---|
| `E/project-before.json` | `78ff3f12a818aea395317bf6a286ba8daca0cb026b13cbe101fbafc2922bbeaa` — список 206 файлов |
| `E/project-before.zip` | `9a80fc04d4d28775d6f227867274046f707ae83c9e6bf573232f4e252e0309ae` — исходный полный snapshot карточки |
| `E/project.local.before.json` | Локальный конфиг до карточки; остаётся в `local/` |
| Original content manifest | `74c37c18e9ac7e30196c134076dacf6f2a8bf3897f7def73905d09feb3647797` |
| Research content manifest | `37bb7f1a79be0ef893c033bb4cc9bfae6470d1b64024e32639c05eb012fe0fe5` |

`E/baseline/copy-comparison.json` уже до работы содержит три исторических
различия research: `Influx_PS.bak`, `Influx_PS.log`, `python.log`. Они
сохранены; утверждение «research изначально равен original» было бы неверным.
`E/checkpoint-before-email-comparison.json` — PASS полного совпадения обеих
копий со **своим** baseline после восстановления username-этапа. Это checkpoint,
а не финальная проверка после email-этапа/обычной установки.

Работа разделена по файлам; реальные запуски клиента и управление серверными
процессами выполняет root. Процесс основного сайта имеет отдельного владельца.

| Владелец / область | Изменённые или добавленные файлы |
|---|---|
| Data: единая identity и read adapter | `web/src/security.mjs`, `store.mjs`, `app.mjs`, `game-adapter.mjs` |
| Data: миграция и явная привязка | `web/migrations/002_email_nickname.sql`, `web/scripts/assign-email.mjs` |
| Data: формы без переработки дизайна | `web/views/auth.ejs`, `home.ejs`, `account.ejs` |
| Data: проверки | `web/tests/email-nickname.test.mjs`, `game-adapter.test.mjs`, `portal.test.mjs`, `restart.test.mjs`, `network.test.mjs`, `web/package.json` |
| Data: модель и HTTP/SQLite сверка | `tools/hangar_state.py`, `tools/account_state_probe.py` |
| Data: контракт | `web/GAME_ADAPTER.md`, `web/EMAIL_IDENTITY.md`; этот отчёт |
| Wire: native gateway | `tools/wg_probe/src/identity091.rs`, `login091.rs`, `gateway091.rs`, `hangar091.rs`, `transport091.rs`, `capture091.rs`, `redirect091.rs`, `main.rs`; соответствующая конфигурация crate |
| Wire: независимые проверки | `tools/verify_unified_entry.py`, `tools/check_unified_verifier.py` |
| GUI: original login/lifecycle | `client_patch/sr_interactive.py`, `project_auth.py`, `project_preferences.py`, `client_patch/INTERACTIVE.md`; прежний `hangar_bootstrap.py` используется без изменения |
| GUI: установка и собственные ресурсы | `tools/interactive_client.py`, `compile_interactive27.py`, `project_login_resources.py` |
| GUI: проверки границ | `tests/test_project_auth.py`, `test_project_preferences.py`, `test_interactive_license_policy.py`, `test_interactive_primitive.py` |
| Root: процессы и сквозная приёмка | `tools/local_server.py`, `tools/account_site_probe.py`, plan/STATUS, локальные конфиги, actual-run evidence |

Точный список 19 файлов data/email-этапа и hashes:
`E/data-agent/email-results.json`; read-only audit подтвердил 19/19 совпадений
после финальных тестов. Для GUI — `E/gui-agent/email-final-source-audit.json`,
для wire — `E/wire-agent/server-code-05.json`, `WIRE_FINAL.json` и последующие verification reports.
Эти manifests являются снимками своих этапов; более поздний root-edit требует
нового hash, а не переписывания исторического manifest. Итоговый список
исходников и фактических изменений: `E/project-after.json`,
`E/project-changes.json`; проверка передаваемых файлов: `E/source-handoff-audit.json`.
Этот список включает параллельные изменения сайта, их авторство не присваивается
целиком данной карточке. Собственные исследовательские helpers перечислены
отдельно в `E/local-tools-manifest.json`, остаются в ignored local/.

EJS изменены только после согласованной остановки обоих старых website runtime:
старый primary остановлен владельцем в 12:19:01.270 UTC, изолированный сайт
остановлен root раньше. `E/data-agent/email-views/` содержит точные before/after,
hash manifest и шесть реальных render-проверок. Каталог/оформление соседней
сессии не использовались как область разработки этой карточки.

## Один аккаунт и постоянный игровой профиль

**VERIFIED, source + HTTP/SQLite + отдельные native cases:**

1. Регистрация и единственный password registry — существующая таблица
   `users` сайта. `users.id` является доменным `account_id` игры.
2. Сайт владеет записью identity DB. Bridge открывает ту же БД readonly,
   `query_only=ON`, требует schema2, использует тот же scrypt verifier и не
   мигрирует users, не создаёт web session, не меняет password/last_login_at.
3. Отдельная `game.sqlite` хранит профиль, stable native ID и ограниченные
   rate counters; копии паролей или второго реестра пользователей там нет.
4. Успешная проверка email/password разрешает создать первый test_lab профиль.
   Неверные credentials не получают UUID/native ID/данные профиля и не создают
   профиль. Существующий снимок при ошибке не сбрасывается.
5. Gateway получает UUID/native ID/display nickname и проверяемый путь fixture.
   Перед Session он сверяет ответ с `manifest.json` и `compatibility.json`.
   Native IDs принадлежат слою совместимости, не заменяют доменный UUID.
6. `/api/game` берёт account_id только из собственной web session. Параметр
   чужого UUID в query не меняет subject. Browser session и native session
   разные по протоколу, но обе относятся к одному аккаунту.

Bridge: `127.0.0.1:20020`, строго локальный bearer из файла — 43 base64url
символа без newline. `GET /health` отдаёт только
`{"status":"ok","scope":"game-identity-bridge"}`. Основной запрос:

```text
POST /internal/native/login
request  = {email, password}
200 body = {account_id, native_database_id, name, fixture_dir}
```

`name` — ник. Email в успешный ответ, игровой снимок и native display payload
не попадает. `fixture_dir` — canonical путь внутри `local/`; UUID/r1 используется
как имя каталога, ник/почта не используются для путей. Gateway не сравнивает
ник с почтой: доверенный ответ bridge связывает principal с UUID, затем
проверяются UUID/native ID/ник и metadata снимка.

В read adapter различаются `not_connected`, `unlinked`, `ready`, `unavailable`.
`unlinked` означает отсутствие первого игрового профиля у того же аккаунта,
а не необходимость создать или вручную связать вторую учётку. `ready` означает
наличие сохранённого снимка и не обещает, что EXE сейчас подключён.

Игровой profile schema1 хранит UUID, immutable display nickname в исторически
названном поле `username`, native ID, creation date, revision и ресурсы.
Стартовые значения **test_lab**: 100000 credits, 0 gold, 0 freeXP; одна выданная
MS-1 с проверенным native descriptor, 90 HP, без назначенного экипажа и
боекомплекта. Нулевые бои/победы/поражения/ничьи — данные нового аккаунта,
а не придуманная история. Цены/каталожные поля являются минимальными
справочными данными недоступных действий; работающей экономики нет.

Публикация UUID/r1 атомарна. Повторный вход проверяет descriptor source hash,
profile-input hash и equality, UUID/native ID/ник, длины и hashes трёх wire
payloads. Нарушение даёт 503, не регенерацию с новым балансом или датой.
Прежний измеренный generator SHA разрешён явно:
`bf026f98e6ccfb84bc2bde4720d9837863beae662a2f4600ad80e78356b040f4`.
Новый SHA:
`541441a0f38f8ce7600b133b77acad88ee40e01e28093d18e60bbb74261f269a`.
Регрессионный тест запускает сохранённый реальный predecessor и подтверждает
неизменность старого r1 с 43210/7/9 ресурсов, native ID 77 и прежними UUID/date.
Это проверка сохранности, не доказательство native-входа этим unit fixture.

У native fresh account dossier версии 80 проверены 88 B, header `<35H`,
блок total index11 длиной 18 B. Генератор меняет только creationTime,
байты 70..73 uint32 LE, на `floor(users.created_at/1000)`; остальные bytes
fresh descriptor неизменны. Этот descriptor находится в `state.stats.dossier`.
Отдельный `dossier.bin` остаётся stream-ответом для пустого набора vehicle
dossiers. Layout/zero evidence: `E/data-agent/dossier-format/`,
`dossier-records/`, `dossier-header/`, `dossier-source-integrity.json`.
Реальный source `H/native-descriptors.json` SHA:
`18e6c2babfc205ce80fa24c2c9f23385a1731233c4d504be369638485652d6f2`.

## Email, ник, пароль и миграция

Полный проверяемый контракт записан в `web/EMAIL_IDENTITY.md`.

| Поле | Правило |
|---|---|
| Email для входа | ASCII до нормализации; edge trim только U+0009..U+000D/U+0020, lowercase; всего ≤254 B, local part 1..64 B, ровно один `@` |
| Local part | Dot-atom: ASCII буквы/цифры, `.!#$%&'*+/=?^_`, backtick, `{\|}~-`; без крайних точек и `..` |
| Domain | Минимум два label по 1..63; ASCII alnum/hyphen, alnum на концах; последний label содержит букву |
| Игровой ник | ASCII Latin, русские А–Я/а–я/Ёё, цифры и `_`; 3..24 scalars, ≤48 UTF-8 B; обычные ASCII пробелы по краям удаляются |
| Нормализация ника | Только NFD пары Е/е+U+0308 и И/и+U+0306 приводятся к NFC; display case сохраняется; unique key — lowercase |
| Пароль | Точные 15..128 Unicode scalars, ≤512 UTF-8 B; без trim/normalization; Unicode и краевые пробелы значимы |

`users.username` — canonical unique nickname key, `display_nickname` —
отображаемый ник, `display_name` — отдельное личное имя веб-профиля.
SQLite Unicode `NOCASE` не используется. `Ёжик` и `Е◌̈жик` занимают один ключ;
`Ежик` — другой. Визуально похожие Latin/Cyrillic не транслитерируются.
Другие Unicode-буквы, emoji, bidi/control и неподдержанные combining marks
отклоняются. Это поддержка явно перечисленного русского/латинского алфавита.

`POST /register`: `csrf,email,nickname,password,password_confirm`, optional
`display_name` с default nickname. HTML сейчас отдельно спрашивает личное имя.
`POST /login`: только `csrf,email,password`; старое поле `username` отвергается
400, ник в поле почты не авторизует. `/api/profile` — `web-profile.v2`, включает
собственные id/username/nickname/email/displayName/bio/dates.

Миграция `002_email_nickname.sql` создаёт перед schema1→2 целостную SQLite
snapshot через `VACUUM INTO`, затем выполняет транзакцию. UUID, password
records, registration dates и sessions сохраняются; display_nickname получает
прежний username, email остаётся NULL. Повторный старт schema2 миграцию не
повторяет. Старым аккаунтам почта автоматически не придумывается.

Существующая web session связывает email через `POST /account/email`:
`csrf,email,current_password`, проверка Origin/CSRF/пароля, до 5 попыток/15 мин.
NULL→email разрешено, повтор того же адреса идемпотентен; занятый адрес или
замена другого уже привязанного адреса — 409. Без действующей сессии есть
явная локальная операция владельца `web/scripts/assign-email.mjs` с JSON
`{account_id,email}`; она не создаёт аккаунт и не перезаписывает чужую привязку.

**UNKNOWN / не реализовано:** подтверждение владения ящиком, DNS/SMTP,
доставка, recovery, смена уже привязанной почты, смена игрового ника.
Email этой версии — непроверенный идентификатор, не подтверждённый контакт.

## Ограничения серверной и клиентской границ

**VERIFIED_STATIC и конкретные negative controls:** bridge требует точный
numeric loopback Host, отвергает Origin, ограничивает headers 4096 B,
login body 2048 B, Content-Length, без chunked/compression. Максимум
16 TCP connections, 4 active requests, 2 KDF, 2 generator processes;
deadline 4.5 s, socket/request 5 s, generator 2.5 s/16 KiB stdout.
Счётчики ограничены 1024 rows, 60 attempts/min global и 10/email/15 min.
Password verifier сайта — scrypt N=131072,r=8,p=1. Секреты не передаются
через argv и не печатаются в прикладной trace.

Rust получает bounded HTTP ответ, проверяет строгую форму JSON, UUID,
positive signed32 native ID, finite nickname repertoire и metadata.
401 переводится в native INVALID_PASSWORD=67; unavailable — SERVER_NOT_READY=73;
без успешной identity/fixture проверки Session не выделяется. Медленный KDF
работает через ограниченный worker и не блокирует обработку активного канала.
Допускается одна активная native session; другая учётка не подменяет её.

В отдельном interactive transport сохранены bounded window/queue: body512,
window8, outbox128, recent incoming64. Допускаются pre-wrap sequence до
1000000; общий wraparound не реализован. Session duration конфигурируется
600..7200 s, default1800. Native evidence доказывает выход server sequence
за прежний lab limit32; многочасовая сессия и весь возможный канал NOT_RUN.

Реальный максимальный login измерен как два UDP datagram 1437+142 B,
logical1553 B, 12 RSA-1024 OAEP/SHA1 blocks → 949 B plaintext. Внутри native
username JSON 391 B и password512 B используют canonical extended24-bit
length. Поддерживается только измеренная форма из двух fragments: один peer,
диапазон из двух sequence, max4 pending sets, lifetime5 s, exact duplicate
и reverse order. Противоречивый duplicate удаляет частичную запись; одна часть
не авторизует. General fragmentation остаётся UNKNOWN/unsupported.

Wire остаётся native. Служебные `auth_method=basic`, `auth_realm=RU`,
`game=wot`, аппаратный digest и прочие подтверждённые protocol identifiers
не переименованы ради публичного бренда. Правила `docs/NAMING.md` сохранены.

Собственный data-only protocol2 encoder пишет только разрешённые примитивы.
Rust structural validator ограничивает каждый payload 16 KiB, 4096 nodes,
depth16; не выполняет pickle. На входящих данных нет `pickle.loads`, eval/exec
или загрузки произвольных классов. Source и hashes payloads проверяются до
передачи original Account handlers.

## Original LoginView и воспроизводимая установка

Пакет устанавливается только в research-копию. `prepare` создаёт reviewable
plan; `install` проверяет instance mutex и hashes, сохраняет backup и durable
ledger **до записи**. Original-копия только читается. Собственные Python2.7
модули скомпилированы локальным 2.7.3, EXE и native transport не изменяются.

Измеренные изменения ограничены endpoint/own public key, GUI bootstrap,
изолированными preferences, проектной авторизацией и несколькими существующими
строками меню. Original dispatcher получает точный password через узкую
совместимость с его `.strip`; не заменяются сетевой login или Account success.
Из original ConnectionManager убрана только передача credentials в debug tuple.
Пароль не сохраняется в settings/preferences; writer отвергает непустые
password/pwd/token2. Неактивный `rememberPassVisible` не выдаётся за аудит
всех возможных native компонентов.

Normal plan не содержит control-файла: `test_control=null`,
`normal_auto_login=false`, `normal_auto_quit=false`. Отсутствие control
проверяется до submit/таймера quit. Пассивный trace ограничен 16 MiB;
достижение лимита прекращает observer, а не игру. Явный fatal bootstrap exit
остаётся отдельным записываемым сбоем. Доказательство этого source-пути не
подменяет final normal EXE gate.

По решению владельца `--disable-legacy-license-dialog` меняет только
`version.xml/showLicense` 3→0 с backup/hash/ledger. Записывается
`owner_requested=true`, `user_agreement_recorded=false`; license files и
account settings не меняются. `intUserSettings[54]=3` не присваивается.
CMD1600 пока имеет статическое evidence; реализация принятия/хранения условий
не заявлена. Для измеренного native CMD108 SET_AND_FILL_LAYOUTS реализован
RES_NOT_AVAILABLE=-10 с тем же request ID, без покупки или изменения fixture.
Source/codec checks PASS; реальное отображение этого отказа в клиентском UI
отдельно NOT_RUN.

Основные static sources: `E/gui-agent/implementation-findings-01.json`,
`email-final-source-audit.json`, `login-swf-contract-05.json`,
`layouts-command-108.json`, `eula-contract-01/eula-contract.json`.
Original LoginDispatcher pyc SHA:
`dac04754cddb813e390657e17634dbd769d5ecb5554951a29db40fbf7c89f4de`
(`password.strip`, bytecode offsets234..243); ConnectionManager SHA:
`84deb9fbacb295991ae332df520c54a48fad62dcfee5d854eb7637bf402c0d20`.

## Сохранённые неудачи и что они доказали

Старые FAIL не удалены и не переименованы. Промежуточный успешный callback
не превращает запуск с более поздней ошибкой в общий PASS.

| Запуск / результат | Факт, исправление и evidence |
|---|---|
| UI02 FAIL → UI03 PASS | ResMgr не открыл absolute local preference path. Добавлен собственный prefix в backed-up paths.xml и относительный `sr_preferences.xml`; UI03 original LoginView, native read/save7158 B, 0wire, exit0. `E/gui-agent/ui-runtime-02/`, `ui-prepare-02/postrun/`, `ui-runtime-03/visual-review.json` |
| Auth04 FAIL | PUBLIC_KEY_LOOKUP_FAILED, 0UDP: ключ должен быть в `res_mods/0.9.1/sr_local.pubkey`. `E/gui-agent/auth-runtime-04/`, `auth-prepare-04/` |
| Auth05 FAIL | Частичный res_mods/text скрывал остальные gettext domains: NoTranslation/as_show. Исправление — targeted `research/res/text/LC_MESSAGES/menu.mo` с backup и сохранённым каталогом ключей. `E/gui-agent/localization-directory-fix.json`, `i18n-static/`, `auth-prepare-05/postrun/` |
| Auth06 функциональное наблюдение, overall FAIL | Original Flash с Unicode/краевыми пробелами дошёл до LOGGED_ON/ангара, но свежий duplicate alternative URL оставил общий FAIL. `url_token=''` убрал дубликат. Старый URLError был exact before prefix, не свежим внешним запросом. `E/gui-agent/token-url-fix.json`, `E/wire-agent/verify-auth06-02/` |
| Auth07/Auth08 FAIL | Настоящие 128 ASCII и 512 UTF8 B пароли превысили прежние login bounds; измерены extended lengths и RSA envelope. `E/wire-agent/native-login-boundaries-01/boundaries.json` |
| Auth09 | Фактический CMD108 дополнительно исследован. Сохранённый `E/verify-auth09-02/` имеет FAIL; этот документ не объявляет его успешной приёмкой |
| Auth10 PASS промежуточного username-контракта | Native ready96.469 s, server sequence78; `E/wire-agent/verify-auth10-final/`. Не доказывает поздний email-only контракт |
| Email11 framing control | Незарегистрированные boundary credentials: не auth PASS. Реальные 2-fragment packets/extended391B username установили точную форму. `E/wire-agent/native-login-fragments-01/analysis.json` |
| Email12 overall FAIL | Functional gates и screenshot PASS, но ready48.2390613 s < требуемых60. Порог не снижался. `E/wire-agent/verify-email12-01/`, `E/verify-email12-01/` |
| Email15 initial visual FAIL → final PASS | Первому review не хватало нового поля `entered_nickname`; старый review сохранён, значение добавлено после просмотра actual PNG. Это не изменение native evidence. `E/wire-agent/verify-email15-nickname-01/`, `verify-email15-nickname-final/` |
| Port-conflict control | Windows позволил wildcard/specific listener coexistence; root добавила явный listener preflight. Повторный ожидаемый отказ: `E/service-port-conflict/state.json`, status FAILED, пустые owned processes, причина refusing-to-shadow. Основной сайт не принадлежит этому supervisor |

Сохранены также неудачные локальные checks: Rust tests05 со старым expectation,
tests07 с borrow error в test helper; verifier controls05 искал
intUserSettings не в том корне. Исправлены test/helper assumptions; actual
native evidence не переписан. Последние успешные checks указаны отдельно.

## Реально выполненные проверки

| Проверка | Результат | Evidence |
|---|---|---|
| Финальный Node HTTP/SQLite/forms suite | **PASS 58/58**, 0skip, exit0 | `E/data-agent/email-tests-02.tap` |
| Node syntax и Python compile | **PASS** | `email-results.json`, audit `E/data-agent/EMAIL_FINAL.md` |
| Default fixture regression | **PASS 21/21**, все три wire SHA неизменны | `E/data-agent/email-default-regression/{manifest.json,encoder-tests.json}` |
| Email client boundary/exact password | **PASS 6 tests × Python3/Python2.7.3**, compilation PASS | `E/gui-agent/email-boundary-01/checks.json` |
| Preferences boundary | **PASS**, 5 tests на каждом Python3/2 | `E/gui-agent/unit-01/results.json` |
| Owner/diagnostic dialog policy | **PASS 5 tests** | `E/gui-agent/license-policy-01/checks.json` |
| Rust | **PASS 55 tests**, build PASS | `E/wire-agent/rust-tests-08.log`, `rust-build-05.log` |
| Legacy own-UDP regression | **PASS 33 controls** | `E/wire-agent/oldlab-controls-04/results.json` |
| Независимый verifier/negative controls | **PASS 97 checks**; offline mutations не равны native run | `E/wire-agent/verifier-email-controls-08/checks.json` |
| Изолированный зарегистрированный maximum email/password/русский ник | **PASS Email13**: ready106.479178 s/107samples, 338packet hashes, server85/client26 | `E/wire-agent/verify-email13-final/unified-entry-verification.json` |
| Native неверный пароль | **PASS Email14**: code67, 2UDP, 0allocation/BaseApp/Account | `E/wire-agent/verify-email14-wrong-01/unified-entry-verification.json` |
| Ник вместо почты в original Flash | **PASS Email15**: LoginView/validation, 0native account/callback/UDP, пустой frozen gateway span | `E/wire-agent/verify-email15-nickname-final/unified-entry-verification.json` |
| Legacy аккаунт после email binding и backend restart на изолированном сайте | **PASS Email16**: тот же UUID/nativeID1/r1, ready91.4936 s, 296packet hashes | `E/wire-agent/verify-email16-legacy-01/unified-entry-verification.json` |
| Два существующих аккаунта, собственный `/api/game`, ignored foreign query и сохранность DB/fixture после restart/native | **PASS**, HTTP+readonly SQLite; сами эти tools native не запускают | `E/email-state-before-restart-01/account-state.json`, `email-state-after-restart-01/account-state.json`, `email-state-after-native-01/account-state.json` |
| Primary website schema2/retained users/start/content | **PASS в записи владельца сайта**: 21HTTP checks; не native gate | `local/web/email-cutover/run-01/completion.json` |
| Primary email / русский ник / relogin | **PASS Email17/18/19**, одинаковые website UUID/native ID/fixture; ready91.360/176.846/76.359 s | `E/wire-agent/verify-email17-primary-01/`, `verify-email18-primary-cyrillic-01/`, `verify-email19-primary-relogin-01/` |
| Обычный idle без control | **PASS Normal21**:95.003 s process/76.435 s LoginView/0own-UDP; clean exit NOT_RUN, остановлен harness | `E/gui-agent/normal21-prepare/normal-idle/normal-idle-report.json` |
| Ручной ввод владельца | **PASS только AUTH_AND_SERVER_ACCOUNT_DATA_ONLY**; HUMAN_ATTESTED; full GUI FAIL | `E/wire-agent/manual-auth20/manual-auth-analysis-02.json` |
| Исправление primitive observer | **PASS9/9 Python3;5/5 CPython2.7.3 before/after; compile PASS** | `E/gui-agent/primitive-fix-01/{unit-checks.json,runtime27-checks-02.json,compiled.json}` |
| Email22 после исправления observer | **Overall FAIL**: wire/backend/ангар/PNG/cleanup PASS, но1originalToolTip exception после fini_enter; ready76.452 s,253packets | `E/wire-agent/verify-email22-final-observer-01/unified-entry-verification.json` |
| Итоговая установка и полная целостность | **PASS**, финальный пакет без control оставлен установленным | `local/client-install-001/patch-ledger.json`, `E/final-state-audit-02.json` |

Финальный verifier проверяет цепочку: registration/binding UUID → native ID/ник →
Session/creation/showGUI → exact state/shop/dossier wire bytes и CRC → original
callbacks/header/resources/statistics → continuous ready ≥60s → только свежий
хвост ошибок → cleanup/rollback → hash actual PNG и его просмотр root.
Неверный пароль требует собственного frozen gateway span; отказ другой ранней
попытки из общего лога не засчитывается. Email15 доказывает frontend refusal,
но не проверку присланного пароля сервером.

**OBSERVED:** actual Email12/13 поле LoginView имеет maxChars0; Account.name
и original header callback получили полные 26/48 UTF8 B ника. PNG показывает
русскую кириллицу и Ё, длинный ник original header визуально обрезает.
Физический ввод 254 символов клавиатурой NOT_RUN. Screenshot reviews:
`E/gui-agent/email-prepare-12/visual-review.json`,
`E/gui-agent/email-prepare-13/visual-review.json`.

Ключевые hashes, позволяющие закрепить этот срез:

| Артефакт | SHA-256 |
|---|---|
| Node 58/58 TAP | `4b496d44bb3e516d57a6817d7ce358ef0269335369de0cbc85019d2b601373e7` |
| Email13 final verifier | `f7087cd3deeb98f2c9e96257af37069adab45338c12a9dccd62a767791cd70ca` |
| Email14 wrong-password verifier | `8fe4bb909c534adc587b26825503c49592ac47aaa52f6d35200f06c89bba73de` |
| Email13 actual visual review | `4ee2469ce22e45e5dde9b68fe1472e4258b550b6efad2548d4717e475954b77d` |
| Gateway binary | `86cac81b396ff5b2e301de85b56dfdba333e3fad9a707d02c4f46a2e2125daf9` |
| Primary website owner completion | `ec5118a6797766cd0082ef48b1a8ebd685b3e3aaaac1a70b36539bf8b77edced` |

Default lab payload regression hashes (это не hashes каждого per-account state):
state1106 B `bc69a8c943fef796ea159068ccf897a9be93f4158ab8d0746c38326cac2c4fee`;
shop361 B `210617723b8094186b7e8f5991e505941052c25c5d04dcc10c556d17d5d880b1`;
dossier8 B `70b70fe0dd6f28761228250a57e0a0a71e9d16ee0db54ff6e9252f06267034f1`.
Per-account hashes берутся из соответствующего UUID/r1 manifest.

## Запуск, повторная проверка и обычный клиент

Все команды выполняются из `D:\WoT_9.1_Server`. Новый output-каталог выбирается
свободным; существующие evidence/fixture не перезаписываются. Credentials и
приватные ключи инструмент читает из ignored файлов, не из командной строки.

Основной service config — `local/server/service.json`, schema2,
`web_mode=external`, сайт3091 и `local/web/runtime/portal.sqlite`.
Сайт остаётся единственным identity writer и имеет своего владельца запуска.
Supervisor проверяет loopback health существующего сайта и запускает только
bridge/gateway; stop не останавливает сайт. Исторический schema1 service config
поддерживается как managed для изолированного3092. Взаимное соответствие
portal/bridge paths, ключей, endpoint и gateway config проверяется до запуска.

```powershell
python tools/local_server.py status --config local/server/service.json
python tools/local_server.py start --config local/server/service.json --capture
python tools/local_server.py stop --config local/server/service.json
```

Не нужно повторно выполнять init существующего `local/server` или запускать
второй bridge поверх supervisor. Для конкретной native-приёмки gateway capture
включается до запуска; runtime outputs и собственные PID записывает supervisor.

Финальный пакет **уже установлен**, клиент оставлен закрытым, основной сервер
запущен. Не выполнять повторно `prepare/install` в существующий каталог:
ledger намеренно откажет. Команды ниже воспроизводят подготовку в новом пустом
каталоге после отката предыдущей установки. В пакете нет `--test-control`:

```powershell
python tools/interactive_client.py prepare --out local/client-install-001 --public-key local/server/native-public.pem --profile-dir local/client-profile --trace-dir local/client-runtime-001 --endpoint 127.0.0.1:20014 --registration-url http://127.0.0.1:3091/register --disable-legacy-license-dialog
python tools/interactive_client.py install --out local/client-install-001
```

Обе копии клиента должны быть закрыты для install/rollback, иначе preflight
останавливается до изменений. Запуск исследовательского
`WoT_0.9.1_RU_0717_research/WorldOfTanks.exe` выполняется обычным способом;
почта и пароль вводятся в original форме, не передаются через argv.
Имя EXE — исходный путь ресурса совместимости, а не новое публичное имя проекта.
Для обычного запуска из PowerShell:

```powershell
Start-Process -FilePath 'D:\WoT_9.1_Server\WoT_0.9.1_RU_0717_research\WorldOfTanks.exe' -WorkingDirectory 'D:\WoT_9.1_Server\WoT_0.9.1_RU_0717_research'
```

Сайт: `http://127.0.0.1:3091/register`, вход — по почте и тому же паролю.
Учётка владельца лежит в `E/operator-email-binding-01/test-credentials.json`.
Клиент сохраняет свои preferences/ограниченный trace в `local/client-profile`
и `local/client-runtime-001`; пароль туда не записывает.

Если основной сайт когда-либо остановлен, сначала запустить **один** website
runtime в отдельном терминале с сохранённой конфигурацией его владельца:

```powershell
$srWebEnvironment = Get-Content -LiteralPath local/web/email-cutover/run-01/launch-environment.json -Raw | ConvertFrom-Json
foreach ($srName in @('WEB_HOST','WEB_PORT','WEB_ORIGINS','WEB_DATA_DIR','GAME_BRIDGE_ORIGIN','GAME_BRIDGE_TOKEN_FILE')) {
    [Environment]::SetEnvironmentVariable($srName, [string]$srWebEnvironment.$srName, 'Process')
}
npm.cmd --prefix web start
```

Затем `tools/local_server.py start --config local/server/service.json --capture`
в другом терминале. Не запускать второй сайт поверх текущего и не повторять
one-time `local/web/email-cutover/run-01/start.ps1`: его завершённая миграция
уже записана. Существующий supervisor также отказывает при занятом own lock.

Повтор source/unit checks (Rust build при остановленном own gateway, чтобы
Windows не держала бинарник):

```powershell
. ./tools/rust_env.ps1
cargo test --locked --offline --manifest-path tools/wg_probe/Cargo.toml
cargo build --locked --offline --manifest-path tools/wg_probe/Cargo.toml
node --test --test-concurrency=1 --test-reporter=tap web/tests/*.test.mjs
npm.cmd --prefix web run check
python -m py_compile tools/hangar_state.py tools/account_state_probe.py
python tests/test_project_auth.py
python tests/test_interactive_license_policy.py
python -m unittest tests.test_interactive_primitive -v
$env:SR_TEST_TEMP = (Resolve-Path local).Path
python tests/test_project_preferences.py
& local/toolchains/cpython-2.7.3-x86/python.exe tests/test_project_auth.py
& local/toolchains/cpython-2.7.3-x86/python.exe tests/test_project_preferences.py
```

Реальные descriptors обязательны для полного integration suite; skip при их
отсутствии нужно обозначать NOT_RUN. Данные клиента не добавляются в репозиторий.
Повтор default fixture в новом каталоге:

```powershell
python -X utf8 tools/hangar_state.py --out local/evidence/20261004-p02-unified-account/fixture-repeat-next --native-descriptors local/evidence/20261004-p02-hangar/native-descriptors.json
```

Для per-account генерации добавляется `--profile` с существующим серверным
`profile-input.json`; отдельный пользователь и новая история не выдумываются.
Для offline/own-UDP controls:

```powershell
python tools/check_unified_verifier.py --evidence local/evidence/20261004-p02-unified-account --out local/evidence/20261004-p02-unified-account/wire-agent/verifier-repeat-next
python tools/check_gateway_probe.py --source local/evidence/20261004-p02-hangar/native-final-03/01-normal --out local/evidence/20261004-p02-unified-account/wire-agent/oldlab-repeat-next
```

Повтор независимого анализа сохранённого Email13 не запускает клиент и не
регистрирует аккаунт. Получение UUID из несекретного registration.json не
печатает содержимое credentials:

```powershell
$taskEvidence = 'local/evidence/20261004-p02-unified-account'
$taskRegistration = Get-Content -LiteralPath "$taskEvidence/email-boundary-registration-01/registration.json" -Raw | ConvertFrom-Json
$taskAccount = $taskRegistration.users | Where-Object case -eq 'email254_unicode512'
python tools/verify_unified_entry.py --install "$taskEvidence/gui-agent/email-prepare-13" --registration "$taskEvidence/email-boundary-registration-01/registration.json" --credentials "$taskEvidence/email-boundary-registration-01/test-credentials.json" --case email254_unicode512 --private-key "$taskEvidence/service-test/native-private.pem" --fixture "$taskEvidence/service-test/fixtures/$($taskAccount.account_id)/r1" --min-ready-seconds 60 --out "$taskEvidence/verify-email13-repeat-next"
```

`tools/account_site_probe.py` создаёт новые тестовые регистрации на явно
выбранном собственном сайте. В этой карточке отдельно проверены isolated3092
и основной3091 с разными credentials/evidence. Для уже существующих аккаунтов
`tools/account_state_probe.py` делает настоящий web login, читает собственный
`/api/game`, проверяет чужой query и readonly snapshots DB/fixtures. Он не
вызывает bridge login и не создаёт игровой профиль. Пример повторной сверки
изолированной пары после старта соответствующего service-test:

```powershell
python tools/account_state_probe.py --service-config local/evidence/20261004-p02-unified-account/service-test/service.json --credentials local/evidence/20261004-p02-unified-account/email-persistence-credentials.json --expect ascii=ready --expect unicode_spaces=ready --compare local/evidence/20261004-p02-unified-account/email-state-before-restart-01/account-state.json --out local/evidence/20261004-p02-unified-account/email-state-repeat-next
```

Этот HTTP probe меняет только обычные login session/rate/last_login_at данные;
он не является полностью read-only запросом к приложению. Primary запуск
использует свои credentials/binding evidence и свой service config; подстановка
изолированной пары не закрывает primary gate.

## Сохранность и откат

Клиентский откат после закрытия клиента:

```powershell
python tools/interactive_client.py rollback --out local/client-install-001
python tools/local_server.py stop --config local/server/service.json
```

Rollback сохраняет postrun-копии, восстанавливает точные before файлы/логи,
удаляет только созданные своим ledger файлы и пустые каталоги, проверяет
hashes. Неожиданные изменения не перезаписываются. Local profile, DB, fixtures
и evidence сохраняются. Обычная финальная установка оставлена и сверена
с plan/installed hashes; наличие разрешённых патчей не означает совпадение
research с original. Три исторических research-лога сохранены как baseline.

Primary schema1 backup по записи владельца сайта:
`local/web/runtime/portal.sqlite.pre-v2-0a14783a-e6d2-4105-a2aa-95ee86381081.sqlite`,
45056 B, SHA
`314c71646f9cbb78928a1bcb6881065cc6efdd0cf45509134cac1560233dd779`.
Проверены integrity и protected user projection до миграции. Этот файл
**предшествует** последующим email bindings/регистрациям. Перед откатом нужно
согласованно остановить владельцев website/bridge/gateway, отдельно сохранить
актуальную schema2 DB/WAL/SHM и новые записи, затем восстановить совместимые
старые source/schema1 при остановленных процессах. Автоматической обратной
миграции новых данных нет. Game DB и UUID/r1 не удалять как «исправление входа».

После ручной проверки сохранены согласованные текущие schema2 portal и schema1
game snapshots через SQLite backup API из readonly источников, включая WAL:
`E/handoff-database-snapshot-01/{portal.sqlite,game.sqlite,snapshot.json}` — PASS,
обе integrity_check=ok. Они дополняют, а не заменяют исторический pre-v2 backup.
Точный before исправления observer: `E/gui-agent/primitive-fix-01/sr_interactive.before.py`.
Обратный патч проверен командой
`git apply -R --check local/evidence/20261004-p02-unified-account/gui-agent/primitive-fix-proposed.patch`;
его применение меняет собственный source, но не уже установленный `.pyc`.
Клиент сначала откатить через ledger и пересобрать пакет из выбранного source.

**Ограничение: exact source rollback только email-этапа NOT_AVAILABLE.** Полный
snapshot app/store/security/game-adapter непосредственно перед этим этапом не
сохранён. Есть исходный exact ZIP всей карточки и отдельные before трёх EJS,
`E/data-agent/username-v1-tools/{hangar_state.py,account_state_probe.py}`.
Реконструкция по памяти не называется точным откатом. Для полного rollback
использовать `E/project-before.zip` и согласованную DB snapshot, выбирая только
собственные файлы после проверки hashes; не распаковывать весь ZIP поверх
параллельных изменений сайта. Новые игровые данные и evidence сохранять
отдельно даже при возврате старой версии source.

`.gitignore` исключает `local/`, обе клиентские копии, local config, secrets,
DB/dumps/pcap/pyc и build outputs. Наличие правил не заменяет проверку состава
Git перед публикацией. Клиентские derived resources и actual wire evidence
не публиковались этим документом; здесь только пути, hashes и собственный код.

## Окончательная приёмка основного сайта

Primary3091 использует `local/web/runtime/portal.sqlite`; c5326cc1…/nativeID1
и271022a3…/nativeID2 — именно основные пользователи. Исторический isolated
3260d317… — другой UUID, хотя в тесте использовались такие же credentials.

| Gate | Результат | Evidence |
|---|---|---|
| Миграция primary schema2 и единственный writer | PASS21HTTP owner checks; старый website остановлен владельцем, текущий PID9452 | `local/web/email-cutover/run-01/completion.json` |
| Сохранённая сессия владельца → email binding | PASS CSRF/current password/UUID unchanged/fresh email login | `E/operator-email-binding-01/` |
| Новые primary регистрации | PASS HTTP/login/negative/profile; второй русский ник прошёл native, новая ASCII-учётка пока unlinked | `E/primary-email-registration-01/registration.json` |
| Два primary native профиля | PASS Email17+18; native ID1/2, UTF8 nickname, original callbacks, exact streams/CRC, PNG | `E/wire-agent/verify-email17-primary-01/`, `verify-email18-primary-cyrillic-01/` |
| Настоящий backend restart и relogin | PASS: website PID9452 остался прежним, игровые children перезапущены, UUID/nativeID/profile/fixture preserved; Email19 PASS | `E/primary-external-restart-01/restart.json`, `E/primary-state-before-restart-01/`, `primary-state-after-restart-01/`, `primary-state-after-native-01/` |
| Read API двух пользователей | PASS собственные данные; чужой query не меняет authenticated subject | Те же state reports и `E/primary-state-after-manual-01/` |
| Normal21 без control/autologin/autoquit | PASS95.003sprocess/76.435sLoginView/0ownUDP; завершён harness exit1 | `E/gui-agent/normal21-prepare/normal-idle/normal-idle-report.json` |
| Manual20 | HUMAN_ATTESTED ручной ввод; AUTH_AND_SERVER_ACCOUNT_DATA_ONLY PASS, fullGUI/idle FAIL | `E/wire-agent/manual-auth20/manual-auth-analysis-02.json` |
| Окончательный пакет | PASS12устанавливаемых файлов, ещё3runtime logs сохранены в backup; `test_control=null`, normal_auto_login/quit=false | `local/client-install-001/{install-plan.json,patch-ledger.json,install.json}` |
| Original и research integrity | PASS полный original unchanged; research = свой baseline + final ledger, неожиданных изменений0; 21/21 diagnostic restore checks PASS | `E/final-state-audit-02.json`, `E/final-manifest/` |
| Общая identity/данные/обычный пакет | **PASS узкого среза**, подкреплённый указанными критериями | Не означает полного GUI/P02 или боя |
| Последняя native-регрессия Email22 | **FAIL**: все основные gates кроме native_errors PASS;1ToolTip exception при fini | `E/wire-agent/verify-email22-final-observer-01/unified-entry-verification.json` |
| Полный GUI/P02 | **FAIL GUI / PARTIAL P02**, P03 NOT_STARTED | Оставшийся дефект описан ниже |

Email18 измерил180.2630625snetwork/176.84588sready, server/client seq134/40:
выход за прежнюю границу32 подтверждён на обеих сторонах. Длительность default
1800s и его завершение не измерялись. Исторические Normal20/21 остановлены
harness принудительно, поэтому clean native exit для них NOT_RUN. Скриншот
Normal21 NOT_RUN; actual primary PNG17/18/19/22 просмотрены root отдельно.

На момент передачи основной supervisor PID83412, identity78212, gateway94520,
run `local/server/run-20261004T124926-beeaa5`; сайт остаётся PID9452.
Это OBSERVED snapshot, не обещание сохранения PID при следующем запуске.
Клиент закрыт, isolated3092/testbackend остановлен. Final ledger SHA256:
`f0671d7f40232a4a54ea3625de5f84111d58c386966555148a2df95040be82c0`.
Полный original manifest SHA256:
`74c37c18e9ac7e30196c134076dacf6f2a8bf3897f7def73905d09feb3647797`.
Полный research final manifest SHA256:
`e988dc2d45a52e0a9ea883bf141e3dbe90109963e045d241c8e38ab0f51146ee`.
Audit SHA256: `e89f2b306f59e3e2799fd9bbf554cd3f11e5625134376dddd9316214fab5a61a`.

Первый `E/final-state-audit.json` сохранён FAIL: helper передал пути в Git
через Windows text-mode CRLF, Git вернул quoted paths с literal CR и проверка
membership ошибочно отвергла все9ignore checks. Сами21restore/original/research
проверки уже были PASS. Во втором отчёте вход/выход Git сделан binary NUL-delimited;
все9исключений подтверждены. `.gitignore` для получения PASS не менялся.

## Ручной вход, обнаруженные UI ошибки и исправление observer

Владелец прямо подтвердил: **«Да, сам ввел, вошел, потыкал разное»**.
Это HUMAN_ATTESTED физический ввод, а не инструментальный перехват клавиатуры.
Normal20 не содержал control/autologin/autoquit, diagnostic submit отсутствует;
реальный original LoginView вызвал native login и получил LOGGED_ON. Проверены
точные credentials по private evidence, UUIDc5326cc1…/nativeID1, три server streams
с CRC, original callbacks,100000/0/0 и нулевая статистика. В narrow analysis
215пакетов. Строгий idle gate закономерно FAIL: пользователь начал играть с UI.

Полный GUI того запуска FAIL: семь original ToolTip `len(None)` и один наш
`primitive` TypeError при ProfileAwards. Исключения есть в flushed JSONL;
отсутствие полного buffered traceback в принудительно закрытом python.log
не считается чистым запуском. Evidence: `E/gui-agent/normal20-errors-01/report.json`.
Original source: `res/scripts/client/gui/Scaleform/framework/ToolTip.pyc`, SHA256
`93b44d6c3cf47e32eca5f035442db2e245af5fab3f23475823348b1b5ff91e04`.
`onCreateComplexTooltip` line65/offset21 вызывает `__genComplexToolTip`;
line74/offset6 вызывает `len(tooltipId)` с None. Ошибка возникает до localization,
parse/as_show; default registration перед этим уже получена. Ни конкретная
Flash-кнопка, ни отсутствующее серверное поле этим evidence не установлены.

Наш observer `primitive` исправлен: ключи остаются строками, исчерпание
node/depth/width/48KiB encoded budget возвращает явный truncated и прекращает
обход. Данные GUI не заменяются. Source SHA256
`4f4629698b8a5b947de692e5f83d7f01f3c888e6c15eb72c4c8faf7dff9ac031`.
Tests9/9 + actual CPython2.7.3 before/after5/5 PASS, compile PASS. Ранний runtime
test с неверным nested budget5 ожиданием сохранён FAIL; правильный контрпример
budget4 проверен отдельно, source между ними не менялся.

Email22 на этом source:253/253packet hashes,80.2926042swire,76.452022sready,
server64/client20/lastACK65; account/nativeID/fixture и просмотр PNG PASS.
Observer-исключений не записано. Однако trace line400/t93.738352s содержит
original ToolTip TypeError **после** quit_requested93.561191/fini_enter93.584869,
между cleanup native_spaces/gui_personality. Все10cleanup stages и exit0 PASS,
но общий результат **FAIL**. Это наблюдение порядка событий, а не доказательство
первопричины. Отчёт SHA256
`55d428c5fbffe6669e58cf7c9526cbef75a8a4da1d2a7e930b5866fae1c2ff66`.
Намеренное повторение ProfileAwards/семи tooltip-действий после фикса NOT_RUN.
Tooltip-обработчик не патчился, ошибки не подавлены пустым ответом.

Повтор анализа сохранённого Email22 (ожидается тот же FAIL, EXE не запускается):

```powershell
python -X utf8 tools/verify_unified_entry.py --install local/evidence/20261004-p02-unified-account/gui-agent/email22-final-observer-prepare --registration local/evidence/20261004-p02-unified-account/operator-email-binding-01/registration.json --credentials local/evidence/20261004-p02-unified-account/operator-email-binding-01/test-credentials.json --case operator_shared --private-key local/server/native-private.pem --fixture local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r1 --expect hangar --min-ready-seconds 60 --out local/evidence/20261004-p02-unified-account/verify-email22-repeat-next
```

## Оставшиеся неизвестные и один следующий шаг

**INFERRED:** boundary/negative/primary/native evidence обосновывает заявленный
email/password/nickname контракт этого клиента/окружения, но не произвольные
действия UI, все устройства ввода или production нагрузку.

**UNKNOWN / NOT_RUN:** producer None tooltipId; реальный ProfileAwards повтор
после observer fix; полный P02, general fragments/wraparound, конкурентные
native игроки, многочасовой сеанс, внешний игровой endpoint, arena/бой,
изменение inventory/progress, экономика, recovery/mail ownership, смена ника,
другие Unicode алфавиты. Для будущего двухклиентского теста нужна независимая
машина/клиент; mutex/EXE не обходились. Карточка не добавляла выдуманную историю,
экипаж/боекомплект или новые исторические механики.

Остаточные original product strings видны в welcome/ресурсах. Публичные имена
проекта отделены от stable/native/resource identifiers; полный ребрендинг
клиента не выполнен и массовая замена не применялась. Пароли/ресурсы/дампы
остаются ignored; локальная приёмка не объявляет готовность публичного сервиса.

**Единственный следующий проверяемый шаг:** записать аргументы и источник
вызова `onCreateComplexTooltip`, воспроизвести один None tooltipId на конкретном
UI-действии или при штатном закрытии и проверить исправление его причины.
Не подавлять exception и не выдавать пустую подсказку за готовую поддержку.
Арена и следующая фаза в этой карточке не начинались.
