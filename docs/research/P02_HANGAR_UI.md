# P02 — каталог модулей и интерфейс ангара

2026-10-04. Карточка [плана](../plans/P02_hangar_ui.md), отдельная от арены.
Исторический checkpoint UI06 приведён ниже. Текущий итог после UI12:
**cached sync и GUI проверены по отдельным gates; полная приёмка PARTIAL**,
подробности в последнем разделе.
Здесь `E` = `local/evidence/20261004-p02-hangar-ui/`.

## Подтверждённая причина и изменение

**VERIFIED:** прежний серверный `shop.bin` перечислял только МС-1.
Оригинальный ItemsRequester строит доступные предметы из `itemPrices`, поэтому
у пяти уже установленных модулей отсутствовали строки каталога. В UI04 родной
Flash получил `selectedIndex=-1`; записаны три вызова complex tooltip с `None`
и три настоящих исключения. Скриншоты владельца UI05 показывают пять `textField`
вместо предметов. Ошибка не подавляется перехватом и не исправляется заменой
`None` на пустую строку.

Источники: `E/profile-analysis/inspect_shop_enumeration.py`,
`mounted_module_provenance.py`, `verify_module_catalog.py`,
`E/gui-analysis/inspect_empty_dropdown.py`, original hashes/offsets в их outputs,
`E/wire-analysis/ui04-negative-03/hangar-ui-verification.json`,
`E/owner-screenshots-ui05/`. Исходный original ToolTip.pyc:
`93b44d6c3cf47e32eca5f035442db2e245af5fab3f23475823348b1b5ff91e04`.

`tools/hangar_state.py --catalog-version 2` добавляет пять установленных модулей
с проверенными ID и reference prices из XML именно #717. Все пять цен МС-1
в исходных данных равны нулю. Это данные отображения, разрешения на покупку
из них не выводятся. Новая версия публикуется рядом: `UUID/r1-catalog2`.
Доменный профиль остаётся revision1; `state.bin` и `dossier.bin` побайтно
сохранены. Исторический `UUID/r1` не перезаписывается.

Bridge проверяет исходники, каждую длину/хеш payload, exact profile и связь
`catalog-migration.json` перед повторным использованием. Повреждённый снимок
даёт отказ 503; автоматического сброса аккаунта нет. Для двух прежних primary
учёток сохранены UUID/native ID, дата регистрации, ресурсы, статистика и
ответ кабинета: `E/catalog-domain-preservation-01.json` PASS.

**VERIFIED:** пустой родной dropdown рисует пять шаблонных строк, если список
пуст. `client_patch/hangar_capabilities.py` после полного original `_update`
отключает только действительно пустые optionalDevice/equipment selectors,
сохраняет hit testing для подсказки и передаёт явный текст недоступности.
Пять заполненных selectors не изменяются. Изменение комплектации получает
явный отказ стенда, без ложного успеха/RPC. Все три original class bindings
и временные свойства восстанавливаются при cleanup. Фактическое срабатывание
отказа `setVehicleModule` в UI06 **NOT_RUN** — пользователь его не вызвал.

## Реальные запуски

| Run | Результат |
|---|---|
| UI03 | 337.827 s, exit0/rollback PASS, два original ToolTip None — FAIL сохранён |
| UI04 | 181.448 s, exit0/rollback PASS; Awards/шесть переходов наблюдались, три ToolTip None — FAIL сохранён |
| UI05 | 147.630 s, exit0/rollback PASS; замороженные исходники UI04, три прежние ошибки; фотографии владельца показывают placeholders |
| UI06 | 305.905 s процесса, 818 packets, 279.601 s непрерывно готового ангара, exit0, 11 cleanup stages, rollback PASS; свежих Python-ошибок 0 |
| UI07 normal | 456.398 s процесса, 171 packets, ручной вход без control; Awards/Statistics/Technique и возврат в ангар, exit0/11 cleanup/rollback, 0 ошибок; strict duration gate FAIL: longest ready23.338 s <60 s |

UI06: `E/ui06-catalog2-manual-prepare/native-outcome.json`,
`E/wire-analysis/ui06-predecessor-02/hangar-ui-verification.json`
SHA256 `6965604447ecb8aab98637a1be952beb62d7069ad1f9e17e7720a5cafa22119a`.
Session PASS включает настоящий wire, original Account callbacks, immutable
серверный snapshot и просмотр native Hangar PNG. Original EXE SHA256:
`86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed`.

**VERIFIED:** UI06 содержит 14 завершённых original complex tooltip цепочек
`onCreateComplexTooltip:28 → __genComplexToolTip:117 → as_showS:30`.
Original `AmmunitionPanelMeta.as_setDataS` передал пять настоящих mounted ID
`6658/5891/5892/3589/7` и завершил bound Flash вызовы.
Evidence: `E/wire-analysis/ui06-native-catalog-policy-01.json`.
Это доказательство данных и вызовов; оно само по себе не доказывает пиксели.

**OBSERVED:** пользовательские UI06 PNG показывают заполненный список
37-мм орудия и читаемую штатную подсказку башни МС-1. Сохранены без изменения:

- `E/owner-screenshots-ui06/gun-list.png`, SHA256
  `26148d4134c58aca16c7c9a15d423dd2b765720187d68c747de942250a1abf50`;
- `E/owner-screenshots-ui06/turret-tooltip.png`, SHA256
  `64b05069c26bd6469e7a32214b2a335b666b4cbc29dab82f4050d5d0090b7b9f`.

Источник — прямые вложения владельца; exact native call/timestamp этих PNG
не установлен. Пассивные screenshots с задержкой иногда захватили следующий
UI после движения мыши. Они не использованы как PASS соответствующей подсказки.
Public PyGFx координаты оказались кэшированными; поздний hover по ним не
атрибутируется. В UI06 `native_profile_call=0`: ответ владельца «сделал» не
заменяет отсутствующую трассу Awards. Награды и видимый текст недоступности
по этой серии остаются **NOT_RUN**.

После просьбы владельца управление компьютером прекращено. UI05/06 не
переключали вкладки автоматически; дальнейшие mouse/keyboard действия
выполняет владелец. Разрешены пассивные trace/PNG. UI07 завершён как обычный
вход без control/autologin/autoquit. Отчёт
`E/wire-analysis/ui07-normal-manual-01/hangar-ui-verification.json`, SHA256
`4ecd3ffccacb0a8b97ae904dcb09ac653940edc80b97866c81aeb28d86a699d6`.
Новые original Awards119 → Meta120 завершились offsets266/30, семь секций,
92 элемента каталога, earned0; десять complex Tooltip вызовов прошли штатно.
Общее соединение около47 s; переходы разбили его на серии ready, максимальная
23.338 s. Порог60 s сохранён: strict session/overall **FAIL по длительности**,
не ошибка клиента. Awards/Tooltip PNG отсутствуют, visual GUI **NOT_RUN**.
Обычный повторный вход/те же данные/clean exit фактически наблюдались,
но полный критерий длительности и визуальной приёмки ими не подменяется.

Для следующего отдельного run добавлен opt-in `--capture-ui-passive`:
без control/login/input/переключений, до8 tooltip PNG, до2 Awards PNG отдельно
и до2 PNG реально выбранных владельцем машин после2 s стабильной ready-модели.
Первый Hangar PNG сохраняется отдельно, всего не более13. Marker каждой машины
связан с `native_hangar.observation_index`; actual pixels всё равно проверяются.
Default normal mode этого не включает. 12 unit scheduler/boundary checks и
компиляция настоящим Python2.7.3 PASS: `E/passive-ui-02/`.
Новая native проверка этого opt-in на момент checkpoint **NOT_RUN**.

## Проверки и повтор

PASS: observer primitive 9 tests; original Python 2.7.3 compile/runtime checks;
UI probe 15 tests; capabilities 14 tests на Python3 и Python2.7.3; mounted
catalogue 9 tests; bridge catalogue suites 21 tests; GUI verifier 73 tests.
Их журналы лежат в `E/gui-analysis/`, `E/profile-analysis/`,
`E/bridge-catalog-tests-02.log`, `E/wire-analysis/`.
Unit tests не названы проверкой клиентской совместимости.

```powershell
python -X utf8 local/evidence/20261004-p02-hangar-ui/prepare_case.py --tag ui-repeat-01 --normal
python -X utf8 local/evidence/20261004-p02-unified-account/drive_native.py --install local/evidence/20261004-p02-hangar-ui/ui-repeat-01-prepare --timeout 720 --service local/server/service.json
```

`ui-repeat-01` должен быть новым именем. Runner меняет только research-copy,
сохраняет before hashes/backups, wire/logs и выполняет rollback при завершении.
Владелец вручную входит, открывает «Достижения → Награды», возвращается в
ангар, проверяет подсказки и закрывает игру. Таймаутное завершение не считается
чистым выходом. Независимая проверка UI06:

```powershell
python tools/verify_hangar_ui.py --install local/evidence/20261004-p02-hangar-ui/ui06-catalog2-manual-prepare --registration local/evidence/20261004-p02-unified-account/operator-email-binding-01/registration.json --credentials local/evidence/20261004-p02-unified-account/operator-email-binding-01/test-credentials.json --case operator_shared --private-key local/server/native-private.pem --fixture local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r1-catalog2 --catalog-baseline local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r1 --mode controlled --min-ready-seconds 60 --out local/evidence/20261004-p02-hangar-ui/ui06-verification-repeat-01
```

Ожидаемый результат этого неполного GUI run — session PASS / overall NOT_RUN.
Новый normal verifier использует `--mode normal --previous-report` с UI06
отчётом. Два неполных GUI run не складываются в полный PASS.

## Сохранность и откат

До карточки: `E/before.json`, `project-before.json/zip`, согласованные
`before-game.sqlite` и `before-portal.sqlite`, конфиги, `client-install-001-before`,
полные `E/baseline-installed/` manifests. Старый установленный package001
откачен своим ledger; повторно использовать этот ledger нельзя.

Для любого ещё установленного диагностического пакета:
`python tools/interactive_client.py rollback --out <его prepare directory>`.
Rollback проверяет текущие/исходные хеши, сохраняет новые журналы и не трогает
original-copy. Исторические пользовательские логи сохранены.

Откат каталога: остановить только собственный game supervisor, вернуть
сохранённый bridge/generator source из `project-before.zip` и запустить с
сохранившимся `r1`; БД и identity для этого не заменяются. Снимки `r1-catalog2`
сохраняются как evidence. Для нового аккаунта, созданного уже в catalogue2,
возврат и повторное продвижение требуют отдельной проверки migration ledger;
не удалять/переписывать существующий snapshot автоматически.

## Ограничения

Арена/бой/покупки/экипаж/зарядка не реализованы. Нули статистики — отсутствие
боёв, а не имитация истории. ИС-7 исследуется отдельной явно разрешённой
[карточкой](../plans/P02_test_is7.md); его native export UI06 получен, выдача
и реальное переключение на момент этого checkpoint **NOT_RUN**.
Полный P02 PARTIAL, P03 NOT_STARTED.

## Итог после реальных cached runs UI08–UI12

Текущий статус **PARTIAL**. Старые checkpoint/NOT_RUN выше относятся к своим
запускам. UI08 подтвердил серверный ИС-7 и74.336 s ready; UI11 после исправления
cached sync подтвердил обе модели, возврат между ними, original callbacks,
реальные Awards и readable complex tooltip вкладки «Ангар». Все10 native PNG
UI11 просмотрены root; файлы visual-review*.json в prepare связывают пиксели
с trace/call/observation, источник ручных действий — ответ владельца «готово».
Typed tooltip орудия МС-1 также виден. Текст недоступности оборудования на
имеющихся PNG не пойман, поэтому его визуальная приёмка **NOT_RUN**.

UI11:289 packets,109.445 s процесса,91.320 s канала,0 свежих ошибок,11 cleanup,
exit0 и rollback PASS. Session/overall остаётся **FAIL**: непрерывный ready
между переключениями41.173 s вместо заранее заданных60. UI12:1866 packets,
727.338 s процесса; отдельно OBSERVED657.1134961 s/655 ready samples одного
МС-1. Владелец подтвердил только вход; дальнейшие UI-действия/выход не
зафиксированы.720 s timeout завершил процесс сexit1; полный cleanup не выполнен,
filesystem restore PASS. Полной успешной сессией этот запуск не является.

Доказательства: `E/is7-verifier/ui11-reviewed-final-01/`,
`E/is7-verifier/ui12-timeout-negative-01/`,
`E/is7-verifier/ui12-narrow-observation-01/`,
`E/wire-analysis/ui11-cached-proof-03/`,
`E/accounts-final-01.json`. Точные причины двух устранённых зависаний,
исходники и откат — [P02_TEST_IS7](P02_TEST_IS7.md).

Python full suite:236 tests,235 PASS/1skipped; отсутствующий local temp для
guarded-write затем предоставлен, его5-test suite PASS без skip.
Итого все236 уникальных checks выполнены. Логи `E/python-full-final-01.log`
и `E/preferences-guard-final-01/test.log`. Node65/65, Rust61/61 PASS.

Оставлен пакет `local/client-install-002`: те же шесть compiled modules,
обычный вход, без diagnostic control/autologin/autoquit/capture.
Отдельный запуск окончательного конфига после установки NOT_RUN.
Rollback: `python tools/interactive_client.py rollback --out local/client-install-002`.
Полные manifests и source delta — `E/final-manifest-02/`, `E/final-audit-03/`.
Controlled integrity PASS: original3469 файлов неизменны, research3480 файлов,
17/17 before/backup checks,11/11 восстановлений своих ledger. Два входных лога
поменялись между UI04 и UI05 (инициатор UNKNOWN), затем сохранялись побайтно.
Их не подменяли старой версией ради PASS; strict baseline FAIL отдельно сохранён
в final-audit-01. Пустой replay после UI12 timeout с исходным SHA/backup
обратимо перенесён в `E/ui12-timeout-replay-01/`; оригинальная копия не затронута.
Следующий шаг: один полный контрольный cached run с60 s до действий,
пикселями оборудования/Awards и ручным выходом; затем можно закрыть карточку.

## UI13: ручное завершение вместо таймера

2026-10-04, по прямому запросу владельца. Подготовлен повтор на том же
`local/client-profile-002`, без очистки Account/Shop/Dossier cache. Пакет002
откачен своим ledger (`local/client-install-002/restore.json` PASS); новый
подготовленный пакет — `E/ui13-is7-manual-prepare`, trace —
`E/ui13-is7-manual-runtime`. Все шесть исходников и compiled modules точно
совпадают с UI12: `E/manual-runner-01/prelaunch-package.json`. Хеши семи
входных profile-файлов — `E/manual-runner-01/profile-before.json`.

Утилита `tools/manual_client_run.py` заменяет прежний временный runner с720s
timeout. Она ожидает закрытия процесса пользователем, без автоматических
terminate/kill и без управления вводом. Прерывание утилиты при живом клиенте
должно оставить клиент и установку нетронутыми, записать незавершённое
состояние. Откат исследовательских файлов — только после выхода клиента.
Объём диагностики ограничен отдельно; исчерпание записи не должно закрывать
игру или превращаться в ложный PASS.

Read-only проверка действующего gateway на17:11:30UTC: процесс60212 и
identity101620 живы, health200; запись2163/10000 packets,47724/16MiB bytes.
Сервер всё ещё имеет отдельный1800s deadline соединения,8s idle и bounded
retries. Поэтому отсутствие автозакрытия EXE не означает безлимитный канал.
Решение о серверных лимитах этой проверкой не менялось.

Пассивный наблюдатель измеряет60s готового ангара; сам не ожидает, не закрывает
процессы и не вводит команды. `E/manual-runner-01/observe_ready.py` повторил
историческое значение UI11 ровно41.1733396s; отрицательный duration gate
сохранён. Команда для живого снимка:

```powershell
python -X utf8 local/evidence/20261004-p02-hangar-ui/manual-runner-01/observe_ready.py --runtime local/evidence/20261004-p02-hangar-ui/ui13-is7-manual-runtime --expected local/evidence/20261004-p02-hangar-ui/is7-verifier/ui08-reviewed-03/test-garage-verification.json
```

Runner/tests заморожены: SHA256 runner
`9020053e2c748f1540bb1d8388f431c7e0cdc109fddf7dee935da16462ac59aa`.
Новая suite14/14 PASS: `E/manual-runner-tests-01.log`; проверены обычный exit,
crash, прерывание/ошибка при живом процессе, spawn failure, partial ledger,
capture failure/limit, bounds, roots и запрет control/autologin/autoquit.
Это тесты управления процессом, не проверка совместимости с native.

Реальный UI13 запущен17:19:31UTC: клиент81144, скрытый runner12364.
`E/manual-runner-01/launcher.json`, stdout/stderr и
`E/ui13-is7-manual-prepare/native-process.json` подтверждают фактический старт.
Команда, выполненная root из скрытого фонового процесса:

```powershell
python -X utf8 tools/manual_client_run.py --install local/evidence/20261004-p02-hangar-ui/ui13-is7-manual-prepare --service local/server/service.json
```

Подготовленный run одноразовый: повтор требует нового `--out` при prepare
и нового trace-каталога после закрытия/отката предыдущего. Повтор тестов:

```powershell
python -X utf8 -m unittest discover -s tests -p test_manual_client_run.py -v
```

После ручного закрытия runner собирает результаты и откатывает свой ledger.
Если runner прерван при живом клиенте, он пишет interrupted report и оставляет
игру; после самостоятельного закрытия ручной отложенный откат:

```powershell
python -X utf8 tools/interactive_client.py rollback --out local/evidence/20261004-p02-hangar-ui/ui13-is7-manual-prepare
```

**Итог UI13 — PASS.** Общий verifier, session, cards garage/GUI и relogin
PASS. Готовый ангар125.7657979s/126samples до первой вкладки, network198.9757065s,
586 packets, process247.3996002s, exit0/no timeout,11 cleanup и rollbackPASS.
Оба танка с ожидаемыми именами/HP/ресурсами видимы на root-reviewed nativePNG.
Original Awards196 и complex Hangar tooltip199 читаются на своих PNG.
Trace SHA `4fa3b0c0550272ded05850387a7dcb21e295387415edcfeca5f60481fa4e7b4e`.
Основной отчёт `E/is7-verifier/ui13-reviewed-01/test-garage-verification.json`,
SHA `2b6620e1b91725bfe941a59dbffbc968748630381fb9fc090a24e53213cee3cc`.
Независимый wire proof16/16 PASS — `E/wire-analysis/ui13-manual-proof-01/`.
Все7 frozen verifier/generator/client source hashes сохранены. Старые FAIL
не переписывались; UI08→UI13 связаны тем же profile_dir и точным состоянием.

Фото владельца `E/owner-screenshots-ui13/equipment-unavailable.png`, SHA
`49200248b89515ff11dd58aeb818858428f1859b8f17653b7e3496b24352fa00`:
видны ИС-7, ник/ресурсы и читаемое сообщение о недоступности оборудования.
Классификация OBSERVED/PASS для пикселей; exact photo timestamp/callID UNKNOWN.
Это изображение не выдаётся за native screenshot marker. Основной GUI gate
пройден собственными nativePNG без изменения verifier.

После UI13 установлена обычная сборка `local/client-install-003`, без
capture/control/autologin/autoquit, те же6 compiled modules и profile002.
План SHA `3012282b0f30b87735deb6678ac46c8e46cc27b1c3bcacf7a56fb81776c16d44`;
сверка `E/final-package-handoff-003.json` записана ДО дополнительного запуска.

Владелец затем сам запустил003 в22:32–22:33 и подтвердил «Да, это я проверял».
Новый PID62556 trace: OBSERVED вход, server Account и ангар,11cleanup/fini.
Свой harness outcome отсутствует: exit code UNKNOWN; полная native-приёмка
этого дополнительного run NOT_RUN. В fresh python.log два IndexError:
RecruitWindow.__getInitialData и VehicleCustomization →
ShopRequester.getInscriptionsGroupHiddens. Найм/внешний вид пока не готовы
(OBSERVED_FAIL); PASS UI13 на них не распространяется.
Логи, исходный prefix и trace сохранены read-only в `E/normal003-extra-launch-01/`.
Изменение лога во время manifest-03 дало строгий audit04 FAIL, он сохранён.
Финальный аудит после сохранения логов PASS: `E/final-audit-05/`, полный
`E/final-manifest-04/`. Original3469 файлов неизменны; research3480,
неожиданных отличий0.12/12 diagnostic restores и17/17 before/backup checks
пакета003 PASS; откат002 проверен отдельно. Приняты только два точных
сохранённых хеша логов этого owner run;4 negative controls PASS отвергают
другие hash/size/файлы. Report SHA
`5c957e0b6cd82e2c9f1a47126c0a2d20df14215e57c97274c5d190d34c249909`.
Это проверка целостности файлов, она не отменяет две native UI ошибки.

Сайт/оба аккаунта после дополнительного запуска: PASS
`E/accounts-after-normal003-01.json` (без новых auth requests и записей в БД).
Primary сохраняет МС-1+ИС-7, secondary только МС-1; точные UUID/nativeID,
profile_json, даты, ресурсы100000/0/0 и нулевая статистика неизменны.

Откат текущего обычного пакета после закрытия клиента:

```powershell
python -X utf8 tools/interactive_client.py rollback --out local/client-install-003
```

Он сохраняет postrun logs в своём ledger и не удаляет profile002 или серверный
инвентарь. Откат самого grant и dossier cache — отдельная процедура из отчёта
ИС-7; реальный primary rollback NOT_RUN. Документы до этой правки сохранены в
`E/manual-runner-01/docs-before-ui13-final/`; новые runner/tests самостоятельны.

Повтор независимой проверки завершённого UI13 (новый output обязателен):

```powershell
python -X utf8 tools/verify_test_garage.py --install local/evidence/20261004-p02-hangar-ui/ui13-is7-manual-prepare --registration local/evidence/20261004-p02-unified-account/operator-email-binding-01/registration.json --credentials local/evidence/20261004-p02-unified-account/operator-email-binding-01/test-credentials.json --case operator_shared --fixture local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r2-catalog3 --base-fixture local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r1-catalog2 --private-key local/server/native-private.pem --mode normal --min-ready-seconds 60 --previous-report local/evidence/20261004-p02-hangar-ui/is7-verifier/ui08-reviewed-03/test-garage-verification.json --out local/evidence/20261004-p02-hangar-ui/is7-verifier/ui13-reviewed-repeat-01
```

Обычный запуск EXE при работающем своём сервере:

```powershell
Start-Process -FilePath 'D:\WoT_9.1_Server\WoT_0.9.1_RU_0717_research\WorldOfTanks.exe' -WorkingDirectory 'D:\WoT_9.1_Server\WoT_0.9.1_RU_0717_research'
```

Ограничения: test_lab выдача, нет экипажа/боеприпасов/боя; неподдерживаемые
окна найма/внешнего вида требуют отдельных исправлений;1800s gateway limit;
старая строка продукта в welcome notification пока сохранена.
Следующий единственный рекомендуемый шаг — минимальный серверный экипаж
МС-1, его отображение и сохранение после relogin. Эта задача на UI13 остановлена.
