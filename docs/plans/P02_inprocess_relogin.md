# P02 — повторный вход в одном процессе

2026-10-05. Отдельная ночная проверка уже реализованного Account/Hangar после
закрытия карточки окон windows01→02. Основание:
`local/evidence/20261005-p02-hangar-windows/gui/next-narrow-checks.md`.
До эксперимента same-process logoff/relogin UNKNOWN/NOT_RUN; баг не объявляется.

1. Сохранить sources/config/profile/consistent DB baseline при normal005.
   Original read-only. Endpoint/backend/generators/fixtures/оба profiles frozen.
2. Отдельный opt-in диагностический модуль. Один EXE/PID/init, настоящий
   синхронизированный МС-1 с двумя танкистами,15 последовательных секунд
   наблюдения и native PNG. Никаких input events/имитации ручного меню.
3. Один measured original `g_windowsManager.window.logoff()`; original
   Account.onBecomeNonPlayer, настоящий disconnected callback и LoginView.
   Не вызывать watcher/lifecycle вручную, не очищать кэш, не менять player.
4. Повторный original LoginView.onLogin теми же собственными credentials.
   Одноразовые данные сохраняются только в памяти явной диагностики, очищаются
   сразу при втором submit/ошибке/fini. Не сбрасывать consume_control и не
   добавлять автологин в обычную сборку. Пароль/его производные не логировать.
5. Второй реальный вход/handshake/session/Account в том же PID,15 секунд
   непрерывно готового ангара, прежние UUID/nativeID/resources/stats/дескрипторы/
   обе машины и экипаж; второй native PNG. Адреса Python objects могут
   переиспользоваться — не делать из их неравенства критерий нового Account.
6. Независимый verifier: два последовательных wire sessions, retirement
   первой до принятия второй, точные payloads/real cached requests в каждом,
   отсутствие мутаций/свежих ошибок и один конечный cleanup/exit0/rollback.
   При найденном дефекте сохранить FAIL, исправлять только доказанную причину.
7. Вернуть обычную установку с проверенными sources безcontrol/autoquit,
   полный manifest/ledger и account аудит, STATUS/отчёт/точные команды/откат.

15 секунд — измеренный минимальный regression gate, не таймер закрытия EXE.
Harness ждёт штатного native выхода по завершённому условию; kill/timeout нет.
Ручное подтверждение диалога пользователем и длительная устойчивость NOT_RUN.
Сетевой бой, новая экономика, каталог снаряжения/кастомизации и ИС-7 crew вне
этой карточки. Полный P02 остаётся PARTIAL.

Evidence `local/evidence/20261005-p02-inprocess-relogin/` (R).
Статус PASS. Baseline288sources/14local/2DB сохранён до правок.
Runner37 checks, direct personality control5 checks, общий interactive regression23
PASS. Normal005 проверен и откатан перед диагностикой.

## Подтверждённый дефект R01 и узкое исправление

R01 завершён FAIL: первый ангар появился, original logoff удалил Account repository,
второй настоящий login получил `LOGIN_REJECTED_SERVER_NOT_READY`. Сервер записал
`AUTH_REJECT code=73 allocated=0 reason=retired_or_rate`. Клиент повторно использовал
транспортный ключ, но сменил зашифрованный nonce и LoginApp endpoint. Первая сессия
закрыта до второго запроса. Второй BaseApp endpoint пока UNKNOWN.

Полный отрицательный результат сохранён до изменения gateway:
`R/wire/verify-relogin01-negative-01/inprocess-relogin-verification.json`, SHA256
`8b3dea4c27a28b51861672b5cb54601e8a32ee19af76a0b1ee85deb39d808dfe`.
95 пакетов, один PNG, exit0/12 cleanup/restore PASS. Это не успешный relogin.
Прежние verifier/tests/gateway сохранены в `R/wire/verifier-before-gateway-fix-01`.

Разрешено исправить только доказанную политику retirement gateway:

- Небольшой bounded журнал закрытых попыток: ключ, nonce, login/base endpoints,
  TTL120 секунд, максимум32 записи. Не вытеснять защиту ради новой сессии.
- Повтор старого nonce отвергать; свежий nonce с тем же ключом требует новой
  проверки собственных credentials через сайт. Проверять условия до и после KDF.
- При том же ключе прежние endpoints закрытой сессии отвергать до handshake,
  decrypt и обработки ACK, чтобы старые ACK/heartbeat не меняли новое окно.
- Повтор того же ключа и endpoint остаётся недоступен до истечения TTL.
  Активная подмена UDP source address этим не решается; это ограничение стенда.
- Noninteractive lab сохраняет консервативную политику. Генераторы, fixtures,
  аккаунты и конфигурация не меняются.

Отдельно версия диагностического сценария получает пассивное наблюдение отказа
второго login: завершение ошибкой через существующий штатный quit на следующем
advance, без исключения из родного callback и без ожидания600 наблюдений.
После unit/negative checks — новый native run и независимая проверка обоих
реальных login/Account/PNG. Старый FAIL сохраняется.

Завершено05:06: R02 strict PASS9f42acfd…b071, root повтор PASSb0152450…1369.
Два настоящих входа,188packets,2PNG,0 новых ошибок,exit0/12cleanup/restore.
Gateway83/verifier83/scenario112 executed tests PASS. Ordinary006 установлен,
original3469/research3486 full audit PASS0ff1f08a…ff35,0unexpected,обаprofiles
неизменны. Ручная приёмка NOT_RUN. Следующая карточка отдельно: переключение
существующих аккаунтов primary→secondary→primary без сброса кэша.
