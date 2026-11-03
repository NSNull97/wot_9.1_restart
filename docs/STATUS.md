# Состояние проекта

> Дополнение 31.10.2026: владелец уточнил, что работу вести по карточкам;
> завершённую реализацию документировать, а дальнейшие тесты передать
> отдельному агенту. Актуальные состояния PERF-02, LATE-BOTS, CAT-NATIONS и
> PG-01, точные исходники и ограничения — в [описи](PROJECT_INVENTORY_20261031.md#передача-карточек-на-проверку).
> Готовность реализации сама по себе не означает успешное выполнение тестов.
> Проверка 31.10 вечер: CAT и интеграция дают 8 новых FAIL gate (старый SHA каталога в seed-фикстурах); код не влит — [детали](TEST_HANDOFF_20261031.md#результат-проверки--31102026-вечер-claude).

> Сверка 2026-10-31: база этой документации — main `a54b6aa`. Три раздела
> BW-01, TURRET-01 и INPUT-01 с формулировкой «не в main» ниже — снимки до
> принятия объединённой сборки `d03969e` и merge `3d90d26`; актуальна запись
> непосредственно под этой поправкой. Аналогично старые NOT_RUN SPAWN-15
> относятся к моменту до последующей приёмки. Подробности и не принятые
> кандидаты — [опись](PROJECT_INVENTORY_20261031.md). Остальной текст сохранён
> для проверки, даты в исторических разделах не означают текущий статус.

## UI-06c маркеры над машинами по эталонам владельца — в ветке `codex/ui-06c-vehicle-markers`, не в main — 2026-11-02

- Замена родного вида, включена по умолчанию: `prepare` кладёт в `res_mods` копию `VehicleMarkersManager.swf` #717. Число урона белое,
  ореол — прежний цвет числа (выбор цвета родной, `DAMAGE_COLOR`), правка 48 байт данных. Полоса HP своя: тонкая на тёмной плашке, в цвет
  метки (голубой союзник голубой), число HP под ней с пробелами тысяч. Видимость и данные маркера родные, дистанции нет.
  `--native-vehicle-markers` — откат и проверка. Native **NOT_RUN**. План — [UI06C](plans/UI06C_VEHICLE_MARKERS.md).
- Доработка 03.11 по бою владельца: под числом HP нет фона (`bgShadow` скрыт), чёрный ореол толще родного; цвет полосы — родной цвет
  метки из `hitSplash` (`94ff00`…); кусок снятого HP той же высоты, что полоса, цвета родные; значки классов Lesta из
  `local/ui-borrowed/vehicle-markers` (`tools/battle_ui_marker_art.py`, флаг `--vehicle-marker-art`), без файла — родной значок.
  Число урона не показывалось из-за сохранённых настроек маркеров владельца: «Урон» выключен (`MARKERS_ENEMY/ALLY` = `0x03000117`), не патч.
- Второй бой 03.11: полоса и имена — цвет значка класса своей метки (Lesta или родной), одинаковый у трёх. Числа урона нет по-прежнему
  из-за настроек: `2097431` — «Урон» выключен в Base и Alt, это не умолчание клиента (`0x011F0028`). Умолчания не записываются:
  шлюз отвергает запись `_initializeDefaultSettings` (-10), потому что ключ `MARKS_ON_GUN` = 500 вне `MAX_KEY = 56`. Нужна правка UI-01.
- Круг 7: контур машины в цвет полосы, отлетающий урон и значки пожара/БК поверх соседних маркеров, значки пожара/БК белые с
  ореолом числа урона, урон по тимкиллеру голубой (`DAMAGE_COLOR`). Native NOT_RUN.
- Круг 8: подъём маркера над соседями убран (движок терял маркеры: `invokePy2As - Failed to invoke method`),
  значки пожара/БК без пятна (отсечка альфы), контур машины непрозрачный (пробно, альфа ×1,5).
- Круг 9: контур светлее (×9/5, тело картинки серое), значки пожара/БК белые в самих картинках (фильтр цвета Scaleform
  рисовал чёрным квадратом), зелёный ореол урона по союзникам `70c000`.
- Круг 10: значки пожара и БК свои — родные рисунки белой геометрией (`tools/battle_ui_marker_icons.py`), превью принято.
- Круг 11: контурные иконки машин в ушах и маркерах — плоские с деталями, в ушах цвет класса (танк/ПТ/арта), в маркерах
  цвет полосы (`tools/battle_ui_contour_icons.py`, 368 иконок в `res_mods`).
- Круг 12: ореол значков пожара/БК вписан в картинки — фильтр на заменяющих кадрах (урон по противнику) Scaleform терял.
- Круг 13: палитра владельца — маркеры по команде, ореол урона по цели (свой `#E2A53D`), шире; уши: `gui_colors.xml` и пять
  наборов иконок по цвету строки с оттенками класса.
- Круг 14: палитра темнее в маркерах и ушах, имена маркеров в цвет полосы, значок БК под числом урона.
- Круг 15: маркеры ещё темнее (×0,86), экран загрузки боя — иконки по командам (`project_loading_icons`).
  Ореол числа урона плотнее (blur 6, strength 6 вместо родных 11 и 3) по просьбе владельца.

## UI-06b голубой маркер целиком и ряд машин на счётчике — в ветке `codex/ui-06b-teamkill-look`, не в main — 2026-11-02

- П. 6: в #717 кадр `blue` полосы HP показывает зелёную полосу. Флаг `prepare --team-killer-marker` (нужен `--enable-profile13-battle`)
  кладёт в `res_mods` копию `VehicleMarkersManager.swf` с одним DoAction: на метке `blue` полоса получает `ColorMatrixFilter` в цвет
  `blueColor`. Без флага фильм родной. Native **NOT_RUN**.
- П. 7: ряд машин на счётчике родной (`showVehiclesCounter`, бит 9 GAME), у аккаунта владельца выключен: шлюз объявляет версию
  настроек 11 без разделов, первая запись GAME обнулила остальные биты (сохранено 32). Включить на вкладке «Игра»; исправление
  хранения UI-01 — отдельная карточка. Полосы HP команд нет: HP скрытых противников клиенту не передаётся. План — [UI06B](plans/UI06B_TEAMKILL_LOOK.md).
## CRASH-01 поза машины после её leaveAoI — в ветке `codex/client-crash-leave-aoi` (от `dba4afb`), не в main — 2026-11-02

- Вылеты клиента 01.11 и 02.11 (стенд -12, код 3, без дампа). Захваты: в обоих случаях часть пачки поз `reliable-burst-v2`
  ушла после leaveAoI машины, которую ещё содержала (2 из 2; в 8 других выходах — нет). Код 3 у #717 даёт любое необработанное
  исключение (CRITICAL → `abort`, VERIFIED статически). Связь с вылетом INFERRED: адрес падения не получен.
- Исправлено: отложенная часть позы (v2 и `latest-unreliable-v1`) фильтруется по видимости на момент отправки, записи скрытых
  машин не уходят ни до, ни после leaveAoI. Тесты на пакетах `crash01_*` + NET-01: 16 PASS; без правки два теста порядка
  падают. Полный gate и native — NOT_RUN. План/итог — [CRASH01](plans/CRASH01_LEAVE_AOI_POSE.md).

## UI-02b индикатор обстрела своего вида вместо родного — в ветке `codex/ui-02b-lesta-indicator`, не в main — 2026-11-02

- Решения владельца 02.11: вид по эталону `ref2/hit-indicator.png`, графика своя (Lesta не копируем), замена родной реализации, а не
  мод рядом. `tools/battle_ui_hit_art.py` рисует 10 спрайтов кодом, `prepare` пишет `res_mods/.../DamageIndicator.swf` под родным именем:
  родной фильм с дугой, свои спрайты, сцена 1020 px. Включено по умолчанию в клиенте profile13; `--hit-indicator standard|off` —
  проверка и откат. Текст (машина, тип снаряда) под углом маркера, крит с уроном не желтеет. Раунд 3 (03.11, после боя
  владельца): чёрный ореол у текста, значки класса и модулей из Lesta (`local/ui-borrowed`, без папки — свои), маркеры одной стороны
  разводятся поворотом, подпись о крите — строкой при маркере. Раунд 4: без типа снаряда, ореол у значка класса, блок почти
  чёрный. Раунд 5: текст и значок класса по оси маркера. Native **NOT_RUN** для раундов 3–5.
  План — [UI02](plans/UI02_HIT_INDICATOR.md#ui-02b-свой-вид-вместо-родного).

## UI-03b вид ленты и истории как в живом бою Lesta — в ветке `codex/ui-03b-feed-history-look`, не в main — 2026-11-02
- Замечание владельца: индикатор не похож на родной. Разрешение владельца: чего нет в #717, временно брать из локальной копии Lesta.
  `tools/battle_ui_hit_art.py` режет спрайты атласа `damageIndicator` в `local/ui-borrowed/hit-indicator/` (в Git только инструмент),
  `prepare --hit-indicator-art <папка>` встраивает их в `ProjectHitIndicator.swf` родным способом #717 (`DefineBitsLossless2`,
  `DefineShape`). Папки или обязательного файла нет — прежний рисованный индикатор. Канал и факты те же. Native **NOT_RUN**.
  План — [UI02](plans/UI02_HIT_INDICATOR.md#ui-02b-вид-на-графике-lesta).
## UI-03b лента, история и суммы — часть родного `battle.swf`, свой вид — в ветке `codex/ui-03b-feed-history-look`, не в main — 2026-11-02

- Решение владельца: замена родной реализации, не мод; своя графика по `ref2/`, без Lesta. Код добавлен в копию родного
  `gui/scaleform/battle.swf` (pin SHA-256 и раскладки тегов, при несовпадении `prepare` отказывает), Python говорит с родным окном боя
  через события `g_windowsManager`. Включено по умолчанию вместе с `--hit-indicator`; `--no-battle-feed` / `--no-battle-history` — откат.
- Крит без урона в нанесённом — своя строка; суммы с нулями с начала боя. Плашка снаряда из записи канала `KIND_SHELL` (шлюз этой ветки).
  Native **NOT_RUN**. План — [UI03, «Родная реализация»](plans/UI03_BATTLE_FEEDS.md#родная-реализация-и-свой-вид-ui-03b-0211).
- Круг 3: мягкие плашки на строку с градиентом, иконки Lesta по `--battle-icons <папка>` (без неё — свои), цвета владельца (нанесённое
  зелёное, полученный крит золотой, полученный урон красный), сжатые столбцы, лента ниже.
- Круг 4: суммы и история без слов, крупнее (шаг 22, текст 14/16), верх блока вровень с панелью танка (230 px от низа).
- Круг 5: в ленте один значок и ширина по содержимому, плавный градиент (`beginGradientFill`, без него — полосы), суммы без «+»,
  плашка снаряда без ореола, скруглённая и уже.
- Круг 6: новая строка ленты въезжает снизу (300 мс, замедление), старая уходит вверх и гаснет; плашка снаряда по ширине названия.
- Круг 7: значок события в ленте крупнее (75 %), полученный урон сверху встаёт справа от ушей по их текущей ширине.
- Круг 8: в засвете имя машины (шлюз), только пока получатель её видит.
- Круг 9: поджог — одна строка с выжженным уроном, когда пожар погас или сжёг цель (шлюз); строки «×N» больше нет.
- Круг 13: палитра владельца в ленте, истории, индикаторе, сообщениях обнаружения; уши берут иконки по цвету строки,
  фон панели танка и рамки миникарты `#192126`; история снова считает выжженный урон.
- Круг 14: уши различают команды, палитра темнее, строки урона зелёные, засвет/крит золотые со значками, базы на миникарте.

## UI-05 вкладка «Информирование в бою» в родных окнах настроек — в ветке `codex/ui-05-native-settings`, не в main — 2026-11-02

- Флаг `prepare --battle-settings` при всех трёх виджетах. Вкладка в ангарном AS3 и боевом AS2 окнах из родных компонентов, родные
  байты не меняются: отдельный `DoABC` в ангаре, спрайт и `DoInitAction` в бою. Значения — секция `projectBattleUi` в
  `sr_preferences.xml` с версией: из боя сервера нет, ключи 0..56 свободны, шлюз не менялся. Лента и история меняются сразу,
  индикатор со следующего попадания. Исправлена ошибка UI-02: клиент с `--hit-indicator` падал при старте на `unicode`.
  Native **NOT_RUN**, главный риск — загрузка второго ABC в Scaleform #717. План — [UI05](plans/UI05_NATIVE_SETTINGS.md).

## UI-06 счётчик фрагов в ушах и голубение за тимдамаг — в ветке `codex/ui-06-ears-teamkill`, не в main — 2026-11-02

- Ключ `"team_score": true` (нужны `profile13_battle`, `visibility_v1`), клиент не меняется: родные `VEHICLE_STATISTICS` и
  `TEAM_KILLER`. Счёт — функция журналов: +1 за врага, -1 за союзника вплоть до отрицательного, пожар идёт автору поджога.
  Порог голубения WG неизвестен, правила проектные: первый HP снарядом, сплэшем или пожаром, таран только убийством; флаг до
  конца боя, только своей команде. Итоги: необязательный блок `team_score` (Results10) заполняет `tkills`, `tdamageDealt`,
  `directTeamHits`, `isTeamKiller`, старые бои валидны, схема БД та же. Native **NOT_RUN**.
  План — [UI06](plans/UI06_EARS_TEAMKILL.md).

## UI-04 история событий боя и родные поля итогов — в ветке `codex/ui-04-battle-history`, не в main — 2026-11-02

- Ключ `"results_ledger": true`: журнал итогов получает необязательный блок `ledger` (Results9), из него родные
  `damageBlockedByArmor`, `potentialDamageReceived`, `damageAssistedRadio`, `damageAssistedTrack` и ассист по целям в
  `details`. Старые бои в БД валидны и не меняются, схема БД та же; расхождение блока с `details` — явный отказ.
  Ключ `"battle_events": {"version":1,"feed":true,"history":true}` и флаг клиента `--battle-history bottom|top` (нужен
  `--hit-indicator`): виджет истории на записях UI-02/03 и одна запись итогов в конце боя. Native **NOT_RUN**.
  План — [UI04](plans/UI04_BATTLE_HISTORY.md).

## UI-03 ленты событий боя и учёт блока, ассиста, поджога — в ветке `codex/ui-03-battle-feeds`, не в main — 2026-11-02

- Ключ `"battle_events": {"version":1,"feed":true}` и флаг клиента `--battle-feed labels|icons` (нужен `--hit-indicator`).
  Записи ленты идут по каналу UI-02 только после отдельного объявления `sr_battle_feed`; без ключа или объявления
  ни байта. Повторов при переподключении нет: READY закрывает канал. `battle_ledger.rs` считает блок, потенциальный
  урон, ассист двух видов и выжженное по проектным формулам; родные поля итогов заполнит UI-04.
  Native **NOT_RUN**. План — [UI03](plans/UI03_BATTLE_FEEDS.md).

## UI-02 индикатор обстрела и канал боевых событий — в ветке `codex/ui-02-hit-indicator`, не в main — 2026-11-01

- Ключ `battle_events` (`{"version":1}`, нужен `visibility_v1`) и флаг клиента `--hit-indicator standard|extended`.
  Канал только получателю через родной `updateArena(200)` после объявления клиента; без ключа или объявления
  ни одного нового байта. Native **NOT_RUN**, ждёт приёмки владельца. План — [UI02](plans/UI02_HIT_INDICATOR.md).

## BW-01 + INPUT-01 + TURRET-01 — приняты владельцем, в main — 2026-10-29

- Native (владелец, стенд `full-test-20261027-11`, Малиновка, 1 человек + 29 ботов, release-шлюз `d03969e`, Domain):
  бой 15×15 плавный до итогов; смена настроек в бою не выбрасывает (INPUT-01); отлёт башни после подрыва БК в
  процессе Jolt (TURRET-01); процесс боя убит во 2-м бою — закрыт только этот бой, новый процесс, 3-й бой до итогов
  (BW-01). TURRET-01 перенесён на генерируемые кодеки BW-01. Канонический gate 1857 PASS / 2 FAIL / 16 ignored.

## BW-01 Battle Worker отдельным процессом — в ветке `codex/bw-01-on-main` (от main `d0a9b9e`), не в main — 2026-10-29

- Ключ `battle_worker` (`{"version":1}`, тайм-ауты): шаг каждой арены (`advance_battle` + Jolt-сцена) — в своём процессе
  (тот же exe, loopback, токен через stdin, кадры с пределами); мир между шагами в шлюзе, журналы NET-01 идут
  приращениями. Потеря worker'а → `battle_worker_lost` → STAB-02 `contain_arena`; следующий бой — новый worker.
  Без ключа — прежний путь.
- Тесты `bw01` 9 PASS. Release-бенч NET-01 1+29, полный бой, `reliable-burst-v2`: оба режима без сбоев; worker —
  CPU 16,7 против 11,6 мс/шаг, p99 цикла +2 мс, кадр в конце боя ≈ 162 КБ. Native, канонический gate — NOT_RUN.
  План/итог/шаги стенда — [BW01_BATTLE_WORKER](plans/BW01_BATTLE_WORKER.md).

## TURRET-01 на BW-01 — в ветке `codex/turret-01-on-bw` (от `a5fb3ea` = main + BW-01 + INPUT-01), не в main — 2026-10-29

- Оторванная башня — тело Jolt в worker'е сцены (TURRET-01), кодеки BW-01 перегенерированы для `Flight`/`Launch`/
  `Trajectory`/`Jolt`/`World`. Полёт до покоя одинаков с `battle_worker` и без (побайтно без сцены; на настоящем Jolt —
  те же выборки и клиренсы). Набор шлюза — FAIL-множество как у базы. Native, канонический gate — NOT_RUN.
  [TURRET01_DETACHED_PHYSICS](plans/TURRET01_DETACHED_PHYSICS.md).

## INPUT-01 неподдержанные методы Avatar не выбрасывают из боя — в ветке `codex/input-01-settings-methods`, не в main — 2026-10-29

- Находка владельца (-11, BW-01): смена настроек в бою — Base `doCmdIntArr(CMD_ADD_INT_USER_SETTINGS=1600)` и
  `setDevelopmentFeature('server_marker')` (VERIFIED по #717) — ID вне таблицы шлюза → отказ → канал встал → `idle_timeout`.
- Таблица exposed-методов Avatar/Vehicle (INFERRED по .def, совпадает со всеми наблюдаемыми ID): нереализованные
  записи пропускаются по длине с логом; неразбираемый ID в Driving отбрасывает конверт целиком без применения,
  номер потребляется. Набор шлюза FAIL = `d0a9b9e` (94 = 94). Gate, release, native — NOT_RUN.
  План/итог — [INPUT01](plans/INPUT01.md).

## 15x15-интеграция — принята владельцем, в main — 2026-10-29

- В main одним слиянием `1bd0dce` (стенд -11): VIS-PERF, STAB-02, RES-30, MM-01 (с уровнями ботов по командам,
  окном очереди UINT32 и классом своей машины без matchmaker), POSTMORTEM-01, NET-01 (`pose_delivery`,
  copy-on-write журналы боя), AV-01.
- Владелец: бой 15х15 (1+29 ботов, Малиновка) при `"pose_delivery": "reliable-burst-v2"` — без «пинга» и выбросов;
  LAG_RESYNC 0, цикл к концу боя ~2 мс (было ~85). MM-01 3х3 на 4 клиентах, наблюдатель, звук/декали/индикатор — PASS.
- Канонический gate на `1bd0dce`: 1842 PASS / 2 FAIL (`tests_p04m`, известные) / 13 ignored.
- Не закрыто: `latest-unreliable-v1` в бою не проверен; late results с ботами не поддержаны; FPS клиента ~50 при 15х15;
  шаг арены ~20 мс растёт с think_ms ботов; таблица по уровням в окне очереди — нужен клиентский патч (решение владельца).

## AV-01 обратная связь боя — принята владельцем, в main — 2026-10-29

- Замечания владельца 29.10 (-11): невидимый стрелок без трассера/индикатора, нет двигателей, нет голоса «пробил/не
  пробил», декалей. По #717 (VERIFIED): шлюз не слал `showShotResults`, `showOwnVehicleHitDirection`, `onScoutEvent`,
  `engineMode` (create (0,0) = выкл.), `damageStickers`; `showTracer` клиента принимает отсутствующего стрелка.
- Сделано при `visibility_v1`: анонимный трассер невидимого стрелка (ID 0, старт +40 м по баллистике — проектная
  политика), его остановка/взрыв; попадание по себе от невидимого (эффект с ID 0) и индикатор урона; голос результата
  стрелку; «Противник обнаружен» по журналу первого засвета; engineMode из серверного ввода; декали (последние 30).
  «Вас обнаружили» в #717 нет (лампа без голоса). Звук выстрела невидимого стрелка невозможен (нужна сущность).
- Владелец 29.10 (-11, сборка `d988b3d` = a69ac83 + NET-01 + AV-01, бой 15×15 1+29): двигатели, голос «пробил/не пробил/
  обнаружен», декали — PASS; трассер незасвеченного отдельно не проверен (NOT_RUN). Gate `d988b3d` 1840/2/13 — норма.
  0x55/0x42 OBSERVED по голосу владельца. Индикатор урона 0x41 рисовался с противоположной стороны — исправлено
  (курс полёта снаряда вместо обратного), native-повтор NOT_RUN.
  План/итог — [AV01_BATTLE_FEEDBACK](plans/AV01_BATTLE_FEEDBACK.md).

## NET-01 доставка поз и измерение шага — принята владельцем, в main — 2026-10-29

- Ключ `pose_delivery`: `reliable-burst-v1` — все готовые надёжные тела за итерацию цикла (было одно);
  `latest-unreliable-v1` — вдобавок поза последнего тика вне надёжного окна пакетом `0x0408`, без повторов.
  Без ключа — прежний путь. Позы в `vehicle.def` объявлены Volatile (VERIFIED); приём клиентом `0x0408` с телом — UNKNOWN.
- Release-бенч 1+29: прежний режим теряет 38 из 1200 тиков поз (114 при 10 кадр/с, 122 с подвисаниями), надёжные
  тела ждут в окне до 230 мс; оба новых режима — 0 потерь, ожидание ≤ 1–36 мс. Лог: `NET01_STEP_STATS`/`NET01_SESSION_STATS`.
- Бои владельца 29.10, стенд -11, 1 + 29: `reliable-burst-v1` — FAIL («пинг 5000+»); без ключа — как утром;
  `reliable-burst-v2` (один tickSync на тик, части позы по одной за итерацию) — PASS по оценке владельца («пинга
  практически нет», счётчик 15–25). Трасса клиента 10 Гц (`--trace-pose-10hz`): часы клиента 1:1, своя машина
  ≈0,2 с за сервером без роста. Причина v1 (дубли tickSync) — INFERRED, сравнительной трассы нет.
- Бой 12:24 упал по fail-closed (накопленное отставание дедлайна из-за роста итерации до 86 мс). Причина — клоны
  `World`/`Session` с растущими журналами. Исправлено (`26f7387`): журналы copy-on-write. Release-бенч на полный бой:
  публикация 0,5 → 0,6 мс вместо 0,5 → 13–14 мс, итерация в конце боя 1,8 мс (p99 20–25) против 32 мс (p99 60).
  На стенде — NOT_RUN.
- План/итог/шаги — [NET01_POSE_DELIVERY](plans/NET01_POSE_DELIVERY.md).

## POSTMORTEM-01 наблюдатель после смерти и маркер убитого союзника — принята владельцем, в main — 2026-10-29

- Находки владельца 29.10 (-11, MM-01): `bindToVehicle` на союзника (камера наблюдателя, VERIFIED по #717
  `PostMortemControlMode.__switchToVehicle`) отвергался и стопорил надёжный канал → `idle_timeout`; союзник, убитый
  невидимым противником, получал только свойство `health` без `onHealthChanged` → живой маркер «0%».
- Исправлено: камера на свою/союзника/0 принимается без изменения власти и интереса, противник/неизвестный ID — отказ
  без отравления канала; `onHealthChanged` всегда, скрытый атакующий = ID 0. Набор шлюза FAIL = `c76fd62` (94 = 94).
  Канонический gate, release, native — NOT_RUN. План/итог — [POSTMORTEM01](plans/POSTMORTEM01.md).

## MM-01 очередь и подбор — принята владельцем, в main — 2026-10-28

- Ключ `matchmaker` (`team_size`, `tiers`, `tier_spread`, `wait_seconds`, `lease_seconds`): «В бой» — билет очереди;
  группа берёт свободную арену, когда полна или по тайм-ауту (остальное — боты BOT-01); резерв Domain только в свой бой,
  lease шлюза возвращает не севших. Без ключа — прежний фиксированный ростер.
- Окно очереди: родной `receiveQueueInfo` со счётом ожидающих по классам; таблицы по уровням в 0.9.1 нет (VERIFIED по
  `.def`/байткоду) — вопрос владельцу о клиентском патче.
- Тесты MM-01 19 PASS; набор шлюза 1699/94/12 против 1680/94/12 базы `6f3882a`, FAIL равны; Python FAIL ⊂ базы.
  Native, release, канонический gate — NOT_RUN. План/итог/шаги стенда — [MM01_MATCHMAKER](plans/MM01_MATCHMAKER.md).
- 2026-10-29: боты на одинаковых местах обеих команд — одного уровня (решение владельца после сценария A).
- 2026-10-29: пустое окно очереди (сценарий E) — длина ARRAY в `receiveQueueInfo` была 1 байт вместо UINT32;
  исправлено в `codex/mm-01-queue-info-array`, на стенде подтверждено. Без ключа — класс своей машины
  (`codex/mm-01-own-queue-class`).

## BOT-01 серверные боты на местах арены — принята владельцем, в main — 2026-10-28

- Native (владелец, стенд `full-test-20261027-11`, один клиент, Малиновка, release-шлюз `f1de7ba`): 1 игрок + 5 ботов
  (T-34, KV-3, M4 Sherman, Chi-Ri, T-34-85), бой с ездой, стрельбой ботов (50 выстрелов), уроном и итогами
  (`P08C_RESULT_FROZEN`, доставка в ангар) — PASS («всё хорошо»). Канонический gate 1772 PASS / 2 FAIL / 12 ignored
  (FAIL — `tests_p04m`). Конфиг стенда: `gateway.json` → `battle_players: 6`, `bots`; откат — `*.before-bot01.*`.
- Политика `project.bot01.route-hold-visible-aim.v1` — проектная, не исследованное поведение ботов WG. План/итог,
  release-бенч 1+29 — [BOT01_SERVER_BOTS](plans/BOT01_SERVER_BOTS.md).
- Не закрыто: больше 6 участников — RES-30 (Domain отвергает итоги); бой с ботами на нескольких клиентах не проверен;
  коммиты ветки после `f1de7ba` (`ef93d8a` объезд препятствий и упреждение, `38bd11f`) на стенде не проверены и не в main.

## BATTLE-ANY бой на любой машине каталога 0.9.1 — принята владельцем, в main — 2026-10-28

- Native (владелец, стенд `full-test-20261027-11`, 4 клиента, Малиновка, release-шлюз `dde88f9`): пилоты KV-3, M4 Sherman,
  Waffenträger auf E 100, Chi-Ri — исследование и покупка при нулевой экономике, экипаж своей нации, три типа снарядов,
  бой со стрельбой, попаданиями и итогами — PASS («всё работает как надо»). Канонический gate 1757 PASS / 2 FAIL /
  11 ignored (FAIL — `tests_p04m`, путь удалённого Codex worktree).
- Генератор: на этапе 1 было 246/128; текущая таблица после этапа 2 — 232 из 374 generated, 142 refused; на стенде — 5 курируемых + 4 пилота
  (манифест шаблонов v5, каталог `219b2f07…`). Переключение стенда — `tools/full_test_stand.py battle-any`
  (копии конфигов и БД, односторонняя миграция склада, `--disable` — откат). План/итог — [BATTLE_ANY](plans/BATTLE_ANY.md).
- Найдено на стенде и исправлено до приёмки (сгенерированные виды не были доведены до живого боя): `p04m_pool` и
  `BattleTemplate` требовали 5/7 шаблонов; посадка строила старое орудие с 0 снарядов и v1-модули отвергали generated;
  старт сцены искал вид только среди курируемых; эффект выстрела и урон искали снаряд только в `PROFILES`.
  Живой тест `battle_any_stand_four_pilots_start_one_scene_and_drive` (ignored, `BATTLE_ANY_STAND`): 4 пилота, SPAWN-15,
  одна сцена IPC7, езда и 4/4 выстрела. Не закрыто: ошибка внутри `contain_battle_failure` всё ещё завершает весь процесс
  шлюза; машины uk/china/france ждут коррекции наций каталога (FV215b (183) не в пилоте).

## SPAWN-15 команды на базах, раскладка до 30 машин — принята владельцем, в main — 2026-10-28

- Native (владелец, стенд `full-test-20261027-11`, 4 клиента, 2×2): команды у своих баз на Прохоровке; на Малиновке
  на release-шлюзе бой плавный, попадания, уничтожение танка и итоги — PASS. Найдено и исправлено попутно: поток
  поз оторванной башни забивал надёжный канал и замораживал мир после подрыва БК (старая ошибка main). Debug-шлюз
  с 4 машинами отстаёт на 150–500 мс за шаг — стенды с боями > 2 мест только на release. Канонический gate
  1746 PASS / 2 FAIL / 9 ignored (FAIL — `tests_p04m`, путь удалённого Codex worktree). Бои > 6 мест — до BOT-01 не заполнить.

- Ветка `codex/spawn-15-team-bases` на main `75a9437`. Проектная политика `spawn15-team-base-formation-v1`
  (`server/contracts/spawn_formations.json`, `tools/spawn15_formation.py`): 15 мест на команду у ctf-базы из пакета
  карты, лицом к противнику, отказ вместо наложения; ключ `spawn_policy`. Native-слоты 6..29 (алиасы 146..169,
  башни 170..193; таблица алиасов клиента 256×u32 — VERIFIED по PE); `battle_players` 7..30 только с политикой и
  `connection_capacity`. Исправлены пределы > 6: пакет позиций > 13 машин, binding с готовностью 29 машин.
- Jolt: 30 машин оседают на местах — Прохоровка, Малиновка (сцена, debug+release); Карелия — 60 одиночных прогонов.
  Набор шлюза 1663/83/9 против 1656/83/8 базы, FAIL-наборы равны. Release-бенч: Прохоровка 2×30 p99 1,4 мс;
  **Малиновка 30 — пики шага шлюза ≈ 90 мс, один 2×30 fail closed** (причина UNKNOWN, прежний код).
  План/итог — [SPAWN15_TEAM_BASES](plans/SPAWN15_TEAM_BASES.md). Канонический gate и native — NOT_RUN.
- Стенд -11: спавн у баз — PASS (владелец). Исправлено: поле конфига (предел 29), «замирание» после
  отрыва башни (поза покоящейся башни каждые 5 мс — ошибка и в main). Малиновка 2×2 выбросы — debug-шлюз не
  успевает за 4 машинами: **стенды с > 2 местами — только release-шлюз** (`build.py --release`, проверка в
  `full_test_stand.py prepare`).

## ARENA-01 несколько арен — принята владельцем, в main — 2026-10-27

- Native (владелец, стенд `full-test-20261027-11`: `arenas: 2`, `connection_capacity: 256`, Domain, 4 клиента,
  4 свежих владельца): два параллельных боя на Прохоровке дошли до итогов — PASS. Канонический gate
  1737 PASS / 2 FAIL / 8 ignored (FAIL — `tests_p04m`, путь удалённого Codex worktree). Живой бой пока ≤ 6 машин
  (нативная раскладка), большие арены — только модель/физика и бенч; для боёв > ~10 машин нужен release-шлюз.

- Ветка `codex/arena-01-multi-arena` на main `2da4baa`: `Arena` = мир + сцена Jolt + шаблон; K = 1..4 арен в процессе
  шлюза (ключ `arenas`, нужен `connection_capacity`); шаг арен — на потоках, изоляция ошибки/паники по арене;
  сбой арены возвращает в ангар только её игроков. Без ключа — прежний путь (FAIL-набор равен базе).
- Граница ростера — одна `MAX_ACTORS = 30` (клиент: `maxPlayersInTeam=15`); native-раскладка — 6 машин.
  Найдено бенчем: `InterestSet(u8)`, лимит 15 контактов танк-танк (парсер и домен), спавн 30 машин.
- Бенч release 30 машин: шаг p99 ≤ 4,5 мс, ≈ 0,08 ядра шлюза + 0,08 ядра Jolt на арену; debug-шлюз (на стендах)
  30 машин не держит. Malinovka: полоса спавна 2 не оседает (бои 3..6 мест там не стартуют). Native — NOT_RUN.

## GW-01 ёмкость Gateway — принята владельцем, в main — 2026-10-27

- Native (владелец, стенд `full-test-20261026-10`, `connection_capacity: 256`, Domain включён): игрок в ангаре
  не блокирует, бой стартует, когда входят оба, итоги и повторный вход без ошибок — PASS. Канонический gate
  1728 PASS / 2 FAIL / 7 ignored (FAIL — `tests_p04m`, путь удалённого Codex worktree). Узкое место 200 CCU —
  лимиты входа bridge (60/мин, 2 проверки пароля одновременно), не шлюз.

- Ветка `codex/gw-01-gateway-capacity` на main `b31f691`: ключ шлюза `connection_capacity` (2..256, только
  profile13, не с учебными комнатами и hold5). Ангарная сессия не держит место арены; Join берёт место, пока оно
  есть; бой стартует, когда все места арены готовы. Без ключа — прежний путь. Полный шлюз — настоящий 73.
- Gateway-набор: 1646/83/7 против 1638/83/7 у `b31f691`, FAIL-наборы равны. Инструмент `tools/gw01_login_load.py`.
- 200 синтетических native-входов/выходов на копии стенда `gw01-load-01` (6 своих владельцев через P08B
  stage/onboard): 200/200 успех, 73 — 0, 6 одновременных ангарных сессий при 2 местах арены; шлюз ≤ 62,8 МБ.
  Узкое место — bridge (10 входов/e-mail/15 мин, 2 scrypt, ~4,4 с фикстура). Канонический gate и native — NOT_RUN.
  План/итог — [GW01_GATEWAY_CAPACITY](plans/GW01_GATEWAY_CAPACITY.md).

## DOM-01 Domain service — принята владельцем, в main — 2026-10-26

- Native (владелец, стенд `full-test-20261026-10`, Domain включён): вход, ангар, окна экипажа и БК, бой на
  Малиновке и его итоги — PASS, всё быстрее прежнего. Канонический gate 1719 PASS / 2 FAIL / 7 ignored
  (FAIL — `tests_p04m`, путь удалённого Codex worktree). Флаг `domain_service` по умолчанию выключен.

- Ветка `codex/dom-01-domain-service` на main `e61a385`: один долгоживущий Python-процесс
  `server/domain/service.py` — единственный писатель аккаунт-агрегатов (ангар, бой, итоги, late results);
  протокол `wot091-domain.v1` по loopback с HMAC, флаги `domain_service` у шлюза и bridge (по умолчанию выкл. =
  прежний путь). Ответы побайтно равны ответам воркеров. Включение на стенде: `tools/full_test_stand.py domain`.
- Замер (медиана 5): чтения 0,86–0,90 с → 0,12–0,18 с, команды ~1,0–1,2 с → 0,26–0,47 с; аккаунт с 192 танкистами
  2,3–3,0 с → 0,36–1,02 с (цель < 300 мс для чтений там не достигнута). План/итог —
  [DOM01_DOMAIN_SERVICE](plans/DOM01_DOMAIN_SERVICE.md).
- Наборы против main в одной среде: новых FAIL нет. Канонический gate и native — см. выше.

## Сейчас: восстановление после чистки 2026-10-24 и регрессия P02 — 2026-10-26

- Чистка Codex 2026-10-24 удалила `local/stands`, `local/build` и опустошила `local/evidence`.
  Фикстуры восстановлены из переносных копий (побайтно по SHA таблицы переноса) и пересборкой
  MAPS-01/02 (`final01`, каталоги v8, зонд `probe02` — побайтно равны пинам). Резерв — `E:`.
- Регрессия `e4296af`: обход ворот profile13 в `ready_for_arena_base` для любого аккаунта с
  исследованиями. Исправлено (`9b6c566`): обход только при `arena_source_bundle`.
- Канонический gate этой ветки: 1712 PASS / 2 FAIL / 6 ignored. FAIL — `tests_p04m` (2): тест
  читает сборку физики по пути удалённого Codex worktree `p05c-night-shared-physics`; NOT_RUN по
  окружению, не код. Стенды не пересобраны; клиенты требуют сверки установок — NOT_RUN.

## Текущий статус: CREW-ANY native lifetime gate принят — 2026-10-25

Карточка `codex/crew-any` закрыта на clean native evidence. Изолированный B/v2
T-26 стенд запускался после удаления WAL/SHM и пересоздания fixtures. install13
доказал 175 настоящих CMD303 hires `#18..#192` и 162 настоящих original CMD306
dismissal’а; install16 отдельно доказал отказ `#193` с raw `[5,4609,3,0]`,
proxy/onCmdResponseExt `-10`, без `_update`, inventory extension или изменения
snapshot. Финальная SQLite-проверка: `next_native_id=193`, `free_left=0`,
`configuration_revision=354`, active=30, retired=162.

Evidence: `local/stands/crew-any-native-t26-lifetime-fix-20261025-01/evidence-native-lifetime-controller-20261025.json`.
Проверки: targeted unittest 49/49 PASS, py_compile PASS, git diff --check PASS.
Патчи bounded guard’ов конечны: input=4096, selector=1024, recruit windows=256,
dismissal windows=256, lifetime deadline=7200s. Старые install07–12 FAIL/partial
сохранены в trace/history и не подменяют clean acceptance.

**Приёмка карточки: PASS / ACCEPTED.**

Отдельная стыковка source-bundle с уже принятым shared profile13 маршрутом
закрыта финальным bounded native прогоном 2026-10-26. Режим
`legacy091-profile13-source-bundle` принимает только hash-anchored portable
bundle под `config.local_root`; primary db1 получил per-admission
`SHARED_SOURCE_BUNDLE_VERIFIED` (MS-1/type 3329/native inventory 1/HP 90), а
сам бой остался под authority profile13 reservation/FrozenLoadout.
Перед кликами оба клиента дошли до `native_hangar waiting_visible=false` с
`items_cache_synced=true`, `vehicle_model_loaded=true` и `native_connected=true`.
FightButton нажат последовательно. Зафиксирован один настоящий shared-бой
`7307814506127825970`: gateway записал `SHARED_WORLD_STARTED`,
`P05C_SCENE_READY`, два `SHARED_ENTRY` и два `SHARED_ANNOUNCED`, без
`SHARED_BATTLE_FAILED`; оба native клиента выполнили `onEnterWorld`,
`updateVehicleHealth` и штатный выход из world. Жизненный цикл дошёл до
`P08C_LATE_SEAL_FROZEN`/двух `P08C_RESULT_FROZEN`, двух
`P06T_LOSS_TERMINAL_FROZEN`, двух `P06T_LOSS_RESULT_COMMITTED`,
`P08C_RESULTS_COMPLETE` с `native_account_delivery=true` и двух
`SHARED_RETURN reason=natural_result_confirmed`. Оба клиента вернулись в
стабильный native hangar с `waiting_visible=false`, загруженными моделями и
синхронизированным cache. В процессе writer потребовался bounded retry после
обновления post-finish fixture; задержка сохранена в gateway evidence и не
скрыта. Exact legacy r3/r4 manifest по-прежнему не заявляется.
Evidence: `local/evidence/p02-source-bundle-profile13-20261026-final-result-03.json`.

Отдельная bounded-диагностика update-gate на 2026-10-25 завершена частично:
свежая research-copy через loopback `127.0.0.1:20340` дошла до обычного
`LoginView`, update/modal-событий не было, install rollback и остановка стенда —
PASS. Login-submit не выполнялся, поэтому raw reply/auth reason — `NOT_RUN`, а
не PASS. Evidence:
`local/evidence/update-gate-bounded-20261025-02/update-gate-evidence.json`.
Старый `tools/wg_probe` остаётся запрещённым backend для новых запусков: его
toolkit-путь формирует `74` (`UPDATER_NOT_READY`), тогда как актуальный gateway
для #717 отправляет `73` (`SERVER_NOT_READY`).

Один bounded account-run выполнен 2026-10-25 на той же чистой копии после
ручного ввода тестовой пары в native LoginView. Raw login reply был пойман в
loopback capture: `packet[11]=67` (`INVALID_PASSWORD`), 35 байт; callback клиента
зафиксировал `LOGIN_REJECTED_INVALID_PASSWORD`. Gateway успел записать
`SHARED_LOGIN_STARTED request_id=86428 identity_jobs=1`; финальная строка
`AUTH_REJECT` не успела попасть в stdout до controlled stop, поэтому причина
помечена как `INFERRED_FROM_SOURCE_AND_RAW_REPLY`: ветка `session.rs` с
`auth_result=Ok(None)` отправляет code 67 и означает отказ identity-проверки.
Коды `73/74` в этом единственном прогоне не наблюдались. Evidence:
`local/evidence/update-gate-bounded-20261025-03/update-gate-account-evidence.json`;
raw reply SHA256 `9df31244c3397a43a79d645b221fce617ac0dc2942edb894960c23dc39d0bce5`;
trace SHA256 `7d2e1961b31e05dfaa6003c6137354a21224be04b5b5b68626c8ee39eea0ca1e`.

Повтор с явно выбранным локальным account label `sr.ascii.f4d1e9` дал тот же
результат: raw `packet[11]=67 (INVALID_PASSWORD)`, а callback клиента —
`LOGIN_REJECTED_INVALID_PASSWORD`. `73 SERVER_NOT_READY` и `74
UPDATER_NOT_READY` снова не наблюдались. Gateway успел записать только
`SHARED_LOGIN_STARTED request_id=46912 identity_jobs=1`; финальный `AUTH_REJECT`
не был flushed до controlled stop. Поэтому причина gateway классифицирована как
`INFERRED`: ветка `session.rs` сводит `auth_result=Ok(None)` к коду `67`, а
различить lookup неизвестного аккаунта и несовпадение пароля этим контрактом
нельзя. Клиент, сервисы и install ledger после прогона восстановлены.

Evidence:
`local/evidence/update-gate-bounded-20261025-04/update-gate-account-evidence.json`;
raw reply SHA256 `30bac841b65ac369133798066e193fdc54acbfd9fc21d4ff5ad27765c78ba65e`;
trace SHA256 `2748bb57415c1b71b9cc01e3d2f0856c6b31b9d2b50dd79390a70407e6fd3cf8`.

Активная worktree identity-запись после повторной read-only сверки уже принимает
известную локальную test-пару из
`D:/WoT_9.1_Server/local/client-controls/crew-t26-control-20261024-06.json`;
перезапись `web.sqlite` не потребовалась. Bridge-only POST на
`127.0.0.1:3692/internal/native/login` вернул HTTP `200`,
`native_database_id=1`, `name=sr_ascii_f4d1e9`; клиент и gateway не запускались.
Следовательно, прежний native `67` нельзя объяснять drift’ом активного hash:
наиболее вероятен другой вручную введённый email/password byte sequence
(короткий label вместо полного canonical email или отличие в пароле). Plaintext
в trace отсутствует по дизайну.

Identity evidence: `local/evidence/update-gate-bounded-20261025-04/credential-sync-bridge-evidence.json`;
status `PASS_ALREADY_SYNCED_BRIDGE_ONLY`. Предыдущий audit superseded этим
evidence: `local/evidence/update-gate-bounded-20261025-04/identity-record-audit.json`.

Один native bounded-прогон с полным email `sr.ascii.f4d1e9@example.test` и той же
локальной test-парой завершился успешно: оригинальный `LoginView.onLogin` сделал
submit, trace получил callback `LOGGED_ON`, gateway записал
`SHARED_LOGIN_STARTED request_id=21802`, `SHARED_SESSION_PENDING ...
authenticated=true` и `SESSION_ACTIVE id=1`. Raw login success reply —
`packet-000005-server_to_client.bin`, 28 байт, `packet[11]=1`, без `67`, `73` или
`74`; gateway `AUTH_REJECT` не записал. Сохранены пять повторных login request’ов
`21802..21806` и полный loopback native UDP capture до account sync. Внешний
сниффер не использовался; client/services после прогона остановлены, install
ledger восстановлен.

Evidence: `local/evidence/update-gate-bounded-20261025-06/update-gate-native-account-evidence.json`;
raw reply SHA256 `c5669abe58b8f0d72e26c05ca099ea38d5b48511b68c8040e6e67ae9b5240b5b`;
trace SHA256 `67db58024d9782132dd9736a432ffb8a24292df502b7e2c36bd8fd1a595e20e8`;
capture manifest SHA256 `d89b1a00fd62dcbcb5b61f48514dea960ddd26f7be296f6030a063c1c733aefb`.

Следующий bounded native-шаг BaseApp/Account sync до готового ангара выполнен
2026-10-25 на свежей установке той же research-copy. После `LOGGED_ON` trace
зафиксировал настоящий `Account.onBecomePlayer`, ответы `onCmdResponseExt`
для запросов `221/222/223` с `result=1`, streams `221=2904`, `222=23109`,
`223=103` байта с совпадающей целостностью, `Account.showGUI` и запрос `224`
с `result=0`. Gateway записал `SHARED_BASE_BOUND`, `SESSION_ACTIVE`, три
`ACCOUNT_SYNC_REQUEST` (`command=100/300/600`) и `ACCOUNT_SHOW_GUI_QUEUED`.
Loopback capture сохранил 311 native-пакетов: 118 client→server BaseApp и 187
server→client BaseApp; payload’ы не печатаются, в evidence лежат только пути,
размеры и SHA-256. На `77.20 s` клиент перешёл в `LobbyView` с `Hangar`,
`hangar_space_inited=true`, `hangar_space_loaded=true`, четырьмя загруженными
моделями и выбранным MS-1. Запрос приложения `226` получил штатный
`result=-10` (`APPLICATION_UNAVAILABLE`, `state_changed=false`) и не помешал
готовности ангара. Бой и действия в ангаре не запускались; внешний сниффер не
использовался. Клиент, оба сервиса и install ledger после прогона остановлены
и восстановлены.

Evidence: `local/evidence/update-gate-bounded-20261025-07/baseapp-account-hangar-evidence.json`;
raw login reply SHA256 `21bd31398613e3fb6e0ca3db13a245c0649b2cd0035494dde64958a6d77067c9`;
trace SHA256 `790dd66218cac2356c1c0db24a2825429a491417f4436ef66e973f68d3af0172`;
capture manifest SHA256 `da2ea9cab55efddf32641787eabb51aa662e0f5262b51764e380df1d42151e07`.

Единственный следующий шаг: выполнить обычный review/merge карточки по
`docs/07_CODEX_WORKFLOW.md`, затем открыть следующую карточку для оставшихся
не native lifetime задач.

После merge `5667317` начат отдельный bounded P02-срез Avatar/Arena-ready на
ветке `codex/p02-arena-ready-bounded`. Preflight установки клиента прошёл и
полностью откатился, bridge был поднят и остановлен, но native-клиент намеренно
не запускался: доступный `local/build/server/gateway-crewany-native01` отверг
режим `legacy091-arena-ready-probe` на CLI и показал старый набор режимов без
arena-probe entrypoint. Закреплённый Rust toolchain в этом worktree тоже не
доступен: `local/toolchains/cargo` указывает на отсутствующую junction-цель,
`cargo`/`rustc` не найдены. Поэтому Avatar/Arena raw/callback evidence имеет
статус **NOT_RUN**, а не PASS.

Evidence: `local/evidence/native-arena-ready-20261025-01/arena-ready-preflight-evidence.json`;
gateway SHA256 `5200ceb429c38abe8911a77d4eff2038d6bb68a8ad65015644d09160da9fccbd`;
CLI stderr SHA256 `4f5708c22c8745fd5516330bc57c46cea15d88d94ee32dc3388e78f361fdb361`.
Единственный следующий шаг этой ветки: восстановить/собрать свежий gateway с
`legacy091-arena-ready-probe`, затем повторить новый one-shot control и native
run с тем же typed trigger-контрактом.

Этот следующий шаг выполнен частично в worktree `codex/p02-arena-ready-bounded`.
Изолированный Rust toolchain восстановлен (`rustc 1.90.0`, `cargo 1.90.0`),
LLVM-MinGW архив проверен по SHA; pinned `rustup-init.exe` не подменялся после
обнаруженного hash drift. Свежий legacy gateway
`local/build/server/gateway-arena-ready-20261025-11/target/debug/p01-wg-probe.exe`
принял CLI `legacy091-arena-ready-probe`; `arena_ready091::tests::` — 7/7 PASS.
Отдельный session regression filter `arena_transition_requires_all` — 1/1 PASS.
Полный suite оставлен как `FAIL_ENVIRONMENT_FIXTURES` (1217 passed, 494 failed,
6 ignored; fixture-dependent ENOENT), а не выдан за toolchain PASS.

Bounded run `native-arena-ready-20261025-12` дошёл до настоящего
`LOGGED_ON`/`SESSION_ACTIVE`, Account sync `221/222/223`, `ACCOUNT_SHOW_GUI` и
loopback capture (payload bytes не публикуются). После typed trigger gateway
один раз записал `ARENA_BASE_TRIGGER_REJECT reason=queue_failed`; native
Avatar/Space/Vehicle/Ready callbacks и `setClientReady` не наблюдались. Входной
fixture был profile13 `p09d-r21`, тогда как fail-closed
`arena_vehicle091::load` требует точный pinned profile4 manifest
15490 bytes/SHA `ea9678…`; это зафиксировано в evidence, а не замаскировано
повторным heartbeat.

Evidence: `local/evidence/native-arena-ready-20261025-12/arena-ready-evidence.json`;
rollback: `local/evidence/native-arena-ready-20261025-12/restore.json`;
profile4 feasibility candidate:
`local/stands/profile4-arena-ready-source-bundle-20261025-01/candidate-receipt.json`.
Исходная копия клиента и основная DB не трогались, все процессы стенда остановлены.
Статус P02 bounded slice: **NOT_RUN_NATIVE_VEHICLE_LOADER / NOT_ACCEPTED**.
Единственный следующий шаг: восстановить exact legacy r3/r4 manifests либо
открыть отдельную карточку на source-bundle-aware fail-closed arena loader,
после чего повторить свежий native Account→Avatar→Space→Vehicle→Ready run.

Отдельная opt-in карточка source-bundle-aware loader выполнена частично в
worktree `codex/p02-arena-source-bundle`. Strict legacy loader не ослаблялся:
добавлен отдельный режим `legacy091-arena-ready-bundle-probe`, который принимает
только hash-anchored portable bundle под `gateway.local_root` и держит profile13
Account/Avatar отдельно от profile4-derived Vehicle state. Targeted Rust tests
portable source bundle — 2/2 PASS, capture CLI — 3/3 PASS. Полный старый набор
vehicle tests оставлен `NOT_RUN_FIXTURE_DEBT`: шесть существующих тестов требуют
отсутствующие exact legacy fixture-файлы.

Bounded native run
`local/evidence/native-arena-source-bundle-20261025-01/arena-source-bundle-evidence.json`
дошёл до настоящих callbacks Account→Avatar→Space→Vehicle: gateway записал
`ARENA_VEHICLE_ANNOUNCED`, `ARENA_ENTITY_UPDATE_REQUEST` и
`ARENA_VEHICLE_QUEUED`, клиент выполнил `PlayerAvatar.onSpaceLoaded` и
`Vehicle.onEnterWorld`. После этого клиент остался в `BattleLoading` с
`ready=false`, gateway — в `ARENA_READY_WAITING`; `ARENA_READY_ACCEPTED` и
Prebattle не наблюдались до controlled timeout. Loopback capture сохранён как
425 packet-файлов / 34 907 wire bytes, payloads в STATUS не печатаются; client
trace — 524 строки, SHA-256 указан в evidence. Процессы остановлены, install2
восстановлен.

Приёмка source-bundle карточки: **NOT_ACCEPTED_HASH_ANCHORED_PORTABLE**.
Exact legacy manifest bytes по-прежнему отсутствуют, поэтому этот прогон доказывает
только hash-anchored portable Vehicle bridge и native Vehicle callbacks, но не
совместимость с полным legacy arena-ready и не настоящий бой. Два клиентских
`deactivateTrigger` исключения отмечены как OBSERVED diagnostics; причинность не
доказана. Единственный следующий шаг: отдельно исследовать, почему native
клиент не публикует Ready после `onSpaceLoaded`/`Vehicle.onEnterWorld`, либо
вернуться к восстановлению exact legacy r3/r4 manifests.

Повтор source-bundle прогона с исправленным порядком trigger выполнен в
`local/evidence/native-arena-source-bundle-20261025-02/`: trigger `avatar_ready`
создан только после `arena_entry_resources`, трёх стадий `arena_bootstrap` и
`arena_ready_armed` в штатном ангаре. Это сняло прежний timing/bootstrap race.
Клиент без Python-исключений прошёл настоящий Avatar init до финального
`__onInitStepCompleted` offset `640`, `Vehicle.startVisual` offset `407`,
`userSeesWorld`; native trace получил `arena_ready_complete` с двумя PNG и
родным PREBATTLE countdown. Gateway записал `ARENA_READY_ACCEPTED` для
33-байтного compound (`sequence=18`, `create_sequence=106`) и
`ARENA_PREPARATION_QUEUED` (`reliable_sequence=108`, `body_bytes=105`), без
reject/error. Клиент завершился через `arena_ready_observed` до запуска боя;
полный battle/movement/fire/result остаются NOT_RUN.

Финальный delayed-trigger evidence: `local/evidence/native-arena-source-bundle-20261025-02/arena-source-bundle-evidence.json`;
trace — 1 063 строки, capture — 357 packet-файлов / 34 420 wire bytes, rollback
и cleanup — PASS. Статус обновлён до **OBSERVED_NATIVE_READY_HASH_ANCHORED_PORTABLE**:
native Ready/Prebattle для portable hash-anchored режима подтверждены, но exact
legacy manifest bytes отсутствуют, поэтому это всё ещё не full legacy PASS и не
приёмка настоящего боя. Предыдущий run01 остаётся историей ложного раннего
trigger, а не причиной gateway.

## История статуса до clean lifetime gate

## Сейчас: CREW-ANY — T-26/profile13 native slice принят, full card частично открыта

Карточка живёт в ветке `codex/crew-any`. На стенде
`local/stands/crew-any-native-t26-20261024-03` выполнен запрошенный native-шаг:
чистый v2 B-аккаунт с T-26 inventory `4`, тремя unskilled 50% членами экипажа,
пустыми навыками и AP/APCR/HE `96/32/32`; затем P04M recruitment в казарму создал
unassigned tankman `native_id=16` (revision `137→138`). Доказательство команды —
`local/stands/crew-any-native-t26-20261024-03/evidence-crew-barracks-t26.json`.

Оба native-клиента вошли в один настоящий profile13 бой на `05_prohorovka`:
B inventory `4` и A inventory `5`. Gateway записал `P08B_QUEUE_PENDING` Join,
`P06T_LOSS_RESERVED`, `SHARED_WORLD_STARTED` (`sessions=2`, `actors=2`),
`P05C_SCENE_READY`, `SHARED_ENTRY`, `SHARED_ANNOUNCED`, native snapshots и
подтверждённые результаты. Бой `4932769758126515471` завершился с двумя
`p06t_result.acked=1`; резервации закончены на ревизиях `141` и `198`.
Оба клиента оставили полноценные native traces с `native_fight_call`,
`arena_bootstrap`, `shared_native_snapshot`, `native_avatar_call` и
`onLeaveWorld`. Скриншоты countdown/боя/результата лежат в
`local/stands/crew-any-native-t26-20261024-03/evidence-profile13-t26-prohorovka-20261024/`.

Причина сообщения «сервер не готов» на приложенном скриншоте — клиентская
модалка «Требуется обновление»: она блокирует `sr_interactive.py` до native login.
После её закрытия и чистого перезапуска сервер принял обе сессии; это не новый
дефект gateway. Авторизационные изменения стенда делались только с резервными
копиями `web.before-*.sqlite`; секреты в доказательства не записывались.

В этом запуске вручную пройден native UI найм T-26. Оригинальный client callback
зафиксирован как `CMD303` с raw-layout `[5,4609,3,0]`: profile13 native shop
действительно публикует revision 5. Gateway нормализует его в принятый внутренний
P04K layout `[3,4609,3,0]`; это подтверждено исходником нормализации и успешным
ledger/SQLite commit. Новый tankman — `native_id=19`, роль `driver`,
`result_code=0`, конфигурационная ревизия экипажа `67→68`, бесплатный остаток
`174→173`. Доказательство —
`local/stands/crew-any-native-t26-20261024-03/evidence-native-ui-cmd303-t26-20261024.json`.

Следом выполнена отдельная capacity-проверка в свежей копии стенда
`local/stands/crew-any-native-t26-capacity-20261025-01` на том же чистом v2 B-аккаунте.
Настоящий native CMD303 из окна Казармы нанял 17-го tankman для T-26: raw
`[5,4609,3,0]`, роль `driver`, `result=0`, `inventory_id=17`, ledger revision
`143→144` и `snapshot_revision=144`. В SQLite `p04d_crew_meta` зафиксировано
`next_native_id 17→18`,
`free_left 176→175`, `configuration_revision 16→17`; после операции профиль13
содержит 17 членов. Evidence —
`local/stands/crew-any-native-t26-capacity-20261025-01/evidence-native-capacity-id17-20261025.json`,
trace и screenshot указаны в [ACTIVE_GATE](ACTIVE_GATE.md).

Исторически до clean lifetime gate: T-26/profile13 slice и boundary `#17` были PASS,
а full card оставалась PARTIAL / NOT_ACCEPTED: native boundary `#17` PASS, но native lifetime
`#18..#192` и отказ `#193` ещё **NOT_RUN**. Automated P04K evidence guard
по-прежнему намеренно MS-1/ИС-7-only. Подробная матрица и единственный
следующий шаг — в [ACTIVE_GATE](ACTIVE_GATE.md).

Попытка lifetime-прогона после этого boundary авторизовалась как B
(`native_database_id=2`) и прочитала native Казарму (`total=17`,
`unassigned=2`). После обновления списка client patch зафиксировал повторяющийся
`p04k_barracks_renderers_pending` с `ready=false`: виртуализированный original
renderer-пул не довёл `buy` tile до готового состояния. Поэтому native
RecruitWindow не открылся, `CMD303 #18` не был отправлен, а SQLite осталась на
`next_native_id=18/free_left=175/configuration_revision=17`; в P09D осталось 28
старых команд. Proof —
`local/stands/crew-any-native-t26-lifetime-20261025-01/evidence-native-lifetime-blocked-20261025.json`.
Это технический UI blocker для следующего шага, а не серверный отказ capacity.

После tail-only renderer fix повторный bounded native-запуск на
`local/stands/crew-any-native-t26-lifetime-fix-20261025-01` подтвердил
`p04k_barracks_open` и `p04k_barracks_window_ready` для того же списка
`total=17/unassigned=2`. Renderer blocker снят, но native selector цепочка
остановилась после одного `updateNationDropdown`: оригинальный `buyTankman`
callback не вызван, `CMD303 #18` не ушёл. Доказательство —
`local/stands/crew-any-native-t26-lifetime-fix-20261025-01/evidence-native-lifetime-fix-blocked-20261025.json`, trace
`D:/WoT_9.1_Server/local/client-runtime-crew-lifetime-fix-native-20261025-01/native-96800-1792898583101.jsonl`.
DB не изменилась (`next_native_id=18/free_left=175/configuration_revision=17`),
поэтому `#18..#192` и отказ `#193` остаются **NOT_RUN**. Статус full card:
**PARTIAL / NOT_ACCEPTED**; серверный capacity отказ не наблюдался.

## Historical note

The earlier PARTIAL / NOT_ACCEPTED wording below predates the clean install13/install16 native evidence. The active status is the accepted lifetime gate at the top of this file.

## Ранее: MAPS-01 + MAPS-02 приняты владельцем (2026-10-21, стенд `-09`, Малиновка)

Ветка `codex/integration-maps02-poles` (main `2f611ec` + MAPS-01 `27488a5` + MAPS-02
`e973862`). Native (владелец): бой на Малиновке — рельеф, деревья валятся; столбы
(`fallingAtoms`, каталог v8 `61dd9a23`) на малой скорости стоят (танк проходит сквозь,
как в 0.9.1 по маскам коллизии), на скорости сносятся — PASS. Ограничения: постройки
(`structures`) и часть заборов/фрагилов исключены с причинами; выстрел по столбу — отдельная
карточка (D2). Доработка: `full_test_stand.py map` принимает только v7 — на `-09` каталог
v8 подставлен вручную (`battle-profiles.v7-malinovka.json` — откат).

## Ранее: CAT-01 единый каталог — принят владельцем 2026-10-21 (стенд `-07`, Прохоровка, флаги каталога включены)

Каталог `config/catalog/catalog.v1.json` (SHA `a6bd44f4…`) собирается `tools/catalog_build.py`
из пинов клиента + `server_profiles.v1.json`; генерации Rust/Python/JS/Py2.7; допуск —
поле `battle_admission`. Потребители (шлюз `parse_frozen`, bridge `p06t-mixed`/`p04m-pool`,
Python реестр/`freeze_mixed`, клиент `map_drive_client`) читают каталог только за флагами,
прежние списки остаются ([research](research/CAT01_SINGLE_CATALOG.md)). Контракт и сторы в
обоих режимах PASS; канонический gate `gateway-integration-20261021-01` (CAT-01 + MAPS-01)
1700/0/5; native владелец: бой Т-34 против Т-34-85, покупка, окна MS-1/ИС-7 — как прежде (PASS).
Флаги по умолчанию выключены; включение по умолчанию — отдельное решение.

## MAPS-01 — конвейер карт (ветка `codex/maps-01-map-pipeline`, не слита)

Один экспортёр `tools/map_package.py` (пакет карты с SHA-256: рельеф, физика, снарядная
геометрия, арена, статический native-индекс разрушаемого), реестр карт
`server/contracts/map_registry.json` вместо `enum MapId` в gateway и физике. Карелия/
Прохоровка — побайтно прежние пины/буферы/каталог; Малиновка — новая карта реестра.
Отчёт по 44 картам и факты — [MAPS01](research/MAPS01_MAP_PIPELINE.md).
Native-бой на Малиновке — NOT_RUN (владелец); `fallingAtoms` — исключены (правило
падения UNKNOWN).

## MAPS-02 — fallingAtoms (ветка `codex/maps-02-falling-atoms`, не слита)

Одобрено владельцем 2026-10-21 (D1–D4), реализовано: триггеры столбов, каталог v8/v9,
sensor-тела в IPC7, доменное правило и публикация `fallenColumns` 0xa0. Факты и
доказательства — [MAPS02](research/MAPS02_FALLING_ATOMS.md), план —
[plans/MAPS02](plans/MAPS02_FALLING_ATOMS.md). Gateway gate в worktree 1423/281/5, FAIL-набор = базе MAPS-01;
native-проверка владельца (Прохоровка) — NOT_RUN.

## Ранее: BRIDGE-01 + LOGIN-01 приняты (2026-10-20)

Интеграционная ветка `codex/full-test-integration-20261020` (main `859452d` +
`codex/full-test-pending-login-queue` + `codex/full-test-bridge-latency`): канонический
gate `gateway-integration-20261020-01` **1691 PASS / 0 FAIL / 5 ignored** (composition02
больше не падает), exe `e28b646e…`. Стенд `-06`: владелец — оба клиента вошли
одновременно, операции ангара быстрее, бой работает (native PASS). Следующая карточка —
CAT-01 (ADR-002).

## Ранее: FULL-TEST (2026-10-19) — слит в main 2026-10-20

Слит по приёмке владельца (native PASS, стенд `-05`) с явным исключением: полный gate
1685 PASS / 1 FAIL — `p08b_restart_cas_composition02` падает только под нагрузкой из-за
медленного старта bridge (проходит отдельно). Исправление — карточка bridge
(постоянные воркеры, кеш каталога). Дальше: независимый вход аккаунтов (ветка
`codex/full-test-pending-login-queue`, в работе), затем экипаж/БК для любой машины.

**Main `ffce8cb` (STAB-01) не менялся с 15 октября.** Всё последующее — одна
неслитая цепочка карточек P08B → P08C → P05C → P07B → P06T → nightly polygon →
ram publication (213 коммитов над main). Каждая карточка требовала native-приёмки,
а каждый native-прогон обрывался первым fail-closed сбоем, поэтому ни одна не
слилась. Текущая ветка `codex/full-test-20261019` — интеграционная голова этой
цепочки; [ACTIVE_GATE](ACTIVE_GATE.md) — один общий сценарий.

Исправлено в этой карточке (канонический gate 1685 PASS / 1 FAIL под нагрузкой,
проходит отдельно 1/0; native NOT_RUN; [19.10](research/FULL_TEST_20261019.md),
[20.10](research/FULL_TEST_20261020.md)):

- сбросы боя: выстрел в упор, паузы цикла gateway, гонка тестов каденса;
- стенд, физика, мост и клиентский патч из одного checkout (раньше физика без
  `279be0c`, клиенты — из ночного клона);
- отрыв башни: у жертвы больше нет второй башни, у атакующего она не исчезает;
- поворот на ходу делит скорость с вращением корпуса;
- явная политика `test_lab.zero-economy.v1`: 100 слотов, все цены 0, премиум без
  исследования, снаряды пула ≥100; купленные Т-26/Т-34/Т-34-85 допускаются в бой
  (стенд `-04`: у A готов Т-34, у B Т-34-85; UI экипажа/БК для них не подключён);
- проектный звук лампы 6-го чувства (`gun_intuition`, не оригинал 0.9.1);
- сервис profile13 живёт 12 ч вместо 1 ч.

## Принято владельцем раньше (native)

- STAB-01: изоляция ошибок боя, возврат и повторный вход (в main).
- P08B/P08C: вход в бой из ангара профиля 13, отсчёт, захват, итоги, возврат.
- P05C: переворот, столкновения, захват; таран без вылета (19.10, после `aa0dfcc`).
- P07B: геометрия засвета, переворот МС-1 с сохранением видимости, визуальная лампа.

## Открыто

- Native FULL-TEST по [матрице](ACTIVE_GATE.md): движение, покупки и бой на
  купленных Т-26/Т-34/Т-34-85, экипаж/БК, отрыв башни, звук лампы `gun_intuition`.
- Не сделано: коллизия ствола оторванной башни (нет тела в Jolt); ёмкость экипажа
  >16 за всё время аккаунта (CHECK в SQLite); бой на купленных машинах вне пула
  5 типов (нет профилей физики/брони); разрушаемость всех объектов всех карт
  (Прохоровка 1038 из 3904, других карт нет в экспорте).
- Причина пауз главного цикла gateway — UNKNOWN (теперь каждая пишется
  `SHARED_DRIVE_LAG_RESYNC`).
- Python full suite (Python06): 12 FAIL / 45 ERROR — прежний долг.
- P10B (N игроков), NET-02 (два ПК), микролаг ~150 мс.
- Задержка bridge (ветка `codex/full-test-bridge-latency`, не слита, стенд не
  перезапущен): кэш производного каталога + memo `Catalog.sha256` + один `lstat`
  на компонент — воркер ~3× быстрее (≈3,1 → ≈1,05 с), ответы побайтно равны base;
  [план](plans/FULL_TEST_BRIDGE_LATENCY.md). Долгоживущие воркеры — после очереди входа.
- D: освобождено 44 ГБ удалением старых `local/build/*/target` (решение владельца 19.10).

## CAT-NATIONS — независимая проверка (29.10.2026)

На `6923d28` выявлен риск миграции базы с LATE: старый мигратор может оставить старый late marker при PASS. В рабочее дерево перенесён guard из невлитого наследника `033569d`: непустая late/reservation/research-история отклоняется, её перенос не реализован. Backup резервирует имя с `O_EXCL`, но защита от подмены пути не доказана: нужна отдельная копия, остановленные writers и доверенный каталог. Проверки текущего дерева в данном проходе — NOT_RUN, приёмка CAT-NATIONS не пройдена. Подробности — в плане ниже.

Ветка `codex/cat-nations-independent-review` от `a54b6aa`: работа `c37a61c` перенесена без изменения чужой ветки. Исходные данные #717 подтверждают порядок наций, 275 мм HESH и барабаны 6/4. Текущая таблица 232/142; добавлены FV215b (183), 113 и Bat.-Châtillon. Миграция усилена; synthetic 18 PASS, историческая копия БД: apply/rollback PASS и 46 таблиц равны. На 30.10 парные проверки были подготовлены, но PERF-02 завершилась с 2 FAIL `impact segment first surface differs from contact`, причина на тот момент была UNKNOWN; LATE-BOTS тогда не запускала тяжёлые проверки. Для этого HEAD полные наборы CAT-NATIONS и gate — NOT_RUN. Native на этом HEAD и изменение стенда -11 — NOT_RUN. План: [CAT_NATIONS_FIX](plans/CAT_NATIONS_FIX.md).

31.10: входы 8 тестов перештампованы на новый каталог, исправлена проекция pool-профиля после миграции (`CORRUPT_STORE`). Gate D: на `21d1666` — 1857/2 FAIL (только база `tests_p04m`), Python FAIL/ERROR = база. Мигратор не покрывает `battle_owner_hold_schema`; native и стенд — NOT_RUN.

## IMPACT-01 — запасная перепривязка первой поверхности попадания — принята владельцем, в main — 2026-10-31

- Перенос части `geometry.rs` из `c27f83c` (интеграция PERF-02) на main `711803e`: если подтверждённое
  мировое первое попадание из-за ulp-погрешности f32 не попадает в исходную грань, одна перепривязка
  в пределах прежнего `CONTACT_TOLERANCE` с интервальным доказательством; принимается только при
  согласии локальной и обеих моделей упакованного сегмента. Иначе бой по-прежнему fail-closed.
- Причина: на стенде `full-test-20261031-12` (main `711803e`) два боя на Ch22_113 оборвались
  `impact segment first surface differs from contact` при попаданиях ботов.
- Gate в D: на `0215c6e`: 1869 PASS / 3 FAIL / 19 ignored; 2 базовых `tests_p04m`, третий
  `p08b_owner_hold17` — окружение (TEMP на E:), отдельно с обычным TEMP 1/1 PASS. 13 тестов `perf02_` PASS.
- Native (владелец, стенд -12, release `fd00bff5`): бой на 113 до итогов без обрыва — PASS.
  Bat.-Châtillon: бой до итогов на старом и на новом шлюзе — PASS (свежий клиент). Ранее один раз клиент
  закрылся без исключения и дампа после пяти боёв в одном запуске, сервер ошибок не записал — причина
  UNKNOWN (INFERRED: память 32-битного клиента), не повторилось. CAT-NATIONS native: FV215b, 113, Bat — PASS.
- Откат: `git revert -m 1 <merge>`.

## LATE-NOTICE-01 — кэш итогов боя клиента — принят владельцем, в main — 2026-11-01

- #717 `BattleResultsCache` вычисляет `CACHE_DIR` при импорте из нативного пути настроек
  (`Wargaming.net/WorldOfTanks/D:/…`), до подмены getter патчем профиля, и каждое `save()` падало
  `WindowsError 123`. `client_patch/project_preferences.py` переносит `CACHE_DIR` в
  `<profile>/battle_results`, принимая только измеренное нативное или собственное значение.
- Тесты `tests.test_project_preferences`: Python 3 и 2.7 — 9 OK (1 skip).
- Native (владелец, стенд -12, клиент a `install-a-18`): трасса записала перенаправление; после полного
  боя `63535897693681792` в кэше создан `.dat`, исключений `BattleResultsCache` нет — PASS.
- Уведомления о боях этим не включаются: сервер шлёт их только с LATE-BOTS и
  `p08c_late_notice_experimental` (сейчас false). Откат: `git revert -m 1 <merge>` и переустановка патча.

## LATE-BOTS — итоги ушедшего игрока в боях с ботами — принята владельцем, в main — 2026-11-01

- Ключ `late_bots` (`project.late-bots.continue-until-outcome.v1`, проектная политика, не поведение WG; требует `bots` и
  P08C late results): после ухода последнего человека бой доигрывается в обычном темпе до реального исхода, вышедший
  владелец получает итог. Seal v2 `project.late-bots.final-world-after-release.v1` хранит строки ботов без аккаунтных
  записей. Показанный урон может отличаться от инвентаря, закрытого при выходе — осознанный компромисс. Без ключа прежний сброс.
- Native (владелец, стенд -12, release `gateway-late01-release-e16837c`, клиент `install-a-18`, 1 + 29 ботов): выход
  посреди боя, бой `977789593489329` доигран, seal `actual_outcome`, уведомление показано, итоги подгрузились, query и
  ACK 1501 приняты, `SHARED_BATTLE_FAILED` 0 — PASS. Уведомление `0x4b` OBSERVED на этом бою.
- Python полный набор в D:: новых FAIL нет (93 FAIL/ERROR ⊂ main). Release-композиция HTTP/SQLite PASS.
- Не проверено: выход одного из двух людей в native (только синтетика); release-бенч пути после выхода.
- Откат: `git revert -m 1 <merge>` и выключить ключ, но старый Domain не читает seal v2 — нужна стратегия БД, см.
  [LATE_BOTS](plans/LATE_BOTS.md).

## PERF-02 (тир X) — LOS укладывается в шаг, бои с ботами X уровня не обрываются — принято владельцем, в main — 2026-11-01

- Причина FAIL 30.10: скан засвета на тире X занимал 88% шага (пик 64 мс без клиента). Тайлы высот в `any_ground` и скан на 4 потоках: LOS 32,5 → 2,9 мс на тик, p95 цикла бенча 35 → 2,8 мс. Ответы LOS не меняются (проверено сравнением с полным перебором). Подробно — [PERF02_TIER10_LOS](plans/PERF02_TIER10_LOS.md).
- На main боты с ограниченным углом башни обрывали бой (`aim.rs:168`): перенесены `c1f783d`, `d136b72`. Манифест с шестью машинами вне диапазона wire теперь отвергается при загрузке.
- Native (владелец, стенд -12, release `gateway-perf02-release-b1471f3`, 1 + 29 ботов тира X, Малиновка): бой `44920837690963176` до итогов, победа, query и ACK — PASS. Три боя шлюза: `LAG_RESYNC` 0, `SHARED_BATTLE_FAILED` 0, цикл макс. 37,8 мс, тик в бою ~100 мс.
- Клиент один раз тихо закрылся в бою на 113 (без исключения, дампа и события Windows). Сервер работал штатно, бой доигран, итог сохранён. Причина UNKNOWN. В следующем запуске под наблюдением — пик виртуальной памяти ~2,0 ГБ, вылета нет.
- Не закрыто: остальные пункты PERF-02, включая MALINOVKA-STEP. Откат: `git revert -m 1 <merge>`.

## PERF-02 (остаток) — снаряды не дают пиков шага, MALINOVKA-STEP — принято владельцем, в main — 2026-11-01

- Снаряд на каждом участке полёта строил сетки всех 29 машин; машины вне досягаемости теперь пропускаются, выбор цели тот же. Бенч тира X: пик снарядов 32,5 → ~3 мс, пик шага 33 → ~7 мс; два боя одновременно — пик 13 мс. Подробно — [PERF02_TIER10_LOS](plans/PERF02_TIER10_LOS.md).
- `think_ms` не растёт: 0,05–0,32 мс на тик. MALINOVKA-STEP: при 14–18 снятых разрушаемых объектах пиков нет.
- Native (владелец, стенд -12, release `gateway-perf02-release-fb66f6d`, 1 + 29 тира X, Малиновка): бой `71865897957760064` до итогов, победа, query и ACK — PASS. `LAG_RESYNC` 0, цикл макс. 15 мс, шаг макс. 11 мс, тик макс. 123 мс.
- Не закрыто: сравнение с Прохоровкой NOT_RUN; разовый пик 49 мс в бенче не повторился, причина INFERRED (система). Откат: `git revert -m 1 <merge>`.
