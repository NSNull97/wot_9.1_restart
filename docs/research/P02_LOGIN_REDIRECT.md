# P02: native LoginSuccess и первый BaseApp request

Дата: 2026-10-02, Asia/Yekaterinburg. Run: `20261002-p02-login-redirect`.
**PASS данной узкой карточки. Полная приёмка P02 — NOT_RUN.**
Владелец разрешил этот следующий эксперимент после отчёта P00–P01 словом
«погнали». Граница записана в [плане](../plans/P02_login_redirect.md).

## Что действительно выполнено

Дважды запущен настоящий исследовательский клиент. Его встроенный
`BigWorld.connect` отправил native LoginRequest на `127.0.0.1:20014`.
Собственный Rust-процесс за capture proxy (`127.0.0.1:20015`) расшифровал
запрос и ответил LoginSuccess с адресом `127.0.0.1:20016` и одноразовым
токеном. Клиент самостоятельно отправил на этот второй endpoint шесть
21-байтовых datagrams в каждом запуске. Все они содержат выданный токен.

BaseApp endpoint только записывал пакеты. Ответ BaseApp, session establishment,
Account, ангар и арена не реализовывались. Успешного callback `LOGGED_ON` нет.
Таким образом, проверен **redirect и первый запрос**, а не законченный вход.
Штатный выход EXE после диагностического таймера не является проверкой logout
из установленной игровой сессии.

## Объект, версии и исходное состояние

VERIFIED: клиент `v.0.9.1 #717`, RU, EXE SHA-256
`86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed`.
Обе копии до опыта совпали с результатом P01: 3469 файлов, 14 680 626 869 байт;
content manifest `74c37c18e9ac7e30196c134076dacf6f2a8bf3897f7def73905d09feb3647797`.
[Проверка baseline](../../local/evidence/20261002-p02-login-redirect/baseline-verified.json).
Активная VM снова сообщила Python 2.7.3, Jun 17 2014, MSC v.1700, 32 bit;
[runtime](../../local/evidence/20261002-p02-login-redirect/native-02/runtime.jsonl).

Оригинал только читался. До изменений создан `project-before.zip` из 60
собственных файлов и отдельная копия исключённого локального config.
SHA-256 архива: `ffa9acb84fd6f7eb254e22fa710dfc5b61c1f48f242861b63b5af984e80fe8a2`.
Git пока без commits: версии текущих файлов закреплены в
`project-files.json`, `code-manifest.json`, diff в `project-diff.patch`.

Зависимости: прежний wg-toolkit commit `5b879f0b960ccb4a3b799ede952256e253ef74cb`,
Rust 1.90.0 GNU, rsa 0.8.2, sha1 0.10.7; blowfish 0.9.1 теперь прямая зависимость
из уже закреплённого graph. Python verifier использует cryptography 48.0.0
для независимого RSA/Blowfish декодирования; ключи не печатаются в отчёте.
Штатный modern BaseApp codec не принят как совместимый и не использовался
для чтения native BaseApp datagrams. Vendor не изменён.

## Формат успешного ответа — VERIFIED для измеренного сценария

Доказательства: `native-02/capture.json`, `packet-001-server_to_client.bin`,
`redirect-verification.json`. SHA-256 ответа:
`717aeff1901702b8c216784cd6b32220052a059466f826ca1070cdc56fcfdd3c`.
Он сопоставлен с запросом `packet-000-client_to_server.bin`, SHA-256
`f8da26457097387c79451d8265a94f3884da6b43ee476c1309ba8c6d9cba6d9b`.

| Offset | Bytes | Наблюдаемое содержимое |
|---|---:|---|
| 0 | 2 | flags=0, little endian |
| 2 | 1 | reply element ID=255 |
| 3 | 4 | length=21, little endian; включает request ID |
| 7 | 4 | request ID соответствующего LoginRequest |
| 11 | 1 | status=1 |
| 12 | 16 | Два блока зашифрованной записи redirect |

После расшифровки: IPv4 `7f 00 00 01`, порт `4e 30` (20016, big endian),
два нулевых байта, четыре байта токена, четыре нулевых байта дополнения.
Назначение двух байтов между портом и токеном для других режимов UNKNOWN;
современный codec называет их salt, но это название не доказывает семантику 0.9.1.

VERIFIED: ранее неизвестное 16-байтовое поле LoginRequest пригодно как ключ
Blowfish данного ответа. Схема: шифрование каждого 8-байтового блока после XOR
с предыдущим **открытым** блоком; начальный блок XOR — нули; дополнение нулевое.
Клиент извлёк правильный адрес/токен, что подтверждено последующими реальными
пакетами. Это сильнее round-trip нашего кодера. Шифрование следующих каналов
этим же ключом пока UNKNOWN.

## Первый BaseApp request — VERIFIED bytes, ограниченная семантика

Доказательство: `native-02/packet-002-base_client_to_server.bin`, SHA-256
`ba5eaebe94e355e9649a2366d3f59bda458121b4231aa0ed77c2bf9dbaa66a10`.
Файл создан capture listener после ответа Login endpoint, без генерирования
клиентского пакета нашим кодом. Проверка токена — `redirect-verification.json`.

| Offset | Bytes | Наблюдаемое содержимое |
|---|---:|---|
| 0 | 2 | flags=1, HAS_REQUESTS |
| 2 | 1 | element ID=0 в контексте BaseApp |
| 3 | 2 | length=8, little endian |
| 5 | 4 | request ID, little endian |
| 9 | 2 | next request offset=0 |
| 11 | 4 | Точное совпадение с токеном LoginSuccess |
| 15 | 4 | Последовательно `00 00 00 00` … `05 00 00 00` |
| 19 | 2 | first request offset=2 |

Здесь нет modern четырёхбайтового prefix. Первый запрос содержит токен
открытым текстом. Это не утверждение об отсутствии шифрования последующего
BaseApp трафика. Число 0 — ID сообщения данного endpoint, не entity ID Account.

OBSERVED: в каждом запуске значения последних четырёх payload bytes при
чтении little endian — 0, 1, 2, 3, 4, 5. Первое сообщение использует тот же
source UDP port, что LoginRequest, последующие — другие ephemeral ports;
интервал около одной секунды. INFERRED: это счётчик попыток. Разрядность
счётчика и назначение трёх старших нулевых байтов UNKNOWN: наблюдение совместимо
и с u32, и с u8 плюс отдельные поля. Поведение за пределами этого окна NOT_RUN.

В закреплённом modern toolkit `app/base/element.rs:75` LoginKey описан как
Fixed(7), с u32 + u8 + u16. Наши bytes имеют Variable16-подобный заголовок и
payload 8. **Совпадение имени сообщения не разрешает применять modern layout.**
Запуск полного modern BaseApp decoder на этом corpus — NOT_RUN.

## Реализация и проверки

- `tools/wg_probe/src/redirect091.rs`: один loopback peer, один случайный
  handoff token на процесс, не более 64 datagrams и 60 секунд. Повтор запроса
  сохраняет токен. Второй session key/другой peer явно отвергаются. Это
  ограничение исследовательского стенда, не модель production-сессий.
- `login091.rs` сохраняет ключ только в памяти и проверяет точные измеренные
  тестовые credentials. Произвольный username с подходящей подстрокой больше
  не принимается. Полноценного хранения аккаунтов/паролей здесь нет.
- UDP receive buffer ограничен 65536 bytes, после чтения decoder отвергает
  datagram длиннее 1024. Так oversize не превращается в Windows WSAEMSGSIZE
  с аварийным завершением. Проверен UDP payload 65507 bytes.
- `client_probe.py` пишет второй endpoint в тот же capture/ledger и откатывает
  изменения в finally. `base_endpoint_received=PASS` означает получение байтов;
  их семантическую корреляцию отдельно проверяет `verify_redirect_capture.py`.
- Diagnostic personality реализует `onChangeEnvironments` как запись события.
  В native-01 отсутствие этого hook дало AttributeError в Python log; исправлено,
  в native-02 и P01 regression свежие части лога ошибок не содержат. Исторические
  строки исходного python.log не смешиваются с новым запуском.

| Проверка | Результат | Evidence внутри текущего run |
|---|---|---|
| Закреплённая offline сборка | PASS, 3 прежних предупреждения vendor | `build-final.log` |
| 4 Rust boundary tests | PASS | `rust-tests.log` |
| 20 Python tests, включая реальные ресурсы | PASS | `python-tests.log` |
| Native redirect + токен в BaseApp, два запуска | PASS | `native-01/redirect-verification.json`, `native-02/redirect-verification.json` |
| Первый отсутствующий diagnostic hook | FAIL, исправлено и перепроверено | `native-01/python-log-new.txt`; `native-02/log-check.json` |
| 34 offline проверки повреждений настоящего BaseApp corpus | PASS | `negative-01/results.json` |
| 17 live UDP controls/проверок backend | PASS | тот же файл + `backend.stdout.log` |
| Прежний P01 rejection, точный callback code 73 | PASS | `p01-regression/verification.json` |
| Полный откат обоих клиентских деревьев | PASS | `final-integrity/baseline-comparison.json` |
| Git exclusions / завершение собственных процессов | PASS | `git-safety.json`, `process-cleanup.json` |
| Полные V01/V02/V04 этапа P02 | NOT_RUN | Есть только узкие parser checks; 10 полноценных входов не выполнялись |
| Успешная сессия, Account, arena, два клиента | NOT_RUN | Не входят в эту карточку |

Среди UDP cases: пустой/усечённый/повреждённый/слишком длинный datagram,
неверный protocol/chain, повреждённый RSA, неверные username/password, повтор,
новый request ID с прежним токеном, второй ключ и закрытие peer. Мутанты
построены из настоящего corpus и явно отделены от двух реальных client runs.
Неответ на плохой пароль проверен в течение 250 ms; понятная пользователю
ошибка авторизации настоящим клиентом здесь NOT_RUN.

## Команды повторения

PowerShell из `D:\WoT_9.1_Server`. Использовать новый каталог, свободные
loopback ports 20014–20016 и отсутствие другого клиента: preflight проверяет
`wot_client_mutex` и отказывает до установки файлов, если он занят.

```powershell
. ./tools/rust_env.ps1
cargo build --locked --offline --manifest-path tools/wg_probe/Cargo.toml
cargo test --locked --offline --manifest-path tools/wg_probe/Cargo.toml
python -X utf8 -m unittest discover -s tests -v
$taskRun = 'local/evidence/p02-redirect-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
python -X utf8 tools/client_audit.py manifest --out "$taskRun/baseline"
python -X utf8 tools/client_probe.py run --out "$taskRun/native" --backend local/vendor/wg-toolkit-rs/target/debug/p01-wg-probe.exe --backend-profile legacy091-redirect
python -X utf8 tools/verify_redirect_capture.py --run "$taskRun/native"
python -X utf8 tools/check_redirect_probe.py --run "$taskRun/native" --out "$taskRun/negative"
python -X utf8 tools/client_probe.py run --out "$taskRun/p01-regression" --backend local/vendor/wg-toolkit-rs/target/debug/p01-wg-probe.exe --backend-profile legacy091
python -X utf8 tools/verify_native_capture.py --run "$taskRun/p01-regression"
python -X utf8 tools/client_audit.py manifest --out "$taskRun/after"
Get-FileHash "$taskRun/baseline/original-content-manifest.json","$taskRun/baseline/research-content-manifest.json","$taskRun/after/original-content-manifest.json","$taskRun/after/research-content-manifest.json"
```

Все четыре content hashes должны совпасть. Compiler/runtime prerequisites —
[REPRODUCE](REPRODUCE.md); для двух новых Python tools нужен cryptography 48.0.0.
Не запускать одновременно backend negative checks и native run: они используют
один порт 20015. Прямое присоединение к WG/«Ориону» не требуется и не выполнялось.
OS-wide firewall/egress capture не включались; такого доказательства отчёт
не заявляет. Game personality и штатный login host list не запускались.

## Откат и границы

Client patches автоматически сняты после всех трёх запусков. Полные manifests
обеих копий после запусков совпали с baseline и принятым P01. Для прерванного
будущего run после завершения именно его PID:

```powershell
python -X utf8 tools/client_probe.py restore --out "$taskRun/native"
```

Уже восстановленный run повторно restore не принимает. Для этой карточки
сохранены ledger, backup и postrun каждого запуска. EXE не патчился, mutex
не обходился, другой игровой процесс не завершался.

Проектный откат: сохранить последующие правки, затем восстановить только
изменённые файлы по `changed-files.json` из `project-before.zip`; новые файлы
убрать адресно. Локальный config восстанавливается из `project.local.before.json`.
Не распаковывать архив поверх будущих правок без сравнения; не удалять local
evidence или клиентские деревья массовой очисткой. Миграций БД и системных
изменений нет. Зависимости/бинарники остаются в ignored local.

UNKNOWN: ответ BaseApp и установление канала; значение оставшихся полей;
session/auth lifecycle, ACK/sequence/fragments, шифрование канала и wire IDs
сущностей. Происхождение дистрибутива независимо от его закреплённого хеша
по-прежнему UNKNOWN. Новых обязательных входных файлов от владельца нет.

**Единственный следующий рекомендуемый шаг:** отдельный эксперимент P02 —
ответить на измеренный BaseApp request, проверить реакцию настоящего клиента
и получить первое следующее сообщение канала. Формат ответа сначала доказать;
Account/ангар/арену не добавлять в эту карточку автоматически.
