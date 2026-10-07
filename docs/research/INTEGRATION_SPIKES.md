# INTEGRATION_SPIKES — выполненные проверки

Дата: 2026-10-02. Run ID: `20261002-p00-p01`.
Этот документ сохраняет историю первого run. Текущее продолжение
`20261002-p01-bootstrap`: runtime/native rejection PASS, P01 принят как
исследование. [Новый отчёт и таблица checks](P01_BOOTSTRAP_AND_NATIVE_LOGIN.md).
Client content manifest SHA-256:
`74c37c18e9ac7e30196c134076dacf6f2a8bf3897f7def73905d09feb3647797`.
Версия исследовательского кода закреплена `code-manifest.json` в evidence;
Git-коммит отсутствует, поскольку Git identity не задана.
Точные команды: [REPRODUCE.md](REPRODUCE.md).

Все evidence paths ниже относительно `local/evidence/20261002-p00-p01/`.

| ID | Реально выполнено | Результат | Evidence |
|---|---|---|---|
| S00 | Сверка 20 файлов исходного пакета и backup | PASS | `local/baseline/package-check.json` (от корня проекта) |
| S01 | Полное хеширование обеих клиентских копий до/после | PASS, 3469/3469 файлов, отличий 0 | `baseline/`, `final-integrity/baseline-comparison.json` |
| S02 | Git ignore настоящих client/config/key/extraction paths | PASS | `git-ignore-check.txt`, `git-safety.json` |
| S03 | ZIP indexes, PE header, все pyc magic | PASS: 62 pkg, i386, 2255 pyc | `static/` |
| S04 | Bounded Packed XML + статическое чтение code records | PASS: 70 файлов | `decoded/sources.json`, `summary/` |
| S05 | Исторические модули/снаряды на настоящих данных | PASS: 128 mm = 6; 150 mm = 4; HESH = 275/275 | `summary/resource-facts.json`, `tests-final.log` |
| S06 | Одна collision-модель и chunk/cdata Прохоровки | PASS в пределах структурного анализа | `geometry/` |
| S07 | Сборка wg-toolkit CLI и локального login probe | PASS после настройки локального toolchain | `wg-build-mixed.log`, `wg-probe-build-verified.log` |
| S08 | wg-toolkit читает реальный T-34-85.xml и account.def | PASS | `wg-resources/`, `wg-resource-check.json` |
| S09 | wg-toolkit декодирует все байты vertex section 0.9.1 | **FAIL**: 7292/9700, остаток 2408 | `wg-geometry.log` |
| S10 | Три запуска diagnostic research client | **FAIL** ожидаемого diagnostic init; exit EXE 0 | `native-probe-01/`, `native-probe-02/`, `native-probe-03/outcome.json` |
| S11 | OS-трасса собственного client process | PASS как диагностика раннего выхода | `native-probe-02/windows-debug-events.json` |
| S12 | Runtime sys.version / mod marker | NOT_RUN: Python init не достигнут | `native-probe-03/outcome.json` |
| S13 | Родной login datagram, decode/ответ toolkit | NOT_RUN: получено 0 пакетов | `native-probe-03/capture.json`; backend реально bind 127.0.0.1:20015 |
| S14 | Backup → временная диагностика → откат | PASS, включая полный повтор SHA-256 | Все `patch-ledger.json`, `restore.json`; `final-integrity/` |
| S15 | Jolt API/ABI headless, 300 шагов по 1/60 s | PASS: 1 contact, final Y=0.4860385 | `physics-result.json`, `physics-build-final.log` |
| S16 | Python boundary tests + проверки настоящих ресурсов | PASS: 20 тестов (15 synthetic boundaries + 5 real data) | `tests-final.log` |
| S17 | Проверка закреплённых bootstrap prerequisites | PASS в данной среде | `bootstrap-check.log` |
| S18 | Развёртывание всего стенда на второй чистой машине | NOT_RUN | Такой запуск не выполнялся |
| S19 | Два клиента, арена, движение, звуки/UI, historical RNG | NOT_RUN | Вне завершённого среза; P02+ не начаты |

## wg-toolkit-rs

Закреплён commit **5b879f0b960ccb4a3b799ede952256e253ef74cb**;
подмодуль serde-pickle **bb098cafb6775604614000d58a885a72dd5c495f**.
Источник: [репозиторий на этом commit](https://github.com/theorzr/wg-toolkit-rs/tree/5b879f0b960ccb4a3b799ede952256e253ef74cb).
LICENSE — MIT, SHA-256 `1bfaee0781869e38c1efc2abbe4c37188960d043cd7e3bff06bd5e081e9a5988`.
Текст/ограничения: [THIRD_PARTY_NOTICES](../../THIRD_PARTY_NOTICES.md).

Исходники vendor не изменены. URL подмодуля изменён только в локальной Git
конфигурации с SSH на HTTPS. Основной lockfile сохранён в
`config/wg-toolkit.Cargo.lock`, probe имеет отдельный `tools/wg_probe/Cargo.lock`.

Среда: Rust/cargo 1.90.0 GNU; LLVM-MinGW 20250910 используется для dlltool,
линкер и GCC runtime libraries — из поставки Rust. Всё в `local/toolchains/`,
системный PATH не менялся. Первые попытки сборки не прошли: сначала не был
доступен dlltool, затем его assembler, затем LLVM linker не нашёл libgcc.
Финальная комбинация явно записана в `tools/rust_env.ps1`; все промежуточные
ошибки сохранены в `wg-build*.log`. Поздний одновременный build/run probe
дал Windows file-lock failure; последующая последовательная сборка успешна.

У toolkit есть реальные ресурсные функции, но blanket-совместимость 0.9.1
**не установлена**. У vertex decoder выявлена конкретная ошибка формата;
native-транспорт остаётся непроверенным. В upstream RSA decoder используется
`unwrap()` на ошибке расшифровки (`net/filter/rsa.rs`); сетевой hardening и
ресурсные лимиты требуют отдельного аудита до любого публичного применения.
Это локальный эксперимент, не готовый production gateway.

## Headless-физика

Собран собственный минимальный C# console spike на установленном SDK
**9.0.315**, runtime **9.0.17**, Windows 10.0.19045, x64.
NuGet: **JoltPhysicsSharp 2.22.0**, **JoltPhysics.Native 1.1.0**.
NuGet metadata закрепляет wrapper commit
`77a5be2dd30d587c1981dfcaf15851f18041b39c`, native joltc commit
`59f7d63ff7760981b771b6b161346fcc007f4dfd`; зависимости/хеши в packages.lock.json.
Дополнительно скачанный HEAD исходников wrapper
`3ab66bf9e970b10c2b22b8f5b88dfdc2c765a7fb` не является версией использованного пакета.

Проверены Foundation.Init, создание статической/динамической формы,
шаг simulation, контактный callback и устойчивое положение после падения.
Проверяется ошибка Update и конечность/допустимый диапазон позиции; это не
пустой вызов библиотеки. Финальная сборка: 0 warnings, 0 errors.

Наличие типа TrackedVehicleController подтверждено; управление гусеничной
машиной, импорт WoT mesh в Jolt, Linux/ARM, deterministic replay и физика
2014 года — **NOT_RUN**. .NET 10 SDK отсутствует; его запуск — **NOT_RUN**.
net9.0 выбран только для доступного исследовательского процесса и не
утверждает производственный стек проекта.

## Вывод первого run и последующее закрытие P01

В первом run P00 выполнен, P01 оставался частичным из-за bootstrap.
Продолжение воспроизвело early exit через instance mutex и подтвердило
runtime/compiled module. Получены настоящие login request и rejection reply,
расшифровка собственным ключом и правильный client callback, два штатных
повтора без debugger. Full login/arena NOT_RUN. По исследовательскому
критерию docs/03_ROADMAP.md P01 PASS; P02 NOT_STARTED.
Существующие FAIL toolkit сохранены, stock-совместимость не заявляется.

Следующий шаг один: отдельная карточка P02 — LoginSuccess/redirect и первый
BaseApp request на своём loopback endpoint. Общая арена пока не оценена по
измеренному полному контракту и не обещается на основании этого rejection.
