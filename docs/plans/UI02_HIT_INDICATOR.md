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

## Ограничения

- Native **NOT_RUN**: клиент никто не запускал. Мини-интерпретатор AS2 в тестах доказывает, что байты
  делают написанное на макетах, но не то, что Scaleform их нарисует. Вид и размер — на приёмке.
- Канал откроется только если ID 0xa1 верен. Если нет — клиент останется с родной дугой, в журнале шлюза
  не будет `BATTLE_EVENTS_HELLO`.
- Факты привязаны к индикатору по `yaw`: два попадания с одинаковым `yaw` в окне 5 с покажут последний факт.
- Иконки модулей не добавлены: вместо них короткая родная фраза из `ingame_gui`.
- Модель модулей — нынешняя; точность критических зависит от SHELL-03/04.
