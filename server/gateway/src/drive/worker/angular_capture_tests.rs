//! Offline only: decode immutable raw captures with the real pool, parser and
//! complete physical proof validator. This test never starts a worker process.
use super::*;

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
fn replay()->io::Result<Value>{
    let binding_path=PathBuf::from(std::env::var_os("WOT_ANGULAR_DECODE_BINDING").ok_or_else(bad)?);
    non_reparse(&binding_path)?;let raw=read(&binding_path,65536)?;
    let binding_sha=std::env::var("WOT_ANGULAR_DECODE_BINDING_SHA256").map_err(|_|bad())?;hash_text(&binding_sha)?;
    if format!("{:x}",Sha256::digest(&raw))!=binding_sha{return Err(bad());}
    let binding=json(&raw,65536)?;fields(&binding,&["version","local_root","capture_receipt","pools"])?;
    if uint(&binding["version"])?!=1{return Err(bad());}
    let root=PathBuf::from(text(&binding,"local_root")?);non_reparse(&root)?;let root=root.canonicalize()?;
    owned(&root,&binding_path)?;
    fields(&binding["pools"],&["ms1_pivot","ms1_chain","is7_pivot","is7_chain"])?;
    let (_,receipt_raw)=pinned(&root,&binding["capture_receipt"],1024*1024)?;
    let receipt=json_with_node_limit::<2048>(&receipt_raw,1024*1024,4096)?;
    let (_,capture_binding_raw)=pinned(&root,&receipt["binding"],1024*1024)?;
    let capture_binding=json_with_node_limit::<2048>(&capture_binding_raw,1024*1024,4096)?;
    let (catalog_path,_)=pinned(&root,&capture_binding["catalog"],1024*1024)?;
    let catalog=CatalogSpec::load(&root,&catalog_path,text(&capture_binding["catalog"],"sha256")?)?;
    if catalog.version()!=8{return Err(bad());}
    let cases=[("is7","pivot",1),("is7","pivot",2),("ms1","pivot",1),("ms1","pivot",2),
        ("ms1","chain",1),("ms1","chain",2),("is7","chain",1),("is7","chain",2)];
    let results=receipt["results"].as_array().filter(|a|a.len()==cases.len()).ok_or_else(bad)?;
    let mut report=Vec::new();let mut total_frames=0;let mut total_receipts=0;let mut total_acks=0;
    for (i,(row,(kind,mode,repeat))) in results.iter().zip(cases).enumerate(){
        if row["case"]!=serde_json::json!([kind,mode,repeat]){return Err(bad());}
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
        let initial=catalog.entries().iter().map(CatalogEntry::object_id).filter(|id|!keep.contains(id)).collect::<Vec<_>>();
        let mut scene=Scene::new(&catalog,&initial)?;let generation=19000+i as u32;
        value_same(requests[0],&catalog::scene_request(map,&catalog,generation,0,&scene,true)?)?;
        let ready=catalog::response_with_profile(replies[0],map,&catalog,generation,0,None,&scene,Some(profile))?;
        if ready.angular_proof.as_ref().is_none_or(|f|!f.receipts.is_empty()){return Err(bad());}
        let input=if mode=="pivot"{Input{throttle:0,steer:1,brake:false}}else{Input{throttle:1,steer:0,brake:false}};
        let mut cursor=1;let mut fractures=0;let mut acks=0;
        for seq in 1..=120 {
            let request=requests.get(cursor).ok_or_else(bad)?;let reply=replies.get(cursor).ok_or_else(bad)?;
            value_same(request,&catalog::request_catalog(seq,input,&scene,&catalog)?)?;
            let state=catalog::response_with_profile(reply,map,&catalog,generation,seq,None,&scene,Some(profile))?;
            let proof=state.angular_proof.ok_or_else(bad)?;total_frames+=1;cursor+=1;
            if !proof.receipts.is_empty(){
                let mut ids=scene.ids().to_vec();for r in &proof.receipts{if !keep.contains(&r.object_id){return Err(bad());}ids.push(r.object_id);}
                ids.sort_unstable();let next=Scene::new(&catalog,&ids)?;
                value_same(requests.get(cursor).ok_or_else(bad)?,&catalog::scene_request(map,&catalog,generation,seq,&next,false)?)?;
                catalog::ack(replies.get(cursor).ok_or_else(bad)?,map,&catalog,generation,seq,&next)?;
                fractures+=proof.receipts.len();scene=next;cursor+=1;acks+=1;
            }
        }
        if cursor!=requests.len(){return Err(bad());}total_receipts+=fractures;total_acks+=acks;
        report.push(serde_json::json!({"case":[kind,mode,repeat],"pool":binding["pools"][&pool_key],"raw":row["raw"],
            "config_sha256":map.config_sha256,"profile_sha256":profile.sha(),"generation":generation,
            "ready":1,"advances":120,"validated_receipts":fractures,"validated_acks":acks,"final_scene_sha256":scene.hash()}));
    }
    Ok(serde_json::json!({"status":"PASS_FULL_TYPED_FRAME_DECODE","binding_sha256":binding_sha,
        "capture_receipt":binding["capture_receipt"],"cases":report,"advances":total_frames,"receipts":total_receipts,"acks":total_acks,
        "workers_launched":0,"domain_both_worker_barrier":"NOT_RUN_BY_OFFLINE_DECODER","native_acceptance":"NOT_RUN"}))
}

#[test]
#[ignore = "requires a root-pinned immutable actual capture and four exact source pools; offline only"]
fn angular_saved_capture_full_decoder(){
    let result=replay().expect("pinned actual capture must pass the full production decoder");
    let output=PathBuf::from(std::env::var_os("WOT_ANGULAR_DECODE_OUT").expect("fresh output path"));
    let binding:Value=serde_json::from_slice(&fs::read(std::env::var_os("WOT_ANGULAR_DECODE_BINDING").unwrap()).unwrap()).unwrap();
    let root=Path::new(binding["local_root"].as_str().unwrap()).canonicalize().unwrap();
    let parent=owned(&root,output.parent().unwrap()).unwrap();assert!(output.is_absolute());
    assert_eq!(output.parent().unwrap().canonicalize().unwrap(),parent);assert!(!output.exists());
    let mut file=fs::OpenOptions::new().write(true).create_new(true).open(&output).unwrap();
    file.write_all(&serde_json::to_vec_pretty(&result).unwrap()).unwrap();file.write_all(b"\n").unwrap();
    println!("ANGULAR_SAVED_CAPTURE_PROOF {}",serde_json::to_string(&result).unwrap());
}
