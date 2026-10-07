# Порядок в серверных исходниках

2026-10-06. Владелец уточнил: сейчас развёртывать сервер не нужно; нужно начать
наводить порядок в папках и названиях, чтобы не накопить проблемы будущего переноса.
Предполагаемая будущая ОС — Linux. Упаковка/доставка/портирование не входят в карточку.

## Цель и границы

Создать canonical `server/` для control, gateway и physics исходников; `tools/`
оставить исследованиям и совместимым старым точкам запуска. Не держать две
редактируемые копии одного runtime модуля. Клиент, patch, research evidence,
toolchains, базы, credentials и извлечённый контент остаются вне server/.

Текущий локальный native backend/сайт/клиент не перезапускаются и не изменяются.
Исторические frozen генераторы и source hashes сохраняются. Их перемещение
вместе с рабочими базами не маскируется простым переименованием путей.
Linux runtime acceptance — отдельный проверяемый результат; пока NOT_RUN.

## Выполнение

1. Зафиксировать before хеши рабочего кода/конфигураций и фактические PID.
2. Read-only аудит runtime путей, приватных inputs, платформенных ограничений.
3. Перенести bytes unchanged core Rust/C# в server/gateway и server/physics;
   старые Cargo/MSBuild entrypoints обращаются к тем же файлам. Старый P01 CLI
   остаётся research инструментом, обычный gateway имеет отдельный entrypoint.
4. Перенести control/lifecycle и сохранить импортные/CLI wrappers в tools/.
   Общая identity/portal часть остаётся frozen dependency до versioned migration;
   записать это явно, без массового нарушения provenance.
5. Добавить inventory/check layout и протестировать canonical+legacy commands,
   Cargo/MSBuild в отдельном output, не заменяя действующие binaries.
6. Зафиксировать будущие Linux/remote native blockers, результаты и неизменность
   действующего стенда; обновить README/STATUS/MISSING_INPUTS.

## Приёмка

PASS_SERVER_SOURCE_LAYOUT означает один источник runtime кода, явные границы,
рабочие новые/старые entrypoints и неизменность активного стенда. Это не deploy.
NOT_RUN: Linux compilation/physics/native удалённый вход без целевого Linux
host/runner. Не менять loopback policy автоматически и не импортировать живые
БД/клиентский контент. Не создавать production deploy/стрельбу/разрушение.

## Откат

Before копии source/docs в `local/evidence/20261006-server-layout/before/`.
Откат перемещений восстанавливает исходные файлы и убирает только новые wrappers/
canonical файлы после сверки хешей; активные binaries/config/state не меняются.
Любой будущий
перенос runtime/data потребует отдельной versioned migration и проверки.
