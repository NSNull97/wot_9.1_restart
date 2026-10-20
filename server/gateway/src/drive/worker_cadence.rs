//! Opt-in, bounded diagnostics for the production IPC7 scene worker.
//!
//! The normal gateway path does not open files and does not sample processes.
//! A stand enables this card explicitly with `WOT091_STAB_DIAGNOSTICS_DIR`.
//! Receipts contain monotonic durations, scheduler lag, bounded stderr
//! metadata and (on Windows) process CPU time.  They never contain protocol
//! payloads, client paths or credentials.

use std::{
    fs::{self, File, OpenOptions},
    io::{self, Write},
    path::{Path, PathBuf},
    sync::{Arc, Mutex, atomic::{AtomicU64, Ordering}},
    time::{Duration, Instant},
};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

const ENV_DIR: &str = "WOT091_STAB_DIAGNOSTICS_DIR";
const SCHEMA: u64 = 1;
const SCOPE: &str = "p05c-stab-worker-cadence-v1";
const MAX_EVENTS: usize = 4096;
const MAX_BYTES: usize = 512 * 1024;
pub(crate) const MAX_STDERR_BYTES: usize = 4096;
pub(crate) const MAX_STDERR_PREFIX: usize = 512;
static FILE_NONCE: AtomicU64 = AtomicU64::new(0);

struct State {
    file: File,
    events: usize,
    bytes: usize,
    truncated: bool,
}

/// An optional sink shared by the worker's gateway and pipe-reader threads.
/// Write failures disable diagnostics only; they never change simulation or
/// deadline behavior.
pub struct Sink {
    path: PathBuf,
    started: Instant,
    state: Mutex<State>,
}

impl Sink {
    /// Create a fresh sink when the explicit diagnostics directory is set.
    /// The directory must already exist and have no reparse/symlink ancestor;
    /// the function never creates or cleans user paths.
    pub fn from_env(scope: &str, generation: u32) -> io::Result<Option<Arc<Self>>> {
        let Some(raw) = std::env::var_os(ENV_DIR) else { return Ok(None); };
        Self::from_dir(&PathBuf::from(raw), scope, generation).map(Some)
    }

    /// Same sink in an explicit directory. Tests use this instead of mutating
    /// the process-wide variable, which raced with parallel actual-worker tests
    /// ("diagnostics directory must exist").
    fn from_dir(root: &Path, scope: &str, generation: u32) -> io::Result<Arc<Self>> {
        validate_dir(root)?;
        let nonce = FILE_NONCE.fetch_add(1, Ordering::Relaxed);
        let pid = std::process::id();
        let path = root.join(format!("{scope}-g{generation}-p{pid}-n{nonce}.jsonl"));
        let file = OpenOptions::new().write(true).create_new(true).open(&path)?;
        let sink = Arc::new(Self { path, started: Instant::now(), state: Mutex::new(State {
            file, events: 0, bytes: 0, truncated: false,
        })});
        sink.record(json!({"event":"diagnostic_open","generation":generation,"pid":pid}));
        Ok(sink)
    }

    pub fn path(&self) -> &Path { &self.path }

    pub fn elapsed_us(&self, at: Instant) -> u64 {
        at.checked_duration_since(self.started).unwrap_or(Duration::ZERO).as_micros().min(u128::from(u64::MAX)) as u64
    }

    pub fn record(&self, mut value: Value) {
        let Some(obj) = value.as_object_mut() else { return; };
        obj.insert("schema".into(), json!(SCHEMA));
        obj.insert("scope".into(), json!(SCOPE));
        let Ok(mut raw) = serde_json::to_vec(&value) else { return; };
        if raw.len() > 16 * 1024 {
            raw = serde_json::to_vec(&json!({"event":"oversize_event","original_bytes":raw.len()})).unwrap_or_default();
        }
        raw.push(b'\n');
        let Ok(mut state) = self.state.lock() else { return; };
        if state.events >= MAX_EVENTS.saturating_sub(1) || state.bytes.saturating_add(raw.len()) > MAX_BYTES {
            if !state.truncated {
                let marker = serde_json::to_vec(&json!({"schema":SCHEMA,"scope":SCOPE,"event":"diagnostic_truncated","max_events":MAX_EVENTS,"max_bytes":MAX_BYTES})).unwrap_or_default();
                let mut marker = marker;
                marker.push(b'\n');
                if state.events < MAX_EVENTS && state.bytes.saturating_add(marker.len()) <= MAX_BYTES {
                    let _ = state.file.write_all(&marker);
                    let _ = state.file.flush();
                    state.bytes = state.bytes.saturating_add(marker.len());
                    state.events = state.events.saturating_add(1);
                }
                state.truncated = true;
            }
            return;
        }
        if state.file.write_all(&raw).is_ok() && state.file.flush().is_ok() {
            state.bytes += raw.len();
            state.events += 1;
        } else {
            state.truncated = true;
        }
    }

    /// Record only bounded metadata and a short printable prefix. The digest
    /// permits correlating the captured chunk without storing raw stderr.
    pub fn record_stderr(&self, at: Instant, bytes: &[u8], total: usize, truncated: bool) {
        let prefix = bytes.iter().copied().take(MAX_STDERR_PREFIX).filter(|b| (0x20..=0x7e).contains(b)).collect::<Vec<_>>();
        self.record(json!({"event":"worker_stderr","at_us":self.elapsed_us(at),"bytes":bytes.len().min(MAX_STDERR_BYTES),
            "total_bytes":total.min(MAX_STDERR_BYTES),"truncated":truncated,"sha256":format!("{:x}",Sha256::digest(bytes)),
            "prefix_ascii":String::from_utf8_lossy(&prefix)}));
    }

    pub fn record_process(&self, event: &str, at: Instant, pid: u32, cpu_100ns: Option<u64>) {
        self.record(json!({"event":event,"at_us":self.elapsed_us(at),"pid":pid,"cpu_100ns":cpu_100ns,
            "cpu_sample":"windows_get_process_times"}));
    }

    pub fn record_error(&self, event: &str, at: Instant, message: &str) {
        let bounded = message.as_bytes().iter().copied().take(256).filter(|b| (0x20..=0x7e).contains(b)).collect::<Vec<_>>();
        self.record(json!({"event":event,"at_us":self.elapsed_us(at),"message_bytes":message.len().min(1024),
            "message_sha256":format!("{:x}",Sha256::digest(message.as_bytes())),"message_prefix_ascii":String::from_utf8_lossy(&bounded)}));
    }
}

fn validate_dir(path: &Path) -> io::Result<()> {
    if !path.is_absolute() || !path.is_dir() { return Err(io::Error::new(io::ErrorKind::InvalidInput, "diagnostics directory must exist")); }
    for ancestor in path.ancestors() {
        let meta = fs::symlink_metadata(ancestor)?;
        if meta.file_type().is_symlink() { return Err(io::Error::new(io::ErrorKind::InvalidInput, "diagnostics reparse ancestor")); }
        #[cfg(windows)] {
            use std::os::windows::fs::MetadataExt;
            if meta.file_attributes() & 0x400 != 0 { return Err(io::Error::new(io::ErrorKind::InvalidInput, "diagnostics reparse ancestor")); }
        }
    }
    Ok(())
}

/// Process CPU time sample. Windows is the native stand; other targets keep
/// the field unavailable while retaining the wall/scheduler receipts.
pub fn process_cpu_100ns(pid: u32) -> Option<u64> {
    #[cfg(windows)] {
        type Handle = *mut core::ffi::c_void;
        type Dword = u32;
        const PROCESS_QUERY_LIMITED_INFORMATION: Dword = 0x1000;
        unsafe extern "system" {
            fn OpenProcess(access: Dword, inherit: i32, pid: Dword) -> Handle;
            fn GetProcessTimes(handle: Handle, creation: *mut u64, exit: *mut u64, kernel: *mut u64, user: *mut u64) -> i32;
            fn CloseHandle(handle: Handle) -> i32;
        }
        unsafe {
            let handle = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid);
            if handle.is_null() { return None; }
            let (mut creation, mut exit, mut kernel, mut user) = (0u64, 0u64, 0u64, 0u64);
            let ok = GetProcessTimes(handle, &mut creation, &mut exit, &mut kernel, &mut user) != 0;
            let _ = CloseHandle(handle);
            if ok { Some(kernel.saturating_add(user)) } else { None }
        }
    }
    #[cfg(not(windows))]
    { let _ = pid; None }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{fs, time::Duration};

    fn temp_dir() -> PathBuf {
        let p = std::env::temp_dir().join(format!("wot091-stab-cadence-{}-{}", std::process::id(), FILE_NONCE.fetch_add(1, Ordering::Relaxed)));
        fs::create_dir(&p).unwrap(); p
    }

    #[test]
    fn sink_is_bounded_and_marks_truncation_without_pass_claim() {
        let dir = temp_dir();
        let sink = Sink::from_dir(&dir, "test", 9).unwrap();
        for i in 0..(MAX_EVENTS + 10) { sink.record(json!({"event":"sample","i":i})); }
        let path = sink.path().to_owned(); drop(sink);
        let raw = fs::read_to_string(path).unwrap();
        assert!(raw.len() <= MAX_BYTES);
        assert!(raw.lines().any(|line| line.contains("diagnostic_truncated")));
        assert!(!raw.contains("PASS"));
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn stderr_receipt_is_bounded_and_hashed() {
        let dir = temp_dir();
        let sink = Sink::from_dir(&dir, "test", 10).unwrap();
        sink.record_stderr(Instant::now() + Duration::from_millis(1), &[b'a'; 8192], 8192, true);
        let path = sink.path().to_owned(); drop(sink);
        let text = fs::read_to_string(path).unwrap();
        assert!(text.contains("worker_stderr"));
        assert!(text.contains("sha256"));
        assert!(text.len() < 4096);
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn fail_closed_receipt_is_structured_and_never_pass() {
        let dir = temp_dir();
        let sink = Sink::from_dir(&dir, "test", 11).unwrap();
        sink.record(json!({"event":"scheduler_lag","lag_us":500001,"max_lag_us":500000,"status":"FAIL_CLOSED"}));
        sink.record(json!({"event":"worker_deadline","elapsed_us":500001,"limit_us":500000,"status":"FAIL_CLOSED"}));
        let path = sink.path().to_owned(); drop(sink);
        let text = fs::read_to_string(path).unwrap();
        assert_eq!(text.matches("FAIL_CLOSED").count(), 2);
        assert!(!text.contains("\"status\":\"PASS\""));
        let _ = fs::remove_dir_all(dir);
    }
}
