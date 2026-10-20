# Ночной checkpoint — 2026-10-16, P04M active

## UPDATE: latest (остальное ниже описывает более ранний WIP)

- RootHEAD **786a516** (merge C#component220e008); branchP04M без смены.
- C#candidate06 **PASS component**: actualgetters3/maps7/handling+contact6/
  negatives6/legacyv1-v2null2/catalog+scalarwitness+ACK6. Contactmax1.29/13.57/.80mm,
  limit50mm. Six repeatcases2091frames bit-exact; priorP05Cv1wholeframes182 exact.
  Receipt local/evidence/20261016-p04m-physics01/component06-receipt.json.
  C#worktree commit220e008 frozen. Source-policy Discrete+collisionSteps4 only
  new-kind scenes, legacy1; всеCCDизмененияудалены, прежниеFAILы сохранены.
- Rootскопировал getters06 smallqualified3 JSON в drive/worker/p04m-*-qualified-profile.json
  и сгенерировал ram_proof::Profile5+for_vehicle/mass/half/binding из настоящихbits.
  SHA T26=9674a5e9ef24b9f1c857845bd6021aeb302333ed2c3d52e92f07eb0bb85c7217,
  T34=1ac77973e1ca2b18449102b814c23c9208e9b91f61d9f16afeb73a58f9d0583e,
  T3485=ebe62bae0281f775b45f269a37919e86fbc99789eac789fc9368c42210880a0a.
  emit_rust_profiles.py сохранёнignored, повторно поверхфайлов НЕзапускать.
- Drive VehicleProfile supportsnewclosedSHA/config3, checksnativebits/physicsprojection;
  Pool.shared_source_profile getter готов. SceneKind5/SceneSpecv2 ready, exact6keys
  EVERYactor source_profile oldnull/newref, inputfilepin checked; v1exact5keys unchanged.
- RootWorld/Trace profilelabels/for_vehicle+fragileammo propagation исправлены.
  Rootnew p04m_capacity_tests.rs(3tests) checksreal960shotadmission, mounted160/
  legacy96, fragilebudgetbind-beforeevents; modulewired, ещё NOT_RUN.
- Firstcompile01 FAIL ровноодна exhaustivepolicy_for match fragiles newtypes;
  исправлена. **СЕЙЧАС compile02**, execsession20927, gatewaybuildwithouttests:
  `python -B -X utf8 server/build.py gateway --out local/build/server/gateway-p04m-compile02`.
  На productionfreeze не менять runtimeпоканеокончится (Pythonwriter продолжает).
- Protocol bridge готов/frozen: curatedmanifest3/Vec2or5/resources/sourceprofiles,
  BatchRuntimeScenev2 nullold, Profile::for_vehicle,6newtests.
- P05Cagent теперь пишет ONLY ROOT NEW drive/scene_worker/tests_p04m.rs; rootуже
  wiredmodule cfgtest path, файл покаотсутствует. Actual Rust→C#06→original
  shared_angular_proof(FrameProof) new3+mixed6/150advances/staticpreparedACK/negatives;
  build/test не запускать покаagentнеfreeze. Worldclaimневыдумывать.
- Writer4registrytestsPASS, tools/p04m_stock_registry.py+testготовы. Реальный
  newPoolStore/crew/ammo optinpath вработе, новыйcrew/ammo companion потребуется
  Rustrootдоnative. OldP08Bcompanion/ledger/frozenF-Kконтракты неизменять.
- Оригинальныеcheckpoint03:25/P05Csourceгейты исторические, P07Bfull975ужеPASS;
  никакогоactivefull/sourcegateсейчаснет, только compile02безтестов.

Новее checkpoint0325. NIGHT_20261016 продолжать без ручных вопросов. Владелец
спит; native/UI NOT_RUN, main не сливать. Root D:/WoT_9.1_Server, branch
**codex/p04m-five-battle-profiles**, HEAD **87d65a3**. В runtime есть shared WIP,
не reset/checkout/конкурирующие edits. Heartbeat wot-16 до08:00+05.

## Пройденные и сохранённые карточки

- Main ffce8cb/STAB01; P08B c7999e6, P08C2ef781f сохранены, приёмка утром.
- P05C branch codex/p05c-shared-physics docs9f2df41/runtime019ed2f:
  full03 **940PASS/5ignored/buildPASS**,602sourcefiles before/after PASS.
- P07B branch codex/p07b-server-visibility docs **e711844**, runtime
  **8fecb9dc59e51052c983cbfc7f5dd52161af6a8b**: focused23PASS/build;
  full01 **975PASS/5ignored/buildPASS**,607files sourcebefore/after PASS.
  Exe a969893a4763fa6d8514244162a7313051e5242669e90a2bf97a0f2274193cd9.
  Full/source gate ЗАВЕРШЁН, не запускать after ещё раз и не переписывать proof.
  Source-bound actualmap360LOS/20sixrecipient snapshots:1153us/matrix debugOBSERVED,
  no performance/native claim. Public hiddenattacker killonce fix+realAP3shot test PASS.

## Стенд (не запущен)

local/stands/night-battle-20261016-01: own SQLitebackup A108/MS1AP14/IS7AP19/fullcrew,
B25/MS1AP14/IS7incompletecrew, sourceDB unchanged. 3481/20130/20131.
Oldfix03 ledgerrollbackPASS, newplans38pycCPython2.7.3 each PASS, install/services/client
NOT_RUN. Source P05C binding.json исторический. gateway.json теперь18fields/
visibility_v1=true; P05Cbackup gateway-p05c-before-visibility.json и visibility-mode01.json.
**binding-p07b.json actual bindPASS975/5/sourcegate**, run.py check22resources PASS.
Текущий P04M runtime WIP не соответствует P07B binding; для запуска нужен новый
итоговый gate/binding или явный checkout P07B без потери WIP. Не launch старый
exe с новым runtime. Новые клиентские планы ещё не установлены.
Сервисы/клиенты лучше подготовить к утру, session lifetime≤2h; запуск03:30 истечёт
до08:00. Original C:/WoT_0.9.1_RU_0717_original readonly; copies local/clients/p03f/a,b.

## P04M ownership и текущий WIP

Root restored importer/test из staging, exact source11PASS и oldcontact23PASS
повторены. Committed87d65a3 source importer/plan/report/ACTIVE. FutureP04M stage
теперь восстановлен полностью; receipt local/night-staging/20261016 сохранён.

- Protocol night_p08c_protocol: combat files vehicle_profile/geometry/materials/AP/aim
  +p04m_combat_profile_tests.rs и p04m_geometry_tests.rs (5tests NOT_RUN), frozen.
  Enum5 Ms1/Is7/T26/T34/T3485, ALL/index()/from_label/from_vehicle_compact_id,
  ranges240/400/280/240/350, newinitial20AP explicittemporarylab, ownedadmissionfalse.
  Separate exact3 sourceJSONloader schema p04m-battle-source.v1, sparsearmorIDs.
  NEWownership: shared/profile13_templates.rs,server.rs,server_scene_runtime.rs:
  manifestv3 curated5, VecResources/maps, pernewactor source_profile pin,
  actorSceneSpecv2 fornew kinds; oldv1/2 kept. Не править эти файлы параллельно.
- Root: model/impact/fire/fragiles/wire/ram_proof +drive/worker/profile.rs и
  drive/scene_worker.rs. Уже WIP: MAX_AMMO160/global960; Worldgeometryarray5/index;
  World/Trace mixedbudget max(96,maxboundkindammo)*N preservesoldtwo-kindceilings;
  fire.with_mounted_loadout(ammo,reload,capacity) preserveslegacy96constructor;
  fragiles.State.ammo_capacity default96/bind_ammo_capacity beforeevents;
  Worldattach cloneTrace+fragiles, newsourcefire; start checksactualactorgeometry;
  wireold6test usesw.shot_limit insteadglobal960.
  ЕЩЁ НЕ СДЕЛАНО: ram_proof Profileenum5+for_vehicle/getter data; Trace/model old
  Profilematches; Trace bindfragiles/Worldbindfragiles propagatealreadyboundammo;
  new3 SceneSpec/VehicleProfile loader fullqualifiedsourceJSON support; source
  trace labels newkinds. Из-за этого compile сейчас ожидаемо ещё НЕ запускался.
- Writer p08b_writer_research: tools/p04m_stock_registry.py+test (4PASS), Python
  optinPoolStore/crew/ammo versionedmigration draft/work, battle/profile13.rs ifneeded.
  NativeID3 ownerA реальноObject261, неТ26. OldP08Bpolicy/vectors/frozenF→Kledgers
  нельзя менять. New3 admissionfalse until owner; propernewcrew/radioman/current
  snapshot/companion нужен дляownedroute. Root явно поручил продолжать реальный
  PoolStore+projection, не заканчивать толькоmetadataprep; reportunsupported честно.
- P05Cagent night_p05c_plan: отдельный existingworktree
  C:/Users/NSNull/.codex/worktrees/p05c-night-shared-physics/WoT_9.1_Server,
  branch codex/p04m-physics-profile-prep от9c26910. OwnC#only, rootcherrypickпозже.
  Actualgetter3/nativebasis+analyticboxPASS, maps6+sixmixedscene7PASS, handlingPASS.
  ContactT26firstimpact7.6316cm>5cm FAIL сохранён flat01/02/05. CCD ineffective;
  setterMotionQuality haslocalJoltSharp ABI issue (in enum) foundactualreadback.
  ОтCCD полностью отказались. **Сейчас candidate06 Discrete + collisionSteps4
  onlynew-kind scenes**, outer60Hz controls/ticks unchanged, oldv1collisionSteps1.
  Нужны actualcontact/handling/staticcatalog/angularwitness gates; не ослаблять5cm.
  Outputs local/evidence/20261016-p04m-physics01/{gettersNN,flatNN,mapsNN,...}.
  Getter05profiles существуют, но mappingCCD устарел: НЕ считатьfinal и неembed
  их SHA до frozenfinalcandidate. Native mass/inertia numbers stableactualmeasured.
  qualified_worker_sha inJSON — provenance, not equality againstcurrentDLL;
  runtime checks fixedmanaged/nativepins,closeddefinition/config/getterbits.

## Дальше

Дождаться frozenfinalC#profiles, подключитьnew3 в Rootdrive/scalar/SceneSpec,
первый compile→исправитьexhaustive matches, focusedP04M/actualRust↔Jolt/SQLite/
ammo160/960bounds+memorygate; только затем full/source gate и утреннийstandbinding.
НепринятуюP04M не объявлятьcomplete из-заsourceimport/инертногоregistry.
Затем P06T→P10B→NET02→firstcombat test→tail. Source docs P06T/P10B/NET02 untracked
сохранены; metadata не равнаruntime/native. Backend403 периодически прерывает
agents/root; сохранять WIP и продолжать локально, не начинать заново.
