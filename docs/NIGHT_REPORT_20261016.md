# Ночная реализация 2026-10-16 — утренняя приёмка

Цель — выполнить утверждённый порядок без остановок на ручные проверки,
сохранить отдельные ветки, реальные доказательства и точный запуск на утро.
Main/origin SHA `ffce8cb660e9e6af6872aa4a5de444f461bc73fe` не менялся.
STAB-01 принята; следующие карточки остаются вне main до обязательной приёмки.
Прежние промежуточные отчёты/FAIL сохранены в git и local evidence.

Последний программный checkpoint — **NET-02 runtime608bb23**, полный
**1414PASS/0FAIL/5oldignored/buildPASS**,542.04с,794source files exact до/после.
Tag `net02-private-lan-20261016-01`, exe SHA256
`28e9589f0bfa88cf9d0ec821f8989582dbab201ccc64e71a5035616348cd3f0b`.
Actual ownhost Login/Base/Account/room/Ready/Leave PASS45.391с, ownstop PASS.
Native двух ПК, firewall и hosting ещё NOT_RUN. Первый боевой тест пока не принят.
Стабильная копия этого отчёта вне переключаемого checkout —
`local/stands/night-battle-20261016-01/MORNING-ALL-CARDS-20261016-02.md`.
Предыдущая стабильная копия без suffix02 сохранена как исторический checkpoint.

Оба установленных клиента по-прежнему **coreV7**; их ledgers/nonmutable файлы
сверены, rollback не выполнялся. Родные hangar/cache/model core наблюдались,
его новый бой/UI/управление ещё NOT_RUN. Собственные предыдущие core/extended/
P10B процессы остановлены по receipts; чужой p09e стенд не трогался.

## Сохранённые ветки и фактические gates

Все значения gateway ниже — PASS/build, с пятью прежними ignored.
Это автоматические проверки конкретных runtime, не принятие native/UI.

| Карточка | Ветка / docs head | Проверенный runtime | Что остаётся утром |
|---|---|---|---|
| STAB-01 | main `ffce8cb` | `0574ab0`,854tests; actual fault containment; owner два manualleave/repeat/управление | Принята; редкие physics deadlines остаются отдельным долгом |
| P08B | `codex/p08b-profile13-battle` / `c7999e6` | `5c08ef5`,893tests; owner18→16→14,8shots/4manualleave, cancel/requeue; actual restartrefund14/nativehangars | Postrestart, mutation/warmN→full1, refusal/ИС7 |
| P08C | `codex/p08c-battle-lifecycle` / `2ef781f` | `8c96580`,919tests; countdown/capture/outcome/results writer | Native countdown/исход/гибель/итоги/audio |
| P05C | `codex/p05c-shared-physics` / `9f2df41` | `019ed2f`,940tests/602exact; actual one scene2/6/mixed/scalar/ACK | Native mixed contact/6clients; HP тарана не реализован |
| P07B | `codex/p07b-server-visibility` / `e711844` | `8fecb9d`,975tests/607exact; actual terrain LOS/packet absence/epochs | Native hide/respot; bush/camo/radio/delay отсутствуют |
| P04M | `codex/p04m-five-battle-profiles` / `2340236` | `483bb2b`,1006tests/634exact; five profiles/real Jolt/new3 | Native T-26/T-34/T-34-85 qualification; admissionfalse |
| P06T | `codex/p06t-mixed-shell-damage` / `b9239e3` | core`9920a63`,1096/683exact; World7`0f1db40`,1162/725exact | Typed ammo/effects/modules/crew/fire; WT/FV qualification; ownedV3 live path отсутствует |
| P10B | `codex/p10b-native-training-room` / `6c6b7b7` | `e55ba01`,1397tests/785exact; actual socket Ready2, Admit2→prestartdisconnect→Finished2→новая комната | Native room/Account→Avatar/start/control/return/repeat/6players |
| NET-02 | `codex/net-02-private-lan` / runtime`608bb23` |1414tests/794exact; native LAN policy/allowlist/redirect/client policy | Ownhost actual45.391с PASS; real native/twoPC/firewall/hosting NOT_RUN |

Теги: core `p06t-core-20261016-01`; WT/FV `p06t-world-seven-20261016-01`;
P10B `p10b-host-20261016-02`; NET-02 `net02-private-lan-20261016-01`.
P10B старый tag `p10b-host-20261016-01` содержит full04 до Python bootstrap fix.

## Что изменено и действительно проверено

P08B/P08C соединяют owned profile13→резерв→бой→durable результат→ангар;
P05C использует один Jolt world на бой, P07B фильтрует скрытые состояния на
сервере. P04M добавляет пять source-bound боевых видов. P06T: per-stack
AP/HEAT/APCR/HE, reload/clip, source mesh и terrain LOS splash, module/crew
proxy/fire, единые HP/death/результаты. WT128 clip6/2с/reload60 и FV183 HESH275
связаны с original #717. LAB приближения не объявлены исторической точностью.
OwnedV3 имеет29SQL/source checks, но live factory/cacheACK/ownedWTstock не подключён.

P10B: bounded room/domain/aliases/streams200/201, exact Session generations,
HTTP/SQL readonly Ready, checked rebase, TeamPlan, serial Preparing reserve/
compensation, Account-stage final411→launchcommit, retained selected/bench,
actual Finished до claim release. Garage/results errors используют тот же
retirement boundary. Native VERSION8 подготовлен; сейчас не установлен.

Actual P10B stand02 binding-room02.json:

- Minimum `room-startup02`: обе Login/Base/Account/run_open, Create/Join, две
  HTTP/SQL Ready, Assign, noncreator refusal, оба Leave/recreate PASS. No reserves.
  Receipt SHA `d48564867b1de2cd9ac602056e7e95bd5aa20b8b444e135a2a93bd58c81bc594`.
- `room-durable01`: actual Admit2→final411/launchcommit→оба обычных logout за
  5.750мс→training_prestart_disconnect до Worldstart→actual Finished2 PASS.
  Exact SQL Admit/Finish/Frozen/CAS/journal chains, reason battle_failure,
  no Cancel/aborted_restart. Повторный Login/новая комната в том же gateway PASS.
  Receipt SHA `438463647cc95ab24f63f9f81b1625bb2beb1fffd56f67ed5a6e1fb0391bd9b6`.
- Итог C43/D44, MS1[AP0,HEAT4,HE10],active0,HP90,credits/XP0, old history exact.
  Snapshot startedfalse/tick1000, shots/projectiles/damage/device/RNG0.
  Это проверяет prestart failure; Avatar/Worldstart не проверялись.

NET-02: explicit game_network version1/lan_test, canonical RFC1918 endpoints,
один host/разные Login/Base ports, exact advertisedBase,1..24 unique /32.
Private HTTP остаётся127.0.0.1. Config streaming visitor сохраняет nested
ключи-дубликаты,4096/top23/HTTP16/fixture64 bounds прежние. Все12 loaders и
common entrypoints fenced; first Base проверяет IP authenticated Login при
сохранении token/key/live peer/retirement. Allowlist до rate/capture/crypto,
aggregate256/s сохранён. Client lan-test-v1 сохраняет original dispatcher и
exact submitted host; LAN registration пустой URL, собственные готовые accounts.

Actual NET02 focused17/build, full1414/build, client CPython273auth6/network9/
training15/mapdrive61PASS/3oldhostskips. Host mapdrive64/manualrunner14/replay59
PASS; prepare5/compile3 и Node private network/identity/portal7PASS/0skip.
Actual NET ownhost02: оба Login с собственного LAN-IP→точный advertisedBase→
Account/run_open→Create/Join→две HTTP/SQL Ready→оба Leave/retire PASS45.391с.
NET DB C44/D45, ammo[0,4,10]/active0; source P10B43/44 raw+logical unchanged.
Windows listener check: UDP на выбранном RFC1918IP20240/20241, единственный
bridgeTCP127.0.0.1:3492. Это не проверка доступности сB. Оба процесса ownstopped.
Receipt SHA `7ca2881a23c442f683e9a62eafb7b191faabc3ffbf760182d8a9ac09c945d4f7`.
Первая operator30s попытка FAIL сохранена: до BOUND,0packets/SQLunchanged,
actual compensation stop обоих. Version02 с fixed90с измерила BOUND30.736с,
полный startup42.718с. Runtime/HTTP/auth deadlines не менялись. Source restore
actual capture4/audit794/changes0 PASS, applyNOT_RUN;15isolatedGit checks PASS.

Дополнительный actual gateway-only ingress-size01: **размерный gate PASS**,
34.445с/BOUND30.222с. Четыре max controls Login1553/Base1024 captured до/после,
oversize1554/1025 отсутствуют, responses0; final capture/log после ownstop и
source/resource binding recheck PASS. Own-IP canary DELIVERED; source127 canary
FAIL WinError10051, поэтому allowlist-negative NOT_RUN и denied traffic не отправлен.
HTTP3492 удерживался exclusive socket без listen; bridge/auth/HTTP/SQL actions0.
Protected15/core installed96/runtime794 unchanged. Helper23componentPASS на fake
socket/Popen fixtures отдельно от actual run. ПервыйBase cross-IP/nativefragment/
remoteMTU/twoPC NOT_RUN. ReceiptSHAf9dae74c2cb32b26340e09d0c4606776a34684bcc67e1cbbfaa91017c35ff431.

Не запускался весь Python/legacy/rustfmt набор. Первый broad CPython glob FAIL
из-за Python3-only greeting сохранён; exact suites прошли отдельно.
Layoutcheck FAIL на прежнем server/__pycache__, guard не ослаблялся.

Новый P10B `client_v2.py` исправляет settings.schema_version1 vs moduleVERSION8,
проверяет actual own PYC/compile/source/ledger; component10PASS. Root перенесла
только новый helper и отдельный MORNING supplement, frozen service files exact.
Actual bind на NET02 правильно отказал до metadata: нельзя выдать NET02 за P10B.
Positive P10B binding/полный prepare/install/native ещё NOT_RUN.

Полный список изменений: `git diff --name-only ffce8cb..codex/net-02-private-lan`.
Текущие NET02 paths: account/{identity,game_network}.rs, protocol/redirect.rs,
session.rs, shared/server.rs, client_patch/{project_auth,project_network,
sr_interactive}.py, tools/interactive_client.py и их tests. Детали карточек —
[research/INDEX](research/INDEX.md), текущий план — [NET-02](plans/NET-02.md).

## Единый порядок ручной приёмки

Начать с уже установленного coreV7. После сохранения текущей работы:

```powershell
git switch --detach p06t-core-20261016-01
python -B -X utf8 local/stands/night-battle-20261016-01/mixed-01/restore_core_source.py --apply
python -B -X utf8 local/stands/night-battle-20261016-01/mixed-01/run.py check
python -B -X utf8 local/stands/night-battle-20261016-01/mixed-01/run.py services --run morning-mixed01 --binding binding-p06t02.json --visibility-v1 --p06t-mixed-ammo
python -B -X utf8 local/stands/night-battle-20261016-01/mixed-01/verify_startup.py --run morning-mixed01
python -B -X utf8 local/stands/night-battle-20261016-01/mixed-01/run.py client --run morning-mixed01 --slot a
# После реального ангара A / SESSION_ACTIVE:
python -B -X utf8 local/stands/night-battle-20261016-01/mixed-01/run.py client --run morning-mixed01 --slot b
```

Не запускать synthetic login_smoke в том же native run; не повторять core install.
Имена run/receipt должны быть новыми. Stop — только фактически запущенные
компоненты через receipts этого run. Точные команды в `mixed-01/MORNING-core.md`.

| Шаг | Проверка человека | Обязательная сверка |
|---|---|---|
| Core queue | A«В бой»→отмена→повтор, Bjoin | Нет зависшего reserve; true owned MS1 |
| Countdown/бой |30с без движения/расхода, затем оба едут/крутят башню/стреляют | Ровно1HEAT+1HE каждым если договорённый сценарий;[0,3,9] после возврата |
| Возврат/repeat | Оба Esc→ангар, loaded typed ammo, повторный бой | Actual native_leave/Finished2/active0; warm cache/revision корректны |
| P08C | Отдельно уничтожение/захват/ничья/900с timeout, итоги/reopen/relogin | Actual outcomes/results, UI/audio не подменять server log |
| P05C/P07B | Mixed MS1/ИС7, контакт лоб/борт; hide/respot за рельефом/дальностью | Нет проваливания, hidden packets не содержат точных позиций |
| P06T | HE splash/LOS, critical/crew/fire, смерть; сохранение всех типов БК | Серверные counters + actual effects; LAB proxy limitations |
| Qualification | T-26/T-34/T-34-85, отдельно WT128clip6/FV183HESH275 | Новые owned admission не включать до проверки каждой машины |
| P10B V8 | Native room/list/preview/join/autoReady/side/start→оба Avatar | Actual Admit2 + one World/Jolt, управление/стрельба |
| P10B repeat | A manualleave при B в бою→warm list, Bleave→новая комната/бой | Все Finished до новогоclaim; active0/сохранённый БК |
| NET02 | Два ПК через actual LAN Login/advertisedBase, room/battle/return/rejoin | Два реальных sourceIP, private TCP недоступен сB, RTT/retransmit/gaps |

Сначала core gate, затем lawful rollback реально установленного overlay.
P04M квалификация имеет новый standalone маршрут
`local/stands/night-battle-20261016-01/MORNING-P04M-QUALIFIED-01.md`.
Старый parent MORNING rollback normal outputs не применять: они PREPARED,
без ledger. Successor проверяет actual coreV7 ledgers и38 source/PYC records
каждого из6 overlays, затем exact483/raw634/qVERSION6. Material634 полностью
восстановимы:278 Git blob/355 wholeCRLF/1 retained own test;14 isolated Git/
path/partialwrite tests PASS. Root повторно проверил actual materials/artifacts,
source_ready/apply/install/native NOT_RUN; helper отказывает текущему NET head.
Promotion receipt `local/evidence/20261016-morning-qualification01/promotion01.json`,
SHA0d6addfbaf8c0eed13a148706bdb62a4e5dd634e15c35ad6de03ff3b847fb06f.
WT/FV extended qualification — отдельные сохранённые команды
`extended-01/MORNING-extended.md`; existing binding-full06 уже создан.
Не обходить installed-target guard и не копировать тяжёлые client resources.

P10B после выбора exact full05/runtimee55 и restore_room_source: новый helper
уже лежит рядом с frozen runner. Последовательность bind→prospective prepare
argv→реальные install plans→installonce→fresh services→client_v2 A/B дана в
`local/stands/p10b-room-20261016-02/MORNING-P10B-V8-startup02.md`.
В нём fresh readonly baseline и actual90с startup verify стоят до clientA;
возврат services сам по себе ещё не означает завершение подготовки World.
Старый `run.py client` имеет settings.version bug и не применяется для V8.
При checkout raw Windows EOL восстанавливаются только source-bound helper.

NET02 twoPC: B address/path/config ещё UNKNOWN. A interface OBSERVED Public,
Private-only firewall rule не сработает; профиль/firewall не менялись. Новый
ownhost stand — отдельная диагностика только своего IP, он не доказывает2PC.
До выбора actualB/Private interface полноценный LAN plan остаётся UNBOUND.
Native/UI/6windows/WAN/NAT/hosting все отдельно NOT_RUN.

## Доказательства и откат

- `local/evidence/20261016-p10b-full05` + `local/build/server/gateway-p10b-full05`:
  clean785 rawsource/full1397/build; P10B tag выше.
- `local/stands/p10b-room-20261016-02/runs/{room-startup02,room-durable01}`:
  actual socket receipts/logs/SQL; ownstop receipts.
- `local/evidence/20261016-p10b-components02/checkpoint05.json` и
  `native-helper-promotion01.json`/`native-helper-net02-refusal01.json`.
- `local/evidence/20261016-net02-integration01`: raw promotion/client/HTTP checks,
  первые FAIL не переписаны. `local/evidence/20261016-net02-full01` и
  `local/build/server/gateway-net02-full01`: full794raw/1414/build.
- `local/stands/net02-ownhost-20261016-01/prepared.json`: actual C43/D44 SQLite
  backup/fixture publication/80refs, source databases raw+logical unchanged,
  no grants/no activation. Actual run net02-ownhost02 receipt/logs/timing/OS
  listener/ownstop сохраняются там же; final NET C44/D45, источник P10B43/44 intact.
- `local/evidence/20261016-net02-integration01/checkpoint02.json`: final full+
  ownhost closure, SHA708730d58ba81e7ea249a4fafd992f62a1f8b136fe321d3cf593eeddc0ac0014.
  Startup uses fresh binding-startup02.json (SHA1efaf590e184d6aa582b2375d278df44015bec0eca1e4398307920535b9fbb5a);
  original binding.json/restore sidecar/retained4bytes сохранены отдельно.
- NET02 фактически выполненные команды и consumed-state ограничения:
  `local/stands/net02-ownhost-20261016-01/MORNING-NET02-EVIDENCE.md`.
  Финальный readonly raw+logical/source state:
  `local/evidence/20261016-net02-integration01/final-state03.json`.
- `local/evidence/20261016-net02-ingress01`: canary-feasibility01 FAIL10051,
  protected before02, prepare03/send04 commands/logs и after05 actual closure;
  SHA06a11ceb7645caa658308eb5693aa8bed4fbdf6f0200aa04c30d9c3cc1f12d92.
  Stand `local/stands/net02-ingress-20261016-01/runs/ingress-size01` содержит
  actual capture4/rawbytes/startup/launch/ownstop/poststop result. Точные команды
  и scope — новый stand-local `MORNING-INGRESS-EVIDENCE-01.md`; consumed ownhost
  initial43/44 proof не затрагивался и не переиспользовался.

Software rollback — соответствующий сохранённый tag/ветка и exact source restore.
Client rollback — только actual latest install ledger с остановленным процессом;
восстановленный ledger не переиспользовать для install. DB — whole SQLite backup
и durable recovery, reservations вручную не удалять. Firewall удаляется только
по identity своей будущей rule; сейчас rule не создавалась. Тяжёлые assets не копировались.

Автоматическая проверка ранее отклонила удаление трёх Cargo-кэшей неудачных
сборок, причина «blocked by policy». Удаления не было; обход не применялся.

Приёмка: STAB-01 принята; остальные ночные карточки — автоматические границы
выше, обязательные native NOT_RUN, без main merge. Хвост/микролаг/склад/
оборудование/слоты/P04L/legacy/Python/rustfmt не начинались до боевой вехи.
Доступные ночные программные/full/ownhost gates сохранены. Единственный первый
шаг владельца — coreV7 native сценарий выше. Затем квалификация/V8/P10B и actualB
для отдельного paired LAN stand; его план UNBOUND до настоящих данных. Consumed
ownhost initial43/44 proof не повторять на44/45, SQL/initial_state не сбрасывать.
