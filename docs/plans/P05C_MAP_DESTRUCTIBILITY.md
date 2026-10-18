# P05C follow-up — generic dynamic-object destruction contract

## Цель

Закрыть безопасный серверный срез для разрушаемых объектов, общий для любой
карты. Карта поставляет только source-bound fixture/catalog: идентификаторы,
материал, массу, прочность и разрешённые типы контакта. Серверный domain слой
принимает только ограниченный контактный кандидат от авторитетной физики или
трассы, проверяет его и единожды меняет состояние объекта. Native AreaDestructibles,
рендер, rubble и фактический проход танка остаются отдельными ручными воротами.

## Что уже подтверждено

- **VERIFIED:** `shared::fragiles::State` уже авторитетно ведёт cumulative
  `scene_version`, `removed_ids`, projectile/vehicle contacts и ждёт worker ACK
  до публикации (`server/gateway/src/shared/fragiles.rs`, `server/gateway/src/shared/server.rs`).
- **VERIFIED:** в `main` есть P06N–P06R source-bound срезы whole fragiles, деревьев
  и movement fences; это не full-map acceptance.
- **OBSERVED:** P06R fence-chain может потерять проходимость после последовательного
  контакта; compound structures и их native collision/rubble semantics не приняты.
- **UNKNOWN:** историческая формула прочности/удара 0.9.1 для всех типов,
  `destroyedModules`, смешанный BSP, точные slope/obstacle tree angles и
  полноценный native reconnect.

## Границы этой карточки

Входит:

1. Новый map-agnostic domain contract `dynamic_destructible` с bounded catalog,
   object material/mass/durability/contact policy, server-only contact input,
   idempotent destruction transition и public observer delta без координат,
   HP/массы и скрытых источников.
2. Snapshot/restore только для серверного разрушенного состояния, с проверкой
   catalog revision и object identity.
3. Узкие Rust tests: catalog limits/ordering, material/contact admission,
   duplicate contact, one-time scene version, observer delta privacy, cumulative
   snapshot/reload и cross-map fixture equivalence.
4. Документированный следующий ручной сценарий для source-bound whole/tree/fence
   объектов: `contact → worker ACK → native setter → passage → reconnect`.

Не входит:

- изменение native protocol, AreaDestructibles packet IDs или client resources;
- привязка domain к `MapId`, Prohorovka/Karelia или конкретному native ID;
- compound structures, modules, rubble/material replacement, falling columns и
  undefined catalog rows;
- исторические damage/ram formulas, slope-specific tree animation и заявка
  full-map/native/network PASS.

## Контракт

`Catalog` обязан иметь непустой map asset/revision и отсортированный уникальный
набор объектов с bounded `object_id`, `material_kind`, finite positive `mass_kg`,
positive `durability` и `ContactMask`. `ServerContact` содержит только server
receipt fields: contact id, object id, material, contact kind, source slot, tick,
damage и physics mass/speed. Клиент не может создать этот тип через wire path.

`State::apply_contact` отклоняет malformed/stale/foreign material or contact,
дедуплицирует contact id, не меняет уже уничтоженный объект и коммитит transition
атомарно. Публичная выдача содержит только catalog revision, object id,
scene version и destruction state; координаты, скрытые позиции, HP и массу не
передаёт.

## Проверки и evidence

Автоматический gate — focused `cargo test` для `dynamic_destructible` и обычный
gateway build/test после изменения. Evidence сохраняется в новой карточке под
`local/evidence/<date>-p05c-map-destructibility/`; отсутствие native/client run
помечается `NOT_RUN`, синтетический round-trip не выдаётся за совместимость с
настоящим клиентом.

## Откат и следующий шаг

Откат — reviewed revert единственного commit этой ветки; `main`, `local/`,
оригинальный клиент и старые стенды не изменяются. После автоматического PASS
единственный следующий шаг — владелец запускает свежий source-bound native
сценарий на двух клиентах для whole fragile/tree/movement fence и прикладывает
цепочку `contact → ACK → native publication → passage`; до этого native/UI/
actual destructibility остаются `NOT_RUN`.
