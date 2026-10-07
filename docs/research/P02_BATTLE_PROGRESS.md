# P02/P03: следующий проверяемый срез к полноценному бою

Дата: 2026-10-06, Asia/Yekaterinburg. Ветка продолжает игровую арену
параллельно с архитектурным разделением инфраструктуры.

## Что уже подтверждено

VERIFIED — native арена и движение.

- local/evidence/20261005-p02-arena-entry/data/verify-vehicle03-final-01/arena-vehicle-native-verification.json имеет status=PASS, но full_arena=NOT_RUN: один авторизованный Account → Avatar → геометрия → собственный МС-1. Визуальный результат — родной HUD и экран ожидания.
- local/evidence/20261005-p02-arena-ready/data/verify-ready01-final-02/arena-ready-native-verification.json имеет status=PASS, full_arena=NOT_RUN: реальный setClientReady, родной PREBATTLE/countdown и штатное завершение. Active battle, передача боекомплекта, движение/физика, стрельба/попадание и второй игрок этим запуском не приняты.
- local/evidence/20261005-p02-arena-movement/data/verify-move02-final-01/arena-movement-native-verification.json имеет status=PASS, full_arena=NOT_RUN: один native move/stop и authoritative lab-публикация позиции. Это не историческая физика и не игровой бой.

VERIFIED — текущая блокирующая неисправность.

local/evidence/20261006-manual-battle-button/manual-result-01/result.json сохраняет full_manual_lifecycle=FAIL_TWO_DISCONNECTS; следующий шаг в самом receipt — измеренный sniper-camera contract и чистый return/re-entry.
local/evidence/20261006-sniper-camera/scoped-review-02/result.json имеет full_card_acceptance=PARTIAL; второй clean warm return/re-entry не выполнен, а shooting оставлена NOT_RUN.

VERIFIED — боекомплект пока только ангарный.

docs/research/P02_MS1_AMMO.md и native fixture подтверждают МС-1
(20 AP), но явно оставляют бой, расход/пополнение/покупку снарядов
NOT_RUN; avatar_ammunition_transfer=NOT_RUN.

## Выполненный срез этой карточки

Запущена только изолированная canonical gateway сборка с тестами:

    python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-battle-contract-01
    python -B -X utf8 local/evidence/20261006-battle-progress-arena-contract/contract_audit.py

Receipt:
local/evidence/20261006-battle-progress-arena-contract/result.json.

Результат PASS_ARENA_LIFECYCLE_CONTRACT_GUARDS_ONLY:

- 291 Rust tests и offline build прошли в свежем output;
- state machine явно разделяет account/base/space/vehicle/ready/movement;
- readiness валидирует измеренный compound и не объявляет battle started;
- неподдержанные Avatar-команды получают transport ACK без gameplay application;
- движение и публикация позиции отделены от боевой симуляции;
- source hashes до/после audit совпали;
- deployed gateway hash не заменён.

В evidence сохранён и первый исправленный запуск:
local/evidence/20261006-battle-progress-arena-contract/attempt-01/result.json
— это честный FAIL проверки из-за ошибочного пути статического маркера, не
runtime/совместимость FAIL; он не перезаписывался.

## Что не объявляется готовым

native_client, firing_damage, second_player, battle_transition — NOT_RUN.
Наличие native ACK или успешной поездки не доказывает выстрел, попадание,
урон, перезарядку, расход снаряда или бой 15x15.

## Domain loadout gate (2026-10-06)

После повторного owner-report «в бою снова нет БК» добавлен отдельный
типизированный доменный gate
`server/gateway/src/battle/loadout.rs`. Он принимает только уже
аутентифицированную связку vehicle inventory → turret/gun → shell mapping и
положительный count; любая потеря identity, mapping, capacity или stack
заканчивается fail-closed. Модуль не содержит native byte encoder, packet ID,
HUD-вызовов или fire handler.

Receipt: `local/evidence/20261006-battle-progress-loadout-gate/result.json`,
`PASS_DOMAIN_LOADOUT_GATE`; изолированная компиляция и 11/11 тестов прошли. Это
проверяет только доменное состояние. Native Avatar loadout/ammo transfer и
совместимость провода по-прежнему `NOT_RUN`.

Подготовлен offline harness
`local/evidence/20261006-battle-progress-loadout-gate/capture_loadout_event.py`
и план `capture-plan.md`. Без закрытого native `capture.json` он возвращает
`NOT_RUN_NO_CAPTURE`; backend/client не запускает. После отдельной записи harness
проверит только bounded manifest, размеры и SHA packet-файлов, оставляя
`loadout_event=UNKNOWN_NOT_DECODED` до независимого native разбора.

Статический анализ оригинального PlayerAvatar.shoot зафиксирован в
docs/research/PROTOCOL_MAP.md, но входной envelope, порядок, authority и
ACK semantics пока UNKNOWN. Поэтому серверный fire handler сейчас не
добавляется: это было бы угадывание протокола.

## Frozen native capture receipt: loadout/ammo route (2026-10-06)

Выполнен один bounded native capture на свежем run-каталоге
`local/server/run-20261006T102148-d2dd40`. Receipt
`local/evidence/20261006-battle-progress-loadout-capture-01/summary.json`
имеет `status=PASS_CAPTURE_FINALIZED_NO_AMMO_ROUTE`: 345 raw-пакетов,
`packet_hash_integrity=PASS`, manifest SHA256
`24fdd6c87695b698d64b3d39ee8a7eddf7e95bdcdca5fc43c899320382026e33`,
`packets.jsonl` SHA256
`af3e779ba0be4a625d2b81bc5fc97c4c147dc544ee49d7fa4b7a7d99aea335fe`.

Gateway markers подтверждают только `MAP_DRIVE_ANNOUNCED`,
`MAP_DRIVE_VEHICLE_CREATED`, `MAP_DRIVE_BOUND` и `MAP_DRIVE_WORKER_READY` по
одному. `AMMO`, `LOADOUT`, `BATTLE`, `FIRE` и `SHOOT` — по нулю. Наблюдение
владельца: БК не появился, выстрел не выполнялся. Offline harness сохранил
только integrity candidates (`PASS_CAPTURE_INTEGRITY_CANDIDATES_ONLY`);
`native_loadout_decode`, `native_wire_compatibility` и server reject остаются
`NOT_RUN`/`NOT_OBSERVED`. Это не доказательство отсутствия пакетов в
протоколе: native payload пока не декодирован.

После capture backend штатно восстановлен в обычный режим:
`status=RUNNING`, `native_wire_capture=false`, сайт на loopback `3091`;
`client_changed=false`, `deployed_gateway_replaced=false`. Capture и его raw
manifest заморожены, повторный запуск в этой карточке не выполнялся.

## Изменённые файлы

- добавлены docs/plans/P02_BATTLE_PROGRESS.md;
- добавлен этот отчёт;
- добавлен новый evidence local/evidence/20261006-battle-progress-arena-contract/;
- добавлен frozen capture evidence
  local/evidence/20261006-battle-progress-loadout-capture-01/;
- product/server/client/site/database не изменялись.

## Откат

Вернуть этот отчёт и план к их исходным SHA256 перед receipt
(`D370A07E70861523CBF644C21410532DD1DE159DC5B184745A3DAB3C9D2666D8` и
`3094952171D7124BCBE4212B3E353F80BC48BDFF93754B87EAAEEE2C53A5299C`), либо
удалить только эти два docs-файла, если карточка целиком отзывается. Frozen
raw capture не перезаписывать и не удалять при откате документации. Это не
касается deployed gateway, текущего backend/site, клиентских установок и БД.

## Единственный следующий шаг

Единственный следующий шаг — подключить и проверить серверный battle-loadout
route через уже изолированный fail-closed domain gate, не угадывая native
packet. После этого нужен ещё один отдельный native capture для проверки
появления `AMMO/LOADOUT/BATTLE`; до доказанного события PlayerAvatar.shoot,
стрельбу и урон не реализовывать.

