# P03: battle shooting — loadout preparation route

Дата: 2026-10-06, Asia/Yekaterinburg.

## P03D owner acceptance (2026-10-07)

The fresh research-client MS-1 entry on the isolated panel gateway visibly
showed the complete three-slot battle ammo panel: AP `2570:20`,
HOLLOW_CHARGE `2826:0`, HIGH_EXPLOSIVE `3082:0`. This is classified as
`OBSERVED_OWNER_SCREENSHOT`; the copied screenshot and SHA256 are recorded in
`local/evidence/20261007-battle-ammo-panel-01/owner-test/owner-panel-acceptance-01.json`.

The frozen owner capture contains 621 packet files with packet-integrity PASS
and zero bounded transport parse errors. Packet 73 is the server→client
155-byte body; its bytes from offset 122 are exactly
`13440a0a0000140000000013440a0b0000000000000013440a0c00000000000000`,
with method prefixes at `122/133/144`. The transport audit deliberately does
not decode pickle/object payloads, so the wire evidence is bounded transport
verification while the HUD result comes from the owner screenshot.

`equipment` and `consumables` remain `null` in the verified MS-1 input; no
server-provided equipment item was expected or observed. Zero-count shell
selection, firing, reload, consumption, hit/damage and physics remain outside
this card. The panel card is accepted as
`PASS_OWNER_NATIVE_AMMO_PANEL_HUD`; the next card must be a separate
server-authoritative firing/reload/consumption slice.

## P03D — complete battle ammo panel route (2026-10-07)

Owner screenshot after build07 showed the selected AP row `2570:20`, but no
HOLLOW_CHARGE/HIGH_EXPLOSIVE rows. The route inspection found that build07
appended one `Avatar.updateVehicleAmmo` entity method only. The closed native
MS-1 export and GUI callback already verify the complete ordered panel:
`2570:20`, `2826:0`, `3082:0`; `equipment` and `consumables` remain absent.

The isolated P03D change adds all three fixed 11-byte methods atomically after
the existing binding/preparation body. Ordinary map-drive binding is now
`122 + 33 = 155` bytes; PREBATTLE preparation is `51 + 33 = 84` bytes. The
route accepts only the pinned MS-1 descriptors/counts and keeps
`quantityInClip=0`/`timeRemaining=0` as the same explicit candidate values.

Canonical build `gateway-battle-ammo-panel-01`: 319 Rust tests PASS, executable
SHA256 `4247c1e9a575570e6252e3ccbfd503fa0b50d8d926f04ac8f3acaefdf2630a0a`.
Legacy shared entrypoint: 318 tests PASS, SHA256
`4e222ddee890938e2af2fc47ade4fab976f6247ebc5f42100ba99713fb4d4c03`.
Fresh isolated bind-smoke on `20134/20136` PASS. The deployed gateway and live
service were not replaced. Full receipt:
`local/evidence/20261007-battle-ammo-panel-01/result.json`.

The offline route/build acceptance was followed by one fresh owner-driven
MS-1 entry. The screenshot confirms all three battle ammo slots, while the
bounded capture confirms the 155-byte server body and three method prefixes.
Zero-count row selection and any separate equipment battle message remain
**NOT_RUN/UNKNOWN**. Fire, reload, movement, sniper and a second client remain
outside this card.

## Owner capture review and build07 correction

Первый owner-driven прогон build06 завершён, но его результат — это route
miss, а не доказательство того, что клиент отверг ammo event. В
`owner-capture-060` bounded-аудит подтверждает 658 packet files, Login/BaseApp
redirect и 654 encrypted transport frames без ошибок. Клиентский trace
подтверждает выбранный MS-1, вход в `BattleLoading`/`onSpaceLoaded` и чистый
выход. Сразу после точного `READY_COMPOUND` сервер послал binding body длиной
122 байта; ни `0x13 0x44`, ни `13440a0a00001400000000` в server→client телах нет.
Владелец наблюдал «БК нет». Хангарные callback-данные `2570:20`, `maxAmmo=96`
остаются только OBSERVED_NATIVE_HANGAR.

Причина подтверждена кодом: для живого map-drive `self.drive.is_some()` в
`receive_ready` направляет сообщение в `drive_avatar`, а не в более позднюю
`queue_map_binding` ветку. В `drive_avatar` build06 оставлял старый 122-byte
binding. В build07 кандидат строится из того же проверенного
`BattlePreparation`, добавляется в эту реальную ветку до reliable enqueue, и
сервер пишет `route=drive_avatar`, `native_receipt=NOT_RUN`.

Build07: 318 Rust tests PASS; executable SHA256
`39be8ca6b782ed5c902c0aa93d9dff4cf31a50910d959947687db338e719bec8`
(полное значение и receipt —
`local/build/server/gateway-battle-shooting-native-loadout-07/result.json`),
source layout PASS, isolated bind smoke PASS. Fresh owner handoff:
`local/evidence/20261006-battle-shooting-native-loadout-01/owner-test-build07.md`.
Следующий единственный шаг — один повторный MS-1 entry на build07 с
`owner-capture-070`; fire/move/sniper по-прежнему запрещены.

## Native Avatar ammo candidate: offline card

Отдельная offline-карточка `P03_BATTLE_SHOOTING_NATIVE_LOADOUT` довела
исследование до точки, где нужен ручной native test. В сохранённом
`method-tables.json` из original #717 `Avatar.updateVehicleAmmo` имеет
`native_message_id=68 (0x44)`, типы `INT32, UINT16, UINT8, INT16` и ровно 9
байт аргументов. Existing `updateOwnVehiclePosition`/entity framing закрепляет
выбор сущности префиксом `0x13`; новый codec строит только фиксированный
`0x13 0x44` body.

Candidate выводится из уже authenticated/server-owned `BattlePreparation` и
принимает только MS-1 inventory1, turret5891, gun5892, shell2570, count20.
Закодированный tuple сейчас `(2570, 20, 0, 0)`: compact descriptor, total
quantity, `quantityInClip`, `timeRemaining`. Первые два значения подтверждены
закрытым native MS-1 ammo evidence; `quantityInClip=0` — bounded
**INFERRED_CANDIDATE** для одноствольного орудия, а не runtime fact. В ordinary
map-drive маршруте пакет добавляется после существующего 122-байтового
ready/binding body после own-vehicle creation ACK: итоговая reliable запись —
133 байта. Duplicate ready не создаёт повторную ammo запись, retransmit сохраняет
те же bytes. Отдельный legacy PREBATTLE probe остаётся 51 + 11 = 62 байта.
Session пишет
`BATTLE_NATIVE_AMMO_CANDIDATE ... native_receipt=NOT_RUN` и не считает это
native compatibility acceptance.

Отдельный bounded offline-аудит закрытого `map-drive-phase2-v1` capture
проверил все 345 packet hashes, RSA Login/BaseApp handoff и 341 encrypted
channel packet: каждый channel packet расшифровался и прошёл тот же ограниченный
transport parser, что и `protocol/transport.rs`. В payload не найден ни точный
кандидат `13440a0a00001400000000`, ни `0x13 0x44` prefix; два случайных
`0a0a` совпадения помечены только как byte pattern. Это VERIFIED_OFFLINE факт,
что старый map-drive capture не содержит ammo candidate. Semantic object/pickle
decode не выполнялся, поэтому это не доказательство native Avatar acceptance.
Полный receipt: `local/evidence/20261006-battle-progress-loadout-capture-01/offline-transport-audit.json`.

Изолированная canonical сборка `gateway-battle-shooting-native-loadout-07`
прошла **318 Rust tests**, executable SHA256
`39be8ca6b782ed5c902c0aa93d9dff4cf31a50910d959947687db338e719bec8`, source layout PASS,
deployed `p01-wg-probe.exe` не изменён. Полный receipt:
`local/evidence/20261006-battle-shooting-native-loadout-01/result.json`.
Не подтверждены после route fix: фактический Avatar callback в бою, точное
значение `quantityInClip`/`timeRemaining` в этом состоянии, порядок относительно
других server messages и визуальный HUD. Первый owner handoff build06 сохранён
в `local/evidence/20261006-battle-shooting-native-loadout-01/owner-test.md` и
его capture/trace разобраны; свежий follow-up лежит в
`local/evidence/20261006-battle-shooting-native-loadout-01/owner-test-build07.md`.
`client-install-020` с `enable_map_drive=true` установлен только в research
copy; `owner-test/owner-capture-070` пуст и готов для build07, pool закреплён в
`owner-test/map-drive-pool-060.json`. Bind smoke build07 на `20124/20126`
прошёл; receipt — `owner-test/map-drive-smoke-071.json`, smoke-процесс остановлен.
Единственный следующий шаг — owner запускает один build07 capture, входит на
MS-1, проверяет HUD и нормально выходит; fire/move/sniper пока не трогать.

## Результат карточки

**PASS_DOMAIN_BATTLE_PREPARATION_LOADOUT** в изолированной canonical и shared
legacy сборке. Перед серверным PREBATTLE и перед ordinary `drive_join` gateway
теперь строит typed `BattlePreparation` только после проверки authenticated
`VehicleSeed`, а затем exact server-owned profile/compatibility/manifest/native
ammo inputs. Результат сохраняется на `Session` для конкретного поколения
арены; при cancel/return он очищается.

Старый первый вариант этой карточки был сохранён как
`local/evidence/20261006-battle-shooting-loadout-route/attempt-01/result.json`.
Он получил `FAIL_ROUTE_REVIEW`: projection собирала данные из literals, не
читала профиль, и была подключена только к старому PREBATTLE пути. Код не
выдавался за принятый результат. После исправления добавлен
`attempt-02/review.json` с точным восстановлением before SHA, а текущая
реализация прошла обе дороги.

## VERIFIED

- `profile-input.json`: 1877 bytes, SHA256
  `2610dbd9ee64a12852986def336da057326f14a3289dda43eaae616286998d2d`;
  из него берётся owned MS-1 и ammunition count `20`.
- `compatibility.json`: 1603 bytes, SHA256
  `825a7e7024993c83b132499fe6f383b233ac288049bb77ca94b5407430f8d4d3`;
  из него берётся vehicle/shell mapping и mounted turret `5891`/gun `5892`.
- `manifest.json`: 15490 bytes, SHA256
  `ea967805376908e939fa691bb3bbc51e72253162aff98732bd753762eec35718`;
  он должен указывать native ammo export размером `7683`, SHA256
  `683daac81143a9d7edfbe671870ba163db088c54f5101fa52e077f596ebbfc74`.
- Native export проверяет MS-1 inventory `1`, vehicle type `3329`, turret
  `5891`, gun `5892`, capacity `96` и совместимый AP shell `2570`; затем общий
  `battle::loadout::validate` повторяет vehicle/turret/gun/shell/count guards.
- Legacy identity и immutable state hash проверяются через существующий
  `VehicleSeed::validate_session`; отдельная `game.account.v1` assertion не
  фабрикуется и не подменяет инфраструктурный owner boundary.
- Diagnostic `BATTLE_LOADOUT_DOMAIN_READY` явно содержит
  `native_event=false`, `native_packet=false`, `hud=false`,
  `ammo_mutation=false`, `fire_enabled=false`. Это серверный лог доменного
  gate, не client HUD и не native compatibility proof.

## Проверки

Команды:

```powershell
python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-battle-shooting-before-01
python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-battle-shooting-after-05
python -B -X utf8 server/build.py gateway --legacy --test --out local/build/server/gateway-battle-shooting-legacy-02
python -B -X utf8 server/check_layout.py
```

Результаты:

- canonical baseline: 307 tests PASS;
- canonical after: 312 tests PASS, fresh executable SHA256
  `cdbdbd9d53b7bdc46ecd70ac93d94bd80b8ca84a1273b2b7f1bdd0d37c370710`;
- legacy shared entrypoint: 311 tests PASS;
- source layout: PASS, 50 files;
- deployed `p01-wg-probe.exe` до/после: SHA256
  `daef0dde9e012beac4e0f363bf66b672ec4a154473be4b05b00cfe4cc0608c3b`;
  active process, backend, site, client and database не перезапускались.

Выбранные проверки в canonical log: чтение реальных profile inputs и binding
generation, все 15 semantic mutations mapping/count/revision, mutation/truncate/
extension checks exact source bytes, ordinary `drive_join` и PREBATTLE Session
commit. Полный receipt: `local/evidence/20261006-battle-shooting-loadout-route/result.json`.

## Maintenance preflight correction

Первый receipt в `local/evidence/20261006-battle-shooting-maintenance-preflight-01/rejected-01/`
ошибочно принял отсутствие `restore.json` за незавершённый install. Для active
ordinary `client-install-016` это поле отсутствовало штатно. Ошибка исправлена:
37 research-файлов возвращены к сохранённым prior postrun SHA,
`repair016-result.json` и `mistaken-rollback016.json` сохранены. Original,
deployed gateway и supervisor не трогались.

Текущий audit — `NOT_READY_NATIVE_LOADOUT` с
`PASS_READ_ONLY_AUDIT` в
`local/evidence/20261006-battle-shooting-maintenance-preflight-01/result.json`.
Он подтверждает supervisor `109740`, identity `15772`, gateway `37248`, обычный
run `run-20261006T103155-7dfce0`, `native_wire_capture=false`, старый deployed
EXE и уже закрытый 345-пакетный capture без БК. Изолированная сборка не
развёрнута; plan017 после восстановления current016 не применять.

Повторный live run сейчас не является следующим действием: domain route не
отправляет native Avatar ammo event, а запуск старого EXE не проверит новую
реализацию. Сначала нужна offline-карточка native method/serializer/order по
клиенту #717 и сохранённым packets. Только после проверенной native реализации
снова планируется одно owner-driven окно; raw payload остаётся
`UNKNOWN_NOT_DECODED` до независимого decode evidence.

## Статусы и границы

`native_loadout_event`, `native_wire_decode`, `fire`, `reload ACK`, расход БК,
hit, damage, physics и второй игрок — **NOT_RUN**. Frozen capture
`local/evidence/20261006-battle-progress-loadout-capture-01/` не перезаписывался;
его `AMMO/LOADOUT/BATTLE/FIRE/SHOOT=0` остаётся фактом старого запуска, до
подключения этого route и без native semantic decode.

Данные native export подтверждают локальную совместимость модулей/ёмкости, но
не подтверждают, что клиент уже получил Avatar ammunition event. Exact SHA —
целостность/версия, не криптографическая сетевая аутентификация. Абсолютный
путь native export закреплён старым test_lab manifest; перенос контента требует
отдельной карточки provenance.

## Откат

Удалить `server/gateway/src/battle/preparation.rs`, убрать его объявление,
Session wiring/diagnostic marker и legacy include, удалить только новые
`local/evidence/20261006-battle-shooting-loadout-route/` и
`local/build/server/gateway-battle-shooting-*`. Восстановить изменённые source
по `source-before.json`; текущий deployed gateway, клиент, БД и frozen capture
не трогать.

## Единственный следующий шаг

Один bounded maintenance run с вручную выполненным владельцем действием:
запустить закреплённый client #717 с включённым local wire capture после
подготовки собственного gateway, войти в МС-1 и дождаться реального native
`AMMO/LOADOUT` event. Если payload не декодируется, сохранить raw bytes,
manifest и `UNKNOWN`; к fire/reload переходить только после настоящего
числового БК.


## P03E native fire/reload route (2026-10-07)

Эта карточка закрывает изолированный серверный срез до ручного owner-шага.
`method-tables.json` закрепляет `vehicle_shoot=0x88`,
`vehicle_replenishAmmo=0x89`, `updateVehicleAmmo=0x44`,
`updateVehicleGunReloadTime=0x46` и `updateVehicleSetting=0x40`;
`client__Avatar.json` показывает, что `PlayerAvatar.shoot` без
`__currShellsIdx` выходит до native вызова. Поэтому initial binding отправляет
`CURRENT_SHELLS=0` + compact descriptor `2570`, а затем все три MS-1 rows.

Серверный `battle/fire.rs` парсит только bounded zero-arg `0x88/0x89`,
клонирует state перед применением и коммитит его только после успешной
очереди callback. При принятом shot AP меняется `20 → 19`, reload получает
`2.5 s`; cooldown, no-ammo, malformed, unknown, mixed и очередь не меняют
state. `0x89` распознаётся и логируется, но остаётся
`domain_applied=false` без бесплатного ammo/economy mutation.
Projectile, hit, damage, physics, visibility, equipment и persistence в эту
карточку не входят.

Изолированные проверки: canonical `328` тестов PASS
(`local/build/server/gateway-battle-fire-reload-07/result.json`, EXE
`72dfc02beef4b3af645a98914634463d84a21abb6274a897eac6ba5d47e32ff`), legacy
`327` PASS (`local/build/server/gateway-battle-fire-reload-legacy-02/result.json`,
EXE `e1c05aed270e79d4a8ff25510619e0abd288f5e1718bf4fda68da189cbe9d127`),
`server/check_layout.py` PASS. Static and source receipts собраны в
`local/evidence/20261007-battle-fire-reload-01/`; owner client receipt пока
`NOT_RUN`.

Ограничение: исходный WG-клиент ещё не подтвердил фактический fire ACK,
callback order и HUD reload. Следующий один шаг — запустить подготовленный
owner handoff, сделать ровно один выстрел на MS-1, подождать reload и сохранить
скрин/capture; до этого native fire/reload нельзя называть owner-совместимым.

## P03E follow-up: initial reload latch (2026-10-07)

Первый owner capture на build07 дал `VERIFIED_OWNER_CAPTURE_NO_SHOT`: crypto
и bounded transport прошли, ammo-panel candidate найден в server→client
body `162`, но в client→server frames нет `0x88` и gateway stdout не содержит
`BATTLE_SHOT_ACCEPTED` или `BATTLE_SHOT_REJECTED`. Владелец наблюдал
«орудие перезаряжается», `0,00` возле прицела и неизменившийся AP. Это
**OBSERVED** симптом, а причина стала **VERIFIED_STATIC + INFERRED_RUNTIME**:
`PlayerAvatar.shoot()` проверяет `aim.isGunReload()` и выходит до
`base.vehicle_shoot()`, а initial binding ещё не вызывал
`updateVehicleGunReloadTime`.

Исправленный codec отправляет после `CURRENT_SHELLS=0/2570` bounded
`0x13 0x46` callback с vehicle entity `0x09100003`, `timeLeft=0.0` и
`baseTime=2.5`. Новые reliable body sizes: PREBATTLE `105`, map-drive
binding `176`. Это сбрасывает клиентскую reload latch, но не делает сам
выстрел доверенным: server-owned state по-прежнему единственный источник
AP/reload, а owner fire receipt остаётся **NOT_RUN** до следующего прогона.

Изолированная проверка после фикса: canonical build08 — `329` tests PASS,
EXE `b70c73af9cc0060343e51202bf959326d0a584ce37b20a29ad3b4fe253085727`;
legacy build03 — `328` PASS, EXE
`034277a63a55340f21e6604081dfef51d35258e1431307648b992663f5b4fafd`;
layout — `PASS_SERVER_SOURCE_LAYOUT`. Deployed gateway SHA не изменён.
Первый ручной отрицательный прогон сохранён в
`local/evidence/20261007-battle-fire-reload-01/owner-test/owner-attempt-01-observation.json`;
следующий шаг — свежий build08 capture и ровно один выстрел MS-1.

## P03E owner acceptance: fire/reload/consumption (2026-10-07)

Build09 прошёл полный isolated suite и owner run. Владелец сделал пять
выстрелов в одном MS-1 session; gateway зафиксировал server-owned остаток
AP `19,18,17,16,15`, а между ними пять `BATTLE_RELOAD_COMPLETE` callbacks
с `updateVehicleGunReloadTime(0x46, timeLeft=0.0, baseTime=2.5)`. Визуально
владелец подтвердил: «сделал 5 выстрелов, все прошли нормально».

Свежий capture `owner-capture-fire-reload-03` содержит `671` packet files,
`667` bounded channel frames, `parse_errors=[]`, initial binding `176` байт
и пять server callback bodies по `25` байт для AP/reload. Gateway stdout
сохраняет последовательности `51/79`, `87/113`, `118/145`, `151/177`,
`182/209` (shot/completion). Owner receipt:
`local/evidence/20261007-battle-fire-reload-01/owner-test/owner-acceptance-fire-reload-03.json`.

Статус P03E: **PASS_OWNER_NATIVE_FIRE_RELOAD_CONSUMPTION**. Это не
подтверждение projectile, hit, damage, physics, visibility, equipment или
persistence; эти темы остаются **NOT_RUN** и должны идти отдельной карточкой.
