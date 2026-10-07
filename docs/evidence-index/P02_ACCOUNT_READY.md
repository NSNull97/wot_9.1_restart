# Evidence index — минимальный Account lifecycle / initial sync

Основной [отчёт](../research/P02_ACCOUNT_READY.md), [план](../plans/P02_account_ready.md).
Root: [local/evidence/20261004-p02-account-ready](../../local/evidence/20261004-p02-account-ready/).

| Путь относительно root | Что доказывает |
|---|---|
| `project-before.zip`, `project-before.json`, `project.local.before.json` | 100 исходных собственных файлов, hashes/config для отката; web исключён |
| `baseline/`, `after-final-client/`, `integrity-comparison.json` | Полные manifests обеих копий до/после,3469 файлов, ни одного отличия |
| `source-hashes.json`, `verified-static-sources.json` | EXE/Account/Settings/game/defs hashes;26 static module entries сверены с original |
| `bootstrap-static/sources.json`, `cache-static/sources.json` | Original Settings/game/Account/cache зависимости, line/offset records |
| `account-full-static/`, `account-dependencies/` | Частично завершённые probes; не все имеют sources index, причина описана в отчёте |
| `account-more-dependencies/`, `sync-controller/`, `persistent-data-static/`, `live-crc-static/` | Original command constants, cache/sync callbacks, исходные hashes |
| `shutdown-static/`, `stream-bootstrap-static/` | Original shutdown и checksum/dispatch stream path |
| `pe-preferences*/`, `pe-path-controls/` | Static source CompanyName/ProductName prefix и путь preferences |
| `pe-rpc*/`, `pe-method-handler/`, `pe-variable-header/`, `pe-rpc-size*/` | Read-only EXE registration, ranges, dispatch/size ordering candidates |
| `pe-stream*/`, `pe-select*/` | Original stream readers/header/fragment и player selection |
| `method-candidates/`, `method-candidates-2/` | Первая отвергнутая гипотеза и уточнённый порядок; неподтверждённые IDs остаются INFERRED |
| `settings-01/`, `settings-path/`, `settings-isolated/`, `server-settings-01/02/03/`, `rpc-layout/` | Сохранённые bootstrap guards/errors, timeout, промежуточные native наблюдения |
| `sync-01/01-normal/` | Negative native wrong method0x4c: ACK/CRC есть, initial sync FAIL |
| `sync-02/01-normal/account-ready-strengthened.json` | Первый подтверждённый original lifecycle/initial sync PASS |
| `native-final/account-ready-verification.json` | Native series8/8, один gateway PID22872, IDs1..7, negative password и recovery |
| `native-final/*/account-ready-verification.json` | Отдельная проверка original returns/identity/RPC correlation/CRC/ACK/cleanup |
| `runner-corrected/account-ready-verification.json` | Повтор после исправления ошибочных generic outcome fields; окончательный runner |
| `no-creation/01-normal/account-verification.json` | Account отсутствует без server creation; diagnostic Settings сами не создают entity |
| `no-creation/gateway-verification.json` | Native regression прежнего bounded transport gateway |
| Каждый run: `capture.json`, `packet-*.bin`, `runtime.jsonl`, `backend.stdout.log` | Полученные bytes/SHA, forwarding controls, оригинальные callbacks и server apply counts |
| Каждый run: `native-rpc-layout.json` | Всего88 B read-only своего child; ranges за pinned EXE header/hash |
| Каждый run: `patch-ledger.json`, `backup/`, `postrun/`, `restore.json`, `profile-created-files.json` | Before hashes, созданные cache files, диагностические логи и откат |
| `client-restores.json` | Все19 client runs восстановлены, текущие hashes сверены с before |
| `rust-tests-01.log`, `python-tests-final.log` | 26 Rust/20 Python tests PASS |
| `corpus-controls/results.json`, `gateway-regression/results.json` | 311 повреждений actual corpus/negative native control;33 собственных UDP controls |
| `build-04.log`, `dependencies.json` | Final build, binary hash, tool versions, pinned clean vendor |
| `port-mutex-cleanup.json`, `process-cleanup.json`, `git-safety.json` | Свободные порты/mutex,31 собственный PID завершён/отсутствует, ignored/staged checks |
| `changed-files.json`, `project-files-after.json`, `project-diff.patch` | Итоговый собственный список/hash/diff без web |
| `acceptance.json`, `evidence-files.json` | Границы приёмки и SHA-256 index локальных evidence |

Raw клиентский bytecode/PE disassembly, runtime dumps, cache contents и тестовые
ключи остаются в ignored local; в Git идут только собственные утилиты и выводы.
README/SCOPE/NAMING фиксируют GAYmDev Stutio / «Стальной рубеж» и единую учётку
сайта/игры как требование. Web→game сквозной вход, штатный ангар, native preferences
и арена NOT_RUN. Подробные FAIL и ограничения не скрыты за общим PASS карточки.
