# P04 — исследование typed content import

Дата: 2026-10-07. Ветка: `codex/p04-content-import`.

## Что установлено

- `tools/content_bundle.py` уже даёт read-only, hash/size-verified
  `server-content.v1` с относительными путями и provenance.
- `tools/map_geometry.py` уже проверяет экспортированные #717 triangle meshes,
  finite coordinates, indices, zero-area triangles и instance AABB.
- Native selection-07 реально загрузил `ussr:IS-7` (2150 HP, 5 crew slots,
  model loaded), но в текущем профиле зафиксированы incomplete crew и zero
  shells. Это observation гаража, не разрешение боевого входа.
- Tech-tree screenshots показывают отдельный каталог исследования: наличие
  машины в garage не доказывает наличие её узла/ветки в research tree. Полный
  tree import поэтому не подменён данным garage profile.

## Отдельная проверка каталога исследования

Существующий web-артефакт уже содержит полный справочный граф, но это другой
контур данных. По сохранённым SHA из `web/RESEARCH_TREE_REPORT.md`:

- `web/data/catalog.v1.json` — `d66aad60c13d83807f49b1ebfc8cc89f330e658ed3223706169f763052547567`;
- `web/data/catalog-research.v1.json` — `fddd218109633aeb009bfca2859e5da1c4416737a48be71aa63b278a848df698`;
- 374 дерева, 3945 узлов, 2062 перехода; для СССР 85 записей и уровни I–X;
- `ussr-ms-1` имеет корневые модули уровня I и переходы к технике уровня II;
- `ussr-is8` содержит переход `gun-2 → vehicle-ussr-is-7` с 189200 XP.

Следовательно, по имеющемуся справочному графу ИС-8 и уровень I не отсутствуют.
Скриншот нативного окна — `OBSERVED`: его визуальный каталог ещё не получает
этот граф через игровой протокол. Garage ownership и research tree надо
связать отдельной native/UI карточкой; подмена одного другим будет врать.

## Контракт

`content-import.v1` состоит из target, hash конкретного source bundle,
provenance, typed records и explicit `missing` entries. Records не могут
ссылаться на неизвестный content ID или запись другого kind. Bounds, transforms,
armor meshes и spawn/base positions проверяются до выдачи canonical report.

## Evidence

Synthetic self-contained receipt: `local/evidence/20261007-p04-content-import-01/result.json`.
It records a verified two-file `server-content.v1` fixture, six typed records,
the canonical import hash and the zero-missing runtime-ready result. The fixture
is not a claim about the complete #717 catalogue.

## Статусы доказательств

- `VERIFIED`: структура и hashes existing portable bundle, локальные unit tests.
- `OBSERVED`: native IS-7 model/selection screenshot and trace from
  `local/evidence/20261007-p03i-vehicle-profile-loadout-01/native-selection-07`.
- `INFERRED`: typed cross-record schema is a project boundary, not a reverse
  engineered client serializer.
- `UNKNOWN`: complete #717 vehicle/module/shell catalog, historical armor
  surfaces/materials, all map meshes and native selection-to-battle handoff.

## Не утверждается

Canonical round-trip of this validator is not native-client compatibility,
physics equivalence, ballistic correctness, or license clearance. Real dataset
import and map/armor checkpoints remain `NOT_RUN`.
