# P02: настоящий Flash-клик «В бой!»

Дата: 2026-10-06, Asia/Yekaterinburg.
Статус кнопки: **PASS_2_NATIVE_FLASH_CLICKS**. Исправление ordinary
`local/client-install-016` дважды пропустило настоящий ручной Flash callback;
сервер принял обе очереди и создал Avatar. Полный ручной цикл поездки:
**FAIL_TWO_DISCONNECTS** — владелец дважды сообщил разрыв после включения
снайперского прицела. Успешный штатный возврат и повторный вход в арену через
него этим прогоном не подтверждены. Следующая узкая карточка разбирает
измеренный native contract переключения прицела.

## Установленные факты

VERIFIED: ordinary normal014 действительно имел enable_map_drive=True и
test_control=None, устанавливал map_drive_client overlay и разрешал штатное
обновление кнопки. В двух ручных журналах — пять battle_capability_denied,
ноль map_drive_client_denied/action/init_error. Первый фильтр mapID/actionName
возвращал прежний hangar-only обработчик до вызова original FightButton.
Исходные журналы, настройки, исходники и владельческий screenshot сохранены
с SHA256 в `E/baseline-01/manifest.json`, где
`E=local/evidence/20261006-manual-battle-button/`.

VERIFIED: сценарий предыдущей ночной карточки вызывал fightClick(0, '')
напрямую. Он проверял original native handler/RPC и поездку, но не форму
аргументов ручного Flash callback. Успешные Ride21/22 остаются scoped
диагностическими доказательствами; ручную кнопку по ним принимать нельзя.

В отдельном пакете015 (module VERSION2) добавлен bounded сбор первых32 вызовов
до фильтра. Готовность/Account/MS1/боекомплект/CAPTCHA и gate не менялись.
Владелец вручную вошёл, нажал кнопку и закрыл игру.

**VERIFIED native callback: `mapID=0.0`, Python type=float;
`actionName=''`, type=str.**

- Файл: `E/telemetry-runtime/native-92192-1791263106470.jsonl`, строка267.
- SHA256: `b14379b8a67cdda779bddff02f40123132be497444911e6f63054d93af041ad9`.
- Событие map_drive_client_click, VERSION2, elapsed33.8576335s.
- Ссылка на record и hash: `E/native-click-01.json`.

Первый gate запрещал float даже при нулевом значении. Поэтому именно этот
подтверждённый callback попадал в предупреждение «Бои пока недоступны».

## Исправление и проверки

VERSION3 преобразует только точный builtin float с числовым значением0.0 в
точный int0 перед прежним gate и original fightClick. Сырой callback остаётся
в ограниченном журнале с normalized_random_map=True. Ненулевые float, bool,
NaN/infinity, посторонние объекты/subclasses и неизвестные действия не получают
разрешения. Проверки состояния игрока и сервера не подменяются.

| Проверка | Результат | Evidence |
|---|---|---|
| Первичная telemetry, host tests | 52+15 PASS | `E/policy-telemetry-tests.log`, `click-contract-tests-01.log` |
| Исправленный ordinary handler + click contract | 54+18 PASS | `E/fixed-unit-tests.json`, два fixed-test logs |
| Действительный CPython2.7.3 x86 | 52 PASS,2 SKIP | `E/python273-tests.json`; host-only decoder checks SKIP |
| Предыдущий acceptance/control сценарий | 100+12 PASS | `E/acceptance-regression.json`, regression logs |
| Установленный ordinary016,34 immutable payloads | PASS hashes | `E/installed016-review.json` |
| Настоящий ручной Flash callback до исправления | PASS observation, кнопка FAIL | `E/native-click-01.json` |
| Настоящие ручные переходы после исправления | PASS: 2 native Flash clicks, 2 server queue accepts, 2 Avatar enters | `E/manual-result-01/result.json` |
| Полный ручной цикл поездки и штатного возврата | FAIL: 2 разрыва сессии, forced failure returns | Тот же receipt; исходные client/server logs сохранены |
| Движение вперёд, повороты и задний ход | VERIFIED native input; OBSERVED владельцем | 72 MAP_DRIVE_INPUT в sessions4/5; прямой отзыв владельца |
| Круиз-контроль | OBSERVED_OWNER_FEEDBACK; exact native contract UNKNOWN | Прямой отзыв владельца; wire-проверка круиза в этой карточке не выполнена |
| Плавность движения/историческая физика | OBSERVED_DEFECT / UNKNOWN, test_lab | Владелец сообщил неказистое движение и остановку/возобновление на подъёме |
| Штатный ручной возврат после исправления прицела | NOT_RUN | Следующая карточка `docs/plans/P02_sniper_camera_protocol.md` |

Unit fixtures проверяют корректность adapter и exact INT32 argument; они не
выдаются за сетевую совместимость. CPython2.7.3 запускал собственный тестовый
модуль; пакет016 также компилировался штатным закреплённым toolchain.

Предварительный prepare015 отказал до изменения клиента, поскольку ещё стоял
normal014 (engine_config отличался от original). Выполнен штатный rollback014,
затем prepare/install015. После ручного измерения — rollback015,
prepare/install016. Ledgers/verified backups/restore receipts сохранены.
Original клиент не изменялся; EXE не патчился.

Telemetry package payload delta к014: map_drive_client.pyc, settings.json и
engine_config.xml. В XML изменился только путь сохранения screenshot;
профиль/родная personality/renderer остались прежними. Никаких автоматических
скриншотов, ввода, автологина или закрытия в этих пакетах не включено.

## Закрытый ручной прогон016

VERIFIED: `E/fixed-runtime/native-7528-1791263513642.jsonl` содержит1474
строки и заканчивается `fini` на строке1474. SHA256:
`8cc0430d315665841f44d1c7459e3d1770892b5a83d95bfc1647b7df6dc63b75`.
Это окончательный закрытый журнал; промежуточный hash живого файла для
приёмки не используется.

| Событие | Первый заход | Второй заход |
|---|---|---|
| map_drive_client_click: raw float0.0, str'', normalized_random_map=True, VERSION3 | Строка204,13.8282209s | Строка725,86.5797542s |
| Original enqueue call/return | Строки215/247 | Строки726/758 |
| native Avatar.onBecomePlayer | Строка279,16.364501s | Строка792,88.7968969s |
| map_drive_client_lifetime видит настоящий Avatar | Строка289,16.8213312s | Строка802,89.8774295s |
| native connection_callback: disconnected | Строка557,74.185827s | Строка1400,302.2463184s |

Промежду разрывами виден новый LOGGED_ON на строке601 и новый Account на
строке633. Поэтому второй вход является повторным логином после разрыва,
а не доказательством успешного штатного маршрута «арена → ангар → арена».
Возвращение обработчика enqueue также не объявляет успех сервера:
`server_success_claimed=false` сохранён в обоих client records.

VERIFIED server evidence:
`local/server/run-20261006T045129-130e11/gateway.stdout.log`, SHA256
`e27a054d6d9c299ac07c7b56883a8bf053f72c961e321222dded1e54a24465bb`.
В sessions4/5 queue command700 с map_request0 принят на строках600/1247.
Первый contract reject каждого захода находится на строках1037/8081:
sequence115/body_bytes13 и sequence1740/body_bytes17 соответственно.
`body_bytes` — размер тела transport message; эти числа сами по себе не
устанавливают название или семантику неизвестного RPC. Последующие
пятибайтовые отказы также не устанавливают отдельный неизвестный метод.
На строках1075/8123 сохранён `RequestWindow`; строки1076/8124 прямо указывают
`reason=worker_or_publication_failure`. Это принудительный recovery path,
не штатный выход владельца в ангар.

VERIFIED: в session4 принято6, в session5 —66 MAP_DRIVE_INPUT. В частности,
задний ход flags2/10 принят на строках4602/4613; направления и повороты
подтверждаются самими входящими командами. Это72 записи, а не72 поездки.
По два generic MAP_DRIVE_UNSUPPORTED в каждой сессии обозначают
vehicle_changeSetting и autoAim; записей MAP_DRIVE_UNSUPPORTED_MOVE в этом
журнале нет. Отсутствие этих записей не проверяет правильную обработку
всех способов включения круиз-контроля. OBSERVED_OWNER_FEEDBACK: владелец
подтвердил движение вперёд, повороты, задний ход и субъективно работающий
круиз; exact cruise contract остаётся UNKNOWN в рамках этой проверки.

OBSERVED_DEFECT: владелец описал неказистое движение и остановку с последующим
возобновлением при подъёме на гору. Причина конкретного рывка ещё UNKNOWN;
нынешний контроллер остаётся test_lab. Плавность и историческая физика
не получают PASS по успешной кнопке или приёму движения.

VERIFIED: одна Python exception сохранена на строке568,78.9207974s:
Minimap._onMapClicked → ChatCommandsController.sendAttentionToCell →
`AttributeError: 'NoneType' object has no attribute 'getControllerByCriteria'`.
Она возникла после первого disconnect. INFERRED: может быть вторичным
эффектом уже потерянных arena services; причинная связь ещё не проверена.
Ошибка не удалялась и не подавлялась.

Закрытые hashes, позиции событий, обе ошибки и счётчики воспроизводит
`E/manual-result-01/review.py`. Он читает только закреплённые журналы и
прежние test receipts, не запускает игру, сервер или тесты заново.
`result.json` отдельно сохраняет PASS кнопки и FAIL всего ручного цикла.

## Команды и откат

Рабочий backend восстановлен отдельной карточкой
`docs/research/P02_SERVICE_RECOVERY.md`. Для его текущего состояния:

```powershell
python -B -X utf8 tools/local_server.py status --config local/server/service.json
```

Обычный запуск владельцем:
`D:\WoT_9.1_Server\WoT_0.9.1_RU_0717_research\WorldOfTanks.exe`.
Войти прежней email-учёткой, МС-1 → «В бой!». Таймера закрытия EXE нет.
Полный повтор с переключением прицела и штатным возвратом относится к
следующей карточке; текущее подтверждение кнопки не обещает завершённый бой.

Повторение чтения закрытых доказательств из корня проекта:

```powershell
python -B -X utf8 local/evidence/20261006-manual-battle-button/manual-result-01/review.py
```

Повтор reader возвращает тот же receipt; при изменении закреплённых входов
или готового результата он отказывает и сохраняет существующий файл.

Повторение host-проверок:

```powershell
python -B -X utf8 -m unittest discover -s tests -p test_map_drive_client.py -v
python -B -X utf8 -m unittest discover -s tests -p test_map_drive_click_contract.py -v
python -B -X utf8 -m unittest discover -s tests -p test_map_drive_acceptance.py -v
python -B -X utf8 -m unittest discover -s tests -p test_map_drive_acceptance_control.py -v
& 'local/toolchains/cpython-2.7.3-x86/python.exe' -B tests/test_map_drive_client.py -v
```

Клиентский откат при закрытом игровом окне:

```powershell
python -B -X utf8 tools/interactive_client.py rollback --out local/client-install-016
```

Это возвращает исследовательские файлы в состояние до установки016,
сохраняя profile/local evidence и postrun logs. Для отката исходников сверить
hash и восстановить map_drive_client.py/test_map_drive_client.py из E/baseline-01;
новый тест click contract можно удалить. Предыдущие install ledgers не
переиспользуются для повторной установки.

Изменены: client_patch/map_drive_client.py, tests/test_map_drive_client.py;
новый tests/test_map_drive_click_contract.py, план и этот отчёт. Завершающий
docs/evidence pass добавил только `E/manual-result-01/review.py` и
`result.json`, обновил этот отчёт; код и runtime в нём не менялись.
STATUS/README обновляет основная карточка по фактическому текущему состоянию.

Приёмка этой узкой карточки: кнопка PASS_2_NATIVE_FLASH_CLICKS; полный
ручной lifecycle FAIL_TWO_DISCONNECTS. Реально запущенные прежние tests:
72 host PASS,52 actual273 PASS+2 SKIP,112 acceptance/control PASS;
повтор implementation tests на завершающем docs-only pass — NOT_RUN.
UNKNOWN: exact native contract переключения прицела, контракт круиза,
причина поведения на подъёме, историческая точность физики. Стрельба, урон
и бой вдвоём NOT_RUN и остаются за рамками карточки.

Единственный следующий проверяемый шаг: установить по реальному wire-пакету
контракт переключения снайперского прицела, затем проверить его ручное
включение и штатный возврат в ангар без разрыва сессии.
