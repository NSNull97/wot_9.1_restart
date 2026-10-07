# Недостающие данные и незакрытая приёмка

**Актуально на 2026-10-07:** P03 **IN_PROGRESS**. Owner-gates P03D
`PASS_OWNER_NATIVE_AMMO_PANEL_HUD` и P03E
`PASS_OWNER_NATIVE_FIRE_RELOAD_CONSUMPTION` закрыты; повторять пять выстрелов
для организационной карточки не требуется. Точные receipts и pins:
[ACTIVE_GATE](docs/ACTIVE_GATE.md), [P03D](docs/evidence-index/P03D.md),
[P03E](docs/evidence-index/P03E.md).

Для полного P03 ещё нужны две независимые native-сессии в общем мире и
проверка с двух ПК при доступном втором тестировщике. Projectile/hit/damage,
visibility и полный боевой цикл не приняты; оборудование требует проверенного
профиля с установленным предметом. Это будущие gates, а не отсутствие данных
для текущей организационной работы. Linux/deploy остаются NOT_RUN.

ORG-0A: первоначальный `Author identity unknown` разрешён владельцем,
предоставившим имя/email для local Git config. Полный Python-набор: 2028 тестов, 10 ошибок,
4 пропуска — [ORG-0B backlog](docs/plans/ORG-0B_TEST_TRIAGE_BACKLOG.md).
Публикация baseline/main теперь PASS_REMOTE_VERIFIED: владелец повторил
команды, независимый ls-remote подтвердил main и обе SHA аннотированного тега.
Ранние HTTP 408/TLS ошибки остаются историей. Единственный следующий шаг —
отдельная ORG-0B; она пока не начата.

## История недостающих данных по карточкам

Все записи ниже относятся к указанной дате; старые NOT_RUN не отменяют
более поздние owner receipts. Последующие рекомендации карточек не являются
текущим поручением.

**2026-10-06, карточка структуры серверных исходников:** для наведения порядка
новые файлы/доступы от владельца не требовались. PASS_SERVER_SOURCE_LAYOUT;
server/ имеет нормальные имена и один source каждого runtime core файла.
Существующий локальный стенд сохранился, deployment не выполнялся.

Перед будущим удалённым запуском остаются технические задачи, а не причины
останавливать текущую организацию кода:

- Linux runner/дистрибутив/архитектура пока не закреплены: build/native ABI
  и настоящий вход с удалённым сервером **NOT_RUN**. Ничего не устанавливалось.
- Worker loader требует .exe; native endpoints/redirect loopback-only.
- Identity/profile генерация имеет shared frozen web/tools code, client-resource
  reads и абсолютные source/fixture/provenance paths; versioned export ещё нужен.
- Map content manifests живут в historical evidence; перенос inputs требует
  версии формата и проверок. Current map-drive account/profile4 закреплён.
- Подключение новой сборки sr-gateway к рабочему service config **NOT_RUN**:
  текущий deployed EXE/pins не менялись. Старые direct-live-source research
  readers не адаптированы, их повтор после source migration **NOT_RUN**.

Отчёт: `docs/SOURCE_LAYOUT.md`; доказательства:
`local/evidence/20261006-server-layout/`, `local/build/server/`.
Следующий рекомендуемый шаг — отдельный versioned export server content и
encoder/provenance inputs. Ниже сохранены незакрытые условия игровой приёмки.

**2026-10-06, после ручных запусков016:** файлы и доступы от владельца не
требуются. Два native входа/14 camera toggles/первый штатный возврат и reentry
подтверждены, code/build290PASS; полная строгая ручная приёмка PARTIAL.

- Второй native_leaveArena/warm return в последнем запуске **NOT_RUN**:
  соединение закрылось из второй арены,4 tail publications retired без ACK.
- После fix2 exact nonzeroMove→первый6 **NOT_OBSERVED_NATIVE**. Прежний настоящий
  пакет проверен captured-literal regression, но это не новое native событие.
- Pivot: команды приходят в tracked worker, near-rest rotation почти0;
  gearbox/RPM/track angular states отсутствуют, причина **UNKNOWN**.
- Ступени R/F25/50% не реализованы; полный режим имеет поддерживаемыеflags1/2.
  Действия владельца по конкретным ступеням **NOT_RUN**. Причина hill pauses
  без action/time correlation **UNKNOWN**, не приписывается только физике.
- Разрушения деревьев/объектов отсутствуют; native notification contract и
  авторитетная смена collision states **UNKNOWN / NOT_RUN**.

Отчёты: `docs/research/P02_SNIPER_CAMERA_PROTOCOL.md`, `P02_DRIVE_LIMITATIONS.md`.
Следующий проверяемый шаг — отдельная pivot диагностика. Ниже — исторические
границы завершённой ночной карточки, её PASS не заменяет эти ручные условия.

**2026-10-06, текущая карточка поездки:** новые файлы/клиент/доступы от владельца
для локального исследованного пути не требуются. Native Ride21 и Ride22
подтвердили обе случайные карты, авторитетное движение, остановки, препятствие,
границу и повторные возвраты. Подробности: `docs/research/P02_MAP_DRIVE.md`.
Normal014 установлен для обычного EXE. Итоговый аудит файлов и БД **PASS**:
`local/evidence/20261005-p02-map-drive/final-audit-02/final-state-audit.json`,
SHA256 `c07de7886178861d5c254eb0df1e0711446f01ec018b45547c8fb3482bc973c7`.

Оставшиеся границы:

- **NOT_RUN:** физическая клавиатура владельца и субъективная плавность именно
  normal014. Один следующий шаг — ручная поездка МС-1 через «В бой!», задний ход,
  препятствие, выход в ангар и повторный вход. Управления компьютером нет.
- **UNKNOWN / test_lab:** историческая точность подвески/контроллера,
  воспроизводимость между платформами, причина цветной сетки в native PNG.
- **FAIL_OBSERVED сохранён:** normal луча над камнем Прохоровки отличается от
  нормали экспортированной геометрии; высота совпадает. Контактные manifolds
  не записаны. Преходящие перекрытия грубого корпуса с препятствием/стеной
  измерены, нулевая пенетрация не заявляется.
- **NOT_RUN / не входит:** выстрелы, урон, противник, многосессионный бой,
  стрельбовый боекомплект Avatar, результаты боя и нагрузка1000CCU. Для проверки
  боя вдвоём впоследствии понадобится независимый второй клиент и многосессионность.
- Происхождение отдельной команды вперёд в Ride11 — **UNKNOWN**; владелец
  подтвердил отсутствие своего ввода. В новых прогонах все movement callers
  объяснены, но это не восстанавливает недостающий caller старого события.

Прежние статусы ниже относятся к прошлым карточкам и сохранены как история.

**2026-10-05, после Move02:** nativeforward/stop и серверные обновления
положения подтверждены19/19 PASS; собственный МС-1/модель переместились2m,
остановка≥3s. `docs/research/P02_ARENA_MOVEMENT.md`. Новых файлов или ручных
действий владельца для этой карточки не требовалось. Normal013/ordinary
установлены; два replay сохранены/откачены; клиент закрыт.

Незакрыто: originalgetOwnVehicleMatrix остаётся уseed при движущейсяVehicle;
contacts0/0, groundYне подтверждён, gunrotatorне запущен. **Следующий один
шаг:** исследовать и проверить родную связь controlEntity/сервернойкоррекции
с матрицей собственной машины. Fullcontroller/groundcollision/Avatarammo/
стрельба/урон/второйигрок/итоги — NOT_RUN. Четыре конечных stoppedupdates
безACK отдельно deliveryNOT_RUN; решающийholdподтверждён ранееACKedданными.
Точный prediction/reconciliation, графическаясетка, звукUNKNOWN. Ручнойвход
именноnormal013/replayplayback/длительнаянагрузкаNOT_RUN. Нативныйperiod3 в
диагностике не делает полныйбой готовым. Ранние результаты ниже — история.

**2026-10-05, после Ready01:** настоящий setClientReady и серверная подготовка
арены с родным отсчётом приняты:18/18 PASS, два PNG27→21, чистый Python
lifecycle, exit0/restore. Отчёт `docs/research/P02_ARENA_READY.md`.
Новых файлов или действий владельца для этого checkpoint не требуется.
Normal012/ordinary установлены; итоговая сохранность проверяется отдельно:
`local/evidence/20261005-p02-arena-ready/final-audit-01/final-state-audit.json`.
Ранние утверждения ниже о неподдержанном ready/countdown — история.

**NOT_RUN:** активный BATTLE, native expiry30s данного PREBATTLE, Avatar ammo,
авторитетное движение, контакт с грунтом, стрельба/попадание, второй игрок/итоги.
Точный native filter/prediction/reconciliation UNKNOWN; статические physics
hooks подтверждены: `docs/research/PHYSICS_AUTHORITY.md`. Гусеничный контроллер
Jolt и импорт collision-геометрии не запускались. Длительная синхронизация часов,
звук и причина цветной сетки UNKNOWN; ручной вход именно с normal012 NOT_RUN.
Generated replay сохранён/откачен; его playback NOT_RUN.
Следующий проверяемый шаг — отдельный эксперимент одной команды движения МС-1
и серверного обновления позиции. На gateway пока одна активная сессия.

**2026-10-05, после Vehicle03:** доступный следующий checkpoint выполнен:
Account→Avatar→Карелия→собственный МС-1, родные модели/HUD и чистый выход —
17/17 PASS. Отчёт `docs/research/P02_ARENA_ENTRY.md`; сервер вернулся в ordinary
режим, normal011 установлен, клиент закрыт. Новых файлов от владельца для
этой приёмки не требуется. Ниже normal010 — история предыдущей карточки.

Не реализованы/NOT_RUN: серверная обработка настоящего setClientReady и фаз
арены, countdown, native Avatar ammo transfer, физический spawn/грунт, движение,
выстрел/попадание, второй игрок, конец боя. Экран ожидания и90HP не доказывают
эти функции. Следующий рекомендуемый шаг — одна серверная фаза подготовки
арены после настоящего setClientReady, с проверкой родного отсчёта.
Он здесь не начат. На текущем gateway поддерживается одна активная сессия;
для последующей игры вдвоём нужны многосессионность и второй независимый клиент.

Мощности1000CCU: `docs/research/CAPACITY_1000_CCU.md`,19 arithmetic tests PASS.
Реальная стоимость CPU-ms/tick иp99, RSS/PSS, PPS/traffic настоящего боя и
плотность совместного размещения UNKNOWN/NOT_RUN.3/5/7 физических серверов —
условные сценарии, не подтверждённая спецификация закупки. География игроков,
RPO/RTO и допустимое поведение при отказе worker ещё не определены.
Первый полный manifest выявил автоматически созданный replay Vehicle03;
он сохранён и точечно убран из research после проверки отсутствия в baseline.
Полный контроль состояния: `local/evidence/20261005-p02-arena-entry/final-audit-02/`.
Повторное воспроизведение replay и ручной вход именно с normal011 NOT_RUN.

**2026-10-05, текущий статус:** для доступных узких проверок аккаунта и
ангара новых файлов или действий владельца не требуется. Используются две
существующие собственные учётные записи и прежний client profile002.
Минимальный экипаж МС-1, честная недоступность неподключённых окон, повторный
вход внутри EXE и изоляция A→B→A подтверждены настоящими запусками.
Отчёты: `docs/research/P02_MS1_CREW.md`, `P02_HANGAR_SERVICE_LIMITS.md`,
`P02_HANGAR_WINDOWS.md`, `P02_INPROCESS_RELOGIN.md`, `P02_ACCOUNT_SWITCH.md`.
Исторический normal009 и полный filesystem/profile audit L — PASS.
Новый normal010 установлен после двух настоящих входов с боекомплектом МС-1:
20 обычных ББ,0 HEAT,0 ОФ. Серверный profile4, сайт и родная панель согласованы;
paired native report и60 независимых отрицательных проверок PASS.
Отчёт `docs/research/P02_MS1_AMMO.md`. Полный текущий audit PASS:
original3469/research3490,0unexpected,17completed diagnostic restores.
Ручная проверка владельцем новой выдачи20ББ NOT_RUN; данных для её работы хватает.

Ручная приёмка входа, экипажа МС-1 и переключения МС-1 ↔ ИС-7 — PASS_BY_OWNER.
Естественное истечение сессии→LoginView→повторный вход — PASS_MANUAL_AND_BACKEND:
`docs/research/P02_MANUAL_EXPIRY_20261005.md`. Остальные UI-пути этим не проверены.
Кириллический ник второго аккаунта передаётся полностью, но при1024px его конец
обрезается заголовком — OBSERVED; причина цветного зерна native PNG UNKNOWN.
Найм/переобучение экипажа, покупка/пополнение/расход боекомплекта, внешний вид
и полный магазин не реализованы. Боекомплект ИС-7 не выдавался.
Окна явно недоступны, их функциональность не названа готовой.

Карточка T завершена PASS: прежний UDP endpoint действительно освободился;
ровно3 исходных datagrams закрытого A отвергнуты при живом B. Отчёт:
`docs/research/P02_RETIRED_BASE_REPLAY.md`. Другие сети, source spoofing,
истечение TTL и restart этим не проверены. Длительный готовый ангар с реальными
periodic CCU replies — PASS:913s/182ответа/3одинаковых снимка/2580packets,
отчёт `docs/research/P02_LONG_HANGAR.md`.
Session11 действительно закрыта по session_deadline, затем тот же аккаунт
успешно вошёл в session12. Переход GUI подтверждён владельцем; точная задержка
UNKNOWN, автоматический native trace NOT_RUN. Evidence:
`local/evidence/20261005-p02-manual-expiry/review01/`.
Следующий рекомендуемый срез: минимальный native переход Account→Avatar и
загрузка одной собственной локальной арены. Для начала read-only исследования
новые файлы/действия владельца не нужны; готовность движения/стрельбы не доказана.
Арена/бой/двухклиентская игра остаются
вне ночного объёма, второй независимый клиент/окружение для будущей проверки
пока не предоставлен. Серверный лимит1800s и полный P02 PARTIAL сохраняются.

Ниже — исторические checkpoints, их старые NOT_RUN не отменяют новые доказательства.

2026-10-04. Для завершённой карточки UI13 входных данных больше не нужно:
normal/cached relogin, обе машины, ToolTip/Awards и ручной выход PASS.
Нужное фото недоступности оборудования получено от владельца, сохранено в
`local/evidence/20261004-p02-hangar-ui/owner-screenshots-ui13/`.

Остались конкретные функции будущей карточки: серверный экипаж/найм,
боекомплект и внешний вид. Дополнительный ручной запуск normal003 выявил
IndexError в RecruitWindow и VehicleCustomization/ShopRequester; evidence:
`local/evidence/20261004-p02-hangar-ui/normal003-extra-launch-01/`.
Владелец подтвердил авторство запуска. Логи сохранены, ошибки не названы PASS.
Код завершения этого дополнительного процесса UNKNOWN; отдельный полный
native verifier для него NOT_RUN. Сохранность обоих аккаунтов после него PASS.

Нет приёмки арены/боя, полного оборудования/снаряжения/магазина, многочасовой
сессии и всех UI-путей. Лимит gateway1800s остаётся. Для будущей проверки
двух игроков всё ещё нужны два независимых клиента/окружения. Полный P02 PARTIAL.

Ниже сохранены исходные входные данные и исторические checkpoints.

| Вход/доказательство | Для чего нужен | Статус |
|---|---|---|
| Инициализация EXE и объяснение раннего exit | Получить trace и native bytes | ПОЛУЧЕНО: mutex control, runtime init, `.pyc` diagnostic loader |
| Свежий sys.version и ResMgr marker от этого hash | Закрепить runtime | ПОЛУЧЕНО: Python 2.7.3 / 32-bit; native-05/runtime.jsonl |
| Реальные request/reply на собственном loopback | Проверить узкий native transport | ПОЛУЧЕНО: login 273 B, rejection 45 B и клиентский callback; не доказывает entity RPC IDs |
| LoginSuccess и первый BaseApp request | Следующий срез входа/сессии | ПОЛУЧЕНО: два реальных запуска; reply 28 B → BaseApp 21 B, токен совпал |
| Ответ BaseApp и первый encrypted frame | Проверить handshake | ПОЛУЧЕНО: два real runs, LOGGED_ON и echo нового token |
| ACK первого packet и limited keepalive | Проверить начальную reliability | ПОЛУЧЕНО: два положительных real runs, controls ACK=0/1; удержание до 21.61 s |
| Первый reliable server packet/client ACK | Проверить обратное направление | ПОЛУЧЕНО: seq0 и duplicate → native cumulative1/1, три corrected runs |
| Ограниченный канал и transport/session lifecycle | Проверить собственный gateway | ПОЛУЧЕНО: selective ACK/retry, auth/digest rejection, 10 native cycles на одном процессе; [отчёт](docs/research/P02_LAB_GATEWAY.md) |
| Первое native Account creation | Entity type/message ID и минимальный payload | ПОЛУЧЕНО: ID5/type0, оригинальный PlayerAccount, все 3 поля; пять native runs, loss/absence/duplicate controls |
| Минимальный Account Python lifecycle / initial sync | Успешно исполнить оригинальные обработчики | ПОЛУЧЕНО: original constructors/become/non-player, sync revision1, requests100/300/600 и stream CRC; native series8/8 |
| Штатный ангар / собственная сводка статистики | Вывести реальный игровой UI и серверные данные | ПОЛУЧЕНО: original showGUI/AppEntry/LobbyView/Hangar/ProfileSummary, MS-1/ресурсы/нулевой dossier; итоговая native серия4/4, шесть PNG |
| Обычный bootstrap / native preferences | Самостоятельный EXE на свой endpoint | ПОЛУЧЕНО в узком срезе: original LoginView/preferences, Normal21 без control95salive/76.435sready/0own-UDP PASS; собственный compatibility bootstrap сохраняется; clean native exit idle harness NOT_RUN |
| Общий канал / произвольные fragments / длительный сеанс | Последующие транспортные контракты | Измеренные two-fragment login/state streams и interactive sequence>32 ПОЛУЧЕНЫ: primary18server134/client40; general fragmentation/wraparound/многочасовой сеанс NOT_RUN |
| Persistence / web→game auth / разные пользователи | Одна регистрация и общий профиль сайта/игры | ПОЛУЧЕНО: primary17/18/19, два UUID/nativeID, email-only и русский ник, real restart, unchanged resources/fixture и изоляция /api/game |
| Producer пустого tooltipId / конкретное UI-действие | Устранить настоящий full-GUI blocker | УСТАНОВЛЕН в текущей карточке: отсутствовали пять mounted items в каталоге, original selectedIndex=-1/None. Catalogue2 исправлен; UI06:0ошибок, заполненные списки/typed tooltip подтверждены. Полная normal GUI/relogin приёмка пока NOT_RUN; см. docs/research/P02_HANGAR_UI.md |
| Второй независимый клиент/ПК | Будущий двухклиентский arena/state тест | НЕТ для отдельной будущей карточки; instance mutex не обходился; текущую авторизацию не блокирует |
| Финальная установленная копия / полный integrity audit | Зафиксировать передаваемое пользователю состояние | ПОЛУЧЕНО: final-state-audit-02.json PASS, original unchanged, 21/21 restore checks, research baseline+final ledger |
| Независимый эталон/история происхождения клиентского архива, если нужен статус «оригинальный дистрибутив» | Установить аутентичность, а не только неизменность двух копий | UNKNOWN; не блокирует локальное исследование этой закреплённой копии |
| .NET 10 SDK и отдельная проверка на нём, если он будет выбран | Проверить предложенный production target | Сейчас установлен 9.0.315; headless spike на net9.0 PASS |
| Git user.name/user.email, когда понадобится коммит от владельца | Сохранить историю без выдуманной личности | Сейчас не настроены; git init и локальные архивы готовы, не блокирует текущие проверки |

Владелец утвердил GAYmDev Stutio и «Стальной рубеж»; [NAMING](docs/NAMING.md)
обновлён, сайт уведомлён. Конкретные названия карт не утверждены и для текущего
исследования не требуются. Массовый клиентский ребрендинг не выполняется.
Чужие аккаунты, ключи, доступ к WG/«Ориону», старый офлайн-проект и соседние
репозитории не нужны и не запрашиваются.

Независимая работа выполнена: исходные хеши, структуры/схемы, дескрипторы,
одна collision-модель, один map chunk, сборка toolkit, XML/resource probes,
headless Jolt, boundary tests и проверенный откат. Подробности —
[STATUS](docs/STATUS.md) и [INTEGRATION_SPIKES](docs/research/INTEGRATION_SPIKES.md).
Продолжение: [P01_BOOTSTRAP_AND_NATIVE_LOGIN](docs/research/P01_BOOTSTRAP_AND_NATIVE_LOGIN.md).
Обязательных дополнительных входных файлов для завершённого P01 сейчас нет.
Для выполненной карточки [P02 redirect](docs/research/P02_LOGIN_REDIRECT.md)
новых входных файлов также не требуется. Если запущена другая игровая копия,
диагностический preflight откажет до изменений; игру владельца он не закрывает.
В карточке [BaseApp reply](docs/research/P02_BASEAPP_REPLY.md) mutex сначала
был занят; владелец закрыл игру, затем проверка подтвердила освобождение.
Новых обязательных файлов для текущего узкого handshake нет.
Для завершённой [карточки ACK](docs/research/P02_CHANNEL_ACK.md) дополнительных
входных файлов также не требуется. Исправленный Windows UDP capture проверен
реальным закрытым портом и повторными client runs; исходный FAIL сохранён.
Для [native Account](docs/research/P02_NATIVE_ACCOUNT.md) дополнительных файлов
от владельца не требуется. Bootstrap blocker установлен по конкретному
original traceback/bytecode и устранён в [следующей карточке](docs/research/P02_ACCOUNT_READY.md).
Для завершённой [карточки ангара](docs/research/P02_HANGAR.md) новых обязательных
файлов от владельца не требуется. Ангар и собственная сводка статистики приняты;
веб-аккаунт на том этапе ещё не проверялся. Теперь этот исторический NOT_RUN
закрыт [единым email-входом](docs/research/P02_UNIFIED_ACCOUNT.md), включая
primary restart/relogin. Владелец подтвердил Normal20 словами «Да, сам ввел,
вошел, потыкал разное»; AUTH_AND_SERVER_ACCOUNT_DATA_ONLY PASS по
`wire-agent/manual-auth20/manual-auth-analysis-02.json`, full GUI FAIL сохранён.
Остаются исследовательские неизвестные, а не запрос доступа к чужим аккаунтам.

Три отличия логов research появились между захваченными сериями и сохранены.
Владелец предположил, что это его попытка запуска. Это вероятное объяснение,
не техническая атрибуция; расследование инициатора не блокирует результат ангара.
Полный откат к before последнего run PASS, строгое совпадение с самым первым
baseline FAIL по этим трём журналам. Evidence: final-state-audit.json и log-lineage.json
в local/evidence/20261004-p02-hangar/.

Это история предыдущей карточки; окончательное состояние новой установки
отдельно записано и проверено PASS в
`local/evidence/20261004-p02-unified-account/final-state-audit-02.json`.
Единственный следующий проверяемый шаг — воспроизвести конкретное UI-действие
и локализовать producer пустого tooltipId. После этого арена может быть только
отдельно разрешённой карточкой; к следующей фазе автоматически не переходим.
