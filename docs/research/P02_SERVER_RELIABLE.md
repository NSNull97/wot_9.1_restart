# P02: первый reliable packet сервера и настоящий ACK клиента

Дата: 2026-10-04, Asia/Yekaterinburg. Run: `20261004-p02-server-reliable`.
**Карточка PASS; общий надёжный канал и полный gate P02 NOT_RUN.**
Владелец попросил сообщить готовность и продолжить после
[P02_CHANNEL_ACK](P02_CHANNEL_ACK.md). Граница — [план](../plans/P02_server_reliable.md).

## Результат

VERIFIED на закреплённом клиенте: пустой зашифрованный server packet с
sequence=0 получает native transport ACK с cumulative=1. Один намеренный
дубликат того же server packet получает ещё один ACK с cumulative=1,
без ложного продвижения до 2. Три runs после исправления обработчика PASS.
Старый профиль без server reliable packet не вызывает эти transport-only ACKs.

Ни Account, ни игровые сообщения, ни арена не создавались. Отправляются
ровно две копии одного номера по расписанию. Автоматические повторы после
потери, несколько outstanding packets и production channel не реализованы.

`E` далее — `local/evidence/20261004-p02-server-reliable/`.

## База и воспроизводимость

VERIFIED: клиент v.0.9.1 #717/RU; EXE SHA-256
`86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed`.
Обе копии до/после: 3469 файлов / 14 680 626 869 байт; content hash
`74c37c18e9ac7e30196c134076dacf6f2a8bf3897f7def73905d09feb3647797`.
`baseline-verified.json` и `final-integrity-routing/baseline-comparison.json` PASS.
Оригинал только читался. Все пять client runs восстановлены по ledger.

До изменений сохранены 78 own files (`project-before.zip/json`) и config
(`project.local.before.json`). Внешних правок относительно предыдущего
own source snapshot нет; mutex свободен. `web/` и `local/web/` исключены из
работы, snapshot и отката. Конкретная версия нового кода — `code-manifest.json`;
hashes compiler/binary/dependencies — `dependencies.json`. Новых зависимостей
нет, vendor commit `5b879f0b960ccb4a3b799ede952256e253ef74cb` и lockfiles прежние.

Основание гипотезы: ранее измеренный C→S footer и exact EXE cumulative ACK
handler, указанный с хешем в `static-basis.json`. Совпадение S→C layout
изначально было гипотезой; ниже она подтверждена самим клиентом. Современный
toolkit PacketSocket не используется как готовый legacy transport.

## Измеренные bytes и опровергнутое предположение

Server reliable packet после снятия ранее проверенного Blowfish footer:

| Offset | Размер | Значение |
|---|---:|---|
| 0 | 2 | flags `58 04` = 0x0458 |
| 2 | 4 | server sequence=0, u32 LE |
| 6 | 4 | ACK первого client reliable packet: cumulative=1 |

Clear length=10, wire length=16. Application payload отсутствует.
Первый packet отправляется через 2 s после проверенного первого client
frame, его byte-identical duplicate — через 5 s от того же события.
Это намеренный диагностический дубликат, а не срабатывание retry timeout.

Ответы настоящего клиента также clear=10 / wire=16:

| Ответ | Clear bytes |
|---|---|
| На первый server sequence=0 | `48 04 01 00 00 00 01 00 00 00` |
| На его дубликат | `48 04 02 00 00 00 01 00 00 00` |

VERIFIED: flags 0x0448, поле sequence у ACK-пакетов 1 и 2, cumulative ACK
в обоих случаях **1**. В flags нет бита 0x0010, присутствующего у reliable
packet. Это пустые transport-only frames, без application element ID/token.
Значения ACK packet sequence 1/2 не объявляются общим правилом счётчика.
Связь reliable/unreliable numbering, wraparound и дальнейшие номера UNKNOWN.

Изначальное предположение «в каждом client channel packet есть ID1 + token»
**опровергнуто**. `native-01` реально получил оба ответа, но backend отверг
их старой проверкой прикладного префикса. `outcome.json` подтверждает только
прежний handshake/capture; независимый `server-reliable-verification.json`
правильно ставит **FAIL**: wire correlation PASS, backend feedback FAIL.
Исходный run не переписан и не представлен полным успехом.

Исправление узкое: transport-only ACK разрешён только в новом профиле,
после подтверждённого first-token handshake и фактической отправки server
packet. Peer и cipher key уже закреплены на BaseApp handshake. Exact length,
flags, cumulative=1 и наблюдаемые счётчики проверяются отдельно. Проверка
прикладного token для остальных frames сохранена. Это не заявление о
production-криптографической защищённости legacy обмена.

При финальном review transport-only header перенесён перед проверкой
application token: байты ACK-счётчика могли случайно совпасть с token и
попасть в ветку unparsed remainder. Эта маршрутизация повторно проверена
настоящим клиентом в native-04 и всеми 35 новыми controls.

## Реальные запуски

Все адреса — числовые loopback 127.0.0.1, порты 20014–20017, отдельные
disposable credentials/keys. Системный egress capture не выполнялся.
Personality исходник в этой карточке не изменён; используется прежний
native BigWorld.connect, elapsed timestamps и диагностический quit.

| Run | Наблюдение | Удержание после LOGGED_ON | Итог |
|---|---|---:|---|
| native-01 | Клиент ACK-нул обе копии seq0; backend отверг новый формат | 16.5923 s | FAIL observer; corpus сохранён |
| native-02 | Два transport ACK распознаны, cumulative1/1 | 16.5836 s | PASS |
| control-ack-only | Прежний keepalive; server seq отсутствует; transport-only ACK отсутствует | 16.5826 s | PASS контроля/регрессии |
| native-03 | Повтор после исправления формата, ACK1/1 | 21.6194 s | PASS |
| native-04 | Финальный код с явным приоритетом transport ACK, ACK1/1 | 16.5861 s | PASS |

Во всех runs native EXE exit=0, timeout=false, client rollback PASS,
свежие Python logs без Traceback/AttributeError/ValueError. Записанные Windows
UDP 10054 на закрытом порту не скрываются и не выданы за native disconnect;
их обработка проверена предыдущей карточкой и повторной регрессией.

Главные hashes `native-02`:

| Файл | SHA-256 |
|---|---|
| packet-007-base_server_to_client.bin (и identical packet-012) | `d82d1adc7bb1af70dff2a72d0aa291bc6d9338a3a880a612c5db2bd5af3c9bb9` |
| packet-009-base_client_to_server.bin | `71cc688f65827a3eb89f2c05c60a887c3bf22ddc9390800730e030293c671c7f` |
| packet-014-base_client_to_server.bin | `7ce39d346611324b9633ee9f064e2fddd8b10ba9f21d16dd32e2d622b93fc4fd` |

Каждый ACK записан после соответствующей отправки; первый ACK — до дубликата.
Полная матрица/времена/пакеты: `experiment-matrix-final.json`, run/capture.json и
run/server-reliable-verification.json. Это проверка реального клиента,
не round-trip собственного codec.

## Код, тесты и пределы

`reliable091.rs` содержит только state одного server sequence и двух
контролируемых отправок. `baseapp091.rs` подключает его исключительно для
`legacy091-server-reliable`; прежние профили сохранены. `channel091.rs`
сохраняет bounded keepalive (≤32 sends, ≥1 s между ними). Общие ограничения
backend прежние: 60 s, до 129 принятых datagrams, payload ≤1024 B.

`verify_channel_capture.py` расширен измеренным 0x0448 и отдельной проверкой
transport-only ACK. `verify_server_reliable.py` требует native bytes, hashes,
correlation/order, распознавание backend, runtime, exit и restore.
`check_server_reliable.py` отделяет corpus-derived mutants и собственный
UDP peer от настоящего client evidence.

При упаковке snapshot у `client_probe.py` восстановлены исходные LF окончания
строк после добавления профиля. AST до/после совпадает, syntax check PASS;
native-04 использовал семантически тот же исходник. Хеши обеих версий и
проверка: `line-ending-check.json`.

| Проверка | Результат | Evidence в E |
|---|---|---|
| Offline build | PASS; 3 прежних vendor warnings | build-final-routing.log |
| Rust tests | PASS, 13 | rust-tests-final-routing.log |
| Python resource/parser tests | PASS, 20 | python-tests.log |
| Новые parser/corpus/UDP controls | PASS, 35 (23 offline + 12 UDP), повтор на финальном коде | checks-final-routing/results.json |
| Прежние ACK controls | PASS, 34 | regression-channel/results.json |
| Три corrected real runs и native control | PASS | experiment-matrix-final.json |
| Первый observer до исправления предположения | FAIL, сохранён | native-01/server-reliable-verification.json |
| Client restore/manifests, Git и cleanup | PASS | final-integrity-routing/baseline-comparison.json, git-safety-final.json, process-cleanup-final.json |
| Loss/reorder, несколько outstanding packets, общий канал, Account/арена/full P02 | NOT_RUN | Вне этой карточки |

Negative controls включают ACK до первого token frame/до server send,
неправильный token, неверный cipher key, усечения, чужой peer, ACK за ещё
не отправленный номер, преждевременный счётчик второго ACK и дубликат feedback.
Мутанты не считаются native compatibility proof.

## Команды повторения и откат

PowerShell из `D:\WoT_9.1_Server`; другая копия игры закрыта, порты свободны.

```powershell
. ./tools/rust_env.ps1
cargo build --locked --offline --manifest-path tools/wg_probe/Cargo.toml
cargo test --locked --offline --manifest-path tools/wg_probe/Cargo.toml
python -X utf8 -m unittest discover -s tests -v
$taskRun = 'local/evidence/p02-server-seq-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
python -X utf8 tools/client_audit.py manifest --out "$taskRun/baseline"
python -X utf8 tools/client_probe.py run --out "$taskRun/native" --backend local/vendor/wg-toolkit-rs/target/debug/p01-wg-probe.exe --backend-profile legacy091-server-reliable --probe-seconds 25
python -X utf8 tools/verify_server_reliable.py --run "$taskRun/native"
python -X utf8 tools/check_server_reliable.py --run "$taskRun/native" --out "$taskRun/checks"
python -X utf8 tools/client_probe.py run --out "$taskRun/control" --backend local/vendor/wg-toolkit-rs/target/debug/p01-wg-probe.exe --backend-profile legacy091-channel-ack --probe-seconds 20
python -X utf8 tools/verify_channel_capture.py --run "$taskRun/control" --expect ack
python -X utf8 tools/check_channel_probe.py --run "$taskRun/control" --control local/evidence/20261004-p02-channel-ack/control-stale --out "$taskRun/regression"
python -X utf8 tools/client_audit.py manifest --out "$taskRun/after"
Get-FileHash "$taskRun/baseline/original-content-manifest.json","$taskRun/baseline/research-content-manifest.json","$taskRun/after/original-content-manifest.json","$taskRun/after/research-content-manifest.json"
```

Все четыре content hashes должны совпасть. Старый stale corpus для regression
можно получить заново командами [предыдущей карточки](P02_CHANNEL_ACK.md).
Native runs/UDP controls выполняются последовательно, порты общие.

Client изменения уже откатились. Для прерванного будущего run завершить
только его процессы из processes.json и выполнить:
`python -X utf8 tools/client_probe.py restore --out "$taskRun/native"`.
Повторный restore завершённого run откажет. Ledger, исходные backups и
послеопытные файлы сохранены. Оригинальный EXE и mutex не изменялись.

Проектный откат адресно по changed-files.json из project-before.zip;
local config — project.local.before.json, с сохранением последующих правок.
Не трогать web/ и local/web/. Git commits пока нет; source snapshots/hashes
фиксируют код. Клиентские packets/resources/keys/logs остаются в ignored local.

Новых обязательных входных файлов от владельца нет. UNKNOWN: общие правила
нумерации и окна доставки, loss/reorder/fragmentation, жизненный цикл
Account и игровых сущностей. Намеренный дубликат не доказывает recovery потерь.

**Единственный следующий шаг:** две последовательные reliable server посылки
с контролируемым пропуском первой, повтором и проверкой продвижения cumulative
ACK настоящего клиента. Это отдельная карточка, без перехода к Account/арене.
