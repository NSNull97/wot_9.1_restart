# Внешние репозитории для P00–P01: WoT decompile, BigWorld OSE и WoT 0.8.2 offline

Дата проверки: 2026-10-07 (UTC+5, рабочая копия проекта). Проверены общедоступные GitHub-деревья и закреплённые исходники; оригинальный WoT-клиент и внешние серверы не запускались.

## Итог для принятия решения

Ни один из трёх репозиториев не является готовым сервером для клиента WoT 0.9.1 и не закрывает native transport/login/arena compatibility. Декомпиляция 0.9.2 годится только как справочник имён и скелета клиентских обработчиков; BigWorld OSE — как справочный материал по общей серверной декомпозиции, entity definitions, сетевым каналам и физическим примитивам; `WoT-0.8.2-offline-Battles` — как источник исследовательских гипотез о старом Python-клиенте и client-side механиках 0.8.2. Последний является локальным модом с ботами, а не сетевым сервером.

До подтверждения на закреплённом 0.9.1-клиенте нельзя переносить из этих репозиториев имена методов, ID, сериализаторы, тайминги, физику, броню или экономические формулы. Использование кода BigWorld или offline-мода в production требует отдельного provenance/license review.

## WorldOfTanks-Decompiled

**Идентификатор источника.** Репозиторий `StranikS-Scan/WorldOfTanks-Decompiled`, проверенная ветка `0.9.2`, commit `ba6f98be9b2d176ec9def4dbdf76041e5b79f589`. Ветки `0.9.1` в опубликованном списке refs нет; default branch указывает на современный клиент, поэтому использовать URL без ветки нельзя.

**VERIFIED.** README описывает архив распакованных/decompiled файлов WoT и отдельные ветки по версиям. В ветке `0.9.2` дерево содержит только `source/` с Python-декомпиляцией (1086 файлов); XML, entity `.def`, `paths.xml`, `version.xml`, геометрия и полный ресурсный пакет в этой ветке отсутствуют. Сам README заявляет Python-файлы начиная с 0.9.2 и XML начиная с 0.9.12 — это не полный снимок target-клиента 0.9.1.

**OBSERVED.** Статический разбор 0.9.2 даёт полезные направления поиска: `BigWorld.connect`/`ConnectionManager`, группы `AccountCommands`, диапазоны stream IDs, `ARENA_UPDATE`, вызовы Avatar `vehicle_moveWith`, `vehicle_shoot`, `vehicle_changeSetting`, `setClientReady` и `leaveArena`. Это наблюдения другого патча и декомпилятора; ошибки декомпиляции и изменения API между 0.9.2 и 0.9.1 возможны.

**Лицензия и происхождение.** В корне/README ветки нет COPYING/NOTICE/license, а содержимое представляет декомпилированный клиентский код и инструменты PjOrion/Uncompile6. Статус `REFERENCE_ONLY/TAINTED`; исходники, zip, бинарники и производные файлы в наш репозиторий не копировать. Разрешены только URL, pinned SHA, хеши и независимый конспект гипотез с обязательной сверкой по локальному 0.9.1 trace.

**Решение.** Не использовать как source of truth для R01–R22 и не назначать по нему native method IDs/сериализаторы. Добавить каждую полезную гипотезу в `docs/research/KNOWN_UNKNOWNS.md` со статусом `INFERRED`, затем закрывать её только наблюдением exact 0.9.1 клиента.

## BigWorld-Engine-14.4.1

**Идентификатор источника.** [Репозиторий `v2v3v4/BigWorld-Engine-14.4.1`](https://github.com/v2v3v4/BigWorld-Engine-14.4.1), ветка `main`, проверенный commit `3d3cc16ae60bb1d71cb014e9b0539e54e6d8c4fb` ([tree](https://github.com/v2v3v4/BigWorld-Engine-14.4.1/tree/3d3cc16ae60bb1d71cb014e9b0539e54e6d8c4fb)).

**VERIFIED.** README описывает BigWorld Open-Source Edition (2014) как комплект server/client/tools для MMO; заявлены C/C++, Python, CentOS и функции load-balancing, scalability, fault tolerance. Указанные зависимости: Windows 10 с WSL2/Hyper-V, CentOS 7, Visual Studio 2019–2022, Vagrant, Docker. В корне есть Server Installation Guide, Server Build Guide и Whitepaper (PDF), `programming/bigworld`, `programming/fantasydemo`, RPM `bigworld-bwmachined-14.4.1.el7.x86_64.rpm`, `LICENSE`, `THIRD-PARTY-NOTICES`.

Полное дерево содержит 39 165 записей (без усечения): 819 файлов в `programming/bigworld/server`, 3 861 в `lib`, 172 в `client`, 574 в `examples`, 558 в `build` и 29 298 в `third_party`. Серверные цели разбиты на `baseapp`, `baseappmgr`, `cellapp`, `cellappmgr`, `dbapp`, `dbappmgr`, `loginapp`, `reviver` и tools. Библиотека `lib/network` содержит framing/channel/bundle/TCP/UDP/encryption/compression primitives; `lib/entitydef` — типы данных, свойства, методы и `.def`-модель; `lib/physics2` — BSP/hull/world triangles/quadtree/materials; examples содержат `entity_defs/*.def`, Python scripts и `res/server/bw.xml`.

Корневой CMake требует запуск с `BW_CMAKE_TARGET`, минимум CMake 2.8.12 и исторические MSVC tokens (9–14); без remote build код явно ограничивает платформу Windows. Это исходники и инструменты BigWorld OSE со своим клиентским протоколом и своим runtime, не код WoT.

**Лицензия.** [`LICENSE`](https://raw.githubusercontent.com/v2v3v4/BigWorld-Engine-14.4.1/3d3cc16ae60bb1d71cb014e9b0539e54e6d8c4fb/LICENSE) содержит MIT-подобное разрешение BigWorld Pty Ltd (1999–2014); GitHub помечает репозиторий MIT-0. Однако [`THIRD-PARTY-NOTICES`](https://raw.githubusercontent.com/v2v3v4/BigWorld-Engine-14.4.1/3d3cc16ae60bb1d71cb014e9b0539e54e6d8c4fb/THIRD-PARTY-NOTICES) — самостоятельный набор условий: CppUnitLite2 (MIT с дополнительным запретом военных применений/финансирования), Curl, JsonCpp, MongoDB C++ Driver, NedAlloc, NvMeshrender, Nvtt, Openautomate SDK, OpenSSL, pnglib, Python, RE2, Recast Navigation, SQLite3, WTL, zlib. Нельзя считать весь tree чистым MIT и нельзя тащить bundled third-party без SBOM и сохранения уведомлений.

**OBSERVED.** В публичном tree есть большой объём third-party и исторические build artefacts/RPM; локальная сборка не выполнялась. README не доказывает, что репозиторий собирается современным SDK или что его сервер принимает WoT 0.9.1.

**INFERRED.** Его правильная роль в нашем проекте — reference-only: заимствовать идеи границ Base/Cell/DB/Login, шаблоны `.def`, bounded network primitives и тестовую организацию после отдельной проверки. Прямая интеграция создаст второй runtime/protocol и размоет native-путь. `CppUnitLite2` лучше не включать даже в исследовательский продукт из-за ограничения лицензии; заменить собственным тестовым раннером.

**UNKNOWN.** Точная версия BigWorld, на которой построен клиент WoT 0.9.1; соответствие WoT-методам/aliases; фактическая сборка на текущей машине; полная лицензия каждого файла third-party; пригодность RPM. Ответить можно только отдельным pinned-SHA license/SBOM audit и build-smoke без подключения к внешним серверам.

## WoT-0.8.2-offline-Battles

**Идентификатор источника.** [Репозиторий `fr3asikx/WoT-0.8.2-offline-Battles`](https://github.com/fr3asikx/WoT-0.8.2-offline-Battles), ветка `main`, проверенный commit `85450aaedf9accdf687f6b5819dd11a5898026ea` ([tree](https://github.com/fr3asikx/WoT-0.8.2-offline-Battles/tree/85450aaedf9accdf687f6b5819dd11a5898026ea)).

**VERIFIED.** README прямо называет проект offline-модификацией клиента WoT 0.8.2: файлы `scripts` копируются в `res_mods/0.8.2/`; серверная часть BigWorld, сетевой multiplayer-протокол и обход официальной авторизации отсутствуют; вызовы мокируются на клиенте, login перенаправляется в локальный Manager, gold/credits/XP живут только в локальной сессии. Исходный репозиторий не содержит `.exe`, моделей, текстур, звуков и иных оригинальных игровых ресурсов; права на WoT assets/trademark заявлены за Wargaming/Lesta.

Дерево содержит 307 записей (296 blobs): 37 `.py`, 34 `.pyc`, 218 небольших `.dds/.png` и `Patchnotes.txt`, `LICENSE`, `Installation-Linux`. Основные файлы: `scripts/client/gui/mods/mod_offhangar.py` (34 KB), `offhangar/offline_battle.py` (773 KB), `internal_layout_profiles.py` (538 KB), `internal_layout_debug.py` (106 KB), `internal_hit_layouts.py` (72 KB), `bot_routes.py` (65 KB), `nav_grid.py` (55 KB), `device_damage.py` (36 KB), `internal_geometry.py` (36 KB), `physics.py` (29 KB), `battle_economy.py`, `battle_ledger.py`, `destructibles_authority.py`, `server.py` и tools.

`server.py` — `FakeServer`, который маршрутизирует локальные `AccountCommands` и планирует Python callbacks с `cPickle`; сокетов и transport framing нет. `offline_battle.py` создаёт локальные mock entities, bots, aim/ballistics, visibility, module/device damage, sounds and destructibles. `physics.py` помечает параметры как извлечённые из `scripts/common/physics_shared.pyc` клиента 0.8.2; это полезный lead для исторического сравнения, не доказательство 0.9.1. Исходники используют Python 2 idioms (`cPickle`, `execfile`, `__nonzero__`); patchnotes требуют embedded Python 2.6 для регенерации `.pyc`.

В дереве отсутствуют тестовые файлы/CI; README и Patchnotes — описание автора, а не независимая совместимость. Запуск не выполнялся: нужен отдельный 0.8.2 клиент, которого нельзя смешивать с закреплённым оригиналом 0.9.1.

**Лицензия.** Репозиторий публикуется под [GPLv3](https://raw.githubusercontent.com/fr3asikx/WoT-0.8.2-offline-Battles/85450aaedf9accdf687f6b5819dd11a5898026ea/LICENSE) и сообщает, что содержит код `SigmaTel71/mod_offhangar_legacy` также под GPLv3. Это copyleft: при распространении производных частей нужно сохранить GPLv3-условия и corresponding source. Происхождение каждой из 37 `.py`, 34 `.pyc` и 218 icon-assets не проверялось; `.pyc` нельзя считать независимым разрешением. WG/Lesta game assets не входят в исходный tree, но мод обращается к ним при запуске клиента.

**OBSERVED.** Это существенно более поздняя рабочая модификация (Patchnotes 2026) поверх исторического 0.8.2 API; на страницах проекта нет доказательства совместимости с 0.9.1.

**INFERRED.** Для P00–P01 разумно использовать только read-only разбор: порядок загрузки `res_mods`, Python 2 import/injection, названия клиентских подсистем, карта зависимостей для physics/ballistics/device damage/map destructibles и как оформлять observation logs. Нельзя переносить `FakeServer`, offline bots или client-owned HP/positions в авторитетный gateway; это противоречит проектным правилам.

**UNKNOWN.** Реальная работоспособность на конкретной версии 0.8.2 без её клиента; переносимость на 0.9.1; происхождение всех source/pyc/assets; соответствие заявленных формул и модульных коэффициентов историческому серверу; юридическая совместимость с планами распространения проекта.

## Матрица применимости к P00–P01

| Направление | WoT decompiled 0.9.2 | BigWorld OSE | WoT 0.8.2 offline | Решение |
|---|---|---|---|---|
| R01–R03: билд/регион/loader | Нет 0.9.1; только branch metadata | Только общая документация OSE | Наблюдения Python 2/res_mods 0.8.2 | Не заменяет аудит 0.9.1 |
| R04–R07: entity defs/transport | Имена/скелет, но нет `.def` и wire proof | Сильный reference для `.def`, channels, packet code | Нет native transport | Использовать как гипотезы, не dependency |
| R08–R10: arena/movement | Client callbacks/enum hints | OSE-семантика не WoT | Клиентская локальная арена/bots | Только поведенческие наблюдения |
| R11–R17: modules/armor/physics/rules | Не target patch, без ресурсного source of truth | Общие engine primitives | Ближе к WoT 0.8.2 client-side formulas | Перепроверить против 0.9.1 inputs и native traces |
| R18: headless physics | Не применимо напрямую | Есть physics2 source, старый C++ stack | Есть Python physics helper | Отдельный benchmark; не обещает WoT identity |
| R19–R22: toolkit/native/security | Нет gateway/auth/license | Не относится к WoT protocol | Нет gateway/auth | Не использовать для acceptance |

## Рекомендуемый порядок работы с источниками

1. Зафиксировать URL, SHA, дату и локальный hash snapshot в evidence-index; исходники внешних репозиториев не помещать в production tree.
2. Для BigWorld сделать только license/SBOM и compile-smoke выбранной библиотеки, без запуска клиентского/внешнего endpoint; исключить CppUnitLite2 из продукта.
3. Для offline-мода провести static read-only index: import graph, Python version markers, named data paths и claims, затем занести каждую гипотезу в `KNOWN_UNKNOWNS.md` как `INFERRED`.
4. Каждое число/метод из decompiled 0.9.2 или offline 0.8.2 принять только после сравнения с exact WoT 0.9.1 client resources/trace. Native packet, login, arena and entity acceptance по-прежнему требуют собственных локальных captures.
5. Перед любым кодовым reuse провести provenance record и решение по лицензии; при сомнении использовать идею как reference и переписать собственную реализацию по независимой спецификации.

## Отчёт выполнения

- Цель: оценить три внешних репозитория для P00–P01.
- Изменённые файлы проекта: этот отчёт.
- Команды: GitHub tree API/`Invoke-WebRequest` для pinned commit, `git ls-remote` для HEAD; локальные клиент/серверы не подключались.
- Тесты: NOT_RUN (ни один клиент/BigWorld build не запускался).
- Доказательства: URL и SHAs в разделах выше; tree snapshots сохранялись во временную директорию `C:\Users\NSNull\AppData\Local\Temp\wot-offline-files` и `bigworld-tree.json`.
- Неподтверждённое: native WoT 0.9.1 совместимость, переносимость механик и полная лицензия вложенных компонентов.
- Ограничения: проверены только public GitHub sources; нельзя считать README независимым техническим доказательством.
- Откат: удалить этот Markdown-файл; внешние временные snapshots не входят в репозиторий.
- Статус приёмки: PASS_RESEARCH_ONLY; production reuse NOT_APPROVED.
- Единственный следующий шаг: привязать выводы к `docs/research/KNOWN_UNKNOWNS.md`/`docs/evidence-index` и продолжить собственный R01–R07 аудит exact 0.9.1 client.
