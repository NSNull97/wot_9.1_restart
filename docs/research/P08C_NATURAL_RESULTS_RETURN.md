# P08C — natural Elimination, личная сводка и возврат уничтоженного игрока

## OBSERVED native failure

Владелец подтвердил marker fix на runtime363daa3: оба enemy имени и ромба
красные, движение/наведение работают. Затем первый игрок уничтожил Ёжа.
Личная сводка победителя пуста, но командная таблица содержит90урона/1фраг;
перед итогами виден экран загрузки интерфейса. У уничтоженного игрока чёрный
экран и последующий выброс. Natural results/return gate — FAIL.

Actual run `morning-marker01`, arena9187569394802767952: winner2/Elimination,
A/session1 team2 сделал3выстрела (2КС+1ОФ), B/session2 team1 уничтожен.
Read-only SQL: A120/HP90/damage90/kills1/ammo[0,1,8], B35/HP0/received90/
killer152043525/ammo[0,3,9], active0. Оба own result rows содержат одинаковый
full DTO SHA1f997471e5672a4cf9c667aec050ae95ca9355d247167a7a9f1745d12f48e31e.
Терминалы battle_finished и оба result ACK подтверждены. Это не UI PASS.

Оба Avatar stream100 подтверждены и Account reset поставлены в очередь.
Только A имеет завершённый HANGAR_RETURNED и Account1500 query. B остановился
на warm sync после enableEntities. Own processes остановлены по receipts;
logs/traces/screenshot и consistent RO SQLite backup сохранены в
`local/evidence/20261016-p08c-natural-failure01`. Корневые python.log старые,
не относятся к этому запуску и исключены из причинных выводов.

## VERIFIED measured return record

Actual B clientseq3527 — enableEntities09, принят. Следующий seq3528/169bytes
содержит5байтов авторизации и164байта приложения:

-11байтов Avatar.bindToVehicle: method0d,VAR2 length8, routing старого
 собственного Avatar02=152043522 и единственный OBJECT_ID Vehicle03=152043523;
-153байта обычного Account: CMD100/300/600 requests226/227/228, chat1/10,2/9,3/30.

Штатный parser после enabled=true отправлял0d в hangar::requests и отвергал
весь compound как unmeasured hangar method. Последующие5byte frames — пустое
приложение с авторизацией, а не новые плохие RPC. Канал не продвинулся, затем
idle_timeout. У победителя фактический seq3563 содержит153байта такого же
Account bundle без старого bind и принимается. Cipher packet3528 SHA
ef9b87d728be090aa27866bea7e71d27a29eae3b097211eea0407815153fc259;
token-stripped164B SHA5e8aed252f04679cbc695798a84947794e4b87372d74503969e34017696db8c5.
Original #717 CellMethods/AvatarPositionControl.__doBind90/__doUnbind99
подтверждают routing+OBJECT_ID, а не два аргумента метода.

Узкая правка принимает эту форму только в Returning до warm mask,
после reset ACK+enable, с dead retained actor, correction/binding ACK,
точными старыми собственными Avatar/Vehicle IDs и общим budget32. Это
валидация старого camera record без игровых команд/контроля/публикации.
Driving zero-mailbox validator остаётся отдельным. Unknown records по-прежнему
отвергаются; весь receive/piggyback сохраняет атомарный откат.

## VERIFIED original personal details

Original BattleResultsCache.convertToFullForm176 читает personal.details через
VehicleInteractionDetails.fromPacked().toDict(). Пустая строка допустима, но
даёт пустой словарь. BattleResultsWindow.__populateEfficiency829 строит
карточки именно по нему, а не по public damageDealt/kills. В старом gateway
details всегда emptybytes, spotted всегдаdefault0. Source audit59assertions
не обнаружил общего расхождения81personal/41public/9common/6player.

Packed details: все target IDs <NI>, затем все строки <BbHHHHHHIH>, по20байтов
значений на цель, итого24байта/цель, без count header. Поля: spotted,
deathReason(-1 если не уничтожен),directHits,explosionHits,piercings,damageDealt,
damageAssistedTrack,damageAssistedRadio,crits,fire. Засвет требует собственного
авторитетного журнала наблюдений; попадание не доказывает первый засвет.

## Реализованный кандидат, до fresh native replay

Results7 / Participant19 остаются прежними при отсутствии нового раздела.
Results8 добавляет `interaction_details` version1 с закрытой policy, nullable
spotting policy и ограниченными attacker/target rows. Старые результаты
читаются без backfill; новые подробности сохраняются в том же atomic finish
и читаются через существующий scoped query/ack. Inventory/terminal/CAS не
меняются при query/ack, старые terminal bytes не переписываются.

Персональные строки выводятся из committed Shot/Contact/Impact/Damage/Splash
журналов с проверкой итоговых damage/hit/piercing/kill и received/killer полей.
Первый засвет собирается отдельно только в profile13 visibility_v1 шаблоне:
первое Battle-наблюдение живой готовой цели живым готовым противником;
при равенстве — минимальный domain slot, один credit на цель за бой, максимум6.
Это явная LAB policy, не исторические camouflage/radio правила. Повторные
появления credit не умножают. LOS failure не фиксирует частичные lifecycle/
journal/cursor; World/Trace целиком ради этого не клонируются.

Assists, crit-mask и native fire counter пока не учитываются и должны быть
нулевыми в этой версии; настоящий HP-урон пожара входит в damage journal.
Эти показатели не объявляются принятыми. Доходы/опыт остаются прежней нулевой
LAB policy. Новая версия не восстанавливает отсутствующие подробности старых
боёв. Старый reader Results7 отвергает Results8: откат старого бинарника не
обеспечивает чтение новых итогов; базу ради возврата БК восстанавливать нельзя.

Диагностический canonical focused `p08c_`:43PASS/0FAIL/0ignored/buildPASS.
В него входят6 actual-envelope,13 firstspot pure/actualWorld и11 detail
projector/codec/serde тестов плюс прежние P08C проверки. Отдельные3 настоящих
SQLite finish/query/ack/reopen/failpoint/forgery теста PASS. Полная выбранная
Python матрица результатов/mixed writer/original contract:33PASS,0skips,
379.172s. После focused добавлен один actual World/geometry/fired-journal→
personal81/details тест; он PASS в полном наборе: реальные source contacts,
выстрелы, Trace, damage/spot journals дали90damage/1kill/1spot и согласованный
native81/details. Это World/component proof, не worker/native UI.

Canonical full на `09274f2f273ba07113a50073eb3b7186e978317e`:
**1130 PASS / 0 FAIL / 5 прежних ignored / build PASS**,327.38s tests.
Все689raw source SHA до/после совпали, head во время прогона не менялся.
Executable SHA256 `6de229a078333f064cc84eade21ab6c83bd201339fe58b8e542181fb60784360`.
Новый full build фиксирует `RUST_TEST_THREADS=1`,
`CARGO_INCREMENTAL=0`, чтобы не создавать дополнительный incremental cache.
Evidence: `local/evidence/20261016-p08c-natural-results-fix01`,
`local/build/server/gateway-p08c-natural-full01`. Свежая штатная binding05
создана после полного gate; services/startup `morning-natural01` PASS,
в actual log есть FIRST_SPOT_BOUND с точной policy. Оба клиента последовательно
загрузили fresh native hangar/cache/model,96 installed files unchanged,
база после run_open A121/B36/active0, ammoA[0,1,8]/B[0,3,9].
`ready11.json` SHA256
`92457329c3a9eb74835e8e869bbb1aeadc8ba1bc6c6155001b715d18e5ae2fef`.
Клиентская переустановка, grants и reseed не выполнялись. Вопрос владельцу
на повторное уничтожение отправлен. Native повторная приёмка ещё NOT_RUN;
предыдущий естественный возврат остаётся FAIL до неё.

План — [P08C_NATURAL_RESULTS_RETURN](../plans/P08C_NATURAL_RESULTS_RETURN.md).
Marker
gate остаётся принятым; late manual-leaver append/spawn — отдельные открытые
пункты. Main и ночные ветки не меняются.

## Natural05 прерван автоприцелом

OBSERVED owner: «нажал автоприцел и словил вылет из сессии»; после выброса
у Ёжа открылись итоги с засветом. VERIFIED gateway: arena5172357154243584472,
session1/slot1/team2 — A, session2/slot0/team1 — Ёж; Forfeit после Disconnect A,
оба HP90,damage0,kills0. Natural уничтожение и dead return не состоялись,
статус NOT_RUN_INTERRUPTED. У A собственный full result отсутствует — известный
отдельный early-leaver gap. У B Results8 сохранён/acked, native Avatar100 и
Account query/return присутствуют; B→A spotted1, A→B spotted1/directHits4/
piercings0/damage0. Четыре выстрела A действительно списали1КС+3ОФ.

VERIFIED actual first reject: seq1076, flags0x458, ACK1220, token-stripped
application11B `0c08000000000003001009`, SHA256
`ef7f4c7af5335a14f6b385a3284a78f801fe5e530503224aa98157eca319cf14`.
Encrypted packet007619 SHA256
`6769423feb84f8617be70aa7e3a12b9239e38940d091508114e3ca044a5864a8`.
CellMethods autoAim id12: mailbox0 плюс один OBJECT_ID target152043523,
не два Python аргумента. Driving allowlist не содержал0x0c; последующие
настоящие aim/heartbeat отвергнуты из-за reliable gap, затем Disconnect.
Принятый exact READY33 с autoAim0 этого самостоятельного пути не покрывал.

VERIFIED original PlayerAvatar.autoAim:2183 сразу включает TARGET_LOCK и
gunRotator.clientMode=false. PlayerAvatar.onAutoAimVehicleLost:1126 очищает
__autoAimVehID, снимает TARGET_LOCK и возвращает clientMode=true. Original
Avatar exposed rank0, FIXED0 даёт callback body `[0x13,0x3b]` с явным выбором
текущего Avatar. Это не результат Account и не метод выбранного Vehicle.
Поэтому ACK/ignore ненулевого захвата не используется.

Текущий узкий ремонт: только exact11B/routing0; nonzero запрос явно отменяется
native callback, без чтения цели или domain-команды. Нулевой cancel принимается
без echo. Неизвестная/self/dead/hidden цель получает одинаковый отказ без
раскрытия скрытого состояния. Серверный auto-tracking пока не реализован;
native callback/mouse восстановление до фактического теста NOT_RUN.

Evidence: `local/evidence/20261016-p08c-autoaim-failure01`,
`local/night-staging/20261016/p08c-autoaim-native01`,
`local/night-staging/20261016/p08c-autoaim-results01`.
Own processes остановлены по точным receipts. Consistent DB backup SHA256
`0a9736ffb36ce7486c105293afe8eddccff8731c3a5e4469b2653d66739bea76`,
A123/B38,ammoA[0,0,5]/B[0,3,9],active0. Независимый checker, требующий два
own full result, корректно отказал `DURABLE_OWNER_RESULT_COUNT`; это покрытие
данного прерванного сценария, а не PASS обоих natural возвратов.

Runtime `46d5c2058b36d9c6480896b6e80dfbab2fc86cca`: строгий standalone parser
и source-bound native отказ реализованы. Шесть новых регрессий включают actual
11B в полном Session/Window receive, реальный sent predecessor ACK, replay,
callback ACK и следующий heartbeat; cancel0 без echo; одинаковый parser отказ
семи классов target; rollback malformed size/route/late Aim+Move/tail/piggyback;
закрытые фазы/retired throwaway drain и outbox128. Test-only absent-roster и
hidden Book cases изолированы до обычного interest refresh и не объявляются
native/валидной World сценой. Source proof64static и Python original contract
7PASS/0skips, включая2 новых проверки исходного loss/cancel и FIXED0/rank0/PE.
При разработке исправлен только неверный ожидаемый tagged Packed XML scalar
Interface: lossless decoder возвращает `{'base64':'Chat'}`; production parser
ради теста не менялся. Независимый review committed8file diff замечаний не дал.

Canonical full: **1136 PASS / 0 FAIL / 5 прежних ignored / build PASS**,
333.34s tests, `RUST_TEST_THREADS=1/CARGO_INCREMENTAL=0`. Все689raw source SHA
до/после совпали, runtime head не менялся. Executable SHA256
`24cc44f18c3c919bbc51e07f4215fd95baf40f9028bec76c92e1d2550200770f`.
Evidence: `local/build/server/gateway-p08c-autoaim-full01`,
`local/evidence/20261016-p08c-autoaim-fix01`; source-bound binding06,
read-only preflight и startup morning-autoaim01 PASS, клиенты запускаются.
Callback/звук/мышь и natural kill/details/return до owner проверки NOT_RUN.

Команды нового запуска: `run_step.py binding06`, RO stand checker preflight,
`run_step.py services07`, `startup08`, `client-a09`, `hangar-a`, `client-b10`,
`hangar-b`, RO checker ready; каждый результат сохраняется новым exclusive
receipt. Штатный runner/guards и обе установки coreV7 сохранены. Следующий
native сценарий: каждый пробует отказ автоприцела/мышь без выброса; затем Ёж
с его3КС/9ОФ уничтожает первого игрока вручную, оба ждут естественных итогов
и ангаров. Проверяются фактические урон/фраг/details, без фиксированного числа
выстрелов и без восстановления потраченного БК. Main остаётся прежним.

Actual new run: bridge97704/gateway101180/A90096/B92612; Root PID-specific
hangar-a/hangar-b receipts подтвердили обоих fresh native cache/model/GUI
ангары. Пока Root выполнял дополнительный current-idle ready, owner сам
нажал Fight в обоих. Поэтому ready01 закономерно отказал
CURRENT_CONSECUTIVE_HANGAR_READY: последняя lobby view уже BattleQueue.
Это не runtime/native exception и не повод ослаблять checker или перезапускать
бой. Отказ сохранён. Actual log: arena2975833524010313505, session1 A slot1,
session2 B slot0, оба owned admission/READY, 30s Prebattle. Owner получил
уточнённый сценарий для уже запущенного боя. Native callback/мышь, personal
damage/kill и оба natural возврата ещё NOT_RUN до ответа/actual wire/SQL.

## Owner + actual result-wire приёмка autoaim06

OBSERVED owner: «Захват снялся, мышь работает; личные итоги верные, оба
вернулись». VERIFIED actual arena2975833524010313505: Elimination/winner1,
оба BattleFinished, полный Results8 одинакового SHA
`b064c9def098c55f04801e64cf98976c619baa4a0308d56a80eb5299bc8ec66a`.
A126:HP0/received90/killerB/death0,1HEshot,remaining[0,0,4].
B41:HP90/5HEshots/direct5/pierced3/damage90/kill1/spot1,remaining[0,3,4].
Оба active0, Avatar100/actualAccount1500/acked/naturalreturn/hangar по одному;
manual leave отсутствует. Actual late routed dead bind A принят без передачи
authority; rejects/faults/idle_timeout0. Owner + wire + SQL закрывают узкий
natural death/details/return gate, не всю P08C и родительские карточки.

Independent checker02 result-only:9474actualpackets/484046wirebytes, оба
Avatar100 и actualAccount1500 payload/81fields/details согласованы с completed
RO SQLite backup SHA
`38888b11651fa889187c2ccf8179a08d4273aa47f5155041eb27df6a86e0fc7d`.
`freshresults02.json` SHA
`39da27da29e22dfc7c1bad5a6d9712525149e80b6c0615a99f88f2bc23327f02`.

Первый optional autoaim checker02 дал ложный FAIL: ACK-only flags0x448 и
reliable application0x458 могут иметь одинаковый seq. Новый ignored03
разделяет application по transport reliable bit0x10; настоящий конфликт
reliable replay остаётся FAIL. Реальные пары ciphertext/pins сохранены,
28pure/source tests PASS. Aggregateautoaim03NOT_RUN: у A лишь cancel0,
нет nonzero capture. У B2nonzero→exact133b callbacks seq824/853→ACK825/854,
затем ownaim/authenticated reliable heartbeat в том же Avatar PASS. Это
компонентное покрытие B, не выдуманное native покрытие A. Owner mouseboth
подтверждена. Старый checker02 и его FAIL не переписаны.

Root acceptance SHA
`6d607b6e4c2b29e1e07a756fe7f59cd6eeaf5fb182a9aba88ebd5af0825ea75a`,
evidence `local/evidence/20261016-p08c-autoaim-acceptance01`.
Own run сохранён в ангарах. Mainffce8cb и ночные ветки не меняются.
Новая screenshot18HP/ammoBayDestroyed — отдельный P06T gap. Владелец поручил
actual детонацию/башню и новое project-only правило потери всего оставшегося
loaded БК. Это не историческая механика и не применяется к прошлым результатам.
