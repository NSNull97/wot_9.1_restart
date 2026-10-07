# P02: первый reliable packet сервера → настоящий ACK клиента

Дата: 2026-10-04, Asia/Yekaterinburg. Владелец попросил сообщить готовность
и продолжить следующий шаг после P02_CHANNEL_ACK.

Цель: отправить один пустой reliable server packet с sequence=0 и увидеть
изменение native client cumulative ACK с 0 на 1. Затем намеренно повторить
тот же packet и проверить, что подтверждение не превращается в ACK=2.
Это контроль первого номера, а не общий retransmission/window implementation.

1. Snapshot own source/config, mutex и полные client manifests; original
   только читать. Параллельные web/ и local/web/ не менять и не включать в откат.
2. Отдельный ограниченный профиль на прежних loopback endpoints. Гипотеза:
   clear flags 0x0458 + sequence u32 + cumulative ACK u32, без app payload.
   До настоящего опыта формат S→C не объявлять проверенным.
3. Унаследовать подтверждённые login/BaseApp/first-client-ACK/keepalive;
   отправить sequence=0 после handshake и один контролируемый дубликат.
4. Записать реальный client reply, сверить token/flags/sequence/ACK независимо,
   проверить старый режим без server sequence и повторить положительный опыт.
5. Отрицательные проверки размера/token/преждевременного и неверного ACK,
   регрессия применимых старых проверок, полный откат, STATUS и отчёт.

Нет Account/entities/арены, production retransmission или внешних endpoints.
Evidence: local/evidence/20261004-p02-server-reliable/.
Откат: own project-before.zip + project.local.before.json; client ledger/backup
и tools/client_probe.py restore --out <run> после остановки его процессов.

## Результат

PASS: три corrected native runs и контроль, 35 новых + 34 regression checks,
13 Rust / 20 Python tests. Предположение о token в transport ACK опровергнуто
реальными bytes; native-01 observer FAIL сохранён. Все пять runs откатились.
[Отчёт](../research/P02_SERVER_RELIABLE.md). Общий канал/full P02 NOT_RUN.
