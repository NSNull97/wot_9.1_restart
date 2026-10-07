# P02 — минимальный Account: lifecycle и начальная синхронизация

2026-10-04. Продолжение по поручению владельца «доведём акк до готовности».
План: [P02_account_ready](../plans/P02_account_ready.md).
Evidence root: `local/evidence/20261004-p02-account-ready/` (далее E).
Публичные названия: GAYmDev Stutio, «Стальной рубеж»; [NAMING](../NAMING.md).

**Приёмка узкой карточки PASS:** отдельный сервер создаёт оригинальный
`Account.PlayerAccount`; его конструкторы, onBecomePlayer, первоначальная
синхронизация и onBecomeNonPlayer завершаются без исключений. Источник данных —
настоящие packets собственного loopback сервера, обработчики Account не заменены.
**Полный Account/ангар и весь P02 остаются PARTIAL.** Диагностический bootstrap,
пустые лабораторные данные и один stream не доказывают готовность игрового сервиса.
P03, Avatar/арена, экономика, лаунчер и боты не реализовывались.

## Что изменено

- `client_patch/p01_probe.py`: opt-in оригинальные Settings, пассивное наблюдение
  original Account frames/state, ограниченный stream → original game dispatcher,
  штатное завершение EntityManager и Account repository/cache threads.
- `tools/client_probe.py`: exclusive profile с before hashes/backup/rollback,
  учёт созданных cache files, bounded read-only наблюдение своего дочернего EXE;
  отдельная отчётность для persistent gateway и независимого verifier.
- `tools/wg_probe/src/account091.rs`, `gateway091.rs`, `main.rs`, `transport091.rs`:
  отдельный `legacy091-account-ready`, три измеренных первоначальных команды,
  ограниченные ответы и stream, атомарная обработка входного bundle, защита от
  повторного исполнения. Старые transport/wire profiles сохранены.
- `tools/bytecode_probe.py`, `account_method_candidates.py`, `native_layout091.py`:
  маленькие статические/диагностические инструменты; не general memory dumper.
- `tools/gateway_suite.py`, `gateway_faults.py`, `verify_account_ready.py`,
  `check_account_ready.py`: native series, loss/duplicate controls, независимые
  wire/runtime criteria и повреждения настоящего corpus.
- README/NAMING/STATUS/MISSING_INPUTS/KNOWN_UNKNOWNS/REPRODUCE и evidence index.
  Полный собственный diff и hashes: E/changed-files.json, project-diff.patch.
  `web/` и `local/web/` принадлежат параллельной сессии, здесь не редактировались.

## Подтверждённые контракты

VERIFIED для закреплённого клиента `v.0.9.1 #717 RU`, compatibility
`ru_0.9.1_2`, Python 2.7.3 x86. EXE SHA-256:
`86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed`.
Account.pyc SHA-256:
`bb6e88e4aec03161212847ffc3601d16917610b8f7815c42f91f610693f4d0ef`.
Остальные исходные hashes: E/source-hashes.json, static */sources.json,
method-candidates-2/method-candidates.json; каждый PE probe привязан к EXE hash.

| Факт | Расположение и проверка |
|---|---|
| Account type0 / createBasePlayer ID5 VAR2; 3 свойства version/name/serverSettings | Предыдущая карточка P02_NATIVE_ACCOUNT + каждый новый native capture/пассивные player samples |
| Original Settings получает 3 настоящих native init arguments | `settings.pyc` Settings.__init__ line50; `game.pyc` init offsets42..63; E/bootstrap-static/ |
| serverSettings требует file_server и использует voipDomain | Account constructor и CustomFilesCache.__init__, E/account-full-static/, cache-static/; реальные KeyError и успешные повторы |
| Диапазоны client methods59..157, properties158..254, base methods134..254 | Каждый native-rpc-layout.json: 24 B globals +64 B header, всего88 B из собственного Popen; адреса 0x2305654, 0x2305660, 0x230555c |
| Client doCmdInt3: ID0x8e/VAR2, args `<hhqii>` | Реальный client sequence1: три 23-byte сообщения; request221/222/223, commands100/300/600, остальные args=0 |
| onCmdResponseExt: selectPlayerEntity0x13, method0x4d, VAR1 | Реальные original callbacks line302/return119, requestID/resultID коррелируют с server packets; отрицательный 0x4c сохранён |
| Account sync100: revision1 + пустые inventory/stats/economics | Original Account._update line1451/return661; native flag synchronized=True, revision1 |
| Shop sync300 заканчивает первоначальный запрос | Original response result0/ext{}; shop isSynchronizing=False; каталог остаётся пустым, usable shop НЕ проверен |
| Dossier sync600: result1 RES_STREAM + stream ID=requestID | Resource header52/VAR2, fragment53/VAR2 (u16 id/u8 seq/u8 last), 18 B zlib data |
| CRC и длина проверены самим оригинальным game dispatcher | native_stream + original Account.onStreamComplete line351/return255; desc integrity `[False,18,18,1424607769,1424607769]` |
| Оригинальный выход завершён | onBecomeNonPlayer line246/return366; repository closed; native exit0; server client_disconnect, active0/pending0/retired_pending0 |

Ответы содержат только собственные маленькие protocol2 data literals, без
GLOBAL/REDUCE и без загрузки объектов во входном серверном parser. Dossier payload
декодируется как `(0, [])` оригинальным клиентом: версия пустого cache0. На стороне
инструментов используется ограниченный zlib decoder и проверка точных data bytes,
`pickle.loads`, eval/exec и выполнение извлечённого клиентского bytecode не нужны.

OBSERVED: пустое состояние своего лабораторного аккаунта принимается этим
diagnostic bootstrap. Наличие словарей и завершение sync не доказывают, что
штатному ангару хватает этих данных. Store revision0/ext{} означает отсутствие
обновления пустого каталога; торги/цены/балансы не реализованы и не принимаются
за успешную экономику. Voice service и file endpoints явно недоступны.

INFERRED: статический порядок методов по fixed stream size объясняет native
индексы. Первоначальный расчёт без фиксированного SERVER_STATISTICS ошибочно
давал slot17/0x4c. После учёта FIXED_DICT получен slot18/0x4d. Подтверждены лишь
фактически вызванные RPC; остальные строки candidate tool остаются гипотезами.

## Изоляция и ограничения bootstrap

OBSERVED: при абсолютном preferences path EXE возвращает строку с исходными
CompanyName/ProductName впереди (`preferences_probe`), а DossierCache дополнительно
требует byte string UTF-8. Guard первых runs остановил инициализацию до connect.
PE путь исследован в E/pe-preferences*/ и pe-path-controls/.

Diagnostic personality проверяет точную исходную форму пути, затем перенаправляет
только Python getter `BigWorld.wg_getPreferencesFilePath` в новый
`research/p01_profile/preferences.xml`. Папка должна отсутствовать до run;
содержимое учитывается, сохраняется в postrun и удаляется при rollback.
EXE, оригинальный Account и его entity callbacks не патчатся. Это узкий
исследовательский shim, не штатная реализация профиля. Native preferences
persistence и обычный game.init/showGUI — NOT_RUN.

`sys.setprofile` наблюдает конкретные original Account frames: normal return
проверяется по offset, а не только по отсутствию traceback. В конце вызываются
original resetEntityManager и _delAccountRepository; без последнего остались
рабочие cache threads и был реальный timeout (сохранён ниже).

Компоненты с внешними service URLs не включались; явный connect направлен только
на 127.0.0.1:20014, BaseApp на 20016; свои backend ports20015/20017. Системный
egress capture/firewall isolation не проверялся — NOT_RUN, отсутствие вообще
любых внешних пакетов ОС не заявляется. Все учётные данные и ключи лабораторные.

## Запуски и результаты

| Проверка | Результат | Evidence относительно E |
|---|---|---|
| Первый original Account lifecycle + initial sync | PASS, 21 ready samples /10.0633 s | sync-02/01-normal/account-ready-strengthened.json |
| Один persistent gateway PID22872; 7 успешных сессий, IDs1..7 | PASS | native-final/account-ready-verification.json |
| Потеря initial sync reply seq2 и Account creation seq0 | PASS: identical retry attempt2, потом original sync | native-final/03-drop-server-sync/, 05-drop-server-first/ |
| Дубликат initial RPC bundle и первого frame | PASS: команды применены по1 разу, 1 allocation/session | native-final/04-duplicate-client-sync/, 06-duplicate-client-first/ |
| Неверный пароль + следующий успешный вход | PASS: native code67, allocation0; следующий session7 | native-final/07-wrong-password/, 08-normal/ |
| Вся native series | PASS 8/8; synchronized state держится9.06–10.09 s | native-final/account-ready-verification.json |
| Повтор после исправления отчётности runner | PASS; правильный profile, capture verification отдельно | runner-corrected/account-ready-verification.json |
| Оригинальные Settings, без Account create packet | PASS: player отсутствует; предыдущий gateway проходит | no-creation/01-normal/account-verification.json и no-creation/gateway-verification.json |
| Rust boundary/replay/ACK/atomic bundle tests | PASS 26/26 | rust-tests-01.log |
| Python tests, 5 из них читают настоящий клиент | PASS 20/20 | python-tests-final.log |
| Повреждения actual corpus + negative native wrong-route | PASS 311 checks; это не311 client runs | corpus-controls/results.json |
| Предыдущие собственные UDP gateway controls | PASS 33/33 | gateway-regression/results.json |
| Полный rollback клиентских файлов | PASS: 19 runs, обе копии3469 файлов без отличий | client-restores.json, integrity-comparison.json, after-final-client/ |
| Штатный ангар, общий web→game login, два разных пользователя, persistence, арена | NOT_RUN | Не закрываются этой карточкой |

Ошибки не удалялись и не переименовывались в PASS:

- `settings-01`, `settings-path`: guard invalid native preferences, connect NOT_RUN.
- `settings-isolated`: original `KeyError: file_server`; initial lifecycle FAIL.
- `server-settings-01`: original DossierCache TypeError unicode decoding; FAIL.
- `server-settings-02`: исходящие RPC уже есть, но cache threads не завершились;
  timeout/forced cleanup FAIL. postrun/python.log остался baseline, поэтому он
  не является свежим чистым логом этого run. Runtime/capture сохранены.
- `server-settings-03`, `rpc-layout`: original construction/calls изучены,
  начальные RPC ещё не обработаны сервером; sync NOT_READY.
- `sync-01`: native transport ACK и stream CRC проходят, но ошибочный RPC0x4c
  не вызывает onCmdResponseExt; sync=False, pending3. Acceptance FAIL.
- Старый generic `outcome.json` native-final содержит ошибочное `base_next_received=FAIL`
  из-за поиска старого log marker и показывает legacy gateway profile. Реальные
  capture/runtime проверены независимо; исправленный runner подтверждён отдельным
  runner-corrected run. Исходные outcome files не переписаны.
- Два static bytecode probes остановились после неверного пути к следующему модулю;
  partial artifacts сохранены в account-full-static/account-dependencies. Наличие
  некоторых JSON без sources.json не считается завершённым probe. Проверенные
  пути повторно исследованы через cache-static/account-more-dependencies.

В успешных fresh python.log остаются только два явно известные сообщения
`Vivox is not supported` от отключённой voice service. Verifier разрешает только
эту конкретную причину; любые другие ERROR/Traceback отвергают PASS.

Все31 записанные собственные PID завершены/отсутствуют, UDP20014–20017 и instance
mutex свободны. Клиенты, локальный config, дампы и ключи исключены из Git,
staged files отсутствуют. Canonical manifest обеих копий совпал с baseline:
`74c37c18e9ac7e30196c134076dacf6f2a8bf3897f7def73905d09feb3647797`.
Сборка offline, новых dependencies нет, pinned vendor tree чистый; версии и
binary SHA-256 находятся в E/dependencies.json.

В ходе карточки владелец уточнил: сайт и игра обязаны иметь один аккаунт,
одну регистрацию и общий account_id/профиль. Это зафиксировано в SCOPE/ARCHITECTURE
и передано сессии сайта. Текущие тестовые реализации временно раздельны;
сквозной website registration → native login не запускался, NOT_RUN.

## Повторный запуск

Из `D:\WoT_9.1_Server`, при свободном native instance mutex и портах20014–20017.
Новая папка обязательна: evidence append-only. Vendor/компилятор уже закреплены;
команды не скачивают зависимости и не обращаются к чужим игровым серверам.

```powershell
. ./tools/rust_env.ps1
cargo test --locked --offline --manifest-path tools/wg_probe/Cargo.toml
cargo build --locked --offline --manifest-path tools/wg_probe/Cargo.toml
python -X utf8 -m unittest discover -s tests -v
$taskRun = 'local/evidence/p02-account-ready-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
python -X utf8 tools/client_audit.py manifest --out "$taskRun/baseline"
python -X utf8 tools/gateway_suite.py --source local/evidence/20261004-p02-account/native-final/01-normal --out "$taskRun/native" --account-probe --account-bootstrap --cases normal,normal,drop-server-sync,duplicate-client-sync,drop-server-first,duplicate-client-first,wrong-password,normal
python -X utf8 tools/verify_account_ready.py --suite "$taskRun/native"
python -X utf8 tools/check_account_ready.py --run "$taskRun/native/01-normal" --negative-run local/evidence/20261004-p02-account-ready/sync-01/01-normal --out "$taskRun/corpus"
python -X utf8 tools/check_gateway_probe.py --source local/evidence/20261004-p02-account/native-final/01-normal --out "$taskRun/gateway-controls"
python -X utf8 tools/client_audit.py manifest --out "$taskRun/after"
Get-FileHash "$taskRun/baseline/original-content-manifest.json","$taskRun/baseline/research-content-manifest.json","$taskRun/after/original-content-manifest.json","$taskRun/after/research-content-manifest.json"
```

Для одного быстрого client experiment заменить список `--cases` на `normal`;
independent verifier по-прежнему обязателен. Повтор статического чтения:

```powershell
python -X utf8 tools/bytecode_probe.py --out "$taskRun/static" --module client/account --record 'PlayerAccount|AccountRepository'
python -X utf8 tools/account_method_candidates.py --out "$taskRun/methods"
```

## Откат и следующий шаг

Каждый run автоматически восстанавливает свой ledger/backup; исходный клиент
только читается. После аварийного завершения сначала сверить owned PID/EXE в
processes.json и остановить только их, затем для незавершённого конкретного run:

```powershell
python -X utf8 tools/client_probe.py restore --out "$taskRun/native/01-normal"
```

Повтор restore уже завершённого run намеренно запрещён. До изменения собственных
исходников сохранены E/project-before.zip и project-before.json (100 файлов),
local config отдельно. Для rollback кода сверять changed-files.json, извлекать
только нужные существовавшие файлы из snapshot и удалять только перечисленные
новые файлы после проверки пути внутри проекта; затем пересобрать offline.
Не распаковывать snapshot поверх изменённой параллельно web/ и не применять
массовый git reset (в репозитории ещё нет commit history).

UNKNOWN: состав минимального настоящего hangar state; normal GUI/bootstrap,
общий канал/fragments/wraparound, игровые account actions, persistence и
web→native identity. Новый поток — только один fragment фиксированных18 B.
Один disposable лабораторный аккаунт не доказывает изоляцию разных пользователей.

**Единственный следующий проверяемый шаг:** исследовать и запустить original
`Account.showGUI` на этом же локальном соединении, зафиксировав первую конкретную
недостающую зависимость/структуру данных штатного ангара. Без перехода к арене
или реализации экономики по предположениям.
