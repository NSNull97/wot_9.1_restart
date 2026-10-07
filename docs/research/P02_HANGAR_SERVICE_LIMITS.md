# P02 — границы доступных действий ангара

2026-10-05, ночная доводка по поручению владельца. Цель: убрать приглашение
в неподдерживаемый бой и чужое публичное название из фактического приветствия.
Реальные очередь, снаряды, арена и бой не реализуются. Серверный profile3 с
экипажем МС-1, его fixtures и прежние журналы выдач сохраняются.

`H` = `local/evidence/20261005-p02-hangar-limits/`.
Статус: **PASS узкой native-карточки**, limits02 → limits03. Оба полных
прохода, повторный вход с тем же кэшем и установка обычного пакета004 завершены.
Ручная проверка человеком и физический hover остаются NOT_RUN. Первый
limits01 выявил ошибку собственного наблюдателя и сохранён как FAIL.

## Основание и реализация

**VERIFIED:** original #717 `Vehicle.isReadyToFight` проверяет состояние
машины и экипаж; боекомплект в эту проверку не входит. Последующий
`FightButton.fightClick` запускает dispatcher, затем ammo check и CMD700.
Подробные original hashes/offsets:
`local/evidence/20261005-p02-ms1-crew/data/next-hangar-gates.md`.

В `hangar_capabilities.py` добавлены два точных обратимых binding:
`fightClick` и `_FightButton__disableFightButton`. Сохранены оригинальный
update и его завершение. Исходный setter получает disabled=True и подсказку
«Бои пока недоступны». Direct callback показывает SystemMessages.Warning
до dispatcher/автопополнения. Это политика своего исследовательского сервиса;
она не заменяет серверную проверку. Серверный отказ неизвестного CMD700
сохраняется; negative application response очереди пока не исследован.

**VERIFIED:** оригинальный AS setter отключает главную кнопку; последующая
настройка списка режимов не включает её обратно. Disabled guard имеется и
на пути ENTER. Hover привязан к родителю и использует WARNING TooltipProps.
Это статический контракт; физические мышь/клавиатура в ночной приёмке NOT_RUN.
Хеши/offsets и 20 новых тестов на Python3/2.7.3, прежние 14 тестов на обоих:
`H/gui/HANDOFF_01.md`, `H/gui/source-audit-01.json`. Helper SHA
`b1d0798ead4e78165b461173ce5379d63d02a40bba57b7054ea60725abeb5175`.

**VERIFIED:** `SystemMessagesInterface.__onConnected` использует ровно
`#system_messages:connected`. Производный `system_messages.mo` меняет только
этот перевод на `Добро пожаловать на сервер «%s»!`. Прежние 656 ключей,
метаданные и остальные 655 переводов побайтово сохраняются. Original SHA
`c48a1f5d461c865c0e6b1ee8f9ec2afee21f29ca1fde5badd240aa566ba36992`, output SHA
`c4c73be8f79c52bbd2f7552069dc2ad5777008c792669e36eb0720df6d5fdbc6`.
Новый ограниченный data-only parser/writer: `tools/project_greeting_resources.py`.
16 тестов PASS, включая независимый gettext и повреждённые входы:
`H/data/greeting-01/result.json`. Original только читается; installer проверяет
research before hash и сохраняет backup/ledger существующего файла.
Неполная папка res_mods/text не создаётся, имена ресурсов/ключи не меняются.

## Native сценарий и первый отрицательный результат

Новый `hangar_limits_scenario.py` запускается только явным one-shot control.
Последовательность: МС-1 → ИС-7 → профиль → МС-1 → complex tooltip → прямой
вызов установленного отказа боя. Проверяются actual Flash enabled=False,
готовность выбранной модели, неизменная identity/ресурсы/статистика, три
прочитанных родными API snapshot экипажа и шесть PNG. Полный tooltip API
использует original Flash showComplex, подготавливающий нужные _props.
Диагностический вызов с одним аргументом даёт INFO-оформление; это проверка
текста/render, **не физического WARNING-hover**. Private toolTip readback
может быть UNKNOWN; переданный текст отдельно проверяется original Meta.

Limits01: actual приветствие и disabled button на двух машинах наблюдались,
два PNG просмотрены. Затем реальный ProfileSummary открылся и прислал
активный dossier callback, но мой сценарий вызвал старый bootstrap observer,
который ждёт флаг другого способа запуска GUI. Это ошибка диагностики,
а не доказанное зависание исходного окна. Native source/compiled versions
сохранены в `H/limits01-sources/` и prepare. Исправление использует прежний
интерактивный `_observe('profileSummaryPage', databaseID)` без подмены GUI.
Исторический run не превращается в PASS из-за успешных отдельных callbacks.

## Результат исправленного прохода

| Проверка | Фактический результат |
|---|---|
| Limits01 | FAIL сценария на лимите600 observations; exit0/12cleanup/restore PASS |
| Limits02 | PASS:115 пакетов,28.1833671с канала,47.6572588с процесса |
| Limits03 | PASS:114 пакетов,28.2332727с канала,47.5523425с процесса |
| Повторный вход02→03 | PASS: тот же hash-bound profile002, ненулевые реальные hints кэша |
| Кнопка/профиль/тексты | PASS: шесть состояний и шесть просмотренных PNG каждого прохода |
| Состояние аккаунта | PASS: три одинаковых crew observations; ресурсы/статистика/дескрипторы прежние |
| Сетевые мутации | PASS: нет CMD108/700/701; только измеренные sync/refresh |
| Завершение02/03 | PASS: exit0,12cleanup,capture,rollback;0 новых trace/log errors |
| Второй аккаунт через сайт | PASS: snapshot1,свой МС-1 без экипажа;297байт игровой записи прежние |
| Обычная установка004 | PASS установки и exact10 compiled/MO match; отдельный ручной запуск NOT_RUN |
| Длительная устойчивость нового полного сценария | NOT_RUN; короткие проходы её не заменяют |

Независимый парный report:
`H/wire/verify-limits03-strict-01/hangar-limits-verification.json`, SHA256
`f296eaedd7e9c40aad4a7da9d58d24070cfbbf25819da2775d3a4abf74162587`.
Verifier дополнительно отвергает новый пустой каталог профиля вместо cached
relogin. Фактические hints: account−1406441505, shop518/−846328027,
dossier1/1791128141. UUID/nativeID, три payload SHA и10compiled неизменны.
63 проверки verifier PASS, включая настоящие отрицательные corpora; source SHA
`73fa5db5bfaeabf3fd4c6c71301dd47435cf838abda60cb7c95668f974bc34f0`.

Сценарий после исправления SHA
`5f0d37899778912c72a4d1ca4e51c4e49d79bd9d6d696f99341cd323d4c6dd96`;
28 unit checks и pinned2.7.3 compilation PASS. Runner30checks PASS.
Скрины: `H/limits02-runtime/screenshots/`, `H/limits03-runtime/screenshots/`;
отдельные visual-review-limits.json в prepare привязывают человеческий просмотр
ассистентом к точным PNG/trace SHA. Private Flash toolTip чтение UNKNOWN;
родные Meta callbacks и видимый текст подтверждены отдельно. INFO diagnostic
не засчитывается как физический WARNING hover.

HTTP второго аккаунта: `H/data/secondary-http-01/report.json`, SHA
`a58b3504ee9faf288e7df839a44dbb2a987a82768a756a06e55fd8c2aa71be9f`.
Там же проверены own identity, cabinet, чужой UUID query,anonymous401 и logout.
Разрешённый last_login обновился; игровая запись не менялась. Оба профиля:
`local/evidence/20261005-p02-ms1-crew/accounts-during-limits01.json` PASS.

На native PNG сохраняется цветная зернистость, замеченная ещё в crew-карточке.
Причина UNKNOWN; этот результат не является приёмкой всей графики.

Для повторной проверки сохранённых фактических проходов (новый --out):

```powershell
python -B -X utf8 tools/verify_hangar_limits.py --install local/evidence/20261005-p02-hangar-limits/limits03-prepare --previous-install local/evidence/20261005-p02-hangar-limits/limits02-prepare --fixture local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r3-catalog3 --native-export local/evidence/20261005-p02-ms1-crew/native-ms1-crew-export01.json --out local/evidence/20261005-p02-hangar-limits/verify-repeat-01
python -B -X utf8 -m unittest discover -s tests -p test_hangar_limits_verifier.py -v
```

Новый настоящий запуск, только когда предыдущая установка откатана и mutex
свободен: `H/prepare_run.py --name limitsNN`, затем
`tools/diagnostic_client_run.py --install H/limitsNN-prepare --service local/server/service.json`.
`H` в командах заменить полным указанным каталогом; NN — новый номер.
Helper берёт собственные credentials из прежнего ignored файла и создаёт
одноразовый consumed control. Он не регистрирует аккаунт и не пишет пароль в отчёт.

## Сохранение состояния и откат

Перед правкой: `H/baseline-01/project-before.zip/json` — 271 исходник,
14 конфигурационных/профильных файлов, consistent backup обеих своих БД.
Точные research before hashes и backups каждого запуска — его install-plan,
patch-ledger, backup и restore. Original никогда не записывается.

После закрытия клиента штатный откат конкретной установки:

```powershell
python -X utf8 tools/interactive_client.py rollback --out local/evidence/20261005-p02-hangar-limits/limits01-prepare
```

Исходники восстанавливать выборочно из baseline после сверки текущего SHA.
Не разворачивать старую БД поверх живых аккаунтов. Эта UI-карточка не должна
менять backend/generator или отменять серверную выдачу экипажа.

Обычный пакет `local/client-install-004` установлен:19 статических payloads
и3 runtime logs в ledger, без control/autologin/autoquit/capture. Точные10sources
и оба MO соответствуют принятому limits03: `H/normal004-preinstall.json`.
Полная сверка `H/final-audit-01/final-state-audit.json` PASS, SHA256
`506c0792bf55f1bac0fda5c21ca3d00f364fd1e01a4c993be3ad93395755dddb`:
original3469/research3484, SHA у каждого файла, неожиданных отличий0;
семь ночных диагностических восстановлений и22 before-checks пакета004.
Отдельно подтверждены29 замороженных backend/generator исходников.
Десять отрицательных проверок отвергают испорченный manifest/ledger.
Откат после закрытия клиента:

```powershell
python -X utf8 tools/interactive_client.py rollback --out local/client-install-004
```

Следующий проверяемый шаг: отдельная небольшая карточка входов
«Внешний вид»/«Обслуживание», с честным отказом неподдерживаемых операций.
Read-only основание: `H/gui/appearance-audit-01.md`; реальное падение
«Внешнего вида» подтверждено прежним normal003, падение обслуживания UNKNOWN.
