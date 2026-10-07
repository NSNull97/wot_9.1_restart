# Portable server-content/encoder export

Карточка закрывает только изолированный export/loader для существующей
`test_lab` MS-1 profile1/profile4 closure. Это не native compatibility и не
переключение live backend.

## Что сделано

- `tools/export_content_bundle.py` создаёт свежий `server-content.v1` bundle из
  явно указанной read-only копии клиента и локальных принятых blobs.
- `tools/content_bundle.py` проверяет manifest revision, относительные paths,
  size/digest bounds, source classification/license record и полный набор файлов.
  Loader не читает `config/project.local.json`, SQLite или установленный клиент.
- `tools/portable_hangar_state.py` читает descriptor/profile/packed XML только по
  content IDs bundle и вызывает frozen primitive fixture/encoder. Он scoped к
  проверенному MS-1 catalog revision 2; profile4 chain экспортируется и
  hash-пинится, но не объявляется новым standalone encoder.
- Старые `tools/hangar_state.py`, profile validators и old fixtures не изменены.
  Старые absolute-path manifests не копируются в bundle: их hash anchors входят
  в `metadata/profile-chain` и остаются в прежней evidence receipt.

Bundle содержит 56 blobs: seven measured original-client XML resources, both
native descriptor inputs, crew/ammo exports, accepted profile1 and profile4
chain inputs/payloads, one prior preservation receipt and frozen provenance
metadata. Passwords, email, sessions, SQLite/WAL, live configs and complete
client trees are absent. Resource redistribution remains
`UNKNOWN; local-only non-redistribution`.

## Проверки

```powershell
python -B -X utf8 tools/content_bundle.py --bundle local/evidence/20261006-content-export/portable-bundle-03
python -B -X utf8 tools/portable_hangar_state.py --bundle local/evidence/20261006-content-export/portable-bundle-03 --profile-id profile1 --out local/evidence/20261006-content-export/portable-generation-04
python -B -X utf8 -m unittest discover -s tests -p test_content_bundle.py -v
```

Bundle verification: `PASS_CONTENT_BUNDLE`, 56/56 blobs, encoder revision
`sha256:006b36a8f47687371da935d95ddbfa5a2cc8a1a1dfb041d7875113f2de96bec3`.
Portable profile1 generation: `PASS_PORTABLE_MS1_GENERATION`. Generated
`state.bin`, `shop.bin`, and `dossier.bin` are byte-identical to the accepted
`r1-catalog2` payloads: 1106, 419 and 8 bytes, respectively, with hashes
`aa855586…`, `7576ca75…`, and `70b70fe0…`. A text scan found no absolute client
path in the portable bundle or generated output. The command supplied no
installed-client argument; all reads after export were through the bundle.

## Статус и ограничения

`native_compatibility` remains `NOT_RUN`; no original client received a fresh
portable fixture. Profile4's immutable r4→r3→r2→r1 chain is exported and
anchored, while a general profile4 regeneration API and arbitrary vehicle
closure remain future work. The selected XML/native exports may not be
redistributable; no legal decision was inferred. Historical 0.9.1 gameplay
rules, economy, battle, native transport and 15×15 are outside this card.

Evidence: `local/evidence/20261006-content-export/` contains the read-only
initial audit, before/after manifests, bundle manifests (the `-03` export and
`portable-generation-04` are the current append-only receipts; `-01`/`-02` and
earlier generation attempts are retained as superseded history),
verification and generation receipts. Rollback deletes only the new content-export source files
and ignored evidence bundle; existing fixtures, client copies, live service and
old provenance receipts remain untouched.
