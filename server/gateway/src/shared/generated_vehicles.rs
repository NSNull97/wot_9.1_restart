//! BATTLE-ANY: vehicles whose battle profile is generated from the #717 client
//! (`tools/battle_any_profiles.py`) instead of a hand-closed `VehicleKind` arm.
//! The table and the physics qualification record are embedded by exact bytes and
//! SHA-256; a `GeneratedId` exists only after both verified and parsed. Facts are
//! the table's source facts; physics/damage policies stay the explicit test_lab
//! ones of P04M/P06T. Owned battle admission is a separate catalog decision.
use std::{collections::BTreeMap,io,sync::OnceLock};
use serde_json::Value;
use sha2::{Digest,Sha256};
use super::vehicle_profile::{AimSpec,ShellSpec};
use super::aim::source_aim::{SourceAim,SourceEnvelope};
use crate::p06t_shells091::{Family,GunProfile,Mount,Shell};
use crate::p06t_device_caps::{Cap,Seat};

include!("battle_any_pins.rs");
const TABLE:&[u8]=include_bytes!("../../../../config/catalog/battle_profiles.v1.json");
const QUALIFICATION:&[u8]=include_bytes!("../../../../config/catalog/battle_qualification.v1.json");
pub const POLICY:&str="battle-any-generated-v1";
/// Same bound as the scene worker's angular frame and ram response.
pub const MAX_GENERATED:usize=512;

fn bad(reason:&str)->io::Error{io::Error::new(io::ErrorKind::InvalidData,format!("generated vehicles: {reason}"))}

/// Copy handle of one registry entry; only issued by this module.
#[derive(Clone,Copy,Debug,PartialEq,Eq,PartialOrd,Ord,Hash)]
pub struct GeneratedId(u16);
/// BW-01: an id from the gateway is accepted only if this process's registry issues it.
impl crate::bw_wire::Wire for GeneratedId {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){crate::bw_wire::Wire::put(&self.0,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{
        let id=<u16 as crate::bw_wire::Wire>::get(bw_i)?;
        if usize::from(id)<registry()?.entries.len(){Ok(Self(id))}else{Err(crate::bw_wire::bad("generated vehicle id"))}
    }
}
impl GeneratedId { pub fn get(self)->usize{usize::from(self.0)} }

#[derive(Debug)]
pub struct Entry {
    pub id:GeneratedId,
    pub label:String,
    pub vehicle_id:String,
    pub nation_id:u8,
    pub descriptor:Vec<u8>,
    pub type_compact_id:u32,
    pub gun_compact_id:u32,
    pub max_hp:i16,
    pub mass_kg:f64,
    pub view_range:f32,
    pub aim:AimSpec,
    pub source_aim:SourceAim,
    pub gun:GunProfile,
    pub suffixes:[String;3],
    pub caps:[Cap;9],
    pub crew:Vec<Seat>,
    pub engine_fire_chance:f64,
    pub geometry_sha256:String,
    pub geometry_revision:String,
    pub materials_revision:String,
    pub geometry_bytes:u64,
    /// Source part names (Hull/Turret_NN/Gun_NN) and ordinary armor IDs per slot.
    pub parts:[String;3],
    pub armor_ids:[Vec<u16>;3],
    pub material_kinds:[Vec<u16>;3],
    pub pivots:[[f32;3];3],
    pub physics:Value,
    pub handling:Value,
    pub qualified_sha256:String,
    pub qualified_bytes:u64,
    pub inverse_mass_bits:u32,
    pub principal_inverse_bits:[u32;3],
    pub inertia_rotation_bits:[u32;4],
    /// Native shot effectsIndex of each stack (shot_effects.xml order).
    pub effects:[u8;3],
    /// Per-kind evidence labels of the explicit test_lab policies.
    pub ap_policy:String,
    pub impact_label:String,
    pub pose_policy:String,
}
impl Entry {
    pub fn shell_spec(&self)->ShellSpec {
        let s=self.gun.shots[0];
        ShellSpec{caliber:s.caliber_mm,damage:s.damage_hp,power_100:s.penetration_mm[0],power_500:s.penetration_mm[1],
            raw_speed:s.raw_speed_mps as f32,gravity:s.raw_gravity_mps2 as f32,speed_factor:s.projectile_speed_factor as f32,
            max_distance:s.max_distance_m as f32,effects:self.effects[0]}
    }
}

pub struct Registry {
    entries:Vec<Entry>,
    by_label:BTreeMap<String,GeneratedId>,
    by_vehicle:BTreeMap<String,GeneratedId>,
    by_compact:BTreeMap<u32,GeneratedId>,
}
static REGISTRY:OnceLock<Result<Registry,String>>=OnceLock::new();

/// Verify and parse the embedded table once; repeated calls return the same result.
pub fn registry()->io::Result<&'static Registry> {
    REGISTRY.get_or_init(||build(TABLE,QUALIFICATION).map_err(|e|e.to_string())).as_ref().map_err(|e|bad(e))
}
/// An issued id always refers to a verified entry (issued only by `registry()`).
pub fn entry(id:GeneratedId)->&'static Entry {
    match REGISTRY.get() {Some(Ok(r))=>&r.entries[id.get()],_=>unreachable!("GeneratedId issued without a registry")}
}
impl Registry {
    pub fn entries(&self)->&[Entry]{&self.entries}
    pub fn by_label(&self,label:&str)->Option<GeneratedId>{self.by_label.get(label).copied()}
    pub fn by_vehicle(&self,vehicle_id:&str)->Option<GeneratedId>{self.by_vehicle.get(vehicle_id).copied()}
    pub fn by_compact(&self,compact:u32)->Option<GeneratedId>{self.by_compact.get(&compact).copied()}
    pub fn by_geometry(&self,sha256:&str)->Option<GeneratedId>{self.entries.iter().find(|e|e.geometry_sha256==sha256).map(|e|e.id)}
}

/// Client `constants.VEHICLE_CLASSES` order (#717 `scripts/common/constants.pyc`):
/// the index `Account.receiveQueueInfo` `classes` counts use.
pub const VEHICLE_CLASSES:[&str;5]=["lightTank","mediumTank","heavyTank","SPG","AT-SPG"];
static TIERS:OnceLock<Result<BTreeMap<String,(u8,u8)>,String>>=OnceLock::new();
/// MM-01: client `list.xml` `level` of every vehicle row of the embedded table
/// (generated or refused), keyed by `vehicle:<nation>:<name>`.
pub fn tier(vehicle_id:&str)->io::Result<Option<u8>> {Ok(profile(vehicle_id)?.map(|p|p.0))}
/// MM-01: (tier, `VEHICLE_CLASSES` index) from the same table row.
pub fn profile(vehicle_id:&str)->io::Result<Option<(u8,u8)>> {
    let tiers=TIERS.get_or_init(||{
        if digest(TABLE)!=TABLE_SHA256 {return Err("embedded table SHA".into());}
        let table:Value=serde_json::from_slice(TABLE).map_err(|_|"table JSON".to_owned())?;
        let mut tiers=BTreeMap::new();
        for row in table["vehicles"].as_array().ok_or_else(||"vehicle rows".to_owned())? {
            let id=row["vehicle_id"].as_str().filter(|s|!s.is_empty()&&s.len()<=128).ok_or_else(||"vehicle id".to_owned())?;
            let level=row["tier"].as_u64().and_then(|t|u8::try_from(t).ok()).filter(|t|(1..=10).contains(t)).ok_or_else(||"tier".to_owned())?;
            let class=row["vehicle_class"].as_str().and_then(|c|VEHICLE_CLASSES.iter().position(|x|*x==c)).ok_or_else(||"vehicle class".to_owned())?;
            if tiers.insert(id.to_owned(),(level,class as u8)).is_some() {return Err("duplicate vehicle".into());}
        }
        Ok(tiers)
    }).as_ref().map_err(|e|bad(e))?;
    Ok(tiers.get(vehicle_id).copied())
}

fn digest(raw:&[u8])->String{format!("{:x}",Sha256::digest(raw))}
fn f(v:&Value)->io::Result<f64>{v.as_f64().filter(|x|x.is_finite()).ok_or_else(||bad("number"))}
fn u(v:&Value)->io::Result<u64>{v.as_u64().ok_or_else(||bad("integer"))}
fn s(v:&Value)->io::Result<&str>{v.as_str().filter(|s|!s.is_empty()&&s.len()<=128).ok_or_else(||bad("string"))}
fn arr(v:&Value,n:usize)->io::Result<&Vec<Value>>{v.as_array().filter(|a|a.len()==n).ok_or_else(||bad("array length"))}
fn v3(v:&Value)->io::Result<[f32;3]>{let a=arr(v,3)?;Ok([f(&a[0])? as f32,f(&a[1])? as f32,f(&a[2])? as f32])}
fn rad(deg:f64)->f32{(deg*(std::f64::consts::PI/180.))as f32}
fn leak(text:&str)->&'static str{Box::leak(text.to_owned().into_boxed_str())}

fn family(name:&str)->io::Result<Family>{Ok(match name{"ARMOR_PIERCING"=>Family::ArmorPiercing,"ARMOR_PIERCING_CR"=>Family::ArmorPiercingCr,
    "HOLLOW_CHARGE"=>Family::HollowCharge,"HIGH_EXPLOSIVE"=>Family::HighExplosive,_=>return Err(bad("shell family"))})}

fn shell(v:&Value)->io::Result<(Shell,u8)> {
    let compact=u16::try_from(u(&v["compact_descr"])?).map_err(|_|bad("shell compact"))?;
    let pen=arr(&v["penetration_mm"],2)?;
    let effects=u8::try_from(u(&v["effects_index"])?).map_err(|_|bad("effects index"))?;
    Ok((Shell{resource:leak(s(&v["resource"])?),compact_descr:compact,family:family(s(&v["family"])?)?,caliber_mm:f(&v["caliber_mm"])?,
        damage_hp:u16::try_from(u(&v["damage_hp"])?).map_err(|_|bad("damage"))?,
        device_damage:u16::try_from(u(&v["device_damage"])?).map_err(|_|bad("device damage"))?,
        penetration_mm:[f(&pen[0])?,f(&pen[1])?],explosion_radius_m:if v["explosion_radius_m"].is_null(){None}else{Some(f(&v["explosion_radius_m"])?)},
        raw_speed_mps:f(&v["raw_speed_mps"])?,projectile_speed_factor:f(&v["projectile_speed_factor"])?,speed_mps:f(&v["speed_mps"])?,
        raw_gravity_mps2:f(&v["raw_gravity_mps2"])?,gravity_mps2:f(&v["gravity_mps2"])?,max_distance_m:f(&v["max_distance_m"])?,
        premium_gold_flag:v["premium_gold_flag"].as_bool().ok_or_else(||bad("gold flag"))?,effects_resource:leak(s(&v["effects_resource"])?),
        piercing_power_loss_factor_by_distance:if v["piercing_power_loss_factor_by_distance"].is_null(){None}else{Some(f(&v["piercing_power_loss_factor_by_distance"])?)}},
        effects))
}

/// Source pitch/yaw envelope (degrees in the table) in the P06T f32 form.
fn envelope(gun:&Value)->io::Result<SourceEnvelope> {
    let e=&gun["pitch_envelope"];let basic=arr(&e["basic"],2)?;let basic=(rad(f(&basic[0])?),rad(f(&basic[1])?));
    let extra=|key:&str|->io::Result<Option<(f32,f32,f32)>>{if e[key].is_null(){return Ok(None);}
        let a=arr(&e[key],3)?;Ok(Some((rad(f(&a[0])?),rad(f(&a[1])?),rad(f(&a[2])?))))};
    // Missing XML transition uses the source default 0.4 radians (P06T WT/FV proof).
    let transition=if e["transition_degrees"].is_null(){0.4}else{rad(f(&e["transition_degrees"])?)};
    let yaw=if gun["turret_yaw_limits"].is_null(){None}else{let y=arr(&gun["turret_yaw_limits"],2)?;
        let (lo,hi)=(f(&y[0])?,f(&y[1])?);if lo<=-180.&&hi>=180.{None}else{Some((rad(lo),rad(hi)))}};
    SourceEnvelope::from_source(basic,extra("front")?,extra("back")?,transition,yaw).map_err(|_|bad("pitch/yaw envelope"))
}

fn build(table:&[u8],qualification:&[u8])->io::Result<Registry> {
    if digest(table)!=TABLE_SHA256||digest(qualification)!=QUALIFICATION_SHA256 {return Err(bad("embedded table/qualification SHA"));}
    let table:Value=serde_json::from_slice(table).map_err(|_|bad("table JSON"))?;
    let qualification:Value=serde_json::from_slice(qualification).map_err(|_|bad("qualification JSON"))?;
    if table["schema"]!="wot091-battle-profiles.v1"||qualification["schema"]!="wot091-battle-qualification.v1"
        ||qualification["policy"]!=POLICY {return Err(bad("schema/policy"));}
    let mut qualified=BTreeMap::new();
    for row in qualification["profiles"].as_array().ok_or_else(||bad("qualified rows"))? {qualified.insert(s(&row["kind"])?.to_owned(),row);}
    let mut entries=Vec::new();
    for row in table["vehicles"].as_array().ok_or_else(||bad("vehicle rows"))? {
        if row["status"]!="generated" {continue;}
        let label=s(&row["kind"])?;
        // The five legacy kinds keep their hand-closed VehicleKind arms.
        if matches!(label,"ms1"|"is7"|"t26"|"t34"|"t3485") {continue;}
        let q=qualified.get(label).ok_or_else(||bad("generated row without qualification"))?;
        if entries.len()>=MAX_GENERATED {return Err(bad("registry size"));}
        let id=GeneratedId(u16::try_from(entries.len()).map_err(|_|bad("id"))?);
        let identity=&row["identity"];let g=&row["gun"];
        let descriptor=hex(s(&identity["descriptor_hex"])?)?;
        let shots=arr(&row["shots"],3)?;
        let parsed=[shell(&shots[0])?,shell(&shots[1])?,shell(&shots[2])?];
        let nation=u8::try_from(u(&row["native_nation_id"])?).map_err(|_|bad("nation"))?;
        let type_cd=u32::try_from(u(&identity["type_compact_id"])?).map_err(|_|bad("type"))?;
        let gun_cd=u32::try_from(u(&identity["module_compact_ids"]["gun"])?).map_err(|_|bad("gun"))?;
        let clip=u8::try_from(u(&g["clip_count"])?).ok().filter(|c|(1..=6).contains(c)).ok_or_else(||bad("clip"))?;
        let gun=GunProfile{mount:Mount::Generated(id),native_nation_id:nation,
            vehicle_type_compact_descr:u16::try_from(type_cd).map_err(|_|bad("type u16"))?,
            gun_compact_descr:u16::try_from(gun_cd).map_err(|_|bad("gun u16"))?,
            capacity:u16::try_from(u(&g["max_ammo"])?).map_err(|_|bad("capacity"))?,reload_seconds:f(&g["reload_seconds"])?,
            clip_count:clip,clip_interval_seconds:f(&g["clip_interval_seconds"])?,clip_from_mounted_source:g["clip_source"]=="MOUNTED_OR_SHARED",
            burst_count:1,burst_interval_seconds:0.,additional_vehicle_qualification_required:false,shots:parsed.map(|(s,_)|s)};
        let pivots_v=&row["pivots"];
        let pivots=[v3(&pivots_v["hull_position"])?,v3(&pivots_v["turret_position"])?,v3(&pivots_v["gun_position"])?];
        let env=envelope(g)?;
        let basic=env.basic();
        let back=&g["pitch_envelope"]["back"];
        let (rear_sector,rear_max)=if back.is_null(){(0.,basic.max.to_degrees())}else{let a=arr(back,3)?;(f(&a[2])? as f32,f(&a[1])? as f32)};
        let aim=AimSpec{yaw_rate:rad(f(&g["turret_rotation_deg_s"])?),pitch_rate:rad(f(&g["gun_rotation_deg_s"])?),
            min_pitch:basic.min,max_pitch:basic.max,max_pitch_degrees:f(&arr(&g["pitch_envelope"]["basic"],2)?[1])? as f32,
            rear_sector_degrees:rear_sector,rear_max_degrees:rear_max,
            pivot:[pivots[0][0]+pivots[1][0],pivots[0][1]+pivots[1][1],pivots[0][2]+pivots[1][2]],gun:pivots[2],
            turret_dispersion:f(&g["dispersion_turret_rotation"])? as f32/1f32.to_radians(),
            movement_dispersion:f(&g["dispersion_vehicle_movement"])? as f32*3.6,
            hull_dispersion:f(&g["dispersion_vehicle_rotation"])? as f32/1f32.to_radians(),aiming_time:f(&g["aiming_seconds"])? as f32};
        let source_aim=SourceAim{envelope:env,yaw_rate:aim.yaw_rate,pitch_rate:aim.pitch_rate};
        let suffix=arr(&row["shell_suffixes"],3)?;
        let devices=arr(&row["devices"],9)?;
        let mut caps=[Cap{max:0,regen:0};9];
        for (i,d) in devices.iter().enumerate() {
            if u(&d["extra_index"])?!=26+i as u64 {return Err(bad("device order"));}
            caps[i]=Cap{max:u16::try_from(u(&d["max_health"])?).map_err(|_|bad("cap"))?,regen:u16::try_from(u(&d["max_regen_health"])?).map_err(|_|bad("regen"))?};
        }
        let mut crew=Vec::new();
        for seat in row["crew_seats"].as_array().filter(|a|(1..=8).contains(&a.len())).ok_or_else(||bad("crew seats"))? {
            let roles=seat["roles"].as_array().ok_or_else(||bad("roles"))?;
            crew.push(Seat{extra:u8::try_from(u(&seat["extra_index"])?).map_err(|_|bad("extra"))?,
                roles:u8::try_from(u(&seat["role_bits"])?).map_err(|_|bad("role bits"))?,
                primary_driver:roles.first()==Some(&Value::from("driver")),primary_radioman:roles.first()==Some(&Value::from("radioman"))});
        }
        let geometry=&row["geometry"];let geometry_sha=s(&geometry["sha256"])?.to_owned();
        let components=arr(&geometry["components"],3)?;
        let ids=|c:&Value,key:&str|->io::Result<Vec<u16>>{c[key].as_array().ok_or_else(||bad("ids"))?.iter()
            .map(|v|u16::try_from(u(v)?).map_err(|_|bad("id"))).collect()};
        let parts=[s(&components[0]["name"])?.to_owned(),s(&components[1]["name"])?.to_owned(),s(&components[2]["name"])?.to_owned()];
        if parts[0]!="Hull"||!parts[1].starts_with("Turret_")||!parts[2].starts_with("Gun_") {return Err(bad("component parts"));}
        let armor_ids=[ids(&components[0],"armor_ids")?,ids(&components[1],"armor_ids")?,ids(&components[2],"armor_ids")?];
        let material_kinds=[ids(&components[0],"material_kinds")?,ids(&components[1],"material_kinds")?,ids(&components[2],"material_kinds")?];
        let effects=parsed.map(|(_,e)|e);
        let bits=|key:&str,n:usize|->io::Result<Vec<u32>>{arr(&q[key],n)?.iter().map(|x|u32::try_from(u(x)?).map_err(|_|bad("bits"))).collect()};
        let principal=bits("principal_inverse_bits",3)?;let rotation=bits("inertia_rotation_bits_xyzw",4)?;
        let entry=Entry{id,label:label.to_owned(),vehicle_id:s(&row["vehicle_id"])?.to_owned(),nation_id:nation,descriptor,
            type_compact_id:type_cd,gun_compact_id:gun_cd,
            max_hp:i16::try_from(u(&identity["max_hp"])?).map_err(|_|bad("hp"))?,mass_kg:f(&identity["mass_kg"])?,
            view_range:f(&row["view_range_m"])? as f32,aim,source_aim,gun,
            suffixes:[s(&suffix[0])?.to_owned(),s(&suffix[1])?.to_owned(),s(&suffix[2])?.to_owned()],caps,crew,
            engine_fire_chance:f(&row["engine_fire_starting_chance"])?,
            geometry_revision:format!("battle-any-collision-717:{geometry_sha}"),materials_revision:format!("battle-any-materials-717:{geometry_sha}"),geometry_sha256:geometry_sha,
            geometry_bytes:u(&geometry["bytes"])?,parts,armor_ids,material_kinds,pivots,physics:row["physics"].clone(),handling:row["handling"].clone(),
            qualified_sha256:s(&q["sha256"])?.to_owned(),qualified_bytes:u(&q["bytes"])?,
            inverse_mass_bits:u32::try_from(u(&q["inverse_mass_bits"])?).map_err(|_|bad("mass bits"))?,
            principal_inverse_bits:[principal[0],principal[1],principal[2]],inertia_rotation_bits:[rotation[0],rotation[1],rotation[2],rotation[3]],
            ap_policy:format!("test_lab-battle-any-{label}-ap-single-plate-v1"),
            impact_label:format!("battle_any_{}_ap_{}",label.replace('-',"_").to_lowercase(),parsed[0].0.compact_descr),
            pose_policy:format!("test_lab-battle-any-{label}-source-full-pose-v1"),
            effects};
        entries.push(entry);
    }
    if entries.is_empty() {return Err(bad("empty registry"));}
    let mut by_label=BTreeMap::new();let mut by_vehicle=BTreeMap::new();let mut by_compact=BTreeMap::new();
    for e in &entries {
        if by_label.insert(e.label.clone(),e.id).is_some()||by_vehicle.insert(e.vehicle_id.clone(),e.id).is_some()
            ||by_compact.insert(e.type_compact_id,e.id).is_some() {return Err(bad("duplicate generated identity"));}
    }
    Ok(Registry{entries,by_label,by_vehicle,by_compact})
}
fn hex(text:&str)->io::Result<Vec<u8>> {
    if text.len()%2!=0||text.len()>64 {return Err(bad("descriptor hex"));}
    (0..text.len()).step_by(2).map(|i|u8::from_str_radix(&text[i..i+2],16).map_err(|_|bad("descriptor hex"))).collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use super::super::vehicle_profile::VehicleKind;

    #[test]
    fn embedded_registry_verifies_and_excludes_legacy_kinds() {
        let r=registry().unwrap();
        // 232 generated rows minus the five hand-closed kinds.
        assert_eq!(r.entries().len(),227);
        for refused in ["vehicle:france:AMX_13_90","vehicle:france:AMX_M4_1945"] {assert!(r.by_vehicle(refused).is_none(),"{refused}");}
        for (i,e) in r.entries().iter().enumerate() {
            assert_eq!(e.id.get(),i);assert_eq!(r.by_label(&e.label),Some(e.id));
            assert!(VehicleKind::from_label(&e.label).is_none(),"{} shadows a legacy label",e.label);
            assert!((1..=6).contains(&e.gun.clip_count)&&e.gun.burst_count==1,"{}",e.label);
            assert!(!e.crew.is_empty()&&e.max_hp>0&&e.gun.capacity>0,"{}",e.label);
        }
    }

    #[test]
    fn agents_invariants_wt_drum_six_and_fv_hesh_275() {
        let r=registry().unwrap();
        let wt=entry(r.by_vehicle("vehicle:germany:Waffentrager_E100").unwrap());
        assert_eq!((wt.gun.clip_count,wt.gun.capacity,wt.gun_compact_id),(6,60,23060));
        let fv=entry(r.by_vehicle("vehicle:uk:GB48_FV215b_183").unwrap());
        let hesh=fv.gun.shots.iter().find(|s|s.compact_descr==21082).unwrap();
        assert_eq!((hesh.family,hesh.penetration_mm,hesh.premium_gold_flag,fv.gun_compact_id),
            (Family::HighExplosive,[275.,275.],true,13908));
    }

    /// WT/FV exist both as closed P06T kinds and as generated rows; the two must not diverge.
    #[test]
    fn generated_wt_fv_match_closed_kinds() {
        let r=registry().unwrap();
        for (vehicle,kind) in [("vehicle:germany:Waffentrager_E100",VehicleKind::Wt128),("vehicle:uk:GB48_FV215b_183",VehicleKind::Fv183)] {
            let g=VehicleKind::Generated(r.by_vehicle(vehicle).unwrap());
            assert_eq!(g.descriptor(),kind.descriptor(),"{vehicle}");
            assert_eq!((g.vehicle_compact_id(),g.gun_compact_id(),g.shell_compact_id()),
                (kind.vehicle_compact_id(),kind.gun_compact_id(),kind.shell_compact_id()),"{vehicle}");
            assert_eq!((g.max_health(),g.ammo_limit(),g.panel_rows()),(kind.max_health(),kind.ammo_limit(),kind.panel_rows()),"{vehicle}");
            assert_eq!((g.reload_seconds(),g.view_range(),g.mass_kg()),(kind.reload_seconds(),kind.view_range(),kind.mass_kg()),"{vehicle}");
            let(a,b)=(g.shell(),kind.shell());
            assert_eq!((a.caliber,a.damage,a.power_100,a.power_500,a.raw_speed,a.effects),
                (b.caliber,b.damage,b.power_100,b.power_500,b.raw_speed,b.effects),"{vehicle}");
        }
    }

    #[test]
    fn tampered_or_foreign_bytes_are_refused() {
        let mut table=TABLE.to_vec();let n=table.len();table[n/2]^=1;
        assert!(build(&table,QUALIFICATION).is_err());
        let mut q=QUALIFICATION.to_vec();let n=q.len();q[n/2]^=1;
        assert!(build(TABLE,&q).is_err());
        assert!(build(QUALIFICATION,TABLE).is_err());
        assert!(hex("0").is_err()&&hex("zz").is_err()&&hex(&"00".repeat(33)).is_err());
    }
}
