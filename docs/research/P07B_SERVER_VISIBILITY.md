# P07B — серверная видимость v1

2026-10-16. Ночная зависимая ветка `codex/p07b-server-visibility` после P05C;
native-приёмка отложена владельцем до утра. Источники #717, exact AoI layout и
stock range pins — [P07B_NATIVE_INTEREST](P07B_NATIVE_INTEREST.md). Не смешивать
статический контракт, автоматическую сетевую репликацию и настоящую native UI.

## Реализованный контракт

VERIFIED_CODE: `visibility_v1` — явный boolean config, defaultfalse, разрешён
только с profile13 battle. Ночной config включает true; legacy сценарии сохраняют
прежнюю публикацию. Config budget20, общий private request DTO budget16 не изменён.
World получает authoritative kind/team/pose; stock МС-1 turret23 имеет240м,
stock ИС-7 turret47 —400м. Центры сравниваются по3D inclusive distance.

Explicit **test_lab-interest-range-single-los-v1**: своя машина и союзники
передаются всегда; противник требует range и одного чистого LOS. Sight point —
stock turret pivot +0.5m по локальному Y, затем полный authoritative hull rotation.
Смещение0.5m, centre distance, single ray, allies policy и немедленное переключение
приближённые; исторические camo/кусты/radio/delay/retention не реализованы.
LOS использует настоящие pinned Terrain и static BVH существующего projectile
export. Его collision mask — явное приближение, не восстановленная visibility mesh.
Ground не исключается; разрушенные/упавшие объекты исключаются по actual mesh
instanceID из подтверждённого World. Ошибка query завершает battle по STAB policy,
а не разрешает старый permissive interest set. Совпавшие sight points считаются
чистым нулевым лучом до Terrain query; сами точки проверяются на finite bounds.

VERIFIED_CODE: каждому соединению принадлежит bounded Book на6slots. Порядок:
Hidden → queued Enter → фактический requestEntityUpdate → Create → creation ACK.
Каждый Create привязан к reliable sequence именно своей части Enter. Sequence0
разрешён. Отдельного ожидания Enter ACK нет: клиент вправе запросить уже queued
entity до самостоятельного ACK-пакета. Поздний запрос скрытой машины поглощается
без создания; неизвестный/отсутствующий slot и испорченный envelope отвергаются.

При скрытии fresh state сразу закрыт, даже при полном восьмипакетном окне.
Queued Leave ждёт actual cumulative/selective ACK; новый Enter до этого ACK
невозможен. Старые Create/HP/pending requests/ready state очищаются; повторный
засвет требует нового Create и его ACK. Все mutations происходят в Session clone;
испорченный хвост откатывает ACK/Book/очереди/commands целиком. Incoming wrapper
обновляет вид из свежего World в том же transaction, а отдельный last_pose_tick
не позволяет refresh заглушить новые позиции.

VERIFIED_CODE: позиции/aim, Create, численное HP, fire cues, tracer и impact FX
фильтруются до reliable enqueue. Отложенные private bodies хранят target slots
и current Enter epochs отдельно от public outbox; при освобождении окна проходят
повторную проверку. Скрытие/новый epoch удаляет их до присвоения sequence. Если
из combined impact+HP body исчез стрелок, catch-up HP оставшейся видимой жертвы
инвалидируется и восстанавливается из текущего World. Уже назначенный reliable
sequence сохраняет неизменные retry bytes: это ранее разрешённое состояние.

Terminal снаряда требует текущего засвета стрелка и, при vehicle collision, цели.
Нельзя передать точку скрытого попадания через stopTracer/explodeProjectile.
При запрещённом terminal callback подавляется, событие поглощается; original
bounded flight заканчивается по range. Поведение его FX после исчезновения
стрелка всё ещё требует native проверки. Заново засвеченная машина не проигрывает
старые выстрелы/попадания. Собственный HUD получает фактическое HP от скрытого
стрелка без его позиций. Public kill event передаётся ровно однажды независимо
от точных impact FX, поэтому скрытый lethal shot не ломает событие арены.

Явно публичны roster/name/type/team/ready/alive, arena periods/capture/kill IDs
и общее состояние разрушенных map objects. В этих данных нет координат машин,
aim, численного чужого HP или исходных точек скрытых выстрелов. Это не режим
скрытого состава команд. Полный результат после боя — существующий P08C contract.

## Проверки и доказательства

Pure components:12PASS/0ignored, `local/build/server/p07b-components04/receipt.json`.
Интеграция: `gateway-p07b-focused01` **23PASS/0ignored/buildPASS**:

- восемь Session/codec/ACK/epoch/backpressure/rollback сценариев;
- семь world/geometry сценариев, Config boolean и два source range;
- шесть packet tests: hidden initial request, private deferred purge,
  fresh pose after refresh, hidden-target terminal, hidden-attacker own HP,
  три настоящих AP-попадания со смертью созданной машины/public kill once.

Тест actual Прохоровки использует pinned terrain и285350 static triangles:
закрытый луч instance17/triangle8521 и чистый луч независимо перепроверены
read-only Python reader. Шесть mixed получателей ×20snapshots дают360 LOS;
матрица повторяется, World не меняется. Original client при этом не запускался.
`local/evidence/20261016-p07b-01/independent-rays01.json` и actual-map-timing01.*.
OBSERVED debug/unit timing:23063µs на20полных матриц,1153µs на одну матрицу;
это измерение конкретной машины/выбранных лучей, без native/performance порога.

Read-only cross-review — `local/evidence/20261016-p07b-integration-audit01/`.
Он нашёл private raw-outbox, cached-view и hidden-kill риски; реализация и
соответствующие tests исправляют их, исходные отчёты сохранены.

Полный canonical gate runtime `8fecb9dc59e51052c983cbfc7f5dd52161af6a8b`:
**975 PASS / 5 прежних ignored / build PASS**. Source607files/exactHEAD before
и after совпадают: `local/evidence/20261016-p07b-full01/`.
Exe SHA256 `a969893a4763fa6d8514244162a7313051e5242669e90a2bf97a0f2274193cd9`.
Стенд actual bind PASS (`binding-p07b.json`), visibility_v1=true18fields.
Native disappearance/reappearance, UI/markers/audio/control — **NOT_RUN**.

## Запуск, ограничения, откат

```powershell
$env:RUST_TEST_THREADS='1'
python -B -X utf8 server/build.py gateway --test --test-filter p07b_ --out local/build/server/gateway-p07b-focused-FRESH
python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-p07b-full-FRESH
```

Ночной стенд: `local/stands/night-battle-20261016-01`, команды/MORNING.md и
run.py требуют exact tested source/exe/config/resources. visibility-mode01.json
сохраняет config backup P05C; после full/sourceafter нужен свежий P07B binding.
Install/services/native пока NOT_RUN. Утром: обоюдный засвет вблизи, укрытие за
геометрией и возврат,300м между mixed ИС7/МС1 (asymmetric400/240), повторить
hide/show, выстрел по скрытой цели/от скрытого стрелка, смерть/итоги/новый бой.
Точные packet absence проверяются автоматически; визуальная проверка отдельно.

Откат — P07B commits на своей ветке, прежний P05C exe и сохранённый config;
клиент — install ledger. Новых DB migrations эта карточка не добавляет.
Приёмка: **автоматический focused/full/source/build PASS, native NOT_RUN**.
Единственный следующий шаг — подготовить P04M
в отдельной зависимой ветке без merge непринятой native карточки в main.
