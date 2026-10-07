# Структура серверных исходников

Карточка 2026-10-06: привести серверные файлы и названия к одному основному
дереву, сохранив работающий локальный стенд. Владелец уточнил, что сейчас
развёртывание не требуется; будущая предполагаемая ОС — Linux.

## Что изменено и чем подтверждено

**VERIFIED:** серверный control расположен в `server/control/`, Rust gateway —
в `server/gateway/`, C# worker — в `server/physics/`. Файлы называют функцию:
`session.rs`, `protocol/transport.rs`, `account/hangar.rs`, `arena/movement.rs`,
`drive/world.rs`. Фаз и версии клиента в именах canonical файлов нет.
Действующие protocol IDs, ресурсные имена и локализация не менялись.

20 Rust и 2 C# файла перемещены с сохранением каждого байта. Старые Cargo и
MSBuild entrypoints используют новые пути к тем же файлам. Старые Python
entrypoints — короткие wrappers; lifecycle перемещён byte-identical,
service имеет ограниченные изменения imports, ROOT и identity entrypoint.
Полная карта путей: `server/layout.json`. Before копии и исходные SHA256:
`local/evidence/20261006-server-layout/before-manifest.json`, `before/`.
Доказательства перемещения: `rust-module-layout.json`,
`physics-relocation-01/result.json` в том же evidence каталоге.

**VERIFIED:** `server/identity/service.mjs` запускает существующую identity
реализацию через общую зависимость. Извлечена точка запуска, а не вся логика
аккаунта. Копии `web/src/game-adapter.mjs` и frozen Python encoders не созданы.
Текущие 13 явно закреплённых shared dependencies остаются на прежних местах.

**VERIFIED:** `server/build.py` создаёт только новый каталог под `local/build/`;
Cargo target и MSBuild obj/bin вынесены туда. Restore offline/locked. Активный
gateway не заменяется и сверяется по хешу. Сборки native GNU Rust 1.90.0 и
.NET SDK 9.0.315 действительно выполнены на текущем Windows-хосте.
Старый deployed EXE всё ещё имеет имя `p01-wg-probe.exe`: рабочая конфигурация
сохраняет его строгий путь. Новая сборка `sr-gateway.exe` проверена отдельно,
но не активирована. Не выдавать новую организацию исходников за миграцию службы.

## Правила новых файлов

1. Runtime код добавляется в подходящий модуль `server/` по ответственности.
   Сетевые индексы и сериализация относятся к gateway, доменные команды и
   симуляция — к своим модулям. Если функция исследовательская — она в `tools/`.
2. Имя файла описывает функцию и не содержит номер фазы, патч клиента, дату,
   `final`, `new`, `copy`. Python/Rust/JavaScript используют обычные имена
   `snake_case`; C# сохраняет принятые `Program.cs`, `CheckedInput.cs`.
3. Один runtime модуль имеет один редактируемый source. Совместимость старого
   запуска обеспечивается wrapper или ссылкой сборки на source, не копией.
4. Версия протокола остаётся в совместимости, версия payload/config — в схеме,
   обновления зависимостей — в lockfiles. Переименование source не даёт права
   менять native IDs, клиентские ресурсы или исторические характеристики.
5. Частные данные, секреты, извлечённый контент и outputs — в ignored `local/`.
   Сборки не выполняются внутрь source дерева. Новые зависимости должны быть
   явно указаны; `server/layout.json` фиксирует существующие общие зависимости.
6. После изменения запускается `server/check_layout.py` и относящиеся к
   изменению проверки. Guard отвергает известные private/generated names,
   дубли, links и version/phase filenames. Это проверка структуры, а не
   универсальный secret scanner или утверждённый deploy manifest.

## Выполненные проверки

| Проверка | Результат | Доказательство |
|---|---|---|
| Canonical gateway offline/locked test + build | PASS, 291 тест | `local/build/server/gateway-canonical-01/result.json` и test/build logs |
| Старый gateway entrypoint, те же core sources | PASS, 290 тестов | `local/build/server/gateway-legacy-01/result.json` |
| Canonical и старый C# build | PASS, 2 сборки | `local/build/server/physics-canonical-02/result.json`, `physics-legacy-02/result.json` |
| Два новых worker: ready, stop/forward/stop, EOF | PASS | `local/evidence/20261006-server-layout/worker-smoke-01/result.json` и JSONL |
| Python lifecycle/integration/capture | PASS, 50 тестов | `local/evidence/20261006-server-layout/python-tests-02/result.json` |
| Source layout negative checks | PASS, 7; SKIP, 1 | тот же receipt; symlink создание недоступно учётной записи Windows |
| Identity config, HTTP errors, CLI readiness/shutdown | PASS, 4 | `local/evidence/20261006-server-layout/identity-tests-02/result.json` |
| Итог layout/source/runtime сверки | PASS в рамках карточки | `local/evidence/20261006-server-layout/final-audit-02/result.json` |
| Новая native поездка / новый game profile | NOT_RUN | эта карточка не запускала клиент и не изменяла рабочие профили |
| Linux build / physics ABI / native remote вход | NOT_RUN | проверенного Linux runner/сервера для карточки нет |

**OBSERVED:** в двух worker smoke процессах совпали все четыре состояния на
одном Windows-хосте с одной геометрией и последовательностью команд. Это не
доказательство общей детерминированности физики или Windows/Linux идентичности.
Smoke не заменяет native приёмку движения, pivot или субъективной плавности.

Ранние неуспешные проверки сохранены: C# restore в `physics-canonical-01` и
`physics-legacy-01` использовал пустой default NuGet cache и завершился FAIL.
Драйвер исправлен на уже существующий project-local cache; успешные сборки —02.
Первый identity harness дал FAIL при завершении IPC дочернего процесса: HTTP
слушатель закрылся, но parent удерживал IPC pipe. Исправлен только harness;
`identity-tests-01` сохранён, `identity-tests-02` имеет 4 PASS.
Первый final collector также сохранил harness FAIL: он пытался читать старый
путь намеренно перенесённого C# source. Исправление отделило source relocation
от deployed artifact preservation; `final-audit-01/failure.json` сохранён,
проверка02 использует обе независимые группы доказательств.

## Что остаётся перед будущим удалённым сервером

**VERIFIED / ограничения:** структура `server/` пока не самодостаточный deploy
bundle. Fresh profile генератор читает проверенные client resources и местную
конфигурацию. Profile provenance привязан к source hashes, fixture/trace paths
в `local/evidence/`. Карты также имеют абсолютные пути к manifests/buffers.
Identity разделяет frozen реализацию с сайтом и encoders с `tools/`.

Native transport и redirect остаются loopback; поездка закреплена за тестовым
аккаунтом/profile4. Worker loader требует `.exe`. Живые SQLite базы имеют
текущую модель владения процессами; перенос/разделение между хостами не выполнены.
Перемещение этих inputs требует версии формата и миграции provenance, а не
замены всех строк путей. Независимый Linux runner/build/native ABI — **UNKNOWN**
до действительного выполнения. Открывать endpoints наружу автоматически нельзя.

Старые research readers `tools/retired_base_probe.py` и
`tools/verify_inprocess_relogin.py` содержат live reads старых Rust source paths.
Они не входят в приёмку этой карточки: их повтор на новом дереве **NOT_RUN**.
Исторические manifest keys, source pins и архивы не переписаны. Если такой
reader снова понадобится, его адаптация должна использовать `layout.json`
и отдельно проверять provenance. Дубликаты source ради старого reader запрещены.

## Команды и откат

Обычный запуск, status и сборка приведены в `server/README.md`. Быстрый повтор:

```powershell
python -B -X utf8 server/check_layout.py
python -B -X utf8 -m unittest discover -s tests -p test_service_lifecycle.py
python -B -X utf8 -m unittest discover -s tests -p test_map_drive_integration.py
python -B -X utf8 -m unittest discover -s tests -p test_map_drive_capture.py
python -B -X utf8 -m unittest discover -s tests -p test_server_layout.py
node --test tests/server_identity.test.mjs
python -B -X utf8 server/manage.py status --config local/server/service.json
```

Не использовать `git restore`: на старте рабочая папка была полностью untracked.
Точные source/docs backups лежат в `local/evidence/20261006-server-layout/before/`.
Откат восстанавливает исходные source/entrypoints/docs из проверенных копий и
удаляет только новые файлы карточки с совпавшими after hashes. Проверка без
изменений: `python -B -X utf8 local/evidence/20261006-server-layout/rollback_layout.py`.
Для применения отдельного source отката после штатной остановки собственного
backend: та же команда с `--apply`. Изменившиеся после приёмки файлы блокируют
откат. Клиент, deployed binaries, конфигурация и БД не откатываются этой утилитой;
изолированные build/evidence каталоги сохраняются.

Статус приёмки: **PASS_SERVER_SOURCE_LAYOUT**, без объявления Linux/deploy/native
readiness. Единственный рекомендуемый следующий шаг: отдельно версионировать
серверный контент и encoder/provenance inputs, чтобы генерация аккаунта перестала
зависеть от установленного клиента и каталогов исследовательских запусков.
