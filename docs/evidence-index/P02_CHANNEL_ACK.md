# Evidence index — ACK первого packet

Run: `local/evidence/20261004-p02-channel-ack/`.
Трактовка и ограничения: [отчёт](../research/P02_CHANNEL_ACK.md).

| Доказательство | Путь |
|---|---|
| Исходное состояние и mutex | [baseline](../../local/evidence/20261004-p02-channel-ack/baseline-verified.json), [mutex](../../local/evidence/20261004-p02-channel-ack/instance-before.json) |
| Статический путь ACK в EXE | [strings](../../local/evidence/20261004-p02-channel-ack/pe-channel-strings.json), [aligned receiver/handler](../../local/evidence/20261004-p02-channel-ack/pe-ack-receiver-confirmed/pe-startup.json) |
| Сопоставление пяти реальных runs | [matrix](../../local/evidence/20261004-p02-channel-ack/experiment-matrix.json) |
| Контроль без ACK | [verification](../../local/evidence/20261004-p02-channel-ack/control-none/channel-verification.json) |
| ACK=0: связь жива, seq0 повторяется | [verification](../../local/evidence/20261004-p02-channel-ack/control-stale/channel-verification.json) |
| Сохранённый FAIL первого capture | [verification](../../local/evidence/20261004-p02-channel-ack/native-ack-01/channel-verification.json) |
| Два положительных native runs после исправления | [run 02](../../local/evidence/20261004-p02-channel-ack/native-ack-02/channel-verification.json), [run 03](../../local/evidence/20261004-p02-channel-ack/native-ack-03/channel-verification.json) |
| Реальный timed runtime | [trace](../../local/evidence/20261004-p02-channel-ack/native-ack-03/runtime.jsonl) |
| Hashes/backup/restore | [ledger](../../local/evidence/20261004-p02-channel-ack/native-ack-03/patch-ledger.json), [restore](../../local/evidence/20261004-p02-channel-ack/native-ack-03/restore.json) |
| Новые 34 проверки | [results](../../local/evidence/20261004-p02-channel-ack/checks-01/results.json) |
| Регрессия 75 corpus/backend checks | [results](../../local/evidence/20261004-p02-channel-ack/regression-baseapp/results.json) |
| 11 Rust / 20 Python tests | [Rust](../../local/evidence/20261004-p02-channel-ack/rust-tests.log), [Python](../../local/evidence/20261004-p02-channel-ack/python-tests.log) |
| Полная сверка клиентов / cleanup / Git | [integrity](../../local/evidence/20261004-p02-channel-ack/final-integrity/baseline-comparison.json), [cleanup](../../local/evidence/20261004-p02-channel-ack/process-cleanup.json), [Git](../../local/evidence/20261004-p02-channel-ack/git-safety.json) |
| Проект до / после / изменения | [before](../../local/evidence/20261004-p02-channel-ack/project-before.zip), [after](../../local/evidence/20261004-p02-channel-ack/project-source-snapshot.zip), [changes](../../local/evidence/20261004-p02-channel-ack/changed-files.json) |
| Версия кода / зависимости / хеши evidence | [code](../../local/evidence/20261004-p02-channel-ack/code-manifest.json), [dependencies](../../local/evidence/20261004-p02-channel-ack/dependencies.json), [index](../../local/evidence/20261004-p02-channel-ack/evidence-files.json) |

Клиентские ресурсы, captures, keys, decoded bytes и logs остаются в ignored
local. Source snapshot исключает `web/` отдельно запрошенной параллельной
сессии. Общий канал/Account/arena/full P02 gate — NOT_RUN.
