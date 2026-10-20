# P06T — seven LAB, loss4 и late results вместе

Software checkpoint 2026-10-17: `codex/p06t-seven-loss-integration`, runtime
`0e03e196db69abfde3f44ac420c3ba1367b2f50e` от5c86c03. Выполнен normal merge savedb9239e3,
commonbase9920a63. Mainffce8cb и исходные ветки сохранены.

## VERIFIED: изменения и границы

Три source conflicts решены по pinned baseline: UNION attributes, World loss/
turret и extended fields, фактический plate+Gun31 branch с одним totalHP record.
Шесть Rust resolutions проверены byteexact до установки; raw CRLF→LF сравнение
отдельно записано в resolution.json. Два документальных конфликта сохраняют
актуальные P08C данные, исторические seven отчёты остаются явно историческими.

Profile::ALL намеренно5, SUPPORTED7. Public detonation Input использует checked
source lookup: WT/FV возвращают ошибку до journal/tombstone mutation. Owned
loss4 и extended LAB взаимно отказывают до actor attachment. Старый Frozen/
loss policy/5device rows/hash не расширяются; fallible device constructor
адаптирован в двух старых MS1 fixtures. Новые WT/FV не получают owned admission.

Сохранены accepted marker/natural-return/autoaim refusal, Results8/firstspot,
все late runtime/Dispatcher release/Finished/seal/before_reset hooks. Actual
late Runtime→HTTP/SQL composition повторно прошла уже на новом объединённом
head. Seven LAB использует отдельные resource4/7; normal owned profile13
сохраняет resource3/5 и старые допуски MS1/IS7. Для новых3 и WT/FV native
qualification/admission остаются открытыми, не включаются этим merge.

## Выполненные проверки

- Focused `p06t_seven_loss`:5 PASS/0FAIL/0ignored/buildPASS,43.36s driver.
  Проверены чужая policy/поддельный extended wrapper/старый cancel без mutation,
  public leaf без panic/tombstone, следующие законные события и ALL5 boundary.
- Python `test_p06t*.py`:102 PASS/0FAIL/0skip,676.521s. Actual original source
  geometry/profiles, WT128clip6/FV275, SQLite v2/loss4/v3 cutover/terminal,
  CPython cache fixtures и old source/policy bytes. Тестовый PYTHONPATH явно
  ограничен ROOT/tools+tests; disposable canonical test onboarding не является
  выдачей имущества рабочим аккаунтам. Рабочий стенд не менялся.
- Canonical full: **1295 PASS/0FAIL/5oldignored/buildPASS**,601.96s tests/
  646.14s driver,783rawsourcebefore/afterexact. В том числе actual mixed-six
  seven source scene/scalar/ACK и прежняя late HTTP/SQL composition. Это
  автоматические компоненты, не native gameplay.

Evidence: `local/evidence/20261017-p06t-seven-merge01/resolution.json`,
`local/evidence/20261017-p06t-seven-focused01/source-after.json`,
`local/evidence/20261017-p06t-seven-python01/source-after.json`,
`local/evidence/20261017-p06t-seven-full01/composition-full.json`.
ExeSHA `ee746ac03d02299c4a8a69d1a5d1a419dc2028f62e727a6f98850fc10680eba5`.
Raw archiveSHA `177a632d65ff5841f676f5894cacbf8df3974440180fe44e8308a3f2f2ef6595`.

Команды, full output всегда новый:

```powershell
$env:RUST_TEST_THREADS='1'
$env:CARGO_INCREMENTAL='0'
$env:CARGO_PROFILE_DEV_DEBUG='0'
$env:CARGO_PROFILE_TEST_DEBUG='0'
python -B -X utf8 server/build.py gateway --test --cargo-temp-target --out local/build/server/gateway-p06t-seven-full01
python -B -X utf8 local/evidence/20261017-p06t-seven-python01/run.py
```

Последняя команда — сохранённый одноразовый source/evidence runner, повтор
требует новой output папки; его точные subprocess/env находятся в receipt.
Python source/geometry outputs свежие, old generated ресурсы не заменялись.

## UNKNOWN / NOT_RUN и откат

Native UI/аудио/микс6/столкновения/новые машины/WTclip/HESH остаются NOT_RUN.
Серверный module/fire solver явно LAB policy, historical probability/impulse
не объявлены подтверждёнными. Консервативный late append не решает parked
inventory после раннего Finish; это отдельный future frozen hold5 contract.

Автоматический checkpoint PASS; вся карточка/native не приняты и не merge
в main. Откат — source5c86c03 с его совместимым reader и отдельным binding;
игровые DB назад не восстанавливать, committed fired/lost не возвращать.
Следующий ночной шаг — отдельная P10B ветка, normal merge6c6b7b7 и typed
loss Saga04/Host05/Web05, actual compensation/retry/launch/Finished gate.
