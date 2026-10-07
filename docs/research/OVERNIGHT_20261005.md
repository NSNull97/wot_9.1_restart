# Ночная работа 5 октября 2026 года

Утренний сводный отчёт по поручению владельца работать самостоятельно.
Цель: довести текущий Account/Hangar, сохранить настоящий native протокол,
проверить данные и повторный вход. Ночь завершена стабилизацией установленной
обычной сборки009. Полный P02 остаётся PARTIAL; ручная приёмка ночью NOT_RUN.
Актуальная установка — в `docs/STATUS.md`, хронология —
`docs/plans/OVERNIGHT_20261005.md`.

Дополнение после утренней ручной проверки: владелец подтвердил нормальные
вход, отображение экипажа МС-1 и переключение МС-1 ↔ ИС-7. Эти три пункта
теперь PASS_BY_OWNER (OBSERVED), подробности и отдельные логи:
[P02_MANUAL_ACCEPTANCE_20261005.md](P02_MANUAL_ACCEPTANCE_20261005.md).
Позднее владелец также прошёл естественное истечение сессии и повторный вход;
сервер подтвердил session_deadline11→fresh session12. Результат PASS_MANUAL_AND_BACKEND:
[P02_MANUAL_EXPIRY_20261005.md](P02_MANUAL_EXPIRY_20261005.md).
Исторические NOT_RUN ниже описывают ночь до этих подтверждений; точная задержка
возврата к LoginView по-прежнему неизвестна, прочие окна не входят в ручную приёмку.

## Что уже сделано

1. Основному тестовому аккаунту выдан минимальный серверный экипаж МС-1:
   командир и механик-водитель. Настоящий клиент отображает портреты, имена,
   роли и квалификацию; сайт видит тот же экипаж. Повторная выдача идемпотентна.
   ИС-7 остаётся тестовой машиной без экипажа. Это не реализация найма и экономики.
2. Неподключённые операции ангара явно недоступны: бой, изменение/найм экипажа,
   внешний вид и обслуживание. Вместо запуска сломанных окон выдаётся родное
   предупреждение. Списки установленных модулей берут данные проверенного
   клиента #717; каталог оборудования и снаряжения пока не реализован.
3. Внутри одного EXE работает выход к входному экрану и новый вход с прежним
   кэшем. Найден и исправлен настоящий отказ gateway: клиент сохраняет один
   транспортный ключ между входами, но меняет nonce и UDP endpoint. Теперь
   новая авторизация проходит, при этом проверка закрытых endpoints сохранена.
4. Проверена смена двух собственных аккаунтов A→B→A в одном EXE. Второй получает
   только свой МС-1 без экипажа; первый возвращает свой МС-1, ИС-7 и двух танкистов.
   Все три потока данных каждой сессии совпали с собственными fixtures; dossier
   и кэш не смешались. Профили, ресурсы и статистика остались прежними.
5. Диагностический runner перестал сохранять хеш control-файла с учётными
   данными. Проверка подмены осталась в RAM; значения и производные credentials
   не попадают в новые отчёты. Отдельный negative test меняет только пароль той
   же длины и подтверждает отказ до запуска клиента.
6. Реально повторены три старых UDP datagrams первого аккаунта при работающем
   втором. Все три сервер отверг; второй остался в ангаре, первый вошёл обратно.
   Проверены все280 пакетов и весь backend log, без скрытого удаления ошибок.
7. Настоящий ангар непрерывно готов более15минут:913.294s/909наблюдений.
   182реальных периодических CCU запроса/ответа и normal callbacks, три точных
   неизменных снимка аккаунта, два просмотренных nativePNG, штатное закрытие.
   Это проверка существующего соединения, не новая симуляция или прогресс.

## Реально выполненные проверки

| Срез | Результат и граница |
|---|---|
| Серверный экипаж МС-1 | PASS: crew02/03, настоящие descriptor/GUI/PNG и сайт; live grant journal сохранён |
| Ограничения неподключённых функций | PASS: limits02/03 и windows01/02, настоящие предупреждения; функции сами не реализованы |
| Повторный вход внутри EXE | PASS: R02,188 пакетов,2 авторизации/Account,2 PNG; первый R01 FAIL сохранён |
| Смена аккаунтов внутри EXE | PASS: switch02,279 пакетов,3 авторизации/Account,3 PNG; fleet2→1→2,crew2→0→2 |
| Исправление gateway | PASS:83 Rust tests и настоящий повторный вход; unit-тесты отдельно от native |
| Последний полный аудит L | PASS:original3469/research3488,0unexpected,14 завершённых diagnostic restores,оба профиля прежние |
| Реальный replay закрытого peer | PASS:3 исходных datagrams/3 ingress/3 точных отказа, Bready и возврат A;58 независимых controls |
| Длительный ангар | PASS:long01,2580packets/182responses,913.294sready,181eligible callbacks/span907.793s,0retransmits,exit0/cleanup12/restore |
| Проверщик длительного ангара | PASS:40unit controls,55independent controls,20gates native evidence; первый ошибочный verifier FAIL сохранён |
| Независимый review final audit | PASS:11actual binding checks,38negative controls;8artifacts/trace/2580packets/2PNG rehashed |
| Ручная проверка ночных изменений владельцем | NOT_RUN |
| Арена/бой/экономика/двухклиентская игра | NOT_RUN, вне ночного объёма |

Прежние FAIL и промежуточные verifier/audit результаты сохранены. В частности,
подготовка switch01 была отклонена до изменения клиента из-за ещё установленной
обычной сборки; после проверенного отката выполнен fresh switch02. Дополнительный
review усилил schema проверщика, не потребовав повторного запуска игры.
В L первый FAIL был ошибкой учёта возобновлений родного генератора
`onBecomePlayer` в новом verifier; исправлена именно проверка. Реальный первый
неуспех R01 при повторном входе был исправлен в gateway и подтверждён новым R02.
Эти две разные причины не объединяются в один «всё всегда проходило».

## Где смотреть доказательства

- `docs/research/P02_MS1_CREW.md` и `local/evidence/20261005-p02-ms1-crew/`.
- `docs/research/P02_HANGAR_SERVICE_LIMITS.md` и `local/evidence/20261005-p02-hangar-limits/`.
- `docs/research/P02_HANGAR_WINDOWS.md` и `local/evidence/20261005-p02-hangar-windows/`.
- `docs/research/P02_INPROCESS_RELOGIN.md` и `local/evidence/20261005-p02-inprocess-relogin/`.
- `docs/research/P02_ACCOUNT_SWITCH.md` и `local/evidence/20261005-p02-account-switch/`.
- `docs/research/P02_RETIRED_BASE_REPLAY.md` и `local/evidence/20261005-p02-retired-base-replay/`.
- `docs/research/P02_LONG_HANGAR.md` и `local/evidence/20261005-p02-long-hangar/`.

Последний принятый native report L:
`local/evidence/20261005-p02-long-hangar/wire/verify-long01-03/long-hangar-verification.json`,
SHA256 `c74df14374e053bab68c13a5c1b366814834b50ba8a084123340b32062b95d25`.
Последний принятый полный audit L:
`local/evidence/20261005-p02-long-hangar/final-audit-01/final-state-audit.json`,
SHA256 `1932650550743d296355af81edd48c8e176820853a9e52ba916c6c0e82a2cf1e`.
Independent audit review:
`local/evidence/20261005-p02-long-hangar/wire/audit-review-01/result.json`,
SHA256 `c82997905b315e35636034b75acd87a5081a7203d1463233016fd69d3adc617b`.
Команды воспроизведения, исходные SHA и отдельные способы отката — в каждом
указанном отчёте. Секреты, клиентские ресурсы и raw captures находятся только в
игнорируемых локальных каталогах; в Git не добавлялись.

## Остающиеся границы

Полный P02 остаётся PARTIAL. Нет боя, боекомплекта, полноценного оборудования,
магазина, найма/переобучения или внешнего вида. Успех15-минутной проверки не
доказывает многочасовой сеанс. Лимит сессии gateway1800s сохраняется.
Retirement guard ограничен120s и текущим процессом; это не утверждение о защите
от всех replay/source-spoofing сценариев. Карточка T доказала только один
реальный случай поздних пакетов.
Источник gateway закрывает session на1800s без специального nativekick.
Время фактического native timeout и переход в LoginView при этом UNKNOWN/NOT_RUN.
Read-only основание: `local/evidence/20261005-p02-long-hangar/data/deadline-feasibility-01/`.

OBSERVED: при1024px длинный кириллический ник второго аккаунта обрезается справа,
хотя полное значение корректно передано и прочитано native getter. Причина
цветного зерна на native PNG UNKNOWN. Эти визуальные ограничения не скрыты
за общим PASS изоляции аккаунтов.

Оригинальный клиент только читался. Диагностические изменения research делались
через before hashes, backups и ledger; каждую законченную установку откатили.
Обычный пакет остаётся установленным отдельно и имеет свой точный rollback.
Не выполнять откат старой установки поверх более новой: текущий номер и команда
всегда находятся наверху `docs/STATUS.md`.

## Файлы и текущее состояние

Точный список changed/new исходников и тестов со сверкой SHA относительно
начала карточки C: [OVERNIGHT_20261005_FILES.md](OVERNIGHT_20261005_FILES.md).
Главные изменения: `tools/wg_probe/src/gateway091.rs` (повторный native login),
`web/src/ms1-crew.mjs`/`tools/ms1_crew_state.py` (journalled test crew),
`client_patch/crew_capabilities.py`/`hangar_capabilities.py`/`sr_interactive.py`
(подключение экипажа и доступность UI), отдельные диагностические сценарии,
строгие offline verifiers и их тесты. README/STATUS/NAMING и отчёты сохраняют
различие VERIFIED/OBSERVED/INFERRED/UNKNOWN и фактический объём приёмки.

Исследовательская копия установлена для обычного EXE на свой endpoint;
`local/client-install-009`,14native-tested modules,23immutable payloads
и3preservedownerlogs. Нет one-shot control/autologin/autoquit/автоскриншотов.
Игра закрыта. Собственный server run20261004T234409-c866fd и сайт работают;
endpoint игры127.0.0.1:20014/20016, сайт http://127.0.0.1:3091/.

Git ничего не staged/committed: репозиторий по-прежнему без tracked files.
Actual exclusions проверены для обоих EXE, local config, private key, обеих
БД, test credentials, capture и diagnostic log. Evidence:
`local/evidence/20261005-overnight-final/repository-check-01/result.json`.
Проверка не читала содержимое credentials и не названа универсальным secret scan.

Финальная read-only проверка в07:37 местного времени:
`local/evidence/20261005-overnight-final/runtime-check-01.json` — PASS.
Проверены собственные HTTP health сайта/identity, хеши работающих процессов,
освобождённый client mutex и все26 файлов текущего ordinary package.
Это отдельная проверка живого состояния, не повтор полного клиентского скана.

Утренний архив authored source files:
`local/evidence/20261005-overnight-final/final-authored-sources-01.zip`.
Перечень каждого файла/его SHA и хеш ZIP хранятся рядом в
`final-authored-sources-01.manifest.json`; результат перечитывания архива —
`final-authored-sources-01.verification.json`. Клиенты, raw evidence, базы,
локальная конфигурация, зависимости и учётные данные в этот архив не входят.
Это локальный снимок кода, не Git commit и не полная резервная копия сервиса.

Ночное поручение завершено утром05.10; heartbeat automation-2 переведён вPAUSED.
Исходный09:00 был верхней границей ночного плана. Срез стабилизирован раньше:
все начатые карточки закрыты, следующий30-минутный expiry experiment выделен
отдельно и остаётся NOT_RUN. Границы Account/Hangar не расширялись.

## Точные команды

Из `D:\WoT_9.1_Server`, PowerShell:

```powershell
python -B -X utf8 tools/local_server.py status --config local/server/service.json
# Если собственный сервер остановлен; существующий external website запускается отдельно:
python -B -X utf8 tools/local_server.py start --config local/server/service.json --capture
# Обычный запуск игры для владельца:
Start-Process -FilePath 'D:\WoT_9.1_Server\WoT_0.9.1_RU_0717_research\WorldOfTanks.exe' -WorkingDirectory 'D:\WoT_9.1_Server\WoT_0.9.1_RU_0717_research'

# Read-only повтор последнего native proof; --out должен быть новым:
python -B -X utf8 tools/verify_long_hangar.py --install local/evidence/20261005-p02-long-hangar/long01-prepare --fixture local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r3-catalog3 --native-export local/evidence/20261005-p02-ms1-crew/native-ms1-crew-export01.json --out local/evidence/20261005-p02-long-hangar/morning-recheck-01
python -B -X utf8 -m unittest discover -s tests -p test_long_hangar_verifier.py -v
```

Команда `start` приведена для последующего запуска; работающий сервер ей
повторно не запускался. Ночные штатные запуски/проверки указаны в карточках;
команда обычного ручного EXE после final install009 — NOT_RUN.

## Откат

Обычный client package после закрытия игры и проверки текущего ledger:

```powershell
python -B -X utf8 tools/interactive_client.py rollback --out local/client-install-009
```

Это снимает текущий клиентский пакет. Его installed rollback пока NOT_RUN;
тот же штатный механизм реально восстановил14 завершённых diagnostic installs.
Отдельные backup/hash/journals сохранены для каждого изменения.
Откат серверного gateway (старый EXE/source, штатная остановка/перезапуск)
описан в [P02_INPROCESS_RELOGIN.md](P02_INPROCESS_RELOGIN.md).
Откат crew grant по конкретному journal без удаления ИС-7 — в
[P02_MS1_CREW.md](P02_MS1_CREW.md): isolated rollback PASS, live rollback NOT_RUN.
Автоматического отката профилей/БД поверх текущих аккаунтов не выполнялось.

**Единственный следующий рекомендуемый шаг:** отдельный настоящий тест
`session_deadline1800 → disconnected → LoginView` с полным capture и собственной
учёткой, без подстановки callbacks/logoff/kill. До него многочасовая работа
и корректность GUI после истечения сессии остаются UNKNOWN.
