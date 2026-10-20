//! Actual saved owner-scoped SQLite pending replies. Session/Window fixtures
//! below are explicitly authored transport state, not native/client proof.
use super::*;
fn fixture()->Value{let raw=include_bytes!("../../../../tests/fixtures/p08c-late-loss-two-owner-discovery-vectors.json");
    assert_eq!(format!("{:x}",Sha256::digest(raw)),"c2124ddb960630a86ff3e399993f8711214167d2f6cabd2c94452316141181fa");serde_json::from_slice(raw).unwrap()}
fn saved(index:usize)->(Query,Value){let f=fixture();let row=&f["pending_vectors"][index];let request=row["request"].clone();let body=canonical(&request).unwrap().into_bytes();
    let owner=Arc::new(identity091::Profile{account_id:request["account_id"].as_str().unwrap().into(),database_id:request["native_database_id"].as_i64().unwrap()as i32,
        name:"authored Account transport fixture".into(),fixture_dir:std::path::PathBuf::new()});
    let context=Context{session:7,key:[23;16],epoch:0,owner:owner.account_id.clone(),native:owner.database_id};
    (Query{context,owner,request,sha:format!("{:x}",Sha256::digest(&body)),body},row["response"].clone())}
fn session(q:&Query)->Session{let now=Instant::now();let mut s=Session::new(q.context.session,q.context.key,"127.0.0.1:29990".parse().unwrap(),now);
    s.active=true;s.account_ready=true;s.sync_mask=7;s.base_peer=Some("127.0.0.1:29991".parse().unwrap());s.identity=Some(q.owner.clone());
    s.shared=Some(super::super::Client::new(0));s}
fn stage(index:usize)->(Discovery,Session){let(q,v)=saved(index);let page=q.parse(&serde_json::to_vec(&v).unwrap()).unwrap();let s=session(&q);
    (Discovery{query:Some(q),page:Some(page),..Default::default()},s)}
#[test]fn p08c_late_pending_actual_sqlite_before_ack_and_after_ack_are_not_fabricated(){
    let(q,v)=saved(0);assert_eq!(q.request.as_object().unwrap().len(),7);let p=q.parse(&serde_json::to_vec(&v).unwrap()).unwrap();assert_eq!(p.rows.len(),1);
    assert_eq!(p.rows[0].arena,9007199254740993);assert_eq!(p.rows[0].vehicle,3329);assert_eq!(p.rows[0].own_team,1);assert_eq!(p.rows[0].winner,2);assert!(p.next.is_none());
    let(q,v)=saved(1);assert!(q.parse(&serde_json::to_vec(&v).unwrap()).unwrap().rows.is_empty());
}
#[test]fn p08c_late_pending_source_owner_cursor_hash_and_last_row_poison_rejected(){
    let(q,v)=saved(0);for field in["account_id","command_key","request_sha256","policy_sha256","after_arena_id"]{let mut poison=v.clone();poison[field]="forged".into();assert!(q.parse(&serde_json::to_vec(&poison).unwrap()).is_err(),"{field}");}
    for value in[json!("09007199254740993"),json!("0"),json!("9223372036854775808"),json!(9007199254740993u64)]{
        let mut poison=v.clone();poison["rows"][0]["arena_id"]=value;assert!(q.parse(&serde_json::to_vec(&poison).unwrap()).is_err());}
    let mut poison=v;poison["rows"][0]["vehicle_type_compact_id"]=65536.into();assert!(q.parse(&serde_json::to_vec(&poison).unwrap()).is_err());
}
#[test]fn p08c_late_pending_literal_lexical_cursor_fullpage_and_duplicate_rules(){
    let(q,mut v)=saved(0);let template=v["rows"][0].clone();v["rows"]=Value::Array(["10","100","101","102","103","104","105","11"].into_iter().map(|id|{let mut r=template.clone();r["arena_id"]=id.into();r}).collect());
    v["next_arena_id"]="11".into();let p=q.parse(&serde_json::to_vec(&v).unwrap()).unwrap();assert_eq!(p.rows.len(),8);assert_eq!(p.next,Some(11));
    let mut bad=v.clone();bad["next_arena_id"]="12".into();assert!(q.parse(&serde_json::to_vec(&bad).unwrap()).is_err());
    let mut bad=v.clone();bad["rows"][7]=bad["rows"][6].clone();assert!(q.parse(&serde_json::to_vec(&bad).unwrap()).is_err());
    let mut bad=v;bad["rows"].as_array_mut().unwrap().push(template);assert!(q.parse(&serde_json::to_vec(&bad).unwrap()).is_err());
}
#[test]fn p08c_late_pending_real_account_epoch_and_auth_key_fence_late_page(){
    let(mut d,mut s)=stage(0);s.battle_results.begin_account_epoch().unwrap();assert!(d.publish_page(std::slice::from_mut(&mut s),Instant::now(),1792080060).unwrap());
    assert_eq!(s.tx.len(),0);assert!(s.outbox.is_empty());assert!(d.query.is_none());assert!(d.states.is_empty());
    let(mut d,mut s)=stage(0);s.key[0]^=1;d.publish_page(std::slice::from_mut(&mut s),Instant::now(),1792080060).unwrap();assert_eq!(s.tx.len(),0);
    let(mut d,mut s)=stage(0);s.shared.as_mut().unwrap().phase=Phase::Returning;d.publish_page(std::slice::from_mut(&mut s),Instant::now(),1792080060).unwrap();assert_eq!(s.tx.len(),0);
}
#[test]fn p08c_late_pending_late_encode_failure_rolls_back_whole_native_page(){
    let(mut d,mut s)=stage(0);let first=d.page.as_ref().unwrap().rows[0].clone();let mut poison=first.clone();poison.arena+=1;poison.created_unix=1792080061;
    d.page.as_mut().unwrap().rows.push(poison);let before=s.tx.clone();
    assert!(d.publish_page(std::slice::from_mut(&mut s),Instant::now(),1792080060).is_err());assert_eq!(s.tx.len(),before.len());assert!(s.outbox.is_empty());
    assert!(d.states.values().all(|st|st.seen.is_empty()&&st.cursor.is_none()));assert!(d.page.is_some());
    d.page.as_mut().unwrap().rows.pop();d.publish_page(std::slice::from_mut(&mut s),Instant::now(),1792080060).unwrap();assert!(s.tx.len()>0);assert!(d.page.is_none());
}
#[test]fn p08c_late_pending_pressure_retains_page_no_false_offer_or_sql_ack(){
    let(mut d,mut s)=stage(0);let mut row=d.page.as_ref().unwrap().rows[0].clone();row.arena+=1;d.page.as_mut().unwrap().rows.push(row);
    s.outbox=std::iter::repeat_n(vec![19],127).collect();assert!(d.publish_page(std::slice::from_mut(&mut s),Instant::now(),1792080060).is_err());
    assert_eq!(s.outbox.len(),127);assert_eq!(s.tx.len(),0);assert!(s.battle_results.idle());assert!(d.states.values().all(|st|st.seen.is_empty()));
    s.outbox.clear();d.publish_page(std::slice::from_mut(&mut s),Instant::now(),1792080060).unwrap();assert_eq!(s.tx.len(),2);assert!(s.battle_results.idle());
}
#[test]fn p08c_late_pending_repeat_same_epoch_is_not_second_native_callback(){
    let(mut d,mut s)=stage(0);let context=d.query.as_ref().unwrap().context.clone();let(q,v)=saved(0);d.publish_page(std::slice::from_mut(&mut s),Instant::now(),1792080060).unwrap();let queued=s.tx.len();
    d.query=Some(q.clone());d.page=Some(q.parse(&serde_json::to_vec(&v).unwrap()).unwrap());d.publish_page(std::slice::from_mut(&mut s),Instant::now(),1792080060).unwrap();
    assert_eq!(s.tx.len(),queued);assert_eq!(d.states[&context].seen.len(),1);assert!(s.battle_results.idle());
}
#[test]fn p08c_late_pending_one_account_budget_cannot_hold_other_owner_page_forever(){
    let(mut d,mut s)=stage(0);let context=d.query.as_ref().unwrap().context.clone();
    d.states.entry(context.clone()).or_default().seen=(1..=128).collect();
    d.publish_page(std::slice::from_mut(&mut s),Instant::now(),1792080060).unwrap();
    assert!(d.states[&context].disabled);assert!(d.query.is_none());assert!(d.page.is_none());assert_eq!(s.tx.len(),0);assert!(s.battle_results.idle());
}
#[test]fn p08c_late_pending_read_worker_exit_barrier_does_not_block_udp_join(){
    let(tx,rx)=mpsc::channel();let(release,wait)=mpsc::sync_channel(0);let(sent,received)=mpsc::sync_channel(0);
    let handle=thread::spawn(move||{tx.send(Ok(Page{rows:Vec::new(),next:None,rejected:None})).unwrap();sent.send(()).unwrap();wait.recv().unwrap();});
    received.recv().unwrap();let mut job=Job{rx,handle};assert!(job.poll().is_none());release.send(()).unwrap();
    let deadline=Instant::now()+Duration::from_secs(2);while !job.handle.is_finished(){assert!(Instant::now()<deadline);thread::yield_now();}
    assert!(job.poll().unwrap().unwrap().rows.is_empty());job.handle.join().unwrap();
}
