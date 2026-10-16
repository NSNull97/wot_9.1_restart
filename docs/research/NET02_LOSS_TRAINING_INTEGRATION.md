# NET-02: LAN поверх Loss4, late results и training — 17.10.2026

Software checkpoint, native/two-PC gate открыт. База P10B bce643f,
normal NET merge43790d1 сохранённой ветки b6c294f, технический runtime
`442ce7daeed861b20b3b86168b0c6816ea9efafc`. Mainffce8cb не изменён.
Работа выполнялась по NIGHT_20261017 без ручных остановок до09:00.

VERIFIED: exact union12 сохранил82 текущих source blobs и loss/late/room
hooks. Пятый конфликт research/INDEX сведён объединением обеих записей.
Config-only typed visitor имеет budget28; вложенный game_network декодируется
до Value, с отклонением duplicate keys. Private HTTP REQUEST_FIELDS16 не
расширялся. Три новых regression теста проверяют объединённый full config,
closed nested fields и отдельные config/request budgets.

Network policy остаётся explicit lan_test: canonical RFC1918, numeric Login и
Base на одном host, разные порты1024..65535, advertise точно Base bind,
1..24 точных /32 peers. Ingress allowlist/size precedes capture/crypto/rate;
первый Base принадлежит IP аутентифицированного Login. Все12 loaders/runtime
entrypoints проверяют допустимость режима. Diagnostics/LAB остаются loopback;
private HTTP127 остаётся закрытым. Историческая source-документация:
[NET02_PRIVATE_LAN](NET02_PRIVATE_LAN.md).

Изменены client_patch/project_network.py, project_auth.py, sr_interactive.py
(VERSION8), tools/interactive_client.py; gateway identity/game_network,
redirect, Session и shared server с сетевыми тестами. Изменение retained-C
build helper — отдельная техническая карточка, описанная в
[BUILD_TEMP_EXECUTABLE_REFERENCE](BUILD_TEMP_EXECUTABLE_REFERENCE.md).

Реально выполнено на runtime442ce7d:

- Canonical full: **1573PASS/0FAIL/5 прежних ignored/buildPASS**,709.31s test,
  757.77s driver, **876 raw source files before==after**. Новых ignored нет.
- В том же full снова прошли actual late Runtime→HTTP/SQLite/reopen/pending/
  query1500/ACK1501 и actual Loss4 training Host compensation→same-run room→
  Admit2/ACKlaunch→Finished2/claims released. Child receipts оставлены PENDING;
  успешный полный parent удостоверен отдельным outer seal.
- Python17 новых retained guards +11 старых, network9, prepare5, auth6,
  P10Bclient79, mapdrive64 — PASS без skips на host Python.
- Actual CPython2.7.3: network9/auth6, P10B76PASS+3 прежних host-only skips,
  mapdrive61PASS+3 прежних host-only skips. Это наш код и engine mocks, не
  исполнение оригинального клиента или native приёмка.
- Прежние backend SQL17 (raw source8 subcases), Web4/HTTP3 и oldWeb37 не
  запускались повторно отдельно: **297 файлов dependency
  closure** tools/backend/Web/testhelpers совпали с их проверенными receipts.
  Единственное исключение tools/interactive_client.py относится к client
  prepare и проверено отдельно. Carry-forward явно указан в outer receipt.

Последняя строка dependency closure означает точное сравнение297 файлов,
а не новый запуск прежних backend suites.

Полная команда запуска:

```powershell
$env:RUST_TEST_THREADS='1'
$env:CARGO_INCREMENTAL='0'
$env:CARGO_PROFILE_DEV_DEBUG='0'
$env:CARGO_PROFILE_TEST_DEBUG='0'
python -B -X utf8 local/evidence/20261017-net-retain-driver01/run.py
python -B -X utf8 local/evidence/20261017-net-retain-driver01/seal.py
python -B -X utf8 local/evidence/20261017-net-own16-execution01/run.py
```

Эти fresh-output команды уже выполнены; повторять поверх тех же каталогов
нельзя. Последняя команда выполнила prepare/publish/bind/check/start/probe/
exact stop нового диагностического стенда. Секреты и пакеты не печатались.

Evidence:

- `local/evidence/20261017-net-retain-full01/source-before.json`,
  `source-after.json`, `composition-full.json`; outerSHA
  `125e56a4f47d26803b067aa9314386b74247593467516c8a338db76269e7421f`.
- Gateway exeSHA
  `082217015b1167d300d825b5cd7d9307f08153afa3eaf1f5a7ce64f6438fc4a7`;
  actual C path и allocation/origin/environment/reference pins — в source-after.
- Raw source ZIP создан НОВЫМ файлом в том же owned C Cargo target, SHA
  `68b86504d20ce212d26d313446c5ae1ff16de5cd68f72f3bbe7ece24b11c628f`.
  Старые source archives не перемещались/удалялись.
- `local/evidence/20261017-net-retain-components01/source-after.json`.
- `local/evidence/20261017-net-own16-execution01/result.json` и
  `local/stands/net02-loss-ownhost-20261017-01/runs/own-lan-loss14-01/own-lan-loss4-smoke14.json`.

OBSERVED/VERIFIED actual own-LAN diagnostic: Ethernet7,192.168.1.101/24,
Windows Public profile сохранён; только собственный /32 разрешён. Login20240,
Base20241, privateHTTP127.0.0.1:3492. Оба существующих владельца прошли
реальный encrypted Login→HTTP auth→RunOpen4→decrypted advertised Base→
измеренный21-byte first Base; ответы28/24bytes, correlation/key/handoff
проверены. В новом diagnostic DB A129→130/B43→44, active0/grants0, содержимое
профилей/боекомплект не изменены; исходный loss-01 остался A129/B43. Gateway
BOUND после24.41s, весь operator run73.09s. Exact own PID98836/105456 остановлены.
Smoke receiptSHA `91d340ef82d2fea46742a292cc774f42e7b7608a7e461f42d2aa8f580304cdaf`.

Preflight limitation retained: frozen smoke14 pin ожидал incoming LF hash,
а merge создал140CRLF строк game_network.rs. До запуска обнаружено совпадение
нормализованных bytes; frozen14 не менялся и не запускался. Successor16
закрепил настоящий rawSHA `e3d5cca1c368d981b18b4ca2b64530dde014e96c57cfdc3c3e34451684cbd2f2`.
Это не причина менять исходник после full или подменять raw hash normalized.

NOT_RUN: native V8 install/UI/gameplay UDP, два ПК, peer с другим IP,
firewall/NAT/WAN/hosting. Own-host diagnostic не доказывает inbound LAN.
Агрегатный rate limiter не обещает fair-share. Ни правило Windows, ни профиль
сети не менялись. Seven LAB/new3/WT/FV owned admission не включались.

Откат к P10B bce643f допустим только на quiescent исходниках с совместимыми
данными. Новый diagnostic DB не переносить обратно и не восстанавливать
старую БД поверх потраченных снарядов. Retained C target нужен всем bindings;
его удаление/замена инвалидирует proof. Все службы/клиенты STOP.

Приёмка: SOFTWARE_CHECKPOINT_PASS, NATIVE_NOT_RUN, main без merge. Следующий
шаг — отдельная Hold5 integration и подготовка свежих утренних contexts;
ночь продолжается до09:00, без остановки на ручной проверке.
