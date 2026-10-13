//! Retained historical private workers migrated under explicit new pins.
//! Missing P06N/P06O root artifacts are not reconstructed or substituted.
//! See docs/plans/P06Q_ACCEPTANCE_ENVIRONMENT_REPAIR.md and the local
//! 20261013-p06q-fixture-migration-01 receipt for source/copy provenance.
use crate::map_drive_worker091::Pool;
use sha2::{Digest, Sha256};
use std::{fs, path::Path};

pub(super) const P06O_POOL_SHA: &str =
    "a96e7b8c1b410446e3e7c0f6e7e7453b633c3fbb19ce94a62686fbb319031d21";

fn pinned_pool(directory: &str, expected: &str) -> Pool {
    let local = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../local").canonicalize().unwrap();
    let path = local.join("build/server").join(directory).join("pool-near.json");
    let metadata = fs::metadata(&path).expect("required historical private fixture pool");
    assert!(metadata.is_file() && metadata.len() <= 16_384);
    let raw = fs::read(&path).unwrap();
    assert_eq!(format!("{:x}", Sha256::digest(&raw)), expected,
        "fixture pool changed; no automatic fallback or repinning");
    // The pool pin covers both unchanged map configurations and the complete
    // artifact manifest. Pool::load verifies every runtime file before spawn.
    let pool = Pool::load(&local, &path).unwrap();
    assert_eq!(pool.sha256, expected);
    pool
}

pub(super) fn p06n() -> Pool {
    pinned_pool("physics-p06n-private-fixture-01",
        "80f14d87bb01c9c28f5376265dce80989eeb715fdfe3f15018b6d29c54db9251")
}

pub(super) fn p06o() -> Pool {
    pinned_pool("physics-p06o-private-fixture-01", P06O_POOL_SHA)
}
