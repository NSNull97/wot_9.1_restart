# Рабочие заметки агента

Практика, проверенная на этой машине. Правила — в [AGENTS.md](../AGENTS.md),
порядок работы — [07_CODEX_WORKFLOW](07_CODEX_WORKFLOW.md).

## Общий стенд FULL-TEST (2026-10-20)

- Стенд только из одного checkout: `python -B -X utf8 tools/full_test_stand.py prepare
  --source-stand <последний actual стенд> --physics local/build/server/<physics> --gateway
  <exe> --out local/stands/<новый>`; затем `economy --stand <новый>` (100 слотов, цены 0)
  и при необходимости `provision --stand <новый> --account <id> --vehicle vehicle:ussr:T-34`
  (UI экипажа/БК клиента — только MS-1/ИС-7). Сервисы стенда при этом остановлены.
- Канонический gate требует чистого git-дерева; `p08b_restart_cas_composition02` падает
  только под полной параллельной нагрузкой (identity), отдельно проходит — exe брать из
  `--test-filter p08b_restart_cas_composition02` прогона.
- Клиенты a/b: установка из этого checkout `local/stands/full-test-clients-20261020/install-a-08` / `install-b-07`
  (head `1fd5ee4`, `--sixth-sense-sample <mp3 владельца> --player-kill-marker`, `--sixth-sense-sound gun_intuition`; `install-X`, `-02`, `-03` откатаны; стенд `-05`); откат
  `tools/interactive_client.py rollback --out <install-a-09|install-b-08>`. Флаги prepare — в
  `command` его `install-plan.json`.
  CPython 2.7.3: `local/toolchains-py27-20261019/cpython-2.7.3-x86/python.exe`.
- Python-тесты списком модулей: часть тестов импортирует соседей из `tests/` —
  запускать их через `-m unittest discover -s tests -t . -p <файл>`; `test_p08b_owner_hold_store`
  требует `P08B_OWNER_HOLD_SEED`.

## Сборка и тесты

- P10B loss4 runtime689fb93: full1553/5/build/source865, actual Host/HTTP/SQL
  same-run compensation/relaunch/Finished2 PASS; proof20261017-p10b-loss-full01.
  Training synthetic ACK/Account warm идти через Host.receive, обычный
  Session.receive намеренноотказывает training_opt_in. Test startup обязан
  вызывать config-gated Dispatcher.enable_training_finished. SQL battle_id
  это runUUID:arena, arena хранится decimal string (не JS Number). READY
  source compare использует profile_bytes, не canonical исторического JSON.


- P08C late runtimeea43262 full1224PASS/5oldignored/buildPASS,740rawsourceexact;
  actual loss4 Runtime→HTTP/SQL/reopen/pending/1500/1501 PASS. Evidence
  20261017-p08c-late-full02/composition-full.json. Actual pool test helper
  обязан Fixtures::load_p04m, metadata_research остаётся original production.
  SQL17+1/Web5+37/HTTP1+1 PASS0skip. Notice0x4b INFERRED/nativeNOT_RUN.
  СтарыеDBнеоткатыватьповерхновойlatehistory; новыйreaderобязателен.

- P08B regular restart composition на7ff8b30: gateway-p08b-composition-full02,
  1189PASS/5oldignored/buildPASS/716rawsourceexact. Новый test обычный, сам
  запускает Node controller и same test exe2phases; noextraignored/noenvskip.
  Зависимости исходного bundle/original/Node/Python обязательны, missing=FAIL.
  Windows verbatim argv/HERE/source args нормализуются до project boundaries.
  Evidence20261017-p08b-composition-full02/composition-full.json. Нельзя выдавать
  authored Session/ACK/HP0 и AP-only proof за native/loss4 gameplay.

- При нехватке D: `server/build.py gateway --test --cargo-temp-target --out
  local/build/server/<fresh>` создаёт новый target только в default OS temp
  другого локального диска. Cargo/temp остаётся для аудита; только проверенный
  exe копируется в обычный output. Ничего автоматически не удаляется. Нужны
  source-before/after и actual full gate; old default/physics/legacy не меняются.
  Первый actual full: gateway-build-temp01 на0e970b7,1188PASS/5oldignored/
  buildPASS/713rawsourceexact. Exe60860207141afd2bdb00cfaf9436ca08c41d201238243b2cd97bb52f0a988d99,
  actual C→D hash equality PASS; evidence20261016-build-temp01.

- P06T loss checkpoint ed67531: fresh gateway-p06t-ammo-loss-full02,
 1188PASS/5oldignored/buildPASS,712rawsourceexact. Новый isolated loss-01
  binding-loss01; команды/rollback `local/stands/night-battle-20261017-01/loss-01/MORNING-full02.md`.
  Existing CoreV7 installed bytes сохранены; actual two own UDP Login→loss4
  RunOpen PASS, A129/B43/96shells each/active0. Новые services ownSTOP;
  native детонация/башня/потеря БК ещё NOT_RUN. Не запускать старый binding на
  изменённом runtime tree и не выдавать startup smoke за игру клиента.

- Gateway: `python -B -X utf8 server/build.py gateway --test --out local/build/server/<новый-каталог>`.
  Нынешний полный набор с actual HTTP/SQLite compositions занимает около20–22мин
  на закреплённой машине (утро17октября:1292.59с тестов плюс44.83с компиляции);
  прежняя оценка6мин устарела. Выборочно — `--test-filter <имя>`.
  Каталог вывода всегда новый. Внешний runner должен вмещать полный набор;
  отдельные тестовые watchdog не заменяют игровые HTTP/Finish deadlines.
  Итог печатается JSON-строкой (`tests_passed`, `tests_ignored`, `status`); логи —
  `<out>/test.stdout.log`. Базовые 5 ignored — это `#[ignore]` в main.
- Физика (C# worker): `python -B -X utf8 server/build.py physics --out local/build/server/<каталог>`.
- Python: `python -B -X utf8 -m unittest discover -s tests -q`. Тесты хранилищ без
  бандла молча пропускаются (NOT_RUN). Задавать `P04D_TEST_BUNDLE`, `P04F_TEST_BUNDLE`,
  `P04G_TEST_BUNDLE` … `P04K_TEST_BUNDLE` и `P09D_TEST_BUNDLE` = каталог `source-bundle-05`
  любого стенда (например `local/stands/p09e-main-01/source-bundle-05`).
- Web: `cd web && P04D_TEST_BUNDLE=<бандл> node --test tests/<файл>.test.mjs`.
- Клиентский патч: CPython 2.7.3, компилируется при `tools/interactive_client.py prepare`.
  С 18.10 `local/toolchains` — junction на C: без CPython, а `prepare` отвергает
  пути через junction. Интерпретатор восстановлен из `local/downloads/python-2.7.3.msi`
  (`tools/extract_python273.py`, python.exe 702e31ed…) в
  `local/toolchains-py27-20261019/cpython-2.7.3-x86/`; передавать `--compiler`.
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

- P04M qualification после coreV7: применять новый parent supplement
  `night-battle-20261016-01/MORNING-P04M-QUALIFIED-01.md`. Старый parent
  MORNING ссылается на normal PREPARED outputs без ledger: это не текущий
  rollback. Successor использует actual mixed-01 ledgers, exact runtime483bb2b,
  raw634 restore из Git278/CRLF355/retained1 и q VERSION6 plans. Helper остаётся
  `local/night-staging/20261016/p04m-native-morning01/restore_p04m_source.py`.
  Component14/Root material634/artifact audits PASS; actual checkout/apply/
  rollback/install/native NOT_RUN. Предшествующий identity20020 не останавливать;
  q runner требует его доступности, собственную identity службу не запускает.

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
  MORNING-ALL-CARDS-20261016-02.md, first coreV7; clients не переставлялись.
  Дополнительный `net02-ingress-20261016-01`: standalone binding099357da,
  actual gateway-only max1553/1024→oversize1554/1025→max controls PASS34.445с,
  captured4/responses0/ownstop. No bridge/auth/SQL, protected15/core96 unchanged.
  Loopback canary10051 оставляет allowlist-negative NOT_RUN; см. отдельный
  `MORNING-INGRESS-EVIDENCE-01.md`. Nativefragment/firstBasecrossIP/twoPC NOT_RUN.

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

- NET union17.10 использует typed ConfigFields28, private HTTP16. Не заменять
  его старым Bounded23/27. Hold5 successor добавляет только bool и budget29.
- При почти полном D --cargo-temp-target --retain-temp-executable оставляет
  verified canonical exe в ownCtarget. Consumer обязан явно использовать
  built_executable_for_result и actual full/source proof; bad mode/path не
  выбирает старый Dexe. Старые runner13/15 D-only честно отказывают C mode.
- Exact raw source hash сохраняет EOL: NET game_network.rs после normal merge
  имеет140CRLF и raw e3d5cca1…, normalizedLF e90c8d… лишь provenance. После
  full нельзя менять bytes ради совпадения старого diagnostic pin.
- Старый Hold09 adapter test-view удаляет P10B routes: не применять его full
  copy/patch. Reviewed writer19 восстанавливает bounded Hold hunks поверх
  текущего adapter, сохраняет обе selection routes и явно403 для Hold5 owner.

`STATUS.md` — короткое текущее состояние (до ~150 строк), история — в git.
План карточки — `docs/plans/<CARD>.md` на время работы; после слияния удалить, факты
оставить в `docs/research/` (+ строка в [INDEX](research/INDEX.md)) и одной записью в STATUS.
- Не создавать `res_mods/0.9.1/audio`: `<mediaPath>audio</mediaPath>` берёт первый каталог
  `audio`, и FMOD теряет все остальные банки (2026-10-20). Звуковые банки менять на месте в
  `res/audio` исследовательской копии с бэкапом.
