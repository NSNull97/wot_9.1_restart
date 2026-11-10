# План SPG-02 — машины с одним или двумя видами снарядов (2026-11-11)

Ветка `codex/spg-02-variable-ammo-stacks` от main `ff0c0746`. Решение владельца 11.11 ночью: «переменное число» (вариант А),
начать этой ночью; к утру рабочих САУ на стенде не ожидается.

## Зачем

Генератор `tools/battle_any_profiles.py` с разрешёнными САУ (проба 11.11, test_lab): из 37 отказанных САУ 34 отказаны
`SHELL_SOURCE_UNSUPPORTED` «1 или 2 вида снарядов, среде нужно 3» (Karl, GB25 Loyd Carrier, GB29 Crusader 5 inch — по одному,
остальные по два); 2 — `SUPPORT_SOURCE_UNRESOLVED` (Bat.-Chât. 155 55, 105 leFH18B2); 1 — `PHYSICS_ENVELOPE_EXCEEDED` (FV304).

## Что известно

- Клиент 0.9.1 получает боеприпасы вызовами `Avatar.updateVehicleAmmo(compactDescr, quantity, quantityInClip, timeRemaining)`,
  по одному на вид снаряда (`battle/native_ammo.rs`) — для двух снарядов хватает двух вызовов (VERIFIED по кодировщику;
  поведение клиента с двумя строками — проверка в бою).
- Каталог (`tools/catalog_build.py`) хранит `shells` списком; три требуются явной проверкой для допущенных машин.
- Шлюз: фиксированные `[_;3]` в армаменте, загрузке, удержании, журналах потерь, детонации, панели (~16 файлов, см. ниже).

## Представление

Снаружи (таблица, каталог, склад) — список 1–3 видов. Внутри шлюза — по-прежнему три ячейки, лишние — «нет снаряда»:
`Shell::ABSENT` (compact 0), количество всегда 0, выбрать нельзя, клиенту не отправляется, в журналах — 0. Настоящие снаряды
не дублируются и не придумываются. Обоснование: форматы журналов, реплея и BW-01 кодеков остаются прежними.

## Этапы

1. Генератор и таблицы test_lab: 1–3 выстрела у САУ test_lab; `battle_any_data_test_lab.py`, пины Rust.
2. Шлюз: разбор таблицы (`generated_vehicles.rs`), `GunProfile.shots` с пустыми ячейками, армамент (выбор, текущий/следующий),
   загрузка и удержание (`profile13_v2/hold/loss`), детонация (заряд по реальным снарядам), панель — только реальные строки.
3. Каталог и склад (Python): `catalog_build.py`, `p04m_pool_store.py`, `p06t_owned_store_v3.py`, `p08b_battle_store.py`,
   `p09d_ammo_projection.py`, `hangar_state.py`, проекции ангара — стеки по числу видов.
4. Стенд -13: 34 САУ в каталоге стенда, бой владельца.

## Файлы шлюза с тремя стеками (без тестов)

armament.rs (8), profile13_v2.rs (5), profile13_session_loss.rs (4), profile13_loss.rs (4), profile13_hold.rs (4),
owner_hold_capture.rs (2), armament_wire.rs (2), ammo_detonation.rs (2), profile13_hold_projection.rs (2), fire.rs (2),
vehicle_profile.rs, profile13_session_v2.rs, p06t_shell_data.rs, p06t_extended_world.rs, shared/mod.rs, late_results_capture.rs.

## Проверки

Тесты шлюза в worktree против базы (тот же набор падений из-за фикстур D:), Python-набор в D:, канонический gate в D:,
бой владельца на САУ с двумя снарядами (панель, выбор снаряда, перезарядка, детонация).
