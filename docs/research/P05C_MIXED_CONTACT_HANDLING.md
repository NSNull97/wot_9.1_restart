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
Native combat/тот же склон/новый roll/возвраты пока PENDING/NOT_RUN.

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
Ни reverse-brake cycle, ни взаимное «прилипание» wheel rays там не подтверждены.

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

Canonical full с новым `WOT_P05C_ARTIFACTS` и свежий Core successor выполнены.
Следующий шаг — ручное подтверждение владельца на уже загруженном mixed бою.
В первом — ИС7, во втором — МС1, после отсчёта проверить управление/наведение;
ИС7 толкает неподвижный МС1 по ровному на тот же подъём без отпускания газа,
затем отъезжает назад. Отдельно — полный переворот/камера и возврат обоих.
Не считать code/component PASS native приёмкой. Main не изменён.

Остановка живого129: взять exact argv `stop.b`, затем `stop.a` из
`native-commands129.json`, затем `stop_gateway`/`stop_bridge` из
`operators-core129.json`. Только own identity-bound receipts; текущую БД
сохранить. Не запускать старые120 packets на129 и не возвращать старый БК.

Будущий [RULESET-01](../plans/RULESET01_SCOPE.md) записывает новые требования
владельца: общие правила/конфиги, тимдамаг, командный/общий чат и обсуждение
дальности. Это требования; gameplay/defaults и полёт снаряда здесь не менялись.
