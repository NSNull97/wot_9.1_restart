# ADR-001 — NATIVE_PRIMARY; зависимости остаются экспериментальными

Статус: **PROVISIONAL STACK / P01 PASS / P02 LOCAL GATEWAY/SESSION PASS, FULL GATE PARTIAL**. Дата: 2026-10-04.
Цель не меняется: отдельный авторитетный сервер для закреплённого клиента.

## Проверенные ограничения

1. Локальный клиент — v.0.9.1 #717/RU, i386, активный runtime Python 2.7.3
   подтверждён trace. Исходный manifest закреплён.
2. Есть настоящие entity definitions, descriptors и collision geometry.
   Это не заменяет framing/login/lifecycle corpus.
3. wg-toolkit-rs `5b879f0...` собирается и читает XML, но его vertex decoder
   не соответствует legacy stride; stock native login несовместим. Узкий
   собственный legacy091 profile с toolkit reply writer проверен реальным клиентом.
4. JoltPhysicsSharp 2.22.0 / Native 1.1.0 реально работают в headless net9.0
   на Windows x64. Проверка не охватывает гусеницы и историческую физику.
5. Instance mutex воспроизводит early exit. Compiled diagnostic `.pyc`
   загружается; login/rejection и штатный выход повторены дважды.
   [Измерения](../research/P01_BOOTSTRAP_AND_NATIVE_LOGIN.md).
6. Отдельная карточка P02 подтвердила LoginSuccess и первый BaseApp request
   в двух реальных запусках. Blowfish LoginSuccess encoder toolkit подходит
   измеренному сценарию; modern BaseApp layout не подставляется в legacy.
   [Измерения](../research/P02_LOGIN_REDIRECT.md). Полная сессия не проверена.
7. [BaseApp reply](../research/P02_BASEAPP_REPLY.md) подтверждён двумя реальными
   runs: u32 token в encrypted reply, первый encrypted frame с echo token,
   native LOGGED_ON. Полный канал/Account не реализованы; после неизвестных
   сообщений наблюдается callback 6/NOT_SET.

## Решение

- Сохранить **NATIVE_PRIMARY**. Смена на CUSTOM_ADAPTER не разрешалась и не
  выполнялась. Diagnostic personality использует родной BigWorld.connect;
  это исследовательский вход, без собственной симуляции или офлайн-ангара.
- Основные resource tools используют Python 3 stdlib; для статического PE
  анализа использованы pefile 2024.8.26 и capstone 5.0.9. Отдельный CPython
  2.7.3 компилирует только наш diagnostic source; системная установка не менялась.
- wg-toolkit использовать как закреплённый исследовательский кандидат.
  Не принимать его целиком как совместимый gateway/importer и не исправлять
  vendor скрытыми непроверенными патчами. Собственный профиль не меняет vendor:
  measured framing, bounded RSA/fields, код 73 из EXE; generic reply bundle writer
  переиспользован. XML/geometry/stock login/profile имеют разные статусы.
- .NET/Jolt оставить кандидатами для отдельного авторитетного процесса.
  Использованный net9.0 — локальный spike; .NET 10 и production stack пока
  не приняты на основании недоступного теста. Пустые server projects не созданы.
- Сейчас не вводить межъязыковую границу Rust/C# ради схемы из плана. Выбор
  gateway процесса определяется только следующим реальным native experiment.

Сохраняемые границы: сетевые IDs/серилизация — compatibility; доменные IDs и
авторитетные правила — domain/simulation; исходные resource IDs/path — content
provenance; публичные подписи — отдельные данные по NAMING.

## Альтернативы и последствия

Полностью принять toolkit сейчас нельзя: есть измеренные resource и native
mismatches. Корпус начального login/rejection теперь есть. Писать новый протокол/глубокий adapter без
решения владельца нельзя. Откладывать все исследования из-за runtime-блокера
тоже не требуется: независимые ресурсы и headless API уже проверены.

Native-путь поддержан [локальным gateway/session рубежом](../research/P02_LAB_GATEWAY.md):
10 native входов/выходов на одном процессе, selective ACK/retry, auth/digest
rejection, duplicate/disconnect/recovery. Затем подтверждён [native Account
creation contract](../research/P02_NATIVE_ACCOUNT.md): ID5/type0/три свойства,
пять native runs и отрицательный no-creation control. Original Python lifecycle
пока FAIL на отсутствующем Settings bootstrap. Публичный сервис ещё не доказан.
Первый server seq0 и duplicate уже подтверждены native cumulative1/1:
[server reliable](../research/P02_SERVER_RELIABLE.md).
ACK первого client frame и limited keepalive до 21.61 s уже подтверждены
[controls и повторными runs](../research/P02_CHANNEL_ACK.md), без Account.
Полный gate P02 PARTIAL; последующий Account lifecycle/UI/fragments требуют
следующих реальных проверок. Следующий узкий шаг — original Settings bootstrap.

## Откат и пересмотр

Все client patches уже откатились, обе копии совпадают с baseline по всем
файлам. Инструменты и lockfiles изолированы; зависимости лежат в ignored local.
Нет schema migrations, server DB, открытых публичных endpoints или внедрённых
production dependencies. Решение пересматривается после двух подтверждённых
native сообщений и lifecycle evidence; смена транспорта требует владельца.
