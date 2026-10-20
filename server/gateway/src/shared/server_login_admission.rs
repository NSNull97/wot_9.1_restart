//! Per-account native login admission for the shared gateway. Logins of
//! different accounts run their identity jobs concurrently; one account has
//! at most one identity job and never starts one while its own session or
//! account writer exists. Nothing here authenticates: completed jobs still go
//! through the single-threaded admission in the server loop.
//!
//! Before authentication the account is only known by its canonical email
//! (`identity091::credentials`). The key is a SHA-256 of that email with a
//! per-process salt; neither email nor key is logged.
//!
//! OBSERVED (FULL_TEST 2026-10-20 stand -05, P08B native-fix01): the native
//! client resends one LoginRequest every 1 s (10 sends, new request ID each),
//! accepted a reply 11.03 s after its first send and reported
//! LOGIN_REJECTED_NO_LOGINAPP_RESPONSE 17.17 s after submit; one profile13
//! identity job took 10.6-11.0 s. A temporarily blocked login therefore gets
//! no reply (its own next retry is the wait) only while that wait plus the
//! last measured job still fits `CLIENT_WINDOW`; afterwards SERVER_NOT_READY.
//! A deferred attempt keeps only its LoginAttempt and first-seen time.
use super::*;

pub(super) type AccountTag = [u8; 32];

pub(super) const MAX_IDENTITY_JOBS: usize = 4;
pub(super) const MAX_DEFERRED: usize = 16;
pub(super) const START_SPACING: Duration = Duration::from_millis(250);
/// Below the single observed 17.17 s native timeout (INFERRED margin).
pub(super) const CLIENT_WINDOW: Duration = Duration::from_secs(16);
/// Conservative duration until the first job of this process completes.
pub(super) const DEFAULT_IDENTITY: Duration = Duration::from_secs(11);

pub(super) struct Pending {
    pub(super) job: AuthJob,
    pub(super) account: AccountTag,
    pub(super) started: Instant,
}

/// Account writers that a new login must not overlap. `global` is the
/// fail-closed fallback for writers without a resolvable per-account owner.
#[derive(Default)]
pub(super) struct Writers {
    pub(super) global: bool,
    pub(super) accounts: Vec<AccountTag>,
}

#[derive(Debug, PartialEq, Eq)]
pub(super) enum Decision {
    Start,
    /// Temporarily blocked: no reply, the native retry comes back.
    Defer(&'static str),
    /// SERVER_NOT_READY now.
    Reject(&'static str),
}

pub(super) struct Admission {
    salt: [u8; 32],
    limit: usize,
    jobs: Vec<Pending>,
    deferred: VecDeque<(LoginAttempt, Instant)>,
    last_start: Option<Instant>,
    last_identity: Option<Duration>,
}

impl Admission {
    /// `limit` 1 keeps the old one-job-at-a-time order for modes whose
    /// writers have no per-account owner (owner hold, training rooms).
    pub(super) fn new(limit: usize) -> io::Result<Self> {
        if !(1..=MAX_IDENTITY_JOBS).contains(&limit) { return Err(model::bad()); }
        let mut salt = [0; 32]; OsRng.fill_bytes(&mut salt);
        Ok(Self { salt, limit, jobs: Vec::new(), deferred: VecDeque::new(), last_start: None, last_identity: None })
    }

    pub(super) fn account(&self, canonical_email: &str) -> AccountTag {
        let mut hash = Sha256::new(); hash.update(b"wot091.login-account.v1\0"); hash.update(self.salt);
        hash.update((canonical_email.len() as u32).to_le_bytes()); hash.update(canonical_email.as_bytes());
        hash.finalize().into()
    }

    pub(super) fn is_empty(&self) -> bool { self.jobs.is_empty() }
    pub(super) fn len(&self) -> usize { self.jobs.len() }
    pub(super) fn has_account(&self, account: &AccountTag) -> bool { self.jobs.iter().any(|p| &p.account == account) }
    pub(super) fn accounts(&self) -> impl Iterator<Item = &AccountTag> { self.jobs.iter().map(|p| &p.account) }

    pub(super) fn max_wait(&self) -> Duration {
        CLIENT_WINDOW.saturating_sub(self.last_identity.unwrap_or(DEFAULT_IDENTITY))
    }

    /// A native retry of an in-flight attempt changes only its reply ID.
    pub(super) fn refresh(&mut self, request: u32, candidate: &LoginAttempt, fields: &login::Fields) -> bool {
        self.jobs.iter_mut().any(|p| p.job.refresh_pending_request(request, candidate, fields))
    }

    /// `sessions` yields every live or writer-retained session as
    /// (its login account, whether it is this very attempt).
    pub(super) fn decide<I>(&self, attempt: &LoginAttempt, account: &AccountTag, sessions: I, writers: &Writers, now: Instant) -> Decision
        where I: IntoIterator<Item = (Option<AccountTag>, bool)> {
        if self.has_account(account) { return Decision::Reject("account_identity_in_flight"); }
        if self.jobs.iter().any(|p| p.job.attempt.login_peer == attempt.login_peer || p.job.attempt.key == attempt.key) {
            return Decision::Reject("peer_conflict");
        }
        if sessions.into_iter().any(|(owner, same_attempt)| !same_attempt && owner.as_ref() == Some(account)) {
            return Decision::Reject("account_session_active");
        }
        if writers.accounts.contains(account) { return Decision::Defer("account_writer"); }
        if writers.global { return Decision::Defer("shared_writer"); }
        if self.jobs.len() >= self.limit { return Decision::Defer("identity_capacity"); }
        if self.last_start.is_some_and(|last| now.saturating_duration_since(last) < START_SPACING) { return Decision::Defer("start_spacing"); }
        Decision::Start
    }

    /// True: stay silent (still inside the window). False: answer 73 now.
    pub(super) fn defer(&mut self, attempt: LoginAttempt, now: Instant) -> bool {
        self.deferred.retain(|(_, first)| now.saturating_duration_since(*first) <= CLIENT_WINDOW);
        let first = match self.deferred.iter().find(|(a, _)| a.same_attempt(&attempt)) {
            Some((_, first)) => *first,
            None => {
                if self.deferred.len() >= MAX_DEFERRED { return false; }
                self.deferred.push_back((attempt, now)); now
            },
        };
        if now.saturating_duration_since(first) <= self.max_wait() { return true; }
        self.deferred.retain(|(a, _)| !a.same_attempt(&attempt));
        false
    }

    pub(super) fn waited(&self, attempt: &LoginAttempt, now: Instant) -> Duration {
        self.deferred.iter().find(|(a, _)| a.same_attempt(attempt)).map_or(Duration::ZERO, |(_, first)| now.saturating_duration_since(*first))
    }

    pub(super) fn started(&mut self, job: AuthJob, account: AccountTag, now: Instant) {
        self.deferred.retain(|(a, _)| !a.same_attempt(&job.attempt));
        self.jobs.push(Pending { job, account, started: now });
        self.last_start = Some(now);
    }

    /// Remove every finished job; a stopped worker is an identity failure.
    pub(super) fn completed(&mut self, now: Instant) -> Vec<(Pending, io::Result<Option<Authenticated>>)> {
        let mut done = Vec::new();
        let mut index = 0;
        while index < self.jobs.len() {
            let result = match self.jobs[index].job.receiver.try_recv() {
                Ok(result) => result,
                Err(mpsc::TryRecvError::Empty) => { index += 1; continue; },
                Err(mpsc::TryRecvError::Disconnected) => Err(model::bad()),
            };
            let pending = self.jobs.remove(index);
            self.last_identity = Some(now.saturating_duration_since(pending.started));
            done.push((pending, result));
        }
        done
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn peer(port: u16) -> SocketAddr { SocketAddr::from((Ipv4Addr::LOCALHOST, port)) }
    fn fields(key: u8, nonce: u32, user: &[u8]) -> login::Fields {
        login::Fields { username_len: user.len(), password_len: 4, key_len: 16, nonce,
            session_key: [key; 16], digest: [9; 16], lab_credentials_valid: false,
            username: user.to_vec(), password: b"test".to_vec() }
    }
    fn attempt_of(f: &login::Fields, port: u16) -> LoginAttempt { LoginAttempt::new(f.session_key, f.nonce, peer(port)) }
    fn job(request: u32, f: &login::Fields, port: u16) -> (AuthJob, mpsc::SyncSender<io::Result<Option<Authenticated>>>) {
        let salt = [3; 32]; let (sender, receiver) = mpsc::sync_channel(1);
        (AuthJob { request, attempt: attempt_of(f, port), credential_salt: salt,
            credential_tag: pending_credential_tag(&salt, f), receiver }, sender)
    }
    fn none() -> Vec<(Option<AccountTag>, bool)> { Vec::new() }
    fn reply_id(wire: &[u8]) -> u32 { u32::from_le_bytes(wire[7..11].try_into().unwrap()) }

    #[test]
    fn two_accounts_overlap_their_identity_jobs_and_complete_independently() {
        let t0 = Instant::now();
        let mut admission = Admission::new(MAX_IDENTITY_JOBS).unwrap();
        let (alpha, bravo) = (admission.account("alpha@example.test"), admission.account("bravo@example.test"));
        assert_ne!(alpha, bravo);
        let a = fields(1, 11, b"alpha"); let b = fields(2, 22, b"bravo");
        let idle = Writers::default();
        assert_eq!(admission.decide(&attempt_of(&a, 40001), &alpha, none(), &idle, t0), Decision::Start);
        let (a_job, a_done) = job(109211, &a, 40001); admission.started(a_job, alpha, t0);
        // B arrives 5.8 s into A's job (stand -05 timing) and starts at once.
        let t_b = t0 + Duration::from_millis(5800);
        assert_eq!(admission.decide(&attempt_of(&b, 40002), &bravo, none(), &idle, t_b), Decision::Start);
        let (b_job, b_done) = job(99189, &b, 40002); admission.started(b_job, bravo, t_b);
        assert_eq!(admission.len(), 2);
        // Interleaved native retries refresh only their own attempt.
        for step in 0..5u32 {
            assert!(admission.refresh(109212 + step, &attempt_of(&a, 40001), &a));
            assert!(admission.refresh(99190 + step, &attempt_of(&b, 40002), &b));
        }
        assert!(!admission.refresh(1, &attempt_of(&b, 40001), &b));
        // A finishes first; B's job is untouched and still pending.
        a_done.send(Ok(None)).unwrap();
        let done = admission.completed(t0 + Duration::from_millis(10600));
        assert_eq!(done.len(), 1);
        assert_eq!(done[0].0.account, alpha);
        assert_eq!(reply_id(&login::rejection(done[0].0.job.request, 67)), 109216);
        assert!(done[0].1.as_ref().unwrap().is_none());
        assert!(admission.has_account(&bravo) && !admission.has_account(&alpha));
        b_done.send(Ok(None)).unwrap();
        let done = admission.completed(t_b + Duration::from_millis(10600));
        assert_eq!((done.len(), done[0].0.account, done[0].0.job.request), (1, bravo, 99194));
        assert!(admission.is_empty());
        // B's reply came 10.6 s after its first send, inside the window.
        assert!(Duration::from_millis(10600) <= CLIENT_WINDOW);
    }

    #[test]
    fn same_account_twice_is_rejected_while_its_job_or_session_exists() {
        let t0 = Instant::now();
        let mut admission = Admission::new(MAX_IDENTITY_JOBS).unwrap();
        let alpha = admission.account("alpha@example.test");
        let idle = Writers::default();
        let first = fields(1, 11, b"alpha");
        let (a_job, a_done) = job(1, &first, 40001); admission.started(a_job, alpha, t0);
        // A second client (other key/nonce/peer) of the same account.
        let second = fields(5, 55, b"alpha");
        let later = t0 + Duration::from_secs(1);
        assert_eq!(admission.decide(&attempt_of(&second, 40005), &alpha, none(), &idle, later), Decision::Reject("account_identity_in_flight"));
        // Same peer or key with another account is ambiguous routing.
        let other = admission.account("other@example.test");
        assert_eq!(admission.decide(&attempt_of(&fields(7, 70, b"o"), 40001), &other, none(), &idle, later), Decision::Reject("peer_conflict"));
        assert_eq!(admission.decide(&attempt_of(&fields(1, 70, b"o"), 40009), &other, none(), &idle, later), Decision::Reject("peer_conflict"));
        a_done.send(Ok(None)).unwrap(); assert_eq!(admission.completed(later).len(), 1);
        // After admission the live session holds the account; only the very
        // same attempt (lost redirect) may authenticate again.
        let admitted = vec![(Some(alpha), false)];
        assert_eq!(admission.decide(&attempt_of(&second, 40005), &alpha, admitted.clone(), &idle, later), Decision::Reject("account_session_active"));
        assert_eq!(admission.decide(&attempt_of(&first, 40001), &alpha, vec![(Some(alpha), true)], &idle, later), Decision::Start);
        // An unrelated account is not blocked by that session.
        assert_eq!(admission.decide(&attempt_of(&fields(8, 80, b"o"), 40008), &other, admitted, &idle, later), Decision::Start);
    }

    #[test]
    fn writers_block_only_their_account_and_unresolved_writers_defer_everyone() {
        let t0 = Instant::now();
        let admission = Admission::new(MAX_IDENTITY_JOBS).unwrap();
        let (alpha, bravo) = (admission.account("alpha@example.test"), admission.account("bravo@example.test"));
        let garage = Writers { global: false, accounts: vec![alpha] };
        let a = attempt_of(&fields(1, 11, b"a"), 40001); let b = attempt_of(&fields(2, 22, b"b"), 40002);
        assert_eq!(admission.decide(&a, &alpha, none(), &garage, t0), Decision::Defer("account_writer"));
        assert_eq!(admission.decide(&b, &bravo, none(), &garage, t0), Decision::Start);
        let unresolved = Writers { global: true, accounts: Vec::new() };
        assert_eq!(admission.decide(&b, &bravo, none(), &unresolved, t0), Decision::Defer("shared_writer"));
        // The old modes keep exactly one identity job.
        let mut serial = Admission::new(1).unwrap();
        let (job_a, _keep) = job(1, &fields(1, 11, b"a"), 40001); serial.started(job_a, alpha, t0);
        assert_eq!(serial.decide(&b, &bravo, none(), &Writers::default(), t0 + Duration::from_secs(1)), Decision::Defer("identity_capacity"));
        assert!(Admission::new(0).is_err() && Admission::new(MAX_IDENTITY_JOBS + 1).is_err());
    }

    #[test]
    fn deferred_login_stays_silent_only_inside_the_client_window() {
        let t0 = Instant::now();
        let mut admission = Admission::new(MAX_IDENTITY_JOBS).unwrap();
        let alpha = admission.account("alpha@example.test");
        let b = attempt_of(&fields(2, 22, b"b"), 40002);
        assert_eq!(admission.max_wait(), CLIENT_WINDOW - DEFAULT_IDENTITY);
        // Start spacing defers the second start for 250 ms.
        let (job_a, a_done) = job(1, &fields(1, 11, b"a"), 40001); admission.started(job_a, alpha, t0);
        let bravo = admission.account("bravo@example.test");
        assert_eq!(admission.decide(&b, &bravo, none(), &Writers::default(), t0 + Duration::from_millis(100)), Decision::Defer("start_spacing"));
        assert_eq!(admission.decide(&b, &bravo, none(), &Writers::default(), t0 + START_SPACING), Decision::Start);
        a_done.send(Ok(None)).unwrap(); admission.completed(t0 + Duration::from_millis(10600));
        assert_eq!(admission.max_wait(), Duration::from_millis(5400));
        // A retry of a deferred attempt keeps its first-seen time.
        assert!(admission.defer(b, t0));
        assert!(admission.defer(b, t0 + Duration::from_millis(5400)));
        assert_eq!(admission.waited(&b, t0 + Duration::from_secs(5)), Duration::from_secs(5));
        assert!(!admission.defer(b, t0 + Duration::from_millis(5401)));
        // A later retry of the same attempt is a new, bounded deferral.
        assert!(admission.defer(b, t0 + Duration::from_secs(6)));
        let (job_b, _b_done) = job(9, &fields(2, 22, b"b"), 40002); admission.started(job_b, bravo, t0 + Duration::from_secs(6));
        assert_eq!(admission.waited(&b, t0 + Duration::from_secs(7)), Duration::ZERO);
        // The deferral table is bounded.
        for n in 0..MAX_DEFERRED as u8 { assert!(admission.defer(attempt_of(&fields(100 + n, 1, b"x"), 41000 + n as u16), t0 + Duration::from_secs(7))); }
        assert!(!admission.defer(attempt_of(&fields(200, 1, b"x"), 42000), t0 + Duration::from_secs(7)));
    }

    #[test]
    fn account_tags_are_salted_per_process_and_bind_the_full_email() {
        let first = Admission::new(1).unwrap(); let second = Admission::new(1).unwrap();
        assert_eq!(first.account("a@example.test"), first.account("a@example.test"));
        assert_ne!(first.account("a@example.test"), second.account("a@example.test"));
        assert_ne!(first.account("a@example.test"), first.account("a@example.tes"));
        let stopped = { let (job_a, sender) = job(1, &fields(1, 11, b"a"), 40001); drop(sender); job_a };
        let mut admission = Admission::new(1).unwrap(); let alpha = admission.account("a@example.test");
        admission.started(stopped, alpha, Instant::now());
        let done = admission.completed(Instant::now());
        assert!(done.len() == 1 && done[0].1.is_err() && admission.is_empty());
    }
}
