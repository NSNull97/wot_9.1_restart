use super::*;
fn lease(n:u8)->domain::AuthLease{domain::AuthLease{account:domain::Account([n;16]),generation:1}}
fn setup(n:u8)->(domain::Registry,domain::RoomKey,BTreeMap<domain::Account,NativeFacts>){
    let mut reg=domain::Registry::default();let mut facts=BTreeMap::new();for i in 1..=n{reg.bind_authenticated(lease(i),format!("Player{i}"),0).unwrap();
        facts.insert(lease(i).account,NativeFacts{database_id:i as i32,selected:None,descriptor:Vec::new(),igr_type:0,clan_database_id:0,clan_abbrev:String::new()});}
    let events=reg.command(lease(1),domain::Command::Create(domain::Settings{capacity:6,map:domain::QualifiedMap::Karelia,seconds:600,opened:true,comment:String::new()}),0).unwrap();
    let key=match events[0]{domain::Event::Created(k)=>k,_=>panic!()};for i in 2..=n{reg.command(lease(i),domain::Command::Join(key),0).unwrap();}(reg,key,facts)
}
fn aliases(reg:&domain::Registry,key:domain::RoomKey,book:&mut aliases::Book)->Vec<aliases::Binding>{book.stage_view(key.0,&current_members(reg,key).unwrap()).unwrap()}
#[test]fn recipient_projection_two_to_six_always_places_actual_own_account_id_in_first_roster(){
    for n in 2..=6{let(reg,key,facts)=setup(n);for i in 1..=n{let mut book=aliases::Book::new(canonical(lease(i))).unwrap();let mut out=VecDeque::new();
        stage_initialization(&reg,&mut book,lease(i),17,&facts,1000.,&mut out).unwrap();assert_eq!(out.len(),21+n as usize);
        let own=&out[21];assert_eq!(own[3],1);let raw=&own[5..];assert_eq!(&raw[..6],b"\x80\x02]((J");assert_eq!(&raw[6..10],&aliases::OWN_ENTITY_ID.to_le_bytes());
        let bindings=aliases(&reg,key,&mut book);assert_eq!(bindings.iter().find(|b|b.member.canonical==canonical(lease(i))).unwrap().alias,aliases::OWN_ENTITY_ID);
        assert_eq!(bindings.iter().map(|b|b.alias).collect::<std::collections::BTreeSet<_>>().len(),usize::from(n));
    }}
}
#[test]fn late_kick_after_peer_replacement_never_hits_new_player_and_creator_checks_remain_real(){
    let(mut reg,key,_)=setup(3);reg.command(lease(3),domain::Command::Leave,0).unwrap();let mut book=aliases::Book::new(canonical(lease(1))).unwrap();
    let bindings=aliases(&reg,key,&mut book);let old=bindings.iter().find(|b|b.member.canonical==canonical(lease(2))).unwrap().alias;
    reg.command(lease(2),domain::Command::Leave,0).unwrap();reg.command(lease(3),domain::Command::Join(key),0).unwrap();let before=reg.clone();
    assert_eq!(target_command(&mut reg,&book,lease(1),old,TargetAction::Kick,0).unwrap_err(),Error::Alias(aliases::Error::StaleAlias));assert_eq!(reg,before);
    let bindings=aliases(&reg,key,&mut book);let new=bindings.iter().find(|b|b.member.canonical==canonical(lease(3))).unwrap().alias;assert!(new>old);
    assert_eq!(target_command(&mut reg,&book,lease(1),old,TargetAction::Kick,0).unwrap_err(),Error::Alias(aliases::Error::StaleAlias));assert_eq!(reg,before);
    let mut other=aliases::Book::new(canonical(lease(3))).unwrap();aliases(&reg,key,&mut other);
    assert_eq!(target_command(&mut reg,&other,lease(3),aliases::OWN_ENTITY_ID+1,TargetAction::Kick,0).unwrap_err(),Error::Domain(domain::Error::NotCreator));assert_eq!(reg,before);
    target_command(&mut reg,&book,lease(1),new,TargetAction::Kick,0).unwrap();assert!(reg.claim(lease(3).account).is_none());
}
#[test]fn same_peer_leave_rejoin_between_publications_gets_new_alias_from_real_domain_membership_nonce(){
    let(mut reg,key,_)=setup(2);let mut book=aliases::Book::new(canonical(lease(1))).unwrap();let old=aliases(&reg,key,&mut book)[1].alias;
    reg.command(lease(2),domain::Command::Leave,0).unwrap();reg.command(lease(2),domain::Command::Join(key),0).unwrap();
    let before=reg.clone();assert_eq!(target_command(&mut reg,&book,lease(1),old,TargetAction::Assign(domain::Roster::assigned(domain::Side::Two)),0).unwrap_err(),Error::Alias(aliases::Error::StaleAlias));assert_eq!(reg,before);
    let new=aliases(&reg,key,&mut book)[1].alias;assert!(new>old);
    target_command(&mut reg,&book,lease(1),new,TargetAction::Assign(domain::Roster::assigned(domain::Side::Two)),0).unwrap();
    assert_eq!(reg.room(key).unwrap().members().find(|m|m.account()==lease(2).account).unwrap().roster(),domain::Roster::assigned(domain::Side::Two));
    assert_eq!(target_command(&mut reg,&book,lease(1),aliases::OWN_ENTITY_ID,TargetAction::Assign(domain::Roster::assigned(domain::Side::Two)),0).unwrap_err(),Error::Alias(aliases::Error::SelfTargetUnsupported));
}
#[test]fn late_invalid_facts_or_full_native_queue_roll_back_alias_allocation_and_complete_initialization(){
    let(reg,_key,mut facts)=setup(6);let mut book=aliases::Book::new(canonical(lease(1))).unwrap();let mut out=VecDeque::from([vec![1;3]]);
    facts.get_mut(&lease(6).account).unwrap().database_id=1;let before=book.clone();let queue=out.clone();
    assert!(matches!(stage_initialization(&reg,&mut book,lease(1),17,&facts,1000.,&mut out),Err(Error::Wire(wire::Error::Duplicate))));assert_eq!(book,before);assert_eq!(out,queue);
    facts.get_mut(&lease(6).account).unwrap().database_id=6;out.extend((0..101).map(|_|vec![1]));let queue=out.clone();
    assert_eq!(stage_initialization(&reg,&mut book,lease(1),17,&facts,1000.,&mut out).unwrap_err(),Error::Queue);assert_eq!(book,before);assert_eq!(out,queue);
}
