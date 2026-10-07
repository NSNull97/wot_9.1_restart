# P02 — тестовый ИС-7 в общем аккаунте

**Актуальный итог UI13, 2026-10-04: карточка двух машин и cached relogin
PASS.**125.7657979s ready,586 packets, обе модели/характеристики и цикл,
ToolTip/Awards/native PNG, чистый ручной exit0/11cleanup/rollback.
Полная normal/cached пара UI08→UI13 PASS без очистки profile002.
Отчёт `local/evidence/20261004-p02-hangar-ui/is7-verifier/ui13-reviewed-01/`.
Обычный пакет сейчас003. В дополнительном ручном normal003 владелец открыл
найм экипажа и внешний вид: эти неподключённые окна дали IndexError.
Точные оба профиля после него сохранились. Подробный новый отчёт/команды/откат —
[UI13](P02_HANGAR_UI.md#ui13-ручное-завершение-вместо-таймера).
Дальше документ сохраняет историю, включая прежние PARTIAL и FAIL.

Дата:2026-10-04. Запрос владельца: «также добавь ИС-7 для тестов».
План: [P02_test_is7](../plans/P02_test_is7.md).

**Тестовая выдача и исправленный cached relogin подтверждены настоящим
клиентом; полная приёмка карточки PARTIAL.** UI11: wire/backend/garage/GUI
PASS, обе машины/неизменные данные/0 ошибок/exit0. Общий session FAIL только
по41.173 s непрерывного ready вместо60. UI12 держал готовый ангар657.113 s,
но завершился по720 s таймауту; его exit1/неполный cleanup остаются FAIL.
Исторические UI09/UI10 зависания устранены двумя узкими серверными правками.
Генераторы, клиентские исходники и кэш при этих исправлениях не менялись.

Здесь `E` означает `local/evidence/20261004-p02-hangar-ui/`, `U` —
`local/evidence/20261004-p02-unified-account/`. Пути считаются от корня проекта
`D:\WoT_9.1_Server`. Эти локальные материалы игнорируются Git. Приведены
хеши и расположения доказательств, без паролей, токенов и ресурсов клиента.

## Что реализовано и где проходит граница

VERIFIED по исходникам и журналу: новый `web/src/test-garage.mjs` предоставляет
отдельную локальную CLI выдачи конкретному уже существующему UUID. HTTP-маршрута
выдачи нет. Требуются остановленный игровой сервис, свободные собственные порты,
общий `supervisor.lock`, ожидаемый SHA точного `profile_json`, явное время и
новый каталог журнала. Identity читается через существующий read-only reader.
Операция не создаёт пользователя и не меняет способ авторизации.

Перед изменением используется согласованный SQLite-снимок `VACUUM INTO`.
Публикуется новый immutable `r2-catalog3`, затем транзакция compare-and-swap
меняет `profile_json` ровно одного UUID/nativeID. Внутри транзакции проверяется,
что остальные строки не изменились. Старые representations сохраняются.
Повтор той же команды возвращает `ALREADY_GRANTED`; второй ИС-7 не возникает.
Сбой после commit до записи receipt имеет отдельный проверенный путь
восстановления журнала, без повторного изменения профиля.

`web/src/game-adapter.mjs` понимает profile2 только при явном pinned-поле
`test_garage` в конфигурации bridge. Оно содержит `version: 1`, абсолютный
локальный путь `native_is7` и его SHA256. Bridge проверяет уже опубликованный
snapshot и не генерирует новый инвентарь при входе. Старый profile1 остаётся
поддержан. Кабинет `web/views/account.ejs` выводит весь серверный inventory
вместо прежнего единственного `inventory[0]`; EJS escaping сохранён.

Новый `tools/test_garage_state.py` формирует только проверенную разницу
profile1 → profile2, используя родные descriptors. Исторический
`tools/hangar_state.py` не изменён. Доменный snapshot2, native Account sync
revision1, каталог3 и dossier cache version1 — разные версии разных слоёв.

| Доменный экземпляр | Native inventory ID | Native type CD | HP | Состояние |
|---|---:|---:|---:|---|
| `<UUID>:starter-vehicle-v1` / `vehicle:ms1` | 1 | 3329 | 90 | Сохранён |
| `<UUID>:test-is7-v1` / `vehicle:is7` | 2 | 7169 | 2150 | Явная тестовая выдача |

Native ID хранятся в слое совместимости. UUID, nickname, native databaseID,
дата создания аккаунта, ресурсы, нулевая статистика и все прежние поля МС-1
сохраняются. У ИС-7 нулевой опыт, пять незаполненных мест экипажа и пустой
боекомплект. `CREW_NOT_FULL` — ожидаемое состояние; готовность боя не заявляется.
В каталог добавлены только ИС-7 и пять его установленных видимых модулей с
ценами из конкретного исходного клиента. Справочная цена не включает покупку:
покупки, продажи, смена модулей и бой остаются недоступны в этом стенде.

Схема, ограничения размеров и происхождение полей:
`E/is7-generator/SCHEMA.md`, `E/is7-generator/RESULTS.md`,
`E/gui-analysis/test-garage-01/REPORT.md`.

## Происхождение данных ИС-7

VERIFIED: исходные XML проверены в разрешённой original-копии. OBSERVED:
в UI06 родной `VehicleDescr` реально экспортировал `ussr:IS-7`, type CD7169,
HP2150 и пять ролей экипажа. Экспорт не менял выбранный МС-1.

- `E/ui06-catalog2-manual-runtime/original-vehicle-is7.json`: 1290 bytes,
  SHA256 `4b24a59c5344808018caf438c044d31d86cf1da20c8b2cbd58f93b8ab2f859b1`.
- `E/ui06-catalog2-manual-runtime/native-84612-1791125424030.jsonl`, строка171,
  `original_vehicle_export` при16.3809513 s. SHA256 трассы
  `95c35236266dc1d41d1b4329b82701f63cc411121e5dd9e7773c4ea31bd3924b`.
- XML `res/scripts/item_defs/vehicles/ussr/is-7.xml` original-копии:
  SHA256 `8d55fa4657a88f1436cd164afe11bade875a906fa7b97256f1fb2f803b09c10d`.
  Узлы/ID шасси, двигателя, бака, радио, башни и орудия перечислены в
  `E/is7-analysis/original-is7-static.json`.

Пустое native vehicle dossier имеет70 bytes и version81. Генератор сохраняет
его нулевую историю и меняет только creationTime на явное время выдачи.
Сервер отправляет `(1, [(7169, grantSeconds, descriptor)])`: owner здесь
type CD7169, не inventory ID2. Version1 — собственная политика этого сервера,
а не якобы найденная константа исторического сервиса. Старое account dossier
и прежнее отсутствие записи МС-1 сохранены.

## Фактическая выдача и контроль сохранности

OBSERVED: операторская выдача выполнена для собственного тестового аккаунта
`c5326cc1-8524-479c-8bba-72e973489c22`, nickname `sr_ascii_f4d1e9`, nativeID1.
Время операции `1791128141411` ms — `2026-10-04T15:35:41.411Z`.
`E/is7-primary-operation-01/result.json` имеет статус
`PASS_SERVER_GRANT_ONLY`; повтор в `repeat.stdout.log` — `ALREADY_GRANTED`.
Их первоначальные `native_compatibility: NOT_RUN` сохранены: последующие
native-доказательства находятся в отдельных отчётах, старые записи не переписаны.

| Объект | SHA256 |
|---|---|
| Точный профиль до выдачи | `7ae8e337e3b490dcdf7ac67b8d31a9b5c885cbb82c44d5fa76d87e46b061cf95` |
| Точный профиль после выдачи | `31a2d6f0427f14536371568387ccfb4acefe874934527b85f18932bcf68ccbdc` |
| `E/is7-primary-grant-01/prepared.json` | `38528dcd834d0012e5c25624b81121c439eca432f48cdd2b6e791c1a15b92326` |
| Реальный `r2-catalog3/manifest.json` | `3de57cf5719c8159a5a5dd7c96080168b15cde3fe2ecf76dd2c29993ad32ba21` |
| `state.bin`,1202 bytes | `d787f71c0643d9088a7a12e1897e244930d1a1628b118881966f7df26d55e6b6` |
| `shop.bin`,507 bytes | `b8bd4a9c23a5b58c28d0838a5eab5c3f99c707ce2d496dd3747f9fb8e344c467` |
| `dossier.bin`,92 bytes | `eb1fa654c81a9888885752278e426308274b1007bd27da6b03128b77759afa09` |

Representation:
`local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r2-catalog3/`.
Журнал содержит before/after, согласованный `game-before.sqlite`, hash-bound
provenance, `prepared.json` и `committed.json`. Снимок до интеграции исходников
и двух БД: `E/before-is7-01/`. Шаблон кабинета отдельно сохранён в
`E/gui-analysis/test-garage-01/account.ejs.before` с записью исходного SHA.

`E/accounts-after-ui07-01/account-state.json` используется как baseline.
После выдачи и после двух попыток native-входа primary имеет100000 кредитов,
0 золота,0 свободного опыта и0 боёв. Второй аккаунт nativeID2 имеет только
свой МС-1; его profile_json не изменён. Совпадение профилей проверяется
отдельно от счётчиков входа: изменение rate-limit counters не выдаётся за
изменение инвентаря и не мешает целевому откату.

## Реальный сайт: proof1 и proof2

OBSERVED: `E/is7-live/website_proof.py` выполнил две обычные HTTP-авторизации
существующих собственных аккаунтов на `http://127.0.0.1:3091`. Новых регистраций
и вызовов `/internal/native/login` этот helper не делал. Он прочитал `/api/game`
и настоящий HTML `/account`, сопоставил subject с текущим аккаунтом и проверил,
что query с чужим UUID не переключает subject. Primary получает обе машины,
secondary — один МС-1. Второй проход использовал те же cookies в памяти.

| Проверка | Время UTC | Результат | Доказательство |
|---|---|---|---|
| Сайт после grant,2 новых web-login |15:40:20.447562| PASS | `E/is7-live/run-01/proof1.json` |
| Сайт после UI08/UI09,0 новых login |15:54:59.560740| PASS | `E/is7-live/run-01/proof2.json` |
| Primary identity/resources/statistics/МС-1 сохранены | Оба прохода | PASS | `grant_preservation` обоих отчётов |
| Secondary profile неизменён, чужой UUID не меняет subject | Оба прохода | PASS | `accounts`, `comparison` |
| Реальные строки inventory в HTML | Оба прохода | PASS | `proof{1,2}-*-inventory.html` |
| Визуальный рендер сайта браузером этим helper | — | NOT_RUN | HTTP/HTML не заменяют просмотр пикселей |

SHA256 proof1:
`bc2e79de00e2cc8639084de41f71d150837e3c703582376d83cc48dab498e357`;
proof2: `2118cafd378d6238232fc83eba3a3a9259d52001a423ff098e63e2bddeeb5228`.
В обоих проходах hash game_profiles равен
`8e4c284202d750345d7ff1d7a4daf773910b135a9b57925d7902b3c5c50c28fe`,
hash неизменяемых полей identity равен
`45c752341d6442a59e31b89c56fbf7ede475198acb69da84e9065be4ed73c7c1`.

`E/is7-live/run-01/outcome.json`: `PASS_WEBSITE_AND_PRESERVATION_ONLY`,
helper exit0. Пароли, cookies, CSRF и полные auth-ответы не записаны в отчёт;
HTML-доказательства ограничены строками inventory. Сайт PASS не закрывает
native relogin: это прямо отмечено в `native_scope`.

## Настоящий клиент: UI08 PASS и UI09 FAIL

Оба запуска использовали настоящий #717 EXE в research-копии, обычную установку
без control/autologin/autoquit и изолированный `local/client-profile-002`.
Мышь и клавиатура оставались у владельца. EXE SHA256:
`86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed`.

**UI08 — PASS первой native-сессии и двух машин.** Независимый отчёт:
`E/is7-verifier/ui08-reviewed-02/test-garage-verification.json`.
357 raw packets проверены по hash; исходные Account stream callbacks,
ресурсы, статистика, header и оба родных model descriptors подтверждены.
Непрерывный готовый ангар до Profile наблюдался74.3364496 s при пороге60 s.
Зафиксирован ручной цикл МС-1 → ИС-7 → МС-1 → ИС-7 и оба локализованных
названия. 0 свежих Python-ошибок, exit0,11 cleanup stages и client restore PASS.

Просмотренные root native PNG привязаны к trace/observation, а не просто к
имени файла: `E/ui08-is7-normal-runtime/screenshots/vehicle_1_002.png`
SHA `19f3081ecd0e2c10f22446c8e813086f8fca38b56fa1bf3b8f6a38840bbb8d42`,
`vehicle_2_005.png`
SHA `390ede122de52c81f7725d4b550a46abe65119986cfc138a9dfe4a960dce0bac`.
Доказательство просмотра: `visual-review-garage.json`; SHA native trace
`7c4d7fec4087855cb7507cb3f9f7a86cee7a1eccaff0db09afdba78cd0205265`.
Awards callbacks и пиксели PASS. Все7 опоздавших tooltip PNG честно записаны
как misses: tooltip visual и полная GUI-приёмка **NOT_RUN**. Поэтому верхний
`status` UI08 остаётся NOT_RUN при `session_status` и `card_garage` PASS.

**UI09 — FAIL повторного входа.** Отчёт:
`E/is7-verifier/ui09-failed-cache-01/test-garage-verification.json`.
Клиент прошёл auth, затем отправил реальный bundle158 bytes:

```text
CMD100(0, -1176871600, 0)
CMD300(0, 518, -846328027)
CMD600(1, 1791128141, 0)
```

VERIFIED по сохранённому packet367: strict Account parser отверг непредусмотренные
cached fields первых двух команд; CMD600 соответствует выданному dossier.
Bundle целиком не был применён/ACKed. Последующие retransmission/piggyback
достигли установленного ограничения вложенности. Это не основание увеличивать
лимиты парсера. Root/wire/data исследуют исходные AccountSyncData/Shop и узкую
выдачу полного authenticated snapshot для такого запроса.

Доказательство: `E/wire-analysis/ui09-cached-sync-01/diagnosis.json`,
SHA `5df5ffde5b299ceb69fab0b98bd03dbf9791fcfc8445098ccefa64edccd9f10e`;
packet367 SHA `e6cafe664030027d263cbc0e7b2592cfc7cf8e9eb83b7ad848c2a6d997a25110`.
UI09 завершён пользователем, exit0/restore PASS,0 свежих Python-ошибок;
это не исправляет FAIL транспорта. Все747 packets и исходный отказ сохранены.
Повторное доказательство на **том же профиле с теми же кэшами** пока NOT_RUN.

## Исходники и выполненные локальные проверки

Read-only review после реальных запусков подтвердил совпадение следующих
исходников с `E/gui-analysis/test-garage-01/final-source/handoff.json`.
В этой финализации изменён только данный отчёт; source/БД/клиенты не менялись.

| Файл | SHA256 |
|---|---|
| `web/src/test-garage.mjs` | `86f946a10ee4d2a4088cf73df18c0dd4286807a500b8aeacfedf0a527a0c40e3` |
| `web/src/game-adapter.mjs` | `4b14b78ed9072ef489795f7a7ade27985a53973a05a60e77ff8e76836e57e6ae` |
| `web/tests/test-garage.test.mjs` | `91018bd8744963ca70f9bbca5a769ca39a8521083aab7d5d39a77b2b5134f94c` |
| `web/views/account.ejs` | `aa19ec5507ca65db0be380432bbe9fc4d6d3a0aae3d4ba1544b59ff24d7e4b39` |
| `tools/test_garage_state.py` | `dec1f884dd8b22ef0d4a6c21389cb37c075f008feb6a12bc7d43888c5b4c5825` |
| `tests/test_test_garage_state.py` | `fca8780c7dce83dfe49344ae7944f4aa1482baab23dec42ae40e3ffadd9c25c2` |
| Неизменённый `tools/hangar_state.py` | `ac60b6ea2be39eaa59327ef1eefb935595e8111ff13a12720ed3a3ebf02c7e79` |

Новый generator test-файл: `tests/test_test_garage_state.py`. Его источник и
compile hash закреплены в `E/is7-generator/source-freeze.json`. Независимый
verifier и его тесты описаны отдельно в `E/is7-verifier/RESULTS.md`;
исправление cached sync развивается отдельно и этим списком не замораживается.

| Проверка | Результат | Сохранённое доказательство |
|---|---|---|
| Targeted grant/storage/CLI/bridge/EJS tests | PASS7/7 | `E/gui-analysis/test-garage-01/node-grant-final-02.tap` |
| Полный Node suite | PASS65/65,0 skips,exit0 | `node-full-final-02.tap` в том же каталоге |
| Node syntax/whitespace | PASS | `final-source/handoff.json` |
| Encoder, отрицательные delta/bounds/provenance проверки | PASS14/14 | `E/is7-generator/unit-tests-02.log` |
| CLI promote и2 generate, детерминированные payload | PASS | `E/is7-generator/candidate-02/candidate-verification.json` |
| Реальная выдача и её повтор | PASS | `E/is7-primary-operation-01/` |
| Реальный откат данной primary-выдачи | NOT_RUN | На аккаунте ИС-7 оставлен |
| Откат после изменённых counters/другого профиля в отдельной SQLite | PASS | Targeted7 tests |
| Пара native first entry + cached relogin | FAIL / повтор NOT_RUN | UI08/UI09 отчёты выше |

Существенные отрицательные тесты: занятый порт/lock/running service;
чужой UUID, неверный expected SHA, изменённая identity; повреждённые fixture,
backup или journal; скрытое изменение ресурсов/истории; rollback с более новым
target profile; восстановление потерянного receipt; явный regrant новым журналом.
Тесты используют отдельную настоящую SQLite, реальный encoder, HTTP bridge и
EJS. Они не изображают проверку совместимости с native-клиентом.

Исторический FAIL65-suite сохранён как `node-full-final.tap`:61 PASS/4 FAIL
из-за Windows `fsync` read-only backup handle. Исправление открывает только
новый собственный backup как `r+` перед flush; ошибка не скрыта. После этого
выполнен конечный65/65. При подготовке данного отчёта тесты не повторялись:
исходники с момента этих проверок не изменились.

## Точные команды воспроизведения

Команды выполняются из `D:\WoT_9.1_Server`. Проверки создают только свежие
временные данные под `local/web/tests/`; native запуск остаётся отдельным шагом.

```powershell
node --check web/src/test-garage.mjs
node --check web/src/game-adapter.mjs
node --check web/tests/test-garage.test.mjs
node --test --test-concurrency=1 web/tests/test-garage.test.mjs
node --test --test-concurrency=1 'web/tests/*.test.mjs'
python -m unittest discover -s tests -p test_test_garage_state.py -v
```

Фактически выполненная grant-команда ниже. Её повтор допустим только при
закрытом клиенте и остановленном игровом сервисе; с текущим журналом ожидается
`ALREADY_GRANTED`. Она не является командой выдачи другому аккаунту.

```powershell
node web/src/test-garage.mjs grant --service local/server/service.json --account-id c5326cc1-8524-479c-8bba-72e973489c22 --native-is7 D:\WoT_9.1_Server\local\server\native-is7-descriptors.json --granted-at-ms 1791128141411 --expect-profile-sha256 7ae8e337e3b490dcdf7ac67b8d31a9b5c885cbb82c44d5fa76d87e46b061cf95 --journal local/evidence/20261004-p02-hangar-ui/is7-primary-grant-01
```

HTTP proof можно повторить только в новом output-каталоге, при уже запущенных
собственных сайте/bridge. Вторая фаза ждёт отдельный `continue.request` после
реального native-run; elapsed time не заменяет эту проверку. Точные argv
выполненного запуска и безопасная схема сигнала: `E/is7-live/README.md`.
Private inputs под `U/primary-persistence-credentials.json` не копируются в Git.

Read-only native verification повторяется с новым `--out`:

```powershell
python tools/verify_test_garage.py --install local/evidence/20261004-p02-hangar-ui/ui08-is7-normal-prepare --registration local/evidence/20261004-p02-unified-account/operator-email-binding-01/registration.json --credentials local/evidence/20261004-p02-unified-account/operator-email-binding-01/test-credentials.json --case operator_shared --fixture local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r2-catalog3 --base-fixture local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r1-catalog2 --private-key local/server/native-private.pem --mode normal --min-ready-seconds 60 --out local/evidence/20261004-p02-hangar-ui/is7-verifier/ui08-review-rerun
```

## Откат: серверный профиль и native-кэш — отдельные состояния

Обычный серверный rollback сохраняет все посторонние аккаунты и текущие
счётчики входов. Он меняет только exact-after `profile_json` этого UUID на
exact-before из проверенного журнала. Изменённый target, исходники, descriptor,
конфигурация или fixture приводят к явному отказу. Полный `game-before.sqlite`
оставлен для отдельно рассмотренного аварийного восстановления; он не
копируется поверх живой БД обычной командой отката.

Ниже только серверная часть отката. Для согласованного отката клиента и сервера
сначала закрыть клиент, остановить сервис и выполнить guarded cache-quarantine
из указанного далее recipe, затем вернуть серверный профиль:

```powershell
python tools/local_server.py stop --config local/server/service.json
node web/src/test-garage.mjs rollback --service local/server/service.json --journal local/evidence/20261004-p02-hangar-ui/is7-primary-grant-01 --expect-journal-sha256 38528dcd834d0012e5c25624b81121c439eca432f48cdd2b6e791c1a15b92326
```

На настоящем primary этот rollback **NOT_RUN**. Команда оставляет snapshots и
журналы, повтор возвращает `ALREADY_ROLLED_BACK`. Rolled-back журнал нельзя
молча использовать для новой выдачи. Протестирован только явный новый журнал
с тем же одобренным временем, дающий тот же immutable representation.

**VERIFIED ограничение native-кэша:** DB rollback не меняет файлы
`local/client-profile-002/account_caches/*.dat` и `dossier_cache/*.dat`.
Original `DossierCache.__sendSyncRequest` line256 offsets19..46 посылает
`CMD600(version,maxChangeTime,0)`. `__onSyncComplete` line205 при смене version
очищает записи, но не сбрасывает `maxChangeTime`; offset185 сохраняет максимум.
`__writeCache` line286 записывает это состояние. Original pyc SHA256
`cde6f8b72c8e83db6b0d7583d3aec008d05b566ec6f412cd6702d7ed9d2edad7`;
байткод/offsets: `E/wire-analysis/dossier-contract-01/` и
`E/gui-analysis/is7-switch-static-01/client__account_helpers__DossierCache.json`.

Измеренный файл именно этого собственного профиля:
`local/client-profile-002/dossier_cache/GEZDOLRQFYYC4MJ2GIYDAMJUHNZXEX3BONRWS2K7MY2GIMLFHE======.dat`,
96 bytes, SHA256
`1d836c556cb373b6b21c133a8793ab51e5b8936c68c82e69c2287747b521c027`.
Он хранит cursor1/1791128141; это не cold cursor прежнего profile1.
Следовательно, команда DB rollback сама по себе не доказывает успешный
последующий native-вход. Точный рецепт подготовлен в
`E/wire-analysis/is7-grant-audit-01/rollback-cache-recipe.md`: закрытый клиент,
STOPPED service, проверка пути/reparse/hash, backup и перемещение только этого
одного файла в новый журнал. Обратное восстановление запрещает overwrite
кэша от более нового запуска. Recipe **не исполнялся**; его выполнение и
native-вход после серверного rollback — **NOT_RUN**. Account/Shop cache-файлы
рецепт не удаляет: их continuation проверяется отдельно исправлением UI09.
Все кэши сейчас сохраняются для честного relogin, не удаляются ради PASS.

Откат исходников выполняется после отката данных, пока доступны проверенные
module/config/source pins. Bridge до интеграции находится в
`E/before-is7-01/web/src/game-adapter.mjs`, шаблон — в указанном отдельном backup.
Сравнить текущие SHA перед восстановлением, затем убрать optional test_garage
из согласованной локальной конфигурации и перезапустить собственные процессы.
Нельзя сначала удалить module/config и затем ожидать, что строгий журнал
примет изменившиеся inputs. Исследовательские клиентские overrides UI08/UI09
уже восстановлены их собственными ledger; это не очистка native profile.

## Исправление сохранённого native-кэша и итог

VERIFIED: original AccountSyncData/Shop/DossierCache и реальные UI09/UI10
пакеты подтверждают initial100(0,persistentHash,0), initial300(0,size,CRC),
600(1,grantSeconds,0), затем100(1,тот же persistentHash,0). Старый parser
принимал только cold initial и refresh с нулевым hash. Три server streams
после первого исправления доходили, но отсутствие последнего no-change ответа
оставляло original ItemsCache в ожидании. Сохраняются оба отрицательных corpus.

`hangar091.rs`/`gateway091.rs` теперь принимают эти bounded варианты только
для interactive profile. Descriptor не является доверенным состоянием:
сервер отдаёт полный собственный immutable snapshot, затем точно
`RES_SUCCESS {'prevRev':1,'rev':1}`. Refresh требует предшествующего initial100,
его же hash, правильной revision/третьего аргумента/уникального request ID.
Неверный пакет отвергается атомарно; retries проверены. Исторический
account091 parser не расширялся. Fixtures/БД/native cache не переписывались.

Original offsets/hashes: `E/is7-verifier/cached-sync-analysis-02/FINDINGS.md`,
`E/is7-verifier/cached-refresh-analysis-01/FINDINGS.md`,
`E/gui-analysis/cached-lifecycle-01/FINDINGS.md`. Rust61/61 PASS и build PASS:
`E/wire-analysis/cached-refresh-rust-tests-01.log`,
`cached-refresh-rust-build-01.log`, `cached-refresh-source-after-01.json`.
EXE SHA256 `5b1e32b3a4278a0d9310d7a64c1a2df275a05ccaa6bf52e82c6d8699fdae19c9`.
Предыдущие EXE и исходники сохранены в cached-sync/refresh-source-before-01.

UI11 scoped proof `E/wire-analysis/ui11-cached-proof-03/cached-relogin-proof.json`
SHA256 `4c2de7fefeca225157eacbe99a17b93525dbe74e130f8c39f6051ea36d347b9b`:
15/15checks,289 реальных packets,91.319537 s канала,server74/client22,
streams1202/507/92B точно совпадают с grant. Полная проверка с actual PNG:
`E/is7-verifier/ui11-reviewed-final-01/test-garage-verification.json`.
Она сохраняет duration FAIL41.173 s; UI12 отдельно сохраняет timeoutFAIL.
UI12 narrow ready OBSERVED657.1134961 s не является успешным clean-exit run.
Подробная таблица — STATUS и заключительный раздел P02_HANGAR_UI.

Финальная сохранность обоих аккаунтов после UI12:
`E/accounts-final-01.json` SHA256
`c69df430d54fba5d92fd9a5c03de732e8c64d9758a6afba234bad9193eb2e922`.
Точные profile/immutable identity hashes совпали с proof2. Второй аккаунт
не получил ИС-7. Сайт3091 health200; никаких новых auth запросов для этой
проверки не выполнялось. Все236 Python checks выполнены (один initial skip
закрыт отдельным guarded-write тестом), Node65/65 и Rust61/61 PASS.

Один служебный start16:12:07 завершился WinError5 при atomic replace state.json.
Процессы остановлены supervisor, clean retry16:13:41 запустил сервис.
Причина кратковременной Windows-блокировки UNKNOWN; она не скрывается как
успешный первый старт. Логи: `local/server/run-20261004T161207-6ac550/` и
соответствующий supervisor stderr. После retry UI11/UI12 использовали один
gateway; рабочая версия server source и конфигурация не менялись.

## Обычный запуск и оставшиеся проверки

Оставлен `local/client-install-002` на исследовательской копии. Игра закрыта,
сервер/сайт работают. В этом пакете нет control/autologin/autoquit/capture;
отдельный native запуск именно финального конфига после install **NOT_RUN**.
Compiled client modules совпадают с UI11/UI12. Оригинальная копия read-only.
Полный audit/хеши/source delta: `E/final-manifest-02/`, `E/final-audit-03/`.
Контролируемое конечное состояние PASS: original3469 файлов неизменны,
research3480 файлов,17/17 before/backup checks и11/11 own-ledger restores.
Сохранены два точных входных лога, изменившихся между UI04 и UI05; кто их
создал, UNKNOWN. Strict initial baseline FAIL остаётся в final-audit-01.
Отдельный пустой temp replay после UI12 timeout сохранён с хешем и backup,
обратимо перенесён в `E/ui12-timeout-replay-01/`. Последующий audit не стирает
эту историю. Полный список36 изменённых исходников — project-changes.json.

```powershell
Set-Location -LiteralPath 'D:\WoT_9.1_Server'
python tools/local_server.py status --config local/server/service.json
python tools/local_server.py start --config local/server/service.json
Start-Process -FilePath 'D:\WoT_9.1_Server\WoT_0.9.1_RU_0717_research\WorldOfTanks.exe' -WorkingDirectory 'D:\WoT_9.1_Server\WoT_0.9.1_RU_0717_research'
```

Сайт: http://127.0.0.1:3091 . Вход по почте/паролю своей проектной учётки.
Секреты хранятся только в ignored local evidence. При остановленном external
сайте сначала восстановить его по web/README; service start сайтом не владеет.
Client rollback: `python tools/interactive_client.py rollback --out local/client-install-002`.
Откат самой выдачи и native dossier cache описан выше; на primary **NOT_RUN**.

UNKNOWN/NOT_RUN: полный конечный run с60 s до действий, видимым текстом
недоступности оборудования и ручным выходом; все возможные GUI действия;
нативный вход после отката grant. Осталась старая продуктовая подпись в
welcome notification: обнаружена на PNG, массовый ребрендинг сюда не добавлялся.
Экипаж/снаряды/бой/арена/магазин остаются отдельными задачами, готовность боя
не заявляется. Предоставлять дополнительные клиентские файлы не нужно.

**Единственный следующий проверяемый шаг:** один контрольный cached run на
прежнем profile002: измеренные60 s до переключений, обе машины, оборудование/
Awards, возвращение и ручной exit0. Старые FAIL не переписывать, новую фазу
до закрытия этой проверки автоматически не начинать.
