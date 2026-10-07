# Ночная работа05.10.2026

Владелец поручил продолжать без его участия до утра. Контрольная точка принята
09:00 Asia/Yekaterinburg, с08:30 стабилизация. Heartbeat этой сессии:
`automation-2`, каждые30мин до утра; после итогового отчёта приостановить.

Стартовая карточка: [минимальный экипаж МС-1](P02_ms1_crew.md). Сначала закончить
её с доказательствами, затем доступные независимые проверки и узкие исправления
устойчивости единого аккаунта/ангара. Арена, бой, экономика и соседние проекты
вне объёма. Мышью и клавиатурой не управлять. Native API diagnostics отдельно
от ручной визуальной приёмки; не закрывать клиент таймером или kill.
Текущая карточка и точное состояние — в последнем checkpoint и docs/STATUS.md.

## Checkpoint01 —01:54 местного времени

- Источники253, БД обеих систем и профиль002 сохранены в
  `local/evidence/20261005-p02-ms1-crew/baseline-01/`.
- Original/research manifest там же в `baseline-client-manifests/`.
- Исследованы original TankmanDescr, inventory[8], два места МС-1, passport и
  dossier. Реальные дескрипторы пока NOT_RUN, первый native экспорт запущен.
- Новые `ms1_crew_probe.py`, `crew_capabilities.py`, диагностический runner.
  Локальные suite17/12/24PASS; их mocks не доказывают native совместимость.
- Rust coherent profile3 branch:62PASS, primaryEXE НЕ пересобран, сервер прежний.
- Новый `ms1_crew_state.py`: validate_base actualr2 byteexactPASS. В разработке
  строгая проверка native export и отдельный guarded Node grant/bridge3.
- Normal003 откатан штатным ledger; latest owner logs сохранены и возвращены
  по точным SHA. Доказательства `normal003-log-preservation*.json`.
- Первый run: `export01-prepare`, `export01-runtime`, root helperPID78172,
  clientPID16540. Проверять outcome/trace; НЕ запускать второй, пока этот жив.
- Live grant НЕ выполнялся. Профили ещё version2/version1, данные прежние.
- Root владеет integration/новым generator кроме validate_export; hangar_data
  проверяет validate_export+tests; hangar_wire —новый ms1-crew.mjs и additive
  game-adapter; hangar_gui —read-only native UI сценарии. Не дублировать работу.

Следующее действие: проверить export01 outcome и actual marker, сохранить
provenance envelope; при ошибке чинить причину по native traceback, сохранить
FAIL, не выдавать синтетические дескрипторы за результат клиента.

## Checkpoint02 —02:23 местного времени

- Export01 actualPASS, envelope `native-ms1-crew-export01.json` SHA
  `df0a9c26181a4efd65bfc8e9c34e2fbabc6f92a860db5676355890e400377a65`.
- Локальные проверки: generator23PASS, probe21PASS;
  полный Node73PASS, Rust62PASS. Подробностив соответствующих data/wire logs.
- **Livecrew GRANTED** основномуUUIDc5326cc1-8524-479c-8bba-72e973489c22,
  journal `primary-crew-grant-01/prepared.json` SHA
  `4a68cd7243af1a10d69110c1c85b8a48d0843d31d8c2dcc70fb05287fcf73bef`.
  Profile3 SHA5167ea63f0503952b4ab1e7c4b1ed2dca5e5da6b6812bd476a87124a891e0888;
  повторapply ALREADY_GRANTED. Generator/Node/bridge **заморожены**: journal
  проверяетsourcehash. Не править их ради следующей маленькой UI-задачи.
- Новыйgateway4e22d2fd… собран; serverRUNNING run20261004T210716-864dea,
  supervisor88612/identity3616/gateway27928. Configfiles неизменны.
- Crew01 FAIL из-за observer:getItemsData имеет typeCDkeys, а не inventoryIDs.
  Поправлен толькоhelpercc02507c…, экспортфункциянеизменна, oldproof остаётся.
- Crew02/03: actualscriptcomplete,3exactcrew snapshots,2nativePNGs каждый,
  штатныйexit0/capture/rollbackPASS. Root просмотрела4PNG; reviewJSON вобоих
  prepare. Crew02→03 cached relogin выполнен без очисткиprofile002. Независимый
  nativeverifier агентwire пока дописывает, итоговый PASS ещёне закрыт.
- Website перезапущен штатнымguardedscript: PID48784,тотжесохранённыйnetwork
  config/порт3091 +GAME_BRIDGE_ORIGIN127.0.0.1:20020/tokenfileстарый. Before
  runtimebackup `website-reload-01`. Actual primarylogin/API/cabinet PASS,
  `website-proof-01.json`, crewMS1true/IS7false. APIforeignqueryignorePASS.
- Аккаунтыпослеrelogin: primaryexactcrewdelta,secondbyteidentical,immutable
  identitypreserved. `accounts-after-relogin-01.json`.
- Сейчасclient закрыт,diagnostic overlays откатились; normal004 ещёНЕ
  установлен. Следующее: закончитьindependentverifier/двеnativeпроходки,
  закрытьотчёт/MS1crewSTATUS, затем новаяузкаякарточка UXнеподдерживаемых
  действийангара. Dataагентпокаread-onlyисследует battlebutton/старыйwelcome
  текст, не начинаетсяарена/бой/экономика. Не дублироватьживыхагентов.

## Checkpoint03 —02:55 местного времени

- Crew02→03 принят независимым verifier и повторён root с тем же report SHA
  ec625af4067714e80c56a7bb260007483f1ef8736da2ea5c7d452683c7961dd6.
  Отдельный review data-агента PASS, ручная приёмка NOT_RUN.
- STATUS, P02_MS1_CREW и план экипажа обновлены. Normal004 пока не установлен.
- Начата узкая карточка `P02_hangar_service_limits.md`, evidence
  `local/evidence/20261005-p02-hangar-limits/` (H). Новый baseline271 sources,
 14 local files, consistent2DB сохранён до реализации.
- Политика боя не меняет original update/данные машины; только два guard
  binding и явная подсказка. Greeting меняет ровно system_messages:connected.
  Никаких изменений frozen backend/fixture/generator, очередь не реализуется.
- Проверки: policy20+oldmodule14 на Python3 и2.7.3; greeting16; scenario24;
  runner30. Нативная приёмка этой карточки ещё НЕ закрыта.
- Limits01 запущен root, helper63580/client49264. Перед вторым запуском
  обязательно дождаться outcome/mutex. Частично видно disabledFalse и новое
  приветствие, но сценарий застрял на неверном bootstrap profile observer.
  Реальный ProfileSummary активен; run должен завершиться штатно после
  исчерпания600 observations и остаться FAIL. No kill/таймер harness.
- Exact10 sources limits01 сохранены в H/limits01-sources. Исправлен только
  новый scenario: readiness через measured interactive Profile observer.
  Data-агент дописывает regression; wire — независимый limits verifier;
  GUI — read-only аудит ещё не готового окна внешнего вида. Не дублировать.
- Следующее: проверить завершение limits01, запустить limits02 с новым
  свежим control/prepare/runtime, проверить6PNG и cached повтор. Потом
  обычная установка/финальный аудит. Компьютер не выключать.

## Checkpoint04 —03:40 местного времени

- Limits02→03 принят строгим verifier; root повтор с тем же report SHA
  f296eaedd7e9c40aad4a7da9d58d24070cfbbf25819da2775d3a4abf74162587.
  63 verifier tests PASS. Limits01 остаётся FAIL ошибочного profile observer.
- Normal004 установлен и полностью проверен: H/final-audit-01/report
  (`final-state-audit.json`) SHA506c0792bf55f1bac0fda5c21ca3d00f364fd1e01a4c993be3ad93395755dddb.
  Original3469/research3484 все SHA, неожиданных отличий0,7ночных restores.
- Начата следующая узкая карточка `P02_hangar_windows.md`, evidence W=
  `local/evidence/20261005-p02-hangar-windows/`. Baseline280sources/14local/2DB.
  Два original AmmunitionPanel callbacks теперь guard до fireEvent, родные
  Warning; кастомизация/ремонт/пополнение не реализуются и не имитируются.
- Policy helper SHA3d68c281050cad0c5318bf07d0ef7899815aaa946e29d3d109bbcaf9cd738f14,
  source freeze.110 policy tests PASS (новые21+старые34 на двухPython).
  Scenario SHAb44cd18f2b2fde1d0aa8bebf830d7fcaa6a0ec331b978d256c1e15a76cafdf36,
  31tests/compile2.7 PASS. Runner33; passive trace4; interactive regression18PASS.
- Original WINDOW.getView безcriteria возвращаетNone, поэтому сценарий
  использует проверенный alias query technicalMaintenance + getViewCount и
  current LOBBY_SUB. Fake-empty scan не засчитывается как отсутствие окон.
- Normal004 уже откатан после22exact checks. W/normal004-prerollback.json
  и local/client-install-004/restore.json PASS. Normal005 ещё НЕ установлен.
- Windows01: nativecomplete/exit0/restore,78packets35.002s,3crew/3PNG;
  root просмотрела3 PNG и сохранила visual-review-windows.json в prepare.
  Полная независимая приёмка ещё NOT_RUN, wire-агент завершает verifier.
- Windows02 сейчас helper76656, prepare/runtime в W. Перед следующим
  клиентом дождаться native-outcome/mutex. Data-агент готовит read-only
  final_audit для normal005. GUI-агент закончил read-only контракт
  потенциального следующего same-process logoff/relogin, пока НЕ начинать
  реализацию до закрытия W. Root integration frozen до завершения run02.
- Сервер/сайт живы, profile3/MS1crew, backend/generators/fixtures frozen.
  Следующее: завершитьwindows02 и визуальный review, независимый pair proof,
  normal005 безcontrol/autoquit, fullmanifestаудит/документы; затем отдельная
  карточка same-process relogin в рамках готового ангара. BattleNOT_STARTED.

## Checkpoint05 —04:01 местного времени

- W/windows01→02 принято, report62a206bf7c208a313900b12e5cfdcf30b4a7690d01676ae8e7ea81a4d78903ec,
  root повтор exact. В каждом78packets/3PNG/3crew/12cleanup/exit0/restore,
 0 свежихошибок. Verifier53PASS, дополнительныйreviewGUI36controls+156packets
  linkagePASS. Все Windows sources/verifier заморожены.
- Normal005 установлен,20immutable+3logs,11accepted compiled modules и2MO,
  безcontrol/autologin/autoquit/capture. Клиент закрыт. Full original3469/
  research3485 auditPASS0unexpected;9restores/29frozenbackend/обаprofiles.
  W/final-audit-01/final-state-audit.json SHA
  ddbfa7525ce105e44518f1ae4bb797e31db588af46718fb898503627788eda32.
  README,STATUS,P02_HANGAR_WINDOWS ипланобновлены; P02PARTIAL/бойNOT_STARTED.
- Следующая отдельнаякарточка `P02_inprocess_relogin.md` начата,R=
  `local/evidence/20261005-p02-inprocess-relogin/`. Baseline288sources/14local/2DB.
  Цель1EXE/init→первыйангар15s→originalapp.logoff→достоверныйLoginView/
  disconnected/repositoryNone→второйoriginalsubmit→второйангар15s→exit0.
- Root добавила12й module name hangar_relogin_scenario, новый opt-in flag
  verify_inprocess_relogin/conditioninprocess_relogin_observed. Credentials
  толькоarm(username,password) вRAM; clear_credentials наquit/fini.
  Runner37PASS, directcontrol/trace5PASS, interactive23PASS; sourcecompile
  check01 был до добавления passive target _delAccountRepository.
  Передnativeбудетнормальнаяprepare-компиляцияактуальныхsources.
- Владение: GUI новый client_patch/hangar_relogin_scenario.py+егоtest,
  wire новыйtools/verify_inprocess_relogin.py+егоtest (derivedcapturesegments
  только вновом --out, полныйbinding/no-gaps/no-overlap), data read-only
  server/clientretirementcontracts. Root integration/tests+launch/docs.
- AppEntry.logoff decoratedwrapper возвращается раньше реальногоdisconnect;
  isDisconnected() включаетtransition. Нужен фактический status==disconnected,
  originalAccountnonplayer иactualAccount.g_accountRepositoryNone. Passive
  native_logoff_call покрывает exactAppEntry/framework/ConnectionManager
  иAccount._delAccountRepository (безlocals). Pointer/port/requestID reuse
  допустим, уникальность sessionkey нельзя навязывать бездоказательства.
- Rprepare_run.py/rollback_normal005.py созданы, НЕ запускались.
  НовыхnativeRrunпокаНЕТ,normal005ещёinstalled. ПередзапускомдождатьсяGUI
  sourcefreeze иunitchecks, затемguardedrollback005 иfreshrelogin01prepare.
  Старыеgenerator/backend/journalpins иprofiles untouched. Сервер/сайтживы.

## Checkpoint06 —04:29 местного времени

- R01 завершён: original logoff и очистка Account repository PASS, второй
  actual login отвергнут gateway (`retired_or_rate`, code73). Native сохраняет
  cipher key, меняет encrypted nonce и LoginApp peer. Second BaseApp peer UNKNOWN.
- Строгий FAIL сохранён в R/wire/verify-relogin01-negative-01, report SHA
  8b3dea4c27a28b51861672b5cb54601e8a32ee19af76a0b1ee85deb39d808dfe.
  95 packets/5182B, один PNG/crew, exit0/12cleanup/restore. Сценарий исчерпал
 600 наблюдений (625.467s); не было kill/timer, fresh python.log errors0.
- Normal005 проверен по23 hashes и откатан. Сейчас клиент закрыт, временные
  диагностические файлы восстановлены; ordinary normal006 ещё НЕ установлен.
- Old gateway/verifier/tests сохранены R/wire/verifier-before-gateway-fix-01.
  План дополнен доказанным дефектом. hangar_data владеет узким исправлением
  gateway091.rs+Rust tests: retired nonce/peers,32 records/120s, fail-closed
  capacity, fresh website KDF, pre/post worker checks, staleACK rejection до
  transport Window, старый lab guard. Не build/restart, это сделает root.
- hangar_gui владеет v2 scenario/test: passive note_login_result и orderly
  error при actual rejected second login. Root интегрирует watcher callback.
- hangar_wire владеет strict verifier: source/version pins, два actual wire
  legs, private equality только booleans и endpoints. 51 checks PASS.
- Из1081 original pyc и EXE не установлен callable rekey API; UNKNOWN,
  не выдумывать reset API/не менять hardware tag как будто это cipher key.
- Сервер прежний run20261004T210716-864dea, сайт жив. Генераторы/fixtures/
  profiles/configs заморожены. Следующее: закончить узкий fix+negative tests,
  guarded rebuild/restart, freshR02 native, независимый двухэтапный proof.

## Checkpoint07 —04:52 местного времени

- Gateway frozen `2edd6e6c0c36fb2544bc66fd6d7252b6a4e0d59b1e24cba7f1fb2c2800738ade`.
  Rust83/83 PASS (21 новых, включая actual state-changing tokenless ACK control).
  GUI independent source review0 blockers, R/gui/gateway-review-01.
- Scenario v2 frozenecb3e4b0…6d120,112 checks на двух Python PASS; root
  sr_interactivec5b76490…5e982, integration24PASS. R02compile12modules PASS.
- Guarded server rebuild: первый PowerShell wrapper FAIL (execution policy,
  cargo не найден; ложный exit0 пойман неизменным EXE). История сохранена.
  Прямой pinned cargo offline/locked PASS, source unchanged, new EXE
  8aea2e503c3b20e13b5eb9a9be7d66d2912a5027d8404a268bf65dfc778c41e1.
  R/server-rebuild-01/{before,after}.json и build-direct01 command/logs.
  Сейчас server RUNNING run20261004T234409-c866fd. Сайт не перезапускался,
  четыре config hash прежние; аккаунты/генераторы/fixtures не менялись.
- R02 native завершён: PID90800, два LOGGED_ON и два16s готовыхангара,
 2crew/2PNG/188packets, exit0/12cleanup/restore PASS. Root просмотрела
  relogin_first_001.png и relogin_second_002.png (native globalcounter),
  visual-review-relogin.json записан. Resource/profile/crew snapshot прежние.
- Полный строгий verifier ещё IN_PROGRESS. ПервыйR02report FAIL сохранён
  0d00b34451158eb078f5e64f58016c46fc170f7241e9498234aa03f35843fa2b:
  старый resourcechecker захватил ужеdisconnected transitionalUI снулевыми
  ресурсами иstaleitems_synced. Wire исправляет только original lifecycle
  bounds, не фильтрацию по ресурсам, добавляет negative controls.
- GUI review выявил gap binary/source provenance: wire добавляетобязательную
  связь R/server-rebuild-01 build→afterstate→actual nativegateway_run.
  Никакого нового native run только для verifier исправлений не требуется.
- Normal006 подготовлен и проверен,12modules/21immutable+3logs, exactR02pyc/MO,
  no control/autologin/autoquit/capture. НЕ установлен доstrictPASS.
- Data R/final_audit.py готов (c3e8582c…9033),5 negative unit controlsPASS,
  final auditNOT_RUN. RootпослеPASS установитnormal006, запуститполные
  original/research manifests, затемdataполучитexactnative reportSHA/manifests.
- Следующее: strictR02PASS+independentreview, rootrepeatverifier, ordinary006,
  fullaudit/docs. Только после закрытияR отдельная следующаяузкаякарточка.

## Checkpoint08 —05:08 местного времени

- R карточка закрыта PASS. Final verifierf55ee426…7374,83 checks PASS.
  R/wire/verify-relogin02-03/report9f42acfd…b071, root повторPASSb0152450…1369.
  Разные derived output paths объясняют разные report hashes.188 исходных
  packets=93+95,2freshauth/2Account/2точныхstreamsets/2PNG/0ошибок.
- GUI independent review PASS,0remainingblockers: build-chain и8negative
  controls, compiledv2→v1 downgrade иcallbackreorder теперьотклоняются,
  все188 packet/linkage и2PNGнезависимосверены. R/gui/relogin-verifier-review-01.
- Normal006 УСТАНОВЛЕН иfullauditPASS, report0ff1f08a…ff35,helperc3e8582c…9033.
  Original3469/research3486,0unexpected,11diagrestores,12modules/21immutable+3logs,
  no control/autologin/autoquit/capture.29backends:28unchanged+gateway2edd;
  4configs/обаprofiles/fixtures byteexact. NativeclientCLOSED,server/sitelive.
- Сервер run20261004T234409-c866fd: supervisor55120,identity58628,gateway23912,
  EXE8aea2e50…41e1. Website PID48784 unchanged. Generator/journalpinsFROZEN.
- Исходный R01 FAIL и промежуточные R02 validatorFAIL/PASS сохранены.
  docs/research/P02_INPROCESS_RELOGIN.md,STATUS,README,plan updated.
- Следующая выбранная отдельнаякарточка: primary→secondary→primaryв1EXE,
  изоляция Account/машин/экипажа/cache. Read-only обоснованиеR/data/next-check.md.
  Старый native secondaryPASS не покрывает нынешнийr1-catalog2, UNKNOWN.
  Inputsесть; действующееночное поручениевладельцапокрываетэтуузкуюпроверку,
  дополнительное разрешение/пробуждение пользователя не нужно.
- До новых правок создать docs/plans/P02_account_switch.md и Sbaseline,
  S=local/evidence/20261005-p02-account-switch. Никакихновыхgrant/fixture/config
  измененийзаранее. Тотжеprofile002 неочищать. SecondaryодинМС1/0crew,
  primaryМС1+ИС7/2crew; balancesодинаковыисамипосебенеproofизоляции.

## Checkpoint09 —05:29 местного времени

- S карточка IN_PROGRESS, baseline295sources/14localfiles/2consistentDB сохранён.
  Normal006 пока установлен, native закрыт; server/site прежние. Ничего в
  profile002, fixtures, генераторах и gateway не менялось.
- Новый account_switch_scenario frozen f3ef956c…9f0f:91 executed unit PASS,
  1 Py27 static-version SKIP (этот static test PASS на Python3).
  Новый account_switch_expectations frozen2e3cdd97…76e1,24 checks PASS,
  два actual fixtures дают1422B public expectations, разные raw dossier SHA.
- Root добавил узкую интеграцию13-го compiled module/explicit control/watcher/
  cleanup. Root control9, runner regression37, interactive regression24 PASS.
  GUI независимо проверяет интеграцию; wire завершает strict3session verifier
  иnegative controls. Data готовит отдельный final audit дляnormal007.
- S/rollback_normal006.py и prepare_run.py созданы. Rollback/prepare/native
  пока NOT_RUN. Первым перед запуском проверяются24 файла normal006 против
  принятого полногоmanifestR, затемstandardrollback иfreshswitch01 install.
- Секреты толькоRAM/consumedcontrol; trace содержит лишь public expectations.
  Ручной ввод/скрины пользователя ночью NOT_RUN. Управление мышью отсутствует.

## Checkpoint10 —05:55 местного времени

- S завершена PASS. switch01prepareFAIL доclientchanges (normal006 ещё стоял),
  историческийFAIL/controldeleteбезdigest сохранены. Затем24fileguard+rollback,
  freshswitch02nativePID7600:86.04s/3auth/3Account/279packets/3PNG/0errors/restore.
- Fleet2→1→2/crew2→0→2/nativeID1→2→1, exactdossier/streams/cacheAreturn;
  actualready16.073/16.076/16.070s. PNGroot+GUIviewed; secondarynickname1024px
  clippingOBSERVED, полноеимяgetter/stream. Цветноезерноoutsidecard.
- Runner421a546e…ae747 fix: controlchecksumRAMonly, no credentialderivatives
  inartifacts;40runner+9control+10independentreviewPASS. Nativecompiledunchanged.
- Verifier60ffcbbe…29d4 frozen,46tests+31independentreviewPASS. Intermediate
  report2b30/audit01 preserved: verifierallowedunknownpublicsecretmetadata;
  exactschemafixed. FinalreportS/wire/verify-switch02-02SHA530dd127…12dd6,
  rootrepeatPASS c5782cfd…59a06, GUIreviewd4e1ffc6…04501, finalwiremanifest829b…f38.
- Normal007 УСТАНОВЛЕН,13modules/22immutable+3logs/noauto/control/capture.
  Fullmanifestoriginal3469/research3487/0unexpected; finalaudit02PASS
  5f3f202c…02c42,12restores20negativecontrols,29backend/4configs/2profilesunchanged.
  NativeCLOSED, sameownserver55120/58628/23912 andsite48784live. NoDB/generatorchanges.
- Начата только новая Tcard: docs/plans/P02_retired_base_replay.md,
  T=local/evidence/20261005-p02-retired-base-replay, baseline304sources17files2DB.
  ReusefrozenSscenario безclientpatches. Dataделаетtools/retired_base_probe.py
  +tests, wireverify_retired_base_replay.py+tests, GUIindependentreview.
  Rootownsrollbacknormal007→prepareTnative→normal008later.
- Exactly3currentfirstAoriginaldatagrams (tokenlessfeedback1+logout2), bindoldA
  endpoint exclusive/noSO_REUSEADDR whileactualBready andTTL120. Busyport→NOT_RUN,
  noalternatepeer/noexternalLoginRequests. Fullcapture+strict injected/native
  indexhashpartition; everypacketaccounted. Покаsockets/nativeNOT_RUN.
- Дальнейшее до08:30 пооднойузкойкарточке;08:30стабилизация/09:00final+pause
  heartbeatautomation-2. Пользователя не будить, компьютерным вводом не управлять.

## Checkpoint11 —06:08 местного времени

- Tdata sender иTwire verifier в разработке, native/socketNOT_RUN.
  GUIstaticreview: original Bready→logoff17.0926s, PNG→logoff1.7754ms — trigger
  толькораннийfreshstate2, неPNG. Sourceguard/captureпровереныbeforedecrypt.
  SenderdraftнайденыsafeFAILpin typo/publicsize иbackendprocessrecheckgap,
  dataисправляетдоfreeze; агентsocketнеоткрывает.
- Root25fileguardnormal007+standardrollbackPASS. Tnormal007-prerollback.json
  иrollback-lineage-check-01.json фактическиеPASS, baseline3470=original+ownerbak.
  Fresh T/replay01-prepare/runtime/controlсозданы,13compiledmodulesидентичныS;
  EXEНЕзапущен. Контрольprivate/unconsumed, нечитатьвoutput.
- Tprobeбудетзапущендонаtive runner с--outT/probe01; ждётarmed.json, затем
  realnative-process.json. Bound180sтолькопробе, неgame. Exactly3sends,
  exclusiveoldpeer; первые3sactualBstabletrigger. Wrong/busyport→NOT_RUN0,
  partialsend→FAIL. Передкаждымsendnative+gatewayliveness/actualBready.
- Wire18partition/sourcecontrolPASS, finalTcorrelationgateпишется. Fullrawcapture
  сохраняется, exactly3injectedingress+3rejectlinesотдельноучитываются, native-only
  derivativeявноanalysis_view_not_a_native_run соstrictbijectiveindexmap.
  Rootподтвердилаэтоттехническийспособ, oldSverifierнеизменяется.
- RootновыйTfinal_audit.pyDRAFT (неfrozen) созданизhash-pinnedSaudit; prepare
 12negativecontrolsPASS_UNIT_ONLY, fullauditNOT_RUN. ActualrollbacklineagePASS.
  Ждётwireфинальныйreportshapeиnative. Helpernormal008checker/visualreviewсозданы,
  syntax5localhelpersPASS. Normal008неподготовлен/неустановлен.
- Сервер/site прежниеlive, клиентCLOSED. READMEещёфиксируетпринятуюSordinary007
  исторически; actualрабочаяустановкаSTATUStop. MISSING_INPUTSобновлёндоS/T,
  созданпромежуточныйdocs/research/OVERNIGHT_20261005.md безclaimsбудущегоPASS.

## Checkpoint12 —06:45 местного времени

- T закрыта PASS. Replay01 PID96040:85.961s,exit0/12cleanup/restore;
  280packets=277native+3replay64B. Старый peer55682 освобождён, три точных
  datagrams отвергнуты retired_base_peer; B56307 остаётся ready, A возвращён.
  Native report8a7274f8…f72f5,rootrepeat5f5431ef…a174;3PNG просмотрены.
- Sender61b41911…b8720/27tests,verifierf6503fd5…62f3/59tests frozen.
  GUI58controls/full14gates PASS,manifest a3890a1f…623b.
  TTL120.0 first verifier FAIL сохранён, исправлен finite numeric gate;
  источники и native evidence не переписывались.
- Normal008 УСТАНОВЛЕН,13modules/22immutable+3ownerlogs, noauto/control/capture.
  Normal007 проверенно откатан. Полные original3469/research3487,0unexpected,
  13restores/28auditnegativecontrols/29backend4config2profiles unchanged.
  T/final-audit-02 SHA05a20913…a066 PASS; helper6361d3d9…d835 frozen.
  Первый audit FAIL(trace.file/path) сохранён. Independent review actual binding
  и17negative controls PASS,T/data/audit-review-02/result.json6346d054…e964.
- Клиент/probe CLOSED,server55120/identity58628/gateway23912 прежние,site48784.
  README/STATUS/MISSING_INPUTS/Tplan/Treport/nightdraft обновлены по actual PASS.
- Data read-only исследует один следующий шаг:15–20min стабильного ангара,
  реальные periodic server updates/сохранность профиля. Карточка ещё NOT_STARTED,
  native NOT_RUN. Никакой арены/экономики/новых выдач. Не менять frozen scenarios
  ради длительности.08:30стабилизация,09:00report+pauseautomation-2.

## Checkpoint13 —07:02 местного времени

- Начата одна Lcard, docs/plans/P02_long_hangar.md,
  L=local/evidence/20261005-p02-long-hangar,baseline311/17localfiles/2DB PASS.
  Цель181 originalstatsreturns/span900s continuousready+3snapshots+2nativePNG.
  Это собственные CCU1/1,неplayerbattleprogress. Backend/fixtures/config прежние.
- Normal00825fileguardPASS,c23a1430813c78563fcc1667fc91cd55cf3d8a942c5597c1669b660e17fe6156,
  штатныйrollbackRESTORED. Data независимая clean lineage3469/3470PASS.
- Root3integration frozen: sr_interactive b56ceb1b…b947,
  interactive_client8c8db390…8894,diagnostic_client_run e8828342…5099.
  New9controls+old40runner/9switch/6relogin PASS; independent8boundarycontrolsPASS.
  Отдельнаяcondition безexternaltimeout,actualtraceexhaustion→FAIL/nativequit.
- GUInewlong_hangar_scenario6d13f7d8…fb0d,30Python3+30nativePython2.7.3testsPASS.
 14compiledmodules prepared,9253capturepackets remaining,preflightPASS.
- long01 ЗАПУЩЕН06:59: harness70104/native49420,
  traceL/long01-runtime/native-49420-1791165541310.jsonl. На07:01 ready121.6s,
  24eligibleoriginalreturns,actualspan116.1s,maxsamplegap1.016. ЭтоPROGRESS,неPASS.
  Не трогатьактивныйклиент/файлы,неkill;nativeусловие181+900s+2PNG закрываетсамо.
- Wireпишетverify_long_hangar/tests;GUIindependentreview. DataL/final_audit.py
  draft27negativecontrolsPASS,fullauditNOTRUN. RootпослеnativeсмотритобаPNG,
  пишетvisual-review-long-hangar.json,проверяетreport,ordinary009/fullmanifests.
  До08:30можно закончитькарточку,после—стабилизация.09:00итог/pauseautomation-2.

## Checkpoint14 —07:46 местного времени, утреннее завершение

- L long01 завершён:913.294s непрерывного ready,182ответа CCU/181eligible,
  2580packets,3совпавших snapshots,2просмотренныхPNG,exit0/cleanup12/restorePASS.
  Final20gate report c74df143…95d25,40tests и55independent controls PASS.
- Полные original3469/research3488,0unexpected,14completedrestores;
  finalaudit19326505…cf1e PASS. Independent audit review11actual bindings и
  38negative controls PASS, result c8299790…617b. Старые FAIL сохранены.
- Normal009 установлен:14modules/23immutable+3ownerlogs, noauto/control/capture.
  Клиент закрыт. На07:37 runtime-check-01 PASS:mutexfree, website/identity health,
  реальные process hashes и26current package files. Сервер и сайт работают.
- Итог docs/research/OVERNIGHT_20261005.md и точный FILES index подготовлены.
  F=local/evidence/20261005-overnight-final: source-inventory-01,repository-check-01,
  runtime-check-01; итоговый ZIP authored sources и manifest сохраняются здесь же.
- Automation-2 PAUSED через app tool, подтверждённый ответ PAUSED. Завершение утром
  раньше верхней границы09:00: начатые карточки приняты, новый длинный эксперимент
  не запускается. Компьютер/сайт/сервер не выключались; Git не staged/committed.
- Единственный следующий шаг: настоящий session_deadline1800→disconnected→
  LoginView. Сейчас UNKNOWN/NOT_RUN; read-only feasibility сохранён в L/data/.
  Ручная приёмка новых ночных изменений NOT_RUN. Полный P02 PARTIAL, бой не начат.
