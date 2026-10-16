# Ночь 16–17 октября: сервер до 09:00

Рабочий отчёт, обновляется по проверенным checkpoint. Окончание задания:
17.10.2026 09:00 Asia/Yekaterinburg (04:00 UTC). Ручные тесты выполняет
владелец утром. Отложенная native/UI/звук/управление приёмка остаётся NOT_RUN.
Main и сохранённые ночные ветки не заменяются непринятыми кандидатами.

## Сохранённая исходная точка

Main `ffce8cb660e9e6af6872aa4a5de444f461bc73fe`. Узкий natural P08C
checkpoint `1e87e1b`, проверенный runtime `46d5c20`: full1136PASS/5ignored/
buildPASS, 689 raw source files exact. Владелец подтвердил правильные личные
итоги и возврат обоих; wire/SQLite это подтверждают. Полная карточка P08C
пока не принята: capture/timeout/repeat/early-leaver fullresult открыты.

Старый стенд: `morning-autoaim01` в ignored mixed-01, оба клиента вернулись
в ангары. Принятая natural запись A126/[0,0,4],B41/[0,3,4] сохранена как
историческая. При новой подготовке actual SQL уже A127/[0,48,48],
B42/[0,50,46],active0; источник не изменялся. Старые клиенты/службы затем
остановлены только собственными PID/exe/creation receipts.

## P08C: поздние итоги — software checkpoint

Ветка `codex/p08c-late-owner-results`, runtimeea43262 от6289216.
Full1224PASS/0FAIL/5oldignored/buildPASS,740rawsourceexact,443.32s tests/
484.18s driver. Actual loss4 Runtime→JobLoss/Dispatcher→World final seal→HTTP/
SQLite→reopen/pending→1500/1501 PASS. Early A manual return и natural B используют
один sealed Results; append не выполняет второй inventory Finish. SQL17+1,
Web5+37, actualHTTP1+1 PASS0skip; focused34+1. Full01 FAIL1223/1/5 retained:
в test helper исправлен только explicit pool loader. Подробности/команды:
[P08C_LATE_OWNER_RESULTS](research/P08C_LATE_OWNER_RESULTS.md).

Evidence `local/evidence/20261017-p08c-late-full02/composition-full.json`,
exe e5310617717be1772e21f0a0d6d74297fad8c101d507551b2d6ea4211bcdaa0f.
Raw archive12667ffada762c40352aec7673a73d6e13ac80df81bde8a29126ea2e6ee9f60f.
Native notice0x4bINFERRED/defaultfalse, UI/UDP/Jolt composition NOT_RUN.
Crash beforeappend и изменённый parked actor не закрыты; для N>2 отдельно
проектируется заранее frozenHold5, старый contract4 не переосмысляется.
Mainffce8cb unchanged. Следующая отдельная ветка — seven+loss P06T integration,
затем typed loss4 P10B и NET-02; новый утренний binding ещё необходим.

## P08B: restart/warm/full/следующая CAS — software checkpoint

Ветка `codex/p08b-restart-cas-composition`, runtime7ff8b30 от BUILD-TEMP7d2252f.
Добавлен ordinary self-orchestrated regression, production поведение не менялось.
Actual HTTP/SQLite/Config RunOpen/Dispatcher/Job/Fresh проведены двумя child
процессами одного test exe. ReserveAP20 → restart/recoveryonce → unload19 →
Admit → authoredHP0 Finish/repair90 → warm2 → full1 → unload18/CASwire2.
SQL revision14→21, active0, consumedAP0, depotAP+2, ресурсы/crew/research/старые
строки неизменны. Это isolated test seed с explicit test-only grant100, не стенд.

Canonical `gateway-p08b-composition-full02 --cargo-temp-target`:1189PASS/0FAIL/
5oldignored/buildPASS,359.74s,716rawsourceexact. Focused04 1PASS/0ignored,
Node11PASS0skip. Exe1f7c998645b897dc22eca18e0873eacc2d23ed6f8644ffaea3947ac11f7d9b66.
Evidence `local/evidence/20261017-p08b-composition-full02/composition-full.json`
связывает actual result/rawmap/head/testexe с внешним fullgate; inner PENDING
receipt не изменялся. Full01/focused02/03 FAIL retained: нормализованы только
Node entrypoint/HERE/source paths Windows verbatim, production fences сохранены.
Откат7d2252f/test-only files, DB не менялась.

AP-only contract1 composition; syntheticSession/ACK/HP0, native/UI/UDP/death/
loss4 complete composition NOT_RUN. Mandatory native gates не закрыты, main
ffce8cb unchanged. Следующий шаг P08C conservative late results.

## Техническая предпосылка: место для сборок

Отдельная зависимая `codex/build-temp-cargo-target`, runtime0e970b7. Новый
явный `server/build.py gateway --test --cargo-temp-target --out
local/build/server/gateway-build-temp01` создал fresh Cargo target в C OS temp,
провёл full1188PASS/0FAIL/5oldignored/buildPASS (299.21s tests),713 raw source
before/after exact и экспортировал только проверенный exe19,599,083B на D.
ExeSHA60860207141afd2bdb00cfaf9436ca08c41d201238243b2cd97bb52f0a988d99
совпал до/после копии.11 Python guards PASS. Старые builds/evidence не удалялись,
обе новые папки сохраняются, deployed не заменён. Evidence
`local/evidence/20261016-build-temp01/source-after.json` и `actual-copy.json`.
Откат — build без флага; новый native/Linux/legacy/physics NOT_RUN.
В main не слито из-за непринятых игровых родителей. Следующий шаг P08B.

## P06T: детонация и потеря БК — автоматический checkpoint

Ветка `codex/p06t-ammo-rack-detonation` от `1e87e1b`; план
[P06T_AMMO_RACK_DETONATION](plans/P06T_AMMO_RACK_DETONATION.md).
Особое правило владельца: уничтоженный непустой AmmoBay убивает машину и
уничтожает все оставшиеся loaded stack, включая барабан; склад не меняется.
Пустой БК не детонирует. Это политика проекта, историческая точность не заявлена.

Новый opt-in contract4 `p06t-ammo-rack-loss.v1` замораживает отдельную
политику перед допуском. Frozen = fired + lost + remaining по каждому исходному
снаряду; shots = sum(fired). Старые v2 записи, source/terminal policy и результаты
не пересчитываются. Новый читатель различает архивы mixed-v2/loss-v1.

Применены отдельный причинный журнал, единая смерть/HP запись, native negative
health и DetachedTurret request/create/ACK/pose/leave. Plate Trace сохраняет
только исходный урон снаряда. Полёт башни — явно обозначенная серверная
баллистическая визуализация с проверкой исходного terrain; это не Jolt body и
не исследованная историческая модель импульса. Полёт не изменяет замороженные
HP/итоги после результата. Всё фактическое native исполнение новой механики
пока NOT_RUN.

Изменения сосредоточены в shared World/armament/native publication,
profile13 identity/session/dispatcher/results, отдельном SQLite writer/CLI
и private Web bridge. Новые cross-language fixtures получены из отдельных
SQLite тестов, без изменения игрового стенда и без выдачи имущества. Они
не являются доказательством сетевой игры.

Выполненная canonical проверка runtime `ed675319cc9b46a6bbff8e9ff9a411f7fb58f48a`:

```powershell
$env:RUST_TEST_THREADS='1'
$env:CARGO_INCREMENTAL='0'
$env:CARGO_PROFILE_DEV_DEBUG='0'
$env:CARGO_PROFILE_TEST_DEBUG='0'
python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-p06t-ammo-loss-full02
```

Full1188PASS/0FAIL/5oldignored/buildPASS;302.78s,712 raw source files before/
after exact. ExeSHA `3962811b78cd0cbcc9edc7ad3001f79e74835d94439d8071aa3b55226e72b9f8`.
Evidence — ignored `local/evidence/20261016-p06t-ammo-loss-full02/source-after.json`;
там же exact raw source archive для EOL rollback. Focused143PASS/0ignored;
SQL12+old15/actualHTTP1/Web13PASS0skip. Первый canonical01/diagnostic01 FAIL
сохранён: неверные test module paths и неполные test prerequisites исправлены
без ослабления production. Подробности —
[P06T_AMMO_RACK_LOSS](research/P06T_AMMO_RACK_LOSS.md).

Новый ignored стенд `local/stands/night-battle-20261017-01/loss-01`: consistent
backup game/web, отдельный token, действительная loss активация/publish,0grants,
неизменные исходные SQL rows/loaded/depot/revisions.161 resource checks и8guard
tests PASS. `binding-loss01.json` закрепляет full02. Actual `startup-loss01`
поднял5профилей/DETONATION_BOUND/BOUND. Actual startup-loss02 затем проверил
два own derived-corpus UDP Login и настоящие loss4 RunOpen A128→129/B42→43,
loaded/depot/crew/results/reservations unchanged,active0; оба own services
остановлены по receipts. Первый limiter-guard FAIL/partial A127→128 сохранены.
Native UI/Base attach и клиенты NOT_RUN. Точные команды/ограничения — ignored
`MORNING-full02.md`; новый актуальный остаток A[0,48,48]/B[0,50,46] при A129/B43.

Ограничение сохранности: committed finish/replay/relogin/restart сохраняют
потерю. При падении процесса до terminal commit старая явно сохранённая
политика aborted_restart возвращает первоначальный резерв один раз. Отдельный
per-shot WAL пока не реализован; более сильная crash durability не заявлена.

## Дальнейшие checkpoint

После auto gate продолжить P08B → P08C → P05C → P07B → P04M → P06T → P10B →
NET-02 → подготовка первого боевого теста, используя уже сохранённые реализации.
Каждую зависимую карточку вести отдельной веткой. Saved P06T `b9239e3` →
P10B `6c6b7b7` → NET `b6c294f` имеют общую с текущей линией базу `9920a63`.
Нельзя заменить нынешнее дерево старым: потеряются принятые marker/results/
autoaim исправления. P10B Saga пока V2-only; совместимость с новым loss4
требует явной реализации, а не переключения версии в JSON.

## Утренняя приёмка новой механики

Сценарий уточняется по финальному source-bound стенду; до его binding запуск
NOT_RUN. В существующие исторические БД ничего не дописывать задним числом.

1. Оба настоящих ангара, выбранные машины и исходные три stack записаны.
   Отмена очереди → повторная очередь → общий бой → движение/наведение.
2. Уничтожить непустую БК: HP0, один фраг, отрыв/движение башни и корректные
   эффекты у обоих. Проверить личные/командные итоги и оба возврата без black
   screen/выброса. Lost не увеличивает shots.
3. После возврата все оставшиеся loaded снаряды жертвы0; склад и выстрелы
   нападающего соответствуют журналу. После перезапуска/перезахода результат
   сохраняется. Повторный бой только с действительным БК из своего склада.
4. Отдельно проверить повреждённую, но не уничтоженную БК; затем пустую БК:
   одного нулевого deviceHP недостаточно для детонации пустой машины.
5. Проверить исчезновение/повторный засвет, выход/обрыв во время полёта,
   второй общий бой. UI/audio и фактические пакетные трассы оценить отдельно.

Откат: остановка только собственных receipt-owned процессов, переключение на
сохранённую ветку/проверенный binding и его прежнюю БД. Исходный mixed-01,
CoreV7 ledgers и оригинальный клиент сохраняются; loss-v1 БД изолирована,
старым writer её не обслуживать.

Статус приёмки: P06T автоматическая часть PASS, новая native механика NOT_RUN;
main без новых слияний. Текущий следующий шаг после сохранённых P08B/P08C — отдельная seven+loss
P06T integration ветка, затем P10B/NET и свежий утренний source binding.
