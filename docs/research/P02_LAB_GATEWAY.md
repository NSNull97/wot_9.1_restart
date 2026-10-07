# P02: ограниченный native gateway и локальная сессия

2026-10-04, Asia/Yekaterinburg. Evidence run `20261004-p02-session-gateway`.
Основание: владелец разрешил идти последовательно до первого крупного
проверенного шага. [План](../plans/P02_session_gateway.md).

**Локальный transport/session рубеж PASS. Полный P02 — PARTIAL.**
Десять последовательных native входов/выходов прошли на одном живом gateway.
Все 14 сценариев итоговой серии, controls и полный client rollback проверены.
Это завершение текущего крупного шага; до P03/арены работа не продолжалась.

## Граница результата

Это минимальный **локальный transport/session gateway с одним тестовым
аккаунтом**. Настоящий EXE выполняет BigWorld.connect/disconnect, родной
Login/BaseApp обмен, ACK и обработку ошибок. Процесс шлюза живёт между
клиентскими запусками, владеет сессией и освобождает её состояние.

Используется обратимая исследовательская personality, а не штатный игровой
UI. Account entity, ангар, арена и общий игровой мир отсутствуют. Callback
LOGGED_ON не подменяется. Нет публичной регистрации/постоянных аккаунтов,
экономики или интеграции с независимо разрабатываемым web/.

## Источники и неизменность среды

Проверенный клиент `v.0.9.1 #717`, RU; EXE SHA-256:
`86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed`.
Исходный content manifest обеих копий:
`74c37c18e9ac7e30196c134076dacf6f2a8bf3897f7def73905d09feb3647797`.
3469 файлов / 14 680 626 869 байт в каждой. Издательская аутентичность UNKNOWN.

Далее `E` — `local/evidence/20261004-p02-session-gateway/`.
До изменения кода сохранены 84 собственных файла (`project-before.zip/json`),
local config, Git status и свободный mutex. `changes-before.json`: внешних
правок own source относительно предыдущего snapshot нет. web/ исключён.
`baseline-verified.json` подтверждает хеши до первого нового запуска.
Все 22 client runs восстановлены (`client-restores.json`). После них полные
manifests обеих копий совпали с baseline:
`final-integrity/baseline-comparison.json`. Оригинал только читался.

## Измеренный gap и восстановление доставки

VERIFIED, `gap-01/capture.json`, `clear-observation.json`,
`gateway-verification.json`: сервер намеренно отправил sequence **1, 0, 1**.
Пропуск 0 в этом первом опыте был расписанием диагностики, не работой retry.

| Событие | Clear bytes клиента | Наблюдение |
|---|---|---|
| Получен 1 при отсутствующем 0 | `4c0401000000010000000100000000` | cumulative=0, selective ACK=[1] |
| Позднее получен 0 | `48040200000002000000` | cumulative=2 |
| Дубликат 1 | `48040300000002000000` | cumulative остаётся 2 |

VERIFIED: flags 0x044c, после sequence находятся u32 selective ACK, один байт
count=1 и u32 cumulative ACK. Это дополнение к измеренному 0x0448. Count>1
реальным клиентом здесь не порождался: ограниченная обработка до 16 entries
проверяется отдельно и не объявляется подтверждённым native corpus.

Далее `transport091.rs` реализует очередь до 8 неподтверждённых packets,
таймер 700 ms и максимум 5 отправок одного sequence. Эти значения — наши
лабораторные ограничения, не исторические константы клиента. Подтверждение
ещё не отправленного номера отвергается до изменения состояния. Старый ACK
не уменьшает cumulative; подтверждённый packet удаляется из очереди.

В gateway-опыте `drop-server-first` proxy **записал и действительно отбросил**
первую отправку seq0 (`forwarded_copies=0`). Клиент увидел seq1, подтвердил его
выборочно; таймер gateway повторил seq0, после чего native ACK продвинулся.
Это автоматический повтор после контролируемой потери настоящего трафика.
Wire evidence и backend event `attempt=2` сверяются независимо.

## Авторизация, сессия и выход

VERIFIED: разбор login отделён от решения об авторизации. Принимается только
точная собственная disposable lab identity и тестовый пароль; это не общий
API авторизации. Digest сравнивается с 16 байтами, измеренными в native login
проверенной копии. Этот digest не объявляется криптографическим manifest
всех ресурсов или защитой от модифицированного клиента.

Подтверждены реальные клиентские отказы:

| Условие | Native status | Код | Evidence |
|---|---|---:|---|
| Неверный тестовый пароль | LOGIN_REJECTED_INVALID_PASSWORD | 67 | smoke-01/05-wrong-password |
| Сервер ожидает другой digest | LOGIN_REJECTED_BAD_DIGEST | 69 | digest-mismatch/01-normal |

Статическое основание: `pe-login-codes/pe-startup.json`, exact EXE,
VA 0x60d7fa/0x60d80f (INVALID_PASSWORD, 0x43),
VA 0x60d8bc/0x60d8d1 (BAD_DIGEST, 0x45). Runtime callback подтверждает код.
Digest mismatch создан в собственном server expectation; другой клиентский
билд не запускался. Повреждение реальных игровых ресурсов не имитировалось.

`gateway091.rs`: Pending → Active после первого валидного клиентского
сообщения → Closed. Один стабильный доменный lab account, последовательный
session ID, отдельные случайные handoff/token/key bindings. Повтор входного
login возвращает тот же handoff; дубликат первого frame не создаёт сессию.

VERIFIED для этого сценария: native BigWorld.disconnect порождает reliable
body `01 <token> 0b 00`, sequence=1. Gateway подтверждает следующий client
sequence=2 и освобождает состояние. При blackhole нет ложного clean logout:
клиент теряет соединение, очередь исчерпывает retry, gateway закрывает сессию
с явной причиной. Pending handshake отдельно имеет timeout 8 s.

Старые ключи закрытых сессий удерживаются в ограниченном списке (до 32,
120 s), повторный login с ними отвергается. Это ограниченная lab replay policy,
не завершённая защита публичного игрового сервиса.

## Проверки и ограничения

Промежуточная `smoke-01`: шесть сценариев PASS на одном gateway PID 21776;
четыре нормальных закрытия, отказ пароля без allocation и blackhole с
`retry_exhausted`. Сессий одновременно больше одной не создавалось.

Финальная серия `acceptance` прошла на одном PID **87048**:

- 01: неверный пароль — отказ, allocation отсутствует.
- 02–11: **10 последовательных успешных входов/выходов**; session IDs 1–10.
  Внутри серии: потеря первого server packet, потеря ACK и дубликат первого
  client packet. Все сессии закрылись по native disconnect.
- 12: повторный неверный пароль — снова без allocation.
- 13: blackhole — session 11 закрыта по retry_exhausted.
- 14: восстановление — новый успешный вход/выход, session 12.

Итоговый ledger пуст: active=null, все очереди удалены при закрытии; один
gateway PID на всю серию. Это проверка bounded state cleanup, не RSS soak.

| Проверка | Результат | Evidence в E |
|---|---|---|
| Gap: selective ACK и поздняя доставка | PASS | gap-01/gateway-verification.json |
| 14 финальных сценариев, 10 успешных циклов подряд | PASS | acceptance/gateway-verification.json, local-gate.json |
| Несовпадение digest, реальный callback | PASS | digest-mismatch/gateway-verification.json |
| 33 corpus-derived / собственных UDP controls | PASS | controls-02/results.json |
| 35 checks предыдущего server-first профиля | PASS | regression-server-first/results.json |
| Rust tests / Python tests | PASS, 19 / 20 | rust-tests-final.log, python-tests.log |
| Offline build | PASS; 3 прежних vendor warnings и 1 unused test-helper warning | build-final.log |
| Client rollback и полный manifest | PASS, 22 runs | client-restores.json, final-integrity/baseline-comparison.json |
| Первая попытка новых UDP controls | FAIL тестового инструмента, сохранён | controls-01/results.json, harness-error.json в том же каталоге |
| Account, штатный UI, арена, generic fragments, публичный сервис | NOT_RUN | Вне принятого локального рубежа |

Исходный controls-01 остановился до отправки мутанта из-за TypeError:
cryptography RSA encrypt требовал bytes, инструмент передал bytearray.
После исправления только harness все 33 controls выполнены в controls-02.
Это не был отказ gateway; исходный FAIL не переписан.

Не приравнивать `runner_status` к compatibility PASS: runner проверяет запуск
и откат, `verify_gateway_capture.py` проверяет реальные bytes, hashes,
доставку/потерю, callbacks и связанный журнал сессий.

Явные пределы реализации:

- Только числовые loopback endpoints 127.0.0.1:20014–20017; нет опытов с WG,
  «Орионом» или другими операторами. Системный egress capture NOT_RUN.
- Одна lab identity и одна pending/active session. Это не многопользовательский
  gateway и не интеграция с сайтом.
- До 32 server sequences за сессию, без wraparound; до 8 pending; максимальный
  datagram 1024 B, parse depth 8, общий budget 32 вложенных frames, 16 ACKs.
- Служебные reliable server packets пустые. Из прикладных client сообщений
  разрешены только измеренные начало и disconnect. Остальные не dispatch-ятся.
- Фрагментация, произвольные bundles/entity RPC, общий приём вне порядка,
  долгоживущие сессии, перезапуск с persistence и игровой UI **NOT_RUN**.
- Gateway ограничен 900 s/8192 входящими datagrams, до 128 datagrams/s.
  Это лабораторные бюджеты, не доказанная эксплуатационная производительность.
- Синтетические UDP cases отделены от native-client evidence. Heap/RSS soak,
  несколько игроков, Windows/Linux cross-platform и публичная безопасность NOT_RUN.

## Повторение и откат

PowerShell из `D:\WoT_9.1_Server`, другая копия игры закрыта:

```powershell
. ./tools/rust_env.ps1
cargo build --locked --offline --manifest-path tools/wg_probe/Cargo.toml
cargo test --locked --offline --manifest-path tools/wg_probe/Cargo.toml
python -X utf8 -m unittest discover -s tests -v
$taskRun = 'local/evidence/p02-gateway-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
python -X utf8 tools/client_audit.py manifest --out "$taskRun/baseline"
python -X utf8 tools/client_probe.py run --out "$taskRun/gap" --backend local/vendor/wg-toolkit-rs/target/debug/p01-wg-probe.exe --backend-profile legacy091-gap --probe-seconds 20
python -X utf8 tools/verify_gateway_capture.py --run "$taskRun/gap" --case gap
python -X utf8 tools/gateway_suite.py --source "$taskRun/gap" --out "$taskRun/acceptance" --cases wrong-password,normal,drop-server-first,drop-client-ack,duplicate-client-first,normal,normal,normal,normal,normal,normal,wrong-password,blackhole,normal
python -X utf8 tools/verify_gateway_capture.py --suite "$taskRun/acceptance"
python -X utf8 tools/gateway_suite.py --source "$taskRun/gap" --out "$taskRun/digest" --cases normal --digest-mismatch
python -X utf8 tools/verify_gateway_capture.py --suite "$taskRun/digest"
python -X utf8 tools/check_gateway_probe.py --source "$taskRun/acceptance/02-normal" --out "$taskRun/controls"
python -X utf8 tools/client_audit.py manifest --out "$taskRun/after"
Get-FileHash "$taskRun/baseline/original-content-manifest.json","$taskRun/baseline/research-content-manifest.json","$taskRun/after/original-content-manifest.json","$taskRun/after/research-content-manifest.json"
```

Четыре content hashes должны совпасть. Все native/UDP commands выполняются
последовательно, порты общие. Существующий output повторно не использовать.

Suite владеет только своим gateway PID. Каждый client run имеет отдельный
ledger, исходные хеши, backups, postrun files и автоматический restore.
При прерывании остановить только PIDs своего run/suite, затем:
`python -X utf8 tools/client_probe.py restore --out <конкретный-client-run>`.
Повторный restore завершённого run намеренно запрещён.

Код откатывать адресно из `E/project-before.zip` по `changed-files.json`,
сохраняя последующие пользовательские правки. Локальная конфигурация — из
`project.local.before.json`. web/ и local/web/ не входят в этот откат.

Следующий шаг после принятия локального рубежа — исследовать и подтвердить
первое native создание минимальной Account-сущности, не подменяя её mock.
Переход к P03/арене этим отчётом не закрывается.
