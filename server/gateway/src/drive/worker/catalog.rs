//! IPC3 cumulative collider-removal snapshots. Source identities are exporter
//! instance IDs only; native client IDs and damage policy do not belong here.
use super::*;
use crate::map_profile091::MapId;

pub const MAX_CATALOG_OBJECTS:usize=64;
pub const MAX_REMOVED_OBJECTS:usize=40;

#[derive(Clone,Debug,PartialEq,Eq)]
pub struct CatalogEntry {object_id:u32,instance_id:u32,first_triangle:u32,triangle_count:u32,object_revision:String}
impl CatalogEntry {
    pub fn object_id(&self)->u32{self.object_id}
    pub fn instance_id(&self)->u32{self.instance_id}
    pub fn first_triangle(&self)->u32{self.first_triangle}
    pub fn triangle_count(&self)->u32{self.triangle_count}
    pub fn object_revision(&self)->&str{&self.object_revision}
}
#[derive(Clone,Debug,PartialEq,Eq)]
pub struct CatalogSpec {pub(super) path:PathBuf,pub(super) sha256:String,map_id:MapId,entries:Vec<CatalogEntry>}
impl CatalogSpec {
    pub fn load(local_root:&Path,path:&Path,sha256:&str)->io::Result<Self>{
        non_reparse(local_root)?;let root=local_root.canonicalize()?;hash_text(sha256)?;
        let path=owned(&root,path)?;let raw=read(&path,131072)?;
        if format!("{:x}",Sha256::digest(&raw))!=sha256{return Err(bad());}
        let value=json(&raw,131072)?;
        let entries=Self::validate(&value)?;
        let map_id=MapId::from_asset(text(&value,"map")?)?;
        Ok(Self{path,sha256:sha256.into(),map_id,entries})
    }
    fn validate(v:&Value)->io::Result<Vec<CatalogEntry>>{
        fields(v,&["version","profile","map","physics_manifest_sha256","projectile_manifest_sha256","objects"])?;
        let map_id=MapId::from_asset(text(v,"map")?)?;let profile=map_id.spec();
        if uint(&v["version"])?!=2 || text(v,"profile")?!="test_lab"
            || text(v,"physics_manifest_sha256")?!=profile.physics_manifest_sha256
            || text(v,"projectile_manifest_sha256")?!=profile.projectile_manifest_sha256{return Err(bad());}
        let rows=v["objects"].as_array().ok_or_else(bad)?;
        if rows.is_empty() || rows.len()>MAX_CATALOG_OBJECTS{return Err(bad());}
        let mut entries=Vec::new();let mut instances=BTreeSet::new();let mut previous=0;
        for row in rows {
            fields(row,&["object_id","instance_id","first_triangle","triangle_count","object_revision"])?;
            let id=uint(&row["object_id"])?;let instance=uint(&row["instance_id"])?;
            let first=uint(&row["first_triangle"])?;let count=uint(&row["triangle_count"])?;
            let revision=text(row,"object_revision")?;hash_text(revision)?;
            if id<=previous || id>u32::MAX as u64 || instance>=profile.instance_count as u64 || !instances.insert(instance)
                || count==0 || count>4096 || first>profile.physics_triangle_count as u64
                || first+count>profile.physics_triangle_count as u64{return Err(bad());}
            previous=id;entries.push(CatalogEntry{object_id:id as u32,instance_id:instance as u32,first_triangle:first as u32,
                triangle_count:count as u32,object_revision:revision.into()});
        }
        let mut spans=entries.iter().collect::<Vec<_>>();spans.sort_by_key(|e|e.first_triangle);
        if spans.windows(2).any(|p|p[1].first_triangle<p[0].first_triangle+p[0].triangle_count){return Err(bad());}
        Ok(entries)
    }
    pub(super) fn verify(&self,root:&Path,map:&MapSpec)->io::Result<()>{
        self.verify_map(map)?;
        if Self::load(root,&self.path,&self.sha256)?!=*self{return Err(bad());}
        let raw=read(&owned(root,&map.config)?,16384)?;
        if format!("{:x}",Sha256::digest(&raw))!=map.config_sha256{return Err(bad());}
        let config=json(&raw,16384)?;
        if text(&config,"map")?!=self.map_id.asset(){return Err(bad());}
        let reference=&config["obstacles"];
        fields(reference,&["path","sha256"])?;
        let expected=self.map_id.spec().physics_manifest_sha256;
        if text(reference,"sha256")?!=expected{return Err(bad());}
        let source=read(&owned(root,Path::new(text(reference,"path")?))?,8*1024*1024)?;
        if format!("{:x}",Sha256::digest(&source))!=expected{return Err(bad());}
        // Exact hash-pinned original manifests contain more rows than the
        // small untrusted IPC parser's array limit. Its byte bound remains fixed.
        let source:Value=serde_json::from_slice(&source).map_err(|_|bad())?;
        self.verify_source(&source)
    }
    fn verify_source(&self,source:&Value)->io::Result<()>{
        let profile=self.map_id.spec();
        if uint(&source["version"])?!=1 || text(source,"map")?!=self.map_id.asset()
            || text(source,"kind")?!="original_091_static_triangle_mesh"{return Err(bad());}
        let total=uint(&source["triangles"]["count"])?;
        if total!=profile.physics_triangle_count as u64{return Err(bad());}
        let rows=source["instances"].as_array().ok_or_else(bad)?;
        if rows.len()!=profile.instance_count{return Err(bad());}
        for entry in &self.entries {
            let row=&rows[entry.instance_id as usize];let resource=text(row,"resource")?;
            if text(row,"kind")?!="model" || resource.is_empty() || resource.len()>1024
                || uint(&row["first_triangle"])?!=entry.first_triangle as u64 || uint(&row["triangles"])?!=entry.triangle_count as u64
                || entry.first_triangle as u64+entry.triangle_count as u64>total{return Err(bad());}
        }Ok(())
    }
    pub fn sha256(&self)->&str{&self.sha256}
    pub fn entries(&self)->&[CatalogEntry]{&self.entries}
    pub fn map_id(&self)->MapId{self.map_id}
    fn verify_map(&self,map:&MapSpec)->io::Result<()>{
        if map.asset!=self.map_id.asset() || map.arena_type_id!=self.map_id.arena_type_id(){return Err(bad());}Ok(())
    }
}

/// Immutable full cumulative snapshot. Canonical IDs are strictly increasing;
/// scene revision is its cardinality, not a driving sequence or native ID.
#[derive(Clone,Debug,PartialEq,Eq)]
pub struct Scene {catalog_sha256:String,ids:Vec<u32>,hash:String}
impl Scene {
    pub fn new(spec:&CatalogSpec,ids:&[u32])->io::Result<Self>{
        hash_text(&spec.sha256)?;
        if ids.len()>MAX_REMOVED_OBJECTS || ids.iter().enumerate().any(|(i,id)|*id==0 ||
            (i>0 && ids[i-1]>=*id) || !spec.entries.iter().any(|e|e.object_id==*id)){return Err(bad());}
        let mut digest=Sha256::new();digest.update(b"wot091-fragile-scene-v3\0");
        for i in (0..64).step_by(2){digest.update([u8::from_str_radix(&spec.sha256[i..i+2],16).map_err(|_|bad())?]);}
        digest.update((ids.len() as u32).to_le_bytes());for id in ids{digest.update(id.to_le_bytes());}
        Ok(Self{catalog_sha256:spec.sha256.clone(),ids:ids.to_vec(),hash:format!("{:x}",digest.finalize())})
    }
    pub fn version(&self)->u32{self.ids.len() as u32}
    pub fn ids(&self)->&[u32]{&self.ids}
    pub fn hash(&self)->&str{&self.hash}
    pub(super) fn validate(&self,spec:&CatalogSpec)->io::Result<()>{
        if Self::new(spec,&self.ids)?!=*self{return Err(bad());}Ok(())
    }
    pub(super) fn extends(&self,previous:&Self)->bool{
        self.catalog_sha256==previous.catalog_sha256 && previous.ids.iter().all(|id|self.ids.binary_search(id).is_ok())
    }
}

pub(super) fn scene_request(map:&MapSpec,spec:&CatalogSpec,generation:u32,seq:u32,scene:&Scene,restore:bool)->io::Result<Vec<u8>>{
    spec.verify_map(map)?;
    scene.validate(spec)?;
    if generation==0 || seq>MAX_SEQUENCE || (restore && seq!=0){return Err(bad());}
    ipc_bytes(&serde_json::json!({"version":3,"op":if restore{"restore_scene"}else{"sync_removed"},
        "generation":generation,"config_sha256":map.config_sha256,"catalog_sha256":spec.sha256,
        "advance_seq":seq,"scene_version":scene.version(),"removed_object_ids":scene.ids,"scene_sha256":scene.hash}))
}
pub(super) fn request_catalog(seq:u32,input:Input,scene:&Scene)->io::Result<Vec<u8>>{
    let mut v=json(&request(seq,input)?,1024)?;v["version"]=3.into();v["scene_version"]=scene.version().into();
    v["scene_sha256"]=scene.hash.clone().into();ipc_bytes(&v)
}
#[derive(Clone,Debug,PartialEq,Eq)]
pub struct CatalogAck {pub generation:u32,pub config_sha256:String,pub catalog_sha256:String,pub advance_seq:u32,
    pub tick:u32,pub scene_version:u32,pub removed_object_ids:Vec<u32>,pub scene_sha256:String}
pub(super) fn ack(raw:&[u8],map:&MapSpec,spec:&CatalogSpec,generation:u32,seq:u32,scene:&Scene)->io::Result<CatalogAck>{
    spec.verify_map(map)?;
    scene.validate(spec)?;
    if !raw.is_ascii() || generation==0 || seq>MAX_SEQUENCE{return Err(bad());}
    let v=json(raw,1024)?;
    fields(&v,&["version","event","generation","config_sha256","catalog_sha256","advance_seq","tick",
        "scene_version","removed_object_ids","scene_sha256"])?;
    if uint(&v["version"])?!=3 || text(&v,"event")?!="scene_synced" || uint(&v["generation"])?!=generation as u64
        || text(&v,"config_sha256")?!=map.config_sha256 || text(&v,"catalog_sha256")?!=spec.sha256
        || uint(&v["advance_seq"])?!=seq as u64 || uint(&v["tick"])?!=180+seq as u64*6
        || uint(&v["scene_version"])?!=scene.version() as u64 || text(&v,"scene_sha256")?!=scene.hash{return Err(bad());}
    let ids=v["removed_object_ids"].as_array().ok_or_else(bad)?;
    if ids.len()!=scene.ids.len(){return Err(bad());}
    for (value,id) in ids.iter().zip(&scene.ids){if uint(value)?!=*id as u64{return Err(bad());}}
    Ok(CatalogAck{generation,config_sha256:map.config_sha256.clone(),catalog_sha256:spec.sha256.clone(),advance_seq:seq,
        tick:180+seq*6,scene_version:scene.version(),removed_object_ids:scene.ids.clone(),scene_sha256:scene.hash.clone()})
}
pub(super) fn response(raw:&[u8],map:&MapSpec,spec:&CatalogSpec,generation:u32,seq:u32,spawn:Option<[f32;3]>,scene:&Scene)->io::Result<State>{
    spec.verify_map(map)?;
    scene.validate(spec)?;
    if !raw.is_ascii() || generation==0{return Err(bad());}let mut v=json(raw,1024)?;
    fields(&v,&["version","event","seq","tick","settle_ticks","map","config_sha256","state","generation","catalog_sha256","scene_version","scene_sha256"])?;
    if uint(&v["version"])?!=3 || uint(&v["generation"])?!=generation as u64 || text(&v,"catalog_sha256")?!=spec.sha256
        || uint(&v["scene_version"])?!=scene.version() as u64 || text(&v,"scene_sha256")?!=scene.hash{return Err(bad());}
    let object=v.as_object_mut().ok_or_else(bad)?;
    for key in ["generation","catalog_sha256","scene_version","scene_sha256"]{object.remove(key);}
    v["version"]=1.into();
    let mut state=response_at_spawn(&serde_json::to_vec(&v).map_err(|_|bad())?,map,seq,spawn)?;
    state.scene_version=scene.version();Ok(state)
}

#[cfg(test)]
pub(super) mod tests {
    use super::*;
    pub(in super::super) fn descriptor(n:usize)->Value{serde_json::json!({"version":2,"profile":"test_lab","map":"01_karelia",
        "physics_manifest_sha256":PHYSICS_MANIFEST,"projectile_manifest_sha256":PROJECTILE_MANIFEST,
        "objects":(0..n).map(|i|serde_json::json!({"object_id":i+1,"instance_id":i,"first_triangle":i*42,
            "triangle_count":42,"object_revision":"e".repeat(64)})).collect::<Vec<_>>()})}
    pub(in super::super) fn spec(n:usize)->CatalogSpec{
        CatalogSpec{path:"unit".into(),sha256:"b".repeat(64),map_id:MapId::Karelia,entries:CatalogSpec::validate(&descriptor(n)).unwrap()}
    }
    pub(in super::super) fn spec_for(map_id:MapId,n:usize)->CatalogSpec{
        let v=descriptor_for(map_id,n);let raw=serde_json::to_vec(&v).unwrap();
        CatalogSpec{path:"unit".into(),sha256:format!("{:x}",Sha256::digest(raw)),map_id,entries:CatalogSpec::validate(&v).unwrap()}
    }
    fn descriptor_for(map_id:MapId,n:usize)->Value{
        let mut v=descriptor(n);v["map"]=map_id.asset().into();
        v["physics_manifest_sha256"]=map_id.spec().physics_manifest_sha256.into();
        v["projectile_manifest_sha256"]=map_id.spec().projectile_manifest_sha256.into();v
    }
    fn source_for(spec:&CatalogSpec)->Value{
        let mut source=serde_json::json!({"version":1,"map":spec.map_id.asset(),"kind":"original_091_static_triangle_mesh",
            "triangles":{"count":spec.map_id.spec().physics_triangle_count},"instances":vec![Value::Null;spec.map_id.spec().instance_count]});
        for e in &spec.entries{source["instances"][e.instance_id as usize]=serde_json::json!({"kind":"model","resource":"source.model",
            "first_triangle":e.first_triangle,"triangles":e.triangle_count});}source
    }
    #[test]fn both_maps_pin_catalog_counts_sources_and_cumulative_scene(){
        for map_id in [MapId::Karelia,MapId::Prohorovka]{
            let profile=map_id.spec();let spec=spec_for(map_id,2);assert_eq!(spec.map_id(),map_id);
            spec.verify_source(&source_for(&spec)).unwrap();
            let mut map=super::super::tests::map();map.asset=map_id.asset().into();map.arena_type_id=map_id.arena_type_id();
            let scene=Scene::new(&spec,&[1,2]).unwrap();let request=scene_request(&map,&spec,2,0,&scene,true).unwrap();
            let mut reply=json(&request,1025).unwrap();reply.as_object_mut().unwrap().remove("op");
            reply["event"]="scene_synced".into();reply["tick"]=180.into();
            let raw=ipc_bytes(&reply).unwrap();ack(&raw,&map,&spec,2,0,&scene).unwrap();
            let other=if map_id==MapId::Karelia{MapId::Prohorovka}else{MapId::Karelia};
            let mut wrong_map=map.clone();wrong_map.asset=other.asset().into();wrong_map.arena_type_id=other.arena_type_id();
            assert!(scene_request(&wrong_map,&spec,2,0,&scene,true).is_err());
            assert!(ack(&raw,&wrong_map,&spec,2,0,&scene).is_err());
            wrong_map=map.clone();wrong_map.arena_type_id=other.arena_type_id();assert!(spec.verify_map(&wrong_map).is_err());
            for key in ["physics_manifest_sha256","projectile_manifest_sha256"]{
                let mut v=descriptor_for(map_id,1);v[key]=if key=="physics_manifest_sha256"{other.spec().physics_manifest_sha256}else{other.spec().projectile_manifest_sha256}.into();
                assert!(CatalogSpec::validate(&v).is_err());
            }
            let mut last=descriptor_for(map_id,1);last["objects"][0]["instance_id"]=(profile.instance_count-1).into();
            last["objects"][0]["first_triangle"]=(profile.physics_triangle_count-42).into();CatalogSpec::validate(&last).unwrap();
            last["objects"][0]["instance_id"]=profile.instance_count.into();assert!(CatalogSpec::validate(&last).is_err());
            last["objects"][0]["instance_id"]=0.into();last["objects"][0]["first_triangle"]=(profile.physics_triangle_count-41).into();assert!(CatalogSpec::validate(&last).is_err());
            for field in ["map","triangles","instances"]{
                let mut source=source_for(&spec);
                match field{"map"=>source["map"]=other.asset().into(),"triangles"=>source["triangles"]["count"]=(profile.physics_triangle_count-1).into(),
                    _=>{source["instances"].as_array_mut().unwrap().pop();}}
                assert!(spec.verify_source(&source).is_err(),"{field}");
            }
        }
        let a=spec_for(MapId::Karelia,2);let b=spec_for(MapId::Prohorovka,2);
        let sa=Scene::new(&a,&[1]).unwrap();let sb=Scene::new(&b,&[1]).unwrap();
        assert_ne!(sa.hash(),sb.hash());assert!(!sa.extends(&sb));assert!(sa.validate(&b).is_err());
        let mut unknown=descriptor(1);unknown["map"]="unknown_map".into();assert!(CatalogSpec::validate(&unknown).is_err());
    }
    #[test]fn catalog_bounds_identity_and_full_spans(){
        for n in [1,6,64]{assert_eq!(CatalogSpec::validate(&descriptor(n)).unwrap().len(),n);}
        for n in [0,65]{assert!(CatalogSpec::validate(&descriptor(n)).is_err());}
        for (key,value) in [("object_id",0.into()),("instance_id",2918.into()),("first_triangle",1_500_000.into()),
            ("triangle_count",0.into()),("triangle_count",4097.into()),("object_revision","legacy-label".into()),("object_id",1.0.into())]{
            let mut v=descriptor(1);v["objects"][0][key]=value;assert!(CatalogSpec::validate(&v).is_err(),"{key}");
        }
        for key in ["object_id","instance_id","first_triangle"]{
            let mut v=descriptor(2);v["objects"][1][key]=v["objects"][0][key].clone();assert!(CatalogSpec::validate(&v).is_err(),"{key}");
        }
        let spec=spec(2);let mut source=serde_json::json!({"version":1,"map":"01_karelia","kind":"original_091_static_triangle_mesh",
            "triangles":{"count":MapId::Karelia.spec().physics_triangle_count},"instances":vec![Value::Null;2918]});
        for (i,e) in spec.entries.iter().enumerate(){source["instances"][i]=serde_json::json!({"kind":"model","resource":"source.model",
            "first_triangle":e.first_triangle,"triangles":e.triangle_count});}
        spec.verify_source(&source).unwrap();
        for (key,value) in [("resource","".into()),("first_triangle",1.into()),("triangles",41.into()),("kind","terrain".into())]{
            let mut v=source.clone();v["instances"][0][key]=value;assert!(spec.verify_source(&v).is_err(),"{key}");
        }
    }
    #[test]fn scene_is_canonical_catalog_bound_and_bounded(){
        let s=spec(64);let empty=Scene::new(&s,&[]).unwrap();
        assert_eq!(empty.version(),0);assert_eq!(empty.hash(),"3b4d76b3e9b6266fea62459b5d9d2567819a9851fc9abdc2c59640f8e089f81f");
        let ids=(1..=40).collect::<Vec<_>>();let full=Scene::new(&s,&ids).unwrap();assert_eq!(full.version(),40);
        assert!(full.extends(&empty));assert!(!empty.extends(&full));assert!(full.extends(&full));
        for bad_ids in [vec![0],vec![65],vec![2,1],vec![1,1],(1..=41).collect()]{assert!(Scene::new(&s,&bad_ids).is_err());}
        let mut other=s.clone();other.sha256="c".repeat(64);assert!(!Scene::new(&other,&ids).unwrap().extends(&full));
    }
    #[test]fn forty_maximum_u32_ids_fit_the_fixed_ipc_line(){
        let mut s=spec(40);for (i,e) in s.entries.iter_mut().enumerate(){e.object_id=u32::MAX-39+i as u32;}
        let ids=s.entries.iter().map(|e|e.object_id).collect::<Vec<_>>();let scene=Scene::new(&s,&ids).unwrap();
        let map=super::super::tests::map();let raw=scene_request(&map,&s,u32::MAX,MAX_SEQUENCE,&scene,false).unwrap();
        assert!(raw.len()<=1025);assert_eq!(json(&raw,1025).unwrap()["removed_object_ids"].as_array().unwrap().len(),40);
        let mut v=json(&raw,1025).unwrap();v.as_object_mut().unwrap().remove("op");v["event"]="scene_synced".into();v["tick"]=(180+MAX_SEQUENCE*6).into();
        let raw=ipc_bytes(&v).unwrap();assert_eq!(ack(&raw,&map,&s,u32::MAX,MAX_SEQUENCE,&scene).unwrap().removed_object_ids,ids);
    }
}
