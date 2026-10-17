# P05C — смешанный контакт и полные перевороты, 17 октября 2026

Ветка `codex/p05c-mixed-contact-handling` от принятого Core checkpoint
`2dcd5b9`, runtime предшественника `19ba479`. Main не менять до приёмки
зависимой цепочки. Старые сборки, receipts, БД и доказательства сохранять.

## Основание и границы

- OBSERVED владельцем: ИС-7/МС-1 загружаются, едут, наводятся и соприкасаются;
  МС-1 может зависнуть наклонённым у ИС-7. При уже выполняющемся толкании по
  прямой ИС-7 останавливается на переходе к подъёму; снова нужен разгон.
- VERIFIED на старте: BattleTank ограничивал pitch/roll значением PI/3. Полный
  переворот прямо разрешён владельцем; это правило проекта, не заявление
  об исторической физике клиента 0.9.1.
- На старте причина потери тяги была UNKNOWN. Для позднего replay окна
  2961–3044 теперь измерен повторный reversal brake; attribution исходного
  native эпизода ограничена frozenreplay/causal intervention. Другие
  остановки не объявлять тем же дефектом без проверки controls/контактов.
- Сохранить управление P05B и профильные массу/мощность/трение. Оригинальный
  клиент и предыдущий single-vehicle worker не менять. Автовыпрямление,
  урон за переворот и таймер гибели в эту правку не входят.

## Исходная последовательность до contact129

1. Сохранить mixed01 observations, фото-хеш и SQL141/53; остановить только
   собственные клиенты/сервисы по exact receipts до правки source. DONE.
2. Добавить ограниченную необязательную private диагностику настоящего Jolt:
   quaternion/скорости, команда, мотор/тормоз/RPM/передача, ID тел опор,
   импульсы и нормали каждого колеса. Не менять IPC7/native data contract.
3. На закреплённом worker воспроизвести смешанный flat contact и переход
   flat→slope; отдельно проверить переворот. Настоящую геометрию карты не
   подменять авторской под историческим source hash.
4. Разрешить полный поворот только BattleTank; минимально исправлять тягу
   и контакт по фактическому замеру. Проверить полную ориентацию до wire.
5. Выполнить component/IPC7 проверки, применимую P05B матрицу и source-bound
   gateway gate при изменении gateway/source binding. Сохранить FAIL тоже.
6. Подготовить свежий стенд из актуальной БД Core-loss4, revisions141/53,
   grants0, без пересоздания снарядов. Обоим клиентам — повторный mixed native
   тест flat→slope, отпускание контакта, бок/крыша, управление и возврат.

## Продолжение по native contact129

Владелец подтвердил перевороты/столкновения и естественное завершение по
захвату с правильной причиной итогов и обоими загруженными ангарами. Оба окна
после этого закрыл сам. Новая общая приёмка остаётся FAIL: перевёрнутый МС1
теряет взаимный засвет, ИС7 продолжает разгон в powered turn, на пригорке ИС7
откатывается около−1км/ч под W+поворотами. Для конкретного позднего replay
окна причина теперь измерена; остальные объяснения не обобщать без данных.

До новых runtime правок: screenshot и read-only log prefix сохранены;
оба native уже отсутствуют, gateway/bridge остановлены exact129 receipts.
Текущую БД не заменять старой. Новый launcher/full до native повторения.

1. Исправить регрессию интеграции полного переворота с LOS: сейчас clearance
   +0.5m вращается вместе с корпусом. Проверить source-bound roof-rest
   положение обоих профилей на настоящем terrain resolver; сохранить
   скрытие настоящим препятствием и прежнее upright/yaw поведение.
2. Сначала измерить поворот/разгон при одинаковом времени и начальных
   состояниях. Предыдущая P05B matrix не требовала снижения скорости в
   powered turn. Кандидат проверять actualJolt сравнением, без прямого
   изменения body velocity, profile power/mass и без произвольного успеха.
3. Пригорок: извлечь actual controls/stall intervals; провести отдельный
   ограниченный реконструированный replay с drivetrain/contact telemetry.
   Не объявлять отсутствие RPM/manifolds в original log доказательством
   сбоя управления. Если точного воспроизведения нет, оставить UNKNOWN и
   подготовить наблюдаемый следующий тест вместо недоказанного retune.
4. Runtime/source-bound tests, значимые регрессии движения обоих профилей,
   новый canonical full при изменении gateway, свежий stand из актуальных
   SQL144/56 либо более позднего фактического snapshot. Native новых правок
   до ручного прогона NOT_RUN. Main не менять.

Уточнение владельца: ИС не стоит, а откатывается около−1км/ч под W и
поворотами. В полном recorded04 replay найден отдельный8.3с continuousW
rollback с17включениями/выключениями reversal brake; первые peer-support
окна не подменяют этот результат. Новый проверяемый кандидат: reversal
brake вооружается только новой rawthrottle командой, при повторяющемся
удержанном W не перевооружается. Release сохраняет прежний порог−0.5м/с;
предложенный−0.05 не включать без отдельного основания. Сначала causal
late-activation experiment на exact04 выполнен: publicprefix≤2940 byteexact,
все5611controls одинаковы; первая разница2970. В окне2961–3044 motor1/brake0
во всех84samples, вместо17циклов старого brake; source-terrain gain
−1.294→+1.533м без power/friction/geometry retune. Это causal replay proof,
а не native приёмка. Driverlogic и actual moving W↔S выполнены на current06.
Legacy default выключен, shared включён отдельным intent flag. Исторический
full02 bc5c1c6/physics05 завершён1632PASS/0FAIL/5ignored, build/source941exact;
его PASS не распространяется на06. Currentphysics06 build25rawexactPASS.

Production-linked combined proof50061cfa содержит отдельно synthetic driver
logic520assertions/530Apply (0PhysicsSystem.Update), core72actualworldruns,
16flat matched W↔S tracepairs/743first-brakeframes exact/24replays. Отдельный
strict flat→16/21°ramp:24runs/8exercised/0notEx/0unmatched; первое торможение
exact, после выхода повторного arm на heldW нет. Powered128PASS; legacy03
build25exactPASS; обе P05B06 9×2 quality/replayPASS, publicbytes/metrics
exact04==05==06. Source35 до/после совпал. Никакая unit не объявлена traction
доказательством; специальные speedcap toggles и native новых правок NOT_RUN.

Ближайший шаг: finalsourcecommit, canonical full03 (**PREPARED_NOT_RUN** до
фактического запуска), затем bind/seal свежего stand130 на этом full/runtime06
из actual SQL144/56 либо более поздней БД. Native130 NOT_RUN. Один manual
сценарий: mixed AИС7/BМС1, движение/наведение, powered turn, бок/крыша/взаимный
засвет, тот же подъём с удержанным W и новым W после отката, затем итоги/оба
ангара. Не менять main и не выдавать component PASS за приёмку карточки.

## Доказательства и приёмка

Исходные ignored evidence: `local/evidence/20261017-morning-core01/`:
`mixed01-observation.json` SHA256
`11ec3527976f149f1a4a0ea113d462668b4a497a9ef78b628064abfea67823a0`,
`mixed-physics-owner01.png` SHA256
`27cee2fd65035c9892930753789c9d387401895531534a4ea75f8df274fb4146`.
Оба старых клиента и gateway/bridge остановлены собственным retest120 driver;
4 exit0 receipts сохранены там же. Боекомплект AМС1[0,46,46]/ИС7[19,0,0],
BМС1[0,48,44]/ИС7[0,0,0], active reservations0. Склад прежний.

P05C остаётся PARTIAL/FAIL: contact129 подтвердил перевороты/столкновения и
итоги/возврат, но три замечания требуют native130 (NOT_RUN). Current06
автоматические gates PASS; full03 PASS (1632/0/5, build/source-after exact). Combined evidence:
`local/evidence/20261017-p05c-production06-checks01/result.json`, SHA256
`50061cfaf61e63b713b5220740a7898f18d13d051dad17976cbb6e750eecd974`.
Автоматические проверки не заменяют native приёмку. Откат —
остановить новые own процессы, вернуть предыдущий runtime19ba479 и его
согласованные артефакты/launcher; актуальную БД не заменять старым снимком.


Отдельное поручение владельца P07B «оригинальный засвет0.9.1 без маскировки»:
исходные points/rays/viewrange и SixthSensealways для командира исследуются
в другом чате, собственной ветке/worktree. Его pending runtime не является
частью P05C acceptance, здесь не запускался и не объявлен готовым.


## Contact130 native observation

Owner observed a normal full rollover: inverted MS-1 retained mutual visibility with IS-7. This is a native PASS for the rollover LOS regression only. The same live battle later ended with `SHARED_BATTLE_FAILED` reason `shared scene worker deadline` at the server worker deadline; the manual run is therefore interrupted and P05C overall remains open. Failure receipt: `local/evidence/20261017-morning-core01/contact130-worker-deadline-failure.json` SHA256 `59324a31e4dc3e0173cf193bec6e269413d38b4a9f8fd8e725feed6255fde582`. Native powered-turn/hill and full battle-return acceptance remain NOT_RUN/INCOMPLETE.
