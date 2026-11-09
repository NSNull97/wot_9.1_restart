# План DISP-01 — двойной разброс (2026-11-09)

Ветка `codex/disp-01-dual-dispersion` от main `a8c58600`. Источники: [Shell Mechanics 2.0](../decisions/SHELL_MECHANICS_2_0.md) §3 и §9, байткод клиента #717.

## Что есть сейчас

| Факт | Категория |
|---|---|
| Сервер не считает разброс: снаряд летит точно по стволу (`aim::shot_geometry_pose_for`); круг сведения рисует клиент по `updateTargetingInfo` | VERIFIED (код) |
| Боты целятся с придуманной ошибкой `sigma(t) = 0.004·(1+3·e^(-t/aiming))` (`bots.rs`) | VERIFIED (код), LAB |
| Формула размера круга, `Avatar.getOwnVehicleShotDispersionAngle` (`res/scripts/client/avatar.pyc`): см. ниже | VERIFIED (байткод) |
| Как сервер 0.9.1 распределял снаряды внутри круга | UNKNOWN (в клиенте нет) |

Формула клиента:

```text
ideal = mult * sqrt(1 + ((speed*movement)^2 + (rspeed*rotation)^2 + (turret_speed*turret)^2 + shot^2) * additive^2)
aiming = start_factor * exp((start_time - now) / aiming_time)
if aiming < ideal: aiming = ideal; start_time = now; start_factor = ideal
angle = gun.shotDispersionAngle * aiming
```

`shot` — 0 без выстрела, `afterShot` при выстреле, `afterShotInBurst` в очереди. `shotDispersionAngle` — из `shotDispersionRadius` (на 100 м).
`whileGunDamaged` орудия (2.0 у проверенного образца) — данные, сейчас в `capabilities` зашито 2.

## Что сделать

1. Серверный круг той же формулой на каждого участника: скорости из авторитетной физики, `afterShot`/`whileGunDamaged` из данных орудия.
2. Отклонение выстрела: угол `r` и направление `theta` вокруг линии ствола, бросок из зерна выстрела, запись в трассу и повтор.
3. Только под ключом стенда `shell_rules`; без него снаряд летит как раньше, фикстуры не меняются.
4. Статистика: ≥ 100 000 выстрелов на профиль (доля в зоне 75 %, границы круга), детерминизм от зерна.
5. Бой владельца на -13.

## Решения владельца 09.11

1. Внутри круга — Dual Dispersion 2.0: `k(A) = clamp(0.5 + 0.8*(A - 0.35), 0.35, 0.70)`, 75 % в зоне `R*k`, `r = R*U^alpha`, `alpha = ln k / ln 0.75` (коэффициенты `experimental`).
2. САУ — усечённое нормальное, сигма = R/2, всегда внутри круга (`requires_verification`); ×1.25 и сплэш ×1.10 — ENV/SPG.
1а. После боя 09.11 (трасса 323 выстрела: 41 % ближе 0.1 R при формуле `U^alpha`) владелец выбрал форму: усечённое нормальное, сигма подбирается под орудие так, чтобы 75 % попадало в `k(A)*R`.
3. Боты: придуманная ошибка убирается, стреляют по тем же правилам разброса, что и игроки (под тем же ключом).
