//! Parameterized #717 layouts, kept separate from the frozen primary-profile
//! probes. Bounded actors retain their own immutable server-selected profiles.
use std::io;
use super::{model::{self, Actor, World}, projectile::Projectile};
use super::{aim, vehicle_profile::VehicleKind};
use crate::{arena091 as arena, arena_vehicle091 as vehicle};

pub const SPACE: u32 = 1;
/// Original #717 gun_rotation_shared: 10 biased yaw bits, 6 restricted pitch.
/// Keep this serializer at the wire boundary, not in the aiming simulation.
pub fn packed_angles(state: &aim::State) -> io::Result<u16> { packed_angles_for(VehicleKind::Ms1,state) }
pub fn packed_angles_for(kind: VehicleKind,state: &aim::State) -> io::Result<u16> {
    let spec=kind.aim();
    if !state.yaw.is_finite() || !state.pitch.is_finite() || state.yaw.abs() > std::f32::consts::PI
        || !(spec.min_pitch..=spec.max_pitch).contains(&state.pitch) { return Err(model::bad()); }
    let yaw = ((state.yaw as f64 + std::f64::consts::PI) * 1024. / (2. * std::f64::consts::PI)).round() as u16 & 1023;
    let pitch = ((state.pitch as f64 - spec.min_pitch as f64) * 63. / (spec.max_pitch as f64 - spec.min_pitch as f64)).round() as u16;
    Ok((yaw << 6) | pitch)
}
pub fn aim_intent(raw: &[u8], own: usize) -> io::Result<Option<aim::Intent>> {
    let id = *raw.first().ok_or_else(|| model::bad())?;
    let expected = match id { 0x8e => 8, 0x8f => 12, 0x0f => 16, _ => return Ok(None) };
    if raw.len() != 3 + expected || raw[1..3] != (expected as u16).to_le_bytes() { return Err(model::bad()); }
    vehicle_id(own)?;
    let args = if id == 0x0f {
        if raw[3..7] != vehicle_id(own)?.to_le_bytes() { return Err(model::bad()); } &raw[7..]
    } else { &raw[3..] };
    let value = |n: usize| f32::from_le_bytes(args[n*4..n*4+4].try_into().expect("checked fixed aim layout"));
    let intent = if id == 0x8e { aim::Intent::Hold { yaw: value(0), pitch: value(1) } }
        else { aim::Intent::Point([value(0),value(1),value(2)]) };
    intent.validate()?; Ok(Some(intent))
}
pub fn vehicle_id(slot: usize) -> io::Result<u32> {
    if slot >= model::MAX_ACTORS { return Err(model::bad()); }
    // The original pair occupies3/5; AreaDestructibles owns7..150. New
    // actors and their Avatars use another server-owned entity ID range.
    Ok(if slot<2 {vehicle::VEHICLE_ENTITY_ID+2*slot as u32}
        else {0x0911_0003+2*(slot as u32-2)})
}
pub fn avatar_id(slot: usize) -> io::Result<u32> { Ok(vehicle_id(slot)? - 1) }
pub fn vehicle_alias(slot:usize)->io::Result<u8> {
    vehicle_id(slot)?;
    // Existing area aliases2..145 retain their accepted native layout.
    Ok(if slot<2 {slot as u8}else{240+slot as u8-2})
}
pub fn slot_for_vehicle(id: u32) -> io::Result<usize> {
    (0..model::MAX_ACTORS).find(|slot| vehicle_id(*slot).ok() == Some(id)).ok_or_else(|| model::bad())
}
fn string(b: &mut Vec<u8>, value: &[u8]) -> io::Result<()> {
    if value.len() >= 255 { return Err(model::bad()); } b.push(value.len() as u8); b.extend(value); Ok(())
}
fn var16(id: u8, p: &[u8]) -> io::Result<Vec<u8>> {
    if p.is_empty() || p.len() > 500 { return Err(model::bad()); }
    let mut b = vec![id]; b.extend((p.len() as u16).to_le_bytes()); b.extend(p); Ok(b)
}
fn f3(b: &mut Vec<u8>, p: [f32; 3]) { for x in p { b.extend(x.to_le_bytes()); } }
fn native_direction(b: &mut Vec<u8>, ypr: [f32; 3]) { f3(b, [ypr[2], ypr[1], ypr[0]]); }
fn actor(w: &World, slot: usize) -> io::Result<&Actor> {
    vehicle_id(slot)?;
    let a = w.actors.get(slot).ok_or_else(|| model::bad())?;
    if w.id == 0 || a.identity.database <= 0 || a.identity.name.len() > 48 || !(0..=a.vehicle_kind().max_health()).contains(&a.health)
        || a.position.iter().any(|x| !x.is_finite() || x.abs() > 2000.)
        || a.direction.iter().any(|x| !x.is_finite() || x.abs() > std::f32::consts::PI)
        || a.direction[0] != a.yaw { return Err(model::bad()); }
    Ok(a)
}
pub fn reset(w: &World, slot: usize) -> io::Result<Vec<u8>> {
    let a = actor(w, slot)?;
    let mut b = vec![0x13, 0x3b]; // Account.onArenaCreated
    b.extend(arena::reset_to_avatar_base_for_map(&arena::AvatarBaseSeed { entity_id: avatar_id(slot)?,
        name: &a.identity.name, arena_unique_id: w.id }, w.map)?); Ok(b)
}
pub fn roster(w: &World) -> io::Result<Vec<u8>> {
    if w.actors.len() != model::CAPACITY { return Err(model::bad()); }
    roster_list(w,0..model::CAPACITY)
}
fn roster_row(w:&World,slot:usize)->io::Result<Vec<u8>> {
    let a=actor(w,slot)?;let mut d=vec![b'(',b'J'];d.extend(vehicle_id(slot)?.to_le_bytes());
    d.push(b'U');string(&mut d,a.vehicle_kind().descriptor())?;
    d.push(b'U');string(&mut d,a.identity.name.as_bytes())?;
    d.extend([b'K',w.team(slot)?,if a.health>0{0x88}else{0x89},if a.ready{0x88}else{0x89},0x89,b'J']);
    d.extend(a.identity.database.to_le_bytes());d.extend([b'U',0,b'K',0,b'K',0,0x89,b'}',b'K',0,b't']);Ok(d)
}
fn roster_list(w:&World,slots:std::ops::Range<usize>)->io::Result<Vec<u8>> {
    // Own bounded literal protocol2 data; never an input object decoder.
    let mut d = vec![0x80, 2, b']'];
    for slot in slots {d.extend(roster_row(w,slot)?);d.push(b'a');}
    d.push(b'.'); update(1, &d)
}
/// Original ClientArena updates2/11 each consume one vehicle tuple; the
/// initial list is kept small enough for the measured UINT8 stream length.
pub fn roster_updates(w:&World,slot:usize)->io::Result<Vec<u8>> {
    if w.actors.len()==model::CAPACITY{return roster(w);}
    let mut d=vec![0x80,2];d.extend(roster_row(w,slot)?);d.push(b'.');update(11,&d)
}
fn update(kind: u8, d: &[u8]) -> io::Result<Vec<u8>> {
    if d.len() > 252 { return Err(model::bad()); }
    let mut b = vec![0x13, 0x58, (d.len() + 2) as u8, kind, d.len() as u8]; b.extend(d); Ok(b)
}
pub fn announcement(w: &World, own: usize) -> io::Result<Vec<u8>> {
    if w.actors.len()!=model::CAPACITY {return Err(model::bad());}
    let a = actor(w, own)?;
    let mut b = arena::create_cell_avatar(&arena::AvatarCellSeed { space_id: SPACE,
        player_vehicle_id: vehicle_id(own)?, position: a.position })?;
    b[39] = w.team(own)?;
    // Native createCellPlayer's direction stream is roll/pitch/yaw, while
    // the domain/worker stores yaw/pitch/roll.
    for (i, value) in [a.direction[2], a.direction[1], a.direction[0]].into_iter().enumerate() {
        b[27 + i * 4..31 + i * 4].copy_from_slice(&value.to_le_bytes());
    }
    b.extend(arena::space_data_for_map(SPACE, (SPACE as u64).to_le_bytes(), w.map)?);
    b.extend(roster(w)?);
    for slot in 0..model::CAPACITY {
        b.push(0x0a); b.extend(vehicle_id(slot)?.to_le_bytes()); b.push(vehicle_alias(slot)?);
    }
    if b.len() > 500 { return Err(model::bad()); } Ok(b)
}
/// Split only between complete native records. No oversized pickle or
/// fragmented entity method is handed to the client's reliable dispatcher.
pub fn announcement_parts(w:&World,own:usize)->io::Result<Vec<Vec<u8>>> {
    if w.actors.len()==model::CAPACITY{return Ok(vec![announcement(w,own)?]);}
    if !(2..=model::MAX_ACTORS).contains(&w.actors.len()) || w.actors.len()!=w.expected_actors() {return Err(model::bad());}
    let a=actor(w,own)?;
    let mut first=arena::create_cell_avatar(&arena::AvatarCellSeed{space_id:SPACE,player_vehicle_id:vehicle_id(own)?,position:a.position})?;
    first[39]=w.team(own)?;
    for(i,value)in[a.direction[2],a.direction[1],a.direction[0]].into_iter().enumerate(){first[27+i*4..31+i*4].copy_from_slice(&value.to_le_bytes());}
    first.extend(arena::space_data_for_map(SPACE,(SPACE as u64).to_le_bytes(),w.map)?);
    // Maximum-length owned names can make even two rows exceed252 bytes.
    first.extend(roster_list(w,0..1)?);
    let mut parts=Vec::new();let mut body=first;
    for slot in 1..w.actors.len(){
        let mut d=vec![0x80,2];d.extend(roster_row(w,slot)?);d.push(b'.');let record=update(2,&d)?;
        if body.len()+record.len()>500{parts.push(body);body=Vec::new();}body.extend(record);
    }
    for slot in 0..w.actors.len(){
        let mut record=vec![0x0a];record.extend(vehicle_id(slot)?.to_le_bytes());record.push(vehicle_alias(slot)?);
        if body.len()+record.len()>500{parts.push(body);body=Vec::new();}body.extend(record);
    }
    if !body.is_empty(){parts.push(body);}if parts.iter().any(|p|p.is_empty()||p.len()>500){return Err(model::bad());}Ok(parts)
}
pub fn create_vehicle(w: &World, slot: usize) -> io::Result<Vec<u8>> {
    let a = actor(w, slot)?;
    let mut p = vec![0]; p.extend(vehicle_id(slot)?.to_le_bytes()); p.extend(2u16.to_le_bytes());
    f3(&mut p, a.position); f3(&mut p, a.direction);
    p.extend([8, 0, 0, 1, 1, 2]); p.extend(packed_angles_for(a.vehicle_kind(),&a.aim)?.to_le_bytes());
    p.push(3); p.extend(a.health.to_le_bytes()); p.extend([4, 0, 0, 5]);
    string(&mut p, a.identity.name.as_bytes())?; string(&mut p, a.vehicle_kind().descriptor())?;
    p.push(1); p.extend(0i32.to_le_bytes()); p.push(0);
    p.push(6); p.extend(0i32.to_le_bytes()); p.push(7); p.extend(0i32.to_le_bytes());
    var16(9, &p)
}
pub fn entity_requests(b: &[u8]) -> io::Result<Option<Vec<usize>>> {
    if b.first() != Some(&8) { return Ok(None); }
    if b.is_empty() || b.len() > model::MAX_ACTORS*7 || b.len() % 7 != 0 { return Err(model::bad()); }
    let mut slots = Vec::new();
    for row in b.chunks_exact(7) {
        if row[..3] != [8, 4, 0] { return Err(model::bad()); }
        let slot = slot_for_vehicle(u32::from_le_bytes(row[3..7].try_into().map_err(|_| model::bad())?))?;
        if slots.contains(&slot) { return Err(model::bad()); } slots.push(slot);
    }
    Ok(Some(slots))
}
pub fn ready(payload: &[u8], own: usize) -> io::Result<()> {
    // Preserve the previously native-observed exact four-method compound,
    // validating only the identity field against this connection's own actor.
    if payload.len() != 33 || payload[7..11] != vehicle_id(own)?.to_le_bytes() { return Err(model::bad()); }
    let mut pinned = payload.to_vec(); pinned[7..11].copy_from_slice(&vehicle::VEHICLE_ENTITY_ID.to_le_bytes());
    crate::arena_ready091::validate_compound(&pinned, vehicle::VEHICLE_ENTITY_ID)
}
/// Original AvatarPositionControl postmortem rebind measured in native01:
/// Cell Avatar.bindToVehicle, mailbox0 + own OBJECT_ID. This acknowledges a
/// redundant camera binding only; caller must require the owned actor dead.
pub fn postmortem_rebind(payload: &[u8], own: usize) -> io::Result<()> {
    if payload.len()!=11 || payload[..7]!=[0x0d,8,0,0,0,0,0]
        || payload[7..]!=vehicle_id(own)?.to_le_bytes() { return Err(model::bad()); }
    Ok(())
}
pub fn ready_update(slot: usize) -> io::Result<Vec<u8>> {
    let mut d = vec![0x80, 2, b'J']; d.extend(vehicle_id(slot)?.to_le_bytes()); d.push(b'.'); update(7, &d)
}
pub fn reload(slot: usize, time_left: f32) -> io::Result<Vec<u8>> { reload_for(VehicleKind::Ms1,slot,time_left) }
pub fn reload_for(kind: VehicleKind,slot: usize, time_left: f32) -> io::Result<Vec<u8>> {
    if !time_left.is_finite() || !(0. ..=kind.reload_seconds()).contains(&time_left) { return Err(model::bad()); }
    let mut b = vec![0x13, 0x46]; b.extend(vehicle_id(slot)?.to_le_bytes());
    b.extend(time_left.to_le_bytes()); b.extend(kind.reload_seconds().to_le_bytes()); Ok(b)
}
pub fn ammo_count(count: u16) -> io::Result<Vec<u8>> { ammo_count_for(VehicleKind::Ms1,count) }
pub fn ammo_count_for(kind: VehicleKind,count: u16) -> io::Result<Vec<u8>> {
    if count > kind.ammo_limit() { return Err(model::bad()); }
    let mut b = vec![0x13, 0x44]; b.extend(kind.shell_compact_id().to_le_bytes()); b.extend(count.to_le_bytes());
    b.extend([0, 0, 0]); Ok(b)
}

#[cfg(test)]
#[test]
fn profile13_owned_ammunition_publication_accepts_source_capacity_without_granting_any() {
    for kind in [VehicleKind::Ms1,VehicleKind::Is7] {
        for count in [0,7,11,kind.ammo_limit()] {
            let body=ammo_count_for(kind,count).unwrap();
            assert_eq!(&body[..2],&[0x13,0x44]);assert_eq!(&body[2..6],&kind.shell_compact_id().to_le_bytes());
            assert_eq!(&body[6..8],&count.to_le_bytes());
        }
        assert!(ammo_count_for(kind,kind.ammo_limit()+1).is_err());
    }
}
/// Pinned #717: selectEntity FIXED4, Vehicle.showShooting(UINT8), then restore
/// Avatar selection. One MS-1 shot has burstCount=1. Native prediction handles
/// the shooter's already-played effect; neighbours use their original extras.
pub fn shooting(slot: usize) -> io::Result<Vec<u8>> {
    let mut b = vec![0x12]; b.extend(vehicle_id(slot)?.to_le_bytes());
    b.extend([0x3b, 1, 0x13]); Ok(b)
}

/// Original Avatar.showTracer fixed method: selected Avatar, shooter vehicle
/// id, bounded shot id, ordered shell-effects index and native projectile
/// parameters. The index is a wire concern; the domain owns only the flight
/// geometry and effective shell values. Launch facts remain serializable after
/// collision/range stop so a delayed receiver can receive start then stop.
/// Per-receiver delivery cursors own that order and exactly-once policy.
pub fn tracer_start(projectile: &Projectile) -> io::Result<Vec<u8>> {
    if projectile.sequence == 0 || projectile.sequence as usize > model::MAX_BATTLE_SHOTS
        || projectile.slot >= model::MAX_ACTORS
        || !projectile.origin.iter().all(|v| v.is_finite())
        || !projectile.velocity.iter().all(|v| v.is_finite())
        || !projectile.gravity.is_finite() || projectile.gravity <= 0.0
        || !projectile.max_distance.is_finite() || projectile.max_distance <= 0.0
    { return Err(model::bad()); }
    let mut b = vec![0x13, 0x4c];
    b.extend(vehicle_id(projectile.slot)?.to_le_bytes());
    b.extend(projectile.sequence.to_le_bytes());
    // Pinned #717 ordered effects: smallArmorPiercing2 / largeArmorPiercing14.
    b.push(projectile.vehicle_kind.shell().effects);
    f3(&mut b, projectile.origin);
    f3(&mut b, projectile.velocity);
    b.extend(projectile.gravity.to_le_bytes());
    b.extend(projectile.max_distance.to_le_bytes());
    if b.len() != 43 { return Err(model::bad()); }
    Ok(b)
}

/// Original Avatar.stopTracer fixed method. It is emitted once per tracer
/// start, and only after the server has stopped the projectile.
pub fn tracer_stop(projectile: &Projectile) -> io::Result<Vec<u8>> {
    if projectile.sequence == 0 || projectile.sequence as usize > model::MAX_BATTLE_SHOTS
        || projectile.slot >= model::MAX_ACTORS || !projectile.stopped
        || !projectile.terminal.iter().all(|v| v.is_finite())
    { return Err(model::bad()); }
    let mut b = vec![0x13, 0x48];
    b.extend(projectile.sequence.to_le_bytes());
    f3(&mut b, projectile.terminal);
    if b.len() != 18 { return Err(model::bad()); }
    Ok(b)
}
pub fn binding(w: &World, own: usize, now: std::time::Instant) -> io::Result<Vec<u8>> {
    let a = actor(w, own)?;
    let mut b = vec![2, 10, 3]; b.extend(w.tick.to_le_bytes());
    for slot in 0..w.actors.len() { if slot == own || w.actors[slot].ready { b.extend(ready_update(slot)?); } }
    if w.lifecycle.is_some() { b.extend(lifecycle_period(w)?); }
    else {
        let mut period = vec![0x80, 2, b'(', b'K', 3, b'G']; period.extend(3700f64.to_be_bytes());
        period.push(b'G'); period.extend(3600f64.to_be_bytes()); period.extend(b"Nt."); b.extend(update(3, &period)?);
    }
    b.push(0x14); b.extend(avatar_id(own)?.to_le_bytes()); b.extend(SPACE.to_le_bytes()); b.extend(vehicle_id(own)?.to_le_bytes());
    for _ in 0..6 { b.extend(0f32.to_le_bytes()); }
    b.extend([0x13, 0x4a]); f3(&mut b, a.position); f3(&mut b, a.direction);
    b.extend(a.speed.to_le_bytes()); b.extend(0f32.to_le_bytes());
    // Native Avatar.updateTargetingInfo starts the original gun rotator and
    // its original target-input path. Nominal resource parameters, no crew
    // modifier claim; conversions mirror the original resource readers.
    b.extend([0x13, 0x4b]);
    let kind=a.vehicle_kind(); let aiming=kind.aim();
    for value in [a.aim.yaw, a.aim.pitch, aiming.yaw_rate, aiming.pitch_rate, 1.,
        aiming.turret_dispersion, aiming.movement_dispersion, aiming.hull_dispersion, aiming.aiming_time] {
        b.extend(value.to_le_bytes());
    }
    for (descriptor, original_count) in kind.panel_rows() {
        b.extend([0x13, 0x44]); b.extend(descriptor.to_le_bytes());
        b.extend((if descriptor == kind.shell_compact_id() { a.fire.ammo() } else { original_count }).to_le_bytes());
        b.extend([0, 0, 0]);
    }
    b.extend([0x13, 0x40, 0]); b.extend(kind.shell_compact_id().to_le_bytes());
    let left = a.fire.reload_until().map(|end| end.saturating_duration_since(now).as_secs_f32()).unwrap_or(0.);
    b.extend(reload_for(kind,own, left.min(kind.reload_seconds()))?); Ok(b)
}
pub fn publication<const N:usize>(w: &World, visible: [bool; N]) -> io::Result<Vec<u8>> {
    if !(1000..=37000).contains(&w.tick) || N<w.actors.len() || N>model::MAX_ACTORS { return Err(model::bad()); }
    let mut b = vec![0x0d, w.tick as u8];
    for (slot, known) in visible.into_iter().take(w.actors.len()).enumerate() {
        if !known { continue; }
        let a = actor(w, slot)?;
        b.push(0x15); b.extend(vehicle_id(slot)?.to_le_bytes()); f3(&mut b, a.position);
        native_direction(&mut b, a.direction);
        // Pinned #717 dynamic entityProperty base 0x9e + indexed property 2.
        // UINT16 is fixed2. Restore Avatar selection after each vehicle.
        b.push(0x12); b.extend(vehicle_id(slot)?.to_le_bytes());
        b.push(0xa0); b.extend(packed_angles_for(a.vehicle_kind(),&a.aim)?.to_le_bytes()); b.push(0x13);
    }
    Ok(b)
}

pub fn finish_reason(reason: super::lifecycle::Reason) -> u8 {
    // Original #717 FINISH_REASON: extermination1, base2, timeout3,
    // failure4/technical5. No-contest uses the explicit technical result.
    match reason { super::lifecycle::Reason::Elimination => 1, super::lifecycle::Reason::Capture => 2,
        super::lifecycle::Reason::Timeout => 3, super::lifecycle::Reason::NoContest | super::lifecycle::Reason::Forfeit => 5 }
}
pub fn lifecycle_period(w: &World) -> io::Result<Vec<u8>> {
    use super::{lifecycle::Phase, lifecycle_wire::{self,Period}};
    let state = w.lifecycle.as_ref().ok_or_else(|| model::bad())?;
    let view = state.view();
    let phase = match view.phase { Phase::Waiting=>Period::Waiting,Phase::Prebattle=>Period::Prebattle,
        Phase::Battle=>Period::Battle,Phase::Afterbattle=>Period::Afterbattle };
    lifecycle_wire::period(phase,100. + view.ends_ms.unwrap_or(0) as f64 / 1_000.,
        view.length_ms as f64 / 1_000.,view.outcome.map(|o|(o.winner,finish_reason(o.reason))))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Instant;
    fn six_mixed(now:Instant)->World {
        let mut w=World::new_for_roster(123,now,crate::map_profile091::MapId::Karelia,6).unwrap();
        w.enable_lifecycle(super::super::lifecycle::Rules::prohorovka()).unwrap();
        for slot in 0..6 {
            let kind=if slot%2==0{VehicleKind::Ms1}else{VehicleKind::Is7};
            let(mut owner,frozen)=model::tests::profile13_loadout(kind,slot,kind.ammo_limit());owner.name="Я".repeat(24);
            w.attach_owned(owner,slot as u32+7,&frozen).unwrap();
        }
        w.start(now).unwrap();w
    }
    #[test] fn six_mixed_native_roster_splits_complete_single_vehicle_updates_and_preserves_own_profile() {
        let now=Instant::now();let w=six_mixed(now);
        let parts=announcement_parts(&w,5).unwrap();assert!(parts.len()>1);
        assert!(parts.iter().all(|part|!part.is_empty()&&part.len()<=500));
        let raw=parts.concat();let mut rosters=Vec::new();
        // The pinned ClientArena stream uses UINT8 argument lengths. Inspect
        // records independently of roster_row/roster_list construction.
        for at in 0..raw.len().saturating_sub(5) {
            if raw[at..at+2]==[0x13,0x58] {
                let len=raw[at+4] as usize;assert_eq!(raw[at+2] as usize,len+2);
                assert!(len<=252);let data=raw.get(at+5..at+5+len).unwrap();
                assert_eq!(&data[..2],&[128,2]);assert_eq!(data.last(),Some(&b'.'));
                rosters.push((raw[at+3],data.to_vec()));
            }
        }
        assert_eq!(rosters.iter().map(|row|row.0).collect::<Vec<_>>(),vec![1,2,2,2,2,2]);
        assert_eq!(&rosters[0].1[..3],&[128,2,b']']);
        for(slot,(_,data))in rosters.iter().enumerate(){
            assert!(data.windows(4).any(|bytes|bytes==vehicle_id(slot).unwrap().to_le_bytes()));
            assert!(data.windows(48).any(|bytes|bytes=="Я".repeat(24).as_bytes()));
            assert!(data.windows(w.actors[slot].vehicle_kind().descriptor().len())
                .any(|bytes|bytes==w.actors[slot].vehicle_kind().descriptor()));
            let mut enter=vec![0x0a];enter.extend(vehicle_id(slot).unwrap().to_le_bytes());enter.push(vehicle_alias(slot).unwrap());
            assert_eq!(raw.windows(enter.len()).filter(|bytes|*bytes==enter).count(),1);
            let create=create_vehicle(&w,slot).unwrap();assert!(create.len()<500);
        }
        assert_eq!(parts[0][39],2); // slot5's own native team, not slot0's.
        assert!(announcement(&w,5).is_err());
        let changed=roster_updates(&w,4).unwrap();assert_eq!(&changed[..2],&[19,88]);assert_eq!(changed[3],11);
        assert_eq!(&changed[5..9],&[128,2,b'(',b'J']);
        assert_eq!(&changed[9..13],&vehicle_id(4).unwrap().to_le_bytes());
        let visible=publication(&w,[true;model::MAX_ACTORS]).unwrap();
        assert!(visible.len()<=500);for slot in 0..6 {
            let mut position=vec![0x15];position.extend(vehicle_id(slot).unwrap().to_le_bytes());
            assert_eq!(visible.windows(position.len()).filter(|bytes|*bytes==position).count(),1);
        }
        assert!(publication(&w,[true;2]).is_err());
    }
    #[test] fn six_native_requests_and_last_actor_shot_ids_are_bounded() {
        let now=Instant::now();let w=six_mixed(now);
        let mut requests=Vec::new();for slot in 0..6 {requests.extend([8,4,0]);requests.extend(vehicle_id(slot).unwrap().to_le_bytes());}
        assert_eq!(entity_requests(&requests).unwrap(),Some((0..6).collect()));
        let mut duplicate=requests.clone();duplicate.extend(&requests[..7]);assert!(entity_requests(&duplicate).is_err());
        let mut p=Projectile::launch(model::MAX_BATTLE_SHOTS as u32,5,&w.actors[5],now).unwrap();
        assert_eq!(&tracer_start(&p).unwrap()[2..6],&vehicle_id(5).unwrap().to_le_bytes());
        p.stopped=true;assert!(tracer_stop(&p).is_ok());p.sequence+=1;
        assert!(tracer_start(&p).is_err());assert!(tracer_stop(&p).is_err());
    }
    #[test] fn six_actor_and_full_area_catalog_namespaces_never_overlap() {
        use super::super::destructible_wire as areas;
        let mut ids=std::collections::BTreeSet::new();let mut aliases=std::collections::BTreeSet::new();
        for slot in 0..model::MAX_ACTORS {
            assert!(ids.insert(vehicle_id(slot).unwrap()));assert!(ids.insert(avatar_id(slot).unwrap()));
            assert!(aliases.insert(vehicle_alias(slot).unwrap()));
        }
        for area in 0..144 {
            assert!(ids.insert(areas::area_id(area).unwrap()));
            let announcement=areas::area_announcement(area).unwrap();
            assert!(aliases.insert(*announcement.last().unwrap()));
        }
        assert_eq!(ids.len(),156);assert_eq!(aliases.len(),150);
        assert_eq!(vehicle_id(0).unwrap(),0x09100003);assert_eq!(vehicle_id(1).unwrap(),0x09100005);
        assert_eq!(vehicle_id(2).unwrap(),0x09110003);assert_eq!(vehicle_alias(5).unwrap(),243);
    }
    #[test] fn world_map_controls_native_base_and_geometry_without_changing_battle_binding() {
        use crate::map_profile091::MapId;
        let now = Instant::now();
        let mut w = model::tests::world(now);
        assert_eq!(w.map, MapId::Karelia);
        for own in 0..model::CAPACITY {
            w.map = MapId::Karelia;
            let old_binding = binding(&w, own, now).unwrap();
            let old_vehicle = create_vehicle(&w, own).unwrap();
            let old_announcement = announcement(&w, own).unwrap();
            for (map, arena_bytes, geometry) in [
                (MapId::Karelia, [1, 0, 0, 0], b"spaces/01_karelia".as_slice()),
                (MapId::Prohorovka, [4, 0, 0, 0], b"spaces/05_prohorovka".as_slice()),
            ] {
                w.map = map;
                let base = reset(&w, own).unwrap();
                assert_eq!(&base[..5], &[0x13, 0x3b, 4, 0, 5]);
                let name_len = base[13] as usize;
                assert_eq!(name_len, w.actors[own].identity.name.len());
                let arena_at = 14 + name_len + 8;
                assert_eq!(&base[arena_at..arena_at + 4], &arena_bytes);
                let entry = announcement(&w, own).unwrap();
                // createCellPlayer is a complete VAR2 message. Its direction,
                // position, space and vehicle binding must survive map selection.
                let space_at = 3 + u16::from_le_bytes([entry[1], entry[2]]) as usize;
                assert_eq!(space_at, 46);
                assert_eq!(&entry[..space_at], &old_announcement[..space_at]);
                assert_eq!(entry[space_at], 7);
                let space_end = space_at + 3 +
                    u16::from_le_bytes([entry[space_at + 1], entry[space_at + 2]]) as usize;
                assert_eq!(&entry[space_at + 81..space_end], geometry);
                assert_eq!(binding(&w, own, now).unwrap(), old_binding);
                assert_eq!(create_vehicle(&w, own).unwrap(), old_vehicle);
            }
        }
    }
    #[test] fn aiming_routes_validate_complete_fixed_args_and_owned_vehicle() {
        for own in 0..2 {
            for id in [0x8f,0x0f] {
                let mut p=Vec::new();if id==0x0f {p.extend(vehicle_id(own).unwrap().to_le_bytes());}
                f3(&mut p,[20.,30.,100.]);let b=var16(id,&p).unwrap();
                assert_eq!(aim_intent(&b,own).unwrap(),Some(aim::Intent::Point([20.,30.,100.])));
                for n in 1..b.len() {assert!(aim_intent(&b[..n],own).is_err());}
                let mut extra=b.clone();extra.push(0);assert!(aim_intent(&extra,own).is_err());
                if id==0x0f {assert!(aim_intent(&b,1-own).is_err());}
                for v in [f32::NAN,f32::INFINITY,1_000_001.] {
                    let mut bad=b.clone();let at=if id==0x0f{7}else{3};bad[at..at+4].copy_from_slice(&v.to_le_bytes());
                    assert!(aim_intent(&bad,own).is_err());
                }
            }
        }
        assert_eq!(aim_intent(&[0x88,0,0],0).unwrap(),None);
        let mut hold=vec![0x8e,8,0];hold.extend(1f32.to_le_bytes());hold.extend(0f32.to_le_bytes());
        assert_eq!(aim_intent(&hold,0).unwrap(),Some(aim::Intent::Hold{yaw:1.,pitch:0.}));
    }
    #[test] fn current_angles_seed_rejoins_and_only_known_entities_receive_properties() {
        let mut w=model::tests::world(Instant::now());
        w.actors[1].aim.yaw=-std::f32::consts::PI/2.;w.actors[1].aim.pitch=aim::MIN_PITCH;
        assert_eq!(&create_vehicle(&w,1).unwrap()[40..42],&0x4000u16.to_le_bytes());
        let b=publication(&w,[false,true]).unwrap();
        assert_eq!(&b[31..],&[18,5,0,16,9,160,0,64,19]);
        assert_eq!(publication(&w,[false,false]).unwrap(),[13,232]);
        let b=binding(&w,1,Instant::now()).unwrap();
        assert_eq!(&b[b.len()-92..b.len()-90],&[19,75]);
        assert_eq!(&b[b.len()-90..b.len()-86],&w.actors[1].aim.yaw.to_le_bytes());
        assert_eq!(&b[b.len()-86..b.len()-82],&aim::MIN_PITCH.to_le_bytes());
    }
    #[test] fn both_native_creations_encode_neutral_gun_angles_not_the_zero_sentinel() {
        let w = model::tests::world(Instant::now());
        for slot in 0..2 {
            let b = create_vehicle(&w, slot).unwrap();
            // Measured indexed Vehicle UINT16 property 2, following the two
            // boolean properties. Independent #717 decoder, not an encoder round trip.
            assert_eq!(&b[34..42], &[8, 0, 0, 1, 1, 2, 0x30, 0x80]);
            let packed = u16::from_le_bytes([b[40], b[41]]);
            let yaw = (packed >> 6) as f64 * 360. / 1024. - 180.;
            let pitch = -25. + (packed & 63) as f64 * 33. / 63.;
            assert_eq!(yaw, 0.);
            assert!(pitch.abs() < 0.27); // Half of the actual 33/63 degree pitch bin.
        }
    }
    #[test] fn shot_selects_the_shooter_then_restores_avatar_selection() {
        // Independent pinned PE/def contract: FIXED4 selectEntity=18,
        // Vehicle first ClientMethod=59, UINT8 single-shot burst, selectPlayer=19.
        assert_eq!(shooting(0).unwrap(), [18,3,0,16,9,59,1,19]);
        assert_eq!(shooting(1).unwrap(), [18,5,0,16,9,59,1,19]);
        assert_eq!(shooting(5).unwrap(),[18,9,0,17,9,59,1,19]);
        assert!(shooting(model::MAX_ACTORS).is_err());
    }
    #[test] fn identities_are_distinct_and_requests_cannot_select_an_unannounced_id() {
        assert_eq!(vehicle_id(0).unwrap(), 0x09100003); assert_eq!(vehicle_id(1).unwrap(), 0x09100005);
        assert_eq!(avatar_id(1).unwrap(), 0x09100004); assert!(vehicle_id(model::MAX_ACTORS).is_err());
        let two = [8, 4, 0, 3, 0, 16, 9, 8, 4, 0, 5, 0, 16, 9];
        assert_eq!(entity_requests(&two).unwrap(), Some(vec![0, 1]));
        for n in [1, 3, 6, 8, 13] { assert!(entity_requests(&two[..n]).is_err()); }
        let mut bad = two; bad[10] = 15; assert!(entity_requests(&bad).is_err());
        let mut duplicate = two; duplicate[10] = 3; assert!(entity_requests(&duplicate).is_err());
    }
    #[test] fn ready_is_bound_to_each_players_own_vehicle() {
        let first = [0x0d,8,0,0,0,0,0,3,0,16,9,0x8d,5,0,2,1,0,0,0,0x86,0,0,0x0c,8,0,0,0,0,0,0,0,0,0];
        ready(&first, 0).unwrap(); assert!(ready(&first, 1).is_err());
        let mut second = first; second[7] = 5; ready(&second, 1).unwrap();
        assert!(ready(&second, 0).is_err());
    }
    #[test] fn native_fields_preserve_layout_with_distinct_ids_and_utf8_names() {
        let now = Instant::now(); let mut w = model::tests::world(now);
        w.actors[1].identity.name = "Танкист_Ёж_e91322".into();
        let first = create_vehicle(&w, 0).unwrap(); let second = create_vehicle(&w, 1).unwrap();
        assert_eq!(&first[..10], &[9, 87, 0, 0, 3, 0, 16, 9, 2, 0]);
        assert_eq!(&second[4..8], &0x09100005u32.to_le_bytes());
        assert_eq!(&second[10..14], &w.actors[1].position[0].to_le_bytes());
        assert!(roster(&w).unwrap().len() < 255);
        assert!(announcement(&w, 0).unwrap().len() < 500);
        let b = binding(&w, 1, now).unwrap();
        assert!(b.windows(13).any(|s| s == [vec![0x14],0x09100004u32.to_le_bytes().to_vec(),1u32.to_le_bytes().to_vec(),0x09100005u32.to_le_bytes().to_vec()].concat()));
        assert_eq!(publication(&w, [true, true]).unwrap().len(), 78);
        assert_eq!(publication(&w, [true, false]).unwrap().len(), 40);
    }
    #[test] fn tracer_callbacks_preserve_pinned_fixed_native_layout() {
        let now = Instant::now();
        let mut w = model::tests::world(now);
        w.apply(0, 1, &[model::Command::Fire(crate::battle091::fire::Command::Shoot)], now).unwrap();
        let start = tracer_start(&w.projectiles[0]).unwrap();
        assert_eq!(start.len(), 43);
        assert_eq!(&start[..2], &[0x13, 0x4c]);
        assert_eq!(&start[2..6], &vehicle_id(0).unwrap().to_le_bytes());
        assert_eq!(&start[6..10], &1u32.to_le_bytes());
        assert_eq!(start[10], 2);
        assert!(tracer_stop(&w.projectiles[0]).is_err());
        let end = w.projectiles[0].end_at().unwrap();
        w.advance(end + std::time::Duration::from_millis(100)).unwrap();
        let stop = tracer_stop(&w.projectiles[0]).unwrap();
        assert_eq!(stop.len(), 18);
        assert_eq!(&stop[..2], &[0x13, 0x48]);
        assert_eq!(&stop[2..6], &1u32.to_le_bytes());
    }
    #[test] fn stopped_projectile_preserves_launch_bytes_for_delayed_receiver() {
        let now = Instant::now();
        let mut w = model::tests::world(now);
        w.apply(0, 1, &[model::Command::Fire(crate::battle091::fire::Command::Shoot)], now).unwrap();
        let mut projectile = w.projectiles[0];
        let launch_bytes = tracer_start(&projectile).unwrap();
        assert!(tracer_stop(&projectile).is_err());
        // A collision can stop the flight before a peer's next publication.
        projectile.terminal = [14.0, 25.0, 36.0];
        projectile.stopped = true;
        let mut delayed = tracer_start(&projectile).unwrap();
        assert_eq!(delayed, launch_bytes);
        delayed.extend(tracer_stop(&projectile).unwrap());
        assert_eq!(delayed.len(), 43 + 18);
        assert_eq!(&delayed[43..49], &[0x13, 0x48, 1, 0, 0, 0]);
        for (index, expected) in projectile.terminal.iter().enumerate() {
            let offset = 49 + index * 4;
            assert_eq!(f32::from_le_bytes(delayed[offset..offset + 4].try_into().unwrap()), *expected);
        }
    }
    #[test] fn tracer_callbacks_keep_identity_finite_and_positive_value_guards_after_stop() {
        let now = Instant::now();
        let w = model::tests::world(now);
        let base = Projectile::launch(1, 0, &w.actors[0], now).unwrap();
        let corruptions: [fn(&mut Projectile); 11] = [
            |p| p.sequence = 0,
            |p| p.sequence = model::MAX_BATTLE_SHOTS as u32 + 1,
            |p| p.slot = model::MAX_ACTORS,
            |p| p.origin[0] = f32::NAN,
            |p| p.velocity[2] = f32::INFINITY,
            |p| p.gravity = f32::NAN,
            |p| p.gravity = 0.0,
            |p| p.gravity = -1.0,
            |p| p.max_distance = f32::INFINITY,
            |p| p.max_distance = 0.0,
            |p| p.max_distance = -1.0,
        ];
        for stopped in [false, true] {
            for corrupt in corruptions {
                let mut projectile = base;
                projectile.stopped = stopped;
                corrupt(&mut projectile);
                assert!(tracer_start(&projectile).is_err());
            }
        }
        let mut projectile = base;
        projectile.stopped = true;
        projectile.terminal[1] = f32::NAN;
        assert!(tracer_stop(&projectile).is_err());
    }
}
