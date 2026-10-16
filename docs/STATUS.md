# Состояние проекта — 2026-10-17

Текущая P06T seven+loss integration завершила software checkpoint0e03e19:
full1295PASS/0FAIL/5oldignored/buildPASS/783rawsourceexact, focused5,
Python102PASS0skip. Ветка `codex/p06t-seven-loss-integration`.
[Факты](research/P06T_SEVEN_LOSS_INTEGRATION.md). Следующая P10B typed loss4.

Ночь продолжается до09:00 Asia/Yekaterinburg без ручных проверок. Сохранённая
ветка `codex/p08c-late-owner-results`, runtimeea43262: software checkpoint
**full1224PASS/0FAIL/5oldignored/buildPASS/740rawsourceexact**. Actual
HTTP/SQL/Dispatcher/World seal/reopen/pending/1500/1501 PASS; native/UI/звук/
gameplayUDP NOT_RUN. [Факты](research/P08C_LATE_OWNER_RESULTS.md).
Следующий ночной шаг — P10B typed loss4 integration, затем NET-02.

Main `ffce8cb660e9e6af6872aa4a5de444f461bc73fe` сохранён. Непринятые карточки
в отдельных зависимых ветках; отложенные ручные gates не подменяются PASS.
[ACTIVE_GATE](ACTIVE_GATE.md), [порядок](IMPLEMENTATION_ORDER.md),
[ночной отчёт](NIGHT_REPORT_20261017.md), [DEV_NOTES](DEV_NOTES.md).

## Проверенные ночные software checkpoints

| Ветка | Runtime | Реально выполнено |
|---|---|---|
| codex/p06t-ammo-rack-detonation | ed67531 | full1188/5/build; одна смерть/фраг, lost3/clip, depot untouched; SQL12+15/HTTP1/Web13 |
| codex/build-temp-cargo-target | 0e970b7 | full1188/5/build; C-temp→D exe SHA exact; Python11 |
| codex/p08b-restart-cas-composition | 7ff8b30 | full1189/5/build; actual AP-only restart/recovery/Fresh/warm2→full1→CAS2; Node11 |
| codex/p08c-late-owner-results | ea43262 | full1224/5/build; actual loss4 late composition; SQL17+1/Web5+37/HTTP1+1 |
| codex/p06t-seven-loss-integration | 0e03e19 | full1295/5/build; seven+loss boundaries5; Python102/source783 |

Все полные проверки имеют raw source before/after и сохранённые evidence.
Последний exeSHA e5310617717be1772e21f0a0d6d74297fad8c101d507551b2d6ea4211bcdaa0f.
Evidence `local/evidence/20261017-p08c-late-full02/composition-full.json`.

Loss policy проекта: уничтоженная непустая БК убивает машину и теряет весь
оставшийся loaded БК; fired и lost различаются, склад не меняется. Native
башня/FX/учёт после реального выстрела пока NOT_RUN. Консервативные late rows
не меняют старую inventory; parked damage после раннего возврата требует
нового future hold5 contract, не скрытой смены смысла старой версии4.

## Стенд и принятые владельцем факты

Все own службы/клиенты STOP. Изолированный loss-01 A129/B43, loaded
A[0,48,48]/B[0,50,46],active0/grants0. CoreV7 сохранён; его96immutable files
совпали. Binding-loss01 только дляed67531; новый runtime требует fresh binding.
Оригинальный клиент read-only, старые DB/builds/evidence не удалялись.

STAB-01 в main принят: выход обоих вручную, повторный бой, управление/наведение/
стрельба; ошибка закрывает бой, а не сервер. P08B native cycles18→16→14,
queue cancel/requeue подтверждены. P08C marker04 оба красных маркера и natural
autoaim06 личные итоги/возврат подтверждены владельцем; полная приёмка
P08B/P08C и последующей цепочки остаётся открытой.

Сохранённая предыдущая ночная цепочка: P05C019ed2f/full940, P07B8fecb9d/975,
P04M483bb2b/1006, seven P06T0f1db40/1162, P10Be55ba01/1397,
NET608bb23/1414; везде5oldignored/buildPASS на своих source heads. Эти старые
проверки не доказывают новую объединённую цепочку. Native mixed/6, visibility,
новые машины, training иtwo-PC NOT_RUN. Owned3 новых/WT/FV не включать без
qualification; временный seven LAB — отдельный explicit mode.

Полная история доступна в git; текущие исследовательские границы —
[research/INDEX](research/INDEX.md). Хвост после подготовки боевого теста:
микролаг, склад/оборудование/слоты/продажа, P04L, legacy/Python/rustfmt.
