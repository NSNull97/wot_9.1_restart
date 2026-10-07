# CLIENT_AUDIT — P00–P01

Дата: 2026-10-02, Asia/Yekaterinburg. Run: `20261002-p00-p01`.
Приёмка P00: PASS в текущей среде. P01: PARTIAL, runtime-критерий не закрыт.

## Объект и baseline

Оригинал: `D:\WoT_9.1_Server\WoT_0.9.1_RU_0717_original` (только чтение).
Исследовательская копия: `D:\WoT_9.1_Server\WoT_0.9.1_RU_0717_research`.
Локальные результаты: `D:\WoT_9.1_Server\local`.

VERIFIED: в каждой копии **3469 файлов, 14 680 626 869 байт**.
До экспериментов и после отката совпали все относительные пути, размеры и SHA-256.
Канонический manifest содержимого обеих копий:
`74c37c18e9ac7e30196c134076dacf6f2a8bf3897f7def73905d09feb3647797`.
Он не содержит абсолютного корня, времени выполнения или mtime и потому
повторяется при неизменном содержимом. Полный manifest отдельно сохраняет mtime.

Доказательства: [baseline](../../local/evidence/20261002-p00-p01/baseline/),
[сравнение после отката](../../local/evidence/20261002-p00-p01/final-integrity/baseline-comparison.json).
Команда: `python -X utf8 tools/client_audit.py manifest --out <новый local-каталог>`.

VERIFIED: исходные 20 файлов пакета соответствовали `PACKAGE_MANIFEST.json`.
Первоначальный пакет сохранён в `local/baseline/project-package/`;
проверка — `local/baseline/package-check.json`. Git до запуска отсутствовал;
создан локальный репозиторий `main`, remotes/коммитов нет. Автор Git не настроен,
выдумывать имя или email не стали. Никакой исходный пользовательский diff не затёрт.

## Идентификация

| Статус | Вывод | Доказательство |
|---|---|---|
| VERIFIED | `version.xml`: `v.0.9.1 #717`, client `435206`, overrides `435633`, localization `428638 RU` | `version.xml`, SHA-256 `d9a36dfbd6eb8733e5b0cab367fbe4707e05f5379575b7a623a554a28c1ab48f`; `static/metadata.json` |
| OBSERVED | Windows version resource EXE: FileVersion/ProductVersion `0, 9, 1, 0` | `tool-environment.json` |
| VERIFIED | EXE — PE i386 (`0x14c`); SHA-256 `86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed` | `static/metadata.json`, полный manifest |
| VERIFIED | В EXE есть строка сборки `19:03:39 Jun 17 2014`, смещение 20741220 | `static/metadata.json` |
| VERIFIED | В Account.default требуется `ru_0.9.1_2` | `res/scripts/entity_defs/account.def`, `Properties/requiredVersion_9100/Default`; `decoded/...account.def.flat.json` |
| UNKNOWN | Аутентичность относительно дистрибутива издателя, отсутствие старых неофициальных патчей | Внешнего эталонного manifest/проверенной истории происхождения нет |

RU подтверждается содержимым файлов, а не названием каталога. `#717`, version
resource и строка совместимости — разные идентификаторы; ни один не подменяет другой.
Локальный config заполнен только установленными значениями.

## Скрипты и загрузка

VERIFIED: все **2255 `.pyc`** имеют magic `03 f3 0d 0a`; формат соответствует
семейству CPython 2.7. Источник формата:
[CPython v2.7.3 import.c](https://github.com/python/cpython/blob/v2.7.3/Python/import.c).
Отдельно проверено совпадение magic и таблицы opcodes версии эпохи клиента
v2.7.3 с техническим справочником v2.7.18, использованным при первом разборе:
`era-python-reference.json`. Более поздние игровые характеристики не привлекались.
Встроенные code records десяти ключевых модулей прочитаны ограниченным парсером
`tools/py27_static.py`, без `marshal.loads`, создания code objects или исполнения.

VERIFIED: EXE содержит строку `2.7.3` по смещению **19947044**;
`summary/resource-facts.json`. INFERRED: встроен Python 2.7.3.
В первом run runtime не был получен. Теперь **VERIFIED** по
`20261002-p01-bootstrap/native-05/runtime.jsonl`:
`2.7.3 (default, Jun 17 2014, 19:02:39) [MSC v.1700 32 bit (Intel)]`, pointer size 4.

VERIFIED: `paths.xml` задаёт порядок: `./res_mods/0.9.1`, перечисленные `.pkg`,
`./res`, `./res_bw`. `engine_config.xml/personality` — `game`.
В res_mods найдены только старые каталоги версий и текстовые маркеры, без
предоставленного исполняемого мода. Доказательства: полный manifest,
`static/metadata.json`, `decoded/res__engine_config.xml.flat.json`.
Поддержка `.wotmod` не установлена и не использовалась.

Первоначально загрузка собственного personality была INFERRED. В продолжении
`20261002-p01-bootstrap/native-05` она подтверждена для скомпилированного
`.pyc` в `res_mods/0.9.1/scripts/client/`. Source-only на этом пути дал ImportError.
Это diagnostic loader, а не подтверждённый запуск штатного игрового UI.

## Фактические запуски

В `client_patch/p01_probe.py` создан только собственный диагностический код:
runtime/version, маркер ResMgr, `BigWorld.connect('127.0.0.1:20014', ...)`,
таймер выхода. Игровой `game` не импортируется. Используется отдельная
одноразовая тестовая пара RSA и собственные тестовые login/password.

`tools/client_probe.py` до изменений сохраняет хеши и backup engine config,
логов и всех заранее известных затрагиваемых путей; патчирует только research;
после завершения сохраняет postrun и восстанавливает baseline.
Первичные настройки не менялись в original. Три запуска дали одинаковый
результат: процесс завершился с кодом **0**, до diagnostic init, пакетов **0**.

OBSERVED: свежего `python.log` нет; сохранённый лог побайтно остался старым,
с датой 2020 года. Старый лог не используется как доказательство запуска 2026 года.
В отладочном запуске 02 зарегистрировано 98 Windows debug events: загрузка EXE,
79 LOAD_DLL, два первоначальных debugger breakpoints, штатное EXIT_PROCESS(0).
Необработанный crash этой трассой не установлен. D3DX9_43/D3DCompiler_43
загружены; объяснять сбой их отсутствием было бы неверно.

Доказательства: `native-probe-01/`, `native-probe-02/windows-debug-events.json`,
`native-probe-03/outcome.json`, `patch-ledger.json`, `restore.json` и `postrun/`
в каждом каталоге. В окончательной версии runner возвращает ошибку, если
runtime/пакеты не появились; нулевой exit клиента не считается PASS.

Ограничения: нет системного egress-захвата или правила firewall; процесс не
имел административных прав. Все заданные экспериментальные игровые адреса —
числовой loopback; внешние login/аккаунты не использовались. Снимки памяти и
клиентские бинарники не публикуются. Полный запуск штатного UI — NOT_RUN.

## Продолжение и следующий проверяемый эксперимент

Описанные выше три запуска относятся к первому run. Продолжение воспроизвело
early exit занятым `wot_client_mutex`, подтвердило активный Python и обмен
native login/rejection. [Полный отчёт](P01_BOOTSTRAP_AND_NATIVE_LOGIN.md).
Предположение владельца о другой копии подтверждено как воспроизводимый
механизм; наличие mutex именно при старых запусках остаётся INFERRED.
После этого отчёта владелец разрешил отдельную карточку P02:
LoginSuccess/redirect → первый BaseApp request. Она выполнена с двумя
реальными запусками: [P02_LOGIN_REDIRECT](P02_LOGIN_REDIRECT.md).
Получены 28-byte reply и 21-byte BaseApp request с проверенным токеном;
успешная сессия и арена остаются NOT_RUN.
В отдельной карточке 2026-10-04 подтверждены также BaseApp reply, первое
зашифрованное сообщение и callback LOGGED_ON:
[P02_BASEAPP_REPLY](P02_BASEAPP_REPLY.md). Полный Account/игровой lifecycle
этим не проверен; raw callbacks и ограничение канала сохранены в отчёте.
В следующей [карточке ACK](P02_CHANNEL_ACK.md) timer/времена diagnostic
personality стали явными. Контроли ACK=0/1 отличили keepalive от прекращения
повторов первого packet; два завершённых real runs удержались до 16.59/21.61 s.
Windows UDP capture FAIL сохранён, исправление проверено, все patches откатились.
Следующая [server reliable карточка](P02_SERVER_RELIABLE.md) подтвердила
server seq0 и duplicate → native cumulative ACK1/1. Измерен transport-only
feedback без application token. Первый observer FAIL сохранён, три corrected
runs PASS; исходник personality в этой карточке не менялся.

В [gateway/session продолжении](P02_LAB_GATEWAY.md) получены selective ACK,
automatic retry, отказы неправильного пароля/digest и 10 native cycles на
одном живом gateway. Все 22 новых запуска откатились. Personality получила
только отрицательный password control; native callbacks не подменяются.

Команды и откат: [REPRODUCE.md](REPRODUCE.md). Индекс хешей:
[P00_P01](../evidence-index/P00_P01.md).
