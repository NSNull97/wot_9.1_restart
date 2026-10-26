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

## Итог (2026-10-26)

Коммиты: `a612d52` (шлюз и тесты), `208ef2d` (инструмент, общий тест-вектор шифра), затем инструмент/документы.

- Unit: `cargo test gw01` — 9/9 PASS (`capacity_config_tests`, `server_capacity_tests`,
  `gw01_capacity_dispatch_tests`); `python -m unittest tests.test_gw01_login_load` — 4/4 PASS.
  Шифр канала инструмента сверен с `baseapp::encrypt` одним вектором в обоих тестах (VERIFIED).
- Полный gateway-набор (цель на C:, та же раскладка `local/`): ветка 1646/83/7, база `b31f691` 1638/83/7;
  FAIL-наборы совпадают построчно (83 — окружение: пути удалённых worktree, real-worker фикстуры,
  composition-тесты). Канонический gate в `D:/WoT_9.1_Server` — NOT_RUN.
- Нагрузка 200 циклов — **NOT_RUN**. Копия стенда `D:/WoT_9.1_Server/local/stands/gw01-load-01`
  (с разрешения, порты 20440/20441/3792, без Domain, 4 синтетических аккаунта) bridge не запускает:
  - OBSERVED: каждый список владельцев bridge — 1..6 аккаунтов (`web/src/p08b-battle.mjs:13` и соседние),
    основной аккаунт обязателен; значит, в копии помещается не больше 4 своих аккаунтов;
  - OBSERVED: новый владелец без цепочки P08B owner-source падает на активации воркера
    `OWNER_SOURCE_REQUIRED` (`tools/p08b_owner_source.py:188`); подготовка пишет в фиксированный
    `local/evidence/20261015-p08b-01` — вне разрешённого;
  - чужие (владельца) тестовые учётные данные не использовались; подмена фикстур через «identity-заглушку»
    отвергнута — это фальшивые данные.
- Найдено попутно (OBSERVED, код bridge): 60 входов/мин на процесс, 10 на e-mail за 15 мин и не более
  2 одновременных проверок scrypt — третий одновременный вход получает 503 → шлюз отвечает 73.
  Для 200 CCU это узкое место bridge/Domain (MM-01/LOAD-200), не шлюза. Не исправлялось (вне карточки).
- Инструмент готов к запуску, когда будут подготовленные тестовые владельцы: `run` соблюдает лимиты bridge
  (окно 15 мин на аккаунт, ≤ 55/мин, ≤ 2 параллельно), держит N сессий одновременно, затем гоняет циклы и
  пишет `summary.json`, `cycles.json`, `process-samples.json`.

### Включение на стенде -10 (владелец)

Остановить `services.ps1 stop`, затем `domain.ps1 stop`. Собрать шлюз из ветки:
`python -B -X utf8 server/build.py gateway --cargo-temp-target --out local/build/server/<fresh>`.
Указать exe в `services.ps1` стенда, добавить в `gateway.json` `"connection_capacity": 256`.
Запустить `domain.ps1 start`, затем `services.ps1 start`. В логе шлюза ожидается `GATEWAY_CAPACITY connections=256 arena_places=2 …`.
Откат: убрать ключ (и/или вернуть прежний exe), перезапустить.
