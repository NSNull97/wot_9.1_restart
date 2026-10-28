//! SPAWN-15 native layout for 2/6/15/30 vehicles: own encoder only. These
//! tests prove namespace uniqueness, bounded records and byte identity of the
//! six-vehicle path; they do not prove that the native client shows 30 tanks.
use super::*;
use super::wire::*;
use super::vehicle_profile::VehicleKind;
use super::{destructible_wire as areas, detached_turret as turrets};
use std::{collections::BTreeSet, time::Instant};

fn roster(n: usize, now: Instant) -> World {
    let mut w = World::new_for_roster(321, now, crate::map_profile091::MapId::Prohorovka, n).unwrap();
    w.enable_lifecycle(super::lifecycle::Rules::prohorovka()).unwrap();
    for slot in 0..n {
        let kind = if slot % 2 == 0 { VehicleKind::Ms1 } else { VehicleKind::Is7 };
        // Longest owned names: the worst case for roster records.
        let (mut owner, frozen) = model::tests::profile13_loadout(kind, slot, kind.ammo_limit()); owner.name = "Я".repeat(24);
        w.attach_owned(owner, slot as u32 + 7, &frozen).unwrap();
    }
    w.start(now).unwrap(); w
}

#[test]
fn spawn15_thirty_vehicle_ids_and_aliases_never_overlap_areas_or_turrets() {
    let mut ids = BTreeSet::new(); let mut aliases = BTreeSet::new();
    for slot in 0..MAX_WIRE_ACTORS {
        assert!(ids.insert(vehicle_id(slot).unwrap()) && ids.insert(avatar_id(slot).unwrap()));
        assert!(ids.insert(turrets::entity_id(slot).unwrap()));
        assert!(aliases.insert(vehicle_alias(slot).unwrap()) && aliases.insert(turrets::alias(slot).unwrap()));
        assert_eq!(slot_for_vehicle(vehicle_id(slot).unwrap()).unwrap(), slot);
    }
    for area in 0..areas::MAX_AREAS {
        assert!(ids.insert(areas::area_id(area).unwrap()));
        assert!(aliases.insert(*areas::area_announcement(area).unwrap().last().unwrap()));
    }
    assert_eq!(ids.len(), 3 * 30 + 144); assert_eq!(aliases.len(), 2 * 30 + 144);
    assert!(!aliases.contains(&255));
    // The accepted six-vehicle bytes are unchanged.
    assert_eq!((0..6).map(|s| vehicle_alias(s).unwrap()).collect::<Vec<_>>(), [0, 1, 240, 241, 242, 243]);
    assert_eq!((0..6).map(|s| turrets::alias(s).unwrap()).collect::<Vec<_>>(), [248, 249, 250, 251, 252, 253]);
    assert_eq!(vehicle_id(5).unwrap(), 0x0911_0009); assert_eq!(vehicle_alias(6).unwrap(), 146);
    assert_eq!(vehicle_alias(29).unwrap(), 169); assert_eq!(turrets::alias(6).unwrap(), 170); assert_eq!(turrets::alias(29).unwrap(), 193);
    assert_eq!(vehicle_id(29).unwrap(), 0x0911_0039);
    assert!(vehicle_id(MAX_WIRE_ACTORS).is_err() && vehicle_alias(MAX_WIRE_ACTORS).is_err() && turrets::alias(MAX_WIRE_ACTORS).is_err());
}

#[test]
fn spawn15_roster_announcement_for_2_6_15_30_is_complete_bounded_and_split_by_record() {
    let now = Instant::now();
    for n in [2usize, 6, 15, 30] {
        let w = roster(n, now);
        let team1 = (0..n).filter(|s| w.team(*s).unwrap() == 1).count();
        assert_eq!((team1, n - team1), (n.div_ceil(2), n / 2));
        for own in [0, n - 1] {
            let mut desired = [false; model::MAX_ACTORS]; for want in desired.iter_mut().take(n) { *want = true; }
            let parts = announcement_parts_for(&w, own, desired).unwrap();
            assert!(parts.iter().all(|p| !p.body.is_empty() && p.body.len() <= 500));
            let raw = parts.iter().map(|p| p.body.clone()).collect::<Vec<_>>().concat();
            let mut kinds = Vec::new();
            for at in 0..raw.len().saturating_sub(5) {
                if raw[at..at + 2] == [0x13, 0x58] {
                    let len = raw[at + 4] as usize; assert_eq!(raw[at + 2] as usize, len + 2); assert!(len <= 252);
                    kinds.push(raw[at + 3]);
                }
            }
            assert_eq!(kinds.len(), n); assert_eq!(kinds[0], 1); assert!(kinds[1..].iter().all(|k| *k == 2));
            assert_eq!(parts.iter().flat_map(|p| p.enters.clone()).collect::<Vec<_>>(), (0..n).collect::<Vec<_>>());
            for slot in 0..n {
                let enter = enter_vehicle(slot).unwrap();
                assert_eq!(raw.windows(enter.len()).filter(|b| *b == enter).count(), 1);
                assert!(create_vehicle(&w, slot).unwrap().len() < 500);
            }
        }
        let mut requests = Vec::new(); for slot in 0..n { requests.extend([8, 4, 0]); requests.extend(vehicle_id(slot).unwrap().to_le_bytes()); }
        assert_eq!(entity_requests(&requests).unwrap(), Some((0..n).collect()));
    }
}

#[test]
fn spawn15_position_publication_splits_above_thirteen_and_keeps_one_body_below() {
    let now = Instant::now();
    for n in [2usize, 6, 13, 14, 15, 30] {
        let w = roster(n, now);
        let mut visible = [false; model::MAX_ACTORS]; for want in visible.iter_mut().take(n) { *want = true; }
        let whole = publication(&w, visible).unwrap(); let parts = publication_parts(&w, visible).unwrap();
        assert_eq!(parts.len(), n.div_ceil(13));
        if n <= 13 { assert_eq!(parts, vec![whole.clone()]); }
        assert!(parts.iter().all(|p| p.len() <= 500 && p[..2] == whole[..2]));
        assert_eq!(parts.iter().flat_map(|p| p[2..].to_vec()).collect::<Vec<_>>(), whole[2..].to_vec());
        for slot in 0..n {
            let mut position = vec![0x15]; position.extend(vehicle_id(slot).unwrap().to_le_bytes());
            assert_eq!(parts.iter().map(|p| p.windows(5).filter(|b| *b == position).count()).sum::<usize>(), 1);
        }
    }
}

#[test]
fn spawn15_binding_with_29_ready_peers_stays_one_bounded_body_and_defers_the_rest() {
    let now = Instant::now();
    for n in [6usize, 15, 30] {
        let mut w = roster(n, now);
        for slot in 0..n - 1 { w.set_ready(slot, slot as u32 + 7).unwrap(); }
        for own in [0, n - 1] {
            let body = binding(&w, own, now).unwrap();
            assert!(body.len() <= 512, "n={n} own={own} len={}", body.len());
            for slot in 0..n {
                let ready = ready_update(slot).unwrap();
                let inside = body.windows(ready.len()).any(|b| b == ready);
                assert_eq!(inside, binding_ready(&w, own, slot));
                assert_eq!(inside, slot == own || slot < MAX_NATIVE_ACTORS && w.actors[slot].ready);
            }
        }
    }
}
