//! Bounded two-session native dispatcher. Authentication and channel replay
//! policy are shared with the accepted gateway; no unauthenticated lab login.
use super::{model::{self, World}, ap, impact_wire, terrain_wire, wire, Client, Phase};
use super::super::*;

#[derive(Default)]
struct Table { sessions: Vec<Session>, retirement: RetirementWindow }

/// Owns one accepted P05 worker per shared actor. The handles live outside
/// `World` because `World` is cloned for atomic packet application; cloning a
/// worker would duplicate process authority. Every imported row is copied into
/// the next world snapshot only after the worker contract has validated it.
struct IntegratedRuntime {
    pool: Arc<crate::map_drive_worker091::Pool>,
    workers: [Option<crate::map_drive_worker091::Worker>; model::CAPACITY],
    poses: [Option<([f32; 3], [f32; 3], f32)>; model::CAPACITY],
    offsets: [[f32; 3]; model::CAPACITY],
    anchored: [bool; model::CAPACITY],
    dispatched: [Option<Instant>; model::CAPACITY],
    started: bool,
}

/// A worker frame may be compared with a client frame in focused tests, but an
/// integrated session now starts each worker at its own map lane. Only the
/// tiny settle drift from that requested lane is anchored. Applying the old
/// cross-terrain X/Z translation would retain a different terrain height while
/// keeping worker Y, which was the airborne-tank bug.
fn worker_frame_offset(client_spawn: [f32; 3], worker_spawn: [f32; 3]) -> [f32; 3] {
    [client_spawn[0] - worker_spawn[0], 0., client_spawn[2] - worker_spawn[2]]
}

fn worker_frame_position(worker_position: [f32; 3], offset: [f32; 3]) -> [f32; 3] {
    [worker_position[0] + offset[0], worker_position[1], worker_position[2] + offset[2]]
}

impl IntegratedRuntime {
    fn new(pool: Arc<crate::map_drive_worker091::Pool>) -> Self {
        Self { pool, workers: std::array::from_fn(|_| None), poses: [None; model::CAPACITY],
            offsets: [[0.; 3]; model::CAPACITY],
            anchored: [false; model::CAPACITY],
            dispatched: [None; model::CAPACITY], started: false }
    }

    fn map(&self) -> io::Result<crate::map_drive_worker091::MapSpec> {
        self.pool.maps.iter().find(|candidate| candidate.asset == "01_karelia"
            && candidate.arena_type_id == 1).cloned().ok_or_else(model::bad)
    }

    fn lane_spawn(map: &crate::map_drive_worker091::MapSpec, slot: usize) -> [f32; 3] {
        [map.spawn[0] + if slot == 0 { -4. } else { 4. }, map.spawn[1], map.spawn[2]]
    }

    fn spawn_slot(&mut self, world_id: u64, slot: usize, map: crate::map_drive_worker091::MapSpec,
        now: Instant) -> io::Result<()> {
        if self.workers[slot].is_some() { return Err(model::bad()); }
        let lane = Self::lane_spawn(&map, slot);
        self.offsets[slot] = [0.; 3];
        self.anchored[slot] = false;
        self.dispatched[slot] = None;
        let worker = crate::map_drive_worker091::Worker::launch_at_spawn(self.pool.clone(), map.clone(),
            u32::try_from(slot + 1).map_err(|_| model::bad())?, now, Some(lane))?;
        println!("SHARED_INTEGRATED_WORKER_START battle={} slot={} map={} arena_type_id={} config_sha256={} pool_sha256={} physics=test_lab coordinate_bridge=worker_lane_full_pose_bridge=position_ypr spawn_override={:?} offset={:?}",
            world_id, slot, map.asset, map.arena_type_id, map.config_sha256, self.pool.sha256, lane, self.offsets[slot]);
        self.workers[slot] = Some(worker);
        Ok(())
    }

    fn start(&mut self, world: &mut World, now: Instant) -> io::Result<()> {
        if self.started || world.actors.len() != model::CAPACITY || world.started.is_none() { return Err(model::bad()); }
        // The native wire currently advertises Karelia (space_id=1). Do not
        // let an arbitrary pool ordering silently pair that wire with another
        // map; fail closed until the protocol carries an explicit map choice.
        let map = self.map()?;
        let lane_spawns = std::array::from_fn(|slot| {
            Self::lane_spawn(&map, slot)
        });
        // Native announcements are emitted later in this same loop. Rebase
        // before that happens so no old flat-lab spawn can reach the client.
        world.rebase_external_spawns(lane_spawns)?;
        for slot in 0..model::CAPACITY {
            self.spawn_slot(world.id, slot, map.clone(), now)?;
        }
        self.started = true;
        Ok(())
    }

    fn ready_for_native(&self) -> bool {
        self.workers.iter().all(|worker| worker.as_ref().is_some_and(|value| value.ready()))
    }

    fn step(&mut self, world: &mut World, now: Instant) -> io::Result<()> {
        if world.started.is_none() { return Ok(()); }
        let mut rows = Vec::new();
        for slot in 0..model::CAPACITY {
            if world.actors.get(slot).and_then(|a| a.session).is_none() {
                self.workers[slot].take(); self.poses[slot] = None; self.anchored[slot] = false;
                self.dispatched[slot] = None;
                if let Some(actor) = world.actors.get(slot) {
                    rows.push((slot,actor.position,actor.direction,0.));
                }
                continue;
            }
            if self.workers[slot].is_none() {
                let map = self.map()?;
                world.reset_external_spawn(slot, Self::lane_spawn(&map, slot))?;
                self.spawn_slot(world.id, slot, map, now)?;
            }
            let worker = self.workers[slot].as_mut().ok_or_else(model::bad)?;
            if let Some(state) = worker.poll(now)? {
                if state.seq == 0 {
                    let actor = world.actors.get(slot).ok_or_else(model::bad)?;
                    self.offsets[slot] = worker_frame_offset(actor.position, state.pose.position);
                    self.anchored[slot] = true;
                    println!("SHARED_INTEGRATED_WORKER_READY battle={} slot={} process_id={} map={} worker_tick={} settled_position={:?} direction={:?} contacts={} wheel_contact_masks={:?} anchor_offset={:?}",
                        world.id, slot, worker.process_id().ok_or_else(model::bad)?, worker.map.asset,
                        state.tick, state.pose.position, state.pose.direction, state.pose.contacts, state.pose.wheel_contact_masks,
                        self.offsets[slot]);
                }
                if !self.anchored[slot] { return Err(model::bad()); }
                let position = worker_frame_position(state.pose.position, self.offsets[slot]);
                if position.iter().any(|v| !v.is_finite()) || state.pose.direction.iter().any(|v| !v.is_finite()) {
                    return Err(model::bad());
                }
                self.poses[slot] = Some((position, state.pose.direction, state.pose.speed));
                rows.push((slot, position, state.pose.direction, state.pose.speed));
            } else if let Some((position, direction, speed)) = self.poses[slot] {
                rows.push((slot, position, direction, speed));
            }
        }
        for slot in 0..model::CAPACITY {
            if world.actors.get(slot).and_then(|a| a.session).is_none() { continue; }
            let worker = self.workers[slot].as_mut().ok_or_else(model::bad)?;
            if worker.ready() && !worker.pending()
                && self.dispatched[slot].is_none_or(|sent| now.duration_since(sent) >= crate::map_drive_worker091::STEP) {
                let actor = world.actors.get(slot).ok_or_else(model::bad)?;
                let input = crate::map_drive_worker091::Input { throttle: actor.input.throttle,
                    steer: actor.input.steer, brake: actor.input.throttle == 0 && actor.input.steer == 0 };
                let seq = worker.advance(input, now)?;
                self.dispatched[slot] = Some(now);
                println!("SHARED_INTEGRATED_WORKER_INPUT battle={} slot={} seq={} throttle={} steer={} brake={}",
                    world.id, slot, seq, input.throttle, input.steer, input.brake);
            }
        }
        // Do not publish a mixed frame while the two workers are settling.
        // The old client-space spawn is deliberately not a fallback pose:
        // waiting one bounded loop keeps the second actor from appearing at
        // the laboratory Y for a single tick before its worker is ready.
        if rows.len() != model::CAPACITY {
            return Ok(());
        }
        if world.tick == 1000 && world.actors.iter().any(|actor| actor.session.is_some() && !actor.ready) {
            // The native arena has not completed its ready handshake yet, but
            // its first announcement must still use the settled worker pose.
            // Before first battle both actors must settle; later a reconnect
            // must not freeze the already playing survivor.
            if world.actors.iter().all(|actor| actor.session.is_some()) {
                world.import_external_poses(&rows)?;
            }
            return Ok(());
        }
        world.advance_with_external(now, Some(&rows))?;
        Ok(())
    }
}
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
    serve_with_pool(key_path, digest_path, config_path, capture_path, None, None, false, None)
}

fn terrain_for_pool(pool: &crate::map_drive_worker091::Pool) -> io::Result<Arc<super::terrain::Terrain>> {
    use std::io::Read;
    let map=pool.maps.iter().find(|map|map.asset=="01_karelia" && map.arena_type_id==1).ok_or_else(model::bad)?;
    // Pool load already validated ownership/schema; recheck these exact bytes
    // so a replaced config cannot substitute projectile geometry afterwards.
    let mut raw=Vec::new(); fs::File::open(&map.config)?.take(65537).read_to_end(&mut raw)?;
    if raw.is_empty() || raw.len()>65536 || format!("{:x}",Sha256::digest(&raw))!=map.config_sha256 { return Err(model::bad()); }
    let config:serde_json::Value=serde_json::from_slice(&raw).map_err(|_|model::bad())?;
    if config["terrain"]["sha256"].as_str()!=Some(super::terrain::MANIFEST_SHA256) { return Err(model::bad()); }
    let path=config["terrain"]["path"].as_str().ok_or_else(model::bad)?;
    let terrain=super::terrain::Terrain::load(&pool.local_root,Path::new(path))?;
    // Same original map resources, independently filtered with the original
    // projectile mask128. The vehicle-physics mask18 export is not substituted.
    let obstacle_path=pool.local_root.join("evidence/20261010-p06m-terrain-impact-01/projectile-obstacles01/01_karelia/manifest.json");
    let obstacles=super::obstacles::Obstacles::load(&pool.local_root,&obstacle_path)?;
    Ok(Arc::new(terrain.with_obstacles(Arc::new(obstacles))?))
}

pub fn serve_integrated(key_path: &str, digest_path: &str, config_path: &str,
    pool_path: &str, capture_path: &str, geometry_path: Option<&str>, ap_test_lab: bool, terrain_test_lab: bool) -> Result<(), Box<dyn std::error::Error>> {
    if ap_test_lab && geometry_path.is_none() { return Err(model::bad().into()); }
    if terrain_test_lab && !ap_test_lab { return Err(model::bad().into()); }
    let config = crate::identity091::Config::load(config_path)?;
    let pool = crate::map_drive_worker091::Pool::load(&config.local_root, Path::new(pool_path))?;
    let geometry = geometry_path.map(|path| super::geometry::Bundle::load(&config.local_root, Path::new(path)))
        .transpose()?.map(Arc::new);
    let terrain = if terrain_test_lab { Some(terrain_for_pool(&pool)?) } else { None };
    serve_with_pool(key_path, digest_path, config_path, capture_path, Some(Arc::new(pool)), geometry, ap_test_lab, terrain)
}

fn serve_with_pool(key_path: &str, digest_path: &str, config_path: &str, capture_path: &str,
    integrated_pool: Option<Arc<crate::map_drive_worker091::Pool>>, geometry: Option<Arc<super::geometry::Bundle>>, ap_test_lab: bool,
    terrain: Option<Arc<super::terrain::Terrain>>)
    -> Result<(), Box<dyn std::error::Error>> {
    if ap_test_lab && (integrated_pool.is_none() || geometry.is_none()) { return Err(model::bad().into()); }
    if terrain.is_some() && !ap_test_lab { return Err(model::bad().into()); }
    let config = Arc::new(crate::identity091::Config::load(config_path)?);
    let private = login::load_key(key_path)?;
    if fs::metadata(digest_path)?.len() != 16 { return Err(model::bad().into()); }
    let digest: [u8; 16] = fs::read(digest_path)?.try_into().map_err(|_| model::bad())?;
    let login_socket = UdpSocket::bind(config.login_bind)?;
    let base_socket = UdpSocket::bind(config.base_bind)?;
    login_socket.set_nonblocking(true)?; base_socket.set_nonblocking(true)?;
    let capture_profile = if integrated_pool.is_some() { crate::capture091::Profile::IntegratedWorldV1 }
        else { crate::capture091::Profile::SharedWorldV1 };
    let mut capture = Some(Recorder::open_profile(capture_path, &config.local_root, capture_profile)?);
    let mut table = Table::default();
    let started = Instant::now();
    let mut world = World::new(OsRng.next_u64().max(1), started)?;
    if let Some(bundle) = geometry {
        world.bind_geometry(bundle)?;
        println!("SHARED_GEOMETRY_BOUND battle={} bundle_sha256={} revision={} material_revision={} components=Hull,Turret_01,Gun_02 scope=other_actor_only damage={} terrain_projectiles={}",
            world.id, super::geometry::BUNDLE_SHA256, super::geometry::SOURCE_REVISION, super::materials::PROFILE_REVISION, ap_test_lab, terrain.is_some());
    }
    if ap_test_lab {
        world.enable_ap_test_lab()?;
        println!("SHARED_AP_PROFILE revision={} historical_fidelity={} damage={} rng=false friendly_fire=true persistence=false",
            ap::PROFILE_REVISION, ap::HISTORICAL_FIDELITY, ap::DAMAGE);
    }
    if let Some(terrain) = terrain {
        let revision=terrain.source_revision();
        world.bind_terrain(terrain)?;
        println!("SHARED_TERRAIN_BOUND battle={} revision={} manifest_sha256={} obstacle_manifest_sha256={} map=01_karelia geometry=original_world material=source_kind terrain_only=false obstacles=true projectile_mask=128 tie_policy=world_first_f32_bucket",
            world.id,revision,super::terrain::MANIFEST_SHA256,super::obstacles::MANIFEST_SHA256);
    }
    let mut contact_cursor = 0usize;
    let mut terrain_cursor = 0usize;
    let mut impact_cursor = 0usize;
    let mut integrated = integrated_pool.map(IntegratedRuntime::new);
    let mut next_id = 1u32;
    let mut auth: Option<AuthJob> = None;
    let mut last_auth: Option<Instant> = None;
    let mut fragments = login::LoginFragments::default();
    let mut rate_started = started; let mut rate_count = 0u32;
    println!("BOUND {} base_backend={} profile={} battle={} capacity=2 scope=allied_temporary_ms1 motion={} physics={} inventory_changed=false",
        config.login_bind, config.base_bind,
        if integrated.is_some() { "legacy091-integrated-lab" } else { "legacy091-shared-lab" },
        world.id, if integrated.is_some() { "map_drive_worker" } else { "bounded_kinematic" }, integrated.is_some());
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
        if world.started.is_some() {
            if let Some(runtime) = integrated.as_mut() {
                if !runtime.started { runtime.start(&mut world, now)?; }
                runtime.step(&mut world, now)?;
            } else { world.advance(now)?; }
        }
        let integrated_native_ready = integrated.as_ref().is_none_or(IntegratedRuntime::ready_for_native);
        for s in &mut table.sessions {
            let reason = if now.duration_since(s.created_at) >= config.session_duration { Some("session_deadline") }
                else if now.duration_since(s.last_rx) >= Duration::from_secs(8) { Some("idle_timeout") } else { None };
            if let Some(reason) = reason { closing.push((s.id, reason)); continue; }
            // Keep the transport alive while workers settle, but gate the
            // native arena reset until both workers have supplied a settled
            // pose. This avoids the old outer `continue`, which also skipped
            // heartbeats and made a client look disconnected during startup.
            if let Err(error) = poll_with_native_start(s, &mut world, now, integrated_native_ready) {
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
        for contact in world.contacts.iter().skip(contact_cursor) {
            println!("SHARED_GEOMETRIC_CONTACT {}", serde_json::json!({
                "battle":world.id.to_string(), "shot":contact.shot, "target_slot":contact.target_slot,
                "tick":contact.tick, "segment_start":contact.segment_start, "segment_end":contact.segment_end,
                "segment_seconds":contact.segment_seconds, "endpoint":contact.endpoint,
                "target_position":contact.target_position, "target_direction":contact.target_direction,
                "target_aim":contact.target_aim, "triangle_id":contact.triangle.triangle_id,
                "mesh":contact.triangle.mesh, "group":contact.triangle.group, "material":contact.triangle.material,
                "t":contact.triangle.t, "normal":contact.triangle.normal,
                "geometry_revision":contact.geometry_revision, "transform_revision":contact.transform_revision,
                "material_facts":contact.material_facts.json(),
                "terminal":match world.impacts.iter().find(|event| event.shot==contact.shot).map(|e| &e.outcome) {
                    Some(model::ImpactOutcome::Ap(_)) => "test_lab_impact",
                    Some(model::ImpactOutcome::WreckBlocked) => "test_lab_wreck_impact",
                    None => "unresolved_collision"},
                "damage_applied":world.impacts.iter().any(|event| event.shot==contact.shot && event.health_after<event.health_before)}));
        }
        contact_cursor = world.contacts.len();
        for contact in world.terrain_contacts.iter().skip(terrain_cursor) {
            let (surface,instance_id,material_kind)=match contact.hit.surface {
                super::terrain::Surface::Ground => ("terrain",None,None),
                super::terrain::Surface::StaticObstacle{instance_id,material_kind} =>
                    ("static_obstacle",Some(instance_id),Some(material_kind)),
            };
            println!("SHARED_TERRAIN_CONTACT {}",serde_json::json!({
                "battle":world.id.to_string(),"shot":contact.shot,"shooter":contact.shooter,"tick":contact.tick,
                "triangle_id":contact.hit.triangle_id,"t":contact.hit.t,"endpoint":contact.hit.point,
                "normal":contact.hit.normal,"direction":contact.direction,
                "segment_start":contact.segment_start,"segment_end":contact.segment_end,
                "geometry_revision":if surface=="terrain" {super::terrain::SOURCE_REVISION} else {super::obstacles::SOURCE_REVISION},
                "surface":surface,"instance_id":instance_id,"material_kind":material_kind,
                "effect_material_index":contact.hit.effect_material_index(),"material_policy":contact.hit.material_policy(),
                "damage_applied":false}));
        }
        terrain_cursor=world.terrain_contacts.len();
        for event in world.impacts.iter().skip(impact_cursor) {
            if let model::ImpactOutcome::WreckBlocked = event.outcome {
                println!("SHARED_WRECK_IMPACT {}", serde_json::json!({
                    "battle":world.id.to_string(),"shot":event.shot,"attacker":event.attacker,"target":event.target,"tick":event.tick,
                    "policy_revision":model::WRECK_POLICY_REVISION,"historical_fidelity":"approximate",
                    "outcome":"wreck_blocked","health_before":event.health_before,"health_after":event.health_after,
                    "damage":0,"native_effect_available":event.segment.is_some()}));
                continue;
            }
            let model::ImpactOutcome::Ap(resolution) = &event.outcome else { return Err(model::bad().into()); };
            println!("SHARED_AP_IMPACT {}", serde_json::json!({
                "battle":world.id.to_string(),"shot":event.shot,"attacker":event.attacker,"target":event.target,"tick":event.tick,
                "profile_revision":resolution.profile_revision,"historical_fidelity":ap::HISTORICAL_FIDELITY,
                "outcome":resolution.outcome.label(),"reason":format!("{:?}",resolution.outcome),
                "armor":resolution.armor,"incidence_degrees":resolution.incidence_degrees,
                "normalization_degrees":resolution.normalization_degrees,
                "effective_armor":resolution.effective_armor,"nominal_power":resolution.nominal_power,
                "health_before":event.health_before,"health_after":event.health_after,
                "damage":event.health_before-event.health_after,"native_effect_available":event.segment.is_some()}));
        }
        impact_cursor = world.impacts.len();
        // Both peers receive a snapshot of the same completed server tick.
        for s in &mut table.sessions { if let Some(c) = &mut s.shared { c.view = Some(world.clone()); } }
        thread::sleep(Duration::from_millis(5));
    }
    Ok(())
}

fn poll_with_native_start(s: &mut Session, world: &mut World, now: Instant,
    allow_native_start: bool) -> io::Result<()> {
    if world.started.is_none() { return Ok(()); }
    if allow_native_start && entry_ready(s, now) { s.shared_start(world, now)?; }
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
    let mut tracer_starts = Vec::new();
    let mut tracer_stops = Vec::new();
    let mut impact_publications = Vec::new();
    let prior_projectile_count = world.projectiles.len();
    if c.phase == Phase::Driving {
        for shot in next_world.shots.iter().filter(|shot| shot.sequence > c.shot_cursor).copied().collect::<Vec<_>>() {
            let observable = c.correction && c.binding.is_some_and(|(_, ack)| ack) && c.visible()[shot.slot];
            if observable {
                let index = shot.sequence.checked_sub(1).ok_or_else(model::bad)? as usize;
                let projectile = next_world.projectiles.iter().find(|p| p.sequence == shot.sequence)
                    .ok_or_else(model::bad)?;
                if !c.tracer_started[index] {
                    // Keep the existing native muzzle/sound cue and then send
                    // the original fixed showTracer callback in one reliable
                    // order. The start flag is committed with this clone.
                    next.outbox.push_back(wire::shooting(shot.slot)?);
                    next.outbox.push_back(wire::tracer_start(projectile)?);
                    c.tracer_started[index] = true;
                    tracer_starts.push((shot.sequence, shot.slot));
                }
            }
            // Even a skipped event is consumed: becoming visible later must
            // not replay stale gunfire. The cursor commits with the queue.
            c.shot_cursor = shot.sequence;
            shot_publications.push((shot, observable));
        }
        // Expiry is server-owned. A peer receives a stop only if this exact
        // connection received/queued the corresponding start, so reconnects
        // cannot inherit old effects or produce orphan stops.
        if c.correction && c.binding.is_some_and(|(_, ack)| ack) {
            for projectile in next_world.projectiles.iter().filter(|p| p.stopped) {
                let index = projectile.sequence.checked_sub(1).ok_or_else(model::bad)? as usize;
                if index >= c.tracer_started.len() { return Err(model::bad()); }
                if c.tracer_started[index] && !c.tracer_stopped[index] {
                    if let Some(contact)=next_world.terrain_contacts.iter().find(|c|c.shot==projectile.sequence) {
                        // Original explodeProjectile terminates its own mover.
                        // A subsequent stopTracer would hide/cancel ground FX.
                        next.outbox.push_back(super::terrain_wire::explode_material(projectile.sequence,
                            contact.hit.point,contact.direction,contact.hit.effect_material_index())?);
                    } else {
                        next.outbox.push_back(wire::tracer_stop(projectile)?);
                    }
                    c.tracer_stopped[index] = true;
                    tracer_stops.push((projectile.sequence, projectile.slot));
                }
            }
            for event in next_world.impacts.iter().skip(c.impact_cursor) {
                let shot_index = event.shot.checked_sub(1).ok_or_else(model::bad)? as usize;
                let visible = c.visible()[event.target] && c.visible()[event.attacker];
                let observed_shot = c.tracer_started.get(shot_index).copied().ok_or_else(model::bad)?;
                let mut body = Vec::new();
                if visible && observed_shot {
                    if let Some(segment) = &event.segment {
                        let outcome = match &event.outcome {
                            // Explicit laboratory policy: a wreck blocks the shell.
                            // The native resisted FX also works on HP0 entities;
                            // this is not an armor calculation or a new death.
                            model::ImpactOutcome::WreckBlocked => impact_wire::ShotOutcome::NotPierced,
                            model::ImpactOutcome::Ap(resolution) => match resolution.outcome {
                                ap::Outcome::Ricochet => impact_wire::ShotOutcome::Ricochet,
                                ap::Outcome::NotPierced => impact_wire::ShotOutcome::NotPierced,
                                ap::Outcome::Pierced => impact_wire::ShotOutcome::Pierced,
                                ap::Outcome::Unsupported(_) => return Err(model::bad()),
                            },
                        };
                        let component = match segment.component {
                            super::materials::Component::Hull => 1,
                            super::materials::Component::Turret01 => 2,
                            super::materials::Component::Gun02 => 3,
                        };
                        body.extend(impact_wire::show_damage(event.attacker,event.target,component,
                            segment.bounds,segment.start,segment.end,outcome)?);
                    }
                    if event.health_after < event.health_before
                        && c.health_sent[event.target].is_none_or(|hp| hp > event.health_after) {
                        body.extend(impact_wire::health_changed(event.target,event.health_after,event.attacker)?);
                        c.health_sent[event.target] = Some(event.health_after);
                        if event.target == c.slot {
                            body.extend(impact_wire::owner_health(event.health_after)?);
                            c.owner_health_sent = Some(event.health_after);
                        }
                        if event.health_after == 0 { body.extend(wire::roster(&next_world)?); }
                    }
                }
                let queued = !body.is_empty();
                if queued { next.outbox.push_back(body); }
                impact_publications.push((event.shot,event.target,event.health_after,queued));
                c.impact_cursor += 1;
            }
            // Late creation/reconnect gets current HP, never old effects or
            // an intermediate health value that would resurrect the actor.
            for target in 0..model::CAPACITY {
                if !c.visible()[target] { continue; }
                let hp = next_world.actors[target].health;
                let mut body = Vec::new();
                if c.health_sent[target] != Some(hp) {
                    if hp != 90 {
                        let attacker = next_world.impacts.iter().rev().find(|e| e.target == target)
                            .map(|e| e.attacker).ok_or_else(model::bad)?;
                        body.extend(impact_wire::health_changed(target,hp,attacker)?);
                        if hp == 0 { body.extend(wire::roster(&next_world)?); }
                    }
                    c.health_sent[target] = Some(hp);
                }
                if target == c.slot && hp != 90 && c.owner_health_sent != Some(hp) {
                    body.extend(impact_wire::owner_health(hp)?); c.owner_health_sent = Some(hp);
                }
                if !body.is_empty() { next.outbox.push_back(body); }
            }
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
    // At most40 shots: start cue+tracer+stop+one compound impact, plus
    // bounded reload/readiness/health catch-up. Slow peers cannot grow forever.
    if next.outbox.len() > model::MAX_SHOTS * 4 + 32 { return Err(model::bad()); } next.drain_outbox()?;
    for outcome in outcomes { println!("SHARED_FIRE battle={} session={} slot={slot} outcome={outcome:?}", world.id, s.id); }
    for command in &commands { if let model::Command::Move(input) = command { println!("SHARED_INPUT battle={} session={} slot={slot} input={input:?} client_position_used=false", world.id, s.id); } }
    for command in &commands { if let model::Command::Aim(intent) = command { println!("SHARED_AIM battle={} session={} slot={slot} intent={intent:?} client_angles_authoritative=false", world.id, s.id); } }
    for (shot, delivered) in shot_publications {
        println!("SHARED_SHOT_CUE battle={} session={} shot={} shooter_slot={} tick={} queued={} reason={}",
            world.id, s.id, shot.sequence, shot.slot, shot.tick, delivered,
            if delivered { "visible_native_vehicle" } else { "not_observable_at_event" });
    }
    if next_world.projectiles.len() > prior_projectile_count {
        for projectile in next_world.projectiles.iter().skip(prior_projectile_count) {
            println!("SHARED_PROJECTILE_LAUNCHED battle={} shot={} shooter_slot={} origin={:?} velocity={:?} gravity={} max_distance={} flight_seconds={:.6}",
                world.id, projectile.sequence, projectile.slot, projectile.origin, projectile.velocity,
                projectile.gravity, projectile.max_distance, projectile.flight_time.as_secs_f32());
        }
    }
    for (sequence, shooter_slot) in tracer_starts {
        println!("SHARED_TRACER_START battle={} session={} shot={} shooter_slot={} native_method=Avatar.showTracer queued=true", world.id, s.id, sequence, shooter_slot);
    }
    for (sequence, shooter_slot) in tracer_stops {
        if next_world.terrain_contacts.iter().any(|c|c.shot==sequence) {
            println!("SHARED_TERRAIN_PUBLICATION battle={} session={} shot={} shooter_slot={} native_method=Avatar.explodeProjectile queued=true",world.id,s.id,sequence,shooter_slot);
        } else {
            println!("SHARED_TRACER_STOP battle={} session={} shot={} shooter_slot={} native_method=Avatar.stopTracer queued=true", world.id, s.id, sequence, shooter_slot);
        }
    }
    for (shot,target,hp,queued) in impact_publications {
        println!("SHARED_AP_PUBLICATION battle={} session={} shot={} target={} health={} queued={} historical_fidelity=approximate",
            world.id,s.id,shot,target,hp,queued);
    }
    *world = next_world; *s = next; Ok(())
}

fn poll(s: &mut Session, world: &mut World, now: Instant) -> io::Result<()> {
    poll_with_native_start(s, world, now, true)
}

fn entry_ready(s: &Session, now: Instant) -> bool {
    s.ready_for_arena_base() && s.shared.as_ref().is_some_and(|c| c.phase == Phase::Account
        && c.hangar_since.is_some_and(|start| now.saturating_duration_since(start) >= Duration::from_secs(3)))
}

#[cfg(test)]
mod tests {
    use super::*;
    fn peer(port: u16) -> SocketAddr { SocketAddr::from(([127,0,0,1], port)) }
    #[test]
    fn integrated_worker_bridge_keeps_worker_terrain_height() {
        let client = [-67.499908, 22.416676, -440.81305];
        let worker = [-67.499344, 21.44713, -440.81094];
        let offset = worker_frame_offset(client, worker);
        assert_eq!(offset, [-0.0005645752, 0., -0.0021057129]);

        let bridged = worker_frame_position(worker, offset);
        assert!((bridged[0] - client[0]).abs() < 0.001);
        assert!((bridged[2] - client[2]).abs() < 0.001);
        assert_eq!(bridged[1], worker[1]);
        assert_ne!(bridged[1], client[1]);
    }

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
    #[test] fn terrain_fx_is_once_per_peer_excludes_stop_and_queue_retry_is_atomic() {
        let now=Instant::now(); let (mut a,mut b,_)=visible_pair(now);
        let mut w=model::tests::terrain_world(now,3.);
        a.shared.as_mut().unwrap().commands.push(model::Command::Fire(crate::battle091::fire::Command::Shoot));
        poll(&mut a,&mut w,now).unwrap(); poll(&mut b,&mut w,now).unwrap();
        w.advance(now+model::STEP).unwrap(); assert_eq!(w.terrain_contacts.len(),1);
        let c=&w.terrain_contacts[0]; let fx=terrain_wire::explode(c.shot,c.hit.point,c.direction).unwrap();
        let stop=wire::tracer_stop(&w.projectiles[0]).unwrap();
        let (mut retry,_,_)=visible_pair(now); *retry.shared.as_mut().unwrap()=a.shared.as_ref().unwrap().clone();
        retry.outbox.push_back(vec![0;513]);
        assert!(poll(&mut retry,&mut w,now+model::STEP).is_err());
        assert!(!retry.shared.as_ref().unwrap().tracer_stopped[0]);
        assert_eq!(w.actors[1].health,90); assert!(w.impacts.is_empty());
        retry.outbox.clear();
        for s in [&mut a,&mut b,&mut retry] {
            poll(s,&mut w,now+model::STEP).unwrap();
            let before=queued_bodies(s,now+model::STEP);
            assert_eq!(before.iter().filter(|body|body.windows(fx.len()).any(|bytes|bytes==fx)).count(),1);
            assert!(!before.iter().any(|body|body.windows(stop.len()).any(|bytes|bytes==stop)));
            assert!(s.shared.as_ref().unwrap().tracer_stopped[0]);
            poll(s,&mut w,now+model::STEP).unwrap();
            let after=queued_bodies(s,now+model::STEP);
            assert_eq!(after.iter().filter(|body|body.windows(fx.len()).any(|bytes|bytes==fx)).count(),1);
            assert!(!after.iter().any(|body|body.windows(stop.len()).any(|bytes|bytes==stop)));
        }
    }
    #[test] fn delayed_terrain_fx_follows_tracer_and_reconnect_skips_old_effects() {
        let now=Instant::now(); let (mut a,mut b,_)=visible_pair(now);
        let mut w=model::tests::terrain_world(now,3.);
        w.apply(0,1,&[model::Command::Fire(crate::battle091::fire::Command::Shoot)],now).unwrap();
        w.advance(now+model::STEP).unwrap();
        let c=&w.terrain_contacts[0]; let fx=terrain_wire::explode(c.shot,c.hit.point,c.direction).unwrap();
        let start=wire::tracer_start(&w.projectiles[0]).unwrap();
        for s in [&mut a,&mut b] {
            poll(s,&mut w,now+model::STEP).unwrap(); let raw=queued_bodies(s,now+model::STEP).concat();
            assert!(raw.windows(start.len()).position(|v|v==start).unwrap()<raw.windows(fx.len()).position(|v|v==fx).unwrap());
        }
        let (mut rejoin,_,_)=visible_pair(now+model::STEP);
        rejoin.shared.as_mut().unwrap().shot_cursor=w.latest_shot();
        poll(&mut rejoin,&mut w,now+model::STEP).unwrap();
        assert!(!queued_bodies(&rejoin,now+model::STEP).concat().windows(fx.len()).any(|v|v==fx));
    }
    #[test] fn static_stone_effect_uses_original_material_on_both_peers() {
        let now=Instant::now(); let (mut a,mut b,_)=visible_pair(now);
        let mut w=model::tests::obstacle_world(now,20.,3.);
        w.apply(0,1,&[model::Command::Fire(crate::battle091::fire::Command::Shoot)],now).unwrap();
        w.advance(now+model::STEP).unwrap(); let c=&w.terrain_contacts[0];
        let fx=terrain_wire::explode_material(c.shot,c.hit.point,c.direction,1).unwrap();
        let wrong=terrain_wire::explode(c.shot,c.hit.point,c.direction).unwrap();
        for s in [&mut a,&mut b] {
            poll(s,&mut w,now+model::STEP).unwrap(); let raw=queued_bodies(s,now+model::STEP).concat();
            assert_eq!(raw.windows(fx.len()).filter(|v|*v==fx).count(),1);
            assert!(!raw.windows(wrong.len()).any(|v|v==wrong));
        }
        assert!(w.impacts.is_empty()); assert_eq!(w.actors[1].health,90);
    }
    #[test] fn ap_publication_is_once_per_peer_and_failed_queue_does_not_repeat_damage() {
        let now=Instant::now(); let (mut a,mut b,_) = visible_pair(now);
        let mut w=model::tests::ap_world(now);
        a.shared.as_mut().unwrap().commands.push(model::Command::Fire(crate::battle091::fire::Command::Shoot));
        poll(&mut a,&mut w,now).unwrap(); poll(&mut b,&mut w,now).unwrap();
        w.advance(now+model::STEP).unwrap(); assert_eq!(w.actors[1].health,60);
        // Make the next drain fail after the world has already committed HP.
        let (mut retry,_,_)=visible_pair(now);
        *retry.shared.as_mut().unwrap()=a.shared.as_ref().unwrap().clone();
        retry.outbox.push_back(vec![0;513]);
        assert!(poll(&mut retry,&mut w,now+model::STEP).is_err());
        assert_eq!(retry.shared.as_ref().unwrap().impact_cursor,0);
        assert_eq!(w.actors[1].health,60); assert_eq!(w.impacts.len(),1);
        retry.outbox.clear(); poll(&mut retry,&mut w,now+model::STEP).unwrap();
        for s in [&mut a,&mut b] { poll(s,&mut w,now+model::STEP).unwrap(); }
        let hp=impact_wire::health_changed(1,60,0).unwrap();
        for s in [&mut a,&mut b,&mut retry] {
            let bodies=queued_bodies(s,now+model::STEP);
            assert_eq!(bodies.iter().filter(|body| body.windows(hp.len()).any(|bytes| bytes==hp)).count(),1);
            let before=bodies.into_iter().filter(|body| body.windows(hp.len()).any(|bytes| bytes==hp)).collect::<Vec<_>>();
            poll(s,&mut w,now+model::STEP).unwrap();
            let after=queued_bodies(s,now+model::STEP).into_iter()
                .filter(|body| body.windows(hp.len()).any(|bytes| bytes==hp)).collect::<Vec<_>>();
            assert_eq!(after,before);
            assert_eq!(s.shared.as_ref().unwrap().impact_cursor,1);
        }
        assert_eq!(w.actors[1].health,60);
    }
    #[test] fn ap_late_publication_is_monotone_and_reconnect_only_catches_current_health() {
        let now=Instant::now(); let (mut a,mut b,_) = visible_pair(now);
        let mut w=model::tests::ap_world(now);
        for round in 0..3 {
            let at=now+Duration::from_secs(round*3); if round>0 {w.advance(at).unwrap();}
            w.apply(0,1,&[model::Command::Fire(crate::battle091::fire::Command::Shoot)],at).unwrap();
            w.advance(at+model::STEP).unwrap();
        }
        let at=now+Duration::from_secs(7);
        for s in [&mut a,&mut b] {
            poll(s,&mut w,at).unwrap();
            let all=queued_bodies(s,at).concat(); let mut prior=0;
            for hp in [60,30,0] {
                let bytes=impact_wire::health_changed(1,hp,0).unwrap();
                let at=all.windows(bytes.len()).position(|row| row==bytes).unwrap();
                assert!(at>prior); prior=at;
            }
        }
        let (_,mut rejoin,_)=visible_pair(at);
        rejoin.shared.as_mut().unwrap().impact_cursor=w.impacts.len();
        rejoin.shared.as_mut().unwrap().shot_cursor=w.latest_shot();
        rejoin.shared.as_mut().unwrap().health_sent=[Some(90),Some(0)];
        let creation=wire::create_vehicle(&w,1).unwrap();
        assert!(creation.windows(7).any(|r|r==[3,0,0,4,0,0,5]));
        rejoin.shared.as_mut().unwrap().view=Some(w.clone());
        poll(&mut rejoin,&mut w,at).unwrap();
        assert_eq!(queued_bodies(&rejoin,at),vec![impact_wire::owner_health(0).unwrap()]);
        assert_eq!(w.actors[1].health,0);
    }
    #[test] fn wreck_effect_reaches_both_peers_once_without_health_or_death_replay() {
        let now=Instant::now(); let (mut a,mut b,_) = visible_pair(now);
        let mut w=model::tests::ap_world(now);
        // Kill through real server shots, then fire a fourth shot at the wreck.
        for round in 0..4 {
            let at=now+Duration::from_secs(round*3);
            if round>0 { w.advance(at).unwrap(); }
            w.apply(0,1,&[model::Command::Fire(crate::battle091::fire::Command::Shoot)],at).unwrap();
            for s in [&mut a,&mut b] { poll(s,&mut w,at).unwrap(); }
            w.advance(at+model::STEP).unwrap();
            if round<3 { for s in [&mut a,&mut b] { poll(s,&mut w,at+model::STEP).unwrap(); } }
        }
        let at=now+Duration::from_secs(9)+model::STEP;
        assert_eq!(w.actors[1].health,0); assert_eq!(w.impacts.len(),4);
        let event=w.impacts.last().unwrap();
        assert_eq!(event.outcome,model::ImpactOutcome::WreckBlocked);
        let segment=event.segment.as_ref().unwrap();
        let component=match segment.component {
            super::super::materials::Component::Hull=>1,
            super::super::materials::Component::Turret01=>2,
            super::super::materials::Component::Gun02=>3,
        };
        let fx=impact_wire::show_damage(0,1,component,segment.bounds,segment.start,segment.end,
            impact_wire::ShotOutcome::NotPierced).unwrap();
        let death=impact_wire::health_changed(1,0,0).unwrap();
        for s in [&mut a,&mut b] {
            let previous=queued_bodies(s,at);
            let death_count=previous.iter().filter(|body| body.windows(death.len()).any(|v|v==death)).count();
            let owner_health=s.shared.as_ref().unwrap().owner_health_sent;
            assert_eq!(s.shared.as_ref().unwrap().impact_cursor,3);
            poll(s,&mut w,at).unwrap();
            let first=queued_bodies(s,at);
            assert_eq!(first.iter().filter(|body|**body==fx).count(),1);
            assert_eq!(first.iter().filter(|body|body.windows(death.len()).any(|v|v==death)).count(),death_count);
            assert_eq!(s.shared.as_ref().unwrap().owner_health_sent,owner_health);
            assert_eq!(s.shared.as_ref().unwrap().impact_cursor,4);
            poll(s,&mut w,at).unwrap();
            assert_eq!(queued_bodies(s,at),first);
        }
        let (_,mut rejoin,_)=visible_pair(at);
        let c=rejoin.shared.as_mut().unwrap();
        c.impact_cursor=w.impacts.len(); c.shot_cursor=w.latest_shot();
        c.health_sent=[Some(90),Some(0)]; c.owner_health_sent=Some(0); c.view=Some(w.clone());
        poll(&mut rejoin,&mut w,at).unwrap();
        assert!(queued_bodies(&rejoin,at).is_empty());
        assert_eq!(w.actors[1].health,0);
    }
    fn point(slot:usize,p:[f32;3])->Vec<u8> {
        let mut b=vec![0x0f,16,0];b.extend(wire::vehicle_id(slot).unwrap().to_le_bytes());
        for x in p {b.extend(x.to_le_bytes());} b
    }
    #[test] fn native_postmortem_rebind_is_owned_dead_only_and_keeps_reliable_channel_live() {
        let now=Instant::now(); let (_,mut b,mut w)=visible_pair(now);
        let raw=[0x0d,8,0,0,0,0,0,5,0,0x10,9];
        let before=b.rx; assert!(b.receive(&frame(&b,&raw),now).is_err()); assert_eq!(b.rx,before);
        w.actors[1].health=0; b.shared.as_mut().unwrap().view=Some(w.clone());
        b.receive(&frame(&b,&raw),now).unwrap(); assert_eq!(b.rx,before+1);
        b.receive(&frame(&b,&[]),now).unwrap(); assert_eq!(b.rx,before+2);
        assert!(b.shared.as_ref().unwrap().commands.is_empty());
        for offset in [1,3,7] {
            let mut bad=raw; bad[offset]^=1;
            let before=b.rx; assert!(b.receive(&frame(&b,&bad),now).is_err()); assert_eq!(b.rx,before);
        }
        assert_eq!(w.actors[1].health,0); assert_eq!(b.shared.as_ref().unwrap().slot,1);
    }
    #[test] fn integrated_native_gate_keeps_account_session_alive_until_worker_ready() {
        let now = Instant::now();
        let (mut s, mut world) = driving(now);
        s.arena_base = false;
        s.base_peer = Some(peer(34001));
        s.sync_mask = 7;
        let client = s.shared.as_mut().unwrap();
        client.phase = Phase::Account;
        client.hangar_since = Some(now - Duration::from_secs(3));

        // A settling worker must not trigger the native arena reset yet.
        poll_with_native_start(&mut s, &mut world, now, false).unwrap();
        assert_eq!(s.shared.as_ref().unwrap().phase, Phase::Account);

        // Once both workers are ready, the same session may enter the arena.
        poll_with_native_start(&mut s, &mut world, now, true).unwrap();
        assert_eq!(s.shared.as_ref().unwrap().phase, Phase::Enable);
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
        let tracer=wire::tracer_start(&w.projectiles[0]).unwrap();
        assert_eq!(queued_bodies(&a,now).iter().filter(|body| **body==cue).count(),1);
        assert_eq!(queued_bodies(&b,now),vec![cue.clone(),tracer.clone()]);
        let rejected=frame(&a,&[0x88,0,0]);a.receive(&rejected,now).unwrap();poll(&mut a,&mut w,now).unwrap();
        assert_eq!(w.shots.len(),1);
        b.receive(&frame(&b,&[0x88,0,0]),now).unwrap();poll(&mut b,&mut w,now).unwrap();poll(&mut a,&mut w,now).unwrap();
        assert_eq!(w.shots.len(),2);
        for s in [&a,&b] {assert_eq!(queued_bodies(s,now).iter().filter(|body| **body==wire::shooting(1).unwrap()).count(),1);}
    }
    #[test] fn server_owned_flight_stops_each_delivered_tracer_once() {
        let now=Instant::now(); let (mut a,mut b,mut w)=visible_pair(now);
        a.receive(&frame(&a,&[0x88,0,0]),now).unwrap();
        poll(&mut a,&mut w,now).unwrap(); poll(&mut b,&mut w,now).unwrap();
        let end=w.projectiles[0].end_at().unwrap();
        w.advance(end + Duration::from_millis(100)).unwrap();
        assert!(w.projectiles[0].stopped);
        poll(&mut a,&mut w,end + Duration::from_millis(100)).unwrap();
        poll(&mut b,&mut w,end + Duration::from_millis(100)).unwrap();
        let stop=wire::tracer_stop(&w.projectiles[0]).unwrap();
        for s in [&a,&b] { assert_eq!(queued_bodies(s,end).iter().filter(|body| **body==stop).count(),1); }
        poll(&mut a,&mut w,end + Duration::from_millis(200)).unwrap();
        poll(&mut b,&mut w,end + Duration::from_millis(200)).unwrap();
        for s in [&a,&b] { assert_eq!(queued_bodies(s,end + Duration::from_millis(200)).iter().filter(|body| **body==stop).count(),1); }
    }
    #[test] fn projectile_continues_after_shooter_disconnect_and_rejoin_does_not_replay() {
        let now=Instant::now(); let (mut a,_,mut w)=visible_pair(now);
        a.receive(&frame(&a,&[0x88,0,0]),now).unwrap(); poll(&mut a,&mut w,now).unwrap();
        let start_body = wire::tracer_start(&w.projectiles[0]).unwrap();
        let end=w.projectiles[0].end_at().unwrap();
        w.detach(1).unwrap();
        w.advance(end + Duration::from_millis(100)).unwrap();
        assert!(w.projectiles[0].stopped);
        w.attach(w.actors[0].identity.clone(),3).unwrap();
        let (mut rejoin,_) = driving(now); rejoin.id=3;
        let c=rejoin.shared.as_mut().unwrap(); c.phase=Phase::Entities; c.correction=false;
        c.binding=None; c.creations=[Some((0,true));2]; c.view=Some(w.clone());
        let ready=[0x0d,8,0,0,0,0,0,3,0,16,9,0x8d,5,0,2,1,0,0,0,0x86,0,0,0x0c,8,0,0,0,0,0,0,0,0,0];
        rejoin.receive(&frame(&rejoin,&ready),end + Duration::from_millis(100)).unwrap();
        poll(&mut rejoin,&mut w,end + Duration::from_millis(100)).unwrap();
        assert_eq!(rejoin.shared.as_ref().unwrap().shot_cursor,1);
        let bodies = queued_bodies(&rejoin,end + Duration::from_millis(100));
        assert!(bodies.iter().all(|body| *body != start_body));
    }
    #[test] fn contact_before_peer_poll_still_delivers_start_then_stop_once() {
        let now = Instant::now(); let (mut a, mut b, _) = visible_pair(now);
        let mut w = model::tests::collision_world(now, false);
        a.shared.as_mut().unwrap().view = Some(w.clone());
        b.shared.as_mut().unwrap().view = Some(w.clone());
        a.receive(&frame(&a, &[0x88,0,0]), now).unwrap(); poll(&mut a, &mut w, now).unwrap();
        w.advance(now+model::STEP).unwrap(); assert_eq!(w.contacts.len(),1);
        // Receiver has not polled since before launch; first observation is terminal.
        poll(&mut b, &mut w, now+model::STEP).unwrap();
        let start = wire::tracer_start(&w.projectiles[0]).unwrap();
        let stop = wire::tracer_stop(&w.projectiles[0]).unwrap();
        let bodies = queued_bodies(&b,now+model::STEP);
        assert!(bodies.iter().position(|b| *b==start).unwrap() < bodies.iter().position(|b| *b==stop).unwrap());
        poll(&mut b, &mut w, now+model::STEP).unwrap();
        let bodies = queued_bodies(&b,now+model::STEP);
        assert_eq!(bodies.iter().filter(|b| **b==start).count(),1);
        assert_eq!(bodies.iter().filter(|b| **b==stop).count(),1);
    }
    #[test] fn projectile_creation_failure_rolls_back_fire_ammo_and_history() {
        let now=Instant::now(); let (_,_,mut w)=visible_pair(now);
        let before=w.clone();
        w.actors[0].aim.yaw=f32::NAN;
        assert!(w.apply(0,1,&[model::Command::Fire(crate::battle091::fire::Command::Shoot)],now).is_err());
        assert_eq!(w.actors[0].fire,before.actors[0].fire);
        assert!(w.shots.is_empty()); assert!(w.projectiles.is_empty());
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
        assert_eq!(queued_bodies(&b,later),vec![wire::shooting(0).unwrap(), wire::tracer_start(&w.projectiles[1]).unwrap()]);
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
