# BUILD-TEMP — место для продолжения ночных сборок

После P06T checkpoint ed67531/14bf2e7 на D осталось примерно0.5GiB, на C —
около64GiB. Исторические builds/evidence/DB и клиентские копии не удаляются.
Предыдущий отказ automatic cleanup не обходится. Это техническая предпосылка
продолжения разрешённой ночной реализации, а не новая игровая возможность.

Отдельная зависимая ветка `codex/build-temp-cargo-target`, только после
завершения текущего isolated loss startup smoke. Main не меняется.

1. Добавить явный `server/build.py gateway --cargo-temp-target`, только для
   canonical gateway; старый default/legacy/physics сохранить. Не принимать
   пользовательский путь наружу: создать fresh `wot091-cargo-*` исключительно
   в default OS temp на другом локальном диске, проверить junction/reparse и
   сохранить происхождение в обеих собственных папках. Ничего не удалять.
2. Cargo dependencies/intermediates остаются в C temp. После действительной
   сборки эксклюзивно скопировать только bounded regular MZ executable в
   привычный fresh D `local/build/.../target/debug/sr-gateway.exe`; проверить
   source SHA до/после, size и output SHA. Logs/result/source proof остаются
   в обычном D output. Ошибка сохраняет оба дерева и явно возвращает FAIL.
3. Добавить meaningful unit guards: wrong mode, existing/escaping output,
   reparse, actual fresh C allocation, actual tiny-file export и испорченный
   hash. Не запускать очистку даже тестовых temporary directories.
4. Проверить новый режим полноценной canonical сборкой/тестами current head
   с before/after source map; убедиться, что фактическая C→D копия равна и
   deployed gateway/старые proofs не менялись. При необходимости source EOL
   новых файлов закрепить явно до gate, а не переписывать проверенные proofs.
5. Commit/evidence/DEV_NOTES, затем отдельная P08B restart/CAS ветка. Утренний
   loss стенд остаётся привязан к ed67531; этот tooling checkpoint сам по себе
   не означает приёмку новой native механики.

Откат — старый build command без флага и сохранённая ветка. Новые C/D outputs
остаются для аудита; перемещения или удаления существующих файлов нет.
