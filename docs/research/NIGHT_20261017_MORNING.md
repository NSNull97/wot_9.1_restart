# Утро 17 октября: Core → rooms → Hold → T26 LAB

Это **операторская инструкция, команды ниже ещё не выполнялись**. **T26 LAB сейчас
BLOCKED: фактическая private auth-проба89 отказала, classic C fixture не проходит
проверку исторического пути. Блок4 пока не выполнять; нужен отдельный исправленный
контекст и успешная повторная probe, старые SHA не ретегать.** Native/UI/
боевые проверки остаются NOT_RUN до реального утреннего теста владельца.
Не склеивать все блоки в один автоскрипт: между режимами нужны настоящий выход
обоих клиентов и проверка результата. Никаких паролей, токенов или содержимого
control-файлов вручную читать/выводить не нужно.

Основание — подготовленные morning61-final контексты и их frozen925/full C
binding. Дополнительные source-only ветки Selection5/CLI/bridge не включают
Training+Hold5 в этом runtime. Если helper отказывает из-за source/binding/ledger
или занятого порта — остановиться и сохранить отказ. Не менять SHA, адрес,
план или старые файлы ради продолжения. Старые partial02 и startup-* не повторять.

Последнее уточнение03:50UTC: отдельный **server-only99** уже подготовлен и
связан с full925. Его actual private auth97/02 получил200 у обоих аккаунтов,
профили/fixtures/Web сохранены,2own stops/Job0. Контекст:
`C:/wot091-night-20261017-01/w/local/stands/night-battle-20261017-03/lab-t26-99`,
binding `ccabbd5252cc9ab5105cfdc7d61ecd0c9dba8d17bfd8e434be52148bccf27e8c`.
**У99 ещё нет собственного native launcher/install API.** Поэтому блок4 со
старым89 остаётся BLOCKED; новый auth PASS не разрешает использовать его
argv с другим stand. Core/rooms/Hold ниже готовы к своей ручной проверке.
Actual95 дополнительно проверил их6 own private HTTP200 и6normal stops;
указанные утренние native run-имена ещё не использованы.

## 0. Переменные, публичные команды и утренний GO

Выполнить в PowerShell после 09:00 Екатеринбурга (04:00 UTC), по уже заданному намерению владельца провести ручной утренний тест.
Launcher78/89 проверяют время и явный флаг; отдельного подтверждающего диалога нет.

```powershell
$Py = 'C:/Users/NSNull/AppData/Local/Python/pythoncore-3.14-64/python.exe'
$A = 'C:/Users/NSNull/AppData/Local/Temp/wot091-night-workspace-kcadgetk'
$M = "$A/morning61"
$H = "$A/morning-launcher78"
$L = "$A/lab-launch89-research"
$N = "$A/net61"
$Tag = 'morning61-final'
$Context78 = '59695cacd7d0503236708f5ea7a4a52baf59e82f85048f646e77202426727e22'
$Context89 = '012526e704a9ac9dc95b3412a8d0f571a300b86a92702786cad13a1079a7a099'

if ([DateTimeOffset]::UtcNow -lt [DateTimeOffset]::Parse('2026-10-17T04:00:00Z')) { throw 'До 04:00 UTC native запрещён' }

function Invoke-Recorded([string[]]$CommandLine) {
    if ($CommandLine.Count -lt 2 -or $CommandLine[0] -ne $Py) { throw 'Не тот Python/argv' }
    $Program = $CommandLine[0]
    $ProgramArguments = @($CommandLine | Select-Object -Skip 1)
    & $Program @ProgramArguments
    if ($LASTEXITCODE -ne 0) { throw "Команда отказала, exit=$LASTEXITCODE. Не продолжать." }
}
function Read-PublicCommandPacket([string]$PacketPath, [string]$ExpectedSha) {
    if (-not (Test-Path -LiteralPath $PacketPath -PathType Leaf)) { throw 'Нет operator packet' }
    if ((Get-Item -LiteralPath $PacketPath).Length -gt 65536) { throw 'Слишком большой packet' }
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $PacketPath).Hash.ToLowerInvariant() -ne $ExpectedSha) { throw 'Operator packet изменился' }
    Get-Content -LiteralPath $PacketPath -Raw | ConvertFrom-Json
}
$Ops = Read-PublicCommandPacket "$M/evidence/morning61-final/operator-commands.json" '86b55d06a72f05c4c541b3fcfbf03df09d74c3427f7da68a2d68aff370e151e9'
```

Разрешены только собственные D-копии:
`D:/WoT_9.1_Server/local/clients/p03f/a` и `/b`.
Все новые планы, profile/trace/control находятся в C-контекстах night-battle-20261017-03.
Оригинальный клиент не трогать. Старый D mixed/run.py здесь не применять.

До первого старта должны быть остановлены **старые собственные** клиенты и
службы из startup62/83/89 и старых стендов. Для них нужен их собственный
receipt/guard stop; новый morning-run не даёт права завершать чужой PID.
Не использовать taskkill по имени. Все Core/rooms/Hold используют одни
UDP20130/20131 и private TCP3481 — одновременно только один режим.

## 1. Core: V7 → V8 один раз

Сначала получить Core command packet, **пока V7 ещё установлен**. После rollback
этот генератор закономерно откажет, потому что проверяет исходный V7 ledger.
Возвращается только публичный argv, никаких credentials.

```powershell
Invoke-Recorded $Ops.'core-loss4'.check
$CorePacketText = @(Invoke-Recorded $Ops.'core-loss4'.client_commands)
$CoreClient = ($CorePacketText -join "`n") | ConvertFrom-Json

# Каждая группа целиком: rollback ОБОИХ, prepare ОБОИХ, затем install ОБОИХ.
foreach ($CommandLine in $CoreClient.'rollback-current') { Invoke-Recorded $CommandLine }
foreach ($CommandLine in $CoreClient.prepare) { Invoke-Recorded $CommandLine }
foreach ($CommandLine in $CoreClient.install) { Invoke-Recorded $CommandLine }
Invoke-Recorded $Ops.'core-loss4'.check_clients
```

Не делать prepareA→installA→prepareB: второй prepare справедливо откажет из-за
уже установленного V8. Планы schema1, controller VERSION8; это разные версии,
не надо чинить settings.version или переписывать ledger.

Далее служба и настоящий запуск A. Выполнять команды по одной, проверяя exit0:

```powershell
Invoke-Recorded $Ops.'core-loss4'.services
& $Py -B -X utf8 "$H/run.py" preflight --context-sha256 $Context78 --mode core-loss4 --slot a
if ($LASTEXITCODE) { throw 'Core A preflight отказал' }
& $Py -B -X utf8 "$H/run.py" launch --context-sha256 $Context78 --mode core-loss4 --slot a --execute-client-action
if ($LASTEXITCODE) { throw 'Core A launch отказал' }
```

Дождаться **настоящего ангара A**. Перед B helper проверяет два последних
hangar-ready события именно текущего A PID, его создание, image и mutex.
Никакой таймер не заменяет эту проверку.

```powershell
& $Py -B -X utf8 "$H/run.py" preflight --context-sha256 $Context78 --mode core-loss4 --slot b
if ($LASTEXITCODE) { throw 'Core B preflight отказал — дождаться настоящего A ангара' }
& $Py -B -X utf8 "$H/run.py" launch --context-sha256 $Context78 --mode core-loss4 --slot b --execute-client-action
if ($LASTEXITCODE) { throw 'Core B launch отказал' }
```

Теперь владелец вручную проверяет бой/управление/результаты. Запуск не означает
PASS боевой карточки. Не выдавать автоматический auth/UDP smoke за UI или бой.

Завершить оба клиента штатным Exit. Если собственный клиент остался жив —
следующие команды привязаны к его receipt/PID/creation/image. Они также могут
записать подтверждённое отсутствие уже вышедшего собственного клиента:

```powershell
& $Py -B -X utf8 "$H/run.py" stop --context-sha256 $Context78 --mode core-loss4 --slot b --execute-client-action
if ($LASTEXITCODE) { throw 'Проверить own B stop' }
& $Py -B -X utf8 "$H/run.py" stop --context-sha256 $Context78 --mode core-loss4 --slot a --execute-client-action
if ($LASTEXITCODE) { throw 'Проверить own A stop' }
Invoke-Recorded $Ops.'core-loss4'.stop_gateway
Invoke-Recorded $Ops.'core-loss4'.stop_bridge
```

Каждый stop receipt создаётся один раз. Если он уже есть — проверить его, не
повторять команду вслепую и не удалять marker/receipt ради нового запуска.

## 2. Rooms: тот же установленный Core V8

Повторного rollback/prepare/install нет. Core и rooms используют один точный
`unified-01/client-v8-morning61-final` и одинаковые source/PYC/settings.
Не повторять rooms client-commands после Core установки: генератор ожидает V7.

```powershell
Invoke-Recorded $Ops.'rooms-loss4'.check
Invoke-Recorded $Ops.'rooms-loss4'.check_clients
Invoke-Recorded $Ops.'rooms-loss4'.services
& $Py -B -X utf8 "$H/run.py" preflight --context-sha256 $Context78 --mode rooms-loss4 --slot a
if ($LASTEXITCODE) { throw 'Rooms A preflight отказал' }
& $Py -B -X utf8 "$H/run.py" launch --context-sha256 $Context78 --mode rooms-loss4 --slot a --execute-client-action
if ($LASTEXITCODE) { throw 'Rooms A launch отказал' }
# После настоящего ангара A:
& $Py -B -X utf8 "$H/run.py" preflight --context-sha256 $Context78 --mode rooms-loss4 --slot b
if ($LASTEXITCODE) { throw 'Rooms B preflight отказал' }
& $Py -B -X utf8 "$H/run.py" launch --context-sha256 $Context78 --mode rooms-loss4 --slot b --execute-client-action
if ($LASTEXITCODE) { throw 'Rooms B launch отказал' }
```

После ручной проверки комнат — штатный Exit обоих, затем при необходимости
exact own stops и служебные stops:

```powershell
& $Py -B -X utf8 "$H/run.py" stop --context-sha256 $Context78 --mode rooms-loss4 --slot b --execute-client-action
if ($LASTEXITCODE) { throw 'Проверить own B stop' }
& $Py -B -X utf8 "$H/run.py" stop --context-sha256 $Context78 --mode rooms-loss4 --slot a --execute-client-action
if ($LASTEXITCODE) { throw 'Проверить own A stop' }
Invoke-Recorded $Ops.'rooms-loss4'.stop_gateway
Invoke-Recorded $Ops.'rooms-loss4'.stop_bridge
```

## 3. Hold5: отдельная БД, установленный Core overlay переиспользуется

Это обычный owned бой с ранним Account-return/сохранённым резервом до финала.
**Native Training+Hold5 остаётся закрытым.** Снова ничего не устанавливать.
Сгенерированный check_clients уже содержит `--reuse-core-tag morning61-final`.

```powershell
Invoke-Recorded $Ops.hold5.check
Invoke-Recorded $Ops.hold5.check_clients
Invoke-Recorded $Ops.hold5.services
& $Py -B -X utf8 "$H/run.py" preflight --context-sha256 $Context78 --mode hold5 --slot a
if ($LASTEXITCODE) { throw 'Hold A preflight отказал' }
& $Py -B -X utf8 "$H/run.py" launch --context-sha256 $Context78 --mode hold5 --slot a --execute-client-action
if ($LASTEXITCODE) { throw 'Hold A launch отказал' }
# После настоящего ангара A:
& $Py -B -X utf8 "$H/run.py" preflight --context-sha256 $Context78 --mode hold5 --slot b
if ($LASTEXITCODE) { throw 'Hold B preflight отказал' }
& $Py -B -X utf8 "$H/run.py" launch --context-sha256 $Context78 --mode hold5 --slot b --execute-client-action
if ($LASTEXITCODE) { throw 'Hold B launch отказал' }
```

Ручной ранний выход и проверка замка/финального снятия резерва — отдельное UI
наблюдение. Двух игроков и немедленный Forfeit не считать доказательством
продолжающегося N>2 боя; у такой проверки собственная software composition.

После Exit обоих:

```powershell
& $Py -B -X utf8 "$H/run.py" stop --context-sha256 $Context78 --mode hold5 --slot b --execute-client-action
if ($LASTEXITCODE) { throw 'Проверить own B stop' }
& $Py -B -X utf8 "$H/run.py" stop --context-sha256 $Context78 --mode hold5 --slot a --execute-client-action
if ($LASTEXITCODE) { throw 'Проверить own A stop' }
Invoke-Recorded $Ops.hold5.stop_gateway
Invoke-Recorded $Ops.hold5.stop_bridge
```

## 4. T26 LAB: отдельный overlay и launcher89

**BLOCKED на текущем binding89. Следующие argv сохранены для review, не для
исполнения.** Root действительно запустил HTTP probe89: первыйA login отказал;
обе собственные службы остановлены, Job завершился active0. HTTP status/body
старый probe не сохранял — точный status UNKNOWN. Независимый вызов настоящего
readonly validateAmmoFixture на C A4 дал `Exact existing crew base path required`:
в r3 manifest сохранён исторический D base_fixture, валидатор требует текущий C.
Нельзя чинить это заменой SHA или правкой старого manifest/binding. После
versioned remedy нужны новые проверенные producer/context/binding/launcher pins;
показанные ниже current89 команды автоматически не становятся новой приёмкой.

LAB: Login20142/Base20143, private identity3493. Это временный server-selected
T26, **не owned grant/admission**. A/B имеют те же nativeID1/2; старые профили
версий4/1 не надо ретегать. Совпадение account ID не доказывает пароль; отдельная
Root HTTP-проба89 ведётся своей записью и не заменяет native login/UI.

Получить LAB packet, затем rollback текущего Core V8 ОБОИХ и создать LAB overlay.
LAB packet использует latest-ledger rollback, не старый V7 runner:

```powershell
throw 'LAB BLOCKED: сначала versioned binding/context + фактический auth PASS; current89 не выполнять'
Invoke-Recorded $Ops.lab.check
$LabPacketText = @(Invoke-Recorded $Ops.lab.client_commands)
$LabClient = ($LabPacketText -join "`n") | ConvertFrom-Json
foreach ($CommandLine in $LabClient.'rollback-current') { Invoke-Recorded $CommandLine }
foreach ($CommandLine in $LabClient.prepare) { Invoke-Recorded $CommandLine }
foreach ($CommandLine in $LabClient.install) { Invoke-Recorded $CommandLine }
Invoke-Recorded $Ops.lab.check_clients
Invoke-Recorded $Ops.lab.services
& $Py -B -X utf8 "$L/launcher89.py" preflight --context-sha256 $Context89 --slot a
if ($LASTEXITCODE) { throw 'LAB A preflight отказал' }
& $Py -B -X utf8 "$L/launcher89.py" launch --context-sha256 $Context89 --slot a --execute-client-action
if ($LASTEXITCODE) { throw 'LAB A launch отказал' }
# После настоящего ангара A:
& $Py -B -X utf8 "$L/launcher89.py" preflight --context-sha256 $Context89 --slot b
if ($LASTEXITCODE) { throw 'LAB B preflight отказал' }
& $Py -B -X utf8 "$L/launcher89.py" launch --context-sha256 $Context89 --slot b --execute-client-action
if ($LASTEXITCODE) { throw 'LAB B launch отказал' }
```

89 проверяет оба установленных LAB overlay, но не требует выключать A ради
старта B: для A проверяются оба отсутствующих mutex, для B — exact own живой A,
два его свежих hangar-события и отсутствующий B. Старый M61 checked() целиком
перед B не вызывать: он закономерно требует оба клиента выключенными.

Проверить T26 вручную; результаты этой qualification пока NOT_RUN. Затем Exit:

```powershell
& $Py -B -X utf8 "$L/launcher89.py" stop --context-sha256 $Context89 --slot b --execute-client-action
if ($LASTEXITCODE) { throw 'Проверить LAB own B stop' }
& $Py -B -X utf8 "$L/launcher89.py" stop --context-sha256 $Context89 --slot a --execute-client-action
if ($LASTEXITCODE) { throw 'Проверить LAB own A stop' }
Invoke-Recorded $Ops.lab.stop_gateway
Invoke-Recorded $Ops.lab.stop_bridge
```

В ресурсах7 профилей: MS1, IS7, T26, T34, T34-85, WT128 и FV183. В M61 wrapper
только5 дополнительных qualification choices;89 закрыт только на T26. Нельзя
подставлять `--kind` в89 или объявлять все7 проверенными. WT/FV требуют отдельного
явного curated-lab-v2 service run и своей квалификации; их owned admissionfalse.

После LAB, если нужен возврат overlay, выполнить latest-ledger rollback ОБОИХ
через уже полученные `$LabClient.'rollback-current'`, при выключенных клиентах.
Это снятие текущего LAB V8, а не автоматическая переустановка прежнего V7.
Не копировать клиентские файлы из соседних стендов и не править ledger вручную.

## 5. NET61: исторический own-host UDP smoke69, не повторять

`own-lan-c61-01` УЖЕ ИСПОЛЬЗОВАН фактическим69. Старые services/probe/stop argv
из operator JSON имеют статус **HISTORICAL_ALREADY_EXECUTED_DO_NOT_REPEAT**.
Не запускать этот run утром второй раз и не удалять receipts. Допустимы только
пассивный check текущего source binding и чтение публичного результата:

```powershell
$NetOps = Read-PublicCommandPacket "$N/evidence/net61-final/operator-commands.json" 'e1b2776a08f293319fd61cdff4152d23366ee83dc9d6f1f899a8e42bee3a5716'
Invoke-Recorded $NetOps.check
$NetReceipt = 'C:/wot091-night-20261017-01/w/local/stands/net02-loss-ownhost-c61-01/runs/own-lan-c61-01/own-lan-loss4-smoke34.json'
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $NetReceipt).Hash.ToLowerInvariant() -ne '3ab9cdf5b12410ed7639a22eeb6eb11c5df9d850ea64298cb46bc25709478b45') { throw 'Исторический NET69 receipt изменился' }
$NetResult = Get-Content -LiteralPath $NetReceipt -Raw | ConvertFrom-Json
$NetResult | Select-Object status, native, two_pc, active_reservations, new_grants
```

Root69 aggregate: A/net-ownhost-run69/evidence01/result.json; actual scope —
собственный192.168.1.101/32/interface7 Login→RunOpen4→первыйBase и два own stops,
Job0. UDP20240/20241, private3492. Это НЕ native Account/Avatar/бой и НЕ два ПК.
Новый повторный сетевой run требует нового reviewed command packet/свежего run,
а не ручной замены имени в старом argv. Windows network profile/firewall/IP/
interface/allowlist/ports не менять. Public firewall/Internet/NAT/WAN/другой ПК
остаются NOT_RUN. Старый LAN16 и его DB/pins не ретегать как C61 proof.

## Что считать результатом и как откатываться

Каждый launcher пишет own receipt и отказывается повторять один слот/режим/run.
Не удалять attempt/control/receipt ради повторения. На отказе сохранить полный
путь evidence, остановить только собственные процессы их guard-командами и
разбирать причину. Source-independent own stop не требует актуального HEAD,
но требует того же PID/creation/image/receipt. Никаких kill по имени.

Установки/реальный native/Core/rooms/Hold/T26/два ПК по этой инструкции — NOT_RUN
до наблюдения владельца.12 guards89 и9 guards78 — software/source проверки,
не совместимость UI. Scoped independent source review78/89 завершён без нового
blocker;89 peer-review receipt supersedes его более раннюю README строку NOT_RUN.
Root89 review: A/root-lab89-review.json, SHA
8d34e02044734ac61bdee7d68f13660e6461d9fc31e2b47e51d69a9c2e57cdc3.
HTTP-пробу89 Root запустил отдельной сессией, и она завершилась FAIL на первомA
request с успешной own-cleanup/Job0. Здесь её **не повторять**. Нативного
разрешения или положительной LAB-приёмки это не добавляет.

Откат overlay — только текущий latest-ledger rollback для обоих выключенных own
клиентов. Службы — exact own receipt stop. БД/evidence сохраняются; не восстанавливать
старую БД для возврата потраченных боеприпасов и не запускать grant/reseed.
Восстановление V7, новый service run после частичного отказа или расширение89
на другой kind — отдельное reviewed действие, не правка этой инструкции на ходу.

Единственный первый реальный шаг утром по намерению владельца после04UTC: Core public packet
до rollbackV7, затем rollbackBOTH→prepareBOTH→installBOTH и actual A launch.
