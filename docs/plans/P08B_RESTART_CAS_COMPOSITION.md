# P08B — перезапуск, warm/full sync и следующая CAS-операция

Зависимая `codex/p08b-restart-cas-composition` от BUILD-TEMP7d2252f, main
не меняется. Предыдущая native проверка резерв/recovery была частичной:
утренний postrestart mutation/warm source N→full1 ещё NOT_RUN. Ночь до09:00
позволяет продолжить автоматически без вопросов, сохраняя manual gate.

1. Продвинуть frozen parent02 (manifest e442418bfbd0eb9ffb9ae94a352000a3f20857d98d8d902bcf2f2c438315cdea)
   из ignored staging: test-only Rust child + Node controller и регистрацию.
   Ни production session/worker/store, ни игровые DB/клиенты не изменять.
2. Обычный Rust test запускает Node и тот же test exe двумя фазами. Actual
   production HTTP/SQLite/identity/Job/Dispatcher: reserveAP20, exit process,
   bridge reopen без самовольного recovery, новый actual Config/run UUID,
   aborted_restart ровно раз, unload20→19, новый reserve, authoredHP0 Finish,
   Account reset/ACK, неверный warm1 atomically refused, верный warm2 +shop/
   dossier fullsync→wire1, следующая unload19→18/CAS→wire2.
3. Отдельный disposable seeded DB/own credentials/explicit test-only100-shell
   grant, loopback port0. Нет игровых UDP sockets/изменений утреннего стенда.
   Independent SQL: active0, два settled reserves, repair90/consumedAP0,
   depot+2/loaded18, ресурсы/crew/research/старые journal rows неизменны.
4. Canonical full current head с raw source before/after, fresh C-temp target.
   Внутренний parent proof PENDING_PARENT_FULL_GATE до внешнего gate; без
   новых ignored tests, пропусков или требований своего будущего result.json.
5. Сохранить branch/tests/evidence/report; далее P08C conservative late-result
   append. Native/UI/gameplayUDP/геометрическая гибель не проверяются этим
   authored Session/ACK/HP0 тестом и остаются NOT_RUN.

Source prerequisites — существующий source-bundle-05 и оригинал#717 read-only.
При их отсутствии тест FAIL, не silent skip. Свои дочерние процессы ограничены
временем/ChildProcess handles; ошибка сохраняет evidence и ожидает их close.
Откат — предыдущий checkpoint7d2252f; удалить только регистрацию и два новых
test source в новом коммите. Старые receipts/builds/stand не трогать.

Canonical full01 на0b548f7: existing1188PASS/новый1FAIL/5oldignored. Ошибка
не в runtime: Node guard сравнивал verbatim argv с обычным fileURL path и
молча пропускал main; actual result отсутствовал. Source715 before/failure
exact, evidence20261016-p08b-composition-full01 сохранён. Real Node invocation
regression воспроизвёл10PASS/1FAIL до fix; guard нормализует обе стороны.
Нужен fresh full02, прошлый FAIL не заменяется частичным запуском.
