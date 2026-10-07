# P02 — поездка через родную кнопку «В бой!»

2026-10-05. **IN_PROGRESS, полный запрос владельца ещё не принят.**
План: `docs/plans/P02_map_drive.md`. Все новые локальные доказательства:
R=`local/evidence/20261005-p02-map-drive/`.
Промежуточные binding/geometry проверки ниже не закрывают полноценную поездку.

## Изменение границы и исходное состояние

Владелец разрешил продолжать до полноценной поездки, входа через родную кнопку,
случайной проверенной карты и повторного возврата/входа. Автоматизация мыши и
клавиатуры по прежнему исключена; source-verified original diagnostic methods
и штатный `BigWorld.screenShot` используются только в явных диагностических runs.
Обычный режим не должен закрывать EXE по таймеру или условию сценария.
Original клиент неизменяем; все установки только research, с предварительными
хешами, резервными копиями и rollback. Сеть только собственный loopback.

`R/baseline-01`: 380 authored files, 17 local files, 2 согласованные SQLite backup.
`R/environment-01/result.json`: normal013 и сервис исходного шага проверены.
Normal013 откатан через `R/rollback_normal013.py`: 31immutable+3ownerlogs сохранены,
история `R/normal013-prerollback-01/`; сайт этой работой не перезапускался.

## Native binding — пройден узкий checkpoint

VERIFIED: `forcedPosition` устанавливает native Avatar.vehicle; исходный метод
`Avatar.updateOwnVehiclePosition` и отложенный callback привязывают собственную
матрицу к filter.bodyMatrix. `controlEntity` для этого пути не добавлялся.
Сетевые координаты клиента остаются недоверенными и не задают серверную позицию.

- Bind01/PID6664/68.338s/195packets — **FAIL**. В `0x4a` ошибочно добавили длину32.
  Native метод имеет fixed32; реальные неверные float побитно совпали с однобайтным
  сдвигом. FAIL/source/binary сохранены, fixed32 исправлен отдельно.
- Bind02/PID87828/153.651s/1867packets — **FAIL наблюдателя**. Корректные native
  callback1445/198 и2951/151 были, однако getter bodyMatrix создаёт каждый раз новый
  Python wrapper на filter+0x598. `is` между обёртками не доказывает связь.
  Исправление опирается на original PE, сохраняет identity как наблюдение и требует
  оригинальные callbacks, attachment, согласованные матрицы и настоящее движение.
- Bind03/PID104052/53.100s/426packets — **PASS binding condition**. Original
  forward171/stop235; own/body matrix delta `[0,0,2]`, stopped hold3.04091s.
 103 пары update198,102 deferred151+2 штатных retry179 независимо проверены.
  EXE exit0, rollbackPASS, оба PNG просмотрены;90/90HP и original карта/МС-1 видны.
  Цветная сетка изображения остаётся UNKNOWN. Surface-driving здесь не принимался:
  исходная лабораторная точка всё ещё была выше земли.

Доказательства: `R/bind03-root-review-01/result.json`
SHA256 `2b2053b446bc5a2e26ad14945984fe6777095648fb04cab12879138d9347f596`;
`R/gui/bind03-native-review-01/result.json`
SHA256 `1f2c499d6e597677dd6dde32c86eb1db9bde00c4beb09b1b9240342dbab96c58`.
Каждый generated replay сохранён отдельно и прежнее отсутствие восстановлено:
`R/bind01-replay/restore.json`, `bind02-replay/restore.json`, `bind03-replay/restore.json`.
Старые Q модули и свидетельства не переписывались.

## Геометрия и физический worker

VERIFIED original resources: Карелия ctf type1; Прохоровка ctf type4.
Число в имени `05_prohorovka` не является её сетевым ID. Стабильные публичные
названия не назначаются этим исследованием.

Исходные heightmaps69×69 с двухпиксельным бордюром →65×65 подписанных миллиметров;
шахматная триангуляция подтверждена PE. Для каждой карты проверены144cells,
17039соседних швов и720storedLOD. Реальные BSP2 модели/деревья преобразованы
в world triangle meshes. Corrected obstacle-mesh-04 исключает только29/1 исходных
Maple faces, ставших точно нулевой площади после float32 transform; первоначальный
FAIL/mesh03 сохранён. Полный evidence index: `R/data/handoff-01/index.json`,
SHA256 `c63177806ddc6dcf5f392642ce1a8a19c943c81ccbb58ce7dd5de9c871721f45`.

В Bind03 получены7 заранее закреплённых original rays:6terrain+1Stone BSP.
Независимый max|deltaY|=0.000028848236m, нормали≤0.00000329673.
`R/data/bind03-ground-review-01/result.json`
SHA256 `703a220eaabacf54e65fb6d25c9c882ada95bc795feda7126b9f87aad03edee6`.
Это проверка выбранных точек Карелии, не всех столкновений на обеих картах.

Новый `tools/map_drive_worker/` — .NET9, закреплённый JoltPhysicsSharp2.22.0,
без сетевого сокета. Private JSONL domain controls, fixed60Hz; gateway должен
заказывать6ticks/10Hz. Worker не получает native method IDs, клиентские координаты
или часы. Local config/meshes/runtime assets закрепляются хешами. Динамика явно
`test_lab`; исторически точные подвеска/двигатель/трение остаются UNKNOWN.

`R/physics/track-probe-01`: synthetic tracked API PASS; первый compile FAIL сохранён.
`R/physics/geometry-smoke-01`: реальные обе карты/меши, синтетический корпус;
forward/turn/brake/reverse/stop,141states/map, минимум4contacts, PASS только offline.
Native export даёт массу МС-1 4691kg, hull/chassis/turret bounding boxes,
carrying(X,Z), original limits8.88896/2.22224m/s и31626.5W. Корпус/подвеска на основе
этих измерений ещё проверяются. `ms1-drive-01/02` сохранили FAIL первоначального
требования≥3contacts на каждом движущемся сэмпле; результаты не скрыты.

Worker parser review нашёл nullable hash bypass и непроверенных предков root.
Оба исправлены: `R/physics/worker-build-02/` и
`R/data/worker-fixed-review-01/`:13managed controls+7actualIPC checks PASS.
Текущий speed limit — порог отключения тяги, не жёсткая отсечка скорости на склоне.

Независимые offline causal пары проверили один реальный камень и восточную
границу каждой карты: с препятствием удерживаемый газ останавливает корпус;
контроль с удалением только выбранных треугольников проходит дальше на
15.62/16.49m, контроль со сдвинутой границей — на39.69/39.91m.
`R/data/offline-collision-review-01/result.json`, SHA256
`f7a36c875c9aad6fe6eb1e764feefebfc1b54813c8f3bb027b50f2c5749c6a6e`:
4пары/10реальных процессов/32negativecontrols PASS. Контрольные meshes остались
только в ignored evidence; ordinary pool использует полные исходные препятствия.
Это проверка server worker, пока не доказательство native collision отображения.

## Серверный MS-1 и обычный режим — интеграция продолжается

`R/physics/ms1-drive-03`: реальные mass/hull bounds МС-1, lab120.804Nm,
обе карты, по141states/840physics ticks. Независимо проверены signed forward
10.5467/11.3788m, turn1.2990/0.6042rad, reverse−5.4076/−4.4086m,
final velocity norms0.000604/0.000838m/s. Во всех840тиках на каждой карте
минимум2опоры, минимум1с каждой стороны; side-miss0. Минимальный sampled
hull-ground clearance+0.06785/+0.03955m. Это offline динамика, не native PASS.
`R/data/ms1-drive03-review/result.json`: independent reader+20negativecontrols.

Worker build03 DLL SHA256
`7654cecec0f8f228cb9d9ccda3bf9a2dc47065392b190d60aa4f3fcbac78a76c`.
`R/publish_worker01.py` сохранил неизменяемую копию16runtime files в
`local/server/map-drive/worker-v1/`; packaged apphost ready/state/EOFexit0 PASS.
Pool `local/server/map-drive/pool.json` SHA256
`8994553cd223678e093c44de9cb5bfa78ccfedb5c2b3ff0fe49e1ed84e8cbc12`.
Пул содержит обе проверяемые карты, а не подмену одной карты двумя названиями.

Root ordinary integration: explicit installer `--enable-map-drive`, service
`--map-drive local/server/map-drive/pool.json`. Исходный режим остаётся default,
ordinary Avatar lifetime не вызывает Account-only observer, original input и
`onChangeEnvironments` делегируются игре. Процессные arena services сохраняются
между поездками; завершаются только при настоящем закрытии EXE. Компиляция и
реальный полный цикл проверяются далее. `R/root-integration-02/`: backup4sources,
7integrationguards+51diagnosticcontrols+40runner+5licensepolicy PASS.

## Ride01 — сохранённый FAIL до создания арены

PID111892,25.4609291s,50wirepackets,EXEexit0,install/replay rollback PASS.
`R/ride01-prepare/native-outcome.json`, SHA256
`705421a43dfcbf86d0e82f4e21c8b3be0a64e4c2fd1dfff2b678ad3bc9613d1d`;
`R/ride01-runtime/native-111892-1791211287701.jsonl`, SHA256
`3d4aaefd8e89767fffc17a85313af4de450fd9c9ede249d8dada16bb1913a239`.
Original FightButton.fightClick действительно вызван; CMD700/worker/Avatar нет.

Две отдельные проблемы, без смешения причин:

- VERIFIED: диагностический observer завершился с Python2 TypeError при вызове
  чужого unbound method. Исправление наследования нового observer проверено
  настоящим Python2.7.3, включая отрицательный случай чужого receiver. Старые
  binding/movement probes не менялись. `R/gui/RIDE01_OBSERVER_FIX.md`.
- VERIFIED: исходный r4 stream содержит stats.battlesTillCaptcha=0; original
  CaptchaController при таком значении ставит ShowCaptchaAspect на enqueueRandom.
  Свежий python.log фиксирует reCAPTCHA.getImageSource после urllib.urlopen/read,
  перед неудачным regex.group. Это **неожиданный внешний HTTP-путь** старого
  клиента, нарушивший намеренную границу own-loopback эксперимента. UDP capture
  не устанавливает HTTP-peer, proxy, redirects или содержимое ответа; они UNKNOWN.
  Повтор до исправления запрещён в рабочем процессе. Отсутствие CMD700 связано
  с CAPTCHA по исследованному control flow (INFERRED), а не доказано TypeError.

Исходные материалы: `R/data/ride01-queue-review/run-01/`,
`R/wire/ride01-review/result.json` и append-only `cause-addendum-01.json`.
Коррекция в работе: версия server service policy только ordinary map-drive
передаёт counter1 в initial full Account state, сохраняя immutable r4 и его hash;
отдельный обратимый client guard запрещает неожиданный legacy CAPTCHA HTTP
до urlopen и сообщает ошибку, не выдаёт поддельный ответ. Перед original кнопкой
observer должен пассивно подтвердить counter1/isCaptchaRequiredFalse.
Новый EXE получает full state до CaptchaController.start; disk cache не удаляется.
`R/wire/captcha-policy-design-01/PROPOSAL.md`. Native повтор пока NOT_RUN.

## Ride02 — service policy PASS, диагностический аргумент FAIL

Ordinary AccountPolicy v1 реализована в `map_drive_service091.rs`; separate
outgoing SHA256 `138c21ed9063b36e30ca5995d6d200045c3db99dc9d54f4dc70fd34b94f58698`,
исходный r4/VehicleSeed SHA неизменён. 238Rust tests PASS, старый test-harness
FAIL сохранён. `R/wire/captcha-policy-integration-01/result.json`; собственный
server build02 SHA256 `74756c8d9dab9fbf3b26353264208982c57bbbc866010356b5fb1051b4e9bb06`.

Ride02/PID4856/393.1796s/1052packets: independent wire подтвердил точный1329B
projected stream, старые shop/dossier и отсутствие CMD700/701. Actual native
counter1, original isCaptchaRequiredFalse, guard blocked0; 6ordinary cleanup,
12hangar cleanup, EXEexit0/install+replay restore PASS. Это **PASS политики**, но
**FAIL поездки**: после родной кнопки клиент остался Account до budget361.

VERIFIED fresh python.log (строго прежние9568B + новый хвост): original
Account.enqueueRandom дошёл до doCmdInt3, который отверг argument5=None вместо
INT32. Диагностика передавала `fightClick(None, '')`; родные PrebattleAction и
JoinRandomQueueCtx сохраняют это значение до RPC без нормализации.
Исправляется только диагностический аргумент случайной карты на `0`.
Клиентские проверки боекомплекта не объявляются причиной: traceback показывает
проход через них до enqueueRandom. Native movement/return/screenshots NOT_RUN.

Доказательства: `R/gui/ride02-native-review-01/result.json`, SHA256
`a777e668b28414164f8b91057556c9a64dd57df868b96cec2d2ff37fdfad8e19`;
`R/wire/ride02-review-final-01/result.json`, SHA256
`67497c01333ab9cc137244a37880a3ec5fb3b083720c6f3f8c4951e23a740235`.
Прежние FAIL/source snapshots сохраняются; ordinary source/server здесь
повторно не меняются. Следующий native run получает свежий prefix Ride03.

## Ride03 — настоящая очередь и Avatar base, FAIL перед пространством

PID18592/206.4294s/744packets, ordinary sources/server прежние; diagnostic
integer-zero исправлен. VERIFIED: actual CMD700 accepted, server OsRng выбрал
01_karelia/type1, packaged workerPID81520 прошёл180settle ticks и вернул
позицию[-63.499344,21.44713,-440.81094],5опор; затем создан actual Avatar base.
Cell/geometry/Vehicle не появились, движения нет. До этого readonly собственный
source-bound route от того же spawn отдельно пройден offline; это не native PASS.

Первый отвергнутый пакет client reliable seq6 содержит original doCmdInt3
request202/CMD502/args(1,0,0): BattleQueue запрашивает состояние очереди после
onEnqueued. Этот ранее не реализованный запрос задержал последующие reliable
пакеты, включая enableEntities. Сервер завершил неготовую арену и вернул Account;
workerEOF exit0/reaped, без Kill. Observer правильно объявил неожиданный teardown
до явного leave ошибкой. Исправляется ordinary CMD502 с учётом фазы: до reset
ответ своей очереди; после поставленного reset — только дренаж запоздавшего
Account request, без отправки метода Account в Avatar. Остальные frame guards
не ослабляются.

`R/gui/ride03-native-review-01/result.json`, SHA256
`5660c2594333c59c16123061e62d23ed5d7067c7cec5ea07bace390b472c45d0`:
175base-only states, original ctor/onBecome/onNon callbacks; нет свежего
Python traceback, есть repeated original ArenaDataProvider empty-roster NOTES.
CAPTCHA1/False/blocked0,6ordinary+12hangar cleanup,EXEexit0/installrestore PASS.
Создался **частичный** replay288B/zeroJSONblocks. Обычный replay validator честно
отказал; bytes сохранены, принадлежность привязана к priorabsence/ownPID/time,
прежнее отсутствие восстановлено отдельным `R/restore_ride03_partial.py`.
`R/ride03-replay/restore.json`, SHA256
`d2c18cf082e6cabcd246740e96e3d0eeda9b6281d501b501d6d655b110a4b502`.

## Ride04/05 — мир и позиции работают, найден порядок углов

CMD502 correction:248Rust tests PASS, build03 SHA256
`ab0475718c4c9d0354de53636d7d0e7ae250f44650e3348f097b457e017ff3c1`.
Ride04/PID35404/30.167s/92packets: actual502→27Bresponse→ACK до reset,
enable/space/Vehicle/ready/forced binding прошли. Семь65B публикаций точно
соответствуют worker; двеACKed,terminal5unacked. FAIL observer: проверка
crew_active через `is True` отвергала original UINT8 int1. Исправлена повторным
использованием прежнего строго типизированного `_native_flag`, а не общим bool().
Сбойный current snapshot теперь сохраняется до re-raise. Доказательства:
`R/wire/ride04-review-01/result.json` (`d60e277a…abb86`),
`R/data/ride04-physical-review-01/result.json` (`c6589bcb…9bf04`).

Ride05/PID80236/82.497s/1609packets:503worker→wire65B публикации побайтно
совпали,497ACKed,terminal6unacked. Семь native Karelia rays опять совпали с
terrain/BSP до0.00002885m. Actual intcrew1 принят, движение началось;
original forward1,turn9,stop0,reverse2 и emergency stop0 действительно вызваны.
**Полная приёмка FAIL:** reverse за30s не дал ожидаемого перемещения относительно
модели. Разбор показал существенную ошибку, которую нельзя обойти инверсией теста:
native heading совпал с третьей компонентой worker direction (roll), а не yaw.
Например worker[-2.4003124,-0.3134818,1.0173631]→native heading1.01736310979.
Маркёр turn0.221rad поэтому не считается доказательством правильного поворота.

VERIFIED original Python: Avatar1445 передаёт direction прямо в
Math.Matrix.setRotateYPR; deferred2951 затем берёт native filter.bodyMatrix.
Разбирается отдельный native формат direction у встроенных Entity сообщений:
нельзя переставлять углы одновременно во всех сообщениях по догадке.
`R/gui/ride05-native-review-02/result.json`, SHA256
`b80b64a1472f5caf28c20e20dae216178d699e0f260254d21c80725b8fbc4caf`,
содержит actual angle-correlation и исходные callbacks. Original entryPNG
`R/ride05-runtime/screenshots/map_drive_entry_001.png` просмотрен root:
МС-1 на карте,90/90HP,HUD/мини-карта видны; цветная сетка поверхности остаётся
OBSERVED/UNKNOWN, визуальная историческая точность не заявляется.
Оба запуска закрылись exit0,install/replayrestore PASS; сохранены6ordinary+
12hangar cleanup и отсутствие свежих traceback. Ordinary lifetime/source1301,
физический worker и исходные client resources этой коррекцией не менялись.

## Codec orientation v2 и Ride06/07

VERIFIED original #717 PE: built-in0x06/createCellPlayer и0x15/entity update
читают wire RPY;0x09/createEntity и original Avatar0x4a используют YPR.
Domain worker остаётся YPR. Изменены только два соответствующих serializer;
253Rust tests PASS. `R/wire/direction-contract-01/result.json`, SHA256
`c764bfe6207da1488bb7c30ce3ddd15761dea07fa14d30178977f118b9e585c7`,
содержит38 exact PE anchors. Build04 SHA256
`59de4e8efb8bc277a96ce01c81cd0435a75b96d9d4cf22ff0c687752dee810f7`.

Ride06/PID12376/37.329s/80packets: random выбрал Prohorovka. FAIL до движения:
observer проверил roster-ready в окне между model-ready и получением native
server-ready122B. Сервер ответ отправил; его ACK и original0x4a ещё отсутствовали.
Исправлен только bounded wait для exactfalse/period1/isOnArenaFalse до первой
готовности; смерть, другая identity и утрата ранее принятой готовности — FAIL.
68Py3/66Py273+2hostSKIP/compile PASS; клиентская версия `bb8fa144…47b63`.
Wire evidence `R/wire/ride06-review-02/result.json` SHA256
`e888257629c068925e976ea717ab87043778d8b584f43227cd38177ff4425021`.

Ride07/PID19964/94.105s/637packets: actual Prohorovka, forward4.327409m,
turn0.399384rad, reverse2.640092m, обе stable hold≥2s наблюдались настоящим
клиентом. Два native PNG entry/driven просмотрены root: MS1/90HP, карта/HUD,
изменение положения/ориентации. Все176 worker65B публикаций получили ACK;
1056 physics ticks имеют опоры слева/справа. Это scoped drive observation,
**полная приёмка FAIL**: original leave создал Account, но следующий native
warm-sync пакет отвергнут; после retry exhaustion клиент отключился.
Возврат PNG отсутствует. Gateway/observer cause исследуется отдельно.
`R/gui/ride07-native-review-01/result.json`, SHA256
`ad361369f1c0f4aa08531ea476b135b10c4cb29a2f4bd8d33f983550086f5114`.
Свежих Python traceback нет; ordinary6+hangar12cleanup и install/replay rollback
PASS. Prohorovka terrain ray высоты/нормали совпадают; normal одного BSP rock
отличается при nonuniform transform, исходный строгий reader FAIL сохранён.
Это отдельно расследуется, пороги и серверная геометрия не меняются.

## Незакрытая приёмка

Уточнение владельца после Ride11: на заднем ходу камера движется рывками.
Статус **OBSERVED user report**, это дефект текущей поездки, приёмка не закрыта.
VERIFIED original0x4a устанавливает static server transform, обнуляет target,
а deferred callback возвращает provider к filter.bodyMatrix. Последовательность
сейчас повторяется10Hz. На Ride11 во времяreverse текущая body/own позиция
отставала от последней raw server pose примерно на0.265–0.268m. Причинная связь
с видимой тряской пока **INFERRED**: нужны временные ряды внутри кадров и сравнение
с серверной физикой. Клиентское сглаживание или изменение порога ради PASS
не применяются. Phase2 candidate остаётся не установленным до этой проверки.

Ride11 также содержит original moveVehicle call517 flags1/isKeyDownTrue вне
диагностического intent. Владелец явно ответил, что клавиши не нажимал:
**HUMAN_INPUT_DENIED**. Внутренний caller UNKNOWN; не приписывать команду
владельцу или переключению фокуса без доказательства. Сценарий остановлен
из-за неатрибутированной команды, не объявлен успешным. Клиент
закрылся exit0, install/replayrestore PASS; snapshot ангара после return NOT_RUN.

Закрытые дополнительные опыты: Ride08 FAIL readiness observer из-за временного
target=None; scoped retry0.1s сохраняет прежний предел разрыва3s. Ride09 прошёл
родной warm enable09,100/300/600 и showGUI, но observer неверно запретил отдельную
геометрию spaces/hangar_v2 после leave. После привязки к original teardown этот
шаг принят в Ride10; следующий exact LOBBY_SUB=None во время загрузки потребовал
обычного ожидания. Во всех случаях исходные FAIL сохранены. Backend warm-sync
исправления проверены273 Rust tests, build07 и его sources сохранены в
`R/server-drive-build-07`. Базовые лимиты capture не менялись; только явный
`map-drive-phase2-v1` допускает48k packets/32MiB для повторных поездок.

Более частое чтение потребуется для проверки камеры. В Ride09 строки1532→1549
показывают за0.109072s движение own provider вперёд0.489508m при движении
body/model/server назад0.216671/0.216693/0.229656m. Разрыв own/body0.706180m
исчезает при переходе targetFalse→True. Числа **OBSERVED**, источник сброса
provider **VERIFIED**, влияние на actual camera всё ещё **INFERRED**: у родной
ArcadeCamera две ветки привязки. Отчёт `R/data/ride11-jitter-review-01/result.json`
SHA256 `5d4ad1e4ffa5182340f1aefdc387ace1b23868785b6c0be4d6de2eae7098ba26`;
контракты getter/веток: `R/gui/ride11-camera-review-01/FINDINGS.md`.

Ride12/PID94444,32.018s,147packets,exit0/restorePASS — **FAIL измерителя до движения**.
Пассивный sampler записал7 actualcamera/body/own отсчётов, затем отверг
BigWorld.callback handle своим неверным неотрицательным signed32 ограничением.
Исходный сырой token не записывался; причина конкретного значения ещё не
доказана по trace. Отдельное чтение PE подтвердило signed32 контракт callback и
cancelCallback, включая отрицательные номера. Исправление измерителя и новый
baselineA обязательны до сравнения с31B кандидатом. Исходный sampler и8+8 tests
caller-only metadata сохранены в `R/gui/sampler-checks-02` и
`R/gui/movement-caller-checks-01`. Replay сохранён с проверкой исходного времени
и восстановленным отсутствием: `R/ride12-replay/restore.json`, SHA256
`941896051bc4c2d28d548a50f895df594582b51bac753118827fe74864f312a8`.

## Закрытое сравнение камеры A13/B15

После исправления signed callback ABI baseline A13 прошёл полный цикл на
Прохоровке:54.400965s/643packets/620samples/3PNG/exit0/restorePASS. Original
negative token−1979711481 и отмена−1124073459 реально наблюдались. Все семь
movement callers объяснены (два штатных stop и пять команд диагностики).
Первый Account/ammo/repository совпал с готовым ангаром после original leave;
новый Account/showGUI и warm sync подтверждены независимо.
`R/gui/ride13a-native-review-01/result.json` SHA256
`1ec237484d485f499cf4fd461a2f7686f2dea3ef63aaebdc6c4989b414566fe0`.

Build08 меняет только periodic publication:31B tickSync+Entity15 вместо65B с
повторным Avatar4a. Начальная122B привязка, worker, geometry, physics, input,
ACK и Account неизменны.277Rust tests PASS. Exact apply/source/build/start:
`R/rebuild_drive_server08.py`, `R/server-drive-build-08`,
`R/wire/entity-only-publication-02/apply-01/result.json`.
EXE SHA256 `8a3d3dcce4de4ca6a02bf59a7ad65913a33e0362a5512f3c68a0262a6841d43d`.
Ride14B выбрал Карелию и прошёл цикл; Ride15B случайно выбрал Прохоровку,
что позволило сравнить одну и ту же карту,25 идентичных клиентских модулей
и неизменную серверную физику. B15:52.740358s/627packets/674samples/3PNG.

**OBSERVED, одна пара на одной карте:** максимальный шаг камеры относительно
корпуса при reverse0.477005→0.003705m; при turn1.134191→0.001334m.
Переключения target300→0; own/body совпали во всех674 B отсчётах. У A камера
за0.02259225s прыгнула−0.992549m при движении корпуса+0.133637m; это actual
camera transform, а не интерпретация PNG. Родные часы, реальные интервалы и
пределы измерений сохранены. **INFERRED:** повторная жёсткая коррекция вызывала
эти скачки; single-change A/B и исходный путь reset/rebind поддерживают вывод.
Гарантия нулевой тряски/исторической физики не заявляется.

Итоговый отчёт `R/data/camera-ab13-15-review-01/result.json`, SHA256
`89031ecfaaf6a242365bfdf6836eba502ef909edc7c07a27b20dba54cee2f38f`,
содержит команды воспроизведения reader, actual measurements и ограничения.
Independent wire B15: `R/wire/ride15b-camera-review-01/result.json`, SHA256
`fb5091d0e1cb280502a3d4d2f98fdd9f636d9f66b47176568e7fdf9e4644a4ba`.
Root просмотрела три PNG A13 и три B15; evidence
`R/root-visual-review-02` и`03`. Карта/танк/90HP и возврат в ангар видны;
цветная сетка в native screenshots отмечена отдельно как UNKNOWN.

Следующий ограниченный опыт — phase2 same-EXE обе случайные карты и реальный
камень Карелии. Sampler после длинного маршрута сохраняет45s/1600-per-ride,
общий предел8rides/12800samples. Управление маршрутом читает current native
filter.speedInfo; initial4a после build08 больше не является текущей скоростью.
Исходный кандидат и проверки: `R/gui/phase2-candidate-03`.

Независимо выполнены только **offline** feasibility маршруты к границе:
`R/root-boundary-route-01` (Карелия reverse, крутой склон, tilt59.28° — для
native опыта непригоден) и`02` (Прохоровка forward, unchanged spawn/worker,
1031states, z максимум498.48334, tilt13.10°, удержание у+Z границы).
Это не native boundary PASS; физические состояния и команды сохранены сырыми.

## Ride16: повторные арены и причинная проверка камня

Закрытый PID43508:232.394752s,4694packets,exit0/installrestore PASS.
Пять последовательных случайных карт1,1,1,1,4, пространства1..5 и различные
arena IDs. Все пять original Fight→movement→leave→warm Account подтверждены,
25 Account/ammo/repository snapshots неизменны. Все1360 публикаций31B совпали
с worker F32/RPY и ACKed; terminal unACKed — только пустой heartbeat.
Wire: `R/wire/ride16-review-03/result.json`, SHA256
`f78060c0a7b13de3259c56fb05fad2d0728275db6f6e47ffe9f6aa5e24e3e236`.
GUI/lifecycle: `R/gui/ride16-native-review-03/result.json`, SHA256
`eab66f39dd560bedd84e2b79d80a821e6d300fe5eb41045646d1a6ff0baa5b55`.
Root реально просмотрела четыре PNG: `R/root-visual-review-04/result.json`,
SHA256 `5519192c5ecefeb4f83c6af2bdf43d71d01255b9682d81da7747c94ece721f7b`.

**PARTIAL_STRICT_STATIONARY_HOLD_NOT_OBSERVED:**2399 плотных native samples
выявили ошибку диагностического `_hold`: отсчёт включал последний замер с
ещё недопустимой скоростью. В9/10 basic интервалов фактический stationary suffix
составил1.4279..1.9527s вместо2s; условия не ослаблялись. Итоговый reader
`R/data/ride16-physics-review-06/result.json`, SHA256
`36b32dd5997b0484ee12535ccf73c9ad438474438c9b2a7fca41f5304b331ae6`.
Все8160 worker60Hz ticks имели опоры обеих сторон; это наблюдение этого прогона.
Все35 native heights совпали с mesh; прежнее расхождение одной Proho BSP normal
остаётся FAIL_OBSERVED. Строгая проверка остановки повторяется в Ride17.

**OBSERVED_CAUSAL_IMPACT_AND_BLOCKING:** точные716 исходных worker inputs первой
поездки воспроизведены на полных данных:10024 float32 значений и4296 масок
побитно совпали. В отдельной локальной копии mesh удалены только696 треугольников
env044_Caucasus_Stones02, chunk[-1,-4]/model[3], рядом с(-77.0334,-389.2913).
Первые467 advances одинаковы; расхождение начинается при ударе468. При одном и
том же непрерывном газе493..522 (2.9s) с камнем перемещение0.000347m,
без него17.137519m. Рабочая geometry/worker/config не изменялись.
Addendum `R/data/ride16-rock-causal-review-01/result.json`, SHA256
`a86ff18616b4e3e8bcb02185b1c95b46d396c6485ad537c8e3b0a55f38c625df`.
Старый предзаданный критерий «все5s скорость<0.1» сохранён NOT_CONFIRMED:
в начале интервала ещё происходило замедление. Sampled SAT overlap2.65cm
не скрыт; нулевая пенетрация/contact manifolds/историческая физика UNKNOWN.

Общий исправленный source `client_patch/map_drive_acceptance.py` SHA256
`3b7efdf6ef0e67a0431811b40a90d1350c100db016796e419a39118b6243fb07`
содержит явные режимы phase2_drive и boundary_only. `_hold` начинает отсчёт
с первого действительно допустимого sample и сбрасывает его при нарушении.
Обычный input/server/physics не менялись. Boundary отдельно выбирает первую
случайную Прохоровку, ограничивает forward110s, удержание у границы5s,
stop3s/reverse5m/stop2s; остальные action bounds сохраняют30s.
Режим не заявляет basic-drive/camera приёмку и требует независимых worker ticks.
Freeze: `R/gui/boundary-promotion-01/freeze.json` и
`R/root-mode-integration-01/freeze.json`.186Python3 PASS;
181actualPython2.7.3 PASS+5 прежних host-only SKIP;102 common regression PASS.
Два старых host fixture не извлекали ранее добавленный observation_byte_limit;
первый FAIL сохранён, затем они подключили настоящий helper с прежними assert.

Новый capture startup с тем же build08: `R/server-drive-restart-09/after.json`,
SHA256 `b1981d7920f5a83f7f3cee1619f5eee93b74e2f74360b8ed09d922243a13b8d2`.
Конфиги/сайт/EXE/pool неизменны; старый Ride16 связан со своим исходным gateway.
Ride17/PID22712 закрыт:134.291143s,1568packets,exit0/installrestore PASS;
**FAIL** второй арены. Первая Прохоровка завершила drive/warm return. Во второй
Карелии строка1951 gateway-span: MAP_DRIVE_FAILED при poll_drive после request247.
Generic «unsupported session input» не определяет конкретный источник отказа
и не является доказательством нового native RPC. Wire исследует guard публикации.
Последующие channel_state/retry_exhausted и native Disconnect — последствия.
Actualcall371 flags0/False идёт от setForcedGuiControlMode→Disconnect→showKick;
к действиям владельца он не относится. GUI FAIL сохранён в
`R/gui/ride17-native-review-01/result.json`.
Replayrestore `R/ride17-replay/restore.json`, SHA256
`fdc3b5e95613c5f2736cf6c80290004e354a7e797a7be7379ae38fb58aaf9b5d`.
Первый leg17 отдельно подтвердил остановки:2.66679/2.85440s непрерывных
низкоскоростных dense samples после original stop,107/119samples. Это уточняет
проверку reader: нельзя обрезать реальный suffix по более позднему редкому
hold marker и объявлять его всю длительность. Порог2s не снижен; весьrunFAIL.

## Исправление расписания и повторный Ride18

Старый predicate due допускал запрос нового worker state в уже опубликованном
native tick1252; это VERIFIED по source и сохранённому regression-before FAIL.
Связь именно этого guard с Ride17 остаётся INFERRED: точный poll timestamp247
не записывался. Новая версия ждёт следующего собственного100ms тика, сохраняет
верхние пределы и выдаёт конкретную причину вместо generic invalid().
Отдельно VERIFIED: recovery складывал reset в outbox, но отправка зависела от
следующего успешного receive. Теперь reset проходит bounded flush сразу;
старые Avatar-команды только в Returning до ACK-bound09 проверяются целиком,
не применяются к миру и ограничены32 envelopes/512B/16methods. Неправильный
хвост/token/ACK/generation/piggyback отвергает весь receive атомарно.

Кандидат/точные команды: `R/wire/publication-recovery-integration-01/`.
284/284Rust tests PASS, семь новых содержательных regression PASS, прежний
FAIL сохранён. Guarded apply/build/start: `R/rebuild_drive_server10.py`,
`R/server-drive-build-10/after.json` SHA256
`a963700617737ef5490ad299981c1979b9237b11470bd23c1807db0fd9bc45f7`.
EXE SHA256 `aac7a53e09b110a2370d6044c47eaa15ed9e8d1d2a29b642daceb169099a9d05`.
Конфиги/сайт/worker/geometry не менялись; периодические31B и начальная122B
привязка сохранены. Native аварийный recovery сам по себе ещё NOT_RUN.

Ride18/PID21924:129.110943s,3028packets,exit0/restorePASS, полный сценарий
**FAIL original movement made insufficient bounded progress** наturn первой
Карелии.51route decisions привели к камню, затемstop3s/backoff5.4539m/stop2s.
Последующийbasicforward3.8194m иturn снова приблизили машину к камню:
heading−0.687573→−0.587029 (Δ0.100545) не достиг порога0.15 за30s. Рабочую коллизию не отключаем,
порог угла не уменьшаем; корректируется только диагностический отъезд передbasic
с5 до12m. Причина конкретного упора отдельно проверяется по worker/geometry.
Replayrestore `R/ride18-replay/restore.json`, SHA256
`99d88812b8d7fa6ce5de6a655807f29d736c9c96e7a76d6d03d5a8d8a9eb50ac`.

NOT_RUN: native boundary, corrected full two-map run, ordinary install без
autologin/autoquit и физический ввод владельца. Полная карточка IN_PROGRESS.
Стрельба, повреждения, экономика и второй игрок не входят в текущую карточку.

Точные одноразовые команды опытов сохранены в `R/*prepare.command.json`,
`R/server-rebuild-01/02/*.command.json`, physics run.py/result.json и GUI checks.
Повторный native опыт требует свежего prefix, replay baseline, mutex absent,
согласованного source freeze и собственного local capture gateway; существующие
каталоги результатов не перезаписываются.

Откат: immutable client ledger каждого native run → installer rollback, ownerlogs
отдельно сохранены, replay exact hash/time guard. Исходники до карточки —
`R/baseline-01`, каждый кандидат — отдельный source snapshot. Gateway EXE до карточки
сохранён как `R/server-rebuild-01/gateway-before.exe`; возвращать только при
остановленном собственном supervisor и после сверки соответствующих исходников.

Работа продолжается: обычный Native gateway + worker + FightButton/leave.

## 2026-10-06, Ride19–20: два возврата и уточнение проверок

Ride19/PID22780, build10 и client clearance05 `00e1a14c…9e8bafd`:
150.310957s, 3204 packets, native exit0, installer/replay restore PASS.
Карелия → Прохоровка одним EXE; 955/955 публикаций побайтно совпали с worker
и подтверждены ACK. Два разных world owner, две исходные цепи lifecycle,
два возврата в готовый ангар, Account/боекомплект/repository сохранены.
После камня фактический отъезд 13.662737m, затем basic forward/turn/reverse.
Wire: `R/wire/ride19-review-01/result.json`, SHA256
`349a10c78aa95376c349681491ddd4461b5928d34bc6dbb9064e5d6500446ad5`.
GUI: `R/gui/ride19-native-review-01/result.json`, SHA256
`b7fa9219da9f24751642159f6bcbff72b8626b702eaa3c85e73d1df0485f097b`.
Root просмотрела четыре настоящих PNG: обе карты, МС-1 90HP и финальный
готовый ангар с двумя танкистами,20AP,100000credits и сохранённым ИС-7.
`R/root-visual-review-05/result.json`, SHA256
`cb78654c0b3bc4424b516f653b60b41d07cc16e443bfdb12e5975a25060292b7`.
Цветная сетка на original screenshots остаётся UNKNOWN; PNG не доказывает
плавность или причинность коллизии.

Общая приёмка Ride19 **PARTIAL**, несмотря на PASS_SCOPED GUI/wire.
После остановки за камнем worker отскочил до0.447058m/s и к следующему
forward успел непрерывно простоять ниже0.1m/s только1.8s. На finalreverse
редкий1Hz sample увидел0.094033m/s; следующие9 dense samples снова дали
0.113…0.167766…0.101318m/s. До premature holdmarker суффикс1.7466s,
до actual leave уже2.75994s. Второе наблюдение не переписывает ранний FAIL.
Минимум независимой приёмки2s сохранён; дополнительная диагностическая
пауза3s пока только кандидат, до нового actualrun не подтверждена.
`R/data/ride19-physics-review-01/result.json`, SHA256
`09e25250497b1daac925d449b8528fae80351ac3c68125304f75d2b12dafaed6`;
raw explanation `R/data/ride19-hold-explanation-01/result.json`, SHA256
`26742ba188d81a968bce19f5ca318bb3a1c5499ebbf64346a72cb3dcb6fd224d`.
Все5730 масок опор имеют минимум2 контакта и обе стороны; airborne0.
1070 dense samples: own/body Δ0, targetdrop0. Reverse camera-relative
maxstep6.14mm на Карелии и3.13mm на Прохоровке — **OBSERVED** этого прогона.
Высоты14 лучей совпали; прежний FAIL_OBSERVED нормали камня Прохоровки сохранён.

Ride20/PID66728, тот же source, режим boundary_only:34.639635s,204packets,
exit0/restorePASS. **FAIL до движения:** `_Pixels.request` разрешал только
имена map_drive_rNN_*, а новый режим запросил map_boundary_rNN_*.
Граница и warm return **NOT_RUN**. Wire сохранил все204 пакета, отсутствие
положительных movement inputs и backend errors; четыре последних публикации
не ACKed, их доставка NOT_RUN. `R/wire/ride20-review-02/result.json`, SHA256
`c7170dc24de297a6212f7f433b7a3aa53c05cd59334cea6eb97fac95585f5b52`.
Replay restore `R/ride20-replay/restore.json`, SHA256
`09a5c15b8fedfc92822d10e174296ac219beb7fff2a6fcd298989aa22241819a`.
Свежий capture запущен тем же build10, без изменения source/config/pool:
`R/server-drive-restart-11/after.json`, SHA256
`4d0bc5166e1266587b6820a85648f56118462a7fade5149121bf7951298e866a`.
Исходные FAIL, client backups и capture предыдущего запуска сохранены.

## 2026-10-06, итог native Ride21/22 и обычный пакет

Цель этой карточки — управляемая локальная поездка через родную кнопку,
случайная проверенная карта, авторитетная физика и возврат с сохранённым
аккаунтом. Она не включает выстрел, урон или бой нескольких игроков.
Новый client revision6 меняет только диагностическое ожидание2→3s и allowlist
имён native PNG. Source `3b85cdf0e2038fbfeae3c3ba17e00dfe95ca14b7e4535247702b172fe1f0b30a`,
actual273 pyc `f46106f482da2a0ce5dd9042e326d2474725b90f31613ef92e3f85d75e8fe5b1`.
Обычная логика управления, backend10, worker и карты прежние.
После переноса:191Python3 PASS;186actualPython2.7.3 PASS+5 прежних host-only SKIP,
compilePASS. Порог независимой приёмки2s сохранён; ожидание3s — запас времени,
а не подмена фактического измерения. Freeze `R/gui/hold-margin-promotion-06/freeze.json`,
SHA256 `458c1aecd71e0a5c4e786471845119cf34c92cffd46dc9259290a73fdd381731`.

| Проверенный объём | Фактический результат |
|---|---|
| Ride21, native EXE | PASS:276.920651s,5946packets,5 арен1→1→1→1→4,5 возвратов,exit0/rollbackPASS |
| Worker→wire→ACK21 | PASS:1760 публикаций31B, точный Float32/RPY, все ACKed; нет duplicate native ticks |
| Остановки21 | PASS:12/12; минимальный dense suffix2.740286s, worker после routebackoff2.8s |
| Контакты21 | PASS в измеренном объёме:10560 масок60Hz, минимум2 опоры, обе стороны, airborne0 |
| Native камера21 | OBSERVED:3129 samples, own/bodyΔ0, targetdrop0; A13/B15 сравнение сохранено отдельно |
| Account21 | PASS:5 возвратов, неизменные ресурсы/машины/экипаж/боекомплект;1repository |
| Ride22, native boundary | PASS:129.088811s,2935packets,1Прохоровка,881 точная публикация, все ACKed,return/exit0/rollbackPASS |
| Powered boundary22 | OBSERVED:5.02584s native stall /5.8s worker под газом, reverse6.4045m |
| Остановки22 | PASS: native3.014/3.011s, worker3.9/4.1s |
| Контакты22 | 5286 масок, airborne0;14ticks без левой опоры, правая сохранялась |
| Обычный normal014 | PASS проверка установленного пакета:25модулей/34immutable+3ownerlogs;manual native NOT_RUN |

В21 worker request219 поколения3 был отозван при выходе до публикации:
REVOKED_UNPUBLISHED, доставка NOT_RUN. Единственный неподтверждённый последний
seq1970 — пустой heartbeat, не позиция. В22 все позиции ACKed.
Оригинальные movement callers21:83 диагностических+10 автоматическихstop0;
22:73+2. Нет неизвестных callers в этих новых прогонах. Это не доказывает
происхождение прежней внеплановой команды Ride11; владелец её не вводил.

Доказательства21:

- `R/data/ride21-physics-review-01/result.json`, SHA256
  `87d5b179b91799b9678f8ff9db14c79909bf93f35a0a1a757502d40892bdcf64`;
  подробные12 остановок — рядом в `SUMMARY.md`.
- `R/wire/ride21-review-01/result.json`, SHA256
  `b580b004d5f4d69ea82fed49dae71c99145d1f19d0b117ce9cd8514a49ce4d4d`.
- `R/gui/ride21-native-review-01/result.json`, SHA256
  `f73f1865c848cc76062bdc1a5beb09e5f4a78afd682f4405c478786980d8b903`.
- `R/root-visual-review-06/result.json`, SHA256
  `c2112eeb278027e2d5b5f79887ec64786e032b4962a215675a59c43e6f034bee`:
  root фактически просмотрела4 из15PNG — обе карты и конечный ангар.
- `R/ride21-replay/restore.json`, SHA256
  `0bf029a18b732d23c857cc25c9d5cb0117c29b55b1469f3f7e7eea499bea16cf`.

Доказательства22:

- `R/data/ride22-physics-review-01/result.json`, SHA256
  `28bd1d279317bbfcd0f734a7a17a358346097269d7cde52b67c9fd3a3598848a`.
- `R/wire/ride22-review-01/result.json`, SHA256
  `f109e1a9f0f1e4a1908fec2ff7d6fa6162cea09309c45c4b2a772aef4f701445`.
- `R/gui/ride22-native-review-01/result.json`, SHA256
  `9e38548d2bc5fa3306cce5b70ef170bc7d029107122b1a5054325fa8dba17e2c`.
- `R/root-visual-review-07/result.json`, SHA256
  `68d5bc4a79c0b02ab1a71bce10b25075e7282866aea3030bddb264ac9114e915`:
  root просмотрела все3PNG, включая красную границу и возвращённый ангар.
- `R/ride22-replay/restore.json`, SHA256
  `4316070e66e263668da1bd5507e17d60c4b3ea15bfad0ac42c3f31e4ff25d3f3`.

Отдельный разбор стены22 — `R/data/ride22-wall-review-01/result.json`, SHA256
`95157d10c5a6e22918f1f6f3c35044e5086c773fbb041ae6672544c7993bbf89`.
**VERIFIED source:** Program.cs создаёт реальные static Jolt boxes с внутренними
плоскостями±500; присваивания координат через clamp нет, выход за допустимые
границы вызывает ошибку. **OBSERVED:** при input[1,0,false] worker664→665
скорость6.701949→0.164424m/s за0.1s; затем704..762 удерживают стену5.8s.
Hull-plane gap в установившемся интервале−75..−26µm; все3904 исходные obstacle
bounds отделены от140 поз проверяемого участка минимум15.81797m;1120 углов
корпуса выше terrain минимум0.20724m. **INFERRED:** блокирует именно заданная
стена. Удаление стены и повтор22 **NOT_RUN**, contact manifolds не записаны.
Преходящий sampled overlap8.58547cm и14ticks без левой опоры сохранены; нулевая
пенетрация и идеальная подвеска не заявляются. Ограничение rough test_lab hull
существенно для будущей доводки физики.

Normal014 установлен с теми же25 source/pyc, что21/22. Точные11 настроек:
test_control=None, captures=False, enable_map_drive=True, loopback20014,
profile002, trace `R/normal014-runtime`. Автологин и автозакрытиеFalse;
обычный клиент после установки не запускался. Package review
`R/gui/normal014-package-review-01/result.json`, SHA256
`82f950421a134aacac4290f0ee69c910c01fa4bcd386560302120de3779a6d72`.
Сервер без capture перезапущен с тем же build10/pool/config:
`R/server-ordinary-12/after.json`, SHA256
`f2c51e35061118332ba42cbd89feb6c8db799fceca62a4a0dab102421e4d0e69`.
Сайт не перезапускался. Итоговая сверка original/research/БД и cumulative
native acceptance выполняется отдельно; её окончательный результат указан
вверху `docs/STATUS.md`, не выводится из успешности одного GUI-reader.

### Повторение и ручная приёмка

Обычный backend, из `D:\WoT_9.1_Server`:

```powershell
python -B -X utf8 tools/local_server.py start --config local/server/service.json --map-drive local/server/map-drive/pool.json
```

Затем вручную открой `WoT_0.9.1_RU_0717_research/WorldOfTanks.exe`. Учётка
прежняя; локальная запись тестовых данных:
`local/evidence/20261004-p02-unified-account/operator-email-binding-01/test-credentials.json`
(case operator_shared). Не публиковать этот файл или его содержимое.

Один следующий проверяемый шаг: ручная поездка МС-1 — «В бой!», W/S/A/D,
задний ход с поворотом камеры, остановка, упор/отъезд от камня, штатный выход
в ангар и повторный вход. Карта случайна среди двух; повтор той же карты
допустим. ИС-7 остаётся ангарным тестом. Закрытие EXE только вручную;
сессия и часовая тестовая фаза арены имеют собственные границы.

Повторный анализ уже закрытой трассы, без запуска игры и с новым output:

```powershell
python -B -X utf8 local/evidence/20261005-p02-map-drive/data/drive_modes_reader.py --backend-revision 10 --startup-revision 11 --client-revision 6 --mode phase2_drive --install local/evidence/20261005-p02-map-drive/ride21-prepare --trace local/evidence/20261005-p02-map-drive/ride21-runtime/native-111400-1791233457758.jsonl --out local/evidence/20261005-p02-map-drive/data/ride21-repeat-01
python -B -X utf8 local/evidence/20261005-p02-map-drive/data/drive_modes_reader.py --backend-revision 10 --startup-revision 11 --client-revision 6 --mode boundary_only --install local/evidence/20261005-p02-map-drive/ride22-prepare --trace local/evidence/20261005-p02-map-drive/ride22-runtime/native-10736-1791233893861.jsonl --out local/evidence/20261005-p02-map-drive/data/ride22-repeat-01
```

Это реальные команды reader; каталоги `*-repeat-01` пока не создавались.
Их повторный запуск — NOT_RUN; выполненные исходные команды сохранены рядом
с reports. Для нового native experience нужен свежий prefix, отдельный capture,
откат ordinary-пакета и replay-before ledger; не перезаписывать Ride21/22.

Откат текущей установки при закрытой игре:

```powershell
python -B -X utf8 tools/local_server.py stop --config local/server/service.json
python -B -X utf8 tools/interactive_client.py rollback --out local/client-install-014
```

Это останавливает собственный backend и возвращает клиент к сохранённому
состоянию до normal014. Внешний процесс сайта и БД не удаляются. Исходники до
карточки сохранены в `R/baseline-01/project-before.zip`; возвращать только
перечисленные в итоговом source delta файлы после сравнения актуальных хешей,
не распаковывать архив поверх всего проекта. Все diagnostic installs и replay
уже откатились, original не изменялся; итоговый full manifest проверяется отдельно.

Не подтверждены: физическая клавиатура/normal014 manual flow, историческая
динамика, cross-platform repeatability, replay playback, звук, contact manifolds,
причина цветной сетки на native screenshots. Native fault-injected аварийный
recovery build10 отдельно NOT_RUN; его bounded state machine покрыта Rust tests.
Исходные неудачи сохранены. Полный бой/P02 не объявляется готовым.

### Итоговая приёмка сохранности,02:24 UTC+5

**PASS_AUTHORIZED_LOCAL_DRIVE_SCOPE**:
`R/final-audit-02/final-state-audit.json`, SHA256
`c07de7886178861d5c254eb0df1e0711446f01ec018b45547c8fb3482bc973c7`.
Root прочитала фактический JSON и перепроверила этот SHA. Исполненная команда
со всеми аргументами, временем, интерпретатором и exit0:
`R/final-audit-02/command.json`, SHA256
`006641e68146dbb7a4120e53b342e849e99dcab1c8eaf402b5fa4898689ae26c`.
Это завершает ровно разрешённую локальную карточку поездки, не весь P02.

Аудит выполнялся21:20:08–21:24:09UTC. Проверены60 controls,25 диагностических
запусков/32619 сохранённых пакетов,25 replay restores и27 исторических
restore records. Original3469/research3499: неожиданных отличий0. Normal014
имеет25 модулей/34immutable files+3 сохранённых owner logs. Полный authored
inventory404:17 изменённых и24 новых пути; сайт и посторонние проекты не
менялись. Сохранены4 конфигурации, обе БД по semantic rows, профили4/1 и fixtures.
Own ordinary runtime: gateway39372,identity82056,supervisor88676; captureFalse,
native0/worker0/mutex absent на момент аудита. PID — наблюдение этого запуска.

Сводная native приёмка11 ролей: `R/wire/native-adapter-final-03/result.json`,
SHA256 `01a20cae15b4f3b2e5ca08686d99d3c7dcc7641a696b6016a4bf44a93fd046ef`.
Отдельный review этого adapter:
`R/data/native-adapter-review-02/result.json`, SHA256
`d42e7c76d5287d2f2f34cf5c81a50f01b29dbc053dad57529f4411e4b2ab9cd1`.
FAIL итогового reader01 сохранён: единственный старый Bind03 startup использует
схему без captured_utc. Исправление привязало именно его сохранённые after,
start.command и stdout по SHA и проверило порядок времени; общего ослабления
для остальных запусков нет. Исходные FAIL/PARTIAL сценариев не переписаны.

Основные изменённые группы файлов:

- Native server: `tools/wg_probe/src/map_drive091.rs`, `map_drive_service091.rs`,
  `map_drive_worker091.rs`, `map_drive_world091.rs`; изменения `gateway091.rs`,
  `arena_control091.rs`, `hangar091.rs`, `capture091.rs`, `main.rs`.
- Физика/геометрия: `tools/map_drive_worker/` и `tools/map_geometry.py`.
- Клиентская совместимость: `client_patch/map_drive_client.py`,
  `map_drive_scenario.py`, `map_drive_acceptance.py`, `sr_interactive.py`.
- Подготовка/запуск: `tools/interactive_client.py`, `local_server.py`,
  `manual_client_run.py`, `diagnostic_client_run.py`.
- Применимые tests, README, STATUS, MISSING_INPUTS, план и этот отчёт.

Полный список с before/after hashes — раздел `sources_and_configs` итогового
аудита и `R/final-source-inventory-01.json`. После аудита обновлены только
итоговые формулировки README/STATUS/MISSING_INPUTS/этого отчёта; inventory02 и
отдельный docs-only receipt связывают эту редакцию с аудитом без повторной
перепроверки32тысяч неизменённых пакетов. Git-exclusion проверен отдельно:
`R/final-git-exclusion-01.json` — local config/private key/capture/обе копии
клиента исключены, запрещённых tracked paths нет. Git commit не создавался.

Результаты применимых проверок:284 Rust PASS на build10;191 Python3 и186
actualPython2.7.3 PASS+5 прежних host-only SKIP;102 control/runner regression
PASS; native21/22, отдельные GUI/wire/physics readers и итоговый аудит PASS.
Повторный запуск read-only команд из раздела выше пока NOT_RUN; native manual
утром также NOT_RUN. Риски/ограничения/откат остаются указанными выше.
Единственный следующий шаг — ручной круг МС-1 владельцем на normal014.
