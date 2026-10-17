# STAB-01: утренний регресс возврата Core

Цель: оба настоящих клиента после выстрелов возвращаются в ангар без выброса;
мир не сбрасывается до завершения terminal Avatar/asyncFinish, ошибка боя не
создаёт бесконечный цикл containment/reset. Обязательный manual критерий после
автоматических проверок остаётся NOT_RUN до ответа владельца.

Ветка `codex/stab01-core-return-reset` зависит от сохранённой ночной цепочки
e6112a4c/200dcd2/runtime64767ec. Это исправление нового detonation/Leaving пути
поверх принятого P08C, поэтому начинать с main без цепочки нельзя.

1. Сохранить actualFAIL: первый fault, native prefix, writer/SQLite остатки,
   owned stop receipts. Не удалять103MBlog и не откатывать боекомплект.
2. Исправить reset barrier для current-battle native Avatar независимо от
   наличия события детонации. Queue cancel до Avatar не должен зависнуть.
   Отдельно проверить настоящий battle-failure путь без повторной публикации
   старого slot на новом мире. Не глушить mod303 catch/ложным успехом.
3. Регрессии: Leaving без детонации, отложенный Finish/итоги/native ACK,
   возврат→единственный reset, queue cancel/чужойview; fault containment.
4. Один новый canonical full gateway build/source-before/source-after; прежние
   targets/exe/evidence сохранить. Перед сборкой проверить свободное место.
5. Новый Core stand из SQLite backup actualC profiles134/46 с loaded
   A[0,47,47]/B[0,49,45], depot прежний, active0. Не использоватьD129/43,
   не выдавать снаряды и не менять старый binding. УстановленныйV8 переиспользовать
   только после проверки всех plan.sources/bytes против новогоfullmap.
6. Запустить собственные службы иA→два настоящихангара→B; повторить ручной
   выход и следующий бой. FAIL/NOT_RUN оставляет карточку внеmain.

FX незасвеченного стрелка и задержки сохранены отдельными дефектами: их нельзя
объявить исправленными от устранения reset race. Реальные сроки queue/join
снять до и после с разделением native/input/writer/Avatar этапов.

Утренний full01 на25ac184 завершён:1624PASS/1FAIL/5old ignored,1292.59с.
Все6новых STAB регрессий PASS. Единственный FAIL actual4Hold: Node watchdog180с;
Final4/возвраты/all-finalSQL пройдены на162.139с, процесс остановлен в query/ACK
tail. Production state/panic failures не наблюдались; причина wall-time variance
UNKNOWN. Логи, failure.json и raw925-source equality сохранены; source-after gate
NOT_RUN из-за FAIL, старый запуск не объявлять зелёным.
Измеренный бюджет теста увеличен только в обвязке: Node180→210с, Rust parent
240→360с (seed120+phase210+margin30). HTTP/Finish deadlines и assertions прежние.
Read-only review выявил входящий native ACK containedAvatar, который обновлялся
по replacementWorld до receive. Incoming03 использует production helper с
проверкой retained identity/view/terminal receipt и атомарным receive на клоне;
phaseLeaving сохраняется, старые команды разбираются без допуска к authority.
Ошибка доставки результатов тоже выбирает retirement по сохранённому миру,
сохраняя Hold5 outcome. Три новые регрессии: ACK/confirmation/rollback/подмена,
обычный ingress refresh, Hold5 natural-old/new-live. Static review PASS;
полный full02 и native retest PENDING до фактических запусков.
Evidence: local/evidence/20261017-morning-core01/stab01_full01_failure_retained.json;
внешние audit781cedfe/budget02freeze52aa1063 сохранены отдельно.

Full02 наb1beb0f скомпилирован. Ранний focused14:13PASS/1FAIL — новый Hold5
fixture пропустил реальный Capture.departed_after_detach для ушедшего peer до
Forfeit, валидатор actual result/source terminal mismatch корректно отказал.
Полный запуск остановлен раньше через exact own test handle/image/creation и
runner ancestry, children0; cargo/build/runner завершились1. Все артефакты
сохранены, source925 до остановки совпал; full/source-after NOT_RUN/ABORTED.
Fixture04 добавляет только пропущенный production hook и проверки ownNone /
peerDisconnect/tick. Production/validators неизменны, static reviewPASS.
Следующий fresh target full03 и early14; старые full01/02 не перезаписывать.

Откат: остановить только новые ownпроцессы, вернуться к сохранённому runtime
через его неизменные артефакты в новом совместимом контексте; mutableDB/расход
не восстанавливать поверх позднего состояния. Следующий шаг — regression/full.
