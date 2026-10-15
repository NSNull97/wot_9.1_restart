//! Small P08B persistence handoff. Session parsing only clones `State`;
//! external writer calls start after the complete native transaction commits.
//! A `Job` owns its immutable task independently of the session table.
use std::{io, sync::{Arc, atomic::{AtomicBool, Ordering}, mpsc}, thread::{self, JoinHandle}};
use crate::{ammo_service091, hangar091, identity091};
use crate::battle091::profile13::{self, Context, FinishReason, Reply, ReplyStatus, Request, Reservation, ReservationStatus};
use super::model::World;

const MAX_COMMANDS: u32 = 512;
static WORKER_ACTIVE: AtomicBool = AtomicBool::new(false);
fn bad(message: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, format!("profile13 session: {message}"))
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct State {
    pub(super) run_id: String,
    pub(super) revision: u64,
    pub(super) selection: Option<u32>,
    pub(super) reservation: Option<Reservation>,
    pub(super) pending_return: Option<Terminal>,
    pub(super) in_flight: bool,
    pub(super) command_counter: u32,
    pub(super) stale_envelopes: u8,
}
impl State {
    pub(crate) fn garage_idle(&self) -> bool {
        self.selection.is_none() && self.reservation.is_none() && self.pending_return.is_none() && !self.in_flight
    }
    pub(super) fn new(run_id: String, revision: u64) -> io::Result<Self> {
        let context = Context { account_id: "12345678-1234-4234-8234-123456789abc".into(), native_database_id: 1,
            command_key: "p08b:validate".into(), expected_revision: revision, run_id: run_id.clone() };
        profile13::encode_request(&context, &Request::RunOpen)?;
        Ok(Self { run_id, revision, selection: None, reservation: None, pending_return: None,
            in_flight: false, command_counter: 0, stale_envelopes: 0 })
    }
    /// A retry retains the returned Context. Calling this again creates a new
    /// command and must never replace an ambiguous old writer operation.
    pub(super) fn next_context(&mut self, owner: &identity091::Profile, session: u32) -> io::Result<Context> {
        if session == 0 || self.in_flight || self.command_counter >= MAX_COMMANDS {
            return Err(bad("service command bound or operation in flight"));
        }
        let counter = self.command_counter + 1;
        let context = Context { account_id: owner.account_id.clone(), native_database_id: owner.database_id,
            command_key: format!("p08b:{}:{session}:{counter}", self.run_id),
            expected_revision: self.revision, run_id: self.run_id.clone() };
        profile13::encode_request(&context, &Request::Inspect)?;
        self.command_counter = counter;
        Ok(context)
    }
    /// First terminal cause wins. A subsequent disconnect can refer to the
    /// same frozen snapshot, but must not change its AP or HP after authority
    /// has already been revoked.
    pub(super) fn retain_terminal(&mut self, terminal: Terminal) -> io::Result<bool> {
        terminal.validate()?;
        if self.reservation.as_ref() != Some(&terminal.reservation) || terminal.reservation.run_id != self.run_id {
            return Err(bad("terminal is not this client's reservation"));
        }
        if let Some(existing) = &self.pending_return {
            if existing.reservation != terminal.reservation || existing.remaining_ap != terminal.remaining_ap
                || existing.terminal_hp != terminal.terminal_hp {
                return Err(bad("conflicting terminal snapshot"));
            }
            return Ok(false);
        }
        self.pending_return = Some(terminal);
        self.selection = None;
        self.stale_envelopes = 0;
        Ok(true)
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(super) struct Terminal {
    pub(super) reservation: Reservation,
    pub(super) remaining_ap: u16,
    pub(super) terminal_hp: i16,
    pub(super) reason: FinishReason,
    pub(super) results_json: Option<String>,
    pub(super) native_database_id: i32,
}
impl Terminal {
    fn validate(&self) -> io::Result<()> {
        let row = &self.reservation;
        let account = row.vehicle_inventory_id.get(..36).ok_or_else(|| bad("terminal owner"))?;
        row.frozen.validate_owned(account)?;
        if row.status != ReservationStatus::Active || row.result.is_some() || row.battle == 0
            || row.native_inventory_id != row.frozen.native_inventory_id
            || row.vehicle_inventory_id != row.frozen.vehicle_inventory_id
            || self.remaining_ap > row.frozen.ap_count || !(0..=row.frozen.max_hp).contains(&self.terminal_hp) {
            return Err(bad("terminal reservation or authoritative outcome"));
        }
        if (self.reason==FinishReason::BattleFinished)!=self.results_json.is_some() {return Err(bad("natural finish requires its result snapshot"));}
        profile13::encode_request(&Context { account_id: account.into(), native_database_id: self.native_database_id,
            command_key: "p08b:validate".into(), expected_revision: 13, run_id: row.run_id.clone() }, &self.request())?;
        Ok(())
    }
    /// Capture before Leave/detach/reset. Native entity IDs do not enter the
    /// outcome; the world checks this slot's authenticated session authority.
    pub(super) fn from_actor(reservation: &Reservation, world: &World, slot: usize, session: u32,
        reason: FinishReason) -> io::Result<Self> {
        Self::from_actor_result(reservation,world,slot,session,reason,None)
    }
    pub(super) fn from_actor_result(reservation: &Reservation, world: &World, slot: usize, session: u32,
        reason: FinishReason,result:Option<&super::lifecycle_wire::Results>) -> io::Result<Self> {
        let actor = world.owned(slot, session)?;
        reservation.frozen.validate_owned(&actor.identity.account)?;
        if world.id != reservation.battle || !world.mixed_profiles() && world.vehicle_kind() != reservation.frozen.kind
            || actor.vehicle_kind() != reservation.frozen.kind {
            return Err(bad("terminal actor battle/profile mismatch"));
        }
        let terminal = Self { reservation: reservation.clone(), remaining_ap: actor.fire.ammo(),
            terminal_hp: actor.health, reason, native_database_id:actor.identity.database,
            results_json:result.map(serde_json::to_string).transpose().map_err(|_|bad("natural result serialization"))? };
        terminal.validate()?;
        Ok(terminal)
    }
    /// A reserved queue that never created a world actor has spent no AP and
    /// entered with the writer's fully repaired source health.
    pub(super) fn cancelled(reservation: &Reservation) -> io::Result<Self> {
        let terminal = Self { reservation: reservation.clone(), remaining_ap: reservation.frozen.ap_count,
            terminal_hp: reservation.frozen.max_hp, reason: FinishReason::Cancelled, results_json:None, native_database_id:1 };
        terminal.validate()?;
        Ok(terminal)
    }
    pub(super) fn request(&self) -> Request {
        if let Some(results_json)=&self.results_json {
            return Request::FinishResults {battle:self.reservation.battle,native_inventory_id:self.reservation.native_inventory_id,
                reservation_id:self.reservation.reservation_id.clone(),remaining_ap:self.remaining_ap,terminal_hp:self.terminal_hp,
                results_json:results_json.clone()};
        }
        Request::Finish { battle: self.reservation.battle, native_inventory_id: self.reservation.native_inventory_id,
            reservation_id: self.reservation.reservation_id.clone(), remaining_ap: self.remaining_ap,
            terminal_hp: self.terminal_hp, reason: self.reason }
    }
}

pub(super) struct Fresh {
    pub(super) owner: Arc<identity091::Profile>,
    pub(super) fixtures: Arc<hangar091::Fixtures>,
    pub(super) binding: ammo_service091::Metadata,
}
pub(super) struct Completion {
    pub(super) session: u32,
    pub(super) old_owner: Arc<identity091::Profile>,
    pub(super) context: Context,
    pub(super) request: Request,
    pub(super) reply: Reply,
    pub(super) fresh: Option<Fresh>,
    /// A known durable reply must survive a subsequent projection/read failure.
    /// Keep authority closed and recover the projection, never repeat a new
    /// admission key simply because the Account snapshot could not be loaded.
    pub(super) refresh_error: Option<io::Error>,
}

fn work(session: u32, owner: Arc<identity091::Profile>, config: Arc<identity091::Config>,
    context: Context, request: Request) -> io::Result<Completion> {
    let reply = config.battle(&owner, &context, &request)?;
    let refresh = matches!(reply.status, ReplyStatus::Ready | ReplyStatus::Admitted | ReplyStatus::Finished);
    let (fresh, refresh_error) = if refresh {
        let result = (|| -> io::Result<Fresh> {
            let fresh = config.refresh_battle_profile(&owner)?;
            let fixtures = hangar091::Fixtures::load_research(&fresh.fixture_dir)?;
            let binding = ammo_service091::metadata_research(&fresh.fixture_dir, &fresh.account_id, fresh.database_id)?;
            if binding.revision != reply.revision || binding.wire_revision != 1 {
                return Err(bad("fresh projection does not match committed revision"));
            }
            Ok(Fresh { owner: Arc::new(fresh), fixtures: Arc::new(fixtures), binding })
        })();
        match result { Ok(fresh) => (Some(fresh), None), Err(error) => (None, Some(error)) }
    } else { (None, None) };
    Ok(Completion { session, old_owner: owner, context, request, reply, fresh, refresh_error })
}

fn report_result(session: u32, operation: &str, result: &io::Result<Completion>) {
    match result {
        Ok(value) => {
            println!("P08B_WRITER_JOB_RESULT session={session} operation={operation} status={:?} revision={} refreshed={} refresh_failed={} native_delivery=not_yet_dispatched",
                value.reply.status, value.reply.revision, value.fresh.is_some(), value.refresh_error.is_some());
            if let Some(error)=&value.refresh_error {println!("P08B_WRITER_REFRESH_ERROR session={session} operation={operation} error={error} durable_reply_retained=true");}
        },
        Err(error) => println!("P08B_WRITER_JOB_ERROR session={session} operation={operation} error={error} outcome_requires_recovery=true native_delivery=not_yet_dispatched"),
    }
}

pub(super) struct Job {
    pub(super) session: u32,
    pub(super) owner: Arc<identity091::Profile>,
    pub(super) context: Context,
    pub(super) request: Request,
    receiver: Option<mpsc::Receiver<io::Result<Completion>>>,
    worker: Option<JoinHandle<()>>,
}
impl Job {
    pub(super) fn start(session: u32, owner: Arc<identity091::Profile>, config: Arc<identity091::Config>,
        context: Context, request: Request) -> io::Result<Self> {
        profile13::encode_request(&context, &request)?;
        if session == 0 || context.account_id != owner.account_id || context.native_database_id != owner.database_id
            || !config.profile13_battle || context.run_id != config.battle_run_id {
            return Err(bad("job authenticated owner/run"));
        }
        if WORKER_ACTIVE.compare_exchange(false, true, Ordering::AcqRel, Ordering::Acquire).is_err() {
            return Err(bad("another battle writer call is still active"));
        }
        let (sender, receiver) = mpsc::sync_channel(1);
        let (task_owner, task_context, task_request) = (owner.clone(), context.clone(), request.clone());
        let operation = request.operation();
        let started = thread::Builder::new().name("p08b-account-writer".into()).spawn(move || {
            struct Active;
            impl Drop for Active { fn drop(&mut self) { WORKER_ACTIVE.store(false, Ordering::Release); } }
            let _active = Active;
            let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(||
                work(session, task_owner, config, task_context, task_request)))
                .unwrap_or_else(|_| Err(bad("writer thread panicked; outcome requires recovery")));
            // Log before publication as well as returning the typed result.
            // This closes the receiver-drop/send race: a successful send can
            // otherwise be discarded concurrently without either side seeing
            // its error. No credentials or raw response bodies enter this log.
            report_result(session,operation,&result);
            if sender.send(result).is_err() {println!("P08B_JOB_OBSERVER_RETIRED session={session} operation={operation} durable_ledger_retained=true");}
        });
        let worker = match started { Ok(worker) => worker, Err(error) => {
            WORKER_ACTIVE.store(false, Ordering::Release); return Err(error);
        }};
        Ok(Self { session, owner, context, request, receiver: Some(receiver), worker: Some(worker) })
    }
    fn join_finished(&mut self) -> io::Result<()> {
        if self.worker.as_ref().is_some_and(|worker| worker.is_finished()) {
            if self.worker.take().ok_or_else(|| bad("missing writer handle"))?.join().is_err() {
                return Err(bad("writer join panicked; outcome requires recovery"));
            }
        }
        Ok(())
    }
    pub(super) fn poll(&mut self) -> Option<io::Result<Completion>> {
        // Receiving a value can precede the worker's final guard drop. Wait
        // until it has actually returned before allowing the dispatcher to
        // start its next single-writer job in this same UDP iteration.
        if self.worker.as_ref().is_some_and(|worker|!worker.is_finished()) {return None;}
        let receiver = self.receiver.as_ref()?;
        let result = match receiver.try_recv() {
            Ok(result) => result,
            Err(mpsc::TryRecvError::Empty) => return None,
            Err(mpsc::TryRecvError::Disconnected) => Err(bad("writer channel ended without outcome; recover transaction")),
        };
        self.receiver = None;
        if let Err(error) = self.join_finished() { return Some(Err(error)); }
        Some(result)
    }
}
impl Drop for Job {
    fn drop(&mut self) {
        // Never block the UDP loop waiting for bounded-but-slow HTTP. If its
        // owner stops observing, the producer already reports its exact final
        // outcome before attempting delivery. Run fencing and the
        // durable ledger retain authority; dropping a handle is no cancellation.
        drop(self.receiver.take());
        if let Err(error) = self.join_finished() {
            println!("P08B_JOB_DROP_ERROR session={} error={error}", self.session);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn reservation() -> Reservation {
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../tests/fixtures/profile13-writer-vectors.json");
        let vectors: serde_json::Value = serde_json::from_slice(&std::fs::read(path).unwrap()).unwrap();
        let row = &vectors["vectors"][2]; let input = &row["request"];
        let context = Context { account_id: input["account_id"].as_str().unwrap().into(),
            native_database_id: input["native_database_id"].as_i64().unwrap() as i32,
            command_key: input["command_key"].as_str().unwrap().into(), expected_revision: input["expected_revision"].as_u64().unwrap(),
            run_id: input["run_id"].as_str().unwrap().into() };
        profile13::parse_reply(&serde_json::to_vec(&row["response"]).unwrap(), &context,
            &Request::Admit { battle: 1, native_inventory_id: 1 }).unwrap().reservation.unwrap()
    }
    fn owner(row: &Reservation) -> identity091::Profile {
        identity091::Profile { account_id: row.vehicle_inventory_id[..36].into(), database_id: 1,
            name: "owned-test".into(), fixture_dir: std::path::PathBuf::new() }
    }
    #[test] fn profile13_session_context_clone_counter_bound_and_failed_check_are_atomic() {
        let row = reservation(); let owner = owner(&row);
        let mut state = State::new(row.run_id.clone(), 16).unwrap(); let initial = state.clone();
        assert!(state.garage_idle());state.selection=Some(1);assert!(!state.garage_idle());state.selection=None;
        assert!(state.next_context(&owner, 0).is_err()); assert_eq!(state, initial);
        let first = state.next_context(&owner, 7).unwrap(); let mut clone = state.clone();
        let second = clone.next_context(&owner, 7).unwrap();
        assert_ne!(first.command_key, second.command_key); assert_eq!(first.expected_revision, 16);
        assert_eq!(state.command_counter, 1); assert_eq!(clone.command_counter, 2);
        assert!(first.command_key.len() <= 96);
        state.in_flight = true; assert!(state.next_context(&owner, 7).is_err());
        state.in_flight = false; state.command_counter = MAX_COMMANDS; assert!(state.next_context(&owner, 7).is_err());
        assert!(State::new("bad-run".into(), 16).is_err()); assert!(State::new(row.run_id, 12).is_err());
    }
    #[test] fn profile13_terminal_captures_owned_ap_hp_before_detach_and_deduplicates() {
        let row = reservation(); let owner = owner(&row); let now = std::time::Instant::now();
        let mut world = World::new(row.battle, now).unwrap();
        world.attach_owned(super::super::model::Identity { account: owner.account_id.clone(), database: 1,
            name: owner.name.clone() }, 7, &row.frozen).unwrap();
        world.actors[0].fire.apply(&[crate::battle091::fire::Command::Shoot], now).unwrap(); world.actors[0].health = 23;
        let terminal = Terminal::from_actor(&row, &world, 0, 7, FinishReason::ManualLeave).unwrap();
        assert_eq!((terminal.remaining_ap, terminal.terminal_hp), (19, 23));
        assert!(Terminal::from_actor(&row, &world, 0, 8, FinishReason::Disconnect).is_err());
        world.detach(7).unwrap(); assert!(Terminal::from_actor(&row, &world, 0, 7, FinishReason::Disconnect).is_err());
        assert_eq!((terminal.remaining_ap, terminal.terminal_hp), (19, 23));
        let mut state = State::new(row.run_id.clone(), 16).unwrap(); state.reservation = Some(row);
        assert!(state.retain_terminal(terminal.clone()).unwrap());
        let mut repeated = terminal.clone(); repeated.reason = FinishReason::Disconnect;
        assert!(!state.retain_terminal(repeated).unwrap()); assert_eq!(state.pending_return, Some(terminal.clone()));
        let before = state.clone(); let mut conflicting = terminal; conflicting.remaining_ap -= 1;
        assert!(state.retain_terminal(conflicting).is_err()); assert_eq!(state, before);
    }
    #[test] fn profile13_cancelled_reservation_preserves_all_ap_and_checks_bounds() {
        let row = reservation(); let terminal = Terminal::cancelled(&row).unwrap();
        assert_eq!((terminal.remaining_ap, terminal.terminal_hp), (20, 90));
        assert_eq!(terminal.reason, FinishReason::Cancelled);
        let mut changed = terminal.clone(); changed.remaining_ap += 1; assert!(changed.validate().is_err());
        changed = terminal; changed.terminal_hp = 91; assert!(changed.validate().is_err());
    }
    #[test] fn profile13_job_poll_waits_for_worker_exit_before_releasing_the_next_dispatch() {
        // Executor-only channel scheduling regression, no HTTP/native claim.
        let row=reservation();let owner=Arc::new(owner(&row));
        let mut state=State::new(row.run_id,16).unwrap();let context=state.next_context(&owner,7).unwrap();
        let (sender,receiver)=mpsc::sync_channel(1);let (release,wait)=mpsc::sync_channel(1);
        let (sent,delivered)=mpsc::sync_channel(1);
        let worker=thread::spawn(move||{
            sender.send(Err(bad("synthetic executor error"))).unwrap();sent.send(()).unwrap();wait.recv().unwrap();
        });
        delivered.recv().unwrap();
        let mut job=Job{session:7,owner,context,request:Request::Inspect,receiver:Some(receiver),worker:Some(worker)};
        assert!(job.poll().is_none());
        release.send(()).unwrap();job.worker.take().unwrap().join().unwrap();
        let result=job.poll().expect("delivered executor result");assert!(result.is_err());assert!(job.poll().is_none());
    }
}
