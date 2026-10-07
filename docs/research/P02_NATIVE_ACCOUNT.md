# P02 — первое создание native Account

Дата: 2026-10-04. EXE: `v.0.9.1 #717`, RU. Продолжение по разрешению владельца
после [локального gateway/session рубежа](P02_LAB_GATEWAY.md).
План: [P02_native_account](../plans/P02_native_account.md).

**Приёмка wire creation: PASS. Полная инициализация Account: FAIL;
карточка Account и общий P02: PARTIAL.** Настоящий клиент принял сообщение
сервера, создал `Account.PlayerAccount` и прочитал все три переданных поля.
Оригинальный Python-конструктор затем остановился на отсутствующем объекте
настроек в diagnostic personality. Ангар, общая регистрация/авторизация,
Avatar, арена и следующие фазы не реализованы и не проверены.

Evidence root: [20261004-p02-account](../../local/evidence/20261004-p02-account/).
Все номера ниже относятся только к закреплённому клиенту и измеренной форме.

## Что установлено

| Статус | Вывод | Доказательство |
|---|---|---|
| VERIFIED | `Account.def` имеет 3 BASE_AND_CLIENT свойства: `requiredVersion_9100`, `name`, `serverSettings`. Развёрнуты Chat, AccountEditor, TransactionUser; добавочных свойств у них нет | [account-contract.json](../../local/evidence/20261004-p02-account/contract/account-contract.json), `schemas`, исходные hashes |
| VERIFIED | Original `account.pyc` присваивает `Account = PlayerAccount`; диагностический observer не создаёт и не заменяет эти классы | Там же `bytecode.account`, module offsets 489–520; source SHA-256 `bb6e88e4aec03161212847ffc3601d16917610b8f7815c42f91f610693f4d0ef` |
| VERIFIED | `createBasePlayer` — message ID 5, VAR2; Account type ID 0 принят этим клиентом | PE registration + реальные packets и native class/properties в [native-final verifier](../../local/evidence/20261004-p02-account/native-final/01-normal/account-verification.json) |
| VERIFIED | Payload начинается с u32 LE entity ID и u16 LE type ID, затем три коротких length-prefixed значения в указанном порядке | Reader `0xd6da50`; [PE body](../../local/evidence/20261004-p02-account/pe-create-body/native-pe.json); native runtime values |
| OBSERVED | В пяти запусках `BigWorld.player()` был пустым до создания, затем содержал `Account.PlayerAccount`, ID 152043521, имя `p02-native-account`, версию `ru_0.9.1_2`, `serverSettings={}`, `isPlayer=True` | `native-01`, `native-repeat/*`, `native-final` / `runtime.jsonl`, `account-verification.json` |
| OBSERVED | Без create packet тот же observer получил 22 отсутствующих player samples, Python log чистый | [no-creation verifier](../../local/evidence/20261004-p02-account/no-creation/01-normal/account-verification.json) |
| VERIFIED | Потерянный seq0 с Account payload повторён сервером автоматически; реальный client SACK=[1], cumulative0 сменился cumulative2 после retry0 | [drop verifier](../../local/evidence/20261004-p02-account/native-repeat/02-drop-server-first/account-verification.json), proxy `forwarded_copies=0`, `sequence=0 attempt=2` |
| OBSERVED | Оригинальный Account lifecycle не завершился: `Settings.g_instance` отсутствует, далее `syncData` не создан | [свежий Python log](../../local/evidence/20261004-p02-account/native-final/01-normal/postrun/python.log), `ContactInfo.__checkLoginDataSection` bytecode offsets 0–6 |
| INFERRED | Следующий необходимый bootstrap шаг — инициализация оригинальных Settings в изолированном профиле | Наблюдённая первая ошибка; её устранение ещё не доказывает достаточность остальных данных/UI |
| UNKNOWN | Остальные entity type IDs, RPC indices, полный PYTHON wire grammar, длинные строки, settings schema, последующие Account requests и достаточный bootstrap | Не подменены порядком имён, toolkit форматом или моками |

Хеш EXE: `86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed`.
Хеш `res/scripts/entity_defs/account.def`:
`883ec72e77675600f245e0f0aea8837e35c2c4bb9e7a5c5d70f3656d9d076674`.
Все 8 источников, размеры и hashes сохранены в `account-contract.json/sources`.

## Точный измеренный пакет

Application body, 46 bytes:

```text
05 2b00 01001009 0000
0a 72755f302e392e315f32
12 7030322d6e61746976652d6163636f756e74
06 80027d71002e
```

| Поле | Значение |
|---|---|
| Message ID / payload length | `05`, u16 LE `43` |
| Entity ID | u32 LE `0x09100001` = 152043521, собственный lab ID |
| Entity type | u16 LE `0`, подтверждён как Account |
| requiredVersion_9100 | 1-byte length 10 + ASCII `ru_0.9.1_2` |
| name | 1-byte length 18 + ASCII `p02-native-account`, тестовое имя |
| serverSettings | 1-byte length 6 + fixed Python pickle protocol-2 literal empty dict `80 02 7d 71 00 2e` |

Сервер не принимает и не выполняет PYTHON/pickle объекты. Он посылает только
собственный фиксированный безопасный literal; независимый verifier сравнивает
эти 6 bytes, не десериализует pickle. Обобщение на другие объекты — UNKNOWN.
`0x09100001` не является ID веб-аккаунта или подтверждённым databaseID.

Transport envelope: flags `0x0458`, этот body, seq0, cumulative ACK1;
далее ранее измеренное Blowfish packet encryption. Поле неизвестного blob
и component count из современного toolkit здесь не добавлялись: reader #717
сразу после 4+2 bytes передаёт оставшийся stream в EntityManager.

Static chain: CRT slot `0x16f10c0` → initializer `0x1683d50` → регистрация
VAR2 `createBasePlayer`; handler member записан в `0x16842f5` значением
`0xd6da50`. `EntityManager` при `0x5c7b40` передаёт type в lookup `0x5bf870`,
затем вызывает создание `0x5bfe00`. [Static sources](../../local/evidence/20261004-p02-account/contract/account-contract.json)
содержат кандидатные IDs и других сообщений; **только ID5/type0 подтверждены
новым native опытом**. Raw PE refs сами по себе не доказывают исполнение.

## Реальные проверки

| Проверка | Результат | Evidence |
|---|---|---|
| Первый native creation | PASS wire; FAIL original Python lifecycle | `native-01/01-normal/` |
| Повтор на persistent gateway PID23468 | 3 PASS wire: normal, drop-server-first, duplicate-client-first; по 1 session allocation/close | `native-repeat/`, per-run verifiers |
| Последняя сборка и diagnostic source | PASS wire; FAIL original Python lifecycle | `native-final/01-normal/`; binary SHA совпадает с сохранённым gateway metadata |
| Контроль без создания | PASS: 22 пустых player samples; transport lifecycle PASS, свежий Python log чистый | `no-creation/`, account + gateway verifiers |
| Rust unit tests | 20 PASS | [rust-tests-final.log](../../local/evidence/20261004-p02-account/rust-tests-final.log); новый test — владение payload, предел и сохранение при retry |
| Python resource/parser tests | 20 PASS | [python-tests.log](../../local/evidence/20261004-p02-account/python-tests.log) |
| Gateway own-UDP controls | 33 PASS; не замена native совместимости | [controls/results.json](../../local/evidence/20261004-p02-account/controls/results.json) |
| Откат всех 6 client runs | PASS | [client-restores.json](../../local/evidence/20261004-p02-account/client-restores.json), каждый patch-ledger/backup/restore |
| Полные manifests после последнего запуска | PASS, обе копии по 3469 files / 14,680,626,869 bytes, различий с baseline нет | [integrity-comparison.json](../../local/evidence/20261004-p02-account/integrity-comparison.json) |
| Штатный UI, Account sync/RPC, web→game login, два клиента, арена, fragments | NOT_RUN | За пределами этого измеренного создания |

Нативная сессия в Account runs держалась 11.58–11.68 s после LOGGED_ON до
планового disconnect; реальный native объект наблюдался более 9.5 s.
Это не успешный полный lifecycle: `Account.py:67 → Account.py:1641 →
ContactInfo.py:43` дал `AttributeError: 'NoneType' object has no attribute
'userPrefs'`; затем `Account.py:224` и `:257` дали отсутствие `syncData`.
Ошибки сохранены во всех пяти runs, verifier явно выдаёт lifecycle FAIL.

Полный content manifest SHA-256 обеих копий до и после:
`74c37c18e9ac7e30196c134076dacf6f2a8bf3897f7def73905d09feb3647797`.
Исходный manifest содержит единственный `res/scripts/client/account.pyc`;
в `res_mods/` до эксперимента только version-marker `.txt`, Account override нет.

Начальный запуск нового PE helper также выявил ошибку инструмента: попытку
перевести PE overlay offset в RVA (`None`). Поиск CALL ограничен executable
sections, pointer hits — mapped bytes; исправленный инструмент выполнен.
Это ошибка статического helper, не авария native клиента.

## Изменения и границы

Добавлены `account091.rs`, `account_contract_probe.py`, `native_pe_probe.py`,
`verify_account_capture.py`. Gateway получил отдельный opt-in профиль
`legacy091-account`, bounded reliable queue хранит собственный payload до ACK.
Runner/suite/fault control умеют этот опыт; personality только читает
`BigWorld.player()` и поля, не вызывает создание, не monkey-patch-ит Account.
Verifier транспорта по умолчанию продолжает отвергать application payloads
и ошибки Python; новый Account verifier явно разделяет wire PASS/lifecycle FAIL.

Исходники клиента Account/ContactInfo/entity_defs не менялись. Все диагностические
записи ограничены research копией; original только читалась. Endpoints —
числовой loopback 127.0.0.1:20014–20017, собственный ключ и disposable учётка.
Перехват всей системной исходящей сети — NOT_RUN; здесь доказан записанный
локальный обмен, а не изоляция ОС. Vendor/зависимости не менялись.

Сессии сайта по прямому поручению владельца передан статус: собственные
регистрация/вход сайта уже проверены её отчётами; общий вход web→game ещё не
подключён. Новое wire создание Account этой интеграцией не является.
Файлы `web/` и `local/web/` этой карточкой не изменялись.

## Повторение

Из корня `D:\WoT_9.1_Server`; нужен свободный `wot_client_mutex`.
Runner проверяет его до patch и не закрывает чужую игровую копию.

```powershell
. ./tools/rust_env.ps1
cargo build --locked --offline --manifest-path tools/wg_probe/Cargo.toml
cargo test --locked --offline --manifest-path tools/wg_probe/Cargo.toml
python -X utf8 -m unittest discover -s tests -v
$taskRun = 'local/evidence/repeat-account-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
python -X utf8 tools/account_contract_probe.py --out "$taskRun/contract"
python -X utf8 tools/gateway_suite.py --source local/evidence/20261004-p02-session-gateway/acceptance/02-normal --out "$taskRun/native" --account-probe --cases normal,drop-server-first,duplicate-client-first
python -X utf8 tools/verify_account_capture.py --run "$taskRun/native/01-normal"
python -X utf8 tools/verify_account_capture.py --run "$taskRun/native/02-drop-server-first" --case drop-server-first
python -X utf8 tools/verify_account_capture.py --run "$taskRun/native/03-duplicate-client-first" --case duplicate-client-first
python -X utf8 tools/gateway_suite.py --source local/evidence/20261004-p02-session-gateway/acceptance/02-normal --out "$taskRun/control" --observe-account --cases normal
python -X utf8 tools/verify_account_capture.py --run "$taskRun/control/01-normal" --control
python -X utf8 tools/verify_gateway_capture.py --suite "$taskRun/control"
python -X utf8 tools/check_gateway_probe.py --source "$taskRun/control/01-normal" --out "$taskRun/udp-controls"
python -X utf8 tools/client_audit.py manifest --out "$taskRun/integrity"
```

Account verifier exit0 означает его узкий wire criterion; проверять также
поле `original_python_lifecycle`, сейчас FAIL. `gateway_suite` runner PASS
означает завершение процессов/откат, не совместимость. Каждый rerun требует
нового output каталога. Полный capture содержит локальные ключи/данные и
остаётся в Git-ignored `local/`.

Для статического повторения PE цепочки:

```powershell
python -X utf8 tools/native_pe_probe.py --out "$taskRun/pe" --va 0x1683d50 --va 0xd6da50 --va 0x5c7b40 --va 0x5bfe00 --bytes 1024
```

## Откат и следующий шаг

Client patches уже восстановлены автоматически. Если будущий запуск аварийно
прерван, сначала завершить только его process IDs из capture/process metadata,
затем `python -X utf8 tools/client_probe.py restore --out <каталог client run>`.
Уже восстановленный каталог повторно не применять. Ledger проверяет исходные
hashes backup и ограничивает запись research root.

До изменений сохранены 93 собственных файла в
[project-full-before.zip](../../local/evidence/20261004-p02-account/project-full-before.zip)
и локальная конфигурация `project.local.before.json`. Для отката серверных
исходников восстановить только изменённые существовавшие файлы по
`changed-files.json`, убрать только перечисленные новые файлы этой карточки,
затем пересобрать offline. Перед заменой проверить, что их текущие hashes
совпадают с итоговым manifest; последующие правки пользователя не затирать.
`web/`, клиентские каталоги и evidence архивом не заменять; общего git clean/reset
нет. Коммиты не создавались, Git identity по-прежнему не задана.

**Единственный следующий рекомендуемый шаг:** инициализировать оригинальные
Settings в изолированном diagnostic профиле и повторить тот же native Account
packet, проверив устранение первой `userPrefs` ошибки без подмены Account.
Достаточность последующего bootstrap и serverSettings установить новым trace.
