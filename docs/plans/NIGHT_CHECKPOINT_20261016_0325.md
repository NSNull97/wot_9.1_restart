# Ночной checkpoint — 2026-10-16 03:25 +05

**Новее:** [P04M checkpoint](NIGHT_CHECKPOINT_20261016_0400.md).

Продолжать NIGHT_20261016 без ручных вопросов. Native/UI NOT_RUN, main не принимать.
Root D:/WoT_9.1_Server, **codex/p07b-server-visibility**, HEAD8fecb9d.
**СЕЙЧАС FULL GATE**, exec session86179:
`python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-p07b-full01`.
RUST_TEST_THREADS=1, source607files before receipt сохранён. НЕ менять runtime/HEAD
до окончания и `python -B -X utf8 local/evidence/20261016-p07b-full01/source_gate.py after`.
Focused23PASS/0ignored/buildPASS; actualmap exact1PASS (debug1153us/sixsnapshot,
20snapshots/360LOS), proof local/evidence/20261016-p07b-01/actual-map-timing01.*.
Main ffce8cb, P08B c7999e6, P08C2ef781f сохранены; всё native pending — утром.

## P05C законченная автоматическая проверка

Ветка codex/p05c-shared-physics, final docs9f2df41, runtime
**019ed2f5bbb40b88e3e6967d2be914f9f6006827**. Full03 **940PASS/5ignored/buildPASS**.
`local/evidence/20261016-p05c-full03/source-before.json` и source-after.json:
602files/exactHEAD PASS, exe187e445c3e905156110cddb1a003f89147f5f6cb4439b304d8b5c637f9ecba62.
Sourcegate завершён. Full01=936/4FAIL и full02=939/1FAIL сохранены; исправлены
legacy projectile bound60, устаревшие assertions и mixedshot576 fixture.
Actual Jolt2/6/240batches/14fractures/10ACKcommits PASS. Domain04 departure в
preparedACK и reattach после ACK PASS, лог скопирован в root domain-integration01.
Уход одного из6 в Battle не завершает бой, пока присутствуют обе команды.

## Активное владение P07B

- Protocol night_p08c_protocol: shared/mod.rs,wire.rs,interest_session_tests.rs.
  Pure visibility/interest_wire restored+committed8ec180b (12standalonePASS).
  Client.enable_spotting/refresh_interest/queue_private(outbox,body,targets),
  pending_private_len; Session.shared_refresh_world/flush_shared_interest(events)/
  flush_shared_private. Отдельные last_pose_tick/creation_announcements epochs.
  ACK теперьResult; Session caller root уже добавил ?. Коммитов/build пока нет.
- Writer p08b_writer_research: account/identity.rs,shared/model.rs,
  vehicle_profile.rs,visibility_world_tests.rs. visibility_v1 defaultfalse,
  onlyprofile13; ConfigBounded17→20, DTO16 неизменён. desired_visibility(own)
  actualterrain/staticnearest +fragiles.projectile_excluded instanceIDs,
  stock240/400, turretpivot+lab0.5m, equalpoints→true. Cargo пока не запускать.
- Root: shared/server.rs,server_visibility_tests.rs,SessionACKcaller.
  Serverdraft уже применён,5packettests написаны, ещё NOT_RUN. FreshWorld в
  receiveclone/poll; private queue epoch validation при reliableenqueue;
  hidden launch/terminal suppression (включая hidden target); отдельный pose tick.
  Audit local/evidence/20261016-p07b-integration-audit01/REPORT.md.
  Всё committed8fecb9d. Root publickillonce hiddenattacker и шестойrootrealAP3shots
  test включены. Полный gate сейчас идёт; без sourceafter новые runtime не начинать.

## Стенд и сохранённая подготовка

local/stands/night-battle-20261016-01: backup A108 MS1AP14/IS7AP19/fullcrew,
B25 MS1AP14/IS7INCOMPLETE_CREW; старый sourceDB unchanged35tables7finished1aborted.
Порты3481,20130,20131; sharedphysics manifestv2 rootnight01. Fresh token не печатать.
run.py/MORNING.md/prepare_clients.py: oldfix03 ledgerrollback A/B PASS,
новыеplans38pycCPython2.7.3 each PASS. Новыеinstall/services/client NOT_RUN.
**binding.json actualPASS на P05Cfull03/019ed2f**, исторический proof.
gateway.json уже visibility_v1=true18fields, backup gateway-p05c-before-visibility.json
и visibility-mode01.json; P05C binding откажет без восстановления старого config.
run.py check22resources PASS. P07B требует нового versioned binding после full/sourceafter.
Runnerselector не меняет config. После latest gate root сам install/launch
разрешённые copies local/clients/p03f/a,b; original C:/WoT_0.9.1_RU_0717_original
только read-only. Никаких новых тяжёлых copies/symlink/junction к local assets.

После P07B — P04M в отдельной зависимой ветке. P04M importer/test ещё в
local/night-staging/20261016 (receipt pins). Будущие docs P04M/P06T/P10B/NET02
пока untracked, сохранять. P04M source5proposal/physics=null/admissionfalse,
11new+23regressionPASS. P05Cagent read-only в своём worktree уточняет physics:
T26 четыреradius, W_L/R=.16113; T34 mounted extraPitchLimits/back=-17 1 42
(старый rootreport ошибочен, требуется исправление). Никакой cargo/Jolt параллельно.
P06T doc сохранён25pins/26checks +codes/extrasPASS; internalcrewgeometry
отсутствует, не выдумывать. WT128clip6/150clip4, FVHESH275.
P10B/NET02 source research сохранены, runtime ещё не реализован.

Дополнение03:30: P05Cagent в своём worktree codex/p04m-physics-profile-prep
реализует C#component: manifestv2 actor.source_profile pin, explicitKind,
genuine Joltgetter qualifier. Metadata-only fresh rootlocal/evidence/20261016-p04m-physics01
разрешён; heavybuild пока запрещён до rootfull. Writer готовит ignoredP04M draft:
nativeID3 реальноObject261, crew oldDDL16/безradioman/толькоvehicles1,2 иammo2mounts
требуютversionedmigration; не подставлять inventoryID3→Т26, никакихgrants/DBwrites.

Backend403 прерывал агентов/активный root01:55–03:15. Файлы сохранены, агенты
resumed03:17. При повторении root продолжает локально; checkpoint важнее
повторного исследования. wot-16 каждые20мин до08:00+05, без дублей автоматики.
