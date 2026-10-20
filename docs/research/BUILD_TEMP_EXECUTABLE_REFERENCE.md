# BUILD-TEMP: verified executable остаётся в owned OS temp

Техническая ветка `codex/build-temp-retained-executable` от NET union43790d1,
runtime442ce7d. Изменены только server/build.py и
tests/test_build_temp_reference.py; default восемь helper AST и прежний copy
ABI сохранены. Исходный дефицит D около80MiB. Старые данные не удалялись и
не перемещались; automatic cleanup отсутствует.

Новый `--retain-temp-executable` разрешён только canonical gateway вместе с
`--cargo-temp-target`. Он оставляет exe в точной fresh default OS-temp Cargo
allocation на другом диске, проверяет origin/output/environment, local path/
no reparse, regular MZ/size/file identity и hash before/handle/after. Result
получает явный mode/path/reference SHA. Ошибочная ссылка не выбирает старый
D exe. Строгий consumer `built_executable_for_result` повторяет проверку.

VERIFIED:17 новых Python guards и11 прежних PASS,0skip. Canonical actual full
**1573PASS/0FAIL/5oldignored/buildPASS/876rawsourceexact** на этом source head
прошёл с новым режимом. D output/target и copy receipt отсутствуют. Actual
exeSHA `082217015b1167d300d825b5cd7d9307f08153afa3eaf1f5a7ce64f6438fc4a7`.
Новый own-host encrypted Login/Base smoke также действительно исполнил этот
C exe, проверенный по SHA+PID+creation receipt, затем остановил его.

Команда driver: `python -B -X utf8 server/build.py gateway --test
--cargo-temp-target --retain-temp-executable --out
local/build/server/gateway-net-retain-full01`; environment1/0/0/0,
полный before/after runner и реальные receipts —
[NET02_LOSS_TRAINING_INTEGRATION](NET02_LOSS_TRAINING_INTEGRATION.md).
Gate03 импортировал exact build.pySHA
`9126038cc054e3f2ed76dcaf220f44a7ec909a5aa9ddead5f9557f7a193d1ada`.
Новый raw source ZIP также создан отдельным файлом в own C target, без
перемещения старых evidence. Никакого UI/native PASS из этих фактов нет.

Ограничение: старые D-only consumers честно отказывают C mode. Утренним
runner13/15 нужен отдельный проверенный consumer successor; вручную копировать
exe/перетегировать старый binding нельзя. Новый mode не решает большой размер
SQLite/fixture outputs тестов на D: после full осталось около40MiB. Следующая
техническая предпосылка проверит NTFS compression ТОЛЬКО fresh empty owned
output directories перед их первыми writes; старые файлы/каталоги не трогать.

Статус SOFTWARE_PASS; native/Linux/legacy mode NOT_RUN. Откат — revert двух
source/test файлов или predecessor43790d1; хранить C target и receipts до
окончания зависимых проверок. Единственный следующий шаг — fresh-output
compression prerequisite, затем Hold5, без изменения production path guards.

После сохранения веток Git checkout нормализовал один новый тест в CRLF.
Проверка876raw это обнаружила: normalized content был тем же. Точные проверенные
LF bytes восстановлены из sealed C source archive; отдельный .gitattributes
pin предотвращает повторение. Receipt checkout-eol-restoration.json рядом с
полным proof. Это восстановление tested bytes, не новый запуск тестов и не
подмена исходника ради прохождения gate; все876raw снова совпали с full.
