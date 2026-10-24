# Текущие ворота: CREW-ANY — native gate 2026-10-24

Ветка `codex/crew-any`, база карточки — `4b46f7e`. План карточки — [CREW_ANY](plans/CREW_ANY.md). Этот запуск проверял native-путь для контракта экипажа v2 и флагов CREW-ANY на отдельной копии клиента; исходная копия клиента `C:\WoT_0.9.1_RU_0717_original` не трогалась.

## Стенд и запуск

Официальный стенд: `local/stands/crew-any-native-20261024-02`. В нём закреплены пять профилей CAT-01 (MS-1, ИС-7, Т-26, Т-34, Т-34-85), `legacy091-profile13`, Прохоровка `05_prohorovka`, terrain/obstacle pins, каталог, P08C late results и P06T armament/ammo-rack. Адреса: login `127.0.0.1:20340`, base `127.0.0.1:20341`, identity `127.0.0.1:3692`.

Подготовка и миграция, выполненные на копии стенда:

```powershell
python -B -X utf8 tools/full_test_stand.py prepare `
  --source-stand D:\WoT_9.1_Server\local\stands\full-test-20261020-04 `
  --physics local/build/server/physics-crewany-native01 `
  --gateway local/build/server/gateway-crewany-native01/target/debug/sr-gateway.exe `
  --out local/stands/crew-any-native-20261024-02
python -B -X utf8 tools/full_test_stand.py crew-contract `
  --stand local/stands/crew-any-native-20261024-02 --version 2
powershell -NoProfile -ExecutionPolicy Bypass `
  -File local/stands/crew-any-native-20261024-02/services.ps1 start
powershell -NoProfile -ExecutionPolicy Bypass `
  -File local/stands/crew-any-native-20261024-02/services.ps1 stop
```

Первый старт потребовал пересчитать вложенные map/profile hashes и вернуть в стенд проверенные terrain/obstacle resources. После этой нормализации финальный startup прошёл чисто. По завершении bridge/gateway остановлены, клиентский процесс завершён, control-файл удалён.

## Матрица приёмки

| Проверка | Статус | Доказательство / граница |
|---|---|---|
| Подготовка стенда и загрузка ресурсов | **PASS** | `stand-receipt.json`; gateway загрузил 5 профилей, terrain/obstacle, каталог 1038 объектов, P08C/P06T |
| Миграция аккаунтов на `p04m-pool-crew.v2` | **PASS** | `crew-contract-v2-receipt.json`; A: revision 185, capacity 192, free 176, members 12; B: revision 123, capacity 192, free 180, members 12 |
| Bridge/gateway transport и profile13 bind | **PASS** | `bridge-20261024-123144.stdout.log`, `gateway-20261024-123150.stdout.log`; `BOUND`, `SESSION_ACTIVE`, `ACCOUNT_SYNC_REQUEST`, `AMMO_ACCOUNT_REFRESH` |
| Нативный CPython и CREW-ANY bootstrap | **PASS** | trace: CPython 2.7.3 32-bit, `crew_any_policy`, `max_tankmen=192`, `server_authoritative=true`, каталог SHA `a6bd44f4…` |
| Оригинальный login flow → native hangar | **PASS** | trace: `LoginView.onLogin`, `LOGGED_ON`, `native_connected=true`, `hangar_space_loaded=true`, четыре видимые модели |
| Наблюдение crew/P09D callbacks | **OBSERVED** | trace: 8 crew callbacks и 16 ammo callbacks; это не подтверждение принятия доменных команд |
| Диагностическое `hangar_limits_observed` | **FAIL** | control получил `diagnostic_condition_failed`; native login/hangar при этом состоялись |
| P09D native command acceptance | **NOT_RUN** | отдельный сценарий остановлен клиентским guard: baseline ожидал unskilled MS-1, а v2-аккаунт имел `commander_tutor`; CMD108 до gateway не дошёл |
| T-26/не-MS-1 native UI | **NOT_RUN** | нет отдельного чистого native-сценария |
| Найм, перевод, увольнение, казарма | **NOT_RUN** | команды не выполнялись в native trace |
| Ёмкость экипажа `>16` | **NOT_RUN** | native UI/команда не проверены |
| Настоящий бой profile13 на Прохоровке | **NOT_RUN** | arena-entry smoke только экспортировал статический `01_karelia`; `compatibility_acceptance=false`, arena не загружалась |
| Клиент без `--crew-any` | **NOT_RUN** | отдельная legacy-проверка не запускалась |

Итог карточки: **`PARTIAL / NOT_ACCEPTED`**. Это не полный native PASS: серверный транспорт, авторизация и hangar доказаны, но игровой CREW-ANY command path и настоящий бой ещё не закрыты. Ветка остаётся неслитой.

## Evidence

Основная квитанция: `local/stands/crew-any-native-20261024-02/native-gate-crew-any-20261024-receipt.json` (`PARTIAL_NATIVE_PASS_WITH_ACCEPTANCE_GAP`).

- Gateway: `local/stands/crew-any-native-20261024-02/gateway-20261024-123150.stdout.log`.
- Bridge: `local/stands/crew-any-native-20261024-02/bridge-20261024-123144.stdout.log`.
- Native login/hangar trace: `D:/WoT_9.1_Server/local/client-runtime-crew-native-a-02/native-211624-1792827183386.jsonl`.
- Arena export smoke: `D:/WoT_9.1_Server/local/client-runtime-crew-native-a-02/native-240536-1792826920991.jsonl`.
- P09D descriptor-guard trace: `D:/WoT_9.1_Server/local/client-runtime-crew-native-a-02/native-237808-1792827224777.jsonl`.
- Stand receipts: `stand-receipt.json`, `crew-contract-v2-receipt.json` в каталоге стенда.

## Ограничения и следующий шаг

Физический build в этой карточке не являлся новым доказательством: для стенда использованы уже проверенные локальные артефакты; самостоятельный повторный build physics отмечен `NOT_RUN`. Native arena export не равен бою. P09D нужно повторить на чистом v2-аккаунте с baseline, соответствующим probe (unskilled crew), иначе тест сам себя закрывает до команды.

Единственный следующий шаг: подготовить отдельный чистый v2 native-сценарий с Т-26 и unskilled baseline, выполнить через реальный клиент recruitment/crew command и довести его до profile13 боя; только после этого пересматривать статус ворот.
