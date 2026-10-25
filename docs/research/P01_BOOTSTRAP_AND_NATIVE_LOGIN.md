# P01: instance mutex, действующий Python и настоящий native login/rejection

Дата: 2026-10-02. Run: `20261002-p01-bootstrap`.
Продолжение по запросу владельца: проверить, не мешала ли другая игровая копия.
Все относительные evidence paths ниже — внутри `local/evidence/20261002-p01-bootstrap/`.

## Результат и приёмка

**PASS исследовательского сценария:** настоящий research EXE загрузил наш
скомпилированный diagnostic personality, вызвал родной BigWorld.connect,
отправил RSA-зашифрованный login request, принял отрицательный ответ нашего
loopback endpoint и штатно завершился. Два последовательных запуска без
отладчика: `native-04` и `native-05`. Во втором проверен дополненный rollback.

Это **не успешная авторизация**, не штатный ангар и не серверная арена.
Функции аккаунтов/сессий/мира не реализованы; P02–P03 NOT_STARTED.

Исследовательская приёмка P01 соответствует `docs/03_ROADMAP.md`, раздел P01:

| Критерий документа | Доказательство |
|---|---|
| Реальные трассы своего клиента и воспроизводимые эксперименты | `native-04/`, `native-05/`: request + reply + точный callback; `verification.json` |
| Явно известно, что осталось для входа и общей арены | Последовательность и UNKNOWN ниже; PROTOCOL_MAP / KNOWN_UNKNOWNS |
| Решение по стеку либо узкий следующий эксперимент | NATIVE_PRIMARY; Rust profile измеренного login + toolkit bundle writer; следующий срез — LoginSuccess/первый BaseApp request |

По этому исследовательскому критерию **P01 PASS**. Приёмка сетевого входа P02
и общего мира P03 не подменяется данным тестом. У исходного toolkit остаются
доказанные несовместимости; их обнаружение является результатом исследования.

## Закреплённый клиент

WorldOfTanks.exe SHA-256:
`86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed`.
Билд `v.0.9.1 #717`, RU. Baseline обеих копий: 3469 файлов,
14 680 626 869 байт, content manifest SHA-256
`74c37c18e9ac7e30196c134076dacf6f2a8bf3897f7def73905d09feb3647797`.
Original только читался. Чужие игровые процессы не останавливались,
память/файлы другой игровой копии не читались.

## Почему EXE молча выходил

- OBSERVED: `processes-before.json` — подходящих процессов в момент этой
  проверки не было. Состояние процессов во время старого run не записано.
- VERIFIED static: UTF-16 string `wot_client_mutex` по VA `0x17c6bd4`;
  CreateMutexW вызывается по VA `0x5a4e1a`, затем GetLastError `0x5a4e28`.
  Ненулевой результат ведёт в ветку раннего выхода, если не задан специальный
  режим ожидания. `pe-mutex-final/pe-startup.json` содержит строки/xrefs/код.
  `wot_wait_for_mutex` найден, но его режим **не запускался**.
- OBSERVED control: собственная утилита создала отсутствующий mutex, затем
  запустила тот же research EXE с безопасным diagnostic config. Клиент вышел
  с `0`, python.log не изменился, пакетов нет. `mutex-control/`.
  Собственный handle освобождён; чужие handles не менялись.
- OBSERVED comparison: без mutex первый повтор дал свежий Python log с
  `ImportError: No module named p01_probe`, exit `3`. `native-01/postrun/python.log`.
- INFERRED: работающая копия владельца правдоподобно объясняет прежние три
  exit `0`. Достаточность занятого mutex воспроизведена, но его прежнее
  состояние неизвестно, поэтому историческую причинность не объявляем VERIFIED.

Семантика именованных объектов: официальные
[CreateMutexW](https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-createmutexw)
и [OpenMutexW](https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-openmutexw).
Теперь runner проверяет mutex до изменения файлов. Проверка отказа при
занятом объекте: `preflight-refusal/verification.json` PASS, config не изменён,
patch ledger не создавался, реальный клиент не запускался.

## Загрузка диагностики и активный runtime

OBSERVED: установка только `res_mods/0.9.1/scripts/client/p01_probe.py`
в этом bootstrap завершалась ImportError. После компиляции собственного
исходника и установки `.pyc` по тому же resource path — успешный init.
Это проверка данного пути, не утверждение, что все возможные loaders клиента
вообще не умеют читать исходный Python.

VERIFIED runtime (`native-05/runtime.jsonl`):

```text
2.7.3 (default, Jun 17 2014, 19:02:39) [MSC v.1700 32 bit (Intel)]
pointer_bytes = 4
sys.path = scripts/client; scripts/common; scripts/common/Lib; scripts/client/DLLs/win32
init args_count = 4
ResMgr marker = P01_RES_MODS_091
```

Использован официальный [CPython 2.7.3 x86 MSI](https://www.python.org/downloads/release/python-273/).
Файл 15 867 904 байт, MD5 совпал с опубликованным
`c846d7a5ed186707d3675564a9838cc2`; дополнительно закреплён SHA-256
`05bf3b9686a64a413eeb6efb03b591f8a6f2d9c5496898f367e9cef79e4b2c02`.
Это воспроизводимое закрепление скачанного файла; GPG-проверка NOT_RUN.
MSI прочитан через read-only database APIs и SetupIterateCabinetW, installer
не исполнялся, регистрации/PATH patch нет. Итог —
`local/toolchains/cpython-2.7.3-x86/extraction.json`, 3082 файла с хешами.
Первая попытка через expand.exe обнаружила коллизию cabinet IDs `FileList.py`
и `filelist.py`; неполный каталог `python-2.7.3-x86` не используется.
Финальный extractor сразу использует точное соответствие MSI File/Directory.

Компилятор запускается с `-E -S -B`, компилирует только наш исходник,
не исполняет его и не загружает клиентский marshal. Magic `03f30d0a`, timestamp
заголовка `.pyc` нормализован к 0. `native-05/compiler.json` фиксирует source/pyc hashes.

## Измеренный login request

Первый настоящий corpus: `native-02/packet-000-client_to_server.bin` и два
повтора. Пакеты по 273 байта. Наш RSA private key успешно расшифровал payload;
проверены тестовые строки пользователя и пароля. Ключи и plaintext только local.

| Поле | Wire offset / размер | Уверенность |
|---|---|---|
| Packet flags `0x0001` | 0 / 2, LE | VERIFIED raw; трактовка HAS_REQUESTS подтверждена toolkit config и ответом |
| Login element ID `0x00` | 2 / 1 | OBSERVED для этого вызова |
| Payload length `260` | 3 / 2, LE | VERIFIED, полное потребление |
| Request ID | 5 / 4, LE | OBSERVED, тот же ID принят в ответе |
| Next request offset `0` | 9 / 2 | OBSERVED; многозвенные запросы NOT_RUN |
| Protocol value `0x02030000` | 11 / 4, LE | VERIFIED raw; внутренний смысл version bits UNKNOWN |
| RSA ciphertext | 15 / 256 | VERIFIED, 2 блока RSA-1024 OAEP/SHA1 |
| First request offset `2` | 271 / 2, LE | OBSERVED; другие варианты не поддержаны профилем |

Расшифрованная структура — 158 байт: flags `1`, короткая length-prefixed
строка username (93 байта), password (25), blob (16), ещё 16 байт и u32 trailer.
Username/password подтверждены заданными лабораторными значениями. Названия
`session key`, `digest`, `nonce` для остальных полей пока **INFERRED** по
структуре/сопоставлению; использование шифрования BaseApp и смысл digest ещё
не проверялись. Код не принимает эти поля за доказанную авторизацию.

## wg-toolkit: измеренные отличия и узкий профиль

Commit сохранён: `5b879f0b960ccb4a3b799ede952256e253ef74cb`. Vendor не изменён.
Штатный reader ожидает современный 4-byte packet prefix, дополнительный
encryption bool и context. У измеренного запроса их нет. Офлайн-прогон того
же настоящего datagram: stock PacketConfig возвращает
`UnknownFlags(16384)`; добавление внутреннего нулевого prefix позволяет
прочитать конфигурацию пакета. `native-offline-decode.log`.

`tools/wg_probe/src/login091.rs` — собственный ограниченный профиль данного
наблюдения: 1024-byte datagram cap, один peer, deadline 60 s, максимум 64
пакета, только observed flags/protocol/одно request, не более четырёх RSA
блоков. Ошибка RSA возвращается через Result, без upstream RSA unwrap.
Расширенные string lengths, другие flags/версии явно отвергаются. Для ответа
переиспользован toolkit Bundle/reply writer; современный prefix в сеть не отправляется.
Это серверная совместимость с native wire, а не новый клиентский протокол.

На `native-03` прежняя toolkit-константа `74` дала реальный callback
`LOGIN_REJECTED_UPDATER_NOT_READY`. В нашем EXE VA `0x60da55` регистрирует
`SERVER_NOT_READY=0x49` (73), VA `0x60dab6` — `UPDATER_NOT_READY=0x4a` (74).
Доказательство: `pe-status-code/pe-startup.json`. Современный enum из профиля
убран; исправленный код 73 подтверждён на `native-04` и `native-05`.

## Двусторонний контроль

`native-05/verification.json` проверяет хеши настоящих packets, длины,
совпадение request ID, код/строку ответа и точный runtime callback:

```text
[1, 'LOGIN_REJECTED_SERVER_NOT_READY', 'P01_LOCAL_PROBE: no game service']
```

Запрос — 273 байта, ответ — 45. Есть `quit_requested`, `fini`, client exit 0,
timeout false. Backend после опыта останавливается родительским runner;
его termination code не интерпретируется как protocol failure.
На native-02 старый 20-second deadline завершил клиента вскоре после init;
факт timeout сохранён. Текущий deadline 45 s, допустимый диапазон 5–60.

Все игровые адреса сценария числовые loopback. Native game personality не
загружен. Системный firewall/общесистемный egress capture не применялись;
отсутствие любого фонового OS-трафика не утверждается.

## Проверки и восстановление

| Проверка | Результат | Evidence |
|---|---|---|
| Собственный instance mutex воспроизводит early exit | PASS | `mutex-control/` |
| Занятый mutex останавливает runner до изменений | PASS | `preflight-refusal/verification.json` |
| Собран профиль, без изменения vendor | PASS, 3 прежних upstream warnings | `wg-profile-build-final.log` |
| Runtime / res_mods / request / correct rejection callback | PASS | `native-04/`, `native-05/` |
| Независимая корреляция raw request/reply и callback | PASS | `native-05/verification.json` |
| Python tests | PASS 20/20 | `python-tests.log` |
| Rust boundary tests | PASS 4/4 | `rust-tests.log` |
| Actual corpus + truncation / wrong flags / damaged RSA | PASS 4/4, errors без panic | `real-corpus-negative/results.json` |
| Stock native decoding | FAIL, профиль требуется | `native-offline-decode.log` |
| Полный login, BaseApp, account, arena, два клиента | NOT_RUN | Не входят в этот завершённый узкий эксперимент |

Первая полная сверка обнаружила один новый `Influx_PS.bak`, идентичный
исходному Influx_PS.log. Он сохранён в `extra-write-backup/`, отсутствие
в baseline проверено, затем удалён только этот новый файл. Журнал —
`extra-write-restoration.json`. Runner теперь включает `.bak` в штатный
backup/restore ledger; `native-05` проверяет исправленный путь.
Финальная полная сверка — `final-integrity-verified/baseline-comparison.json`.

## Оставшееся и один следующий шаг

UNKNOWN: LoginSuccess data/redirect, первый BaseApp message, Blowfish/channel
handshake, sequence/ACK/fragmentation, inherited wire method order, обязательные
Account/Avatar/Arena события, authority/visibility и общий мир. Механика
двух клиентов из diagnostic rejection не выводится. Ограничение одного
экземпляра на этот mutex также нужно учесть при последующем стенде; обход
EXE не выполнялся, будущие тесты на двух ПК не ограничены одним локальным mutex.

Проверяемый путь: измеренный Login request/reply → LoginSuccess/собственный
BaseApp endpoint → минимальная native session → обязательные Account события
→ переход в Avatar/Arena → две сессии одного server world. После первой
стрелки всё остаётся работой последующих карточек, а не реализованной архитектурой.

**Единственный следующий рекомендуемый шаг:** отдельная карточка P02 —
измерить минимальный LoginSuccess/redirect и получить первый настоящий
BaseApp request на втором собственном loopback endpoint. Сейчас остановка
после P01. Команды/откат — [REPRODUCE](REPRODUCE.md).

## Bounded update-gate diagnosis — 2026-10-25

На свежей отдельной research-copy `local/clients/controller-fresh` поднят
изолированный локальный стенд `crew-any-native-t26-lifetime-fix-20261025-01`:
bridge `127.0.0.1:3692`, native login `127.0.0.1:20340`, base
`127.0.0.1:20341`. Внешний сниффер и внешние endpoints не использовались.

Клиент #717 с `sr_interactive` дошёл до обычного `LoginView`; endpoint в trace
зафиксирован как `127.0.0.1:20340`, update/modal-событий нет, а install ledger
полностью откатан (`restore=PASS`). Login-submit не выполнялся, поэтому raw
native reply и gateway auth reason в этом конкретном run имеют статус `NOT_RUN`;
пакетов в bounded manifest — `0`.

Причина старого окна «Требуется обновление» локализована до двух различимых
путей: актуальный `server/gateway/src/protocol/login.rs` отправляет исторический
`SERVER_NOT_READY=73`, тогда как старый `tools/wg_probe` через современный
toolkit формирует `74`, который клиент #717 трактует как
`UPDATER_NOT_READY`. Чистая копия на актуальном gateway update-модалку не
воспроизвела. Для окончательной классификации server-side ветки нужен отдельный
собственный login-submit с test-учётными данными и одновременной записью raw
reply/callback; этот шаг здесь намеренно не подменён синтетикой.

Evidence: `local/evidence/update-gate-bounded-20261025-02/update-gate-evidence.json`;
trace SHA256 `d2f4997c39b4d97a4ccf00c037059a919e619e73276882429e4c7c167b20d42b`.

### Account-run — 2026-10-25

Один ручной bounded submit на той же чистой копии достиг native login и дал
полную связку request/reply/callback без внешнего capture. В ответном login
пакете длиной 35 байт статусный байт `packet[11]` равен `67`
(`INVALID_PASSWORD`); trace сохранил `project_login_submit` и
`LOGIN_REJECTED_INVALID_PASSWORD`. Gateway stdout успел записать только
`SHARED_LOGIN_STARTED request_id=86428 identity_jobs=1`; отсутствие финальной
строки до controlled stop явно отмечено в evidence. По ветке
`server/gateway/src/session.rs` это `auth_result=Ok(None)`, то есть identity
не приняла введённую пару. Ни `73 SERVER_NOT_READY`, ни `74 UPDATER_NOT_READY`
в этом запуске не наблюдались, поэтому update-gate снова не является причиной
данного отказа.

Evidence: `local/evidence/update-gate-bounded-20261025-03/update-gate-account-evidence.json`;
raw reply SHA256 `9df31244c3397a43a79d645b221fce617ac0dc2942edb894960c23dc39d0bce5`;
trace SHA256 `7d2e1961b31e05dfaa6003c6137354a21224be04b5b5b68626c8ee39eea0ca1e`.

### Повтор account-run — 2026-10-25

Повторный ручной bounded submit с явно выбранным локальным account label
`sr.ascii.f4d1e9` снова достиг native login и дал тот же raw/callback результат:
`packet[11]=67 (INVALID_PASSWORD)` и
`LOGIN_REJECTED_INVALID_PASSWORD`. Коды `73 SERVER_NOT_READY` и `74
UPDATER_NOT_READY` в raw reply отсутствуют. Gateway stdout содержит
`SHARED_LOGIN_STARTED request_id=46912 identity_jobs=1`, но не содержит финальный
`AUTH_REJECT`, поскольку controlled stop произошёл до flush. По исходнику
`server/gateway/src/session.rs` это согласуется с `auth_result=Ok(None)` →
rejection code `67`; точный split между неизвестной identity и неверным
паролем контракт не предоставляет.

Evidence: `local/evidence/update-gate-bounded-20261025-04/update-gate-account-evidence.json`;
raw reply SHA256 `30bac841b65ac369133798066e193fdc54acbfd9fc21d4ff5ad27765c78ba65e`;
trace SHA256 `2748bb57415c1b71b9cc01e3d2f0856c6b31b9d2b50dd79390a70407e6fd3cf8`.

### Credential sync и bridge-only verification — 2026-10-25

Активная worktree-запись `sr.ascii.f4d1e9@example.test` уже совпала с известной
локальной test-парой из
`D:/WoT_9.1_Server/local/client-controls/crew-t26-control-20261024-06.json`,
поэтому hash не переписывался и backup для mutation не создавался. Отдельный
bridge-only POST на `127.0.0.1:3692/internal/native/login` вернул HTTP `200`,
`native_database_id=1`, `name=sr_ascii_f4d1e9`; client/gateway не запускались.
Это supersede’ит прежнюю гипотезу о mismatch активного hash. Для прежнего native
`67` остаётся только безопасный вывод: вручную отправленные байты отличались от
известной test-пары — например, был введён короткий label вместо полного email
или другой парольный байт. Plaintext credentials trace не сохраняет.

Evidence: `local/evidence/update-gate-bounded-20261025-04/credential-sync-bridge-evidence.json`;
status `PASS_ALREADY_SYNCED_BRIDGE_ONLY`. Предыдущий metadata audit помечен
superseded в `local/evidence/update-gate-bounded-20261025-04/identity-record-audit.json`.

### Native bounded account-run — 2026-10-25

Один bounded-прогон с полным email `sr.ascii.f4d1e9@example.test` и той же локальной
test-парой прошёл через оригинальный `LoginView.onLogin`: trace сохранил
`project_login_submit`, `diagnostic_login_submit` и callback
`LOGGED_ON`. Gateway зафиксировал `SHARED_LOGIN_STARTED request_id=21802`, четыре
`AUTH_PENDING_DUPLICATE` для `21803..21806`, затем
`SHARED_SESSION_PENDING ... authenticated=true` и `SESSION_ACTIVE id=1`.
Raw login success reply — 28 байт, `packet[11]=1` (`LOGIN_SUCCESS`), без
`67/73/74`; `AUTH_REJECT` отсутствует. Встроенный loopback Recorder сохранил
пять login requests и последующий BaseApp/account sync; внешний сниффер не
использовался. Client, services и install ledger после запуска восстановлены.

Evidence: `local/evidence/update-gate-bounded-20261025-06/update-gate-native-account-evidence.json`;
raw reply SHA256 `c5669abe58b8f0d72e26c05ca099ea38d5b48511b68c8040e6e67ae9b5240b5b`;
trace SHA256 `67db58024d9782132dd9736a432ffb8a24292df502b7e2c36bd8fd1a595e20e8`.

### BaseApp/Account sync до готового hangar — 2026-10-25

Отдельный bounded native-прогон продолжил успешный login на свежей установке
`local/clients/controller-fresh` и остановился после готовности штатного ангара.
Внешний сниффер не применялся: запись выполнялась встроенным loopback gateway
recorder на стенде `crew-any-native-t26-lifetime-fix-20261025-01`.

После `ConnectionManager.connectionWatcher` с `status=LOGGED_ON` trace сохранил
оригинальные Account callbacks: `onBecomePlayer`, `onCmdResponseExt` для
`requestID=221/222/223` с `resultID=1`, `onStreamComplete` для streams
`221/222/223` (2904/23109/103 байта, integrity-пары совпали), затем
`showGUI`; запрос `224` вернулся с `resultID=0`. Gateway независимо записал
`SHARED_BASE_BOUND`, `ACCOUNT_CREATE_QUEUED`, `SESSION_ACTIVE`,
`ACCOUNT_SYNC_REQUEST` для команд `100/300/600` и `ACCOUNT_SHOW_GUI_QUEUED`.
Поздний `request=226 command=1600` получил `result=-10` как неподдерживаемое
приложение и не изменил состояние.

Встроенный capture содержит 311 native-пакетов: 5 login client→server, 1 login
server→client, 118 BaseApp client→server и 187 BaseApp server→client. Raw
файлы оставлены в локальном capture; в отчёт вынесены только безопасные
метаданные, размеры и SHA-256. На первой готовой observation (`77.20 s`)
одновременно наблюдались `native_connected=true`, `items_cache_synced=true`,
`hangar_space_inited=true`, `hangar_space_loaded=true`,
`hangar_space_loading=false`, `LobbyView/Hangar`, `vehicle_model_loaded=true`
и четыре видимые vehicle-модели; выбранный объект — штатный MS-1 inventory `1`.
Это доказывает границу login → BaseApp → Account → готовый hangar, но не бой и
не интерактивное действие в ангаре.

Evidence: `local/evidence/update-gate-bounded-20261025-07/baseapp-account-hangar-evidence.json`;
trace `local/client-runtime-update-gate-bounded-20261025-07/native-257272-1792931216771.jsonl`
(SHA-256 `790dd66218cac2356c1c0db24a2825429a491417f4436ef66e973f68d3af0172`);
capture manifest SHA-256
`da2ea9cab55efddf32641787eabb51aa662e0f5262b51764e380df1d42151e07`.
