# Текущая карточка — 2026-10-15

**P08B — «В бой» из ангара профиля 13.** Выбранная машина с проверенным боевым
профилем входит в общий бой, резервируется и возвращается в ангар.

Полная постановка, разбивка и приёмка — пункт 2 в
[IMPLEMENTATION_ORDER](IMPLEMENTATION_ORDER.md). Боевой стенд и команды — в
[DEV_NOTES](DEV_NOTES.md). Состояние проекта — [STATUS](STATUS.md).

Начать с исследования работающего одиночного `legacy091-map-drive`: родная
кнопка «В бой!», переход Account → Avatar и возврат уже были проверены там.
Изучить `P02_MAP_DRIVE` / `P02_MANUAL_BATTLE_BUTTON`, цепочку профиля13 и
`battle/profile4_adapter.rs`; затем краткий план P08B и ветка от актуального main.

STAB-01 принята на runtime `0574ab0`: изоляция ошибки, оба native-возврата и
повторный бой. Факты и ограничения — [исследование STAB-01](research/STAB01_BATTLE_STABILITY.md).
Lab-only временная машина не реализует выбор/резерв машины профиля13.
P08B в работе, ветка `codex/p08b-profile13-battle`: writer/Web/client проверки
пройдены, gateway890 PASS/5 ignored и сборка PASS на `0834fee`;
свежая native-приёмка ещё не закрыта, в main карточка не слита.
Факты и явная test_lab policy — [исследование P08B](research/P08B_PROFILE13_BATTLE.md).
