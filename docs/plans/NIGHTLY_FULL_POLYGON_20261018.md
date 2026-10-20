# Ночной full-polygon integration 2026-10-18

## Цель

Собрать в отдельной ветке цельный серверный полигон из уже готовых P08B/P08C,
P05C, P07B, P04M, P06T и P10B, с ангарным исследованием/покупкой и доступным
боевым профилем. `main` не меняется до утренней ручной приёмки.

## Порядок

1. Проверить текущий source-bound chain и узкие Rust/Python gates.
2. Закрыть подтверждённые P06T defects: переходы engine/fuel, module facts в
   Results8, persistent detached turret с parent hide и collision handoff.
3. Сверить profile13/P09E research, purchase, crew, ammo и admission на одном
   D-only successor stand без SQL-мутаций исходных стендов.
4. Подготовить свежий stand и автоматический composition/full gate; native/UI/
   audio/control/two-PC остаются `NOT_RUN` до утреннего прогона владельца.
5. Записать единый manual сценарий: research → purchase → crew/loadout → queue /
   cancel / requeue → mixed battle → visibility/physics → shells/modules/fire /
   ammo rack/turret → capture/destruction/timer → Results8 → both hangars.

## Правила доказательства

Каждый gate фиксируется с branch/head, executable/database SHA, точной командой,
реальным результатом и границами. Автоматический composition PASS не закрывает
native приёмку. При нехватке D места новые targets не создаются, historical
evidence/client resources не удаляются.
