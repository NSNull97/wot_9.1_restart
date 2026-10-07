# Интерактивный вход конкретного клиента #717

Этот отдельный профиль показывает оригинальный LoginView и оставляет его
открытым до действий пользователя. Без отдельного one-shot control-файла он
не вводит учётные данные, не вызывает вход и не ставит таймер закрытия.
Оригинальный EXE, Account, LoginDispatcher, ConnectionManager и сетевые
callbacks не заменяются. Состояние Account приходит с локального сервера.

## Файлы и границы

- `sr_interactive.py`: lifecycle измеренных оригинальных GUI-служб, передача
  событий ввода исходному `game`, пассивные ограниченные наблюдения.
- `project_auth.py`: вход только по почте ASCII, максимум254символа; пароль 15..128 Unicode scalar
  values / максимум512UTF8байт; это проверка входа, не новый password registry.
  Почта нормализуется как на сайте: ASCII до обработки, trim только ASCII
  whitespace на краях, lowercase; local-part1..64 dot-atom без краевых/двойных
  точек, домен из2+labels1..63, буквы/цифры/дефис без краевых дефисов,
  последний label содержит букву. SMTPUTF8, quoted local-part и IP-literal
  не поддерживаются. Отображаемый ник не используется для входа.
  Точный пароль сохраняется через исходный `password.strip()` с помощью
  byte-string subclass. Исходный dispatcher затем вызывает native connect.
  Строка ConnectionManager с открытым паролем удаляется из debug logging.
  Расширенная длина на всём native transport проверяется отдельно; unit tests
  не доказывают поддержку всех длин конкретным EXE.
- `project_preferences.py`: исходный DataSection сохраняется как XML только в
  заданной папке `local/`. Перед GUI требуется точное совпадение измеренного
  некорректного native Windows-пути. Python cache getter направляется в свой
  профиль, native `savePreferences` не используется Python-кодом. Настройки
  читаются через выделенную запись `paths.xml` и `sr_preferences.xml`.
- `hangar_bootstrap.py`: неизменённый helper предыдущей принятой карточки;
  используется его init/fini и пассивное чтение объектов. Интерактивное начало
  GUI происходит через оригинальный `gui.shared.personality.start` до входа.

Исходная попытка абсолютного `ResMgr.openSection` завершилась FAIL в UI-only02;
UI-only03 подтвердил resource search path, реальное чтение/сохранение XML,
оригинальный LoginView, отсутствие login-пакетов и штатный выход.

## Установка и откат

Команды запускаются из корня проекта. `prepare` создаёт только проверяемый
пакет в `local/`, `install` изменяет только research-копию. Оба клиента должны
быть закрыты перед install/rollback: операция удерживает настоящий mutex.

```powershell
python tools/interactive_client.py prepare --out local/client-install-001 --public-key local/server/native-public.pem --profile-dir local/client-profile --trace-dir local/client-runtime-001 --endpoint 127.0.0.1:20014 --registration-url http://127.0.0.1:3091/register --disable-legacy-license-dialog
python tools/interactive_client.py install --out local/client-install-001
python tools/interactive_client.py rollback --out local/client-install-001
```

Пакет `local/client-install-001` уже установлен 2026-10-04 и соответствует
своему серверному ключу. Повторная подготовка требует нового пустого output
после отката старой установки; существующий ledger не перезаписывается. `install-plan.json` содержит
все before/installedSHA256, источники, точечные изменения ресурсов и конфиг.
До первой записи создаются проверенные backup и `patch-ledger.json`.
Откат сохраняет postrun и восстанавливает прежние файлы/три клиентских лога.
При постороннем изменении патча откат отказывается его перезаписывать.
Повторный откат проверяет уже восстановленные хеши. Профиль `local/` остаётся.

Изменения ресурсов: свой loopback host/public key, отключённые внешние URL,
RSS/voice/roaming, отсутствие сохранения пароля, регистрация на своём сайте,
пять адресных строк формы входа. Ключи локализации не переименовываются.
Производный MO создаётся в ignored bundle и устанавливается только в
разрешённую research-копию; ресурсные бинарники не добавляются в Git.
Меняется существующий `res/text/LC_MESSAGES/menu.mo` только research-копии с
beforeSHA/backup: исходный i18n разрешает папку `text` целиком, поэтому маленькая
однофайловая папка `res_mods/text` скрывает прочие каталоги gettext (Auth05 FAIL).
Папки локализации и все остальные домены остаются по исходным путям.

## Управляемая native-проверка

Только при явном `prepare --test-control local/.../control.json` профиль ищет
этот файл после готового original LoginView. Обычная установка этого параметра
не содержит. Файл читается один раз, удаляется до отправки, его credentials
не переносятся в install plan, trace или preferences.

Поля: `username` (здесь это почта для входа), `password` (оба или ни одного), `quit_after_seconds` (5..600),
`screenshot_when` (`login`/`hangar`), `submit_via` (`python` по умолчанию/`flash`).
Не хранить реальные данные в документации или примерах командной строки.
`python` вызывает original LoginView.onLogin. `flash` вызывает original
as_setDefaultValuesS и as_doAutoLoginS; исходная Flash-форма читает свои поля,
проверяет пароль и отправляет onLoginS. Это проверяет Flash→Python→native путь,
но не выдаётся за физический ввод с клавиатуры или клик мышью.

По решению владельца для обычной установки доступна отдельная явная опция
`--disable-legacy-license-dialog`. Она отключает старый сервисный диалог,
меняя только `version.xml/showLicense` с3 на0. Содержимое лицензионных файлов
не изменяется, согласие пользователя не записывается, `intUserSettings[54]`
не назначается. Перед подготовкой `version.xml` сверяется с оригиналом; затем
его before/installed hashes, backup и откат проходят через общий ledger.
В `resources.legacy_service_dialog` плана записываются `owner_requested=true`,
`disabled=true`, `user_agreement_recorded=false`. Эта опция работает как с
контрольным файлом, так и без него, не включает auto-login или auto-quit.

Прежняя `--diagnostic-no-license-dialog` сохраняется только для запусков с
явным control-файлом. Без control она отклоняется, даже если одновременно
указана новая опция. Без обеих опций сохраняется исходный диалог. Нативный
обычный запуск без control с новой опцией проверен в Normal21: 95 секунд жизни
процесса, готовая original LoginView, отсутствие отправки credentials и пакетов
своему gateway. Завершение было принудительным действием harness; clean exit
для этого idle-сценария NOT_RUN. Normal20 сохранил отдельный idle FAIL: владелец
вручную вошёл и открыл другие вкладки; это подтверждено им и native trace.
Ошибки подсказок/диагностики того запуска перечислены в итоговом отчёте.
Primitive observer исправлен: строковые ключи, явный truncated при исчерпании
лимита,48KiB ASCII-escaped budget.9unit/5CPython2.7.3 controls PASS. Email22
на новом source подтвердил вход/данные/76.452sready/exit0, но overallFAIL из-за
originalToolTip после начала fini. Это не ошибка observer и не полный GUI PASS.
Намеренное открытие ProfileAwards после исправления NOT_RUN.

Обычный исходный `showLicense=3` сравнивается с серверным
`intUserSettings[54]`; отсутствующее значение означает0. Локальный preferences
не служит сохранённым согласием. Настоящее событие принятия вызывает original
`Account.base.doCmdIntArr(requestID,1600,[54,3])` с типами
`INT16,INT16,ARRAY<INT32>`. Затем original EULADispatcher немедленно продолжает
загрузку GUI, не дожидаясь результата команды. Серверное сохранение этого
действия необходимо проверять отдельно при следующем входе; его нельзя
заменить заранее выставленным54=3. Отключение диалога новой опцией не является
проверкой или имитацией этой цепочки; ручное принятие и его сохранение NOT_RUN.
Статическая цепочка с hashes/offsets:
`gui-agent/eula-contract-01/eula-contract.json` в evidence этой карточки.

Trace: `init`, `preferences_probe`, `preferences_local_save/ready`,
`native_login`, `project_login_submit`, `diagnostic_login_submit`,
`connection_callback`, `native_player`, `native_account_call`,
`native_hangar`, `native_header_call`, `native_profile_call`,
`native_screenshot_requested/return`, `python_exception`, `fini_enter/fini`.
Штатный observer ограничен16MiB; это диагностический предел, не автозакрытие.
Скриншотный marker означает запрос; PNG и реальное содержимое проверяются
отдельно. Нельзя объявлять совместимость по одним marker/готовности observer.

## Локальные проверки исходников

```powershell
python tests/test_project_auth.py
python tests/test_interactive_license_policy.py
python -m unittest tests.test_interactive_primitive -v
$env:SR_TEST_TEMP = (Resolve-Path local).Path
python tests/test_project_preferences.py
& local/toolchains/cpython-2.7.3-x86/python.exe tests/test_project_auth.py
& local/toolchains/cpython-2.7.3-x86/python.exe tests/test_project_preferences.py
```

Evidence этой карточки: `local/evidence/20261004-p02-unified-account/gui-agent/`.
Unit results находятся в `unit-01/results.json`; точный Flash input contract
извлечён без исполнения в `login-swf-contract-05.json`. Native результаты
собирает владелец запуска, а общий итог фиксируется в документации карточки.
