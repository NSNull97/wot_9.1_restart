//! Imported original fragile geometry. Damage is explicitly approximate test_lab:
//! unscaled reference HP, fixed AP30, and termination on the first surface.
use std::{fs, io::{self, Read}, path::Path, sync::Arc};
use sha2::{Digest,Sha256};
use serde_json::Value;
use crate::map_profile091::MapId;
use super::{model::{bad,MAX_SHOTS,CAPACITY},terrain,obstacles};

pub const MAX_OBJECTS:usize=64;
pub const MAX_CONTACT_OBJECTS:usize=1024;
pub const POLICY:&str="test_lab-fragile-reference-hp-ap30-v1";
/// Minimal authoritative ramming policy. The worker supplies a hash-bound
/// vehicle mass from the map descriptor; client claims are never used. A
/// contact below this kinetic-energy floor remains a contact candidate but
/// does not remove the object, so a light tap cannot fell every tree.
pub const RAMMING_MIN_MASS_KG:f32=1000.;
pub const RAMMING_MAX_MASS_KG:f32=100000.;
pub const RAMMING_MIN_ENERGY_J:f32=8_000.;
pub const DEFINITIONS_SHA:&str="bd39e3047b435fc8917ca2e7c3dc82de4a5a03cc164054af83395af8b479fdd5";
pub const PHYSICS_SHA:&str="ea6ef22aed0fdd4e4826500c280a616737f8990ce7ab7cd808b9382227ec5ffd";

#[derive(Clone,Debug,PartialEq)]
pub struct Object {
    pub object_id:u32,pub instance_id:u32,pub chunk_id:u16,pub native_index:u8,
    pub resource:String,pub health:u32,pub material_kind:u8,
    pub projectile_first_triangle:u32,pub projectile_triangle_count:u32,
    pub physics_first_triangle:u32,pub physics_triangle_count:u32,pub object_revision:String,pub kind:ObjectKind,
}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum ObjectKind { Fragile, Tree }
#[derive(Clone,Debug,PartialEq)]
pub struct Catalog {pub map:MapId,pub sha256:String,pub worker_file:String,pub worker_sha256:String,pub contacts:bool,pub objects:Vec<Object>}
fn fields(v:&Value,k:&[&str])->io::Result<()> {crate::map_drive_worker091::fields(v,k).map(|_|())}
fn uint(v:&Value)->io::Result<u32>{u32::try_from(v.as_u64().ok_or_else(bad)?).map_err(|_|bad())}
fn text(v:&Value,max:usize)->io::Result<String>{v.as_str().filter(|s|!s.is_empty()&&s.len()<=max&&!s.chars().any(char::is_control)).map(str::to_owned).ok_or_else(bad)}
fn hash(v:&Value)->io::Result<String>{let s=text(v,64)?;if s.len()!=64||!s.bytes().all(|b|b.is_ascii_digit()||(b'a'..=b'f').contains(&b)){return Err(bad());}Ok(s)}
fn non_reparse(path:&Path)->io::Result<()>{for p in path.ancestors(){let m=fs::symlink_metadata(p)?;
    if m.file_type().is_symlink(){return Err(bad());}
    #[cfg(windows)]{use std::os::windows::fs::MetadataExt;if m.file_attributes()&0x400!=0{return Err(bad());}}
}Ok(())}
impl Catalog {
    pub fn load(root:&Path,path:&Path,sha:&str)->io::Result<Self>{
        if !path.is_absolute(){return Err(bad());} non_reparse(root)?;non_reparse(path)?;
        let root=root.canonicalize()?;let path=path.canonicalize()?;
        if !path.starts_with(&root)||path==root{return Err(bad());}
        let mut bytes=Vec::new();fs::File::open(path)?.take(1024*1024+1).read_to_end(&mut bytes)?;
        Self::parse(&bytes,sha)
    }
    fn parse(bytes:&[u8],sha:&str)->io::Result<Self>{
        if format!("{:x}",Sha256::digest(bytes))!=sha{return Err(bad());}
        let v=crate::map_drive_worker091::json_catalog(bytes,1024*1024)?;
        let base_fields=["version","profile","map","destructibles_sha256","physics_manifest_sha256","projectile_manifest_sha256","native_exports_sha256","worker","objects"];
        if v.get("contacts").is_some(){fields(&v,&["version","profile","map","destructibles_sha256","physics_manifest_sha256","projectile_manifest_sha256","native_exports_sha256","worker","objects","contacts"])?;}else{fields(&v,&base_fields)?;}
        let map=MapId::from_asset(v["map"].as_str().ok_or_else(bad)?)?;
        let profile=map.spec();
        let version=v["version"].as_u64().ok_or_else(bad)?;
        if !(version==1||version==2)||v["profile"]!="test_lab"||v["destructibles_sha256"]!=DEFINITIONS_SHA
            ||v["physics_manifest_sha256"]!=profile.physics_manifest_sha256||v["projectile_manifest_sha256"]!=profile.projectile_manifest_sha256{return Err(bad());}
        if version==1 && bytes.len()>131072{return Err(bad());}
        let contacts=version==2;
        if contacts && v["contacts"]!=true || !contacts && v.get("contacts").is_some(){return Err(bad());}
        let exports=v["native_exports_sha256"].as_array().filter(|a|(1..=2).contains(&a.len())).ok_or_else(bad)?;
        let pins=exports.iter().map(hash).collect::<io::Result<Vec<_>>>()?;
        if pins.windows(2).any(|w|w[0]>=w[1]){return Err(bad());}
        fields(&v["worker"],&["file","sha256"])?;
        let worker_file=text(&v["worker"]["file"],64)?;
        if worker_file!="physics-removals.json"{return Err(bad());}
        let worker_sha256=hash(&v["worker"]["sha256"])?;
        let rows=v["objects"].as_array().filter(|a|!a.is_empty()&&a.len()<=if contacts{MAX_CONTACT_OBJECTS}else{MAX_OBJECTS}).ok_or_else(bad)?;
        let mut objects=Vec::with_capacity(rows.len());
        for row in rows {
            let object_fields=["object_id","instance_id","chunk_id","native_index","resource","health","material_kind","projectile_first_triangle","projectile_triangle_count","physics_first_triangle","physics_triangle_count","object_revision"];
            if contacts{fields(row,&["object_id","instance_id","chunk_id","native_index","resource","health","material_kind","projectile_first_triangle","projectile_triangle_count","physics_first_triangle","physics_triangle_count","object_revision","kind"])?;}else{fields(row,&object_fields)?;}
            let kind=match row.get("kind").and_then(Value::as_str){Some("tree")=>ObjectKind::Tree,Some("fragile")|None=>ObjectKind::Fragile,Some(_)=>return Err(bad())};
            if contacts && row.get("kind").is_none(){return Err(bad());}
            let object=Object{object_id:uint(&row["object_id"])?,instance_id:uint(&row["instance_id"])?,
                chunk_id:u16::try_from(uint(&row["chunk_id"])?).map_err(|_|bad())?,native_index:u8::try_from(uint(&row["native_index"])?).map_err(|_|bad())?,
                resource:text(&row["resource"],240)?,health:{let health=uint(&row["health"])?;
                    if !contacts && health>i16::MAX as u32 { return Err(bad()); }
                    health},
                material_kind:u8::try_from(uint(&row["material_kind"])?).map_err(|_|bad())?,
                projectile_first_triangle:uint(&row["projectile_first_triangle"])?,projectile_triangle_count:uint(&row["projectile_triangle_count"])?,
                physics_first_triangle:uint(&row["physics_first_triangle"])?,physics_triangle_count:uint(&row["physics_triangle_count"])?,object_revision:hash(&row["object_revision"])?,kind};
            objects.push(object);
        }
        let catalog=Self{map,sha256:sha.into(),worker_file,worker_sha256,contacts,objects};catalog.validate()?;Ok(catalog)
    }
    fn validate(&self)->io::Result<()>{
        let profile=self.map.spec();
        if self.objects.is_empty()||self.objects.len()>if self.contacts{MAX_CONTACT_OBJECTS}else{MAX_OBJECTS}
            ||self.objects.windows(2).any(|w|w[0].object_id>=w[1].object_id){return Err(bad());}
        for (i,o) in self.objects.iter().enumerate(){
            let (resource_ok,material_ok,projectile_ok)=match o.kind {
                ObjectKind::Fragile=>(o.resource.starts_with("content/")&&o.resource.ends_with(".model"),o.material_kind==73,o.projectile_triangle_count>0),
                ObjectKind::Tree=>(o.resource.starts_with("speedtree/")&&o.resource.ends_with(".spt"),o.material_kind==71,o.projectile_triangle_count==0),
            };
            if o.instance_id as usize>=profile.instance_count||o.object_id!=o.instance_id+1||o.health<=0||!material_ok
                ||o.resource.contains("..")||o.resource.contains('\\')||!resource_ok
                ||!projectile_ok&&matches!(o.kind,ObjectKind::Fragile)||o.physics_triangle_count==0
                ||o.projectile_first_triangle.checked_add(o.projectile_triangle_count).is_none_or(|end|end as usize>profile.projectile_triangle_count)
                ||o.physics_first_triangle.checked_add(o.physics_triangle_count).is_none_or(|end|end as usize>profile.physics_triangle_count)
                || !((121..=132).contains(&(o.chunk_id>>8))&&(121..=132).contains(&(o.chunk_id&255))) {return Err(bad());}
            for old in &self.objects[..i]{
                if (old.chunk_id,old.native_index)==(o.chunk_id,o.native_index)
                    ||ranges_overlap(old.projectile_first_triangle,old.projectile_triangle_count,o.projectile_first_triangle,o.projectile_triangle_count)
                    ||ranges_overlap(old.physics_first_triangle,old.physics_triangle_count,o.physics_first_triangle,o.physics_triangle_count){return Err(bad());}
            }
        }Ok(())
    }
    pub fn instance(&self,id:u32)->Option<&Object>{self.objects.iter().find(|o|o.instance_id==id)}
    pub fn contacts(&self)->bool { self.contacts }
    pub fn chunks(&self)->Vec<u16>{let mut v=self.objects.iter().map(|o|o.chunk_id).collect::<Vec<_>>();v.sort_unstable();v.dedup();v}
    pub fn bind_geometry(&self,terrain:&terrain::Terrain)->io::Result<()>{
        if terrain.map_id()!=self.map{return Err(bad());}
        for o in &self.objects{
            if matches!(o.kind,ObjectKind::Fragile) {
                terrain.validate_instance(o.instance_id,o.projectile_first_triangle,o.projectile_triangle_count,o.material_kind)?;
            }
        }Ok(())
    }
}
fn ranges_overlap(a:u32,n:u32,b:u32,m:u32)->bool{a<b+m&&b<a+n}

#[derive(Clone,Debug,PartialEq)]
pub struct Damage {pub object_id:u32,pub instance_id:u32,pub object_revision:String,pub shot:u32,pub shooter:usize,pub tick:u32,
    pub health_before:u32,pub health_after:u32,pub scene_before:u32,pub scene_after:u32,pub hit:terrain::Hit}
#[derive(Clone,Debug,PartialEq)]
pub struct VehicleContact {pub object_id:u32,pub instance_id:u32,pub object_revision:String,pub shooter:usize,pub tick:u32,pub substep:u8,
    pub point:[f32;3],pub normal:[f32;3],pub velocity:[f32;3],pub mass_kg:f32,pub kind:String,pub scene_before:u32,pub scene_after:u32,pub fallen_tree:Option<u32>}
#[derive(Clone,Debug,PartialEq)]
pub struct State {pub catalog:Arc<Catalog>,health:Vec<u32>,fallen:Vec<Option<u32>>,pub events:Vec<Damage>,pub vehicle_events:Vec<VehicleContact>}
impl State {
    pub fn new(catalog:Arc<Catalog>)->Self{Self{health:catalog.objects.iter().map(|o|o.health).collect(),fallen:vec![None;catalog.objects.len()],catalog,events:Vec::new(),vehicle_events:Vec::new()}}
    fn latest_tick(&self)->Option<u32>{self.events.last().map(|event|event.tick).into_iter()
        .chain(self.vehicle_events.last().map(|event|event.tick)).max()}
    pub fn scene_version(&self)->u32{self.health.iter().zip(&self.fallen).filter(|(h,f)|**h==0||f.is_some()).count() as u32}
    pub fn removed_ids(&self)->Vec<u32>{self.catalog.objects.iter().zip(self.health.iter().zip(&self.fallen)).filter(|(_, (h,f))|**h==0||f.is_some()).map(|(o,_)|o.object_id).collect()}
    pub fn excluded(&self)->Vec<u32>{self.catalog.objects.iter().zip(self.health.iter().zip(&self.fallen))
        .filter(|(_, (h,f))|**h==0||f.is_some()).map(|(o,_)|o.instance_id).collect()}
    pub fn native_destroyed(&self,chunk:u16)->Vec<u8>{let mut ids=self.catalog.objects.iter().zip(self.health.iter().zip(&self.fallen))
        .filter(|(o,(h,f))|o.chunk_id==chunk&&**h==0&&f.is_none()&&matches!(o.kind,ObjectKind::Fragile)).map(|(o,_)|o.native_index).collect::<Vec<_>>();ids.sort_unstable();ids}
    pub fn native_fragile_values(&self,chunk:u16)->Vec<u16>{
        let mut values=self.catalog.objects.iter().zip(self.health.iter().zip(&self.fallen)).filter_map(|(o,(h,f))|{
            if o.chunk_id!=chunk||*h!=0||f.is_some()||!matches!(o.kind,ObjectKind::Fragile){return None;}
            let shot=self.events.iter().any(|e|e.instance_id==o.instance_id&&e.health_after==0);
            let ram=self.vehicle_events.iter().any(|e|e.instance_id==o.instance_id);
            Some((u16::from(o.native_index)<<8)|u16::from(shot&&!ram))
        }).collect::<Vec<_>>();values.sort_unstable();values
    }
    pub fn native_fallen_trees(&self,chunk:u16)->Vec<u32>{let mut values=self.catalog.objects.iter().zip(&self.fallen)
        .filter_map(|(o,f)|if o.chunk_id==chunk{*f}else{None}).collect::<Vec<_>>();values.sort_unstable();values}
    pub fn ram_contact(&mut self,object_id:u32,shooter:usize,tick:u32,substep:u8,point:[f32;3],normal:[f32;3],velocity:[f32;3],mass_kg:f32,kind:String)->io::Result<Option<VehicleContact>>{
        if shooter>=CAPACITY||tick==0||!(1..=6).contains(&substep)||!matches!(kind.as_str(),"hull"|"wheel")
            ||point.iter().chain(normal.iter()).chain(velocity.iter()).any(|v|!v.is_finite())
            ||point.iter().any(|v|v.abs()>terrain::MAX_QUERY_COORDINATE)
            ||velocity.iter().map(|v|v*v).sum::<f32>()>625.
            ||!mass_kg.is_finite()||!(RAMMING_MIN_MASS_KG..=RAMMING_MAX_MASS_KG).contains(&mass_kg)
            ||(normal.iter().map(|v|v*v).sum::<f32>()-1.).abs()>1e-4
            ||self.latest_tick().is_some_and(|last|last>tick){return Err(bad());}
        let index=self.catalog.objects.iter().position(|o|o.object_id==object_id).ok_or_else(bad)?;let object=&self.catalog.objects[index];
        if kind=="wheel" { return Ok(None); }
        if velocity.iter().map(|v|v*v).sum::<f32>()<1. { return Ok(None); }
        if self.health[index]==0||self.fallen[index].is_some(){return Ok(None);}
        // `normal` is oriented from the tank into the object. Positive
        // signed dot therefore means the hull is closing on the object.
        let closing=velocity[0]*normal[0]+velocity[1]*normal[1]+velocity[2]*normal[2];if closing<0.1{return Ok(None);}
        let energy_j=0.5*mass_kg*closing*closing;
        if energy_j<RAMMING_MIN_ENERGY_J{return Ok(None);}
        let scene=self.scene_version();let fallen_tree=if matches!(object.kind,ObjectKind::Tree){
            let yaw=velocity[0].atan2(velocity[2]);let speed=if closing>=8.{3.}else if closing>=4.{2.}else if closing>=1.{1.}else{0.};
            Some(super::destructible_wire::encode_fallen_tree(object.native_index,yaw,0.,speed)?)
        }else{None};
        self.health[index]=0;self.fallen[index]=fallen_tree;
        let event=VehicleContact{object_id,instance_id:object.instance_id,object_revision:object.object_revision.clone(),shooter,tick,substep,point,normal,velocity,mass_kg,kind,scene_before:scene,scene_after:scene+1,fallen_tree};self.vehicle_events.push(event.clone());Ok(Some(event))
    }
    pub fn contact(&mut self,shot:u32,shooter:usize,tick:u32,hit:terrain::Hit)->io::Result<Option<Damage>>{
        let terrain::Surface::StaticObstacle{instance_id,material_kind}=hit.surface else{return Ok(None)};
        let Some(index)=self.catalog.objects.iter().position(|o|o.instance_id==instance_id) else{return Ok(None)};
        let object=&self.catalog.objects[index];let before=self.health[index];
        if !matches!(object.kind,ObjectKind::Fragile){return Ok(None);}
        if before<=0||shot==0||shot>MAX_SHOTS as u32||shooter>=CAPACITY||tick==0||self.events.len()>=MAX_SHOTS
            ||self.events.iter().any(|e|e.shot==shot)||self.latest_tick().is_some_and(|last|last>tick)
            ||material_kind!=object.material_kind||!(object.projectile_first_triangle..object.projectile_first_triangle+object.projectile_triangle_count).contains(&hit.triangle_id)
            ||!hit.t.is_finite()||!(0. ..=1.).contains(&hit.t)||hit.point.iter().chain(hit.normal.iter()).any(|v|!v.is_finite())
            ||hit.point.iter().any(|v|v.abs()>terrain::MAX_QUERY_COORDINATE)||(hit.normal.iter().map(|v|v*v).sum::<f32>()-1.).abs()>1e-4{return Err(bad());}
        let after=before.saturating_sub(30);let scene=self.scene_version();
        let damage=Damage{object_id:object.object_id,instance_id,object_revision:object.object_revision.clone(),shot,shooter,tick,
            health_before:before,health_after:after,scene_before:scene,scene_after:scene+u32::from(after==0),hit};
        self.health[index]=after;self.events.push(damage.clone());Ok(Some(damage))
    }
}

#[cfg(test)]
#[path="fragiles_tests.rs"]
pub(crate) mod tests;
