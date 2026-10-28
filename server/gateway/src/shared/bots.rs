//! BOT-01 server bots. A bot is an arena participant without a client and
//! without an account: it owns its actor through a synthetic session that no
//! gateway Session can have, and drives it through the same `World::apply`
//! a native player's packets reach. Physics, visibility, reload, ammunition,
//! aiming rates and damage are therefore the player's. The behaviour below is
//! explicit PROJECT policy, not a reconstruction of any historical bot.
use super::*;
use std::f32::consts::PI;

pub const POLICY: &str = "project.bot01.route-hold-visible-aim.v1";
/// Synthetic bot sessions are `SESSION_BASE + slot`. The gateway refuses a
/// login before its own session counter could reach this band.
pub const SESSION_BASE: u32 = 0xB000_0000;
/// Synthetic native database ids start here; ids already used in the battle
/// are skipped (a battle never holds two equal ids).
const DATABASE_BASE: i32 = 0x7F00_0000;
/// Engagement range: the original spotting `max_detection_m` of the rules.
const ENGAGE_M: f32 = 445.;
const WAYPOINT_M: f32 = 25.;
const HOLD_M: f32 = 20.;
const STEER_DEADBAND: f32 = 8. * PI / 180.;
const TURN_IN_PLACE: f32 = 60. * PI / 180.;
const SPACING_M: f32 = 14.;
const SPACING_CONE: f32 = 35. * PI / 180.;
const STUCK_TICKS: u16 = 30;
const UNSTICK_TICKS: u16 = 15;
const STUCK_SPEED: f32 = 0.6;
/// Playable-area inset; the client's `playable_bounds_xz` stay 40 m away.
const BOUNDS_INSET_M: f32 = 40.;
/// Bot aim circle: sigma(t) = SIGMA0 * (1 + 3 e^(-t/aiming_time)) radians.
const SIGMA0: f32 = 0.004;
const SETTLE_TURRET: f32 = 2. * PI / 180.;
const AIM_TOLERANCE: f32 = 0.3 * PI / 180.;
/// Aim at the hull, not the ground point under it (project constant).
const AIM_HEIGHT_M: f32 = 1.2;
const STATS_TICKS: u32 = 100;
/// Steering probes (project policy): a hull-wide corridor along candidate
/// headings, re-cast every PROBE_TICKS; offsets tried from the goal bearing.
const PROBE_TICKS: u32 = 3;
const PROBE_M: f32 = 14.;
const PROBE_HALF_WIDTH_M: f32 = 1.7;
const PROBE_HEIGHT_M: f32 = 1.0;
const PROBE_OFFSETS_DEG: [f32; 9] = [0., 25., -25., 50., -50., 75., -75., 105., -105.];
/// A vehicle standing still blocks a corridor like an obstacle.
const STANDING_MPS: f32 = 1.;
/// After a stuck reversal: a side point off the blocked bearing, kept until
/// reached or expired; the third stuck at one spot drops the waypoint.
const DETOUR_M: f32 = 30.;
const DETOUR_DEG: f32 = 80.;
const DETOUR_TICKS: u32 = 80;
const DETOUR_REACHED_M: f32 = 8.;
const STUCK_SPOT_M: f32 = 12.;
/// Lead: the target's ground velocity (smoothed position delta), bounded.
const LEAD_MAX_MPS: f32 = 25.;
/// Distinct bot vehicle kinds in one plan (curated five plus generated ones).
pub const MAX_KINDS: usize = 16;
/// The own sight line to the target is re-cast at most every 0.5 s.
const LINE_RECHECK_TICKS: u32 = 5;
/// A target the team shows but this bot cannot see for 2 s: keep advancing
/// along the route (turret on the target) instead of waiting behind a hill.
const BLOCKED_ADVANCE_TICKS: u32 = 20;

/// Client `arena_defs` playable bounds (min x, min z, max x, max z) carried by
/// the MAPS-01 packages' `arena.json` `playable_bounds_xz` (see BOT01 plan).
fn playable_bounds(asset: &str) -> Option<[f32; 4]> {
    match asset {
        "01_karelia" | "02_malinovka" | "05_prohorovka" => Some([-500., -500., 500., 500.]),
        _ => None,
    }
}

/// Explicit gateway configuration of the bots of every arena.
#[derive(Clone, Debug, PartialEq)]
pub struct Plan { pub human_places: usize, pub seed: u64, pub kinds: Vec<VehicleKind> }
impl Plan {
    pub fn validate(&self, places: usize) -> io::Result<()> {
        if !(1..places).contains(&self.human_places) || places > MAX_ACTORS || self.kinds.is_empty()
            || self.kinds.len() > MAX_KINDS || self.kinds.iter().any(|k| k.is_extended())
            || self.kinds.iter().enumerate().any(|(i, k)| self.kinds[..i].contains(k)) { return Err(bad()); }
        Ok(())
    }
}

#[derive(Clone, Debug, PartialEq)]
struct Brain {
    slot: usize, rng: u64, route: Vec<[f32; 2]>, waypoint: usize,
    stuck: u16, unstick: u16, unstick_steer: i8,
    target: Option<usize>, settle_tick: u32, error: [f32; 2], turret_yaw: f32,
    sent_input: Input, sent_aim: Option<aim::Intent>,
    /// Own sight line to the target: (enemy, tick cast, clear, blocked since).
    line: Option<(usize, u32, bool, u32)>,
    /// Steering: preferred avoidance side (+1 left/-1 right of the goal
    /// bearing), offset chosen at `probe_tick`, side point after a stuck.
    side: f32, avoid: f32, probe_tick: u32, detour: Option<([f32; 2], u32)>,
    /// Last stuck place and how many times in a row it was there.
    stuck_spot: Option<([f32; 2], u8)>,
    /// Lead: (target, tick, last position, smoothed velocity).
    track: Option<(usize, u32, [f32; 3], [f32; 3])>,
}

#[derive(Clone, Debug, PartialEq)]
pub(crate) struct Bots { plan: Arc<Plan>, brains: Vec<Brain>, last_tick: Option<u32>, digest: u64, shots: u32,
    /// Engaged decisions without a shot: [not aimed, aiming time, reload/ammo, terrain line].
    held: [u32; 4],
    /// Stuck reversals (each starts a side detour).
    stucks: u32,
    /// Wall time spent in bot decisions (diagnostic only; not in the digest).
    think_ns: u64 }

fn splitmix(state: &mut u64) -> u64 {
    *state = state.wrapping_add(0x9E37_79B9_7F4A_7C15);
    let mut z = *state;
    z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    z ^ (z >> 31)
}
fn unit(state: &mut u64) -> f32 { (splitmix(state) >> 40) as f32 / (1u64 << 24) as f32 }
/// Uniform point in the unit disc.
fn disc(state: &mut u64) -> [f32; 2] {
    let (r, a) = (unit(state).sqrt(), unit(state) * 2. * PI);
    [r * a.cos(), r * a.sin()]
}
fn fnv(mut hash: u64, bytes: &[u8]) -> u64 {
    for b in bytes { hash ^= u64::from(*b); hash = hash.wrapping_mul(0x0000_0100_0000_01B3); }
    hash
}
fn distance(a: [f32; 2], b: [f32; 2]) -> f32 { (a[0] - b[0]).hypot(a[1] - b[1]) }
fn clamp_box(p: [f32; 2], b: [f32; 4]) -> [f32; 2] { [p[0].clamp(b[0], b[2]), p[1].clamp(b[1], b[3])] }
fn inside(p: [f32; 2], b: [f32; 4]) -> bool { (b[0]..=b[2]).contains(&p[0]) && (b[1]..=b[3]).contains(&p[1]) }

impl World {
    /// Bind the bot plan to a template World before any actor attaches.
    pub fn enable_bots(&mut self, plan: Plan) -> io::Result<()> {
        plan.validate(self.expected_actors)?;
        if self.bots.is_some() || self.started.is_some() || !self.actors.is_empty() || !self.mixed_profiles
            || self.extended_lab || self.owner_hold || self.lifecycle.is_none() || self.terrain.is_none()
            || self.map.spec().ctf_bases.is_none() || playable_bounds(self.map.asset()).is_none() { return Err(bad()); }
        for kind in &plan.kinds {
            // BATTLE-ANY generated kinds only ride mixed-ammo battles (typed gun).
            if kind.is_generated() && !self.mixed_ammo { return Err(bad()); }
            self.geometry_for(*kind)?;
        }
        self.bots = Some(Bots { plan: Arc::new(plan), brains: Vec::new(), last_tick: None, digest: 0xcbf2_9ce4_8422_2325, shots: 0, held: [0; 4], stucks: 0, think_ns: 0 });
        Ok(())
    }
    pub fn bot_plan(&self) -> Option<&Plan> { self.bots.as_ref().map(|b| b.plan.as_ref()) }
    /// Places taken by native players; the rest of the roster is bots.
    pub fn human_places(&self) -> usize { self.bots.as_ref().map_or(self.expected_actors, |b| b.plan.human_places) }
    pub fn is_bot(&self, slot: usize) -> bool { self.actors.get(slot).is_some_and(|a| a.bot.is_some()) }
    /// No native player holds a place any more (bots never park).
    pub fn humans_parked(&self) -> bool { self.actors.iter().all(|a| a.bot.is_some() || a.session.is_none()) }
    /// Replay witness: FNV-1a over every bot command batch (tick, slot, commands).
    pub fn bot_digest(&self) -> Option<u64> { self.bots.as_ref().map(|b| b.digest) }
    pub fn bot_shots(&self) -> u32 { self.bots.as_ref().map_or(0, |b| b.shots) }
    pub fn bot_stucks(&self) -> u32 { self.bots.as_ref().map_or(0, |b| b.stucks) }
    /// Wall time of every bot decision so far (bench diagnostics).
    pub fn bot_think_ns(&self) -> u64 { self.bots.as_ref().map_or(0, |b| b.think_ns) }

    /// Fill the roster after the native players' places, in the start turn
    /// before `start`. Atomic: on any error the World is unchanged.
    pub fn fill_bots(&mut self) -> io::Result<usize> {
        let Some(bots) = &self.bots else { return Ok(0); };
        let plan = bots.plan.clone();
        if self.started.is_some() || self.actors.len() != plan.human_places || !bots.brains.is_empty()
            || self.actors.iter().any(|a| a.bot.is_some() || a.session.is_some_and(|s| s >= SESSION_BASE)) { return Err(bad()); }
        let mut next = self.clone();
        let count = self.expected_actors - plan.human_places;
        for ordinal in 0..count {
            let slot = next.actors.len();
            let kind = plan.kinds[(ordinal + (plan.seed % plan.kinds.len() as u64) as usize) % plan.kinds.len()];
            let mut database = DATABASE_BASE.checked_add(ordinal as i32).ok_or_else(bad)?;
            while next.actors.iter().any(|a| a.identity.database == database) { database = database.checked_add(1).ok_or_else(bad)?; }
            let identity = Identity { account: format!("bot01:{ordinal}"), database, name: format!("Bot-{:02}", ordinal + 1) };
            let session = SESSION_BASE.checked_add(slot as u32).ok_or_else(bad)?;
            if next.attach_bot_actor(identity, session, kind)? != slot { return Err(bad()); }
            next.actors[slot].bot = Some(u8::try_from(ordinal).map_err(|_| bad())?);
        }
        let bounds = playable_bounds(self.map.asset()).ok_or_else(bad)?;
        let inner = [bounds[0] + BOUNDS_INSET_M, bounds[1] + BOUNDS_INSET_M, bounds[2] - BOUNDS_INSET_M, bounds[3] - BOUNDS_INSET_M];
        let bases = self.map.spec().ctf_bases.ok_or_else(bad)?;
        let mut brains = Vec::with_capacity(count);
        let mut per_team = [0usize; 2];
        for slot in plan.human_places..next.actors.len() {
            let team = next.team(slot)?;
            let (own, enemy) = (bases[usize::from(team) - 1], bases[2 - usize::from(team)]);
            let k = per_team[usize::from(team) - 1]; per_team[usize::from(team) - 1] += 1;
            let mut rng = plan.seed ^ self.id.rotate_left(17) ^ (slot as u64).wrapping_mul(0x9E37_79B9_7F4A_7C15);
            splitmix(&mut rng);
            let axis = [enemy[0] - own[0], enemy[1] - own[1]];
            let length = axis[0].hypot(axis[1]);
            if !(length > 1.) { return Err(bad()); }
            let perp = [-axis[1] / length, axis[0] / length];
            let lane = 60. * (1 + (k / 2) % 3) as f32 * if k % 2 == 0 { 1. } else { -1. };
            let point = |along: f32, side: f32| clamp_box([own[0] + along * axis[0] + side * perp[0], own[1] + along * axis[1] + side * perp[1]], inner);
            let jitter = disc(&mut rng);
            let route = vec![point(0.35, lane), point(0.6, lane * 0.5),
                clamp_box([enemy[0] + jitter[0] * 25., enemy[1] + jitter[1] * 25.], inner)];
            let error = disc(&mut rng);
            let side = if splitmix(&mut rng) & 1 == 0 { 1. } else { -1. };
            brains.push(Brain { slot, rng, route, waypoint: 0, stuck: 0, unstick: 0, unstick_steer: 0, target: None,
                settle_tick: 1000, error, turret_yaw: 0., sent_input: Input::STOP, sent_aim: None, line: None,
                side, avoid: 0., probe_tick: 0, detour: None, stuck_spot: None, track: None });
        }
        next.bots.as_mut().ok_or_else(bad)?.brains = brains;
        println!("BOT01_FILL battle={} humans={} bots={count} kinds={:?} seed={} policy={POLICY} accounts=none domain_writes=none",
            self.id, plan.human_places, next.actors[plan.human_places..].iter().map(|a| a.vehicle_kind().label()).collect::<Vec<_>>(), plan.seed);
        *self = next;
        Ok(count)
    }
    /// The player's attach path with a server-chosen stock LAB loadout; no
    /// owned receipt, inventory or reservation is created or implied.
    fn attach_bot_actor(&mut self, identity: Identity, session: u32, kind: VehicleKind) -> io::Result<usize> {
        if kind.is_extended() || !self.mixed_profiles || self.extended_lab || kind.is_generated() && !self.mixed_ammo { return Err(bad()); }
        self.geometry_for(kind)?;
        // Mixed ammo: the full stock rack of the first shell on the typed gun,
        // v1 devices, as `attach_owned_v2_inner` seats a player's kind.
        let typed = if self.mixed_ammo {
            let source = crate::p06t_shells091::profile(kind.mount());
            Some(fire::State::with_typed(kind.mount(), [source.capacity, 0, 0], source.shots[0].compact_descr)?)
        } else { None };
        let devices = if self.mixed_ammo {
            Some(crate::p06t_device_state::State::new(crate::p06t_device_caps::Profile::for_owned(kind).ok_or_else(bad)?)?)
        } else { None };
        let (previous, mixed) = (self.vehicle_kind, self.mixed_ammo);
        self.mixed_ammo = false; self.vehicle_kind = kind;
        // A generated kind has no legacy single-stack gun: seat it typed.
        let attached = if kind.is_generated() { self.attach_loadout_fire(identity, session, None, typed.clone()) }
            else { self.attach_loadout(identity, session, None) };
        self.vehicle_kind = previous; self.mixed_ammo = mixed;
        let slot = attached?;
        if let Some(fire) = typed { self.actors[slot].fire = fire; self.actors[slot].devices = devices; }
        Ok(slot)
    }
    /// Bots become ready once the scene has settled (players follow their
    /// own native entry). Returns the number of bots made ready now.
    pub fn ready_bots(&mut self) -> io::Result<usize> {
        if self.started.is_none() { return Err(bad()); }
        let mut count = 0;
        for (slot, actor) in self.actors.iter_mut().enumerate() {
            if actor.bot.is_none() || actor.ready { continue; }
            if actor.session != Some(SESSION_BASE + slot as u32) { return Err(bad()); }
            actor.ready = true; count += 1;
        }
        if count > 0 { println!("BOT01_READY battle={} bots={count} tick={}", self.id, self.tick); }
        Ok(count)
    }

    /// One decision per domain tick for every live, ready bot, applied through
    /// the player's `apply`. An error here is a bot bug and fails the arena.
    pub fn drive_bots(&mut self, now: Instant) -> io::Result<usize> {
        let Some(state) = &self.bots else { return Ok(0); };
        if self.started.is_none() || state.brains.is_empty() || state.last_tick == Some(self.tick) { return Ok(0); }
        let mut state = state.clone();
        state.last_tick = Some(self.tick);
        if self.lifecycle.as_ref().is_some_and(|l| !l.allows_actions()) { self.bots = Some(state); return Ok(0); }
        let mut issued = 0;
        let clock = std::time::Instant::now();
        for index in 0..state.brains.len() {
            let slot = state.brains[index].slot;
            let actor = self.actors.get(slot).ok_or_else(bad)?;
            if actor.bot.is_none() || !actor.ready || !actor.alive() { continue; }
            let (commands, aimed_for) = self.think(&mut state.brains[index], now, &mut state.held)?;
            if state.brains[index].unstick == UNSTICK_TICKS { state.stucks = state.stucks.saturating_add(1); }
            if commands.is_empty() { continue; }
            let outcomes = self.apply(slot, SESSION_BASE + slot as u32, &commands, now)?;
            let shot = outcomes.iter().any(|o| matches!(o, fire::Outcome::AcceptedShot { .. }
                | fire::Outcome::Typed(crate::p06t_armament091::Outcome::Shot { .. })));
            if shot {
                state.shots = state.shots.saturating_add(1);
                if let Some((target, metres, aim_s)) = aimed_for {
                    println!("BOT01_FIRE battle={} slot={slot} target={target} tick={} distance_m={metres:.0} aim_s={aim_s:.1}", self.id, self.tick);
                }
            }
            state.digest = fnv(state.digest, format!("{}:{slot}:{commands:?}:{outcomes:?};", self.tick).as_bytes());
            issued += 1;
        }
        state.think_ns = state.think_ns.saturating_add(u64::try_from(clock.elapsed().as_nanos()).unwrap_or(u64::MAX));
        if self.tick % STATS_TICKS == 0 {
            let alive = state.brains.iter().filter(|b| self.actors[b.slot].alive()).count();
            let engaged = state.brains.iter().filter(|b| b.target.is_some() && self.actors[b.slot].alive()).count();
            let hits = self.damage_events.iter().filter(|e| self.is_bot(e.attacker)).count()
                + self.impacts.iter().filter(|e| self.is_bot(e.attacker)).count();
            println!("BOT01_STATS battle={} tick={} bots={} alive={alive} engaged={engaged} shots={} damage_rows={hits} held_aim={} held_settle={} held_reload={} held_terrain={} stucks={} think_ms={:.0}",
                self.id, self.tick, state.brains.len(), state.shots, state.held[0], state.held[1], state.held[2], state.held[3], state.stucks, state.think_ns as f64 / 1e6);
        }
        self.bots = Some(state);
        Ok(issued)
    }

    /// Pure decision from this World snapshot and the bot's own RNG.
    fn think(&self, brain: &mut Brain, now: Instant, held: &mut [u32; 4]) -> io::Result<(Vec<Command>, Option<(usize, f32, f32)>)> {
        let slot = brain.slot;
        let actor = &self.actors[slot];
        let team = self.team(slot)?;
        let here = [actor.position[0], actor.position[2]];
        // What a native player in this place is sent: the team's spotting.
        // The initialized spotting row is the published one; asking
        // desired_visibility would rebuild every actor's points per bot.
        let visible = match &self.original_spotting {
            Some(state) if state.initialized() => state.desired(slot)?,
            _ => self.desired_visibility(slot)?,
        };
        let mut target: Option<(usize, f32)> = None;
        for (other, enemy) in self.actors.iter().enumerate() {
            if other == slot || !visible[other] || self.team(other)? == team || !enemy.alive() { continue; }
            let d = distance(here, [enemy.position[0], enemy.position[2]]);
            if d <= ENGAGE_M && target.is_none_or(|(_, best)| d < best) { target = Some((other, d)); }
        }
        // Keep the current target while it stays a valid choice and no other
        // is much closer: switching restarts the aim (no flapping).
        if let (Some(current), Some((_, best))) = (brain.target, target) {
            let enemy = &self.actors[current];
            let d = distance(here, [enemy.position[0], enemy.position[2]]);
            if visible[current] && enemy.alive() && d <= ENGAGE_M && d <= best * 1.25 { target = Some((current, d)); }
        }
        let bounds = playable_bounds(self.map.asset()).ok_or_else(bad)?;
        let inner = [bounds[0] + BOUNDS_INSET_M, bounds[1] + BOUNDS_INSET_M, bounds[2] - BOUNDS_INSET_M, bounds[3] - BOUNDS_INSET_M];
        // Own line to the target's hull (cached): the team may show a target
        // this bot cannot hit from where it stands.
        let hold = match target {
            None => { brain.line = None; false },
            Some((enemy, _)) => {
                let fresh = brain.line.filter(|(e, at, _, _)| *e == enemy && self.tick.saturating_sub(*at) < LINE_RECHECK_TICKS);
                let (clear, since) = match fresh {
                    Some((_, _, clear, since)) => (clear, since),
                    None => {
                        let p = self.actors[enemy].position;
                        let clear = self.bot_line_clear(actor, [p[0], p[1] + AIM_HEIGHT_M, p[2]])?;
                        let since = match brain.line { Some((e, _, false, since)) if e == enemy && !clear => since, _ => self.tick };
                        brain.line = Some((enemy, self.tick, clear, since));
                        (clear, since)
                    },
                };
                clear || self.tick.saturating_sub(since) < BLOCKED_ADVANCE_TICKS
            },
        };
        let input = if target.is_some() && hold {
            brain.stuck = 0; brain.unstick = 0; Input::STOP
        } else if brain.unstick > 0 {
            brain.unstick -= 1; Input { throttle: -1, steer: brain.unstick_steer, speed_percent: 100 }
        } else {
            while brain.waypoint + 1 < brain.route.len() && distance(here, brain.route[brain.waypoint]) < WAYPOINT_M { brain.waypoint += 1; }
            if brain.detour.is_some_and(|(point, until)| self.tick >= until || distance(here, point) < DETOUR_REACHED_M) { brain.detour = None; }
            let outside = !inside(here, inner);
            let route_goal = if outside { clamp_box([0.5 * (inner[0] + inner[2]), 0.5 * (inner[1] + inner[3])], inner) } else { brain.route[brain.waypoint] };
            let goal = brain.detour.map_or(route_goal, |(point, _)| point);
            if !outside && brain.detour.is_none() && brain.waypoint + 1 == brain.route.len() && distance(here, goal) < HOLD_M {
                brain.stuck = 0; Input::STOP
            } else {
                let bearing = (goal[0] - here[0]).atan2(goal[1] - here[1]);
                if self.tick >= brain.probe_tick + PROBE_TICKS || self.tick < brain.probe_tick {
                    brain.probe_tick = self.tick;
                    let length = (PROBE_M + 1.5 * actor.speed.abs()).min(distance(here, goal).max(4.));
                    let mut chosen = None;
                    for offset in PROBE_OFFSETS_DEG {
                        let offset = offset.to_radians() * brain.side;
                        if self.bot_corridor_clear(slot, bearing + offset, length)? { chosen = Some(offset); break; }
                    }
                    // Boxed in: turn hard away on the preferred side; the stuck rule backs out.
                    brain.avoid = chosen.unwrap_or(135f32.to_radians() * brain.side);
                }
                let desired = bearing + brain.avoid;
                let error = aim::wrap(desired - actor.yaw);
                let steer = if error > STEER_DEADBAND { 1 } else if error < -STEER_DEADBAND { -1 } else { 0 };
                let mut throttle = if error.abs() > TURN_IN_PLACE { 0 } else { 1 };
                // A moving ally ahead: wait; a standing one is steered around (corridor).
                let blocked = self.actors.iter().enumerate().any(|(other, ally)| {
                    if other == slot || !ally.alive() || ally.speed.abs() < STANDING_MPS || self.team(other).ok() != Some(team) { return false; }
                    let to = [ally.position[0] - here[0], ally.position[2] - here[1]];
                    let d = to[0].hypot(to[1]);
                    d < SPACING_M && aim::wrap(to[0].atan2(to[1]) - actor.yaw).abs() < SPACING_CONE
                });
                if blocked { throttle = 0; }
                if throttle == 1 && actor.speed.abs() < STUCK_SPEED { brain.stuck += 1; } else { brain.stuck = 0; }
                if brain.stuck >= STUCK_TICKS {
                    brain.stuck = 0; brain.unstick = UNSTICK_TICKS;
                    let repeats = match brain.stuck_spot { Some((spot, n)) if distance(spot, here) < STUCK_SPOT_M => n.saturating_add(1), _ => 1 };
                    brain.stuck_spot = Some((here, repeats));
                    // Same spot again: try the other side; the third time give up this waypoint.
                    if repeats >= 2 { brain.side = -brain.side; }
                    if repeats >= 3 && brain.waypoint + 1 < brain.route.len() { brain.waypoint += 1; brain.stuck_spot = None; }
                    let away = (route_goal[0] - here[0]).atan2(route_goal[1] - here[1]) + DETOUR_DEG.to_radians() * brain.side;
                    brain.detour = Some((clamp_box([here[0] + DETOUR_M * away.sin(), here[1] + DETOUR_M * away.cos()], inner),
                        self.tick + UNSTICK_TICKS as u32 + DETOUR_TICKS));
                    // Reverse turning the nose toward the detour side.
                    brain.unstick_steer = if brain.side > 0. { -1 } else { 1 };
                    brain.avoid = 0.; brain.probe_tick = self.tick;
                }
                Input { throttle, steer, speed_percent: 100 }
            }
        };
        let mut commands = Vec::new();
        if input != brain.sent_input { commands.push(Command::Move(input)); brain.sent_input = input; }
        let turret_moved = aim::wrap(actor.aim.yaw - brain.turret_yaw).abs() > SETTLE_TURRET;
        brain.turret_yaw = actor.aim.yaw;
        let mut aimed_for = None;
        let intent = if let Some((enemy, metres)) = target {
            if brain.target != Some(enemy) { brain.target = Some(enemy); brain.settle_tick = self.tick; brain.error = disc(&mut brain.rng); }
            if turret_moved || actor.speed.abs() > 0.5 { brain.settle_tick = self.tick; }
            let aim_s = self.tick.saturating_sub(brain.settle_tick) as f32 * 0.1;
            let tau = actor.vehicle_kind().aim().aiming_time;
            let sigma = SIGMA0 * (1. + 3. * (-aim_s / tau).exp()) * metres;
            let observed = self.actors[enemy].position;
            // Smoothed ground velocity of the target from its positions on consecutive ticks.
            let velocity = match brain.track {
                Some((e, tick, last, v)) if e == enemy && tick + 1 == self.tick => {
                    let raw = [(observed[0] - last[0]) / 0.1, 0., (observed[2] - last[2]) / 0.1];
                    let next = [0.5 * (v[0] + raw[0]), 0., 0.5 * (v[2] + raw[2])];
                    if next[0].hypot(next[2]) > LEAD_MAX_MPS { [0.; 3] } else { next }
                },
                Some((e, tick, _, v)) if e == enemy && tick == self.tick => v,
                _ => [0.; 3],
            };
            brain.track = Some((enemy, self.tick, observed, velocity));
            let shell = actor.fire.typed().map(|state| state.current());
            let flight_mps = shell.map_or(actor.vehicle_kind().shell().speed(), |s| s.speed_mps as f32);
            let p = lead_point(actor.position, observed, velocity, flight_mps);
            let line = [p[0] - actor.position[0], p[2] - actor.position[2]];
            let length = line[0].hypot(line[1]).max(1.);
            let side = [-line[1] / length, line[0] / length];
            let point = [p[0] + side[0] * brain.error[0] * sigma, p[1] + AIM_HEIGHT_M + brain.error[1] * sigma * 0.5,
                p[2] + side[1] * brain.error[0] * sigma];
            let (yaw, pitch) = aim::solve_for(actor.vehicle_kind(), actor.position, actor.direction, point, actor.aim.yaw, actor.aim.pitch, shell);
            let (min, max) = aim::pitch_limits_for(actor.vehicle_kind(), actor.aim.yaw)?;
            let aimed = aim::wrap(yaw - actor.aim.yaw).abs() < AIM_TOLERANCE && (pitch - actor.aim.pitch).abs() < AIM_TOLERANCE
                && (min..=max).contains(&pitch);
            let reloaded = actor.fire.reload_until().is_none_or(|until| until <= now) && actor.fire.ammo() > 0
                && actor.devices.as_ref().is_none_or(|d| d.capabilities().can_fire);
            let sighted = brain.line.is_some_and(|(e, _, clear, _)| e == enemy && clear);
            let clear = aimed && reloaded && aim_s >= tau && sighted;
            if !clear { held[if !aimed { 0 } else if aim_s < tau { 1 } else if !reloaded { 2 } else { 3 }] += 1; }
            if clear {
                commands.push(Command::Fire(fire::Command::Shoot));
                brain.error = disc(&mut brain.rng);
                aimed_for = Some((enemy, metres, aim_s));
            }
            aim::Intent::Point(point)
        } else {
            brain.target = None;
            aim::Intent::Hold { yaw: 0., pitch: 0. }
        };
        let changed = match (brain.sent_aim, intent) {
            (Some(aim::Intent::Point(a)), aim::Intent::Point(b)) => (0..3).any(|i| (a[i] - b[i]).abs() > 0.25),
            (old, new) => old != Some(new),
        };
        if changed {
            // Aim precedes Fire so the shot leaves along the current state.
            let at = commands.iter().position(|c| matches!(c, Command::Fire(_))).unwrap_or(commands.len());
            commands.insert(at, Command::Aim(intent)); brain.sent_aim = Some(intent);
        }
        Ok((commands, aimed_for))
    }
    /// Steering probe: two hull-edge rays at probe height clear static
    /// obstacles (ground ignored: slopes are driven), and no standing or dead
    /// vehicle lies in the corridor.
    fn bot_corridor_clear(&self, slot: usize, heading: f32, length: f32) -> io::Result<bool> {
        let terrain = self.terrain.as_ref().ok_or_else(bad)?;
        let actor = &self.actors[slot];
        let (forward, left) = ([heading.sin(), heading.cos()], [heading.cos(), -heading.sin()]);
        let excluded = self.spotting_excluded()?;
        for edge in [-PROBE_HALF_WIDTH_M, PROBE_HALF_WIDTH_M] {
            let start = [actor.position[0] + left[0] * edge, actor.position[1] + PROBE_HEIGHT_M, actor.position[2] + left[1] * edge];
            let end = [start[0] + forward[0] * length, start[1], start[2] + forward[1] * length];
            if terrain.obstacle_t(start, end, &excluded)?.is_some() { return Ok(false); }
        }
        Ok(!self.actors.iter().enumerate().any(|(other, vehicle)| {
            if other == slot || vehicle.alive() && vehicle.speed.abs() >= STANDING_MPS { return false; }
            let to = [vehicle.position[0] - actor.position[0], vehicle.position[2] - actor.position[2]];
            let along = to[0] * forward[0] + to[1] * forward[1];
            let across = to[0] * left[0] + to[1] * left[1];
            along > 0. && along < length && across.abs() < 2. * PROBE_HALF_WIDTH_M
        }))
    }
    /// The bot does not fire into a hill: the sight line to its aim point must
    /// clear the terrain (same query and exclusions as spotting).
    fn bot_line_clear(&self, actor: &Actor, point: [f32; 3]) -> io::Result<bool> {
        let terrain = self.terrain.as_ref().ok_or_else(bad)?;
        let excluded = self.spotting_excluded()?;
        Ok(!terrain.any_hit_excluding_many(Self::visibility_sight_point(actor), point, &excluded)?)
    }
}

/// Where the target will be when a shell fired now arrives: two fixed-point
/// refinements of the flight time over the straight distance (project policy).
fn lead_point(shooter: [f32; 3], target: [f32; 3], velocity: [f32; 3], flight_mps: f32) -> [f32; 3] {
    if !(flight_mps > 1.) { return target; }
    let mut point = target;
    for _ in 0..2 {
        let d = ((point[0] - shooter[0]).powi(2) + (point[1] - shooter[1]).powi(2) + (point[2] - shooter[2]).powi(2)).sqrt();
        let t = d / flight_mps;
        point = [target[0] + velocity[0] * t, target[1] + velocity[1] * t, target[2] + velocity[2] * t];
    }
    point
}

#[cfg(test)]
#[path = "bots_tests.rs"]
pub(crate) mod tests;
