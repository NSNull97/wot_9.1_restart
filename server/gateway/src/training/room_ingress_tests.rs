use super::*;
use crate::account091 as account;
fn parse(body:&[u8])->Result<Vec<Incoming<account::Request>>,Error>{requests(body,Gate::TrainingV1,account::requests,|r|Some(r.id))}
// Independent source-layout literals, NOT captured PRB native packets.
const CREATE:&[u8]=&[0x9a,12,0,1,0,0,0,0x58,2,0,0,1,2,b'h',b'i'];
const LIST:&[u8]=&[0x97,28,0,200,0,8,2,5,0,0,0,2,0,0,0,7,0,0,0,0,0,0,0,0,0,0,0,50,0,0,0];
const FILTER:&[u8]=&[0x96,20,0,200,0,9,2,2,0,0,0,0,0,0,0,1,0,0,0,3,b'A',b'B',b'C'];
const LEAVE:&[u8]=&[0x8e,20,0,221,0,0x91,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0];
const OWN404:&[u8]=&[0x8e,20,0,222,0,0x94,1,1,0,0x10,9,0,0,0,0,2,0,0,0,0,0,0,0];
const COMMENT:&[u8]=&[0x95,7,0,223,0,0x99,1,2,b'o',b'k'];
const SYNC:&[u8]=&[0x8e,20,0,225,0,100,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]; // measured old common shape
fn int3(id:i16,command:i16,a:i64,b:i32,c:i32)->Vec<u8>{
    let mut v=vec![0x8e,20,0];v.extend(id.to_le_bytes());v.extend(command.to_le_bytes());v.extend(a.to_le_bytes());v.extend(b.to_le_bytes());v.extend(c.to_le_bytes());v
}
fn only(body:&[u8])->Request{let rows=parse(body).unwrap();assert_eq!(rows.len(),1);let Incoming::Room(r)=rows.into_iter().next().unwrap()else{panic!()};r}

#[test]fn p10b_ingress_source_literals_create_list_filter_own404_and_comment_have_exact_types(){
    let r=only(CREATE);assert_eq!(r.reply,Reply::JoinedOrFailure);
    assert!(matches!(r.kind,Kind::Create{arena_type:1,seconds:600,opened:true,comment}if comment.as_bytes()==b"hi"));
    assert_eq!(only(LIST),Request{reply:Reply::ListStream,kind:Kind::List{prebattle_type:2,sort_key:7,idle:false,start:0,end:50}});
    assert!(matches!(only(FILTER),Request{reply:Reply::ListStream,kind:Kind::ListByCreator{prebattle_type:2,idle:true,mask}}if mask.as_bytes()==b"ABC"));
    assert_eq!(only(OWN404),Request{reply:Reply::Plain(222),kind:Kind::Assign{account_entity:0x09100001,roster:2}});
    assert!(matches!(only(COMMENT),Request{reply:Reply::Plain(223),kind:Kind::ChangeComment{comment}}if comment.as_bytes()==b"ok"));
    assert_eq!(only(LEAVE),Request{reply:Reply::Plain(221),kind:Kind::Leave});
}

#[test]fn p10b_ingress_required_int3_commands_keep_full_i64_and_distinct_reply_routes(){
    let huge=9_007_199_254_740_993i64;
    assert_eq!(only(&int3(202,400,huge,0,0)),Request{reply:Reply::JoinEvent,kind:Kind::Join{room:huge}});
    assert_eq!(only(&int3(201,523,huge,0,0)),Request{reply:Reply::RosterStream,kind:Kind::Preview{room:huge}});
    assert_eq!(only(&int3(221,402,huge,0,0)).kind,Kind::Ready{native_inventory:huge});
    assert_eq!(only(&int3(221,403,3,0,0)).kind,Kind::NotReady{state:3});
    assert_eq!(only(&int3(221,404,huge,18,0)).kind,Kind::Assign{account_entity:huge,roster:18});
    assert_eq!(only(&int3(221,405,0,0,0)).kind,Kind::SwapTeams);
    assert_eq!(only(&int3(221,406,4,0,0)).kind,Kind::ChangeArena{arena_type:4});
    assert_eq!(only(&int3(221,407,1800,0,0)).kind,Kind::ChangeDuration{seconds:1800});
    assert_eq!(only(&int3(221,408,1,0,0)).kind,Kind::ChangeOpened{opened:true});
    assert_eq!(only(&int3(221,410,0,0,0)).kind,Kind::ChangeVoip{mask:0});
    assert_eq!(only(&int3(221,411,2,1,0)).kind,Kind::TeamReady{team:2,force:true});
    assert_eq!(only(&int3(221,412,1,0,0)).kind,Kind::TeamNotReady{team:1});
    assert_eq!(only(&int3(32767,414,i64::MAX,0,0)),Request{reply:Reply::Plain(32767),kind:Kind::Kick{account_entity:i64::MAX}});
    // Signed values stay exact for semantic WRONG_ARGS/UNAVAILABLE handling.
    assert_eq!(only(&int3(221,406,i64::MIN,0,0)).kind,Kind::ChangeArena{arena_type:i64::MIN});
}

#[test]fn p10b_ingress_default_gate_delegates_old_whole_bundle_and_stays_closed_for_prb(){
    assert_eq!(Gate::default(),Gate::Disabled);
    assert_eq!(requests(SYNC,Gate::Disabled,account::requests,|r|Some(r.id)).unwrap(),vec![Incoming::Legacy(account::Request{id:225,command:100})]);
    for p in [CREATE,LIST,FILTER,LEAVE,OWN404,COMMENT]{assert!(requests(p,Gate::Disabled,account::requests,|r|Some(r.id)).is_err());}
    assert!(account::requests(OWN404).is_err());assert!(account::requests(CREATE).is_err());
}

#[test]fn p10b_ingress_enabled_mixed_bundle_preserves_record_order_and_legacy_global_validation(){
    let rows=parse(&[SYNC,OWN404,LEAVE].concat()).unwrap();
    assert!(matches!(rows[0],Incoming::Legacy(account::Request{id:225,command:100})));
    assert!(matches!(rows[1],Incoming::Room(Request{kind:Kind::Assign{..},..})));
    assert!(matches!(rows[2],Incoming::Room(Request{kind:Kind::Leave,..})));
    // Same legacy command in separate records must still fail in the REAL
    // old parser; parsing each legacy record individually would miss this.
    let mut duplicate=SYNC.to_vec();duplicate[3..5].copy_from_slice(&226i16.to_le_bytes());
    assert_eq!(parse(&[SYNC,OWN404,&duplicate].concat()).unwrap_err(),Error::Legacy);
    let mut collision=OWN404.to_vec();collision[3..5].copy_from_slice(&225i16.to_le_bytes());
    assert_eq!(parse(&[SYNC,&collision].concat()).unwrap_err(),Error::Duplicate);
    assert_eq!(parse(&[OWN404,OWN404].concat()).unwrap_err(),Error::Duplicate);
    assert_eq!(parse(&[LIST,FILTER].concat()).unwrap_err(),Error::Duplicate);
    assert!(parse(&[int3(202,400,7,0,0),int3(202,400,8,0,0)].concat()).is_ok()); // no-response202 is not a callback namespace
}

#[test]fn p10b_ingress_late_poison_wrong_methods_counts_reserved_ids_and_zero_args_reject_complete_bundle(){
    for p in [CREATE,LIST,FILTER,LEAVE,OWN404,COMMENT]{
        for end in 1..p.len(){assert!(parse(&[SYNC,&p[..end]].concat()).is_err(),"truncate {end}");}
        let mut poison=p.to_vec();poison.push(0);assert!(parse(&poison).is_err());
    }
    for id in [i16::MIN,-1,0,200,201,202,220]{assert_eq!(parse(&int3(id,401,0,0,0)).unwrap_err(),Error::Request);}
    for (id,cmd)in[(221,400),(202,523),(200,523)]{assert_eq!(parse(&int3(id,cmd,7,0,0)).unwrap_err(),Error::Request);}
    for (a,b,c)in[(1,0,0),(0,1,0),(0,0,1)]{assert_eq!(parse(&int3(221,401,a,b,c)).unwrap_err(),Error::Shape);}
    assert_eq!(parse(&int3(221,411,1,2,0)).unwrap_err(),Error::Shape);
    assert_eq!(parse(&int3(221,408,2,0,0)).unwrap_err(),Error::Shape);
    let mut wrong=OWN404.to_vec();wrong[0]=0x97;assert_eq!(parse(&wrong).unwrap_err(),Error::Method);
    let mut wrong=LIST.to_vec();wrong[7]=6;assert_eq!(parse(&wrong).unwrap_err(),Error::Shape);
    let mut wrong=LIST.to_vec();wrong[3]=201;assert_eq!(parse(&wrong).unwrap_err(),Error::Request);
    let mut wrong=CREATE.to_vec();wrong[11]=2;assert_eq!(parse(&wrong).unwrap_err(),Error::Shape);
}

#[test]fn p10b_ingress_short_strings_body_and_record_bounds_are_explicit_without_pickle_or_utf8_guess(){
    let mut text=vec![0x95,69,0,221,0,0x99,1,64];text.extend([0xff;64]);
    let Kind::ChangeComment{comment}=only(&text).kind else{panic!()};assert_eq!(comment.as_bytes(),[0xff;64]);
    let mut over=text.clone();over[1]=70;over[7]=65;over.push(0);assert_eq!(parse(&over).unwrap_err(),Error::String);
    let mut sentinel=COMMENT.to_vec();sentinel[7]=255;assert_eq!(parse(&sentinel).unwrap_err(),Error::String);
    assert_eq!(parse(&vec![0;513]).unwrap_err(),Error::Bound);
    let rows=(0..16).map(|n|int3(221+n,401,0,0,0)).collect::<Vec<_>>();let body=rows.concat();assert_eq!(parse(&body).unwrap().len(),16);
    let mut over=body;over.extend(int3(300,401,0,0,0));assert_eq!(parse(&over).unwrap_err(),Error::Bound);
    assert!(parse(&[]).unwrap().is_empty());
}

#[test]fn p10b_ingress_shim_refuses_bad_legacy_decoder_arity_before_returning_partial_rows(){
    let r=requests(&[SYNC,OWN404].concat(),Gate::TrainingV1,|_|Ok(Vec::<account::Request>::new()),|r|Some(r.id));
    assert_eq!(r.unwrap_err(),Error::LegacyArity);
}
