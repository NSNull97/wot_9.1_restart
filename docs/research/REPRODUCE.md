# Повторный запуск P00–P01

Все команды — PowerShell из `D:\WoT_9.1_Server`. Новый run directory обязателен:
Python-утилиты не перезаписывают существующие JSON evidence. Клиентские копии
и local config остаются локальными и исключены из Git.

## Предусловия и версии

Установлены Python 3.14.3, Git 2.53.0.windows.1, .NET SDK 9.0.315/runtime 9.0.17.
OpenSSL для одноразового ключа: `C:\Program Files\Git\usr\bin\openssl.exe`.
Версии и бинарные хеши — `tool-environment.json` и `dependencies.json` run 20261002.
`tools/bootstrap_research.ps1` скачивает только открытые инструментальные
зависимости в local, проверяет hash/revision и не стартует клиент.
Полная установка этого script на второй чистой машине — NOT_RUN; фактически
выполненная проверка существующей среды:

```powershell
Set-Location D:\WoT_9.1_Server
./tools/bootstrap_research.ps1 -CheckOnly
```

На новой разрешённой машине сначала заполнить `config/project.local.json`
по example (не перезаписывать существующий), затем:

```powershell
./tools/bootstrap_research.ps1
```

Если текущий rustup-init URL выдаёт другой SHA-256, script откажется запускать
его. Это ожидаемая защита pinning; нужен сохранённый проверенный installer
либо отдельное обновление pin. Установка .NET/Git/Python этим script не делается.

## Ресурсы и тесты

```powershell
Set-Location D:\WoT_9.1_Server
$taskRun = 'local/evidence/recheck-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
New-Item -ItemType Directory -Path $taskRun | Out-Null
python -X utf8 -m unittest discover -s tests -v
python -X utf8 tools/client_audit.py manifest --out "$taskRun/baseline"
python -X utf8 tools/client_audit.py metadata --out "$taskRun/static"
python -X utf8 tools/static_extract.py --out "$taskRun/decoded"
python -X utf8 tools/geometry_spike.py --out "$taskRun/geometry"
python -X utf8 tools/research_summary.py --out "$taskRun/summary"
```

На закреплённых данных ожидается 20/20 tests, 3469 files/copy, 2255 pyc,
62 pkg, 70 decoded files, hull 301 vertices / 198 triangles / 16 groups.
Unit boundary fixtures синтетические и помечены отдельно от пяти тестов
на настоящих клиентских ресурсах. Никакой сетевой приёмки они не закрывают.

## wg-toolkit и его измеренное ограничение

```powershell
. ./tools/rust_env.ps1
cargo build --locked --manifest-path local/vendor/wg-toolkit-rs/Cargo.toml -p wg-toolkit-cli --no-default-features --features wot
cargo build --locked --manifest-path tools/wg_probe/Cargo.toml
& local/vendor/wg-toolkit-rs/target/debug/wgtk.exe pxml -f WoT_0.9.1_RU_0717_research/res/scripts/item_defs/vehicles/ussr/t-34-85.xml -x
& local/vendor/wg-toolkit-rs/target/debug/wgtk.exe pxml -f WoT_0.9.1_RU_0717_research/res/scripts/entity_defs/account.def -x
& local/vendor/wg-toolkit-rs/target/debug/p01-wg-probe.exe geometry "$taskRun/geometry/hull.primitives"
```

Последняя команда **должна сейчас завершиться ненулевым кодом** и сообщить
`section_bytes=9700 consumed_bytes=7292 trailing_bytes=2408`. Это воспроизводимый
FAIL совместимости toolkit с наблюдаемым legacy layout. Исходники toolkit
не исправлены. Не собирать EXE одновременно с его запуском: Windows блокирует файл.
Upstream lockfile закреплён отдельно в config; `bootstrap` проверяет/устанавливает его.

## Headless Jolt

```powershell
$env:DOTNET_CLI_HOME = 'D:\WoT_9.1_Server\local\dotnet-home'
$env:NUGET_PACKAGES = 'D:\WoT_9.1_Server\local\nuget-packages'
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
$env:DOTNET_GENERATE_ASPNET_CERTIFICATE = 'false'
dotnet restore tools/physics_spike/PhysicsSpike.csproj --locked-mode
dotnet run --project tools/physics_spike/PhysicsSpike.csproj -c Release --no-restore
```

Ожидается JSON `status=PASS`, 300 steps, contact>0, finalY около 0.486 на
зафиксированной среде. Тест не обещает побитовой идентичности на другой машине
и не проверяет исторический vehicle controller. Production .NET 10 — NOT_RUN.

## Реальный клиент и локальный endpoint

Выполнять только после завершения сборки. Утилита использует research config
и собственный diagnostic personality; original никогда не запускается.
Отдельный toolkit endpoint привязан к `127.0.0.1:20015`, ограниченный capture
к `127.0.0.1:20014`. По умолчанию 45 секунд (`--timeout` 5–60),
64 datagrams, 4096 bytes/datagram. Профиль legacy091 дополнительно ограничен
1024 байтами, одним peer и 60 секундами.
Чужой процесс/занятый порт не завершаются и не переиспользуются.
При существующем `wot_client_mutex` runner откажет до любых client patches.
Для успешного запуска нужен свободный mutex; играющая копия не закрывается автоматически.

Собственный `.pyc` компилируется официальным CPython 2.7.3, распакованным
локально без запуска MSI installer. На текущей машине он уже подготовлен.
При первом развёртывании (extractor откажется затирать непустой target):

```powershell
New-Item -ItemType Directory -Path local/downloads -Force | Out-Null
if (-not (Test-Path -LiteralPath local/downloads/python-2.7.3.msi)) {
    Invoke-WebRequest -Uri https://www.python.org/ftp/python/2.7.3/python-2.7.3.msi -OutFile local/downloads/python-2.7.3.msi
}
python -X utf8 tools/extract_python273.py --msi local/downloads/python-2.7.3.msi --out local/toolchains/cpython-2.7.3-x86
```

Extractor проверяет закреплённый SHA-256 MSI. Команды после resource/baseline
секции и завершения cargo build:

```powershell
python -X utf8 tools/client_probe.py run --out "$taskRun/native" --backend local/vendor/wg-toolkit-rs/target/debug/p01-wg-probe.exe --backend-profile legacy091
python -X utf8 tools/verify_native_capture.py --run "$taskRun/native"
```

Ожидаем **PASS узкого native rejection**: активный Python 2.7.3, marker,
request 273 B, reply 45 B, callback `LOGIN_REJECTED_SERVER_NOT_READY`, exit 0,
timeout false, восстановление. Полный вход/arena — NOT_RUN. Успешный
`BOUND` backend и exit 0 сами по себе не достаточны: проверяется точный callback.
Backend останавливается parent runner после опыта, отдельно от client exit.
Не запускать старый replay batch или штатный login в качестве обхода:
они не входят в этот локальный диагностический сценарий.

Контроль причины раннего выхода (только если mutex сейчас отсутствует):

```powershell
python -X utf8 tools/client_probe.py run --out "$taskRun/mutex-control" --source-only --mutex-control --debug
```

PASS здесь означает instance_guard_control: занятый собственным тестом mutex
привёл к раннему exit 0 без нового Python log/пакетов. Это не network PASS.

Проверки Rust и декодирование уже сохранённого настоящего corpus:

```powershell
. ./tools/rust_env.ps1
cargo test --locked --offline --manifest-path tools/wg_probe/Cargo.toml
& local/vendor/wg-toolkit-rs/target/debug/p01-wg-probe.exe legacy091-decode "$taskRun/native/test-private.pem" "$taskRun/native/packet-000-client_to_server.bin"
```

Для статического PE-анализа дополнительно нужны установленные pefile 2024.8.26
и capstone 5.0.9 (metadata в evidence). Команда не запускает клиент:

```powershell
python -X utf8 tools/exe_startup_probe.py --out "$taskRun/pe" --va 0x5a4db0 --va 0x5a4f18 --va 0x60da40
```

При прерывании Python до его finally, сначала убедиться, что завершены
именно PID данного run из capture/debug evidence, затем восстановить:

```powershell
python -X utf8 tools/client_probe.py restore --out "$taskRun/native"
```

Повторный restore уже восстановленного run откажет. Backup проверяется по
SHA-256; текущие затрагиваемые файлы сначала сохраняются в postrun. Для ручного
возврата есть `patch-ledger.json` с исходными путями/хешами и каталог `backup/`.

После диагностического запуска обязательно:

```powershell
python -X utf8 tools/client_audit.py manifest --out "$taskRun/after"
Get-FileHash "$taskRun/baseline/original-content-manifest.json","$taskRun/baseline/research-content-manifest.json","$taskRun/after/original-content-manifest.json","$taskRun/after/research-content-manifest.json"
git check-ignore -v config/project.local.json WoT_0.9.1_RU_0717_original/WorldOfTanks.exe WoT_0.9.1_RU_0717_research/WorldOfTanks.exe local/evidence/test.pem
```

Все четыре manifest hashes должны совпасть. В обоих завершённых runs это
`74c37c18e9ac7e30196c134076dacf6f2a8bf3897f7def73905d09feb3647797`.

## Откат изменений проекта

Client patches уже полностью откатились. Исходный документационный пакет
сохранён в `local/baseline/project-package/`, его проверка в
`local/baseline/package-check.json`. Для отката проектных документов
восстановить конкретные изменённые README/STATUS/.gitignore из этой копии,
сначала сохранив текущие версии. Новые инструменты/отчёты и local toolchains
можно убрать адресно после сохранения нужного evidence; массовую очистку не
выполнять. Пока клиенты лежат внутри корня, сохранять правила их исключения
из Git, даже если откатывается остальная часть `.gitignore`.

Нет commits, remote, миграций БД, системного PATH patch или публичного
серверного сервиса, которые нужно откатывать. Любая повторная подготовка
проверяет существующие каталоги и не затирает другой vendor revision молча.
Продолжение добавило local CPython compiler и новые own tools/profile. Клиентский
EXE не патчился, instance guard не обходился. Полный отчёт продолжения —
[P01_BOOTSTRAP_AND_NATIVE_LOGIN](P01_BOOTSTRAP_AND_NATIVE_LOGIN.md).

## P02: только LoginSuccess → первый BaseApp request

По отдельному разрешению выполнена узкая карточка redirect. Полный gate P02
и сессия NOT_RUN. Существующая среда/компилятор используются без переустановки;
для verifier нужен уже установленный `cryptography==48.0.0`.

```powershell
. ./tools/rust_env.ps1
cargo build --locked --offline --manifest-path tools/wg_probe/Cargo.toml
cargo test --locked --offline --manifest-path tools/wg_probe/Cargo.toml
python -X utf8 -m unittest discover -s tests -v
$taskRun = 'local/evidence/p02-redirect-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
python -X utf8 tools/client_audit.py manifest --out "$taskRun/baseline"
python -X utf8 tools/client_probe.py run --out "$taskRun/native" --backend local/vendor/wg-toolkit-rs/target/debug/p01-wg-probe.exe --backend-profile legacy091-redirect
python -X utf8 tools/verify_redirect_capture.py --run "$taskRun/native"
python -X utf8 tools/check_redirect_probe.py --run "$taskRun/native" --out "$taskRun/negative"
python -X utf8 tools/client_audit.py manifest --out "$taskRun/after"
Get-FileHash "$taskRun/baseline/original-content-manifest.json","$taskRun/baseline/research-content-manifest.json","$taskRun/after/original-content-manifest.json","$taskRun/after/research-content-manifest.json"
```

Ожидаемый PASS: реальный request 273 B → encrypted success 28 B → BaseApp
request 21 B с тем же токеном. `base_endpoint_received` проверяет только приход
пакета; `redirect-verification.json` отдельно проверяет содержимое, хеши,
request ID и токен. Callback `LOGGED_ON` не ожидается и не подделывается;
BaseApp endpoint пока не отвечает. Ports 20014–20016 должны быть свободны.
Native run и negative checks запускать последовательно.

Если процесс прерван до finally, завершить именно его child PID и выполнить
`python -X utf8 tools/client_probe.py restore --out "$taskRun/native"`.
В завершённых runs откат уже сделан, повторный restore откажет.
Проектный snapshot до этой карточки:
`local/evidence/20261002-p02-login-redirect/project-before.zip`; отдельный
config backup рядом. Восстанавливать адресно с учётом `changed-files.json`,
не затирая последующие изменения. Полные команды и ограничения —
[P02_LOGIN_REDIRECT](P02_LOGIN_REDIRECT.md).

## P02: BaseApp reply → первый encrypted frame

Следующая отдельно разрешённая карточка подтверждена 2026-10-04.
Полный gate P02 NOT_RUN; Account и устойчивого канала ещё нет.
Сборка и baseline — как выше; новый профиль и verifier:

```powershell
$taskRun = 'local/evidence/p02-baseapp-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
python -X utf8 tools/client_audit.py manifest --out "$taskRun/baseline"
python -X utf8 tools/client_probe.py run --out "$taskRun/native" --backend local/vendor/wg-toolkit-rs/target/debug/p01-wg-probe.exe --backend-profile legacy091-baseapp
python -X utf8 tools/verify_baseapp_capture.py --run "$taskRun/native"
python -X utf8 tools/check_baseapp_probe.py --run "$taskRun/native" --out "$taskRun/negative"
python -X utf8 tools/client_audit.py manifest --out "$taskRun/after"
Get-FileHash "$taskRun/baseline/original-content-manifest.json","$taskRun/baseline/research-content-manifest.json","$taskRun/after/original-content-manifest.json","$taskRun/after/research-content-manifest.json"
```

Порты 20014–20017 должны быть свободны, другая игровая копия закрыта.
Ожидается BaseApp reply 24 B, первый encrypted client frame 24 B и реальный
LOGGED_ON; это не вход в ангар. Последующие сообщения пока не dispatch-ятся.
PID для аварийного восстановления сохраняются заранее в `processes.json`.
После остановки именно этих процессов команда отката прежняя:
`python -X utf8 tools/client_probe.py restore --out "$taskRun/native"`.

Подробные команды сборки, regression, static probe, hashes и границы —
[P02_BASEAPP_REPLY](P02_BASEAPP_REPLY.md). Проектный snapshot до этой карточки
лежит в `local/evidence/20261004-p02-baseapp-reply/project-before.zip`;
параллельные `web/` и `local/web/` к этому откату не относятся.

## P02: первый ACK и keepalive

Сборка/тесты — как выше; backend прежний, новые profiles выбраны явно.
Минимальный positive run (другая копия игры закрыта):

```powershell
$taskRun = 'local/evidence/p02-ack-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
python -X utf8 tools/client_probe.py run --out "$taskRun/ack" --backend local/vendor/wg-toolkit-rs/target/debug/p01-wg-probe.exe --backend-profile legacy091-channel-ack --probe-seconds 25
python -X utf8 tools/verify_channel_capture.py --run "$taskRun/ack" --expect ack
```

Сопоставимые controls: профиль `legacy091-baseapp` с `--probe-seconds 20`
и verifier `--expect none`; профиль `legacy091-channel-stale` с тем же timer
и verifier `--expect stale`. Для каждого нужен собственный каталог.
Полные команды, 34 новых checks, 75 regression cases, исходный capture FAIL
и подтверждённый откат — [P02_CHANNEL_ACK](P02_CHANNEL_ACK.md).
Общий надёжный канал/Account/arena этим не проверены.

## P02: первый reliable packet сервера

```powershell
$taskRun = 'local/evidence/p02-server-seq-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
python -X utf8 tools/client_probe.py run --out "$taskRun/native" --backend local/vendor/wg-toolkit-rs/target/debug/p01-wg-probe.exe --backend-profile legacy091-server-reliable --probe-seconds 25
python -X utf8 tools/verify_server_reliable.py --run "$taskRun/native"
python -X utf8 tools/check_server_reliable.py --run "$taskRun/native" --out "$taskRun/checks"
```

Сборка/13 Rust/20 Python tests, native control, regression и сверка отката —
в [P02_SERVER_RELIABLE](P02_SERVER_RELIABLE.md). Принимается только seq0 и
один намеренный duplicate; это не общий retry/window implementation.

## P02: локальный gateway/session

Полная последовательность gap → persistent gateway → десять native cycles →
отрицательные случаи → manifests находится в [P02_LAB_GATEWAY](P02_LAB_GATEWAY.md).
Собирать теми же offline командами; 19 Rust / 20 Python tests.

Для повторения на сохранённом проверенном corpus:

```powershell
$taskRun = 'local/evidence/p02-gateway-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
python -X utf8 tools/gateway_suite.py --source local/evidence/20261004-p02-session-gateway/gap-01 --out "$taskRun/suite" --cases wrong-password,normal,drop-server-first,drop-client-ack,duplicate-client-first,normal,normal,normal,normal,normal,normal,wrong-password,blackhole,normal
python -X utf8 tools/verify_gateway_capture.py --suite "$taskRun/suite"
python -X utf8 tools/check_gateway_probe.py --source "$taskRun/suite/02-normal" --out "$taskRun/controls"
```

Suite запускает один собственный gateway, сохраняет PID/key/config в ignored
local, выполняет клиентов последовательно и завершает только свой процесс.
Нативный Account/игровой UI/арена здесь NOT_RUN.

## P02: native Account wire creation

Полные команды пяти creation runs, absence control, source/hash evidence,
независимый verifier и откат — [P02_NATIVE_ACCOUNT](P02_NATIVE_ACCOUNT.md).
Быстрый повтор с текущей offline сборкой:

```powershell
$taskRun = 'local/evidence/p02-account-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
python -X utf8 tools/gateway_suite.py --source local/evidence/20261004-p02-session-gateway/acceptance/02-normal --out "$taskRun/native" --account-probe --cases normal
python -X utf8 tools/verify_account_capture.py --run "$taskRun/native/01-normal"
```

Verifier разделяет `native_creation=PASS` и `original_python_lifecycle=FAIL`.
Выход0 этого узкого verifier не означает успешный ангар или полный Account.
Сейчас воспроизводится Settings.userPrefs bootstrap error; ошибки не скрываются.

## P02: минимальный Account lifecycle и initial sync

Предыдущий профиль `legacy091-account` сохраняет старый wire-only эксперимент.
Для подтверждённого минимального lifecycle используется отдельный
`legacy091-account-ready`, выбранный двумя явными флагами suite.
Полные команды, static sources, 26 Rust/20 Python tests, 311 corpus и33 own-UDP
controls: [P02_ACCOUNT_READY](P02_ACCOUNT_READY.md).

```powershell
. ./tools/rust_env.ps1
cargo build --locked --offline --manifest-path tools/wg_probe/Cargo.toml
$taskRun = 'local/evidence/p02-account-ready-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
python -X utf8 tools/gateway_suite.py --source local/evidence/20261004-p02-account/native-final/01-normal --out "$taskRun/native" --account-probe --account-bootstrap --cases normal
python -X utf8 tools/verify_account_ready.py --suite "$taskRun/native"
```

Для полной повторной серии: `--cases normal,normal,drop-server-sync,duplicate-client-sync,drop-server-first,duplicate-client-first,wrong-password,normal`.
Требуются свободные mutex/UDP20014–20017 и отсутствие research/p01_profile до
запуска. Original только читается; research patch/profile откатываются в finally.
Первоначальные before hashes и backups обязательны и создаются runner.
При аварии — проверка/остановка только owned процессов из processes.json и
`python -X utf8 tools/client_probe.py restore --out "$taskRun/native/01-normal"`
для ещё не восстановленного конкретного run. Затем полный manifest comparison
обеих копий, как в основном отчёте.

PASS означает original Account lifecycle + три initial RPC + checksum одного
stream в диагностическом bootstrap. Обычный ангар, native preferences, web→game
account identity и арена — NOT_RUN; сайт/игра по требованию владельца должны
использовать единую учётку после отдельной реализации и сквозной проверки.
