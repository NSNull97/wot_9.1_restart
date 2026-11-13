# CONTENT-0 3.1 — установка модулей в ангаре (бесплатно), 2026-11-12

Ветка `claude/content-0-module-mount-5c101e` (от `codex/content-0-modules-plan` `e52a005d`). План —
[CONTENT0_S3_MODULES](../plans/CONTENT0_S3_MODULES.md), подшаг 3.1. Нативная приёмка (клиент, провод, бой): **NOT_RUN**.

## Итог

Серверная часть 3.1 уже была сделана в P09E (`tools/p09e_*`, шлюз `research_service.rs`/`hangar.rs`) и на стенде
включена (`gateway.json` -20: `research_service: true`; клиент `install-a-55` с `--enable-research-service`). Запись
в плане «закрыто клиентским патчем» неточна: в режиме research `hangar_capabilities.py` пропускает пять видов модулей
к серверу ещё с P09E. В этом подшаге код сервера **не менялся**; добавлены проверки на пути стенда CONTENT-0 (P06T
MixedAmmoStore в режиме каталога), исследование по клиенту и две правки текстов клиента.

| Что | Где | Статус |
|---|---|---|
| 101 `Inventory.equip` (id машины в инвентаре, CD модуля, 0) | `p09e_native_commands.domain_request` → `ResearchStore.plan("install")` | есть, проверено тестами |
| 101 `Inventory.equipTurret` (id, CD башни, CD орудия или 0) | то же, пара башня+орудие одной командой | есть, проверено тестами |
| Маршрут шлюза | `hangar.rs` (`requests_profile`, `research_service`) → `/internal/native/research` → Domain → `p08b_battle_service.execute("research")` → `native_service` | есть (Rust-тесты P09E) |
| Бесплатно | `POLICY test_lab.research.free-credit-xp.v1`: store не списывает опыт и кредиты вовсе | есть |
| Бой только сток | `StockRegistry.resolve_owned`/`freeze_mixed` → `BATTLE_PROFILE_UNSUPPORTED` → шлюз `JOIN_FAILURE.WRONG_VEHICLE` | есть, проверено тестами |
| Подсказка в ангаре | `map_drive_client._profile13_selection` → `unsupported_configuration` | **текст исправлен** |
| Уведомление о прочих отказах | `hangar_capabilities._ModuleChangeGuard` | **текст для режима research** |

## VERIFIED (статически, оригинал `C:\WoT_0.9.1_RU_0717_original`, не исполнялся)

Байткод прочитан `tools/py27_static.py` с таблицей опкодов CPython 2.7.3 из `local/toolchains-py27-20261019`.

- `client/account_helpers/inventory.pyc` (sha256 `3d17842c…3cbf19`, 22 611 б): `Inventory.equip` (строка 181)
  проверяет `itemTypeIdx in (_CHASSIS, _GUN, _ENGINE, _FUEL_TANK, _RADIO)` и шлёт `_doCmdInt3(CMD_EQUIP, vehInvID,
  itemCompDescr, 0)`; `equipTurret` (204) — `_doCmdInt3(CMD_EQUIP, vehInvID, turretCompDescr, gunCompDescr)`. Обёртка
  ответа — `lambda requestID, resultID, errorStr, ext={}: callback(resultID, ext)`: **строка ошибки сервера клиенту
  не передаётся**.
- `client/gui/shared/gui_items/processors/module.pyc` (sha256 `9ed4b67e…ed5bd9`, 21 142 б):
  `TurretInstaller._request` (569) и `OtherModuleInstaller._request` (616) зовут `_response(code, callback, ctx=ext)`;
  `CommonModuleInstallProcessor._errorHandler` (508) берёт ключ `module_apply/<errStr>`, а при пустой строке —
  `module_apply/server_error`. Значит, любой отказ сервера на 101 клиент покажет как «Произошла серверная ошибка
  установки модуля %(kind)s '%(name)s'…» (`system_messages.mo`). Успех читает `ctx.get('incompatibleEqs', [])` —
  пустой `ext` по умолчанию подходит.
- `TurretInstaller.__init__` (525): если текущее орудие не встаёт в новую башню, клиент сам ищет на Складе подходящее
  орудие (`mayInstall(vehicle, slotIdx=0, gunCD=…)`) и добавляет `TurretCompatibilityInstallValidator`;
  `OtherModuleInstaller` — `CompatibilityInstallValidator`. Тексты клиента: `module_apply/error_too_heavy`,
  `error_need_turret`, `error_no_gun`, `error_not_for_current_vehicle`, `clientInstallError_too_heavy`.
- `common/items/vehicles.pyc` (sha256 `805240e4…3ae8b6`, тот же файл, что закреплён в P09E):
  - `VehicleDescr.__computeWeight` (1432): `maxWeight = chassis['maxLoad']`, масса = `hull.weight + chassis.weight +
    engine.weight + fuelTank.weight + radio.weight + Σ(turret.weight + gun.weight)`, затем поправки оборудования
    (`weightOnVehicle` → доля и добавка к массе и к `maxLoad`).
  - `_isWeightAllowedToChange(newWeights, prevWeights)` (6212): `newReserve = new.max − new.weight`; разрешено, если
    `newReserve >= 0.0` **или** `newReserve >= prev.max − prev.weight`.
  - `mayInstallComponent` (705) / `mayInstallTurret` (614) возвращают `(False, 'wrong nation' | 'wrong item type' |
    'not for this vehicle type' | 'not for current vehicle' | 'too heavy')`; орудие ищется в `guns` **текущей** башни;
    `equipTurret` с орудием 0 оставляет текущее орудие.
- Каталог P09E (374 машины клиента): сток **каждой** машины укладывается в `maxLoad` стоковой ходовой (тест
  `test_every_stock_assembly_fits_its_stock_chassis`). Конфигураций ходовая × двигатель × радио × (башня, орудие) —
  14 860; перегружены 2 243 у 164 машин (подсчёт `assembly()` по каталогу; план называл 14 861 — расхождение в одну,
  не разбиралось). Пример: КВ-3 на стоковой ходовой везёт всё (верх 68 225 кг из 68 250); МС-1 на T-18 не везёт АМО-3.
- Самое длинное обновление после смены башни и орудия (compDescr, repair, shells, shellsLayout, 4 счётчика Склада при
  предельных id и количествах) — 190 байт (ИС, башня IS-122 + Д-10Т) при пределе `Account.update` 240
  (тест `test_every_turret_gun_swap_delta_fits_the_account_update_bound`).

## Проверки сервера (что делает store, где тест)

`ResearchStore.plan("install")` (`tools/p09e_research_store.py`), одна транзакция с журналом и повтором по ключу:

| Отказ | Условие | Тест |
|---|---|---|
| `UNOWNED_VEHICLE` | id машины не из инвентаря аккаунта | `test_content0_module_mount`, `test_content0_module_rules` |
| `UNKNOWN_MODULE` / `UNEXPECTED_GUN_SELECTION` / `INVALID_GUN_SELECTION` | неизвестный CD; орудие при не-башне; «орудие» не орудие | оба |
| `MODULE_NOT_RESEARCHED` (302) | покупка неисследованного | `test_content0_module_mount` |
| `MODULE_NOT_OWNED` | модуля нет на Складе (установка без покупки) | оба |
| `INCOMPATIBLE_MODULE` | модуль не из `compatible` этой машины | оба |
| `INCOMPATIBLE_TURRET_GUN` | орудие не из `gun_turrets` для башни | оба |
| `CHASSIS_OVERLOAD` | масса > `maxLoad` ходовой | оба (МС-1 + АМО-3; граница в граммах) |
| `NO_CONFIGURATION_CHANGE` | ставится уже стоящий модуль | оба |
| `VEHICLE_RESERVED` | машина в очереди/бою (`game_vehicle.state != available`) | оба |
| `UNLOAD_AMMUNITION_REQUIRED` | смена башни/орудия при загруженных снарядах | оба |
| `INTERNAL_COMPONENT_UNSUPPORTED` | топливный бак | `test_content0_module_rules` |
| `DUPLICATE_MODULE_SLOT` | два модуля одного вида | `test_content0_module_rules` |

Снятый модуль возвращается на Склад (+1), установленный уходит со Склада (−1). Обновление клиенту (`delta_tree`):
`inventory[1].compDescr[id]` (новый описатель `plain_vehicle_descriptor`), при смене башни `repair` (прочность
корпус + башня), при смене башни/орудия `shells = []`, `shellsLayout = {}`; счётчики видов 2–7. В полном состоянии
(`PoolProjectionSource`) — то же; описатель в состоянии равен описателю из store (тест). Цены и опыт: деньги аккаунта
(`resources`) после исследования, покупки и установки не меняются (тест).

## INFERRED

- Правило массы store (`mass <= maxLoad`, целые граммы) совпадает с `_isWeightAllowedToChange` для всех достижимых
  состояний: store никогда не хранит перегруженную сборку (сток проходит, каждая установка проверяется), поэтому вторая
  ветка 0.9.1 («не хуже прежнего») для них не срабатывает. Оборудование (`weightOnVehicle`) появится в шаге 5 — тогда
  правило надо дополнить. Граммы из XML (кг с ≤ 3 знаками) — точные (не проверялось на всех).
- Клиент проверяет массу и совместимость до отправки 101 (валидаторы `plugins`) — отказ сервера по этим причинам у
  нормального клиента не должен появляться; сообщения сервера всё равно не дошли бы (см. VERIFIED).
- В 0.9.1 при смене орудия снаряды, вероятно, уходили на Склад автоматически; у нас — явный отказ
  `UNLOAD_AMMUNITION_REQUIRED` (клиент покажет «серверная ошибка установки»). Как делал оригинальный сервер — UNKNOWN.

## UNKNOWN

- Нативная проверка 101 на клиенте (провод, обратный вызов, обновление ангара) — **NOT_RUN** (в P09E тоже NOT_RUN).
- Что именно клиент шлёт при «купить и установить» из окна модуля: 302 + 101 или 308 (P09E: вызов 308 в GUI не найден).
- Строки ошибок, которые слал оригинальный сервер на 101 (клиент их всё равно отбрасывает).

## Изменения клиента (не установлены)

- `client_patch/map_drive_client.py`: причина `unsupported_configuration` (описатель ≠ стоковый) теперь «На машине
  установлены нестоковые модули. Бой пока доступен только в стоковой комплектации: верните стоковые модули со
  Склада.» — во всплывающей подсказке кнопки «В бой» и в сообщении при нажатии.
- `client_patch/hangar_capabilities.py`: в режиме research отказ для снятия модулей, оборудования и снаряжения
  показывает `RESEARCH_NOTICE` (что недоступно и что можно ставить), без research — прежний `NOTICE`.
- Обе правки скомпилированы закреплённым CPython 2.7.3 (`py_compile`), тесты клиента под 2.7.3 и 3.x.

Установка (не выполнялась; стенд и клиент не трогались): из чекаута, где эта ветка влита в стендовую сборку
(D: `integrate/testlab-stand`), откатить текущую установку и поставить новую с флагами a-55:

```
python -B -X utf8 tools/interactive_client.py rollback --out local/stands/full-test-clients-20261026/install-a-55
python -B -X utf8 tools/interactive_client.py prepare --out local/stands/full-test-clients-20261026/install-a-56 <флаги из install-a-55/install-plan.json "command">
python -B -X utf8 tools/interactive_client.py install --out local/stands/full-test-clients-20261026/install-a-56
```

Сервер не менялся: перезапуск шлюза/домена не нужен.

## Команды и результаты

```
set WOT091_CONFIG=D:/WoT_9.1_Server/config/project.local.json, TEMP/TMP=E:/wot091-tmp,
P04D…P04K/P09D_TEST_BUNDLE=D:/WoT_9.1_Server/local/stands/p09e-main-01/source-bundle-05
python -B -m unittest tests.test_content0_module_mount tests.test_content0_module_rules  -> 3 + 6 OK
python -B -m unittest tests.test_p09e_* tests.test_battle_any_pool tests.test_content0_*  -> см. отчёт сессии
python -B -m unittest tests.test_p09e_client_control tests.test_hangar_capabilities tests.test_profile13_battle_client
    tests.test_map_drive_client tests.test_p06t_battle_client tests.test_hangar_window_capabilities
    tests.test_battle_capabilities  -> 161, 4 ERROR: в worktree нет config/project.local.json (тесты читают его из корня)
```

Откат: `git revert` коммитов ветки (код сервера не менялся; клиент — откат установки `interactive_client.py rollback`).
