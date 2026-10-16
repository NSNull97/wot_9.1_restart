# P08C: единая команда Vehicle и Arena для родного маркера

Утренний coreV7 gate владельца2026-10-16 выявил красное имя и зелёный ромб
противника только у первого игрока. Ветка codex/p08c-native-marker-team от
проверенного core9920a638, исходная NET ветка b6c294f сохранена. Непринятые
родительские карточки не разрешают merge всей цепочки в main.

## VERIFIED / OBSERVED

Original#717 VehicleMarkersManager.createMarker выбирает Ally/Enemy класс по
Vehicle.publicInfo.team против Avatar.team; имя/entityType отдельно берёт
Arena.vehicles.team. PUBLIC_VEHICLE_INFO fixedDict: name/compDescr/teamUINT8/
prebattleID/marks. battle.pyc SHAaa43bc6b7e1f7ae9e2bba03fa527a9e6ce95a5d41ef23f26785b1490cd6f38de.
Own shared/wire.rs::create_vehicle пишет literal1 в publicInfo; roster/Avatar
уже используют World.team. Actual packet1646/1656 последнего боя0380 содержат
VehicleB team1 при rosterteam2; ownerconfirmed A-only green enemy marker.

## Изменение и проверка

1. Сохранить утренний native evidence и durableammo[0,3,9]/active0. Остановить
   только actual clients/gateway/bridge morning-mixed01 по собственным receipts.
2. В shared encoder передавать World.team(slot), без клиентского paint/Flash
   патча и без изменения старого одноклиентского lab seed.
3. Добавить независимый bounded native-layout decode regression для2команд,
   mixed6/variable names/descriptors и сохранения старого all-team1 режима.
4. Committed head, canonical full gateway/source-before-after/executable gate.
   Новая versioned stand binding, те же установленные coreV7 overlays/DB3/9;
   никаких grants/reinstall/старыхbinding edits. Fresh run, реальные A/B снова.
5. Owner проверяет красные вражеские имя И ромб в обоих окнах свежего боя;
   actual wire publicInfo/roster/Avatar команды согласованы. До этого UI NOT_RUN.

Новая найденная проблема late results для раннего manual leaver — отдельный
follow-up P08C: Amanual117 не имеет полного p06t_result, Bnatural32 имеет итог
обоих. Старые terminal/CAS/БК не переписывать. Spawn обеих команд рядом также
отдельное правило размещения; в исправление цвета не подмешивать.

Evidence: local/evidence/20261016-corev7-morning01 и
local/evidence/20261016-p08c-marker-team01. Откат — сохранённый coretag/exe и
matchingbinding03 после ownstop; клиент и БД этой правкой не меняются. Main
ffce8cb неизменен. Единственный следующий шаг — узкая правка sharedteam.
