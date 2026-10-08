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

Read-only static audit дополнительно закрепил исходники #717: `ussr/list.xml`
SHA256 `167a637d725a233d42e52bd7d5bac00b9af45c0ef225163ab578e202454f5138`,
`ussr/is8.xml` SHA256
`73ea8ffa6b7f0522962d7ab5631eaaeeaa05d74f5b20b6c153c8f9feca3cb4be`,
`ussr/is-7.xml` SHA256
`8d55fa4657a88f1436cd164afe11bade875a906fa7b97256f1fb2f803b09c10d`. В
`catalog-research.v1` у `ussr-is8` есть переход `gun-2 → vehicle-ussr-is-7`,
а `ussr-is-7` терминальный. Это объясняет «нет продолжения ИС-8» при выборе
ИС-7: направление связи обратное.

Статический native-аудит уже установил predicate: `NationTreeData.load`
отбрасывает `item.isHidden`, а `Vehicle/FittingItem` получают это состояние из
`shop.items.notInShopItems`. Receipt:
`local/evidence/20261007-native-tree-filter-01/predicate-01.json`. Поэтому
отсутствие купленного МС-1 в нативном дереве — `PASS_STATIC_NATIVE_FILTER`, а
не повод удалять узел из полного каталога. Полный native payload/callback
исследовательского окна остаётся `NOT_RUN`.

## Контракт

`content-import.v1` состоит из target, hash конкретного source bundle,
provenance, typed records и explicit `missing` entries. Records не могут
ссылаться на неизвестный content ID или запись другого kind. Bounds, transforms,
armor meshes и spawn/base positions проверяются до выдачи canonical report.

## Evidence

Synthetic self-contained receipt: `local/evidence/20261007-p04-content-import-02/result.json`.
It records a verified `server-content.v1` fixture, six typed records, strict
`v.0.9.1 #717`/RU `test_lab` scope, real `triangle_mesh.v1` parsing, bounded
source/depth/aggregate geometry checks, reciprocal compatibility and the
canonical import hash. The receipt reports `data_complete=true` while
`runtime_ready=false` and `runtime_eligibility=NOT_RUN`; the fixture is not a
claim about the complete #717 catalogue or native physics.

### Receipt recheck — 2026-10-08

The original self-contained receipt was re-read from the current checkout. Its
historical importer command and bundle/import/map suite both passed:

```text
python -B -X utf8 tools/content_import.py --manifest local/evidence/20261007-p04-content-import-02/manifest.json --bundle local/evidence/20261007-p04-content-import-02/fixture-bundle
PASS_TYPED_IMPORT_VALIDATOR; canonical_sha256=a1b1191b29bbae5e2aed2f4417a139c7e9a2e6740ec40698347ad6baa8aac2b9
python -B -X utf8 -m unittest tests.test_content_bundle tests.test_content_import tests.test_map_geometry
Ran 38 tests — OK (historical receipt recheck)
```

The receipt `result.json` SHA-256 is
`80a34c538ee66c6a60f03b27d5b823dc85ddb7338ab630b897e28af7c159042f`, and its
`unittest-targeted.txt` SHA-256 is
`92503e558f49ebbc037ae39b9d46ac244e60e351a5e11dcac5c4517e08f0dca2`.
This is a local ignored evidence artifact by project policy, so a clean clone
must recreate or restore it before running the CLI. The recheck changes no
runtime eligibility: `runtime_ready=false`, `runtime_eligibility=NOT_RUN`, and
native compatibility remain explicitly unverified.

### Strict bundle-boundary recheck — current evidence

The follow-up strict reader hardening is the authoritative current P04
boundary. `tools/content_bundle.py` rejects duplicate keys, non-finite JSON,
excessive nesting/item counts, boolean-as-integer values and non-lowercase
SHA-256 values before the typed importer consumes the bundle. The current
combined suite is **42 tests, 0 failures/errors, 0 skips**. Its receipt is
`local/evidence/20261008-p04-bundle-hardening-01/recheck.json`, status
`PASS_P04_BUNDLE_STRICT_RECHECK`, SHA-256
`8d07c77de1a01c39c92e9153f4c3e7f4c08fabf6c4c632a1cbdc20db571e9685`.
The canonical typed import hash remains
`a1b1191b29bbae5e2aed2f4417a139c7e9a2e6740ec40698347ad6baa8aac2b9`.
This closes the bounded parser/evidence seam only; complete #717 content,
native selection and physics remain `NOT_RUN`.

## Статусы доказательств

- `VERIFIED`: структура и hashes existing portable bundle, 33 targeted unit
  tests (one known skip), JSON mesh and boundary rejection checks.
- `OBSERVED`: native IS-7 model/selection screenshot and trace from
  `local/evidence/20261007-p03i-vehicle-profile-loadout-01/native-selection-07`.
- `INFERRED`: typed cross-record schema is a project boundary, not a reverse
  engineered client serializer.
- `UNKNOWN`: complete #717 vehicle/module/shell catalog, historical armor
  surfaces/materials, all map meshes and native selection-to-battle handoff.

## Не утверждается

Canonical output of this validator is not native-client compatibility, physics
equivalence, ballistic correctness, historical provenance or license clearance.
Real dataset import, map/armor checkpoints and native selection callbacks remain
`NOT_RUN`; `runtime_ready` is intentionally never inferred by this card.
