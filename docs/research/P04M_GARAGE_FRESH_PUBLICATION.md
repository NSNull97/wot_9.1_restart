# P04M: сохранение БК и атомарное обновление ангара

VERIFIED runtime `471ac475d21d9fc4b932e88eb398447c36c043df`, ветка
`codex/p04m-garage-fresh-publication`, parent checkpoint `e48af3c`.
Main `ffce8cb` сохранён. Исходная D папка и клиентские копии не изменялись.

## Причина и изменение

VERIFIED source defect: успешный pool worker искал новую metadata в старой
immutable fixture_dir. SQLite мог уже сохранить команду, а публикация падала.
Кроме того, прежняя complete забирала Job до apply и теряла известный ответ
при заполненной очереди. Причина наблюдавшейся задержки 3.9s остаётся UNKNOWN.

`account/ammo_session.rs`, новый `ammo_session_fresh.rs` и `shared/mod.rs`
разделяют единственную mutation и readonly Fresh. Singleton Job удерживает
известный ответ; чтение нового профиля повторяется максимум три раза в пределах
90s. Повторной SQL mutation, возврата снарядов или полного Account rebind нет.
Identity/fixtures/pool/source cursor и delta0x57 перед callback публикуются
атомарно на клоне Session. Account epoch, request prefix, used IDs и native
wire cursor сохраняются. Неизвестный исход может закрыть только исходный
канал; заменившая его сессия с тем же SID не получает чужую ошибку или UI.
Данные канала остаются в памяти без Debug/Serialize и не выводятся в логи.

Scope: три production файла, cfg(test) регистрация в shared/server.rs,
garage_fresh_composition_tests.rs и пять Python/Node helpers, EOL attributes.
Active Hold и Training+Hold5 остаются запрещены для этой команды.

## Фактически выполнено

Focused03: **2 PASS, 0 FAIL, 0 ignored, build PASS**, 147.58s driver.
Canonical full01: **1619 PASS, 0 FAIL, 5 прежних ignored, build PASS**,
1158.48s tests / 1209.51s driver, все923 raw source files до/после совпали.
Внешний seal48Hold02 подтвердил **семь** настоящих HTTP/SQLite compositions
именно из этого полного прогона; внутренние PENDING receipts не переписывались.

Два новых сценария используют настоящие Config.authenticate, RunOpen4 либо
RunOpen5+Inspect5, CMD108, Job, SQLite и Fresh. Unload4→3, первый readonly503,
повторное чтение, pressure127, delta перед callback, следующий CAS/reload4,
затем pre-forward503 и чужой same-SID канал. По две SQL mutation и три HTTP
mutation attempts; третий запрос в writer не поступает. Выдач имущества,
изменения склада/экипажа/исследований и других владельцев нет.
Транспорт, ACK, pressure и инъекции503 заданы тестом. Это не native/UI proof.

Focused01 compile FAIL из-за Debug у opaque LoginAttempt и focused02
C33_ABSOLUTE_LOCAL до SQL/HTTP сохранены. Исправлены только безопасное сравнение
без печати канала и нормализация verbatim seed argv перед неизменным guard.

Команды из C:/wot091-night-20261017-01/w (новый output при повторе):

```powershell
$env:RUST_TEST_THREADS='1'
$env:CARGO_INCREMENTAL='0'
$env:CARGO_PROFILE_DEV_DEBUG='0'
$env:CARGO_PROFILE_TEST_DEBUG='0'
$env:WOT091_ROOT='C:/wot091-night-20261017-01/w'
$env:P04D_TEST_BUNDLE="$env:WOT091_ROOT/local/stands/p09e-main-01/source-bundle-05"
$env:P04D_TEST_ORIGINAL='C:/WoT_0.9.1_RU_0717_original'
python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-c-garage-full01
```

Evidence: `local/evidence/20261017-c-garage-full01/source-after.json`,
`composition-full.json` SHA256
`4bfa9efe4b5c2512a54b9a532486554d8bb70b551edb9e53b137d523d926ef02`.
Exe SHA256 `e2d01f65c0f38bfe5e22d574d8e605cb9c5a92ea6c306e036744a2fe755b99e3`.
Focused evidence: OS Temp/wot091-night-workspace-kcadgetk/garage-focused03.

Приёмка software PASS; native ammo108/crew/research UI, звук, управление и
реальная задержка NOT_RUN. Непринятые родители оставляют ветку вне main.
Откат: остановить собственные службы и не использовать ветку либо revert её
source commits; SQLite не откатывать поверх сохранённых расходов. Следующий
шаг ночи — отдельная карточка складских ссылок на снаряды.
