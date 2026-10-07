# Evidence index — P02 LoginSuccess → BaseApp

Run: `local/evidence/20261002-p02-login-redirect/`.
Client: `v.0.9.1 #717`; canonical content SHA-256:
`74c37c18e9ac7e30196c134076dacf6f2a8bf3897f7def73905d09feb3647797`.
Полная трактовка: [отчёт](../research/P02_LOGIN_REDIRECT.md).

| Доказательство | Путь |
|---|---|
| Baseline до изменений, сравнение с P01 | [baseline-verified.json](../../local/evidence/20261002-p02-login-redirect/baseline-verified.json) |
| Собственные файлы до этой карточки | [project-before.json](../../local/evidence/20261002-p02-login-redirect/project-before.json), [snapshot](../../local/evidence/20261002-p02-login-redirect/project-before.zip) |
| Первое реальное перенаправление | [native-01 verification](../../local/evidence/20261002-p02-login-redirect/native-01/redirect-verification.json) |
| Повтор с окончательным кодом | [native-02 capture](../../local/evidence/20261002-p02-login-redirect/native-02/capture.json), [verification](../../local/evidence/20261002-p02-login-redirect/native-02/redirect-verification.json) |
| VM, callback и собственный диагностический hook | [runtime](../../local/evidence/20261002-p02-login-redirect/native-02/runtime.jsonl), [fresh log check](../../local/evidence/20261002-p02-login-redirect/native-02/log-check.json) |
| Хеши и резервные копии затронутых файлов | [patch-ledger](../../local/evidence/20261002-p02-login-redirect/native-02/patch-ledger.json), [restore](../../local/evidence/20261002-p02-login-redirect/native-02/restore.json) |
| 34 offline + 17 UDP controls, без выдачи мутантов за настоящий клиент | [51 cases](../../local/evidence/20261002-p02-login-redirect/negative-01/results.json) |
| Регрессия P01 на настоящем клиенте | [verification](../../local/evidence/20261002-p02-login-redirect/p01-regression/verification.json) |
| 4 Rust / 20 Python tests | [Rust](../../local/evidence/20261002-p02-login-redirect/rust-tests.log), [Python](../../local/evidence/20261002-p02-login-redirect/python-tests.log) |
| Полные manifests после всех трёх запусков | [baseline comparison](../../local/evidence/20261002-p02-login-redirect/final-integrity/baseline-comparison.json) |
| Завершение процессов/освобождение mutex | [cleanup](../../local/evidence/20261002-p02-login-redirect/process-cleanup.json) |
| Git exclusions | [git-safety](../../local/evidence/20261002-p02-login-redirect/git-safety.json) |
| Изменённые файлы, source diff | [changed files](../../local/evidence/20261002-p02-login-redirect/changed-files.json), [diff](../../local/evidence/20261002-p02-login-redirect/project-diff.patch) |
| Версии зависимостей/бинарника | [dependencies](../../local/evidence/20261002-p02-login-redirect/dependencies.json) |
| Точная текущая версия исходников | [code manifest](../../local/evidence/20261002-p02-login-redirect/code-manifest.json), [all project files](../../local/evidence/20261002-p02-login-redirect/project-files.json) |
| Общий локальный индекс хешей артефактов | [evidence files](../../local/evidence/20261002-p02-login-redirect/evidence-files.json) |

Все ссылки на native bytes, runtime logs и одноразовые test keys ведут в
ignored local. Их наличие не означает разрешения публиковать ресурсы клиента.
Полные V01/V02/V04, сессия, Account, арена и следующий BaseApp reply — NOT_RUN.
