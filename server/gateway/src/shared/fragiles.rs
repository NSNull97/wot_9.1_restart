//! Imported original fragile geometry. Damage is explicitly approximate test_lab:
//! unscaled reference HP, fixed AP30, and termination on the first surface.
use std::{fs, io::{self, Read}, path::Path, sync::Arc};
use sha2::{Digest,Sha256};
use serde_json::Value;
use crate::map_profile091::MapId;
use super::{model::{bad,MAX_SHOTS,CAPACITY},terrain,obstacles};

pub const MAX_OBJECTS:usize=64;
pub const POLICY:&str="test_lab-fragile-reference-hp-ap30-v1";
pub const DEFINITIONS_SHA:&str="bd39e3047b435fc8917ca2e7c3dc82de4a5a03cc164054af83395af8b479fdd5";
pub const PHYSICS_SHA:&str="ea6ef22aed0fdd4e4826500c280a616737f8990ce7ab7cd808b9382227ec5ffd";

#[derive(Clone,Debug,PartialEq)]
pub struct Object {
    pub object_id:u32,pub instance_id:u32,pub chunk_id:u16,pub native_index:u8,
    pub resource:String,pub health:i16,pub material_kind:u8,
    pub projectile_first_triangle:u32,pub projectile_triangle_count:u32,
    pub physics_first_triangle:u32,pub physics_triangle_count:u32,pub object_revision:String,
}
#[derive(Clone,Debug,PartialEq)]
pub struct Catalog {pub map:MapId,pub sha256:String,pub worker_file:String,pub worker_sha256:String,pub objects:Vec<Object>}
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
        let mut bytes=Vec::new();fs::File::open(path)?.take(131073).read_to_end(&mut bytes)?;
        Self::parse(&bytes,sha)
    }
    fn parse(bytes:&[u8],sha:&str)->io::Result<Self>{
        if format!("{:x}",Sha256::digest(bytes))!=sha{return Err(bad());}
        let v=crate::map_drive_worker091::json(bytes,131072)?;
        fields(&v,&["version","profile","map","destructibles_sha256","physics_manifest_sha256","projectile_manifest_sha256","native_exports_sha256","worker","objects"])?;
        let map=MapId::from_asset(v["map"].as_str().ok_or_else(bad)?)?;
        let profile=map.spec();
        if v["version"]!=1||v["profile"]!="test_lab"||v["destructibles_sha256"]!=DEFINITIONS_SHA
            ||v["physics_manifest_sha256"]!=profile.physics_manifest_sha256||v["projectile_manifest_sha256"]!=profile.projectile_manifest_sha256{return Err(bad());}
        let exports=v["native_exports_sha256"].as_array().filter(|a|(1..=2).contains(&a.len())).ok_or_else(bad)?;
        let pins=exports.iter().map(hash).collect::<io::Result<Vec<_>>>()?;
        if pins.windows(2).any(|w|w[0]>=w[1]){return Err(bad());}
        fields(&v["worker"],&["file","sha256"])?;
        let worker_file=text(&v["worker"]["file"],64)?;
        if worker_file!="physics-removals.json"{return Err(bad());}
        let worker_sha256=hash(&v["worker"]["sha256"])?;
        let rows=v["objects"].as_array().filter(|a|!a.is_empty()&&a.len()<=MAX_OBJECTS).ok_or_else(bad)?;
        let mut objects=Vec::with_capacity(rows.len());
        for row in rows {
            fields(row,&["object_id","instance_id","chunk_id","native_index","resource","health","material_kind","projectile_first_triangle","projectile_triangle_count","physics_first_triangle","physics_triangle_count","object_revision"])?;
            let object=Object{object_id:uint(&row["object_id"])?,instance_id:uint(&row["instance_id"])?,
                chunk_id:u16::try_from(uint(&row["chunk_id"])?).map_err(|_|bad())?,native_index:u8::try_from(uint(&row["native_index"])?).map_err(|_|bad())?,
                resource:text(&row["resource"],240)?,health:i16::try_from(uint(&row["health"])?).map_err(|_|bad())?,
                material_kind:u8::try_from(uint(&row["material_kind"])?).map_err(|_|bad())?,
                projectile_first_triangle:uint(&row["projectile_first_triangle"])?,projectile_triangle_count:uint(&row["projectile_triangle_count"])?,
                physics_first_triangle:uint(&row["physics_first_triangle"])?,physics_triangle_count:uint(&row["physics_triangle_count"])?,object_revision:hash(&row["object_revision"])?};
            objects.push(object);
        }
        let catalog=Self{map,sha256:sha.into(),worker_file,worker_sha256,objects};catalog.validate()?;Ok(catalog)
    }
    fn validate(&self)->io::Result<()>{
        let profile=self.map.spec();
        if self.objects.is_empty()||self.objects.len()>MAX_OBJECTS||self.objects.windows(2).any(|w|w[0].object_id>=w[1].object_id){return Err(bad());}
        for (i,o) in self.objects.iter().enumerate(){
            if o.instance_id as usize>=profile.instance_count||o.object_id!=o.instance_id+1||o.health<=0||o.material_kind!=73
                ||o.resource.contains("..")||o.resource.contains('\\')||!o.resource.starts_with("content/")||!o.resource.ends_with(".model")
                ||o.projectile_triangle_count==0||o.physics_triangle_count==0
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
    pub fn chunks(&self)->Vec<u16>{let mut v=self.objects.iter().map(|o|o.chunk_id).collect::<Vec<_>>();v.sort_unstable();v.dedup();v}
    pub fn bind_geometry(&self,terrain:&terrain::Terrain)->io::Result<()>{
        if terrain.map_id()!=self.map{return Err(bad());}
        for o in &self.objects{terrain.validate_instance(o.instance_id,o.projectile_first_triangle,o.projectile_triangle_count,o.material_kind)?;}Ok(())
    }
}
fn ranges_overlap(a:u32,n:u32,b:u32,m:u32)->bool{a<b+m&&b<a+n}

#[derive(Clone,Debug,PartialEq)]
pub struct Damage {pub object_id:u32,pub instance_id:u32,pub object_revision:String,pub shot:u32,pub shooter:usize,pub tick:u32,
    pub health_before:i16,pub health_after:i16,pub scene_before:u32,pub scene_after:u32,pub hit:terrain::Hit}
#[derive(Clone,Debug,PartialEq)]
pub struct State {pub catalog:Arc<Catalog>,health:Vec<i16>,pub events:Vec<Damage>}
impl State {
    pub fn new(catalog:Arc<Catalog>)->Self{Self{health:catalog.objects.iter().map(|o|o.health).collect(),catalog,events:Vec::new()}}
    pub fn scene_version(&self)->u32{self.health.iter().filter(|&&h|h==0).count() as u32}
    pub fn removed_ids(&self)->Vec<u32>{self.catalog.objects.iter().zip(&self.health).filter(|(_,h)|**h==0).map(|(o,_)|o.object_id).collect()}
    pub fn excluded(&self)->Vec<u32>{self.catalog.objects.iter().zip(&self.health).filter(|(_,h)|**h==0).map(|(o,_)|o.instance_id).collect()}
    pub fn native_destroyed(&self,chunk:u16)->Vec<u8>{let mut ids=self.catalog.objects.iter().zip(&self.health)
        .filter(|(o,h)|o.chunk_id==chunk&&**h==0).map(|(o,_)|o.native_index).collect::<Vec<_>>();ids.sort_unstable();ids}
    pub fn contact(&mut self,shot:u32,shooter:usize,tick:u32,hit:terrain::Hit)->io::Result<Option<Damage>>{
        let terrain::Surface::StaticObstacle{instance_id,material_kind}=hit.surface else{return Ok(None)};
        let Some(index)=self.catalog.objects.iter().position(|o|o.instance_id==instance_id) else{return Ok(None)};
        let object=&self.catalog.objects[index];let before=self.health[index];
        if before<=0||shot==0||shot>MAX_SHOTS as u32||shooter>=CAPACITY||tick==0||self.events.len()>=MAX_SHOTS
            ||self.events.iter().any(|e|e.shot==shot)||self.events.last().is_some_and(|e|e.tick>tick)
            ||material_kind!=object.material_kind||!(object.projectile_first_triangle..object.projectile_first_triangle+object.projectile_triangle_count).contains(&hit.triangle_id)
            ||!hit.t.is_finite()||!(0. ..=1.).contains(&hit.t)||hit.point.iter().chain(hit.normal.iter()).any(|v|!v.is_finite())
            ||hit.point.iter().any(|v|v.abs()>terrain::MAX_QUERY_COORDINATE)||(hit.normal.iter().map(|v|v*v).sum::<f32>()-1.).abs()>1e-4{return Err(bad());}
        let after=(before-30).max(0);let scene=self.scene_version();
        let damage=Damage{object_id:object.object_id,instance_id,object_revision:object.object_revision.clone(),shot,shooter,tick,
            health_before:before,health_after:after,scene_before:scene,scene_after:scene+u32::from(after==0),hit};
        self.health[index]=after;self.events.push(damage.clone());Ok(Some(damage))
    }
}

#[cfg(test)]
#[path="fragiles_tests.rs"]
pub(crate) mod tests;
