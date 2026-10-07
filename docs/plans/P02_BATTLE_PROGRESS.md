# Карточка продолжения боя: стабильный жизненный цикл арены

## Цель

Продолжить путь от подтвержденной поездки к настоящему бою через один
проверяемый native-срез. Инфраструктурная ветка (server layout,
identity/site/DB boundaries) в эту карточку не входит.

## Этапы

1. Повторить один native вход на МС-1 и измеренный контракт снайперского
   режима на закрепленном клиенте #717. Проверить переключение режима,
   штатный выход в ангар и повторный вход в арену.
2. Выполнить один bounded native capture после стабильного входа в арену и
   проверить loadout/ammo transition. Этот запуск уже сохранён как
   `local/server/run-20261006T102148-d2dd40`: 345 пакетов и raw hash integrity
   PASS, но markers `AMMO/LOADOUT/BATTLE/FIRE/SHOOT` отсутствуют. Поэтому
   native decode и wire compatibility остаются NOT_RUN; этот receipt не
   является доказательством выстрела.
2a. До shot capture пропустить authenticated vehicle profile через отдельный
   domain loadout gate: mounted turret/gun, shell mapping и count должны быть
   согласованы; gate уже изолирован и fail-closed, но server-side battle
   route ещё не принят. При отсутствии реального Avatar ammo event gate
   остаётся закрытым. Этот gate не сериализует native packet.
3. Только после независимого разбора входа добавить минимальное
   авторитетное состояние выстрела (cooldown/ammo/shot event). Урон,
   баллистика, разрушения, матч 15x15 и второй игрок — отдельные карточки.

## Ворота приёмки

- PASS: настоящий клиент дошёл до PREBATTLE, штатно вернулся и повторно
  вошёл без разрыва; trace/rollback/hash receipt сохранены.
- PASS только для frozen capture integrity: `summary.json` имеет 345
  пакетов и `packet_hash_integrity=PASS`; это не PASS loadout/ammo.
- NOT_RUN: native loadout decode, AMMO/LOADOUT/BATTLE transition и capture
  выстрела; gateway markers для них равны нулю.
- FAIL: любой disconnect/reject или неподдержанный контракт; исходный trace
  сохраняется, код не маскирует ошибку.
- Никаких моков для native-совместимости и догадок по shoot payload.

## Границы и откат

Работать только с собственным loopback стендом и исследовательской копией
клиента; GUI ввод выполняет владелец вручную. Рабочий backend/site не
перезапускать в этой карточке. Новые outputs только под
local/evidence/20261006-battle-progress-*. Откат — удалить только новый
evidence/build output; продуктовые исходники, клиент, БД и deployed EXE не
изменять.

Frozen receipt `local/evidence/20261006-battle-progress-loadout-capture-01/`
сохраняется отдельно: после capture обычный backend восстановлен и
`native_wire_capture=false`; raw capture не перезаписывать.

