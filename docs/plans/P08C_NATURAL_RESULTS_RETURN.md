# P08C — личные итоги и возврат после уничтожения

Ветка `codex/p08c-natural-results-return` от принятого marker checkpoint
`972843a`; проверенный runtime родителя `363daa3`. Main и ночные ветки
сохраняются. Это исправление native P08C, без изменения экономики и клиента.

## Наблюдение 2026-10-16

Владелец подтвердил красные вражеские маркеры и управление обоими. Следующий
естественный бой завершился Elimination после трёх выстрелов первого игрока.
На сервере оба результата сохранены, но native приёмка FAIL: у победителя
личная сводка пуста при корректных 90 урона и фраге в командной таблице;
у уничтоженного чёрный экран и последующий выброс из сессии. Screenshot перед
итогами содержит «Загрузка интерфейса…». Server commit не доказывает GUI.

VERIFIED source: `lifecycle_wire::field("details")` всегда пишет пустую строку.
VERIFIED log: после reset/enable Account у проигравшего seq3528/169bytes
отвергнут как unmeasured hangar method; последующие5bytes тоже отвергаются,
затем idle_timeout. Точный формат первой отвергнутой записи ещё исследуется.

Собственный `morning-marker01` остановлен по receipts после сохранения обоих
native traces, gateway logs и consistent RO SQLite backup. База A120/B35,
MS-1 A[AP0,HEAT1,HE8], B[0,3,9], active reservations0. Никаких grants/reset.
Корневые python.log старые и не используются как доказательство этого запуска.

## Порядок

1. Закрепить source-bound #717 формат private details и actual rejected frame;
   отдельно установить, что было измерено, а что остаётся выводом.
2. Исправить строгий native return parser, сохранив полную атомарность пакета,
   границы методов/размеров, запрет stale Avatar authority и replay guards.
   Не проглатывать неизвестные методы и не лечить обрыв увеличением timeout.
3. Передавать личные действия по целям из авторитетных фактов мира, в формате
   original VehicleInteractionDetails. Не выдумывать spotting/assists и не
   объявлять неучтённые события нулевыми подтверждёнными показателями.
4. Regression реального отвергнутого native envelope и негативных вариаций;
   независимый source-derived detail decoder и проверки реального damage/kill
   ledger, UI consumer contract. Canonical full на committed head, все raw
   source hashes до/после, новая binding/run без изменения старых receipts.
5. Свежие оба клиента с сохранённым БК. Owner повторяет уничтожение: личная
   сводка и team tab согласованы, оба natural return/result/hangar работают,
   нет выброса. До фактической проверки UI/return остаются FAIL/NOT_RUN.

Evidence: `local/evidence/20261016-p08c-natural-failure01`, отдельные ignored
research helpers. Старый ранний manual-leaver full-result append — отдельный
незакрытый пункт, terminal/CAS/расход БК не переписывать. Spawn и другие
карточки в эту правку не включать.

Откат: свои процессы остановить по receipts; вернуть сохранённую marker ветку
и matching full/binding04, сохранив текущую БД и ammo. Старый reader Results7
не читает новые Results8; новые строки требуют нового reader даже после
отката игрового бинарника. Не восстанавливать БД ради возврата потраченного БК.
Marker gate остаётся
принятым. В main эту зависимую цепочку не сливать до родительских gates.
Выполнено: strict dead routed bind, versioned details из реальных журналов,
first Battle observation с отдельной LAB policy. Focused43/build и Python33
без skips PASS. Runtime09274f2 full1130PASS/5oldignored/buildPASS,689sourceexact;
actual fired World→90damage/1kill/1spot→native81/details PASS. Fresh binding05
и services/startup morning-natural01 PASS. Оба native ангара/cache/model загружены,
96 installedunchanged, A121/B36/active0, ammoA[0,1,8]/B[0,3,9]. Следующий шаг —
повторная owner приёмка уничтожения/личной сводки/обоих natural возвратов;
вопрос отправлен. Fresh UI NOT_RUN до ответа и actual wire/SQL сверки.

## Прерванный повтор natural05: автоприцел

Владелец включил родной автоприцел и был выброшен из сессии; у Ёжа после этого
появились итоги с засветом. Сохранённый arena5172357154243584472 закончился
Forfeit после Disconnect первого игрока: оба HP90, damage0/kills0. У Ёжа
Results8 с spotted1, Avatar/Account delivery и возврат подтверждены; личная
карточка уничтожения и dead natural return ещё NOT_RUN_INTERRUPTED.

VERIFIED actual app11bytes `0c08000000000003001009`: Cell autoAim, routing0,
единственный OBJECT_ID аргумент enemyVehicle03. Driving parser не включает
0x0c в allowlist и отклоняет seq1076; последующий reliable gap ведёт к timeout.
Original PlayerAvatar.autoAim сразу включает локальный захват и отключает
gunRotator.clientMode. Поэтому ACK/ignore без native отмены запрещён.

Узкий ремонт перед повтором: строгий размер/route0 parser; распознанный
autoAim(target!=0) явно недоступен и отменяется original zero-argument
onAutoAimVehicleLost, восстанавливающим мышь. Cancel0 принимается без обратного
callback, чтобы исключить цикл. Серверное сопровождение цели не реализуется
под видом ACK. Не читать и не публиковать скрытое состояние цели. Добавить
captured regression, cancel/replay/whole-frame rollback и native callback
source proof, выполнить current-head full/build и новый fresh run с текущим БК.

Failure evidence: `local/evidence/20261016-p08c-autoaim-failure01`; собственные
процессы morning-natural01 остановлены по receipts. Consistent backup сохранён,
A123/B38, ammoA[0,0,5]/B[0,3,9],active0. Расход не компенсировать.

## Принятый узкий checkpoint autoaim06

Runtime46d5c20 full1136PASS/5oldignored/buildPASS/689raw source exact.
Owner подтвердил снятие захвата/мышь/личные итоги/оба natural ангара.
Actual arena2975833524010313505: Elimination/B90damage/1kill/1spot, оба
BattleFinished/full Results8/Avatar100/actualAccount1500/acked/naturalreturn/
hangar; dead routed bind A отработал, rejects/faults/idle_timeout0.
Independent result-only wire9474packets PASS. Optional autoaim03: B2ненулевых
запроса/2callbacks/ACK/own aim/heartbeat PASS, A лишьcancel0 и nonzeroNOT_RUN.
Owner mouse обоих подтверждена, target tracking не реализован.
A126/B41,ammoA[0,0,4]/B[0,3,4],active0. Evidence
`local/evidence/20261016-p08c-autoaim-acceptance01/acceptance02.json`, SHA
`6d607b6e4c2b29e1e07a756fe7f59cd6eeaf5fb182a9aba88ebd5af0825ea75a`.
Полная карточка P08C и её родители не приняты; capture/timeout/repeat/early
leaver остаются открыты. Main не менять. Owner отдельно поручил детонацию
БК/башню и project-only потерю оставшегося loaded БК — новая зависимая P06T
ветка после этого checkpoint, без ретроактивного изменения текущих результатов.
