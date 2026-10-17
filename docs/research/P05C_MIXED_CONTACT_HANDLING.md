# P05C — контакт разных машин и свободный переворот

Ветка `codex/p05c-mixed-contact-handling`, основание Core checkpoint
`2dcd5b9` / runtime `19ba479`. Main не изменён. Приёмка P05C открыта.

## Жалоба и решение владельца

OBSERVED в общем native бою AИС7/BМС1: машины едут и наводятся, возврат
обоих работает; МС1 можно подвесить у корпуса ИС7. Уточнение владельца:
ИС7 уже движется и толкает МС1 по ровному, но останавливается на переходе
к подъёму, затем требуется новый разгон. Полный боковой/крышевой переворот
прямо разрешён владельцем. Урон за переворот и автовыпрямление не добавлены.
Это правило проекта, не историческое утверждение о физике оригинала.

Исходный mixed бой `4131859507633949383`, exact manifest SHA256
`87e61d7c481918a10a221f254a929ce3cda746ba313d358b87747f6d640fda22`.
Фото и наблюдение сохранены в `local/evidence/20261017-morning-core01/`;
их SHA и исходное состояние БК — в плане карточки.
Own клиенты B/A, gateway и bridge штатно остановлены exact receipts до правки.
Последние данные SQL141/53, active0; AМС1[0,46,46]/ИС7[19,0,0],
BМС1[0,48,44]/ИС7[0,0,0]. Склад сохранён, grants0.

## Изменения

- `BattleTank`: ограничение конуса PI/3 заменено на PI, допускающее полный
  поворот. Single-vehicle `Program.cs` сохраняет прежнее PI/3.
- `BodyOrientation`: yaw/pitch берутся из forward, roll восстанавливается
  из полного right после обратного yaw/pitch. В полюсе выбирается эквивалентный
  базис с roll0. Это устраняет усиление float-ошибки около pitch±90°.
- `BattleScene`: для нескольких тел четыре collision steps вместо одного,
  как уже у stock/extended; одиночные классические MS1/ИС7 остаются на одном.
  Профили, масса, двигатель, сцепление и steering policy не меняются.
- Необязательный `--diagnostics NEW_OWNED_FILE` пишет отдельную ограниченную
  private JSONL: мотор/тормоз/RPM/передача, скорости/quaternion, шесть опор
  с ID тел, импульсами/нормалями и первые реальные hull manifolds по парам.
  Это не поле IPC7 и не данные противнику. Без флага диагностика не снимается.
  Максимум12000строк/32MiB/64KiB на строку; hull64пар с явным omitted counter.
- Legacy csproj получил ссылки на два новых класса; логика legacy управления
  остаётся прежней. Добавлены самостоятельные проверки ориентации, переворота,
  непрерывного толкания на склон и воспроизведения записанных команд.

PI действительно отключает ограничивающий конус по первичной
[документации Jolt](https://jrouwe.github.io/JoltPhysics/class_vehicle_constraint.html);
закреплённый managed2.22.0 передаёт его в native
[без преобразования](https://raw.githubusercontent.com/amerkoleci/JoltPhysicsSharp/77a5be2dd30d587c1981dfcaf15851f18041b39c/src/JoltPhysicsSharp/Vehicle/VehicleConstraintSettings.cs).
Ниже отдельно приведён фактический тест закреплённой native DLL.

## Реальные проверки до canonical full

1. Math:47870случаев/95740проверок PASS, допуск4e-6, максимум ошибки базиса
   2.980232238769531e-7. Есть точные/близкие±90°,±180°, fullroll, q/-q.
   Исходный FAIL18970случаев/ошибка.07489715 сохранён; допуск не ослаблялся.
   Evidence `local/build/physics-orientation01` и `physics-orientation02`.
   Первый02 launch с неверным DLL-путём тоже сохранён; PASS — `validation02b.json`.
2. ActualJolt rollover:2880шагов/480actualStatechecks,4/4 PASS. MS1/ИС7
   с PI проходят90° на22тике и устойчиво лежат крышей на полу; контроляPI/3
   не переворачиваются. Начальный наклон/единственный импульс — только
   явно авторский диагностический сценарий, не server gameplay API.
   Evidence `local/build/physics-rollover01` и повтор `physics-rollover02`
   на final04 source; оба PASS, source до сборки/после запуска совпали.
   Ещё4/4PASS в ignored `physics-rollover-step4-01`: единственная проверенная
   замена Update1→4 в копии harness, production source прежний. Это direct
   BattleTank4step gate, не одновременный крышевой IPC7/native тест нескольких
   машин. Сырая метка stdout1 сохранена; actual4 и diff — в validation/variant proof.
3. P05B полная матрица обоих: по9сценариев×2повтора, quality и replay PASS,
   включая повороты/разгон/торможение. Private engine telemetry проверена.
   Evidence `local/evidence/20261017-p05c-mixed-physics01/{ms1,is7}-matrix04/`.
4. Flat IPC7: old/02/03 PASS400бatches. MaxSAT overlap:
   old/02 .0030795м, four-step03 .00032136м. Старый MS1 упирается в60.057°;
   PI02 достигает104.269°, four-step03 в этом сценарии держится на1.333°.
   Это поведение конкретных прогонов, не гарантия native контакта.
5. Exact2263контроля настоящего mixed боя восстановлены из gateway log и
   запущены в отдельном worker. Это реконструкция IPC по domain inputs,
   не сырой retained IPC и не побитовый native replay. Old и02 дают
   maxSAT .1363475м;03/04 — .01999718м. Scene prepare/sync ACK выполнены.
   03/04 stdout совпали побайтно, SHA256
   `70b83e34555b4721c01df3b5f6ab3615f72626891727d9f342d154fed38d003f`:
   добавленная manifold диагностика физику не изменила. Все own workers
   завершились EOF/exit0, без принудительного kill.
   Ограничение: old replay vs original snapshots совпадает лишь ранним префиксом;
   сseq393 есть расхождение, max1.33527м. Причина/сопоставление UNKNOWN,
   поэтому точное повторение original native траектории не заявлено.
6. Авторский непрерывный flat→6°/12° ramp: production4 mixed cases PASS,
   168тиков толкания на ровном при скорости>0.5м/с, вход на склон около10м/с,
   затем20м вверх с обеими машинами и сохраняющимся контактом, stall0тиков.
   Solo1/4 тоже PASS. Два mixed step1 контроля FAIL по потере контакта/обгону
   МС1, а не остановке; они сохранены как2FAIL контроля, не «8/8PASS».
   Дополнительные oldcone60 контроли дали тот же результат, отделяя влияние
   collision steps от cone. Evidence `local/build/physics-slope03/probe/`.
   Первые compile/leaf-guard отказы harness сохранены в slope01/02.
7. Canonical physics04 и legacy01 build PASS, Windows x64, exact локальные
   Jolt2.22.0/native1.1.0. Physics04 source25 совпали до/после, включая
   embeddedJSON; manifest полного runtime SHA256
   `fd8176dd6cf5dba45330b03394e482e704aca41fc96f500a37a23c950b57e239`.
   Evidence `local/evidence/20261017-p05c-mixed-physics04` и `...-mixed-legacy01`.
8. Python parser/measurement guard4tests PASS. Авторские parser vectors
   не доказывают Jolt/native compatibility.

## Canonical full и живой Core contact129

Runtime `611901977572eb7fe321057a5b72af6c185d1297`: canonical gateway full
**1628PASS/0FAIL/5прежних ignored**, test runtime1272.02с, buildPASS.
Все938raw source файлов совпали до/после; новый physics04 явно выбран через
`WOT_P05C_ARTIFACTS`, actual2/6 World/scalar/ACK/parked-body test PASS.
Full evidence `local/evidence/20261017-p05c-mixed-full01/`, source-after SHA256
`d306f99bf4d98940ee61bab09277d1dac608255f6c3fb9eb13e0694c0a6972ea`.
Build `local/build/server/gateway-p05c-mixed-full01/`, exe SHA256
`edb3245023bd6bd5996ece22d4c145e64ef2124e28c400e2a6c33b034af85972`.

Свежий stand `local/stands/morning-p05c-contact-20261017-01/core-loss4`,
tag `p05c-contact129`, run `p05c-contact129-01`. Actual capture-origin,
SQLite backup всех строк, fresh fixtures, bind/check/check-clients/seal PASS.
Исходная копия141/53, grants0. После native запуска наблюдаются142/54,
active0, loaded/depot прежние: AМС1[0,46,46]/ИС7[19,0,0],
BМС1[0,48,44]/ИС7[0,0,0]. Не объявлять исходные141/53 текущей ревизией.

V8 обоих повторно проверен по новому full/source и installed bytes;
переустановки клиента не было. Actual privateauth/own native launch и по два
последовательных настоящих Hangar samples каждого PASS. A PID117132,
B101916; own gateway119744/bridge106712. Startup25.939с, faults0 на snapshot.
На этом startup срезе combat/склон/roll/возвраты были PENDING/NOT_RUN;
последующий результат contact129 зафиксирован ниже и не ретегает этот срез.

После команды владельца/UI начался настоящий общий mixed бой
`8303176210728121358`: slot0ИС7/slot1МС1 с прежними exactconfig pins,
one_scene=true, workerPID119500 из actual physics04, READY обоих. Captured
native snapshots124укаждого, passive observer mutationsfalse, faults0 на
snapshot. Это OBSERVED загрузка, не подтверждение качества управления/склона.
Evidence `local/evidence/20261017-morning-core01/contact129-battle01-load.json`,
SHA256 `8bdad67439b757c00dc70b9e9f344b824f9c25e5f629970fbefba9d20a08edf5`.

Замороженный helper `C:/Users/NSNull/AppData/Local/Temp/wot091-night-workspace-kcadgetk/morning-p05c-contact129`.
Freeze SHA256 `6827cfc1a6b613fb0b99362bdfffe4f0b7c1d855b94c0b99333ddcce3666fb68`;
31guard tests и4passive CLI PASS. Actual binding SHA256
`a081743922e22db0c3ecfc4567ec1d3a2e57b50b2d7138c83d8e9643ec9dd4a0`.
CONTEXT129 SHA `dc6adea958115c252d72610b1b6c9492b03eb730dec6233db5be3bade93fcfc7`;
operators SHA `b63770ff6ad51034a4648c374fb7605a39e9a6875a7213c054488d085e1ee259`;
native-commands SHA `eddccfebe621fcfb28100a5191d1a01b9f3e815f850240a09bfe0fea5ce6f830`.
Точные фактически выполненные argv/exit/время —
`local/evidence/20261017-morning-core01/p05c129_*.command.json`.
Live handoff129 SHA `19739b8fefc3722caca155384c5e0e20c31ee261c6c5eac18d41731d975a31f3`;
трассы закреплены как read-only byte prefixes, а не неизменные live файлы.

## Граница вывода

VERIFIED: прежний угол60°, свободный actualJolt переворот, улучшенная
сходимость контакта и прохождение непрерывного толкания на авторских склонах.
Это не доказывает устранение любой остановки на настоящей карте.
Старые replay low-speed интервалы нельзя автоматически считать багом тяги:
actual04 длинный385sample интервал — упор в MAP_BOUNDARY385/385callbacks.
Ранний161sample интервал — боковой hull contact; MS1 корпус касается static
obstacles161/161samples при0groundsupports, IS7 —38/161samples. Ground grade
ИС7 там около−1°, downhill. Это упор толкаемой машины в fixed geometry,
не воспроизведённая потеря тяги на открытом подъёме. Старый52sample эпизод
имеет другую траекторию/место; равный номер команды не означает то же место.
Низкая скорость сама по себе не устанавливает первопричину жалобы.
В этих ранних интервалах ни reverse-brake cycle, ни взаимное «прилипание»
wheel rays не подтверждены. Позднее окно2961–3044 исследовано отдельно ниже.

Native/UI/камера/управление перевёрнутым корпусом, повтор exact места у склона,
новый mixed таран/возврат и шесть живых клиентов — NOT_RUN. Не объявлять карточку
принятой или слитой на основании этих component тестов. Скрытый shooterFX и
задержки Account transitions — прежние отдельные открытые замечания.

Private `--diagnostics` предназначен для коротких component captures. При
исчерпании32MiB/12000строк он явно завершает worker ошибкой, не теряет записи
молча. Это не бесконечный пассивный observer для полного native боя; production
gateway этот флаг не включает. Оценка review по реальным2actor записям —
около476сек до32MiB, не замер полного длительного запуска. Для будущего
постоянного observer потребуется отдельное явное завершение capture по квоте.

## Команды и откат

Сборка: `python -B -X utf8 server/build.py physics --out local/build/server/<fresh>`;
legacy — та же команда с `--legacy`. Публикация complete runtime manifest
делается только из фактически собранных файлов с отдельным source proof.
Все текущие outputs на C; D и старые артефакты не изменяются.

Проверки: `python -B -X utf8 -m unittest discover -s tests -p test_p05c_mixed_contact_probe.py -v`;
точные dotnet argv/source hashes — в validation/command receipts соответствующих
новых outputs. `tools/p05c_mixed_contact_probe.py` по умолчанию PLAN_ONLY;
запуск требует exact artifact/log SHA, свежий owned output и `--execute`.
P05B — `tools/tracked_handling_matrix.py` с pinnedconfig/worker, repeats2,
diagnostics; точные параметры/сценарии сохранены в `plan.json` каждой матрицы.

Откат: остановить новые own процессы их receipts, вернуть согласованный
предыдущий runtime19ba479/physics/launcher. Актуальную БД не заменять старым
снимком, не возвращать потраченные снаряды. Старый ретест120 заморожен и уже
содержит историю до141/53; новый стенд обязан сохранить эти данные.

Исторические full01 с `WOT_P05C_ARTIFACTS` и Core successor129 выполнены.
Тогда следующим шагом было ручное подтверждение на загруженном mixed бою;
его результат сохранён ниже. Эти старые инструкции не являются запуском130.
В первом — ИС7, во втором — МС1, после отсчёта проверить управление/наведение;
ИС7 толкает неподвижный МС1 по ровному на тот же подъём без отпускания газа,
затем отъезжает назад. Отдельно — полный переворот/камера и возврат обоих.
Не считать code/component PASS native приёмкой. Main не изменён.

Сохранённая команда остановки129 (уже STOPPED): взять exact argv `stop.b`, затем `stop.a` из
`native-commands129.json`, затем `stop_gateway`/`stop_bridge` из
`operators-core129.json`. Только own identity-bound receipts; текущую БД
сохранить. Не запускать старые120 packets на129 и не возвращать старый БК.

Будущий [RULESET-01](../plans/RULESET01_SCOPE.md) записывает новые требования
владельца: общие правила/конфиги, тимдамаг, командный/общий чат и обсуждение
дальности. Это требования; gameplay/defaults и полёт снаряда здесь не менялись.

## Native contact129: новый результат владельца

OBSERVED владельцем: перевороты и столкновения в этом прогоне работают;
естественный захват завершил бой с правильной причиной в итогах обоих.
Оба ангара загрузились, после этого владелец закрыл окна сам. VERIFIED в
gateway: arena8303176210728121358, winner1/Capture/base2points100,
ended_ms568824; оба ResultFrozen shots0/damage0, оба durable Finished144/56,
два native confirmed return, два HangarReturned, reset на следующую арену.
Два client_disconnect зарегистрированы уже после reset при закрытии окон;
FAILED/BATTLE_FAILED/CONTAINED_RETURN_FAILED0. Это не новый вылет.

Общая приёмка FAIL по трём замечаниям владельца:

- перевёрнутый МС1 и ИС7 взаимно пропадают из засвета;
- ИС7 продолжает разгоняться под газом в повороте;
- ИС7 на пригорке откатывается около−1км/ч под удержанным W+поворотами
  (последующее уточнение владельца).

Идеи о точке под землёй и сбое управления пока OWNER_HYPOTHESIS. Code audit
VERIFIED: +0.5m LOS clearance вращается с fullYPR корпуса; при roofroll она
направлена вниз. Native original log не содержит chassisYPR/LOS-hit, поэтому
точную причинную цепочку конкретного эпизода пока считать INFERRED.
Прежняя P05B matrix проверяла progress/yaw/slip/source speed cap, а не потерю
разгона в powered turn: её PASS этот новый критерий не подтверждал.
На этом исходном срезе причина пригорка была UNKNOWN. Поздний frozen04
replay/causal intervention ниже измеряет repeated reversal brake конкретного
окна; это не подтверждение всех сил/остановок исходного native боя.

Private evidence в `local/evidence/20261017-morning-core01/`:
`contact129-owner-feedback02.gateway-prefix.log` — exact prefix6470525bytes,
SHA256 `441b10d3f91a9f4d5b39ccd52c0d915b2d131313b6e699b891467e4e39bfbb53`;
`contact129-owner-feedback02.png` — owner screenshot,
SHA256 `a1166d7f503934354c7ca22b440985ab5282e9b58331fc361176a3dd59d23cae`;
`contact129-owner-feedback02.json`, затем `contact129-completion01.json`
SHA256 `7d360b1664e9e65662532feb3adb23ad9879dad2b47817db9dcdfbd393c93a60`.
Последний фиксирует отдельный ответ владельца про оба ангара/свои закрытия,
readonly SQL144/56/active0 и exact129 stop receipts: клиенты уже отсутствуют,
gateway/bridge штатно остановлены. Новых grants/выстрелов в этом бою нет.
Source/main/прежние evidence не ретегать; текущую БД сохранять.

## Исторический parent после contact129: bc5c1c6/physics05

Runtime `bc5c1c626b453406c8149f7fb6d1937953c1ab20`, source941. Изменены
`shared/model.rs` и `visibility_world_tests.rs`: один sightpoint helper
вращает stockpivot, затем добавляет0.5м по мировому+Y; обычный засвет и
detached-turret observer используют его. Дальность/team/occluders/AoI прежние.
Четыре новые actualWorld регрессии выполнены в завершённом full02;
full03 для следующего physics06 ещё PREPARED_NOT_RUN.
Source-derived plane diagnostic: oldroofpoint MS1−.364096/IS7−.519438м,
new+.635904/+.480562м; quaternion/8OBBcorners grid211806случаев PASS на
авторских flat/6/12/30/60°planes. Это не World/Jolt/native PASS.
Evidence `local/evidence/20261017-p05c-rollover-los-fix01/`, final verification
SHA256 `41107b222ab23fcf962c44a8356439ab8134b100a6f98acc9299a0a1c63d09c3`.

`TrackedHandling`/`BattleTank` добавляют явную shared test_lab policy:
powered steering тормозит внутреннюю гусеницу, inner2м/с² на полумассу,
speedblend0до4м/с→1при8м/с, с yawFraction и sourceMaxBrakeTorque cap.
Ни body pose/velocity, ни profile/mass/enginepower не переписываются.
Политика включена обычным shared constructor; legacy TrackedHandling
defaultfalse. При отпущенном повороте extra brake снимается сразу.
Пороговые числа — инженерное правило проекта, не исторические параметры.

Новый `tools/p05c_powered_turn_checks` compile-links настоящую production
BattleTank, сравнивает disabled/enabled в свежих Jolt worlds с одинаковым
стартом. Actual128runs PASS:48пар,3361initial low-speed frame exact,
16straight traces exact,12coast/brake/reversal gates,4replays и4ordinary
constructor defaults exact. Low-speed правило не меняет тягу до4м/с.
ИС7: одинаковый старт12.8446м/с, flat4steps, изменение за1с
+0.3176→−0.0995м/с; скорость4с14.0310→12.3634м/с. МС1:
8.8358м/с, +0.0120→−0.1885м/с,4с8.8342→8.0020м/с.
12°launch: ИС7v4 5.1645→5.1488, МС1v4 3.920518exact.
Evidence `local/evidence/20261017-powered-turn-production01/`, resultSHA
`5a0330b1e58b1c7b183f460315949bfa685858210164f4fd0cc441298be0e267`.
Специальные колебания непосредственно на speedcap NOT_RUN; измеренный
motor!=0 gate не изменён. Native handling/UI NOT_RUN.

Canonical physics05 build PASS,25rawsources before/after exact,16binfiles;
artifactmanifest SHA256
`c73870ba2a67d33b9e01787a3a0028a43b26add563a86f2673a29ad73b6f77f5`.
Evidence `local/evidence/20261017-p05c-mixed-physics05`;
build `local/build/server/physics-p05c-mixed05`.
Canonical gateway full02/source941 на exactbc5c1c6 с явным05 завершён:
**1632PASS/0FAIL/5прежних ignored, buildPASS, source941 raw exact**.
Evidence `local/evidence/20261017-p05c-mixed-full02/source-after.json`, SHA256
`06a944ad9dbe170ac18ba27cb7ebb3ddbeb9055d6a37efa44084e2212224d16b`;
build `local/build/server/gateway-p05c-mixed-full02/`, exe SHA256
`c49232028d57aefc142c30c773a6b509ef56cb38452151d06766c02edcf09575`.
Это исторический parent physics05, не fullPASS для нового06. Старые outputs
не изменяются. Current06 и следующий full03 описаны ниже.

Уточнение владельца: «даже не то что вставал, а откатывался -1 км/ч назад»;
до этого W удерживался с попытками поворотов, откат до остановки помогал.
Сохранено в `contact129-owner-feedback04.json`, SHA256
`a19ac28e7e33e35fe3b272deb15f1d821e12f4fa946d5aa88018d71977486f45`.
IntegerHUD не устанавливает точную underlying speed/rounding. Нельзя
продолжать называть жалобу неподвижным стопом или фильтровать только
abs(speed)<.15м/с: номинальные−1км/ч вне такого фильтра.

Отдельный immutable physics04 prefix2200 replay сохранил actualorigins
within10мкм соседнего frame. В двух найденных low-speed powered окнах
IS7wheel1 опирался наMS1, wheels3/5 — наterrain, motorpositive/brake0/gear1;
передний bodybox вышеterrain минимум49мм. Но их signedspeed в основном
положительный, они НЕдоказывают причину owner−1км/ч. Прямой deliveredground
torque UNKNOWN. Source04 audit freeze
`da007af86dc54f6ed41f6718ea3ebef32b3637666568795d03cecb0bfddca260`
лежит в scratch `morning-contact129-stall-audit01`; отдельное signed
supplement сохранено; поздний signed audit и causal experiment завершены
с отдельным frozenprefix ниже.
Эксперимент static-only wheel ray меняет траекторию и остаётся scratch;
production filter/контакты/мощность не менялись. Новая turnpolicy выключена
при таких малых скоростях и исправлением отката не объявляется.


## Поздний replay2961–3044: измеренная причина отката

VERIFIED для сохранённого physics04 replay:84samples/8.3с содержат
непрерывный W (left22/straight41/right21), без запроса brake. Old helper
включает общий reversal brake по одному знаку скорости, поэтому даёт
17on/off cycles/34braked samples, сбрасывает motor ramp и оставляет RPM500.
Signed speed−.539..−.072м/с, положительных samples нет; grade16–21°.
Tank hull contact есть лишь в первых6samples, а не во всём интервале.
Этот случай отделён от ранних peer-support окон и упоров в mapboundary/static.

Causal scratch02 меняет только право перевооружения brake в позднем окне:
после validated rawthrottle edge можно arm при projectedSpeed<−.5м/с,
release остаётся прежним projectedSpeed>=−.5м/с. Ноль, explicit brake и
смена intent снимают старый latch. Удержанный W после выхода не arm повторно
только потому, что гравитация изменила знак скорости. Коэффициенты мощности,
трения, тормоза, геометрия/слои/solver и motor ramp4/s прежние; body setters
не применяются. Вариант release−.05 только подготовлен, NOT_BUILT/NOT_RUN,
в production не включён. Static-only wheel-ray эксперимент не промотирован.

Все5611controls совпали с frozen04 baseline. Publicprefix доseq2940
побайтно совпал:5749949bytes, SHA256
`2f5fd005ef81a4e5f8e9573c32063a6bc862f6f03e8ec5cf078ff99d7e7c0f30`.
Первая public разница2970. В том же окне2961–3044 candidate motor1/brake0
во всех84samples, RPM500→3505, gear1/2/3,55positive samples/first2990.
Source-terrain height gain под origin−1.294→+1.533м, progress вдоль исходного
forward−3.560→+7.220м. Старый brake/ramp цикл препятствовал восстановлению
подъёма в этом replay; смена только request policy устранила цикл.

Causal evidence `local/evidence/20261017-p05c-contact129-stall01/replay-late-intent-oldthreshold-01/`;
точные controls/trajectory/driver comparisons запечатаны в helper
`morning-contact129-intent-latch04/freeze04.json`, SHA256
`0e573c2847462a2e542d3dc6b0ffb8e37e27aeb8addf91c4112f84b304403a7a`.
Полный replay завершён5611commands/6.66с/EOF exit0; исходные отказы/первые
эксперименты сохранены. Later trajectory меняется: другие упоры не выдаются
за те же места/причины. Deliveredgroundtorque остаётся UNKNOWN.

Граница причинности: VERIFIED — механизм old helper и сравнение retained
replay/causal intervention. Связь с жалобой владельца подтверждена recorded
controls и найденным late rollback, но original native log не содержал этой
полной drivetrain telemetry. Новый native130/тот же склон ещё NOT_RUN;
историческая точность или устранение всех остановок не заявлены.

## Текущий physics06 и production-linked gates

Current06 явно включает intent flag для shared BattleTank; legacy helper
optionaldefaultfalse. Powered policy остаётся отдельным flag. Трёх-/четырёх-
аргументные shared constructors делегируют полному internal constructor;
component сравнивает intentfalse/true на том же genuine BattleTank, powered
true в обоих плечах. `Program.cs`, профили, enginepower и source limits прежние.

Canonical physics06 build PASS,25rawsources exact; artifactmanifest SHA256
`cff138e72f0172ea98751884027f880e2ad5592665087b1f8cc6b77710b6aa4d`.
Build `local/build/server/physics-p05c-mixed06/`, proof
`local/evidence/20261017-p05c-mixed-physics06/`.

Единый production-linked результат:
`local/evidence/20261017-p05c-production06-checks01/result.json`, SHA256
`50061cfaf61e63b713b5220740a7898f18d13d051dad17976cbb6e750eecd974`.
Rawbefore/after охватывают physics25 + reversaltool7 + poweredtool3,
35uniquefiles, включая9изменённых production/tool файлов. Source-after SHA256
`bb4d8da9c42f8a1e115ff5c1d07577397ceced809b50666a6ea1a03f4a18a27e`.

- Driverlogic:520assertions/530Apply PASS на настоящих native controller
  readbacks с synthetic signed-speed metrics;0PhysicsSystem.Update. Это
  input/state-machine unit, не движение/сцепление. Покрыты rawintent repeats,
  steering/cruise,−.50001/−.5, clear/signswitch, governor cuts, invalid inputs.
- Отдельный actualJolt core:72worldruns PASS,16flat matched W↔S tracepairs
  полностью exact,743first-brakeframes/24replays exact. Оба профиля,1/4steps,
  short/long prefixes; первый reversal сохранился. Core result SHA256
  `accc47fe294a887555f2cc112d7cf5dac0a2e202fc84b20b3abec60620fe4cef`.
  Uniform16/21°controls после bounded600STOP совпали, но rollback там
  NOT_EXERCISED; исходный180STOP settleFAIL сохранён, CheckSettled не ослаблен.
- Отдельный strict flat→ramp:24worldruns/8exercised/0notEx/0unmatched PASS,
  оба профиля1/4steps,16/21°.180STOP наflat→600W→neutralcoast доactualv<−.6
  →480freshW. Первый brakephase exact, затем heldW не перевооружается.
  MS1old88–144braked steps→new2; IS7old211–287→new3–4. ИС7/4steps/21°:
  finalspeed−.494821→+5.2173896м/с, originheightdelta−1.43318→+8.11153м.
  Авторский mesh8vertices/6triangles не выдаётся за карту клиента. ResultSHA
  `454ddc47cde723162fed5a88d98daee57291790c7897e43c9cf7d572ff5b9ea8`.
- Powered component128actualworldruns PASS, result побайтно равен прежнему
  `5a0330b1e58b1c7b183f460315949bfa685858210164f4fd0cc441298be0e267`.
- Canonical legacy03 build25rawexactPASS; отдельная simulation его бинарника
  NOT_RUN. Обе P05B06 matrices9×2 quality/replayPASS на actual Program route:
  57streams/profile против каждого04/05 результата,3780publicframes с
  calibration, metrics/checks/symmetry byteexact04==05==06.430historical
  evidencefiles неизменны. Это не новое native принятие legacy/shared.

Точные restore/build/run argv, local offline lock/config, source pins и own
PID/creation/EOF/exit receipts находятся в этом combined evidence и fresh
build folders. `tools/p05c_reversal_checks` compile-links productionphysics;
core `--mode all` не запускает отдельный `RampFreshChecks`. Strict ramp PASS
требует24runs/8exercised/0notEx/0unmatched; отсутствие кейса не скрывается.
Production source/runtime/helpers прежних стендов/БД не ретеганы.

## Следующий checkpoint и ручная приёмка

Full03 **PREPARED_NOT_RUN** до фактического Root запуска на finalsourcecommit;
исторический bc5c1c6/full02 не заменяет этот gate. После нового fullPASS и
source-after: свежий source-bound stand130 из actual SQL144/56 либо более
поздней БД, без grants/возврата потраченного БК; старый129 не менять.
Native130/LOS/fullroll-control/новый poweredturn/тот же originalhill NOT_RUN.

Единый manual сценарий после bound/seal130: общий AИС7/BМС1, READY/движение/
наведение; разгон с поворотом, бок/крыша и взаимный засвет, original подъём
под непрерывным W с попытками поворота и новый W после естественного отката;
затем естественные итоги и возврат обоих. Точные commands/rollback берутся
из нового sealed130, не из packets120/129. Актуальные БД/склад/историю не
откатывать. Приёмка P05C остаётся FAIL/open до этих gates; mainffce8cb прежний.


Отдельное поручение владельца P07B «оригинальный засвет0.9.1 без маскировки»:
исходные points/rays/viewrange и SixthSensealways для командира исследуются
в другом чате, собственной ветке/worktree. Его pending runtime не является
частью P05C acceptance, здесь не запускался и не объявлен готовым.
