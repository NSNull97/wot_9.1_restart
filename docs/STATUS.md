# Актуальный указатель — ORG-0B, 2026-10-07

Канонический gate: [ACTIVE_GATE](ACTIVE_GATE.md). **Полный P03 IN_PROGRESS**.
P03D `PASS_OWNER_NATIVE_AMMO_PANEL_HUD` и P03E
`PASS_OWNER_NATIVE_FIRE_RELOAD_CONSUMPTION` подтверждены owner receipts.
Повтор ручного P03E в ORG-0B не требуется. Два клиента в общей арене,
projectile/hit/damage и полная боевая приёмка остаются NOT_RUN.

**ORG-0B: PASS_TEST_REPAIR.** Свежий baseline повторил 2028 tests, 10 errors,
4 skips. После минимальных исправлений — **2047 tests, 0 errors/failures,
2 skips**; отдельный Python 2.7 bytecode check — **1 PASS**. Единственная
проверка из исходных четырёх, не выполненная ни в одном режиме, — Windows
symlink refusal: текущая учётная запись не может создать symlink. Layout PASS
(52 source files / 22 relocations), четыре запуска profile4 CLI/module PASS.
Причины, границы и команды: [ORG-0B receipt](evidence-index/ORG-0B.md).

Исправлены test fixtures и режим импорта offline profile4 verifiers. Протокол,
боёвка, frozen verifiers, клиент и deployed gateway неизменны. Historical tests
проверяют архивные source bytes с прежними строгими SHA; новая live/native
совместимость этих legacy CLI не запускалась и не заявляется.

ORG-0A опубликована: [baseline/remote receipt](evidence-index/ORG-0A.md).
ORG-0B base — `1aa052db33643fab510f2b9185716a8e60d8804a`; точные принятый
head, merge/push и remote SHA записываются после операций в local machine receipt,
указанном в индексе. Следующий один шаг — отдельная P03-карточка двух native
клиентов в общем авторитетном мире. Общая стабильность/release не заявляется.

## История карточек (старые NOT_RUN и рекомендации сохранены)

Все результаты ниже относятся к своему запуску и дате. Старое P03 NOT_STARTED
в архивной таблице не заменяет актуальный IN_PROGRESS выше.

**2026-10-07: P03E owner acceptance — PASS_OWNER_NATIVE_FIRE_RELOAD_CONSUMPTION.**

На build09 владелец сделал пять выстрелов на одном MS-1 entry; все прошли
нормально. Gateway записал server-owned AP `20 → 19 → 18 → 17 → 16 → 15`
и пять `BATTLE_RELOAD_COMPLETE` callbacks с
`updateVehicleGunReloadTime(0x46, timeLeft=0.0, baseTime=2.5)`. Второй и
последующие выстрелы реально дошли до `vehicle_shoot=0x88`, значит клиентская
reload latch после initial `0,00` и после каждого shot отпускается.

Свежий capture: `671` packet files, `667` bounded channel frames, crypto и
transport parse PASS, ошибок нет; initial map binding — `176` байт с panel,
`CURRENT_SHELLS` и initial reload callback, пять shot callbacks — по `25`
байт. Gateway и клиент остановлены после owner run; deployed gateway SHA256
`daef0dde9e012beac4e0f363bf66b672ec4a154473be4b05b00cfe4cc0608c3b`,
supervisor/identity/live gateway не заменялись.

Canonical build09: **330 Rust tests PASS**, EXE SHA256
`460d5d68dd47b6599085d2775c316d4e1192a2d53c45f87aaabf86d9341e7970`;
shared legacy build04: **329 PASS**, SHA256
`558a6b72a65e980395e146a48570e1ef1cec2b7accfcbe2c1cdb2a8e832e114a`;
source layout после completion callback: **PASS** (`52` файлов, `22`
relocations). Receipt owner-приёмки:
`local/evidence/20261007-battle-fire-reload-01/owner-test/owner-acceptance-fire-reload-03.json`.

P03E закрыта для fire/reload/consumption. Projectile, hit, damage, visibility,
physics, equipment и persistence остаются **NOT_RUN**; единственный следующий
шаг — отдельная карточка projectile/hit/damage, без расширения этой фазы.

**2026-10-07: P03E reload-latch correction — PASS_ISOLATED_NATIVE_FIRE_ROUTE_READY_RELOAD_RESET.**

Первый owner-прогон на build07 дал полезный отрицательный результат: HUD уже
показывал панель, но при огне клиент писал «орудие перезаряжается», таймер
оставался `0,00`, AP не менялся, а capture не содержал ни клиентского `0x88`
`vehicle_shoot`, ни `BATTLE_SHOT_ACCEPTED`. Bounded transport/crypto аудит
этого прогона PASS; тело initial binding было `162` байта и заканчивалось
только panel rows + `CURRENT_SHELLS`. Причина подтверждена static Avatar
кодом: `PlayerAvatar.updateVehicleGunReloadTime` не был вызван, поэтому
`aim.isGunReload()` оставался поднят и `PlayerAvatar.shoot` не доходил до
native вызова.

Исправление добавляет перед ручным огнём штатный
`updateVehicleGunReloadTime` (`0x46`) с vehicle entity `152043523`,
`timeLeft=0.0`, `baseTime=2.5`. PREBATTLE body теперь `105` байт, map-drive
binding — `176` байт; callback идёт после трёх ammo rows и
`CURRENT_SHELLS=0/2570`. Это не объявляет fire acceptance: новый owner шаг
ещё нужен.

Canonical isolated gateway build08: **329 Rust tests PASS**, EXE SHA256
`b70c73af9cc0060343e51202bf959326d0a584ce37b20a29ad3b4fe253085727`;
shared legacy build03: **328 PASS**, SHA256
`034277a63a55340f21e6604081dfef51d35258e1431307648b992663f5b4fafd`;
source layout after correction: **PASS** (`52` files, `22` relocations).
Deployed `p01-wg-probe.exe` остался на SHA256
`daef0dde9e012beac4e0f363bf66b672ec4a154473be4b05b00cfe4cc0608c3b`;
supervisor, identity и live gateway не перезапускались.

Первый ручной прогон сохранён как
`local/evidence/20261007-battle-fire-reload-01/owner-test/owner-attempt-01-observation.json`;
свежий handoff build08 будет отдельным capture и не перезапишет этот
отрицательный результат. Приёмка P03E всё ещё **NOT_RUN** для фактического
выстрела; единственный следующий шаг — один MS-1 выстрел на build08,
проверить AP `20 → 19` и пройти reload.

Полный receipt: `local/evidence/20261007-battle-fire-reload-01/result.json`;
static-method receipt: `local/evidence/20261007-battle-fire-reload-01/static-method-receipt.json`.

**2026-10-07: P03E isolated native fire/reload route — PASS_ISOLATED_NATIVE_FIRE_ROUTE_READY.**

Добавлен bounded server-owned маршрут MS-1 для `Avatar.BaseMethods.vehicle_shoot`
(`0x88`) и явный диагностический `vehicle_replenishAmmo` (`0x89`). Сервер
держит AP `20`, принимает только авторизованный zero-arg shot, списывает один
AP и ставит монотонную перезарядку `2.5 s`; callback-ы —
`updateVehicleAmmo` (`0x44`, remaining `19`) и
`updateVehicleGunReloadTime` (`0x46`, `2.5/2.5`). `0x89` пока
`domain_applied=false`: бесплатный боекомплект/экономика не добавлены.

Статически подтверждена причина клиентского silent-stop:
`PlayerAvatar.shoot` требует `__currShellsIdx`; поэтому перед тремя ammo rows
добавлен штатный `updateVehicleSetting(CURRENT_SHELLS=0, 2570)` (`0x40`).
PREBATTLE body теперь `91` байт, map-drive binding `162` байта. Ветвление
применено и к живому `drive.is_some()` маршруту, и к legacy arena route.

Canonical isolated gateway: **328 Rust tests PASS**, EXE SHA256
`72dfc02beef4b3af645a98914634463d84a21abb6274a897eac6ba5d47e32ff`; shared
legacy entrypoint: **327 PASS**, SHA256
`e1c05aed270e79d4a8ff25510619e0abd288f5e1718bf4fda68da189cbe9d127`; source
layout: **PASS** (`52` files, `22` relocations). Deployed
`p01-wg-probe.exe` остался на SHA256
`daef0dde9e012beac4e0f363bf66b672ec4a154473be4b05b00cfe4cc0608c3b`;
supervisor, identity и live gateway не перезапускались.

Owner manual fire/reload пока **NOT_RUN**. Свежий handoff подготовлен в
`local/evidence/20261007-battle-fire-reload-01/owner-test/`; capture пустой
до ручного выстрела. Приёмка этой фазы требует одного MS-1 выстрела, ожидания
примерно `4 s` и проверки HUD/capture на AP `20 → 19` и reload.
Полный receipt: `local/evidence/20261007-battle-fire-reload-01/result.json`;
static-method receipt: `local/evidence/20261007-battle-fire-reload-01/static-method-receipt.json`.

# Статус проекта

**2026-10-07: P03D owner acceptance — PASS_OWNER_NATIVE_AMMO_PANEL_HUD.**
Fresh research-client MS-1 entry on the isolated panel gateway visibly showed
three battle ammo slots: AP `2570:20`, HOLLOW_CHARGE `2826:0`,
HIGH_EXPLOSIVE `3082:0`. This is an owner screenshot observation, not a
synthetic HUD claim. The copied screenshot is hashed in
`local/evidence/20261007-battle-ammo-panel-01/owner-test/owner-panel-acceptance-01.json`.

The frozen owner capture has 621 packet files, packet integrity PASS and no
bounded transport parse errors. Packet 73 is a server→client body of 155 bytes;
its suffix at offset 122 is exactly the three 11-byte methods, with
`0x13 0x44` prefixes at offsets `122/133/144`. Equipment/consumables remain
absent (`null`) in the verified MS-1 input, so no equipment item is claimed.
The isolated panel gateway PID 83200 was stopped after the run; deployed
`p01-wg-probe.exe`, supervisor and identity were not replaced.

Receipts: `local/evidence/20261007-battle-ammo-panel-01/result.json`,
`local/evidence/20261007-battle-ammo-panel-01/owner-test/owner-panel-acceptance-01.json`,
`local/evidence/20261007-battle-ammo-panel-01/owner-test/owner-capture-audit-panel-01-frozen.json`.
Ammo-panel HUD acceptance is complete. Zero-count shell selection and
fire/reload/consumption remain **NOT_RUN**; equipment needs a later verified
item-bearing profile/message. The single next step is a separate firing/reload
card, without widening this panel card into guessed combat semantics.

**2026-10-07: P03D battle ammo panel route — PASS_OFFLINE_BATTLE_AMMO_PANEL_ROUTE.**
После owner-проверки build07 клиент показывал только выбранный AP `2570:20`.
Причина подтверждена текущим payload: сервер отправлял один `Avatar.updateVehicleAmmo`.
Новый изолированный route сохраняет binding prefix и добавляет три bounded
entity-method строки в доказанном native order: `2570:20`, `2826:0`, `3082:0`.
Размер suffix —33 байта; ordinary map-drive binding теперь155 байт вместо133,
PREBATTLE preparation —84 вместо62. `equipment` и `consumables` в закреплённом
MS-1 input отсутствуют (`null`), поэтому фальшивые предметы не отправляются.

Canonical gateway: **319 Rust tests PASS**, SHA256
`4247C1E9A575570E6252E3CCBFD503FA0B50D8D926F04AC8F3ACAEDF2630A0A`; legacy
shared entrypoint: **318 PASS**, SHA256
`4E222DDEE890938E2AF2FC47ADE4FAB976F6247EBC5F42100BA99713FB4D4C03`.
Source layout PASS; isolated bind-smoke на `20134/20136` PASS; deployed
`p01-wg-probe.exe`, live supervisor, сайт, БД и оба клиента не заменялись.
Receipts: `local/evidence/20261007-battle-ammo-panel-01/result.json` и
`local/build/server/gateway-battle-ammo-panel-01/result.json`.

На момент этой offline-записи native HUD ещё был **NOT_RUN**; owner-приёмка
закрыта следующей записью выше. Эта запись сохраняет исходные offline
размеры/хэши и не объявляет оборудование, zero-count selection или fire/reload.

**2026-10-06: P03 owner wire review + build07 route correction — PASS_OFFLINE_OWNER_ROUTE_FIX.**
Первый owner-прогон на build06 теперь зафиксирован как
**VERIFIED_OWNER_CAPTURE_ROUTE_MISS**: capture содержит валидный
`READY_COMPOUND` (packet 74), а следующий server→client binding имеет ровно
122 байта (packet 76). Bounded-аудит 658 packet files / 654 encrypted channel
frames проходит без ошибок, но `0x13 0x44` и exact candidate отсутствуют.
Клиентский trace подтверждает MS-1, `BattleLoading`/`onSpaceLoaded` и чистый
выход; ammo callbacks в trace — только hangar-side до battle, а владелец увидел
«БК нет». Это не доказательство native HUD rejection: старый live route просто
не отправлял кандидат. Receipts:
`owner-test/owner-capture-audit-060.json`,
`owner-test/owner-wire-frame-summary-060.json`,
`owner-test/owner-trace-audit-060.json`.

Причина найдена в dispatch order: live map-drive с `self.drive.is_some()` идёт
через `drive_avatar`, раньше поздней `queue_map_binding` ветки; build06 оставлял
там старый 122-byte binding. Build07 добавляет типизированный 11-byte
`13440a0a00001400000000` в фактический `drive_avatar` route после той же
server-owned BattlePreparation и до reliable enqueue. Новый build07: **318 Rust
tests PASS**, executable SHA256
`39BE8CA6B782ED5C902C0AA93D9DFF4CF31A50910D959947687DB338E719BEC8`, source
layout PASS, isolated bind-smoke PASS на `20124/20126`; deployed gateway SHA
`DAEF0DDE9E012BEAC4E0F363BF66B672EC4A154473BE4B05B00CFE4CC0608C3B` и live
service не менялись. План исправления:
`docs/plans/P03C_OWNER_WIRE_AMMO_ROUTE_FIX.md`.

Следующий ручной шаг подготовлен в
`local/evidence/20261006-battle-shooting-native-loadout-01/owner-test-build07.md`:
остановить только старый owner gateway, запустить build07 с fresh
`owner-capture-070`, один раз войти на MS-1, проверить battle HUD и нормально
выйти; fire/move/sniper/второй клиент запрещены. Native receipt/order/HUD после
build07 пока **NOT_RUN**.

**2026-10-06: P03 battle preparation loadout route — PASS_DOMAIN_BATTLE_PREPARATION_LOADOUT.**
Перед PREBATTLE и ordinary `drive_join` canonical gateway теперь повторно
проверяет authenticated `VehicleSeed`, читает exact profile/compatibility/
manifest/native-ammo inputs по pinned SHA, строит typed
`BattlePreparation` через общий fail-closed `battle::loadout::validate` и
привязывает результат к generation арены. Count берётся из server-owned
profile, mapping — из compatibility, mounted turret5891/gun5892, shell2570 и
capacity96 — из native export; client input и HUD не используются. Cancel/return
очищают доменное состояние. Canonical isolated build: 312 Rust tests PASS;
legacy shared entrypoint: 311 PASS; `server/check_layout.py` PASS; deployed
gateway SHA `DAEF0DDE9E012BEAC4E0F363BF66B672EC4A154473BE4B05B00CFE4CC0608C3B`
не изменился. Финальный output:
`local/build/server/gateway-battle-shooting-after-05`; Evidence:
`local/evidence/20261006-battle-shooting-loadout-route/result.json`; plan/report:
`docs/plans/P03_BATTLE_SHOOTING.md`, `docs/research/P03_BATTLE_SHOOTING.md`.
Native Avatar `AMMO/LOADOUT` event, wire decode, fire/reload, расход БК,
hit/damage, physics и live restart — NOT_RUN. Read-only maintenance audit в
`local/evidence/20261006-battle-shooting-maintenance-preflight-01/` дал
`NOT_READY_NATIVE_LOADOUT`: deployed service всё ещё закреплён на старом EXE,
изолированная сборка не развёрнута, а 345-пакетный capture уже сохранил «БК
нет». Research-копия восстановлена до prior SHA после ошибочного rollback
active install016; original/backend не трогались. Повторный клиентский run сейчас
не просить. Единственный следующий шаг — offline определить native
Avatar ammo method/serializer/order; только потом планировать owner-driven окно
с capture и MS-1 → «В бой!». До реального числового БК fire/reload handler не
добавлять.

**2026-10-06: profile4 battle-loadout revision adapter — PASS_BOUND_PROFILE4_LOADOUT_ADAPTER.**
Добавлен отдельный `server/gateway/src/battle/profile4_adapter.rs` поверх
прежнего domain-only `loadout.rs`. Adapter принимает bounded trusted
`game.account.v1` assertion, exact r4 profile/compatibility/native-ammo SHA,
сверяет account/native DB/nickname/creation, revisions 4/4, MS-1 inventory,
commander+driver crew, 20 AP, mounted turret5891/gun5892, shell2570 и
vehicle-specific maxAmmo96, затем вызывает прежний typed loadout validator.
Canonical isolated gateway test/build: 307 Rust tests PASS; deployed gateway
не заменён, `main.rs` только включает compile-only module без session/transport
wiring. Native Avatar ammo event, battle admission/reservation, consumption,
reload/fire/damage/physics и live backend — NOT_RUN. Existing loadout.rs и
arena/gateway runtime behavior не переписаны. План/отчёт:
`docs/plans/BATTLE_LOADOUT_REVISION_GATE.md`,
`docs/research/BATTLE_LOADOUT_REVISION_GATE.md`; evidence:
`local/evidence/20261006-battle-loadout-revision-gate/`. Следующий один шаг:
после отдельного native capture решить, как adapter связывается с настоящим
Avatar loadout event, не добавляя fire handler по догадке.

**2026-10-06: profile4 r3→r4 semantic diff — PASS_PORTABLE_PROFILE4_SEMANTIC_DIFF.**
Добавлен bundle-rooted offline verifier `tools/profile4_semantic_diff.py`.
Принятый `portable-bundle-05` сначала проходит immutable chain, затем строго
проверяется exact delta: crew/identity/resources/IS-7/vehicle+crew mapping
сохранены, MS-1 ammunition `0→20` добавлен с shell2570/turret5891/gun5892,
`shop.bin` и `dossier.bin` byte-identical, state меняется только shells и
shellsLayout. Пять unit checks PASS, включая отрицательные identity/IS-7/state и
ammo-mapping мутации. Native compatibility, native proof, battle gate и live
backend не запускались; absolute r3/r4 preservation остаётся NOT_BUNDLED.
План и отчёт: `docs/plans/PROFILE4_SEMANTIC_DIFF.md`,
`docs/research/PROFILE4_SEMANTIC_DIFF.md`; evidence:
`local/evidence/20261006-profile4-semantic-diff/semantic-diff.json`.
Следующий один шаг: подключить этот revision/loadout assertion к отдельному
battle-loadout gate без изменения native transport и physics.

**2026-10-06: game account ownership assertion — PASS_GAME_ACCOUNT_OWNERSHIP.**
Добавлен отдельный `game.account.v1` contract и pure builder/validator
`server/identity/ownership.mjs`. Он связывает принятый
`identity.account.v1` game assertion с server-owned profile по `account_id`,
никнейму и creation timestamp, добавляет bounded native database ID,
profile/snapshot revisions и SHA256 профиля. DTO не содержит email, password,
browser session token, fixture path или loadout. Четыре новые isolated Node
проверки и прежние пять identity/account тестов PASS. Arena/gateway/physics,
battle worker, live identity DB и native client не менялись и не запускались.
Это ownership boundary для будущего loadout gate, не боевое разрешение и не
native compatibility. План и отчёт: `docs/plans/GAME_ACCOUNT_OWNERSHIP.md`,
`docs/research/GAME_ACCOUNT_OWNERSHIP.md`; receipt:
`local/evidence/20261006-game-account-ownership/result-final.json`. Следующий
один шаг: отдельный semantic diff r3→r4 crew/ammo delta, который может принять
этот assertion, без изменения battle/native source.

**2026-10-06: bundle-rooted profile4 chain — PASS_PORTABLE_PROFILE4_CHAIN.**
Добавлен отдельный provenance/data-only verifier
`tools/profile4_chain.py`. На свежем bundle проверены immutable
`profile4-r4 → r3 → r2 → r1-catalog2`, profile/base SHA256, версии 4/3/2/1,
account/native DB continuity, monotonic grant IDs/timestamps, payload hashes,
сохранение `shop.bin`/`dossier.bin`, r2 preservation receipt, vehicle/crew
mapping и точная ammo mapping (shell2570/turret5891/gun5892/inventory1).
Native crew/ammo blobs совпали с grant hashes; старый bundle с неверным порядком
цепочки отвергнут negative control. Старые validators/fixtures/live runtime не
менялись, SQLite/client не открывались. Profile4 новый encoder не создан,
r3/r4 absolute preservation и native proof не повторялись: `NOT_RUN`.
План и отчёт: `docs/plans/PROFILE4_PORTABLE_CHAIN.md`,
`docs/research/PROFILE4_PORTABLE_CHAIN.md`; receipt:
`local/evidence/20261006-profile4-chain/result-final.json`. Следующий один шаг:
сделать отдельный semantic diff r3→r4 для crew/ammo delta без native запуска.

**2026-10-06: portable server-content/encoder export — PASS_CONTENT_EXPORT.**
Создан отдельный `server-content.v1` bundle для проверенной MS-1 `test_lab`
closure: 56 измеренных blobs, относительные content IDs, digest каждого файла,
digest полного client manifest и frozen encoder dependency revision.
`tools/content_bundle.py` валидирует bundle без project config, SQLite или
установленного клиента; `tools/portable_hangar_state.py` прочитал descriptor,
profile и packed XML из bundle и повторил profile1-catalog2 byte-for-byte:
`state.bin` 1106 B, `shop.bin` 419 B, `dossier.bin` 8 B. В bundle нет паролей,
email, session, live DB/WAL или абсолютных client paths; старые fixtures,
validators и absolute provenance сохранены без изменений. Profile4 immutable
r4→r3→r2→r1 chain экспортирован как hash-anchored closure, но отдельный новый
profile4 encoder ещё не объявлен. Ресурсы остаются `UNKNOWN; local-only
non-redistribution` до проверки лицензии. Native compatibility, свежий обмен с
клиентом, live cutover и 15×15 — `NOT_RUN`; это переносимость локального
генератора, не native acceptance. Тесты: 2 content-bundle unittest PASS,
bundle verification PASS 56/56, portable profile1 generation PASS. План:
`docs/plans/CONTENT_ENCODER_EXPORT.md`; отчёт:
`docs/research/CONTENT_ENCODER_EXPORT.md`; evidence:
`local/evidence/20261006-content-export/result-final-2.json` и bundle-папка. Следующий один шаг: отдельная
проверка portable profile4 chain на чистом bundle-rooted API без изменения
старых validators и live runtime.

**2026-10-06: opt-in identity/account boundary — PASS_IDENTITY_BOUNDARY.**
Создан отдельный loopback-only `identity.account.v1` сервис в
`server/identity/account_service.mjs` с версионированной SQLite migration,
единым `account_id`, email-only login, русским/латинским ником, scrypt hashes,
browser sessions и profile owner. Новый портал `web/src/account_portal.mjs`
проверен через регистрацию, явный повторный вход, смену профиля и чтение того же
UUID. `game` service-role проверяет те же email/credentials и получает только
`account_id`/ник/created_at; пароль, email, session и fixture path наружу не
выходят. Отказы contract mismatch, неверных credentials/role, неподдерживаемой
DB schema и недоступности сервиса проверены без ложного guest/fallback.
Пять isolated Node tests PASS; все SQLite/токены были в
`local/staging/identity-boundary`, live backend/site/client не переключались и
не перезапускались. Legacy `web/src/server.mjs`, `server/identity/service.mjs`,
старый native gateway и frozen encoders сохранены. Это HTTP/account boundary,
не доказательство native compatibility, настоящего боя или 15×15.
План и фактические границы: `docs/plans/INFRASTRUCTURE_BOUNDARIES.md`;
подробный отчёт и receipt: `docs/research/IDENTITY_BOUNDARY.md` и
`local/evidence/20261006-infrastructure-boundaries/`.
Следующий один шаг: отдельная карточка versioned server content/encoder export,
чтобы game profile generation перестала читать установленный клиент и evidence
paths, сохранив старые validators/provenance до независимой проверки.

**2026-10-06: организация серверных исходников — PASS_SERVER_SOURCE_LAYOUT.**
Завершена отдельная карточка структуры, без развёртывания и изменения физики.
Canonical `server/`: control, identity entrypoint, gateway с protocol/account/
arena/drive, physics. 20 Rust + 2 C# core files перенесены byte-identical,
старые точки запуска/сборки используют тот же source. Имена файлов без `091`
и `P01`; protocol IDs/ресурсные пути/исторические manifests сохранены.
291 canonical + 290 legacy Rust tests/build PASS; 50 Python PASS;
layout 7 PASS/1 SKIP (Windows symlink permission); identity 4 PASS.
Оба C# build PASS; два новых worker реально загрузили geometry, ответили
ready+3 состояния и завершились EOF/exit0. Их состояния на одном Windows
хосте совпали; общая/cross-platform детерминированность этим не доказана.
Ранние C# offline restore FAIL и identity harness FAIL сохранены отдельно.
Ordinary deployed EXE/config/PIDs не переключались: supervisor96576,
identity81748/gateway5192, site43164; capture=False. Source/library/client
hash preservation закрывается `local/evidence/20261006-server-layout/final-audit-02/result.json`.
Новая сборка gateway называется sr-gateway, но текущая служба всё ещё закреплена
за прежним p01-wg-probe.exe. Fresh init также сохраняет прежнее binding правило.
Новый native вход/поездка и Linux/remote build/ABI — NOT_RUN в этой карточке.
Shared identity/encoders остаются frozen; свежий профиль ещё зависит от client
resources и provenance paths. Это source layout, не самостоятельный deploy.
Документация: `server/README.md`, `docs/SOURCE_LAYOUT.md`.
Следующий один шаг: versioned server content/encoder inputs без зависимости
генерации аккаунта от установленного клиента и исследовательских каталогов.
Прежние ограничения pivot/круиза/разрушений ниже сохраняются.

**2026-10-06,11:15 UTC+5: ordinary backend восстановлен без capture;
итог ручного protocol повтора PARTIAL.** Два настоящих Flash-входа,14 camera
changes, первый штатный return/warm/reentry подтверждены, неожиданных
disconnect/reject/Python exceptions0.542 publications совпали с worker,
538 ACKed;4 последних retired при штатном quit из второй арены. Второй warm
return NOT_RUN; nonzeroMove→первый6 после fix2 NOT_OBSERVED (captured regression
PASS). Strict reader FAIL сохранён, supplementary scope PARTIAL.290Rust
tests/build PASS, source review0 blockers. Обычная служба supervisor96576,
identity81748/gateway5192, run061506-d7a679; capture=False, тот же pool,
exe daef0dde…0608c3b; клиент016 прежний. Не объявляется полный P02 PASS.
Владелец сообщил отсутствие pivot и разрушения деревьев. A/D доходят до
TrackedVehicleController, near-rest yaw почти не меняется: причина UNKNOWN.
Мир пока static MeshShape, разрушений нет. Частичные cruise25/50% дают safety
stop;100% идут ordinary flags1/2, действие владельца по ступеням NOT_RUN.
Остановки на подъёме OBSERVED, конкретная причина UNKNOWN. Подробности:
`docs/research/P02_SNIPER_CAMERA_PROTOCOL.md`, `P02_DRIVE_LIMITATIONS.md`;
evidence `local/evidence/20261006-sniper-camera/`. Следующая отдельная карточка —
диагностика pivot, без одновременной реализации разрушений/стрельбы.
Закрывающая read-only сверка ordinary runtime:88 build sources,34 immutable
client files,43 worker/map hash bindings PASS; оба native UDP и identity
слушают127.0.0.1. Сайт3091 сохраняет прежний внешний процесс и адрес0.0.0.0.
`local/evidence/20261006-sniper-camera/final-state-02/result.json`, SHA256
`59f1d6c872f5904ac11357770428e3058e8bf1f0cb5c43d566e968eba0e5d3dc`.
Reader01 harness FAIL (лишнее требование loopback к внешнему сайту) сохранён,
runtime не менялся. Полный inventory клиента/БД сегодня не повторялся.

**2026-10-06, после ручного повтора: fix1 camera PASS_SCOPED, второй вход FAIL;
fix2 собран, native повтор ожидается.** Первые8 переключений камеры прошли,
1719/1719 publications совпали с worker и ACKed; штатный возврат/warm sync.
Второй вход отверг exact app `8a01000106` (Move1→correction6), хотя footer
ACK1863 правильно подтверждал binding1862. Движение проверялось раньше6 в
том же compound; ошибка откатывала валидный ACK и RX. Это возникло до camera
RPC; время нажатия владельца не объявляется причиной. Fix2 учитывает exact6
в том же полностью parsed envelope, сохраняя настоящие forceACK/clone guards
и отсутствие worker effects до commit. 290Rust tests/build PASS, independent
review0 blockers; EXE SHA256
`daef0dde9e012beac4e0f363bf66b672ec4a154473be4b05b00cfe4cc0608c3b`.
Closed fixed-review-01 сохраняет FAIL_REPRO_SECOND_ENTRY; повтор fix2 NOT_RUN
до закрытого native результата. `local/client-install-016` прежний.

**2026-10-06,10:37 UTC+5: ручная Flash-кнопка PASS_2_NATIVE_FLASH_CLICKS;
переключение снайперского прицела — исправление на native повторе.**
Ordinary пакет016 нормализует измеренный callback float0.0→int0. Два реальных
клика открыли Avatar/карту;72 команды движения приняты сервером. Владелец
подтвердил движение/повороты/задний ход, круиз OBSERVED_OWNER_FEEDBACK;
точный контракт круиза UNKNOWN. На подъёме остановка/возобновление движения
OBSERVED_DEFECT, физика test_lab. Полный ручной цикл пока FAIL_TWO_DISCONNECTS:
оба разрыва при снайперском режиме и один последующий Minimap traceback сохранены.
Closed capture1704packets доказал первое неподдерживаемое приложение
`8d05000200000000`: original Avatar Base vehicle_changeSetting(setting2,INT32zero),
настройка автоповорота камеры.5B heartbeat отказы были следствием RX gap.
Сервер теперь валидирует только setting2/INT32 0|1; whole-envelope/ACK guards
сохранены, применение к физике отсутствует и явно логируется.
288Rust tests PASS,offline locked build PASS; новый executable
SHA256 `71b5e9de0af56aab433199ace0e508f69bfa9f8a6d0d738ece620bc776d63e61`.
Native повтор после исправления ожидается, **NOT_RUN до закрытого результата**.
Сайт не перезапускался, клиент016 не менялся; diagnostic capture включён только
для этого повтора. Отчёты: `docs/research/P02_MANUAL_BATTLE_BUTTON.md`,
`docs/research/P02_SNIPER_CAMERA_PROTOCOL.md`; evidence:
`local/evidence/20261006-manual-battle-button/manual-result-01/`,
`local/evidence/20261006-sniper-camera/`. Стрельба/урон/двое не подключены.

**2026-10-06, утро: запуск после устаревшего supervisor.lock восстановлен —
PASS_LOCAL_SERVICE_RECOVERY.** `status` теперь проверяет процессы, прежний
сохранённый RUNNING с отсутствующими PID сообщает как STALE. Автовосстановление
архивирует точные state/lock и требует подтверждённого отсутствия всех старых
процессов, совпадения владельца и свободных игровых портов. Живые/непроверенные
PID и maintenance lock сохраняются. Ранние ошибки serve также освобождают
собственную блокировку; lifecycle guard автоматически освобождается ОС.
36 lifecycle tests и65 применимых regression tests PASS. Обычный backend
поднят: supervisor78824/identity47384/gateway91148, оба native UDP endpoints
и identity health проверены. Внешний сайт43164 поднят с прежней network.json,
ownership/capture/map pool не менялись. Повторный start при живой службе
получил ожидаемый отказ без изменения state/lock. Игровая БД семантически
неизменна; полный дамп БД сайта изменился, точный состав утренней разницы
UNKNOWN (предполагается штатная очистка истёкших sessions). Пользователи
совпадают с сохранённым эталоном предыдущей карточки. PARTIAL этой проверки
сохранён отдельно; не объявляется полная неизменность обеих БД.
Ручной вход владельца сегодня OBSERVED; «В бой!» дал старый hangar-only отказ,
ручная поездка остаётся NOT_RUN. Отдельная карточка
`docs/plans/P02_manual_battle_button.md`: установлен ordinary policy, но первый
фильтр mapID/actionName не пропускает настоящий Flash callback; точные аргументы
пока UNKNOWN. Отчёт восстановления службы:
`docs/research/P02_SERVICE_RECOVERY.md`; evidence:
`local/evidence/20261006-service-recovery/`.

**2026-10-06,02:24 UTC+5: карточка локальной поездки PASS;
финальный аудит сохранности PASS; ручной ввод владельца NOT_RUN.**
Ride21:5 поездок одним EXE (Карелия×4, Прохоровка×1),5946packets,
1760/1760 публикаций подтверждены ACK,12/12 строгих остановок PASS.
Минимальный dense low-speed suffix2.7403s; worker после отхода от камня2.8s.
3129samples: own/bodyΔ0, targetdrop0;10560 масок опор, airborne0.
Ride22: native-путь до границы Прохоровки, stall под газом5.0258s
(worker5.8s), reverse6.4045m, остановки и возврат.881/881 публикация ACKed.
На ударе14/5286ticks потеряли левую опору, правая осталась; airborne0.
Измерено краткое перекрытие грубого корпуса со стеной8.585cm; не скрывается.
GUI/wire/data проверены независимо. Root просмотрела4PNG21 и3PNG22.
Исторические PARTIAL16/19 и FAIL17/18/20 сохранены.

Установлен `local/client-install-014`:25 модулей,34 immutable files и3
сохранённых owner logs. Sources/actual273 bytecode совпадают с21/22.
Автологин/автозакрытие/capture отключены, enable_map_drive=True.
Серверный режим `legacy091-map-drive`, тот же build10/pool, сайт не
перезапускался; игра закрыта. Полные manifests3469 original/3499 research
сняты и сверены с историческим baseline: неожиданных отличий0. Два semantic
DB snapshots, профили4/1, fixtures и4 конфигурации сохранены. Final audit
перепроверил25 текущих diagnostic restores/25replays,32619packets и27
исторических restore records. В обычном режиме native0/worker0, mutex свободен.
Итог `local/evidence/20261005-p02-map-drive/final-audit-02/final-state-audit.json`,
SHA256 `c07de7886178861d5c254eb0df1e0711446f01ec018b45547c8fb3482bc973c7`,
status `PASS_AUTHORIZED_LOCAL_DRIVE_SCOPE`. Предыдущий FAIL итогового reader01
сохранён: старый startup Bind03 имел другую документированную схему времени;
исправлена только её точная проверка, не runtime. После этого PASS менялся
только итоговый текст четырёх документов; отдельная inventory02 фиксирует
неизменность всех остальных исходников без повторения native опытов.
Доказательства: `local/evidence/20261005-p02-map-drive/` →
`data/ride21-physics-review-01`, `data/ride22-physics-review-01`,
`wire/ride21-review-01`, `wire/ride22-review-01`,
`gui/ride21-native-review-01`, `gui/ride22-native-review-01`,
`gui/normal014-package-review-01`, `root-visual-review-06`,
`root-visual-review-07`, `server-ordinary-12/after.json`.
Единственный следующий шаг владельца — ручной круг МС-1: «В бой!», движение
и задний ход, препятствие, возврат в ангар и повторный вход. Без таймера
закрытия игры и без управления компьютером со стороны агента.
Утреннее сообщение назначено около09:30 UTC+5. Полный P02/стрельба/бой вдвоём
не приняты; историческая физика UNKNOWN, текущий контроллер test_lab.

Ниже — история промежуточных прогонов; поздние результаты не переписывают FAIL.

**2026-10-06, ночь: поездка по карте — IN_PROGRESS.**
Последнее уточнение, около 01:40 UTC+5: Ride19 на build10 прошёл Карелию и
Прохоровку одним EXE, два возврата; 955/955 публикаций совпали с worker и ACK.
GUI/wire PASS_SCOPED, общий результат PARTIAL: после отскока на остановке
worker дал 1.8s покоя; между 1Hz замерами native filter кратко снова ускорился,
поэтому dense suffix у второго маркера 1.747s. Минимум приёмки 2s не меняется;
следующий диагностический вариант увеличивает ожидание до 3s. Камера19:
1070 samples, own/body Δ0, targetdrop0; reverse относительный maxstep 6.14mm
на Карелии / 3.13mm на Прохоровке. Это OBSERVED в данном прогоне.
Ride20 boundary_only сохранил FAIL до движения: validator скриншотов ещё
не принимал новую группу имён map_boundary_rNN_*. Клиент закрыт, installer
и replay откатились. Граница по-прежнему NOT_RUN. Результаты:
`local/evidence/20261005-p02-map-drive/data/ride19-physics-review-01`,
`local/evidence/20261005-p02-map-drive/data/ride19-hold-explanation-01`,
`local/evidence/20261005-p02-map-drive/wire/ride19-review-01`,
`local/evidence/20261005-p02-map-drive/gui/ride19-native-review-01`,
`local/evidence/20261005-p02-map-drive/root-visual-review-05`.
Сервер перезапущен с тем же build10 только для свежего ограниченного capture:
`local/evidence/20261005-p02-map-drive/server-drive-restart-11/after.json`.
Обычная установка normal014 ещё NOT_RUN.

R=`local/evidence/20261005-p02-map-drive/`. Ride16 одним EXE прошёл пять
случайных арен (Карелия четыре раза, Прохоровка один), пять возвратов в готовый
ангар; 25 снимков Account/ammo/repository совпали. Все1360 серверных публикаций
совпали с worker и подтверждены ACK; 4694 пакета,2399 native samples.
Wire/lifecycle PASS в этом объёме. Строгая остановка PARTIAL: в9/10 интервалов
фактический низкоскоростной suffix короче2s; исправлен только диагностический
отсчёт с первого допустимого замера. Ride17 сохранил FAIL во второй арене:
серверный poll_drive отказал при публикации worker247, затем оборвалась сессия.
Текст generic invalid() не доказывает неизвестный входящий RPC. Wire выясняет
конкретный guard. Первая Прохоровка17 уже подтвердила настоящий dense stopped
suffix2.667/2.854s после original stop; весь17 не принят. Ввод не автоматизируется.
Причинный replay исходных команд Ride16: полная карта побитно повторила716
состояний и4296 масок; без только696 треугольников целевого камня машина
продолжает путь. Под непрерывным газом2.9s: с камнем0.35mm, без17.14m.
Это OBSERVED_CAUSAL_IMPACT_AND_BLOCKING; sampled overlap2.65cm и прежний
NOT_CONFIRMED строгого5s критерия сохранены, нулевая пенетрация не заявлена.
Доказательства: `R/data/ride16-physics-review-06`,
`R/data/ride16-rock-causal-review-01`, `R/wire/ride16-review-03`,
`R/gui/ride16-native-review-03`, `R/root-visual-review-04`.
Общий source с режимами phase2_drive/boundary_only закреплён в
`R/gui/boundary-promotion-01` и`R/root-mode-integration-01`;186 focused tests
Python3 PASS,181 actualPython2.7.3 PASS+5 прежних host-only SKIP;
102 control/runner regression PASS. Реальная native граница ещё NOT_RUN.
Обычная установка normal014 и итоговый аудит ещё NOT_RUN; клиент во время
исследования запускается только через откатываемый диагностический installer.
Сайт не перезапускался, источник аккаунта и конфиги не менялись.
Игра17 закрыта, install/replay rollback PASS. Утренний heartbeat уже назначен
на6октября около09:30 поЕкатеринбургу.
Build10 применён после сохранённого старого regressionFAIL и284/284RustPASS:
новый запрос worker ждёт следующего непубликовавшегося native tick; ошибки
публикации именованы; аварийный Account reset отправляется сразу. До actual09
старые проверенные Avatar envelopes ограниченно разбираются без применения к
миру. Native прохождение аварийного recovery отдельно NOT_RUN.
Ride18 наbuild10 закрылся со сценариемFAIL: камень удержал машину; после
backoff5.45m basicforward3.82m снова привёл turn в препятствие, поэтому
порог угла не достигнут за30s. Меняется только диагностический отход12m,
граница/обычная физика не смягчаются. Клиент18 закрыт, rollback PASS.
Ниже сохранена история предшествующих результатов этой карточки.

**2026-10-05: управляемая поездка через «В бой!» — IN_PROGRESS.**
План `plans/P02_map_drive.md`, R=`local/evidence/20261005-p02-map-drive/`.
Владелец расширил задание до поездки, случайной проверенной карты, штатного
возврата в ангар и повторного входа. Промежуточные опыты это не закрывают.
Baseline380 authored files/17 local files/2SQLite backups сохранён до изменений.
VERIFIED readonly: native forcedPosition и updateOwnVehiclePosition нужны для
привязки Avatar.vehicle/ownVehicleMProv; прежнее движение тела этого не доказывало.
OBSERVED: отдельный synthetic Jolt tracked API test прошёл forward/turn/brake/reverse,
но не проверяет карту или клиент. Terrain/BSP двух original maps импортируются.
Кнопка и серверный random уже наблюдались на обеих картах; полная поездка,
статический obstacle и возврат/re-entry пока не приняты.
Предыдущие PASS ниже относятся только к явно указанным узким checkpoint.
Bind03 теперь PASS binding only: actual own/body ΔZ2m, original callbacks,
53.100s/426packets/exit0/restorePASS; Bind01 wireFAIL иBind02 observerFAIL сохранены.
Семь native Karelia rays совпали с mesh до0.00002885m. Новый .NET/Jolt worker
собран; обе mapmesh offline пройдены с measured MS-1 и test_lab подвеской;
840ticks/map, все тики имеют опоры слева/справа, forward/turn/reverse/stop PASS.
Worker-v1/pool опубликованы только в ignored local/. Полноценная
native поездка/button/random/return ещё НЕ ПРИНЯТА; работа продолжается.
Ride01/02 FAIL сохранены. Ordinary service policy counter1 + guard до внешнего
urlopen проверены настоящим клиентом: original CaptchaFalse,blocked0.
Исправлен diagnostic None→INT32zero для случайной карты. Ride03 уже даёт
CMD700→server random→workerREADY→Avatar/Vehicle. CMD502 исправлен и проверен.
Ride05 выявил native heading=worker roll: VERIFIED PE #717 требует RPY для
0x06/0x15, тогда как0x09/0x4a используютYPR. Только эти два codec исправлены,
253Rust tests PASS, build04 SHA59de4e8e…810f7. Ride06 выбрал Prohorovka;
начальный native yaw совпал с worker yaw. Запуск FAIL до движения: observer
потребовал roster ready раньше получения отправленного native ready122B.
Ожидание исправлено. Ride07/09 native forward/turn/reverse/stop наблюдались,
176 публикаций Ride07 побайтно связаны с worker и original callbacks/ACK.
Возврат выявил штатный warm enable09 и новую нумерацию ClientChat; исправлены.
Ride09 уже прошёл warm100/300/600, original showGUI/stream completion; текущий
observer FAIL — неверная классификация загрузки spaces/hangar_v2 после leave.
Исправляется только этот observer. Retry чтения native targetNone теперь0.1s,
прежняя readiness gap3s не увеличена. Полная приёмка по-прежнему IN_PROGRESS.
Все исходные FAIL/trace/replay сохранены, install rollback PASS. Серверные
273 теста PASS; отдельный opt-in capture profile48k/32MiB подготовлен для
same-EXE обеих случайных карт. Обычные лимиты и отсутствие autquit сохранены.
Ride10 обнаружил отсутствующий LOBBY_SUB во время перехода; добавлен exactNone
wait, без catch-all. Ride11 прерван отдельной nativeforward командой вне сценария
(её происхождение ещё проверяется). Владелец наблюдал рывки камеры приreverse;
это новый обязательный дефект к устранению до приёмки, не визуальный PASS.
Проверяется periodic0x4a correction против native interpolation и worker motion.
Владелец явно подтвердил: в Ride11 клавиши движения не нажимал. Происхождение
дополнительной команды UNKNOWN; не классифицировать её как ручной ввод.
Закрытые трассы подтверждают скачок own provider Ride09: за0.109072s он
сместился вперёд0.489508m, тогда как body/model/server двигались назад.
Это ещё не доказательство движения самой камеры: actual camera transform
тогда не записывался. R/data/ride11-jitter-review-01/result.json сохраняет
числа и ограничения; R/gui/sampler-checks-02 — новый ограниченный пассивный
измеритель actualcamera/own/body. Следующий опыт A сохраняет65B; кандидатB
проверяет initial4a + periodic15-only без изменений физики и клиентских позиций.
2026-10-05 вечером владелец поручил автономно продолжать эту карточку ночью;
утренний отчёт с ручными проверками назначен на6октября09:30–10:00 UTC+5.
Ride13A/Прохоровка: полный original Fight→drive→leave→готовый Hangar,
54.400965s/643packets/620samples/3PNG/exit0/restorePASS. Все7 movement callers
объяснены; команда Ride11 не повторилась, её происхождение остаётсяUNKNOWN.
Измеритель исправлен по signed32 native callback handle; отрицательный token
реально записан. Ride14B/Карелия и Ride15B/Прохоровка с тем же client source
прошли полный цикл. Build08(8a3d3dcc…41d43d) сохраняет initial122B/4a, дальше
публикует31B tickSync+15. Same-map A13/B15: reversecamera/body maxstep
0.477005→0.003705m, own/body совпали во всех674B samples, target switches300→0.
Это scoped camera/drive/return результат. Полная карточка ещё IN_PROGRESS:
same-EXE повторные карты, native obstacle/bound и обычная установка не закрыты.
Точные доказательства: R/gui/ride13a-native-review-01;
R/wire/ride14b-camera-review-01 иride15b-camera-review-01;
R/data/ride13-frame-review-03 иride15-frame-review-01 (итоговыйA/B отдельный).
Root просмотрела actual PNG A13/B15: карта/МС-1/90HP и возвращённый ангар
подтверждены, цветная сетка в original screenshot остаётсяUNKNOWN.
Развёрнутый текущий отчёт: `research/P02_MAP_DRIVE.md`.

**2026-10-05: native команда движения → серверная позиция — PASS узкой карточки.**
Q=`local/evidence/20261005-p02-arena-movement/`.
Move02/PID114140:63.536s,437packets/14794B, originalforward1→serverpath2m→
originalstop0, nativeVehicle/entitymatrix/modelmatrixΔZ=2m,hold≥3.015s.
Окончательный независимый отчёт19/19 PASS:
`Q/data/verify-move02-final-01/arena-movement-native-verification.json`, SHA256
`dc09da9016bb6fe6f2e8c4391dd7de7a3f4203271eb014aab759db53bd20548f`.
Nativeperiod3 только внутриlab,10Hz/1m/s/2m — собственная политика опыта.
97publications; четыреterminalstopped updates136–139 безACK перечислены
отдельно (доставкаNOT_RUN), принятие движения/hold на них не опирается.
Два originalPNG просмотрены,90/90HP; exit0/cleanup/restorePASS.
Move01 — сохранённыйFAIL наблюдателя доforward: originalauto0earlyRETURN12
ошибочно запрещался. Исправлен только exactautomatic branch;explicitstill345.

181Rust/40control/40runner/18profile/39verifier PASS;scenario36Python3,
35Python2.7.3+1host-onlySKIP иcompilePASS. Исходный Rust180/1FAIL negativefixture,
ранние readerFAIL иcorpora сохранены. Точные команды/хеши/откат —
`research/P02_ARENA_MOVEMENT.md`; план `plans/P02_arena_movement_probe.md`.
Normal01322modules/31immutable+3ownerlogs установлен; ordinarygateway
run121443-951a48 безcapture/trigger, сайт не перезапускался, клиент закрыт.
Обаgeneratedreplay сохранены/hash/timebound иоткачены;manifestoriginal3469/
research3496. Итоговая сверка — `Q/final-audit-01/final-state-audit.json`.
Baseline373sources/17localfiles/2SQLitebackups; игровые данные не менялись.

OBSERVED: getOwnVehicleMatrix осталась уseed,contacts0/0, nativeYoffset−0.07084m,
gunrotatorне запущен. Это ещё не управление своей машиной и не groundphysics.
ПолныйP02PARTIAL;NOT_RUN: гусеничныйконтроллер,ammoAvatar,выстрел/урон,
второйигрок/итоги/нагрузка. ЦветнаясеткаUNKNOWN; свежегоPythontracebackнет.
Один следующий шаг: originalcontrolEntity/сервернаякоррекция и связь с
getOwnVehicleMatrix в отдельном ограниченном опыте. Он здесь не начат.
Предыдущие ordinaryпакеты/рекомендации ниже — история.

**2026-10-05: native setClientReady → серверный PREBATTLE — PASS узкой карточки.**
O=`local/evidence/20261005-p02-arena-ready/`. Ready01/PID27912:90.528s,
247 пакетов/8202B, actual33B→51B preparation, семь разных значений таймера
на интервале6.036s. Два действительно просмотренных native PNG:27→21.
Exit0 и четыре стадии cleanup PASS; независимый отчёт18/18:
`O/data/verify-ready01-final-02/arena-ready-native-verification.json`, SHA256
`094edf304e3b39f6871440f2793df22a5a73ee9f16c1ee0dcc7bf051e7e272f8`.
Сервер применяет только готовность после ACK create97; три других метода
явно неподдерживаемые. Монотонный дедлайн30s не перезапускается и не начинает
BATTLE. Native expiry30s NOT_RUN: клиент завершился по выполненному условию.
Частота10 — параметр собственного опыта, не историческая tickrate.

162 Rust +31 control +40 runner +18 profile +33 verifier PASS; сценарий:
47 Python3 /46 Python2.7.3 PASS +1 host-only SKIP, отдельно PASS на Python3.
Независимый GUI/lifecycle review15/15 PASS: `O/gui/native-ready01-review-02/`.
Первый review-helper FAIL на неверном лимите8KiB для старого ammo-события
сохранён; исправлен только reader, исходные данные/клиент не менялись.
Original LightManager штатно инициализирован(enabled=false) и уничтожен.
Свежего Python traceback нет; графические DEVICE_LOST/RESET/shader warnings
и цветная сетка PNG остаются OBSERVED/UNKNOWN. Вводом компьютера не управляли.

Normal012 установлен:21 modules/30 immutable+3 owner logs; ordinary gateway
run105936-a33e1a без capture/trigger. Сайт не перезапускался, клиент закрыт.
Replay2096B сохранён по exact hash; дата/mtime связаны с запуском, прежнее
отсутствие восстановлено: `O/ready01-replay/restore.json`. Baseline365 sources/
17 local files/2 SQLite сохранён. Final manifest: original3469/research3495.
Отдельный результат итоговой сверки: `O/final-audit-01/final-state-audit.json`.
Полный отчёт, команды и откат: `research/P02_ARENA_READY.md`.

Физика: `research/PHYSICS_AUTHORITY.md`, original5 files/10 methods/17 anchors
PASS_READONLY_RESEARCH. WGVehiclePhysics/filter есть в клиенте; точное
предсказание/коррекция UNKNOWN. Jolt — кандидат библиотеки внутри battle worker;
прежний sphere/floor spike не доказывает гусеничное движение.
Полный P02 PARTIAL: BATTLE, Avatar ammo, ground contact, движение, стрельба,
второй игрок NOT_RUN. Один следующий шаг — ограниченный native эксперимент
команды движения своего МС-1 и серверного обновления положения. Он не начат.
Более ранние обычные установки и рекомендации ниже — история.

**2026-10-05: native арена с собственным МС-1 — PASS узкого checkpoint.**
N=`local/evidence/20261005-p02-arena-entry/`. Vehicle03 настоящий#717/PID73668:
Account→Avatar→Карелия→МС-1, native Battle/HUD,90HP и исходные модели;
172packets/6730B,4готовых наблюдения3.012s,65.475srun,exit0/cleanup/restore.
Независимый17/17 PASS `N/data/verify-vehicle03-final-01/arena-vehicle-native-verification.json`
SHA256 `42a55da5b88e3f2a2105c013e260fc6a70559007f5b136abc6520d6822fa19f2`.
GUI lifecycle/cleanup review14/14 PASS; свежего traceback/__manualSound нет.
Original Vivox unsupported и штатный AccountRepositoryNone warning сохранены.
Нативный снимок действительно просмотрен: ожидание игроков00:00, лабораторная
точка, контакт с грунтом не доказан. Цветная сетка PNG остаётся UNKNOWN.

Исправлен реальный wire порядок:221Bобъявление→actual08+ACKannouncement40→97B
Vehicle. Четыре original init-step return101/101/101/640; prerequisites,
onEnterWorld/startVisual и normal teardown подтверждены. Actual33B содержит
bindToVehicle/changeSetting/setClientReady/autoAim; пока только transport ACK,
без применения доменных команд. Серверные фазы/отсчёт/Avatarammo/движение/
стрельба/второй игрок NOT_RUN. Полный P02 PARTIAL, P03 не начат.

141Rusttests,24Vehicle-verifier,22rootguards+40runner+18profile PASS;
entry26/bootstrap28/space27/Vehicle41 — на Python3 и2.7.3 PASS,capacity19 PASS.
Ранние base01/space01/space02/vehicle02 ипервыйverifier03 FAIL сохранены;
неустановленный vehicle01 NOT_RUN.7настоящих диагностических запусков этой
карточки откатились; дополнительно сохранён generated replay1784B и восстановлено
его отсутствие по exact hash, `N/native-generated-replay-01/result.json`.

**Normal011 установлен:**20modules/29immutable+3ownerlogs, безtestcontrol/
autologin/autoquit/capture/управлениявводом. Gateway ordinary, сайт не
перезапускался этой карточкой, клиент закрыт. Профилиprimary4/secondary1 прежние.
Итоговая независимая сверка original/research,32 ledger entries,4configs,
профилей/fixtures и runtime: `N/final-audit-02/final-state-audit.json`.
Параллельная web demo работа из следующей записи сохранена отдельно и не
включается в функциональную приёмку арены. Полный отчёт/команды/откат:
`research/P02_ARENA_ENTRY.md`. Оценка1000CCU: `research/CAPACITY_1000_CCU.md`,
ориентиры3/5/7 физических узлов — ESTIMATE_ONLY, настоящая нагрузка NOT_RUN.
Единственный следующий шаг — серверная обработка настоящего setClientReady
и фаза подготовки одной арены с родным отсчётом. Эта карточка не начата.

**2026-10-05: публичная демоверсия сайта — PASS.**
По отдельному уточнению владельца опубликован самостоятельный каталог на
`https://tanks.nsnull.su`: главная, техника/модули, карты/миникарты, без аккаунтов
и игровой интеграции. VPS использует отдельные service/user/vhost и HTTPS;
существующий `duo.nsnull.su` сохранил конфигурацию и ответ авторизации.
5 Node-тестов и453 HTTPS-проверки (431изображение) PASS; браузер1280/390px PASS.
Локальные сайт и игровой bridge не перезапускались. Отчёт
`../web/REMOTE_DEMO_REPORT.md`, evidence `local/web/remote-deploy/20261005-01/`.
Это приёмка демонстрации каталога, не изменение статуса native P02 ниже.

**2026-10-05,14:05: native Avatar BASE принят; геометрия Карелии загружена,
чистое завершение частичного Avatar пока FAIL. Карточка арены IN_PROGRESS.**
N=`local/evidence/20261005-p02-arena-entry/`. Base02 independent14/14 PASS
(`data/verify-base02-final-02/`). Space02 independent14/15: точные cell/space
по родному09, original onEnterWorld/onSpaceLoaded, inWorld/space1/load1 PASS;
Vehicle отсутствует, initcounter1, userSeesWorld/worldDrawFalse. Fresh caught
original teardown AttributeError звука башни делает clean runtime FAIL:
`data/verify-space02-final-01/arena-space-native-verification.json`, SHA690b5ff9…9bec.
Оригинальный init_sound выполняется только после последнего шага с Vehicle;
заглушки полей и пропуск destroy не применяются. В этой же карточке готовится
настоящий собственный МС-1 + roster для завершения native lifecycle. Стрельба,
движение и бой NOT_RUN. Старая запись normal010 ниже историческая: сейчас она
штатно откачена; клиент закрыт, gateway в явном исследовательском space-режиме.
Расчёт1000CCU `research/CAPACITY_1000_CCU.md` готов (ESTIMATE_ONLY),19testsPASS.


**2026-10-05,12:51: начата карточка native Account → Avatar / локальная арена.**
План `plans/P02_arena_entry.md`; N=`local/evidence/20261005-p02-arena-entry/`.
Baseline сохранён:336 authored-файлов,17 local-файлов,2 SQLite backups.
Normal010 штатно откачен,3 свежих owner logs сохранены. Реальный resource export01
PASS: original Account/native PID9316,46 packets, родная Карелия type1/ctf,
`spaces/01_karelia/space.settings` доступен;11 исходных hash pins совпали.
Завершение exit0,12 cleanup, rollback PASS. Export не создавал Avatar/space;
загрузка арены и бой пока NOT_RUN. Evidence `N/native-arena-entry-export01.json`
SHA256 `11163b6e86951434d16221fd6fc6d7996a46628b71e75819185f6c28d9f17c2b`.
Подготовлен отдельный opt-in checkpoint смены native player; текущий рабочий
gateway ещё не заменён. Полный P02 PARTIAL, карточка арены IN_PROGRESS.
Параллельный расчёт1000CCU готов: `research/CAPACITY_1000_CCU.md`,
19 arithmetic tests PASS. Ориентиры3/5/7 физических узлов — ESTIMATE_ONLY;
нагрузка настоящего боя и1000 игровых сессий NOT_RUN.
Следующие записи — история предыдущих завершённых карточек.

**2026-10-05,11:54: минимальный серверный боекомплект МС-1 — PASS.**
В принятом test_lab primary profile4:20 обычных ББ,0 HEAT,0 ОФ. Сайт/API
показывают20; оба настоящих входа с прежним profile002 показали20/0/0 через
родной `AmmunitionPanel.__updateAmmo → as_setAmmoS`. В каждом94packets,
3actual snapshots/2PNG, ready17.1284/17.0981s,exit0/12cleanup/restorePASS.
Никаких закупок/пополнения/стрельбы;96 — вместимость,20 — тестовая выдача.
Отчёт `research/P02_MS1_AMMO.md`, M=`local/evidence/20261005-p02-ms1-ammo/`.
Paired report `M/wire/verify-ammo02-pair-02/ms1-ammo-verification.json` SHA256
`b218c032e9fddbee62f5284e98db9cb7019ddead25994d847af8119272ca035c` PASS;
41verifier tests и60 независимых отрицательных controls PASS. 84Rusttests,
85webtests (82full+3targeted),75root regression PASS. Новые data19Python+8Node,
GUI27+32+18 на Python3 и2.7.3 PASS; native не заменён этими unit tests.
**Normal010 установлен**,16modules/25immutable+3ownerlogs, безautologin/autoquit/
capture/управлениявводом. Native закрыт; сервер/сайт работают.
Fullaudit `M/final-audit-02/final-state-audit.json` SHA256
`cc69a32abcdd6b8ced4f82dd8884ecca8f3e330fa695b1baebb7f5471bba8a49` PASS:
original3469/research3490,0unexpected,17completed diagnostic restores,
4configs и secondary сохранны,21negativecontrols PASS_REJECTED.
Независимый review полного аудита также PASS:14дополнительных RAM controls,
`M/gui/final-audit-review-01/result.json` SHA256
`1ea80bb84c67456f76c459e5c8da5776978f34c5fb807d20896e9d66e19fbbe5`.
Выдача обратима4→3 с journal SHA555015e2…87819; exactcommands в отчёте.
Production rollback и ручная проверка владельцем новой выдачи NOT_RUN.
Полный P02 PARTIAL; арена/бой NOT_STARTED. Единственный следующий шаг:
минимальный native Account→Avatar и загрузка одной своей локальной арены.
Карточка завершена; дальнейшие фазы этим запуском не выполняются.
Более ранние IN_PROGRESS/NOT_RUN ниже — история, не текущая приёмка.

**2026-10-05,11:24: P02 боекомплект МС-1 — IN_PROGRESS.**
После разрешения владельца начата одна карточка `plans/P02_ms1_ammo.md`.
Владелец закрыл клиент; before/backups и свежие owner logs сохранены, normal009
штатно откачен. Настоящий export01 прочитал родные данные #717: вместимость96,
снаряды2570/2826/3082, выбор танка не изменён. Native process/capture/restore PASS;
envelope `local/evidence/20261005-p02-ms1-ammo/native-ms1-ammo-export01.json`,
SHA256 `683daac81143a9d7edfbe671870ba163db088c54f5101fa52e077f596ebbfc74`.
Политика test_lab:20 обычных ББ,0 HEAT,0 ОФ, без склада и автопополнения.
Это ещё не выдача: профиль primary пока3; native приёмка боекомплекта NOT_RUN.
Подготовлена добавочная схема4 с неизменным catalog3/wire1; арена/бой вне среза.
Записи ниже описывают историческое состояние на указанный момент.

**2026-10-05,10:41: естественное истечение сессии и повторный вход — PASS_MANUAL_AND_BACKEND.**
Владелец: «истечение сработало, выбросило на вход, вход прошел нормально».
Сохранённый gateway подтверждает SESSION_CLOSED id11 reason=session_deadline
настроке5790, затем session12 ACTIVE5835 для того же UUID/nativeID, sync100/300/600
и showGUI. Между сессиями38no_session rejects, в session12 до конца snapshot
отказов нет. GUI подтверждён владельцем (OBSERVED); точная задержка перехода
UNKNOWN, автоматический native trace сценария NOT_RUN. Новых запусков нет.
Отчёт `research/P02_MANUAL_EXPIRY_20261005.md`; evidence
`local/evidence/20261005-p02-manual-expiry/review01/result.json`, SHA256
`7fb14ef7c550a3f6a6821a6f198fcdbc5a0a7a09cb1f8301e5509914ec2b58a1`.
Normal009 и сервер оставлены работающими, конфигурация/код/профили не менялись.
Полный P02 PARTIAL. Следующий рекомендуемый срез: исследовать родной контракт
боекомплекта МС-1 и проверить минимальный серверный боекомплект после relogin.
Эта новая карточка не начата. Более ранние NOT_RUN ниже — история до подтверждения.

**2026-10-05, после утреннего запуска владельца: ручная проверка PASS (OBSERVED).**
Владелец явно подтвердил «Всё нормально» для входа, экипажа МС-1 и переключения
МС-1 ↔ ИС-7. Отчёт `research/P02_MANUAL_ACCEPTANCE_20261005.md`.
Evidence `local/evidence/20261005-p02-manual-acceptance/review01/result.json`,
SHA256 `9903b5ed5dc0c63702bec6d01fb826f9378bdd1294f05dd633f79d191934e50b`.
Все23 immutable файла обычной009 совпадают с принятой установкой. Свежий
сохранённый python.log:0EXCEPTION/0Traceback,2известныхERROR неподдерживаемого
Vivox. Завершённая server session10 успешна; точная временная связь с клиентским
блоком INFERRED. Более поздняя session11 наблюдается отдельно, mutex занят;
её результат не приписывается предыдущему проходу. Новых запусков/тестов нет.
Ручной PASS относится только к явно перечисленным трём пунктам. Expiry1800s
и прочие окна NOT_RUN; полный P02 PARTIAL. Следующий шаг прежний: настоящий
session_deadline1800→disconnected→LoginView. Исторические ночные записи ниже
сохраняют состояние на момент их написания.

**2026-10-05,07:46: ночной срез завершён — native, полный audit и independent review PASS.**
План `plans/P02_long_hangar.md`, отчёт `research/P02_LONG_HANGAR.md`,
L=`local/evidence/20261005-p02-long-hangar/`. Независимый final audit review завершён:
11 actual bindings и38 negative controls PASS, `L/wire/audit-review-01/result.json`,
SHA256 `c82997905b315e35636034b75acd87a5081a7203d1463233016fd69d3adc617b`.
Один EXE PID49420:938.3719s,2580packets/53082B,exit0/12cleanup/restorePASS.
Native ready913.2943s/909samples/maxgap1.0699222s.182реальныхCMD501/CCU1/1/
normalreturns;181послеready/span907.7934s.3совпавших полных snapshots,2PNG
просмотрены,0fresherrors/retransmissions. Это CCU, не изменение статистики игрока.
Final20gate report `L/wire/verify-long01-03/long-hangar-verification.json`
SHA256 `c74df14374e053bab68c13a5c1b366814834b50ba8a084123340b32062b95d25`.
40verifier tests/55independent controls PASS. Первый verifier FAIL(generator
resume counted as new entry) сохранён; native повтор не понадобился.
**Normal009 установлен**,14modules/23immutable+3ownerlogs, безcontrol/autologin/
autoquit/capture/управлениявводом. Native закрыт, server/site работают.
Fullaudit `L/final-audit-02/final-state-audit.json` SHA256
`1932650550743d296355af81edd48c8e176820853a9e52ba916c6c0e82a2cf1e` PASS:
original3469/research3488,0unexpected,14completedrestores,54negativecontrols;
29backend/4configs/70runtime/обаprofiles/fixtures сохранны в границах L.
Откат ordinary009 после закрытия клиента и сверки ledger:
`python -B -X utf8 tools/interactive_client.py rollback --out local/client-install-009`.
Утренний отчёт `research/OVERNIGHT_20261005.md`, индекс файлов
`research/OVERNIGHT_20261005_FILES.md`. Heartbeat automation-2 PAUSED после
завершения ночного среза; новые карточки не запускаются. Единственный следующий шаг:
реальный session_deadline1800→disconnected→LoginView. Сейчас UNKNOWN/NOT_RUN:
gateway закрывает session безnativekick; немедленный возврат GUI не обещается.
Ручная приёмка ночных изменений NOT_RUN. Полный P02 PARTIAL,арена/бойNOT_STARTED.

**2026-10-05,06:42: поздние datagrams закрытого BaseApp peer — PASS.**
План `plans/P02_retired_base_replay.md`, отчёт `research/P02_RETIRED_BASE_REPLAY.md`,
T=`local/evidence/20261005-p02-retired-base-replay/`.
Один настоящий replay01 PID96040:280 packets, из них277native+3 точных повтора
из действительно освобождённого старого peer. Все3 отвергнуты; B остался готов,
A вернулся со своими данными. Exit0/12cleanup/restorePASS,3PNG просмотрены.
Final verifier `T/wire/verify-replay01-02/retired-base-replay-verification.json`
SHA256 `8a7274f8f6742af1dd2a3d343d8a52817ac2c5f7c0bb85d019a86a44ae0f72f5`.
59verifier tests,58independent controls,14gates offline repeat PASS.
Final audit `T/final-audit-02/final-state-audit.json` SHA256
`05a209133d77e92aa51864083ff59dcdf86c846cf55829234567be4b2af9a066` PASS:
original3469/research3487,0unexpected,13restores,оба profiles/fixtures прежние.
Независимый audit review: actual binding и17negative controls PASS.
**Normal008 установлен**,13modules/22immutable+3ownerlogs, без control/auto-login/
auto-quit/capture;normal007 проверенно откатан. Клиент и probe закрыты.
Сервер run20261004T234409-c866fd и сайт работают. Откат после закрытия игры:
`python -B -X utf8 tools/interactive_client.py rollback --out local/client-install-008`.
Следующий шаг исследуется отдельно: длительный готовый ангар с реальными
periodic server updates. Пока NOT_RUN. Ручная приёмка NOT_RUN; полный P02 PARTIAL.
Никаких новых выдач, экономики или арены.

**2026-10-05,05:49: переключение primary → secondary → primary — PASS.**
План `plans/P02_account_switch.md`, отчёт `research/P02_ACCOUNT_SWITCH.md`,
evidence `local/evidence/20261005-p02-account-switch/` (S).
Один EXE PID7600,3 настоящих auth/Account/repository,279 packets=93+92+94,
16.073/16.076/16.070s готового ангара,3 просмотренных native PNG.
NativeIDs1→2→1; машины2→1→2,танкисты2→0→2, собственные dossier/streams каждого
аккаунта, точное восстановление primary cache. Данные профилей не менялись.
Exit0/12cleanup/restorePASS,0trace/0свежихPythonerrors. Ручная приёмка NOT_RUN.
Verifier60ffcbbe…29d4,46 tests PASS, независимые31 review controls PASS.
Final report `S/wire/verify-switch02-02/account-switch-verification.json`
SHA256 `530dd12717cef8967d23fded670b49fa3d0c3855c56a2ee88537403d17612dd6`.
Root repeat `S/root-verification-02` PASS. Старый verifier пропускал лишние
public metadata fields; exact schema исправлена, промежуточный PASS сохранён.
Runner больше не сохраняет SHA control с credentials, только проверяет в RAM.
На момент закрытия S **Normal007 установлен** (позднее проверенно откатан
карточкой T),13modules/22immutable+3ownerlogs, без control/auto-login/
auto-quit/capture. Full original3469/research3487,0unexpected,12restores,
20negative audit controls;29backend/4config/2profiles/fixtures unchanged.
Final audit `S/final-audit-02/final-state-audit.json` SHA256
`5f3f202c65acf530c1d594e652d9330a65fb205f3cb9f7007379c74b55102c42` PASS.
Игровой клиент закрыт; server run20261004T234409-c866fd и сайт работают.
Откат после закрытия игры и проверки ledger:
`python -B -X utf8 tools/interactive_client.py rollback --out local/client-install-007`.
Следующий отдельный шаг начат карточкой T выше. Арена/экономика/новые выдачи
не начинались.

**2026-10-05,05:06: повторный вход внутри одного EXE — PASS.**
План `plans/P02_inprocess_relogin.md`, evidence `local/evidence/20261005-p02-inprocess-relogin/`.
До изменений сохранены288 sources/14 local files/2 DB. Первый настоящий запуск
R01 завершён FAIL: после корректного logoff сервер отверг второй login кодом73.
Клиент сохраняет транспортный ключ внутри EXE, но меняет encrypted nonce и
LoginApp endpoint; прежний запрет любого retired key слишком широк. Отрицательный
report `local/evidence/20261005-p02-inprocess-relogin/wire/verify-relogin01-negative-01/inprocess-relogin-verification.json`
SHA256 `8b3dea4c27a28b51861672b5cb54601e8a32ee19af76a0b1ee85deb39d808dfe`.
95 пакетов, один ангар/PNG, exit0/12 cleanup/restore PASS. Normal005 откатан;
клиент закрыт. Узкая политика nonce и retired endpoints внедрена,83 Rust checks
PASS; новый gateway EXE `8aea2e503c3b20e13b5eb9a9be7d66d2912a5027d8404a268bf65dfc778c41e1`.
R02 завершил оба входа и два16s интервала готового ангара в одном PID90800:
188 packets,2 PNG просмотрены,exit0/12cleanup/restore,0 свежих ошибок.
Строгий verifier83 tests PASS, итоговый native report
`local/evidence/20261005-p02-inprocess-relogin/wire/verify-relogin02-03/inprocess-relogin-verification.json`
SHA256 `9f42acfd7928d824ad4e52a22c9c0470784a76252e1aff8a82577a047c40b071`.
Root повтор отдельно PASS (`root-verification-01`). Доказаны два свежих auth
worker, retirement1 до allocation2, две доставки всех точных payload/cache.
На момент закрытия R **Ordinary006 был установлен** (затем проверенно откатан
карточкой S),12 compiled modules/21 immutable files+3logs,
без control/autologin/autoquit/capture. Full original3469/research3486 audit
PASS,0 неожиданных отличий,11 диагностических restores; оба profile/fixture
прежние. Итоговый audit SHA256
`0ff1f08a1c7d56a3ac1c1e378aa4848d74511ead31bad52745df6916ffc6ff35`.
Сервер/сайт работают, клиент закрыт. Ручная приёмка ordinary006 NOT_RUN.
Генераторы, fixtures и игровые профили заморожены; мышь/клавиатура
не используются. Предыдущие обычные установки ниже — исторические checkpoints.
[Отчёт, проверки, ограничения и откат](research/P02_INPROCESS_RELOGIN.md).
Откат normal006: `python -B -X utf8 tools/interactive_client.py rollback --out local/client-install-006`.
Следующая отдельная проверка: primary → secondary → primary в одном EXE,
изоляция существующих аккаунтов и кэшей. Пока NOT_RUN; бой NOT_STARTED.

**2026-10-05,03:47: два неподключённых окна ангара — узкая карточка PASS.**
«Внешний вид» и «Обслуживание» из панели теперь показывают отдельные родные
предупреждения. Оба исходных entrypoint/fireEvent и неподключённые окна не
вызываются; информационные callbacks модулей сохранены. Ремонт, пополнение,
кастомизация и бой этим не реализуются.

Windows01→02: по78packets/3 native PNG/3 неизменных crew snapshots,
0 новых ошибок,exit0/12cleanup/restore PASS. Тот же profile002 и ненулевые
cache hints. Парный report `local/evidence/20261005-p02-hangar-windows/wire/verify-windows02-paired-01/hangar-windows-verification.json`,
SHA256 `62a206bf7c208a313900b12e5cfdcf30b4a7690d01676ae8e7ea81a4d78903ec`;
root повтор побайтово тот же. Policy110/scenario31/runner33/verifier53 checks PASS.

**Checkpoint обычной установки normal005**,11 проверенных compiled modules,
без control/autologin/autoquit/capture. Игра закрыта, сервер и сайт работают;
primary profile3 с экипажем МС-1, второе игровое состояние побайтово прежнее.
Full manifest/ledger audit PASS:original3469/research3485,0 неожиданных отличий,
9 ночных restores. Report `local/evidence/20261005-p02-hangar-windows/final-audit-02/final-state-audit.json`,
SHA256 `ddbfa7525ce105e44518f1ae4bb797e31db588af46718fb898503627788eda32`.

Откат: `python -B -X utf8 tools/interactive_client.py rollback --out local/client-install-005`.
Физические клики, ручная приёмка и отдельный запуск normal005 NOT_RUN.
Цветная зернистость native PNG UNKNOWN. Полный P02 PARTIAL; арена/бой NOT_STARTED.
[Отчёт, ограничения, команды](research/P02_HANGAR_WINDOWS.md).
Следующий отдельный проверяемый шаг: original logoff→LoginView→повторный вход
одним аккаунтом внутри одного EXE, без перезапуска. Пока NOT_RUN.

## Checkpoint границ боя и приветствия

**2026-10-05,03:12: границы боя и приветствие — PASS.** Полные native
limits02→limits03 прошли: оба танка, профиль и возврат, реальный disabled
Flash-button, complex tooltip, явный отказ callback, ноль команд мутации.
По6 просмотренных PNG,3 неизменных crew snapshots,0 новых ошибок в каждом
успешном проходе;exit0/12cleanup/restore PASS. Тот же profile002 и ненулевые
реальные cache hints подтверждены отдельной строгой проверкой.

Парный report `local/evidence/20261005-p02-hangar-limits/wire/verify-limits03-strict-01/hangar-limits-verification.json`,
SHA256 `f296eaedd7e9c40aad4a7da9d58d24070cfbbf25819da2775d3a4abf74162587`.
63 проверки verifier PASS. Limits01 сохранён FAIL собственной диагностики;
его штатный выход не выдаётся за успешный сценарий. [Отчёт, команды и откат](research/P02_HANGAR_SERVICE_LIMITS.md).

**Сейчас normal004 установлен**, те же10 compiled modules и два MO, которые
проверены limits03. No control/autologin/autoquit/capture; игра закрыта,
сервер/сайт работают. Откат: `python tools/interactive_client.py rollback --out local/client-install-004`.
Ручной запуск именно этого normal-конфига NOT_RUN. Физический hover NOT_RUN;
проверен original complex API и текст на PNG. Original/research full manifests
сняты:3469/3484 файлов; финальная сверка ledger PASS, неожиданных отличий0.
`local/evidence/20261005-p02-hangar-limits/final-audit-02/final-state-audit.json`
SHA256 `506c0792bf55f1bac0fda5c21ca3d00f364fd1e01a4c993be3ad93395755dddb`.
Семь диагностических откатов и22 before-checks пакета004 PASS. Второй аккаунт
реально проверен через сайт, его игровая запись побайтово прежняя.

Дальше в разрешённой ночной доводке — отдельная карточка входов
«Внешний вид»/«Обслуживание». Оригинальная причина первого падения исследована;
ремонт, пополнение, кастомизация и бой этим не реализуются. Полный P02 PARTIAL,
P03/арена/бой NOT_STARTED. Человеческая приёмка ночью NOT_RUN.

## Checkpoint минимального экипажа

**2026-10-05, ночной checkpoint: минимальный серверный экипаж МС-1 — PASS.**
Собственный primary получил двух танкистов, профиль3. Реальная доставка,
родное отображение, явный отказ изменения экипажа и cached relogin crew02→03
проверены. Деньги/XP/статистика, ИС-7 и второй аккаунт сохранены. Сайт/API
показывают назначение экипажа. Ручная приёмка владельцем NOT_RUN.

Доказательства: `local/evidence/20261005-p02-ms1-crew/` (`C`). Парный отчёт
`C/wire/verify-crew03-final-01/ms1-crew-native-verification.json`, SHA256
`ec625af4067714e80c56a7bb260007483f1ef8736da2ea5c7d452683c7961dd6`.
Полная Node suite73, Rust62, независимый verifier34 PASS. Crew01 FAIL
наблюдателя сохранён; crew02/03 — по62 пакета, три crew snapshots и два PNG,
штатный exit0,12 cleanup и rollback PASS. [Отчёт/команды/откат](research/P02_MS1_CREW.md).

На момент checkpoint экипажа игра закрыта, диагностические overlays сняты. Normal003 уже откатан;
последние пользовательские логи сохранены. Normal004 ещё НЕ установлен.
Сервер/сайт работают с profile3, конфигурации endpoint не менялись.
Полный P02 PARTIAL; P03, арена и бой NOT_STARTED. Долгий проход с новым
экипажем NOT_RUN, найм/обучение/перемещение/личное дело недоступны.

Владелец поручил автономную работу до утра: [ночной план](plans/OVERNIGHT_20261005.md).
Следующая отдельная узкая карточка — честная недоступность кнопки боя и
исправление одного старого приветствия; исследование `C/data/next-hangar-gates.md`.
Она не реализует очередь, экономику или бой.

## Предыдущий checkpoint UI13

**2026-10-04: контрольный UI13 и пара UI08 → UI13 — PASS.** Закрыта
узкая карточка двух машин, подсказок/Awards и повторного входа с кэшем.
Полный P02 остаётся PARTIAL; P03/арена/бой не начинались.

`E` = `local/evidence/20261004-p02-hangar-ui/`.

| Проверка UI13 | Результат |
|---|---|
| Ручной запуск без таймера стенда | PASS; новый manual_client_run,14/14 unit tests; никаких автокликов |
| Повторный native вход с прежним profile002/cache | PASS; initial100/300/600 + revision1 refresh; кэш не очищался |
| Устойчивый ангар до вкладок | PASS;125.7657979s,126 последовательных samples |
| МС-1 ↔ ИС-7, native модели/имена/90 и2150HP | PASS; фактический цикл и native PNG |
| Original complex ToolTip и Awards | PASS; callbacks, просмотренные native PNG;0 свежих ошибок UI13 |
| Подсказка недоступности оборудования | OBSERVED/PASS на фото владельца; хранится отдельно от native markers |
| Сеть/сервер | PASS;586 packets,198.9757065s канала, точные3 streams |
| Ручное завершение | PASS;247.3996002s процесса,exit0,no timeout,11 cleanup,rollback PASS |
| Общий verifier/session/cards/relogin | PASS; `E/is7-verifier/ui13-reviewed-01/` |
| Аккаунты после UI13 и последующего normal003 | PASS; оба точных профиля/ресурсы/статистика сохранены |

Отчёт UI13 SHA256 `2b6620e1b91725bfe941a59dbffbc968748630381fb9fc090a24e53213cee3cc`.
Независимый wire proof: `E/wire-analysis/ui13-manual-proof-01/`,16/16 PASS.
Фото оборудования: `E/owner-screenshots-ui13/`; свежие профили:
`E/accounts-after-normal003-01.json`. Исторические UI09–UI12 FAIL сохранены.

**Отдельная проверка владельца normal003: обнаружены ошибки найма экипажа
и внешнего вида.** Владелец подтвердил собственный повторный запуск22:32–22:33
и открытие этих окон. Trace62556 подтверждает вход и ангар; python.log содержит
IndexError в RecruitWindow.__getInitialData и
VehicleCustomization → ShopRequester.getInscriptionsGroupHiddens. Эти окна
ещё не готовы. Свой outcome/exit code и отдельная полная приёмка normal003
отсутствуют (UNKNOWN/NOT_RUN), ошибки OBSERVED_FAIL. Это не тот же run, что UI13.
Логи не откатывались: `E/normal003-extra-launch-01/`. Аудит04 FAIL по снимку
менявшегося во время ручного запуска лога сохранён. Финальный `E/final-audit-05/`
PASS: original3469 файлов неизменны; research3480, неожиданных отличий0;
12/12 диагностических восстановлений,17/17 backups пакета003 и отдельная
проверка отката002 PASS. Допускаются только два точных сохранённых user-log
хеша;4 отрицательных проверки отвергают любые другие изменения.

Сейчас установлен обычный `local/client-install-003`: те же6 compiled modules,
profile002, endpoint127.0.0.1:20014, без control/autologin/autoquit/автоскриншотов.
Игра закрыта, сервер/сайт работают. Нового таймера закрытия EXE нет; собственный
лимит серверной сессии1800s пока остаётся. Откат после закрытия клиента:
`python tools/interactive_client.py rollback --out local/client-install-003`.
Выдача ИС-7 и данные аккаунтов сохраняются. Команды/доказательства/границы:
[GUI](research/P02_HANGAR_UI.md#ui13-ручное-завершение-вместо-таймера),
[ИС-7](research/P02_TEST_IS7.md).

Следующий рекомендуемый отдельный шаг: минимальный серверный экипаж МС-1
с проверкой отображения и сохранения при повторном входе. В этой задаче
экипаж, кастомизация, боеприпасы и бой не реализовывались.

## Предыдущий checkpoint и история

Текущая карточка, 2026-10-04: **тестовый ИС-7 выдан, каталог модулей
исправлен, повторный native-вход с сохранённым кэшем работает. Полная
приёмка карточки PARTIAL; полный P02 PARTIAL, P03 NOT_STARTED.**
[Каталог/GUI](research/P02_HANGAR_UI.md), [ИС-7 и cached sync](research/P02_TEST_IS7.md).

`E` = `local/evidence/20261004-p02-hangar-ui/`. Основной аккаунт получил второй
серверный экземпляр ИС-7,2150HP; МС-1, UUID/nativeID,100000/0/0 ресурсов и
нулевая статистика сохранены. Сайт/API показывают обе машины; второй аккаунт
сохранил свой МС-1. Повтор выдачи ALREADY_GRANTED. Финальный read-only контроль:
`E/accounts-final-01.json` PASS, сайт3091 работает.

| Проверка | Фактический результат |
|---|---|
| UI08: первый вход с двумя машинами | session/garage PASS,357 packets,74.336 s ready, Awards pixels PASS,exit0/rollback PASS |
| UI09: первый cached relogin | FAIL: не распознаны persistent hints CMD100/300; исторический corpus сохранён |
| UI10: следующий cached run | FAIL: initial streams приняты, но CMD100 revision1 с тем же persistent hash ещё отвергался |
| UI11: после обоих исправлений | wire/backend/garage/GUI PASS,289 packets,0 свежих ошибок,exit0/11cleanup/rollback PASS; strict session FAIL только41.173 s непрерывного ready вместо60 |
| UI12: контроль устойчивости | OBSERVED657.113 s непрерывного готового ангара; полный run FAIL по720s harness timeout/exit1, штатный cleanup NOT_RUN; filesystem rollback PASS |
| Код | 236 Python checks закрыты:235 PASS+1skip в общей suite, пропущенный файловый тест отдельно PASS; Node65/65, Rust61/61 PASS |

UI11 final report: `E/is7-verifier/ui11-reviewed-final-01/test-garage-verification.json`.
Он не маскирует непрошедший duration gate успехом GUI. UI12 не склеивается с
UI11 в выдуманную успешную сессию. Пиксели текста недоступности оборудования
остаются NOT_RUN; оригинальные complex callbacks с этим текстом наблюдались.
Технические исправления проверены настоящим клиентом, полная парная приёмка
с60 s ready, нужными пикселями и штатным выходом в одной сессии ещё не закрыта.

Постоянный research-пакет: `local/client-install-002`, свой endpoint20014,
профиль `local/client-profile-002`, без control/autologin/autoquit/автоскриншотов.
Игра закрыта; сервер и сайт оставлены работающими. Отдельный запуск именно
этого финального конфига после установки NOT_RUN; те же compiled modules
проверены в UI11/UI12. Старый пакет001 восстановлен и повторно не используется.
Финальные manifests: `E/final-manifest-02/`; аудит установки и исходников:
`E/final-audit-03/`. Original3469 файлов неизменны. Research3480 файлов
соответствуют исходному состоянию, двум точно сохранённым входным логам и
финальному ledger: неожиданных отличий0,17/17 before/backup checks,
11/11 диагностических восстановлений PASS. Два лога изменились между
UI04 и UI05; инициатор UNKNOWN. Они сохранены, первоначальное строгое
сравнение остаётся FAIL (`final-audit-02`). Пустой temp replay после timeout
сохранён с хешем/backup и обратимо перенесён в `E/ui12-timeout-replay-01/`.

Откат клиентских overrides — своим ledger; откат выдачи — точная запись
профиля по журналу плюс отдельный обратимый шаг для owned dossier cache.
Реальный откат выдачи на primary NOT_RUN; временные SQLite rollback tests PASS.
Клиентское управление остаётся у владельца. Арена/бой/экипаж/боекомплект и
экономика не реализовывались этой карточкой. Следующий шаг один: завершить
контрольный cached relogin на той же копии с измеренными60 s до переходов,
подсказкой оборудования, Awards и ручным чистым выходом. Ниже история.

Дата исходного плана: 2026-10-02.

Обновлено: 2026-10-04 (Asia/Yekaterinburg). Runs: `20261002-p00-p01`,
`20261002-p01-bootstrap`, `20261002-p02-login-redirect`, `20261004-p02-baseapp-reply`,
`20261004-p02-channel-ack`, `20261004-p02-server-reliable`,
`20261004-p02-session-gateway`, `20261004-p02-account`,
`20261004-p02-account-ready`, `20261004-p02-hangar`,
`20261004-p02-unified-account` (финальная установка/audit завершены).

**Текущий узкий результат: единая email-учётка сайта и native-вход в ангар
с серверными данными — PASS. Полный P02 PARTIAL, P03 NOT_STARTED.**
Одна таблица users и один password verifier; account_id равен users.id.
Вход только по почте, отдельный уникальный ник поддерживает русские буквы,
латиницу, цифры и `_` с сохранением регистра. Email не входит в игровой
payload; resources/inventory остаются test_lab, статистика нового игрока нулевая.
План: [P02_unified_account_entry](plans/P02_unified_account_entry.md);
отчёт и точные команды: [P02_UNIFIED_ACCOUNT](research/P02_UNIFIED_ACCOUNT.md).

В этом текущем блоке `E` = `local/evidence/20261004-p02-unified-account/`.

| Проверенный срез | Результат и evidence |
|---|---|
| Основной сайт → прежний аккаунт → native | PASS Email17: UUID `c5326cc1…`, nativeID1,91.360 s готового ангара; `E/wire-agent/verify-email17-primary-01/unified-entry-verification.json` |
| Второй основной аккаунт с русским ником | PASS Email18: UUID `271022a3…`, nativeID2,176.846 s готового ангара,180.263 s соединения, server/client sequence134/40; `E/wire-agent/verify-email18-primary-cyrillic-01/unified-entry-verification.json` |
| Сохранение профиля через настоящий restart и relogin | PASS Email19: прежний UUID/nativeID1,76.359 s ready,254packet hashes; `E/wire-agent/verify-email19-primary-relogin-01/unified-entry-verification.json` |
| Два primary профиля и изоляция /api/game | PASS: `E/primary-state-before-restart-01/`, `primary-state-after-restart-01/`, `primary-state-after-native-01/`; UUID, данные и fixture hashes сохранены, чужой query не меняет subject |
| Единственный владелец основного сайта | PASS: `E/primary-external-restart-01/restart.json`; game supervisor остановлен/запущен, website PID9452 продолжил работу; external mode не владеет сайтом |
| Обычная форма входа без control/autologin/autoquit | PASS Normal21: процесс жив95.003 s, original LoginView ready76.435 s,0пакетов своего gateway; `E/gui-agent/normal21-prepare/normal-idle/normal-idle-report.json` |
| Ручной вход владельца в Normal20 | PASS только AUTH_AND_SERVER_ACCOUNT_DATA_ONLY: владелец подтвердил «Да, сам ввел, вошел, потыкал разное», trace связывает login с UUID `c5326cc1…`/nativeID1; `E/wire-agent/manual-auth20/manual-auth-analysis-02.json` |

**Полный GUI Normal20 — FAIL, не замаскирован успешным входом.** Сохранены семь
ошибок original ToolTip `len(None)` и одна ошибка primitive-сериализации
собственного observer. Observer исправлен:9 unit +5CPython2.7.3 checks
PASS. Email22 с новым source подтвердил wire/identity/ангар и exit0, но получил
ещё1originalToolTip error после fini_enter: **overall FAIL сохранён**.
Повтор самого ProfileAwards после фикса NOT_RUN. Producer пустого tooltipId
и точная кнопка/действие пока UNKNOWN. Historical idle gate Normal20
остаётся FAIL: человек выполнил вход во время измерения ожидания. Отдельный
Normal21 проверил нетронутую форму. Оба idle harness завершены собственным
принудительным stop, поэтому clean native exit для них NOT_RUN.

Финальная research-копия установлена: `local/client-install-001`,
без control/autologin/autoquit, свой endpoint20014/сайт3091. Клиент закрыт.
Полный audit **PASS**: original unchanged; research = baseline +12установленных
файлов, неожиданных изменений0; 21/21 диагностических откатов и15backup/before
checks PASS. Evidence: `E/final-state-audit-02.json`; состав source/hashes:
`E/project-after.json`, `project-changes.json`, `source-handoff-audit.json`.
Основные Email17/18/19/22 native PNG просмотрены root. Недостающих входных данных
для авторизации нет; двух независимых клиентов/ПК для будущей арены ещё нет.

## История предыдущих карточек

Ниже прежние NOT_RUN, таймеры и числа восстановлений относятся к указанным
карточкам. Текущие результаты и ограничения приведены выше.

**Предыдущий результат: штатный ангар и собственная сводка статистики с серверными
данными — PASS.** Итоговая серия normal/loss/rejection/relogin:4/4 на одном
живом gateway. Настоящий клиент показывает MS-1, ник,100000/0/0 тестовых ресурсов,
90/90HP и нулевую статистику нового игрока; original callbacks и Flash данные
коррелируют с серверными streams. Шесть native скриншотов просмотрены.
План: `docs/plans/P02_hangar.md`; [итоговый отчёт](research/P02_HANGAR.md).
Evidence: `local/evidence/20261004-p02-hangar/verify-final-03/hangar-verification.json`.
Работа была разделена на GUI, данные и wire; реальные запуски выполняла одна сессия.
Оригинальный клиент неизменен, все22 диагностических отката к своему before PASS.
Строгое сравнение research с началом карточки — FAIL по3логам отдельного старта;
они сохранены. Владелец сообщил, что, вероятно, пытался запустить клиент сам.
Полный audit: `local/evidence/20261004-p02-hangar/final-state-audit.json`.
В том лабораторном профиле сохранялись32 reliable sequence/таймер30s.
На этой точке остановились: арена, бои и экономические действия не начаты.
После завершения этого рубежа владелец разрешил следующий срез: **единая учётка
сайта/игры и ручной запуск исследовательского EXE на свой endpoint**.
На момент завершения ангара новая работа была IN_PROGRESS, её приёмка NOT_RUN.
Теперь узкая единая авторизация подтверждена текущим блоком и новым отчётом;
исторический ангарный PASS сам по себе её не заменял.
Единый аккаунт сайта/игры остаётся обязательным требованием; лабораторное
состояние игрока не является отдельным продуктовым реестром авторизации.

**P00 выполнен в текущей среде. P01 PASS по исследовательским критериям
docs/03_ROADMAP.md:** есть реальные client runtime traces, native login request
и принятый клиентом отрицательный ответ своего endpoint. Причина, достаточная
для раннего exit, воспроизведена через instance mutex. Карта оставшихся
неизвестных зафиксирована. По последующему разрешению владельца выполнена
узкая карточка P02: LoginSuccess → первый настоящий BaseApp request, два
клиентских запуска PASS. Следующая разрешённая карточка подтвердила BaseApp
reply, первый encrypted frame и настоящий callback LOGGED_ON в двух запусках.
Следующая карточка подтвердила ACK первого reliable frame и ограниченный
keepalive: 16.5853 и 21.6106 секунд после LOGGED_ON до диагностического quit.
Далее первый reliable packet сервера и его дубликат получили настоящий
client cumulative ACK=1/1 в трёх завершённых runs.
По новому разрешению идти последовательно до крупного шага выполнен
**локальный transport/session gateway рубеж**: 10 native входов/выходов подряд
на одном живом gateway; gap/selective ACK/retry, неверный пароль/digest,
дубликат, обрыв и recovery проверены. Итоговая серия 14/14 PASS.
Следующее разрешённое продолжение подтвердило первое native создание
`Account.PlayerAccount`: message ID5, entity type0, ID и 3 поля из server packet.
Пять реальных creation runs PASS по wire criterion, no-creation control PASS.
В следующей разрешённой карточке устранены исследованные bootstrap blockers:
**минимальный оригинальный Account lifecycle и начальная синхронизация PASS**.
Подтверждены три native RPC, original callbacks и один dossier stream с CRC.
Итоговая серия 8/8: семь успешных Account сессий на одном gateway, включая
loss/duplicate controls, и отказ неверного пароля. Последующий вход успешен.
Следующая карточка довела этот путь до штатного ангара и собственной сводки
профиля:4/4 native cases PASS. Настоящие state/shop/dossier streams, showGUI,
revision refresh и display-only данные проверены; state доставлен в3fragments.
На конец ангарной карточки обычный bootstrap/native preferences, persistence
и web→game login ещё были NOT_RUN; позднее они получили отдельные проверки.
Полный Account/P02 остаётся PARTIAL: общий канал/fragments/wraparound,
полный GUI и арена не приняты. Следующие фазы не начаты.

| Этап | Статус | Доказательства |
|---|---|---|
| P00 | PASS (локальная среда; вторая чистая машина NOT_RUN) | Полные manifests, Git exclusions, проверенный rollback |
| P01 | PASS — исследование, не приёмка игрового сервера | Runtime + native request/rejection PASS; stock toolkit native/vertices FAIL, отличия измерены |
| P02 | Единая email-учётка/native ангар PASS; полный gate PARTIAL | Primary17/18/19, два профиля/restart, normal idle21 PASS; ручной auth20 PASS, full GUI20 FAIL; final installation/audit PASS; Email22 overallFAIL(ToolTip при fini), general transport/арена NOT_RUN |
| P03 | NOT_STARTED | Нет |
| P04–P08 | NOT_STARTED | Нет |
| P09–P12 | NOT_STARTED | Нет |

Точный локальный билд: `v.0.9.1 #717`, RU; metadata client 435206,
overrides 435633, localization 428638 RU. Издательская аутентичность UNKNOWN.
Строка entity compatibility: `ru_0.9.1_2`.

Пути заданы в исключённом `config/project.local.json`; original только читается.
Исторический baseline до hangar: в обеих копиях3469 файлов /
14 680 626 869 байт. Content manifest SHA-256:
`74c37c18e9ac7e30196c134076dacf6f2a8bf3897f7def73905d09feb3647797`.
После запусков account-ready все файлы обеих копий совпали с baseline:
`20261004-p02-account-ready/integrity-comparison.json`.
Все19 client runs той карточки восстановлены; её `client-restores.json` сверяет
hashes с before. Позднейшие три log-различия research сохранены в hangar audit;
новая unified-card использует собственный baseline; final audit PASS с
явным сохранением финальной установки.

Путь старого офлайн-проекта: не требуется; не изменять.
Выбранный транспорт: NATIVE_PRIMARY; узкий login/rejection обмен проверен,
также проверены LoginSuccess, BaseApp reply и первый encrypted client frame;
ACK первого packet и bounded transport проверены; interactive native Account
session и >32sequence подтверждены текущей карточкой. Общий надёжный канал,
wraparound и арена ещё не проверены.
Первые последовательности, selective ACK, ограниченный retry/window и
минимальная лабораторная сессия подтверждены. Полный игровой lifecycle UNKNOWN.
Выбранный стек: предварительный; [ADR](decisions/ADR_TRANSPORT_AND_STACK.md).
Историческая формула разброса: UNKNOWN.
Доказанный онлайн: не измерен.

## Фактические результаты

Это хронология отдельных этапов. Прежний NOT_RUN означает состояние на момент
названного этапа; актуальная общая учётка и её ограничения перечислены в начале.

- PASS: 20 Python tests, из них 5 читают настоящий клиент; 70 файлов decoded,
  44 entity names, 23 aliases, 62 ZIP package indexes, 2255 pyc семейства 2.7.
  Активный runtime подтверждён: Python 2.7.3, MSC v.1700, 32-bit, Jun 17 2014.
- PASS: 128-мм WT E 100 clip=6; 150-мм clip=4; premium HESH FV183 цепочка
  конкретного орудия/снаряда даёт 275/275.
- PASS: collision hull Т-34-85 — 301 vertices, 198 triangles, 16 groups;
  прочитаны chunk/cdata Прохоровки. Полная физическая карта ещё не импортирована.
- PASS: wg-toolkit на commit `5b879f0...` собран и читает настоящий XML.
  FAIL: штатный vertex decoder оставляет 2408 из 9700 байт legacy section.
- PASS: JoltPhysicsSharp 2.22.0 / Native 1.1.0, headless Windows-x64/net9.0,
  300 steps и contact. .NET 10, tracked vehicle simulation, Linux — NOT_RUN.
- PASS: ранний exit воспроизведён занятым `wot_client_mutex`; теперь preflight
  отказывает до изменений, не закрывая игру владельца.
- PASS: собственный `.pyc` в res_mods загружается, marker/runtime получены.
  Python source-only на этом пути дал ImportError; исправлено компиляцией 2.7.3.
- PASS: два запуска без debugger — 273-byte native login → RSA OAEP/SHA1
  decode → 45-byte reply → `LOGIN_REJECTED_SERVER_NOT_READY` → штатный exit 0.
  Исторический код 73 подтверждён; современный toolkit code 74 означал updater.
- PASS: 4 Rust boundary tests и 4 проверки настоящего corpus/его повреждений.
  Stock toolkit читает этот packet неправильно; профиль legacy091 собственный,
  vendor не изменён. Полный login/arena — NOT_RUN.
- PASS: отдельная карточка P02 — ответ 28 B, Blowfish с ключом из native
  LoginRequest, redirect на второй loopback endpoint, шесть реальных BaseApp
  requests по 21 B в каждом из двух запусков. Токен ответа совпал с каждым.
- PASS: 51 проверка текущего corpus/backend (34 offline повреждения BaseApp,
  17 UDP controls/отрицательных случаев), повторные 20 Python / 4 Rust tests,
  прежний native P01 rejection и полный откат. `onChangeEnvironments` hook
  исправлен после ошибки первого run, свежие логи повторного запуска чистые.
- PASS (2026-10-04): BaseApp reply 24 B → первый encrypted client packet 24 B
  с новым token; callback `[1, 'LOGGED_ON', '']`, два настоящих запуска.
  После первого frame другие payloads не dispatch-ятся; наблюдался callback
  `[6, 'NOT_SET', '']`. Причина завершения пока INFERRED, стабильного канала нет.
- PASS: 75 новых corpus/backend checks (50 offline + 25 UDP), 8 Rust / 20
  Python tests, real redirect regression и полный client rollback. Новых
  dependencies нет; прежние profiles сохранены.
- PASS (2026-10-04, channel-ack): clear ACK `08 04 01 00 00 00`, encrypted
  16 B, прекращает повтор первого sequence=0. Два завершённых positive runs
  удержались 16.5853/21.6106 s; ACK=0 удержал связь с 9 вхождениями seq0;
  без ACK разрыв через 5.2258 s до planned quit.
- FAIL сохранён: `native-ack-01`, Windows UDP 10054 в capture при shutdown,
  итоговый exit отсутствовал. Runner исправлен с явной записью bounded reset
  events; повторные runs PASS, включая реальный 10054 в run 03.
- PASS: 34 новых parser/UDP/Windows checks, 75 прежних BaseApp regression
  cases, 11 Rust / 20 Python tests. Все пять client runs откатились, свежие
  Python logs чистые, полные manifests обеих копий совпали. Зависимости прежние.
- PASS (server-reliable): server seq0 и один identical duplicate → native
  transport-only ACK flags0x0448, sequence1/2, cumulative1/1. Три corrected
  runs, удержание16.58–21.62 s; keepalive-only control не вызывает этих ACKs.
- FAIL сохранён: native-01 нового run — bytes получены, но observer ошибочно
  требовал application token. Измеренный transport-only формат добавлен только
  в новый профиль за peer/key/handshake checks; native-02/03/04 PASS.
- PASS: 35 новых controls, 34 ACK regression cases, 13 Rust / 20 Python tests.
  Все пять запусков откатились, manifests совпали, процессы завершены.
  Исходник diagnostic personality в этой карточке не изменялся.
- PASS (session-gateway): server sequence1 при пропуске0 → selective ACK=[1],
  cumulative0; поздний0 → cumulative2; duplicate1 сохраняет2. В gateway
  контролируемая потеря первого0 устранена автоматическим retry по таймеру.
- PASS: один persistent gateway PID87048, 10 успешных native входов/выходов
  подряд; затем отказ пароля, blackhole и успешный recovery. Всего 14 сценариев
  итоговой серии; session IDs1–12, active state в конце отсутствует.
- PASS: native INVALID_PASSWORD=67 и BAD_DIGEST=69, без allocation; digest
  mismatch создан в server expectation, другой клиентский билд NOT_RUN.
- PASS: 33 новых own-UDP controls, 35 regression, 19 Rust / 20 Python tests.
  FAIL controls-01 был ошибкой bytes/bytearray в тестовом harness, сохранён;
  после исправления controls-02 PASS. Код gateway для этого не менялся.
- PASS: все 22 client runs восстановлены, полные manifests совпали. Personality
  получила только явный отрицательный парольный control; native callbacks
  не подменяются. Один disposable lab account; web/ не подключён.
- PASS (native Account wire): серверный `createBasePlayer` ID5/VAR2,
  type0, entity ID152043521 и три поля коррелируют с настоящим
  `Account.PlayerAccount` из `BigWorld.player()` в пяти запусках.
  Контроль без create packet: 22 пустых samples. Потеря packet с Account
  исправлена автоматическим retry; duplicate first client frame не создаёт
  вторую server session. Account/Entity callbacks не подменялись.
- FAIL предыдущей карточки (Account Python lifecycle): `Settings.g_instance.userPrefs` при
  `ContactInfo.py:43`, далее `syncData` отсутствует при become/non-player.
  Этот bootstrap blocker устранён в следующей карточке; старые ошибки сохранены.
- PASS: 20 Rust / 20 Python tests, 33 own-UDP controls, native no-creation
  regression; все 6 client runs восстановлены. Полные manifests после
  последнего запуска сверены с baseline. Файлы web не изменялись.
- PASS (account-ready): оригинальные Settings и Account ctor/onBecomePlayer/
  onBecomeNonPlayer завершаются; native data revision1/synchronized=True,
  pending commands/streams0; lifecycle доказан normal return offsets, не только
  отсутствием traceback. Original Account classes/callbacks не заменены.
- PASS: doCmdInt3 ID0x8e VAR2, commands100/300/600; onCmdResponseExt ID0x4d VAR1;
  native ranges прочитаны из88 bytes своего child. Остальные candidate IDs UNKNOWN.
- PASS: один dossier stream18 B, resource IDs52/53; original game CRC/length
  check и original Account.onStreamComplete подтверждены. General fragments NOT_RUN.
- PASS: 8/8 native series на одном gateway PID22872 — sessions1..7 и password
  rejection67 без allocation; потери create/sync reply и дубликаты first/RPC frames
  обработаны, commands по1 разу. Готовое состояние удерживается9.06–10.09 s.
  Отдельный повтор с исправленным runner и no-creation control также PASS.
- PASS: 26 Rust /20 Python tests, 311 actual-corpus mutation checks и33 прежних
  own-UDP gateway controls. Все19 client runs откатились, полные manifests обеих
  копий совпали,31 записанный собственный PID завершён/отсутствует, порты свободны.
- FAIL эксперименты сохранены: invalid preferences guard, file_server KeyError,
  unicode path TypeError, cache-thread timeout, wrong RPC route0x4c. Старый generic
  outcome ошибочно искал legacy log marker; исправление проверено отдельным run.
  Исследовательский getter shim изолирует Python caches; native preferences NOT_RUN.
- NOT_RUN на конец account-ready: полноценный ангар/магазин, разные пользовательские аккаунты, persistence,
  общая web→game авторизация, OS egress capture, арена. Пустое состояние своего
  diagnostic account не является проверкой экономики или готовности сервиса.

Git инициализирован, remote/commits нет; user.name/email не настроены.
Code version фиксируется evidence code-manifest. Клиенты, дампы, ключи,
локальная конфигурация, vendor и извлечённый контент исключены из Git.
Собственные отображаемые названия зафиксированы в [NAMING](NAMING.md):
владелец утвердил GAYmDev Stutio и рабочее «Стальной рубеж». README обновлён,
сессия сайта уведомлена. Технические имена/provenance сохранены, EXE и исходные
ресурсы массово не переименовывались. Названия карт пока не утверждены.

## Отчёты и приёмка

[CLIENT_AUDIT](research/CLIENT_AUDIT.md), [PROTOCOL_MAP](research/PROTOCOL_MAP.md),
[RESOURCE_MAP](research/RESOURCE_MAP.md), [INTEGRATION_SPIKES](research/INTEGRATION_SPIKES.md),
[KNOWN_UNKNOWNS](research/KNOWN_UNKNOWNS.md), [ADR](decisions/ADR_TRANSPORT_AND_STACK.md),
[MISSING_INPUTS](../MISSING_INPUTS.md), [команды/откат](research/REPRODUCE.md),
[evidence index](evidence-index/P00_P01.md).
Текущее продолжение: [BOOTSTRAP_AND_NATIVE_LOGIN](research/P01_BOOTSTRAP_AND_NATIVE_LOGIN.md).
Предыдущая карточка: [P02_LOGIN_REDIRECT](research/P02_LOGIN_REDIRECT.md).
Далее: [P02_BASEAPP_REPLY](research/P02_BASEAPP_REPLY.md).
Далее: [P02_CHANNEL_ACK](research/P02_CHANNEL_ACK.md).
Далее: [P02_SERVER_RELIABLE](research/P02_SERVER_RELIABLE.md),
[её evidence index](evidence-index/P02_SERVER_RELIABLE.md).
Далее: [P02_LAB_GATEWAY](research/P02_LAB_GATEWAY.md),
[её evidence index](evidence-index/P02_LAB_GATEWAY.md).
Далее: [P02_NATIVE_ACCOUNT](research/P02_NATIVE_ACCOUNT.md),
[её evidence index](evidence-index/P02_NATIVE_ACCOUNT.md).
Далее: [P02_ACCOUNT_READY](research/P02_ACCOUNT_READY.md),
[её evidence index](evidence-index/P02_ACCOUNT_READY.md).
Предыдущая: [P02_HANGAR](research/P02_HANGAR.md), включая точные команды,
снимки,4/4 native acceptance,38Rust/20Python/21encoder/52verifier checks и откат.
Текущая: [P02_UNIFIED_ACCOUNT](research/P02_UNIFIED_ACCOUNT.md): email-only,
русский ник, stable UUID/native ID, primary/restart evidence, normal/manual
срезы и сохранённый full-GUI FAIL. Source suites58Node/55Rust и независимые
native verifiers не объявляют готовность арены или всей продукции.
Ранние разделы выше — история отдельных карточек; их прежний NOT_RUN не заменяет
более позднее подтверждение штатного ангара и сводки статистики.

R02 runtime и диагностический путь R03 закрыты. R05–R07 имеют первый реальный
request/reply corpus. В отдельной карточке P02 подтверждён первый BaseApp
request/reply, первый encrypted frame/ACK и первый server reliable packet/ACK;
ограниченный канал и transport/session lifecycle проверены. Wire creation
Account/type0, original lifecycle/initial sync, showGUI и штатный ангар подтверждены;
неизмеренные entity/RPC IDs UNKNOWN. V02 PASS в лабораторном native-сценарии;
V01/V04 имеют подтверждённые поднаборы, полный P02 остаётся PARTIAL.

**Единственный следующий рекомендуемый шаг:** локализовать producer пустого
tooltipId на конкретной кнопке/действии, получить воспроизводимую original
trace и проверить исправление без подавления ошибки. Арена — отдельная
последующая карточка с явным разрешением; автоматического перехода нет.
P03 не начат.

Отдельно 2026-10-04 владелец запросил параллельную сессию сайта с регистрацией
и личным кабинетом. Чат `01a10526-7835-77f0-bccf-48f0baa5dee0` работает только
в `web/` и `local/web/`; имеет собственные проверки. Веб-авторизация не является
доказательством native Account/session или приёмки P02.
История уведомлений до unified-card: по прямому поручению владельца сайту отправлен статус:
его собственные регистрация/вход проверены, общей авторизации с игрой пока нет.
Сессии также отправлены подтверждённый minimal Account результат и новые
публичные названия. Web→game login не объявлен готовым.
После завершения ангара отправлено новое информационное уведомление:4/4 native
cases PASS, собственная сводка профиля работает, fixture остаётся test_lab,
единая авторизация ещё NOT_RUN; новой работы/фазы уведомление не поручает.
Владелец отдельно подтвердил единую учётку для сайта/игры: одна регистрация,
общие credentials/account_id/профиль. Тогда раздельность была временной,
требование добавлено в SCOPE/ARCHITECTURE и передано сайту. Его прежний
NOT_RUN закрыт current primary17/18/19 и state/restart evidence; история
уведомлений не является текущим статусом авторизации.
