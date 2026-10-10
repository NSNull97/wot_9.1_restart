//! Parameterized #717 layouts, kept separate from the frozen primary-profile
//! probes. Only two server-assigned allied MS-1s can enter these encoders.
use std::io;
use super::{model::{self, Actor, World}, projectile::Projectile};
use super::aim;
use crate::{arena091 as arena, arena_vehicle091 as vehicle, battle091::native_ammo as ammo};

pub const SPACE: u32 = 1;
/// Original #717 gun_rotation_shared: 10 biased yaw bits, 6 restricted pitch.
/// Keep this serializer at the wire boundary, not in the aiming simulation.
pub fn packed_angles(state: &aim::State) -> io::Result<u16> {
    if !state.yaw.is_finite() || !state.pitch.is_finite() || state.yaw.abs() > std::f32::consts::PI
        || !(aim::MIN_PITCH..=aim::MAX_PITCH).contains(&state.pitch) { return Err(model::bad()); }
    let yaw = ((state.yaw as f64 + std::f64::consts::PI) * 1024. / (2. * std::f64::consts::PI)).round() as u16 & 1023;
    let pitch = ((state.pitch as f64 - aim::MIN_PITCH as f64) * 63. / (aim::MAX_PITCH as f64 - aim::MIN_PITCH as f64)).round() as u16;
    Ok((yaw << 6) | pitch)
}
pub fn aim_intent(raw: &[u8], own: usize) -> io::Result<Option<aim::Intent>> {
    let id = *raw.first().ok_or_else(model::bad)?;
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
    if slot >= model::CAPACITY { return Err(model::bad()); }
    Ok(vehicle::VEHICLE_ENTITY_ID + 2 * slot as u32)
}
pub fn avatar_id(slot: usize) -> io::Result<u32> { Ok(vehicle_id(slot)? - 1) }
pub fn slot_for_vehicle(id: u32) -> io::Result<usize> {
    (0..model::CAPACITY).find(|slot| vehicle_id(*slot).ok() == Some(id)).ok_or_else(model::bad)
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
    let a = w.actors.get(slot).ok_or_else(model::bad)?;
    if w.id == 0 || a.identity.database <= 0 || a.identity.name.len() > 48
        || a.position.iter().any(|x| !x.is_finite() || x.abs() > 2000.)
        || a.direction.iter().any(|x| !x.is_finite() || x.abs() > std::f32::consts::PI)
        || a.direction[0] != a.yaw { return Err(model::bad()); }
    Ok(a)
}
pub fn reset(w: &World, slot: usize) -> io::Result<Vec<u8>> {
    let a = actor(w, slot)?;
    let mut b = vec![0x13, 0x3b]; // Account.onArenaCreated
    b.extend(arena::reset_to_avatar_base(&arena::AvatarBaseSeed { entity_id: avatar_id(slot)?,
        name: &a.identity.name, arena_unique_id: w.id })?); Ok(b)
}
pub fn roster(w: &World) -> io::Result<Vec<u8>> {
    if w.actors.len() != model::CAPACITY { return Err(model::bad()); }
    // Own bounded literal protocol2 data; never an input object decoder.
    let mut d = vec![0x80, 2, b']'];
    for slot in 0..model::CAPACITY {
        let a = actor(w, slot)?;
        d.extend([b'(', b'J']); d.extend(vehicle_id(slot)?.to_le_bytes());
        d.push(b'U'); string(&mut d, &vehicle::MS1_DESCRIPTOR)?;
        d.push(b'U'); string(&mut d, a.identity.name.as_bytes())?;
        d.extend([b'K', 1, 0x88, if a.ready { 0x88 } else { 0x89 }, 0x89, b'J']);
        d.extend(a.identity.database.to_le_bytes());
        d.extend([b'U', 0, b'K', 0, b'K', 0, 0x89, b'}', b'K', 0, b't', b'a']);
    }
    d.push(b'.'); update(1, &d)
}
fn update(kind: u8, d: &[u8]) -> io::Result<Vec<u8>> {
    if d.len() > 252 { return Err(model::bad()); }
    let mut b = vec![0x13, 0x58, (d.len() + 2) as u8, kind, d.len() as u8]; b.extend(d); Ok(b)
}
pub fn announcement(w: &World, own: usize) -> io::Result<Vec<u8>> {
    let a = actor(w, own)?;
    let mut b = arena::create_cell_avatar(&arena::AvatarCellSeed { space_id: SPACE,
        player_vehicle_id: vehicle_id(own)?, position: a.position })?;
    // Native createCellPlayer's direction stream is roll/pitch/yaw, while
    // the domain/worker stores yaw/pitch/roll.
    for (i, value) in [a.direction[2], a.direction[1], a.direction[0]].into_iter().enumerate() {
        b[27 + i * 4..31 + i * 4].copy_from_slice(&value.to_le_bytes());
    }
    b.extend(arena::karelia_space_data(SPACE, (SPACE as u64).to_le_bytes())?);
    b.extend(roster(w)?);
    for slot in 0..model::CAPACITY {
        b.push(0x0a); b.extend(vehicle_id(slot)?.to_le_bytes()); b.push(slot as u8);
    }
    if b.len() > 500 { return Err(model::bad()); } Ok(b)
}
pub fn create_vehicle(w: &World, slot: usize) -> io::Result<Vec<u8>> {
    let a = actor(w, slot)?;
    let mut p = vec![0]; p.extend(vehicle_id(slot)?.to_le_bytes()); p.extend(2u16.to_le_bytes());
    f3(&mut p, a.position); f3(&mut p, a.direction);
    p.extend([8, 0, 0, 1, 1, 2]); p.extend(packed_angles(&a.aim)?.to_le_bytes());
    p.push(3); p.extend(90i16.to_le_bytes()); p.extend([4, 0, 0, 5]);
    string(&mut p, a.identity.name.as_bytes())?; string(&mut p, &vehicle::MS1_DESCRIPTOR)?;
    p.push(1); p.extend(0i32.to_le_bytes()); p.push(0);
    p.push(6); p.extend(0i32.to_le_bytes()); p.push(7); p.extend(0i32.to_le_bytes());
    var16(9, &p)
}
pub fn entity_requests(b: &[u8]) -> io::Result<Option<Vec<usize>>> {
    if b.first() != Some(&8) { return Ok(None); }
    if b.is_empty() || b.len() > 14 || b.len() % 7 != 0 { return Err(model::bad()); }
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
pub fn ready_update(slot: usize) -> io::Result<Vec<u8>> {
    let mut d = vec![0x80, 2, b'J']; d.extend(vehicle_id(slot)?.to_le_bytes()); d.push(b'.'); update(7, &d)
}
pub fn reload(slot: usize, time_left: f32) -> io::Result<Vec<u8>> {
    if !time_left.is_finite() || !(0. ..=ammo::MS1_RELOAD_SECONDS).contains(&time_left) { return Err(model::bad()); }
    let mut b = vec![0x13, 0x46]; b.extend(vehicle_id(slot)?.to_le_bytes());
    b.extend(time_left.to_le_bytes()); b.extend(ammo::MS1_RELOAD_SECONDS.to_le_bytes()); Ok(b)
}
pub fn ammo_count(count: u16) -> io::Result<Vec<u8>> {
    if count > ammo::MS1_SHELL_COUNT { return Err(model::bad()); }
    let mut b = vec![0x13, 0x44]; b.extend(ammo::MS1_SHELL.to_le_bytes()); b.extend(count.to_le_bytes());
    b.extend([0, 0, 0]); Ok(b)
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
/// geometry and effective shell values.
pub fn tracer_start(projectile: &Projectile) -> io::Result<Vec<u8>> {
    if projectile.sequence == 0 || projectile.sequence as usize > model::MAX_SHOTS
        || projectile.slot >= model::CAPACITY || projectile.stopped
        || !projectile.origin.iter().all(|v| v.is_finite())
        || !projectile.velocity.iter().all(|v| v.is_finite())
        || !projectile.gravity.is_finite() || projectile.gravity <= 0.0
        || !projectile.max_distance.is_finite() || projectile.max_distance <= 0.0
    { return Err(model::bad()); }
    let mut b = vec![0x13, 0x4c];
    b.extend(vehicle_id(projectile.slot)?.to_le_bytes());
    b.extend(projectile.sequence.to_le_bytes());
    // `smallArmorPiercing` is ordered index 2 in the pinned #717
    // common/shot_effects.xml enumeration.
    b.push(2);
    f3(&mut b, projectile.origin);
    f3(&mut b, projectile.velocity);
    b.extend(projectile.gravity.to_le_bytes());
    b.extend(projectile.max_distance.to_le_bytes());
    if b.len() != 43 { return Err(model::bad()); }
    Ok(b)
}

/// Original Avatar.stopTracer fixed method. It is emitted once per tracer
/// start, and only after the server-owned radial flight deadline.
pub fn tracer_stop(projectile: &Projectile) -> io::Result<Vec<u8>> {
    if projectile.sequence == 0 || projectile.sequence as usize > model::MAX_SHOTS
        || projectile.slot >= model::CAPACITY || !projectile.stopped
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
    for slot in 0..model::CAPACITY { if slot == own || w.actors[slot].ready { b.extend(ready_update(slot)?); } }
    let mut period = vec![0x80, 2, b'(', b'K', 3, b'G']; period.extend(3700f64.to_be_bytes());
    period.push(b'G'); period.extend(3600f64.to_be_bytes()); period.extend(b"Nt."); b.extend(update(3, &period)?);
    b.push(0x14); b.extend(avatar_id(own)?.to_le_bytes()); b.extend(SPACE.to_le_bytes()); b.extend(vehicle_id(own)?.to_le_bytes());
    for _ in 0..6 { b.extend(0f32.to_le_bytes()); }
    b.extend([0x13, 0x4a]); f3(&mut b, a.position); f3(&mut b, a.direction);
    b.extend(a.speed.to_le_bytes()); b.extend(0f32.to_le_bytes());
    // Native Avatar.updateTargetingInfo starts the original gun rotator and
    // its original target-input path. Nominal resource parameters, no crew
    // modifier claim; conversions mirror the original resource readers.
    b.extend([0x13, 0x4b]);
    for value in [a.aim.yaw, a.aim.pitch, aim::YAW_RATE, aim::PITCH_RATE, 1.,
        0.16 / 1f32.to_radians(), 0.42 * 3.6, 0.42 / 1f32.to_radians(), 2.5] {
        b.extend(value.to_le_bytes());
    }
    for (descriptor, original_count) in ammo::MS1_PANEL_ROWS {
        b.extend([0x13, 0x44]); b.extend(descriptor.to_le_bytes());
        b.extend((if descriptor == ammo::MS1_SHELL { a.fire.ammo() } else { original_count }).to_le_bytes());
        b.extend([0, 0, 0]);
    }
    b.extend([0x13, 0x40, 0]); b.extend(ammo::MS1_SHELL.to_le_bytes());
    let left = a.fire.reload_until().map(|end| end.saturating_duration_since(now).as_secs_f32()).unwrap_or(0.);
    b.extend(reload(own, left.min(ammo::MS1_RELOAD_SECONDS))?); Ok(b)
}
pub fn publication(w: &World, visible: [bool; 2]) -> io::Result<Vec<u8>> {
    if !(1000..=37000).contains(&w.tick) { return Err(model::bad()); }
    let mut b = vec![0x0d, w.tick as u8];
    for (slot, known) in visible.into_iter().enumerate() {
        if !known { continue; }
        let a = actor(w, slot)?;
        b.push(0x15); b.extend(vehicle_id(slot)?.to_le_bytes()); f3(&mut b, a.position);
        native_direction(&mut b, a.direction);
        // Pinned #717 dynamic entityProperty base 0x9e + indexed property 2.
        // UINT16 is fixed2. Restore Avatar selection after each vehicle.
        b.push(0x12); b.extend(vehicle_id(slot)?.to_le_bytes());
        b.push(0xa0); b.extend(packed_angles(&a.aim)?.to_le_bytes()); b.push(0x13);
    }
    Ok(b)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Instant;
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
        assert!(shooting(2).is_err());
    }
    #[test] fn identities_are_distinct_and_requests_cannot_select_an_unannounced_id() {
        assert_eq!(vehicle_id(0).unwrap(), 0x09100003); assert_eq!(vehicle_id(1).unwrap(), 0x09100005);
        assert_eq!(avatar_id(1).unwrap(), 0x09100004); assert!(vehicle_id(2).is_err());
        let two = [8, 4, 0, 3, 0, 16, 9, 8, 4, 0, 5, 0, 16, 9];
        assert_eq!(entity_requests(&two).unwrap(), Some(vec![0, 1]));
        for n in [1, 3, 6, 8, 13] { assert!(entity_requests(&two[..n]).is_err()); }
        let mut bad = two; bad[10] = 7; assert!(entity_requests(&bad).is_err());
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
    #[test] fn tracer_callbacks_reject_wrong_lifecycle_and_nonfinite_fields() {
        let now = Instant::now();
        let mut w = model::tests::world(now);
        w.apply(0, 1, &[model::Command::Fire(crate::battle091::fire::Command::Shoot)], now).unwrap();
        let mut projectile = w.projectiles[0];
        projectile.origin[0] = f32::NAN;
        assert!(tracer_start(&projectile).is_err());
        projectile = w.projectiles[0];
        projectile.stopped = true;
        assert!(tracer_start(&projectile).is_err());
        assert!(tracer_stop(&projectile).is_ok());
    }
}
