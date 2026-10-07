# KNOWN_UNKNOWNS — current gate and historical checkpoints

**2026-10-07:** P03 **IN_PROGRESS**. Текущий источник статуса —
[ACTIVE_GATE](../ACTIVE_GATE.md), доказательства — [индекс P03](../evidence-index/P03.md).

| Категория | Актуальное состояние |
|---|---|
| VERIFIED | P03D: native ammo rows 2570:20 / 2826:0 / 3082:0 подтверждены wire receipt; P03E: 5 accepted shots, AP 20 → 15, 5 reload completion callbacks |
| OBSERVED | Владелец увидел три слота БК и сообщил, что все пять выстрелов прошли нормально |
| UNKNOWN / NOT_RUN | Общий мир двух клиентов, projectile/hit/damage, visibility, полный battle lifecycle; оборудование с непустым профилем |
| Ограничения | Движение остаётся test_lab, историческая физическая точность не принята; deployed gateway не обновлён изолированным P03E EXE |

Ранние неизвестности ниже — архив состояния на 2026-10-04. Они сохраняются
для provenance и не объявляют P03 вновь NOT_STARTED. Единственный следующий
шаг текущей организационной карточки — повторить заблокированный сетью push
с проверкой remote SHA; [ORG-0B](../plans/ORG-0B_TEST_TRIAGE_BACKLOG.md) остаётся
отдельной не начатой карточкой.

## Исторический checkpoint: единый email-вход, 2026-10-04

Runs: `20261002-p00-p01`, `20261002-p01-bootstrap`, `20261002-p02-login-redirect`, `20261004-p02-baseapp-reply`, `20261004-p02-channel-ack`, `20261004-p02-server-reliable`, `20261004-p02-session-gateway`, `20261004-p02-account`, `20261004-p02-account-ready`, `20261004-p02-hangar`, `20261004-p02-unified-account`.
UNKNOWN не означает невозможность проекта.

Текущий узкий PASS: единый email/password источник сайта, primary native
ангар/данные, два аккаунта и restart/relogin. Полный P02 PARTIAL, P03 не начат.
`E` ниже = `local/evidence/20261004-p02-unified-account/`.
Final installation/audit PASS; полного UI PASS нет. Observer исправлен
(9+5tests PASS), но Email22 overall FAIL из-за originalToolTip после fini_enter.

| Вопрос | Текущее состояние и evidence | Следующий различающий эксперимент |
|---|---|---|
| R01: exact build/provenance | VERIFIED локальные v.0.9.1 #717/RU; UNKNOWN издательская аутентичность. CLIENT_AUDIT, полный manifest | Сверка с независимо проверенным эталоном, если он будет предоставлен |
| R02: Python runtime | VERIFIED активная VM: 2.7.3, MSC v.1700, 32-bit; native-05/runtime.jsonl | Закрыто для закреплённого EXE |
| R03: mod loading / обычный запуск | VERIFIED compiled compatibility personality + original GUI/preferences; Normal21 test_control=null,95salive/76.435sready/0own-UDP PASS, без autologin/autoquit; source-only FAIL исторический | Полностью убрать compatibility bootstrap не требуется этим срезом; final installed hashes/audit PASS; clean native exit idle harness NOT_RUN |
| R04: definitions | VERIFIED 44 names/23 aliases; Account Implements развёрнуты, 3 client properties коррелируют с native объектом | Остальные property/RPC IDs требуют своих captures |
| R05–R07: login/framing/IDs | VERIFIED bounded gateway, createBasePlayer ID5/VAR2/type0, doCmdInt3 0x8e, responseExt0x4d, stream52/53; maximum email/password в двух native fragments, primary18server134/client40 | Общие bundles/fragments/wraparound, другие entity IDs UNKNOWN; static candidates не считать доказательством |
| R08/R20: Account → Avatar/arena | VERIFIED original lifecycle/showGUI/сводка профиля и primary email-вход; state3/shop1/dossier1 fragments. Арена NOT_RUN | Только после отдельного разрешения исследовать Avatar/arena; двухклиентскому тесту нужен независимый клиент/ПК |
| Account data / persistence / web→game auth | VERIFIED primary17/18/19: одна users DB, stable UUID/nativeID, русский ник, server test_lab данные; real restart и /api/game isolation PASS | Узкая auth/persistence граница закрыта; изменение прогресса/инвентаря и бои NOT_RUN |
| Свободные UI-действия / tooltip producer | OBSERVED Normal20 manual auth/data PASS, но full GUI FAIL:7originalToolTip len(None) и1primitive observer error; `E/wire-agent/manual-auth20/manual-auth-analysis-02.json` | Локализовать producer пустого tooltipId; Email22 повторил ошибку при fini, source observer исправлен/unit PASS, но повтор ProfileAwards NOT_RUN |
| Email/Unicode/product completeness | VERIFIED email-only, отдельный NFC русский/Latin ник3..24, Ё/ё uniqueness, точный пароль; длинный ник визуально обрезается original header | Email ownership/delivery/recovery, смена ника, другие Unicode алфавиты не реализованы; это ограничения, не отсутствующие credentials |
| R09–R10: движение и correction | moveVehicle/shoot найдены; wire payload/таймеры/предсказание UNKNOWN | Две контролируемые команды реального Avatar, сравнение своего и удалённого объекта |
| R11: historical modules | VERIFIED 128 mm clip=6, 150 mm clip=4, premium HESH chain=275/275 | Позже проверить UI и серверный цикл конкретных модулей |
| R12: armor | Прочитан collision hull; 15 armor mappings, surveyingDevice/BSP2/трансформации UNKNOWN | Одно пересечение выбранного треугольника с эталонным runtime hit-test |
| R13–R14: карты/разрушения | Прочитан chunk и cdata; полная height compression, collision instance transforms/destruction UNKNOWN | Декодировать heights и сверить одну точку/стену по runtime trace |
| R15: sound/FX | VERIFIED original UI SoundManager → VibroManager/no-device normal return в3native runs; слышимое качество/physical vibration/боевые FX NOT_RUN | Один подтверждённый server battle event → обработчик → звук/FX в отдельной боевой карточке |
| R16–R17: исторические формулы | UNKNOWN; новые механики или произвольные RNG не добавлялись | Отдельная спецификация из данных 0.9.1 и проверяемых материалов эпохи |
| R18: Jolt | PASS простой Win-x64 headless; tracked controller и межплатформенная повторяемость NOT_RUN | После решения gateway проверить отдельную гусеничную сцену на закреплённой платформе |
| R19: toolkit | PASS build/XML; FAIL 32-byte vertices и stock login; собственный legacy091 profile + toolkit reply writer PASS | Продолжать только по corpus конкретного билда; geometry correction отдельно |
| R21: replay | Один исторический файл присутствует в manifest; содержимое/пригодность не анализировались | Ограниченное чтение metadata и определение того, что replay действительно наблюдает |
| R22: auth/parser security | VERIFIED один настоящий website verifier, loopback bearer bridge, bounded parsers, wrong-password67/noallocation, nickname frontend refusal; production deployment отсутствует | Перед публичным endpoint отдельный threat model/нагрузка/hardening; local PASS не доказывает internet readiness |

## Объяснённый bootstrap и новая граница

Занятый `wot_client_mutex` воспроизводит прежний ранний exit 0. Вторая игровая
копия — правдоподобная причина прошлых запусков, но их mutex state не записан.
Без mutex source-only модуль дал ImportError; compiled .pyc прошёл init.
Гипотезы отсутствующих DirectX DLL/неработоспособного EXE не подтвердились.
См. [измерения и controls](P01_BOOTSTRAP_AND_NATIVE_LOGIN.md).

LoginSuccess и первый BaseApp request теперь подтверждены:
[измерения P02](P02_LOGIN_REDIRECT.md). Ответ BaseApp/первый encrypted frame
также подтверждены: [карточка](P02_BASEAPP_REPLY.md). [ACK первого packet](P02_CHANNEL_ACK.md)
проверен controls ACK=0/1; разрыв без keepalive раньше quit измерен. Первый
[server reliable/ACK](P02_SERVER_RELIABLE.md) тоже проверен, включая отсутствие
application token в transport-only feedback. [Локальный gateway](P02_LAB_GATEWAY.md)
подтвердил bounded retry и transport/session lifecycle. [Native Account](P02_NATIVE_ACCOUNT.md)
подтвердил создание/поля, но выявил bootstrap FAIL. [Следующая карточка](P02_ACCOUNT_READY.md)
устранила его в диагностическом профиле и подтвердила original lifecycle/initial
sync. Отрицательный RPC route0x4c показал, что native ACK сам по себе не доказывает
вызов правильного обработчика. [Штатный ангар/сводка](P02_HANGAR.md) теперь
подтверждены4/4 cases и6PNG. Затем [единая учётка](P02_UNIFIED_ACCOUNT.md)
подтвердила primary17/18/19, обычные original LoginView/preferences и общий
профиль после restart. UNKNOWN: общий канал, producer пустого tooltipId
и последующие обязательные Account/Avatar/Arena events. У двух клиентов
на одном Windows session может возникнуть тот же instance guard. Обход
mutex/EXE не выполнялся; два ПК — отдельный будущий сетевой стенд.

Не хватает входных данных: [MISSING_INPUTS](../../MISSING_INPUTS.md).
Архитектура «Ориона» UNKNOWN и не является обязательным входом.
Единственный следующий рекомендуемый шаг — локализовать producer пустого
tooltipId на конкретной кнопке/действии. Normal20 владелец подтвердил как
ручной вход; это не превращает восемь сохранённых UI/observer ошибок в PASS.
Normal21 отдельно подтверждает нетронутую форму, но его forced stop не
доказывает clean native exit. Primary state/restart evidence лежит в
`E/primary-state-before-restart-01/`, `primary-external-restart-01/`,
`primary-state-after-restart-01/`, `primary-state-after-native-01/`.
Финальная установка и `E/final-state-audit-02.json` PASS: original unchanged,
21/21restore checks, research baseline+final ledger без неожиданных изменений.
Ангар, собственная сводка и единая авторизация PASS в узком срезе;
полный Account/P02 PARTIAL, P03 не начат. Арена требует отдельной карточки;
остальные строки — исследовательский backlog, не разрешение выполнять всё подряд.
