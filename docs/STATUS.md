# Состояние проекта — 17 октября 2026, ночная работа до 09:00

Отдельная карточка codex/p10b-hold-selection-bridge отCLI63 ed53adde:
явный private Selection5 bridge с exact9/11/15 и FrozenHold3, fixed CLI63.
Первый actual HTTP2/C-D PASS97.101s, unit6 PASS; обычный committed-source
прогон ещё PENDING. Primary200/925 не менялся. Native Training5/полный935
NOT_RUN, никаких reserve/Ready/activation из Selection. Новые тесты сохраняют
свои DB/evidence и не меняют старые стенды.
[План](plans/P10B_HOLD_SELECTION_BRIDGE.md).

Отдельный следующий precursor: `codex/p10b-hold-selection-cli` от0472ddbc,
тот же независимый worktree. Добавлены только CLI5 и actual subprocess/SQLite
тесты; прежние reader56 четыре файла сохранены. Обычный committed-source прогон:
18PASS/0FAIL/0errors/0skips за200.682s на02c25d3/raw931, reader10+CLI8.
19 настоящих subprocess-вызовов, четыре владельца из двух attested seedDB,
реальный SQL trace/query_only/отказ DELETE, raw/logical DB без изменений.
Primary200/raw925/index/config и own931/HEAD/index до/после exact.
Evidence local/evidence/20261017-p10b-hold-selection-cli-01; full931 NOT_RUN.
Первый8PASS имел два test-only ResourceWarning; сохранён, closing исправлен,
финальный18PASS stderr чист. Web/Rust/native Ready5 остаются закрыты.
[План, конструкторная граница, команды и откат](plans/P10B_HOLD_SELECTION_CLI.md).

Отдельная карточка reader56: `codex/p10b-hold-selection-reader`, worktree
`C:/wot091-selection56/w`, base200dcd2. Один additive readonly Selection5 reader
и три test/vector файла; текущие Loss2/4 и training+Hold5 запрет сохранены.
Кандидат и обычный postcommit rerun: actual10 SQLite PASS/0FAIL/0skip,
AnchorA/OwnerB/C/D, query_only, raw import и WAL race. Rerun126.456s на
dbbda9e7/new929, HEAD/raw/index до/после exact; primary200/925/index не менялись.
Доказательства: `local/evidence/20261017-p10b-hold-selection-reader-01`,
31 byte-exact receipt/log files, без DB/assets/toolchains. Первый missing-config
FAIL сохранён; добавлен только ignored config1206B с исходным SHA/путями.
Это Python/SQLite precursor, без нового CLI/Web/Rust/native Ready/адмиссии.
Полный gateway929 NOT_RUN; прежние полные результаты ниже относятся к родителям.
[План, команды, ограничения, откат](plans/P10B_HOLD_SELECTION_READER.md).

Рабочая папка: `C:/wot091-night-20261017-01/w`. Исходный D сохранён: там
почти нет места. Main `ffce8cb660e9e6af6872aa4a5de444f461bc73fe` не менялся;
непринятые ночные карточки остаются в отдельных зависимых ветках.

Текущий checkpoint: `codex/p04m-garage-fresh-publication`, runtime471ac47.
**Полный gateway: 1619 PASS, 0 FAIL, 5 прежних ignored; сборка PASS,
923 исходных файла совпали побайтно.** Семь настоящих HTTP/SQLite compositions
из одного полного прогона запечатаны. Known garage reply сохраняется до
readonly Fresh и атомарного native delta; две actual Loss4/Hold5 CMD108 проверки
без повторной mutation прошли. [Факты и откат](research/P04M_GARAGE_FRESH_PUBLICATION.md).

Hold5 удерживает резерв вышедшего игрока до настоящего исхода. Crash до Final
по-прежнему использует явный aborted_restart из frozen-резерва; per-shot WAL
не реализован. Training+Hold5 запрещён: обычные комнаты работают в отдельном
Loss4-режиме. Нельзя открывать эту комбинацию простой сменой флага.

Складские ссылки реализованы в codex/p04w-shell-depot-display runtime722fcf9:
Python9+Web11 PASS/0skip,925raw exact; UI NOT_RUN, общий full после legacy.
[Файлы, исходные цены, evidence, откат](research/P04W_SHELL_DEPOT_DISPLAY.md).
Legacy-входы исправлены в codex/build-legacy-entrypoints runtime64767ec:
gateway3/0/0 иphysics build PASS, настоящий stock+extended IPC7 smoke PASS,
925raw exact. [Команды и ограничения](research/BUILD_LEGACY_ENTRYPOINTS.md).
Сейчас финальный общий full, затем новые утренние стенды и полный Python-набор.

Native/UI/звук/управление/шесть живых клиентов/два ПК новых сборок — NOT_RUN.
Утренние helpers31/34 прошли только input-preflight родителя7595f3f; фактические
backup/activation/bind/install/services/client для нового checkpoint ещё NOT_RUN.
Ночь продолжается до 04:00 UTC / 09:00 местного времени без ручных вопросов.
