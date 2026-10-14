//! Offline only: decode immutable raw captures with the real pool, parser and
//! complete physical proof validator. This test never starts a worker process.
use super::*;

#[derive(Clone,Copy,PartialEq,Eq)]
enum CaptureScope {First8,AllAlive4}
fn angular_changed(before:[f32;3],after:[f32;3])->bool {
    // Physical nonzero debit excludes a signed-zero representation change.
    before.iter().zip(after).any(|(before,after)|*before!=after)
}
impl CaptureScope {
    fn all_alive(self)->bool {self==Self::AllAlive4}
    fn cases(self)->&'static [(&'static str,&'static str,u32)] {match self {
        Self::First8=>&[("is7","pivot",1),("is7","pivot",2),("ms1","pivot",1),("ms1","pivot",2),
            ("ms1","chain",1),("ms1","chain",2),("is7","chain",1),("is7","chain",2)],
        Self::AllAlive4=>&[("is7","pivot",1),("is7","pivot",2),("ms1","pivot",1),("ms1","pivot",2)]}}
    fn binding(self,binding:&Value)->io::Result<()> {
        if self.all_alive(){
            fields(binding,&["version","scope","local_root","capture_receipt","pools"])?;
            if uint(&binding["version"])?!=2||text(binding,"scope")?!="P05B_ANGULAR_ALLALIVE4"{return Err(bad());}
            fields(&binding["pools"],&["ms1_pivot","is7_pivot"])?;
        }else{
            fields(binding,&["version","local_root","capture_receipt","pools"])?;
            if uint(&binding["version"])?!=1{return Err(bad());}
            fields(&binding["pools"],&["ms1_pivot","ms1_chain","is7_pivot","is7_chain"])?;
        }Ok(())
    }
    fn generation(self,i:usize)->u32 {if self.all_alive(){19100+i as u32}else{19000+i as u32}}
}

fn pinned(root:&Path,v:&Value,limit:usize)->io::Result<(PathBuf,Vec<u8>)>{
    fields(v,&["path","bytes","sha256"])?;let path=owned(root,Path::new(text(v,"path")?))?;
    let hash=text(v,"sha256")?;hash_text(hash)?;let size=uint(&v["bytes"])?;
    if size>limit as u64||file_hash(&path,size)?!=hash{return Err(bad());}
    let bytes=if size==0{Vec::new()}else{read(&path,limit)?};Ok((path,bytes))
}
fn lines(raw:&[u8])->io::Result<Vec<&[u8]>>{
    if raw.is_empty()||!raw.ends_with(b"\n"){return Err(bad());}
    let rows=raw[..raw.len()-1].split(|b|*b==b'\n').collect::<Vec<_>>();
    if !(121..=241).contains(&rows.len())||rows.iter().any(|row|row.is_empty()||row.len()>MAX_ANGULAR_IPC_LINE){return Err(bad());}Ok(rows)
}
fn value_same(actual:&[u8],expected:&[u8])->io::Result<()> {
    if json_with_node_limit::<2048>(actual,MAX_ANGULAR_IPC_LINE,4096)?
        !=json_with_node_limit::<2048>(expected,MAX_ANGULAR_IPC_LINE,4096)?{return Err(bad());}Ok(())
}
fn replay(scope:CaptureScope)->io::Result<Value>{
    let binding_path=PathBuf::from(std::env::var_os("WOT_ANGULAR_DECODE_BINDING").ok_or_else(bad)?);
    non_reparse(&binding_path)?;let raw=read(&binding_path,65536)?;
    let binding_sha=std::env::var("WOT_ANGULAR_DECODE_BINDING_SHA256").map_err(|_|bad())?;hash_text(&binding_sha)?;
    if format!("{:x}",Sha256::digest(&raw))!=binding_sha{return Err(bad());}
    let binding=json(&raw,65536)?;scope.binding(&binding)?;
    let root=PathBuf::from(text(&binding,"local_root")?);non_reparse(&root)?;let root=root.canonicalize()?;
    owned(&root,&binding_path)?;
    let (_,receipt_raw)=pinned(&root,&binding["capture_receipt"],1024*1024)?;
    let receipt=json_with_node_limit::<2048>(&receipt_raw,1024*1024,4096)?;
    let (_,capture_binding_raw)=pinned(&root,&receipt["binding"],1024*1024)?;
    let capture_binding=json_with_node_limit::<2048>(&capture_binding_raw,1024*1024,4096)?;
    if scope.all_alive()&&(capture_binding["scope"]!="P05B_ANGULAR_ALLALIVE4"
        ||capture_binding["root_authorized_execution"]!=true
        ||uint(&capture_binding["max_workers"])?!=4||uint(&capture_binding["max_advances"])?!=120
        ||!receipt["post_pin_error"].is_null()||!receipt["outer_error"].is_null()){return Err(bad());}
    let (catalog_path,_)=pinned(&root,&capture_binding["catalog"],1024*1024)?;
    let catalog=CatalogSpec::load(&root,&catalog_path,text(&capture_binding["catalog"],"sha256")?)?;
    if catalog.version()!=8{return Err(bad());}
    let cases=scope.cases();
    let results=receipt["results"].as_array().filter(|a|a.len()==cases.len()).ok_or_else(bad)?;
    let mut report=Vec::new();let mut total_frames=0;let mut total_receipts=0;let mut total_acks=0;let mut targets_complete=true;
    for (i,(row,&(kind,mode,repeat))) in results.iter().zip(cases).enumerate(){
        if row["case"]!=serde_json::json!([kind,mode,repeat]){return Err(bad());}
        if scope.all_alive()&&(uint(&row["frames"])?!=120||row["cleanup"]["exit_code"]!=0
            ||row["cleanup"]["faults"]!=serde_json::json!([])||row["cleanup"]["cleanup_errors"]!=serde_json::json!([])
            ||!row["error"].is_null()){return Err(bad());}
        let pool_key=format!("{kind}_{mode}");let (pool_path,_)=pinned(&root,&binding["pools"][&pool_key],65536)?;
        let pool=Pool::load(&root,&pool_path)?;pool.verify_assets()?;
        let (_,requests)=pinned(&root,&row["raw"]["requests.jsonl"],32*1024*1024)?;
        let (_,replies)=pinned(&root,&row["raw"]["stdout.jsonl"],32*1024*1024)?;
        let (_,stderr)=pinned(&root,&row["raw"]["stderr.bin"],262144)?;if !stderr.is_empty(){return Err(bad());}
        let requests=lines(&requests)?;let replies=lines(&replies)?;if requests.len()!=replies.len(){return Err(bad());}
        let header=json_with_node_limit::<2048>(requests[0],65536,4096)?;
        let map=pool.maps.iter().find(|m|header["config_sha256"]==m.config_sha256).ok_or_else(bad)?;
        let profile=pool.angular_profile(map)?;if pool.vehicle_kind().label()!=kind{return Err(bad());}
        catalog.verify(&root,map)?;
        let keep=if mode=="pivot"{vec![3167]}else{vec![3166,3167]};
        let initial=if scope.all_alive(){Vec::new()}else{catalog.entries().iter().map(CatalogEntry::object_id).filter(|id|!keep.contains(id)).collect::<Vec<_>>()};
        let mut scene=Scene::new(&catalog,&initial)?;let generation=scope.generation(i);
        value_same(requests[0],&catalog::scene_request(map,&catalog,generation,0,&scene,true)?)?;
        let ready=catalog::response_with_profile(replies[0],map,&catalog,generation,0,None,&scene,Some(profile))?;
        if ready.angular_proof.as_ref().is_none_or(|f|!f.receipts.is_empty()){return Err(bad());}
        let input=if mode=="pivot"{Input{throttle:0,steer:1,brake:false,speed_percent:100}}else{Input{throttle:1,steer:0,brake:false,speed_percent:100}};
        let mut cursor=1;let mut fractures=0;let mut acks=0;let mut target_hull_frames=0;let mut target_outcomes=Vec::new();
        let mut target_angular_applied=0;
        for seq in 1..=120 {
            let request=requests.get(cursor).ok_or_else(bad)?;let reply=replies.get(cursor).ok_or_else(bad)?;
            value_same(request,&catalog::request_catalog(seq,input,&scene,&catalog)?)?;
            let state=catalog::response_with_profile(reply,map,&catalog,generation,seq,None,&scene,Some(profile))?;
            if scope.all_alive()&&state.object_contacts.iter().any(|c|c.object_id==3167&&c.kind=="hull"){target_hull_frames+=1;}
            let proof=state.angular_proof.ok_or_else(bad)?;total_frames+=1;cursor+=1;
            if !proof.receipts.is_empty(){
                let mut ids=scene.ids().to_vec();for (ri,r) in proof.receipts.iter().enumerate(){
                    if !scope.all_alive()&&!keep.contains(&r.object_id){return Err(bad());}
                    if scope.all_alive()&&r.object_id==3167{
                        let witness=proof.witnesses.iter().find(|w|w.substep==r.substep).ok_or_else(bad)?;
                        let prior=proof.receipts[..ri].iter().rev().find(|x|x.substep==r.substep)
                            .map_or(witness.post.motion.w,|x|x.solver_after.w);
                        let applied=r.mode==ram_proof::Mode::Angular&&r.solver_branch==Some(ram_proof::SolverBranch::Applied)
                            &&angular_changed(prior,r.solver_after.w);
                        if applied{target_angular_applied+=1;}
                        let mode=match r.mode{ram_proof::Mode::Normal=>"normal_linear",ram_proof::Mode::Total=>"total_linear",ram_proof::Mode::Angular=>"angular_corner"};
                        target_outcomes.push(serde_json::json!({"seq":seq,"substep":r.substep,"mode":mode,"applied_nonzero_angular":applied}));
                    }
                    ids.push(r.object_id);
                }
                ids.sort_unstable();let next=Scene::new(&catalog,&ids)?;
                value_same(requests.get(cursor).ok_or_else(bad)?,&catalog::scene_request(map,&catalog,generation,seq,&next,false)?)?;
                catalog::ack(replies.get(cursor).ok_or_else(bad)?,map,&catalog,generation,seq,&next)?;
                fractures+=proof.receipts.len();scene=next;cursor+=1;acks+=1;
            }
        }
        if cursor!=requests.len(){return Err(bad());}total_receipts+=fractures;total_acks+=acks;
        let mut row_report=serde_json::json!({"case":[kind,mode,repeat],"pool":binding["pools"][&pool_key],"raw":row["raw"],
            "config_sha256":map.config_sha256,"profile_sha256":profile.sha(),"generation":generation,
            "ready":1,"advances":120,"validated_receipts":fractures,"validated_acks":acks,"final_scene_sha256":scene.hash()});
        if scope.all_alive(){
            let target_pass=target_hull_frames>0&&(kind=="ms1"||(target_angular_applied==1&&target_outcomes.len()==1));
            targets_complete&=target_pass;
            row_report["target_observations"]=serde_json::json!({"actual_target_hull_frames":target_hull_frames,"target_outcomes":target_outcomes,
                "status":if target_pass{"PASS_TARGET_OBSERVED"}else{"TARGET_NOT_EXERCISED"}});
        }report.push(row_report);
    }
    let mut result=serde_json::json!({"status":"PASS_FULL_TYPED_FRAME_DECODE","binding_sha256":binding_sha,
        "capture_receipt":binding["capture_receipt"],"cases":report,"advances":total_frames,"receipts":total_receipts,"acks":total_acks,
        "workers_launched":0,"domain_both_worker_barrier":"NOT_RUN_BY_OFFLINE_DECODER","native_acceptance":"NOT_RUN"});
    if scope.all_alive(){result["scope"]="P05B_ANGULAR_ALLALIVE4".into();result["target_observation_gate"]=if targets_complete{"PASS"}else{"TARGET_NOT_EXERCISED"}.into();}
    Ok(result)
}

#[test]
#[ignore = "requires a root-pinned immutable actual capture and four exact source pools; offline only"]
fn angular_saved_capture_full_decoder(){
    let result=replay(CaptureScope::First8).expect("pinned actual capture must pass the full production decoder");
    save_result(&result);
}

#[test]
#[ignore = "requires root-pinned all-alive four-case capture and two source pools; offline only"]
fn angular_allalive_saved_capture_full_decoder(){
    let result=replay(CaptureScope::AllAlive4).expect("all-alive saved frames must pass full production proof");
    save_result(&result);
    assert_eq!(result["target_observation_gate"],"PASS","typed frames passed but required target was not exercised; receipt retained");
}

fn save_result(result:&Value){
    let output=PathBuf::from(std::env::var_os("WOT_ANGULAR_DECODE_OUT").expect("fresh output path"));
    let binding:Value=serde_json::from_slice(&fs::read(std::env::var_os("WOT_ANGULAR_DECODE_BINDING").unwrap()).unwrap()).unwrap();
    let root=Path::new(binding["local_root"].as_str().unwrap()).canonicalize().unwrap();
    let parent=owned(&root,output.parent().unwrap()).unwrap();assert!(output.is_absolute());
    assert_eq!(output.parent().unwrap().canonicalize().unwrap(),parent);assert!(!output.exists());
    let mut file=fs::OpenOptions::new().write(true).create_new(true).open(&output).unwrap();
    file.write_all(&serde_json::to_vec_pretty(&result).unwrap()).unwrap();file.write_all(b"\n").unwrap();
    println!("ANGULAR_SAVED_CAPTURE_PROOF {}",serde_json::to_string(&result).unwrap());
}

#[test]
fn angular_saved_capture_scopes_are_closed(){
    let first=serde_json::json!({"version":1,"local_root":"unused","capture_receipt":{},"pools":{"ms1_pivot":{},"is7_pivot":{},"ms1_chain":{},"is7_chain":{}}});
    let all=serde_json::json!({"version":2,"scope":"P05B_ANGULAR_ALLALIVE4","local_root":"unused","capture_receipt":{},"pools":{"ms1_pivot":{},"is7_pivot":{}}});
    assert!(CaptureScope::First8.binding(&first).is_ok());assert!(CaptureScope::AllAlive4.binding(&all).is_ok());
    assert!(CaptureScope::First8.binding(&all).is_err());assert!(CaptureScope::AllAlive4.binding(&first).is_err());
    let mut bad_scope=all.clone();bad_scope["scope"]="P05B_ANGULAR_FIRST8".into();assert!(CaptureScope::AllAlive4.binding(&bad_scope).is_err());
    let mut extra=all;extra["pools"]["is7_chain"]=serde_json::json!({});assert!(CaptureScope::AllAlive4.binding(&extra).is_err());
    assert_eq!(CaptureScope::First8.cases().len(),8);assert_eq!(CaptureScope::AllAlive4.cases().len(),4);
    assert_eq!(CaptureScope::First8.generation(0),19000);assert_eq!(CaptureScope::AllAlive4.generation(3),19103);
    assert!(!angular_changed([0.,0.,0.],[-0.,0.,0.]));
    assert!(angular_changed([0.,0.,0.],[f32::MIN_POSITIVE,0.,0.]));
}

// Separate fixed differential scope: retain First8/AllAlive4 byte contracts.
const NORMAL_CASES:[(&str,&str,&str);12]=[
    ("ms1","crate","14-reference"),("ms1","crate","15-repeat1"),("ms1","crate","15-repeat2"),
    ("ms1","clear_tree","14-reference"),("ms1","clear_tree","15-repeat1"),("ms1","clear_tree","15-repeat2"),
    ("is7","crate","14-reference"),("is7","crate","15-repeat1"),("is7","crate","15-repeat2"),
    ("is7","clear_tree","14-reference"),("is7","clear_tree","15-repeat1"),("is7","clear_tree","15-repeat2")];
fn normal_binding(binding:&Value)->io::Result<()> {
    fields(binding,&["version","scope","local_root","capture_receipt","catalogs","pools"])?;
    if uint(&binding["version"])?!=3||text(binding,"scope")?!="P05B_NORMAL_V8_DIFFERENTIAL12"{return Err(bad());}
    fields(&binding["catalogs"],&["14","15"])?;
    fields(&binding["pools"],&["ms1_crate_14","ms1_crate_15","ms1_clear_tree_14","ms1_clear_tree_15",
        "is7_crate_14","is7_crate_15","is7_clear_tree_14","is7_clear_tree_15"])?;Ok(())
}
fn normal_lines(raw:&[u8],limit:usize)->io::Result<Vec<&[u8]>> {
    if raw.is_empty()||!raw.ends_with(b"\n"){return Err(bad());}
    let rows=raw[..raw.len()-1].split(|b|*b==b'\n').collect::<Vec<_>>();
    if !(181..=361).contains(&rows.len())||rows.iter().any(|r|r.is_empty()||r.len()>limit){return Err(bad());}Ok(rows)
}
fn replay_normal()->io::Result<Value> {
    let binding_path=PathBuf::from(std::env::var_os("WOT_ANGULAR_DECODE_BINDING").ok_or_else(bad)?);
    non_reparse(&binding_path)?;let raw=read(&binding_path,65536)?;
    let binding_sha=std::env::var("WOT_ANGULAR_DECODE_BINDING_SHA256").map_err(|_|bad())?;hash_text(&binding_sha)?;
    if format!("{:x}",Sha256::digest(&raw))!=binding_sha{return Err(bad());}
    let binding=json(&raw,65536)?;normal_binding(&binding)?;
    let root=PathBuf::from(text(&binding,"local_root")?);non_reparse(&root)?;let root=root.canonicalize()?;owned(&root,&binding_path)?;
    let (_,receipt_raw)=pinned(&root,&binding["capture_receipt"],1024*1024)?;
    let receipt=json_with_node_limit::<2048>(&receipt_raw,1024*1024,8192)?;
    if receipt["status"]!="PASS_CAPTURE_PROTOCOL_GATES_PROOF_PENDING"||!receipt["post_pin_error"].is_null()||!receipt["outer_error"].is_null(){return Err(bad());}
    let (_,capture_raw)=pinned(&root,&receipt["binding"],65536)?;let capture=json(&capture_raw,65536)?;
    if capture["scope"]!="P05B_NORMAL_V8_DIFFERENTIAL12"||capture["root_authorized_execution"]!=true
        ||uint(&capture["max_workers"])?!=12||uint(&capture["max_advances"])?!=180{return Err(bad());}
    let (_,fixtures_raw)=pinned(&root,&capture["fixtures"],65536)?;
    let fixtures=json_with_node_limit::<2048>(&fixtures_raw,65536,8192)?;
    if fixtures["catalogs"]!=binding["catalogs"]{return Err(bad());}
    let results=receipt["results"].as_array().filter(|r|r.len()==12).ok_or_else(bad)?;
    let mut report=Vec::new();let mut total_frames=0;let mut total_receipts=0;let mut total_acks=0;
    for (i,(row,&(kind,target,label))) in results.iter().zip(NORMAL_CASES.iter()).enumerate(){
        if row["case"]!=serde_json::json!([kind,target,label])||uint(&row["frames"])?!=180
            ||row["status"]!="PASS_CAPTURE_PROTOCOL_GATES_PROOF_PENDING"||row["cleanup"]["exit_code"]!=0
            ||row["cleanup"]["faults"]!=serde_json::json!([])||row["cleanup"]["cleanup_errors"]!=serde_json::json!([])
            ||!row["error"].is_null(){return Err(bad());}
        let old=label=="14-reference";let build=if old{"14"}else{"15"};let expected_version=if old{7}else{8};
        let oid=if target=="crate"{3618}else{3680};let generation=19200+i as u32;
        let pool_key=format!("{kind}_{target}_{build}");
        let source=fixtures["cases"].as_array().ok_or_else(bad)?.iter().find(|s|s["kind"]==kind&&s["target"]==target).ok_or_else(bad)?;
        if source["pools"][build]!=binding["pools"][&pool_key]||uint(&source["object_id"])?!=oid{return Err(bad());}
        let (pool_path,_)=pinned(&root,&binding["pools"][&pool_key],65536)?;let pool=Pool::load(&root,&pool_path)?;pool.verify_assets()?;
        let (cat_path,_)=pinned(&root,&binding["catalogs"][build],1024*1024)?;
        let catalog=CatalogSpec::load(&root,&cat_path,text(&binding["catalogs"][build],"sha256")?)?;
        if catalog.version()!=expected_version||catalog.entries().len()!=1038{return Err(bad());}
        let entry=catalog.entries().iter().find(|e|e.object_id()==oid as u32).ok_or_else(bad)?;
        if entry.ram_response()!=Some("normal_linear")||entry.ram_energy_j()!=8000{return Err(bad());}
        let (_,requests)=pinned(&root,&row["raw"]["requests.jsonl"],32*1024*1024)?;
        let (_,replies)=pinned(&root,&row["raw"]["stdout.jsonl"],32*1024*1024)?;
        let (_,stderr)=pinned(&root,&row["raw"]["stderr.bin"],262144)?;if !stderr.is_empty(){return Err(bad());}
        let requests=normal_lines(&requests,catalog.line_limit())?;let replies=normal_lines(&replies,catalog.line_limit())?;
        if requests.len()!=replies.len(){return Err(bad());}
        let header=json_with_node_limit::<2048>(requests[0],catalog.line_limit(),4096)?;
        let map=pool.maps.iter().find(|m|m.asset=="05_prohorovka"&&header["config_sha256"]==m.config_sha256).ok_or_else(bad)?;
        if source["config"]["sha256"]!=map.config_sha256||pool.vehicle_kind().label()!=kind{return Err(bad());}
        let profile=pool.angular_profile(map)?;catalog.verify(&root,map)?;
        let initial=catalog.entries().iter().map(CatalogEntry::object_id).filter(|id|*id!=oid as u32).collect::<Vec<_>>();
        if initial.len()!=1037{return Err(bad());}let mut scene=Scene::new(&catalog,&initial)?;
        value_same(requests[0],&catalog::scene_request(map,&catalog,generation,0,&scene,true)?)?;
        let ready=catalog::response_with_profile(replies[0],map,&catalog,generation,0,None,&scene,Some(profile))?;
        if !ready.fractures.is_empty()||(!old&&ready.angular_proof.as_ref().is_none_or(|p|!p.receipts.is_empty())){return Err(bad());}
        let input=Input{throttle:1,steer:0,brake:false,speed_percent:100};let mut cursor=1;let mut fractures=0;let mut acks=0;
        for seq in 1..=180 {
            let request=requests.get(cursor).ok_or_else(bad)?;let reply=replies.get(cursor).ok_or_else(bad)?;
            value_same(request,&catalog::request_catalog(seq,input,&scene,&catalog)?)?;
            let state=catalog::response_with_profile(reply,map,&catalog,generation,seq,None,&scene,Some(profile))?;
            if !old {
                let proof=state.angular_proof.as_ref().ok_or_else(bad)?;
                if proof.receipts.iter().any(|r|r.mode!=ram_proof::Mode::Normal){return Err(bad());}
            }else if state.angular_proof.is_some(){return Err(bad());}
            total_frames+=1;cursor+=1;
            if !state.fractures.is_empty(){
                if fractures!=0||state.fractures.len()!=1{return Err(bad());}let r=&state.fractures[0];
                if r.object_id!=oid as u32||!state.object_contacts.iter().any(|c|c.object_id==r.object_id&&c.kind=="hull"&&c.substep==r.substep){return Err(bad());}
                let mut ids=scene.ids().to_vec();ids.push(r.object_id);ids.sort_unstable();let next=Scene::new(&catalog,&ids)?;
                value_same(requests.get(cursor).ok_or_else(bad)?,&catalog::scene_request(map,&catalog,generation,seq,&next,false)?)?;
                catalog::ack(replies.get(cursor).ok_or_else(bad)?,map,&catalog,generation,seq,&next)?;
                scene=next;cursor+=1;acks+=1;fractures+=1;
            }
        }
        if cursor!=requests.len()||fractures!=1||acks!=1||scene.ids().len()!=1038{return Err(bad());}
        total_receipts+=fractures;total_acks+=acks;
        report.push(serde_json::json!({"case":[kind,target,label],"pool":binding["pools"][&pool_key],"raw":row["raw"],
            "config_sha256":map.config_sha256,"profile_sha256":profile.sha(),"generation":generation,"catalog_version":catalog.version(),
            "ready":1,"advances":180,"validated_receipts":fractures,"validated_acks":acks,"final_scene_sha256":scene.hash()}));
    }
    Ok(serde_json::json!({"status":"PASS_FULL_TYPED_FRAME_DECODE","scope":"P05B_NORMAL_V8_DIFFERENTIAL12","binding_sha256":binding_sha,
        "capture_receipt":binding["capture_receipt"],"cases":report,"advances":total_frames,"receipts":total_receipts,"acks":total_acks,
        "legacy_cases":4,"angular_proof_cases":8,"workers_launched":0,"physical_parity_and_passage":"CAPTURE_RUNNER_GATES",
        "domain_both_worker_barrier":"NOT_RUN_BY_OFFLINE_DECODER","native_acceptance":"NOT_RUN"}))
}
#[test]
#[ignore = "requires root-pinned normal differential12 capture; offline production decoder only"]
fn normal_v8_saved_capture_full_decoder(){
    let result=replay_normal().expect("fixed normal differential frames must pass production decode");save_result(&result);
}
#[test]
fn normal_saved_capture_scope_is_closed(){
    let normal=serde_json::json!({"version":3,"scope":"P05B_NORMAL_V8_DIFFERENTIAL12","local_root":"unused","capture_receipt":{},
        "catalogs":{"14":{},"15":{}},"pools":{"ms1_crate_14":{},"ms1_crate_15":{},"ms1_clear_tree_14":{},"ms1_clear_tree_15":{},
            "is7_crate_14":{},"is7_crate_15":{},"is7_clear_tree_14":{},"is7_clear_tree_15":{}}});
    assert!(normal_binding(&normal).is_ok());assert!(CaptureScope::First8.binding(&normal).is_err());assert!(CaptureScope::AllAlive4.binding(&normal).is_err());
    let mut wrong=normal.clone();wrong["version"]=2.into();assert!(normal_binding(&wrong).is_err());
    let mut extra=normal.clone();extra["pools"]["is7_pivot"]=serde_json::json!({});assert!(normal_binding(&extra).is_err());
    let mut missing=normal;missing["catalogs"].as_object_mut().unwrap().remove("14");assert!(normal_binding(&missing).is_err());
    let short=b"{}\n".repeat(180);assert!(normal_lines(&short,32768).is_err());
    let minimum=b"{}\n".repeat(181);assert!(normal_lines(&minimum,32768).is_ok());assert!(lines(&minimum).is_ok());
    let long=b"{}\n".repeat(362);assert!(normal_lines(&long,65536).is_err());
    let mut capped=minimum.clone();capped.splice(0..2,vec![b'x';32769]);assert!(normal_lines(&capped,32768).is_err());assert!(normal_lines(&capped,65536).is_ok());
}
