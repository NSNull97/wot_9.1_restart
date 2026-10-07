# Plan: profile4 r3→r4 semantic diff

## Цель

Добавить bundle-rooted offline verifier для конкретной переходной пары `profile4-r3` → `profile4`, который доказывает ожидаемую семантическую дельту экипажа и боекомплекта, сохраняя identity, vehicle mapping, crew, shop и dossier. Проверка не является native compatibility, battle authorization или live DB проверкой.

## Шаги

1. Зафиксировать хеши исходных verifier/content files и принятого portable bundle в evidence до изменения.
2. Реализовать изолированный `tools/profile4_semantic_diff.py` поверх bounded `Bundle`; сначала повторить accepted profile4 chain, затем применить строгие JSON/payload invariants r3→r4.
3. Добавить unit tests на PASS и отрицательные мутации (identity, IS-7, неожиданные inventory changes, ammo mapping).
4. Запустить новый verifier, прежние content/profile4 tests, layout/compile checks; сохранить JSON evidence и negative control.
5. Обновить research/STATUS только после проверок и выпустить финальный receipt с ограничениями и откатом.

## Границы и запреты

- Не читать SQLite, установленный клиент, live service или native trace.
- Не менять arena/gateway/physics/battle source, старые fixtures и validators.
- Не объявлять native compatibility, настоящий бой или экономическую авторитетность.
- Единственные разрешённые изменения этой карточки: новый offline tool/test/plan/research/STATUS/evidence.

## Приёмка

PASS только если текущий `portable-bundle-05` проходит chain verifier и semantic diff с точными ожидаемыми путями: crew сохранён, ammo добавлен `0→20`, compatibility добавляет точный native mapping, shop/dossier byte-identical, identity/IS-7 стабильны; отрицательная мутация отвергнута.
