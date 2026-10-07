# P02 — границы неподключённых окон ангара

2026-10-05. Узкая карточка ночной доводки аккаунта/ангара. Цель: исключить
переход из ангара в неподключённые «Внешний вид» и «Обслуживание», сохранив
родное предупреждение, данные машины и обычные информационные callbacks.
Это не реализация ремонта, пополнения, кастомизации или боя.

`W` = `local/evidence/20261005-p02-hangar-windows/`.
`H` = `local/evidence/20261005-p02-hangar-limits/`.
`C` = `local/evidence/20261005-p02-ms1-crew/`.

## Основание и реализация

VERIFIED: у original #717 AmmunitionPanel два undecorated callbacks без
аргументов: showCustomization firstline210/RETURN31 и
showTechnicalMaintenance firstline207/RETURN25. Их original fireEvent
находится на offsets24/18. SHA исходного .pyc
`54d139dd4280314111ce509c15360da8d932cfbc356b30d40c1d9ca96c3addc8`.
Пути, co_code SHA и disassembly: `W/gui/source-audit-01.json`,
`W/gui/original-binding-audit-01.json`.

OBSERVED_FAIL ранее: самостоятельный normal003 владельца открывал
VehicleCustomization, где отсутствующий inscriptions catalog приводил к
IndexError. Traceback сохранён в старом отчёте UI13/normal003. Исследование
причины: `H/gui/appearance-audit-01.md`. Падение TechnicalMaintenance UNKNOWN;
его оригинальные операции repair/fill/setLayouts существуют, но своим
сервером ещё не поддерживаются.

Собственный `_WindowGuard` проверяет точный original source/signature/code,
затем заменяет только эти два входа. Каждый показывает отдельный родной
SystemMessages.Warning. Original callback/fireEvent не вызываются. Общий
event bus, BusinessLobbyHandler и каталоги не подменяются. Это граница двух
входов из панели, а не утверждение о блокировке всех возможных прямых API.
Сервер по-прежнему отвечает за отказ неподдерживаемых команд.

Существующие `_ModuleChangeGuard` и `_BattleGuard` сохранены побайтово.
Все три политики устанавливаются/восстанавливаются в одной lifecycle stage;
partial install и несколько ошибок cleanup проверены отдельно. Helper SHA
`3d68c281050cad0c5318bf07d0ef7899815aaa946e29d3d109bbcaf9cd738f14`.

## Что действительно запущено

| Проверка | Результат |
|---|---|
| Новая политика окон | PASS:21 новых+34 прежних tests на Python3 и2.7.3, всего110 |
| Диагностический сценарий | PASS:31 tests, компиляция pinned2.7.3 |
| Runner/control | PASS:33 tests; отдельное condition, запрет timer/mixed operations |
| Passive trace | PASS:4 selector tests,18 interactive regression включая эти4 |
| Независимый verifier | PASS:53 tests, включая отрицательные фактические corpora |
| Windows01 | PASS:78packets/4458B,15.0800661s wire,35.0021658s процесса |
| Windows02 | PASS:78packets/4458B,15.0369761s wire,34.7259362s процесса |
| Cached повтор01→02 | PASS: тот же profile002, ненулевые настоящие hints |
| Окна/предупреждения | PASS:3 states/3 PNG в каждом проходе, просмотрены root |
| Аккаунт/экипаж | PASS:3 неизменных snapshots каждого прохода, оба stored profiles прежние |
| Неподдерживаемые исходные callbacks/_populate | PASS:0 вызовов; profiler оставался активен |
| Мутации | PASS: только измеренные sync/refresh; CMD108/700/701 отсутствуют |
| Завершение | PASS:0 свежих ошибок,exit0,12cleanup,захват и точный rollback каждого run |
| Физические клики/ручная приёмка владельцем | NOT_RUN |
| Длительная устойчивость этой новой сборки | NOT_RUN |

Диагностический сценарий вызывает именно установленные callbacks реальной
панели. Мышь/клавиатура не управляются. Клиент штатно завершает работу после
доказанного результата; harness не использует таймер закрытия или kill.
Нативная совместимость подтверждается живым EXE и сетью, а не unit fixtures.

Original WINDOW.getView() без criteria всегда возвращает None. Поэтому
отсутствие обслуживания проверяется реальным запросом
`getView(criteria={POP_UP_CRITERIA.VIEW_ALIAS: VIEW_ALIAS.TECHNICAL_MAINTENANCE})`
и getViewCount; отсутствие кастомизации — сохранением current LOBBY_SUB Hangar.
Проверяется один и тот же экземпляр панели/ангара, native модель МС-1 и его
выбор также во время ожидания PNG. Это целевой запрос, не полный обход всех views.

Native original Account.onBecomeNonPlayer RETURN366 после отказов подтверждает,
что profiler продолжал работать. Его compiled source содержит точные targets
двух entrypoints и двух `_populate`; нулевое число этих событий не берётся
из выключенного наблюдателя.

Парный отчёт `W/wire/verify-windows02-paired-01/hangar-windows-verification.json`,
SHA256 `62a206bf7c208a313900b12e5cfdcf30b4a7690d01676ae8e7ea81a4d78903ec`.
Root повторила verifier в `W/root-verify02-paired-01/`, SHA побайтово тот же.
Source verifier SHA `60108cc47108b9b938558e3c0d2ce58d7e28b01f9558232d6780577dee0d4701`.
Старые crew/limits verifiers заморожены и не изменены.
Независимый read-only review: `W/gui/verifier-review-01.md/json`, JSON SHA
`c676f4e4389a77d151ce1d3636137cc207142b51cfcbbd1e5763bc20dea25824`.
Блокирующих findings нет:36 actual/negative checks и отдельная stdlib сверка
156 пакетов/22 compiled sets/6 PNG PASS. Повторно просмотрены3 PNG Windows02.

Оба run: client sequence7/server21; AccountCRC−1406441505,
Shop518/−846328027, Dossier1/1791128141. Все три payload сверены с собственной
fixture profile3. Полная версия аккаунта не понижается до wire cursor.
Stored profiles: `C/accounts-after-windows02.json` PASS:
primary `5167ea63f0503952b4ab1e7c4b1ed2dca5e5da6b6812bd476a87124a891e0888`,
secondary `b8de0e18d174178815eae3db4acb28a91a3f5c5eddc60aa43e668b6e3b2d6b13`.

PNG находятся в `W/windows01-runtime/screenshots/` и `W/windows02-runtime/screenshots/`.
Файлы visual-review-windows.json в prepare связывают отдельный просмотр root
с точными PNG/trace SHA. На исходных PNG остаётся прежняя цветная зернистость;
причина UNKNOWN, полная графическая приёмка не объявляется.

Первый отчёт verifier Windows01 сохранён FAIL: проверка ожидала basename,
а визуальная аттестация содержала абсолютный путь. Исправлен только формат
сопоставления точного owned PNG; чужой путь по-прежнему отвергается. Это не
падение клиента. Старый limits03 ожидаемо отклоняется новой приёмкой окон,
его исторический PASS своей карточки сохранён.

## Изменённые файлы и повторение

Продукт: `client_patch/hangar_capabilities.py`.
Диагностика: `client_patch/hangar_windows_scenario.py`, `client_patch/sr_interactive.py`,
`tools/interactive_client.py`, `tools/diagnostic_client_run.py`, `tools/verify_hangar_windows.py`.
Тесты: новые test_hangar_window_capabilities, test_hangar_windows_scenario,
test_hangar_windows_verifier, test_interactive_window_trace и расширенный
test_diagnostic_client_run. Документы: этот отчёт, STATUS, карточка/ночной план.
Backend, генераторы, endpoint configs и fixtures этой карточкой не менялись.

Из корня проекта; для повторного отчёта использовать новый --out:

```powershell
python -B -X utf8 tools/verify_hangar_windows.py --install local/evidence/20261005-p02-hangar-windows/windows02-prepare --previous-install local/evidence/20261005-p02-hangar-windows/windows01-prepare --fixture local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r3-catalog3 --native-export local/evidence/20261005-p02-ms1-crew/native-ms1-crew-export01.json --out local/evidence/20261005-p02-hangar-windows/verify-repeat-01
python -B -X utf8 -m unittest discover -s tests -p test_hangar_windows_verifier.py -v
python -B -X utf8 -m unittest discover -s tests -p test_hangar_windows_scenario.py -v
python -B -X utf8 -m unittest discover -s tests -p test_hangar_window_capabilities.py -v
```

Новый native run возможен после штатного отката установленного normal-пакета
и проверки свободного mutex. Helper создаёт новый consumed control, credentials
берёт из существующего ignored файла собственного аккаунта; не регистрирует
новую учётку и не включает пароль в доказательства:

```powershell
python -B -X utf8 local/evidence/20261005-p02-hangar-windows/prepare_run.py --name windows03
python -B -X utf8 tools/diagnostic_client_run.py --install local/evidence/20261005-p02-hangar-windows/windows03-prepare --service local/server/service.json
```

Windows03 выше — команда будущего повторения, NOT_RUN в этой карточке.

## Состояние и откат

`W/baseline-01/`:280 исходников и14 local files до изменений, consistent backups
двух собственных БД. Original только читался. Каждый native install имеет
before SHA, backup, postrun, ledger и restore. Normal004 снят после22 exact
проверок текущего состояния, пользовательские логи сохранены без изменений:
`W/normal004-prerollback.json`, `local/client-install-004/restore.json`.

Установлен обычный normal005:11 проверенных compiled modules и оба MO как
в Windows02. `W/normal005-preinstall.json` PASS,20 static payloads+3 logs.
В нём нет control, autologin, autoquit или автоматических скринов. Отдельный
ручной запуск именно normal005 NOT_RUN. Игра закрыта; сервер и сайт работают.
Финальная сверка полных manifest/ledger PASS:
`W/final-audit-01/final-state-audit.json`, SHA256
`ddbfa7525ce105e44518f1ae4bb797e31db588af46718fb898503627788eda32`.
Original3469 файлов неизменны; research3485 точно соответствует цепочке
003→004 rollback→005, неожиданных отличий0. Все9 ночных restores,23 before-checks,
29 frozen backend sources и оба stored profiles PASS.13 отрицательных контролей
отвергают изменения файлов/манифестов/ресурсов/nativeID и потерю второй учётки.

Откат после закрытия клиента:

```powershell
python -B -X utf8 tools/interactive_client.py rollback --out local/client-install-005
```

Исходники восстанавливать выборочно из baseline только после сверки текущего
SHA. Не восстанавливать старую БД поверх живых аккаунтов. Выдача экипажа/ИС-7
не относится к откату UI-карточки.

Статус: узкая native карточка PASS, весь P02 PARTIAL, P03/арена/бой NOT_STARTED.
Единственный следующий шаг: отдельная проверка штатного выхода на LoginView
и повторного входа тем же аккаунтом внутри одного EXE, без перезапуска процесса.
Измеренный original контракт: `W/gui/next-narrow-checks.md`; этот новый путь NOT_RUN.
