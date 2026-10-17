# P08B: четыре настоящих владельца и retained tank

Цель — проверить Hold5 через настоящие Config/Job/HTTP/SQLite/World и четыре
исходных owned-профиля. Ветка `codex/p08b-owner-hold-four-composition` от
`codex/build-c-night-workspace`; main ffce8cb сохранён.

VERIFIED на C runtime `ab7ad10d4a56da6cdfc1e565af22f306f2a46b9c`: focused1 PASS/0ignored/build,
245.57 s driver /194.87 s tests; canonical full1612 PASS/0FAIL/5oldignored/build,
1115.65 s driver /1065.52 s tests;916 raw source файлов до/после совпали.
Outer seal подтвердил пять композиций из одного полного test executable.
Его SHA b0d84816a90f68a740c19bf256fc060b2c9c3d844d2f12d9708b3413c997201e;
production exe SHA `f06f21ae9970244c764e5545c8872c24813b195bb686c71dee8966b6d1872348`;
raw archive SHA `ff083b1957a845e1b03487c8536d4f4689d28355a63947e849099998b7a15654`.

C/D и A/B импортированы из исходных owned-профилей без новых grants. Original
D metadata/DB SHA сохранены отдельно от attested C runtime metadata; sidecar
seed v2 описывает оба контекста, не переименовывает старые hashes.
Настоящий D-выстрел снижает C HP90→60 и AmmoBay60→10; C вручную покидает бой,
получает locked Account, отключается и снова авторизуется под другим SID.
Его тело остаётся в World. Второй настоящий выстрел даёт HP60→0/AmmoBay10→0,
lost[0,4,10], а стрелку два выстрела/90 damage/1kill. Настоящие A/B сохраняют
обе команды в бою. Реальный timer Outcome создаёт один Final4, pressure128
сохраняет completion до native0x57, все четыре проходят результаты1500/1501.

AUTHORED: Session transport/ACK, clock, flat terrain/analytic placement и finite
Aim search. HP, device changes, reservations, Frozen, Completion, Final и
результаты не подставлялись. Native4/Jolt gameplay/audio/UI/ощущения — NOT_RUN.
Историческая точность распределения случайных исходов этим не утверждается.

Изменены test Rust и шесть Python/Node helpers, test registration, ровно один
новый compression namespace и LF attributes. Production authority не менялась.
План сохранён до merge: plans/P08B_OWNER_HOLD_FOUR_COMPOSITION.md.

Команды из C checkout:
```
python -B -X utf8 C:/Users/NSNull/AppData/Local/Temp/wot091-night-workspace-kcadgetk/actual-four-focused01/run.py
python -B -X utf8 C:/Users/NSNull/AppData/Local/Temp/wot091-night-workspace-kcadgetk/full-four01/run.py
python -B -X utf8 C:/Users/NSNull/AppData/Local/Temp/wot091-night-workspace-kcadgetk/full-seal38/seal.py --evidence C:/wot091-night-20261017-01/w/local/evidence/20261017-c-owner-four-full01
```
Каталоги output эксклюзивны; повтор требует новых имён. Доказательства:
`local/evidence/20261017-c-owner-four-full01/` и соответствующие пять
`local/test-runs/*/run-*/parent-control.json/result.json`. Inner PENDING не
переписаны: их подтверждает независимый outer composition-full.json.

Откат — не запускать эту ветку или обычным revert убрать её test commits;
данные/клиенты не восстанавливать поверх новых расходов. Оригинал клиента,
D checkout/DB, CoreV7 и main не изменялись. Приёмка software PASS; mandatory
native родительских карточек открыта, в main не сливать. Следующий шаг —
отдельная карточка гаражного Fresh32/03 с genuine Loss4 и Hold5 Job proof.
