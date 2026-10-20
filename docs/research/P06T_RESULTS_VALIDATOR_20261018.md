# P06T Results8 validator repair — 2026-10-18

## Причина

После публикации Rust `lifecycle_details::apply_module_facts` в `interaction_details`
появились серверные счётчики `crits` и `fire`. Python writer проходил через
`tools/p08c_battle_results.py::_interaction_details`, где оба счётчика были
обязаны быть нулевыми. `tools/p06t_ammo_loss_store.py::validate_request` поэтому
отклонял естественный `finish` как `INVALID_INPUT` до записи результата. Node
сводил закрытие worker к общему 503, а gateway оставлял клиента в посмертной
камере и не доводил возврат в ангар.

## Исправление

- `crits` принимает только `0..=192`, `fire` только `0..=10`, как Rust
  `Details::validate`;
- ненулевой `crits`/`fire` считается авторитетным фактом даже при нулевом уроне;
- `damage_assisted_track` и `damage_assisted_radio` остаются строго нулевыми;
- имена модулей, их HP и произвольные поля клиента в DTO не добавлены.

## Проверки

- `python -B -m unittest tests.test_p06t_results_validator -v` — **1 PASS / 0 FAIL**;
- `python -m py_compile ...` — **PASS**;
- Rust `p06t_device_v2_` — **13 PASS / 0 FAIL**;
- Rust `p06t_module` — **3 PASS / 0 FAIL**;
- attempted canonical gateway suite: **1653 PASS / 3 FAIL / 5 ignored**, rejected
  as an environment/successor-stand mismatch (`garage_fresh39` twice and
  `p08b_restart_cas02`); this is retained as FAIL evidence, not a gate PASS;
- standalone gateway executable build: **PASS**, SHA-256
  `B3B318B22867E35F2EEF76CE5D9553B2B1B0975CA609E924B241BF00CD7EA46A`;
- receipt: `D:\wot091-successor-worktree-20261018-01\local\evidence\20261018-p06t-results-validator\receipt.json`;
  SHA-256 `8C36FE3DF8C0B96459F21D7EF433E611A0A8DF0463FD2B8A68AB6815DDB32F30`.

Native P06T death/return и fresh gateway build после этой ветки остаются
**NOT_RUN**; canonical suite был запущен, но не принят из-за трёх старых
composition/stand failures. Следующий шаг — свежий D-only native run: детонация
БК/отрыв башни, два естественных `finish`, Results8 с `crits/fire`, ACK и возврат
обоих клиентов в ангары. Откат — `git revert d350201`; база, клиентские ресурсы и
`main` не менялись.
