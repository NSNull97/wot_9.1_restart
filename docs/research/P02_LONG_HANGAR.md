# P02 — длительный ангар и периодический native обмен

2026-10-05, карточка L. **Native PASS**, независимый review55controls PASS;
полный audit обычной установки009 PASS. Независимый review final audit PASS:
11 actual bindings и38 negative controls. Ручная приёмка NOT_RUN.
План: `docs/plans/P02_long_hangar.md`.
Evidence L=`local/evidence/20261005-p02-long-hangar/`.

## Что проверяется

Один cached login существующего primary с прежним профилем3, МС-1, ИС-7
и двумя танкистами МС-1. Условие: минимум181 нормальный возврат оригинального
`Account.receiveServerStats` за не менее900s непрерывно готового ангара.
Все три полных снимка identity/resources/fleet/crew/dossier должны совпасть;
начальный и конечный PNG сохраняет родной `BigWorld.screenShot`.

VERIFIED по original #717: `LobbyHeader.onStatsReceived`,line167, назначает
следующий запрос через5s после ответа; `Account.requestServerStats`,line763,
отправляет command501. Нормальный возврат `receiveServerStats`:line679,offset16.
Account.pyc SHA256 `bb6e88e4aec03161212847ffc3601d16917610b8f7815c42f91f610693f4d0ef`,
LobbyHeader.pyc SHA256 `b94bad0587c1a7f03bc8240a9add4e1dbbe54c35d18460cafcf220039da695b4`.
Исходные инструкции/пути/хеши:
`local/evidence/20261005-p02-retired-base-replay/data/long-hangar-feasibility-01/evidence.json`.

Это запросы и ответы **CCU1/1 собственного стенда**, а не боевая статистика,
симуляция или начисление ресурсов. Backend/config/fixtures не меняются;
арена, экономика, новые выдачи и управление компьютерным вводом вне карточки.

## Реализовано до native запуска

- Отдельный `client_patch/long_hangar_scenario.py`, SHA256
 `6d13f7d8c55a0058f25e807edcdd7d656953dbccd7c1ea9901c3d567a4d0fb0d`.
 Python3:30tests PASS; родной CPython2.7.3:30tests PASS и compilation PASS.
 Evidence `L/gui/checks-01/`, API/схема `L/gui/SOURCE_AND_SCHEMA.md`.
- `sr_interactive.py`: passive profiler передаёт только primitive поля
 настоящего original return; frame/credentials не сохраняет. Неверный return
 передаётся как наблюдаемая ошибка, не отфильтровывается ради PASS.
- Новое явное условие `verify_long_hangar`/`long_hangar_observed`, совместимое
 с bounded public expectation и одним собственным Python LoginView submit.
 Другие операции, timers, alternate credentials и сторонние captures отвергаются.
- `diagnostic_client_run.py`:14-й compiled module и запас не менее5000packets/
 2MiB перед запуском. Public metadata не содержит secret-derived checksum.
 Старые mode metadata сохраняют прежние13keys; L добавляет только свой flag.
- После ≥181ответа/≥900s и конечного PNG выполняется штатный native quit.
 Реальная потеря ready/state/progress, неверный callback или исчерпание trace
 отмечаются FAIL. Внешнего EXE timeout/kill нет. Полный hang engine, при котором
 callbacks перестают исполняться, этим механизмом не закрывается.

Root integration9tests и regression40runner+9switch+6relogin PASS:
`L/root-checks-01/result.json`, SHA256
`f29c81a78c48b403145dd025f5a75cb1da6b1c985f9a2bcfc4bddbacbd6dee82`.
Independent integration review8 boundary controls PASS в `L/data/integration-review-01/`.
Эти проверки не заменяют native acceptance.

## Запуск и исходное состояние

Baseline311sources/17localfiles/2consistentDB сохранён до правок.
Normal008 проверен по25файлам и штатно откатан. Guard
`L/normal008-prerollback.json`, SHA256
`c23a1430813c78563fcc1667fc91cd55cf3d8a942c5597c1669b660e17fe6156`.
Original3469/cleanresearch3470 rollback lineage независимо PASS.

`L/long01-preflight.json`:14compiledmodules, first capture index747,
остаток9253packets; native session limit1800s не менялся. Long01:
harness PID70104/native PID49420, trace
`L/long01-runtime/native-49420-1791165541310.jsonl`.

```powershell
python -B -X utf8 -m unittest discover -s tests -p test_long_hangar_scenario.py -v
python -B -X utf8 -m unittest discover -s tests -p test_long_hangar_control.py -v
# Только после закрытия клиента и проверенного отката текущей обычной установки:
python -B -X utf8 local/evidence/20261005-p02-long-hangar/prepare_run.py --name long02
python -B -X utf8 tools/diagnostic_client_run.py --install local/evidence/20261005-p02-long-hangar/long02-prepare --service local/server/service.json
```

## Фактический native результат

Long01 закончен штатно: PID49420,938.3719303s от runner start до exit0,
12cleanup,0trace/0свежихPythonerrors,capture/restorePASS. Полные2580packets/53082B,
trace4420events/2126181B. Непрерывный native ready913.2943025s,909samples,
maxgap1.0699222s. Отдельная scenario clock даёт913.2685618s; origins не смешиваются.

Ровно182 настоящих CMD501/request202 → response method0x48/CCU1/1 → original
normal return. Из них181 внутри ready span907.7933707s. Три полных снимка
совпали, оба nativePNG просмотрены root и независимым reviewer: МС-1, два
танкиста,100000/0/0,МС-1+ИС-7 в карусели. Цветное зерно остаётся OBSERVED,
причина UNKNOWN. Это не утверждение о визуальном качестве каждого пикселя.

Clientseq186/serverseq650/final cumulativeACK651. Все серверные sequences
подтверждены; physical retries0/0,maxpending3. Один свежий auth worker,
один Account/repository/session; реальные sync/cache payload совпали с fixtures.
Ни цены, ни ресурсы, ни статистика игрока не менялись.

Первый verifier-report сохранён FAIL: новый reader принял возобновления
генератора `onBecomePlayer` за дополнительные входы. Original bytecode имеет
YIELD228/242→RETURN247; frozen S уже различал initial call offset-1 и resumes.
Исправлен только новый verifier, добавлены negatives; native не повторялся.
Затем исправлен унаследованный текст scope про две сессии. Report03 отличается
от report02 только `verifier_sha256` и `checks.process_runtime.scope`;
структурное сравнение сохранено в `L/wire/checks-03/result.json`.

| Доказательство | Путь и SHA256 |
|---|---|
| Actual outcome | `L/long01-prepare/native-outcome.json`, `737a2544fe6c4ffe3126d63dd46557902d2011bdd660d3d4f1a6a7c8724aa0ed` |
| Full capture | `L/long01-prepare/wire/capture.json`, `1e891a12dbff2fb977b4f60a847b9745f064454365f6bb92c31ba29d7cf8088f` |
| Actual trace | `L/long01-runtime/native-49420-1791165541310.jsonl`, `508712dea5109df98a0944435addf4142906013f9fe0afb74426e7d50b361853` |
| Final20gate verifier | `L/wire/verify-long01-03/long-hangar-verification.json`, `c74df14374e053bab68c13a5c1b366814834b50ba8a084123340b32062b95d25` |
| Root repeat before scope-text fix | `L/root-verification-01/long-hangar-verification.json`, `acebc607f6509ad6b88aadad15338f5b9d7dff1d7441877af425fa1b44c4234a` |
| Actual image review | `L/long01-prepare/visual-review-long-hangar.json`, `2f4a94ceb4d9bceb705948c46acc2f477350353954b7d0cc29e84478c64f00fc` |

Final verifier `tools/verify_long_hangar.py` SHA256
`297f5b11a8f3ada5c11b9f0fde3f3a33ae4acafc74ec43c5d7d2fc2af85deddd`,40testsPASS.
Independent reviewer:55controls/20gates offline repeat PASS, evidence
`L/gui/verifier-review-01/controls-03/`; его первый controls-01 KeyError был
ошибкой review-helper, сохранён отдельно и не выдаётся за сбой клиента.
Final review SHA256 `6859e5ea583b2882e760f0b62cb796059ad2bb1b87361176d1647a592f789839`,
manifest SHA256 `3a67a45e7c4888da46483a5b8436ed569c9ad6adb0c8d7085d8a83b84c34e101`.

Обычная009 установлена послеstrictPASS:14 native-tested modules/23immutable
и3preserved ownerlogs, без control/autologin/autoquit/capture. Fullmanifest scan
завершён:original3469/research3488. Финальный audit PASS:
`L/final-audit-01/final-state-audit.json`, SHA256
`1932650550743d296355af81edd48c8e176820853a9e52ba916c6c0e82a2cf1e`.
Ноль неожиданных отличий,14 завершённых diagnostic restores,54negative controls;
29backend/4config/70прочих runtime sources/оба profiles иfixtures неизменны.
Привязаны все2580ciphertext files,trace,8original artifacts и2PNG.
Audit helper SHA256 `23beaabd25ba0da6126e0409d3ad294e54c561334fe90594702c606a779bd4aa`.

Независимый review финального audit завершён без новых запусков и изменений:
`L/wire/audit-review-01/result.json`, SHA256
`c82997905b315e35636034b75acd87a5081a7203d1463233016fd69d3adc617b`.
11 actual bindings PASS;38 содержательных подмен корректно отвергнуты.
Повторно хешированы все2580 UDP files, trace,8 связанных артефактов и2 PNG.
Manifest review SHA256
`2b06c241aae08628245a698fe8b01d44b8e019f1df3c7ba4bf99a9d750419ab4`.

```powershell
python -B -X utf8 tools/verify_long_hangar.py --install local/evidence/20261005-p02-long-hangar/long01-prepare --fixture local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r3-catalog3 --native-export local/evidence/20261005-p02-ms1-crew/native-ms1-crew-export01.json --out local/evidence/20261005-p02-long-hangar/recheck-01
# Откат текущего ordinary package после закрытия игры и сверки ledger:
python -B -X utf8 tools/interactive_client.py rollback --out local/client-install-009
```

Граница:15минут не доказывают многочасовую работу или реакцию GUI на существующий
deadline1800s. Источник gateway действительно закрывает session без отдельного
nativekick; задержка и LoginView после silent expiry UNKNOWN/NOT_RUN.
Read-only исследование: `L/data/deadline-feasibility-01/PROPOSAL.md`, evidence SHA
`5a02deb73e56dd76ef916e1a83e7e4150c6c8bcfcf347969dc8fe8e5231ba271`.
Следующий отдельный проверяемый шаг: реальный session_deadline→disconnected→
LoginView, без подставного callback/logoff/kill; эта карточка его не выполняла.
