# P09A — NationObjDumper static output research

Date: 2026-10-08, Asia/Yekaterinburg. This is a read-only source-boundary
research card. It does not decode a packet, import client Python, start a
client/service or assert that an account payload has this shape.

## Evidence and status

| Claim | Status | Evidence | Limit |
|---|---|---|---|
| Both permitted #717 `dumpers.pyc` copies match SHA `09d86ed36847190f41719e95651b43852bdeba10ffeb1430917669ac3e20c8fc` | `VERIFIED_STATIC` | `tools/nation_dumper_static_audit.py`; receipt below | Bytecode provenance only |
| `NationObjDumper` envelope has `nodes`, `displaySettings`, `scrollIndex`; defaults are empty list, empty dict, `-1` | `VERIFIED_STATIC` | Hash-bound `dumpers.pyc` disassembly and `shape` in receipt | Does not prove wire or Scaleform transport |
| `dump` maps each node through `_getVehicleData(node, data.getItem(node['id']))`, copies `_scrollIndex`, updates display settings for `SelectedNation.getIndex()` and returns the cache | `VERIFIED_STATIC` | Same receipt | No measured native callback bytes |
| `_getVehicleData` emits the thirteen listed node keys and the statically visible value sources | `VERIFIED_STATIC` | Same receipt | Python value types and nested objects remain unknown |
| Account/shop payload, native callback, rendered visibility and server handoff | `NOT_RUN` / `UNKNOWN` | No native capture in this card | Requires owner-gated research-copy run |

## Bounded shape

The static result contains these envelope keys:

`nodes`, `displaySettings`, `scrollIndex`.

Each node map contains, in the observed order:

`id`, `state`, `type`, `nameString`, `primaryClass`, `level`, `longName`,
`iconPath`, `smallIconPath`, `earnedXP`, `shopPrice`, `displayInfo`,
`unlockProps`.

Static value sources are recorded without assigning a guessed serializer type:

- `id`, `state`, `earnedXP`, `displayInfo` come from the node mapping;
- `type`, `nameString`, `level`, `longName`, `iconPath`, `smallIconPath` come
  from item attributes;
- `primaryClass` comes from `_vClassInfo.getInfoByTags(item.tags)`;
- `shopPrice` is a three-tuple of buy-price credits, buy-price gold and either
  the action tooltip or `None`;
- `unlockProps` calls the observed `_makeTuple()` method.

The nested `displayInfo` and `unlockProps` values, account ownership policy,
`notInShopItems`, revision/cursor fields and the bytes sent to Scaleform are
outside this static audit. The result must not be used to manufacture a native
account response.

## Tool and receipt

`tools/nation_dumper_static_audit.py` uses strict bounded UTF-8 JSON with
duplicate-key and non-finite rejection, depth/record/instruction limits,
source-pool checks, path containment and independent #717 source hashes. It
does not execute code. Targeted tests are in
`tests/test_nation_dumper_static_audit.py`.

Receipt: `local/evidence/20261008-p09a-nation-dumper-static-01/receipt.json`,
status `PASS_STATIC_NATION_DUMPER_OUTPUT`, SHA-256
`6bb18e6f7662f822913d6c5f03def51be9b15d42f7660c2c75e28a53e4afe261`.
CLI output SHA-256:
`61787e7303f0b6cbbf9f43d66f7d44f113108de724c013ad3d978ebed7e5fd81`.

## Limits and rollback

This card does not close native account/shop payload, callback framing,
research-tree screenshot correlation, visibility policy, server handoff or
battle admission. Those remain `NOT_RUN`. Rollback is a reviewed revert of
this tool/test/docs commit plus deletion of the ignored receipt directory;
client, fixture, database and runtime state need no restoration.

## Single next step

Capture one bounded research-copy USSR tree run that correlates the
account/shop payload, the TechTree callback and the rendered screen before
writing a native adapter.
