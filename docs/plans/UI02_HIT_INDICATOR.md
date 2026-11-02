# UI-02 — индикатор обстрела и канал боевых событий (2026-11-01)

Ветка `codex/ui-02-hit-indicator` на `codex/ui-01-int-settings` (`de9e0ec`). Первая реализация из
плана [BATTLE_UI](BATTLE_UI.md), исследование — [research/BATTLE_UI](../research/BATTLE_UI.md).
Решения владельца: новый версионируемый канал только получателю; имя невидимого стрелка не раскрывать;
отсутствующие факты показывать честно отсутствующими; графику современного клиента не копировать.
В main не вливать: приёмка владельца утром.

## Исследование

Источник — оригинал #717, байткод как данные (`tools/py27_static.py`), ничего не исполнялось.

| Факт | Статус |
|---|---|
| `ClientArena.update` (`clientarena.pyc:203`) ищет тип в словаре и молча игнорирует неизвестный | VERIFIED |
| `ARENA_UPDATE` занимает 1…11; тип 200 свободен | VERIFIED `constants.pyc` |
| `Avatar.updateArena` (0x58) принимается клиентом | OBSERVED: каждый бой, тип 3/6/8/9 |
| `setDevelopmentFeature(STRING,INT32)` exposed; ID 0xa1 | ID INFERRED (INPUT-01), в бою путь не наблюдался |
| `__onInitStepCompleted`: `setClientReady` (смещение 491) раньше `g_playerEvents.onAvatarReady` (630) | VERIFIED |
| Шлюз до READY отвергает любую запись (`shared/mod.rs:828`) | VERIFIED, тест `ui02_hello_before_ready_is_a_strict_reject` |
| Родной индикатор — Flash `DamageIndicator.swf`, `WGHitIndicatorFlash`, `damageMC`, 90 кадров при 24 к/с | VERIFIED |
| `_DamageIndicatorCtrl` сам ведёт срок жизни, предел на экране и пересоздание при смене прицела | VERIFIED |
| Шрифты BigWorld `system/fonts/*.font` — символы 32…255, кириллицы нет; `GUI.Text` не подходит | VERIFIED |
| Родные тексты боя идут через `ImportAssets2 gfxfontlib.swf $FieldFont` | VERIFIED по 3 SWF |
| Куда C++ `WGHitIndicatorFlash` применяет поворот (`_rotation` или матрица компонента) | UNKNOWN |
| Рисование AS2 (`beginFill`) и `createTextField` в этой сборке Scaleform | UNKNOWN до native |

## Решение

**Транспорт — без правки `.def`.** Изменение `.def` сдвинуло бы нумерацию методов и потребовало подмены
схемы. Вместо этого: сервер → клиент — `updateArena(200, кадр)`; клиент → сервер — объявление
`setDevelopmentFeature('sr_battle_events', 1)`. Обе стороны — существующие методы #717.

**Рукопожатие.** Патч шлёт объявление через 1 с после `onAvatarReady` (канал упорядочен, READY уже
ушёл), до 5 раз раз в 2 с, пока не придёт ответ `hello`. Шлюз без ключа `battle_events` оставляет запись
прежним путём `SHARED_UNSUPPORTED`. Нет объявления → канала нет → ни одного нового байта. Канал живёт
один бой: `reset_for_battle` его закрывает.

**Кадр v1** (`shared/battle_events.rs`): `BE`, версия u8, номер u16, счётчик u8, записи `kind u8, len u8,
payload`. Неизвестный `kind` клиент пропускает по длине: UI-03/04 добавляют виды без новой версии;
изменение раскладки — новая версия. Пределы: 240 байт, 8 событий, 4 критических факта, 10 кадров/с,
очередь > 16 → кадр теряется со счётчиком и строкой журнала `BATTLE_EVENTS_DROPPED`, канал живёт.
Клиент разбирает только точные двоичные поля: никаких pickle/eval.

**Домен отдельно от сети.** `HitReceived` оперирует слотами и фактами; ID появляется только в
кодеке. `World` и кодеки BW-01 **не менялись**: все факты уже есть в журналах `impacts`, `damage_events`,
`device_events`. Публикация — `shared/battle_events_publication.rs`, читает те же курсоры, что родные
вызовы, и не двигает их, поэтому переподключение ничего не повторяет. Кадр ставится в очередь раньше
родного `showOwnVehicleHitDirection` того же прохода.

**Индикатор.** Стандартный — родная дуга без изменений. Расширенный — подкласс родного `_DamageIndicator`
грузит `ProjectHitIndicator.swf`: родной SWF плюс импорт шрифта и один DoAction с `ProjectHit.show`
(луч, круг, число, имя, подпись; рисование и текстовые поля, никакой чужой графики). Родной контроллер
остаётся владельцем жизненного цикла. Дуга прячется только после проверки, что рисование доступно;
SWF не загрузился или ошибка показа — остаётся родная дуга (`policy.failed`). SWF собирается на `prepare`
из `gui.pkg` по закреплённому SHA-256 и в Git не хранится (`tools/battle_ui_hit_flash.py`).

**Значения для UI-05.** `project_hit_indicator.OPTION_SCHEMA`: `view`, `show_critical`, `show_friendly`,
`show_damage`, `show_vehicle`, `dynamic`, `animate`; `policy().apply_options(...)` действует со
следующего индикатора. Начальное значение — из `sr_interactive_settings.json`. Хранение — за UI-05.

### Кому что уходит

| Факт | Видимый стрелок | Невидимый стрелок |
|---|---|---|
| Направление (`yaw`) | да | да, родной `showOwnVehicleHitDirection` уже его даёт |
| Свой урон, исход, номер снаряда | да | да, это свои HP и родные эффекты |
| ID стрелка → название машины | да | **нет**, поле 0 |
| «Удар сдержан» | номинальный урон снаряда из каталога | **нет**: выдал бы орудие; показывается `- -` |
| Дружественный огонь | да | флаг да, ID нет |
| Свои модули, экипаж, пожар | да | да, родной `showVehicleDamageInfo` их уже даёт |
| Позиция, HP, модули стрелка | **никогда** | **никогда** |

Получатель всегда только владелец подбитой машины. Сплэш ОФ, не ставший прямым попаданием, идёт
событием с исходом `splash` без номинала. Родного вызова на сплэш шлюз не шлёт (как и раньше), поэтому
подготовленный клиент сам вызывает родной `Aim.showHit`: неподготовленный клиент сплэш не видит, как раньше.

## Итог

Изменены: `shared/battle_events.rs`, `shared/battle_events_publication.rs`, `shared/server_ui02_tests.rs`
(новые); `shared/mod.rs`, `shared/server.rs`, `shared/lifecycle_wire.rs`, `account/identity.rs`;
`client_patch/project_hit_indicator.py` (новый), `client_patch/sr_interactive.py`;
`tools/battle_ui_hit_flash.py` (новый), `tools/interactive_client.py`; тесты
`tests/test_project_hit_indicator.py`, `tests/test_battle_ui_hit_flash.py`.

Перенесены из `codex/battle-ui-research`: `docs/plans/BATTLE_UI.md`, `docs/research/BATTLE_UI.md`,
`tools/battle_ui_pyc_inventory.py`, его тест, строка индекса.

Включение: `"battle_events": {"version": 1}` в `gateway.json` (нужен `visibility_v1`) и
`tools/interactive_client.py prepare ... --hit-indicator standard|extended`.
Откат: убрать ключ, `rollback` клиента; в Git — не вливать ветку.

Шаги ручной проверки — `local/handoff/UI_BLOCK_CHECK.md` (локально, не в Git).

### Проверки (код `4646f03`)

| Проверка | Результат |
|---|---|
| Канонический gate в D: | 1922 PASS / 2 FAIL `tests_p04m` (норма) / 21 ignored — PASS |
| Пакетные и кодековые тесты `ui02` | 17/17 PASS |
| Клиентский модуль: Python 3 и CPython 2.7.3 | PASS; компилятор `prepare` принял модуль |
| Сборка SWF, мини-интерпретатор AS2 на макетах, закреплённый SHA оригинала | 8/8 PASS |
| Python-набор в D: | 3567 тестов, 94 FAIL/ERROR; база `pyD-main` (`3a60035`) 113. Единственная новая строка — `test_p06t_extended_profiles...fresh_only`: папка `local/evidence/20261016-p06t-extended-source-tests/tests01-generated` осталась от прошлого прогона, файлы теста и инструмента карточкой не менялись |
| Полный `prepare --hit-indicator` | NOT_RUN: нужна изолированная копия без установки, клиент ночью не трогали |
| `install`, `rollback`, native | NOT_RUN |

## UI-02b: вид на графике Lesta

Замечание владельца 02.11: индикатор не похож на родной. Решение владельца заменяет прежнее «графику современного
клиента не копировать»: чего нет в #717, для интерфейса временно брать из локальной копии Lesta, потом заменить своим.
Файлы только в `local/`, в Git и в публикацию не идут; манифест — `UI_BORROWED_ASSETS.md`.

| Факт | Статус |
|---|---|
| Атлас `gui/flash/atlases/damageIndicator.dds` (`gui-part1.pkg`): DXT5, 1024×1280, 53 спрайта, совпадает со скриншотами 01–03 | VERIFIED |
| Современный фильм Lesta — SWF 17 на AS3 (`DoABC`), запустить в Scaleform #717 нельзя; код не брался, разобран только пул констант как данные | VERIFIED |
| Родной `DamageIndicator.swf` — SWF 8, картинка дуги: `DefineBitsLossless2` формат 5 + `DefineShape` с заливкой 0x41 | VERIFIED |
| `WGHitIndicatorFlash` получает имя `damageMC` третьим аргументом, поворот идёт в `_rotation` этого клипа | INFERRED, байткод `aims.pyc`, C++ не читался |
| `arena.vehicles[...]['vehicleType'].type.tags` содержит класс машины | VERIFIED `minimap.pyc`, `__addEntry` |
| `tanksCircle` — топливные баки | INFERRED по рисунку |
| `attachMovie` экспортированного спрайта в этой сборке Scaleform | UNKNOWN до native; при отказе остаётся родная дуга и подписи |

**Встраивание.** `tools/battle_ui_hit_art.py extract` читает пакет только на чтение, сверяет SHA-256 атласа и XML, сам
декодирует DXT5 и пишет PNG. `--hit-indicator-art <папка>` добавляет в фильм на каждый спрайт три определения теми же тегами,
что родная дуга, и `ExportAssets` перед DoAction. Подходит любой 8-битный RGBA PNG с тем же именем: так владелец заменит графику на
свою. Значки модулей и классов необязательны; без обязательного спрайта или папки сборка даёт байт в байт рисованный фильм.

**Показ.** Аргументы `ProjectHit.show` прежние плюс два имени спрайта, рисованный фильм их не читает. Выбор спрайта — в AS2 по цвету и
`scale`: красный — `damageSmall/Medium/Big` (динамические индикаторы), оранжевый — `crit`, серый — `blockedSmall`. Дружественный
огонь, как и раньше, виден по цвету имени, значок класса — зелёный `ally_*`. Значок модуля заменяет число только при нулевом уроне:
так на скриншоте 02, а урон не теряется. У пожара значка нет, остаётся число. Спрайт высотой 358 px в сцене 680 px идёт в масштабе 66 %:
дальний конец в пределах сцены, размер компонента не менялся, луч лежит в той же зоне, что родная дуга. Имя лежит вдоль луча и не бывает
перевёрнутым, число и подпись прямые. Спрайты Blind (режим для дальтоников) не взяты: опции такой в индикаторе нет.

Включение: `python -B -X utf8 tools/battle_ui_hit_art.py extract --lesta D:/Games/Tanki --out D:/WoT_9.1_Server/local/ui-borrowed/hit-indicator`,
затем в `prepare` добавить `--hit-indicator-art D:/WoT_9.1_Server/local/ui-borrowed/hit-indicator`. Откат: `prepare` без флага.

## Ограничения

- Native **NOT_RUN**: клиент никто не запускал. Мини-интерпретатор AS2 в тестах доказывает, что байты
  делают написанное на макетах, но не то, что Scaleform их нарисует. Вид и размер — на приёмке.
- Канал откроется только если ID 0xa1 верен. Если нет — клиент останется с родной дугой, в журнале шлюза
  не будет `BATTLE_EVENTS_HELLO`.
- Факты привязаны к индикатору по `yaw`: два попадания с одинаковым `yaw` в окне 5 с покажут последний факт.
- Иконки модулей не добавлены: вместо них короткая родная фраза из `ingame_gui`.
- Модель модулей — нынешняя; точность критических зависит от SHELL-03/04.
