# P06T — детонация БК и отдельный расход lost-v1

Задача владельца от 2026-10-16: уничтожение непустой БК убивает машину,
отрывает башню и уничтожает все оставшиеся loaded снаряды. Потеря всего БК —
особое правило проекта. Это не утверждение об исторической экономике WoT.
Ветка `codex/p06t-ammo-rack-detonation`, база принятого узкого P08C `1e87e1b`.

## Факты и границы

**OBSERVED.** На присланном владельцем скрине исходного coreV7 AmmoBay был
уничтожен, машина имела18/90HP и сохраняла башню. В прежнем коде уничтожение
устройства меняло только capability/notification, без отдельной катастрофической
смерти. Прежняя natural P08C приёмка остаётся сохранённой; её результаты и БК
задним числом не пересчитываются.

**VERIFIED_STATIC, original #717.** DetachedTurret имеет client type8 после
применения ClientName при построении таблицы клиентских сущностей; порядковый
номер42 из entities.xml для этого непригоден. Клиентские поля: BOOL underwater,
BOOL colliding, INT32 vehicleID, STRING vehicleCompDescr. Vehicle EXPLODED=-1,
TURRET_DETACHED=-2; отдельный showAmmoBayExplosion принимает два FLOAT32.
Проверены исходные .def/байткод/таблица типов PE проверенного локального клиента.
Новые native IDs `0x09120001+slot` и aliases248..253 не пересекаются с шестью
машинами и AreaDestructibles. Этот выбор идентификаторов — решение проекта.

Static evidence — ignored `local/night-staging/20261016/p06t-detached-turret-native01`
и `local/evidence/20261016-p06t-ammo-rack-wire01`; четыре оригинальных Python
contract tests PASS/0skips. Ни один клиентский Python-модуль не исполнялся для
исследования. Исходные клиентские ресурсы не добавлены в репозиторий.

**VERIFIED_LOCAL_AUTOMATED.** Runtime `ed67531`: focused `p06t_` —143PASS/
0FAIL/0ignored,712 raw source files before/after exact. Actual World/Trace test
стреляет по настоящей source geometry через Aim/nearest contact и explicit LAB
module proxy: plate Trace90→60→30, HP journal90→60→0, один kill,90damage,
нападающий2shots, жертва0shots/lost14. Это авторизованный тестовый shooter и
тестовый terrain; FrozenLoss жертвы получен из настоящего отдельного SQLite
writer. Сетевой клиент, UI и авторитетность синтетического shooter этим не
доказываются. Проверены также empty rack после фактического последнего выстрела,
совместная гибель последнего члена экипажа/БК, rollback и включённый в counts clip.

Writer:12 новых SQL tests PASS/0skip на окончательных файлах;15 прежних mixed
SQL PASS/0skip; новый actual HTTP→Python→SQLite PASS/0skip;13 Web tests PASS/
0skip, включая старый actual mixed HTTP и отдельного владельца. Evidence —
`local/night-staging/20261016/p06t-ammo-loss-writer01/handoff01.json`, SHA
`08a53cb14ad412b4af483393b58a65d79b5e38f3b44adb9b910257f9455ddd41`.
Настоящие SQLite векторы сохранены как source fixtures и не являются native
трассой. Первый HTTP FAIL сохранён: тест округлил большой arenaID в JS;
production writer правильно отверг другой ID, ослабления проверок нет.

Первый canonical01 не собрал новые тесты из-за двух ошибочных module paths.
Diagnostic01 после их исправления:124PASS/19FAIL, два дефекта fixture setup —
geometry/AP prerequisites и скачок времени через lifecycle MAX_STEP_MS.
Исправлены только тесты; Diagnostic02:143PASS. Исходные FAIL logs сохранены.
Полный fresh canonical02 на том же runtime:1188PASS/0FAIL/5oldignored,
buildPASS;712 raw source files exact. Test runtime302.78s, exeSHA
`3962811b78cd0cbcc9edc7ad3001f79e74835d94439d8071aa3b55226e72b9f8`.
Evidence — `local/evidence/20261016-p06t-ammo-loss-full02/source-after.json`.
Raw source archive сохранён для точного EOL rollback; старые FAIL не затёрты.

**INFERRED.** Проверенный serializer и реальный Session/Window ACK flow должны
подойти исходному клиенту. Фактическая native приёмка нового отрыва/эффектов/
траектории/возврата остаётся NOT_RUN до утра. Старые подтверждения coreV7 не
переносятся автоматически на новое поведение.

**UNKNOWN.** Исторические внутренние hit volumes, случайности и импульс башни
не установлены. Модель движения башни — PROJECT ballistic point + actual
terrain clamp, без swept body, Jolt contacts, вторичного blast damage или
исторической точности. Настоящие UI/audio/пересечения со зданиями/водой требуют
отдельной проверки. Пожар текущего device policy не повреждает AmmoBay;
дополнительная детонация из такого отсутствующего перехода не выдумывается.

## Авторитетность и совместимость

- Только фактический переход AmmoBay HP>0→0 при непустых loaded counts создаёт
  typed causal event shot/attacker/target/tick/device_sequence. Пустая БК
  получает tombstone, дополнительного HP damage и полёта нет. Точная повторная
  запись не создаёт новое списание; противоречивый повтор отвергается.
- Результирующая потеря записывается в том же World transaction, что module
  transitions и единственная HP/death запись. Исходный plate Trace не изменён;
  AppliedImpact health_after отражает именно plate, итоговая Actor HP может0.
- API4 contract `p06t-ammo-rack-loss.v1`, policySHA
  `f6369197bcf83e4915dbbb16c4c173a6fd3b38103ac08bc2e33913a9071fe94e`.
  FrozenLoss оборачивает неизменённый v2 Frozen и оба хеша. Включается до admit;
  старый активный резерв не мигрирует незаметно. Старые source/terminal policies
  и native result schema81 не изменены.
- `initial = fired + lost + remaining` по каждому исходному stack;
  acceptedShots=sum(fired). Lost включает clip один раз. Depot не меняется.
  Терминальный writer атомарно сохраняет ammo accounting и полные итоги,
  replay не списывает повторно. Старые архивы читаются с provenance mixed-v2,
  новые —loss-v1, без подмены истории. Legacy writer для loss owner закрыт.
- Новый companion `p06t-ammo-loss.json` связывает версию/contract/policy/base
  policy с владельцем, nativeDB, revision и stateSHA. Gateway требует явные
  mixed+visibility+loss flags, bridge — явный subset loss owners. Старые
  запросы/режим не обслуживают активированного владельца.
- Domain health и owner HUD0 сохраняются; negative -2 относится только к
  native Vehicle presentation. Parent terminal health предшествует child.
  Child enter/request/create/ACK/pose/leave требует настоящих sequences и
  текущих visibility/parent epochs. Точные позы ставятся непосредственно в
  свободный Window, не хранятся в отложенной скрытой очереди. Смена parent epoch
  требует leave ACK и нового create. Повторное появление не воспроизводит FX.
- Визуальные часы продолжаются после заморозки результата, без изменения HP,
  устройств и статистики. TTL5s, drain timeout20s; native result stream ждёт
  подтверждённого удаления child. Зависший канал закрывается с сохранённым
  durable результатом, ACK не подделывается. Старый World не сбрасывается до
  handoff Avatar. В Leaving сохраняются только проверенные child requests,
  world commands остаются в throwaway clone.

## Сохранность, стенд и откат

Per-shot WAL отсутствует. Закоммиченный Finish переживает повтор, переоткрытие
и новый run; до terminal commit старый aborted_restart один раз возвращает
исходный reserve с неизвестным исходом боя. Это явное ограничение контракта.

Ignored `local/stands/night-battle-20261017-01/loss-01` — новая SQLite backup,
активация/publish обоих через действительный CLI,0grants. При подготовке A127/
B42 и loaded A[0,48,48]/B[0,50,46] сохранены вместе с depot;active0. Старые SQL
строки/revisions не изменены, добавлены только три loss tables. Source game/web
main+WAL и old configs/run/ledgers сохранены.161 resource checks и8 guard tests
PASS. Exact full02 binding-loss01 создан. Actual startup-loss01 загрузил все5
профилей и объявил P06T_AMMO_DETONATION_BOUND/BOUND. Native клиенты не запускались,
их новая приёмка NOT_RUN; installed V7 остаётся прежним. Старые morning-autoaim01
клиенты/службы остановлены только своими PID/exe/creation receipts.
Actual startup-loss02: по одному derived-corpus own UDP Login на каждого;
настоящие loss4 RunOpen A128→129/B42→43, loaded/depot/crew/results/reservations
не изменились,active0. Native UI/Base attach NOT_RUN. Оба новых own service
PID58220/15492 остановлены и отсутствие проверено. Receipt
`loss-01/runs/startup-loss02/login-smoke-v4.json`, SHA
`871da59de4242881bc4f2c5234b41d6769b80adb778007c2ddeb4220294fa45d`.
Smoke01 FAIL сохранён: слишком строгий guard принял штатное изменение
auth throttle game_limits за игровую мутацию. Отдельный reconciliation доказал
один успешный A127→128; второй прогон проверяет точные source limiter transitions.

Полные команды и prospective запуск — ignored `loss-01/MORNING-full02.md`.
Порты остаются прежними20130/20131/3481 из actual V7 plan. Перед стартом нового
стенда остановить только свои процессы старого run по PID/exe/creation receipt.
Исходный клиент остаётся read-only. Токены/учётные данные не публиковать.

Откат — согласованные прежние branch/build/binding и отдельная БД до активации.
Не удалять маркеры из loss DB и не пытаться обслужить её старым writer.
Main/старые ночные кандидаты/доказательства сохраняются. Приёмка новой P06T
механики пока NOT_RUN; автоматическая часть сохранена на ed67531. Следующий
шаг — P08B restart/CAS composition в отдельной зависимой ветке, без ручных вопросов.
