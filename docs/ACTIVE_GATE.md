# Текущая карточка — 2026-10-16

**P08C — цикл боя**, ночная зависимая реализация после P08B: отсчёт, таймер,
захват, победа/ничья, гибель, native итоги и возврат.

Полная постановка и приёмка — пункт 3 в
[IMPLEMENTATION_ORDER](IMPLEMENTATION_ORDER.md). Боевой стенд и команды — в
[DEV_NOTES](DEV_NOTES.md). Состояние проекта — [STATUS](STATUS.md).

План — [P08C](plans/P08C.md), ночное разрешение владельца и утренняя матрица —
[NIGHT_20261016](plans/NIGHT_20261016.md). Продолжать по порядку без ожидания
ручных проверок; сохранять NOT_RUN и отдельные зависимые ветки до приёмки.

STAB-01 принята на runtime `0574ab0`: изоляция ошибки, оба native-возврата и
повторный бой. Факты и ограничения — [исследование STAB-01](research/STAB01_BATTLE_STABILITY.md).
Lab-only временная машина не реализует выбор/резерв машины профиля13.
P08B ветка `codex/p08b-profile13-battle`: writer/Web/client проверки
пройдены, gateway893 PASS/5 ignored и сборка PASS на `5c08ef5`;
Native-fix03: оба ангара с корректным расходом и повторный общий бой подтверждены
владельцем. Реальный crash с active reserve/recovery/оба native ангараAP14 PASS;
owner postrestart/mutation smoke отложен до утра. В main карточка не слита.
Факты и явная test_lab policy — [исследование P08B](research/P08B_PROFILE13_BATTLE.md).
