//! Bounded two-session native dispatcher. Authentication and channel replay
//! policy are shared with the accepted gateway; no unauthenticated lab login.
use super::{model::{self, World}, wire, Client, Phase};
use super::super::*;

#[derive(Default)]
struct Table { sessions: Vec<Session>, retirement: RetirementWindow }
impl Table {
    fn admissible(&mut self, attempt: &LoginAttempt, now: Instant) -> io::Result<()> {
        self.retirement.check_login(attempt, now).map_err(|_| model::bad())?;
        if self.sessions.iter().any(|s| s.same_login_attempt(attempt)) { return Ok(()); }
        if self.sessions.len() >= model::CAPACITY
            || self.retirement.retained_count() + self.sessions.len() >= MAX_RETIRED
            || self.sessions.iter().any(|s| s.key == attempt.key || s.login_peer == attempt.login_peer
                || s.base_peer == Some(attempt.login_peer)) { return Err(model::bad()); }
        Ok(())
    }
    fn route(&self, peer: SocketAddr, packet: &[u8]) -> io::Result<usize> {
        if packet.len() == 21 {
            let matches: Vec<_> = self.sessions.iter().enumerate()
                .filter(|(_, s)| base::base_request(packet, s.handoff).is_ok()).map(|(i, _)| i).collect();
            if matches.len() != 1 { return Err(model::bad()); }
            let index = matches[0];
            if self.sessions[index].base_peer.is_some_and(|bound| bound != peer)
                || self.sessions.iter().enumerate().any(|(i, s)| i != index &&
                    (s.base_peer == Some(peer) || s.login_peer == peer)) { return Err(model::bad()); }
            Ok(index)
        } else {
            self.sessions.iter().position(|s| s.base_peer == Some(peer)).ok_or_else(model::bad)
        }
    }
    fn retire(&mut self, id: u32, world: &mut World, now: Instant, reason: &str) -> io::Result<()> {
        let index = self.sessions.iter().position(|s| s.id == id).ok_or_else(model::bad)?;
        let s = &self.sessions[index];
        self.retirement.retire(s.login_attempt.ok_or_else(model::bad)?, s.base_peer, now).map_err(|_| model::bad())?;
        // An explicit leave intent already parked this actor. Disconnect and
        // timeout take the same stop-controller path without touching a peer.
        if world.actors.iter().any(|a| a.session == Some(id)) { world.detach(id)?; }
        self.sessions.remove(index);
        println!("SHARED_SESSION_CLOSED battle={} session={id} reason={reason} survivors={} tick={}", world.id, self.sessions.len(), world.tick);
        Ok(())
    }
}

pub fn serve(key_path: &str, digest_path: &str, config_path: &str, capture_path: &str)
    -> Result<(), Box<dyn std::error::Error>> {
    let config = Arc::new(crate::identity091::Config::load(config_path)?);
    let private = login::load_key(key_path)?;
    if fs::metadata(digest_path)?.len() != 16 { return Err(model::bad().into()); }
    let digest: [u8; 16] = fs::read(digest_path)?.try_into().map_err(|_| model::bad())?;
    let login_socket = UdpSocket::bind(config.login_bind)?;
    let base_socket = UdpSocket::bind(config.base_bind)?;
    login_socket.set_nonblocking(true)?; base_socket.set_nonblocking(true)?;
    let mut capture = Some(Recorder::open_profile(capture_path, &config.local_root, crate::capture091::Profile::SharedWorldV1)?);
    let mut table = Table::default();
    let started = Instant::now();
    let mut world = World::new(OsRng.next_u64().max(1), started)?;
    let mut next_id = 1u32;
    let mut auth: Option<AuthJob> = None;
    let mut last_auth: Option<Instant> = None;
    let mut fragments = login::LoginFragments::default();
    let mut rate_started = started; let mut rate_count = 0u32;
    println!("BOUND {} base_backend={} profile=legacy091-shared-lab battle={} capacity=2 scope=allied_temporary_ms1 motion=bounded_kinematic physics=false inventory_changed=false", config.login_bind, config.base_bind, world.id);
    loop {
        let now = Instant::now();
        if now.duration_since(started) >= model::LIFETIME { println!("SHARED_STOP reason=lab_lifetime"); break; }
        if now.duration_since(rate_started) >= Duration::from_secs(1) { rate_started = now; rate_count = 0; }
        let mut closing: Vec<(u32, &'static str)> = Vec::new();
        let result = auth.as_ref().and_then(|job| match job.receiver.try_recv() {
            Ok(result) => Some(result), Err(mpsc::TryRecvError::Empty) => None,
            Err(mpsc::TryRecvError::Disconnected) => Some(Err(model::bad())),
        });
        if let Some(result) = result {
            let job = auth.take().ok_or_else(model::bad)?;
            match result {
                Ok(Some(accepted)) => {
                    let admitted = (|| -> io::Result<usize> {
                        table.admissible(&job.attempt, now)?;
                        if let Some(index) = table.sessions.iter().position(|s| s.same_login_attempt(&job.attempt)) {
                            if !table.sessions[index].verified_duplicate(&job.attempt, &accepted.identity.account_id) { return Err(model::bad()); }
                            return Ok(index);
                        }
                        if table.sessions.iter().any(|s| s.identity.as_ref().is_some_and(|p| p.account_id == accepted.identity.account_id)) { return Err(model::bad()); }
                        let mut s = Session::new(next_id, job.attempt.key, job.attempt.login_peer, now);
                        // Explicitly fail closed on the astronomically unlikely
                        // random capability collision instead of ambiguous routing.
                        if s.handoff == 0 || s.token == 0 || table.sessions.iter().any(|old| old.handoff == s.handoff || old.token == s.token) { return Err(model::bad()); }
                        let mut next_world = world.clone();
                        let slot = next_world.attach(model::Identity { account: accepted.identity.account_id.clone(),
                            database: accepted.identity.database_id, name: accepted.identity.name.clone() }, next_id)?;
                        s.account_probe = true; s.account_ready = true; s.tx = Window::interactive();
                        s.login_attempt = Some(job.attempt); s.identity = Some(accepted.identity);
                        s.hangar = Some(accepted.fixtures); s.shared = Some(Client::new(slot));
                        println!("SHARED_SESSION_PENDING battle={} session={next_id} slot={slot} account={} database={} authenticated=true", world.id,
                            s.identity.as_ref().ok_or_else(model::bad)?.account_id, s.identity.as_ref().ok_or_else(model::bad)?.database_id);
                        next_id = next_id.checked_add(1).ok_or_else(model::bad)?;
                        world = next_world; table.sessions.push(s); Ok(table.sessions.len() - 1)
                    })();
                    match admitted {
                        Ok(index) => {
                            let s = &table.sessions[index];
                            send_wire(&login_socket, job.attempt.login_peer, &redirect091::reply_to(job.request, &s.key, s.handoff, config.base_bind)?, Channel::Login, &mut capture)?;
                        },
                        Err(_) => { send_wire(&login_socket, job.attempt.login_peer, &login::rejection(job.request, 73), Channel::Login, &mut capture)?;
                            println!("SHARED_AUTH_REJECT reason=admission_or_world_capacity allocated=0"); },
                    }
                },
                Ok(None) => { send_wire(&login_socket, job.attempt.login_peer, &login::rejection(job.request, 67), Channel::Login, &mut capture)?; },
                Err(_) => { send_wire(&login_socket, job.attempt.login_peer, &login::rejection(job.request, 73), Channel::Login, &mut capture)?;
                    println!("SHARED_AUTH_REJECT reason=identity_unavailable allocated=0"); },
            }
        }
        for (is_login, socket) in [(true, &login_socket), (false, &base_socket)] {
            let mut data = [0u8; 65536];
            let (length, peer) = match socket.recv_from(&mut data) {
                Ok(value) => value, Err(error) if error.kind() == io::ErrorKind::WouldBlock => continue,
                Err(error) if error.raw_os_error() == Some(10054) => continue,
                Err(error) => return Err(error.into()),
            };
            rate_count += 1;
            if peer.ip() != Ipv4Addr::LOCALHOST || rate_count > 256
                || length > if is_login { login::MAX_INTERACTIVE_DATAGRAM } else { 1024 } { continue; }
            if let Some(recorder) = &mut capture { recorder.observe(if is_login { Channel::Login } else { Channel::Base }, true, peer, &data[..length]); }
            let packet = &data[..length];
            if is_login {
                let assembled = match fragments.push(peer, now, packet) { Ok(Some(value)) => value, Ok(None) => continue,
                    Err(_) => { println!("SHARED_REJECT reason=login_fragments"); continue; } };
                let (request, fields) = match login::decode_interactive(&assembled, &private) {
                    Ok(value) => value, Err(_) => { println!("SHARED_REJECT reason=login_framing"); continue; }
                };
                if fields.digest != digest { send_wire(socket, peer, &login::rejection(request, 69), Channel::Login, &mut capture)?; continue; }
                let attempt = LoginAttempt::new(fields.session_key, fields.nonce, peer);
                let tag = encrypted_attempt_tag(&assembled)?;
                if let Some(job) = &auth {
                    if !job.pending_duplicate(&attempt, &tag) { send_wire(socket, peer, &login::rejection(request, 73), Channel::Login, &mut capture)?; }
                    continue;
                }
                if table.admissible(&attempt, now).is_err() || last_auth.is_some_and(|last| now.duration_since(last) < Duration::from_millis(250)) {
                    send_wire(socket, peer, &login::rejection(request, 73), Channel::Login, &mut capture)?; continue;
                }
                match start_auth(config.clone(), request, peer, &fields, tag, false) {
                    Ok(job) => { auth = Some(job); last_auth = Some(now); },
                    Err(_) => { send_wire(socket, peer, &login::rejection(request, 73), Channel::Login, &mut capture)?; },
                }
            } else {
                let index = match table.route(peer, packet) { Ok(i) => i, Err(_) => { println!("SHARED_REJECT reason=base_route"); continue; } };
                let s = &mut table.sessions[index];
                if s.guard_base_peer(&mut table.retirement, peer, now).is_err() { println!("SHARED_REJECT reason=retired_peer"); continue; }
                if length == 21 {
                    let (request, _) = base::base_request(packet, s.handoff)?;
                    s.base_peer = Some(peer); send(socket, peer, &base::base_reply(request, s.token), &s.key, &mut capture)?;
                    println!("SHARED_BASE_BOUND battle={} session={} peer={peer}", world.id, s.id);
                } else {
                    let frame = match base::decrypt(packet, &s.key).and_then(|b| transport091::parse_interactive(&b)) {
                        Ok(frame) => frame, Err(_) => { println!("SHARED_REJECT session={} reason=channel_framing", s.id); continue; }
                    };
                    match s.receive(&frame, now) {
                        Ok(close) => {
                            if frame.flags & 0x10 != 0 { send(socket, peer, &transport091::ack(s.rx), &s.key, &mut capture)?; s.last_keepalive = now; }
                            if close { closing.push((s.id, "client_disconnect")); }
                        },
                        Err(_) => println!("SHARED_REJECT session={} reason=channel_state sequence={:?} bytes={}", s.id, frame.sequence, frame.body.len()),
                    }
                }
            }
        }
        // Remove known disconnects before applying any queued intent or tick.
        for (id, reason) in closing.drain(..) { table.retire(id, &mut world, now, reason)?; }
        for s in &mut table.sessions {
            if s.ready_for_arena_base() {
                let c = s.shared.as_mut().ok_or_else(model::bad)?;
                if c.hangar_since.is_none() { c.hangar_since = Some(now); }
            }
        }
        if world.started.is_none() && table.sessions.len() == 2 && table.sessions.iter().all(|s| entry_ready(s, now)) {
            world.start(now)?;
            println!("SHARED_WORLD_STARTED battle={} sessions=2 actors=2 space=1 tick=1000", world.id);
        }
        if world.started.is_some() { world.advance(now)?; }
        for s in &mut table.sessions {
            let reason = if now.duration_since(s.created_at) >= config.session_duration { Some("session_deadline") }
                else if now.duration_since(s.last_rx) >= Duration::from_secs(8) { Some("idle_timeout") } else { None };
            if let Some(reason) = reason { closing.push((s.id, reason)); continue; }
            if let Err(error) = poll(s, &mut world, now) {
                println!("SHARED_FAILED session={} reason={}", s.id, error); closing.push((s.id, "world_or_publication")); continue;
            }
            if s.shared.as_ref().is_some_and(|c| c.phase == Phase::Leaving) { closing.push((s.id, "native_leave")); continue; }
            if !s.active { continue; }
            if s.tx.len() == 0 && now.duration_since(s.last_heartbeat) >= Duration::from_secs(2) {
                if s.tx.enqueue().is_err() { closing.push((s.id, "sequence_budget")); continue; } s.last_heartbeat = now;
            }
            if let Some(peer) = s.base_peer {
                match s.tx.due(now, s.rx) {
                    Ok(Some((_, _, body))) => send(&base_socket, peer, &body, &s.key, &mut capture)?,
                    Ok(None) => {}, Err(_) => { closing.push((s.id, "retry_exhausted")); continue; },
                }
                if now.duration_since(s.last_keepalive) >= Duration::from_secs(1) {
                    send(&base_socket, peer, &transport091::ack(s.rx), &s.key, &mut capture)?; s.last_keepalive = now;
                }
            }
        }
        for (id, reason) in closing { table.retire(id, &mut world, now, reason)?; }
        // Both peers receive a snapshot of the same completed server tick.
        for s in &mut table.sessions { if let Some(c) = &mut s.shared { c.view = Some(world.clone()); } }
        thread::sleep(Duration::from_millis(5));
    }
    Ok(())
}

fn poll(s: &mut Session, world: &mut World, now: Instant) -> io::Result<()> {
    if world.started.is_none() { return Ok(()); }
    if entry_ready(s, now) { s.shared_start(world, now)?; }
    let c = s.shared.as_ref().ok_or_else(model::bad)?;
    if matches!(c.phase, Phase::Enable | Phase::Entities) && c.entered.is_some_and(|start| now.duration_since(start) > Duration::from_secs(90)) { return Err(model::bad()); }
    if !matches!(c.phase, Phase::Driving | Phase::Leaving) { return Ok(()); }
    let slot = c.slot;
    let mut next = s.clone(); let mut next_world = world.clone();
    if c.correction { next_world.set_ready(slot, s.id)?; }
    let commands = std::mem::take(&mut next.shared.as_mut().ok_or_else(model::bad)?.commands);
    if !c.correction && !commands.is_empty() {
        // Keep a bounded startup intent until ACK6; no pre-correction motion.
        if commands.iter().any(|cmd| !matches!(cmd, model::Command::Aim(_) | model::Command::Move(model::Input::STOP))) { return Err(model::bad()); }
        next.shared.as_mut().ok_or_else(model::bad)?.commands = commands;
        *s = next; return Ok(());
    }
    if !c.correction { return Ok(()); }
    let outcomes = next_world.apply(slot, s.id, &commands, now)?;
    for outcome in &outcomes {
        if let crate::battle091::fire::Outcome::AcceptedShot { ammo_remaining } = outcome {
            let mut b = wire::ammo_count(*ammo_remaining)?; b.extend(wire::reload(slot, crate::battle091::fire::MS1_RELOAD_SECONDS)?);
            next.outbox.push_back(b);
        }
    }
    if next_world.actors[slot].fire.finish_reload_if_due(now) { next.outbox.push_back(wire::reload(slot, 0.)?); }
    let c = next.shared.as_mut().ok_or_else(model::bad)?;
    let mut shot_publications = Vec::new();
    if c.phase == Phase::Driving {
        for shot in next_world.shots.iter().filter(|shot| shot.sequence > c.shot_cursor).copied().collect::<Vec<_>>() {
            let observable = c.correction && c.binding.is_some_and(|(_, ack)| ack) && c.visible()[shot.slot];
            if observable { next.outbox.push_back(wire::shooting(shot.slot)?); }
            // Even a skipped event is consumed: becoming visible later must
            // not replay stale gunfire. The cursor commits with the queue.
            c.shot_cursor = shot.sequence;
            shot_publications.push((shot, observable));
        }
        for other in 0..2 {
            if next_world.actors[other].ready && !c.ready_sent[other] {
                next.outbox.push_back(wire::ready_update(other)?); c.ready_sent[other] = true;
            }
        }
        // No queue of stale poses for a slow peer. Reliable retries retain their
        // exact bytes; the next fresh pose is queued when capacity is available.
        let old_tick = c.view.as_ref().map(|w| w.tick).unwrap_or(0);
        if c.correction && c.binding.is_some_and(|(_, ack)| ack) && old_tick != next_world.tick && next.tx.len() < 4 {
            let body = wire::publication(&next_world, c.visible())?;
            next.tx.enqueue_body(&body)?;
            println!("SHARED_SNAPSHOT battle={} session={} tick={} positions={:?} ready={:?} aim_yaw_pitch={:?}", next_world.id, s.id, next_world.tick,
                next_world.actors.iter().map(|a| a.position).collect::<Vec<_>>(), c.visible(),
                next_world.actors.iter().map(|a| (a.aim.yaw,a.aim.pitch)).collect::<Vec<_>>());
        }
    }
    if next.outbox.len() > 128 { return Err(model::bad()); } next.drain_outbox()?;
    for outcome in outcomes { println!("SHARED_FIRE battle={} session={} slot={slot} outcome={outcome:?}", world.id, s.id); }
    for command in &commands { if let model::Command::Move(input) = command { println!("SHARED_INPUT battle={} session={} slot={slot} input={input:?} client_position_used=false", world.id, s.id); } }
    for command in &commands { if let model::Command::Aim(intent) = command { println!("SHARED_AIM battle={} session={} slot={slot} intent={intent:?} client_angles_authoritative=false", world.id, s.id); } }
    for (shot, delivered) in shot_publications {
        println!("SHARED_SHOT_CUE battle={} session={} shot={} shooter_slot={} tick={} queued={} reason={}",
            world.id, s.id, shot.sequence, shot.slot, shot.tick, delivered,
            if delivered { "visible_native_vehicle" } else { "not_observable_at_event" });
    }
    *world = next_world; *s = next; Ok(())
}

fn entry_ready(s: &Session, now: Instant) -> bool {
    s.ready_for_arena_base() && s.shared.as_ref().is_some_and(|c| c.phase == Phase::Account
        && c.hangar_since.is_some_and(|start| now.saturating_duration_since(start) >= Duration::from_secs(3)))
}

#[cfg(test)]
mod tests {
    use super::*;
    fn peer(port: u16) -> SocketAddr { SocketAddr::from(([127,0,0,1], port)) }
    fn session(id: u32, now: Instant) -> Session {
        let mut s = Session::new(id, [id as u8;16], peer(30000 + id as u16), now);
        s.login_attempt = Some(LoginAttempt::new(s.key, id, s.login_peer)); s
    }
    fn driving(now: Instant) -> (Session, World) {
        let world = model::tests::world(now);
        let mut s = session(1, now);
        let identity = crate::identity091::Profile {
            account_id: crate::arena_vehicle091::PRIMARY_ACCOUNT.into(), database_id: 1,
            name: crate::arena_vehicle091::PRIMARY_NAME.into(),
            fixture_dir: Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/server/fixtures")
                .join(crate::arena_vehicle091::PRIMARY_ACCOUNT).join("r4-catalog3").canonicalize().unwrap(),
        };
        s.hangar = Some(Arc::new(crate::hangar091::Fixtures::load_interactive(&identity.fixture_dir).unwrap()));
        s.identity = Some(Arc::new(identity)); s.active = true; s.rx = 1; s.account_ready = true;
        s.tx = Window::interactive(); s.arena_base = true;
        let mut c = Client::new(0); c.phase = Phase::Driving; c.correction = true;
        c.binding = Some((0,true)); c.view = Some(world.clone()); s.shared = Some(c); (s,world)
    }
    fn frame(s: &Session, payload: &[u8]) -> Frame {
        Frame { flags:0x458, sequence:Some(s.rx), cumulative:Some(0), selective:vec![],
            body:[vec![1],s.token.to_le_bytes().to_vec(),payload.to_vec()].concat(), piggybacks:vec![] }
    }
    fn visible_pair(now: Instant) -> (Session, Session, World) {
        let (mut a,w) = driving(now);
        a.shared.as_mut().unwrap().creations = [Some((0,true));2];
        a.shared.as_mut().unwrap().ready_sent = [true;2];
        let mut b = a.clone(); b.id = 2; b.shared.as_mut().unwrap().slot = 1;
        (a,b,w)
    }
    fn queued_bodies(s: &Session, now: Instant) -> Vec<Vec<u8>> {
        let mut tx = s.tx.clone(); let mut bodies = Vec::new();
        while let Some((_,_,raw)) = tx.due(now,s.rx).unwrap() {
            bodies.push(transport091::parse_interactive(&raw).unwrap().body);
        }
        bodies.extend(s.outbox.iter().cloned()); bodies
    }
    fn point(slot:usize,p:[f32;3])->Vec<u8> {
        let mut b=vec![0x0f,16,0];b.extend(wire::vehicle_id(slot).unwrap().to_le_bytes());
        for x in p {b.extend(x.to_le_bytes());} b
    }
    #[test] fn native_aim_is_owned_atomic_and_published_from_one_server_state() {
        let now=Instant::now();let (mut a,mut b,mut w)=visible_pair(now);
        let input=point(1,[100.,100.,100.]);
        assert!(a.receive(&frame(&a,&input),now).is_err());
        let mut poison=vec![0x88,0,0];poison.extend(point(0,[f32::NAN,0.,0.]));
        assert!(a.receive(&frame(&a,&poison),now).is_err());assert!(a.shared.as_ref().unwrap().commands.is_empty());
        let packet=frame(&b,&input);b.receive(&packet,now).unwrap();poll(&mut b,&mut w,now).unwrap();
        assert_eq!(w.actors[1].aim.yaw,0.);assert_eq!(w.actors[0].aim,super::super::aim::State::new());
        b.receive(&packet,now).unwrap();assert!(b.shared.as_ref().unwrap().commands.is_empty());
        w.advance(now+model::STEP).unwrap();poll(&mut a,&mut w,now+model::STEP).unwrap();poll(&mut b,&mut w,now+model::STEP).unwrap();
        assert!(w.actors[1].aim.yaw>0.);assert!(w.actors[1].aim.yaw<=super::super::aim::YAW_RATE*0.101);
        let expected=wire::publication(&w,[true,true]).unwrap();
        for s in [&a,&b] {assert!(queued_bodies(s,now+model::STEP).contains(&expected));}
    }
    #[test] fn startup_target_waits_for_correction_and_rejoin_holds_actual_angles() {
        let now=Instant::now();let (mut a,_,mut w)=visible_pair(now);
        a.shared.as_mut().unwrap().correction=false;w.actors[0].ready=false;
        a.receive(&frame(&a,&point(0,[100.,100.,100.])),now).unwrap();poll(&mut a,&mut w,now).unwrap();
        w.advance(now+model::STEP).unwrap();assert_eq!(w.actors[0].aim.yaw,0.);
        a.receive(&frame(&a,&[6]),now+model::STEP).unwrap();poll(&mut a,&mut w,now+model::STEP).unwrap();
        w.advance(now+model::STEP*2).unwrap();let pose=(w.actors[0].aim.yaw,w.actors[0].aim.pitch);
        assert!(pose.0>0.);w.detach(1).unwrap();w.advance(now+model::STEP*3).unwrap();
        w.attach(w.actors[0].identity.clone(),3).unwrap();w.set_ready(0,3).unwrap();w.advance(now+model::STEP*4).unwrap();
        assert_eq!((w.actors[0].aim.yaw,w.actors[0].aim.pitch),pose);
        assert!(w.apply(0,1,&[model::Command::Aim(super::super::aim::Intent::Point([0.;3]))],now+model::STEP*4).is_err());
    }
    #[test] fn backpressure_does_not_enqueue_a_history_of_aim_poses() {
        let now=Instant::now();let (mut a,_,mut w)=visible_pair(now);
        for _ in 0..4 {a.tx.enqueue_body(&[19]).unwrap();}
        for n in 1..30 {w.advance(now+model::STEP*n).unwrap();poll(&mut a,&mut w,now+model::STEP*n).unwrap();}
        assert_eq!(a.tx.len(),4);assert!(a.outbox.is_empty());
    }
    #[test] fn accepted_native_shot_reaches_each_known_vehicle_once_with_private_ammo() {
        let now=Instant::now(); let (mut a,mut b,mut w)=visible_pair(now);
        let shot=frame(&a,&[0x88,0,0]); a.receive(&shot,now).unwrap();
        poll(&mut a,&mut w,now).unwrap(); poll(&mut b,&mut w,now).unwrap();
        assert_eq!(w.actors[0].fire.ammo(),19); assert_eq!(w.actors[1].fire.ammo(),20);
        assert_eq!(w.shots.len(),1);
        // Duplicate reliable input and another publication pass emit no event.
        a.receive(&shot,now).unwrap(); poll(&mut a,&mut w,now).unwrap(); poll(&mut b,&mut w,now).unwrap();
        let cue=wire::shooting(0).unwrap();
        assert_eq!(queued_bodies(&a,now).iter().filter(|body| **body==cue).count(),1);
        assert_eq!(queued_bodies(&b,now),vec![cue]);
        let rejected=frame(&a,&[0x88,0,0]);a.receive(&rejected,now).unwrap();poll(&mut a,&mut w,now).unwrap();
        assert_eq!(w.shots.len(),1);
        b.receive(&frame(&b,&[0x88,0,0]),now).unwrap();poll(&mut b,&mut w,now).unwrap();poll(&mut a,&mut w,now).unwrap();
        assert_eq!(w.shots.len(),2);
        for s in [&a,&b] {assert_eq!(queued_bodies(s,now).iter().filter(|body| **body==wire::shooting(1).unwrap()).count(),1);}
    }
    #[test] fn uncreated_vehicle_cannot_receive_a_cue_or_replay_it_after_creation() {
        let now=Instant::now();let (mut a,mut b,mut w)=visible_pair(now);
        b.shared.as_mut().unwrap().creations[0]=Some((0,false));
        a.receive(&frame(&a,&[0x88,0,0]),now).unwrap();poll(&mut a,&mut w,now).unwrap();poll(&mut b,&mut w,now).unwrap();
        assert_eq!(b.shared.as_ref().unwrap().shot_cursor,1);assert!(queued_bodies(&b,now).is_empty());
        b.shared.as_mut().unwrap().creations[0]=Some((0,true));poll(&mut b,&mut w,now).unwrap();
        assert!(queued_bodies(&b,now).is_empty());
        let later=now+Duration::from_secs(3);
        a.receive(&frame(&a,&[0x88,0,0]),later).unwrap();poll(&mut a,&mut w,later).unwrap();poll(&mut b,&mut w,later).unwrap();
        assert_eq!(queued_bodies(&b,later),vec![wire::shooting(0).unwrap()]);
    }
    #[test] fn rejoin_readiness_starts_after_past_shots_without_replay_or_ammo_grant() {
        let now=Instant::now();let (mut a,_,mut w)=visible_pair(now);
        a.receive(&frame(&a,&[0x88,0,0]),now).unwrap();poll(&mut a,&mut w,now).unwrap();
        w.detach(1).unwrap();w.attach(w.actors[0].identity.clone(),3).unwrap();
        let (mut rejoin,_) = driving(now);rejoin.id=3;
        let c=rejoin.shared.as_mut().unwrap();c.phase=Phase::Entities;c.correction=false;
        c.binding=None;c.creations=[Some((0,true));2];c.view=Some(w.clone());
        let ready=[0x0d,8,0,0,0,0,0,3,0,16,9,0x8d,5,0,2,1,0,0,0,0x86,0,0,0x0c,8,0,0,0,0,0,0,0,0,0];
        rejoin.receive(&frame(&rejoin,&ready),now).unwrap();poll(&mut rejoin,&mut w,now).unwrap();
        assert_eq!(rejoin.shared.as_ref().unwrap().shot_cursor,1);assert_eq!(w.actors[0].fire.ammo(),19);
        assert!(!queued_bodies(&rejoin,now).contains(&wire::shooting(0).unwrap()));
    }
    #[test] fn publication_failure_does_not_commit_shot_ammo_or_event_cursor() {
        let now=Instant::now();let (mut a,_,mut w)=visible_pair(now);
        a.receive(&frame(&a,&[0x88,0,0]),now).unwrap();
        a.outbox.push_back(vec![0;513]);
        assert!(poll(&mut a,&mut w,now).is_err());
        assert_eq!(w.actors[0].fire.ammo(),20);assert!(w.shots.is_empty());
        assert_eq!(a.shared.as_ref().unwrap().shot_cursor,0);assert_eq!(a.tx.len(),0);
    }
    #[test] fn real_channel_clone_rejects_late_poison_without_partial_input_or_ack() {
        let now = Instant::now(); let (mut s,_) = driving(now);
        let mut payload = vec![0x8a,1,0,1,3];
        payload.extend(wire::vehicle_id(1).unwrap().to_le_bytes()); payload.extend([0;17]);
        let f = frame(&s,&payload);
        assert!(s.receive(&f,now).is_err()); assert_eq!(s.rx,1);
        assert!(s.shared.as_ref().unwrap().commands.is_empty()); assert!(s.received.is_empty());
        let mut f = frame(&s,&[0x88,0,0]); f.body[1]^=1;
        assert!(s.receive(&f,now).is_err()); assert_eq!(s.rx,1);
        let mut parent = frame(&s,&[0xff]); parent.sequence=Some(2);
        parent.piggybacks.push(frame(&s,&[0x88,0,0]));
        assert!(s.receive(&parent,now).is_err()); assert_eq!(s.rx,1);
        assert!(s.shared.as_ref().unwrap().commands.is_empty());
    }
    #[test] fn reliable_shot_duplicate_consumes_once_and_cannot_move_the_other_actor() {
        let now = Instant::now(); let (mut s,mut world) = driving(now);
        let f = frame(&s,&[0x88,0,0,0x8a,1,0,1]);
        s.receive(&f,now).unwrap(); assert_eq!(s.rx,2);
        poll(&mut s,&mut world,now).unwrap(); assert_eq!(world.actors[0].fire.ammo(),19);
        s.receive(&f,now).unwrap(); poll(&mut s,&mut world,now).unwrap();
        assert_eq!(world.actors[0].fire.ammo(),19); assert_eq!(world.actors[1].fire.ammo(),20);
        assert_eq!(world.actors[1].input,model::Input::STOP);
        assert_eq!(world.actors[0].input.throttle,1);
    }
    #[test] fn second_actor_telemetry_is_checked_then_discarded() {
        let now = Instant::now(); let (mut s,world) = driving(now);
        let c=s.shared.as_mut().unwrap(); c.slot=1; c.view=Some(world);
        let mut payload=vec![3];payload.extend(wire::vehicle_id(1).unwrap().to_le_bytes());
        payload.extend(99999f32.to_le_bytes());payload.extend([0;13]);
        s.receive(&frame(&s,&payload),now).unwrap();
        assert!(s.shared.as_ref().unwrap().commands.is_empty());
        payload[1..5].copy_from_slice(&wire::vehicle_id(0).unwrap().to_le_bytes());
        assert!(s.receive(&frame(&s,&payload),now).is_err());
    }
    #[test] fn captured_native_stop_before_correction_is_atomic_and_nonzero_stays_gated() {
        let now=Instant::now();let (mut s,_)=driving(now);
        s.shared.as_mut().unwrap().correction=false;
        assert!(s.receive(&frame(&s,&[0x8a,1,0,1,6]),now).is_err());
        assert!(!s.shared.as_ref().unwrap().correction);
        s.receive(&frame(&s,&[0x8a,1,0,0,6]),now).unwrap();
        assert!(s.shared.as_ref().unwrap().correction);
        assert_eq!(s.shared.as_ref().unwrap().commands,vec![model::Command::Move(model::Input::STOP)]);
        let (mut s,_)=driving(now);let c=s.shared.as_mut().unwrap();c.correction=false;c.binding=Some((0,false));
        assert!(s.receive(&frame(&s,&[0x8a,1,0,0,6]),now).is_err());
        assert!(s.shared.as_ref().unwrap().commands.is_empty());
    }
    #[test] fn reservations_cover_all_live_sessions_before_accepting_auth() {
        let now = Instant::now(); let mut t = Table::default();
        for i in 1..31 { t.retirement.retire(LoginAttempt::new([i;16], i as u32, peer(31000 + i as u16)), None, now).unwrap(); }
        t.sessions.push(session(80, now));
        let candidate = LoginAttempt::new([81;16], 81, peer(32081)); t.admissible(&candidate, now).unwrap();
        t.sessions.push(session(81, now));
        assert!(t.admissible(&LoginAttempt::new([82;16], 82, peer(32082)), now).is_err());
        for s in &t.sessions { t.retirement.retire(s.login_attempt.unwrap(), None, now).unwrap(); }
        assert_eq!(t.retirement.retained_count(), MAX_RETIRED);
    }
    #[test] fn route_never_tries_another_key_or_rebinds_a_live_peer() {
        let now = Instant::now(); let mut t = Table::default(); t.sessions = vec![session(1,now),session(2,now)];
        t.sessions[0].base_peer = Some(peer(33001)); t.sessions[1].base_peer = Some(peer(33002));
        assert_eq!(t.route(peer(33001), &[0;24]).unwrap(), 0);
        assert_eq!(t.route(peer(33002), &[0;24]).unwrap(), 1);
        assert!(t.route(peer(33003), &[0;24]).is_err());
        let mut handshake = vec![1,0,0,8,0]; handshake.extend(1u32.to_le_bytes()); handshake.extend([0,0]);
        handshake.extend(t.sessions[1].handoff.to_le_bytes()); handshake.extend(0u32.to_le_bytes()); handshake.extend([2,0]);
        assert!(t.route(peer(33001), &handshake).is_err());
        assert!(t.route(peer(33003), &handshake).is_err());
        assert_eq!(t.route(peer(33002), &handshake).unwrap(), 1);
        assert!(base::decrypt(&base::encrypt(&transport091::ack(1), &t.sessions[0].key).unwrap(), &t.sessions[1].key).is_err());
    }
    #[test] fn retire_one_keeps_other_channel_and_rejects_its_old_attempt() {
        let now = Instant::now(); let mut world = model::tests::world(now); let mut t = Table::default();
        t.sessions = vec![session(1,now),session(2,now)]; let old = t.sessions[0].login_attempt.unwrap();
        let other = (t.sessions[1].key,t.sessions[1].token,t.sessions[1].handoff);
        t.retire(1,&mut world,now,"test_disconnect").unwrap();
        assert_eq!(t.sessions.len(),1); assert_eq!(t.sessions[0].id,2);
        assert_eq!((t.sessions[0].key,t.sessions[0].token,t.sessions[0].handoff),other);
        assert!(t.admissible(&old,now).is_err()); assert!(world.actors[0].session.is_none());
        assert_eq!(world.actors[1].session,Some(2));
    }
}
