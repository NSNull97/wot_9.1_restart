# План карточки: bundle-rooted profile4 chain verifier

## Цель

Проверить принятую MS-1 profile4 immutable chain из portable bundle:
`profile4-r4 → profile4-r3 → profile4-r2 → profile4-r1-catalog2`, включая
`base_profile_sha256`, payload hashes, native export anchors и legacy manifest
hashes. Проверка должна работать только по bundle content IDs и не открывать
live SQLite, project config, установленный клиент или runtime.

## Границы

- Это verifier/provenance API, не новый profile4 encoder и не native acceptance.
- Старые `web/src/*` validators, `tools/*_state.py`, fixtures и absolute legacy
  receipts не меняются.
- Запрещены credentials, live DB/WAL, client copies и service restart.
- Bundle остаётся `test_lab`, MS-1/catalog revision 2, local-only до license
  decision.

## Шаги

1. Снять read-only baseline текущего bundle/encoder/provenance и зафиксировать
   exact chain anchors.
2. Исправить exporter metadata так, чтобы все chain content IDs совпадали с
   фактическими bundle IDs, затем собрать свежую append-only bundle.
3. Добавить bundle-rooted `profile4_chain.py`, который проверяет ordered
   parent links, profile/base hashes, state/shop/dossier hashes, native export
   hashes, accepted legacy manifest hashes и отсутствие absolute paths.
4. Добавить positive/negative tests, запустить verifier на свежем bundle и
   сравнить все hashes с read-only audit receipt.
5. Записать receipt, limitations и rollback. Ручной клиентский прогон не
   выполнять.

## Откат

Удаляются только новые verifier/test/docs и свежие ignored
`local/evidence/20261006-profile4-chain/`/bundle output. Старые bundle,
fixtures, validators, client copies и live runtime сохраняются.
