//! Source facts of a contacted #717 surface, not a penetration/HP decision.
use std::io;
use serde_json::{json, Value};
use super::{model::bad, vehicle_profile::VehicleKind};

pub const PROFILE_REVISION: &str = "ms1-contact-717:7666849add0757fd91c224dbc6c0a6550d8ae1bca434f175eaa5c66b06e2d9ab";
pub const IS7_PROFILE_REVISION: &str = "is7-contact-717:ebb3b8ae6dd383f1f8c31bde7c97257f8569fd626ff79ca8ad030848c1c3ab26";
pub fn profile_revision(kind: VehicleKind) -> &'static str { match kind {
    VehicleKind::Ms1 => PROFILE_REVISION, VehicleKind::Is7 => IS7_PROFILE_REVISION,
    VehicleKind::T26=>"p04m-t26-materials-717:7b6c41b5d8678a6f935701547781090c517649f741c05621a0cbaf063670e55e",
    VehicleKind::T34=>"p04m-t34-materials-717:6c64732e7421f139991df3cdb0d0d161a3d563a3312fcef040a089d26508c306",
    VehicleKind::T3485=>"p04m-t3485-materials-717:25b6c69fd51e26abbda9b16c35572b5f289f2320d0dffe4085dea1b7bdeba1bb",
    VehicleKind::Wt128=>"p06t-wt128-materials-717:0971afa6aed7bbbb0c4ba647560e15002571544cc168005679a9d46a22962aae",
    VehicleKind::Fv183=>"p06t-fv183-materials-717:c14b10be359a86c4c4632cd0943d06c43a47fc9ede2a982880c4f09aed6ecb1d",
    VehicleKind::Generated(id)=>&super::generated_vehicles::entry(id).materials_revision,
} }

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Component { Hull, Turret01, Gun02, Gun01 }
// BW-01 wire codec (tools/bw01_wire_gen.py): Component
impl crate::bw_wire::Wire for Component {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){match self {Self::Hull=>bw_o.tag(0),Self::Turret01=>bw_o.tag(1),Self::Gun02=>bw_o.tag(2),Self::Gun01=>bw_o.tag(3),}}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{match bw_i.tag()? {0=>Ok(Self::Hull),1=>Ok(Self::Turret01),2=>Ok(Self::Gun02),3=>Ok(Self::Gun01),t=>crate::bw_wire::variant(t)}}
}
// end BW-01 wire codec
impl Component {
    pub fn name(self) -> &'static str { match self { Self::Hull => "Hull", Self::Turret01 => "Turret_01", Self::Gun02 => "Gun_02", Self::Gun01 => "Gun_01" } }
    fn parse(s: &str) -> io::Result<Self> { match s {
        "Hull" => Ok(Self::Hull), "Turret_01" => Ok(Self::Turret01), "Gun_02" => Ok(Self::Gun02), "Gun_01" => Ok(Self::Gun01), _ => Err(bad()) } }
}
/// Exact source armor IDs, including genuine holes. No renumbering to a
/// guessed 1..max range. Non-mounted gun components have no valid IDs.
pub(super) fn armor_ids(vehicle:VehicleKind,component:Component)->&'static[u16] {
    match (vehicle,component) {
        (VehicleKind::Ms1,Component::Hull)=>&[1,2,3,4,5,6,7,8,9,10,11,12],
        (VehicleKind::Ms1,Component::Turret01)=>&[1,2,3,4,5,6,7,8,9,10],
        (VehicleKind::Ms1,Component::Gun02)=>&[1,2,3],
        (VehicleKind::Is7,Component::Hull)=>&[1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16],
        (VehicleKind::Is7,Component::Turret01)=>&[1,2,3,4,5,6,7,8,9,10,11,12],
        (VehicleKind::Is7,Component::Gun01)=>&[1,2,3],
        (VehicleKind::T26|VehicleKind::T34,Component::Hull)=>&[1,2,3,4,5,6,7,8,9,10],
        (VehicleKind::T26,Component::Turret01)=>&[1,2,3,4,5,6,7,8],
        (VehicleKind::T26,Component::Gun02)=>&[1,2],
        (VehicleKind::T34,Component::Turret01)=>&[1,2,3,4,5,6,7,8,9],
        (VehicleKind::T34,Component::Gun01)=>&[1,2,3],
        (VehicleKind::T3485,Component::Hull)=>&[1,2,3,4,5,6,7,8,9,10,11,12,13,15,16],
        (VehicleKind::T3485,Component::Turret01)=>&[1,2,3,4,5,6,7,8,9,10,11,12,13],
        (VehicleKind::T3485,Component::Gun01)=>&[1,2,4,5,6],
        (VehicleKind::Wt128,Component::Hull)=>&[1,2,3,4,5,7,8,9,10,11,12,13],
        (VehicleKind::Wt128,Component::Turret01)=>&[1,2,3,4,5,6,7,8],
        (VehicleKind::Fv183,Component::Hull|Component::Turret01)=>&[1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16],
        (VehicleKind::Fv183,Component::Gun01)=>&[1],
        (VehicleKind::Generated(id),component)=>{let e=super::generated_vehicles::entry(id);match component{
            Component::Hull=>&e.armor_ids[0],Component::Turret01=>&e.armor_ids[1],Component::Gun01=>&e.armor_ids[2],Component::Gun02=>&[]}},
        _=>&[],
    }
}
pub(super) fn gun_component(vehicle:VehicleKind)->Component {
    match vehicle {VehicleKind::Ms1|VehicleKind::T26=>Component::Gun02,_=>Component::Gun01}
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SourceClass { ArmorDescriptor, GunVisualMaterial, SurveyingDeviceVisualMaterial, GunBreechVisualMaterial }
// BW-01 wire codec (tools/bw01_wire_gen.py): SourceClass
impl crate::bw_wire::Wire for SourceClass {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){match self {Self::ArmorDescriptor=>bw_o.tag(0),Self::GunVisualMaterial=>bw_o.tag(1),Self::SurveyingDeviceVisualMaterial=>bw_o.tag(2),Self::GunBreechVisualMaterial=>bw_o.tag(3),}}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{match bw_i.tag()? {0=>Ok(Self::ArmorDescriptor),1=>Ok(Self::GunVisualMaterial),2=>Ok(Self::SurveyingDeviceVisualMaterial),3=>Ok(Self::GunBreechVisualMaterial),t=>crate::bw_wire::variant(t)}}
}
// end BW-01 wire codec
impl SourceClass {
    fn name(self) -> &'static str { match self {
        Self::ArmorDescriptor => "armor_descriptor", Self::GunVisualMaterial => "gun_visual_material",
        Self::SurveyingDeviceVisualMaterial => "surveying_device_visual_material",
        Self::GunBreechVisualMaterial=>"gun_breech_visual_material" } }
}
#[derive(Clone, Debug, PartialEq)]
pub struct EffectiveMaterial {
    pub kind: u16, pub armor: Option<f32>, pub extra_is_none: bool,
    pub vehicle_damage_factor: f32, pub use_armor_homogenization: bool,
    pub use_hit_angle: bool, pub use_antifragmentation_lining: bool,
    pub may_ricochet: bool, pub collide_once_only: bool, pub damage_kind: u8,
    pub chance_to_hit_by_projectile: f32, pub chance_to_hit_by_explosion: f32,
    pub continue_trace_if_no_hit: bool,
}
// BW-01 wire codec (tools/bw01_wire_gen.py): EffectiveMaterial
impl crate::bw_wire::Wire for EffectiveMaterial {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{kind,armor,extra_is_none,vehicle_damage_factor,use_armor_homogenization,use_hit_angle,use_antifragmentation_lining,may_ricochet,collide_once_only,damage_kind,chance_to_hit_by_projectile,chance_to_hit_by_explosion,continue_trace_if_no_hit}=self;W::put(kind,bw_o);W::put(armor,bw_o);W::put(extra_is_none,bw_o);W::put(vehicle_damage_factor,bw_o);W::put(use_armor_homogenization,bw_o);W::put(use_hit_angle,bw_o);W::put(use_antifragmentation_lining,bw_o);W::put(may_ricochet,bw_o);W::put(collide_once_only,bw_o);W::put(damage_kind,bw_o);W::put(chance_to_hit_by_projectile,bw_o);W::put(chance_to_hit_by_explosion,bw_o);W::put(continue_trace_if_no_hit,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{kind:W::get(bw_i)?,armor:W::get(bw_i)?,extra_is_none:W::get(bw_i)?,vehicle_damage_factor:W::get(bw_i)?,use_armor_homogenization:W::get(bw_i)?,use_hit_angle:W::get(bw_i)?,use_antifragmentation_lining:W::get(bw_i)?,may_ricochet:W::get(bw_i)?,collide_once_only:W::get(bw_i)?,damage_kind:W::get(bw_i)?,chance_to_hit_by_projectile:W::get(bw_i)?,chance_to_hit_by_explosion:W::get(bw_i)?,continue_trace_if_no_hit:W::get(bw_i)?})}
}
// end BW-01 wire codec
impl EffectiveMaterial {
    fn from_value(v: &Value, kind: u16) -> io::Result<Self> {
        fields(v, &["kind", "armor", "extra_is_none", "vehicleDamageFactor", "useArmorHomogenization",
            "useHitAngle", "useAntifragmentationLining", "mayRicochet", "collideOnceOnly", "damageKind",
            "chanceToHitByProjectile", "chanceToHitByExplosion", "continueTraceIfNoHit"])?;
        if v["kind"].as_u64() != Some(kind as u64) { return Err(bad()); }
        let armor = if v["armor"].is_null() { None } else { Some(scalar(&v["armor"], 100000.)?) };
        Ok(Self { kind, armor, extra_is_none: flag(&v["extra_is_none"])? ,
            vehicle_damage_factor: scalar(&v["vehicleDamageFactor"], 1.)?,
            use_armor_homogenization: flag(&v["useArmorHomogenization"])?,
            use_hit_angle: flag(&v["useHitAngle"])?,
            use_antifragmentation_lining: flag(&v["useAntifragmentationLining"])?,
            may_ricochet: flag(&v["mayRicochet"])?, collide_once_only: flag(&v["collideOnceOnly"])?,
            damage_kind: u8::try_from(v["damageKind"].as_u64().filter(|x| *x <= 1).ok_or_else(|| bad())?).map_err(|_| bad())?,
            chance_to_hit_by_projectile: scalar(&v["chanceToHitByProjectile"], 1.)?,
            chance_to_hit_by_explosion: scalar(&v["chanceToHitByExplosion"], 1.)?,
            continue_trace_if_no_hit: flag(&v["continueTraceIfNoHit"])? })
    }
    fn json(&self) -> Value { json!({"kind": self.kind, "armor": self.armor, "extra_is_none": self.extra_is_none,
        "vehicleDamageFactor": self.vehicle_damage_factor, "useArmorHomogenization": self.use_armor_homogenization,
        "useHitAngle": self.use_hit_angle, "useAntifragmentationLining": self.use_antifragmentation_lining,
        "mayRicochet": self.may_ricochet, "collideOnceOnly": self.collide_once_only, "damageKind": self.damage_kind,
        "chanceToHitByProjectile": self.chance_to_hit_by_projectile, "chanceToHitByExplosion": self.chance_to_hit_by_explosion,
        "continueTraceIfNoHit": self.continue_trace_if_no_hit }) }
}
#[derive(Clone, Debug, PartialEq)]
pub struct MaterialFacts {
    pub component: Component, pub name: String, pub kind: u16, pub source_class: SourceClass,
    /// None means the native component table has no record. It is not armor=0.
    pub effective: Option<EffectiveMaterial>, pub profile_revision: String,
}
// BW-01 wire codec (tools/bw01_wire_gen.py): MaterialFacts
impl crate::bw_wire::Wire for MaterialFacts {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{component,name,kind,source_class,effective,profile_revision}=self;W::put(component,bw_o);W::put(name,bw_o);W::put(kind,bw_o);W::put(source_class,bw_o);W::put(effective,bw_o);W::put(profile_revision,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{component:W::get(bw_i)?,name:W::get(bw_i)?,kind:W::get(bw_i)?,source_class:W::get(bw_i)?,effective:W::get(bw_i)?,profile_revision:W::get(bw_i)?})}
}
// end BW-01 wire codec
impl MaterialFacts {
    pub fn json(&self) -> Value { json!({"component": self.component.name(), "name": self.name,
        "kind": self.kind, "source_class": self.source_class.name(), "effective": self.effective.as_ref().map(EffectiveMaterial::json),
        "profile_revision": self.profile_revision, "normal_orientation": "unknown_triangle_winding_only",
        "ballistic_outcome": "unresolved", "damage_applied": false }) }
}
#[derive(Clone, Debug)]
pub struct Catalog { entries: Vec<MaterialFacts> }
// BW-01 wire codec (tools/bw01_wire_gen.py): Catalog
impl crate::bw_wire::Wire for Catalog {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{entries}=self;W::put(entries,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{entries:W::get(bw_i)?})}
}
// end BW-01 wire codec
fn fields(v: &Value, keys: &[&str]) -> io::Result<()> { crate::map_drive_worker091::fields(v, keys).map(|_| ()) }
fn flag(v: &Value) -> io::Result<bool> { v.as_bool().ok_or_else(|| bad()) }
fn scalar(v: &Value, max: f64) -> io::Result<f32> {
    let x = v.as_f64().filter(|x| x.is_finite() && *x >= 0. && *x <= max).ok_or_else(|| bad())?;
    Ok(x as f32)
}
impl Catalog {
    #[cfg(test)]
    pub(super) fn empty_for_test() -> Self { Self { entries: Vec::new() } }
    /// Called only after the enclosing bundle's exact approved digest check.
    pub(super) fn from_value(revision: &Value, rows: &Value) -> io::Result<Self> {
        Self::from_value_for(VehicleKind::Ms1, revision, rows)
    }
    pub(super) fn from_value_for(vehicle: VehicleKind, revision: &Value, rows: &Value) -> io::Result<Self> {
        let revision_expected = profile_revision(vehicle);
        if revision.as_str() != Some(revision_expected) { return Err(bad()); }
        let (hull_max, turret_max, gun) = match vehicle {
            VehicleKind::Ms1 => (12, 10, Component::Gun02), VehicleKind::Is7 => (16, 12, Component::Gun01),
            _=>return Err(bad()), // New source export has a distinct checked shape.
        };
        let rows = rows.as_array().filter(|a| a.len() == 3).ok_or_else(|| bad())?;
        let mut entries = Vec::new();
        for (index, row) in rows.iter().enumerate() {
            fields(row, &["component", "entries"])?;
            let component = Component::parse(row["component"].as_str().ok_or_else(|| bad())?)?;
            if component != [Component::Hull, Component::Turret01, gun][index] { return Err(bad()); }
            let expected: Vec<u16> = match component {
                Component::Hull => (1..=hull_max).chain([28]).collect(),
                Component::Turret01 => (1..=turret_max).chain([28]).collect(), Component::Gun02 | Component::Gun01 => vec![1,2,3,25] };
            let values = row["entries"].as_array().filter(|a| a.len() == expected.len()).ok_or_else(|| bad())?;
            for (entry, kind) in values.iter().zip(expected) {
                fields(entry, &["name", "kind", "source_class", "effective"])?;
                let (name, source_class) = match kind {
                    25 => ("gun".into(), SourceClass::GunVisualMaterial),
                    28 => ("surveyingDevice".into(), SourceClass::SurveyingDeviceVisualMaterial),
                    _ => (format!("armor_{kind}"), SourceClass::ArmorDescriptor) };
                if entry["kind"].as_u64() != Some(kind as u64) || entry["name"].as_str() != Some(&name)
                    || entry["source_class"].as_str() != Some(source_class.name()) { return Err(bad()); }
                // Missing surveyingDevice is an observed table fact, explicitly
                // distinct from the two real zero-armor records.
                let effective = if kind == 28 {
                    if !entry["effective"].is_null() { return Err(bad()); } None
                } else { Some(EffectiveMaterial::from_value(&entry["effective"], kind)?) };
                entries.push(MaterialFacts { component, name, kind, source_class, effective, profile_revision: revision_expected.into() });
            }
        }
        Ok(Self { entries })
    }
    /// Closed new-source facts only. Gun31 remains a separate unsupported
    /// source class: ordinary armor and exterior gun25 policy do not accept it.
    pub(super) fn from_p06t_source(vehicle:VehicleKind,source:&super::p06t_geometry_source::SourceBundle)->io::Result<Self>{
        use super::p06t_geometry_source::{Assembly,SourceClass as Source};
        let expected=match vehicle{VehicleKind::Wt128=>Assembly::Wt128,VehicleKind::Fv183=>Assembly::Fv183,_=>return Err(bad())};
        if source.assembly!=expected||source.components.len()!=3{return Err(bad());}
        let mut entries=Vec::new();
        for(i,c)in source.components.iter().enumerate(){
            let component=[Component::Hull,Component::Turret01,Component::Gun01][i];
            if c.name!=component.name(){return Err(bad());}
            for m in &c.materials{
                let source_class=match m.source_class{Source::ArmorDescriptor=>SourceClass::ArmorDescriptor,
                    Source::GunVisual=>SourceClass::GunVisualMaterial,Source::SurveyingDeviceVisual=>SourceClass::SurveyingDeviceVisualMaterial,
                    Source::GunBreechVisualUnsupported=>SourceClass::GunBreechVisualMaterial};
                let effective=m.effective.as_ref().map(|v|EffectiveMaterial::from_value(v,m.kind)).transpose()?;
                entries.push(MaterialFacts{component,name:m.name.clone(),kind:m.kind,source_class,effective,profile_revision:profile_revision(vehicle).into()});
            }
        }
        Ok(Self{entries})
    }
    /// BATTLE-ANY generated bundle (digest bound by the registry). Slots map to
    /// Hull/Turret_01/Gun_01 whatever the source part names; material kinds and
    /// their order must equal the registry's table facts.
    pub(super) fn from_generated(vehicle:VehicleKind,components:&Value)->io::Result<Self> {
        let e=vehicle.generated().ok_or_else(||bad())?;
        let rows=components.as_array().filter(|rows|rows.len()==3).ok_or_else(||bad())?;
        let mut entries=Vec::new();
        for (index,row) in rows.iter().enumerate() {
            let component=[Component::Hull,Component::Turret01,Component::Gun01][index];
            if row["name"].as_str()!=Some(e.parts[index].as_str()) {return Err(bad());}
            let values=row["materials"].as_array().filter(|v|v.len()==e.material_kinds[index].len()).ok_or_else(||bad())?;
            for (value,kind) in values.iter().zip(e.material_kinds[index].iter().copied()) {
                fields(value,&["name","kind","effective"])?;
                let(name,source_class)=match kind {
                    25=>("gun".to_owned(),SourceClass::GunVisualMaterial),
                    28=>("surveyingDevice".to_owned(),SourceClass::SurveyingDeviceVisualMaterial),
                    31=>("gunBreech".to_owned(),SourceClass::GunBreechVisualMaterial),
                    1..=16=>(format!("armor_{kind}"),SourceClass::ArmorDescriptor),
                    _=>return Err(bad()),
                };
                if value["kind"].as_u64()!=Some(kind as u64)||value["name"].as_str()!=Some(name.as_str()) {return Err(bad());}
                let effective=if value["effective"].is_null(){None}else{Some(EffectiveMaterial::from_value(&value["effective"],kind)?)};
                entries.push(MaterialFacts{component,name,kind,source_class,effective,profile_revision:profile_revision(vehicle).into()});
            }
        }
        Ok(Self{entries})
    }
    /// Only used after the exact approved P04M full-source export digest gate.
    pub(super) fn from_p04m_for(vehicle:VehicleKind,components:&Value)->io::Result<Self> {
        if !matches!(vehicle,VehicleKind::T26|VehicleKind::T34|VehicleKind::T3485) {return Err(bad());}
        let rows=components.as_array().filter(|rows|rows.len()==3).ok_or_else(||bad())?;
        let mut entries=Vec::new();
        for (index,row) in rows.iter().enumerate() {
            let component=[Component::Hull,Component::Turret01,gun_component(vehicle)][index];
            if row["name"].as_str()!=Some(component.name()) {return Err(bad());}
            let mut expected=armor_ids(vehicle,component).to_vec();expected.push(if index==2{25}else{28});
            let values=row["materials"].as_array().filter(|v|v.len()==expected.len()).ok_or_else(||bad())?;
            for (value,kind) in values.iter().zip(expected) {
                fields(value,&["name","kind","effective"])?;
                let(name,source_class)=match kind {
                    25=>("gun".to_owned(),SourceClass::GunVisualMaterial),
                    28=>("surveyingDevice".to_owned(),SourceClass::SurveyingDeviceVisualMaterial),
                    _=>(format!("armor_{kind}"),SourceClass::ArmorDescriptor),
                };
                if value["kind"].as_u64()!=Some(kind as u64)||value["name"].as_str()!=Some(name.as_str()) {return Err(bad());}
                let effective=if kind==28 {
                    if !value["effective"].is_null() {return Err(bad());}None
                } else {Some(EffectiveMaterial::from_value(&value["effective"],kind)?)};
                entries.push(MaterialFacts{component,name,kind,source_class,effective,profile_revision:profile_revision(vehicle).into()});
            }
        }
        Ok(Self{entries})
    }
    pub fn lookup(&self, component: &str, label: &str) -> io::Result<MaterialFacts> {
        let component = Component::parse(component)?;
        self.entries.iter().find(|e| e.component == component && e.name == label).cloned().ok_or_else(|| bad())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn values() -> Value {
        let root = std::env::var("WOT091_ROOT").unwrap_or_else(|_| "D:/WoT_9.1_Server".into());
        let path = std::path::Path::new(&root).join("local/evidence/20261010-p06j-contact-materials-01/ms1-contact.json");
        serde_json::from_slice(&std::fs::read(path).unwrap()).unwrap()
    }
    #[test] fn is7_material_table_keeps_all_ordinary_screen_zero_and_device_facts() {
        let bundle = super::super::geometry::tests::is7_bundle(); let c = bundle.materials();
        for (part, label, armor, factor) in [("Hull", "armor_16", 100., 1.), ("Turret_01", "armor_12", 30., 1.),
            ("Hull", "armor_13", 0., 1.), ("Turret_01", "armor_10", 0., 1.),
            ("Hull", "armor_14", 20., 0.), ("Hull", "armor_15", 30., 0.), ("Turret_01", "armor_11", 20., 0.),
            ("Gun_01", "armor_1", 350., 0.), ("Gun_01", "gun", 60., 0.)] {
            let facts = c.lookup(part, label).unwrap(); assert_eq!(facts.profile_revision, IS7_PROFILE_REVISION);
            let effective = facts.effective.unwrap(); assert_eq!(effective.armor, Some(armor));
            assert_eq!(effective.vehicle_damage_factor, factor);
        }
        for part in ["Hull", "Turret_01"] { assert!(c.lookup(part, "surveyingDevice").unwrap().effective.is_none()); }
        assert_eq!(c.lookup("Gun_01", "gun").unwrap().component, Component::Gun01);
        assert!(c.lookup("Gun_02", "gun").is_err()); assert!(c.lookup("Hull", "armor_17").is_err());
        let gun = c.lookup("Gun_01", "gun").unwrap().effective.unwrap();
        assert_eq!(gun.damage_kind, 1); assert_eq!(gun.chance_to_hit_by_projectile, 0.33);
    }
    #[test] fn is7_materials_reject_wrong_revision_missing_plate_and_cross_vehicle_gun() {
        let root = std::env::var("WOT091_ROOT").unwrap_or_else(|_| "D:/WoT_9.1_Server".into());
        let raw = std::fs::read(std::path::Path::new(&root).join("local/evidence/20261013-p03m-is7-01/geometry-surface01/is7-contact.json")).unwrap();
        let value: Value = serde_json::from_slice(&raw).unwrap(); let revision = &value["source_revision"];
        let mut rows = value["materials"].clone(); rows[0]["entries"].as_array_mut().unwrap().remove(15);
        assert!(Catalog::from_value_for(VehicleKind::Is7, revision, &rows).is_err());
        let mut rows = value["materials"].clone(); rows[2]["component"] = json!("Gun_02");
        assert!(Catalog::from_value_for(VehicleKind::Is7, revision, &rows).is_err());
        let mut rows = value["materials"].clone(); rows[1]["entries"][0]["effective"]["armor"] = json!(-1);
        assert!(Catalog::from_value_for(VehicleKind::Is7, revision, &rows).is_err());
        assert!(Catalog::from_value_for(VehicleKind::Is7, &json!(PROFILE_REVISION), &value["materials"]).is_err());
    }
    #[test] fn component_specific_armor_and_absence_are_distinct() {
        let b = super::super::geometry::tests::bundle(); let c = b.materials();
        for (component, armor, factor) in [("Hull",16.,1.), ("Turret_01",16.,1.), ("Gun_02",8.,0.)] {
            let m = c.lookup(component, "armor_3").unwrap().effective.unwrap();
            assert_eq!(m.armor, Some(armor)); assert_eq!(m.vehicle_damage_factor, factor);
        }
        for (component, label) in [("Hull","armor_10"), ("Turret_01","armor_8")] {
            let m = c.lookup(component,label).unwrap().effective.unwrap();
            assert_eq!(m.armor,Some(0.)); assert_eq!(m.damage_kind,0);
            assert_eq!(c.lookup(component,"surveyingDevice").unwrap().effective,None);
        }
        let gun = c.lookup("Gun_02","gun").unwrap(); assert_eq!(gun.kind,25);
        let e = gun.effective.unwrap(); assert_eq!(e.armor,Some(10.)); assert_eq!(e.damage_kind,1);
        assert_eq!(e.chance_to_hit_by_projectile.to_bits(),0.33f32.to_bits());
        assert_eq!(c.lookup("Hull","armor_11").unwrap().effective.unwrap().vehicle_damage_factor,0.);
        assert!(c.lookup("Gun_02","gunBreech").is_err()); assert!(c.lookup("Chassis","armor_1").is_err());
    }
    #[test] fn invalid_material_catalog_is_rejected_without_fallback() {
        let v = values(); let rev = &v["source_revision"]; let rows = &v["materials"];
        for (field, value) in [("kind",json!(31)), ("name",json!("gunBreech")), ("source_class",json!("screen"))] {
            let mut m = rows.clone(); m[0]["entries"][0][field] = value; assert!(Catalog::from_value(rev,&m).is_err());
        }
        for (field,value) in [("armor",json!(-1)), ("vehicleDamageFactor",json!(1.1)),
            ("useHitAngle",json!(1)), ("chanceToHitByProjectile",json!(2)), ("damageKind",json!(256)), ("kind",json!(2))] {
            let mut m = rows.clone(); m[0]["entries"][0]["effective"][field] = value;
            assert!(Catalog::from_value(rev,&m).is_err());
        }
        let mut duplicate = rows.clone(); duplicate[0]["entries"][1] = duplicate[0]["entries"][0].clone();
        assert!(Catalog::from_value(rev,&duplicate).is_err());
        let mut extra = rows.clone(); extra[0]["entries"][0]["effective"]["arbitrary"] = json!(0);
        assert!(Catalog::from_value(rev,&extra).is_err());
        let mut fabricated = rows.clone(); fabricated[0]["entries"][12]["effective"] = rows[0]["entries"][9]["effective"].clone();
        assert!(Catalog::from_value(rev,&fabricated).is_err());
        assert!(Catalog::from_value(&json!("foreign-profile"),rows).is_err());
    }
    #[test] fn diagnostic_json_preserves_source_facts_without_claiming_damage() {
        let b = super::super::geometry::tests::bundle();
        let j = b.materials().lookup("Hull","surveyingDevice").unwrap().json();
        assert!(j["effective"].is_null()); assert_eq!(j["damage_applied"],false);
        assert_eq!(j["normal_orientation"],"unknown_triangle_winding_only");
        assert_eq!(j["ballistic_outcome"],"unresolved");
    }
}
