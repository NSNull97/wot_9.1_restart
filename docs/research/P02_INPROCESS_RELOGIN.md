# P02 — выход и повторный вход внутри одного EXE

Статус native и установки: **PASS**, 2026-10-05. Цель — проверить жизнь уже реализованного
Account/Hangar при original logoff → LoginView → повторном входе тем же аккаунтом.
Арена, бой и развитие экономики вне этой карточки. Один PID, прежний profile002,
собственные локальные endpoints. Управление мышью/клавиатурой не используется.

`R` ниже — `local/evidence/20261005-p02-inprocess-relogin/`.
До изменений сохранены288 исходников,14 локальных файлов и две consistent БД:
`R/baseline-01/`. Прежние generators/fixtures/данные аккаунтов заморожены.

## R01 — подтверждённый отказ второго входа

**VERIFIED:** настоящий EXE, SHA256
`86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed`,
PID21880. Первый ангар готов в течение16.0960992s/17 наблюдений. Получены реальные
ресурсы, МС-1 и ИС-7, два танкиста МС-1; native PNG
`R/relogin01-runtime/screenshots/relogin_first_001.png`, SHA256
`86e1baf62b0ff10d29e08f623377fb1e9ebe60831f970393e6ecd4c5d8f9d8fc`.
Root просмотрела этот PNG: МС-1, обе фамилии/100% и110%,100000 кредитов видимы.
Есть цветная зернистость; её причина UNKNOWN, изображение не исправлялось.

**VERIFIED:** original AppEntry.logoff вызван на34.89867s. Возврат его decorator
и завершение generator предшествуют фактическому disconnect. Поэтому они сами
по себе не доказывают завершённый выход. Измерены отдельно:

- Original ConnectionManager.disconnect завершился на35.028s.
- Original Account._delAccountRepository RETURN71 —35.18208s.
- Настоящий watcher stage6/NOT_SET и native_connected=false —35.1821457s.
- Disconnected/LoginView, repository=None и player=None —35.902s.
- Второй original LoginView.onLogin —35.90433s.
- Настоящий stage1/LOGIN_REJECTED_SERVER_NOT_READY —36.0496723s.

Сервер закрыл session9 (`client_disconnect`), затем отверг новый login:
`AUTH_REJECT code=73 allocated=0 reason=retired_or_rate`. Второй session ID
не выделен. Второй ангар, его BaseApp endpoint и screenshot **NOT_RUN**.

**VERIFIED по ciphertext, расшифрованному только в памяти:** cipher key одинаков,
encrypted nonce, RSA ciphertext и plaintext различаются. Login endpoints:
127.0.0.1:63735 →127.0.0.1:58293; request IDs27093→27990. Hardware tag одинаков.
Credentials обоих запросов соответствуют собственному тестовому аккаунту.
Значения ключей, паролей, nonce и их private hashes в отчёт не выводятся.
Источники: `R/wire/relogin01-live-key-analysis-01/analysis.json`
(SHA256 `df3dfdcb50608e24469e04cb9ffc0bb9859d2c9950e7043c8bb027e3a1e70ac9`)
и `private-field-equality.json` рядом. Это первоначальный live-prefix анализ;
окончательный capture проверен полным negative verifier отдельно.

Итог **FAIL** сохранён до правки gateway:
`R/wire/verify-relogin01-negative-01/inprocess-relogin-verification.json`, SHA256
`8b3dea4c27a28b51861672b5cb54601e8a32ee19af76a0b1ee85deb39d808dfe`.
95packets/5182B, один init/fini и12 cleanup, native exit0, restore PASS.
Сценарий v1 исчерпал600 наблюдений;625.467s фактической работы. Его error и
observer error сохранены; новых ошибок python.log нет. Kill/таймера EXE не было.
Прежние verifier/tests/gateway находятся в
`R/wire/verifier-before-gateway-fix-01/`. Этот отказ не переименовывается в PASS.

## Узкие изменения после R01

Gateway получает журнал закрытых попыток с ключом, nonce и
фактическими login/base endpoints. Свежий nonce при том же ключе допускается
только после новой авторизации сайта и при других endpoints. Старые endpoints
при том же ключе отвергаются до обработки handshake/ACK/transport Window.
Повтор старого nonce отвергается независимо от переписанного outer request ID.
Журнал ограничен32 записями и120s; при заполнении новый вход запрещается,
защитные записи не вытесняются. Условия проверяются до и после auth worker.
Noninteractive lab сохраняет прежний консервативный запрет старого ключа.

Это ограниченная локальная политика, не новая криптографическая гарантия.
Nonce выбирает клиент. Active attacker с подменой UDP source address этой
проверкой не решается. Same key/same endpoint до истечения TTL остаётся
недоступен. Реальный второй BaseApp peer должен быть измерен новым запуском.

Сценарий v2 пассивно наблюдает настоящий результат второго login через уже
существующий subscriber после original watcher. При отказе следующий advance
завершает диагностику ошибкой через штатный quit. Callback не бросает исключений,
не меняет native status, не делает retry и не принимает server_message.
Normal без явного test control не импортирует и не запускает сценарий.

Сценарий SHA256 `ecb3e4b0472d7f7af2c2525fef1efb7a713d9f29a0b225b2850415b883e6d120`.
56PASS+1 version skip на каждом из Python3/CPython2.7.3 (112 реально выполнено).
Root integration6 checks и общий interactive regression24 checks PASS.
Evidence: `R/gui/fail-fast-checks-02/report.json`,
`R/interactive-control-tests-03.log`, `R/interactive-regression-02.log`.
Свежая компиляция12 модулей: `R/relogin02-prepare/compiled/`.

Gateway source SHA256
`2edd6e6c0c36fb2544bc66fd6d7252b6a4e0d59b1e24cba7f1fb2c2800738ade`.
83/83 Rust checks PASS, в том числе21 новых. Один тест показывает, что старый
tokenless ACK без guard действительно изменяет новое окно, а с guard его peer
отвергается до любых изменений. Evidence `R/data/gateway-tests-01/result.json`,
SHA256 `90b74ea78bce52fc3c99e18bc8a0da1c0290c2d332f8bad9a2df5dd615b278f2`.
Независимый source review без blocking findings:
`R/gui/gateway-review-01/findings.json`, SHA256
`c04ce93bfc660fbf5b320a78203c582cc39091d38ca623102ac9b4d657921dbc`.

Первый shell build **FAIL**: PowerShell не загрузил rust_env из-за execution
policy, cargo отсутствовал в PATH. Ложный shell exit0 пойман неизменным SHA EXE;
он не принят как сборка. Сохранено `R/server-rebuild-01/shell-build-failure.json`.
Повтор прямым pinned cargo с локальной средой **PASS**, offline/locked.
Новый EXE SHA256 `8aea2e503c3b20e13b5eb9a9be7d66d2912a5027d8404a268bf65dfc778c41e1`.
Штатно перезапущен только собственный server/bridge; сайт не перезапускался,
четыре config hashes прежние. Evidence `R/server-rebuild-01/after.json`.

## R02 — фактический сценарий после исправления

**VERIFIED финальным verifier:** PID90800, один EXE/init/fini.
Две сессии backend1→2, настоящий второй LOGGED_ON;188 packets. Два интервала
готовности16.0792207s и16.0693758s, по17 наблюдений; snapshots экипажа одинаковы,
UUID/native ID/resources/statistics сохранены. Оба PNG просмотрены root:
`relogin_first_001.png` и `relogin_second_002.png` (счётчик native screenshot
общий внутри EXE). Учётка, МС-1, две фамилии/уровня экипажа и ресурсы видимы.
Доказательство просмотра: `R/relogin02-prepare/visual-review-relogin.json`.
Native exit0,12 cleanup, capture/restore PASS,63.9074586s работы.

Первый полный verifier report сохранён FAIL:
`R/wire/verify-relogin02-previsual-01/inprocess-relogin-verification.json`, SHA256
`0d00b34451158eb078f5e64f58016c46fc170f7241e9498234aa03f35843fa2b`.
Причина проверяется как дефект самого verifier: ресурсный инвариант прежнего
односессионного checker захватил переход уже disconnected/LoginView, когда
клиент обнулил UI, но transient items_cache_synced ещё true. Граница инварианта
должна определяться настоящими login/logoff callbacks, а не значениями ресурсов.
Исходные capture, trace и этот FAIL не меняются. Граница исправлена в новом
verifier; отрицательные контроли изменения баланса connected Account и ID
второго Account отклоняются.

Финальный строгий результат **PASS**:
`R/wire/verify-relogin02-03/inprocess-relogin-verification.json`, SHA256
`9f42acfd7928d824ad4e52a22c9c0470784a76252e1aff8a82577a047c40b071`.
Root повторила проверку отдельно: `R/root-verification-01/`, report SHA256
`b01524502a5b7e546f29c8fb0b6ffb1b47d08726c6f8b157ef95872b18681369`.
Разные output paths производных capture дают разные SHA отчётов; оба PASS,
исходные188 пакетов те же. Разделение93+95 полное, без пропусков и пересечений.
В каждом входе отдельный AUTH_PENDING, новый Session/Account и три payload
побайтово соответствуют fixture. Session1 закрыта до allocation2, обе финальные
очереди пусты. Свежих Python/trace ошибок0.

Фактические login и base endpoints в двух фазах совпадают между собой:
127.0.0.1:51316 →127.0.0.1:65359. Cipher key одинаков, nonce различается.
Ненулевые cache hints в обеих фазах: Account CRC−1406441505,
Shop518B/CRC−846328027, Dossier version1/time1791128141.
Primary profile SHA256 `5167ea63f0503952b4ab1e7c4b1ed2dca5e5da6b6812bd476a87124a891e0888`.

Verifier SHA256 `f55ee426a425c49b8fd6949c055a1f943233792c60a8ba5d70c41ed0e8377374`,
83/83 tests PASS. Обязательная build-chain связывает source2edd→direct build→
EXE8aea→PID23912/run234409-c866fd→actual native outcome/capture. Версия сценария
связана с установленным compiled source; подмена v2 наv1 и перестановка
LOGGED_ON после Account constructors отклоняются. Промежуточный PASSa5a…,
до этих усилений, сохранён как промежуточный, не итоговая приёмка.

Независимый final review **PASS_REVIEW**,0 открытых блокеров:
`R/gui/relogin-verifier-review-01/findings.json`, SHA256
`32994d57c04a6bd74682dd1f654f0056260ecb86ac3d7391cf206a71e9ef92a7`.
Повторены обе ранее найденные подмены;8 подмен build-chain отклоняются.
188 packets/9524B и оба PNG независимо сверены с неизменёнными источниками.

## Дальнейшая приёмка и откат

Новый настоящий запуск с двумя wire sessions, двумя готовыми ангарами,
двумя просмотренными native PNG и проверкой неизменности профилей выполнен.
Unit doubles и собственные round-trips не использованы как замена этому запуску.
Ручная проверка пользователем ночью **NOT_RUN**. Полный P02 **PARTIAL**.

Normal005 проверен по23 hashes и откатан передR01, evidence
`R/normal005-prerollback.json` и `local/client-install-005/restore.json`.
Каждый диагностический запуск применяет свой patch-ledger и штатный rollback.
Оригинальный клиент не изменён. **Ordinary normal006 установлен**,12 точных
compiled modules из R02,21 immutable files и3 исходных лога. Нет control,
autologin, autoquit, capture. Отдельный ручной запуск ordinary006 **NOT_RUN**.
Полный manifest original3469/research3486 и ledger audit **PASS**, неожиданных
отличий0;11 диагностических откатов согласованы. Оба профиля и fixtures прежние,
четыре config hashes прежние; из29 backend files изменён только gateway.
Report `R/final-audit-01/final-state-audit.json`, SHA256
`0ff1f08a1c7d56a3ac1c1e378aa4848d74511ead31bad52745df6916ffc6ff35`.
17 отрицательных контролей аудитора PASS. Клиент закрыт, сервер и сайт работают.
Old gateway EXE сохранён до rebuild в `R/server-rebuild-01/gateway-before.exe`,
SHA256 `4e22d2fd5f47070c7597462a056a6c4d59bcd5f73c452817f2357bf21e874a66`.
Возврат EXE разрешён только после штатной остановки собственного сервера,
проверки текущих/backup SHA и отсутствия клиента; базы не откатываются поверх
живых данных.

Изменены gateway091.rs, новый сценарий hangar_relogin_scenario.py и его tests,
интеграция sr_interactive.py/interactive_client.py/diagnostic_client_run.py,
контрольные tests, новый verify_inprocess_relogin.py и его tests, документация
и ignored evidence/helpers. Original ресурсы не включаются в Git.

Повторная проверка без запуска клиента, свежий --out:

```powershell
python -B -X utf8 tools/verify_inprocess_relogin.py --install local/evidence/20261005-p02-inprocess-relogin/relogin02-prepare --fixture local/server/fixtures/c5326cc1-8524-479c-8bba-72e973489c22/r3-catalog3 --native-export local/evidence/20261005-p02-ms1-crew/native-ms1-crew-export01.json --backend-build local/evidence/20261005-p02-inprocess-relogin/server-rebuild-01 --out local/evidence/20261005-p02-inprocess-relogin/verify-repeat-01
python -B -X utf8 -m unittest discover -s tests -p test_inprocess_relogin_verifier.py -v
python -B -X utf8 -m unittest discover -s tests -p test_hangar_relogin_scenario.py -v
python -B -X utf8 tools/local_server.py status --config local/server/service.json
```

Новый native повтор требует свободного mutex и сначала guarded rollback ordinary
пакета по его ledger; не накладывать diagnostic поверхnormal006. Затем свежие
`prepare_run.py --name relogin03` и `tools/diagnostic_client_run.py --install
local/evidence/20261005-p02-inprocess-relogin/relogin03-prepare --service
local/server/service.json`. Это новый эксперимент, его результат не предрешён.

Откат обычного клиента после его закрытия:
`python -B -X utf8 tools/interactive_client.py rollback --out local/client-install-006`.
Откат gateway отдельно: штатно остановить свой сервис, проверить текущий8aea
и backup4e22, вернуть только сохранённый EXE и соответствующий source682d,
затем запустить свой сервис. Не возвращать старые БД поверх живых аккаунтов.

Единственный следующий проверяемый шаг: отдельная карточка primary → secondary
→ primary в одном EXE, чтобы проверить изоляцию различающихся гаражей и кэшей.
Пока NOT_RUN; разрешена действующим ночным поручением в границах Account/Hangar.
