# Ручная проверка утренней сборки009 — 5 октября 2026

Цель: зафиксировать фактический ответ владельца и сохранить логи, не повторяя
ночные тесты и не управляя запущенной игрой.

Позднейшее дополнение: владелец также подтвердил естественное истечение
сессии и повторный вход, backend связал session11→12. Отдельный результат:
[P02_MANUAL_EXPIRY_20261005.md](P02_MANUAL_EXPIRY_20261005.md).
Ниже сохранены выводы первого ручного прохода до этого события.

## Результат и происхождение

**OBSERVED / PASS_BY_OWNER:** после сообщения «проверил» владелец ответил
«Всё нормально» на вопрос: «Как прошло: вход, экипаж МС-1 и переключение
МС-1 ↔ ИС-7 отображались нормально, или что-то сломалось?».
Ручная приёмка этих трёх пунктов закрыта. Скриншоты этого прохода не переданы;
прочие окна, операции и 30-минутное истечение сессии этим ответом не проверены.

**VERIFIED:** read-only snapshot всех23 immutable файлов установленной009
совпал с принятым полным манифестом L. Сохранены отдельные копии трёх
клиентских логов и четырёх backend logs; исходные файлы не менялись.
Последний сохранённый блок python.log начинается05.10.2026 10:05:36 местного
времени, last write05:06:54 UTC:0EXCEPTION/0Traceback. В нём остаются два
ERROR `Vivox is not supported` и завершение `PostProcessing.Phases.fini()`.
Это не утверждение о полном отсутствии любых сообщений ERROR.

Gateway session10, строки2370–2518 сохранённого `backend/gateway.stdout.log`:
успешный вход primary через website_users; CMD100/300/600; showGUI queued;
повторная синхронизация no_change;11ответов CCU1/1;51reliable sequence0..50
с attempt1; final ACK51/pending0; `client_disconnect`, retired_pending0.
Отказов и неподдержанных команд в этом отрезке нет; оба stderr пустые.
Серверная постановка showGUI сама по себе не доказывает отрисовку интерфейса.

**INFERRED:** session10 соответствует завершённому утреннему проходу владельца
по порядку событий. Gateway stdout не содержит wall-clock timestamps;
строгая привязка session10 к конкретному клиентскому блоку не доказана.

**OBSERVED:** после session10 началась отдельная session11, а при snapshot
client mutex занят. Текущая активность не объединена с завершённым проходом;
содержимое ещё буферизуемых логов неизвестно. Игра не закрывалась инструментом.

## Файлы и воспроизведение

Evidence E=`local/evidence/20261005-p02-manual-acceptance/`:

- `capture_review.py` — собственный read-only snapshot helper;
- `review01/result.json` — ответ владельца,23hash comparisons, времена,
  хеши и stability flags семи сохранённых логов;
- `review01/client/` и `review01/backend/` — неизменённые копии логов.

SHA256 result.json:
`9903b5ed5dc0c63702bec6d01fb826f9378bdd1294f05dd633f79d191934e50b`.

Выполнено из `D:\WoT_9.1_Server`:

```powershell
python -B -X utf8 tools/local_server.py status --config local/server/service.json
python -B -X utf8 local/evidence/20261005-p02-manual-acceptance/capture_review.py
```

Helper требует отсутствующий `review01`; повторный вызов намеренно откажет,
сохраняя исходные доказательства. Для read-only повторного просмотра:

```powershell
Get-Content -LiteralPath local/evidence/20261005-p02-manual-acceptance/review01/result.json
Get-FileHash -Algorithm SHA256 -LiteralPath local/evidence/20261005-p02-manual-acceptance/review01/result.json
```

Изменены только STATUS, дополнение ночного отчёта и этот отчёт; новые evidence
игнорируются Git. Код, базы, клиенты и прежний архив318files не менялись.
Новые native/unit tests NOT_RUN; откат работающей системы не требуется.
Снимки новых owner logs следует учитывать перед будущим rollback ordinary009,
не заменяя ими старые принятые evidence или ledger задним числом.

Приёмка: PASS_BY_OWNER для трёх пунктов; полный P02 PARTIAL.
Единственный следующий шаг: реальный expiry1800→disconnected→LoginView.
