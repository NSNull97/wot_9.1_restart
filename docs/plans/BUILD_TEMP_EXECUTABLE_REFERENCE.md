# BUILD-TEMP: явный verified retained C executable

Техническая ветка `codex/build-temp-retained-executable` от NET union43790d1.
На D осталось около80MiB; старые данные не удалять/перемещать. Полный Cargo
target уже создаётся на C. Новый независимый opt-in сохраняет там же verified
gateway exe вместо второй копии20MiB на D. Default copy ABI не менять.

1. Применить два exact frozen02 source/test файла после baseline SHA проверки.
   Explicit selector только canonical gateway + --cargo-temp-target. Строгий
   built_executable_for_result проверяет allocation/origin/environment/MZ/
   file identity/hash и mode; неправильная ссылка не выбирает старый D exe.
2. Запустить17 новых Python guards и11 предыдущих; source exact before/after.
   Новый external full gate обязан явно использовать строгий consumer.
3. Выполнить canonical full объединённого NET head с --retain-temp-executable;
   raw source before/after, source archive, actual test/build/exe receipts,
   проверить отсутствие D duplicate. Actual новый ABI до запуска NOT_RUN.
4. Отдельно сохранить docs/checkpoint/push, затем вернуть техническую ветку в
   зависимую NET ветку. Main и принятые старые receipts не менять.

Frozen inputs: local/night-staging/20261016/build-temp-reference02/freeze01.json
SHA cf6c1bb04a7536d12d4890d0fb163530a52c278a0fe2209d5b3f6a3171e4b77f.
Root и отдельный reviewer не нашли конкретного source blocker; это не build
PASS. Runner13 пока D-export-only, final morning build сохранить default
экспортом или подготовить отдельно проверенный additive consumer successor.

Откат — P10B/NET predecessor или revert только технического source commit;
все новые/старые target/receipts оставить. Native/client/gameplay NOT_RUN.
