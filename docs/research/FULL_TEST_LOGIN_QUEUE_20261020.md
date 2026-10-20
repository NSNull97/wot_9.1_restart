# FULL-TEST: независимый вход аккаунтов (2026-10-20)

Ветка `codex/full-test-pending-login-queue` от `codex/full-test-20261019` `28c7aad`.
Наблюдение владельца: клиент B не может войти, пока A не дошёл до ангара.
Первая версия (ограниченная очередь, `3d7ec55`) по решению владельца заменена
независимым входом по аккаунтам (`ec51d48`, `726b536`); план —
[docs/plans/FULL_TEST_PER_ACCOUNT_LOGIN.md](../plans/FULL_TEST_PER_ACCOUNT_LOGIN.md).

## Причина

`shared/server.rs`: один слот identity (`auth`) и один слот гаража (`ammo_job`).
Пока что-либо из `auth`/`ammo_job`/`battle_dispatch`/`result_manager`/room host
занято или с прошлого старта < 250 мс, новый login сразу получал `rejection(73)`.

## Факты

- **VERIFIED** (EXE VA `0x60da55`, [P01](P01_BOOTSTRAP_AND_NATIVE_LOGIN.md)):
  73 = `LOGIN_REJECTED_SERVER_NOT_READY`.
- **VERIFIED** (байткод `LoginDispatcher.pyc` клиента `p03f/a`, marshal+dis
  CPython 2.7.3, без исполнения): статус идёт в `handleLogOnFailed` — текст и
  `connectionManager.disconnect()`, автоповтора нет.
- **OBSERVED** (стенд `-05`, capture `capture-20261020-114338` пакеты 0–222 по
  mtime; трасса `runtime-b/native-144256-…jsonl`): identity A — 10,6 с; B
  получил шесть 73 и вошёл с седьмого нажатия, через 11,03 с после запроса.
- **OBSERVED**: на одну попытку клиент шлёт до 10 LoginRequest с шагом 1,0 с
  (новый request ID) и принимает ответ только на последний ID.
- **OBSERVED, один замер** (P08B `native-fix01/runtime-b`): от submit до
  `LOGIN_REJECTED_NO_LOGINAPP_RESPONSE` 17,17 с. Константа в EXE — UNKNOWN.
- **VERIFIED** (код `tools/*_store.py`): все писатели — `BEGIN IMMEDIATE`, строки
  по `account_id`, ревизии (`STALE_REVISION`) и ledger по `command_key`;
  `RunOpen` per-account. Общий только файл `game.sqlite`: WAL ставит мост,
  `busy_timeout` Python 2 с.
- **OBSERVED** (копия БД/fixtures стенда `-05` через SQLite backup,
  `local/build/lockprobe-01/result.json` в worktree): `fixture` входа одного
  аккаунта 3,2–3,4 с; два аккаунта параллельно — 3 раунда, оба успешны,
  3,3–3,7 с. Write-lock держится недолго.

## Решение

Шлюз (`shared/server_login_admission.rs`, `server.rs`):

- До 4 identity-заданий одновременно. Аккаунт до аутентификации — SHA-256 с
  солью процесса от канонического email (`identity091::credentials`); при
  допуске ключ сохраняется в `Session.login_account`. Email и ключ в логи не
  выводятся.
- У одного аккаунта не бывает двух заданий, задания при его живой сессии
  (кроме повтора той же попытки — переотправка redirect) и задания поверх его
  писателя (гараж, задания боя, результаты). Конфликт — 73.
- Писатели без владельца-аккаунта (late-results worker, owner hold, room host
  обучения) — прежняя общая сериализация. В режимах owner hold и training
  rooms лимит заданий и гаража — 1 (старый порядок).
- Временная блокировка (интервал 250 мс, 4 задания, общий писатель, писатель
  своего аккаунта) — без ответа, пока ожидание + последняя длительность входа
  ≤ 16 с; родной повтор через 1 с приходит снова. Дальше 73. Хранится только
  `LoginAttempt` и время (≤ 16 записей), без учётных данных. Очередь удалена.
- Гараж: пул до 4 заданий, не больше одного на аккаунт; владелец остаётся и
  после закрытия сессии. При допуске — отказ, если у аккаунта идёт гаражный
  писатель или задача результатов.
- Классы писателей (гараж / бой / результаты) между собой по-прежнему
  взаимоисключают друг друга; результаты больше не ждут входа других аккаунтов.

Мост (`web/src`): у сервиса аккаунта Python-воркеры идут строго по очереди
(`account-worker-lane.mjs`: один работает, один ждёт, третий — отказ; было
«до двух одновременно»). Отдельный предел `login` — 4 (scrypt), общий предел
запросов 4 → 12.

Сценарий стенда `-05` (B через 5,8 с после A) — **INFERRED**: B стартует сразу,
ответ примерно через 10,6 с после своего запроса.

## Ограничения

- Late-results worker, owner hold и обучение по-прежнему блокируют все входы
  на время своей работы (ожидание до окна, затем 73).
- Единичное identity-задание всё ещё ~11 с (scrypt, проекция, `RunOpen`);
  ускорение — отдельная карточка.
- Одиночный путь шлюза (`session.rs`, не shared) не менялся.
- Native-приёмка двух клиентов — **NOT_RUN**. Стенд `-05` не перезапускался.

## Проверки (worktree `amazing-heyrovsky-81f6a6`, пути от его корня)

- Rust `login_admission`: 5 PASS — два перекрывающихся входа разных аккаунтов,
  тот же аккаунт дважды, писатель своего аккаунта / общий fallback, окно клиента,
  соль ключа (`local/build/server/gateway-account-login-filter01`).
- Полный прогон шлюза: ветка 1608 PASS / 83 FAIL / 5 ignored
  (`gateway-account-login-full01`), база `28c7aad` 1603 / 83 / 5
  (`gateway-login-queue-base01`); наборы FAIL совпадают. Все 83 — guard'ы рабочего
  пространства («fixture must belong to current source workspace», «Linked/junction
  path refused»): composition-тесты с настоящим UDP-входом здесь не выполнялись.
- Канонический gate в `D:/WoT_9.1_Server` — **NOT_RUN** (нужен checkout ветки
  там; стенд `-05` берёт оттуда tools).
- Python `test_store_concurrent_accounts`: 4 PASS, 3 повтора стабильно
  (`test_game_profile_tx` OK).
- Node `account-worker-lane`: 3 PASS; `p04m-bridge` (настоящий HTTP-вход и
  crew-воркеры) 3 PASS. Весь web-набор: ветка 67 pass / 37 fail / 12 skip, база 64 / 37 / 12,
  наборы fail совпадают (нет `node_modules`/данных в worktree). Тест
  параллельных логинов `game-adapter` до своего случая не дошёл (нет
  `local/evidence/20261004-p02-hangar`) — **NOT_RUN**.

Откат: не сливать ветку или `git revert` её коммитов; схем и данных нет.
