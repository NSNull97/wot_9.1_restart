# P08C — сохранённые итоги вернувшегося владельца

Software checkpoint 2026-10-17: `codex/p08c-late-owner-results`, runtime
`ea4326291fbe76a5e2ab64250f4bca6b0322be00`. Родитель6289216 сохранён;
mainffce8cb не менялся. Полная native приёмка карточки не завершена.

## VERIFIED: что делает сервер

Actual owned admission связывается с immutable owner/run/arena/reservation/
Frozen/slot/session. Capture живёт вне Session, содержит не более6 участников
и получает release proof только из настоящего Finished completion. Один общий
Results Arc замораживается по настоящему Outcome до World reset; естественные
итоги оставшегося игрока используют тот же объект. Detached actor не теряет
premature_leave при последующем detach других машин.

Отдельный contract `p08c-late-result-append.v1`, policySHA
`f6ae697fb920b9359a2cb0375aa1fd68538a183fab1c8f136772c703de6abe04`,
добавляет только presentation row в новом SQLite namespace. Точный release
stamp читается из уже завершённого исходного резерва. Повторный inventory
Finish, изменение расходов, ревизии, склада или ремонта не выполняются.
Append разрешён только для одинакового release/final actor: HP, экипаж,
устройства, пожар, remaining/fired/lost и причинная запись детонации.
Изменённый parked actor получает `LATE_ACTOR_STATE_CHANGED`.

Reader сохраняет старые mixed/loss archives и record_contract; query1500 и
настоящий ACK1501 работают с новыми строками. Общий command-key fence старого
и нового ACK предотвращает повторное использование ключа с другим payload.
Выбранный battle factory тоже использует новый facade: новый run не может
завершить другой резерв с уже занятым owner+arena cache key. Pending discovery
читает только committed строки, по8 за страницу, не подтверждает их чтением.

Registry bounded8, необратимо неоднозначный active worker не вытесняется.
Точный immutable HTTP task повторяется после транспортной неоднозначности;
локальная детерминированная ошибка завершает только этого владельца. Перед
join проверяется фактическое завершение worker thread. Лимит уведомлений не
останавливает discovery остальных владельцев.

## Выполненные проверки и доказательства

- Runtime332ea1a: focused34 PASS/0FAIL/0ignored/buildPASS,729rawsourceexact.
- Writer9b4124e: actual SQLite17, Web5, actualHTTP1 PASS/0skip. Evidence
  `local/evidence/20261017-p08c-late-active01/source-after.json`.
- Battle facade09/d9f9e13: SQLite1 с двумя mixed2/loss4 подслучаями и
  actualHTTP1 PASS/0skip; новая arena collision отклоняется атомарно, cancel
  и fresh-arena natural Finish остаются рабочими. Evidence
  `local/evidence/20261017-p08c-late-active02/source-after.json`.
- Веб-регрессия на том же production source:37 PASS/0FAIL/0skip, включая
  actual AP-only/loss4/results/auth/registration и Windows verbatim guards.
  Evidence `local/evidence/20261017-p08c-late-web-regression02/source-after.json`.
- Actual Runtime→HTTP→SQLite composition06: focused1 PASS/0ignored/buildPASS;
  actual JobLoss admission2/Finish2, manual A→Forfeit B, same sealed Results,
  reset, bridge reopen, fresh empty-memory discovery, query1500/ACK1501.
  Два SQL barriers доказывают неизменность всех старых строк во время append/
  query/ACK. Source DB untouched. Synthetic Session/ACK/terrain/clock явно
  authored; HP/death/Finished/result receipts не подделывались.
- Canonical full02 наea43262: **1224 PASS/0FAIL/5oldignored/buildPASS**,
  740rawsourcefiles exact до/после; test443.32s, весь driver484.18s.
  `local/evidence/20261017-p08c-late-full02/composition-full.json` связывает
  настоящий дочерний result с завершённым full gate, raw archive и exe.
  ExeSHA `e5310617717be1772e21f0a0d6d74297fad8c101d507551b2d6ea4211bcdaa0f`.
  Raw archiveSHA `12667ffada762c40352aec7673a73d6e13ac80df81bde8a29126ea2e6ee9f60f`.

Команда полного запуска, output всегда свежий:

```powershell
$env:RUST_TEST_THREADS='1'
$env:CARGO_INCREMENTAL='0'
$env:CARGO_PROFILE_DEV_DEBUG='0'
$env:CARGO_PROFILE_TEST_DEBUG='0'
python -B -X utf8 server/build.py gateway --test --cargo-temp-target --out local/build/server/gateway-p08c-late-full02
```

Первый full01 сохранил FAIL1223/1/5: новый test helper использовал
load_research для actual pool fixture. Исправлен только на production
load_p04m + explicit config guard; metadata_research оставлен как в production.
Первый Web regression сохранил25PASS/2NOT_RUN: явно заданы уже проверенные
local descriptors/actual writer vectors и TAP reporter, затем37PASS/0skip.
Первый facade HTTP string assertion сохраняется в ignored candidate09:
старый natural archive использует ASCII escape, production не менялся.

## INFERRED / UNKNOWN / NOT_RUN

Native notice0x4b основан на original primitive schema, но mapping остаётся
INFERRED_STATIC_ONLY. Отдельный experimental flag defaultfalse; отправка
байтов в synthetic Window не доказывает UI и не заменяет ACK1501.
Нативные popup/button/1500 цепочка, UDP gameplay, звук и Jolt в новой
composition — NOT_RUN. Native/core маркеры и natural return ранее приняты
владельцем только в объёме отдельного checkpoint1e87e1b.

До первого committed append seal находится в памяти; crash до него или
между owner appends не восстанавливает отсутствующие строки. Сохранённые
pending rows переживают reopen. Повреждение parked actor после раннего Finish
не пересчитывает старую inventory строку; это известная граница, требующая
нового заранее замороженного hold5 reserve contract для N>2. Текущий мир
повторно войти в уже начатый бой не позволяет; отдельный multi-battle exploit
этим исследованием не установлен.

## Откат и следующий шаг

До первой late row можно выключить flags. После committed строки новый
reader обязателен даже для acked history: config-off startup отказывает.
Не восстанавливать старую DB поверх новой и не возвращать потраченный БК.
Runtime6289216 требует совместимого нового reader, а не молчаливой потери
истории. Изолированные test copies не меняли рабочие игровые DB/клиенты.

Software checkpoint PASS; native/card acceptance NOT_RUN, main не merge.
Следующий ночной шаг — отдельная зависимая P06T ветка: normal merge сохранённых
seven-profile изменений с текущим loss4/late-results и новый current-head gate.
