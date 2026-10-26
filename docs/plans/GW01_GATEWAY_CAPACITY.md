# GW-01 — ёмкость Gateway отделена от размера боя

Ветка `codex/gw-01-gateway-capacity` от main `b31f691`. Основание:
[ADR-002](../decisions/ADR_ARCH01_TARGET.md) (Gateway: ёмкость = число соединений, цель ≥ 256),
[ARCH01_MIGRATION](ARCH01_MIGRATION.md) шаг 6, [текущее состояние](../research/ARCH01_CURRENT_STATE.md),
[FULL_TEST_PER_ACCOUNT_LOGIN](FULL_TEST_PER_ACCOUNT_LOGIN.md). Метки — как в AGENTS.

## Что есть сейчас (VERIFIED, `b31f691`)

- `Table { sessions, retirement, capacity }` — `server/gateway/src/shared/server.rs:80-81`.
  Для profile13 `capacity = config.battle_players` (2..6), для учебных комнат — `MAX_ACCOUNTS`
  (`server.rs:1361`). Лог `BOUND … capacity=` печатает размер арены `world.expected_actors()`
  (`server.rs:1443-1446`), а не ёмкость таблицы.
- Отказ по ёмкости: `Table::admissible` (`server.rs:627-635`) — `sessions.len() >= capacity` или
  `retired + sessions >= MAX_RETIRED (32)` → ошибка; вызывающий шлёт LoginReply **73**
  (`SERVER_NOT_READY`) до auth (`server.rs:1544-1546`) и после auth (`server.rs:1513-1515`,
  `SHARED_AUTH_REJECT reason=admission_or_world_capacity`).
- В profile13 вход **не** занимает место арены: `slot = 0`, `world.attach` не вызывается
  (`server.rs:1483`); место берётся в `attach_waiting_sessions` (`server.rs:1043-1088`) только для
  сессии с резервом текущего боя (`reservation*.battle == world.id`). Резерв ставит писатель Join
  (`profile13_dispatch*.rs`, `RequestLoss::Admit{battle:world.id}` и аналоги) — **без** ограничения
  числа резервов на бой. Старт боя требует `table.sessions.len() == world.expected_actors()`
  (`server.rs:1777-1779`; hold — `profile13_dispatch_hold.rs:39`).
  Итого «каждый вход занимает место арены» сегодня выражено как `capacity = battle_players` плюс
  условие старта «все сессии таблицы — в бою».
- Прочие пределы на пути 256 соединений: окно повторов `MAX_RETIRED=32` на 120 с
  (`session.rs:21-22`); общий бюджет датаграмм `DATAGRAMS_PER_SECOND=256`/с
  (`account/game_network.rs:7,128-132`); цикл читает **одну** датаграмму на сокет за итерацию и спит
  5 мс (`server.rs:1523-1529,1942`) — потолок ~200 датаграмм/с на сокет.
- Bridge (`web/src/game-adapter.mjs:543-563`): не более 60 входов/мин на процесс и 10/15 мин на e-mail,
  вход только для аккаунтов из `battle_service.accounts`.

## Решение

1. Конфиг шлюза `connection_capacity` (целое `battle_players..=256`; ключ отсутствует = прежнее
   поведение побайтно). Допустим только с `profile13_battle`; несовместим с `training_rooms` и
   `p08b_owner_battle_hold` (у них старт требует «все сессии в бою» — отказ конфигурации, а не тихая
   деградация).
2. `Table.capacity = connection_capacity`; новое поле `Table.arena_split = true`. Сессия ангара
   места арены не держит:
   - Join-резерв (`start`, `start_mixed`, `start_loss`) ставится, только если число сессий (живых и
     удержанных диспетчером) с резервом текущего боя `< world.expected_actors()`. Иначе Join ждёт
     (сессия остаётся в очереди клиента) до сброса боя; резерв нового боя — обычным путём.
   - Старт боя: `actors.len() == expected` и каждая занятая позиция принадлежит живой
     `entry_ready`-сессии (вместо «все сессии таблицы»).
   - `attach_waiting_sessions` не пытается занять позицию сверх `expected` (защитно).
   - Сбой боя (`contain_battle_failure`) не трогает ангарные сессии без резерва/записи в полёте.
   - Возврат из боя уже освобождает позицию (detach/сброс мира) — без изменений.
3. Пределы, масштабируемые от `connection_capacity` (только при заданном ключе):
   окно повторов `max(32, 4×capacity)`; бюджет датаграмм `max(256, 4×capacity)`/с;
   чтение до 64 датаграмм на сокет за итерацию. Все очереди ограничены; память на сессию
   измеряется нагрузкой.
4. Отказ при полном шлюзе — прежний настоящий LoginReply 73 + строка
   `GATEWAY_CAPACITY_REJECT`. Есть ли в EXE 0.9.1 отдельный код «сервер полон» — UNKNOWN, не выдумываем.
5. Нагрузочный инструмент `tools/gw01_login_load.py`: только loopback, только собственные тестовые
   аккаунты копии стенда; цикл = настоящий native LoginRequest (RSA-OAEP, ключ стенда) → ответ →
   BaseApp-рукопожатие → первое сообщение канала → native disconnect `[11,0]`. Пишет коды ответа,
   задержки, RSS/CPU шлюза в `local/evidence/…`. Подготовка копии стенда с N тестовыми аккаунтами —
   отдельная команда инструмента, только в `local/stands` этого worktree.

## Приёмка

| Проверка | Как |
|---|---|
| Ключ отсутствует → поведение прежнее | существующие тесты шлюза; FAIL-набор против `b31f691` тот же |
| Конфиг: границы, несовместимости | unit-тесты `identity.rs` |
| Третий вход при `capacity=256` и бое на 2 — не 73; Join сверх мест ждёт; старт боя с ангарными сессиями | unit-тесты `server.rs`/диспетчера |
| Полный шлюз → 73 и запись в окно повторов ограничена | unit-тест |
| 200 входов/выходов без 73, RSS/CPU шлюза | `gw01_login_load.py` на копии стенда → evidence |
| Native: 2 реальных клиента + синтетика | **NOT_RUN** — владелец |

Откат: убрать `connection_capacity` из `gateway.json` и перезапустить шлюз.
