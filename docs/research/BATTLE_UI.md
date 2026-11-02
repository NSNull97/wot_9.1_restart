# BATTLE-UI: исследование клиента #717 (2026-10-29)

Состояние: исследование частичное, приёмка этапа **NOT_RUN**. Источник —
`C:/WoT_0.9.1_RU_0717_original`, только чтение. База кода `main d0a9b9e`.
`.pyc` разобраны как данные `tools/py27_static.py`, без выполнения клиентского
кода. Строки ниже — `firstlineno` записей байткода, не восстановленные исходники.
Наличие обработчика не доказывает визуальный результат или приём нашего пакета.
Скриншоты 01–08 владельца — современный клиент, целевой пример, не источник
исторической семантики. Дезориентацию по решению владельца не переносить;
полный список отсутствующих в 0.9.1 механик остаётся UNKNOWN.

## Источники

Пути ниже относительно `res/scripts/client/` оригинала; SHA-256:

| Файл | SHA-256 |
|---|---|
| `avatar.pyc` | `c13cd58a4c5d766dfd3c5f47ae7be50c962aee6c7f8cf25b4341322381f21e0e` |
| `vehicle.pyc` | `b81d08ca14092bb8912adb2eff20325c3dd23424868bc03164cfe6b8da50463c` |
| `clientarena.pyc` | `30b21bb0e386b909d162f127b79b86e5da1aeecb65e9c6700b2b50f435dbd455` |
| `avatarinputhandler/aims.pyc` | `3be8f030052c58a17a5bfc1ceb28ca3903bff674b2c6ab6dc00cb771521cda6e` |
| `gui/scaleform/battle.pyc` | `aa43bc6b7e1f7ae9e2bba03fa527a9e6ce95a5d41ef23f26785b1490cd6f38de` |
| `gui/scaleform/battledamagemessages.pyc` | `232f52a7478c7f7073c4be80560ddf47c7013aba68c01623faa246b703754012` |
| `account_helpers/settingscore.pyc` | `f95f4cf39852c84ae9396c3d0b4b4ca17ab557c74cecd3a914cbde09c271c1fd` |
| `account_helpers/serversettingsmanager.pyc` | `ac810aa4e4e701adaf0575cc126230811e44b15415f207494021ca3d067c179a` |
| `gui/scaleform/daapi/view/lobby/settings/settings_storages.pyc` | `e547567b746f58832776cc4eda2fc43d0d374eefa61ea1138a5939eb0b346484` |
| `account_helpers/settingscache.pyc` | `90e0b582f21cdd7dea85ff4fa4c08a16e4d1693c013c89dbffb8109583c27cdd` |
| `gui/shared/utils/requesters/intsettingsrequester.pyc` | `7b2e6f2322a81a2f735d9ef7a2e2eab1ac4e01d21a20acf0b27506dd537d4a5a` |
| `account_helpers/intusersettings.pyc` | `2f393dc54f6d4478f54aef0c9984315116bc9f7de5aea39ce156d64f5840c22d` |
| `gui/scaleform/daapi/view/lobby/settings/settingswindow.pyc` | `7c41c9a39ea796b8931b7915499c0ba0b59f849dc27d084c4e90030474c11233` |

Схемы `res/scripts/entity_defs/avatar.def` SHA-256
`38cf983d6ea1fcaf1bbca25fd18567fed5abc3b2e07fbe14b168f46fa883f74d`,
`vehicle.def` `08dc1e6be577f80a04bf813ca046550201a3c4e673dad1540c5f1c6a047d1297`.
Байтовые ID в таблице — используемые шлюзом; их историческая нумерация и
приём всех вариантов клиентом не доказаны одним чтением схемы.
`updateArena` использует ограниченный исходящий pickle protocol 2
(`shared/lifecycle_wire.rs`); клиент использует cPickle. Это не разрешение
десериализовать недоверенные объекты на сервере.

## Карта UI и источников

| Элемент | Есть в 0.9.1? / питание | Шлюз `d0a9b9e` | Статус |
|---|---|---|---|
| Направление попадания | `showOwnVehicleHitDirection(FLOAT32, BOOL)` → `Aim.showHit`, `aims.pyc:372`; `_DamageIndicatorCtrl.add:853`, `_DamageIndicator:909` | `av01_feedback.rs:48` ID `0x41`, владельцу повреждённой машины и при скрытом стрелке, при `spotting_enabled` | VERIFIED обработчик и отправка; ID INFERRED по схеме, новый знак направления native NOT_RUN |
| Длительность и очередь | 90 кадров при 24 кадр/с = 3,75 с; контроллер проверяет порог 5 и удаляет старейший | локальная логика | VERIFIED статически; точное число одновременно видимых и их вид native UNKNOWN |
| HP и всплывающий урон маркера | `health INT16`, `isCrewActive BOOL`; `onHealthChanged(INT16,OBJECT_ID,UINT8)`, `battle.pyc:2597,2715`; Flash получает HP и контекст | `impact_wire.rs:46–76`: health `0xa1`, callback `0x3c`; видящим цель, скрытый атакующий = 0 | VERIFIED код; конкретная визуализация чисел/варианты Alt требуют native |
| Эффекты попадания и маркер смерти | `showDamageFromShot(OBJECT_ID,ARRAY<UINT64>,UINT8)`, `vehicle.pyc:186,385,789` | `impact_wire.rs:159–178`, `0x42 VAR1`; видящим, особый вариант для собственной машины со скрытым ID 0 | VERIFIED путь; отдельные надписи «не пробил/рикошет» над танком UNKNOWN |
| Собственное HP / экипаж | `updateVehicleHealth(INT16,BOOL)`, `avatar.pyc:1145` → DamagePanel и Aim | `impact_wire.rs:68` ID `0x3f`, только владельцу | VERIFIED код, визуальные комбинации NOT_RUN |
| Модули/экипаж, ремонт, пожар | `showVehicleDamageInfo(OBJECT_ID,UINT8,EXTRA_ID,OBJECT_ID)` → `avatar.pyc:1506`, `battle.pyc:2111,2295,2344,2359`; `updateVehicleMiscStatus(OBJECT_ID,UINT8,INT32,FLOAT32)` → ремонт `avatar.pyc:1266`; `showOtherVehicleDamagedDevices` также объявлен | `p06t_publication.rs:24–36,88–105`: события владельцу при `mixed_ammo`, скрытый источник 0; коды ремонта 18/19, огня 3/35; полнота по остальным путям UNKNOWN | VERIFIED ограниченный код; историческая полнота модели и native NOT_RUN |
| Детонация | `showAmmoBayExplosion(FLOAT32,FLOAT32)` | `turret_publication.rs:63` при соответствующем событии модели | VERIFIED наличие пути; форма/частота и native UNKNOWN |
| Сообщения и голос | `showShotResults(ARRAY<UINT64>)`, `avatar.pyc:1521`; `showVehicleDamageInfo`; `battledamagemessages.pyc:55,85` содержит ATTACK/FIRE/RAMMING/WORLD_COLLISION/DEATH_ZONE/DROWNING | `av01_feedback.rs:97` ID `0x55` VAR1, упаковано `vehicleID | flags<<32`, только стрелку при `spotting_enabled`, включая blind fire; события модулей по ограничению выше | VERIFIED обработчики; voice owner OBSERVED в AV-01, не все сценарии |
| Засвет / помощь | `onScoutEvent(UINT8,OBJECT_ID)`, `avatar.pyc:1747`, содержит SPOTTED/HIT_ASSIST/KILL_ASSIST | `0x42` SPOTTED только засветившему (`server.rs:2692`); числовой ассист в реальном времени не установлен | VERIFIED код; ID INFERRED; ассист UNKNOWN |
| Фраги, счёт и базы | `updateArena(UINT8,STRING)`, `clientarena.pyc:324,350`; `battle.pyc:1361,1393,1404,1414`; сообщения `battle.pyc:587,605` | `lifecycle_wire.rs:32,63–82`: `0x58`, типы 6 kill, 8 points, 9 captured; `server.rs:2501–2504,2538–2544` | VERIFIED код, native все комбинации NOT_RUN |
| История как на 07–08 | Ограниченный поиск её не нашёл; assist есть в итогах, не доказан боевой журнал | Отдельного канала такого журнала не установлено | UNKNOWN полное отсутствие; см. границы ниже |

`avatar.def` не содержит `updateVehicleDestroyedState` среди просмотренных
ClientMethods; не подменять реальное имя этим предположением. `vehicle.def`
объявляет `health` и `isCrewActive` как ALL_CLIENTS, но это не отменяет
серверного фильтра видимости.

**Раскрытие:** `onHealthChanged` при скрытом атакующем использует ID 0
(`p06t_publication.rs:110–137`). Но `vehicle_killed` в `server.rs:2501–2504`
и `p06t_publication.rs:50–56,73–81` передаёт настоящий killer ID как публичные
данные ростера. Это отдельный путь, не доказательство безопасности нового UI:
до реализации определить, что клиент 0.9.1 раскрывал после убийства и какую
политику принимает владелец. Позицию, HP, модули и имя скрытой машины новым
каналом не раскрывать без утверждённой политики. Существующая проектная
политика трассера — [AV-01](../plans/AV01_BATTLE_FEEDBACK.md), смещение 40 м.
Дополнительно `showShotResults` сообщает стрелку настоящий ID цели и флаги
даже при blind fire (`server.rs:2477–2493`); возможность связать их с именем
и допустимость этого раскрытия также требуют отдельной проверки.

## Журнал: что именно искали

VERIFIED ограниченный поиск: 492 `.pyc` в `gui/scaleform`, 0 ошибок, 11
совпадений поисковых имён (ассист в итогах, профиле и задачах); три каталога
`ingame_gui.mo` (325 записей, SHA-256 `5ad816d6ecffa0c9851cab83d3f92089990a49da790c39e5a8a7131836048d7a`),
`settings.mo` (419, `c9ac42f8726a578080d79464a8fe93144bdbbb8447c7ae1929b44372b742001b`),
`battle_results.mo` (138, `54546e767e581d02d7d690ebc18f753b6853118eec522d1d3c5e9852a75087c2`):
среди искомых строк найден только ассист в итогах. В `gui.pkg` SHA-256
`d15077bee0032eb577e26bf897563ae223eb1e1d10b3a6262f29b0f5368788bb` — 234 SWF;
по именам и ASCII в шести выбранных SWF нужный журнал не найден. Это не полный
разбор ActionScript и не доказательство отсутствия под другими именами.
Скрипт, точный regex, scope и вывод — `D:/WoT_9.1_Server/local/evidence/20261029-battle-ui-log-research-01/{audit.py,audit.txt}`.

## Настройки

VERIFIED: `_SettingsCore.init:20` содержит GAME, GRAPHICS, SOUND, CONTROLS,
AIM, MARKERS; `ServerSettingsManager` версия 11, `get/setAimSettings:323/374`,
`get/setMarkersSettings:389/426`: для союзников/врагов/уничтоженных маркеров есть
варианты Base/Alt и поля Icon, Level, HpIndicator, Damage, Hp, VehicleName,
PlayerName. `settings_storages.pyc:343,359` передаёт настройки менеджеру;
`settingscache.pyc:70` → `IntSettingsRequester`, :155/166 →
`intUserSettings.addIntSettings`: ID 43–45 arcade, 46–48 sniper, 49–51
маркеры. `intusersettings.pyc:98,133` вызывает команды 1600/1601; константы в
`res/scripts/common/accountcommands.pyc` SHA-256
`ba439d8badead15bba4f28708c1822630c1d58fe4699bd07d76d99db345dc2fe`.
`settingswindow.pyc:67` также вызывает `BigWorld.savePreferences`: локальное
и серверное хранение сосуществуют, разбивка каждого пункта ещё UNKNOWN.
Звук MASTER/MUSIC/VOICE/VEHICLES/EFFECTS/GUI/AMBIENT есть; точное хранение
и поведение каждого индикатора/сообщения не установлены.

VERIFIED по текущему коду: `account/hangar.rs:73,324–327,344–352` относит
1600/1601 к недоступным, `session.rs:1100–1107` отвечает `-10` без изменения
состояния; начальный `intUserSettings` — `{0:11}` (`tools/hangar_state.py:412`).
**OBSERVED (со слов владельца, 2026-10-29):** настройки, по его проверке,
не сохраняются — любые. Точный перечень проверенных пунктов, профиль, стенд,
шаги и трасса нам не предоставлены; причина для каждого пункта UNKNOWN.
Статическое подтверждение отказа 1600/1601 не доказывает, что он объясняет
все настройки: локальное и серверное хранение сосуществуют. Профиль стенда
указан в задании как `local/stands/full-test-clients-20261026/profile-<x>/sr_preferences.xml`;
самостоятельная диагностика на изолированной копии, включая перезапуск и
применение в бою, — **NOT_RUN**.

Владелец предложил выделенный корень
`C:/Users/NSNull/AppData/Roaming/GAYmDev Studio/SteelFrontier` (2026-10-29).
Он создан пустым; клиенты на него **не переключены**. VERIFIED: старый
`C:/Users/NSNull/AppData/Roaming/Wargaming.net/WorldOfTanks/preferences.xml`
существует, но стендовые A–D уже используют отдельные `profile-<x>/sr_preferences.xml`
внутри `local/`. Записи `preferences_local_save` наблюдаются в трассах
`local/stands/full-test-clients-20261026/runtime-a/native-274316-1793263038475.jsonl`,
но сами по себе не подтверждают сохранение выбранных значений.
Установщик `tools/interactive_client.py:226,295–305,318–320` и клиентский
`client_patch/project_preferences.py:87–119` сейчас ограничивают профили `local/`
и ожидают `sr_preferences.xml`; один лишь перенос XML в AppData не перенаправит
установленные клиенты. При одновременном использовании одного файла
`guarded_write` использует общие `.project-pending`/`.project-previous`, без
межпроцессной синхронизации; возможны конфликты. Решение владельца: один общий
файл для одновременно работающих клиентов. Нужны безопасная согласованная
запись и отдельная native-проверка. Серверные настройки не становятся локальными
автоматически от изменения расположения файла.

**VERIFIED, синтетическая проверка:** две последовательные записи через текущий
`guarded_write` полных снимков A и B вернули старое значение настройки A, когда
B записал собственный устаревший снимок. Команда из корня worktree:
`python -B -X utf8 D:/WoT_9.1_Server/local/evidence/20261029-battle-ui-shared-preferences-01/reproduce.py`.
Вывод — `.../result.txt`. Это доказывает риск алгоритма, а не последовательность
действий конкретного клиента: native-сценарий двух процессов — NOT_RUN.

**UI-05, VERIFIED статически (2026-11-02):** окон два. Ангар — Python `SettingsWindow`, AS3 `gui/flash/settingsWindow.swf`
(`dbd8a56a…`). Бой — Python `SettingsInterface`, AS2 `gui/scaleform/SettingsDialog.swf` (`071a8846…`). Вкладки в обоих —
`SettingsConfig.tabsDataProvider`. Новый раздел в этих окнах и решение по хранению — [план UI-05](../plans/UI05_NATIVE_SETTINGS.md).

## Проверки и вопросы

`python -B -X utf8 tools/battle_ui_pyc_inventory.py C:/WoT_0.9.1_RU_0717_original/res/scripts/client/avatar.pyc --contains showOwnVehicleHitDirection`;
вывод и тесты — `D:/WoT_9.1_Server/local/evidence/20261029-battle-ui-inventory-01/`.
Собственный native-тест не запускался; полное исследование SWF/настроек,
политика раскрытия убийцы, доступность и точность серверных фактов — UNKNOWN.
Предложения и вопросы владельцу — [план](../plans/BATTLE_UI.md).
