# Evidence index — native Account #717

Основной [отчёт](../research/P02_NATIVE_ACCOUNT.md), [план](../plans/P02_native_account.md).
Root: [local/evidence/20261004-p02-account](../../local/evidence/20261004-p02-account/).

| Артефакт относительно root | Назначение |
|---|---|
| `project-full-before.zip`, `project-full-before.json` | 93 исходных собственных файла, hashes; web исключён |
| `baseline/*-manifest.json` | Полное исходное содержимое обеих копий |
| `contract/account-contract.json` | 8 hashes, .def + 3 interfaces, оригинальные bytecode records, candidate PE table |
| `pe-registration/pe-startup.json` | Первичный registration/vector lookup disassembly |
| `pe-create-xrefs/native-pe.json`, `pe-handler-init/native-pe.json` | Статические ссылки и handlers |
| `pe-create-body/native-pe.json`, `pe-entity-create/native-pe.json`, `pe-properties/native-pe.json` | Reader 4+2 bytes, native EntityManager/type lookup и создание |
| `native-01/01-normal/account-verification.json` | Первый реальный creation wire PASS / lifecycle FAIL |
| `native-repeat/*/account-verification.json` | 3 повторных native случая, включая реальную потерю пакета |
| `native-final/01-normal/account-verification.json` | Финальная сборка, значения native player и исходные ошибки |
| `no-creation/01-normal/account-verification.json` | 22 пустых player samples без create packet |
| `no-creation/gateway-verification.json` | Native regression прежнего gateway, без Python ошибок |
| Каждый client run: `runtime.jsonl`, `capture.json`, `packet-*.bin` | Runtime/точные полученные bytes, forwarding/drop, SHA-256 |
| Каждый client run: `patch-ledger.json`, `backup/`, `restore.json`, `postrun/python.log` | Исходное состояние, откат и оригинальные ошибки |
| `client-restores.json` | 6 restore PASS, текущие hashes затронутых файлов совпадают с before |
| `after-final-client/`, `integrity-comparison.json` | Полные hashes после последнего client run и сравнение с baseline |
| `controls/results.json` | 33 own-UDP/parser checks; не native gameplay |
| `rust-tests-final.log`, `python-tests.log` | 20 Rust + 20 Python PASS |
| `build-acceptance.log`, `dependencies.json` | Финальная offline сборка, binary hash, dependency/vendor state |
| `port-mutex-cleanup.json`, `process-cleanup.json` | Освобождение стенда, завершение своих процессов |
| `git-safety.json` | Клиенты/config/local/ключи не staged и исключены |
| `changed-files.json`, `project-diff.patch`, `project-files-after.json` | Точный собственный diff и hashes итоговых файлов |
| `acceptance.json`, `evidence-files.json` | Scope/status и индекс hashes evidence |

Wire creation PASS не отменяет original Python lifecycle FAIL. Полный Account
и P02 — PARTIAL. Штатный UI/арена/web→game login/general fragments — NOT_RUN.
Raw клиентский контент, ключи и compiled diagnostic файлы находятся только local.
