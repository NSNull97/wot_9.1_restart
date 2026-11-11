# CONTENT-0 2.5: диапазон угла возвышения в `gunAnglesPacked`

Статический разбор исследовательской копии клиента #717 (байткод и PE не исполнялись).

## Как клиент принимает угол возвышения

- VERIFIED: `res/scripts/client/Vehicle.pyc` (SHA256 `b81d08ca14092bb8912adb2eff20325c3dd23424868bc03164cfe6b8da50463c`),
  `Vehicle.set_gunAnglesPacked`: `decodeGunAngles(self.gunAnglesPacked, self.typeDescriptor.gun['pitchLimits']['absolute'])`,
  затем `filter.syncGunAngles(yaw, pitch)`.
- VERIFIED: `res/scripts/common/gun_rotation_shared.pyc` (SHA256 `eaefc6385bdafed505254c437271feb273b45179322e099d2bd289ee9fcb3de9`):
  младшие 6 бит — угол возвышения. Кодирование `t=clamp((a-min)/(max-min),0,1)`, `int(round(63*t)) & 63`;
  декодирование `min + code/63*(max-min)`.
- VERIFIED (`local/evidence/20261016-p06t-aim01/result.json`, SHA256 `ad09cc66372a8ba03405128ea1f0a17c4909d622d13ed75ad7f469784e103733`, `vehicles.pyc._readGunPitchExtraLimits`):
  `absolute` начинается с `basic` и расширяется `min`/`max` по `front` и `back`, то есть это объединение трёх диапазонов.
  `SourceEnvelope::from_source` в шлюзе считает то же объединение.

Вывод (INFERRED, сильный): клиент квантует угол по `absolute`. Шлюз квантовал по `basic`, поэтому
машины с расширенными front/back секторами отказывались явно. Теперь `aim::wire_pitch_range` для
сгенерированных машин возвращает `envelope.absolute()`, `wire::packed_angles_for` квантует по нему,
а проверка допустимого угла для текущего направления башни (`pitch_limits_for`) остаётся авторитетной.
Пять закреплённых вручную машин не меняются (у них `absolute == basic`).

Нативная проверка на двух клиентах: NOT_RUN.

## Перекрытие front/back секторов (три отказа `AIM_ENVELOPE_UNSUPPORTED`)

`france:AMX_13_90` (front 75°, back 105°), `france:AMX_50_100` и `france:AMX_M4_1945` (front 120°, back 30°)
при переходе по умолчанию 0.4 рад дают `front + back + 2*transition > pi`. Их отклоняют
`aim_envelope_supported` и `SourceEnvelope::validate`, а не диапазон wire. Это изменение их **не** допускает.

VERIFIED (статический дизассемблер окна PE `0x6a6490`, 279 байт, SHA256 `854585035d2f3360bd1bed8661ab1f4b8fb2d56fdc5235e458adec0509b32eb4`): нативная
`wg_calcGunPitchLimits` проверяет по порядку front-сектор, переход front, back-сектор, переход back,
затем basic. При перекрытии побеждает front; отказа в нативном коде нет. В `SourceEnvelope::pitch_limits`
порядок тот же. Чтобы допустить эти три машины, нужно снять запрет перекрытия в генераторе и в `validate`.
Это отдельное решение; нативная проверка NOT_RUN. Как это делал исторический сервер — UNKNOWN.
