# Bounded local client update-gate diagnosis

## Цель

На изолированном локальном стенде воспроизвести окно клиента «Требуется
обновление», собрать только собственные loopback-события клиента и gateway и
определить, какой фактический login status/reply вызывает модалку. Оригинальную
копию клиента, внешние WG/Lesta endpoints и системный packet capture не трогать.

## План

1. Проверить версии/хэши исследовательской копии, `version.xml`, `paths.xml`,
   install ledger и endpoint; убедиться, что клиентская копия отделена от
   оригинала.
2. Поднять свежую копию локального bridge/gateway с bounded native capture,
   одним собственным тестовым аккаунтом и явным loopback endpoint.
3. Запустить минимальный native-клиент без crew/battle сценариев и сохранить
   trace, gateway log, capture receipt и screenshot состояния update/login.
4. Сопоставить raw login reply code, client callback и gateway reason. Проверить
   отдельно коды 73 (`SERVER_NOT_READY`) и 74 (`UPDATER_NOT_READY`) только на
   локальном стенде, без подключения к внешним операторам.
5. Если найдено исправление в проектном коде, внести минимальный обратимый патч,
   прогнать targeted tests и обновить ACTIVE_GATE/STATUS с доказательствами.

## Ограничения

- Никаких внешних снифферов, системного capture и Lesta/WG endpoints.
- Credentials в trace не записывать; только длины, хэши и статусы.
- Не объявлять причину доказанной до совпадения raw reply, client callback и
  gateway receipt в одном bounded run.

## Откат

Остановить локальные процессы; использовать install ledger/rollback для копии
клиента. Удалять только свежий run-каталог и его WAL/SHM после сохранения
evidence. Исходную копию клиента не изменять.
