# Рабочие заметки агента

Практика, проверенная на этой машине. Правила — в [AGENTS.md](../AGENTS.md),
порядок работы — [07_CODEX_WORKFLOW](07_CODEX_WORKFLOW.md).

## Сборка и тесты

- Gateway: `python -B -X utf8 server/build.py gateway --test --out local/build/server/<новый-каталог>`.
  Полный набор ~6 мин; выборочно — `--test-filter <имя>`. Каталог вывода всегда новый.
  Итог печатается JSON-строкой (`tests_passed`, `tests_ignored`, `status`); логи —
  `<out>/test.stdout.log`. Базовые 5 ignored — это `#[ignore]` в main.
- Физика (C# worker): `python -B -X utf8 server/build.py physics --out local/build/server/<каталог>`.
- Python: `python -B -X utf8 -m unittest discover -s tests -q`. Тесты хранилищ без
  бандла молча пропускаются (NOT_RUN). Задавать `P04D_TEST_BUNDLE`, `P04F_TEST_BUNDLE`,
  `P04G_TEST_BUNDLE` … `P04K_TEST_BUNDLE` и `P09D_TEST_BUNDLE` = каталог `source-bundle-05`
  любого стенда (например `local/stands/p09e-main-01/source-bundle-05`).
- Web: `cd web && P04D_TEST_BUNDLE=<бандл> node --test tests/<файл>.test.mjs`.
- Клиентский патч: CPython 2.7.3 `local/toolchains/cpython-2.7.3-x86/python.exe`;
  компилируется при `tools/interactive_client.py prepare`.
- P08C candidate: `local/build/server/gateway-p08c-full01/`, runtime8c96580,
  919PASS/5ignored/buildPASS. Natural result/AP/HP commit атомарен в том же writer;
  private `/internal/native/battle-results` обслуживает Account1500/1501.
  Original Avatar stream100 ждёт scoped confirm перед Account reset; native gate
  NOT_RUN. P08B клиентская установка native-fix03 остаётся последней, процессы
  своих run03 остановлены. Не запускать новый exe со старой source receipt.
- Байткод клиента: оригинал `C:\WoT_0.9.1_RU_0717_original` (путь в
  `config/project.local.json`). Читать `.pyc` через `marshal` + `dis` этим CPython 2.7.3,
  без исполнения кода клиента. Так проверены все факты последних карточек.

## Ловушки

- `server/gateway/src/session.rs` git считает бинарным (`-text`), в репозитории он в LF.
  Правя скриптом, пишите байты LF, иначе diff на весь файл и сломанные слияния.
- `git push` из Bash падает на TLS — пушить из PowerShell.
- Вложенный `powershell.exe` внутри PowerShell-инструмента зависает. Сервисы стенда
  запускать отдельным фоновым процессом и проверять PID после выхода запускающего.
- Ревизия магазина: профиль 13 публикует 5, писатель экипажа P04K связан с 3; gateway
  переводит ровно 5 → 3 только для найма и казармы (`ammo_session.rs`, `crew_shop_revision`).
- Дельта ответа аккаунта ≤ 240 байт (однобайтовая длина конверта). Покупка самого
  большого танка — 217 байт; лишние поля в дельту не влезают.
- Транспорт: интерактивная сессия ждёт подтверждений до 30 с (NET-01), лабораторные
  режимы — 5 × 700 мс. Обновление ангара блокирует клиент на 3–7 с.
- Неподдерживаемые команды аккаунта получают `RES_NOT_AVAILABLE` только из списков
  `UNAVAILABLE_*` в `account/hangar.rs` (ACC-01). Новую команду добавлять, лишь проверив
  по байткоду, что её callback принимает `ext`.

## Цепочка профиля аккаунта

8 P04G → 9 P04H → 10 P04I → 11 P04J → 12 P04K → 13 P09E (исследования и покупка).
Один SQLite-писатель; для профиля 13 — `tools/p09e_research_service.py` (все операции
экипажа и исследования). Миграция только вперёд, из точно известного предшественника;
снимок экипажа P04K ограничен 16 КиБ, исследования хранятся в своей таблице.
Harness профиля 12/13: `tools/p09e_research_harness.py --seed-only`.

## Стенды (`local/stands/`, не в git)

- NET02 runtime608bb23/tag `net02-private-lan-20261016-01`: full1414PASS/
  5oldignored/build/794rawexact. `net02-ownhost-20261016-01` actual two own-IP
  Login/Base/Account/room/Ready/Leave PASS45.391с; ownstop. SourceP10B43/44
  preserved, NETcopy44/45/БКunchanged/active0. Ownhost initial43/44 binding
  consumed; не переписывать snapshot/SQL и не повторять smoke на44/45.
  Actualstartup BOUND30.736с,total42.718с; старый operator30с FAIL сохранён,
  services02 fixed90с, runtime/HTTP budgets прежние. Actual UDPprivateIP/
  HTTP127 подтверждены Windows; remoteB/firewall/native/hosting NOT_RUN.
  Exactcommands/rollback — собственный MORNING-NET02-EVIDENCE.md. Общая
  стабильная утренняя матрица — night-battle-20261016-01/
  MORNING-ALL-CARDS-20261016.md, first coreV7; clients не переставлялись.

- `night-battle-20261016-01/mixed-01`: отдельный P06T opt-in backup, оба
  MS1[AP0,HEAT4,HE10] из своего склада,0grants; исходныйpool-01 сохранён.
  Full02/dc27285/1087PASS source-bound binding-p06t.json исторически проверен:
  actual startup-p06t01/5resources и два synthetic own UDP→v2run_open PASS,
  A111/B28/БК unchanged, gateway/bridge STOPPED по своим receipts.
  Queuefix full03/9920a63:1096PASS/5ignored/build/683sourceexact PASS,
  coretag p06t-core-20261016-01, binding-p06t02.json. V7INSTALLED; native-p06t01
  оба realclient hangar/cache/model OBSERVED, A112/B29/БК unchanged/reserves0,
  ownclients/servicesSTOPPED. UI/control/combatNOT_RUN. При дальнейших runtime
  изменениях выбирать coretag перед этим стендом, guard не обходить.
  `run.py bind --build` принимает basename build либо absolute path;
  relative `local/build/server/...` не использовать. V7 clientplans уже
  INSTALLED, повторять install не нужно. Точные команды/откат — собственный
  `MORNING-core.md`; перед утренними клиентами использовать свежий run.
- `night-battle-20261016-01`: ночной зависимый P04M-кандидат. Исходный
  `game.sqlite` сохранён побайтно; рабочая opt-in копия `pool-01/game.sqlite`,
  fixtures `pool-01/fixtures`, A109/B26/MS1AP14 у обоих/A IS7AP19. Политика
  pool_service явная для A/B; v3 manifest5, gateway p04m_pool/visibility_v1=true.
  `run.py check`52pins и пять local runner/negative tests PASS; source-bound
  `binding-p04m.json` уже закрепляет full02/483bb2b/1006PASS+5ignored/buildPASS.
  Actual normalCLI startup/5resources и ownPID stop PASS, client NOT_RUN.
  Старые binding-P05C/P07B исторические и не запускают текущий runtime.
  `qualification.py`/`qualification-02` готовят временные Т26/Т34/Т34-85 без
  owned grants/admission; собственные overlays PREPARED, native NOT_RUN.
  Точные команды/откат — ignored `MORNING.md` и `pool-01/REPORT.md`.
- `p08b-profile13-01` — свежая общая P08B БД A/B профиля13, bridge3481,
  login20130/base20131. Режим `legacy091-profile13 KEY DIGEST GATEWAY MANIFEST CAPTURE`;
  manifest `battle-profiles.json` закрепляет оба однородных stock MS-1/ИС-7 пула,
  геометрию и общий каталог Прохоровки. Client installs `install-{a,b}-01`,
  только `--enable-profile13-battle` и полный набор9 hangar service flags.
  Текущий запуск — `native-fix03/` со своими install, profile/runtime, binding
  и launch/stop receipts; source runtime `5c08ef5`, gateway full04 893/5.
  Обычный map-drive/shared-lab с ними не смешивать. Native приёмка пока NOT_RUN;
  source/build/launch receipts нужны перед запуском. B создан отдельной явной
  owner-source policy; исходный A13 остался без изменений. Факты — исследование P08B.

- `p09e-main-01` — ангар профиля 13 (экипаж, БК, исследования, покупка).
  Bridge 3480, вход 127.0.0.1:23480, `services.ps1 start|stop`.
  Клиент: `local/clients/p03f/a/WorldOfTanks.exe`; перед запуском скопировать
  `control.template.json` → `control.json` (автовход тестовым аккаунтом проекта,
  учётные данные не печатать). Трасса клиента — `runtime/`, лог gateway — `gateway-*.stdout.log`.
- `hangar-crew-ammo-01` — профиль 12, только источник данных (копировать backup API SQLite).
- Бой двух клиентов: `prepare_stand.py`, `start_stand.py`, `stop_stand.py` в
  `local/evidence/20261014-p05b-handling-fixes-01/native-handling-c17b/`; режим
  `legacy091-integrated-lab`, закреплённые пул физики, геометрия и каталог разрушаемых
  объектов; оба клиента на одном типе танка (`--vehicle-test-lab ms1|is7`).
- Установка патча в копию клиента: `tools/interactive_client.py rollback --out <старая>`,
  затем `prepare --out <новая> --research-copy local/clients/p03f/a … --enable-…` и
  `install --out <новая>`. На копии одновременно стоит одна установка.

## Слияние в main

Ветка `codex/<card>-<purpose>` от main → проверки текущего head → `git merge --no-ff`
в main → push → `git ls-remote origin refs/heads/main` = локальный main.
Allowlist перед push (файл ORG-0A удалён как устаревший): изменённые пути — только
`client_patch/`, `docs/`, `server/`, `tests/`, `tools/`, `web/`, `config/` и корневые `.md`;
никаких `local/`, ресурсов клиента, секретов, `.sqlite`/`.bin`/`.pyc`; дерево слияния
совпадает с проверенным head карточки (`git diff --quiet <card> HEAD`). Если main
открыт в другом worktree, слияние делать во временном worktree от main и переносить
`git merge --ff-only` в том worktree, где открыт main.

## Документация

`STATUS.md` — короткое текущее состояние (до ~150 строк), история — в git.
План карточки — `docs/plans/<CARD>.md` на время работы; после слияния удалить, факты
оставить в `docs/research/` (+ строка в [INDEX](research/INDEX.md)) и одной записью в STATUS.
