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
| `NationXMLDumper` consumes measured nested `unlockProps` indexes and `displayInfo` keys/paths | `VERIFIED_STATIC_FORMAT_ONLY` | Same hash-bound disassembly and nested receipt shape | Format conversions are not a Python or wire serializer; runtime values remain unknown |
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

## Measured nested shape

The same `dumpers.pyc` contains `NationXMLDumper`, which consumes the two
fields after `_getVehicleData` has produced them. This extends the static guard
without assigning a transport type:

- `unlockProps` is read as a four-position result after `_makeTuple()`. The
  builder iterates position `-1`, formats each member with the measured
  `<id>{0:d}</id>` template, preserves `unlockProps[:-1]`, and appends the
  joined text. The node template then consumes indexes `0..3` as
  `parentID:d`, `unlockIdx:d`, `xpCost:n`, and `topIDs:>s`.
- `displayInfo` is copied, then `info['lines']` is traversed. Each line reads
  `inPins`, `outLiteral`, and `outPin`; each input pin reads `viaPins`. The
  measured templates format via-pin positions as `{0[0]:n}`/`{0[1]:n}`, an
  input-pin coordinate and joined child IDs, and the line's output literal,
  output pin, row/column/position and rendered `lines` string.

These are instruction paths and format conversions observed in the pinned
disassembly. They do not prove whether a concrete value is an `int`, `float`,
tuple, list, dict, or a native Scaleform value, and they do not prove callback
bytes or account ownership semantics.

## Tool and receipt

`tools/nation_dumper_static_audit.py` uses strict bounded UTF-8 JSON with
duplicate-key and non-finite rejection, depth/record/instruction limits,
source-pool checks, path containment and independent #717 source hashes. It
does not execute code. Targeted tests are in
`tests/test_nation_dumper_static_audit.py`.

Receipt: `local/evidence/20261008-p09a-nested-shapes-01/receipt.json`, status
`PASS_STATIC_NATION_DUMPER_OUTPUT`, SHA-256
`6a96bf9dc6d926906ae6758ce5db6d261cf387006f93d6ca3b336bcd62cc3e48`.
The receipt includes the seven measured XML format constants and the bounded
nested access shape. The prior envelope-only receipt remains at
`local/evidence/20261008-p09a-nation-dumper-static-01/receipt.json`.

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
