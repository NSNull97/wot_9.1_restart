# P05C: native contact → health publication failure

Ветка `codex/p05c-ram-health-publication`, parent `ea3343b`. Main не менять.

## Подтверждение

19 октября владелец на fresh full-polygon stand воспроизвёл два сброса боя:
контакт IS-7/IS-7 на уклоне, затем контакт с MS-1. В обоих server failure
`p06t_publication.rs:99:106`: HP уменьшен тараном, но fallback publication ищет
только projectile `damage_events` и отклоняет корректное ram-состояние.
Сервер/клиенты остались живы, durable returns и сохранение loaded прошли.
Видимое вхождение корпусов отдельно исследовать: его причина ещё не доказана.

## Работа

1. Сохранить оба actual failure witnesses, профиль/БК и bounded cadence.
2. Воспроизвести ошибку через настоящий recipient publication на committed ram
   event. Проверить nonlethal/lethal и порядок с projectile causes.
3. Исправить выбор последней подтверждённой причины HP, сохранив native reason,
   приватность скрытого attacker и существующие projectile/fire/detonation пути.
   Не создавать фиктивных shots и не подавлять bad().
4. Прогнать узкие regression, затем canonical gate на новом head с тяжёлыми
   targets только D. Сохранить как FAIL/NOT_RUN всё, что не запускалось.
5. Только после автоматических проверок подготовить новый bound successor из
   последней actual БД и один повторный native contact-тест. Прежние БД/стенды
   и evidence не изменять. Текущие клиенты до готовности не перезапускать.

## Приёмка

Native: контакт не сбрасывает бой; HP/attacker/reason корректно публикуются
обоим; корпус-корпус, склон и последующий возврат проходят отдельную проверку.
До фактического повторного прогона native FAIL/open. Откат — остановить только
новые owned processes и вернуться к parent ea3343b с сохранением actual БД.
