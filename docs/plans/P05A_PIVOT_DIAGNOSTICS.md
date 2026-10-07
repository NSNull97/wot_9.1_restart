# P05A — offline pivot diagnostics

Дата: 2026-10-08. Ветка: `codex/p05a-pivot-diagnostics`.
Статус: **PASS_OFFLINE_PIVOT_DIAGNOSTICS / native movement NOT_RUN**.

## Цель

Зафиксировать воспроизводимый диагностический прогон слабого поворота MS-1 на
закреплённом `server/physics` worker. Harness использует только существующий
bounded domain JSONL contract: свежий worker стартует отдельно для каждой
фиксированной последовательности, после settle принимает команды с
`throttle/steer/brake`, а receipt сохраняет каждый серверный кадр.

Карточка не выбирает Jolt API, не меняет коэффициенты движения и не утверждает
историческую физику. Отсутствующие ignored map/config/worker assets дают
`NOT_RUN_MISSING_INPUTS`, а не синтетический PASS.

## Фиксированные сценарии

Для каждого сценария worker стартует заново, поэтому сравнение начинается с
одинакового settle baseline:

- `neutral`: 10 запросов `0/0/false`;
- `left`: 20 запросов `0/-1/false`;
- `right`: 20 запросов `0/1/false`;
- `reverse`: 20 запросов `-1/0/false`.

Каждый запрос содержит `ticks=6`; harness ожидает `ready seq=0 tick=180`,
затем `state seq=1..N` с шагом `tick += 6`.

## Проверки

Harness отклоняет malformed/foreign кадры и проверяет:

- точные contract fields, event/map/config hash;
- monotonic sequence и tick без дубликатов/скачков;
- finite position/direction/velocity/speed;
- position bounds из hash-verified config;
- `contacts` в `0..6` и шесть wheel masks в `0..63`;
- settle frame с минимум тремя контактами и bounded velocity.

Из доступного worker state вычисляются только наблюдаемые метрики: начало/конец
pose, signed speed, yaw delta и contact summary. Engine RPM, left/right track
speed, gear/clutch и delivered torque отсутствуют в текущем worker contract и
receipt должен пометить их `UNKNOWN`, без догадок о причине pivot.

## Scope и границы

Входит: offline runner, fixed command plan, replay receipt, invariant parser,
unit tests и этот план.

Не входит: native/research client, deployed service, database, gateway, Jolt
source/API, physics tuning, destruction, tank-to-tank, native visual/manual
acceptance, историческая или межплатформенная эквивалентность.

## Fresh worker receipt (2026-10-08)

The receipt-matched ignored assets were available in the current checkout, so
the four scenarios were run independently on both imported test-lab maps with
the same bounded command plan. Karelia receipt
`local/evidence/20261008-p05a-pivot-diagnostics-06/result.json` has SHA-256
`9915b226305eee1ef6f1f87c2838b91c5a4751ac1a4e58850c7106da4ada8d93`; its
config SHA is `cf93c617d328865faaf93b7081eb838eb13262b12fe27b4a603e1f2a7023f4c2`.
Prokhorovka receipt
`local/evidence/20261008-p05a-pivot-diagnostics-07-prohorovka/result.json` has
SHA-256 `c692507dacaf2cc5469f8e9c93fe2619ccce14f684fb2e39ce0582bf2d020e2c`;
its config SHA is `eb7e9f3042ce00b8c5f1b84f43c4c3a77530b35e05bdf63c4b6225e1256caf7c`.
Both returned `PASS_OFFLINE_PIVOT_DIAGNOSTICS`, four scenarios, finite bounded
states, monotonic sequence/tick and settled contact frames. The shared worker
binary SHA is `a88d03e279ddd73c1746bb0ba55bcf38fbfb98b52daf9025f84fbeae18024edf`.
The receipt reports only observable pose/speed/yaw/contact metrics. Engine RPM,
left/right track speed, gear/clutch and delivered torque remain `UNKNOWN`.

## Acceptance

- Unit tests проверяют положительный contract и отрицательные seq/tick/finite/
bounds/contact cases.
- `plan` mode создаёт self-contained receipt с четырьмя сценариями и
`telemetry=UNKNOWN` без запуска worker.
- При наличии реальных ignored assets `run` mode возвращает PASS только после
  четырёх свежих worker runs и сохраняет stdout/stderr, config hash, commands и
  metrics; текущий recheck дал два map receipts с четырьмя сценариями каждый.
- `git diff --check`, unit tests и canonical `server/build.py physics` проходят;
сборка сама по себе не считается physics run.

## Откат

Удалить только harness, tests, этот план и ignored receipts этой карточки;
runtime/client/deployed gateway не требуют rollback.

Единственный следующий шаг после карточки — вручную/отдельной native задачей
проверить pivot на настоящем клиенте; не менять физические параметры, пока
telemetry не покажет конкретный слой причины. Offline PASS не закрывает
native collision equivalence, prediction/correction, историческую физику или
owner acceptance.
