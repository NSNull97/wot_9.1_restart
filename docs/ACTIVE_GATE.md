# Текущие ворота: SPAWN-15 — команды на своих базах, бой до 30 машин (2026-10-28)

Ветка `codex/spawn-15-team-bases` на main `75a9437`. План и итог — [SPAWN15_TEAM_BASES](plans/SPAWN15_TEAM_BASES.md).

| Проверка | Статус |
|---|---|
| Ключа `spawn_policy` нет, `battle_players` ≤ 6 → прежний путь | PASS (FAIL-набор равен `75a9437`: 83 = 83) |
| Формации всех карт реестра, отказ 16-го, порча таблицы | PASS (unit, `spawn15_formation.py check`) |
| Кодирование 2/6/15/30: ID/алиасы, ростер, позиции, binding | PASS (unit) |
| Оседание 30 в Jolt: Прохоровка, Малиновка; Карелия по местам | PASS |
| Бенч release 30 | Прохоровка 1/2 × 30 PASS; Малиновка 2 × 30 — 1 из 2 FAIL (пики шага шлюза, причина UNKNOWN) |
| Канонический gate в `D:/WoT_9.1_Server` | NOT_RUN |
| Native: спавн у баз с 2–4 клиентами | NOT_RUN (владелец); бой 15×15 — после BOT-01 |

Включение: `"spawn_policy": "spawn15-team-base-formation-v1"` в `gateway.json`. Откат — убрать ключ.

## Предыдущая карточка

ARENA-01 — несколько арен в шлюзе: принята владельцем на стенде -11 (2026-10-27), в main `75a9437`.
План — [ARENA01_MULTI_ARENA](plans/ARENA01_MULTI_ARENA.md).

GW-01 — ёмкость Gateway: принята владельцем на стенде -10 (2026-10-27), в main `2da4baa`.
План — [GW01_GATEWAY_CAPACITY](plans/GW01_GATEWAY_CAPACITY.md). Более ранние карточки — в истории git.
