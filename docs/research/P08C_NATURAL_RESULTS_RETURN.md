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
personal81/details тест; его выполнит full. Full committed source gate и native replay
пока NOT_RUN. Новый full build фиксирует `RUST_TEST_THREADS=1`,
`CARGO_INCREMENTAL=0`, чтобы не создавать дополнительный incremental cache.

План — [P08C_NATURAL_RESULTS_RETURN](../plans/P08C_NATURAL_RESULTS_RETURN.md).
Marker
gate остаётся принятым; late manual-leaver append/spawn — отдельные открытые
пункты. Main и ночные ветки не меняются.
