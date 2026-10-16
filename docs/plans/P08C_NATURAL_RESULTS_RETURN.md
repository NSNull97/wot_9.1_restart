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
Следующий шаг — точный native parser/detail contract, затем узкая правка.
