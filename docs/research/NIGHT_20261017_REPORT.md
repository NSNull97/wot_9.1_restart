# Ночь 16–17 октября: проверенный сервер и утренняя приёмка

Итоговый отчёт Root. Все статусы ниже относятся к указанным исходникам и receipts; дальнейшие ручные результаты в него не подставлены.
Задание владельца: непрерывная реализация до 17.10.2026 09:00
Asia/Yekaterinburg (04:00 UTC), без ручных вопросов. Автоматическая проверка
не заменяет native/UI/управление и игру с двух ПК.

## Сохранённая сборка

Рабочая копия `C:/wot091-night-20261017-01/w`; исходный
`D:/WoT_9.1_Server` сохранён. Проверенный HEAD
`200dcd221fb48c019b0939046ac38c18a85061dd`, production runtime
`64767ecdc4af5c45a152309816da381709f20022`, ветка
`codex/build-legacy-entrypoints`. Вся игровая цепочка остаётся вне main:
обязательная ручная приёмка открыта. Main
`ffce8cb660e9e6af6872aa4a5de444f461bc73fe` не менялся.

**VERIFIED: canonical gateway 1619 PASS / 0 FAIL / 5 прежних ignored,
сборка PASS; все 925 исходных файлов совпали побайтно до и после.**
Тесты 1182.74 s, полный driver 1236.83 s. Семь настоящих HTTP/SQLite
композиций независимо связаны с этим полным test executable. Собственные
дочерние процессы завершены; Windows Job закрыт с active=0.

Доказательства, относительно C checkout:

| Файл | SHA256 |
|---|---|
| `local/evidence/20261017-c-final-full01/source-before.json` | `d93dafbf8b3ad10f7b522db37e4f4ec6e9e04bb6e1734919778150425726beaa` |
| `local/evidence/20261017-c-final-full01/source-after.json` | `bea35684fa5fd353e2c97babc24071ca74971f96d62dc145204080cc43c261e2` |
| `local/build/server/gateway-c-final-full01/result.json` | `72036e41cb2884ed6fb7b53a632391d62a24ef9513ea97177307b92d39d8a9ea` |
| `local/evidence/20261017-c-final-full01/composition-full.json` | `e2ca06a9084dd2f8eb88bc814583561c303cae0e2144073b24c13295e3da3e70` |
| `local/evidence/20261017-c-final-full01/tested-source-raw.zip` | `d423b9f8272295b32c6ce487d03a8bdba771f4feb1f13baf4c1a3721705f85bc` |
| `target/debug/sr-gateway.exe` | `1fb725ed11373b066db25a8e3fa85b30dc4e6dd96127dc18084a4d7dd0973f0e` |

Команда актуального полного прогона сохранена в OS Temp
`wot091-night-workspace-kcadgetk/full-final03/run.py` и его `result.json`;
канонический дочерний вход — `python -B -X utf8 server/build.py gateway
--test --out local/build/server/gateway-c-final-full01`. Каталог уже занят:
повтор требует нового имени и нового source/evidence receipt. На C не нужен
флаг `--cargo-temp-target`. Пять ignored — прежний долг, не новые PASS.

## Что реализовано и проверено

| Область | Конкретный результат | Граница доказательства |
|---|---|---|
| P06T, правило владельца | Уничтожение непустой БК даёт одну гибель и потерю всех оставшихся loaded снарядов, включая барабан; fired/lost/remaining раздельны, depot не списывается. Пустая БК не детонирует. | Реальный World/Trace и HTTP/SQLite; новый отрыв башни, FX и звук native NOT_RUN. |
| P08B | Настоящие резерв/Finish/restart/CAS; Hold5 сохраняет резерв и тело вышедшего игрока до исхода, повторный вход не создаёт второй Avatar. | Проверены две и четыре исходные owned-учётки, HTTP/SQL и реальный бой World; transport/ACK/clock в этих тестах authored. |
| P08C | Поздний результат раннего выхода связан с единственным итогом боя; полный result не списывает инвентарь второй раз. | Persist/reopen/1500/1501 проверены; новые native цикл/захват/таймер/уведомление требуют утра. |
| P05C / P07B | Общая сцена, смешанные профили, contact и серверные interest/appear/leave пути включены в общий software-набор. | Таран, повторный засвет и шесть живых клиентов утром; число synthetic actors не выдаётся за живых игроков. |
| P04M / P06T | Старые пять профилей и отдельный seven-LAB; WT E100 128 мм имеет шесть снарядов, FV183 HESH — 275 мм из проверенного #717. | Новые admission остаются закрыты до qualification владельцем; WT150 не получает ёмкость WT128. |
| P10B | Training Loss4: компенсация запуска → новая комната того же run → Admit/ACK → Finished и освобождение claims. | Training+Hold5 закрыт; UI/N игроков native NOT_RUN. |
| NET-02 | Own-host LAN encrypted Login → RunOpen4 → advertised Base → первый Base пакет, отдельная диагностическая SQLite. | Это собственный IP, не второй ПК; firewall/NAT/публичный хостинг NOT_RUN. |
| Гаражный Fresh | Known reply сохраняется до readonly Fresh retry; identity/cache/pool/cursor и native delta публикуются атомарно. Две mutation Loss4/Hold5 не повторяются при retry. | Настоящие HTTP/SQL и backpressure; причина пользовательского микролага UNKNOWN. |
| Склад | Шесть исходных shell refs доступны перебору родного склада; реальные количества и экономика прежние, покупка остаётся закрыта. | Python9 и Web11 PASS/0skip; само окно склада native NOT_RUN. |
| `--legacy` | Восстановлены Rust root aliases и C# compile/resources; три старых CLI теста и обе сборки PASS. | Настоящий T26/FV183 BattleScene IPC7 smoke PASS; полный legacy suite/Linux/native NOT_RUN. |

Основные production-файлы: `server/gateway/src/shared/ammo_detonation.rs`,
`detached_turret.rs`, `owner_hold_*.rs`, `late_results_*.rs`,
`server/gateway/src/account/ammo_session.rs`, `ammo_session_fresh.rs`,
`tools/p06t_ammo_loss_store.py`, `p08b_owner_hold_store.py`,
`p08c_late_results.py`, `p04w_shell_display.py`,
`p09e_research_projection.py`, `tools/wg_probe/src/main.rs` и
`tools/map_drive_worker/MapDriveWorker.csproj`. Точные списки, команды,
предыдущие FAIL и откат — в карточках research; старые доказательства не
переписаны и клиентские ресурсы не добавлялись в Git.

## Отдельный следующий P10B-кандидат

`C:/wot091-selection56/w`, ветка `codex/p10b-hold-selection-reader`,
runtime `dbbda9e7e1a0071d0d7f7300e2c776c06e3354be`, checkpoint
`0472ddbc0aa49445ee0315b30e2676dc184c4397` от HEAD200.
Новый read-only selection5-reader проверяет четыре настоящих owned-профиля,
CAS/run/crew/loadout и FrozenHold в одной query-only транзакции. Собственная
проверка 10 PASS и обычный unittest 10 PASS/0skip; WAL race сохраняет
согласованный старый snapshot, затем отвергает старый CAS.

Это 929 raw source, четыре новых файла; старые 925 совпадают. Кандидат не
входит в full925 и утреннюю игровую сборку. Следующие CLI и HTTP кандидаты
описаны отдельно ниже; Rust/native-интеграция и Training+Hold5 остаются
закрыты. Доказательства нового checkout:
`local/evidence/20261017-p10b-hold-selection-reader-01`. Непринятый кандидат
сохранён отдельной веткой и опубликован, main не менялся.

Отдельным следующим шагом реализован CLI: ветка
`codex/p10b-hold-selection-cli`, runtime
`02c25d37f5ae784d57cfa014b57d0e275526a005`, checkpoint
`ed53addea71a5b3623d0a6602caf9dd7c43b23b0`, parent0472.
Обычный postcommit unittest: **18 PASS /0 FAIL /0 errors /0 skip**, 200.682 s;
старый reader10 и новый CLI8 на одном source931. Четыре настоящих owned-профиля
из двух attested DB contexts, 19 реальных subprocess-вызовов, query_only,
повреждённая схема и отказы без мутаций. Исходные925+4reader-файла прежние.
Новый worker принимает только bounded Request9/4096 B, возвращает Reply15/
12288 B; пути и owner задаются доверенными argv, ошибки не раскрывают пути.

Конструктор настоящего OwnerHoldStore кратко открывает RW-capable handle:
текущий конструктор не выполняет DDL, перед методами выставляется query_only;
предварительная проверка открывает mode=ro. Это не гарантия RO с первого
handle. Все подключения закрываются, raw/logical SQL сохранён. Изменены два
новых Python-файла, attrs и docs; Web/Rust/Config/Training5 fence не менялись.
Доказательства в новом checkout:
`local/evidence/20261017-p10b-hold-selection-cli-01`, actual result SHA
`a790b8695dd165689cd1de6829d5cb3f8cc62cb58259097131647f1a3cae90df`.
Root проверила все931 raw-файлы и точный allowlist6, push подтвердил
checkpointed53; mainffce сохранён. В утренний full925 этот кандидат не входит.

Private HTTP bridge сохранён следующей веткой
`codex/p10b-hold-selection-bridge`, tested runtime
`5b8c2b4cfd17f3ce01a9a84701c6404320a3e8a1`, checkpoint
`337ec6184440a3426c53201350657490531183ee`, опубликован с точной сверкой remote.
Явный `/internal/native/room-selection-hold` использует CLI63, проверяет
владельца/Stamp11/весь FrozenHold и хеши; worker 7 s/request 9 s, один worker
на owner, освобождение слота после close, обработка ошибок всех stdio pipes.
Обычные **Node15 и Python18 PASS/0skip**, отдельно прежний Hold HTTP —
**3 PASS** через явно обозначенный DERIVED_TEST_DRIVER: ROOT перенесён в
изолированный checkout, удаление собственного временного fixture отключено,
все assertions и close сохранены. Финальные World-факты этого сценария
AUTHORED; native не запускался. Root сверила raw935, прежний primary925,
allowlist9 и 41 файл доказательств. Durable evidence:
`C:/wot091-selection56/w/local/evidence/20261017-p10b-hold-selection-bridge-01`.
Full935/Rust consumption/native Training5 остаются NOT_RUN; утренний
полный925 не подменялся этим кандидатом.

## Исправления переносимости вне утреннего runtime

В `codex/test-c-short-portability` отдельно исправлены пять тестовых
предпосылок: build-temp reference/target, отсутствующий registration_url,
новые значения network/training_rooms в AST fixture и заведомо внешний cwd
для selection CLI. Production different-drive guard сохранён. Положительная
volume identity у unit-fixture явно AUTHORED; реальная cross-drive Cargo
сборка этим не доказывается. На code `dba0865df380ced679e0d630c51d58a6ed33b41c`
обычный targeted unittest — **41 PASS/0skip**, дополнительно frozen checker —
29 PASS. Документальный checkpoint `54d83e612466544beb196e291900ef64419c765f`.
Primary200/raw925 прежний; прочие920 файлов repair-ветки совпали с200.
Actual receipt `testrepair68-gate01/targeted-result.json`, SHA
`e0e2b0c15e621ae8f9e42ee02e91ee64338d91892346a0940c2b86e523efe072`.
Root независимо проверила все925 raw-файлов, точный allowlist9, документальный descendant и remote checkpoint54d83e6. Семь proof-файлов сохранены в local/evidence/20261017-testrepair-68; root-review-copy-proof.json SHA aa832f5466e80e0135363d5621ef8a8c99ce29cacd9ca3395be5634857b2afd6.

`codex/p06t-profile-map-source` добавляет явный `--map-source` для исходных
двух handling JSON. Их прежние raw pins, предел16KiB и no-link guards
сохранены; рабочие C-конфиги с перенесёнными путями не переписаны. Runtime
`54f1c7f3645d38bc37100c71d4f82c9068daf386`, checkpoint
`ca4955a0016a8de8ec3e9005c2ddbea1c51c086a`. **11 PASS/0skip и реальный CLI
PASS_SOURCE_PROJECTION_ONLY**, включая отрицательную проверку настоящего
NTFS junction; D-исходники до/после те же. Полученные проекты сохраняют
исторические resource paths и автоматически квалифицированной физической
сценой не становятся. Full/новая активация/native NOT_RUN. Доказательства:
`C:/wot091-map-source74/w/local/evidence/20261017-p06t-map-source74`, manifest
`fef8c8898051f023ff2d9de64b5a5a6d1c66fa8b30a16166895606bb1e210503`.

Дополнительная изолированная карточка90 `codex/p02-project-submit-pin`,
checkout `C:/wot091-py27-pin90/w`, runtime
`a6224a9940ef7a9b7b1aec3db2f06dbe5e906678`, checkpoint
`a7c4f1dcb569c8a0a8da547d2108cca60e1c61aa`: настоящий CPython2.7.3 сначала
дал RED1 на старом firstlineno113, затем GREEN1/0skip на115. Аргументы,
freevars/flags и co_code SHA совпали; изменён ровно один собственный AUDIT pin
в `client_patch/hangar_relogin_scenario.py`. `project_auth.py` и все original
WG pins прежние; его код только компилировался, не исполнялся. Обычный Py3
модуль:54PASS/3правдивых SKIP/0FAIL/0ERROR. Job0. Другие924 raw-файла и primary925
прежние. Root independently сверила source/allowlist6/remote и30 durable
proof-файлов. Evidence `local/evidence/20261017-p02-project-submit-pin90`,
manifest SHA783f8d46a9f7036270aafe07d3c2fb89582f9b91b745a6882dcc4d52e382ba42.
Это не новый native relogin PASS и не перепись результата whole06.

## Python и свежие операционные контексты

Полный Python06 завершился фактическим **FAIL**, 2950.785 s, exit1;
3338 tests_run, 3232 addSuccess, 12 FAIL, 45 ERROR и 90 SKIP. Часть ERROR
относится к setUpClass и не увеличивает tests_run — эти счётчики нельзя
просто складывать. Runner failure=null, cleanup=[], OwnJob active0,
source200/raw925 до/после и в worker одинаков. Actual result SHA
`18e0c9316494bad7329de96fa17f2ec89585318b6b95029595313fba2cdd3d3c`,
путь в Temp `python-suite43-successor06/runs/suite06/result.json`.
90 пропусков — 88 отсутствующих закрытых evidence/input contexts, один
требующий Python2.7 bytecode и один отсутствие Windows symlink privilege.
Исторический parser70 отдельно прошёл пять реальных закрытых корпусов,
4092 события, без нового native запуска; это не закрывает весь skipped набор.
Receipt `python43-historical-rows70/result02.json`, SHA
`0004516051d8cd156338613d1e96be32deda4327efa4378a7fc8292b52c42198`.

Actual append-only публикация68 перенесла12 недостающих raw inputs,
8 412 944 B;14 прежних C inputs и D источники сохранены. Relocation67
перенесла два исторических crew/ammo exports с четырнадцатью source members;
оригинальные validators прошли, старые manifest/trace не переписаны.
Receipts SHA соответственно
`0454a1507fab2b5fb8c529f2489d8ce33023a63164f0418f0994815d6dd0d389` и
`644f0e5ffcad1c0d836ff8aa80514e4bf22ded2828ac7bbb4a1abc9f67fcc8cd`.
Root76 скопировала шесть accepted r2 файлов17 376 B, но первая fixture
миграция остановилась на отсутствующем историческом descriptor JSON.
FAIL и partial `local/tests/py72-native-fixture01` сохранены.
Затем78 опубликовал три genuine descriptor/config JSON,84 — ещё два JSON с
проверкой56 прежних members. Оригинальные raw pins и исторические manifests
сохранены. Новая migration79 во fresh py72-native-fixture02 действительно
прошла; receipt SHA232b6735f0b31ec57646ccb41f67d54a3919bf73c08d8517ed146a2432bcd68e.
Старая partial01 не стиралась.

Focused72-02 на неизменённом primary925: **471 tests_run,436 successes,
1FAIL,18ERROR,24SKIP**,47.1747s, exit1; runner failure=null,cleanup=[],Job0.
Receipt python-focused72-successor02/runs/failed01/result.json SHA
431b40cdd8f560bc3ce07b7deeb38dc8736467f2bb04093c4080b2a964b6e9f9.
Три исходные exclusions фиксированы до запуска; новые падения не исключались.
Отдельные68/74 ремонты не подмешивались. Все120 дополнительных inputs
побайтно сохранены. Остались реальные historical-D/source-root contracts,
неполный private corpus и raw-pin/path relocation конфликты; это FAIL.

Append88 затем **действительно** скопировал17 недостающих project-generated
inputs42,797,596B и проверил один прежний manifest; старые120 inputs и source925
сохранены. Шесть архивных OWN source-файлов не исполнялись, geometry vectors
связаны исходными manifest. Receipt python43-tail-inputs88/apply01/result.json
SHAbdd2db8f7e0a8e6e2242b52f97663a605952df95bfba3db48eedbed7fe7518db.
Последующий обычный gate88: **182 tests_run/181 successes/0 assertion FAIL/
1ERROR и4 class-setup SKIP**,28.4377s, exit1, runner failure=null/cleanup=[]/
Job0/source925+316 inputs до/после одинаковы. Четыре модуля: compound catalog,
map geometry,map-drive acceptance,hangar limits. Единственная ERROR:
исторический real119 export привязан к трём LOCAL source paths на D, текущий
inventory — к C; пять file SHAs одинаковы, strict source/spec guard правильно
отказал. Paths/старые manifests не переписаны. Четыре пропуска — отсутствующие
закрытые Limits corpora. Receipt python43-tail-inputs88-gate01/runs/four01/result.json
SHA073a98e8cf850adfdb0ecd6fd82314a2b5ccd57f507b3b16c5aa90c6da03902a.
Это ещё один фактический FAIL, не замена whole06 зелёным.

Actual data-only preparation: morning61 —
`FOUR_CONTEXTS_PREPARED_BOUND_NO_LAUNCH`, NET61 —
`C34_PREPARED_BOUND_NO_LAUNCH`. Новых grants0; install/services/native на этом
шаге NOT_RUN. Операторские команды получены из actual prepared binding,
их SHA не подставлялись вручную. Корень helpers/evidence в OS Temp:
`C:/Users/NSNull/AppData/Local/Temp/wot091-night-workspace-kcadgetk`.

- `morning61/INPUT-morning61-final.json`, SHA
  `eb6f85d352801e814cd1f8f70d25f7d5f426bae0df7953f554b853f2d26c5f15`.
- `morning61/evidence/morning61-final/result.json`, SHA
  `f3fe1a91954bfd9970d3641aba54d1c059682bce666f3fd27c54dbc1b00617dc`.
- `morning61/evidence/morning61-final/operator-commands.json`, SHA
  `86b55d06a72f05c4c541b3fcfbf03df09d74c3427f7da68a2d68aff370e151e9`.
- `net61/evidence/net61-final/result.json`, SHA
  `4c32f7235c981ae694b2937d02d07d3fcc7fa1a2b79fef0993042c4b8d7602e3`.
- `net61/evidence/net61-final/operator-commands.json`, SHA
  `e1b2776a08f293319fd61cdff4152d23366ee83dc9d6f1f899a8e42bee3a5716`.

Свежие независимые data contexts —
`local/stands/night-battle-20261017-03/unified-01/core-loss4`,
`unified-01/rooms-loss4`, `hold5-01`, `lab-seven-01`; сетевой —
`local/stands/net02-loss-ownhost-c61-01`. Основной, rooms и Hold не делят
mutable SQLite. LAB использует свою квалификационную копию и не открывает
owned admission новых машин.

Независимый actual readonly SQL63 подтвердил в трёх C03 owned-контекстах:
A129/B43, loaded A[0,48,48]/B[0,50,46], depot A[114,48,46]/B[114,49,48],
active0, машина available; raw main/WAL/SHM/journal до/после одинаковы.
Receipt `core-depot-confirm63/receipt.json`, SHA
`b8de8f836e8b55dd63036d4e6380fc2355e3da3b22fe4f4b64568fa88a2e50a9`.
Никакой reload этим readonly-аудитом не выполнен.

Старый actual morning31 prepare сохранил FAIL: после backup и публикации A
публикация B отвергла старый D bundle посредством штатного C/local guard.
Partial `local/stands/night-battle-20261017-02` не повторять и не удалять.
Следующая versioned61 closure меняет только проверенный путь bundle на
побайтно одинаковую C-копию: 57 файлов / 292090 B, manifest
`d99f2ba765e39d096cf2d0858c9864ed897a36eb9c4ea6972a15385e2355b2db`.
Оригинальный клиент и его пути не заменялись; старые helpers31/34 сохранены.

## Реальные запуски служебных процессов

Startup62 действительно поднял четыре режима, получил health и штатно
остановил восемь процессов, но parent ошибочно сравнил SQLite tuples с JSON
lists. Его FAIL receipt сохранён. Отдельный83 исправляет только строгую JSON
канонизацию отчёта; bool/int остаются различимыми.23 pure guards PASS.
**Actual83 PASS_FOUR_SERVICES_BOUND_HEALTH_OWN_STOPS:** четыре BOUND/health,
восемь обычных stops, exit0/Job0, все8 DB raw и logical строки прежние,
grants0/auth0/client actions0. Receipt own-service-startup83/evidence01/result.json
SHAbe36e4b599551b5d18c9cc9760b745b16e689a251a76935f87c945f0178b189a.
Это новые startup-*31-02 runs; утренние native runs ещё не заняты.

**ActualNET69 PASS:** own IP192.168.1.101/interface7, UDP20240/20241,
privateHTTP127.0.0.1:3492. Два real encrypted Login→RunOpen4→advertised Base→
первый Base пакета и два собственных штатных stops. Receipt
net-ownhost-run69/evidence01/result.json SHA
d86eb33c7facd563fb08bae8fcbb7cb364e457a7e18ad2d8a7aea97b075bb856.
Diagnostic revisions130/44, loaded/depot прежние, grants/reservations0;
только ожидаемые timed auth counters изменились. Это НЕ Account init/Avatar,
НЕ второй ПК и НЕ WAN. Job0, source925 прежний.

Final readonly audit87 подтвердил три owned C03 контекста129/43, указанные
ниже loaded/depot, отсутствие active battle; отдельный NET130/44. Все10
процессов83/69 с их точными creation/image receipts отсутствуют. Старые
четыре D DB/WAL raw hashes сохранены без открытия D SQLite; V7 installed96 и
ledgers/exes прежние, оба own client mutex отсутствуют. Receipt
morning-final-audit87/report.json SHA
dfa21cd273789b54a5e9a10633281c3346dd2d1f37bf06d1645c5fd120ffc520.
Это проверка согласованности, не native приёмка.

**Actual95: Core/rooms/Hold private auth PASS.** Каждый режим получил два
HTTP200 с exact own UUID/nativeID/name/preparedfixture;6 запросов и6 обычных
собственных stops. Все game tables кроме проверенных auth counters, все Web
таблицы и весь fixture member-set/bytes прежние. Ни queue/бой/резерв/grant,
ни client control/install/Popen не выполнялись. Worker0/Job0/cleanup=[],
source200925 до/после тот же. Receipt morning-auth95/evidence01/result.json
SHA2ed7b8e482096135349b3956e5e7577e03432f9db6971ccfd97df282e9dcdd98.
Root проверила согласованность всех трёх actual receipts; это дополнительная
серверная проверка входа, а не native Account/UI PASS. Утренние run-имена
не заняты: использованы отдельные auth95-core/rooms/hold-01.

Будущий launcher78: frozen28,9 pure guards PASS, passive plan/help PASS;
preflight честно отказал из-за отсутствующего ещё V8 install-plan, до auth/
control/Popen. Только Core/rooms/Hold. Новый89: frozen37,12 pure guards PASS,
отдельный T26 LAB и scoped source review. Оба требуют UTC>=04 и явный
--execute-client-action, оба проверяют own copy/ledger/bytes/PID creation,
для B — реальный текущий A и два свежих hangar события. Новая native часть
не запускалась. Никакого автоматического queue/shot/exit таймера.
Actual89 поднял обе собственные LAB службы, но первый private identity
запрос отказал: **FAIL_PRIVATE_LAB_AUTH_REFUSED**. Точный HTTP статус не
сохранился в frozen89 и остаётся UNKNOWN. Обе службы штатно остановлены,
wrapper exit1/Job0/Job closed/no cleanup errors; native/control/install NOT_RUN.
Root readonly postfailure audit подтвердил все game profiles/resources,
metadata, web tables и fixture bytes прежними; изменились game_limits,
точные process incarnations отсутствуют. Receipt root-lab89-failure-audit.json
SHAb696ac2424c653ccae44e3b3899935db55105e13cc99a327ee75e0f299e83b09.
Production validateAmmoFixture отдельно фактически отверг C classic fixture:
его historical r3 manifest ссылается на D r2-base, а текущий verifier требует
C sibling. Это VERIFIED relocation gap; связь именно с наблюдавшимся HTTP
отказом пока INFERRED. LAB native запуск блокирован до исправления genuine
fixture closure и нового успешного HTTP gate. 89 frozen source не переписан.
Дальше genuine92 producers пересобрали A2→A3→A4 и B1 в отдельном C
output. Пять C/D producer sources совпали;16 profile/state/shop/dossier payload
файлов побайтно равны старым. Current production Node validator для новогоA4
PASS, B encoder21checks PASS. Исходные manifests не переписывались.

Actual new operational92 prepare отказал ДО writes: старый startup83 PID уже
переиспользован Windows, чтение его текущей incarnation получило WinError5.
Новый98 закрепил ровно один уже завершённый launch/stop по SHA, normal83 Job0 и
87 proof отсутствия исходной incarnation; для остальных PID guard прежний.
Root сверила frozen21 и code diff, но actual98 prepare сохранил другой FAIL:
после intent первый backup отверг новый target. В partial lab-t26-92 только
intent/failure, DB/token/fixture/service не созданы. Ни удалять, ни повторять
этот каталог нельзя. Root logs lab92-root-actual01 и lab98-root-actual01
сохранены. Frozen92 SHA250d82eb0939b3da049b55a3e38d3bd9c08ba41c6adc79f2a7632c8a9d191d4e;
frozen98 SHA2c10c301e5994c68d8051a0b5e2fe43457f9314d88a47eed44a4808733ac5b3e.
Это реальные операционные отказы, а не native сбои.

Source-only97 auth-кандидат ещё не запускался без действительного binding;
новые92/98 helper API не имеют install/native launcher. Поэтому даже genuine
fixture PASS не превращает новый LAB в готовый native запуск. Старый89 и его
команды остаются BLOCKED. Дальнейший99 ниже учитывается только при отдельном
actual receipt; отсутствие такого receipt означает NOT_RUN.

**Actual99+97/02 затем PASS.** Новый `lab-t26-99` использует ровно два
mode=ro/query_only SQLite backup в новые C targets через отдельный закрытый
helper; generic output guards не менялись. Источники D raw/logical прежние,
новые DB логически равны source; все fixtures произведены настоящими текущими
C tools. Prepare295,788B/grants0, prepared.json SHA
5ddb3c8376d8776c331abc45b1e7241b5d6aeb481e2dfe243962e57aecfe1868.
Actual binding-c99-lab99-final.json SHA
ccabbd5252cc9ab5105cfdc7d61ecd0c9dba8d17bfd8e434be52148bccf27e8c.
Frozen99 SHA4c9425ad21909745a8fb87fe35cbc097843c59ff272d8c30db0493bc59806668.

Отдельный own HTTP97/02 реально получил **200 у A и B**, exact UUID/native1/2/
nickname/новый preparedfixture. Все game profiles/resources/metadata, все
Web-таблицы и fixture bytes/set прежние; только source-derived game_limits
изменились. Оба own процесса остановлены обычными exact stops, worker0/Job0/
Job closed, ошибок cleanup нет. Parent receipt SHA
0403d2487c506531d54e53fe0c6ad93a88217deb6925ba82f3c7ffe7a75eeb23,
worker SHA325fcfdbb47d926c5a78af73847012c8a54dc906a54034d2a6d2b1f066c8231d;
папка OS Temp `lab-auth-probe97-successor02/auth-probe97-output01`.
Root послеauth повторно проверила actual99Binding и все925 исходных SHA;
completion SHAce86524bd6f80c3d5f9ddb39998d8add85f3487a62ed2fc5228c6d975c75592c.

Это исправленный и проверенный **server-only T26 context**, не native launch.
Нового launcher/install API для99 нет, старый89 жёстко закреплён за другим
контекстом. LAB native этап остаётся BLOCKED до отдельного адаптера; Core/
rooms/Hold78 от этого не зависят. Старые89/92/98 FAIL не переписаны.

## Резервная копия операторских доказательств

Создан и повторно прочитан конечный ZIP из 222 файлов / 2 321 362 B:
`local/evidence/night-ops-recovery-02/operator-helpers.zip`, SHA
`d763511edcdab34e0584323955152a21da2f01c04946e41e1e977c62a62721d7`.
Все имена, размеры и SHA членов проверены, исходные файлы до/после одинаковы.
Это конечный архив helpers и metadata, без SQLite, секретов, клиентских
ресурсов, executable и toolchain. Manifest SHA
`ccf0c82f8aeda2a8cd08f4f27d7b34c0e36d4b342b8757de4fb23cfaa0c1d2a0`,
receipt SHA `7b5010c23f2b657c40cf4661596b85b8acc8cf6d7237d33ee3ac7e276434c6f5`.
Автоматическое восстановление не реализовано и не проверялось: оригинальные
абсолютные пути существенны. Отдельный raw925 source archive указан выше.
Startup62, NET69 и более поздние диагностические wrappers в эти222 не входят.
Отдельный actual93 supplement:83 selected metadata/source files1,965,869B,
ZIP84members с inventory,785,813B. Все members повторно прочитаны по имени/
типу/размеру/SHA; original222 и source925 прежние.10 других proofs только
referenced, не включены payload. Поздние92/95 в этот фиксированный набор
не входят. `local/evidence/night-ops-recovery-03/operator-tail93.zip` SHA
97925248e504123b7b57f7eda6b497de2315d84cd9243db6058f57e7c167f643,
result.json SHA4214db9e02eb9e80dabc3bb8094bd86f6a52bab6aeff458be86150694ccbe732.
Restore NOT_RUN; это выбранные metadata, не резерв всех mutable БД/ресурсов.

Последний actual append04 сохраняет58 конечных файлов259,829B — frozen99,
97/02,95 и выбранные завершённые public receipts. ZIP+manifest59members,
исходные размеры/SHA до/после одинаковы; DB/key/token/control/client assets
отсутствуют. `local/evidence/night-ops-recovery-04/recovery04.zip` SHA
242317744948c4648b790b5a2b4162f22acfdc776591bf8cbb4ad306ea71b69d.
Статус PASS_FINITE_PRIVATE_RECOVERY_APPEND04; автоматический restore NOT_RUN.
Эти архивы дополняют друг друга и не заменяют mutable owner DB backups.

## Единый сценарий на утро

Полный порядок с точными PowerShell-командами: [утренний запуск](NIGHT_20261017_MORNING.md).
Он использует actual morning61 bindings и отдельные frozen78/89 launchers.
Ночью client install/rollback/native launch не выполнялись; старые V7 overlays
сохранены. Перед утренним запуском требуется реальное действие владельца,
04:00UTC само по себе клиенты не запускает. Сначала Core client-commands,
затем rollback BOTH, prepare BOTH, install BOTH; rooms/Hold переиспользуют
CoreV8. LAB — отдельная перекладка обоих overlay и только T26 у launcher89.

1. Основной Core: профиль13, отмена/повтор очереди, общий бой, красный маркер
   противника у обоих, движение/наведение/ручной выстрел. Автоприцел пока должен штатно снять цель и вернуть мышь без выброса; полноценный захват не реализован.
2. В каждом окне один КС и один ОФ в землю → ручной выход обоих → остатки
   A[0,47,47], B[0,49,45] и отсутствие чёрного экрана → повторный общий бой.
3. Естественный исход, уничтожение, захват и таймер отдельно; личные/командные
   урон/фраг/засвет, ранний выход и поздний результат, повторный вход.
4. Смешанные машины/таран и повторный засвет, затем training Loss4 в отдельной
   копии данных. Шесть клиентов проверять только при их фактическом наличии.
5. Отдельный Hold5: выйти первым, оставить тело, повторно войти без второго
   Avatar, дождаться настоящего Final, проверить разблокировку/расход один раз.
6. Детонацию БК делать последней в каждом независимом контексте: непустой БК
   → машина погибла/башня/FX; после боя loaded=0, fired/lost без повторного
   списания, depot прежний. Для продолжения штатно загрузить 96 ББ из depot
   114 → 18 у каждого; сам native reload ещё NOT_RUN. Старый HE loadout целиком восстановить нельзя:
   A не хватает 2 ОФ, B — 1 КС; не выдавать боеприпасы и не откатывать БД.
7. Seven-LAB отдельно от owned admission: пять qualification CLI choices, текущий89 запускает только T26; затем реальный второй ПК и scope,
   когда IP второго ПК известен. Own-host probe не заменяет эту приёмку.

## Ветки и изменённые файлы

Точный основной список427 code/config/test paths от mainffce до tested200:
[NIGHT_20261017_FILES.txt](NIGHT_20261017_FILES.txt), SHA
9ffb6d11034040380c2ae567c2a9a255d0d1a40e3bc2ed4c0c58c9b2eb22b25a.
Отдельные кандидаты ниже не входят в основной full925.

| Ветка codex/ | Сохранённый checkpoint | Проверенный объём |
|---|---|---|
| build-legacy-entrypoints |200dcd221fb48c019b0939046ac38c18a85061dd| canonical full925; docs-only финальный descendant указан в git |
| p04m-garage-fresh-publication |761abf9750f8e96c2c1fc356b2cbd59adcf40ea5| Fresh HTTP/SQL/атомарный native delta |
| p04w-shell-depot-display |bf499c229d26cce317353e59b33452ba8e4d0738| Python9/Web11, затем full925 |
| p10b-hold-selection-reader |0472ddbc0aa49445ee0315b30e2676dc184c4397|10 ordinary PASS |
| p10b-hold-selection-cli |ed53addea71a5b3623d0a6602caf9dd7c43b23b0|18 ordinary PASS |
| p10b-hold-selection-bridge |337ec6184440a3426c53201350657490531183ee|Node15/Python18/derived3 PASS; full935 NOT_RUN |
| test-c-short-portability |54d83e612466544beb196e291900ef64419c765f|41 ordinary PASS, production unchanged |
| p06t-profile-map-source |ca4955a0016a8de8ec3e9005c2ddbea1c51c086a|11 ordinary PASS/actual CLI projection only |
| p02-project-submit-pin |a7c4f1dcb569c8a0a8da547d2108cca60e1c61aa| realCPython2.7 target1PASS, Py3 module54PASS/3SKIP |

Исторические parent checkpoints цепочки сохранены; actual D refs повторно
прочитаны03:32UTC. Это точки истории, не дополнительные утренние runtime:

| Parent branch | HEAD |
|---|---|
|codex/net-02-loss-integration|33d964ed49090fb9b3722cfbe173fd72540b8d09|
|codex/p04m-five-battle-profiles|2340236a1e690e36d617130c054e2ce7e62f685e|
|codex/p05c-shared-physics|9f2df41ac126921c7f4ae3cd63f8555a6fa7d1a6|
|codex/p05c-shared-scene-night|9c269104beb2d21c94d75304f6f1502d6e4d8a24|
|codex/p06t-ammo-rack-detonation|4786c2aa82c0bfbcb56b104f7b9c6038e5b3ba86|
|codex/p06t-seven-loss-integration|91dbdbed6dbb6dd5f230a55d3da78d682907b509|
|codex/p07b-server-visibility|e71184450f5f83fbafcea485a8ed179db4d1b056|
|codex/p08b-owner-battle-hold|3675a486e3cadee5fd08277dee97e32a7d909a02|
|codex/p08b-profile13-battle|c7999e6aa56216cf309e47b6768cbef4be593db7|
|codex/p08b-restart-cas-composition|628921650319e1e5cd142ff494289c1436a12015|
|codex/p08c-battle-lifecycle|2ef781f67de0a50f3e7d6456934b3b460572906a|
|codex/p08c-late-owner-results|5c86c03ddaa8a252018360ee0fa3fdb8e6bd4f54|
|codex/p08c-native-marker-team|972843ae4e9bf8528af70ba07ae9db7a30fe0e5d|
|codex/p08c-natural-results-return|1e87e1b4c11d19185cce1739bb84388cdedc06bb|
|codex/p10b-loss-training-integration|bce643fad4291b6f40b31140c0c711bb784a1cd9|

Новые checkpoint-ветки из первой таблицы опубликованы в night-upstream с проверкой remote SHA;
непринятая цепочка не сливалась в main. Старые runtime/readiness evidence
относятся только к собственным HEAD, а не ко всему925 по наследству.

## Ограничения и откат

Actual disk snapshot03:29:36UTC: D free34,975,744B (~33.4MiB), C free
52,780,523,520B (~49.16GiB). Поэтому сборки/intermediates/new evidence выполнялись
на C. Исторические данные/клиенты на D не удалялись и не переносились; большого
свободного места на D нет. Это отдельное ограничение утреннего запуска.

Микролаг86: SOURCE_REVIEW_ONLY, cause UNKNOWN. Проверены inline capture I/O,
World/Session clones/LOS и off-thread IPC; явного10s gameplay timer в этой
цепочке не найдено. Flush не назван physical fsync, гипотеза не названа
причиной. Новый timing experiment/native reproduction не выполнялся.
Evidence в OS Temp: microlag-source-audit86.md SHA
6b420424e8a59f0bab03ef017b6876f1dec512e2df8a0092d8c7f2655152bf21.

Native/UI/audio/управление новых сборок, шесть клиентов, новый полёт башни,
реальные два ПК и публичный стенд остаются NOT_RUN. Утром не считать принятыми
родительские карточки по старым подтверждениям coreV7. Веха первого боевого
теста не закрыта.

До Final нет per-shot WAL; recovery использует явный aborted_restart из
frozen-резерва. Закоммиченный Final повторно не возвращает снаряды. Training5
закрыт. Оборудование/слоты/продажа/P04L не подключались: сохранённый P04L
кандидат несовместим с новым writer без отдельного переноса. rustfmt NOT_RUN:
закреплённый formatter отсутствует. Причина микролага UNKNOWN.

Откат: остановить только собственные процессы по PID/exe/creation receipt,
использовать предусмотренный client ledger rollback и совместимый code/binding;
новые owner базы с расходом не заменять историческими backup. Для исходников
использовать сохранённый raw archive и соответствующую ветку, а не смешивать
новый exe со старым source receipt. Старые CoreV7/оригинальный клиент сохранены.

Software gates закрыты только в указанном объёме; обязательные native gates
открыты, merge в main не выполнялся. Единственный следующий шаг владельца —
пройти основной Core-сценарий из actual утреннего операторского файла.
