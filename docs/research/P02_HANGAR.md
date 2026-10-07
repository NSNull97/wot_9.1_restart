# P02 — штатный ангар с серверными данными игрока

2026-10-04. Проект GAYmDev Stutio / «Стальной рубеж».
План: [P02_hangar](../plans/P02_hangar.md). Продолжение
[P02_ACCOUNT_READY](P02_ACCOUNT_READY.md) по прямому разрешению владельца
дойти до ангара со статистикой и ресурсами, затем остановиться перед ареной.
Evidence root: `local/evidence/20261004-p02-hangar/` (далее E).

**Узкая карточка «штатный ангар и сводка статистики с серверными данными» PASS.**
Итоговая серия E/native-final-03: обычный вход, потеря sync packet, неверный
пароль и повторный вход на одном gateway — **4/4 PASS**. Независимая проверка:
E/verify-final-03/hangar-verification.json; шесть native PNG просмотрены отдельно.
Прежние FAIL сохранены, включая ошибки звукового bootstrap и clanInfo.
Оригинальный клиент неизменен. Строгое сравнение research с началом карточки
имеет **FAIL по трём сохранённым логам другого запуска**; ресурсы/код и откат
к состоянию перед нашими запусками проверяются отдельно ниже.
Весь P02 остаётся PARTIAL; web→game авторизация, persistence и арена NOT_RUN.

## Объём и реально изменённые части

Исследованы original Account.showGUI, запуск штатного AppEntry/LobbyView/Hangar,
AccountSyncData/Inventory/Stats/Shop/Dossier и обязательные настройки GUI.
Добавлен собственный `test_lab` fixture нового игрока, который сервер доставляет
по измеренным native сообщениям. Исследовательский bootstrap вызывает оригинальные
подсистемы и наблюдает их состояние; Account/GUI callbacks не заменяются
успешными заглушками. Арена, бои и экономические действия не реализованы.

Код текущей карточки находится в следующих файлах; окончательный список изменений
и SHA256: E/project-changes.json, E/project-after.json, E/project-snapshot-hashes.json.

- `tools/hangar_state.py`: ограниченный генератор собственной модели и data-only
  protocol2 payloads; читает оригинальные дескрипторы только из local evidence.
- `tools/hangar_config.py`: проверяемая локальная конфигурация native GUI стенда.
- `tools/wg_probe/src/hangar091.rs`: узкий профиль showGUI/синхронизации, измеренные
  дополнительные запросы, проверка формы fixture и resource streams.
- `tools/wg_probe/src/gateway091.rs`, `main.rs`: интеграция отдельного
  `legacy091-hangar` с существующим transport/session gateway.
- `tools/wg_probe/src/transport091.rs`: доступ к существующему MAX_SEQUENCE
  для предварительной проверки fixture; значение32 не увеличивалось.
- `client_patch/hangar_bootstrap.py`, `client_patch/p01_probe.py`: original GUI
  lifecycle, переадресация действительных native callbacks, пассивные наблюдения
  и запрос штатного screenshot; диагностика и корректное завершение.
- `tools/client_probe.py`, `tools/gateway_suite.py`: opt-in запуск карточки,
  временная локальная конфигурация, ledger/backup/restore и evidence.
- `tools/verify_hangar.py`: независимая проверка записанного обмена и runtime;
  существование verifier не означает PASS его проверки.

`web/` и `local/web/` принадлежат отдельной сессии и этой карточкой не изменяются.
Исходный snapshot сервера: E/project-before.json, 108 файлов, SHA256
`06eec6553f2d36367089986917886b34223de49a1019a5666d4a49681acdc4f3`;
его содержимое сохранено в E/project-before.zip. Не применять ZIP поверх текущей
папки целиком: в ней могут быть последующие и параллельные изменения.

## VERIFIED — среда и native контракты

Закреплён клиент `v.0.9.1 #717 RU`, compatibility `ru_0.9.1_2`, runtime
Python 2.7.3 x86. Это сведения проверенных локальных файлов, не заключение об
издательской аутентичности. EXE SHA256
`86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed`.
Перед карточкой обе копии содержали одинаковые 3469 файлов; SHA256 каждого
content manifest — `74c37c18e9ac7e30196c134076dacf6f2a8bf3897f7def73905d09feb3647797`.
E/baseline/copy-comparison.json не содержит различий. Финальная сверка original
подтвердила тот же content hash. Research содержит три сохранённых отличия
журналов другого запуска; полная цепочка описана в разделе целостности.

| Контракт | Подтверждение и практическое значение |
| --- | --- |
| Account.showGUI принимает STRING с protocol2 dict; `databaseID` обязателен | Account.pyc, showGUI line573, offsets28–38 и262–274, normal return297; E/wire-agent/wire-contract-v1.json. Первоначальный кандидат route0x53 подтверждён actual native showGUI в GUI02 и последующих runtime traces |
| Серверная Account creation и showGUI разделены | createBasePlayer ID5/VAR2 создаёт type0 и три свойства; showGUI идёт через selectPlayerEntity0x13/method0x53. Native Account/имя/database ID наблюдаются в `native_player`, данные приходят с сервера |
| Первичные commands100/300/600 используют onCmdResponseExt0x4d с RES_STREAM=1 | Native клиент отправляет doCmdInt3 0x8e/VAR2. Shop.__onSyncResponse line814 не загружает ext как каталог при RES_SUCCESS; __onSyncDataReceived line862 требует sellPriceFactor. E/data-agent/contracts.json, E/gui-02/01-normal/runtime.jsonl |
| Полный sync требует второго запроса100 с revision1 | AccountSyncData.__onSyncComplete line196 применяет full data и вызывает _synchronize; __onSyncResponse line163 проверяет prevRev. Измеренный GUI02 request224 имеет args(1,0,0). Ответ RES_SUCCESS с `{'prevRev':1,'rev':1}` освобождает ожидающие callbacks; пустой ext означал бы full reset. E/wire-agent/refresh-observation.json; фактический synchronized=True в GUI03 |
| Resource header52 и fragment53 имеют независимую от RPC упаковку | Header ID/requestID; fragment u16 ID/u8 index/u8 last. Original game dispatcher сверяет длину и CRC, затем передаёт stream Account. GUI09 verifier подтвердил три fragments state и по одному shop/dossier, включая совпадение с fixture hashes. E/wire-agent/wire-contract-v1.json привязывает PE offsets к EXE hash; произвольная fragmentation не проверена |
| Дополнительные native BW-chat запросы входят в тот же bundle | GUI01: 0x93, commands10/9/30 вместе с100/300/600. Пустой roster нового fixture — реальные пустые данные собственного аккаунта, не доказательство работающего чата. Mutation/contact/message services не реализованы. E/wire-agent/chat-observation.json |
| SET_LANGUAGE использует другую сигнатуру | GUI03: 0x95 doCmdStr, command1000, строка ru. Account.setLanguage line1269 передаёт callback=None, поэтому фиктивный успешный response не нужен. E/wire-agent/language-observation.json |
| Штатный GUI периодически запрашивает server stats | GUI09 verifier коррелирует пять command501 requests и пять original receiveServerStats responses, cluster/region CCU1 для одного активного лабораторного соединения. Это не нагрузочное измерение онлайна; E/verify-gui09/hangar-verification.json |

Первоначальные файлы исследования могут содержать корректную для момента создания
пометку INFERRED/NOT_RUN. Более поздняя трасса повышает статус только проверенного
поднабора; старые evidence не переписываются задним числом.

Основные source hashes:

| Исходник в `res/scripts/` | SHA256 |
| --- | --- |
| client/account.pyc | `bb6e88e4aec03161212847ffc3601d16917610b8f7815c42f91f610693f4d0ef` |
| client/account_helpers/accountsyncdata.pyc | `8032c14629301d79056e4b5a0bf24c60f86023199bc762b3845860c6ca16dffd` |
| client/account_helpers/shop.pyc | `84aa30eb5b1862ac4fbb08557b67ad36dabc9b90cc1d083a29e0e12040127b6d` |
| client/account_helpers/stats.pyc | `79960cd768250ce4b1e7188f6353c26e2b480b29dae0ea839168dec19f73a983` |
| client/account_helpers/inventory.pyc | `3d17842cc6fa9af05d53cc6d22dc286e6b0434356e58c6f74d5822c2dd3cbf19` |
| client/gui/shared/personality.pyc | `f065bf206e31102a2328babac0c9cc7a4203216ac5a44a4fb289db070be9a7bd` |
| client/gui/windowsmanager.pyc | `e3eda85faa9448170df9b5ab720b51892739ca0cb3c1c97230457318001ada32` |
| common/items/vehicles.pyc | `805240e4b59d8a75950dbb97b41c17867606e7e96d7ff0c8d7b05312b83ae8b6` |

Прочие точные функции/строки/offsets/hashes: E/data-agent/contracts.json,
followup-contracts.json, fixture-05/selection-contracts.json,
fixture-06/capacity-contracts.json; E/gui-agent/FINDINGS.md и тематические
`sources.json`; E/wire-agent/*.json. Клиентский bytecode статически разобран,
не импортирован в исследовательский Python и не выполнен через eval/exec.

## VERIFIED — original GUI и границы bootstrap

Original game.init line76 задаёт зависимости GUI. Для изолированного стенда
вызывается их исследованный необходимый набор: полный game.init также содержит
регистрацию расширения replay и RSS startup. Original GUI personality.init
line228 устанавливает штатные callbacks; start line286 запускает WindowsManager.
Original ConnectionManager получает настоящий callback `[1,'LOGGED_ON','']`;
подставной connected flag не назначается. WindowsManager.__onAppStarted line189
может пропустить LoginView при уже установленном native соединении.

| Настройка/зависимость | Исследованный контракт и конфигурация стенда |
| --- | --- |
| `serverSettings.wallet` | WalletController.start line47 читает [0]/[1] через bool. `(False,False)` отключает внешний общий кошелёк, собственные балансы аккаунта сохраняются |
| `serverSettings.roaming` | RoamingController использует первые три поля; predefined_hosts.roamingHosts line736/offsets36–49 дополнительно читает [3]. Рабочая форма стенда `(0,0,[],[])`; первоначальная тройка вызвала реальный IndexError |
| `regional_settings` | starting_time_of_a_new_day — числовое смещение секунд, starting_day_of_a_new_week — integer для расчёта недели. Собственные 0/0 — test_lab, исторические региональные значения не заявляются |
| showGUI ctx | `isAogasEnabled=False`, collectUiStats=False, logUXEvents=False. Original AOGAS при отсутствии первого ключа имеет default=True |
| Chunk callbacks | game.wg_onChunkLoad line560 и wg_onChunkLoose line569 должны получать реальные callbacks; AreaDestructibles.init вызывается после GUI personality.init. Отсутствующий delegate вызвал настоящую ошибку GUI05 |
| Лицензионный диалог | Original version.xml/showLicense=3. С GUI05 resource override временно задаёт0 для unattended лаборатории; принятие соглашения пользователем не записывается и не утверждается. Before hash/изменение отражены в resource-isolation.json и ledger |
| Внешние сервисы | Временная конфигурация оставляет свой numeric loopback login; внешние URL очищены, RSS/voice/roaming отключены, xmpp_enabled=False. BW-chat использует native канал и не выключается подменой метода |

Факт конфигурирования loopback и выключения исследованных сервисов **не доказывает
OS-wide отсутствие исходящего трафика**: отдельный egress capture здесь NOT_RUN.
Файлы исследовательского override и исходные значения сохранены в каждом
`gui-XX/01-normal/resource-isolation.json`, patch-ledger.json, backup и postrun.
Исходная копия клиента не является местом установки патчей.

Original SoundManager.playControlSound line45 обращается к singleton VibroManager
даже без подключённого устройства. После реального исключения native-final/01
добавлены original constructor/connect, start после GUI start и destroy при fini.
В итоговых трёх положительных runs диагностический вызов настоящего
`soundManager.playControlSound('press','normal',None)` проходит return89 и вложенный
VibroManager.playButtonClickEffect return12. Это проверка исполнения исходного
обработчика/no-device ветки, не оценка слышимого звука, физической вибрации или
имитация мышиного ввода. Sources: E/gui-agent/sound-manager/sources.json,
vibro-lifecycle/sources.json, sound-invocation/sources.json; actual trace и независимая
корреляция — E/native-final-03 и E/verify-final-03/hangar-verification.json.

После снимка ангара опция `--diagnostic-open-profile` вызывает оригинальный
LobbyHeader.menuItemClick с alias LOBBY_PROFILE. Реальные ProfilePage,
ProfileTabNavigator и ProfileSummaryPage активны; оригинальные
ProfileSummary._sendAccountData return235, ProfileSectionMeta.as_responseDossierS
return30 и ProfileSummaryMeta.as_setUserDataS return27 передают данные в Flash.
Наблюдатель не создаёт этих views и не выставляет успешные flags. Перед навигацией
проверяется собственный fixture без клана/редких наград: native ClanCache с ID0
и loader с нулём записей не запускают внешнюю загрузку. Sources:
E/gui-agent/profile-navigation/sources.json, profile-navigation-contract/sources.json,
profile-network/sources.json. Остальные вкладки профиля NOT_RUN.

Original ClientHangarSpace.create line99 сам создаёт `OfflineEntity` как держатель
визуальной модели ангара. Это штатный локальный визуальный объект, отдельный от
настоящего server-created Account. Наличие этого объекта не означает сетевую
арену; отказ от него не был бы корректной проверкой оригинального UI.

## VERIFIED — модель player data и её native соответствие

Fixture — диагностический новый аккаунт, без выдуманных завершённых боёв:

| Собственное поле | Native представление |
| --- | --- |
| account_id `test_lab:hangar-player-v1` | Отдельное compatibility mapping native databaseID900001, nickname `p02-hangar-player` |
| resources | stats.credits100000, gold0, freeXP0; явно заданные тестовые значения, не исторический стартовый баланс |
| statistics | Battles/wins/losses/draws0 из настоящего fresh account dossier; не отдельные подставленные GUI счётчики |
| capacity | stats.slots3, berths16 |
| inventory `test_lab:starter-vehicle-v1` | Native inventoryID1, type compact ID3329, original descriptor MS-1; HP90/90, XP0, два пустых места экипажа, боеприпасов0 |
| services | purchases/sales/battle/crew_recruitment/persistence=False |

**Сайт и игра должны использовать один продуктовый account_id и один источник
учётных данных.** Fixture не создаёт второго реестра регистрации и не является
миграцией аккаунтов сайта. Сквозной web registration → game login, общая
авторизация, разные реальные пользователи и сохранение состояния **NOT_RUN**.
Утверждать их готовность по совпадению nick/balance в ангаре нельзя.

Stats.synchronize line70 разделяет ресурсы/dossier в `stats`, attrs/clan/premium
в `account`, wallet/cache flags в `cache`. Inventory.synchronize line68 читает
integer item type keys: vehicle1, tankman8. Для машины поля — словари по inventoryID:
compDescr bytes; repair=(repairCost,health); crew имеет штатное число позиций;
shellsLayout — dict; eqs/eqsLayout — три native slot значения. Settings manager
использует version11 по integer key0; старые версии инициируют migration writes.
Quests/tokens пусты у собственного нового fixture.

Native descriptor извлечён реальным read-only вызовом оригинального конструктора
в descriptor-01, не сочинён серверным encoder. E/native-descriptors.json SHA256
`18e6c2babfc205ce80fa24c2c9f23385a1731233c4d504be369638485652d6f2`.
Дескриптор машины — 15 байт, SHA256
`4122429c052f5c8eb2ebeae456c775b1a368a007cf37bae8af7b3f87ff064c5c`;
fresh account dossier — 88 байт, SHA256
`26d3424ed165a206cd4ce640b5806dc985c6ccb7e19695c605fec6b2dd46e9b7`.
Они без изменений попадают в state.bin. Components IDs и crewRoles также взяты
из реального original constructor. Клиентские derived bytes остаются только в local.

Для оригинального inventory enumeration необходима запись `itemPrices[3329]`:
ItemsRequester.getItems line407 начинает с ShopDataParser.getItemsIterator,
который выдаёт только присутствующие в price map IDs. `isHidden` не является
фильтром REQ_CRITERIA.INVENTORY. Поэтому fixture-05 добавила display reference
`(0,0)`, прочитанную из оригинального `vehicles/ussr/list.xml`, узел
`/MS-1[1]/price[1]=0`, SHA256
`167a637d725a233d42e52bd7d5bac00b9af45c0ef225163ab578e202454f5138`.
Машина остаётся в notInShopItems. Это обязательная запись для отображения
выданной машины, не работающий магазин.

Fixture-06 дополнительно задаёт `slotsPrices=(3,[0])`, `berthsPrices=(16,1,[0])`.
Shop.getNextSlotPrice line362 требует два поля, второй — непустой список;
getNextBerthPackPrice line388 требует три, включая положительный размер пакета.
Original fallback slot цены ошибочно имеет berth форму `(0,1,[300])`, что и
вызвало TypeError при заполнении carousel. Нулевые display references в новой
конфигурации отмечены `unavailable_test_lab_reference`: цены исторически UNKNOWN,
операции покупки ёмкости не реализованы. В native UI может остаться кнопка с
нулевой ценой; это ограничение лабораторной карточки, не обещание бесплатной покупки.

Zero playLimits также не означают отсутствие ограничений: original
GameSessionController.isParentControlEnabled line202 сравнивает их с86400/604800.
Fixture-04 задаёт явно `unrestricted_test_lab` с этими пределами и нулевым временем
игры. Изменение затронуло два scalar значения; dossier/vehicle не менялись.

Fixture-07 исправляет отсутствие клана: `stats.clanInfo=None`, `clanDBID=0`.
Первоначальный пустой список прошёл загрузку ангара, но пользовательское открытие
профиля в native-final-02 вызвало настоящий IndexError: original
ProfileUtils.getProfileCommonInfo line336 проверяет `is not None`, затем читает
clanInfo[1] (offsets227–251; fault line374). Исправление меняет ровно один байт
state.bin по offset379: EMPTY_LIST0x5d → NONE0x4e; dossier/ресурсы/машина неизменны.
Source SHA256 `10ec7ff54e9ca73e65cbcf1ca0a4dc496797663848b43fde4e3be6ca3aa2e07c`;
разбор и проверки: E/data-agent/fixture-07/profile-contracts.json.

## Текущие payloads и ограничения parser

Вход итогового сервера — `E/fixture-final-02/`, эквивалент fixture-07;
manifest SHA256 `c422f810e4d9c67eed9bcd6c46f9bd22b72bf038e249aa238c124362ff6f94b6`.
В fixture.json находится собственная модель, в compatibility.json — соответствие
ID, в payloads.json — проверяемое представление с различением tuple/bytes/int keys.

| Файл | Размер | SHA256 |
| --- | ---: | --- |
| state.bin | 1106 | `bc69a8c943fef796ea159068ccf897a9be93f4158ab8d0746c38326cac2c4fee` |
| shop.bin | 361 | `210617723b8094186b7e8f5991e505941052c25c5d04dcc10c556d17d5d880b1` |
| dossier.bin | 8 | `70b70fe0dd6f28761228250a57e0a0a71e9d16ee0db54ff6e9252f06267034f1` |

Encoder принимает только простые значения, проверяет размер≤16KiB, nodes≤4096,
depth≤16, signed32 integers, конечные float; отвергает cycles, object constructors,
colliding keys после Python2 encoding и неподдержанные типы. `pickletools` используется
только для просмотра opcode. Rust scanner проверяет literal grammar и root types;
никакого входного pickle.loads/eval/exec нет. Потоки используют bounded zlib stored
block, CRC32 и chunks≤400B; transport bodies≤512B. General-purpose pickle,
произвольные RPC/покупки и все варианты legacy fragmentation не реализованы.

Lifetime transport ограничен32 reliable sequence, window8. Новый fail-fast
до открытия sockets проверяет начальную потребность `sum(ceil((raw_len+11)/400))+6`
в пределах32: actual fixture требует11. Это не продление канала: расход на
последующие запросы остаётся ограниченным. Длительный интерактивный сеанс NOT_RUN.

## OBSERVED — сохранённые реальные запуски и FAIL

`runner_status=PASS`, native init и rollback сами по себе не означают совместимость
или успешное завершение всей GUI приёмки. Для каждой строки ниже raw packets,
runtime, свежий Python log и outcome находятся в `E/<run>/01-normal/`;
общий server log — `E/<run>/gateway.stdout.log`. Ошибки не удалялись.

| Run | Наблюдение | Статус полного входа в готовый ангар |
| --- | --- | --- |
| descriptor-01 | Original init/VehicleDescr/fresh dossier extraction; exit0, restore PASS | NOT_RUN: режим извлечения, не GUI |
| gui-01 | Original AppEntry создан; смешанный bundle sync+BW-chat ещё не принят; revision0, pending3 | FAIL |
| gui-02 | Три native streams приняты, original showGUI вызывается; revision1, pending1, ожидание дополнительного sync100 | FAIL |
| gui-03 | sync/cache PASS, ресурсы100000/0/0 и counters0 читаются оригинальными requesters; KeyError wallet в original controller | FAIL |
| gui-04 | Wallet исправлен; выполнение дошло до processLicense, hangar space ещё не создан; original showLicense3 блокирует unattended проход | FAIL; отсутствие traceback не равно готовому GUI |
| gui-05 | LobbyView/Hangar существуют и Flash-bound; машины нет. Roaming tuple IndexError, отсутствующий wg_onChunkLoad delegate и slot-price TypeError сохранены | FAIL |
| gui-06 | Выбран inventoryID1, четыре original модели loaded/visible, native header получил ник/балансы; slot-price TypeError оставляет Waiting видимым | FAIL |
| gui-07 | Fixture-06: машина/данные/панели видны, Waiting=False; screenshot содержит модальный notSupported. На завершении exit3221226525 (0xC000041D); verifier: last reliable packet unacknowledged, active_at_end1 | FAIL |
| gui-08 | Wire/data/native UI/screenshot прошли проверку, exit0, девять cleanup stages; поздний connection callback попытался писать в закрытый trace: ValueError I/O operation on closed file | FAIL целиком, несмотря на успешные поднаборы |
| gui-09 | Wire/native/visual verifier PASS,105 packets проверены, exit0; поздний callback честно записан с after_fini=True, уничтоженным GUI сервисам больше не делегируется | PASS одного normal run; финальная серия PENDING |
| native-final/01-normal | Wire/visual и exit0 прошли; на19.2145183s original SoundManager.playControlSound line45: None.playButtonClickEffect, настоящее Python исключение | FAIL |
| native-final/02-drop-server-sync | Потерянный packet sync stream восстановлен; native/wire/visual/exit0 проверены | PASS измеренного loss-control |
| native-final/03-wrong-password | Настоящий LOGIN_REJECTED_INVALID_PASSWORD67, новая игровая сессия не выделена; ангар не ожидается | PASS отрицательного контроля; visual NOT_RUN |
| native-final/04-normal | После отрицательного входа тот же gateway снова довёл клиент до ангара и штатного выхода | PASS |
| native-final-02 | Sound bootstrap исправлен,3/4 machine checks PASS; первый normal получил IndexError при пользовательском открытии профиля: clanInfo=[] | FAIL серии; итоговая visual приёмка этой серии NOT_RUN |
| native-final-03 | Fixture-07/clanInfo=None; normal/loss/reject/relogin, original SoundManager и собственная сводка профиля; три положительных clean exits0 и шесть проверенных PNG | PASS4/4 |

GUI03: 42 samples оригинального ItemsCache содержат ожидаемые ресурсы и нулевое
dossier. GUI06: 39 samples имеют selected inventoryID1; конечный показывает90/90 HP,
crew_slots2, xp0, четыре видимых модели. Эти поднаборы **PASS в данных запусков**,
но ни один не устраняет общий FAIL своей строки. `data-agent/native-data-observation-gui03.json`
и `fixture-06/capacity-contracts.json` содержат соответствующие доказательства.

Пассивное чтение `spaceLoading` в раннем observer было некорректным: bound method
трактовался как bool. Поэтому `hangar_space_loading=True` из GUI02–07 не принимается
как измеренное состояние загрузки. В GUI09 и итоговой серии измеряется настоящий
вызов spaceLoading(); False проверен, другие ранние свойства не повышаются автоматически.
Снимок GUI07: `E/gui-07/01-normal/screenshots/hangar_001.png`, SHA256
`95fcd7a96bd8dcc51b95cad6bbd2ee5f3e08cfcf770cd18734f7631bc4c5fcc4`.
Визуально на нём подтверждены ник, баланс100000, машина и штатные панели, но
модальное окно также присутствует. Независимый общий verifier:
E/verify-gui07/hangar-verification.json — **FAIL**, visual_status NOT_RUN в его
автоматическом отчёте; отдельный просмотр изображения не меняет этот результат.

GUI09: E/verify-gui09/hangar-verification.json SHA256
`a089b3fdc4c23e9c629922a427336446d1f4ebbab9b2a4be28dd731de4f118d2` подтверждает
wire/native/visual PASS. 38 последовательных visible-state samples за18.833663s
показывают загруженный ангар, четыре видимых модели, выбранную машину и отсутствие
Waiting; исправленный вызов spaceLoading() возвращаетFalse. Вход/выход и original
Account/header/stream callbacks проходят проверку реальных normal return offsets.
Записан поздний `[6,'NOT_SET','']` с `after_fini=True` на34.7007316s, без попытки
вызвать уже завершённые GUI подсистемы. Это наблюдаемый lifecycle, не скрытая ошибка.

GUI09 screenshot `E/gui-09/01-normal/screenshots/hangar_001.png` SHA256
`34cf21cac1185b33328b3f3cd3b54dcc3fc371075874dc782875653cb98b3dbd`
просмотрен владельцем запуска: машина, ник, баланс и HP видны, блокирующего диалога
нет. Отдельный `visual-review.json` SHA256
`89b8cc1c6af0e502cdb26932170a634c975652f9573245c35b9ec46e6b19f55e`
также отмечает сохраняющийся цветной шум рендера и старое welcome branding.
Визуальная полировка/ребрендинг и открытие окна статистики не принимаются этим PASS.
E/verify-gui08/hangar-verification.json сохраняет прежний FAIL позднего trace write.

Первая серия `E/native-final/` использует один gateway PID91656, session IDs1/2/3;
неверный пароль сессию не создаёт. Независимый `E/verify-final/hangar-verification.json`
SHA256 `66a34e2c3da9a86ddb453be3adde1cc05c5420ceccf5a737d1fef9e385c7d8e9`
фиксирует **3/4 PASS, итог FAIL**. Все четыре runner cases завершились, однако
настоящая ошибка SoundManager в первом normal run запрещает принять всю серию.
Это новый измеренный bootstrap blocker, не повод скрывать обработку sound events.
После исправления выполнены новые серии; старый FAIL не пересчитывался в PASS.

Итоговая native-final-03 использует один gateway PID95948, sessions1/2/3.
В loss-control намеренно потерян server seq2 с первым400B фрагментом state;
повтор того же body через packet025 за0.7011176s принят клиентом, CRC и все
переданные данные совпали с fixture. Reject вернул настоящий INVALID_PASSWORD67,
новой игровой сессии нет. Последующий normal снова вошёл в ангар и профиль.

Таймер диагностического positive run —30s от инициализации; это НЕ30s готового
ангара. По actual samples Account-ready держался18.28–18.80s, ангар6.12–6.17s
до штатной навигации в профиль, профиль9.17–9.70s. Все10 cleanup stages завершены:
music, messenger, post_processing, native_entities, native_spaces, gui_personality,
area_destructibles, vibration, battle_replay, predefined_hosts. Поздний native
callback после fini сохраняется и не делегируется разрушенным подсистемам.

Во всех трёх положительных cases original ProfileSummary показывает своего
игрока/databaseID900001, нулевые battles/wins/losses, дату регистрации04.10.2026,
отсутствие клана/значимых наград. Native averages для нового игрока отображаются
прочерками, ближайшие награды — штатными целями, не заработанными достижениями.
В каждом run проверены `screenshots/hangar_001.png` и `screenshots/profile_002.png`
с точными SHA в visual-review.json и visual-review-profile.json. Исходные шесть
изображений также собраны без изменения пикселей в E/screenshots.zip.
На PNG остаются старый welcome branding и цветной пиксельный узор; происхождение
узора UNKNOWN. Эти дефекты не скрываются успешной проверкой видимых данных.

Хеши исходных runtime.jsonl:

| Run | SHA256 |
| --- | --- |
| gui-01 | `7608473d66f9ca58d969e140f887824e221fdf0d80fcf1d00e9d9b5ce85a275b` |
| gui-02 | `90084d0dd7a14fec107b0b2215332e295468cc619030746c486c4b784ca9f496` |
| gui-03 | `1675a01958825a52bbee16b8eabfc61dac3353a77bcdfce85137f2fde9fafeea` |
| gui-04 | `8910b1610692ef491ef379da4a3d1c4c996bc7da736e028e0fe6dc641b97f747` |
| gui-05 | `6f6ec08e5eef647284729b374c6815a734034d5bf5265ed9a5031a30efec1350` |
| gui-06 | `1e10bfe35b406ac7c0a8d05773c593f5efba370b90205d796a54b8cc607531cc` |
| gui-07 | `d97567849b1de56f51e50dcf6bc7ba10da6e75ffdaf7bb416c79bdfbb9899f9b` |
| gui-08 | `276f6a7d946ff3b4e2bef5d5fb502d44ea0bf9a6b4d0781bb99c5853f825f1bf` |
| gui-09 | `2ce721bae85da9dc410c856d87abd9650adf675be57a17ddb37c9feb901eb4f8` |

## Выполненные проверки

- PASS: финальный fixture,21 encoder checks, bounded primitive grammar и
  rejection cases. E/fixture-final-02/encoder-tests.json.
- PASS: exact native descriptor preservation; fixture-04 изменяет лишь play limits,
  fixture-05/06 сохраняют state/dossier. Evidence в descriptor-verification.json,
  policy-verification.json, selection-contracts.json и capacity-contracts.json.
- PASS на зафиксированных версиях: E/python-tests-01.log —20 tests;
  E/rust-tests-01/02/03/04/06/07/09.log —31/33/34/35/35/36/37 tests.
  Финальные E/rust-tests-final.log и rust-build-final.log:38 tests/build PASS;
  E/python-tests-final.log:20 tests PASS, включая5 проверок настоящих файлов клиента.
  Unit tests сами по себе не являются native acceptance.
- FAIL сохранён: E/rust-tests-08.log — compilation error; следующий
  rust-tests-09.log подтверждает37 passed. Причина исправления отражается в итоговом
  code diff; ошибочный log не удалён.
- PASS:52 независимые verifier checks, включая повреждения wire/loss/CRC,
  отсутствие/ошибки native sound/profile callbacks и visual evidence.
  E/wire-agent/verification/parser-checks-09.json; проверяемый tools/verify_hangar.py
  SHA256 `30d043e426313dcc8e001723df1020e58b5944f4c3463668f755a1c0321d6e24`.
- PASS: Python2.7.3 native compile диагностических модулей и py_compile Python3 tools;
  compiler evidence каждого native runner, E/p01-profile-compile.json.
- PASS: все22 runner restores и сохранённые backup/postrun по их собственным
  before-state. Полная research сверка с началом карточки отдельно FAIL по3логам.
- PASS: E/operational-final.json —35 записанных собственных PID проверены,
  своих живых процессов нет; UDP20014–20017 свободны, instance mutex отсутствует.
- PASS одного native GUI09 run: независимые wire/runtime/visual checks, clean exit0,
  measured three-fragment state stream и process/restore.
- Первая native-final серия: **FAIL целиком**,3/4 отдельных сценария PASS
  (loss/reject/relogin). Native-final-02 тоже FAIL; ранние проблемы сохранены.
- PASS: E/verify-final-03/hangar-verification.json —4/4 итоговых cases,
  machine/wire/visual PASS, statistics_dialog PASS. Это фактическая native проверка.
- NOT_RUN: общая авторизация сайта/игры, persistence, разные пользовательские
  аккаунты, бой/арена, экономические действия, полноценный чат, нагрузка,
  OS egress capture, длительный сеанс, остальные вкладки профиля и платформы вне
  текущей Windows среды. Собственная сводка статистики проверена в итоговой серии.

## Целостность и сохранение изменений между сериями

E/final-state-audit.json и final-state-manifest содержат полный итоговый read-only
аудит. Original:3469файлов/14680626869B, неизменный content SHA256
`74c37c18e9ac7e30196c134076dacf6f2a8bf3897f7def73905d09feb3647797` — PASS.
Research:3470файлов/14680628543B, content SHA256
`37bb7f1a79be0ef893c033bb4cc9bfae6470d1b64024e32639c05eb012fe0fe5`.

Строгое research==card-baseline остаётся **FAIL**: добавлен Influx_PS.bak,
изменены Influx_PS.log и python.log. Остальные3467файлов совпадают. Старые
E/integrity-comparison-02.json и client-restores-02.json сохранены побайтно;
сводный PASS им не присваивается. Хеши трёх отличий:

| Файл | SHA256 сохранённого текущего файла |
| --- | --- |
| Influx_PS.bak | `71ed85663f1fa8536be4747ed8bc0e8220fcad5ab54bce2a5da2abc4b65ab2e8` |
| Influx_PS.log | `0fa5037f96ee7b7e9869fb5e37f00a501a7e6040266bb1ea42cb73b73e5d82cd` |
| python.log | `13a5b1bd9b290f020417fe1604b6429158dbf085b37f80590e83e3cf922d2289` |

VERIFIED по E/log-lineage.json: before первых14runs соответствует baseline;
before последних8 уже содержит текущие три хеша. Первая записанная граница —
native-final-02/01-normal в10:17:43.046616UTC. Python log содержит отдельный
старт в15:14:34 местного времени, отсутствующий в22 захваченных runner runs.
USER_REPORTED: владелец пояснил «наверно это я пытался запустить».
INFERRED: его попытка может объяснять запись. Техническая атрибуция инициатора
UNKNOWN; прежняя гипотеза поздней записи после последнего теста опровергнута
более ранними before-хешами. Эти изменения сохранены, а не стёрты ради baseline PASS.

Полный текущий research совпал с восстановленным expected before последнего
run — PASS. Expected построен из полного baseline плюс КАЖДОЙ before-записи
последнего ledger/restore, существовавшие файлы подтверждены backup bytes/SHA.
Логи не исключены: они проверены против настоящих резервных копий. Отдельно
проверены backup/postrun всех22runs:91backup и367postrun файлов, отсутствия и
ledger consistency — PASS. Совпадение с каждым историческим before показано
отдельно:8совпадений/14различий, поскольку до последних8 поменялись журналы.
Read-only скрипт/команды: E/gui-agent/final-audit/supplemental_audit.py и
SUPPLEMENTAL-COMMANDS.md. Клиентские файлы аудит не меняет.

## INFERRED и UNKNOWN

- INFERRED: текущие поля достаточны для read-only показа именно этого fixture;
  другие машины, экипажи, модули, история боёв и вкладки могут потребовать новых
  исследованных контрактов. Нельзя обобщать выбранный MS-1 на весь каталог.
- INFERRED: причиной аварии GUI07 был прежний порядок раннего разрушения GUI.
  После переноса очистки в engine fini native GUI08/09 завершаются с exit0;
  это подтверждает работоспособность изменённого порядка, но точная native crash
  причина без отдельного dump/debug анализа остаётся гипотезой.
- UNKNOWN: общий legacy fragmentation за проверенными ограниченными streams,
  произвольные native RPC, штатный полный bootstrap без диагностической personality,
  последствия всех пользовательских действий UI.
- UNKNOWN: исторические серверные цены/стартовые балансы/региональная политика.
  Собственная test_lab конфигурация не выдаётся за их реконструкцию.
- OBSERVED: один потерянный sync packet и последующий вход после password rejection
  прошли в native-final. UNKNOWN: общая устойчивость произвольных потерь/дубликатов
  с полным GUI. Итоговая серия повторно подтвердила этот узкий loss-control;
  длительные сессии и sequence wraparound не проверены.
- NOT_RUN и вне приёмки этой карточки: Avatar/арена/сетевая симуляция боя,
  исторические боевые правила, экономика и долговременный прогресс.

## Воспроизведение и откат

Подготовить те же проверенные локальные пути в исключённом
`config/project.local.json`. Source native descriptor уже получен descriptor-01;
его нельзя заменять выдуманными bytes. Повторить генерацию в новый каталог:

```powershell
$runTag = Get-Date -Format 'yyyyMMdd-HHmmss'
python -X utf8 tools/hangar_state.py --out "local/evidence/hangar-fixture-$runTag" --native-descriptors local/evidence/20261004-p02-hangar/native-descriptors.json
```

Команда сама запускает21 encoder checks, сохраняет manifest/fixtures/compatibility,
не запускает клиент и не выполняет сетевые операции. Существующие output files
не перезаписываются. Расшифровка результатов и более ранние команды:
`E/data-agent/REPORT.md`, `E/gui-agent/FINDINGS.md`, `E/wire-agent/*.json`.

Точная выполненная итоговая native команда (существующий output не перезаписывать):

```powershell
python -X utf8 tools/gateway_suite.py --source local/evidence/20261004-p02-account/native-final/01-normal --out local/evidence/20261004-p02-hangar/native-final-03 --account-probe --account-bootstrap --hangar-stage gui --hangar-fixture local/evidence/20261004-p02-hangar/fixture-final-02 --diagnostic-no-license-dialog --visible-hangar --diagnostic-open-profile --cases normal,drop-server-sync,wrong-password,normal
python -X utf8 tools/verify_hangar.py --suite local/evidence/20261004-p02-hangar/native-final-03 --out local/evidence/20261004-p02-hangar/verify-final-03
```

Для нового видимого30s теста со снимком ангара, без автоматического ухода в профиль:

```powershell
Set-Location D:\WoT_9.1_Server
$runTag = Get-Date -Format 'yyyyMMdd-HHmmss'
$runOut = "local/evidence/hangar-$runTag"
python -X utf8 tools/gateway_suite.py --source local/evidence/20261004-p02-account/native-final/01-normal --out $runOut --account-probe --account-bootstrap --hangar-stage gui --hangar-fixture local/evidence/20261004-p02-hangar/fixture-final-02 --diagnostic-no-license-dialog --visible-hangar --cases normal
```

Для полной повторной серии в последней команде добавить `--diagnostic-open-profile`
и заменить cases на `normal,drop-server-sync,wrong-password,normal`. После завершения
вызвать `python -X utf8 tools/verify_hangar.py --suite $runOut --out "$runOut-verification"`.
Visual PASS требует отдельного просмотра новых PNG и соответствующих reviews;
автоматический verifier не угадывает содержимое изображения. Занятый instance
mutex вызывает отказ preflight до изменений. Runner не закрывает чужую игру.

Выполненные команды сборки и unit/regression (из корня):

```powershell
. ./tools/rust_env.ps1
cargo test --locked --offline --manifest-path tools/wg_probe/Cargo.toml
cargo build --locked --offline --manifest-path tools/wg_probe/Cargo.toml
python -X utf8 -m unittest discover -s tests -v
```

Команда финального полного аудита, выполненная в новый каталог:
`python tools/client_audit.py manifest --out local/evidence/20261004-p02-hangar/final-state-manifest`.
Supplemental команда записана в SUPPLEMENTAL-COMMANDS.md; её output append-only.
Для нового повторения нужны новые пути, старые доказательства не перезаписывать.

Для каждого запуска runner до изменения research фиксирует before hashes,
сохраняет backup и patch-ledger, после завершения восстанавливает затронутые
файлы и профиль/cache, записывает restore.json. Original используется только
для чтения. Выход0 и restore — отдельные критерии; аварийный GUI07 не исключён
из списка проверяемого отката. Конфиги/клиентские ресурсы/дескрипторы/ключи/логи
остаются в исключённых local/config путях.

Откат server card — поимённо восстановить ранее существовавшие файлы по
E/project-before.json/project-before.zip с проверкой текущих изменений; новые
файлы удалить только после сверки ownership. Данные параллельной web-сессии
не затрагивать. Для отката лишь display-reference изменения достаточно выбрать
сохранённую предыдущую fixture; её прежняя GUI ошибка при этом ожидаема.
Автоматический откат уже выполнен для всех22запусков. После прерванного run,
только когда его собственный клиент остановлен, точечная команда:
`python tools/client_probe.py restore --out <каталог этого client run>`.
Уже восстановленные runs повторно не затираются. Итоговый audit —
E/final-state-audit.json; неизвестные изменения между сериями сохраняются.
Локальный config до/после: E/project.local.before.json и project.local.after.json.
Снимки server source исключают web; Git exclusions проверены для конфигурации,
клиентов и всех файлов E в E/git-exclusions-final.json. Коммит/публикация не выполнялись.

## Приёмка и единственный следующий шаг

**PASS узкого native рубежа:** завершённый original ангар и собственная сводка
статистики с серверными данными, без блокирующего диалога/ожидания, clean exit0,
loss/rejection/relogin controls. Откат к зафиксированному before PASS;
строгое research==начальный baseline FAIL по сохранённым логам другого запуска.
Предыдущие FAIL остаются частью отчёта. Полный P02 PARTIAL, P03 не начат.

Единственный следующий рекомендуемый проверяемый шаг — соединить авторизацию
сайта и native gateway с одним account_id: зарегистрировать собственный аккаунт
на сайте, войти им настоящим клиентом и сопоставить профиль/данные, проверив
неверный пароль и отсутствие выдачи чужого профиля. Эта интеграция в текущей
карточке не начиналась. Сессии сайта передан информационный статус с явным
NOT_RUN web→game, без поручения начинать новую фазу. Работа остановлена до арены.
