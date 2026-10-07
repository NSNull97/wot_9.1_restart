# P02 — серверный боекомплект МС-1

2026-10-05. Одна карточка Account/Hangar по плану `../plans/P02_ms1_ammo.md`.
Цель: выдать основному тестовому аккаунту минимальный боекомплект, передать его
родным протоколом #717 и сохранить после повторного входа с прежним кэшем.
Приёмка native пары, независимый review и итоговый filesystem audit PASS.
M = `local/evidence/20261005-p02-ms1-ammo/` от корня проекта.

## Подтверждённый контракт

VERIFIED по 13 закреплённым original ресурсам и настоящему export01:

- МС-1: typeCD3329, inventory1, башня `T-18_Standart` CD5891,
  пушка `_37mm_Gochkins` CD5892. Вместимость установленного орудия **96**;
  общий default92 у пушки не заменяет override конкретной машины.
- Родной порядок снарядов: AP2570 (`_37mm_UBRT1`), HEAT2826, HE3082.
- Native loaded/layout: `[2570,20,2826,0,3082,0]`;
  layout лежит по ключу `(5891,5892)` внутри `inventory[1]['shellsLayout'][1]`.
- `isAmmoFull=True` при20/96 следует родному порогу20%, а не означает96/96.
  На штатной панели наблюдается «К бою готов!», но серверный бой ещё недоступен.
- Исходные installed-compatible shell tooltip ветки не требуют новых цен.
  Catalog3/shop507B сохранён. Экспортированные buyPrice/defaultPrice0 в иных
  неподключённых ветках нельзя называть исторической ценой.

Точные пути, строки, offsets и SHA: `M/gui/contract-01/CONTRACT.md`.
Native envelope `M/native-ms1-ammo-export01.json`, SHA256
`683daac81143a9d7edfbe671870ba163db088c54f5101fa52e077f596ebbfc74`.
Он связан с trace record, source/compiled probe, install plan и завершённым EXE.
Экспорт читал МС-1 при выбранном ИС-7, не менял selection и inventory.
Независимая проверка: `M/wire/export-checks-01/result.json`.

## Реализация и точная граница выдачи

**20 обычных ББ / 0 HEAT / 0 ОФ — явная политика test_lab**, не историческая
начальная комплектация. Без запасов на складе, автопополнения, оплаты и стрельбы.
Доменный ID `shell:ms1-stock-ap` отделён от native CD2570 слоем совместимости.

- Новый profile/snapshot4 и `r4-catalog3`, прежний wire sync revision1.
  Frozen генераторы profiles1/2/3 не изменены.
- `tools/ms1_ammo_state.py`: проверка native происхождения и точной дельты;
  безопасный primitive encoder допускает только необходимый layout tuple key.
- `web/src/ms1-ammo.mjs`: offline plan/apply/rollback, SHA перед записью,
  consistent SQLite backups, immutable fixture, один conditional UPDATE,
  идемпотентность, отказ при изменившемся target или журнале.
- `game-adapter.mjs`: отдельное чтение profile4, соответствующая проверка
  fixture и общий сайт/игра overview. `account.ejs` показывает фактический total20.
- `hangar091.rs`: добавлена coherent версия4; смешанные/будущие версии отвергаются.
  Транспортные обработчики и каталог не переписаны.
- Отдельные native probe/scenario и пассивный profiler наблюдают исходные
  `AmmunitionPanel.__updateAmmo → as_setAmmoS`; callback данные не подменяются.

Primary UUID `c5326cc1-8524-479c-8bba-72e973489c22`, nativeID1.
Журнал `M/primary-ammo-grant-01/prepared.json`, SHA256
`555015e23983c510ce17744ce50f9905376db396e9af7f8d09edf43690b87819`.
До: profile3 SHA `5167ea63f0503952b4ab1e7c4b1ed2dca5e5da6b6812bd476a87124a891e0888`.
После: profile4 SHA `2610dbd9ee64a12852986def336da057326f14a3289dda43eaae616286998d2d`.
Фактические результаты: PLANNED → GRANTED → ALREADY_GRANTED.
Независимый read-only review: `M/data/live-grant-review-01/result.json`.

State вырос1284→1329B: изменились только shells/layout МС-1. Обратная замена
восстанавливает все прежние1284B. Shop507B и dossier92B побайтово прежние.
ИС-7, оба танкиста, UUID/nativeID, ресурсы, статистика и второй аккаунт сохранены.
Источник: `M/wire/fixture-checks-01/result.json`, prepared backups и manifest.

## Реально выполненные проверки

| Проверка | Результат и доказательство |
|---|---|
| Реальный native export | PASS, export01 и envelope выше |
| Python generator | PASS19, `M/data/checks-01/` |
| SQLite/HTTP plan/apply/rollback | PASS8, там же; isolated4→3→2→1 |
| Probe и scenario | PASS27+32 на Python3 и те же на2.7.3, `M/gui/` |
| Passive profiler | PASS18 на каждой версии, `M/gui/profiler-01/checks-02/` |
| Root control/regression | PASS75, `M/root-checks-02/result.json` |
| Rust offline/locked | PASS84 и build, `M/server-rebuild-01/` |
| Полный web suite | PASS82, 3optional NOT_RUN в этом запуске; `M/web-checks-01/` |
| Три пропущенных crew regression | PASS3 отдельно с actual export, `M/web-crew-regression-01/` |
| Настоящий HTTP кабинет основной учётки | PASS, `M/website-proof-01.json`; API20 и HTML20, чужой query игнорируется |
| Два native входа после выдачи | PASS, `M/wire/verify-ammo02-pair-02/ms1-ammo-verification.json` |
| Verifier и независимые отрицательные проверки | PASS41 +60 actual controls, `M/wire/checks-final-01/` и `M/gui/verifier-review-01/` |
| Ручная проверка владельцем новой выдачи | NOT_RUN |
| Бой, расход/пополнение/покупка снарядов | NOT_RUN, не реализованы |

Итоговый аудит: `M/final-audit-01/final-state-audit.json`, SHA256
`cc69a32abcdd6b8ced4f82dd8884ecca8f3e330fa695b1baebb7f5471bba8a49`.
Original3469 файлов неизменны; research3490 соответствует ledger обычной010
и сохранённым owner logs,0unexpected. Проверены17completed diagnostic restores,
4неизменные конфигурации и21отрицательный контроль аудита. Manifest01 снят до
установки010; итоговый полный обход после установки — `M/final-client-manifests-02`.
Normal010:16modules,25immutable+3ownerlogs, безcontrol/autologin/autoquit/capture.
Независимый review аудита: `M/gui/final-audit-review-01/result.json` SHA256
`1ea80bb84c67456f76c459e5c8da5776978f34c5fb807d20896e9d66e19fbbe5` PASS,
ещё14 RAM-negative controls отклонены. Проверены текущие профили и связь последних
owner logs с backup/тремя новыми diagnostic ledgers. Финальные authored sources,
конечные health/Git-ignore проверки: `M/closure-02/`.

Файлы этой карточки: изменены `client_patch/sr_interactive.py`,
`tools/interactive_client.py`, `tools/diagnostic_client_run.py`,
`tools/wg_probe/src/hangar091.rs`, `web/src/game-adapter.mjs`, `web/views/account.ejs`.
Добавлены2client modules (`ms1_ammo_probe.py`, `ms1_ammo_scenario.py`),
2tools (`ms1_ammo_state.py`, `verify_ms1_ammo_native.py`), `web/src/ms1-ammo.mjs`,
6Python tests `tests/test_ms1_ammo_*.py` и2web tests
(`account-ammo-display.test.mjs`, `ms1-ammo.test.mjs`).
Обновлены STATUS/README/MISSING_INPUTS, добавлены план и этот отчёт.
Полные before/after SHA каждого продуктового файла находятся в audit
`checks.sources_configs`. Git commit в этой карточке не создавался.

Ammo01 PID50088 и ammo02 PID82864: по94 настоящих пакета, exit0, штатный native
quit после результата,12cleanup и rollback. Прежний client-profile-002 не чистился.
Непрерывная готовность17.1284/17.0981s; по3 фактических снимка account/ammo и2PNG.
Родной Meta normal return27 несёт20/0/0, maxAmmo96 и defaultAmmoCount20.
Первый pre-grant account cache CRC−1406441505, второй51539670; внутри каждого
входа initial/refresh согласованы, shop/dossier прежние. Это новое серверное
состояние после выдачи, а не принятие клиентского кэша как авторитетного.

Четыре PNG просмотрены: счётчики20/0/0, МС-1, два танкиста и ресурсы видны.
Цветное зерно в native PNG осталось OBSERVED; причина UNKNOWN. Визуальная
проверка подтверждает перечисленные элементы, не идеальную картинку целиком.
Артефакты: `M/ammo01-prepare`, `M/ammo02-prepare`, их `*-runtime/screenshots`.

Итоговый native report SHA256
`b218c032e9fddbee62f5284e98db9cb7019ddead25994d847af8119272ca035c`:
17/17 gates каждой сессии и отдельная проверка cached pair. Verifier SHA256
`0545274b6a8f6875ad2b8f7767de6360fa91e456a5c87e53f7e83ca0f81084ac`.
Новый gateway EXE SHA256
`3edf29e2dc85ce40a5b8c8fc9880bc5995cdb053f18c483f2af5d8c8444cf570`;
offline build связан с79 исходными own/vendor inputs и обеими реальными сессиями.

## Повтор запуска

Из `D:\WoT_9.1_Server`; только свой локальный стенд и исследовательская копия.

```powershell
python -B -X utf8 tools/local_server.py status --config local/server/service.json
python -B -X utf8 tools/local_server.py start --config local/server/service.json --capture
```

Команду start применять лишь к остановленному сервису. Обычный ручной запуск:

```powershell
Start-Process -FilePath 'D:\WoT_9.1_Server\WoT_0.9.1_RU_0717_research\WorldOfTanks.exe' -WorkingDirectory 'D:\WoT_9.1_Server\WoT_0.9.1_RU_0717_research'
```

Для нового диагностического повтора нужны закрытый клиент, штатный rollback
обычной установки010 и свежее имя, напримерammo03. Credentials читаются из
имеющегося ignored собственного файла; в отчёт и Git они не записываются.

```powershell
python -B -X utf8 tools/interactive_client.py rollback --out local/client-install-010
python -B -X utf8 local/evidence/20261005-p02-ms1-ammo/prepare_run.py --name ammo03
python -B -X utf8 tools/diagnostic_client_run.py --install local/evidence/20261005-p02-ms1-ammo/ammo03-prepare --service local/server/service.json
```

Это запуск до наблюдаемого условия, без внешнего таймера EXE/управления вводом.
После нового запуска необходимо заново просмотреть PNG и выполнить verifier;
старый visual-review нельзя копировать как доказательство новых пикселей.
Полные фактически использованные argv сохранены в `M/*command.json` и `M/wire/`.

Повтор независимой проверки уже записанной пары, с новым выходным каталогом:

```powershell
python -B -X utf8 tools/verify_ms1_ammo_native.py --install local/evidence/20261005-p02-ms1-ammo/ammo02-prepare --previous-install local/evidence/20261005-p02-ms1-ammo/ammo01-prepare --fixture local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r4-catalog3 --native-ammo-export local/evidence/20261005-p02-ms1-ammo/native-ms1-ammo-export01.json --native-crew-export local/evidence/20261005-p02-ms1-crew/native-ms1-crew-export01.json --build-proof local/evidence/20261005-p02-ms1-ammo/server-rebuild-01/after.json --out local/evidence/20261005-p02-ms1-ammo/recheck-pair-01
```

## Откат и ограничения

Пакет010 откатывается предыдущей командой после закрытия игры и проверки ledger.
Боекомплект откатывается отдельно: остановить собственный game service и:

```powershell
node web/src/ms1-ammo.mjs rollback --service local/server/service.json --journal local/evidence/20261005-p02-ms1-ammo/primary-ammo-grant-01 --expect-journal-sha256 555015e23983c510ce17744ce50f9905376db396e9af7f8d09edf43690b87819
```

Это exact4→3; весь DB backup поверх живой БД не копировать. Fixture/journal
сохраняются. Production rollback сейчас NOT_RUN; isolated rollback PASS.
Для дальнейшего3→2 старый crew journal требует прежний bridgeb3cef…:
подробные guard/hash/commands в `M/data/live-grant-review-01/ROLLBACK.md`.
Журналы ради совместимости не переписывались. Старые source и EXE сохранены
в `M/baseline-01/project-before.zip` и `M/server-rebuild-01/gateway-before.exe`.

Исторические промежуточные FAIL сохранены: первая native проверка ошибочно
считала ранний arm marker началом авторизованного интервала; следующая упиралась
в регистр Windows-пути. Исправлен verifier, а не трасса. Negative controls усилили проверку parent payload
и call offset. Был test-loader FAIL Python2, затем исправлен только тест.
Web restart сработал, но capture_output helper завис после выхода PowerShell;
остановлен только свой ожидающий helper, health и реальная авторизация проверены
отдельно. Exit-code команды restart UNKNOWN; данные/API/кабинет PASS.
Локальные ошибки команд (`utf8-sig`, `apply` вместо `install`) не изменили клиент
или БД; исправлены перед соответствующей операцией. Closure01 ошибочно сравнила
mutable logs с пустым installed hash; closure02 использует их before hash,
сохранённый в ledger. В этих вспомогательных исправлениях продукт не менялся.

Полный P02 остаётся PARTIAL. Нет стрельбы, Cell/Avatar боя, пополнения,
смены раскладки игроком, экипажа/боекомплекта ИС-7. Серверная сессия1800s прежняя.
**Единственный следующий шаг:** исследовать и воспроизвести минимальный native
переход Account→Avatar с загрузкой одной собственной локальной арены; движение
и стрельба не входят в доказательство одного такого перехода.
