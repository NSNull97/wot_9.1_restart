# Evidence — локальный native gateway/session

Run: local/evidence/20261004-p02-session-gateway/.
[Отчёт с командами и ограничениями](../research/P02_LAB_GATEWAY.md).

| Что проверено | Доказательство |
|---|---|
| Исходная копия/проект | [baseline](../../local/evidence/20261004-p02-session-gateway/baseline-verified.json), [source before](../../local/evidence/20261004-p02-session-gateway/project-before.zip) |
| Реальный selective ACK при gap | [wire verifier](../../local/evidence/20261004-p02-session-gateway/gap-01/gateway-verification.json), [capture](../../local/evidence/20261004-p02-session-gateway/gap-01/capture.json) |
| 10 native cycles / 14 сценариев одного gateway | [local gate](../../local/evidence/20261004-p02-session-gateway/local-gate.json), [матрица/ledger](../../local/evidence/20261004-p02-session-gateway/acceptance/gateway-verification.json), [gateway log](../../local/evidence/20261004-p02-session-gateway/acceptance/gateway.stdout.log) |
| Автоматический retry после отброшенного packet | [native fault result](../../local/evidence/20261004-p02-session-gateway/acceptance/03-drop-server-first/gateway-verification.json) |
| Отказ неверного пароля | [native callback/absence of session](../../local/evidence/20261004-p02-session-gateway/acceptance/01-wrong-password/gateway-verification.json) |
| Digest mismatch | [native rejection](../../local/evidence/20261004-p02-session-gateway/digest-mismatch/gateway-verification.json), [EXE status mapping](../../local/evidence/20261004-p02-session-gateway/pe-login-codes/pe-startup.json) |
| Обрыв и последующий вход | [blackhole](../../local/evidence/20261004-p02-session-gateway/acceptance/13-blackhole/gateway-verification.json), [recovery](../../local/evidence/20261004-p02-session-gateway/acceptance/14-normal/gateway-verification.json) |
| 33 новых / 35 прежних controls | [new](../../local/evidence/20261004-p02-session-gateway/controls-02/results.json), [regression](../../local/evidence/20261004-p02-session-gateway/regression-server-first/results.json) |
| Сохранённый FAIL тестового harness | [results](../../local/evidence/20261004-p02-session-gateway/controls-01/results.json), [причина](../../local/evidence/20261004-p02-session-gateway/controls-01/harness-error.json) |
| 19 Rust / 20 Python tests | [Rust](../../local/evidence/20261004-p02-session-gateway/rust-tests-final.log), [Python](../../local/evidence/20261004-p02-session-gateway/python-tests.log) |
| Откат всех 22 запусков | [restore index](../../local/evidence/20261004-p02-session-gateway/client-restores.json), [полные manifests](../../local/evidence/20261004-p02-session-gateway/final-integrity/baseline-comparison.json) |
| Cleanup и Git isolation | [cleanup](../../local/evidence/20261004-p02-session-gateway/process-cleanup.json), [Git](../../local/evidence/20261004-p02-session-gateway/git-safety.json) |
| Точная версия кода | [changes](../../local/evidence/20261004-p02-session-gateway/changed-files.json), [diff](../../local/evidence/20261004-p02-session-gateway/project-diff.patch), [snapshot](../../local/evidence/20261004-p02-session-gateway/project-source-snapshot.zip), [code hashes](../../local/evidence/20261004-p02-session-gateway/code-manifest.json) |
| Зависимости и индекс доказательств | [dependencies](../../local/evidence/20261004-p02-session-gateway/dependencies.json), [evidence hashes](../../local/evidence/20261004-p02-session-gateway/evidence-files.json) |

Raw captures, client resources и disposable keys лежат только в ignored local/.
web/ и local/web/ исключены из этих source snapshots и отката.
