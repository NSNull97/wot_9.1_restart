# P04W: отображение owned снарядов на складе

Parent761abf9, runtime471ac47: canonical full1619/0/5oldignored/build/923raw,
семь actual compositions. Отдельная codex/p04w-shell-depot-display; mainffce8cb
сохранён, ночь до04UTC/09local, native утром. Не добавлять экономику/покупку.

VERIFIED original #717 ItemsRequester/ShopDataParser.iterator требует ammo CD
в itemPrices для отображения inventory10. Проекция inventory уже содержит
остатки, Research shop не содержит ammo refs. Исторические цены шести реальных
MS1/IS7 снарядов проверены по исходному USSR shells XML, SHAed301ed...e7a96.
Нулевую XML цену2570 не заменять выдуманной ценой.

1. Проверить immutable warehouse42 freeze01 и test03 freeze03, прежний
   projection SHAe5a4cf...b55c1. Продвинуть только helper, два hunk projection
   и финальный test03. Сохранить raw EOL bytes через attributes.
2. Добавить ровно шесть source-derived prices и notInShopItems для всех шести:
   2570/2826/3082/14602/14858/15114. Покупки остаются недоступны. Inventory10,
   quantities, CAS, grants, crew и политика магазина5 не меняются. Fresh account
   выполняет полную синхронизацию магазина; hot reload не заявлять.
3. Actual Python9 и Web game-adapter11, source before/after/HEAD/logs. Старые
   business-policy hashes не являются byte hash новой проекции: generated
   projected_shop_sha должен вычислиться заново. Старые immutable cache не
   перезаписывать. Сравнение всего прежнего shop за вычетом ровно шести refs
   с независимо сохранённым encoded baseline обязательно.
4. Сохранить source и результаты отдельным checkpoint. Следующий legacy card
   на зависимой ветке; один совместный final gateway full925 после обеих карточек.
   Mandatory native warehouse UI остаётся NOT_RUN, без merge вmain.

Команды: python -B -X utf8 -m unittest discover -s tests -p test_p04w_shell_display.py -v;
node --test --test-reporter=tap web/tests/game-adapter.test.mjs из project root.
P04D_TEST_BUNDLE/ORIGINAL/WOT091_TEST_NATIVE указывают на проверенные C ресурсы
и original client RO. Все evidence/output новые; старые данные не удалять.

Откат: не использовать ветку либо revert source commits при остановленных
собственных службах. Не откатывать DB ради shell refund. Native утром на новом
namespace: складские ammo позиции и реальные остатки, purchase недоступна.
