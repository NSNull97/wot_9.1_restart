//! Bounded FIFO for native logins that arrive while the single identity job,
//! an account writer or a room host is in flight. Nothing here authenticates:
//! an entry only waits for the ordinary `start_auth` path, which runs one job
//! at a time and re-checks retirement/capacity/account ownership on admission.
//!
//! OBSERVED (FULL_TEST 2026-10-20 stand -05, P08B native-fix01): the native
//! client resends one LoginRequest every 1 s (10 sends, new request ID each),
//! accepts a reply only for its newest ID, still accepted a reply 11.03 s after
//! its first send and reported LOGIN_REJECTED_NO_LOGINAPP_RESPONSE 17.17 s
//! after submit. One profile13 identity job took 10.6-11.0 s. A queued login
//! therefore starts only while its wait plus the last measured job duration
//! fits `CLIENT_WINDOW`; otherwise it is answered with the ordinary
//! SERVER_NOT_READY instead of being authenticated after the client gave up.
use super::*;

pub(super) const LIMIT: usize = 4;
/// Below the single observed 17.17 s native timeout (INFERRED margin).
pub(super) const CLIENT_WINDOW: Duration = Duration::from_secs(16);
/// Conservative duration until the first job of this process completes.
pub(super) const DEFAULT_IDENTITY: Duration = Duration::from_secs(11);

struct Entry {
    request: u32,
    attempt: LoginAttempt,
    // Ephemeral decoded credentials for the later start_auth call. Never
    // logged; dropped on start, expiry or rejection.
    fields: login::Fields,
    credential_salt: [u8; 32],
    credential_tag: [u8; 32],
    queued_at: Instant,
}

impl Entry {
    fn duplicate(&self, candidate: &LoginAttempt, fields: &login::Fields) -> bool {
        let tag = pending_credential_tag(&self.credential_salt, fields);
        self.attempt.same_attempt(candidate)
            && self.credential_tag.iter().zip(tag).fold(0u8, |difference, (left, right)| difference | (*left ^ right)) == 0
    }
}

/// A queued login ready for `start_auth`; its request ID is the newest retry.
pub(super) struct Ready {
    pub(super) request: u32,
    pub(super) attempt: LoginAttempt,
    pub(super) fields: login::Fields,
    pub(super) waited: Duration,
}

/// Only the reply route and the newest request ID leave the queue on expiry.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(super) struct Expired {
    pub(super) request: u32,
    pub(super) peer: SocketAddr,
    pub(super) waited: Duration,
}

#[derive(Debug, PartialEq, Eq)]
pub(super) enum Denial { Full, PeerConflict }

#[derive(Default)]
pub(super) struct LoginQueue {
    entries: VecDeque<Entry>,
    last_identity: Option<Duration>,
}

impl LoginQueue {
    pub(super) fn is_empty(&self) -> bool { self.entries.is_empty() }
    pub(super) fn len(&self) -> usize { self.entries.len() }

    pub(super) fn record_identity(&mut self, elapsed: Duration) { self.last_identity = Some(elapsed); }

    pub(super) fn max_wait(&self) -> Duration {
        CLIENT_WINDOW.saturating_sub(self.last_identity.unwrap_or(DEFAULT_IDENTITY))
    }

    /// A native retry of a queued attempt changes only the reply request ID.
    pub(super) fn refresh(&mut self, request: u32, candidate: &LoginAttempt, fields: &login::Fields) -> bool {
        match self.entries.iter_mut().find(|e| e.duplicate(candidate, fields)) {
            Some(entry) => { entry.request = request; true },
            None => false,
        }
    }

    /// Exact duplicates must be refreshed before this call. A different
    /// attempt sharing a peer or session key with the in-flight job or a
    /// queued entry is ambiguous and is never queued.
    pub(super) fn push(&mut self, request: u32, attempt: LoginAttempt, fields: login::Fields,
                       in_flight: Option<&LoginAttempt>, now: Instant) -> Result<usize, Denial> {
        let conflict = |other: &LoginAttempt| other.login_peer == attempt.login_peer || other.key == attempt.key;
        if in_flight.is_some_and(|job| conflict(job)) || self.entries.iter().any(|e| conflict(&e.attempt)) {
            return Err(Denial::PeerConflict);
        }
        if self.entries.len() >= LIMIT { return Err(Denial::Full); }
        let mut credential_salt = [0; 32]; OsRng.fill_bytes(&mut credential_salt);
        let credential_tag = pending_credential_tag(&credential_salt, &fields);
        self.entries.push_back(Entry { request, attempt, fields, credential_salt, credential_tag, queued_at: now });
        Ok(self.entries.len())
    }

    /// Remove every entry that can no longer be answered inside the client
    /// window. The caller replies SERVER_NOT_READY to the newest request ID.
    pub(super) fn expire(&mut self, now: Instant) -> Vec<Expired> {
        let limit = self.max_wait();
        let mut expired = Vec::new();
        self.entries.retain(|e| {
            let waited = now.saturating_duration_since(e.queued_at);
            if waited <= limit { return true; }
            expired.push(Expired { request: e.request, peer: e.attempt.login_peer, waited });
            false
        });
        expired
    }

    /// FIFO head, only after `expire` for the same instant.
    pub(super) fn pop(&mut self, now: Instant) -> Option<Ready> {
        let entry = self.entries.pop_front()?;
        Some(Ready { request: entry.request, attempt: entry.attempt, fields: entry.fields,
            waited: now.saturating_duration_since(entry.queued_at) })
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
    fn reply_id(wire: &[u8]) -> u32 { u32::from_le_bytes(wire[7..11].try_into().unwrap()) }

    #[test]
    fn second_account_waits_behind_in_flight_identity_and_starts_with_its_newest_request() {
        let t0 = Instant::now();
        let a = fields(1, 11, b"alpha"); let b = fields(2, 22, b"bravo");
        let (mut a_job, a_done) = job(109211, &a, 40001);
        let mut queue = LoginQueue::default();
        // B arrives 5.8 s into A's job (stand -05 timing): queued, no reply.
        let b_attempt = attempt_of(&b, 40002);
        assert!(!a_job.refresh_pending_request(99189, &b_attempt, &b));
        assert!(!queue.refresh(99189, &b_attempt, &b));
        assert_eq!(queue.push(99189, b_attempt, fields(2, 22, b"bravo"), Some(&a_job.attempt), t0 + Duration::from_millis(5800)), Ok(1));
        // Interleaved native retries refresh only their own pending attempt.
        for (step, id) in (99190..=99194).enumerate() {
            assert!(a_job.refresh_pending_request(109217 + step as u32, &a_job.attempt.clone(), &a));
            assert!(!queue.refresh(109217 + step as u32, &a_job.attempt.clone(), &a));
            assert!(queue.refresh(id, &b_attempt, &b));
            assert!(!a_job.refresh_pending_request(id, &b_attempt, &b));
        }
        assert_eq!(a_job.request, 109221);
        // A completes at 10.6 s; the one-job invariant held throughout.
        a_done.send(Ok(None)).unwrap();
        assert!(a_job.receiver.try_recv().unwrap().unwrap().is_none());
        queue.record_identity(Duration::from_millis(10600));
        let done = t0 + Duration::from_millis(10600);
        assert!(queue.expire(done).is_empty());
        let ready = queue.pop(done).unwrap();
        assert!(queue.is_empty());
        assert_eq!(ready.request, 99194);
        assert!(ready.attempt.same_attempt(&b_attempt));
        assert_eq!(ready.fields.username, b"bravo".to_vec());
        assert_eq!(ready.waited, Duration::from_millis(4800));
        // B's own job keeps refreshing exactly as an unqueued login would.
        let (mut b_job, _b_done) = job(ready.request, &ready.fields, 40002);
        assert!(b_job.refresh_pending_request(99195, &b_attempt, &b));
        assert_eq!(reply_id(&login::rejection(b_job.request, 67)), 99195);
        // Expected reply 4.8 s + 10.6 s after B's first send stays in window.
        assert!(ready.waited + Duration::from_millis(10600) <= CLIENT_WINDOW);
    }

    #[test]
    fn queued_login_that_cannot_finish_inside_the_client_window_is_rejected_with_its_newest_request() {
        let t0 = Instant::now();
        let mut queue = LoginQueue::default();
        let b = fields(2, 22, b"bravo"); let b_attempt = attempt_of(&b, 40002);
        assert_eq!(queue.max_wait(), CLIENT_WINDOW - DEFAULT_IDENTITY);
        queue.push(5, b_attempt, fields(2, 22, b"bravo"), None, t0).unwrap();
        assert!(queue.refresh(9, &b_attempt, &b));
        queue.record_identity(Duration::from_millis(10600));
        assert!(queue.expire(t0 + Duration::from_millis(5400)).is_empty());
        let expired = queue.expire(t0 + Duration::from_millis(5401));
        assert_eq!(expired, vec![Expired { request: 9, peer: peer(40002), waited: Duration::from_millis(5401) }]);
        assert!(queue.is_empty() && queue.pop(t0 + Duration::from_secs(6)).is_none());
        let wire = login::rejection(expired[0].request, 73);
        assert_eq!((reply_id(&wire), wire[11]), (9, 73));
        // A job longer than the window disables waiting entirely.
        queue.record_identity(Duration::from_secs(17));
        assert_eq!(queue.max_wait(), Duration::ZERO);
        queue.push(10, b_attempt, fields(2, 22, b"bravo"), None, t0).unwrap();
        assert_eq!(queue.expire(t0 + Duration::from_millis(1)).len(), 1);
    }

    #[test]
    fn queue_is_bounded_fifo_and_refuses_ambiguous_peers_or_keys() {
        let t0 = Instant::now();
        let a = fields(1, 11, b"alpha"); let (a_job, _a_done) = job(1, &a, 40001);
        let mut queue = LoginQueue::default();
        // Same peer or same session key as the in-flight job with a different
        // attempt is never queued (the caller answers SERVER_NOT_READY).
        let same_peer = fields(7, 70, b"other");
        assert_eq!(queue.push(2, attempt_of(&same_peer, 40001), fields(7, 70, b"other"), Some(&a_job.attempt), t0), Err(Denial::PeerConflict));
        let same_key = fields(1, 99, b"other");
        assert_eq!(queue.push(2, attempt_of(&same_key, 40009), fields(1, 99, b"other"), Some(&a_job.attempt), t0), Err(Denial::PeerConflict));
        for n in 0..LIMIT as u8 {
            let f = fields(10 + n, 100 + n as u32, b"queued");
            assert_eq!(queue.push(200 + n as u32, attempt_of(&f, 41000 + n as u16), fields(10 + n, 100 + n as u32, b"queued"), Some(&a_job.attempt), t0), Ok(n as usize + 1));
        }
        let extra = fields(60, 600, b"extra");
        assert_eq!(queue.push(300, attempt_of(&extra, 42000), fields(60, 600, b"extra"), None, t0), Err(Denial::Full));
        // A changed credential/peer on a queued attempt is a conflict, not a refresh.
        let mut changed = fields(10, 100, b"queued"); changed.password[0] ^= 1;
        assert!(!queue.refresh(301, &attempt_of(&changed, 41000), &changed));
        assert!(!queue.refresh(301, &attempt_of(&fields(10, 100, b"queued"), 41009), &fields(10, 100, b"queued")));
        assert_eq!(queue.len(), LIMIT);
        let order: Vec<u32> = std::iter::from_fn(|| queue.pop(t0).map(|r| r.request)).collect();
        assert_eq!(order, vec![200, 201, 202, 203]);
    }
}
