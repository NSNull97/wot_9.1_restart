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
- UNKNOWN: native-результат исправленной версии, fault containment в общем
  сервисе и следующий бой; приёмка STAB-01 ещё не закрыта.

## Откат

Сохранить все evidence. Остановить только процессы из собственных receipts,
откатить battle install и namespace по новым ledgers. Для ангара A выполнить
новый prepare/install из сохранённых параметров прежнего `install01`; старый
ledger повторно не устанавливать. Код карточки откатывается revert её коммитов.
