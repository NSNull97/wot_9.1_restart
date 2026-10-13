//! Session/codec regression checks only. Source-bound model fixtures are used,
//! but synthetic direct State contacts below do not prove native rendering or
//! World/Trace collision acceptance. Those have separate integration gates.
use super::*;
use super::tests::{driving, frame, queued_bodies, visible_pair};
use super::super::{destructible_wire as area_wire, terrain};

fn request(id: u32) -> Vec<u8> {
    let mut bytes = vec![8, 4, 0]; bytes.extend(id.to_le_bytes()); bytes
}

fn point(slot: usize, p: [f32; 3]) -> Vec<u8> {
    let mut bytes = vec![0x8f, 12, 0];
    for value in p { bytes.extend(value.to_le_bytes()); }
    assert_eq!(slot, 0); // this fixture deliberately uses the first owned vehicle
    bytes
}

fn ready(slot: usize) -> Vec<u8> {
    let mut bytes = vec![0x0d, 8, 0, 0, 0, 0, 0];
    bytes.extend(wire::vehicle_id(slot).unwrap().to_le_bytes());
    bytes.extend([0x8d, 5, 0, 2, 1, 0, 0, 0, 0x86, 0, 0]);
    bytes.extend([0x0c, 8, 0, 0, 0, 0, 0, 0, 0, 0, 0]);
    bytes
}

fn present(bodies: &[Vec<u8>], expected: &[u8]) -> usize {
    bodies.iter().map(|body| body.windows(expected.len()).filter(|bytes| *bytes == expected).count()).sum()
}

fn prepare_client(s: &mut Session, world: &World) {
    let c = s.shared.as_mut().unwrap();
    c.view = Some(world.clone());
    c.announced_areas = world.fragiles.as_ref().unwrap().catalog.chunks().len();
    c.shot_cursor = world.latest_shot();
    c.areas = world.fragiles.as_ref().unwrap().catalog.chunks().iter().enumerate()
        .map(|(i, _)| (Some((10 + i as u32, true)), Vec::new())).collect();
}

fn pair(now: Instant) -> (Session, Session, World) {
    let (mut a, mut b, _) = visible_pair(now);
    let world = model::tests::fragile_world(now, None);
    prepare_client(&mut a, &world); prepare_client(&mut b, &world);
    (a, b, world)
}

fn entities(now: Instant, world: &World) -> Session {
    let (mut s, _) = driving(now);
    let c = s.shared.as_mut().unwrap();
    c.phase = Phase::Entities; c.announcement = Some((0, true));
    c.creations = [None; 2]; c.view = Some(world.clone());
    c.areas = vec![(None, Vec::new()); world.fragiles.as_ref().unwrap().catalog.chunks().len()];
    c.announced_areas = c.areas.len();
    s
}

fn direct_contact(world: &mut World, instance: u32, shot: u32) {
    let state = world.fragiles.as_mut().unwrap();
    let object = state.catalog.instance(instance).unwrap().clone();
    let contact = terrain::Hit {
        triangle_id: object.projectile_first_triangle, t: 0.5,
        point: [-402.0, 57.0, -404.0], normal: [0.0, 1.0, 0.0],
        surface: terrain::Surface::StaticObstacle { instance_id: instance, material_kind: object.material_kind },
    };
    state.contact(shot, 0, 1001, contact).unwrap().unwrap();
}

#[test]
fn native_catalog_announces_and_creates_both_chunks_with_vehicle_requests() {
    let now = Instant::now();
    let world = model::tests::fragile_world(now, None);
    let (mut s, _) = driving(now);
    {
        let c = s.shared.as_mut().unwrap(); c.phase = Phase::Enable;
        c.view = Some(world.clone()); c.creations = [None; 2]; c.announcement = None;
    }
    s.receive(&frame(&s, &[9]), now).unwrap();
    let c = s.shared.as_ref().unwrap();
    assert_eq!(c.phase, Phase::Entities);
    assert_eq!(c.areas, vec![(None, vec![]), (None, vec![])]);
    let announced = queued_bodies(&s, now);
    for i in 0..2 { assert_eq!(present(&announced, &area_wire::area_announcement(i).unwrap()), 1); }
    let (sequence, _) = c.announcement.unwrap();
    let ack = frame(&s, &[]);
    s.shared.as_mut().unwrap().acknowledge(sequence + 1, &ack);

    let mut payload = Vec::new();
    for id in [area_wire::area_id(1).unwrap(), wire::vehicle_id(0).unwrap(),
        area_wire::area_id(0).unwrap(), wire::vehicle_id(1).unwrap()] { payload.extend(request(id)); }
    s.receive(&frame(&s, &payload), now).unwrap();
    let c = s.shared.as_ref().unwrap();
    assert!(c.creations.iter().all(Option::is_some));
    assert!(c.areas.iter().all(|(pending, ids)| pending.is_some_and(|(_, ack)| !ack) && ids.is_empty()));
    let created = queued_bodies(&s, now);
    for (i, chunk) in [31354, 31355].into_iter().enumerate() {
        let expected = area_wire::area_create(i, chunk, &[]).unwrap();
        assert_eq!(present(&created, &expected), 1);
    }
}

fn many_chunk_world(now: Instant) -> World {
    let mut world = model::tests::contact_world(now);
    let state = world.fragiles.as_ref().unwrap();
    let template = state.catalog.objects[0].clone();
    let objects = (0..117usize).map(|index| {
        let mut object = template.clone();
        object.object_id = 10_000 + index as u32;
        object.instance_id = 20_000 + index as u32;
        object.chunk_id = 31_000 + index as u16;
        object.native_index = 0;
        object.object_revision = format!("{:064x}", index + 1);
        object
    }).collect();
    let mut catalog = (*state.catalog).clone();
    catalog.objects = objects;
    world.fragiles = Some(super::super::fragiles::State::new(std::sync::Arc::new(catalog)));
    world
}

fn ack_current_and_flush(s: &mut Session, now: Instant) {
    while s.tx.due(now, s.rx).unwrap().is_some() {}
    let max_sequence = {
        let c = s.shared.as_ref().unwrap();
        c.announcement_parts.iter().map(|(sequence, _)| *sequence)
            .chain(c.creations.iter().flatten().map(|(sequence, _)| *sequence))
            .chain(c.areas.iter().filter_map(|(pending, _)| pending.map(|(sequence, _)| sequence)))
            .chain(c.area_creation.iter().map(|(sequence, _)| *sequence))
            .max()
    };
    let Some(max_sequence) = max_sequence else { return; };
    let cumulative = max_sequence + 1;
    let ack = Frame { flags: 0x408, sequence: None, cumulative: Some(cumulative), selective: Vec::new(), body: Vec::new(), piggybacks: Vec::new() };
    s.tx.acknowledge(&ack).unwrap();
    s.shared.as_mut().unwrap().acknowledge(cumulative, &ack);
    s.flush_shared_requests(&mut Vec::new()).unwrap();
}

#[test]
fn full_contact_catalog_stays_bounded_through_ready_phase_and_stages_all_117_area_creates() {
    let now = Instant::now();
    let world = many_chunk_world(now);
    let (mut s, _) = driving(now);
    s.shared.as_mut().unwrap().phase = Phase::Enable;
    s.shared.as_mut().unwrap().view = Some(world.clone());
    s.receive(&frame(&s, &[9]), now).unwrap();
    let c = s.shared.as_ref().unwrap();
    // The first native request must fit the measured eight-body reliable
    // window: two vehicles plus six area controllers. Later area batches are
    // published only after the current batch and its creates are ACKed.
    assert_eq!(c.announced_areas, 6);
    assert_eq!(c.announcement_parts.len(), 1);
    assert!(queued_bodies(&s, now).iter().all(|body| body.len() <= 512));

    let mut payload = Vec::new();
    payload.extend(request(wire::vehicle_id(0).unwrap()));
    payload.extend(request(wire::vehicle_id(1).unwrap()));
    for area in 0..6 { payload.extend(request(area_wire::area_id(area).unwrap())); }
    s.receive(&frame(&s, &payload), now).unwrap();
    assert!(s.tx.len() <= 8);
    // Five area creates fit beside the two vehicle creates and the first
    // announcement; the sixth request remains queued until an ACK frees one
    // reliable slot.
    assert!(s.shared.as_ref().unwrap().pending_area_requests.len() <= 1);

    let mut requested = 6usize;
    let mut ready_phase = false;
    for _ in 0..80 {
        ack_current_and_flush(&mut s, now);
        // A native client enters Driving after its own vehicle binding is
        // acknowledged, while the later area batches may still be pending.
        // Keep this transition in the synthetic wire regression so the
        // catalog cannot silently depend on Phase::Entities forever.
        if !ready_phase {
            s.shared.as_mut().unwrap().phase = Phase::Driving;
            ready_phase = true;
        }
        let announced = s.shared.as_ref().unwrap().announced_areas;
        if requested < announced {
            let mut batch = Vec::new();
            for area in requested..announced { batch.extend(request(area_wire::area_id(area).unwrap())); }
            s.receive(&frame(&s, &batch), now).unwrap();
            requested = announced;
        }
        if requested == 117
            && s.shared.as_ref().unwrap().pending_area_requests.is_empty()
            && s.shared.as_ref().unwrap().areas.iter().all(|(pending, _)| pending.is_some()) {
            break;
        }
    }
    let c = s.shared.as_ref().unwrap();
    assert!(c.pending_area_requests.is_empty());
    assert!(c.areas.iter().all(|(pending, _)| pending.is_some()));
    assert_eq!(c.areas.len(), 117);
    assert!(s.tx.len() <= 8);
}

#[test]
fn all_chunk_creation_acks_gate_commands_selective_ack_is_supported() {
    let now = Instant::now(); let (mut a, _, mut world) = pair(now);
    {
        let c = a.shared.as_mut().unwrap(); c.areas[0].0 = Some((10, false)); c.areas[1].0 = Some((11, false));
        c.commands.push(model::Command::Move(model::Input { throttle: 1, steer: 0 }));
    }
    let actors_before = world.actors.clone();
    poll(&mut a, &mut world, now).unwrap();
    assert_eq!(world.actors, actors_before);
    assert_eq!(a.shared.as_ref().unwrap().commands.len(), 1);
    let ack = frame(&a, &[]);
    a.shared.as_mut().unwrap().acknowledge(11, &ack);
    assert!(a.shared.as_ref().unwrap().areas[0].0.unwrap().1);
    assert!(!a.shared.as_ref().unwrap().areas[1].0.unwrap().1);
    poll(&mut a, &mut world, now).unwrap();
    assert_eq!(world.actors, actors_before);
    assert_eq!(a.shared.as_ref().unwrap().commands.len(), 1);
    let mut selective = frame(&a, &[]); selective.selective = vec![11];
    a.shared.as_mut().unwrap().acknowledge(11, &selective);
    poll(&mut a, &mut world, now).unwrap();
    assert!(a.shared.as_ref().unwrap().commands.is_empty());
    assert_eq!(world.actors[0].input.throttle, 1);
}

#[test]
fn cumulative_same_chunk_updates_are_once_per_peer_and_do_not_touch_neighbor_chunk() {
    let now = Instant::now(); let (mut a, mut b, mut world) = pair(now);
    direct_contact(&mut world, 1513, 1);
    let first = area_wire::area_update(0, &[1]).unwrap();
    let full = area_wire::area_update(0, &[0, 1]).unwrap();
    let other = area_wire::area_update(1, &[0]).unwrap();
    for s in [&mut a, &mut b] {
        poll(s, &mut world, now).unwrap();
        assert_eq!(s.shared.as_ref().unwrap().areas[0].1, vec![1]);
        assert!(s.shared.as_ref().unwrap().areas[1].1.is_empty());
        assert_eq!(present(&queued_bodies(s, now), &first), 1);
    }
    direct_contact(&mut world, 1512, 2);
    for s in [&mut a, &mut b] {
        poll(s, &mut world, now).unwrap();
        assert_eq!(s.shared.as_ref().unwrap().areas[0].1, vec![0, 1]);
        let before = queued_bodies(s, now);
        assert_eq!(present(&before, &first), 1);
        assert_eq!(present(&before, &full), 1);
        assert_eq!(present(&before, &other), 0);
        poll(s, &mut world, now).unwrap();
        assert_eq!(queued_bodies(s, now), before);
    }
    assert_eq!(world.fragiles.as_ref().unwrap().excluded(), vec![1512, 1513]);
    assert_eq!(world.actors[0].health, 90); assert_eq!(world.actors[1].health, 90);
}

#[test]
fn partial_hp_does_not_publish_destruction_before_final_hit() {
    let now = Instant::now(); let (mut a, _, _) = visible_pair(now);
    let mut world = model::tests::fragile_world(now, Some(32)); prepare_client(&mut a, &world);
    let update = area_wire::area_update(0, &[1]).unwrap();
    direct_contact(&mut world, 1513, 1);
    assert_eq!(world.fragiles.as_ref().unwrap().events[0].health_after, 2);
    poll(&mut a, &mut world, now).unwrap();
    assert!(a.shared.as_ref().unwrap().areas[0].1.is_empty());
    assert_eq!(present(&queued_bodies(&a, now), &update), 0);
    direct_contact(&mut world, 1513, 2);
    poll(&mut a, &mut world, now).unwrap();
    assert_eq!(present(&queued_bodies(&a, now), &update), 1);
    assert_eq!(a.shared.as_ref().unwrap().areas[0].1, vec![1]);
}

#[test]
fn fresh_connection_creation_contains_current_state_without_break_replay() {
    let now = Instant::now(); let mut world = model::tests::fragile_world(now, None);
    direct_contact(&mut world, 1513, 1); direct_contact(&mut world, 1512, 2);
    let mut s = entities(now, &world);
    let mut payload = request(area_wire::area_id(0).unwrap()); payload.extend(request(area_wire::area_id(1).unwrap()));
    s.receive(&frame(&s, &payload), now).unwrap();
    assert_eq!(s.shared.as_ref().unwrap().areas[0].1, vec![0, 1]);
    assert!(s.shared.as_ref().unwrap().areas[1].1.is_empty());
    let bodies = queued_bodies(&s, now);
    assert_eq!(present(&bodies, &area_wire::area_create(0, 31354, &[0, 1]).unwrap()), 1);
    assert_eq!(present(&bodies, &area_wire::area_create(1, 31355, &[]).unwrap()), 1);
    assert_eq!(present(&bodies, &area_wire::area_update(0, &[0, 1]).unwrap()), 0);
    {
        let c = s.shared.as_mut().unwrap(); c.phase = Phase::Driving;
        c.creations = [Some((0, true)); 2]; c.ready_sent = [true; 2];
        for (pending, _) in &mut c.areas { pending.as_mut().unwrap().1 = true; }
    }
    poll(&mut s, &mut world, now).unwrap();
    let after = queued_bodies(&s, now);
    assert_eq!(present(&after, &area_wire::area_create(0, 31354, &[0, 1]).unwrap()), 1);
    assert_eq!(present(&after, &area_wire::area_update(0, &[0, 1]).unwrap()), 0);
}

#[test]
fn mixed_unknown_or_duplicate_request_rolls_back_entire_envelope() {
    let now = Instant::now(); let world = model::tests::fragile_world(now, None);
    for bad_id in [123, area_wire::area_id(0).unwrap()] {
        let mut s = entities(now, &world);
        let mut payload = request(area_wire::area_id(0).unwrap());
        payload.extend(request(wire::vehicle_id(0).unwrap())); payload.extend(request(bad_id));
        let rx = s.rx; let bodies = queued_bodies(&s, now);
        assert!(s.receive(&frame(&s, &payload), now).is_err());
        assert_eq!(s.rx, rx);
        assert!(s.shared.as_ref().unwrap().areas.iter().all(|(pending, ids)| pending.is_none() && ids.is_empty()));
        assert_eq!(s.shared.as_ref().unwrap().creations, [None; 2]);
        assert_eq!(queued_bodies(&s, now), bodies);
        let mut valid = request(area_wire::area_id(0).unwrap()); valid.extend(request(area_wire::area_id(1).unwrap()));
        s.receive(&frame(&s, &valid), now).unwrap();
        assert!(s.shared.as_ref().unwrap().areas.iter().all(|(pending, _)| pending.is_some()));
    }
}

#[test]
fn driving_mixed_area_requests_and_aim_are_accepted_atomically() {
    let now = Instant::now();
    let world = many_chunk_world(now);
    let (mut s, _) = driving(now);
    {
        let c = s.shared.as_mut().unwrap();
        c.view = Some(world.clone());
        c.announced_areas = 117;
        c.areas = vec![(None, Vec::new()); 117];
        c.tree_areas = vec![Vec::new(); 117];
        c.creations = [Some((0, true)); 2];
        c.binding = Some((0, true));
        c.correction = true;
    }
    let mut payload = Vec::new();
    for area in 0..6 { payload.extend(request(area_wire::area_id(area).unwrap())); }
    payload.extend(point(0, [100., 100., 100.]));
    s.receive(&frame(&s, &payload), now).unwrap();
    let c = s.shared.as_ref().unwrap();
    assert_eq!(c.commands.len(), 1);
    assert!(c.pending_area_requests.len() <= 1);
    assert!(c.areas.iter().take(6).any(|(pending, _)| pending.is_some()));

    let (mut malformed, _) = driving(now);
    {
        let c = malformed.shared.as_mut().unwrap();
        c.view = Some(world);
        c.announced_areas = 117;
        c.areas = vec![(None, Vec::new()); 117];
        c.tree_areas = vec![Vec::new(); 117];
        c.creations = [Some((0, true)); 2];
        c.binding = Some((0, true));
        c.correction = true;
    }
    let before_rx = malformed.rx;
    let mut invalid_payload = request(area_wire::area_id(0).unwrap());
    invalid_payload.extend([0x8f, 12, 0, 1, 2]);
    assert!(malformed.receive(&frame(&malformed, &invalid_payload), now).is_err());
    assert_eq!(malformed.rx, before_rx);
    let c = malformed.shared.as_ref().unwrap();
    assert!(c.pending_area_requests.is_empty());
    assert!(c.areas.iter().all(|(pending, _)| pending.is_none()));
    assert!(c.commands.is_empty());
}

#[test]
fn driving_mixed_area_requests_and_ready_compound_are_accepted() {
    let now = Instant::now();
    let world = many_chunk_world(now);
    let (mut s, _) = driving(now);
    {
        let c = s.shared.as_mut().unwrap();
        c.view = Some(world);
        c.announced_areas = 117;
        c.areas = vec![(None, Vec::new()); 117];
        c.tree_areas = vec![Vec::new(); 117];
        c.creations = [Some((0, true)); 2];
        c.binding = Some((0, true));
        c.correction = true;
    }
    let mut payload = Vec::new();
    for area in 0..6 { payload.extend(request(area_wire::area_id(area).unwrap())); }
    payload.extend(ready(0));
    s.receive(&frame(&s, &payload), now).unwrap();
    let c = s.shared.as_ref().unwrap();
    assert!(c.commands.is_empty());
    assert!(c.areas.iter().take(6).any(|(pending, _)| pending.is_some()));
}

#[test]
fn late_outbox_failure_does_not_commit_sent_arrays_commands_or_world() {
    let now = Instant::now(); let (mut a, _, mut world) = pair(now);
    direct_contact(&mut world, 1513, 1); direct_contact(&mut world, 1512, 2);
    a.shared.as_mut().unwrap().commands.push(model::Command::Move(model::Input { throttle: 1, steer: 0 }));
    a.outbox.push_back(vec![0; 513]);
    let rx = a.rx; let tx_len = a.tx.len(); let outbox = a.outbox.clone();
    let areas = a.shared.as_ref().unwrap().areas.clone();
    let actors = world.actors.clone(); let state = world.fragiles.clone(); let trace = world.impact.clone();
    assert!(poll(&mut a, &mut world, now).is_err());
    assert_eq!(a.rx, rx); assert_eq!(a.tx.len(), tx_len); assert_eq!(a.outbox, outbox);
    assert_eq!(a.shared.as_ref().unwrap().areas, areas);
    assert_eq!(a.shared.as_ref().unwrap().commands.len(), 1);
    assert_eq!(world.actors, actors); assert_eq!(world.fragiles, state); assert_eq!(world.impact, trace);
    a.outbox.clear(); poll(&mut a, &mut world, now).unwrap();
    assert!(a.shared.as_ref().unwrap().commands.is_empty());
    assert_eq!(a.shared.as_ref().unwrap().areas[0].1, vec![0, 1]);
    assert!(a.shared.as_ref().unwrap().areas[1].1.is_empty());
    let update = area_wire::area_update(0, &[0, 1]).unwrap();
    assert_eq!(present(&queued_bodies(&a, now), &update), 1);
    let before = queued_bodies(&a, now); poll(&mut a, &mut world, now).unwrap();
    assert_eq!(queued_bodies(&a, now), before);
}

fn before_first_ready(now: Instant, slot: usize) -> Session {
    let world = many_chunk_world(now);
    let mut s = entities(now, &world);
    s.id = slot as u32 + 1;
    let c = s.shared.as_mut().unwrap();
    c.slot = slot; c.creations = [Some((0, true)); 2];
    c.binding = None; c.correction = false; c.ready_sent = [false; 2];
    s
}

fn captured_requests_ready(slot: usize) -> Vec<u8> {
    // treeobserve08 application bytes, excluding the private token envelope.
    // Both peers batched six area requests with their first READY33.
    let first = if slot == 0 { 0x09100031 } else { 0x0910002b };
    let mut bytes = Vec::new();
    for id in first..first + 6 { bytes.extend(request(id)); }
    bytes.extend(ready(slot));
    assert_eq!(bytes.len(), 75);
    bytes
}

fn assert_input_rolled_back(s: &Session, before: &Session, now: Instant) {
    assert_eq!(s.rx, before.rx); assert_eq!(s.received, before.received);
    assert_eq!(s.tx.cumulative, before.tx.cumulative);
    assert_eq!(queued_bodies(s, now), queued_bodies(before, now));
    assert_eq!(s.outbox, before.outbox);
    let c = s.shared.as_ref().unwrap(); let old = before.shared.as_ref().unwrap();
    assert_eq!(c.phase, old.phase); assert_eq!(c.binding, old.binding);
    assert_eq!(c.correction, old.correction); assert_eq!(c.creations, old.creations);
    assert_eq!(c.ready_sent, old.ready_sent); assert_eq!(c.areas, old.areas);
    assert_eq!(c.tree_areas, old.tree_areas);
    assert_eq!(c.pending_area_requests, old.pending_area_requests);
    assert_eq!(c.pending_entity_requests, old.pending_entity_requests);
    assert_eq!(c.commands, old.commands);
}

#[test]
fn entities_first_ready_mixed_native_requests_both_slots_and_retry() {
    let now = Instant::now();
    for slot in 0..2 {
        let mut s = before_first_ready(now, slot);
        let payload = captured_requests_ready(slot);
        let input = frame(&s, &payload); let rx = s.rx;
        s.receive(&input, now).unwrap();
        let c = s.shared.as_ref().unwrap();
        assert_eq!(c.phase, Phase::Driving); assert!(!c.correction);
        assert!(c.binding.is_some_and(|(_, ack)| !ack));
        assert!(c.commands.is_empty());
        assert_eq!(c.areas.iter().filter(|(p, _)| p.is_some()).count(), 6);
        assert_eq!(s.tx.len(), 7); assert_eq!(s.rx, rx + 1);
        // Native retry must not create another binding or increment rx twice.
        let after = s.clone(); s.receive(&input, now).unwrap();
        assert_input_rolled_back(&s, &after, now);
    }
}

#[test]
fn entities_first_ready_malformed_suffix_and_requests_rollback() {
    let now = Instant::now();
    for slot in 0..2 {
        let valid = captured_requests_ready(slot);
        let prefix = &valid[..42];
        let mut bad_payloads = vec![];
        for len in 1..33 { bad_payloads.push([prefix, &ready(slot)[..len]].concat()); }
        bad_payloads.push([valid.as_slice(), &[0]].concat());
        bad_payloads.push([prefix, ready(1-slot).as_slice()].concat());
        bad_payloads.push([prefix, point(0, [0.; 3]).as_slice()].concat());
        bad_payloads.push([prefix, &[0x8a, 1, 0, 0]].concat());
        bad_payloads.push([valid.as_slice(), &valid[..7]].concat());
        for id in [123, area_wire::area_id(117).unwrap(), u32::from_le_bytes(valid[3..7].try_into().unwrap())] {
            bad_payloads.push([prefix, request(id).as_slice(), ready(slot).as_slice()].concat());
        }
        for payload in bad_payloads {
            let mut s = before_first_ready(now, slot); let before = s.clone();
            assert!(s.receive(&frame(&s, &payload), now).is_err());
            assert_input_rolled_back(&s, &before, now);
        }
        for own in [None, Some((0, false))] {
            let mut s = before_first_ready(now, slot);
            s.shared.as_mut().unwrap().creations[slot] = own;
            let before = s.clone();
            assert!(s.receive(&frame(&s, &valid), now).is_err());
            assert_input_rolled_back(&s, &before, now);
        }
        let mut future = before_first_ready(now, slot);
        future.shared.as_mut().unwrap().announced_areas = 6;
        let before = future.clone();
        assert!(future.receive(&frame(&future, &valid), now).is_err());
        assert_input_rolled_back(&future, &before, now);
    }
}

#[test]
fn entities_first_ready_reserves_binding_and_uses_same_frame_ack() {
    let now = Instant::now();
    for slot in 0..2 {
        let mut s = before_first_ready(now, slot);
        for _ in 0..7 { s.tx.enqueue().unwrap(); }
        s.receive(&frame(&s, &captured_requests_ready(slot)), now).unwrap();
        let c = s.shared.as_ref().unwrap();
        assert_eq!(c.phase, Phase::Driving); assert_eq!(s.tx.len(), 8);
        assert_eq!(c.pending_area_requests.len(), 6);
        assert!(c.areas.iter().all(|(p, _)| p.is_none()));

        let mut full = before_first_ready(now, slot);
        let sequence = full.tx.enqueue_body_tracked(&wire::create_vehicle(full.shared.as_ref().unwrap().view.as_ref().unwrap(), slot).unwrap()).unwrap();
        full.shared.as_mut().unwrap().creations[slot] = Some((sequence, false));
        for _ in 0..7 { full.tx.enqueue().unwrap(); }
        while full.tx.due(now, full.rx).unwrap().is_some() {}
        let before = full.clone();
        let mut input = frame(&full, &captured_requests_ready(slot));
        assert!(full.receive(&input, now).is_err());
        assert_input_rolled_back(&full, &before, now);
        input.cumulative = Some(sequence + 1);
        full.receive(&input, now).unwrap();
        let c = full.shared.as_ref().unwrap();
        assert_eq!(c.phase, Phase::Driving); assert_eq!(full.tx.len(), 8);
        assert!(c.creations[slot].unwrap().1);
        assert_eq!(c.pending_area_requests.len(), 6);
    }
}
