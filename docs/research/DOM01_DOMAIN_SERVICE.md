# DOM-01 — долгоживущий Domain/Account service: факты и замеры

Ветка `codex/dom-01-domain-service` от main `e4296af`; план — [DOM01_DOMAIN_SERVICE](../plans/DOM01_DOMAIN_SERVICE.md),
решение — [ADR-002](../decisions/ADR_ARCH01_TARGET.md). Метки — как в AGENTS. Это архитектура нашего
сервера, а не сведения о WG/«Орионе». Native-приёмка — **NOT_RUN** (владелец).

## Что было (VERIFIED, `e4296af`)

| Факт | Источник |
|---|---|
| Bridge порождает `python -B -X utf8 <worker> … <operation>` на каждый запрос; для profile13 worker — всегда `tools/p08b_battle_service.py` | `web/src/p04d-crew.mjs:56,76` |
| Очередь аккаунта: 1 выполняется + 1 ждёт, третий — `Crew worker busy` | `web/src/p04d-crew.mjs:71`, `web/src/account-worker-lane.mjs:9` |
| Каждый worker-процесс заново грузит каталог и проверяет клиент | `tools/p08b_battle_service.py:70-71` |
| Класс стора выбирается флагами: `PoolStore → MixedAmmoStore → AmmoLossStore → OwnerHoldStore` | `tools/p08b_battle_service.py:73-78` |
| Late-owner'ы (bridge `late_result_service`) пишут через отдельный порождаемый `tools/p08c_late_results_service.py` | `web/src/game-adapter.mjs:333`, `web/src/p08c-late-results.mjs:138` |
| Шлюз ходит в bridge HTTP только через `Config::post_with_budget` | `server/gateway/src/account/identity.rs:511` |
| Каждое чтение профиля заново проверяет все квитанции увольнения (`p04j_retired_member`), т.е. O(история) | `tools/p04j_crew_store.py:246` |
| «Чистая» часть проверки (plan/response) мемоизирована на **экземпляре** стора | `tools/p04m_pool_store.py:130-134` |

## Что сделано

- `tools/p08b_battle_service.py`: тело `main()` → `execute(context, operation, read_request)`; CLI вызывает его же.
  `tools/p08c_late_results_service.py`: `run/execute` (порядок CLI: декодирование до загрузки каталога сохранён).
- `server/domain/service.py` + `server/domain/protocol.py`: один процесс, каталог и `audit` — один раз;
  протокол `wot091-domain.v1` (u32 длина ‖ u16 длина заголовка ‖ плоский ASCII JSON ‖ тело-байты), HMAC-SHA256
  challenge по секрету 43 символа, кадр ≤ 72 KiB, заголовок ≤ 1 KiB/8 полей, ≤ 16 соединений, 64 запроса/с на
  соединение и 256/с всего, очередь аккаунта 1+1, пул 4 потока, сторож бюджета (`activate` 60 с, прочее 15 с →
  `os._exit(75)`), остановка с ожиданием текущих операций ≤ 20 с.
- Флаги (по умолчанию выключены): шлюз `domain_service` (пути `ammo, crew*, research, battle, battle-results,
  late-result-append, late-result-pending`), bridge `domain_service` (`run` p04d и late-сервис — кадром вместо
  `spawn`; при старте `describe` сверяет флаги каждого аккаунта). Login/profile/website — bridge (identity).
- `tools/p04m_pool_store.py`: мемо «чистой» части проверки квитанций — на процесс (LRU канонических байтов, 64 MiB,
  потокобезопасно); `_scanned_json` хранит SHA-256, а не строки. Проверка квитанций по-прежнему выполняется при
  каждом чтении; подмена квитанции → `CORRUPT_STORE` (тест).
- `tools/full_test_stand.py domain [--disable]`, `tools/domain_stand_rehearsal.py`, `tools/domain_stand_bench.py`,
  `tests/bench_domain_latency.py`.

## Свёртка цепочки сторов (пункт 4 карточки)

VERIFIED тестами: Domain работает на тех же последних классах profile13, что и bridge, на той же схеме; БД,
записанная CLI-воркером, читается Domain и наоборот; квитанции, записанные порождаемым воркером, повторяются через
Domain тем же ответом (`replayed=true`). Миграция данных для одного процесса **не нужна**, поэтому схема и классы
не менялись. Свёртка иерархии `p04d…p04k → p09e → p04m → p06t → p08b` в один модуль — отдельная карточка
(рефакторинг ~13 сторов без изменения поведения; риск регрессий выше пользы для этой цели).

## Замеры

См. раздел «Результат» плана; сырые данные — `local/evidence/20261026-dom01-latency/`.

## Ограничения и UNKNOWN

- **Тяжёлый аккаунт.** На копии стенда CREW-ANY (B: 192 выданных, 162 уволенных, revision 354) чтение ≈ 0,4 с,
  отклонённая команда 0,7–1,0 с (было 2,5–3,1 с). Цель < 300 мс для чтений достигнута для обычных аккаунтов, но
  не для этого. Остаток (OBSERVED, cProfile): `Catalog.sha256` — проверка мутации через `marshal` 33 раза на чтение
  (~0,1 с); разбор 324 JSON квитанций (~0,13 с); глубокие копии. Следующий шаг — контрольная точка проверки
  истории (проверенный префикс квитанций по хешу) и закрепление хеша неизменяемого каталога в процессе Domain;
  обе меняют проверку целостности и требуют своей карточки.
- **Прерывание.** Поток Python прервать нельзя: при превышении бюджета процесс завершается целиком (как kill
  воркера сегодня). Если клиент отказался ждать (дедлайн), Domain может закончить команду: результат — в ledger,
  повтор того же ключа даёт тот же ответ (INFERRED — тот же класс исхода, что и kill после commit сегодня).
- **Оставшиеся писатели вне Domain.** Bridge пишет `game_profiles` при первом входе (`game.ensure`,
  `web/src/game-adapter.mjs:549`) и лимиты `game_limits` — это identity-обязанности. Выборы тренировочной комнаты
  (`room_selection*`) — отдельные порождаемые писатели; с ними Domain не включается (явный отказ шлюза и bridge).
- **JS-проверки ответов bridge** на пути шлюз → Domain не выполняются; остаются проверки стора (Python) и разбор
  ответов шлюза (Rust). Ответ Domain = байты воркера; bridge сегодня отдаёт `JSON.stringify(JSON.parse(...))` —
  равенство как JSON проверено (репетиция), байтовое совпадение с выводом bridge не заявляется.
- **Каталог/клиент** проверяются при старте Domain; изменение ресурсов клиента требует перезапуска.
- **GIL.** Разные аккаунты идут параллельно, но CPU-часть Python сериализуется GIL; для 200 CCU (3–7 оп./с по
  ADR) INFERRED достаточно; замер под нагрузкой — LOAD-200.
- Native (полный ангарный сценарий + бой на пересобранном стенде) — **NOT_RUN**.
