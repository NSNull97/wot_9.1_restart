//! Authenticated legacy Session -> pinned profile4 -> domain loadout.
//! No game.account assertion is fabricated. Hashes guard integrity; Session
//! supplies authentication. Native delivery/reservation/fire remain unavailable.
use std::{fs::File, io::{self, Read}, path::Path};
use serde_json::Value;
use sha2::{Digest, Sha256};
use super::loadout::{self, AmmoMapping, AuthenticatedVehicleProfile, BattleLoadout, ShellStack};
use crate::{arena_vehicle091::VehicleSeed, identity091::Profile};

const PROFILE_SHA: &str = "2610dbd9ee64a12852986def336da057326f14a3289dda43eaae616286998d2d";
const COMPAT_SHA: &str = "825a7e7024993c83b132499fe6f383b233ac288049bb77ca94b5407430f8d4d3";
const MANIFEST_SHA: &str = "ea967805376908e939fa691bb3bbc51e72253162aff98732bd753762eec35718";
const AMMO_SHA: &str = "683daac81143a9d7edfbe671870ba163db088c54f5101fa52e077f596ebbfc74";
const SELECTED: &str = "shell:ms1-stock-ap";
const POLICY: &str = "legacy-session.profile4-ms1.v1";
const MAX_GENERATION: u32 = 32;

fn bad(reason: &str) -> io::Error { io::Error::new(io::ErrorKind::InvalidData, format!("battle loadout: {reason}")) }
fn hash(bytes: &[u8]) -> String { format!("{:x}", Sha256::digest(bytes)) }
fn checked(bytes: &[u8], size: usize, sha: &str) -> io::Result<()> {
    if bytes.len() != size || hash(bytes) != sha { return Err(bad("source size or SHA mismatch")); } Ok(())
}
fn read_pinned(path: &Path, size: usize, sha: &str) -> io::Result<Vec<u8>> {
    // Paths come from authenticated fixture root or the exact pinned manifest.
    if !path.is_absolute() || size > 16384 { return Err(bad("source path")); }
    #[cfg(windows)] {
        use std::path::{Component, Prefix};
        if !matches!(path.components().next(), Some(Component::Prefix(p))
            if matches!(p.kind(), Prefix::Disk(_) | Prefix::VerbatimDisk(_))) { return Err(bad("non-local source path")); }
    }
    let file = File::open(path)?; let meta = file.metadata()?;
    if !meta.is_file() || meta.len() != size as u64 { return Err(bad("source size")); }
    let mut bytes = Vec::with_capacity(size);
    file.take(size as u64 + 1).read_to_end(&mut bytes)?; checked(&bytes, size, sha)?; Ok(bytes)
}
fn parse(bytes: &[u8]) -> io::Result<Value> { serde_json::from_slice(bytes).map_err(|_| bad("source JSON")) }
fn text<'a>(v: &'a Value, key: &str) -> io::Result<&'a str> { v[key].as_str().ok_or_else(|| bad("string field")) }
fn number(v: &Value, key: &str) -> io::Result<u32> {
    v[key].as_u64().and_then(|x| u32::try_from(x).ok()).ok_or_else(|| bad("integer field"))
}
fn small(v: &Value, key: &str) -> io::Result<u16> { u16::try_from(number(v, key)?).map_err(|_| bad("integer bound")) }
fn rows<'a>(v: &'a Value, key: &str, max: usize) -> io::Result<&'a [Value]> {
    let a = v[key].as_array().ok_or_else(|| bad("array field"))?;
    if a.is_empty() || a.len() > max { return Err(bad("array bound")); } Ok(a)
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct BattlePreparation {
    seed: VehicleSeed,
    generation: u32,
    loadout: BattleLoadout,
}
impl BattlePreparation {
    pub fn loadout(&self) -> &BattleLoadout { &self.loadout }
    pub fn validate_for(&self, seed: &VehicleSeed, identity: &Profile, state: [u8; 32], generation: u32) -> io::Result<()> {
        seed.validate_session(identity, state)?;
        if self.seed != *seed || self.generation != generation || self.loadout.account_id != identity.account_id {
            return Err(bad("session/vehicle/generation mismatch"));
        } Ok(())
    }
    pub fn event(&self, session: u32) -> String {
        format!("BATTLE_LOADOUT_DOMAIN_READY session={session} generation={} policy={POLICY} profile_sha256={PROFILE_SHA} compatibility_sha256={COMPAT_SHA} native_ammo_sha256={AMMO_SHA} native_inventory_id={} turret={} gun={} shell={} count={} native_event=false native_packet=false hud=false ammo_mutation=false fire_enabled=false",
            self.generation, self.loadout.native_inventory_id, self.loadout.turret_compact_descr,
            self.loadout.gun_compact_descr, self.loadout.selected_shell_compact_descr, self.loadout.selected_shell_count)
    }
}

// Semantics are tested independently of hashes. The sole production caller
// verifies exact bytes BEFORE parsing; there is no permissive mode.
fn project(identity: &Profile, seed: &VehicleSeed, p: &Value, c: &Value, n: &Value) -> io::Result<BattleLoadout> {
    let a = &n["data"];
    if text(p, "account_id")? != identity.account_id || text(c, "account_id")? != identity.account_id
        || text(p, "username")? != identity.name || text(c, "client_name")? != identity.name
        || number(p, "native_database_id")? != identity.database_id as u32
        || number(c, "native_database_id")? != identity.database_id as u32
        || number(p, "profile_version")? != 4 || number(p, "snapshot_revision")? != 4
        || number(c, "snapshot_revision")? != 4 || number(c, "compatibility_catalog_revision")? != 3
        || number(c, "wire_sync_revision")? != 1 || number(n, "version")? != 1
        || text(n, "kind")? != "native-ms1-ammo" || number(a, "version")? != 1
        || text(a, "vehicle_compact_descr_sha256")? != hash(&seed.descriptor) {
        return Err(bad("identity/revision/descriptor"));
    }
    let inventory = rows(p, "inventory", 2)?.iter().filter(|v| v["vehicle_definition_id"].as_str() == Some("vehicle:ms1")).collect::<Vec<_>>();
    if inventory.len() != 1 { return Err(bad("owned MS-1 missing/duplicate")); }
    let inv = inventory[0]; let inventory_id = text(inv, "inventory_id")?;
    if inv["crew_assigned"].as_bool() != Some(true) { return Err(bad("crew unavailable")); }
    let vm = rows(c, "vehicle_mapping", 2)?.iter().filter(|v| v["inventory_id"].as_str() == Some(inventory_id)).collect::<Vec<_>>();
    if vm.len() != 1 || number(vm[0], "native_inventory_id")? != number(a, "vehicle_inventory_id")?
        || number(vm[0], "type_compact_descr")? != number(a, "vehicle_type_compact_descr")? { return Err(bad("vehicle mapping")); }
    let crew = rows(p, "crew", 2)?;
    if crew.len() != 2 || crew.iter().any(|v| v["vehicle_inventory_id"].as_str() != Some(inventory_id))
        || crew.iter().filter(|v| v["role"].as_str() == Some("commander")).count() != 1
        || crew.iter().filter(|v| v["role"].as_str() == Some("driver")).count() != 1 { return Err(bad("crew binding")); }
    let ammo = rows(p, "ammunition", 1)?; let mapping = rows(c, "ammo_mapping", 1)?;
    let shell = &ammo[0]; let m = &mapping[0];
    if text(shell, "vehicle_inventory_id")? != inventory_id || text(shell, "shell_definition_id")? != SELECTED
        || text(m, "shell_definition_id")? != SELECTED
        || number(inv, "ammunition_count")? != number(shell, "count")? { return Err(bad("ammunition ownership/count")); }
    let native_shells = rows(a, "shells", 16)?;
    if native_shells.iter().filter(|v| v["compact_descr"] == m["native_shell_compact_descr"]
        && v["compatible_with_mounted_gun"].as_bool() == Some(true)).count() != 1 { return Err(bad("shell incompatible")); }
    let profile = AuthenticatedVehicleProfile {
        authenticated: true, account_id: identity.account_id.clone(), vehicle_inventory_id: inventory_id.to_owned(),
        vehicle_definition_id: text(inv, "vehicle_definition_id")?.to_owned(), native_inventory_id: number(vm[0], "native_inventory_id")?,
        turret_compact_descr: number(&a["turret"], "compact_descr")?, gun_compact_descr: number(&a["gun"], "compact_descr")?,
        max_ammo: small(a, "max_ammo")?, shells: vec![ShellStack {
            shell_definition_id: text(shell, "shell_definition_id")?.to_owned(), native_shell_compact_descr: number(m, "native_shell_compact_descr")?,
            count: small(shell, "count")?,
        }],
    };
    let mapping = AmmoMapping {
        shell_definition_id: text(m, "shell_definition_id")?.to_owned(), vehicle_inventory_id: text(m, "vehicle_inventory_id")?.to_owned(),
        native_vehicle_inventory_id: number(m, "native_vehicle_inventory_id")?, native_turret_compact_descr: number(m, "native_turret_compact_descr")?,
        native_gun_compact_descr: number(m, "native_gun_compact_descr")?, native_shell_compact_descr: number(m, "native_shell_compact_descr")?,
    };
    loadout::validate(&profile, &[mapping], SELECTED).map_err(|e| bad(&e.to_string()))
}

pub fn prepare_primary_ms1(seed: &VehicleSeed, identity: &Profile, loaded_state: [u8; 32], generation: u32) -> io::Result<BattlePreparation> {
    seed.validate_session(identity, loaded_state)?;
    if generation == 0 || generation > MAX_GENERATION { return Err(bad("generation")); }
    let directory = &identity.fixture_dir;
    // Count comes from the profile, mapping from compatibility and capacity/
    // modules from the native export referenced by the exact accepted manifest.
    let p = read_pinned(&directory.join("profile-input.json"), 1877, PROFILE_SHA)?;
    let c = read_pinned(&directory.join("compatibility.json"), 1603, COMPAT_SHA)?;
    let manifest = parse(&read_pinned(&directory.join("manifest.json"), 15490, MANIFEST_SHA)?)?;
    let source = &manifest["native_descriptors"]["ammo"];
    if number(source, "bytes")? != 7683 || text(source, "sha256")? != AMMO_SHA { return Err(bad("ammo provenance")); }
    let n = read_pinned(Path::new(text(source, "file")?), 7683, AMMO_SHA)?;
    let loadout = project(identity, seed, &parse(&p)?, &parse(&c)?, &parse(&n)?)?;
    let result = BattlePreparation { seed: seed.clone(), generation, loadout };
    result.validate_for(seed, identity, loaded_state, generation)?; Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn fixture() -> (Profile, VehicleSeed, Value, Value, Value) {
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local").canonicalize().unwrap();
        let identity = Profile { account_id: crate::arena_vehicle091::PRIMARY_ACCOUNT.into(), database_id: 1,
            name: crate::arena_vehicle091::PRIMARY_NAME.into(), fixture_dir: root.join("server/fixtures").join(crate::arena_vehicle091::PRIMARY_ACCOUNT).join("r4-catalog3") };
        let f = crate::hangar091::Fixtures::load_interactive(&identity.fixture_dir).unwrap();
        let seed = crate::arena_vehicle091::load(&identity, f.state_sha256()).unwrap();
        let read = |name| parse(&std::fs::read(identity.fixture_dir.join(name)).unwrap()).unwrap();
        let (p,c) = (read("profile-input.json"), read("compatibility.json"));
        let n = parse(&std::fs::read(root.join("evidence/20261005-p02-ms1-ammo/native-ms1-ammo-export01.json")).unwrap()).unwrap();
        (identity, seed, p, c, n)
    }
    #[test] fn actual_files_bind_seed_descriptor_modules_count_capacity_and_generation() {
        let (i,s,_,_,_) = fixture(); let p = prepare_primary_ms1(&s,&i,s.state_sha256,1).unwrap(); let l = p.loadout();
        assert_eq!((l.turret_compact_descr,l.gun_compact_descr,l.selected_shell_compact_descr,l.selected_shell_count,l.total_shell_count),(5891,5892,2570,20,20));
        p.validate_for(&s,&i,s.state_sha256,1).unwrap(); assert!(p.validate_for(&s,&i,s.state_sha256,2).is_err());
        assert!(prepare_primary_ms1(&s,&i,s.state_sha256,0).is_err()); assert!(prepare_primary_ms1(&s,&i,s.state_sha256,33).is_err());
        let e=p.event(7); assert!(e.contains("native_event=false") && e.contains("fire_enabled=false"));
    }
    #[test] fn semantic_mapping_and_ammunition_mutations_are_rejected() {
        let (i,s,p,c,n)=fixture();
        for change in 0..15 { let (mut p,mut c,mut n)=(p.clone(),c.clone(),n.clone()); match change {
            0=>c["ammo_mapping"][0]["native_turret_compact_descr"]=1.into(),1=>c["ammo_mapping"][0]["native_gun_compact_descr"]=1.into(),
            2=>c["ammo_mapping"][0]["native_shell_compact_descr"]=1.into(),3=>c["ammo_mapping"][0]["native_vehicle_inventory_id"]=2.into(),
            4=>c["ammo_mapping"][0]["vehicle_inventory_id"]="foreign".into(),5=>p["ammunition"][0]["vehicle_inventory_id"]="foreign".into(),
            6=>{p["ammunition"][0]["count"]=0.into();p["inventory"][0]["ammunition_count"]=0.into();},
            7=>{p["ammunition"][0]["count"]=97.into();p["inventory"][0]["ammunition_count"]=97.into();},
            8=>p["ammunition"]=serde_json::json!([]),9=>p["snapshot_revision"]=3.into(),10=>p["account_id"]="foreign".into(),
            11=>n["data"]["vehicle_compact_descr_sha256"]="0".repeat(64).into(),12=>n["data"]["max_ammo"]=0.into(),
            13=>p["ammunition"][0]["count"]=Value::Bool(true),14=>p["crew"][0]["vehicle_inventory_id"]="foreign".into(),_=>unreachable!()
        } assert!(project(&i,&s,&p,&c,&n).is_err(),"mutation {change}"); }
    }
    #[test] fn exact_source_bytes_reject_every_mutation_truncation_extension() {
        let (i,_,_,_,_)=fixture();
        for (file,size,h) in [("profile-input.json",1877,PROFILE_SHA),("compatibility.json",1603,COMPAT_SHA),("manifest.json",15490,MANIFEST_SHA)] {
            let b=std::fs::read(i.fixture_dir.join(file)).unwrap();checked(&b,size,h).unwrap();
            for at in 0..b.len() {let mut x=b.clone();x[at]^=1;assert!(checked(&x,size,h).is_err());}
            assert!(checked(&b[..b.len()-1],size,h).is_err());let mut x=b.clone();x.push(0);assert!(checked(&x,size,h).is_err());
        }
    }
    #[test] fn missing_source_and_changed_identity_or_seed_never_fall_back() {
        let (mut i,mut s,_,_,_)=fixture();let original=i.fixture_dir.clone();i.fixture_dir=original.join("missing");
        assert!(prepare_primary_ms1(&s,&i,s.state_sha256,1).is_err());i.fixture_dir=original;i.database_id=2;
        assert!(prepare_primary_ms1(&s,&i,s.state_sha256,1).is_err());i.database_id=1;s.descriptor[0]^=1;
        assert!(prepare_primary_ms1(&s,&i,s.state_sha256,1).is_err());
    }
}
