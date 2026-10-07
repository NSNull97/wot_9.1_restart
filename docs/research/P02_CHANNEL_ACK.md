# P02: ACK первого reliable frame и ограниченный keepalive

Дата: 2026-10-04, Asia/Yekaterinburg. Run: `20261004-p02-channel-ack`.
**Карточка PASS. Общий надёжный канал и полный gate P02 NOT_RUN.**
Основание — «поехали» владельца после [BaseApp reply](P02_BASEAPP_REPLY.md).
Граница работы — [план](../plans/P02_channel_ack.md).

## Что установлено

VERIFIED для этого клиента: зашифрованный ACK с clear bytes
`08 04 01 00 00 00` прекращает повтор первого reliable packet с sequence=0.
Повторение такого пустого channel packet раз в секунду сохраняет соединение
дольше установленного inactivity timeout 5 секунд. Два завершённых запуска
сохранили LOGGED_ON до диагностического отключения через **16.5853 и 21.6106 s**.
Сервер не создавал Account, сущности или арену; игровых команд здесь нет.

Контроль различает подтверждение и keepalive: те же flags, шифрование и
период, но ACK=0, сохраняют соединение, **не прекращая повтор sequence=0**.
Без server channel packets callback 6/NOT_SET приходит через 5.2258 s,
раньше `quit_requested`. Предыдущее предположение о timeout теперь подкреплено
временами и controls, а не одним неразмеченным callback.

`E` далее — `local/evidence/20261004-p02-channel-ack/`.

## Исходное состояние и доказательства формата

VERIFIED: EXE SHA-256
`86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed`,
клиент v.0.9.1 #717/RU, встроенный Python 2.7.3/32-bit. До изменений 72
собственных файла сохранены в `project-before.zip` + `project-before.json`;
config отдельно в `project.local.before.json`. Внешних изменений со времени
предыдущего снимка нет (`changes-since-prior-card.json`). `web/` исключён.
Mutex свободен (`instance-before.json`); чужие процессы не завершались.

Обе копии до/после: 3469 файлов, 14 680 626 869 байт, content hash
`74c37c18e9ac7e30196c134076dacf6f2a8bf3897f7def73905d09feb3647797`.
`baseline-verified.json` и `final-integrity/baseline-comparison.json` PASS.
Оригинал только читался. Все пять запусков имеют backup/ledger/restore.

Проверяемые локальные основания:

- `prior-clear-packets.json` — независимое расшифрование прежнего corpus.
  В первом clear frame на offsets 8 и 12 находятся два нулевых u32; при
  повторных посылках меняется кандидат sequence и появляются вложенные bytes.
- Pinned toolkit `5b879f0b960ccb4a3b799ede952256e253ef74cb`,
  `wg-toolkit/src/net/packet.rs:615` и `proto.rs` Channel::prepare — исходная
  гипотеза для footer order/ACK. Современный PacketSocket не использовался.
- `pe-channel-strings.json`: строка Channel::handleCumulativeAck по VA
  `0x19c6bc8`, reference `0xee0cc6`. Функция начинается в `0xee0c70`,
  ограничивает значения маской `0x0fffffff` и перебирает подтверждаемые seq
  до переданной границы. Это статическое свидетельство, не wraparound test.
- `pe-ack-receiver-confirmed/pe-startup.json`: дизассемблирование от prologue
  `0xee9590` достигает `0xee979a` (`shr eax, 0xa`), проверки бита и вызова
  `0xee0c70` в `0xee97c2`. Перед этим извлекается u32 через `0xeeab50`.
  Это подтверждает связь бита 0x0400 с cumulative ACK именно в этом EXE.
- Раннее окно `pe-ack-receiver/pe-startup.json` от `0xee9740` попало внутрь
  инструкции. Оно сохранено, **не используется как доказательство**;
  восстановленное выравнивание отражено также в `pe-ack-receiver-aligned.json`.

## Измеренный wire contract

После установленного BaseApp handshake первый client packet имеет clear:

| Offset | Размер | Значение |
|---|---:|---|
| 0 | 2 | flags `58 04` |
| 2 | 1 | element 1 |
| 3 | 4 | Token из BaseApp reply |
| 7 | 1 | Application byte `09`; здесь не dispatch-ится |
| 8 | 4 | sequence=0, u32 LE |
| 12 | 4 | client cumulative ACK=0, u32 LE |

Ответ сервера: clear length=6, flags `08 04` (0x0408), затем u32 LE **1**.
Нет application payload, sequence сервера, отдельного token в открытом body
или modern prefix. Ранее проверенный Blowfish/filter/footer превращает это
в **16-byte datagram** с тем же session cipher key. ACK=1 означает конец
подтверждённого диапазона перед sequence 1 в данном начальном случае.
Обобщение на окна, wraparound, fragments и пропуски не реализовано/NOT_RUN.

В controls flags 0x045a содержат вложенные повторы: длина последнего вложенного
пакета хранится как ones' complement signed i16. Например `f3 ff` → 12 bytes,
`eb ff` → 20 bytes. Ограниченный parser читает их с конца, затем cumulative
ACK и sequence; это позволяет посчитать повторные вхождения sequence=0.
VERIFIED — согласованность с этими реальными frames; общий legacy parser
всех flags/footers пока UNKNOWN. Флаг 0x0002 и подпись piggyback согласуются
с pinned source и corpus. Runtime dispatch вложенных сообщений отсутствует.

`native-ack-03/packet-005-base_server_to_client.bin`, первый ACK, SHA-256:
`ed2253432bdfc94e71fe3573d90933b77556ca8df16a5e64febd12fbe89c5b9f`.
Окончательный второй подтверждённый run и все packet hashes доступны через
`native-ack-03/channel-verification.json` и `capture.json`.

## Реальные эксперименты и ошибка первого сборщика

Все адреса числовые loopback, порты 20014–20017. `probe_seconds` отсчитывается
от diagnostic init, время удержания — от реального LOGGED_ON до callback
отключения или `quit_requested`. Callback timer может исполняться позднее
заданного срока, поэтому ниже фактически измеренные времена.

| Run | Профиль/таймер | Удержание | Вхождения seq=0 | Итог |
|---|---|---:|---:|---|
| control-none | прежний BaseApp, 20 s | 5.2258 s; ранний NOT_SET | 3 | PASS отрицательного контроля |
| native-ack-01 | ACK=1, 20 s | 16.5904 s до quit | 1 | **FAIL сборщика**, сохранён |
| control-stale | ACK=0, 20 s | 16.5873 s до quit | 9 | PASS различающего контроля |
| native-ack-02 | ACK=1, 20 s | 16.5853 s до quit | 1 | PASS; EXE exit 0 |
| native-ack-03 | ACK=1, 25 s | 21.6106 s до quit | 1 | PASS; EXE exit 0 |

`native-ack-01` получил Windows UDP ConnectionResetError/10054 при завершении:
capture сохранился, но итоговый client exit не записался. Runtime показывает
quit/fini, однако run **не переименован в PASS**. Старый verifier первоначально
упал на отсутствующем client_exit; теперь сохраняет корректный FAIL с причиной.
Исследовательская копия восстановлена и в этом неудачном run.

Исправление runner: только известный UDP 10054 регистрируется отдельным
`udp_reset_events` с локальным портом/временем; после 16 событий — явная ошибка.
Остальные исключения пробрасываются. Клиентский exit 0, отсутствие таймаута,
отсутствие runner error и rollback обязательны для PASS. В `native-ack-03`
такое событие снова реально встретилось на порту 20016, штатный выход записан.
Отдельная проверка воспроизводит ICMP/10054 на собственном закрытом UDP-порту.

VERIFIED: отсутствие ACK даёт раннее отключение; ACK=0 сохраняет активность
и повторы, ACK=1 сохраняет активность без повторов первого packet.
INFERRED: раннее отключение обусловлено inactivity timer; его внутренний
native call stack не снимался. Время и внешнее поведение соответствуют 5 s.

## Реализация и пределы

- `channel091.rs`: отдельные profiles `legacy091-channel-ack` и
  `legacy091-channel-stale`; прежний `legacy091-baseapp` по умолчанию без ACK.
  ACK включается только после exact measured first frame с проверенным token.
  Не чаще раза в секунду, максимум 32 отправки; дубликат не сбрасывает лимиты.
  Подтверждается только sequence 0, нет generic sequence-window implementation.
- `baseapp091.rs`: сохранены crypto/peer/token/size checks; добавлено включение
  и отправка отдельного ACK state. Прежний loop bounded 60 s, порог 128 входящих
  datagrams между парами sockets (теоретически до 129). Общий server не создан.
- `client_patch/p01_probe.py`: timestamp каждого события и timer 9…30 s,
  по умолчанию прежние 9 s; inactivityTimeout остаётся 5. Никакой подмены
  BigWorld.connect/callback и клиентских transport функций.
- `verify_channel_capture.py`: независимые crypto/correlation, проверки
  timings/exit/restore, ограниченный разбор footer/piggyback (1024 B,
  depth ≤16, nodes ≤64, не более 16 piggybacks на уровень).
- `check_channel_probe.py`: corpus-derived boundaries и свои UDP controls.
  Fixtures явно отделены от доказательств настоящего клиента.

| Проверка | Результат | Evidence в E |
|---|---|---|
| Offline build | PASS; прежние 3 vendor warnings | build.log |
| Rust tests | PASS, 11 (8 прежних + 3 новых) | rust-tests.log |
| Python resource/parser tests | PASS, 20 | python-tests.log |
| Новые parser/UDP/Windows controls | PASS, 34 | checks-01/results.json |
| Прежний BaseApp verifier и негативные проверки | PASS, 75 | control-none/baseapp-verification.json, regression-baseapp/results.json |
| Реальные ACK controls и два завершённых положительных runs | PASS | experiment-matrix.json, run/channel-verification.json |
| Первый положительный run до исправления capture | FAIL | native-ack-01/channel-verification.json |
| Свежие client Python logs всех пяти runs | PASS | run/log-check.json |
| Client restore / manifests / Git / processes | PASS | final-integrity/baseline-comparison.json, git-safety.json, process-cleanup.json |
| Общее удержание под нагрузкой, потери/перестановка, server reliable packets, два клиента | NOT_RUN | Вне карточки |
| Account/арена/полная приёмка P02 | NOT_RUN | Вне карточки |

## Точные команды повторения

PowerShell из `D:\WoT_9.1_Server`, другая копия игры закрыта, порты свободны.
Новые каталоги для каждого опыта; backend и client запускаются runner-ом.

```powershell
. ./tools/rust_env.ps1
cargo build --locked --offline --manifest-path tools/wg_probe/Cargo.toml
cargo test --locked --offline --manifest-path tools/wg_probe/Cargo.toml
python -X utf8 -m unittest discover -s tests -v
$taskRun = 'local/evidence/p02-ack-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
python -X utf8 tools/client_audit.py manifest --out "$taskRun/baseline"
python -X utf8 tools/client_probe.py run --out "$taskRun/none" --backend local/vendor/wg-toolkit-rs/target/debug/p01-wg-probe.exe --backend-profile legacy091-baseapp --probe-seconds 20
python -X utf8 tools/verify_channel_capture.py --run "$taskRun/none" --expect none
python -X utf8 tools/client_probe.py run --out "$taskRun/stale" --backend local/vendor/wg-toolkit-rs/target/debug/p01-wg-probe.exe --backend-profile legacy091-channel-stale --probe-seconds 20
python -X utf8 tools/verify_channel_capture.py --run "$taskRun/stale" --expect stale
python -X utf8 tools/client_probe.py run --out "$taskRun/ack" --backend local/vendor/wg-toolkit-rs/target/debug/p01-wg-probe.exe --backend-profile legacy091-channel-ack --probe-seconds 25
python -X utf8 tools/verify_channel_capture.py --run "$taskRun/ack" --expect ack
python -X utf8 tools/check_channel_probe.py --run "$taskRun/ack" --control "$taskRun/stale" --out "$taskRun/checks"
python -X utf8 tools/verify_baseapp_capture.py --run "$taskRun/none"
python -X utf8 tools/check_baseapp_probe.py --run "$taskRun/none" --out "$taskRun/regression"
python -X utf8 tools/client_audit.py manifest --out "$taskRun/after"
Get-FileHash "$taskRun/baseline/original-content-manifest.json","$taskRun/baseline/research-content-manifest.json","$taskRun/after/original-content-manifest.json","$taskRun/after/research-content-manifest.json"
python -X utf8 tools/exe_startup_probe.py --out "$taskRun/pe" --va 0xee9590 --va 0xee0c70 --va 0xeeab50
```

Четыре content hashes должны совпасть. Версии/lock hashes/EXE probe hash —
`dependencies.json`, own source version — `code-manifest.json`. Новых
зависимостей нет; vendor/lockfiles не изменены. Публичные endpoints не открыты.

## Откат, неизвестное и следующий шаг

Client patches уже откатились. Для прерванного будущего запуска сначала
завершить только его процессы из `processes.json`, затем:
`python -X utf8 tools/client_probe.py restore --out "$taskRun/ack"`.
Повторный restore завершённого run откажет. Исходные hashes/backups остаются
в его ledger/backup, послеопытные файлы — postrun.

Откат own project адресно по `changed-files.json` из `project-before.zip`;
локальный config — из `project.local.before.json`, сохранив последующие правки.
`web/` и `local/web/` не затрагивать. Git commits пока нет; source snapshots
и manifests фиксируют результат. Клиентские данные/ключи/логи в ignored local.

UNKNOWN/NOT_RUN: общий reliable lifecycle в обе стороны, ACK серверного
packet, окна/потери/перестановки/wraparound/fragmentation, Account и арена.
Назначение application bytes `09`, `0b 00` пока не используется как API.
Новых обязательных входных файлов от владельца нет. Исследования ограничены
числовыми loopback endpoints и тестовыми credentials; системный egress
capture не выполнялся. Авторитетный игровой мир ещё не реализован.

**Единственный следующий проверяемый шаг:** отправить первый надёжный packet
сервера с собственным sequence и подтвердить его получение настоящим ACK
клиента. Это отдельная карточка; Account и арена автоматически не начинаются.
