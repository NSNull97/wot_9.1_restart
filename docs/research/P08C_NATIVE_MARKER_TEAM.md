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

Отдельно зафиксированы неподтверждённая opposite-base spawn policy и отсутствие
полного результата у раннего manual leaverA. Эти изменения не входят в marker
fix и не объявлены нормальной исторической работой клиента.

План — [P08C_NATIVE_MARKER_TEAM](../plans/P08C_NATIVE_MARKER_TEAM.md).
Evidence — local/evidence/20261016-corev7-morning01 и
local/evidence/20261016-p08c-marker-team01. До actual повторной проверки UI
остаётся FAIL/NOT_RUN, вся родительская цепочка вне main.
