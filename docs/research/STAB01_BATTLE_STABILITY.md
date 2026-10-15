# STAB-01 — диагностика устойчивости боя, 2026-10-15

Карточка: `docs/ACTIVE_GATE.md`, пункт 1 `IMPLEMENTATION_ORDER.md`.
Ветка `codex/stab01-battle-isolation`, база `main` `1d19d2e`.

## VERIFIED — диагностический срез

- Коммит `56f5f179dca2b6b3aebb1bda691e7e0c3c43031f`: `model::bad()` сохраняет
  `InvalidData` и сообщает файл/строку/столбец вызова через `#[track_caller]`.
  Передача функции в `ok_or_else` заменена явными ленивыми closures, иначе
  function-pointer shim теряет вызывающую позицию. Lifecycle пока не менялся.
- Полный gateway suite: **831 passed, 0 failed, 5 ignored**, затем сборка PASS.
  `local/build/server/gateway-p05b-stab01-diag01/{result.json,test.stdout.log}`.
  Gateway SHA256 `d18519235f421fcdad171a357cf463d4126048faf6325798750824199238cd93`.
- Новый локальный стенд `local/evidence/20261015-stab01-01/native-diag01/`.
  Binding SHA256 `f93b6066d63ba89828781f1839f93be043a05c9cc1c7e74416f7b5b93b470605`;
  все 321 tracked файла `server/tools/client_patch`, полный gateway artifact,
  шесть старых helpers (byte-for-byte) и зависимости candidate17 проверены.
  Старый `PASS_P05B_CURRENT_RUNTIME_BINDING` — имя схемы совместимости helper,
  не приёмка STAB-01. Неиспользуемый старый preprocessing probe выключен.
- Ангарная установка A `local/stands/p09e-main-01/install01` откачена по ledger.
  Для обеих разрешённых копий созданы новые namespace/install ledgers в новом
  стенде; оригинал клиента не менялся. Ангарный bridge/gateway не останавливались.
- Отдельный боевой identity bridge: `127.0.0.1:20020`, собственный PID 27000,
  `/health` PASS; receipt `local/stands/stab01-identity-01/launch.json`.

## OBSERVED — настоящий native-запуск

- Новый `legacy091-integrated-lab`, Прохоровка, однородная пара MS-1.
  Battle `11522436634285911744`; gateway log `gateway-stabdiag01.stdout.log`
  в новом стенде: два `SESSION_ACTIVE`, `SHARED_WORLD_STARTED`, два `SHARED_READY`
  (own IDs 152043523 и 152043525), движение/выстрелы обоих участников.
- Windows Computer Use не смог получить кадр обоих окон: `FrameArrived timed out`
  и `window capture timed out: timed out waiting on channel`; A повторно выбрана
  и проверена, B проверена после готовности боя. Слепые нажатия не выполнялись.
  Владелец запрошен выполнить Esc → «В ангар» в обоих окнах после двух минут.

## VERIFIED / OBSERVED — воспроизведение выхода

- OBSERVED: владелец выполнил выход обоих клиентов и подтвердил, что оба
  отключились/вернулись ко входу. Новый log: строки 12876 и 13038 —
  `SHARED_FAILED session=1|2 reason=shared laboratory contract at src\shared\server.rs:985:119`;
  следующие строки закрывают сессии на tick 2697 и 2743. Сводка —
  `native-exit-observation.json` в новом стенде.
- VERIFIED: на диагностическом head строка 985 — именно 90-секундный timeout
  `!full_ready`. Native Leave меняет фазу на Leaving, а full_ready требует Driving.
  Ошибка идентифицирована свежим executable и настоящим native-выходом обоих,
  а не только статической гипотезой.
- VERIFIED по исходникам: старый shared loop удаляет Leaving Session через
  `native_leave`, не отправляя native Account reset/create/warm sync.
- Диагностические процессы A/B/gateway остановлены после записи результата по
  своим PID/path/hash receipts: `stop-reprodone.json`. Старый ангар не затронут.
- Реализация исправления: отдельный shared Returning поверх ACK-bound
  WarmAccountReturn, warm100/300/600, сохранение каналов, явный лабораторный
  повтор через native700. Shared unit replay 9/9 и прежний warm regression 18/18
  PASS в изолированном worktree; это ещё не общий gateway gate и не native PASS.

## VERIFIED — исправленный lifecycle и граница ошибки боя

- Runtime head `9b4d26cfebe68e93d47aa2578c894d3cba9e55e3`: отдельный Returning
  сохраняет аутентифицированные UDP/reliable-каналы. Account reset/create следует
  после ранее поставленной отправки; новый warm sync принимается после ACK reset
  и native enable09. Проверены warm100/300/600 и ограниченный drain старого Avatar.
  Повторный native700 относится только к существующему laboratory profile4;
  выбранный танк ангара профиля 13 остаётся P08B.
- Обычный Leave после завершения подготовленной физической транзакции сразу
  отсоединяет своего actor и возвращает Account. Проверки area/correction и
  90-секундная проверка входа не блокируют выход. Команды вышедшего не применяются,
  оставшийся actor сохраняет управление. Объявленная очередь переживает повторное
  присоединение и явно отменяется при отказе до native Avatar.
- Ошибки world/trace-step и публикации ловятся общей границей боя в сервисе.
  `SHARED_BATTLE_FAILED` сохраняет причину и JSON-снимок в удерживаемом stdout:
  actor state/input/aim/fire/HP, снаряды, состояние объектов, SHA геометрии и
  ограниченный хвост последних 64 trace events с числом пропущенных событий.
  Это диагностический снимок, **не полный детерминированный replay**; команды и
  порядок сетевых сообщений остаются в отдельном журнале/pcap стенда.
- После ошибки старый runtime со всеми owned workers уничтожается, мир берётся
  из чистого source-bound шаблона с новым battle ID. Сессии возвращаются в Account;
  явная ошибка возврата журналируется и закрывает соответствующий transport.
  Сервисные sockets, авторизация, следующий session ID и retirement не сбрасываются.
  Подавления ошибок инфраструктуры через фиктивный успех нет.

## VERIFIED — проверки исправленного head

- Полный gateway suite и сборка: **845 passed, 0 failed, 5 ignored**.
  Команда `python -B -X utf8 server/build.py gateway --test --out
  local/build/server/gateway-p05b-stab01-fix04`; `result.json`, команды и полные
  stdout/stderr находятся в этом каталоге. Executable SHA256
  `cf1b068c757d4af311c5c82a46cea135d028e98426542d2b36299bbd9a82640a`.
- Пять meaningful STAB unit-сценариев: оба выхода после 90 с; отложенный выход
  через scene barrier при неготовых areas; настоящий native Leave до correction
  ACK6 сохраняет бой второго; отмена объявленной очереди после reattachment;
  инъекция настоящего trace invariant failure и новый бой в том же контроллере.
- Последний сценарий использует двух настоящих physics workers, проверяет их
  освобождение (EOF/exit0/reaped без принудительного завершения), новый чистый мир,
  сохранение transport/retirement и старт следующего боя с полным боекомплектом.
  Дополнительный exact-test replay с `--nocapture` сохранил действительный снимок
  с причиной `impact segment facts`: `local/evidence/20261015-stab01-01/fault-proof01/`
  (`result.json`, `failure-snapshot.json`, `test.stdout.log`). Это unit evidence;
  оно не подменяет проверку настоящего client UI.
- `python -B -X utf8 server/check_layout.py`: PASS, 116 source files / 22 relocations.
  `git diff --check`: PASS. Независимый статический review выявил и перепроверил
  исправления двух краёв: Leave до ACK6 и очередь до запуска Avatar.
- Прежние общие Python/legacy-долги из preflight сохраняются. Полный Python-набор
  на этом head не перезапускался; Linux/ARM и bitwise cross-platform replay NOT_RUN.

## OBSERVED / UNKNOWN — повторный native-стенд

- Свежий `native-fix04`, run `stabfix04`, binding SHA256
  `fe009c724e283ca8e2bc7f3b99366e1f445fb5b9df30b85449563dc0225c6bc3`.
  Все 321 tracked runtime-файла, новый полный build и прежние закреплённые helpers /
  worker resources проверены; dry-run prepare A/B и server PASS. Клиентские патчи
  диагностического стенда откачены по ledger до нового prepare/install.
- Два настоящих клиента вошли в battle `8865067871889357875`; log
  `native-fix04/gateway-stabfix04.stdout.log` содержит два SESSION_ACTIVE и
  два SHARED_READY. `create-receipt.json`, commands и отдельные launch/prepare
  receipts удерживаются в том же каталоге.
- OBSERVED: владелец начал ехать; один клиент получил чёрный экран, другой вернулся
  в ангар. Перед ручным выходом случился настоящий runtime-сбой
  `integrated drive logical deadline lag exceeds500ms; fail closed`. Причина
  задержки UNKNOWN; политика deadline не ослабляется в рамках STAB-01.
- VERIFIED по новому журналу: `SHARED_BATTLE_FAILED` line5003, возврат обеих сессий
  и reset мира lines5004–5006; старые workers завершены EOF/exit0/reaped. Оба
  Account reset были ACKed и включены; A завершил warm100/300/600 и вернулся в
  ангар, B был отвергнут на первом warm bundle891 (`shared/mod.rs:266`), затем
  закрылся по idle timeout. Процесс и A продолжали служебный обмен.
- VERIFIED из настоящего B packet5031: warm100(req226,rev1), warm300(req227,rev2,
  descriptor430/CRC1559578668), warm600(req228,rev0,0,0). SHA256 исходного пакета
  `877c4027e6de5b03ea93fb19e20a27c1b1330eeb41a494718fb0e7baa1801e6a`.
  Прежняя проверка hardcoded warm300rev3 неверна для SECONDARY r1-catalog2,
  чей уже опубликованный shop имеет rev2. Дальнейшие token-only пакеты892+
  отвергались из-за атомарно отклонённого891. Это отдельная подтверждённая ошибка,
  не неопределённый UI-сбой и не повод ослаблять ordered channel validation.
- Стенд остановлен по собственным PID/path/hash receipts `stop-warmfailure.json`;
  обе установки откачены по ledger. Исправление привязывает warm300 к неизменяемым
  уже загруженным shop bytes конкретной сессии. **Native-приёмка FAIL** на этом
  срезе; оба ручных выхода и повторный вход пока UNKNOWN, merge не выполнен.

## OBSERVED / VERIFIED — инцидент локальных фикстур

- Вспомогательный managed worktree содержал junctions `local/server` и
  `local/vendor` к основному checkout. Root заархивировала worktree, не проверив
  эти ссылки. После архивации обнаружено отсутствие 70 файлов: 68 старых fixture
  files, bridge.json и client-digest.bin. Причинный механизм архиватора отдельно
  не воспроизводился — **UNKNOWN**, последовательность и junction targets записаны.
- Native-запуски были приостановлены; 64 файла восстановлены с совпадением
  независимо удержанного исходного SHA256. Шесть вспомогательных JSON в двух
  старых `r1` воспроизведены из закреплённых данных/генератора с прежними размерами,
  но независимый SHA прежнего файла **UNKNOWN**. Их статус явно отличается от
  точного восстановления. Все файлы текущего боевого профиля и все native
  manifests имеют совпавшие независимые исходные SHA.
- Финальный read-only аудит: все 91 159 файлов прежней инвентаризации server/vendor
  на месте, все размеры совпали; 70/70 восстановленных проверены по указанной
  provenance, 45/45 боевых pins PASS. `local/evidence/20261015-stab01-01/fixture-recovery/`
  содержит `INCIDENT.md`, `audit-final.json`, исходный missing-map, рецепты,
  exact candidates и отчёты переноса. Identity/content pins не ослаблялись.
- Неудачные полные прогоны сохранены: fix02 — 673 passed / 171 failed / 5 ignored
  на отсутствовавших ресурсах; fix03 во время частичного восстановления —
  843 passed / 1 failed / 5 ignored (`grant manifest missing`). Финальный fix04
  выполнялся после восстановления и прошёл полностью.

## Откат

Сохранить все evidence. Остановить только процессы из собственных receipts,
откатить battle install и namespace по новым ledgers. Для ангара A выполнить
новый prepare/install из сохранённых параметров прежнего `install01`; старый
ledger повторно не устанавливать. Код карточки откатывается revert её коммитов.
