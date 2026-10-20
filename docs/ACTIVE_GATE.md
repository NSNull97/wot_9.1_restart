# Текущие ворота: FULL-TEST — общий native-тест всего сделанного

Ветка `codex/full-test-20261019`: вся неслитая цепочка STAB-01 → P08B → P08C → P05C →
P07B → P06T → nightly polygon → ram publication + исправления FULL-TEST.
[План](plans/FULL_TEST_20261019.md), [19.10](research/FULL_TEST_20261019.md),
[20.10](research/FULL_TEST_20261020.md). Main `ffce8cb` не менять до приёмки.

## Стенд

`local/stands/full-test-20261020-04` — сервер, физика, мост, Python и клиентский патч
из одного checkout `D:/WoT_9.1_Server`. Login 20340 / base 20341 / identity 3692.
Клиенты `local/clients/p03f/a`, `b` установлены из `local/stands/full-test-clients-20261020`.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File local/stands/full-test-20261020-04/services.ps1 start
Start-Process local/clients/p03f/a/WorldOfTanks.exe -WorkingDirectory local/clients/p03f/a
Start-Process local/clients/p03f/b/WorldOfTanks.exe -WorkingDirectory local/clients/p03f/b
powershell -NoProfile -ExecutionPolicy Bypass -File local/stands/full-test-20261020-04/services.ps1 stop
```

## Матрица владельца (первый сбой отметить, остальное продолжать)

| # | Проверка | Ожидание |
|---|---|---|
| 1 | Вход обоих, ангары | по 100 слотов; у A в гараже Т-34, у B Т-34-85 (подготовлены сервером: экипаж + БК) |
| 2 | Магазин: купить любой танк, в т.ч. премиум | цена 0, танк в гараже (вне пула 5 типов — только гараж) |
| 3 | Бой Т-34 (A) против Т-34-85 (B) | допуск, движение, стрельба, итоги, возврат, БК списан |
| 4 | Купить Т-26 самостоятельно | машина в гараже; экипаж/БК через UI для неё **не подключены** (UI экипажа/БК только MS-1/ИС-7) — готовить `full_test_stand.py provision` |
| 5 | Бой MS-1/ИС-7: W+A/D на скорости | скорость в повороте падает, не выше прямой |
| 6 | Таран, переворот, засвет, лампа 6-го чувства | бой не закрывается; лампа со звуком (проектный `gun_intuition`) |
| 7 | Стрельба, детонация БК → отрыв башни | у жертвы корпус без башни; у атакующего башня видна и не исчезает |
| 8 | Итоги → ангар → повторный бой | итоги корректны, БК сохранён |

Известно не сделано: коллизия ствола оторванной башни; ёмкость экипажа >16 за всё
время; клиентский UI экипажа/БК для купленных машин (сейчас только MS-1/ИС-7, обход —
`tools/full_test_stand.py provision` при остановленном стенде); бой на машинах вне
пула 5 типов; разрушаемость всех объектов всех карт. Лог сервера: `gateway-*.stdout.log` стенда, сбой — `SHARED_BATTLE_FAILED`.
Native/UI/звук/управление — NOT_RUN до прогона.
