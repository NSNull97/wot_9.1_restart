# Ночной checkpoint — 2026-10-16, 07:15+05

Ветка `codex/p06t-mixed-shell-damage`, сохранённый HEAD
`c25fb84cf81a238e7b1410ccbd453d0a44a2c45f`. Main/origin `ffce8cb` не менялись.
Это продолжение 06:50; старый checkpoint о запущенном full04 устарел.

Full04 завершён: **1100 PASS / 0 FAIL / 5 прежних ignored / build PASS**,
340.80 с тестов, **692 файла исходников до/после совпали**. Доказательства:
`local/evidence/20261016-p06t-full04/source-{before,after}.json` и
`local/build/server/gateway-p06t-full04/result.json`. Exe SHA
`a2f7dea23dde083978fa6215fa721dc24639de2be76fb21693baf466696b908c`.
Tag `p06t-physics-20261016-01` закреплён на c25fb84. Freeze снят.

Сейчас активный маленький компонент: source caps для семи машин и шестое
место экипажа WT. Агент night_p05c_plan владеет caps/state/new v2 tests/new JSON.
Старые ALL5/исходные SHA остаются. State::new теперь fallible/v1-only,
State::new_v2 выбирает новую политику явно. Root адаптировал единственный
production caller через `?`, старые fixture callers — через unwrap, добавил
LF pins двух новых JSON. Тесты текущего WIP ещё NOT_RUN; Cargo не запущен.

Параллельно ONLY ignored: writer готовит отдельный TerminalPolicyV3/Frozen3,
истинный native encoding и disposable C/D через реальные research/buy.
Иностранный SQL hire/ammo и actual stand activation ещё не реализованы.
Protocol agent готовит source-bound combat geometry exporter WT/FV и план
AimEnvelope. Никаких активных geometry/World/VehicleKind7 правок пока нет.

Утренний core tag/stand не потерян: `p06t-core-20261016-01` = 9920a63,
full03 1096/5/build/683 exact. Mixed-01 binding-p06t02/V7 A/B уже установлены.
Два настоящих native hangar boot OBSERVED, UI/control/combat NOT_RUN.
A112/B29, оба MS1 [0 AP,4 HEAT,10 HE], reserves0. Все собственные процессы
остановлены. Команды и откат: mixed-01/MORNING-core.md; не повторять install,
выбирать core tag из чистого сохранённого checkout. Общий рабочий отчёт —
`docs/NIGHT_REPORT_20261016.md`.

Следующее: закончить новый leaf, focused gate, commit, затем full05 с чистыми
source-before/after. Не объявлять весь P06T принятым и не переходить к хвосту.
