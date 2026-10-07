# P02: ответ BaseApp → первое сообщение канала

Дата: 2026-10-04, Asia/Yekaterinburg. Run: `20261004-p02-baseapp-reply`.
**Карточка PASS; полный gate P02 NOT_RUN.** Основание — «давай» владельца
после [карточки redirect](P02_LOGIN_REDIRECT.md). Граница —
[план](../plans/P02_baseapp_reply.md).

## Результат и граница

Два настоящих запуска закреплённого клиента дали цепочку:
native LoginRequest → LoginSuccess → BaseApp request 21 B → наш зашифрованный
BaseApp reply 24 B → первый зашифрованный клиентский пакет 24 B.
Штатный callback `BigWorld.connect` в обоих запусках: `[1, 'LOGGED_ON', '']`.
Первый последующий пакет возвращает новый токен из BaseApp reply.

Account, entity creation, ангар и арена не создавались. ACK/канал ещё не
реализованы: после первого пакета сохранены следующие сообщения, но их
оставшаяся часть явно не обрабатывается. В обоих runs наблюдался также
callback `[6, 'NOT_SET', '']`, затем диагностический выход EXE 0.
**LOGGED_ON здесь доказывает native handshake, а не работающий игровой сервис.**

Evidence root далее обозначен `E`:
`local/evidence/20261004-p02-baseapp-reply/`.

## Исходное состояние и воспроизводимость

VERIFIED: клиент `v.0.9.1 #717`, RU, EXE SHA-256
`86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed`.
Обе копии: 3469 файлов, 14 680 626 869 байт; canonical content hash
`74c37c18e9ac7e30196c134076dacf6f2a8bf3897f7def73905d09feb3647797`.
`E/baseline-verified.json` сопоставляет их с окончанием предыдущей карточки.
Оригинал только читался.

До изменений сохранены 66 собственных файлов в `E/project-before.zip`, hash
`fc6a1519adab3d4d6b54d6e2ba9a30f1e83ecc5f8dbb9b2b0ca5a770dfe04a7f`,
отдельно `project.local.before.json`. Точная итоговая версия —
`E/code-manifest.json`, полный список собственных файлов — `project-files.json`.
Git пока без commits; изменения чужой параллельной веб-сессии в этот снимок
и `changed-files.json` не включаются.

В начале mutex был занят (`instance-before.json`); реальный клиент тогда
не запускался. После ответа владельца «закрыл» `instance-after-user-close.json`
подтвердил его отсутствие. Чужой процесс не завершался, mutex не обходился.

VM снова подтвердила Python 2.7.3, Jun 17 2014, MSC v.1700, 32 bit;
`native-02/runtime.jsonl`. Диагностическая personality по-прежнему вызывает
встроенный `BigWorld.connect`, без подмены callback. Её исходник в этой карточке
не изменён. Все адреса — числовые loopback: Login front/backend 20014/20015,
BaseApp front/backend 20016/20017. Системный egress capture не выполнялся.

## Основание формата до первого запуска

Статическое исследование выполнялось по этому EXE, без патча бинарника:

- `E/pe-network-strings.json`: строка `baseAppLogin`, VA `0x19b0d88`, raw
  reference `0x1683c77`; RTTI `.?AVBaseAppLoginRequest@BW@@`.
- `E/pe-baseapp-rtti.json`: type descriptor `0x1f86320`, vtable `0x19b1a60`.
  Элемент vtable +0x14 указывает на `0xd762a0`.
- `E/pe-baseapp-handler/pe-startup.json`: общий callback `0xd75c60` вызывает
  vtable +0x14; `0xd762a0` запрашивает четыре байта, затем передаёт прочитанное
  значение в `0xd749b0`. Кандидат payload — отдельный u32.
- В том же файле `0xd76260` дважды резервирует/записывает четыре байта.
  Это поддерживает интерпретацию измеренных 8 payload bytes BaseApp request
  как двух 32-битных полей. Название второго поля «счётчик попыток» остаётся
  INFERRED из последовательности 0…5 прошлой карточки.
- `E/pe-interface/pe-startup.json`: регистрация `baseAppLogin` использует
  аргументы 1/2, `authenticate` — 0/4. Числовые wire IDs из порядка регистрации
  не назначались. Дополнительное окно `0xede8d0` из первого static probe
  не является доказанным началом функции и в выводах не использовано.

Закреплённый toolkit использует u32 SessionKey reply и packet Blowfish filter.
Они послужили гипотезой. Его modern BaseApp parser и протокол целиком не
использовались; формат ответа окончательно подтверждён реальным клиентом.

## Подтверждённые bytes

Главные файлы `native-02`:

| Артефакт | SHA-256 |
|---|---|
| `packet-003-base_server_to_client.bin`, 24 B | `46dd0c9a4b8c7636492256674159bf510d1c132b84dfcc996d3f1dd1a31e19a1` |
| `packet-004-base_client_to_server.bin`, 24 B | `8eaa0ebb08fff459e48097c33cfe12d99da3056a7c6bfbc5206a88bff4025e5b` |

VERIFIED: оба datagrams целиком зашифрованы, без modern четырёхбайтового
открытого prefix. Ключ — те же 16 bytes из расшифрованного LoginRequest.
Blowfish blocks по 8 bytes; перед шифрованием XOR с предыдущим **открытым**
блоком, начальный XOR — нули. После packet bytes идут padding, magic
`EF BE AD DE` и byte wastage=padding length+1. На принятых пакетах wastage
равен 3/4/5/7. Диагностический decoder ограничивает его диапазоном 1…8,
проверяет длины до вычитания и не использует assertion на входящих данных.

Наш ответ после снятия crypto footer — **15 bytes**:

| Offset | Bytes | Значение |
|---|---:|---|
| 0 | 2 | flags=0 |
| 2 | 1 | reply ID=255 |
| 3 | 4 | length=8, little endian; включает request ID |
| 7 | 4 | request ID соответствующего BaseApp request |
| 11 | 4 | Новый случайный токен транспорта, возвращённый клиентом |

Первое сообщение клиента после снятия crypto footer — **16 bytes**:

| Offset | Bytes | Подтверждённое наблюдение |
|---|---:|---|
| 0 | 2 | `58 04`, flags=0x0458 |
| 2 | 1 | element ID=0x01 |
| 3 | 4 | Побайтное совпадение с новым токеном BaseApp reply |
| 7 | 1 | `09` |
| 8 | 8 | В обоих первых пакетах нули |

VERIFIED: токен BaseApp отличается от токена LoginSuccess в этих runs.
INFERRED: ID 1 — authenticate; аргумент 4 bytes соответствует найденной
регистрации/возврату токена. Имя сообщения, смысл `09` и восьми последних
нулевых байтов пока не объявляются установленным контрактом.

После первого пакета пришли wire lengths 40, 48 и 24 B (clear 29, 37, 17 B),
flags 0x045a, 0x045a, 0x0458. Crypto/footer и начальный token проверены;
остальная часть UNKNOWN. Toolkit называет отличающийся бит 0x0002
HAS_PIGGYBACKS; это кандидат объяснения повторов, не законченная реализация
legacy ACK/piggyback parser. Callback 6/NOT_SET наблюдался после этих пакетов.
INFERRED: завершение связано с отсутствием продолжения канала при заданном
`inactivityTimeout=5.0`. Причинный timeout/control эксперимент NOT_RUN.

## Реализация и проверки

`baseapp091.rs` — отдельный профиль `legacy091-baseapp`, один Login peer,
один BaseApp peer, один handoff token и один последующий transport token,
лимит 60 секунд и порог 128 datagrams между итерациями (до 129, если оба
сокета готовы в последней итерации). Payload >1024 bytes отвергается до crypto;
receive buffer вмещает полный UDP datagram, чтобы Windows WSAEMSGSIZE не
завершал процесс. Чужой token/peer, плохой crypto footer и неизвестный
начальный element явно отвергаются. Повтор не выдаёт второй token.
Остаток неизвестного сообщения получает `BASEAPP_UNPARSED_REMAINDER` и не
исполняет игровые команды. Generic entity/PYTHON dispatch отсутствует.

`client_probe.py` добавляет двусторонний BaseApp capture и заранее сохраняет
PID своих процессов в `processes.json`. Существующие ledger/backup/postrun/
restore остаются обязательными. Proxy рассчитан на одну локальную попытку:
ответ идёт последнему BaseApp source peer. Многоклиентный routing NOT_RUN.

`verify_baseapp_capture.py` независимо расшифровывает реальные bytes Python
cryptography, проверяет hashes, request IDs, оба токена, первый frame,
настоящий LOGGED_ON и завершение/откат. `check_baseapp_probe.py` строит
явно помеченные мутанты из corpus и проверяет отказ/повторы на loopback.
Ни один мутант не считается настоящей клиентской трассой.

| Проверка | Результат | Evidence в E |
|---|---|---|
| Offline pinned build | PASS, 3 прежних vendor warnings | `build-final.log` |
| Rust: 4 прежних + 4 новых проверки | PASS, 8 | `rust-tests.log` |
| Python resource/parser tests | PASS, 20 | `python-tests.log` |
| Два реальных BaseApp handshakes + первый frame + LOGGED_ON | PASS | `native-01/baseapp-verification.json`, `native-02/baseapp-verification.json` |
| Offline negative checks | PASS, 50 | `negative-01/results.json` |
| Live UDP controls/отрицательные случаи | PASS, 25 | тот же файл, `backend.stdout.log` |
| Предыдущий redirect профиль на настоящем клиенте | PASS | `redirect-regression/redirect-verification.json` |
| Свежие Python logs трёх запусков | PASS | `<run>/log-check.json` |
| Полные клиентские manifests после отката | PASS | `final-integrity/baseline-comparison.json` |
| Git exclusions / свои процессы и порты | PASS | `git-safety.json`, `process-cleanup.json` |
| Полный P02/V01/V02/V04, стабильный канал, Account, арена | NOT_RUN | Вне объёма этой карточки |

Среди live cases — запрос до Login, усечения, header/token/attempt mutations,
UDP 65507 B, плохие magic/wastage, неверный session token, дубликаты,
другой request ID с тем же token и другой peer. Все проверки нового профиля
прошли; неудачных native runs в этой карточке нет. Начальная занятость mutex
разрешилась до запуска и не выдаётся за client FAIL.

## Повторение и откат

PowerShell из `D:\WoT_9.1_Server`, свободные 20014–20017, другая копия игры
закрыта. Среда прежняя: Rust 1.90.0 GNU, pinned Cargo.lock/toolkit commit
`5b879f0b960ccb4a3b799ede952256e253ef74cb`, Python cryptography 48.0.0 и
локальный компилятор CPython 2.7.3. Новых зависимостей не добавлено.

```powershell
. ./tools/rust_env.ps1
cargo build --locked --offline --manifest-path tools/wg_probe/Cargo.toml
cargo test --locked --offline --manifest-path tools/wg_probe/Cargo.toml
python -X utf8 -m unittest discover -s tests -v
$taskRun = 'local/evidence/p02-baseapp-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
python -X utf8 tools/client_audit.py manifest --out "$taskRun/baseline"
python -X utf8 tools/client_probe.py run --out "$taskRun/native" --backend local/vendor/wg-toolkit-rs/target/debug/p01-wg-probe.exe --backend-profile legacy091-baseapp
python -X utf8 tools/verify_baseapp_capture.py --run "$taskRun/native"
python -X utf8 tools/check_baseapp_probe.py --run "$taskRun/native" --out "$taskRun/negative"
python -X utf8 tools/client_probe.py run --out "$taskRun/redirect" --backend local/vendor/wg-toolkit-rs/target/debug/p01-wg-probe.exe --backend-profile legacy091-redirect
python -X utf8 tools/verify_redirect_capture.py --run "$taskRun/redirect"
python -X utf8 tools/client_audit.py manifest --out "$taskRun/after"
Get-FileHash "$taskRun/baseline/original-content-manifest.json","$taskRun/baseline/research-content-manifest.json","$taskRun/after/original-content-manifest.json","$taskRun/after/research-content-manifest.json"
```

Четыре content hashes должны совпасть. Static handler можно перепроверить:
`python -X utf8 tools/exe_startup_probe.py --out "$taskRun/pe" --va 0xd75c60 --va 0xd76260 --va 0xd749b0`.
Native runs и UDP controls запускать последовательно: порты общие.

Клиентские изменения уже автоматически откатились. Для прерванного будущего
run сначала завершить **его** PID из `processes.json`, затем выполнить
`python -X utf8 tools/client_probe.py restore --out "$taskRun/native"`.
Повторный restore завершённого run откажет. Все исходные hashes/backups и
послезапусковые файлы сохранены. Оригинальный EXE и mutex не патчились.

Проектный откат — адресно по `changed-files.json` из `project-before.zip`,
config из `project.local.before.json`, сохранив любые последующие правки.
Новые файлы убирать адресно. `web/` и `local/web/` принадлежат отдельно
запрошенной параллельной сессии; этим откатом их не затрагивать.

Новых обязательных входных файлов от владельца нет. UNKNOWN: полный
channel footer/ACK/piggybacks/sequence, остальные message IDs, устойчивый
transport/session lifecycle, Account и аренa. Аутентичность дистрибутива
относительно внешнего эталона по-прежнему UNKNOWN.

**Единственный следующий шаг:** отдельная карточка P02 — установить формат
ACK для измеренного первого сообщения и проверить, что реальный канал
переживает нынешнее окно завершения без повторов/разрыва. Account и игровые
сущности автоматически не добавлять.
