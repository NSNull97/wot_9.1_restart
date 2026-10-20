# Fresh composition outputs: Windows NTFS compression

Ветка codex/build-fresh-test-compression от NET33d964e. Runtime
`cc2a94d95965a430e9968977cd5cbdeaf8c22be8`. Цель — сократить новые SQL/fixture
outputs при оставшихся35MiB на D, сохранив старые данные и production paths.

Изменены только test-only shared/composition_storage_tests.rs, его cfg(test)
регистрация в shared/mod.rs и по одному call в трёх composition parents:
profile13_restart_cas_tests.rs, p08c_late_composition_tests.rs,
p10b_loss_composition_tests.rs. Raw-byte .gitattributes pins добавлены для
новых/изменяемых tests. Production Web localPath/Node/seeds не расширялись.

Helper вызывается сразу после create_dir и до первого parent-control. Scope:
точный compiled ROOT/local/test-runs, пять закрытых namespaces, run-currentPID-
currentNonce, empty directory/no reparse, nonce/actual creation не старше30s,
same handle identity, NTFS compression capability. Win32 FSCTL_SET_COMPRESSION
ставит default compression только на directory; первый файл — собственная
квитанция. Recursive compact, обход старых outputs, удаление, перемещение и
uncompress отсутствуют. Ошибка после FSCTL сохраняет новый частичный output.

VERIFIED actual canonical focused: **4PASS/0FAIL/0ignored/buildPASS**,0.06stest/
48.40sdriver, **877rawsource before==after**, retainedC/noDduplicate.
Проверены настоящий новый NTFS directory и1MiB authored zeros с readSHA exact
и меньшим allocated size; отказ nonempty с unchanged bytes/attributes,
foreign namespace/currentPID и существующий Windows junction read-only.
FFI на настоящем canonical Windows path также реально прошёл этот запуск.

```powershell
python -B -X utf8 local/evidence/20261017-fresh-compression-focused01/run.py
```

Команда выполнена с env1/0/0/0 и source capture; output fresh, повторять поверх
него нельзя. Полная driver command/log/result:
`local/build/server/gateway-fresh-compression-focused01`.
Evidence `local/evidence/20261017-fresh-compression-focused01/source-before.json`,
`source-after.json` и `local/evidence/20261017-fresh-compression-promotion01/result.json`.
Frozen22 SHA75b3fa4ab3c000119c47ad8a30a87a120c27538f633da0f2252b7cfdace21995;
авторитетный integration02.patch, старый integration.patch/parents01 — WIP.

Полный combined regression и фактический объём SQL outputs — **NOT_RUN** до
следующего dependent Hold full. Четыре focused tests не доказывают actual
HTTP compositions. Python operational sibling22 также пока не сжимал stand;
два tiny прототипа выполнены на новых своих каталогах, старые untouched.
Native/Linux/две машины NOT_RUN. Mainffce8cb сохранён.

Откат — predecessor33d964e или revert этого test-only source commit, сохраняя
все outputs/receipts/C targets. Единственный следующий шаг — отдельная Hold5
integration с сохранением cfgstorage registration, focused30 и actual/full.
