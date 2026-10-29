# MM-01 — очередь и подбор

Ветка `codex/mm-01-matchmaker` от main `6f3882a` (BOT-01 в main). Строка 8 [ARCH01_MIGRATION](ARCH01_MIGRATION.md).
Основание: [GW-01](GW01_GATEWAY_CAPACITY.md) (места арены ≠ соединения), [ARENA-01](ARENA01_MULTI_ARENA.md)
(K арен), [SPAWN-15](SPAWN15_TEAM_BASES.md) (места у баз), [BOT-01](BOT01_SERVER_BOTS.md) (боты на местах).
Метки — как в AGENTS. Правила подбора — **проектная политика**, не исследованный матчмейкер WG 0.9.1.

## Что есть сейчас (VERIFIED, `6f3882a`)

| Факт | Где |
|---|---|
| «В бой» (native `Join`) только ставит `selection` + `join_requested`; `onEnqueued` уходит после коммита резерва | `shared/profile13_queue.rs:34-52`, `profile13_dispatch*.rs` `deliver*` `Admitted` |
| Резерв — writer `Admit{battle,native_inventory_id}` в Domain (`reserve_vehicle`: `state='reserved'`, `battle_id`), без срока | `profile13_dispatch*.rs` `start*`, `tools/game_profile_tx.py:233` |
| Резерв идёт в «лобби»: первая незапущенная арена со свободным местом; FIFO, без правил | `server_arena.rs:97` `lobby`, `server.rs:1869-1874` |
| Старт: `human_places` (= `bots.human_places` или все места) entry-ready, остальное — боты в ход старта | `server.rs:673-676,1958-1961`, `bots.rs:133` |
| Все арены заняты → `BATTLE_BUSY` ожидающим | `server.rs:1776-1785,1825-1835` |
| Уровень машины: `tier` из `list.xml` клиента в `battle_profiles.v1.json` (все 374) | `config/catalog/battle_profiles.v1.json`, встроен в шлюз с проверкой SHA |

## Решение

1. **Ключ `matchmaker`** в `gateway.json` (без ключа — побайтно прежний путь):
   `{"policy":"project.mm01.queue-tier-window.v1","team_size":T,"tiers":[lo,hi],"tier_spread":D,"wait_seconds":W,"lease_seconds":L}`.
   `2·T = battle_players` (места арены не меняются — шаблон уже собран на них); `tiers` ⊂ 1..10; `D` 0..9;
   `W` 1..600; `L` `W`..900. Требует `bots` (добор по тайм-ауту), `connection_capacity`, `p04m_pool`; несовместим
   с учебными комнатами и hold5 (их уже исключает `bots`). Предел мест не зашит: `T` ограничен только
   `battle_players` (до 30 со `spawn_policy`).
2. **Очередь.** Сессия в ангаре с `join_requested`, выбранной машиной, без резерва/возврата/writer'а/места в
   арене — билет `{session, account, tier, since}`. Уровень — по `native_inventory_id` → вид в p04m-привязке ангара
   (1 → МС-1, 2 → ИС-7 — как в identity) → `tier` таблицы. Уровень вне `tiers` или неизвестен — отказ
   `enqueue_failure("BATTLE_PROFILE_UNSUPPORTED")`. Билет объявляется клиенту сразу (`onEnqueued`), до резерва —
   иначе «В бой» молчит всё ожидание (INFERRED: клиент принимает `onEnqueued` до серверного резерва; native NOT_RUN).
   Отмена (`Cancel`) и выход снимают билет.
3. **Подбор** (каждый тик, только для свободной арены: не запущена, без актёров, без резервов на её бой, бой не
   закрыт): якорь — самый старый билет; в группу по FIFO берутся билеты, пока `max−min` уровней группы ≤ `D`,
   до `2·T` человек. Группа готова, если полна (`2·T`) или якорь ждёт ≥ `W` с; иначе — следующий якорь (младший
   билет другого уровня может собрать полную группу). Арене задаётся `human_places = n` людей группы, ботам —
   виды BOT-01 из окна уровней группы `[max−D, min+D]` (если таких нет — ближайшие по уровню, строка
   `MM01_BOT_TIER_NEAREST`). Команды — прежнее `slot % 2 + 1`: люди делятся ⌈n/2⌉/⌊n/2⌋, остальное — боты.
   **Пары мест (решение владельца 2026-10-29):** место команды 1 и то же место (порядковый номер в команде)
   команды 2 — одного уровня. Бот напротив человека — допустимый уровень, ближайший к уровню человека; бот
   напротив бота — общий уровень, ближайший к середине уровней группы (при равенстве — меньший). Вид внутри
   уровня — по кругу; зеркальная машина не обязательна (`matchmaker::paired_kinds`, `World::fill_bots`).
4. **Резерв с lease.** Член группы получает отметку `Matched(battle)`; writer `Admit` берёт только сессии,
   отмеченные этим боем (`Queued` — никогда). Резерв в Domain — прежний `reserve_vehicle`. **Lease** — срок `L` с
   момента подбора до старта боя, его держит шлюз: по истечении члены без места в арене отменяются прежним путём
   возврата (`Terminal::cancelled` → Domain возвращает машину), арена стартует с оставшимися (+ боты); если не
   осталось никого или истёк второй lease — отменяются все, бой закрывается и арена сбрасывается
   (`finish_empty_queue`). Срок в самой строке Domain — нет (INFERRED-ограничение: при падении шлюза резерв
   остаётся до прежнего восстановления; TTL в Domain — PG-01/BW-01).
5. **Не два боя.** Билет и группа — по сессии и по аккаунту; сессия с резервом/возвратом/местом в арене/writer'ом
   в очередь не встаёт; отметка `Matched` одна; writer пропускает сессию в чужой бой. Вход того же аккаунта второй
   раз шлюз и так отвергает (GW-01).
6. Под `matchmaker` ожидающие не получают `BATTLE_BUSY`, когда все арены заняты: билет ждёт свободную арену.

## Окно очереди в клиенте (дополнение владельца 2026-10-28)

Запрос: две таблицы — по уровням и по классам техники, «как в родном клиенте 0.9.1». Исследование — только чтение
оригинала `C:/WoT_0.9.1_RU_0717_original/res` (`.def` через `tools/packed_xml.py`, `.pyc` — `dis` CPython 2.7.3, SWF — строки
после zlib):

| Факт | Метка | Источник |
|---|---|---|
| Окно очереди раз в 5 с вызывает `Account.requestQueueInfo(qType)` → `base.doCmdInt3(REQUEST_ID_NO_RESPONSE, CMD_REQ_QUEUE_INFO, qType, 0, 0)`; `qType` случайных боёв = `QUEUE_TYPE.RANDOMS` | VERIFIED | `gui/scaleform/daapi/view/lobby/battlequeue.pyc` `__updateQueueInfo` (`BigWorld.callback(5, …)`), `account.pyc` `requestQueueInfo` |
| Ответ — client-метод `Account.receiveQueueInfo(RANDOMS_QUEUE_INFO, COMPANIES_QUEUE_INFO, HISTORICAL_QUEUE_INFO)`; клиент передаёт его в `events.onQueueInfoReceived` | VERIFIED | `entity_defs/Account.def`, `account.pyc` `receiveQueueInfo` |
| `RANDOMS_QUEUE_INFO` = FIXED_DICT `AllowNone`, **одно** поле `classes: ARRAY<UINT32>`; полей уровней нет | VERIFIED | `entity_defs/alias.xml` |
| Для случайного боя `BattleQueue.onQueueInfoReceived` показывает `sum(classes)` как число игроков и **одну** таблицу `as_setListByType`: строки тяжёлые, средние, лёгкие, ПТ-САУ, САУ; значение — `classes[VEHICLE_CLASS_INDICES[класс]]` | VERIFIED | `battlequeue.pyc` (строки 197–232 исходника), `TYPES_ORDERED` |
| Порядок индексов `classes`: `VEHICLE_CLASSES = (lightTank, mediumTank, heavyTank, SPG, AT-SPG)` | VERIFIED | `scripts/common/constants.pyc` |
| У meta-класса окна только `as_setTimer`, `as_setType`, `as_setPlayers`, `as_setListByType`, `as_showStart`, `as_showExit`; в `battleQueue.swf` один табличный компонент `listByType` (строки `LEVELS_1..10` — общие константы локализации) | VERIFIED (meta), INFERRED (SWF по строкам) | `meta/battlequeuemeta.pyc`, `gui.pkg:gui/flash/battleQueue.swf` |
| Таблица по уровням в окне очереди — из более поздних версий клиента, в 0.9.1 её нет | INFERRED | отсутствие поля в `.def` и вызова в скриптах 0.9.1 |
| Шлюз уже отвечал на опрос родным методом (индекс 85), но фиксированно «1 лёгкий» (`own_queue_info`); на стенде -11 опрос был один — бой с ботами стартовал сразу | VERIFIED | `drive/world.rs`, `gateway-20261028-175910.stdout.log` |
| ~~Байтовая раскладка ответа (длина массива 1 байт) принималась клиентом~~ — опровергнуто стендом -11 29.10 (сценарий E: окно пустое, `as_setPlayers` не вызван; клиент опрашивал 82×, ответ ставился в outbox) | — | `gateway-20261029-094601.stdout.log` |
| Индекс 85 (`0x55`) = `receiveQueueInfo`: слот 26 = `0x3b`+26; группа переменной длины идёт в порядке `.def` с `onChatAction` (Chat) первым, и её соседи, работающие на клиенте, сходятся: `0x4b` onChatAction (16), `0x4d` onCmdResponseExt (18), `0x53` showGUI (24), `0x57` update (28) | INFERRED (зажат проверенными соседями) | `Account.def`, `interfaces/chat.def`, трасса клиента (`showGUI`, `onCmdResponseExt`, `_update`) |
| `ARRAY` в потоке этого BigWorld — счётчик `UINT32` LE, не байт: так кодирует сам клиент (`doCmdIntArray`: `8+4·count`, `hangar.rs`) и так принимается создание Vehicle (`ARRAY<UINT64>`/`ARRAY<UINT8>` пустые = `0i32`, `arena/vehicle.rs`) | VERIFIED (два рабочих пути) | захват клиента, `create_requested_vehicle` |
| Флаг `AllowNone`: `1` = значение есть, `0` = None | VERIFIED | захват клиента `leaveArena(CLIENT_STATISTICS)` `[0x99,68,0,1,…]` |
| Причина пустого окна: однобайтовая длина массива. Клиент читал `[5,0,0,0]` как длину, ему не хватало байтов, и вызов отбрасывался молча (в `python.log` ничего) | INFERRED (все прочие звенья проверены; перехвата `receiveQueueInfo` в трассе нет) | выше |
| Исправлено: тело 27 байт = `1`, `UINT32 5`, 5×`UINT32`, `0`, `0` (сообщение 30 байт). Затронут и прежний ответ без ключа (`own_queue_info`): он был так же нечитаем | — | `drive/world.rs`, ветка `codex/mm-01-queue-info-array` |
| Проверка без патча клиента: окно очереди должно показать «Игроков в очереди: N» и строки по типам. Если окно останется пустым, доказательство даст перехват в трассе клиента: обёртка `PlayerAccount.receiveQueueInfo` и `BattleQueue.onQueueInfoReceived` с записью аргументов (в проектный трассировщик, как для `showGUI`). Сам не ставил | NOT_RUN | — |

Сделано (только сервер, родной путь): в режиме `matchmaker` ответ `receiveQueueInfo` несёт `classes` — число ожидающих
игроков (в очереди и в подобранных, но не начатых группах) по классам их выбранных машин (класс — `vehicle_class` таблицы
`battle_profiles.v1.json`, из тегов `list.xml`). Ответ отдаётся сессиям, которые ждут; остальным — прежний. Без ключа —
прежний ответ побайтно. Счёт по уровням 1..10 считается тем же состоянием и пишется в лог (`MM01_QUEUE_STATS … levels=`),
но клиенту 0.9.1 его передать нечем.

**Вопрос владельцу (таблица по уровням).** Родной клиент 0.9.1 не имеет ни поля, ни вызова для второй таблицы. Показать её
можно только клиентским патчем (свой Python-обработчик + изменение `battleQueue.swf` или отдельный виджет) и
неродным каналом данных. Без решения владельца не делаю. Варианты: (а) оставить одну родную таблицу по классам;
(б) отдельная карточка клиентского патча.

## Приёмка

| Проверка | Как |
|---|---|
| Конфиг: границы, зависимости, без ключа — прежнее | unit `identity.rs` |
| Правила: окно уровней, полнота, тайм-аут, порядок, несколько арен | unit `matchmaker_tests` |
| Lease: частичный старт, полная отмена | unit `matchmaker_tests`, `server_mm01_tests` |
| Игрок не попадает в два боя (сессия/аккаунт/резерв, writer чужого боя) | unit `matchmaker_tests`, `server_mm01_tests`, `arena01_dispatch_tests` |
| Наборы шлюза и Python против `6f3882a` в одной среде | множества FAIL равны |
| Окно очереди: кодирование `receiveQueueInfo`, счёт по классам и уровням из состояния очереди | unit `server_mm01_tests`, `matchmaker_tests` |
| Native: 4–6 клиентов, несколько боёв подряд | **NOT_RUN** (владелец, стенд) |

Откат: убрать `matchmaker` из `gateway.json`, перезапустить шлюз.

## Итог (2026-10-28, ветка `codex/mm-01-matchmaker`)

- Коммиты: `b068bf2` (очередь, подбор, lease, gate writer'а, конфиг, тесты), `70b7b24` (id распавшейся группы не
  переиспользуется: арена сбрасывается тем же путём, что пустая очередь), `89fcbf8` (окно очереди: родной
  `receiveQueueInfo` со счётом по классам). Не в main, не запушено.
- Код: `shared/matchmaker.rs` (чистая логика), `shared/server_matchmaker.rs` (связка), `server.rs` (тик, writer по аренам
  групп, без `BATTLE_BUSY` в режиме очереди), `profile13_session.rs` (`MatchGate`), `profile13_dispatch*.rs` (фильтр
  `admits_into`; без повторного `onEnqueued`; отказ Domain снимает объявленную очередь), `bots.rs` (`set_match_roster`),
  `generated_vehicles.rs`/`vehicle_profile.rs` (`tier`), `p04m_companion.rs` (`kind_label`), `identity.rs` (ключ).
  `contain_battle_failure` не тронут.
- Тесты MM-01: `bash local/cargo_test.sh mm01` — **19 PASS** (+ окно очереди и статистика) (правила/окно уровней/тайм-аут/арены/lease/один билет —
  `matchmaker_tests`; связка на двух LAB-аренах — `server_mm01_tests`; writer только в свой бой и не второй резерв —
  `arena01_dispatch_tests`; без повторного `onEnqueued` — `queue_loss_tests`; конфиг — `identity`; уровни машин стенда).
- Набор шлюза, один worktree и target (`local/test-runs/gw-*.log`): ветка `89fcbf8` **1699 / 94 / 12** (`70b7b24` — 1697), база `6f3882a`
  **1680 / 94 / 12**; множества FAIL **равны** (94 — окружение worktree: нет `local/evidence` и портативных фикстур,
  `NotFound`). Ветка `b068bf2` — 1696 / 94 / 12, те же FAIL.
- Python (`python -B -X utf8 -m unittest discover -s tests`, бандл `p09e-main-01/source-bundle-05`): 2786 тестов,
  ветка 117 FAIL+ERROR, база 120; FAIL ветки ⊂ FAIL базы (лишние 3 у базы — длинный путь вложенного worktree,
  `FileNotFoundError`). Python-кода MM-01 не меняет.
- Канонический gate, release-сборка и native — **NOT_RUN**.

- **Перенос на `integrate/ft15-20261029` = `d3bf20e`** (main + VIS-PERF + STAB-02), ветка `codex/mm-01-matchmaker-on-ft15`:
  конфликт `server.rs` с STAB-02 — запуск writer'а по аренам групп пропускает закрытую арену (`closed`); подбор и сброс
  арены распавшейся группы не трогают закрытые арены; ошибка этого сброса закрывает только свою арену
  (`containment::contain_arena`, stage `mm01_group_reset`). Тесты `mm01 stab02 terrain_anyhit bot01 arena01` — 52 PASS /
  2 ignored; набор шлюза 1711/94/12 против 1692/94/12 у `d3bf20e`, множества FAIL равны.

Ограничения и неподтверждённое:
- `onEnqueued` до серверного резерва и `enqueue_failure("BATTLE_BUSY")` после него (lease) — INFERRED для клиента 0.9.1.
- Lease держит шлюз; в строке Domain срока нет. Падение шлюза оставляет резерв до прежнего восстановления.
- Команды — прежнее `slot % 2 + 1` (люди поровну, потом боты); балансировки по уровням внутри боя нет.
- Боты не подбираются по месту в очереди: вид из окна уровней группы, иначе ближайший (`MM01_BOT_TIER_NEAREST`).
- Пары мест одного уровня (тест владельца 29.10, сценарий A: 4×T-34 получили KV-3 против M4) — ветка
  `codex/mm-01-bot-tier-pairs` на `18d6e63`. Если окно не содержит уровня человека, бот напротив него берёт
  ближайший допустимый, и уровни пары могут различаться.
- > 6 мест: итоги — RES-30 (в main нет); подбор проверен до 6 мест (`team_size` 15 принимает конфиг, тест).

## Шаги для стенда -11 (утром, после теста 15×15; выполняет родительская сессия с согласия владельца)

Стенд сейчас (BOT-01): Малиновка, `battle_players 6`, `arenas 2`, `connection_capacity 256`, `spawn_policy`,
`p06t_mixed_ammo` + `p06t_ammo_rack_detonation`, late results, Domain, `bots {human_places 1, kinds [t34, KV-3, M4, Chi-Ri,
t3485]}` (уровни 5/7/5/7/6). Клиенты: `p03f/a`, `p03f/b`, `arena/c`, `arena/d` (4). Меняются только `gateway.json` и exe.

1. Если стенд после 15×15 остался на RES-30 (tools/Domain из `D:/WoT_9.1_Server`): шлюз MM-01 без RES-30 пишет ≤ 6 строк
   итога — совместимость INFERRED; надёжнее вернуть стенд на main `6f3882a` (как для BOT-01) или перебазировать MM-01.
2. Release-шлюз **из этого worktree**, не из `D:/WoT_9.1_Server`:
   из корня `D:/WoT_9.1_Server/.claude/worktrees/mm-01-matchmaker-5be088`:
   `python -B -X utf8 server/build.py gateway --release --out local/build/server/gateway-mm01-release-<sha>`
   (exe — `<out>/target/release/sr-gateway.exe` в этом worktree; на D: ≈ 21 ГБ свободно). Канонический gate — по желанию,
   на чистом дереве.
3. Если клиенты запущены — спросить владельца. `services.ps1 stop`, затем `domain.ps1 stop`.
4. Копии: `gateway.json` → `gateway.before-mm01.json`, `services.ps1` → `services.before-mm01.ps1`,
   `game.sqlite` → `game.before-mm01.sqlite` (Domain остановлен).
5. В `gateway.json` добавить (остальное без изменений; `bots.human_places` в режиме очереди задаёт группа):
   `"matchmaker": {"policy": "project.mm01.queue-tier-window.v1", "team_size": 3, "tiers": [1, 10], "tier_spread": 2, "wait_seconds": 30, "lease_seconds": 120}`
6. `services.ps1`: `$gatewayExe` → новый exe. `domain.ps1 start`, `services.ps1 start`. В свежем `gateway-*.stdout.log`:
   `MM01_POLICY_BOUND … team_size=3 places=6 tiers=1..10 tier_spread=2 wait_s=30 lease_s=120 arenas=2 bot_tiers=["t34:5","ussr-KV-3:7",…]`,
   `BOT01_POLICY_BOUND`, `SPAWN15_POLICY_BOUND`, `ARENAS count=2`.
7. Проверки владельца (4 клиента, несколько боёв подряд):
   - **A. Все четыре на T-34 (ур. 5)**, «В бой» почти одновременно: у каждого сразу окно очереди (`MM01_QUEUED`); через
     30 с — `MM01_MATCHED … humans=4 bots=2 tiers=5..5 formed=timeout` в одной арене, 2 на 2 + по боту, бой до итогов.
   - **B. Два на T-34 (5) + два на T-26 (2)**: разница 3 > 2 — две группы по 2 человека в двух аренах
     (`MM01_MATCHED` ×2; у группы T-26 боты ближайшего уровня — `MM01_BOT_TIER_NEAREST`). Оба боя параллельно.
   - **C. Подряд**: после итогов снова «В бой» тем же составом — новая группа, новый `battle` (id растёт), без
     `VEHICLE_RESERVED`; так 2–3 боя.
   - **D. Выход из очереди**: «В бой», затем отмена до 30 с — `MM01_DEQUEUED`, машина свободна, повторный «В бой» работает.
   - **E. Окно очереди**: пока ждут, таблица «по типам» показывает число ожидающих по классам (T-34 — средние, T-26 — лёгкие),
     «Игроков в очереди» = сумма; в логе `MM01_QUEUE_STATS`. Таблицы по уровням в 0.9.1 нет (см. вопрос выше).
   - Нигде: игрок в двух боях, `P08B_ADMISSION_REJECTED VEHICLE_RESERVED` на своём же резерве, `SHARED_FAILED`.
   - 5–6 клиентов (если будут): 6 на близких уровнях — полная группа сразу (`formed=full`, ботов 0).
8. Откат: `gateway.before-mm01.json` и `services.before-mm01.ps1` на место, перезапуск шлюза; при сомнениях в БД —
   `game.before-mm01.sqlite` (Domain остановлен).
