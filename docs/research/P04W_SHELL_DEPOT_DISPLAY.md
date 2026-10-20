# P04W: складские ссылки на шесть снарядов #717

VERIFIED runtime722fcf90636467b2c013335684b08989e08dfa1d,
codex/p04w-shell-depot-display от761abf9. Parent full471ac47:1619/0/5oldignored.
Mainffce8cb не менялся. Цель — показать фактически owned ammo в родном складе.

Original #717 Inventory.requestTableData вызывает ItemsRequester и ShopDataParser
до фильтра inventoryCount. Для перебора требуется itemPrices. Inventory10 уже
передавал настоящие остатки, Research shop не имел этих CD. Исходные PYC изучены
статически без выполнения, packed XML проверен побайтно: USSR shells20468B,
SHAed301edbe07a72b04dc6c6d799bc563de55d0d1f26bd35798354a9f6769e7a96.

Изменены tools/p09e_research_projection.py (import и return), новый
tools/p04w_shell_display.py, новый tests/test_p04w_shell_display.py, три EOL rules.
Добавлены только2570:(0,0),2826:(0,1gold),3082:(8,0),14602:(1118,0),
14858:(0,12gold),15114:(978,0). Нулевая цена2570 — факт исходного XML.
Все шесть попали в notInShopItems; покупка по-прежнему отвергается writer.
Складские количества, loaded, CAS, выдачи и экономика не менялись.

SHOP_REVISION5 сохраняется: проверенный fresh Account запрашивает полную
синхронизацию магазина и заменяет cache. Hot reload открытого окна NOT_RUN.
Неизменные business policy/catalog hashes не являются hash нового serializer.
manifest.files/projected_shop_sha/research-service.shop_sha вычисляются из новых
байтов. Старый same-CAS immutable cache правильно откажет FIXTURE_CHANGED:
нужна свежая publication namespace, старый cache не переписывать.

Фактически на committed722fcf9 выполнены **Python9 PASS/0skip** (1.99s) и
**Web game-adapter11 PASS/0fail/0skip/cancel/todo** (4.58s). Все925 raw source
и заявленные входы до/после совпали, HEAD не менялся. Проверено original
enumeration/cache/цены, hidden flags, отказ conflicting price, прежний полный
shop после удаления ровно шести добавок против независимого baseline23096B
SHA68ae754bf4a61cc457d1568b361aea756a0785b35ad4b0fce3ca0efd68f05f8f.
Web11 создавал свои реальные ephemeral регистрации/SQLite, старые стенды не трогал.

Команды из C:/wot091-night-20261017-01/w:

```powershell
python -B -X utf8 -m unittest discover -s tests -p test_p04w_shell_display.py -v
node --test --test-reporter=tap --test-concurrency=1 web/tests/game-adapter.test.mjs
```

Нужны проверенные C bundle/native blob и original0717 RO. Exact argv/env/input
pins и логи: OS Temp/wot091-night-workspace-kcadgetk/warehouse-promotion55/tests01.
result.json SHAeda0ad72d5e383da8ad3a915d003b91443f4735865d2887beb4d0d8a1195cd66.
Promotion receipt отдельно сохраняет прежние байты и3точных замены.

Targeted software PASS; общий gateway full этого runtime пока NOT_RUN, будет
один совместный final full после следующей legacy карточки. Native Warehouse
UI/остатки/звук/покупка не проверены; покупка остаётся unsupported. В main не слито.
Откат: остановить own services и revert source commit/не использовать ветку;
не откатывать DB или расходы. Следующий шаг — отдельная legacy-entrypoints.
