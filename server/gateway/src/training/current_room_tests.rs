use super::*;
fn lease(n:u8)->domain::AuthLease{domain::AuthLease{account:domain::Account([n;16]),generation:1}}
fn settings()->domain::Settings{domain::Settings{capacity:6,map:domain::QualifiedMap::Karelia,seconds:600,opened:true,comment:String::new()}}
fn setup(creator:u8)->(domain::Registry,domain::RoomKey){
    let mut r=domain::Registry::default();for n in 1..=3{r.bind_authenticated(lease(n),format!("Player{n}"),0).unwrap();}
    let e=r.command(lease(creator),domain::Command::Create(settings()),0).unwrap();
    let domain::Event::Created(key)=e[0]else{panic!()};(r,key)
}
fn book(r:&domain::Registry,key:domain::RoomKey,who:u8)->aliases::Book{
    let mut b=aliases::Book::new(adapter::canonical(lease(who))).unwrap();refresh(r,key,&mut b);b
}
fn refresh(r:&domain::Registry,key:domain::RoomKey,b:&mut aliases::Book)->Vec<aliases::Binding>{
    let members=r.room(key).unwrap().members().map(|m|{let(l,j)=r.member_context(key,m.account()).unwrap();
        aliases::Membership{canonical:adapter::canonical(l),join_generation:j}}).collect::<Vec<_>>();
    b.stage_view(key.0,&members).unwrap()
}
fn reference(who:u8)->domain::WriterReadyRef{
    // Explicit synthetic shape/binding fixture. Does NOT prove owned readiness.
    domain::WriterReadyRef::from_verified_writer(lease(who).account,format!("fixture-owned-{who}"),13,[who;32]).unwrap()
}
fn ready(r:&mut domain::Registry,who:u8){let context=r.selection_context(lease(who)).unwrap();
    r.command(lease(who),domain::Command::Ready{context,selection:reference(who)},0).unwrap();}
fn channel()->Channel{Channel{session:7,generation:11}}
fn profile()->ProfileStamp{ProfileStamp{revision:13,source_binding:[17;32]}}

#[test]
fn own404_after_room_reuse_is_explicitly_current_room_and_invalidates_ready_without_authority_escalation(){
    let(mut r,old)=setup(1);let mut b=book(&r,old,1);
    current(&mut r,&b,lease(1),Action::Leave,0).unwrap();b.leave_room();assert!(r.room(old).is_none());
    let e=r.command(lease(1),domain::Command::Create(settings()),0).unwrap();let domain::Event::Created(new)=e[0]else{panic!()};
    assert_ne!(old,new);refresh(&r,new,&mut b);ready(&mut r,1);
    current(&mut r,&b,lease(1),Action::TeamReady{side:domain::Side::One,ready:true,force:false},0).unwrap();
    assert_eq!(r.room(new).unwrap().team_ready(),[true,false]);
    // A fresh authenticated native404 contains no semantic origin. The server
    // policy uses the current room even if an old UI context motivated it.
    let events=current(&mut r,&b,lease(1),Action::Assign{target_alias:aliases::OWN_ENTITY_ID,
        roster:domain::Roster::assigned(domain::Side::Two)},0).unwrap();
    let room=r.room(new).unwrap();let own=room.members().find(|m|m.account()==lease(1).account).unwrap();
    assert_eq!(own.roster(),domain::Roster::assigned(domain::Side::Two));assert!(own.ready().is_none());
    assert_eq!(room.team_ready(),[false,false]);assert!(events.contains(&domain::Event::RosterChanged{room:new,account:lease(1).account}));
    assert_eq!(r.claim(lease(1).account),Some(domain::Claim::Room(new)));
}

#[test]
fn current_room_fixed_own_id_does_not_grant_noncreator_creator_permissions_or_other_identity(){
    let(mut r,k)=setup(2);r.command(lease(1),domain::Command::Join(k),0).unwrap();let b=book(&r,k,1);
    for action in [Action::Assign{target_alias:aliases::OWN_ENTITY_ID,roster:domain::Roster::assigned(domain::Side::Two)},
        Action::SwapTeams,Action::UpdateSettings(settings()),Action::TeamReady{side:domain::Side::One,ready:true,force:true}]{
        let before=r.clone();assert_eq!(current(&mut r,&b,lease(1),action,0).unwrap_err(),Error::Domain(domain::Error::NotCreator));assert_eq!(r,before);
    }
    let wrong=book(&r,k,2);let before=r.clone();
    assert_eq!(current(&mut r,&wrong,lease(1),Action::NotReady,0).unwrap_err(),Error::Identity);assert_eq!(r,before);
}

#[test]
fn current_room_peer_alias_tombstones_still_reject_old404_and414_after_replacement(){
    let(mut r,k)=setup(1);r.command(lease(2),domain::Command::Join(k),0).unwrap();let mut b=book(&r,k,1);
    let old=refresh(&r,k,&mut b).iter().find(|x|x.member.canonical==adapter::canonical(lease(2))).unwrap().alias;
    r.command(lease(2),domain::Command::Leave,0).unwrap();r.command(lease(3),domain::Command::Join(k),0).unwrap();
    let new=refresh(&r,k,&mut b).iter().find(|x|x.member.canonical==adapter::canonical(lease(3))).unwrap().alias;assert!(new>old);
    for action in [Action::Assign{target_alias:old,roster:domain::Roster::assigned(domain::Side::Two)},Action::Kick{target_alias:old}]{
        let before=r.clone();assert_eq!(current(&mut r,&b,lease(1),action,0).unwrap_err(),Error::Alias(aliases::Error::StaleAlias));assert_eq!(r,before);
    }
    current(&mut r,&b,lease(1),Action::Assign{target_alias:new,roster:domain::Roster::assigned(domain::Side::Two)},0).unwrap();
}

#[test]
fn async_ready_origin_cannot_be_reinterpreted_after_leave_rejoin_revision_channel_or_source_change(){
    let(mut r,k)=setup(2);r.command(lease(1),domain::Command::Join(k),0).unwrap();
    let job=ReadyOrigin::capture(&r,lease(1),channel(),profile(),"fixture-owned-1".into(),221).unwrap();assert_eq!(job.request(),221);
    for poison in 0..6 {
        let(mut staged,mut who,mut c,mut p,mut value)=(r.clone(),lease(1),channel(),profile(),reference(1));
        match poison{
            0=>{staged.command(who,domain::Command::Leave,0).unwrap();staged.command(who,domain::Command::Join(k),0).unwrap();},
            1=>c.generation+=1,2=>p.source_binding[0]^=1,3=>p.revision+=1,
            4=>who.generation+=1,_=>value=reference(2),
        }
        let before=staged.clone();assert_eq!(job.complete(&mut staged,who,c,p,value,0).unwrap_err(),Error::StaleJob);assert_eq!(staged,before);
    }
    // A room setting mutation invalidates a query even with unchanged own ID.
    r.command(lease(2),domain::Command::UpdateSettings(settings()),0).unwrap();let before=r.clone();
    assert_eq!(job.complete(&mut r,lease(1),channel(),profile(),reference(1),0).unwrap_err(),Error::StaleJob);assert_eq!(r,before);
}

#[test]
fn async_ready_origin_commits_only_once_for_exact_current_origin_and_owner(){
    let(mut r,k)=setup(1);let job=ReadyOrigin::capture(&r,lease(1),channel(),profile(),"fixture-owned-1".into(),222).unwrap();
    job.complete(&mut r,lease(1),channel(),profile(),reference(1),0).unwrap();
    assert_eq!(r.room(k).unwrap().members().next().unwrap().ready(),Some(&reference(1)));
    let before=r.clone();assert_eq!(job.complete(&mut r,lease(1),channel(),profile(),reference(1),0).unwrap_err(),Error::StaleJob);assert_eq!(r,before);
}

#[test]
fn current_room_commands_cannot_free_preparing_claims_or_start_a_second_room(){
    let(mut r,k)=setup(1);r.command(lease(2),domain::Command::Join(k),0).unwrap();
    r.command(lease(1),domain::Command::Assign{target:lease(2).account,roster:domain::Roster::assigned(domain::Side::Two)},0).unwrap();
    let b=book(&r,k,1);ready(&mut r,1);ready(&mut r,2);
    for side in [domain::Side::One,domain::Side::Two]{current(&mut r,&b,lease(1),Action::TeamReady{side,ready:true,force:false},0).unwrap();}
    let snapshot=r.room(k).unwrap().preparing().unwrap().clone();let before=r.clone();
    assert_eq!(current(&mut r,&b,lease(1),Action::Assign{target_alias:aliases::OWN_ENTITY_ID,roster:domain::Roster::bench(domain::Side::One)},0).unwrap_err(),Error::Domain(domain::Error::LaunchPending));assert_eq!(r,before);
    let events=current(&mut r,&b,lease(1),Action::Leave,0).unwrap();assert!(events.contains(&domain::Event::AbortRequested{room:k,ticket:snapshot.ticket()}));
    assert_eq!(r.claim(lease(1).account),Some(domain::Claim::Room(k)));assert_eq!(r.claim(lease(2).account),Some(domain::Claim::Room(k)));
    assert_eq!(r.room(k).unwrap().preparing(),Some(&snapshot));assert!(r.room(k).unwrap().abort_requested());
    assert_eq!(r.command(lease(1),domain::Command::Create(settings()),0).unwrap_err(),domain::Error::AlreadyClaimed);
}
