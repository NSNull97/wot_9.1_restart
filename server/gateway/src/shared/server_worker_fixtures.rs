//! Test-only relocation of exact accepted private workers and configurations.
//! Immutable historical pools retain their original pins. Derived pool/config
//! hashes describe only this checkout's paths, never the old native evidence.
//! P06N/P06O provenance remains the P06Q fixture-migration receipt; IPC5 uses
//! the accepted P06R chain pool. No production loader or worker is replaced.
use crate::map_drive_worker091::Pool;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::{fs, io::{self, Read, Write}, path::{Path, PathBuf}, sync::OnceLock};

const HISTORICAL_LOCAL: &str = r"D:\WoT_9.1_Server\local\";
const PACKAGED_SOURCE_SHA: &str = "8994553cd223678e093c44de9cb5bfa78ccfedb5c2b3ff0fe49e1ed84e8cbc12";
const P06N_SOURCE_SHA: &str = "80f14d87bb01c9c28f5376265dce80989eeb715fdfe3f15018b6d29c54db9251";
const P06O_SOURCE_SHA: &str = "a96e7b8c1b410446e3e7c0f6e7e7453b633c3fbb19ce94a62686fbb319031d21";
const P06R_SOURCE_SHA: &str = "62549fb3b3652edadbf6756445141a192f3157e741ab94d2e890c5a54de9783e";
const P06R_CONFIG_SHA: &str = "a1d8f4406661e53636c5430588def8af96de93a1d56b4781a4bedf6a01e8c49e";

fn invalid() -> io::Error { io::Error::new(io::ErrorKind::InvalidData, "historical fixture relocation") }
fn hash(raw: &[u8]) -> String { format!("{:x}", Sha256::digest(raw)) }
fn plain(path: &Path) -> io::Result<()> {
    for parent in path.ancestors() {
        let metadata = fs::symlink_metadata(parent)?;
        if metadata.file_type().is_symlink() { return Err(invalid()); }
        #[cfg(windows)] {
            use std::os::windows::fs::MetadataExt;
            if metadata.file_attributes() & 0x400 != 0 { return Err(invalid()); }
        }
    }
    Ok(())
}
fn owned(root: &Path, path: &Path) -> io::Result<PathBuf> {
    plain(root)?; plain(path)?;
    let actual = path.canonicalize()?;
    if !actual.starts_with(root.canonicalize()?) || actual == root.canonicalize()? { return Err(invalid()); }
    Ok(actual)
}
fn directories(root: &Path, relative: &Path) -> io::Result<PathBuf> {
    use std::path::Component;
    let parts = relative.components().collect::<Vec<_>>();
    if parts.is_empty() || parts.iter().any(|part| !matches!(part, Component::Normal(_))) { return Err(invalid()); }
    plain(root)?;
    let mut path = root.to_path_buf();
    for part in parts {
        path.push(part.as_os_str());
        match fs::symlink_metadata(&path) {
            Ok(_) => (),
            Err(error) if error.kind() == io::ErrorKind::NotFound => fs::create_dir(&path)?,
            Err(error) => return Err(error),
        }
        path = owned(root, &path)?;
        if !path.is_dir() { return Err(invalid()); }
    }
    Ok(path)
}
fn mapped(root: &Path, original: &str) -> io::Result<PathBuf> {
    let relative = original.strip_prefix(HISTORICAL_LOCAL).ok_or_else(invalid)?;
    if relative.is_empty() || relative.contains('/') || relative.contains(':')
        || relative.chars().any(char::is_control)
        || relative.split('\\').any(|part| matches!(part, "" | "." | "..")) {
        return Err(invalid());
    }
    // Do not silently read the primary checkout when the copy is absent.
    owned(root, &root.join(relative))
}
fn pinned(root: &Path, path: &Path, expected: &str, maximum: usize) -> io::Result<Vec<u8>> {
    let path = owned(root, path)?;
    let file = fs::File::open(path)?;
    let metadata = file.metadata()?;
    if !metadata.is_file() || metadata.len() == 0 || metadata.len() > maximum as u64 { return Err(invalid()); }
    let mut raw = Vec::new();
    file.take(maximum as u64 + 1).read_to_end(&mut raw)?;
    if raw.len() as u64 != metadata.len() || hash(&raw) != expected { return Err(invalid()); }
    Ok(raw)
}
fn spelling(path: &Path) -> io::Result<String> {
    let value = path.to_str().ok_or_else(invalid)?;
    // .NET worker ownership checks use ordinary drive spelling, after the
    // canonical/non-reparse Rust check above (the production convention).
    Ok(value.strip_prefix(r"\\?\").unwrap_or(value).to_owned())
}
fn text<'a>(value: &'a Value, key: &str) -> io::Result<&'a str> { value[key].as_str().ok_or_else(invalid) }
fn save(root: &Path, path: &Path, value: &Value) -> io::Result<String> {
    owned(root, path.parent().ok_or_else(invalid)?)?;
    let raw = serde_json::to_vec_pretty(value).map_err(|_| invalid())?;
    if raw.is_empty() || raw.len() > 16384 { return Err(invalid()); }
    fs::OpenOptions::new().write(true).create_new(true).open(path)?.write_all(&raw)?;
    Ok(hash(&raw))
}
fn relocate(source: &str, source_sha: &str, tag: &str) -> io::Result<Pool> {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local").canonicalize()?;
    let original = pinned(&root, &root.join(source), source_sha, 16384)?;
    let mut value: Value = serde_json::from_slice(&original).map_err(|_| invalid())?;
    let base = directories(&root, &Path::new("test-runs/pinned-worker-relocation").join(std::process::id().to_string()))?;
    let output = base.join(tag);
    fs::create_dir(&output)?; owned(&root, &output)?;
    for key in ["executable", "artifact_manifest"] {
        let path = mapped(&root, text(&value["worker"], key)?)?;
        value["worker"][key] = spelling(&path)?.into();
    }
    // Artifact manifest and every executable/runtime member remain unchanged.
    pinned(&root, Path::new(text(&value["worker"], "artifact_manifest")?),
        text(&value["worker"], "artifact_manifest_sha256")?, 65536)?;
    let maps = value["maps"].as_array_mut().ok_or_else(invalid)?;
    if maps.len() != 2 { return Err(invalid()); }
    let mut provenance = Vec::new();
    for (index, map) in maps.iter_mut().enumerate() {
        let source_path = mapped(&root, text(map, "config")?)?;
        let source_hash = text(map, "config_sha256")?.to_owned();
        if tag == "p06r" && text(map, "asset")? == "05_prohorovka" && source_hash != P06R_CONFIG_SHA {
            return Err(invalid());
        }
        let raw = pinned(&root, &source_path, &source_hash, 16384)?;
        let mut config: Value = serde_json::from_slice(&raw).map_err(|_| invalid())?;
        for key in ["terrain", "obstacles"] {
            let path = mapped(&root, text(&config[key], "path")?)?;
            pinned(&root, &path, text(&config[key], "sha256")?, 8 * 1024 * 1024)?;
            config[key]["path"] = spelling(&path)?.into();
        }
        let target = output.join(format!("map-{index}.json"));
        let derived_hash = save(&root, &target, &config)?;
        provenance.push(serde_json::json!({"source_path": spelling(&source_path)?, "source_sha256": source_hash,
            "derived_path": spelling(&target)?, "derived_sha256": derived_hash}));
        map["config"] = spelling(&target)?.into();
        map["config_sha256"] = derived_hash.into();
    }
    let target = output.join("pool.json");
    let derived_hash = save(&root, &target, &value)?;
    let pool = Pool::load(&root, &target)?;
    if pool.sha256 != derived_hash { return Err(invalid()); }
    save(&root, &output.join("relocation.json"), &serde_json::json!({
        "status": "VERIFIED_PATH_RELOCATION_RUNTIME_NOT_RUN", "native_clients": "NOT_RUN",
        "source_pool": source, "source_pool_sha256": source_sha, "derived_pool_sha256": derived_hash,
        "artifact_manifest_sha256": value["worker"]["artifact_manifest_sha256"], "configs": provenance,
        "changed_fields": ["worker.executable", "worker.artifact_manifest", "maps[].config",
            "maps[].config_sha256", "config.terrain.path", "config.obstacles.path"]}))?;
    Ok(pool)
}

pub(crate) fn packaged() -> Pool {
    static POOL: OnceLock<Pool> = OnceLock::new();
    POOL.get_or_init(|| relocate("server/map-drive/pool.json", PACKAGED_SOURCE_SHA,
        "packaged").expect("required pinned packaged IPC1 fixture")).clone()
}

pub(crate) fn p06n() -> Pool {
    static POOL: OnceLock<Pool> = OnceLock::new();
    POOL.get_or_init(|| relocate("build/server/physics-p06n-private-fixture-01/pool-near.json",
        P06N_SOURCE_SHA, "p06n").expect("required pinned P06N private fixture")).clone()
}

pub(crate) fn p06o() -> Pool {
    static POOL: OnceLock<Pool> = OnceLock::new();
    POOL.get_or_init(|| relocate("build/server/physics-p06o-private-fixture-01/pool-near.json",
        P06O_SOURCE_SHA, "p06o").expect("required pinned P06O private fixture")).clone()
}

pub(crate) fn p06r() -> Pool {
    static POOL: OnceLock<Pool> = OnceLock::new();
    POOL.get_or_init(|| relocate("evidence/20261013-p06r-compound-01/fracture-gateway-real01/pool-chain.json",
        P06R_SOURCE_SHA, "p06r").expect("required pinned P06R IPC5 fixture")).clone()
}

#[test]
fn relocation_rejects_prefix_confusion_traversal_and_nonlocal_paths() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local").canonicalize().unwrap();
    let directory = directories(&root, Path::new("test-runs")).unwrap();
    assert_eq!(mapped(&root, &(HISTORICAL_LOCAL.to_owned() + "test-runs")).unwrap(), directory);
    for path in [r"D:\WoT_9.1_Server\local-other\a", r"D:\WoT_9.1_Server\local\..\a",
        r"D:\WoT_9.1_Server\local\.\a", r"D:\WoT_9.1_Server\local\a/../b",
        r"D:\WoT_9.1_Server\local\a:stream", r"C:\outside\a", r"\\server\share\a",
        "relative.json", HISTORICAL_LOCAL] { assert!(mapped(&root, path).is_err(), "{path}"); }
    assert!(owned(&root, root.parent().unwrap()).is_err());
    assert!(directories(&root, Path::new("../fixture-escape")).is_err());
}

#[test]
fn relocation_rejects_changed_missing_and_oversized_pinned_files() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local").canonicalize().unwrap();
    let directory = directories(&root, Path::new("test-runs")).unwrap();
    let path = directory.join(format!("relocation-negative-{}.json", std::process::id()));
    let original = b"{\"version\":1}";
    fs::OpenOptions::new().write(true).create_new(true).open(&path).unwrap().write_all(original).unwrap();
    assert_eq!(pinned(&root, &path, &hash(original), 64).unwrap(), original);
    assert!(pinned(&root, &path, &"0".repeat(64), 64).is_err());
    assert!(pinned(&root, &path, &hash(original), original.len()-1).is_err());
    fs::write(&path, b"{\"version\":2}").unwrap();
    assert!(pinned(&root, &path, &hash(original), 64).is_err());
    assert!(pinned(&root, &path.with_extension("missing"), &hash(original), 64).is_err());
}
