# P03J: native map-drive gun rotation and tracer callbacks

Дата: 2026-10-08.

## Цель

Закрыть узкий runtime-разрыв в авторизованном `legacy091-map-drive`: после
получения штатного `Avatar.updateTargetingInfo` клиент должен иметь gun-rotator,
сервер должен принимать только bounded native aim intents и сохранять их в
серверной арене, а принятый `vehicle_shoot` должен публиковать зафиксированный
shoot/tracer callback и завершать tracer по серверным часам.

## Наблюдение до изменения

`local/server/run-20261008T090312-d3bac3/gateway.stdout.log` содержит
`MAP_DRIVE_UNSUPPORTED` для `vehicle_changeSetting`/`autoAim`,
`MAP_DRIVE_BOUND ... body_bytes=176` (ammo уже доставляется) и 20
`BATTLE_SHOT_ACCEPTED ... projectile=NOT_RUN`. Владелец наблюдает неподвижную
башню/прицел и отсутствие трассеров. Это OBSERVED runtime; native callback
приёмка именно новых bytes ещё NOT_RUN.

## Изменение

1. Добавить в map-drive binding штатный `updateTargetingInfo` с параметрами
   pinned MS-1 rotator/aim profile.
2. Parse `0x8e/0x8f/0x0f` в typed aim intent с теми же bounded guards; не
   принимать клиентские координаты как authoritative.
3. Сохранять intent/angles только в server-owned `drive::Arena` и публиковать
   packed angle property вместе с own vehicle update.
4. При accepted shot добавить native shooting + `Avatar.showTracer` bytes;
   сохранять bounded projectile deadline и публиковать `stopTracer` только
   после server monotonic deadline. Fire/reload/ammo ownership остаются
   server-side.

## Границы

Профиль остаётся pinned MS-1 test_lab. Попадание, collision, damage, visibility,
экономика и второй клиент не добавляются.

## Проверки

Targeted Rust tests for drive wire, aim lifecycle, fire callbacks, compound fire
prefix handling and session atomicity; the pinned gateway build passed **372/372**
tests. Isolated build receipt: `local/build/server/gateway-p03j-native-aim-tracer-07/`;
deployed executable SHA-256 is
`1fa92e383d80f1118b4ac95dc7b3d08b5ebbfcf69446f851bfb59832cdcb5b45`.

Runtime attempt `local/evidence/20261008-p03j-native-aim-tracer-06/` is
**PASS_OBSERVED_NATIVE_FIRE_TRACER_RELOAD**: the visible client completed with
exit code 0 after 460.6 s, the gateway accepted 8 shots (`20 -> 12`), emitted
8 server-owned reload completions (`time_left=0.0`, `base_time=2.5`) and 8
`Avatar.stopTracer` callbacks, with zero `INTERACTIVE_REJECT` lines. The client
also sent compound fire+aim bodies; the bounded fire-prefix split handled them.
The owner reports the latest visible run is now okay. Runtime hit/damage and
two-client visibility remain outside this card and **NOT_RUN**.
