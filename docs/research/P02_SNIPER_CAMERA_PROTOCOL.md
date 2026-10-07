# P02: смена камеры без разрыва native channel

Дата: 2026-10-06, Asia/Yekaterinburg.
Статус: **PARTIAL_ACCEPTANCE_NATIVE_CAMERA_DRIVE_REENTRY**.
Код/290 tests/build приняты; два входа и14 camera changes прошли. Полная
строгая ручная приёмка не закрыта: второй warm return не выполнен, ранний
nonzero Move→6 после fix2 не наблюдался. Старые FAIL сохранены.
`S=local/evidence/20261006-sniper-camera/`.

## Область и исходный сбой

Настоящая Flash-кнопка принята дважды отдельной карточкой
`P02_MANUAL_BATTLE_BUTTON.md`. Владелец подтвердил движение, повороты и задний
ход; круиз — OBSERVED_OWNER_FEEDBACK. Native flags ступеней установлены;
конкретная ступень в действиях владельца и применение частичной скорости
UNKNOWN, детали в `P02_DRIVE_LIMITATIONS.md`.
Остановка на подъёме с последующим возобновлением движения — OBSERVED_DEFECT
текущей физики test_lab. Эти наблюдения не доказывают историческую физику.

Переключение снайперского прицела дважды разорвало сессию. Оба неуспешных
ручных заезда и Minimap traceback после первого disconnect сохранены.
Первый отказ session4: sequence115/body13B; session5: sequence1740/body17B.
Длина body включает5B `[1, session_token]`. Последующие5B отказы — heartbeat
после застрявшей RX последовательности, не неизвестный пятибайтный RPC.
Содержание прежнего12B application message session5 остаётся UNKNOWN.

## Доказанный контракт

VERIFIED: закрытый ручной повтор на ordinary клиенте016 и build10:
`local/server/run-20261006T051849-cbba00`. Владелец вошёл на карту, включил
снайперский прицел, дождался disconnect и закрыл EXE. Отрицательный результат
**FAIL_REPRO_SNIPER_DISCONNECT** не переписывается последующим исправлением.

`S/capture-review-01/result.json`, SHA256
`6d789e499586ec62655d4edfe424cf30b4fe4cae73965bf0826cb34b7c273fc4`:
1704 raw packets,1700 decoded channel frames,0 decode errors,0 piggybacks,
capture budget не достигнут. Сырые файлы сверены по размеру/хешу дважды;
ключи, учётные данные и session token в отчёты не копировались.

| Пакет | Reliable sequence | Token-stripped application | Значение |
|---|---:|---|---|
|1618|527|`8a010001`|Предшествующая команда движения|
|1620|528|`8d05000200000000`|`0x8d`, VAR16len5, setting2, INT32LE0|
|1622|529|Пустое приложение|Только5B служебного envelope|
|1670|551|`8d05000201000000`|Тот же setting2, INT32LE1|

Пакет1620: capture152.0360936s, flags0x458, cumulativeACK534;
SHA256 `64d7f1472001334ba1f3c09c922de592e81be4c4dc28050adfdd1ce17d49df83`.
Gateway log, строка2130: первый `ordinary map-drive contract`.
Пакет1670 SHA256
`0792e099ad28e433cb7ae7ed010c7bfe1da5933f71b6b9fa3a7f40737d3b820f`.
Подробности закрытого клиентского trace — `S/capture-review-01/closed-trace-addendum.json`:
653rows, SHA256 `e55f8417811e4b4031924f2a12425297daccb6f9d9016999a0546aafab14fee6`,
disconnect строка595, fini653, Python exceptions0.

VERIFIED_STATIC: native Avatar Base `vehicle_changeSetting(UINT8,INT32)`:
exposed index7, native message0x8d. Enum original `VEHICLE_SETTING`:
`AUTOROTATION_ENABLED=2`. `AvatarInputHandler.onControlModeChanged` вызывает
`PlayerAvatar.enableOwnVehicleAutorotation`; оригинальный SniperControlMode
МС-1 предпочитает False, поскольку оба chassis имеют
`rotationIsAroundCenter=False`; выход восстанавливает предыдущую настройку.
Точные disassembly offsets/source lines и свежие original/research hashes:
`S/static-review-01/result.json`, SHA256
`adf43c4859e1c8cfe7b6a93ca4fa658477cf5c61311b51e4d2d441bf5f420653`.
Следовательно, identity setting2 в новом пакете VERIFIED совместно по raw и
original schema; имя не выводится из одной длины пакета.

VERIFIED_CODE: parser раньше принимал0x8d лишь внутри readiness compound33B.
Standalone отсутствовал. `receive` clone/commit откатывал вместе с ошибкой
парсера ACK и ожидаемый RX; следующие последовательности отклонялись как gap,
8 неподтверждённых server publications заполняли окно и вызывали RequestWindow.
Новый8B пакет подтверждает первую причину этого каскада. Minimap ошибка первого
заезда после disconnect остаётся отдельным наблюдением; причинность INFERRED.

## Узкое изменение

В `tools/wg_probe/src/map_drive_world091.rs` добавлен typed
`UnsupportedCameraAutorotation(bool)`: ровно5 argument bytes, setting2 и
INT32LE0|1. Другие настройки, значения, длины, неизвестные suffix и более16
методов в envelope отвергаются целиком. Shell/equipment/reload не включены.

В `gateway091.rs` сохраняются Driving/session/identity guards и общий bounded
counter500000. Лог `MAP_DRIVE_CAMERA_PREFERENCE` явно указывает
`transport_accepted=true`, `domain_applied=false`,
`physics_setting_changed=false`, `policy=test_lab_keyboard_only`.
Протокол подтверждает распознанный вызов, но тестовая физика пока не реализует
поворот корпуса вслед за орудием. Локальное переключение камеры остаётся родным.
Изменения worker, параметров физики и публикации позиции отсутствуют.

Shared reader также валидирует позднее восстановление настройки в существующем
retired Avatar drain до warm09: STOP, поколение, бюджет32 и отсутствие pending
worker обязательны. Такой пакет отбрасывается без возврата полномочий старому
Avatar. После warm09 или при mismatch он не становится Account командой.

## Закрытый повтор fix1 и второе исправление

`S/fixed-review-01/result.json`, SHA256
`ef571e10db76cfef074673be1afe794710e33fe385c644dbf2652305f8fde605`:
5721packets/5717frames,0 decode errors, закрытый native trace без Python errors.
Первая поездка:8 camera changes сопоставлены с raw0x8d/setting2/0|1 и server
ACK=client_sequence+1;1719/1719 publications совпали с worker F32 и ACKed;
штатный native_leaveArena и warm sync. Вторая загрузка — **FAIL_REPRO_SECOND_ENTRY**;
владелец сообщил выброс. Первая camera правка принимается лишь в этом scope.

VERIFIED: первый отказ второго входа — gateway7400, packet5663, clientseq1864,
app `8a01000106`: Move(flags1) перед correction6. Footer cumulative1863 уже
ACKs binding1862. PacketSHA256
`ab29060925c50c0537100042156490f3db8b22560df250032f532e5510b3a066`.
Сервер проверял correction_acks==0 до достижения6 в цикле. Это отказ раньше
camera RPC, а не подтверждение гипотезы «владелец слишком рано включил прицел».
Пакет5664 побайтно повторяет binding1862, server RX сохраняет1864: ошибка
откатывала и уже валидный footer ACK. Причина/PE linkage:
`S/second-entry-review-01/result.json`, SHA256
`1cddfcb23d349ae1201296f98f8ce1730662b94732bebfd459a09c4533827fcb`.

Fix2 учитывает exact correction6 в том же полностью валидированном compound
при первом ненулевом Move. Сам6 по-прежнему требует настоящего force ACK и
bounded count. Неверный ACK/отсутствующий6/неизвестный suffix/poison piggyback
откатывает и input, и транспортный state. Worker не вызывается до полного
receive commit. Порядок методов сохраняется; cross-frame buffering и
подставного binding нет. Старые лабораторные probe policy не расширяются.
Новый regression использует exact5B capture literal; изменён старый ordinary
тест, который ошибочно требовал отказ при этом реальном валидном порядке.

## Закрытый повтор fix2: результат и незакрытые условия

Ручной клиент51136, trace `native-51136-1791266247767.jsonl`, server capture
`run-20261006T055352-ff7b06`. `S/scoped-review-02/result.json`, SHA256
`7114f3abf73fb40fcbdc99a8327cf39f28d84010ddcea14317f422b389592ba9`:
1864packets/1860frames,0 decode errors;14 camera changes (6+8) сопоставлены
с exact native bytes и serverACK=seq+1. Оба manual Flash clicks открыли Avatar.
Неожиданных disconnect/reject/worker failures/Python exceptions0.
542/542 publications совпали с authoritative worker F32;538 ACKed,
4 последних606…609 не ACKed и явно retired_pending4 при native client quit.

Первый native_leaveArena→reset→enable→warm100/300/600→ангар→повторный вход
подтверждён полностью. Во второй арене клиент закрыл соединение штатным0b00
без wire native_leaveArena/второго warm return. Это не засчитывается как второй
возврат. Строгий `S/fixed-review-02/result.json` сохраняет FAIL условия двух
чистых возвратов; supplementary scope не переписывает его в PASS.

Оба первых correction compounds содержали `8a01000006` (Move0→6).
Ненулевой Move→первый6 после исправления **NOT_OBSERVED**; exact прежний5B
случай проверен captured-literal regression, но новое native возникновение
не имитировалось. Полная ручная приёмка остаётся PARTIAL.

Теперь действительно наблюдались12B camera+movement compounds:
clientseq383 packet1184 `8a0100018d05000200000000`, SHA256
`3c6347f8e8eca1ef899c544f824102e1ec91f5c7f0668c456be29c03e4eefce2`;
clientseq436 packet1341 `8d050002010000008a010001`, SHA256
`77e6eff63fdd84bd95ab70ec01793d4148b79ac55f05c47b6884235eef039db8`.
Они ACKed/committed, но не восстанавливают identity старого12B отказа session5.
Supplement reader сначала ошибочно ожидал чистые steering-only envelopes;
его harness failure сохранён отдельно, исправлен только reader с учётом
compound2→10→8 и4→0. Продукт при этом не менялся.

## Проверки и запуск

| Проверка | Результат | Evidence |
|---|---|---|
| Original schema/camera/resources,9 hash bindings | PASS_STATIC_REVIEW_ONLY | `S/static-review-01/` |
| Реальный повтор до исправления | FAIL_REPRO_SNIPER_DISCONNECT | `S/capture-review-01/` |
| Offline Rust suite |288 PASS,0 failed|`S/build-01/test.stdout.log`|
| Fix1 offline locked build |PASS|`S/build-01/build.command.json`, `result.json`|
| Fix2 Rust suite/build |290 PASS,0 failed / PASS|`S/build-02/`|
| Fix2 independent code/source review |PASS,0 blockers|`S/code-review-02/result.json`|
| Fix1 native camera |8/8 PASS_SCOPED|`S/fixed-review-01/`|
| Fix1 полный второй вход |FAIL_REPRO_SECOND_ENTRY|Тот же закрытый capture|
| Fix2 два native входа +14 camera changes |PASS_SCOPED|`S/scoped-review-02/`|
| Fix2 строгий полный ручной цикл |PARTIAL; исходный reader FAIL сохранён|Второй warm return NOT_RUN;4 tail messages не ACKed|
| Ранний nonzero Move→первый6 после fix2 |NOT_OBSERVED_NATIVE; captured regression PASS|`S/build-02/`, scoped supplement|
| Историческая физика/плавность/стрельба/урон/двое |NOT_RUN / за рамками|Не выдаются за этот PASS|

Новые regression tests проверяют exact captured literals, все неподдерживаемые
setting IDs, bad INT32/length, truncation/suffix,16-method limit, ACK освобождение
реально отправленного окна8, следующую heartbeat последовательность, replay/
changed replay, wrong token/future ACK/gap, атомарность piggyback tree, фазы,
counter и retired drain. Compound camera+movement покрыт unit fixtures;
в закрытом fix2 capture оба порядка также наблюдались на настоящем клиенте
(seq383/436, exact bytes приведены выше). Nonzero Move→первый6 после fix2
остаётся NOT_OBSERVED и не подменяется этим наблюдением.

Фактически выполненная сборка:

```powershell
python -B -X utf8 local/evidence/20261006-sniper-camera/build_review.py
```

Это одноразовый evidence runner с fresh output и проверкой закрытого mutex,
STOPPED службы и before hash. При повторе он намеренно откажет от перезаписи.
Точные Cargo argv, env/toolchain pins, source snapshot и полный вывод сохранены
в `S/build-01/`. Новая EXE SHA256
`71b5e9de0af56aab433199ace0e508f69bfa9f8a6d0d738ece620bc776d63e61`.

Fix2 выполнен отдельным одноразовым runner `S/build_review02.py`; frozen
snapshot `S/build-02/`. Финальная candidate EXE SHA256
`daef0dde9e012beac4e0f363bf66b672ec4a154473be4b05b00cfe4cc0608c3b`.
Независимый diff review `S/code-review-02/result.json`, SHA256
`85619f5ba7a7bc25cdf192dd1a972e091eb24ca84399658e695ca640dbb1db78`:
88/88 sources совпадают с manifest/current; относительно fix1 изменён только
gateway, Binding/transport/worker/pool/legacy probe без изменений. Все16
pinned worker artifacts и оба map config хешами прежние. Review не заменяет
native test.

Обычный запуск из корня:

```powershell
python -B -X utf8 tools/local_server.py status --config local/server/service.json
python -B -X utf8 tools/local_server.py start --config local/server/service.json --map-drive local/server/map-drive/pool.json
```

Если служба уже RUNNING, повторный start закономерно отказывает; status показывает
фактические процессы. Для закрытого диагностического повтора backend запускался
с дополнительными `--capture --capture-profile map-drive-phase2-v1`.
Ни клиентский пакет016, ни сайт не требуют обновления для этой серверной правки.

После закрытого аудита диагностическая служба остановлена и поднят ordinary
backend без capture: `run-20261006T061506-d7a679`. Клиент016 прежний, game
закрыта, сайт имеет прежнего внешнего владельца. Итоговый runtime/source
receipt — `S/final-state-02/result.json`, SHA256
`59f1d6c872f5904ac11357770428e3058e8bf1f0cb5c43d566e968eba0e5d3dc`:
88 sources,34 client immutable files,43 worker/map records совпали хешами;
ordinary RUNNING/captureFalse, client closed/mutex свободен, health200.
Полный inventory клиента/БД не повторялся: это scoped preservation PASS.
Reader01 ошибочно требовал loopback
от уже существующего внешнего сайта3091 (он слушает0.0.0.0); harness FAIL
сохранён в `S/final-state-01/`. Исправлена только проверка reader: native
UDP20014/20016 и identity20020 остаются127.0.0.1, сайт не изменялся.
Дефекты pivot/частичного круиза и
отсутствующие разрушения описаны отдельно в `P02_DRIVE_LIMITATIONS.md`.

## Откат и следующий шаг

Только при закрытом EXE остановить own backend обычной командой stop.
Сверить before manifest и восстановить2 Rust sources и gateway EXE из
`S/build-baseline-01/`; затем ordinary start. Полная build snapshot также хранит
before EXE/source manifest в `S/build-01/`. Клиентский откат при необходимости:
`python -B -X utf8 tools/interactive_client.py rollback --out local/client-install-016`.
Original клиент не изменялся; повреждённые/неуспешные evidence сохраняются.

Единственный следующий рекомендуемый шаг разработки: отдельная ограниченная
диагностика разворота остановленного МС-1 с RPM/передачей/скоростями гусениц.
Незакрытые ручные protocol conditions перечислены выше и в MISSING_INPUTS;
этот отчёт не получает полного native PASS и не закрывает весь P02.
