# P02 — смена двух аккаунтов в одном клиентском процессе

Карточка S, 2026-10-05. Native, final audit и независимый review: PASS.
Ручная приёмка владельцем: NOT_RUN.
Цель — primary → secondary → primary с прежним profile002, без перезапуска
EXE и очистки кэша. Бой, экономика, новые выдачи и изменение профилей не входят
в эту проверку. Основание — ночное поручение владельца продолжать текущий ангар.

## Входные данные

VERIFIED: первый собственный аккаунт имеет native ID1, profile3, МС-1 и ИС-7,
два танкиста МС-1. Второй — native ID2, profile1, один МС-1 без экипажа.
Имена, UUID, descriptor и dossier hashes, происхождение всех ожидаемых bytes
записаны в `local/evidence/20261005-p02-account-switch/data/expectations-01/`.
Полный путь к evidence ниже обозначен S.

`tools/account_switch_expectations.py` читает два существующих неизменных
fixture `r3-catalog3` и `r1-catalog2`; не создаёт состояние для удобства теста.
Баланс обоих аккаунтов одинаков, поэтому сам по себе не доказывает изоляцию.
Доказательством должны стать разные идентичности, наборы машин, экипаж и dossier.

Baseline S сохраняет 295 исходных файлов, 14 локальных файлов и согласованные
копии двух БД. До снятия normal006 проверены все 24 затронутых файла против
принятого полного manifest R. Стандартный rollback normal006: PASS.

## Реализация и проверки

Новый opt-in `client_patch/account_switch_scenario.py` использует оригинальные
LoginView/AppEntry API и наблюдает реальный disconnected status, отсутствие
Account repository и три независимых готовых ангара. Каждый интервал содержит
не менее 15 секунд последовательных наблюдений, фактический snapshot и PNG.
Нет команд мыши/клавиатуры, внешнего таймера завершения, очистки профиля или
подстановки успешных callback. Обычный запуск сценарий не вооружает.

Первый prepare switch01: FAIL до любых изменений клиента, поскольку ещё был
установлен normal006 и защитная проверка отвергла отличающийся engine_config.
Причина и удаление неиспользованного control без записи его содержимого/хеша:
`S/switch01-preflight-failure.json`. После проверенного rollback создан fresh
switch02; компиляция 13 модулей и prepare: PASS.

OBSERVED/VERIFIED для switch02: один PID7600, три настоящие авторизации и три
Account/repository lifetime, server sessions3→4→5, 279 packets/13894B без
пропусков в разбиении93+92+94. Интервалы непрерывно готового ангара:
16.0732418 /16.0763238 /16.0703415s. Машины2→1→2, танкисты2→0→2, nativeID1→2→1;
исходные hashes compact descriptors и account dossier совпадают с каждым своим
серверным fixture. Primary cached CRC/shop/dossier восстановились; secondary
запросил собственные streams с холодными cache hints. Баланс обоих остался100000.

Все три PNG просмотрены: корректный МС-1, карусель и портреты меняются вместе
с аккаунтом. OBSERVED: длинный кириллический ник во втором PNG обрезается справа
при1024px; полное имя подтверждено getter/stream, не всеми пикселями заголовка.
Ранее наблюдавшееся цветное зерно остаётся вне приёмки этой карточки.

Native exit0, 12 cleanup,0 trace errors/0 свежих Python errors, capture/restore
PASS, consumed control отсутствует. Процесс прожил86.0398858s; таймером не
закрывался. Завершение вызвано выполнением наблюдаемого условия.

Сценарий: 91 реально выполненная проверка на двух версиях Python — PASS;
один статический тест пропущен на Python2.7.3, выполнен на Python3.
Reader ожиданий:24 PASS; runner40, control9, independent integration10 PASS.
Verifier46 PASS, включая13 отрицательных/положительных проверок настоящего S
corpus. Unit-проверки отдельно от native-приёмки.

Найдены и устранены два диагностических недостатка. Runner раньше писал SHA
credential-bearing control; теперь checksum хранится только в RAM, сохранённые
run artifacts не содержат ни значений, ни производных credentials. Проверка
подмены пароля той же длины до spawn сохранена. Затем independent review нашёл,
что verifier не отвергал добавленные password/sha256 fields в public metadata.
Exact schema закрыла эту дыру; исходный run был чистым и не повторялся.
Первый PASS2b30… и audit01 сохранены как промежуточные, без переписывания.

## Доказательства и границы

S = `local/evidence/20261005-p02-account-switch/`.
Подробности исходных getter contracts и границ сценария: `S/gui/HANDOFF_01.md`.
Происхождение данных и cache hints: `S/data/CONTRACTS_01.md`.
План: `docs/plans/P02_account_switch.md`.

Итоговый verifier `tools/verify_account_switch.py` SHA256
`60ffcbbe4f0146b02d73dab3b7dea1d524b74921fc0ccdfebca14d877e3b29d4`.
`S/wire/verify-switch02-02/account-switch-verification.json` — PASS, SHA256
`530dd12717cef8967d23fded670b49fa3d0c3855c56a2ee88537403d17612dd6`.
Root independently repeated the command: `S/root-verification-02/`, PASS,
SHA256 `c5782cfd23c5a9a7657b29888856ef9a7db1dc90f4a00d6f145793b422a59a06`.
Разные пути производных результатов объясняют разные хеши отчётов.
Independent review `S/gui/verifier-review-01/findings.json` — PASS после fix,
31/31 controls, SHA256 `d4e1ffc6bb99acb2ae1fac3adb0d55c41baa8d41c3f758a010bbe25ac8304501`.
Итоговый wire manifest `S/wire/final-01/manifest.json` SHA256
`829b9559ccf2e33f33d09eabd81875db9e031f30abedeb5e082e494aec55ff38`.

Обычная сборка normal007 установлена:13 compiled modules,22 immutable files
и3 сохранённых owner logs; control/autologin/autoquit/capture отсутствуют.
Полные manifests: original3469/research3487,0 неожиданных отличий.
`S/final-audit-02/final-state-audit.json` — PASS, SHA256
`5f3f202c65acf530c1d594e652d9330a65fb205f3cb9f7007379c74b55102c42`.
Проверены12 выполненных диагностических откатов,20 negative audit controls,
29 неизменных backend sources,4 configs,оба profiles/fixtures и live gateway.
Игровые данные этой карточкой не изменялись.

UNKNOWN/NOT_RUN: произвольные длительные циклы, злонамеренный replay закрытого
UDP peer на настоящий живой gateway, ручное меню смены аккаунта владельцем.
Повторное использование cipher key наблюдается; nonce/endpoint и авторизация
новые. Нынешняя bounded retirement policy не является вечной защитой от replay:
её TTL120s/перезапуск и source spoofing ограничения описаны в карточке R.
Ночные диагностики не заменяют физический ввод в GUI.

## Повтор и откат

Из корня проекта, после закрытия клиента и проверки текущего install ledger:

```powershell
python -B -X utf8 local/evidence/20261005-p02-account-switch/prepare_run.py --name switch03
python -B -X utf8 tools/diagnostic_client_run.py --install local/evidence/20261005-p02-account-switch/switch03-prepare --service local/server/service.json
```

Каждый повтор требует свежего номера и исходного состояния research после
стандартного rollback текущей обычной установки. Не запускать эти команды
поверх установленного normal-пакета: preflight намеренно откажет.
Runner сохраняет исходные SHA/backup/ledger, ждёт native exit и автоматически
восстанавливает только свои изменения. Оригинальный клиент — только чтение.
Откат обычного пакета после закрытия игры и проверки current hashes/ledger:

```powershell
python -B -X utf8 tools/interactive_client.py rollback --out local/client-install-007
```

Проверка сохранённого native evidence без запуска игры (новый out обязателен):

```powershell
python -B -X utf8 tools/verify_account_switch.py --install local/evidence/20261005-p02-account-switch/switch02-prepare --primary-fixture local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r3-catalog3 --secondary-fixture local/server/fixtures/271022a3-41e0-406e-b6fa-59930c320442/r1-catalog2 --native-export local/evidence/20261005-p02-ms1-crew/native-ms1-crew-export01.json --out local/evidence/20261005-p02-account-switch/review-repeat-01
```

Следующий проверяемый шаг после закрытия review: отдельная узкая проверка
отказа позднему пакету закрытого UDP peer на своём стенде.
