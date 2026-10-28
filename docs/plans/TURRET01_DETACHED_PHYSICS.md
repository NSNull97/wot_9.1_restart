# TURRET-01 — оторванная башня как тело Jolt

Ветка `codex/turret-01-detached-physics` от `integrate/ft15-20261029` = `c76fd62`. Не влита, не pushed.

## Причина (VERIFIED по коду c76fd62)
`ammo_detonation.rs`: башня — точка с постоянными `LOCAL_VELOCITY [2,8,1.5]`, `ANGULAR_VELOCITY [1.2,0.7,2.4]`,
прижатие к террейну по вертикальному лучу, тела Jolt нет → одна поза, ствол под картой.

## Клиент 0.9.1 (VERIFIED статически, `res/scripts/client/detachedturret.pyc`, без исполнения)
- `DetachedTurret.__init__`: `self.filter = BigWorld.WGTurretFilter()`, `filter.enableSphericalInterpolation = True` —
  клиент интерполирует родные volatile-позы (позиция + yaw/pitch/roll); путь не меняется.
- Орудие крепится к узлу `HP_gunJoint` единичной матрицей → ствол в нейтральном наклоне относительно башни.
- `SynchronousDetachment.transferInputs` берёт начальную матрицу башни машины. `onStaticCollision(energy, point, normal)` —
  клиентский метод эффектов удара; сервер его не шлёт (UNKNOWN частота оригинала, вне карточки).
- Частота: сервер шлёт не чаще позы за тик (100 мс) и только при изменении (как после SPAWN-15). Внутренняя задержка фильтра — UNKNOWN.

## Решение
- Шлюз: при подрыве в бою со сценой (`World::turret_jolt`, ставит `BatchRuntime.start`) — `Flight::jolt`:
  6 вытяжек SplitMix64 боя (журнал `rng_draws`, ординалы 0xe0..0xe5) → `Launch::derive` (политика
  `project.turret01.detached-turret-jolt-launch.v1`, ПРОЕКТНАЯ): вверх 5..10 м/с (сильнее при полном БК),
  вбок 1..4 м/с по курсу атакующий→цель ±60°, вращение до 3/2/3 рад/с. Скорости, не импульсы (массы в данных клиента нет).
- IPC7 op `turret_flight`: точки опоры (98 направлений) коллизионных сеток Turret и Gun в системе шарнира,
  мёртвые машины как статические боксы. Воркер строит отдельный PhysicsSystem «обломков» (террейн, статика,
  присутствующие объекты каталога, стены, обломки корпусов; свой корпус — после выхода башни из его бокса),
  тело `StaticCompoundShape` из двух `ConvexHullShape`, LinearCast, трение 0.8, упругость 0.1 (ПРОЕКТНЫЕ),
  60 Гц до сна или 10 с, выборка раз в 100 мс. Политика тела `project.turret01.detached-turret-jolt-body.v1`.
- Шлюз проигрывает траекторию по часам; до ответа — поза шарнира. После итога боя запрос всё равно уходит
  (`turrets_after_outcome`). Без сцены — прежняя точечная модель (legacy).
- Ограничения: живые машины не препятствие для башни; разрушение объекта под лежащей башней не учитывается.

## Проверки
| Проверка | Статус |
|---|---|
| unit `turret01_launch_*`, `turret01_jolt_flight_*`, мировой `turret01_actual_rack_event_*` | PASS (3) |
| C# сборка `server/build.py physics` (`local/build/physics-turret01-02`) | PASS_ISOLATED_BUILD |
| ignored `turret01_detached_bodies_in_real_jolt_scene` (разные траектории, бит-в-бит повтор, клиренс над террейном) | NOT_RUN |
| ignored `turret01_bench_thirty_places_with_detonations` (release) | NOT_RUN |
| Набор шлюза ветки против `c76fd62` | база 1725/94/12 (`local/evidence/suite-base-c76fd62.log` в worktree); ветка NOT_RUN |
| Native | NOT_RUN |

Запуск реальных тестов: стенд-каталог `D:/WoT_9.1_Server/local/stands/turret01-bench-01` (физика этой ветки):
`TURRET01_MANIFEST=D:/WoT_9.1_Server/local/stands/turret01-bench-01/battle-profiles-05_prohorovka.json TURRET01_OUT=<json> bash local/cargo_test.sh turret01_ -- --ignored --nocapture`
(бенч 30 — с `--release`).

Откат: не сливать ветку; стенды не менялись.
