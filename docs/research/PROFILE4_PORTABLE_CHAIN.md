# Bundle-rooted profile4 chain

Карточка проверяет только локальную provenance/data-only цепочку принятого
MS-1 profile4 fixture. Порядок цепочки: `profile4-r4 → profile4-r3 →
profile4-r2 → profile4-r1-catalog2`.

## Проверено

- `tools/profile4_chain.py` читает только `server-content.v1` content IDs.
  Project config, installed client, SQLite, live runtime и старые JS validators
  не используются.
- Все четыре profile/base blobs имеют ожидаемые версии и hashes:
  `r4=2610dbd9…`, `r3=5167ea63…`, `r2=31a2d6f0…`, `r1=7ae8e337…`.
- Parent links совпадают по `base_profile_sha256`; account UUID и native DB ID
  стабильны.
- Grant links и monotonic timestamps проверены: `test-is7-v1`,
  `test-ms1-crew-v1`, `test-ms1-ammo-v1`.
- `state.bin`, `shop.bin`, `dossier.bin` для каждой ревизии проверены по bytes и
  SHA256. `shop.bin`/`dossier.bin` сохранены на переходах r4→r3 и r3→r2.
- r2 local preservation receipt сверена с payload hashes. Vehicle mappings,
  crew mapping и точная r4 ammo mapping проверены: shell 2570, turret 5891,
  gun 5892, inventory 1.
- Native crew/ammo export blobs проверены по SHA256 и grant anchors.
- Старый bundle с неправильным порядком metadata (`portable-bundle-03`) служит
  negative control и отвергается.

## Ограничения

Старые `manifest.json` не попали в portable bundle, потому что содержат
absolute paths; их hashes сохранены как legacy anchors. `preservation.json` для
r3/r4 также не переносились из-за абсолютных следов, поэтому их exact replay и
native proof остаются `NOT_RUN`. Hash export blob проверяется, но это не
повтор native UI/client verifier. Эта карточка не создаёт новый profile4
encoder и не доказывает native compatibility, историческую экономику, бой или
15×15.

Receipt и negative control: `local/evidence/20261006-profile4-chain/`.
