# STAB-02: ошибка боя закрывает только этот бой

Ветка `codex/stab-02-battle-containment` от main `6f3882a`. Не влита, не запушена.

## Проблема (OBSERVED, стенд -11, 2026-10-28)

Ошибки одного боя завершали весь процесс шлюза: «laboratory fire profile» и «extended device
profile requires explicit v2 policy» (посадка generated-машины), «P06T shell must match closed
source catalogue» (выстрел M4). Причины исправлены в BATTLE-ANY (`f395d21`, `dde88f9`), но путь
отказа остался хрупким.

## Где ошибка становилась выходом процесса (VERIFIED по коду `6f3882a`)

- `contain_battle_failure` (`shared/server.rs`): `Dispatcher::terminal(...)?` — `from_actor_result`
  читает актёра сломанного мира и отказывает той же ошибкой (именно так на стенде: «failure
  containment hit the same device error», `f395d21`); `table.retire(...)?`; проверка
  `contained_world` — `return Err(bad())`; `template.replace(...)?`.
- Главный цикл: все 6 вызовов `contain_battle_failure(...)?` и `before_hold_reset(...)?` перед ними;
  `?` у смены вида шаблона на посадке (`from_resources`/`select`), `finish_empty_queue`,
  сброса припаркованного боя (`template.replace`), `advance_lifecycle` hold-мира, `terminal` при
  ManualLeave до старта, `battle_dispatch.retire` и `retire_contained_session` при закрытии сессии,
  `contained_return_world` в проходе profile13.

## Решение

1. `containment::contain_arena` (`shared/server_containment.rs`) — единственный вход цикла в
   containment; ошибку наверх не возвращает. Порядок: late `before_reset`, `before_hold_reset`
   (отказ — строка `SHARED_CONTAINMENT_HOLD_FREEZE_FAILED`, containment продолжается),
   `contain_battle_sessions` под `catch_unwind`.
2. Containment по сессиям: ошибка одной сессии не прерывает возврат остальных.
   Отказ terminal на сломанном мире → актёр снимается, резерв отменяется без результата боя
   (`SHARED_CONTAINMENT_TERMINAL_FALLBACK … actor_result_discarded=true reservation_cancelled=true`;
   расход/урон не выдумываются). Сессия, которая всё равно не может вернуться, —
   `SHARED_CONTAINMENT_SESSION_UNRETURNED` и отставка.
3. Отставка члена боя (`retire_member`): диспетчер (writer-лейн снимает резерв) → повтор после
   снятия актёра (не дважды в лейн) → только транспорт (`reservation_unreleased=true`) →
   удаление из таблицы `SHARED_SESSION_DROPPED … retirement_unrecorded=true`. Каждый шаг — своя строка.
4. Если сама containment вернула ошибку или упала: `SHARED_CONTAINMENT_FAILED … forced_retirement=true
   return_to_hangar=false` — отставка всех членов боя, сброс мира.
5. Мир не пересоздаётся → арена закрыта: пустой `World`, не шагает, не берёт Join (lobby её
   пропускает, при одной арене — `BATTLE_BUSY`), `SHARED_ARENA_CLOSED … joins_refused=true`;
   повтор сброса раз в 5 с (`SHARED_ARENA_CLOSED_RETRY` / `SHARED_ARENA_REOPENED`).
6. Цикл: перечисленные `?` пути боя заменены на `contain_arena` с этапом (`battle_select`,
   `leave_terminal`, `session_retire`, `lifecycle`, `battle_reset`, `queue_reset`, прежние
   `world_step*`, `result_snapshot`, `publication`, `hold5_pre_avatar_departure`, `training_handoff`).
   Закрытие сессии с ошибкой terminal → containment её боя, затем отставка (`retire_or_contain`).
   Старый `contain_battle_failure` сохранён для тренировочных комнат и тестов (тот же код сессий).

Вне карточки: паники вне шага и containment (сокеты, писатели, вход), `observe_hold_world`,
`before_hold_reset` в `finish_empty_queue` уже внутри новой обработки, тренировочные комнаты
(`retire_training_session` — прежний путь повтора `P10B_CLOSE_RETRY`).

## Итог

Тесты (`shared/stab02_containment_tests.rs`, синтетические резервы, без native):

- `stab02_failure_in_every_battle_phase_closes_only_that_battle` — 10 этапов входа в containment
  (ошибка внедрена): владелец боя арены 0 получает возврат через writer, арена 0 сброшена на
  следующий бой, ангарная сессия и её очередь не тронуты, арена 1 не изменена и шагает дальше.
- `stab02_terminal_refused_inside_containment_cancels_the_reservation_instead_of_exiting` —
  настоящий отказ terminal внутри containment (актёр не совпадает с замороженным контрактом).
- `stab02_world_that_cannot_be_rebuilt_closes_its_arena_and_reopens_on_retry` — настоящий отказ
  сброса (переполнение id): арена закрыта, Join не берёт, арена 1 шагает; повтор открывает.
- `stab02_failed_containment_retires_every_member_even_when_retirement_fails` — принудительная
  отставка, у одного члена нет login attempt: оба закрыты, каждый резерв в лейне ровно раз.
- `stab02_old_helper_still_contains_the_refused_terminal` — на базе `6f3882a` этот случай давал `Err`.

Наборы против базы `6f3882a` (один worktree, target `C:/wot091-stab02-target`, логи
`local/test-runs/stab02/` этого worktree, 2026-10-28):
  - шлюз: ветка `9b2f919` 1696 PASS / 83 FAIL / 12 ignored, база 1691 / 83 / 12 — множества FAIL равны
    (+5 новых тестов STAB-02, все PASS);
  - Python (`unittest discover -s tests`, `local/cache` и `local/tests` — настоящие каталоги): ветка и база
    2789 тестов, 13 failures + 139 errors, 180 skipped — множества FAIL/ERROR равны (Python-код не менялся).
  - Канонический gate — NOT_RUN.

Не проверено: native/стенд (NOT_RUN по заданию); паника внутри containment — только кодом
(`catch_unwind`), без теста с настоящей паникой; закрытая арена при одной арене на стенде —
игроки в очереди получают `BATTLE_BUSY` до переоткрытия.

## Шаги для стенда (владелец)

1. Собрать release-шлюз из ветки (`server/build.py --release …`), поставить на стенд копией,
   прежний exe сохранить рядом.
2. Бой 2 клиентов в двух аренах (`arenas: 2`) или один бой + игрок в ангаре.
3. Ошибку боя на стенде вызвать нечем без отладочного ключа; проверка — обычные бои, выход,
   итоги (регресс), и в журнале после любого сбоя — `SHARED_BATTLE_FAILED` + строки STAB-02, процесс жив,
   другой бой/ангар работают.

## Откат

Вернуть прежний exe шлюза на стенде. В git — `git revert` коммитов ветки (конфиг и БД не менялись,
ключей нет).
