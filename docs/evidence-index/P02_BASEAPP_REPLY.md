# Evidence index — BaseApp reply и первое сообщение

Run: `local/evidence/20261004-p02-baseapp-reply/`.
Полная трактовка: [отчёт](../research/P02_BASEAPP_REPLY.md).
Клиентский content hash:
`74c37c18e9ac7e30196c134076dacf6f2a8bf3897f7def73905d09feb3647797`.

| Доказательство | Путь |
|---|---|
| Baseline и сравнение с предыдущей карточкой | [baseline-verified](../../local/evidence/20261004-p02-baseapp-reply/baseline-verified.json) |
| Освобождение mutex после ответа владельца | [before](../../local/evidence/20261004-p02-baseapp-reply/instance-before.json), [after](../../local/evidence/20261004-p02-baseapp-reply/instance-after-user-close.json) |
| Строки/RTTI/обработчик EXE | [network strings](../../local/evidence/20261004-p02-baseapp-reply/pe-network-strings.json), [RTTI](../../local/evidence/20261004-p02-baseapp-reply/pe-baseapp-rtti.json), [handler](../../local/evidence/20261004-p02-baseapp-reply/pe-baseapp-handler/pe-startup.json) |
| Первый native handshake | [verification](../../local/evidence/20261004-p02-baseapp-reply/native-01/baseapp-verification.json) |
| Повтор с окончательным кодом | [capture](../../local/evidence/20261004-p02-baseapp-reply/native-02/capture.json), [verification](../../local/evidence/20261004-p02-baseapp-reply/native-02/baseapp-verification.json) |
| Настоящие LOGGED_ON и последующий callback | [runtime](../../local/evidence/20261004-p02-baseapp-reply/native-02/runtime.jsonl) |
| PID, ledger и откат | [processes](../../local/evidence/20261004-p02-baseapp-reply/native-02/processes.json), [ledger](../../local/evidence/20261004-p02-baseapp-reply/native-02/patch-ledger.json), [restore](../../local/evidence/20261004-p02-baseapp-reply/native-02/restore.json) |
| 75 negative/control checks | [results](../../local/evidence/20261004-p02-baseapp-reply/negative-01/results.json) |
| 8 Rust / 20 Python tests | [Rust](../../local/evidence/20261004-p02-baseapp-reply/rust-tests.log), [Python](../../local/evidence/20261004-p02-baseapp-reply/python-tests.log) |
| Real redirect regression | [verification](../../local/evidence/20261004-p02-baseapp-reply/redirect-regression/redirect-verification.json) |
| Итоговая сверка обоих клиентов | [baseline comparison](../../local/evidence/20261004-p02-baseapp-reply/final-integrity/baseline-comparison.json) |
| Git exclusions / свои процессы и порты | [git-safety](../../local/evidence/20261004-p02-baseapp-reply/git-safety.json), [cleanup](../../local/evidence/20261004-p02-baseapp-reply/process-cleanup.json) |
| Изменённые файлы этой карточки | [changed files](../../local/evidence/20261004-p02-baseapp-reply/changed-files.json), [diff](../../local/evidence/20261004-p02-baseapp-reply/project-diff.patch) |
| Снимок собственных файлов до изменений | [snapshot](../../local/evidence/20261004-p02-baseapp-reply/project-before.zip) |
| Версия кода и зависимости | [code manifest](../../local/evidence/20261004-p02-baseapp-reply/code-manifest.json), [dependencies](../../local/evidence/20261004-p02-baseapp-reply/dependencies.json) |
| Индекс хешей локальных артефактов | [evidence-files](../../local/evidence/20261004-p02-baseapp-reply/evidence-files.json) |

Мутанты/offline fixtures отдельно от реальных client runs. Клиентские ресурсы,
пакеты, ключи и logs остаются в ignored local. Параллельная веб-сессия имеет
собственное evidence в `local/web/` и не закрывает серверные проверки.
