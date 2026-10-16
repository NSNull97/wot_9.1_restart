# Ночной checkpoint — 2026-10-16, 08:05+05

Продолжение 07:25. Ветка `codex/p06t-mixed-shell-damage`, HEAD остаётся
`9080c4799a193b8ee2a18ec99410931154655fb9`. После него большой согласованный
World7 WIP ещё не закоммичен. Не откатывать и не переключать checkout.

**Full05 закрыт:** 1111 PASS / 0 FAIL / 5 прежних ignored / build PASS,
341.89 с, 695 исходников до/после совпали. Tag `p06t-devices-20261016-01`.
Exe SHA `26b85500cadcfbf86a60c47d3ab8574caad0670e5352d382b1c36900d5a5e599`.
Proof: `local/evidence/20261016-p06t-full05/`, device component receipt —
`local/evidence/20261016-p06t-device-v2-01/component-freeze.json`.
Full04 physical tag и full03 core tag не двигались, main/origin ffce8cb.

## Сейчас идёт focused13 — НЕ full/source freeze

Unified exec session **17464**:
`RUST_TEST_THREADS=1 python -B -X utf8 server/build.py gateway --test
--test-filter p06t_ --out local/build/server/gateway-p06t-focused13`.
Source с начала компиляции не меняется. Текущие новые World tests прошли,
но общий итог ещё PENDING. Дождаться exit/result, не приписывать PASS заранее.

Focused12 сохранён с **128 PASS / 6 FAIL / 0 ignored**,399.27 с, build после
FAIL не запускался. Пять тестов не могли создать typed actor: прежний legacy
конструктор запрещает ammo0, а новые kinds намеренно имеют initial_ammo0.
Root добавил приватный typed factory только под extended_lab; старый minimum
не ослаблялся и фиктивный БК не создавался. Шестой FAIL — тест угадал порог
0.0005 rad, реальная source разница ~0.00049; теперь независимое low-arc
уравнение с допуском2e-6 rad и строгим порядком AP/APCR. Отдельный failure
receipt: `local/evidence/20261016-p06t-world07/focused12-failure.json`.
В cfgtest helper кешируются только immutable hash-checked resource Arcs;
negative manifests по-прежнему загружаются отдельно.

## Уже подключённый WIP

- VehicleKind Wt128/Fv183, SUPPORTED7; старые ALL5/парсеры/owned DTO закрыты.
  Source AimEnvelope: FV±45 yaw, WT обе pitch границы/5° transition; старые
  пять ветвей арифметики сохранены. Новые механические guards в wire.
- Самостоятельный bounded exporter tools/p06t_combat_geometry{,_reader}.py
  +pins JSON; новый строгий Rust geometry loader/materials class31. Никаких
  client meshes в Git/include_bytes. Promoted Python9 PASS и реальный экспорт
  совпал с final pins: WT0971afa6...62aae, FV c14b10be...ecb1d.
  Proof `local/evidence/20261016-p06t-world07/python-geometry02/`; первый
  harness failure из-за отсутствующего output parent сохранён в01.
- Настоящий shared-only Pool4, configs3/qualified source2; legacy independent
  worker launch отклоняет Pool4 до spawn. Kind.extended_vehicle explicit,
  старый vehicle() по-прежнему None для новых двух.
- Resources4 exact7, SharedResources.version/source_profiles7, SceneManifest3
  только world.extended_lab. Actual manifest
  `local/evidence/20261016-p06t-world07/resources01/battle-profiles-seven.json`,
  SHA76f198a10768c24082e49cb3d7c850f13eab1a1a249de559f96025c355f933e6.
- Root World typed LAB attach, same-loadout reattach без refill, policyv2,
  геометрии7, old terminal-v2 guard. CLI `legacy091-p06t-curated-lab` допускает
  только WT128/FV183 и требует новые ресурсы; старый curated CLI закрыт5.
  Временный БК WT[12,6,6], FV[4,4,4], помечен LAB; owned/inventory не меняется.
- Семь новых resource/scene tests, четыре root World tests (clock-only clip6/
  HESH275/reattach/admission), geometry5, Aim/registry14, Pool4tests и CLI gate.
  Полная актуальная приёмка пока NOT_RUN. Gun31 явно Unsupported, не gun25.

## Параллельная работа — ONLY ignored

- Protocol agent готовит actual new2 mesh→ray→Trace→HP/module тесты без
  authored contact. Active geometry/files FROZEN, Cargo/HEAD не трогает.
- Writer закончил изолированный OwnedV3Store:26 SQL/source/terminal PASS,
  export04 actual23vectors+2 CPython PASS. Воспроизвёл и закрыл3 binding races.
  Подготовка отдельного self-contained promotion layout продолжается;
  imports из staging нельзя переносить в production. Live endpoint/router,
  old reader fallback fence, ACK/coldcache и owned WT ammo остаются NOT_RUN.
- Physics/resources agent сейчас ONLY ignored проверяет воспроизводимость
  утреннего core. autocrlf=true может изменить raw SHA при git checkout!
  All683 из full03 восстановимы:326 Gitblob+356 CRLF+1 fixed exact-tested
  mixed-EOL backup нашего test_profile4_semantic_diff.py. Helper/closed sandbox
  tests и audit02 в mixed-01; actual source restore/checkout НЕ запускались.

Утренний core stand сохранён: tag9920a63/full03/1096PASS, binding-p06t02/V7
установлены, A112/B29/MS1[0,4,10]/reserves0, свои процессы STOPPED.
Два real hangar boot OBSERVED, gameplay/UI/audio NOT_RUN. MORNING-core.md
дополняется exact-byte restore между checkout и запуском, без обхода guard.

Следующее: дождаться focused13, устранить реальные FAIL; принять фактические
contact tests, снова focused при новых изменениях. Затем commit и full06 с
clean source-before/after. Не выдавать WT/FV software/native за принятый P06T,
не сливать обязательные NOT_RUN в main и не перескакивать к хвосту.
