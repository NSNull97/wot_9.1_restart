# P04 — typed content import contract

## Цель

Зафиксировать bounded `content-import.v1` для данных техники и карт. Импорт
должен ссылаться на уже проверенный `server-content.v1`, сохранять provenance и
явно сообщать отсутствующие поля. Этот этап не включает импорт всего клиента,
поддержку боя, экономику или выдачу неизвестной брони как «100 мм».

## Последовательность

1. Реализовать строгий JSON reader с отказом от дублирующихся ключей,
   нечисел, traversal и oversized входа.
2. Проверить top-level target/source bundle и typed records: vehicle, module,
   shell, map, armor и material.
3. Проверить ссылки между записями и content IDs исходного bundle; не
   восстанавливать отсутствующие данные молча.
4. Нормализовать порядок set-подобных массивов и выдать canonical SHA256,
   чтобы повторный импорт одного набора был сравнимым.
5. Добавить отрицательные unit-тесты для границ, ссылок, AABB, spawn/base,
   armor triangle и explicit missing report.

## Разрешённые входы и выходы

- `tools/content_import.py` — только локальный manifest и read-only
  `server-content.v1` bundle.
- `tests/test_content_import.py` — синтетический portable bundle; оригинальный
  клиент и deployed service не открываются.
- `docs/research/P04_CONTENT_IMPORT.md` и `docs/evidence-index/P04.md` — границы
  доказательств и воспроизводимая квитанция.

## Приёмка карточки

`PASS_TYPED_IMPORT_VALIDATOR`: валидный manifest импортируется, canonical hash
совпадает при повторном запуске, а каждый отрицательный пример завершается
явной ошибкой. Реальный полный dataset #717, native geometry checkpoints,
броня и ручной бой остаются `NOT_RUN` до отдельного закреплённого источника.

## Риски и откат

Нельзя расширять schema за счёт client-specific эвристик без отдельного
исследования. Откат — revert единственного P04 commit; bundle и клиентские
копии не меняются.
