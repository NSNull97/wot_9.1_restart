# Evidence index — первый reliable packet сервера

Run: local/evidence/20261004-p02-server-reliable/.
[Отчёт и ограничения](../research/P02_SERVER_RELIABLE.md).

| Доказательство | Путь |
|---|---|
| Baseline и mutex | [baseline](../../local/evidence/20261004-p02-server-reliable/baseline-verified.json), [mutex](../../local/evidence/20261004-p02-server-reliable/instance-before.json) |
| Точное статическое основание прошлого шага | [reference/hash](../../local/evidence/20261004-p02-server-reliable/static-basis.json) |
| Опровергнутое предположение о token | [первые реальные bytes](../../local/evidence/20261004-p02-server-reliable/native-01/clear-observation.json), [FAIL observer](../../local/evidence/20261004-p02-server-reliable/native-01/server-reliable-verification.json) |
| Три corrected native runs | [run 02](../../local/evidence/20261004-p02-server-reliable/native-02/server-reliable-verification.json), [run 03](../../local/evidence/20261004-p02-server-reliable/native-03/server-reliable-verification.json), [final run 04](../../local/evidence/20261004-p02-server-reliable/native-04/server-reliable-verification.json) |
| Матрица с контрольным старым профилем | [matrix](../../local/evidence/20261004-p02-server-reliable/experiment-matrix-final.json) |
| Native runtime и capture | [runtime](../../local/evidence/20261004-p02-server-reliable/native-04/runtime.jsonl), [capture](../../local/evidence/20261004-p02-server-reliable/native-04/capture.json) |
| Новые 35 и прежние 34 controls | [new](../../local/evidence/20261004-p02-server-reliable/checks-final-routing/results.json), [regression](../../local/evidence/20261004-p02-server-reliable/regression-channel/results.json) |
| 13 Rust / 20 Python tests | [Rust](../../local/evidence/20261004-p02-server-reliable/rust-tests-final-routing.log), [Python](../../local/evidence/20261004-p02-server-reliable/python-tests.log) |
| Откат клиента и полная сверка | [restore](../../local/evidence/20261004-p02-server-reliable/native-04/restore.json), [integrity](../../local/evidence/20261004-p02-server-reliable/final-integrity-routing/baseline-comparison.json) |
| Git / завершение процессов | [Git](../../local/evidence/20261004-p02-server-reliable/git-safety-final.json), [cleanup](../../local/evidence/20261004-p02-server-reliable/process-cleanup-final.json) |
| Снимки own source и список изменений | [before](../../local/evidence/20261004-p02-server-reliable/project-before.zip), [after](../../local/evidence/20261004-p02-server-reliable/project-source-snapshot.zip), [changes](../../local/evidence/20261004-p02-server-reliable/changed-files.json) |
| Версия кода/зависимостей/evidence | [code](../../local/evidence/20261004-p02-server-reliable/code-manifest.json), [dependencies](../../local/evidence/20261004-p02-server-reliable/dependencies.json), [hash index](../../local/evidence/20261004-p02-server-reliable/evidence-files.json) |

Raw resources/captures/disposable keys/logs находятся только в ignored local.
web/ и local/web/ отдельно запрошенной сессии не включены в own source/rollback.
