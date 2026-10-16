//! Candidate closed geometry importer, isolated from VehicleKind/World.
//! New exact source format; original BSP2/native parity is not established.
use std::{collections::BTreeMap,io};
use serde_json::Value;
use sha2::{Digest,Sha256};
use super::collision::{Mesh,Triangle};
const MAX_BYTES:usize=512*1024;
#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub enum Assembly{Wt128,Fv183}
impl Assembly{
    pub fn label(self)->&'static str{match self{Self::Wt128=>"wt-e100-128",Self::Fv183=>"fv215b-183"}}
    pub fn sha256(self)->&'static str{match self{Self::Wt128=>"0971afa6aed7bbbb0c4ba647560e15002571544cc168005679a9d46a22962aae",Self::Fv183=>"c14b10be359a86c4c4632cd0943d06c43a47fc9ede2a982880c4f09aed6ecb1d"}}
    pub fn revision(self)->&'static str{match self{Self::Wt128=>"p06t-combat-geometry-717:853c8749d6a24e428d351f8447fbfd9cd515d6f1e416e0385a6b3e0b94156a3b",Self::Fv183=>"p06t-combat-geometry-717:55763514993bf24dc83f028c896de25a0d949fc57b77945a4e8f01a123fc4f70"}}
    fn counts(self)->[(usize,usize);3]{match self{Self::Wt128=>[(239,122),(280,189),(631,238)],Self::Fv183=>[(257,150),(667,382),(160,82)]}}
    fn pivots(self)->[[f32;3];3]{match self{Self::Wt128=>[[0.,1.,0.],[0.,0.379118,-1.71333],[0.,1.37102,-0.690134]],Self::Fv183=>[[0.,1.14959,0.],[0.,0.568658,-1.49516],[0.,0.583916,1.59175]]}}
    fn identity(self)->(u64,u64,&'static str){match self{Self::Wt128=>(16913,23060,"1142a1002c00cd000d0086005a0000"),Self::Fv183=>(9297,13908,"51244f003f00cd0014004500360000")}}
    fn material_ids(self,part:usize)->&'static[u16]{match(self,part){
        (Self::Wt128,0)=>&[1,2,3,4,5,7,8,9,10,11,12,13],(Self::Wt128,1)=>&[1,2,3,4,5,6,7,8],(Self::Wt128,2)=>&[25,31],
        (Self::Fv183,0|1)=>&[1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,28],(Self::Fv183,2)=>&[1,25],_=>&[]}}
}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub enum SourceClass{ArmorDescriptor,GunVisual,SurveyingDeviceVisual,GunBreechVisualUnsupported}
#[derive(Clone,Debug)]pub struct SourceMaterial{pub name:String,pub kind:u16,pub source_class:SourceClass,pub effective:Option<Value>}
#[derive(Clone,Debug)]pub struct SourceComponent{pub name:String,pub vertices:Vec<[f32;3]>,pub triangles:Vec<Triangle>,pub materials:Vec<SourceMaterial>,pub visual_bounds:[[f32;3];2],pub mesh_bounds:[[f32;3];2]}
#[derive(Clone,Debug)]pub struct SourceBundle{pub assembly:Assembly,pub pivots:[[f32;3];3],pub components:Vec<SourceComponent>}
fn bad()->io::Error{io::Error::new(io::ErrorKind::InvalidData,"P06T closed source geometry contract")}
fn fields(v:&Value,keys:&[&str])->io::Result<()>{let map=v.as_object().ok_or_else(bad)?;if map.len()!=keys.len()||keys.iter().any(|k|!map.contains_key(*k)){return Err(bad());}Ok(())}
fn array(v:&Value,n:usize)->io::Result<&Vec<Value>>{v.as_array().filter(|r|r.len()==n).ok_or_else(bad)}
fn text(v:&Value)->io::Result<&str>{v.as_str().filter(|s|!s.is_empty()&&s.len()<=128).ok_or_else(bad)}
fn uint(v:&Value)->io::Result<u32>{v.as_u64().and_then(|x|u32::try_from(x).ok()).ok_or_else(bad)}
fn scalar(v:&Value,max:f64)->io::Result<f64>{v.as_f64().filter(|x|x.is_finite()&&*x>=0.&&*x<=max).ok_or_else(bad)}
fn vector(v:&Value)->io::Result<[f32;3]>{let row=array(v,3)?;let mut out=[0.;3];for(i,x)in row.iter().enumerate(){let n=x.as_f64().filter(|n|n.is_finite()&&n.abs()<=32.).ok_or_else(bad)?;out[i]=n as f32;}Ok(out)}
fn bounds(v:&Value)->io::Result<[[f32;3];2]>{let row=array(v,2)?;let out=[vector(&row[0])?,vector(&row[1])?];if(0..3).any(|i|out[0][i]>=out[1][i]){return Err(bad());}Ok(out)}
fn effective(v:&Value,kind:u16)->io::Result<Value>{
    fields(v,&["kind","armor","extra_is_none","damageKind","vehicleDamageFactor","useArmorHomogenization","useHitAngle","useAntifragmentationLining","mayRicochet","collideOnceOnly","chanceToHitByProjectile","chanceToHitByExplosion","continueTraceIfNoHit"])?;
    if uint(&v["kind"])?!=u32::from(kind){return Err(bad());}scalar(&v["armor"],10000.)?;
    for key in["vehicleDamageFactor","chanceToHitByProjectile","chanceToHitByExplosion"]{scalar(&v[key],1.)?;}
    for key in["extra_is_none","useArmorHomogenization","useHitAngle","useAntifragmentationLining","mayRicochet","collideOnceOnly","continueTraceIfNoHit"]{v[key].as_bool().ok_or_else(bad)?;}
    if uint(&v["damageKind"])? > 1{return Err(bad());}
    Ok(v.clone())
}
impl SourceBundle{
    /// The digest is selected from this closed registry before JSON parsing.
    /// A caller cannot make an arbitrary file trusted by supplying its hash.
    pub fn parse(raw:&[u8])->io::Result<Self>{
        if raw.is_empty()||raw.len()>MAX_BYTES{return Err(bad());}
        let digest=format!("{:x}",Sha256::digest(raw));
        let assembly=[Assembly::Wt128,Assembly::Fv183].into_iter().find(|a|a.sha256()==digest).ok_or_else(bad)?;
        let value:Value=serde_json::from_slice(raw).map_err(|_|bad())?;
        Self::from_value(assembly,&value)
    }
    fn from_value(assembly:Assembly,value:&Value)->io::Result<Self>{
        fields(value,&["schema","source_revision","assembly_id","classification","battle_admission","runtime_qualified","identity","geometry","provenance","unknowns"])?;
        if value["schema"]!="p06t-combat-geometry.v1"||value["source_revision"]!=assembly.revision()||value["assembly_id"]!=assembly.label()
            ||value["classification"]!="VERIFIED_STATIC_ORIGINAL_717"||value["battle_admission"]!=false||value["runtime_qualified"]!=false{return Err(bad());}
        let identity=&value["identity"];fields(identity,&["vehicle_type_compact_descr","module_compact_descrs","descriptor_hex","max_health"])?;
        let(type_id,gun_id,descriptor)=assembly.identity();if identity["vehicle_type_compact_descr"].as_u64()!=Some(type_id)
            ||identity["module_compact_descrs"]["gun"].as_u64()!=Some(gun_id)||identity["descriptor_hex"]!=descriptor||identity["max_health"]!=2000{return Err(bad());}
        let g=&value["geometry"];fields(g,&["pivots","components"])?;let p=array(&g["pivots"],3)?;
        let pivots=[vector(&p[0])?,vector(&p[1])?,vector(&p[2])?];if pivots!=assembly.pivots(){return Err(bad());}
        let mut components=Vec::with_capacity(3);
        for(i,row)in array(&g["components"],3)?.iter().enumerate(){
            fields(row,&["name","vertices","triangles","materials","visual_bounds","mesh_bounds","excluded_degenerate_triangle_ids","source_vertex_count","source_triangle_count","material_triangle_counts","source_collision_model","vertex_layout","index_layout"])?;
            let name=["Hull","Turret_01","Gun_01"][i];let(nv,nt)=assembly.counts()[i];if row["name"]!=name||row["source_vertex_count"].as_u64()!=Some(nv as u64)||row["source_triangle_count"].as_u64()!=Some(nt as u64)
                ||row["excluded_degenerate_triangle_ids"]!=serde_json::json!([]){return Err(bad());}
            let layout=&row["vertex_layout"];fields(layout,&["format","header_bytes","stride_bytes","position_offset_bytes","position_type","other_attributes"])?;
            if layout["format"]!=if assembly==Assembly::Wt128{"xyznuvtb"}else{"xyznuv"}||layout["header_bytes"]!=68||layout["stride_bytes"]!=32||layout["position_offset_bytes"]!=0||layout["position_type"]!="FLOAT3"||layout["other_attributes"]!="OPAQUE_NOT_DECODED"{return Err(bad());}
            let il=&row["index_layout"];fields(il,&["format","width_bytes","header_bytes","group_bytes"])?;
            if il["format"]!="list"||il["width_bytes"]!=2||il["header_bytes"]!=72||il["group_bytes"]!=16{return Err(bad());}
            let vertices=array(&row["vertices"],nv)?.iter().map(vector).collect::<io::Result<Vec<_>>>()?;
            let mut materials=Vec::new();
            for(e,&kind)in array(&row["materials"],assembly.material_ids(i).len())?.iter().zip(assembly.material_ids(i)){
                fields(e,&["name","kind","source_class","effective","resolution_capability","common_extra"])?;
                let(name,class,source_class,capability,extra)=match kind{
                    25=>("gun".into(),SourceClass::GunVisual,"gun_visual_material","SOURCE_FACTS_ONLY",Some(("gunHealth",32))),
                    28=>("surveyingDevice".into(),SourceClass::SurveyingDeviceVisual,"surveying_device_visual_material","NO_LOCAL_RECORD",Some(("surveyingDeviceHealth",34))),
                    31=>("gunBreech".into(),SourceClass::GunBreechVisualUnsupported,"gun_breech_visual_material","UNSUPPORTED_MATERIAL31",Some(("gunHealth",32))),
                    _=>(format!("armor_{kind}"),SourceClass::ArmorDescriptor,"armor_descriptor","SOURCE_FACTS_ONLY",None),};
                if e["name"].as_str()!=Some(&name)||uint(&e["kind"])?!=u32::from(kind)||e["source_class"]!=source_class||e["resolution_capability"]!=capability{return Err(bad());}
                if let Some((name,index))=extra{if e["common_extra"]!=serde_json::json!({"name":name,"index":index}){return Err(bad());}}
                else if !e["common_extra"].is_null(){return Err(bad());}
                let effective=if kind==28{if !e["effective"].is_null(){return Err(bad());}None}else{Some(effective(&e["effective"],kind)?)};
                if let Some(ref v)=effective{
                    if kind==31&&(v["armor"]!=0.||v["vehicleDamageFactor"]!=1.||v["chanceToHitByProjectile"]!=1.||v["chanceToHitByExplosion"]!=1.||v["damageKind"]!=1||v["extra_is_none"]!=false||v["useHitAngle"]!=true||v["useArmorHomogenization"]!=true||v["collideOnceOnly"]!=false){return Err(bad());}
                    if kind==25&&(v["armor"].as_f64()!=Some(if assembly==Assembly::Wt128{20.}else{80.})||v["vehicleDamageFactor"]!=0.||v["damageKind"]!=1||v["extra_is_none"]!=false||v["useHitAngle"]!=false||v["collideOnceOnly"]!=true){return Err(bad());}
                }
                materials.push(SourceMaterial{name,kind,source_class:class,effective});
            }
            let mut triangles=Vec::with_capacity(nt);let mut coverage:BTreeMap<String,u32>=BTreeMap::new();
            for(j,t)in array(&row["triangles"],nt)?.iter().enumerate(){
                fields(t,&["triangle_id","a","b","c","mesh","group","material"])?;
                let triangle=Triangle{triangle_id:uint(&t["triangle_id"])?,a:uint(&t["a"])?,b:uint(&t["b"])?,c:uint(&t["c"])?,mesh:text(&t["mesh"])?.into(),group:text(&t["group"])?.into(),material:text(&t["material"])?.into()};
                if triangle.triangle_id!=i as u32*100000+j as u32||triangle.mesh!=name||!materials.iter().any(|m|m.name==triangle.material){return Err(bad());}
                *coverage.entry(triangle.material.clone()).or_default()+=1;triangles.push(triangle);
            }
            if row["material_triangle_counts"]!=serde_json::to_value(&coverage).map_err(|_|bad())?{return Err(bad());}
            Mesh::new(vertices.clone(),triangles.clone(),assembly.revision(),"component-local-v1")?;
            let visual_bounds=bounds(&row["visual_bounds"])?;let mb=&row["mesh_bounds"];fields(mb,&["min","max"])?;
            let mesh_bounds=bounds(&serde_json::json!([mb["min"],mb["max"]]))?;
            for axis in 0..3{let min=vertices.iter().map(|v|v[axis]).min_by(f32::total_cmp).ok_or_else(bad)?;let max=vertices.iter().map(|v|v[axis]).max_by(f32::total_cmp).ok_or_else(bad)?;
                if[min,max]!=[mesh_bounds[0][axis],mesh_bounds[1][axis]]{return Err(bad());}}
            components.push(SourceComponent{name:name.into(),vertices,triangles,materials,visual_bounds,mesh_bounds});
        }
        Ok(Self{assembly,pivots,components})
    }
}

#[cfg(test)]#[path="p06t_geometry_source_tests.rs"]mod tests;
