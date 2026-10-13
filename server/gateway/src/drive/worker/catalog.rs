//! IPC3 cumulative collider-removal snapshots. Source identities are exporter
//! instance IDs only; native client IDs and damage policy do not belong here.
use super::*;
use crate::map_profile091::MapId;

pub const MAX_CATALOG_OBJECTS:usize=64;
pub const MAX_REMOVED_OBJECTS:usize=40;
pub const MAX_LEGACY_CATALOG_BYTES:usize=128*1024;
pub const MAX_CONTACT_CATALOG_OBJECTS:usize=1024;
pub const MAX_CONTACT_REMOVED_OBJECTS:usize=1024;
pub const MAX_EXTENDED_CATALOG_OBJECTS:usize=2048;
pub const MAX_EXTENDED_REMOVED_OBJECTS:usize=2048;

#[derive(Clone,Debug,PartialEq,Eq)]
pub struct CatalogEntry {object_id:u32,instance_id:u32,first_triangle:u32,triangle_count:u32,object_revision:String,kind:String,ram_energy_j:u32,ram_response:Option<String>}
impl CatalogEntry {
    pub fn object_id(&self)->u32{self.object_id}
    pub fn instance_id(&self)->u32{self.instance_id}
    pub fn first_triangle(&self)->u32{self.first_triangle}
    pub fn triangle_count(&self)->u32{self.triangle_count}
    pub fn object_revision(&self)->&str{&self.object_revision}
    pub fn kind(&self)->&str{&self.kind}
    pub fn ram_energy_j(&self)->u32{self.ram_energy_j}
    pub fn ram_response(&self)->Option<&str>{self.ram_response.as_deref()}
}
#[derive(Clone,Debug,PartialEq,Eq)]
pub struct CatalogSpec {pub(super) path:PathBuf,pub(super) sha256:String,map_id:MapId,entries:Vec<CatalogEntry>,contacts:bool,version:u8}
impl CatalogSpec {
    fn parse_manifest(raw:&[u8])->io::Result<Value>{
        let value=json_catalog_extended(raw,1024*1024)?;
        // Reapply the historical parser budgets as well as row bounds. Only
        // explicit v4 catalogs may use the larger array/node envelope.
        if !matches!(value["version"].as_u64(),Some(4|5|6|7)){return json_catalog(raw,1024*1024);}
        Ok(value)
    }
    pub fn load(local_root:&Path,path:&Path,sha256:&str)->io::Result<Self>{
        non_reparse(local_root)?;let root=local_root.canonicalize()?;hash_text(sha256)?;
        let path=owned(&root,path)?;let raw=read(&path,1024*1024)?;
        if format!("{:x}",Sha256::digest(&raw))!=sha256{return Err(bad());}
        // Explicit v4 admits 2048 whole objects. Historical v3 keeps 1024;
        // both retain the one MiB file cap and bounded unique JSON parsing.
        let value=Self::parse_manifest(&raw)?;
        // Keep IPC3/catalog-v2's historical 128 KiB file bound even though
        // the contact profile has a larger one-MiB envelope.
        if value["version"].as_u64()==Some(2) && raw.len()>MAX_LEGACY_CATALOG_BYTES{return Err(bad());}
        let entries=Self::validate(&value)?;
        let version=u8::try_from(uint(&value["version"])?).map_err(|_|bad())?;
        let contacts=version>=3;
        let map_id=MapId::from_asset(text(&value,"map")?)?;
        Ok(Self{path,sha256:sha256.into(),map_id,entries,contacts,version})
    }
    fn validate(v:&Value)->io::Result<Vec<CatalogEntry>>{
        let version=uint(&v["version"])?;
        if version==2 { fields(v,&["version","profile","map","physics_manifest_sha256","projectile_manifest_sha256","objects"])?; }
        else if version==3||version==4 { fields(v,&["version","profile","map","physics_manifest_sha256","projectile_manifest_sha256","contacts","objects"])?; if v["contacts"]!=Value::Bool(true){return Err(bad());} }
        else if matches!(version,5|6|7) {fields(v,&["version","profile","map","physics_manifest_sha256","projectile_manifest_sha256","contacts","objects","ram_policy"])?;
            let policy=match version{7=>fracture::TOTAL_POLICY,6=>fracture::WHOLE_POLICY,_=>fracture::POLICY};
            if v["contacts"]!=Value::Bool(true)||text(v,"ram_policy")?!=policy{return Err(bad());}}
        else{return Err(bad());}
        let map_id=MapId::from_asset(text(v,"map")?)?;let profile=map_id.spec();
        if text(v,"profile")?!="test_lab"
            || text(v,"physics_manifest_sha256")?!=profile.physics_manifest_sha256
            || text(v,"projectile_manifest_sha256")?!=profile.projectile_manifest_sha256{return Err(bad());}
        let rows=v["objects"].as_array().ok_or_else(bad)?;
        let limit=match version{4|5|6|7=>MAX_EXTENDED_CATALOG_OBJECTS,3=>MAX_CONTACT_CATALOG_OBJECTS,_=>MAX_CATALOG_OBJECTS};
        if rows.is_empty() || rows.len()>limit{return Err(bad());}
        let mut entries=Vec::new();let mut instances=BTreeSet::new();let mut previous=0;
        for row in rows {
            if version==7 {fields(row,&["object_id","instance_id","kind","first_triangle","triangle_count","object_revision","ram_energy_j","ram_response"])?;}
            else if version>=5 {fields(row,&["object_id","instance_id","kind","first_triangle","triangle_count","object_revision","ram_energy_j"])?;}
            else if version>=3 {fields(row,&["object_id","instance_id","kind","first_triangle","triangle_count","object_revision"])?;} else {fields(row,&["object_id","instance_id","first_triangle","triangle_count","object_revision"])?;}
            let id=uint(&row["object_id"])?;let instance=uint(&row["instance_id"])?;
            let first=uint(&row["first_triangle"])?;let count=uint(&row["triangle_count"])?;
            let revision=text(row,"object_revision")?;hash_text(revision)?;
            let kind=if version>=3{text(row,"kind")?}else{"fragile"};
            if !matches!(kind,"tree"|"fragile"){return Err(bad());}
            let energy=if version>=5{uint(&row["ram_energy_j"])?}else{0};
            if if matches!(version,6|7){energy!=8_000}else{!matches!(energy,0|8_000)||(energy!=0&&kind!="fragile")}{return Err(bad());}
            let response=if version==7 {
                let response=text(row,"ram_response")?;
                if !matches!(response,"total_linear"|"normal_linear") || response=="total_linear"&&kind!="fragile" {return Err(bad());}
                Some(response.to_owned())
            }else{None};
            if id<=previous || id>u32::MAX as u64 || instance>=profile.instance_count as u64 || !instances.insert(instance)
                || count==0 || count>4096 || first>profile.physics_triangle_count as u64
                || first.checked_add(count).is_none_or(|end|end>profile.physics_triangle_count as u64){return Err(bad());}
            previous=id;entries.push(CatalogEntry{object_id:id as u32,instance_id:instance as u32,first_triangle:first as u32,
                triangle_count:count as u32,object_revision:revision.into(),kind:kind.into(),ram_energy_j:energy as u32,ram_response:response});
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
            let source_kind=if entry.kind=="tree"{"speedtree"}else{"model"};
            if text(row,"kind")?!=source_kind || resource.is_empty() || resource.len()>1024
                || uint(&row["first_triangle"])?!=entry.first_triangle as u64 || uint(&row["triangles"])?!=entry.triangle_count as u64
                || entry.first_triangle as u64+entry.triangle_count as u64>total{return Err(bad());}
        }Ok(())
    }
    pub fn sha256(&self)->&str{&self.sha256}
    pub fn entries(&self)->&[CatalogEntry]{&self.entries}
    pub fn contacts(&self)->bool{self.contacts}
    pub fn version(&self)->u8{self.version}
    fn ipc_version(&self)->u8{if self.version>=5{5}else if self.contacts{4}else{3}}
    fn max_removed(&self)->usize{match self.version{4|5|6|7=>MAX_EXTENDED_REMOVED_OBJECTS,3=>MAX_CONTACT_REMOVED_OBJECTS,_=>MAX_REMOVED_OBJECTS}}
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
        let max_removed=spec.max_removed();
        if ids.len()>max_removed || ids.iter().enumerate().any(|(i,id)|*id==0 ||
            (i>0 && ids[i-1]>=*id) || spec.entries.binary_search_by_key(id,|e|e.object_id).is_err()){return Err(bad());}
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
    let mut v=serde_json::json!({"version":spec.ipc_version(),"op":if restore{"restore_scene"}else{"sync_removed"},
        "generation":generation,"config_sha256":map.config_sha256,"catalog_sha256":spec.sha256,
        "advance_seq":seq,"scene_version":scene.version(),"removed_object_ids":scene.ids,"scene_sha256":scene.hash});
    if spec.contacts {v["contacts"]=true.into();}
    ipc_bytes(&v)
}
pub(super) fn request_catalog(seq:u32,input:Input,scene:&Scene,spec:&CatalogSpec)->io::Result<Vec<u8>>{
    let mut v=json(&request(seq,input)?,1024)?;v["version"]=3.into();v["scene_version"]=scene.version().into();
    v["scene_sha256"]=scene.hash.clone().into();
    v["version"]=spec.ipc_version().into();
    if spec.contacts {v["contacts"]=true.into();}
    ipc_bytes(&v)
}
#[derive(Clone,Debug,PartialEq,Eq)]
pub struct CatalogAck {pub generation:u32,pub config_sha256:String,pub catalog_sha256:String,pub advance_seq:u32,
    pub tick:u32,pub scene_version:u32,pub removed_object_ids:Vec<u32>,pub scene_sha256:String}
pub(super) fn ack(raw:&[u8],map:&MapSpec,spec:&CatalogSpec,generation:u32,seq:u32,scene:&Scene)->io::Result<CatalogAck>{
    spec.verify_map(map)?;
    scene.validate(spec)?;
    if !raw.is_ascii() || generation==0 || seq>MAX_SEQUENCE{return Err(bad());}
    let v=if spec.version>=4{json_catalog_extended(raw,MAX_IPC_LINE)?}else{json(raw,MAX_IPC_LINE)?};
    if spec.contacts {fields(&v,&["version","event","generation","config_sha256","catalog_sha256","advance_seq","tick",
        "scene_version","removed_object_ids","scene_sha256","contacts"])?;} else {fields(&v,&["version","event","generation","config_sha256","catalog_sha256","advance_seq","tick",
        "scene_version","removed_object_ids","scene_sha256"])?;}
    if uint(&v["version"])?!=u64::from(spec.ipc_version()) || (spec.contacts && v["contacts"]!=Value::Bool(true)) || text(&v,"event")?!="scene_synced" || uint(&v["generation"])?!=generation as u64
        || text(&v,"config_sha256")?!=map.config_sha256 || text(&v,"catalog_sha256")?!=spec.sha256
        || uint(&v["advance_seq"])?!=seq as u64 || uint(&v["tick"])?!=180+seq as u64*6
        || uint(&v["scene_version"])?!=scene.version() as u64 || text(&v,"scene_sha256")?!=scene.hash{return Err(bad());}
    let ids=v["removed_object_ids"].as_array().ok_or_else(bad)?;
    if ids.len()!=scene.ids.len(){return Err(bad());}
    for (value,id) in ids.iter().zip(&scene.ids){if uint(value)?!=*id as u64{return Err(bad());}}
    Ok(CatalogAck{generation,config_sha256:map.config_sha256.clone(),catalog_sha256:spec.sha256.clone(),advance_seq:seq,
        tick:180+seq*6,scene_version:scene.version(),removed_object_ids:scene.ids.clone(),scene_sha256:scene.hash.clone()})
}
fn parse_contacts(state:&Value,spec:&CatalogSpec,scene:&Scene)->io::Result<Vec<ObjectContact>>{
    let rows=state.as_array().or_else(||state.get("object_contacts").and_then(Value::as_array)).ok_or_else(bad)?;
    if rows.len()>32{return Err(bad());}
    let mut out=Vec::with_capacity(rows.len());let mut previous=0u32;
    for row in rows {
        fields(row,&["object_id","kind","substep","point","normal","velocity"])?;
        let raw_id=uint(&row["object_id"])?;
        if raw_id==0 || raw_id>u32::MAX as u64 { return Err(bad()); }
        let id=raw_id as u32;
        if id==0 || id<=previous || scene.ids.binary_search(&id).is_ok(){return Err(bad());}
        let entry=spec.entries.iter().find(|e|e.object_id==id).ok_or_else(bad)?;
        let kind=text(row,"kind")?;
        if !matches!(kind,"hull"|"wheel"){return Err(bad());}
        let substep=uint(&row["substep"])?;if !(1..=6).contains(&substep){return Err(bad());}
        let point=vector(&row["point"],-2000.,2000.)?;let normal=vector(&row["normal"],-1.,1.)?;let velocity=vector(&row["velocity"],-25.,25.)?;
        let length=normal.iter().map(|x|x*x).sum::<f32>().sqrt();if !(0.5..=1.5).contains(&length){return Err(bad());}
        if entry.kind!="tree" && entry.kind!="fragile"{return Err(bad());}
        out.push(ObjectContact{object_id:id,kind:kind.into(),substep:substep as u8,point,normal,velocity});previous=id;
    }
    Ok(out)
}
pub(super) fn response(raw:&[u8],map:&MapSpec,spec:&CatalogSpec,generation:u32,seq:u32,spawn:Option<[f32;3]>,scene:&Scene)->io::Result<State>{
    spec.verify_map(map)?;
    scene.validate(spec)?;
    if !raw.is_ascii() || generation==0{return Err(bad());}let mut v=json(raw,MAX_IPC_LINE)?;
    if spec.contacts {fields(&v,&["version","event","seq","tick","settle_ticks","map","config_sha256","state","generation","catalog_sha256","scene_version","scene_sha256","contacts"])?;} else {fields(&v,&["version","event","seq","tick","settle_ticks","map","config_sha256","state","generation","catalog_sha256","scene_version","scene_sha256"])?;}
    if uint(&v["version"])?!=u64::from(spec.ipc_version()) || (spec.contacts && v["contacts"]!=Value::Bool(true)) || uint(&v["generation"])?!=generation as u64 || text(&v,"catalog_sha256")?!=spec.sha256
        || uint(&v["scene_version"])?!=scene.version() as u64 || text(&v,"scene_sha256")?!=scene.hash{return Err(bad());}
    let mut contacts=if spec.contacts {parse_contacts(&v["state"],spec,scene)?} else {Vec::new()};
    let fractures=if spec.version>=5 {
        let receipts=fracture::parse(&v["state"]["fractures"],&contacts,spec,map,seq)?;
        if text(&v,"event")?!=if seq==0{"ready"}else if receipts.is_empty(){"state"}else{"prepared"}{return Err(bad());}
        // An energy-responsive collider must never be destroyed by an ordinary
        // denied/support contact after the worker retained its physical body.
        contacts.retain(|contact| spec.entries.iter().find(|entry|entry.object_id==contact.object_id)
            .is_some_and(|entry|entry.ram_energy_j==0||receipts.iter().any(|receipt|receipt.object_id==contact.object_id)));
        v["event"]=if seq==0{"ready"}else{"state"}.into();
        receipts
    } else {Vec::new()};
    let object=v.as_object_mut().ok_or_else(bad)?;
    for key in ["generation","catalog_sha256","scene_version","scene_sha256"]{object.remove(key);}
    object.remove("contacts");
    if let Some(state)=object.get_mut("state").and_then(Value::as_object_mut){state.remove("object_contacts");if spec.version>=5{state.remove("fractures");}}
    v["version"]=1.into();
    let mut state=response_at_spawn(&serde_json::to_vec(&v).map_err(|_|bad())?,map,seq,spawn)?;
    state.scene_version=scene.version();state.object_contacts=contacts;state.fractures=fractures;Ok(state)
}

#[cfg(test)]
pub(super) mod tests {
    use super::*;
    pub(in super::super) fn descriptor(n:usize)->Value{serde_json::json!({"version":2,"profile":"test_lab","map":"01_karelia",
        "physics_manifest_sha256":PHYSICS_MANIFEST,"projectile_manifest_sha256":PROJECTILE_MANIFEST,
        "objects":(0..n).map(|i|serde_json::json!({"object_id":i+1,"instance_id":i,"first_triangle":i*42,
            "triangle_count":42,"object_revision":"e".repeat(64)})).collect::<Vec<_>>()})}
    pub(in super::super) fn spec(n:usize)->CatalogSpec{
        CatalogSpec{path:"unit".into(),sha256:"b".repeat(64),map_id:MapId::Karelia,entries:CatalogSpec::validate(&descriptor(n)).unwrap(),contacts:false,version:2}
    }
    pub(in super::super) fn fracture_spec(n:usize)->CatalogSpec{
        let mut v=descriptor(n);v["version"]=5.into();v["contacts"]=true.into();v["ram_policy"]=fracture::POLICY.into();
        for row in v["objects"].as_array_mut().unwrap(){row["kind"]="fragile".into();row["ram_energy_j"]=8_000.into();}
        let raw=serde_json::to_vec(&v).unwrap();
        CatalogSpec{path:"unit".into(),sha256:format!("{:x}",Sha256::digest(raw)),map_id:MapId::Karelia,
            entries:CatalogSpec::validate(&v).unwrap(),contacts:true,version:5}
    }
    pub(in super::super) fn whole_spec(n:usize)->CatalogSpec{
        let mut v=descriptor(n);v["version"]=6.into();v["contacts"]=true.into();v["ram_policy"]=fracture::WHOLE_POLICY.into();
        for (i,row) in v["objects"].as_array_mut().unwrap().iter_mut().enumerate(){
            row["kind"]=if i%2==0{"tree"}else{"fragile"}.into();row["ram_energy_j"]=8_000.into();
        }
        let raw=serde_json::to_vec(&v).unwrap();
        CatalogSpec{path:"unit".into(),sha256:format!("{:x}",Sha256::digest(raw)),map_id:MapId::Karelia,
            entries:CatalogSpec::validate(&v).unwrap(),contacts:true,version:6}
    }
    fn response_descriptor(entries:&[(&str,&str)])->Value {
        let mut v=descriptor(entries.len());v["version"]=7.into();v["contacts"]=true.into();v["ram_policy"]=fracture::TOTAL_POLICY.into();
        for (row,(kind,response)) in v["objects"].as_array_mut().unwrap().iter_mut().zip(entries){
            row["kind"]=(*kind).into();row["ram_energy_j"]=8_000.into();row["ram_response"]=(*response).into();
        }v
    }
    pub(in super::super) fn response_spec(entries:&[(&str,&str)])->CatalogSpec {
        let v=response_descriptor(entries);let raw=serde_json::to_vec(&v).unwrap();
        CatalogSpec{path:"unit".into(),sha256:format!("{:x}",Sha256::digest(raw)),map_id:MapId::Karelia,
            entries:CatalogSpec::validate(&v).unwrap(),contacts:true,version:7}
    }
    #[test]fn total_catalog_requires_exact_new_semantics_and_retains_old_field_sets(){
        let rows=[("fragile","total_linear"),("tree","normal_linear"),("fragile","normal_linear")];
        let spec=response_spec(&rows);assert_eq!(spec.ipc_version(),5);assert_eq!(spec.max_removed(),2048);
        assert_eq!(spec.entries()[0].ram_response(),Some("total_linear"));
        assert_eq!(spec.entries()[1].ram_response(),Some("normal_linear"));
        for (field,value) in [("ram_response",Value::Null),("ram_response","total".into()),
            ("ram_response",true.into()),("ram_energy_j",0.into()),("ram_energy_j",serde_json::json!(8000.0)),
            ("kind","tree".into())] {
            let mut invalid=response_descriptor(&rows);invalid["objects"][0][field]=value;
            assert!(CatalogSpec::validate(&invalid).is_err(),"{field}");
        }
        let mut missing=response_descriptor(&rows);missing["objects"][0].as_object_mut().unwrap().remove("ram_response");
        assert!(CatalogSpec::validate(&missing).is_err());
        for policy in [fracture::POLICY,fracture::WHOLE_POLICY,"unknown"] {
            let mut invalid=response_descriptor(&rows);invalid["ram_policy"]=policy.into();assert!(CatalogSpec::validate(&invalid).is_err());
        }
        for version in 2..=6 {
            let mut old=descriptor(1);old["version"]=version.into();
            if version>=3 {old["contacts"]=true.into();old["objects"][0]["kind"]="fragile".into();}
            if version>=5 {old["ram_policy"]=if version==6{fracture::WHOLE_POLICY}else{fracture::POLICY}.into();old["objects"][0]["ram_energy_j"]=8000.into();}
            assert_eq!(CatalogSpec::validate(&old).unwrap()[0].ram_response(),None);
            old["objects"][0]["ram_response"]="normal_linear".into();assert!(CatalogSpec::validate(&old).is_err());
        }
    }
    #[test]fn total_catalog_preserves_capacity_source_spans_and_rejects_future_versions(){
        let rows=vec![("fragile","total_linear");2048];let v=response_descriptor(&rows);
        let raw=serde_json::to_vec(&v).unwrap();assert!(CatalogSpec::parse_manifest(&raw).is_ok());
        let spec=response_spec(&rows);spec.verify_source(&source_for(&spec)).unwrap();
        Scene::new(&spec,&(1..=2048).collect::<Vec<_>>()).unwrap();
        let too_many=response_descriptor(&vec![("fragile","total_linear");2049]);
        assert!(CatalogSpec::validate(&too_many).is_err());
        assert!(CatalogSpec::parse_manifest(&serde_json::to_vec(&too_many).unwrap()).is_err());
        let mut wrong_source=source_for(&spec);wrong_source["instances"][0]["triangles"]=41.into();
        assert!(spec.verify_source(&wrong_source).is_err());
        let mut wrong_version=v;wrong_version["version"]=8.into();assert!(CatalogSpec::validate(&wrong_version).is_err());
    }
    #[test]fn total_catalog_exact_prohorovka_export_changes_only_declared_response(){
        let local=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local").canonicalize().unwrap();
        let base=local.join("evidence/20261013-p05b-tracked-handling-01");
        let new=CatalogSpec::load(&local,&base.join("night-fence-export01/catalog/physics-removals.json"),
            "9c40f5bdeb8b77364805f31f18a9c6943a811630f7676fd10c6ec55d8ec5fd5e").unwrap();
        let old=CatalogSpec::load(&local,&base.join("ram-import01/physics-removals.json"),
            "6d9a57de3b86f1e3b9a66390ff0968677b9a29e9238ca8559158d99dfb3dce16").unwrap();
        assert_eq!(new.version(),7);assert_eq!(new.ipc_version(),5);assert_eq!(new.entries().len(),1038);
        assert_eq!(new.entries().iter().filter(|e|e.ram_response()==Some("total_linear")).count(),403);
        assert_eq!(new.entries().iter().filter(|e|e.ram_response()==Some("normal_linear")).count(),635);
        assert_eq!(new.entries().iter().filter(|e|e.kind()=="tree").count(),626);
        for (new,old) in new.entries().iter().zip(old.entries()) {
            let mut projected=new.clone();projected.ram_response=None;assert_eq!(&projected,old);
        }
    }
    #[test]fn whole_catalog_is_explicit_bounded_and_does_not_relax_old_tree_policy(){
        let spec=whole_spec(2048);assert_eq!(spec.ipc_version(),5);assert_eq!(spec.max_removed(),2048);
        let mut v=descriptor(1);v["version"]=6.into();v["contacts"]=true.into();v["ram_policy"]=fracture::WHOLE_POLICY.into();
        v["objects"][0]["kind"]="tree".into();v["objects"][0]["ram_energy_j"]=8_000.into();
        CatalogSpec::validate(&v).unwrap();
        for energy in [serde_json::json!(0),serde_json::json!(8000.0),serde_json::json!(1),serde_json::json!(8001)] {
            let mut changed=v.clone();changed["objects"][0]["ram_energy_j"]=energy;assert!(CatalogSpec::validate(&changed).is_err());
        }
        for version in [4,5,7] {let mut changed=v.clone();changed["version"]=version.into();assert!(CatalogSpec::validate(&changed).is_err());}
        let mut changed=v;changed["ram_policy"]=fracture::POLICY.into();assert!(CatalogSpec::validate(&changed).is_err());
    }
    #[test]fn fracture_catalog_pins_policy_and_each_energy_without_relaxing_legacy(){
        let spec=fracture_spec(2048);assert_eq!(spec.version(),5);assert_eq!(spec.entries()[0].ram_energy_j(),8_000);
        let mut v=descriptor(1);v["version"]=5.into();v["contacts"]=true.into();v["ram_policy"]=fracture::POLICY.into();
        v["objects"][0]["kind"]="fragile".into();v["objects"][0]["ram_energy_j"]=8_000.into();
        CatalogSpec::validate(&v).unwrap();
        for energy in [serde_json::json!(8000.0),serde_json::json!(-1),serde_json::json!(1),serde_json::json!(8001)]{
            let mut changed=v.clone();changed["objects"][0]["ram_energy_j"]=energy;assert!(CatalogSpec::validate(&changed).is_err());}
        for key in ["ram_policy","contacts"]{let mut changed=v.clone();changed[key]=false.into();assert!(CatalogSpec::validate(&changed).is_err());}
        let mut changed=v.clone();changed["objects"][0]["kind"]="tree".into();assert!(CatalogSpec::validate(&changed).is_err());
        changed["objects"][0]["ram_energy_j"]=0.into();CatalogSpec::validate(&changed).unwrap();
        changed=v;changed["version"]=4.into();assert!(CatalogSpec::validate(&changed).is_err());
    }
    pub(in super::super) fn spec_for(map_id:MapId,n:usize)->CatalogSpec{
        let v=descriptor_for(map_id,n);let raw=serde_json::to_vec(&v).unwrap();
        CatalogSpec{path:"unit".into(),sha256:format!("{:x}",Sha256::digest(raw)),map_id,entries:CatalogSpec::validate(&v).unwrap(),contacts:false,version:2}
    }
    fn descriptor_for(map_id:MapId,n:usize)->Value{
        let mut v=descriptor(n);v["map"]=map_id.asset().into();
        v["physics_manifest_sha256"]=map_id.spec().physics_manifest_sha256.into();
        v["projectile_manifest_sha256"]=map_id.spec().projectile_manifest_sha256.into();v
    }
    fn contact_spec(n:usize)->CatalogSpec{
        let mut v=descriptor(n);v["version"]=3.into();v["contacts"]=true.into();
        for (i,row) in v["objects"].as_array_mut().unwrap().iter_mut().enumerate(){row["kind"]=if i==0{"tree"}else{"fragile"}.into();}
        let raw=serde_json::to_vec(&v).unwrap();CatalogSpec{path:"unit".into(),sha256:format!("{:x}",Sha256::digest(raw)),map_id:MapId::Karelia,entries:CatalogSpec::validate(&v).unwrap(),contacts:true,version:3}
    }
    fn source_for(spec:&CatalogSpec)->Value{
        let mut source=serde_json::json!({"version":1,"map":spec.map_id.asset(),"kind":"original_091_static_triangle_mesh",
            "triangles":{"count":spec.map_id.spec().physics_triangle_count},"instances":vec![Value::Null;spec.map_id.spec().instance_count]});
        for e in &spec.entries{source["instances"][e.instance_id as usize]=serde_json::json!({"kind":"model","resource":"source.model",
            "first_triangle":e.first_triangle,"triangles":e.triangle_count});}source
    }
    fn extended_manifest(n:usize)->Value{
        let mut value=descriptor(n);value["version"]=4.into();value["contacts"]=true.into();
        for row in value["objects"].as_array_mut().unwrap(){row["kind"]="fragile".into();}value
    }
    fn extended_spec(n:usize)->CatalogSpec{
        let raw=serde_json::to_vec(&extended_manifest(n)).unwrap();
        let value=CatalogSpec::parse_manifest(&raw).unwrap();
        CatalogSpec{path:"unit".into(),sha256:format!("{:x}",Sha256::digest(&raw)),map_id:MapId::Karelia,
            entries:CatalogSpec::validate(&value).unwrap(),contacts:true,version:4}
    }
    #[test]fn extended_v4_admits_complete_fence_capacity_but_preserves_legacy_bounds(){
        for n in [1038,2048]{
            let spec=extended_spec(n);assert_eq!(spec.version(),4);assert_eq!(spec.entries().len(),n);
            spec.verify_source(&source_for(&spec)).unwrap();
            assert_eq!(Scene::new(&spec,&(1..=n as u32).collect::<Vec<_>>()).unwrap().version(),n as u32);
        }
        let value=extended_manifest(2049);let raw=serde_json::to_vec(&value).unwrap();
        assert!(CatalogSpec::parse_manifest(&raw).is_err());assert!(CatalogSpec::validate(&value).is_err());
        let spec=extended_spec(2048);assert!(Scene::new(&spec,&(1..=2049).collect::<Vec<_>>()).is_err());
        for n in [1024,1025]{
            let mut old=extended_manifest(n);old["version"]=3.into();let raw=serde_json::to_vec(&old).unwrap();
            assert_eq!(CatalogSpec::parse_manifest(&raw).is_ok(),n==1024);
            assert_eq!(CatalogSpec::validate(&old).is_ok(),n==1024);
        }
        assert!(CatalogSpec::validate(&descriptor(65)).is_err());
        for (field,value) in [("version",5.into()),("contacts",false.into()),("profile","production".into())]{
            let mut invalid=extended_manifest(1038);invalid[field]=value;assert!(CatalogSpec::validate(&invalid).is_err());
        }
    }
    #[test]fn extended_v4_keeps_whole_instance_geometry_and_source_identity(){
        let spec=extended_spec(1038);let source=source_for(&spec);spec.verify_source(&source).unwrap();
        for (field,value) in [("first_triangle",43.into()),("triangles",41.into()),("kind","speedtree".into())]{
            let mut invalid=source.clone();invalid["instances"][1][field]=value;assert!(spec.verify_source(&invalid).is_err());
        }
        for field in ["instance_id","first_triangle","object_id"]{
            let mut invalid=extended_manifest(1038);invalid["objects"][1][field]=invalid["objects"][0][field].clone();
            assert!(CatalogSpec::validate(&invalid).is_err());
        }
        let mut part=extended_manifest(1038);part["objects"][0]["kind"]="module".into();
        assert!(CatalogSpec::validate(&part).is_err());
    }
    #[test]fn extended_v4_complete_maximum_id_scene_fits_ipc4_and_rejects_stale_ack(){
        let mut spec=extended_spec(2048);
        for (i,entry) in spec.entries.iter_mut().enumerate(){entry.object_id=u32::MAX-2047+i as u32;}
        let ids=spec.entries.iter().map(|entry|entry.object_id).collect::<Vec<_>>();
        let scene=Scene::new(&spec,&ids).unwrap();let map=super::super::tests::map();
        let raw=scene_request(&map,&spec,7,MAX_SEQUENCE,&scene,false).unwrap();assert!(raw.len()<=MAX_IPC_LINE);
        assert!(json(&raw,MAX_IPC_LINE).is_err());
        let mut reply=json_catalog_extended(&raw,MAX_IPC_LINE).unwrap();
        assert_eq!(reply["version"],4);assert_eq!(reply["removed_object_ids"].as_array().unwrap().len(),2048);
        reply.as_object_mut().unwrap().remove("op");reply["event"]="scene_synced".into();reply["tick"]=(180+MAX_SEQUENCE*6).into();
        let encoded=ipc_bytes(&reply).unwrap();assert!(encoded.len()<=MAX_IPC_LINE);
        assert_eq!(ack(&encoded,&map,&spec,7,MAX_SEQUENCE,&scene).unwrap().removed_object_ids,ids);
        for (field,value) in [("catalog_sha256","c".repeat(64).into()),("scene_sha256","d".repeat(64).into()),
            ("generation",6.into()),("scene_version",2047.into()),("advance_seq",(MAX_SEQUENCE-1).into())]{
            let mut stale=reply.clone();stale[field]=value;
            assert!(ack(&ipc_bytes(&stale).unwrap(),&map,&spec,7,MAX_SEQUENCE,&scene).is_err(),"{field}");
        }
        for mode in 0..3{
            let mut invalid=reply.clone();let values=invalid["removed_object_ids"].as_array_mut().unwrap();
            match mode{0=>values.swap(0,1),1=>values[1]=values[0].clone(),_=>values.push(1.into())};
            assert!(ack(&ipc_bytes(&invalid).unwrap(),&map,&spec,7,MAX_SEQUENCE,&scene).is_err());
        }
    }
    #[test]fn extended_parser_retains_duplicate_depth_byte_and_old_array_guards(){
        let raw=serde_json::to_vec(&vec![0;1025]).unwrap();
        assert!(json(&raw,MAX_IPC_LINE).is_err());assert!(json_catalog(&raw,MAX_IPC_LINE).is_err());
        assert_eq!(json_catalog_extended(&raw,MAX_IPC_LINE).unwrap().as_array().unwrap().len(),1025);
        assert!(json_catalog_extended(&raw,raw.len()-1).is_err());
        for raw in [br#"{"outer":{"x":1,"x":2}}"#.as_slice(),br#"{"x":1,"x":2}"#.as_slice()]{
            assert!(json_catalog_extended(raw,MAX_IPC_LINE).is_err());
        }
        let deep=format!("{}0{}","[".repeat(13),"]".repeat(13));
        assert!(json_catalog_extended(deep.as_bytes(),MAX_IPC_LINE).is_err());
        let nodes=serde_json::to_vec(&vec![vec![0;20];2048]).unwrap();
        assert!(json_catalog_extended(&nodes,1024*1024).is_err());
    }
    #[test]fn contact_v3_admits_tree_speedtree_source_and_large_scene_bound(){
        let spec=contact_spec(2);let mut source=source_for(&spec);source["instances"][0]["kind"]="speedtree".into();
        source["instances"][0]["resource"]="tree.spt".into();spec.verify_source(&source).unwrap();
        let large=contact_spec(1024);let ids=(1..=1024).collect::<Vec<_>>();assert_eq!(Scene::new(&large,&ids).unwrap().version(),1024);
        assert!(Scene::new(&spec,&(1..=1025).collect::<Vec<_>>()).is_err());
        let mut manifest=descriptor(1024);manifest["version"]=3.into();manifest["contacts"]=true.into();
        for row in manifest["objects"].as_array_mut().unwrap(){row["kind"]="fragile".into();}
        let bytes=serde_json::to_vec(&manifest).unwrap();assert!(json_catalog(&bytes,1024*1024).is_ok());
        assert!(json(&bytes,1024*1024).is_err());
    }
    #[test]fn contact_rows_reject_bad_identity_bounds_and_accept_valid(){
        let spec=contact_spec(2);let scene=Scene::new(&spec,&[]).unwrap();
        let good=serde_json::json!([{"object_id":1,"kind":"hull","substep":2,"point":[1,2,3],"normal":[0,0,1],"velocity":[0,0,8]}]);
        assert_eq!(parse_contacts(&good,&spec,&scene).unwrap().len(),1);
        for bad_row in [
            serde_json::json!({"object_id":1,"kind":"hull","substep":0,"point":[1,2,3],"normal":[0,0,1],"velocity":[0,0,8]}),
            serde_json::json!({"object_id":1,"kind":"wheel","substep":2,"point":[1,2,3],"normal":[0,0,2],"velocity":[0,0,8]}),
            serde_json::json!({"object_id":9,"kind":"hull","substep":2,"point":[1,2,3],"normal":[0,0,1],"velocity":[0,0,8]}),
        ] { let rows=serde_json::json!([bad_row]);assert!(parse_contacts(&rows,&spec,&scene).is_err()); }
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
