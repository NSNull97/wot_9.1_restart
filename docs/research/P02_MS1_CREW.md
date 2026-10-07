# P02 — экипаж МС-1

Карточка начата05.10.2026 по прямому «поехали» владельца. Ночью владелец
поручил продолжать без него. Цель: серверная выдача двух членов экипажа
существующему МС-1 основного тестового аккаунта и сохранение при повторном
входе. Процент основной специальности100, навыки/перки отсутствуют — явная
политика собственного `test_lab`, не утверждение о стартовом аккаунте2014года.

`C` = `local/evidence/20261005-p02-ms1-crew/`.
Текущий статус: **PASS узкой native-карточки**. Серверная выдача, доставка,
отображение и повторный вход проверены настоящим клиентом. Ручная приёмка
владельцем **NOT_RUN**. Обычная установка после ночной доводки ещё не сохранена;
все диагностические установки штатно восстановлены. Полный P02 остаётся PARTIAL.

## Доказанные контракты

- **VERIFIED:** original #717 `ITEM_TYPES.tankman == 8`. В inventory экипаж
  хранится в разделе8; раздел2 означает chassis. Подробные bytecode offsets,
 15source hashes: `C/data/FINDINGS.md`.
- **VERIFIED:** МС-1 `typeID=(0,13)`, `typeCompactDescr=3329`, два места:
  commander+gunner+radioman+loader, затемdriver. `C/data/FINDINGS.md` и
  фактический `C/native-ms1-crew-export01.json`.
- **VERIFIED:** родные `generateCompactDescr` → `TankmanDescr` →
  `makeCompactDescr` дали два стабильных25-байтовых дескриптора, с одинаковым
 6-байтовым пустым native tankman dossier. Обратная сборка байт-в-байт.
  Никакой клиентский inventory этой операцией не изменялся; выбранный ИС-7
  до/после экспорта и native accountID1 совпали.
- **VERIFIED:** hash командира
  `926254dfdbc7acf5a5d0c163d57642c24105da3ab21a7255236060e9534b70b5`,
  механика-водителя
  `e4c85b2b116b96eff5d68aa8df2e509370f923843def67331478e4b62309b76d`.
  Native `roleLevel=100`, `skills=[]`, `freeXP=0`; вычисляемый
  `totalXP()=105030` отражает обученные уровни. Его нельзя выдавать за нулевой
  totalXP или за заработанную боевую статистику.
- **VERIFIED:** пустой native Tankman dossier не содержит добавляемого
  генератором account/vehicle `creationTime`. Не переносить эту правку из
  предыдущей карточки на танкистов.
- **VERIFIED:** RecruitWindow индексирует `tankmanCost[1]['credits']` и
  `[2]['gold']`; текущий стенд передаёт пустой список. Это объясняет прошлый
  IndexError. `C/gui/FINDINGS_01.md`; стоимость не выдумывалась.
- **VERIFIED:** PersonalCase Flash configUI вызывает все пять getters,
  включая обучение и документы. Выбор первой вкладки не изолирует окно от
  отсутствующих тарифов. Полная поддержка личного дела пока **UNKNOWN/NOT_RUN**.

## Первый настоящий экспорт

`export01-prepare`/`export01-runtime`: nativePID16540, CPython2.7.3x86,
original EXE SHA256
`86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed`.
Процесс22.7845305с,46пакетов, exit0, capturePASS,12cleanupPASS, restorePASS.
Управление — исходный LoginView.onLogin с собственной тестовой учёткой;
завершение — BigWorld.quit после записанного export marker. Таймера
завершения и компьютерного ввода не было. Это автоматизированный native
API-эксперимент; ручная проверка UI не заявляется.

Envelope `C/native-ms1-crew-export01.json`, SHA256
`df0a9c26181a4efd65bfc8e9c34e2fbabc6f92a860db5676355890e400377a65`,
связывает точный trace record с планом установки и outcome. Исходный
`ms1_crew_probe.py` SHA256
`37d1444bb58663bddfdfe118e1a8a6315ece894d26036b276033ee913e690ded`,
compiled SHA256
`ea83f9bbeb90e803fd899f0fd561513cae06789c29aed675c06eb19a945494f7`.

Original19entrypoints политики экипажа установились и восстановились без
bootstrap/observer ошибок. Нажатие/предупреждение этой политикой в этом run
не проверялось. В python.log остаются известные сообщения неподдерживаемого
Vivox; отсутствие любых строк ERROR не утверждается.

## Изменение данных и ограничения

Новый профиль3/snapshot3 выдан поверх неизменного profile2 с МС-1/ИС-7.
Native wire revision остаётся1, каталог3, старый dossier cursor1 и его
timestamp сохраняются. Новые доменные crew IDs отделены от native IDs1/2;
назначение обоих —native vehicle1. ИС-7 экипаж не получает.

`ms1_crew_state.py` проверяет исходный r2 повторением замороженного генератора
и требует обратимость единственной crew delta. `shop.bin`, `dossier.bin`,
аккаунт/XP/ресурсы/статистика и оба vehicle descriptors сохраняются.
`ms1-crew.mjs` —отдельные plan/apply/rollback, без публичного route выдачи.
Живая выдача выполнена после отрицательных и rollback tests. Повторное
применение вернуло ALREADY_GRANTED. Журнал `C/primary-crew-grant-01/`,
SHA256 prepared.json
`4a68cd7243af1a10d69110c1c85b8a48d0843d31d8c2dcc70fb05287fcf73bef`.
Точный профиль до выдачи: `31a2d6f0427f14536371568387ccfb4acefe874934527b85f18932bcf68ccbdc`,
после: `5167ea63f0503952b4ab1e7c4b1ed2dca5e5da6b6812bd476a87124a891e0888`.

Не реализуются найм за валюту, обучение, перемещение, увольнение, смена
паспортов, навыки, экипаж ИС-7, снаряды, кастомизация, арена и бой.
UI показывает недоступность операций; серверная валидация остаётся
обязательной. Собственная политика не является готовой игровой экономикой.

## Откат и повтор

Все промежуточные native установки используют отдельный `install-plan.json`,
backup и ledger. После штатного выхода runner выполняет:

```powershell
python -X utf8 tools/interactive_client.py rollback --out <каталог-конкретной-установки>
```

Для новой попытки обязательны свежие plan/runtime/control. Старый
`export01-control.json` употреблён и удалён; повторное использование outcome
или уже откатанной установки запрещено. Исходная normal003 откатана;
последние пользовательские логи сохранены и возвращены по точным хешам:
`C/normal003-log-preservation*.json`. Профиль002/его кэш сохраняются.

Бинарник gateway до сборки версии3: `C/gateway-before/p01-wg-probe.exe`.
Восстанавливать его только с остановленным собственным сервером и после
отката profile3→2. Новый gateway SHA256
`4e22d2fd5f47070c7597462a056a6c4d59bcd5f73c452817f2357bf21e874a66`;
сборка `cargo build --offline --locked --manifest-path tools/wg_probe/Cargo.toml`
прошла, `C/gateway-build.log`. Rust62testsPASS; native delivery этой сборкой
PASS в crew02/crew03. Конфигурации service/bridge/gateway не менялись.

## Доставка, повторный вход и сайт

| Проверка | Результат и доказательство |
|---|---|
| Первый crew01 | FAIL: наблюдатель спутал typeCD и inventoryID; `C/wire/verify-crew01-final-01/` |
| Исправленный crew02 | PASS сессии, 62 пакета, три одинаковых crew observations, два PNG |
| Crew03 после crew02 | PASS сессии и cached relogin, 62 пакета, прежний profile002 без очистки |
| Завершение crew03 | PASS: 28.2610566 с, exit0, 12 cleanup, capture и rollback |
| Ресурсы/статистика/второй профиль | PASS: `C/accounts-after-relogin-01.json`; второй профиль побайтово прежний |
| Сайт и API primary | PASS: настоящий email login, snapshot3, МС-1 crew=true / ИС-7 false; `C/website-proof-01.json` |
| Ручная проверка человеком | NOT_RUN; владелец спит, ввод мышью/клавиатурой не автоматизировался |
| Долгая сессия с новым экипажем | NOT_RUN; эти проходы не заменяют отдельный duration gate |
| Реальный rollback выдачи primary | NOT_RUN; изолированная цепочка rollback 3→2→1 PASS |

Итоговый независимый report:
`C/wire/verify-crew03-final-01/ms1-crew-native-verification.json`, SHA256
`ec625af4067714e80c56a7bb260007483f1ef8736da2ea5c7d452683c7961dd6`.
Verifier не импортирует генератор снимка и проверяет literal delta отдельно,
точные три streams, UUID, сохранённые payloads, original Crew/Meta callbacks,
девять compiled modules, cleanup, отказ неподдерживаемого действия и PNG.
34 отрицательных/положительных проверки verifier PASS. Общая Node suite73,
Rust62, generator23, probe21, crew policy13, scenario16, diagnostic runner27
прошли. Test doubles проверяют код, native совместимость подтверждают только
отдельные фактические запуски. Полные команды и логи: `C/wire/`, `C/data/`,
`C/gui/`; исторические ошибки не удалены.

**OBSERVED на четырёх просмотренных native PNG:** командир «Сержант Иванов»,
механик-водитель «Младший сержант Петров», 100%/110% с командирским бонусом;
МС-1 показывает «Неполный боекомплект», ИС-7 — «Неполный экипаж».
Попытка неподдерживаемого изменения показала предупреждение, дескрипторы
остались прежними. Скрины: `C/crew02-runtime/screenshots/` и
`C/crew03-runtime/screenshots/`; review привязан SHA в соответствующих prepare.
На изображениях мира заметна цветная зернистость; её причина UNKNOWN.
Качество всей графики этой карточкой не принимается.

После назначения экипажа исходный клиент включает кнопку боя. Сервер боёв
ещё нет; отдельный read-only аудит `C/data/next-hangar-gates.md` установил
путь FightButton→queue и точный ключ старого приветствия. Это следующий узкий
шаг ночной доводки, а не переход к P03. Найм, личное дело и операции экипажа
явно закрыты политикой своего сервиса; экипаж пока доступен в ангаре.

## Точные повторные команды

Из корня проекта; каталог --out каждый раз новый:

```powershell
python -B -X utf8 tools/verify_ms1_crew_native.py --install local/evidence/20261005-p02-ms1-crew/crew03-prepare --previous-install local/evidence/20261005-p02-ms1-crew/crew02-prepare --fixture local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r3-catalog3 --native-export local/evidence/20261005-p02-ms1-crew/native-ms1-crew-export01.json --out local/evidence/20261005-p02-ms1-crew/verify-repeat-01
python -B -X utf8 -m unittest discover -s tests -p test_ms1_crew_native_verifier.py -v
python -X utf8 local/evidence/20261005-p02-ms1-crew/audit_profiles.py --out local/evidence/20261005-p02-ms1-crew/accounts-repeat-01.json
```

Точный rollback выдачи, после закрытия клиента; он сохраняет выданный ранее ИС-7:

```powershell
python -X utf8 tools/local_server.py stop --config local/server/service.json
node web/src/ms1-crew.mjs rollback --service local/server/service.json --journal local/evidence/20261005-p02-ms1-crew/primary-crew-grant-01 --expect-journal-sha256 4a68cd7243af1a10d69110c1c85b8a48d0843d31d8c2dcc70fb05287fcf73bef
python -X utf8 tools/local_server.py start --config local/server/service.json --capture
```

Журнал фиксирует SHA своих реализаций: не переписывать ms1_crew_state.py,
ms1-crew.mjs, game-adapter.mjs и прежние генераторы ради следующей UI-правки.
Для отката исходников сохранён `C/baseline-01/project-before.zip` с манифестом;
восстанавливать только выбранные изменённые файлы, после сверки текущих SHA.
Полный архив поверх проекта и старую БД поверх живой базы не разворачивать.
