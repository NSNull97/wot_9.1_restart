# P08C — Vehicle.publicInfo.team и класс родного маркера

## VERIFIED static #717

`res/scripts/client/gui/scaleform/battle.pyc`, SHA
aa43bc6b7e1f7ae9e2bba03fa527a9e6ce95a5d41ef23f26785b1490cd6f38de:
VehicleMarkersManager.createMarker2597 берёт publicInfo.team и сравнивает с
Avatar.team для выбора VehicleMarkerAlly/VehicleMarkerEnemy. Имя/entityType
независимо берёт из Arena.vehicles.team. Vehicle.startVisual562 создаёт класс
маркера один раз; updateMarkers его не перевыбирает. Поэтому исправление до
createDetailed/startVisual, а не поздняя косметическая перекраска.

Originalalias.xml SHA14d5fcce8d979de6c24c50b3ff94d3ddf464f4ad27f2ef68c063407b4bbbc746:
PUBLIC_VEHICLE_INFO — fixedDict nameSTRING/compDescrSTRING/teamUINT8/
prebattleIDOBJECT_ID/marksOnGunUINT8. Originalvehicle.def
SHA08dc1e6be577f80a04bf813ca046550201a3c4e673dad1540c5f1c6a047d1297:
publicInfo ALL_CLIENTS. Исходный клиент исследовался только bounded static
read/dis/packedXML, оригинальный код не исполнялся и не изменялся.

## VERIFIED own source и actual wire

Core9920a638: shared/wire.rs::roster_row и Avatar объявления используют
World.team(slot), но create_vehicle записывает literal1 в publicInfo после
двух строк переменной длины. Функция общая для начального создания и повторного
enter видимости. Старый arena/vehicle.rs лабораторный seed — другой путь.

Actual morning-mixed01/arena8312038850502760380:

| Получатель | Roster | VehicleA | VehicleB |
|---|---|---|---|
| A | packet1631/seq278:1,2 | packet1645/seq280:1 | packet1646/seq281:**1 вместо2** |
| B | packet1636/seq184:1,2 | packet1654/seq186:1 | packet1656/seq187:**1 вместо2** |

Packet1646 SHA9541827be83fc24c296c5a57c3dd26554e80225fb0699ffae4051502cb04c166;
packet1656 SHAed9bd567c09c4b95131fd77462f70b363798ce5c82e6d88ec9e25f5e2e163e78.
Пакеты декодировались только в памяти, auth secrets не выводились. В последующих
creates тоже team1. Capture сохраняется в исходном private stand; сюда ресурсы,
ключи и содержимое пакетов не публикуются.

## OBSERVED owner и вывод

Screenshot: красное имя enemy при зелёном ромбе. Владелец уточнил: только A,
у второго игрока всё правильно. A.team1+VehicleB.team1 даёт Allyclass при
rosterB.team2; B.team2+VehicleA.team1 даёт корректный Enemyclass. Это ровно
совпадает с observed asymmetry. Own clientpatches не подменяют marker class.

Узкая правка: publicInfo.team из World.team(actorSlot), одинаковый для всех
получателей. Legacy all-team1 без lifecycle остаётся прежним. Тесты должны
независимо читать измеренный indexedstream, разные имена/descriptor и все6слотов;
roundtrip нового собственного декодера сам по себе native gate не закрывает.
После full gate нужен свежий бой обоих настоящих клиентов и owner colors.

## VERIFIED automated gate — 2026-10-16

Runtime `363daa371ca00da0ff0d7aa55e7a429d49bb6928`: targeted `p08c_marker_`
3 PASS / 0 ignored и сборка PASS. Canonical full
`python -B -X utf8 server/build.py gateway --test --out local/build/server/gateway-p08c-marker-full01`
при `RUST_TEST_THREADS=1`: **1099 PASS / 0 FAIL / 5 прежних ignored**, сборка PASS.
Все 683 raw source SHA до/после совпали, head не менялся. Executable SHA256
`288a7699aa265a3522db2661f7270804f922c36a15ec6c240125633aab57d6fd`.

Три новых regression независимо читают native layout для owned MS-1/ИС-7,
шести mixed profiles с UTF-8 именами и parked recreate. Отдельный source-derived
golden сохраняет полный legacy all-team1 layout; это не выдаётся за native capture.
Fresh `binding-p06t04.json` создана штатным guard после full/source gate.
Старые binding02/03 не менялись. Перед запуском RO SQL подтвердил A117/B32,
у обоих AP0/HEAT3/HE9, active reservations 0; SQL reset/grants не выполнялись.
Evidence: `local/evidence/20261016-p08c-marker-team01/source-{before,after}.json`,
canonical build logs и versioned launch receipts.

Actual fresh `morning-marker01`: private services startup PASS, A затем B
прошли native login и по два последовательных hangar/cache/model samples
в новых PID-specific traces. Все 96 installed nonmutable files совпадают
с прежними ledgers. После run_open база A118/B33, active0, БК у обоих 0/3/9.
`ready11.json` SHA256
`b7bc1ff92ae220780bd5153df8050322306188cbd00d61c4777652be0dce3f98`.
Инструментация доказывает загрузку ангара; native цвет проверен отдельно ниже.

## VERIFIED actual wire / OBSERVED owner acceptance

Владелец: «У обоих имя и ромб красные, управление работает».
Свежий бой9187569394802767952 содержит два отдельных native Base session.
Порядок входа в очередь обратный предыдущему бою: A/session1 team2,
B/session2 team1. Это не предположение checker по порядку подключения.

| Получатель | Свой Avatar.team | Enemy publicInfo.team / roster.team | Owner UI |
|---|---|---|---|
| A/session1 | 2 | 1 / 1 | красные имя и ромб, управление работает |
| B/session2 | 1 | 2 / 2 | красные имя и ромб, управление работает |

Bounded read-only разбор actual capture:11183 encrypted packets/524550 wire
bytes,4 initial createDetailed,0 team/identity mismatches. Полный line-prefix,
без пропущенных unreliable frames; это snapshot, а не весь будущий run.
Original marker-class выбор остаётся выводом из подтверждённого source;
фактический цвет и управление отдельно подтверждены владельцем. Повторный бой
и visibility recreate этим свежим capture ещё не проверены.

Фактически выполнена команда:
`python -B -X utf8 local/night-staging/20261016/p08c-marker-wire01/check.py --run morning-marker01 --receipt freshmarker01.json`.
Checker имел7 offline authored tests PASS и actual historical negative control:
20712 packets,6 прежних team conflicts,0 identity conflicts. Новый receipt SHA
`483a8bd196bd6490469467cde2113548c302dbe05693046c755abd1be737a631`.
Разбор не выполнял network/UI/SQL actions, не сохранял keys/credentials/plaintext.
Сводный owner+wire receipt `phase12-owner-marker.json` SHA
`4de0bdd0f2c435886e132748d5ab6a1016eb0d997f2a18e2fca00124c22c13f2`.

Отдельно зафиксированы неподтверждённая opposite-base spawn policy и отсутствие
полного результата у раннего manual leaverA. Эти изменения не входят в marker
fix и не объявлены нормальной исторической работой клиента.

План — [P08C_NATIVE_MARKER_TEAM](../plans/P08C_NATIVE_MARKER_TEAM.md).
Evidence — local/evidence/20261016-corev7-morning01 и
local/evidence/20261016-p08c-marker-team01. Узкий marker gate PASS.
Вся P08C и родительская цепочка пока не приняты и остаются вне main.
