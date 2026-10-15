# Указатель исследований

Факты с метками VERIFIED/OBSERVED/INFERRED/UNKNOWN. Читать только нужный файл.
Ссылки внутри исследований на `docs/plans/` и `docs/evidence-index/` ведут в историю:
`git show 1eaff5e:<путь>` (удалены 2026-10-15 при сокращении документации).

## Общие (клиент, протокол, ресурсы, решения)

- [BATTLE_LOADOUT_REVISION_GATE.md](BATTLE_LOADOUT_REVISION_GATE.md) — Исследование: battle-loadout revision adapter
- [CAPACITY_1000_CCU.md](CAPACITY_1000_CCU.md) — Инфраструктура для 1000 одновременных игроков: расчётная модель
- [CLIENT_AUDIT.md](CLIENT_AUDIT.md) — CLIENT_AUDIT — P00–P01
- [CONTENT_ENCODER_EXPORT.md](CONTENT_ENCODER_EXPORT.md) — Portable server-content/encoder export
- [EXTERNAL_REPOSITORIES_20261007.md](EXTERNAL_REPOSITORIES_20261007.md) — Внешние репозитории для P00–P01: WoT decompile, BigWorld OSE и WoT 0.8.2 offline
- [GAME_ACCOUNT_OWNERSHIP.md](GAME_ACCOUNT_OWNERSHIP.md) — Game account ownership assertion
- [IDENTITY_BOUNDARY.md](IDENTITY_BOUNDARY.md) — Identity/account boundary — 2026-10-06
- [INTEGRATION_SPIKES.md](INTEGRATION_SPIKES.md) — INTEGRATION_SPIKES — выполненные проверки
- [KNOWN_UNKNOWNS.md](KNOWN_UNKNOWNS.md) — KNOWN_UNKNOWNS — current gate and historical checkpoints
- [PHYSICS_AUTHORITY.md](PHYSICS_AUTHORITY.md) — Физика: серверная авторитетность и обязанности клиента #717
- [PROFILE4_PORTABLE_CHAIN.md](PROFILE4_PORTABLE_CHAIN.md) — Bundle-rooted profile4 chain
- [PROFILE4_SEMANTIC_DIFF.md](PROFILE4_SEMANTIC_DIFF.md) — Исследование: profile4 r3→r4 semantic diff
- [PROTOCOL_MAP.md](PROTOCOL_MAP.md) — PROTOCOL_MAP — статические контракты клиента #717
- [REPRODUCE.md](REPRODUCE.md) — Повторный запуск P00–P01
- [RESOURCE_MAP.md](RESOURCE_MAP.md) — RESOURCE_MAP — локальные ресурсы 0.9.1 #717

## P01

- [P01_BOOTSTRAP_AND_NATIVE_LOGIN.md](P01_BOOTSTRAP_AND_NATIVE_LOGIN.md) — P01: instance mutex, действующий Python и настоящий native login/rejection

## P02 вход, шлюз, ангар

- [P02_ACCOUNT_READY.md](P02_ACCOUNT_READY.md) — P02 — минимальный Account: lifecycle и начальная синхронизация
- [P02_ACCOUNT_SWITCH.md](P02_ACCOUNT_SWITCH.md) — P02 — смена двух аккаунтов в одном клиентском процессе
- [P02_ARENA_ENTRY.md](P02_ARENA_ENTRY.md) — Native Account → Avatar → собственная локальная арена
- [P02_ARENA_MOVEMENT.md](P02_ARENA_MOVEMENT.md) — P02 — native команда движения и серверное положение
- [P02_ARENA_READY.md](P02_ARENA_READY.md) — P02 — настоящая готовность клиента и серверная подготовка арены
- [P02_BASEAPP_REPLY.md](P02_BASEAPP_REPLY.md) — P02: ответ BaseApp → первое сообщение канала
- [P02_BATTLE_PROGRESS.md](P02_BATTLE_PROGRESS.md) — P02/P03: следующий проверяемый срез к полноценному бою
- [P02_CHANNEL_ACK.md](P02_CHANNEL_ACK.md) — P02: ACK первого reliable frame и ограниченный keepalive
- [P02_DRIVE_LIMITATIONS.md](P02_DRIVE_LIMITATIONS.md) — Ограничения после ручной поездки владельца
- [P02_HANGAR.md](P02_HANGAR.md) — P02 — штатный ангар с серверными данными игрока
- [P02_HANGAR_SERVICE_LIMITS.md](P02_HANGAR_SERVICE_LIMITS.md) — P02 — границы доступных действий ангара
- [P02_HANGAR_UI.md](P02_HANGAR_UI.md) — P02 — каталог модулей и интерфейс ангара
- [P02_HANGAR_WINDOWS.md](P02_HANGAR_WINDOWS.md) — P02 — границы неподключённых окон ангара
- [P02_INPROCESS_RELOGIN.md](P02_INPROCESS_RELOGIN.md) — P02 — выход и повторный вход внутри одного EXE
- [P02_LAB_GATEWAY.md](P02_LAB_GATEWAY.md) — P02: ограниченный native gateway и локальная сессия
- [P02_LOGIN_REDIRECT.md](P02_LOGIN_REDIRECT.md) — P02: native LoginSuccess и первый BaseApp request
- [P02_LONG_HANGAR.md](P02_LONG_HANGAR.md) — P02 — длительный ангар и периодический native обмен
- [P02_MANUAL_ACCEPTANCE_20261005.md](P02_MANUAL_ACCEPTANCE_20261005.md) — Ручная проверка утренней сборки009 — 5 октября 2026
- [P02_MANUAL_BATTLE_BUTTON.md](P02_MANUAL_BATTLE_BUTTON.md) — P02: настоящий Flash-клик «В бой!»
- [P02_MANUAL_EXPIRY_20261005.md](P02_MANUAL_EXPIRY_20261005.md) — Естественное истечение сессии и повторный вход — 5 октября 2026
- [P02_MAP_DRIVE.md](P02_MAP_DRIVE.md) — P02 — поездка через родную кнопку «В бой!»
- [P02_MS1_AMMO.md](P02_MS1_AMMO.md) — P02 — серверный боекомплект МС-1
- [P02_MS1_CREW.md](P02_MS1_CREW.md) — P02 — экипаж МС-1
- [P02_NATIVE_ACCOUNT.md](P02_NATIVE_ACCOUNT.md) — P02 — первое создание native Account
- [P02_RETIRED_BASE_REPLAY.md](P02_RETIRED_BASE_REPLAY.md) — P02 — настоящие поздние BaseApp packets закрытого аккаунта
- [P02_SERVER_RELIABLE.md](P02_SERVER_RELIABLE.md) — P02: первый reliable packet сервера и настоящий ACK клиента
- [P02_SERVICE_RECOVERY.md](P02_SERVICE_RECOVERY.md) — P02: восстановление локальной службы после устаревшего lock
- [P02_SNIPER_CAMERA_PROTOCOL.md](P02_SNIPER_CAMERA_PROTOCOL.md) — P02: смена камеры без разрыва native channel
- [P02_TACTICAL_HANGAR_UI_AUDIT.md](P02_TACTICAL_HANGAR_UI_AUDIT.md) — P02 — Tactical Steel UI: фактический pipeline ангара
- [P02_TEST_IS7.md](P02_TEST_IS7.md) — P02 — тестовый ИС-7 в общем аккаунте
- [P02_UNIFIED_ACCOUNT.md](P02_UNIFIED_ACCOUNT.md) — P02 — единый аккаунт сайта и native-вход в «Стальной рубеж»

## P03 два клиента, стрельба

- [STAB01_BATTLE_STABILITY.md](STAB01_BATTLE_STABILITY.md) — STAB-01 принята: caller context, изоляция боя, два native-возврата и повторный бой; ограничения диагностики/физики

- [P03_BATTLE_SHOOTING.md](P03_BATTLE_SHOOTING.md) — P03: battle shooting — loadout preparation route
- [P03F_TWO_CLIENT_WORLD.md](P03F_TWO_CLIENT_WORLD.md) — P03F — native two-client laboratory research
- [P03G_SHARED_GUN_AIM.md](P03G_SHARED_GUN_AIM.md) — P03G — native shared aiming, 2026-10-07
- [P03H_NATIVE_PROJECTILE_FLIGHT.md](P03H_NATIVE_PROJECTILE_FLIGHT.md) — P03H — native projectile contract, 2026-10-07
- [P03I_RUNTIME_REVIEW_BOUNDARY.md](P03I_RUNTIME_REVIEW_BOUNDARY.md) — P03I runtime review boundary
- [P03I_VEHICLE_PROFILE_LOADOUT.md](P03I_VEHICLE_PROFILE_LOADOUT.md) — P03I — static vehicle/loadout handoff research
- [P03M_IS7_RUNTIME_PROFILE.md](P03M_IS7_RUNTIME_PROFILE.md) — P03M — source-bound IS-7 runtime

## P04 экипаж, импорт

- [P04_CONTENT_IMPORT.md](P04_CONTENT_IMPORT.md) — P04 — исследование typed content import
- [P04B_CREW_EQUIPMENT_SNAPSHOT.md](P04B_CREW_EQUIPMENT_SNAPSHOT.md) — P04B — immutable crew / installed-device snapshot
- [P04C_CONFIGURATION_RESERVATION.md](P04C_CONFIGURATION_RESERVATION.md) — P04C — source-bound configuration and ammunition reservation
- [P04D_NATIVE_CREW_RECRUITMENT.md](P04D_NATIVE_CREW_RECRUITMENT.md) — P04D — one native MS-1 recruitment
- [P04F_NATIVE_CREW_TRANSFER.md](P04F_NATIVE_CREW_TRANSFER.md) — P04F — native crew unloading and reassignment
- [P04G_NATIVE_CROSS_VEHICLE_CREW.md](P04G_NATIVE_CROSS_VEHICLE_CREW.md) — P04G — native cross-vehicle crew assignment
- [P04H_NATIVE_CREW_RECRUITMENT.md](P04H_NATIVE_CREW_RECRUITMENT.md) — P04H — native recruitment for the verified MS-1 and IS-7 rosters
- [P04I_NATIVE_CREW_PROGRESSION.md](P04I_NATIVE_CREW_PROGRESSION.md) — P04I — original PersonalCase, first skill and dossier evidence
- [P04J_NATIVE_CREW_DISMISSAL.md](P04J_NATIVE_CREW_DISMISSAL.md) — P04J — native dismissal, sparse crew and bounded display compatibility
- [P04K_NATIVE_BARRACKS_RECRUITMENT.md](P04K_NATIVE_BARRACKS_RECRUITMENT.md) — P04K — original Barracks recruitment, #717

## P05 движение

- [P05_MATRIX_RECEIPT_AUDIT.md](P05_MATRIX_RECEIPT_AUDIT.md) — P05 movement-matrix receipt audit
- [P05_OFFLINE_DETERMINISTIC_MATRIX.md](P05_OFFLINE_DETERMINISTIC_MATRIX.md) — P05 — offline deterministic movement matrix
- [P05B_ANGULAR_FENCE_IPC.md](P05B_ANGULAR_FENCE_IPC.md) — IPC6 exact field table — agreed Stage B design, no runtime authorization
- [P05B_ANGULAR_RUNTIME_GATE.md](P05B_ANGULAR_RUNTIME_GATE.md) — P05B angular runtime — first-eight/full-scene PASS, paired rejoin FAIL retained
- [P05B_ANGULAR_SCALAR_GATE.md](P05B_ANGULAR_SCALAR_GATE.md) — P05B angular response: completed scalar gate
- [P05B_CONTACT_DIAGNOSTICS.md](P05B_CONTACT_DIAGNOSTICS.md) — P05B — remaining contact diagnostics and native filter speed
- [P05B_MOVING_FENCE_CONTACT.md](P05B_MOVING_FENCE_CONTACT.md) — P05B — moving fence contact, candidate14
- [P05B_OWNER_HANDLING_FIXES.md](P05B_OWNER_HANDLING_FIXES.md) — P05B — исправления управления по ручной проверке 2026-10-14
- [P05B_REAL_WORKER_CADENCE.md](P05B_REAL_WORKER_CADENCE.md) — P05B actual-worker cadence and morning preparation
- [P05B_TRACKED_HANDLING.md](P05B_TRACKED_HANDLING.md) — P05B — bounded tracked handling for MS-1 and IS-7

## P06 баллистика, урон, разрушения

- [P06B_MS1_AP_SOURCE_SPIKE.md](P06B_MS1_AP_SOURCE_SPIKE.md) — P06B — MS-1 AP source-field research spike
- [P06D_IMPACT_RECEIPT_AUDIT.md](P06D_IMPACT_RECEIPT_AUDIT.md) — P06D — bounded impact receipt audit
- [P06E_CLIENT_COLLISION_SOURCE_RESEARCH.md](P06E_CLIENT_COLLISION_SOURCE_RESEARCH.md) — P06E — #717 client collision and projectile callback source audit
- [P06F_MS1_COLLISION_STATIC_CORRELATION.md](P06F_MS1_COLLISION_STATIC_CORRELATION.md) — P06F MS-1 collision static correlation
- [P06G_TRACE_INVARIANT_HARDENING.md](P06G_TRACE_INVARIANT_HARDENING.md) — P06G server-owned impact trace invariant hardening
- [P06H_SERVER_COLLISION_BOUNDARY.md](P06H_SERVER_COLLISION_BOUNDARY.md) — P06H — offline geometric query and trace boundary
- [P06I_NATIVE_COLLISION_BINDING.md](P06I_NATIVE_COLLISION_BINDING.md) — P06I — stock MS-1 surfaces in the accepted integrated world
- [P06J_CONTACT_MATERIALS.md](P06J_CONTACT_MATERIALS.md) — P06J — component material facts before damage
- [P06K_AP_IMPACT_CONTRACT.md](P06K_AP_IMPACT_CONTRACT.md) — P06K — AP source contract and original marker oracle
- [P06L_AP_TEST_LAB.md](P06L_AP_TEST_LAB.md) — P06L — approximate AP damage on the cumulative native runtime
- [P06M_TERRAIN_IMPACT.md](P06M_TERRAIN_IMPACT.md) — P06M — projectile contact with Karelia terrain and static obstacles
- [P06N_DESTRUCTIBLE_STATE.md](P06N_DESTRUCTIBLE_STATE.md) — P06N — one authoritative destructible fixture
- [P06O_DESTRUCTIBLE_IMPORT.md](P06O_DESTRUCTIBLE_IMPORT.md) — P06O — source-driven fragile object catalog
- [P06P_PROHOROVKA_CUMULATIVE.md](P06P_PROHOROVKA_CUMULATIVE.md) — P06P — Prohorovka cumulative map migration
- [P06Q_ACCEPTANCE_ENVIRONMENT_REPAIR.md](P06Q_ACCEPTANCE_ENVIRONMENT_REPAIR.md) — P06Q final acceptance and source relocation — 2026-10-13
- [P06Q_TREE_VEHICLE_CONTACT.md](P06Q_TREE_VEHICLE_CONTACT.md) — P06Q — original trees, vehicle contact, and cumulative scene state
- [P06R_COMPOUND_FENCES_CONTRACT.md](P06R_COMPOUND_FENCES_CONTRACT.md) — P06R — source-bound fences and compound boundary
- [P06R_FENCE_CHAIN_RESPONSE.md](P06R_FENCE_CHAIN_RESPONSE.md) — P06R fence-chain response

## P07 видимость

- [P07A_VISIBILITY_SOURCE_BOUNDARY.md](P07A_VISIBILITY_SOURCE_BOUNDARY.md) — P07A — static visibility source research ledger

## P08 цикл боя

- [P08A_STATIC_BATTLE_LIFECYCLE_SOURCE_BOUNDARY.md](P08A_STATIC_BATTLE_LIFECYCLE_SOURCE_BOUNDARY.md) — P08A — static battle lifecycle source research

## P09 персистентность, БК, исследования

- [P09A_NATION_DUMPER_STATIC.md](P09A_NATION_DUMPER_STATIC.md) — P09A — NationObjDumper static output research
- [P09A_RESEARCH_TREE_VISIBILITY.md](P09A_RESEARCH_TREE_VISIBILITY.md) — P09A — research-tree visibility evidence ledger
- [P09A_TECHTREE_HANDOFF_STATIC.md](P09A_TECHTREE_HANDOFF_STATIC.md) — P09A — TechTree handoff static research ledger
- [P09A_TREE_GRAPH_AUDIT.md](P09A_TREE_GRAPH_AUDIT.md) — P09A — static research-tree graph audit
- [P09B_PERSISTENCE_TRANSACTION_BOUNDARY.md](P09B_PERSISTENCE_TRANSACTION_BOUNDARY.md) — P09B — persistence/transaction boundary research ledger
- [P09C_AMMO_SERVICE_CONTRACT.md](P09C_AMMO_SERVICE_CONTRACT.md) — P09C ammunition service — isolated domain and integration contract
- [P09D_NATIVE_AMMO_SOURCE.md](P09D_NATIVE_AMMO_SOURCE.md) — P09D native ammunition servicing source contract
- [P09E_NATIVE_HANDOFF.md](P09E_NATIVE_HANDOFF.md) — P09E owner native gate — morning handoff
- [P09E_NATIVE_SOURCE.md](P09E_NATIVE_SOURCE.md) — P09E — original #717 research and acquisition boundary
- [P09E_STORE_AND_CLIENT.md](P09E_STORE_AND_CLIENT.md) — P09E same-account research writer and explicit native UI policy

## P10 подбор

- [P10A_TRAINING_ROOM_STATIC.md](P10A_TRAINING_ROOM_STATIC.md) — P10A — training-room lifecycle static research
