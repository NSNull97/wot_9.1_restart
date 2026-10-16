# P10B — native room, typed Loss4 и actual compensation

Software checkpoint 2026-10-17: `codex/p10b-loss-training-integration`, runtime
`689fb93c4a1bfb05cf3bb1d63ce3836e2e2f4a74` от91dbdbe. Ordinary merge saved6c6b7b7 — adfea6e;
mainffce8cb и прежние ветки сохранены. Ручная/native приёмка NOT_RUN,
карточка не сливается в main. Ночное продолжение разрешено до09:00.

## VERIFIED: реализация

Сохранённый native room/controller/stream/Host объединён с current Loss4/late/
firstspot/turret guards. Typed Mode MixedV2|LossV4, ReadySelection/Task/Job/
Completion/Reservation/Saga не превращают старый2 proof в4. Actual selection
POST `/internal/native/room-selection-loss`: closed owner/auth/Host/Origin,
query-only SQLite snapshot,9-field request/3072B,15-field reply/6144B,
full native/source/companion stamp. Нет activation/fixture publication/reserve
по READY, нет bare Inspect вместо Frozen/loadout proof. Exact AmmoLossStore
reader отделён от late writer facade. Existing V2 route/validators сохранены.

Actual compensation требует known cancellation или current bound Fresh после
Inspect; ambiguous Admit сохраняет immutable task/key и claim. После полного
AllReleased новый battleID и pristine World/runtime готовятся до native abort
publication; только после всех fallible stages выполняются swaps. Public
fresh_battle(sameID) и immutable roster guards не ослаблены. Специальный
fresh_loss_roster для N2..6 пересоздаёт только pristine empty ledger; hidden
clock/events/tombstones/actors/outcome/team/extended mode отказывают.

Frozen roster order и team plan независимы от Session arrival. Launch ждёт
реальные Admit/Fresh всех selected и actual reliable ACK final411. Сначала
стадируются source-linked late Capture и Finished observer, затем actual
launch; terminal delivery один, оба observers commit после него. Claims
освобождаются после Finished всех selected, не после первого возврата.

Найденный actual A-only source defect исправлен в V2/Loss4 readers: сравнение
`source.profile_bytes == p09d_import.base_json` сохраняет raw source SHA и
bundle SHA. Historical AnchorA имеет законные неканонические raw bytes;
пересериализация того же объекта давала ложный mismatch. Semantic-equal raw
подмена OwnerB теперь отвергается; старые import/политики/rows не переписаны.

## Выполненные проверки

- Canonical current-head full: **1553 PASS/0FAIL/5oldignored/buildPASS**,
  865 rawsource before/after exact; fresh C Cargo target,
  verified D-export.
- Actual09 в full и отдельно focused06:4 genuine readonly selections,3 actual
  Admit,3 Finish (первый compensation, затем два terminal), same run после
  cancellation → fresh room → ordered B,A/teams2,1 → ACK launch → Forfeit →
  оба claim released +actual late Capture. Initial SQL/depot/crew/research
  resources проверены на barriers, grants0, source DB unchanged.
- Старый actual late Runtime→HTTP/SQLite→reopen→1500/1501 повторно PASS в том
  же full; immutable natural Arc и seal-before-reset сохранены.
- Python17 PASS/0skip: actual raw-source2 methods/8subcases (оба owners и
  V2/Loss4), snapshot/DTO8, clean CLI2, actual SQL5. Эти компоненты выполнены
  на e4875de; carry-forward доказывает неизменность всех dependencies, единственная
  разница —09 Rust config-gated Finished initialization, проверенная новым full.
- New Web4/actual HTTP3 PASS/0skip. Current689fb93 old Web regression37
  PASS/0skip (P08B/P08C/mixed/loss/default guards).
- Our client-code/mock tests: host79 PASS; actual CPython2.7.3 76PASS/3старых
  host-only skips; old clean V2 CLI1 PASS. Это не native UI.

Earlier compile/focused FAIL retained: missing nested module path/enum matching;
old bench poll expectation after legitimate reset;09 ACK sent through forbidden
ordinary Session.receive; raw Anchor mismatch; Node bare arena vs SQL run:arena;
missing configured Finished collector in test setup. Guard relaxation не было.
Active02 import environment failure и Active03 old reader SHA assertion также
сохранены; successor active04 прошёл с actual new reader pin.

## Evidence, команды и файлы

Proof `local/evidence/20261017-p10b-loss-full01/composition-full.json`,
source-after/raw archive рядом. Focused06, active04, web-regression01 и
client-compat01 находятся в соответствующих `local/evidence/20261017-p10b-*`.
Actual09 full child: `D:\WoT_9.1_Server\local\test-runs\p10b-loss-composition09\run-100080-1792186759859913400\result.json`.
ExeSHA `1611241bd4f90005cc4559ba0172115d37a1ef1786127df331d05c27e5b9ec9c`.
Raw archiveSHA `7ac5b4b4e69b74dc1c3b8fbeeecadf1a4f5fb6c38b17c9a4d1a2b0d7608f0688`.

Executed canonical command (output reuse запрещён):

```powershell
$env:RUST_TEST_THREADS='1'
$env:CARGO_INCREMENTAL='0'
$env:CARGO_PROFILE_DEV_DEBUG='0'
$env:CARGO_PROFILE_TEST_DEBUG='0'
python -B -X utf8 server/build.py gateway --test --cargo-temp-target --out local/build/server/gateway-p10b-loss-full01
```

Изменения: shared p10b Host/Ready/Preparing/Launch/typed writer +training091
controller/domain/wire; identity room_selection_loss и Session/server integration;
profile13 loss/v2 Finished observers; tools/p10b_selection*.py и fixed Web route;
actual SQL/HTTP/Host regressions. `.gitattributes` содержит только source-text
pins для reproducible immutable codecs/readers/tests, без ресурсов клиента.
Совокупный diff включает сохранённую предыдущую P10B реализацию; она не
выдаётся за заново написанные этой ночью модули.

## Ограничения, приёмка и откат

Native room methods/callback numeric IDs остаются INFERRED_STATIC, native UI/
шесть клиентов/реальный handoff/звук/UDP gameplay/two-PC NOT_RUN. Actual09
использует synthetic authenticated Session envelopes/Window ACKs, source
Prohorovka terrain, authored engine-binding/clock/Forfeit; не подделывает Ready,
Completion, HP, hits или World reset. Jolt/six automated components в полном
наборе не являются native six. Warm Avatar cycle не покрывается09.

Owned admission по-прежнему только accepted MS1/IS7; новые3 и WT/FV не
включены. Loss4 early return сохраняет старое release поведение; изменённый
parked actor не пересчитывается conservative late append. Future Hold5 —
отдельный typed contract/ветка, здесь не подмешан. Старый notice0x4b defaultfalse.

Все own stand services/clients STOP; старый binding-loss01 толькоed67531.
Откат: checkout91dbdbe с совместимым reader/DB; не восстанавливать старую DB
поверх committed ammo loss/late history. Ничего из старых evidence/builds/DB
не удалено. Обязательные manual gates оставляют карточку вне main.

Единственный следующий шаг: отдельная NET-02 ветка с normal merge saved
b6c294f, preservation текущих typed loss/late/room hooks и новым full/binding.
