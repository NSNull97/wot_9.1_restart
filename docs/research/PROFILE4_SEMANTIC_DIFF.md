# Исследование: profile4 r3→r4 semantic diff

Дата: 2026-10-06

## Цель

Проверить на принятом `server-content.v1` bundle, что переход
`profile4-r3` → `profile4` добавляет только экипажный боекомплект MS-1 и не
переписывает identity, экипаж, IS-7, vehicle/crew mapping, магазин или dossier.
Проверка offline и bundle-rooted; она не доказывает native compatibility,
боевой loadout gate или работу live backend.

## Источник и классификация

**VERIFIED** — `local/evidence/20261006-profile4-chain/portable-bundle-05`,
manifest SHA256 `d99f2ba765e39d096cf2d0858c9864ed897a36eb9c4ea6972a15385e2355b2db`,
сначала прошедший `tools/profile4_chain.py`.

**VERIFIED** — r4 `base-profile-input.json` byte-identical r3
`profile-input.json`: 1470 bytes, SHA256
`5167ea63f0503952b4ab1e7c4b1ed2dca5e5da6b6812bd476a87124a891e0888`.

**VERIFIED** — обе JSON-пары сохраняют account ID
`c5326cc1-8524-479c-8bba-72e973489c22`, native database ID `1`, ресурсы,
статистику, vehicle IDs/health/xp, crew из commander+driver, `test_grant` и
`crew_grant`; IS-7 остаётся без изменений.

**VERIFIED** — профиль меняет `profile_version`/`snapshot_revision` 3→4,
MS-1 `ammunition_count` 0→20 и добавляет ровно одну строку
`ammunition` для `shell:ms1-stock-ap`; fixture меняет также `fixture_version`
3→4. `ammo_grant` имеет ID `test-ms1-ammo-v1`, parent SHA r3
`5167ea63f0503952b4ab1e7c4b1ed2dca5e5da6b6812bd476a87124a891e0888` и native
export SHA `683daac81143a9d7edfbe671870ba163db088c54f5101fa52e077f596ebbfc74`.

**VERIFIED** — compatibility добавляет только точный `ammo_mapping`:
shell `2570`, turret `5891`, gun `5892`, native vehicle inventory `1`;
vehicle/crew mapping и wire/catalog revisions сохраняются.

**VERIFIED** — state descriptor меняет только MS-1 `shells` и
`shellsLayout`: `[]` → `[2570,20,2826,0,3082,0]` и соответствующий layout с
`[5891,5892]`. `state.bin` изменился 1284→1329 bytes
(`186518109966a093397a0602e69653886bc8093c082ec35782278f539bc32120` →
`a2858ec04b42c4974332176faa9faee3dc78e5f23cf7e270b70762845e48b14e`).
`shop.bin` byte-identical 507 bytes SHA256
`b8bd4a9c23a5b58c28d0838a5eab5c3f99c707ce2d496dd3747f9fb8e344c467`,
`dossier.bin` byte-identical 92 bytes SHA256
`eb1fa654c81a9888885752278e426308274b1007bd27da6b03128b77759afa09`.

## Реализация

`tools/profile4_semantic_diff.py` сначала вызывает accepted profile4 chain
verifier, затем применяет bounded JSON/payload checks и возвращает
`PASS_PORTABLE_PROFILE4_SEMANTIC_DIFF` с exact `changed_paths`, стабильными
invariants и SHA payload/native export. Unit tests содержат PASS и отрицательные
мутации identity, IS-7 и native ammo mapping.

## Ограничения

- Это проверка экспортированных JSON descriptors и bytes, не декодирование
  настоящего native wire/клиентского Python и не запуск клиента.
- Native crew/ammo blobs проверены по SHA внутри bundle; повторный native proof
  и совместимость с клиентом — `NOT_RUN`.
- Battle authorization, серверная перезарядка, попадания, экономика и live
  persistence — `NOT_RUN`.
- `profile4-r3/r4` absolute preservation evidence не включён в bundle; этот
  diff сознательно не объявляет его доказанным.
- Историческая точность боекомплекта за пределами зафиксированного MS-1 test
  fixture — `UNKNOWN`.

## Воспроизведение

```powershell
python -B -X utf8 tools/profile4_semantic_diff.py --bundle local/evidence/20261006-profile4-chain/portable-bundle-05
python -B -X utf8 -m unittest discover -s tests -p 'test_profile4_semantic_diff.py' -v
```

Evidence: `local/evidence/20261006-profile4-semantic-diff/semantic-diff.json`.
