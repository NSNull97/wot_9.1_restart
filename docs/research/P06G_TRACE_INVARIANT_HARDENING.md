# P06G server-owned impact trace invariant hardening

Дата: 2026-10-09. Карточка продолжает P06C flight-only boundary и не
утверждает native collision, penetration или damage.

`Trace::launch` теперь ищет admission того же `shot_id` и требует совпадения
`projectile.slot` с `shooter_slot` и launch `server_tick` с admission tick.
Нарушение отклоняется до добавления события. Так серверный trace не может
связать снаряд с чужим актором или скрыто сдвинуть его во времени.

В `World` добавлены проверки same-tick и staggered (90 ms) запусков двух
акторов, полный 40-shot cadence с range terminals, непрерывный event order и
полный снимок published state для ошибочных `apply` и `advance`. Прямой
невалидный launch также проверяется на отсутствие частичной записи.

Результат: **PASS_TRACE_INVARIANT_HARDENING**, gateway Rust suite **385/385
PASS**, source layout **PASS_SERVER_SOURCE_LAYOUT** (59 файлов, 22
перемещения). Профиль остаётся `ms1_ap_2570`; runtime solver не добавлен.

Остаются `UNKNOWN/NOT_RUN`: BSP2 и runtime axes, server intersection,
material/normal/thickness, penetration, damage, HP/module/crew, replay и
client/server equivalence. Следующий шаг требует owner-gated native capture;
до него synthetic hit/damage rows не создаются.
