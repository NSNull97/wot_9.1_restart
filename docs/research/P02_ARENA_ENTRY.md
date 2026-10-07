# Native Account → Avatar → собственная локальная арена

2026-10-05. «Стальной рубеж», GAYmDev Stutio. Одна карточка по
`docs/plans/P02_arena_entry.md`. N=`local/evidence/20261005-p02-arena-entry/`.
**PASS узкого native checkpoint:** Account → Avatar → Карелия → собственный
МС-1, родные модели и Battle/HUD, штатное завершение. Vehicle03 прошёл17/17
независимых проверок. Это первая отрисованная локальная арена, ещё не готовый
бой: экран «Ожидание игроков», лабораторное размещение, нет проверки физики,
движения, стрельбы, переноса боекомплекта в Avatar или второго игрока.
Полный P02 остаётся PARTIAL. Итоговый контроль файлов/профилей/обычной установки:
`N/final-audit-02/final-state-audit.json`; результат этого отдельного аудита
не подменяется PASS native checkpoint.

## Исходное состояние и сохранность

Оригинальный клиент #717 только читается. EXE SHA256
`86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed`.
`N/baseline-01/`:336 authored-файлов в ZIP/manifest,17 локальных файлов,
два согласованных SQLite backup, integrity_check=ok. Перед снятием normal010
проверены25 неизменяемых файлов, три свежих owner log сохранены отдельно;
штатный rollback и восстановление этих логов записаны в
`N/normal010-prerollback-01/`. Изменения профилей в эту карточку не входят.
Primary остаётся profile4:МС-1 с2 танкистами и20ББ; secondary profile1.
Прежний `local/client-profile-002` сохраняется, кэш не очищается.

Каждый клиентский запуск использует отдельные compiled/backup/postrun/ledger,
проверку mutex, собственную loopback-авторизацию и original LoginView submit.
Нет управления мышью/клавиатурой, внешнего таймера или принудительного kill EXE.
Диагностическое завершение обусловлено наблюдением клиента или явной ошибкой.
Сайт остаётся существующим внешним процессом; supervisor им не владеет.

## Проверенные этапы

| Запуск | Фактический результат | Ограничение |
|---|---|---|
| export01,PID9316,46packets | PASS: original Account прочитал ArenaType1/ctf/Карелию,11 исходных pins;exit0/restorePASS | Это экспорт ресурсов, не загрузка мира |
| base01,PID89400,205packets | FAIL: native Avatar callbacks прошли, наблюдатель отверг spaceID=None;exit0/restorePASS | Ошибку наблюдателя сохранили, не переписали trace |
| base02,PID11592,151packets | PASS:14/14 независимых gates, оригинальный Avatar BASE;exit0/restorePASS | Cell/геометрия/Vehicle ещё отсутствовали |
| space01,PID111936,46packets | FAIL до trigger: наш guard отверг original old-style Python2 class;exit0/restorePASS | Исправлен guard с exact-class проверкой, подклассы не разрешены |
| space02,PID76016,162packets | Geometry PASS, clean runtime FAIL:14/15 gates;exit0/restorePASS | Native teardown поймал AttributeError звука башни, Vehicle отсутствовал |
| vehicle01 | NOT_RUN: подготовлен, но не установлен и не запущен | До запуска уточнено чтение original BOOL→UINT8, старый пакет сохранён |
| vehicle02,PID66212,622packets | FAIL: настоящий Vehicle constructor и roster прошли, prerequisites/world отсутствовали;exit0/restorePASS | Исчерпаны239 наблюдений; свежая original ошибка звука при закрытии сохранена |
| vehicle03,PID73668,172packets | PASS:17/17 gates,4 готовых наблюдения за3.012s, родные МС-1/Карелия/Battle;exit0/restorePASS | 65.4751793s от запуска до завершения; игровой цикл не реализован |

Результат base02:
`N/data/verify-base02-final-02/avatar-base-native-verification.json`, SHA256
`eb50563af245b79254699616c10646830d8bc7f70a2ee47d18f3230eab8e66b6`.
Исторический base01 FAIL:
`N/data/verify-base01-final-02/avatar-base-native-verification.json`, SHA256
`26e127ad1cf47d6d3017502a2bdb2dfcc8f993b116a44ce5145129ed2e1c6f55`.
Результат space02:
`N/data/verify-space02-final-01/arena-space-native-verification.json`, SHA256
`690b5ff98b8d4b0443087a7ede7bdb23fa13b21555617456ec1e2c6eb2d19bec`.
Независимая проверка GUI:
`N/gui/space02-native-review-01/result.json`, SHA256
`e8c599c1fe8f5fd5b20dbea4ecf1ee6e62d72603d65af052149fb3f33d9f8b00`.

## VERIFIED и OBSERVED: реальный транспорт и геометрия

Original .def, bytecode и PE registration исследованы в `N/wire/CONTRACT.md`,
`static-audit-01/`, `roster-contract-03/`. Клиентские type ID Account0/Avatar1/
Vehicle2 установлены по оригиналу; ordinal из entities.xml не подставляется.
Последовательный Avatar BASE имеет9 полей, cell4. Размер variable ARRAY —
signed32, не однобайтовая STRING length. Методы сущностей server→client начинаются с0x3b.

Base02 на одной настоящей авторизованной сессии получил50байт reset/createBase;
original Avatar.__init__110/return212 и onBecomePlayer147/882 прошли штатно.
Сохранился тот же AccountRepository. Реальный spaceID=None корректно записан
как недоступный; position/spaceLoadStatus для такого Avatar не вызываются.
Клиент сам отправил post-reset enableEntities09. Это отдельное native наблюдение,
а не круговая проверка собственного codec.

Space02 после настоящего09 получил144байта cell+space. Native Avatar
onEnterWorld388/316 и onSpaceLoaded535/33 завершились. Последнее наблюдение40:
space1,inWorld=true,loadStatus=1.0,geometry=`spaces/01_karelia`,stepsTillInit1,
worldDrawEnabled=false,userSeesWorld=false,Vehicle отсутствует. Именно это
подтверждает загрузку геометрии; нарисованный бой из такого состояния не следует.
Queued geometry note58.411s — время выгрузки заметки наблюдателем, не точное
время engine callback. Сам original onSpaceLoaded59.431687–59.431863s.

Avatar помещён в координаты из исходного space.settings:
[-58.499908447265625,33.770267486572266,-445.81304931640625]. Это выбранное
лабораторное размещение, не подтверждённый физический spawn/контакт с грунтом.

## Почему normal return не означает отсутствие ошибки

Space02 fresh python.log suffix1654байта относительно проверенного backup
содержит original Avatar.py472 traceback: VehicleGunRotator.destroy124 →
_PlayerTurretRotationSoundEffect.destroy940 обращается к отсутствующему
__manualSound. Avatar.onLeaveWorld ловит исключение внутри и возвращает948.
Независимый verifier проверяет и callbacks, и свежий лог, поэтому даёт FAIL.

Original VehicleGunRotator.pyc SHA256
`d0105237b62447fee170cbf17984fd48437115087d6af6bf44743cc0cf68576a`:
constructor912 не создаёт звуковые поля; init_sound919 создаёт их из настоящего
vehicleTypeDescriptor. Единственный измеренный штатный caller — финальная
ветка Avatar.__onInitStepCompleted2579 после четвёртого шага. В space02
остался один шаг, descriptor отсутствовал. Подстановка полей, пропуск destroy
и подавление traceback не являются исправлением и не применяются.

## Опровергнутая гипотеза порядка появления Vehicle

Vehicle02 подтвердил type2, original Vehicle.__init__44/129 и правильный roster,
но не prerequisites/onEnterWorld/startVisual. Независимый отрицательный отчёт:
`N/data/verify-vehicle02-negative-01/arena-vehicle-native-verification.json`, SHA256
`659c14e32d1ba532b1423ba4f68bc57a0bbcc5c24bafad62e9e7b25db51c9d35`.
GUI review `N/gui/vehicle02-native-review-01/result.json`, SHA256
`d56d5fa219bd783a44289dfd61f0c9560501171c1de73d0eee347c2574626247`.

Предложенный по неполному статическому анализу порядок createDetailed→enterAoI
был INFERRED и настоящим запуском опровергнут. После318B server body клиент
отправил sequence18 `08 04 00 03 00 10 09`: сообщение08/VAR2, payload4,
свой entityID0x09100003. В оригинальном PE cached-entity ветка enterAoI
проверяет isClientOnly: [entity+0xc]>=0x40000001. Для нашего серверного ID
проверка ложна, поэтому native идёт к requestEntityUpdate, минуя prerequisites.
Путь для серверной сущности: объявление AoI → настоящий запрос08 → описание
createDetailed; pending enter-count затем разрешает prerequisites. Этот факт
зафиксирован отдельно, прежняя гипотеза и FAIL-результат не переписываются.
Исправленный native обмен проверен отдельным настоящим запуском vehicle03.

## Принятый Vehicle03

Независимый итог:
`N/data/verify-vehicle03-final-01/arena-vehicle-native-verification.json`, SHA256
`42a55da5b88e3f2a2105c013e260fc6a70559007f5b136abc6520d6822fa19f2`.
Все172 datagrams/6730байт связаны с одним собственным авторизованным каналом.
После actual09 сервер объявил cell/space/roster/AoI221B, reliable sequence40.
Настоящий08/VAR2/ownVehicleID и ACK именно40 разрешили однократный97B
createDetailed. Неподтверждённый последующий heartbeat не блокирует этот шаг.
Сервер проверяет аккаунт, profile4 и неизменный fixture; произвольные ID,
ранние/повторные запросы и некорректные ACK не создают новые машины.

Родной Vehicle прошёл ctor44/129, prerequisites99/190, onEnterWorld126/169,
startVisual562/407. Четыре native Avatar init return:101/101/101/640.
Final stepsTillInit0, original Battle виден, worldDrawEnabled=true,
userSeesWorld=true, четыре части модели видимы. Repository тот же, свои
entityID152043523 и90HP совпадают с сервером. Это OBSERVED на закреплённом
клиенте #717, а не обещание совместимости другого билда.

Снимок `N/vehicle03-runtime/screenshots/arena_vehicle_001.png`, SHA256
`85f5104a8ac6f37b47d9ce3aaa93fe180a520b1ba873c305b5f0196c89ca8cdf`,
действительно просмотрен root: Карелия, МС-1,90/90HP, minimap, native HUD.
Отдельный `visual-review.json` SHA256
`d89a2f2ae95d721cba0ec56aba6db1a20032bbdef3758940c2cb8c08bb89834a`.
Виден экран ожидания и00:00; танк в лабораторной точке, контакт с грунтом
не доказан. Причина цветной сетки/зерна снимка UNKNOWN.

При завершении actual stopVisual614/177, Vehicle.onLeave155/48,
Avatar.onLeave425/948 и onBecomeNonPlayer361/193 прошли штатно. Выполнены12
cleanup прежнего bootstrap и3 обёртки arena bootstrap; exit0. Свежего
traceback/__manualSound нет. Известные сообщения неподдерживаемого Vivox и
warning AccountRepository is None сохранены; голосовая связь не объявляется
работающей. Независимый GUI review: `N/gui/vehicle03-native-review-01/`.

Первый verifier03-01 ошибочно ожидал отдельные RPC86/0c, его FAIL сохранён.
Фактический33B пакет разобран целиком по границам, original .def/таблице/pyc:
offset0..11 bindToVehicle(ownID),11..19 vehicle_changeSetting(2,1),
19..22 setClientReady(),22..33 autoAim(0). Независимая wire-проверка:
`N/wire/vehicle03-auto-rpc-01/result.json`, SHA256
`32c7080bcf152e6e63eb05cf42ef7cbc10bfbe64926874256b169f65564ce92c`.
Gateway честно transport-ACKed этот envelope как AVATAR_RPC_UNSUPPORTED,
domain_applied=false. Наличие вызова клиента не выдано за серверную обработку
готовности или управления. Отсутствующие маркеры сервера не дорисованы.

## Проверки, ограничения и повтор

Сборки/argv/toolchain/source snapshots: `N/server-rebuild-01/`..`04/`.
Принятый EXE SHA256
`40513e0cead8cb6193b9737293c45423d70c048cdf8ef8d613ed9584a68e6230`.
141 Rust tests PASS: exact09/08, повторы, token/ACK/sequence/piggyback,
ACK именно объявления и атомарность. Root guards22+runner40+profile18 PASS;
entry probe26, bootstrap28, space scenario27 иVehicle scenario41 — каждый
на Python3 иCPython2.7.3 PASS. Независимые verifier suites: base12,space14,
Vehicle24 PASS. Расчёт мощности19testsPASS. Unit tests не заменяют native evidence.

Прежний bounded unsupported-Avatar sink32envelopes/512payload не реализует
весь Avatar service:33-е неподдерживаемое reliable сообщение может остановить
FIFO. Полноценная обработка команд, собственная физика и multi-session UNKNOWN/
NOT_RUN. Действующий стенд не рассчитан на1000CCU.

Повтор проверок из `D:\WoT_9.1_Server`:

```powershell
python -B -X utf8 -m unittest discover -s tests -p test_avatar_base_native.py -v
python -B -X utf8 -m unittest discover -s tests -p test_arena_space_native.py -v
python -B -X utf8 -m unittest discover -s tests -p test_arena_diagnostic_control.py -v
python -B -X utf8 -m unittest discover -s tests -p test_arena_vehicle_native.py -v
python -B -X utf8 tools/capacity_estimate.py --matrix
```

Проверка закрытого реального Vehicle03 без нового запуска EXE:

```powershell
python -B -X utf8 tools/verify_arena_vehicle_native.py `
  --install local/evidence/20261005-p02-arena-entry/vehicle03-prepare `
  --private-key local/server/native-private.pem `
  --registration local/evidence/20261004-p02-unified-account/operator-email-binding-01/registration.json `
  --credentials local/evidence/20261004-p02-unified-account/operator-email-binding-01/test-credentials.json `
  --case operator_shared `
  --fixture local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r4-catalog3 `
  --trigger local/evidence/20261005-p02-arena-entry/vehicle03-trigger.json `
  --trigger-proof local/evidence/20261005-p02-arena-entry/vehicle03-trigger-proof.json `
  --out local/evidence/20261005-p02-arena-entry/data/verify-vehicle03-repeat-01
```

Для каждой повторной проверки нужен новый `--out`. Source-frozen argv/logs:
`N/data/vehicle-verifier-checks-final-01/`; fresh native prepare/run/trigger:
`N/prepare_vehicle03.py`, `N/trigger_vehicle03.py`, `N/vehicle03-prepare/`.
Последние два helper одноразовые: не запускать поверх существующих outputs;
для нового live run нужны новые пути и обычный guarded rollback normal011.
Space01/02 иVehicle02 исторически должны вернуть FAIL: сохранённая ошибка
не исчезает от исправлений последующего кода.
Контролирующие файлы с паролем остаются вignored local/, в этот отчёт не входят.

Оценка будущего парка вынесена в [CAPACITY_1000_CCU.md](CAPACITY_1000_CCU.md):
3/5/7 узлов по разным допущениям;19 arithmetic tests PASS, реальная нагрузка
боя/1000 клиентов/failover NOT_RUN. Там же формулы, исходные допущения и источники.

## Обычная установка, файлы и откат

Супервизор возвращён в ordinary legacy091-interactive: `N/ordinary-server-01/`.
Без capture/arena trigger; внешний сайт не перезапускался этой карточкой.
Установлен `local/client-install-011`:20modules,29immutable+3ownerlogs,
без test-control/autologin/autoquit/capture и управления вводом. Клиент закрыт.
Серверный лимит1800s прежний. Ручной вход именно с normal011 после этой
установки NOT_RUN; native Vehicle03 использовал те же20 исходных модулей.

Полный manifest01 обнаружил один новый engine-generated replay1784B от
Vehicle03. Это не замолчали как «полный откат PASS»: штатный ledger восстановил
свои файлы, replay оказался дополнительным runtime artifact. Header содержит
своего МС-1/Карелию/время14:52:05; файл отсутствовал в принятом baseline.
Он сохранён вместе с SHA/header/доказательством отсутствия, затем удалён только
этот точный research-путь при закрытом клиенте и совпавшем хеше:
`N/native-generated-replay-01/result.json`, SHA256
`de9390993584121119609101eb7b801405510016331074302376b2b099c72396`.
Сохранённый raw SHA256
`6a8e97d567a9694ca519f5796576a11f855bb69be9d7157bcc45e14305634835`.
Final manifests02 проверяют состояние после этого восстановления; replay
остаётся в ignored evidence, пригодность его воспроизведения NOT_RUN.

Изменён код: `client_patch/sr_interactive.py`; инструменты
`tools/diagnostic_client_run.py`, `interactive_client.py`, `local_server.py`;
Rust `gateway091.rs`, `hangar091.rs`, `main.rs`, `transport091.rs`.
Добавлены4 модуля `client_patch/arena_*.py`,3 Rust `arena*.rs`,3 native verifier,
8 соответствующих test-файлов, capacity tool/test и план/два отчёта.
README/STATUS/MISSING_INPUTS обновлены. Точный список и SHA —
`N/final-authored-sources-02.json` и `N/final-audit-02/final-state-audit.json`.
Одновременные изменения web demo сохранены отдельно как
NOT_REVIEWED_BY_ARENA_TASK; эта карточка их не принимала и не откатывала.

Обычный запуск/проверка состояния:

```powershell
python -B -X utf8 tools/local_server.py status --config local/server/service.json
# Только если сервер STOPPED:
python -B -X utf8 tools/local_server.py start --config local/server/service.json
Start-Process -FilePath 'D:\WoT_9.1_Server\WoT_0.9.1_RU_0717_research\WorldOfTanks.exe' -WorkingDirectory 'D:\WoT_9.1_Server\WoT_0.9.1_RU_0717_research'
```

Обычный вход открывает ангар; кнопка боя ещё ограничена. Он не запускает
диагностический переход автоматически. Откат установленного пакета после
закрытия клиента и проверки его ledger:

```powershell
python -B -X utf8 tools/interactive_client.py rollback --out local/client-install-011
```

Откат исходников: проверенный `N/baseline-01/project-before.zip` и snapshots
перед каждым узким изменением. Не разворачивать весь ZIP поверх последующих
правок; сначала сверить файл/хеш. Рабочий до карточки EXE сохранён в
`N/server-rebuild-01/gateway-before.exe`. Базы не заменять целиком поверх живого
сайта. Профили не менялись. Native diagnostic rollback выполнен по каждому
из7 действительных запусков этой карточки, неиспользованный vehicle01 NOT_RUN.
Откат ordinary011 и возврат старого серверного EXE не выполнялись (NOT_RUN).

**Единственный следующий рекомендуемый шаг:** исследовать и реализовать
серверную обработку настоящего setClientReady и переход одной собственной
арены из ожидания игроков в фазу подготовки с родным отсчётом. Следующая
карточка здесь не начата; боекомплект в Avatar, движение и выстрел остаются
отдельными неподтверждёнными контрактами.

Первый итоговый audit01 сохранил FAIL из-за ошибочного имени кодировки
`utf8-sig` в локальном reader PowerShell output. Продукт не менялся; reader
исправлен на `utf-8-sig`, положительный BOM control и отрицательные проверки
сохранены. Финальный отчёт audit02 — отдельный запуск, первый traceback не
перезаписан: `N/final-audit-01/final-state-audit.json`, SHA256
`63314a68d3d185b1d03cfd42263b8933a3febc267a2ec851d010b64948b8a1ba`.
