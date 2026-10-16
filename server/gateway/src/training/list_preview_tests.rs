use super::*;
fn canonical(n:u8)->aliases::Canonical{aliases::Canonical{account:[n;16],auth_generation:1}}
fn member(n:u8)->PreviewMember{PreviewMember{canonical:canonical(n),membership:u64::from(n),row:wire::Member{
    entity_id:999,database_id:i32::from(n),name:format!("Player{n}"),roster:if n%2==1{1}else{2},state:wire::PlayerState::NotReady,
    joined_seconds:0.,descriptor:Vec::new(),igr_type:0,clan_database_id:0,clan_abbrev:String::new()}}}
fn preview(n:u8)->Preview{Preview{room_key:21,native_room_id:17,revision:1,members:(1..=n).map(member).collect()}}
fn listing()->Listing{Listing{total:1,rows:vec![ListRow{native_room_id:17,created_seconds:0.,arena_type:1,creator:"One".into(),creator_database_id:7,
    players:1,opened:true,comment:String::new(),creator_clan_abbrev:String::new(),creator_igr_type:0}]}}

#[test]fn p10b_list_preview_literal_empty_and_one_room_have_source_tuple_keys_not_custom_schema(){
    assert_eq!(list_raw(&Listing{total:0,rows:Vec::new()}).unwrap(),b"\x80\x02(K\x02K\x00](et.");
    let expected=b"\x80\x02(K\x02K\x01]((G\x00\x00\x00\x00\x00\x00\x00\x00K\x11}(K\x02\x88K\x05K\x01K\x06X\x03\x00\x00\x00OneK\x09X\x00\x00\x00\x00K\x0bK\x01K\x0fU\x00K\x11K\x00K\x12K\x07utet.";
    assert_eq!(list_raw(&listing()).unwrap(),expected);
}

#[test]fn p10b_list_preview_exact_ten_field_own_roster_literal_uses_actual_fixed_account_id(){
    let mut v=preview(1);let m=&mut v.members[0];m.row.name="One".into();m.row.database_id=7;
    let mut b=PreviewBook::new(canonical(1)).unwrap();
    let expected=b"\x80\x02(K\x11]((J\x01\x00\x10\x09X\x03\x00\x00\x00OneK\x07K\x01K\x01G\x00\x00\x00\x00\x00\x00\x00\x00U\x00K\x00K\x00U\x00tet.";
    assert_eq!(preview_raw(&mut b,&v).unwrap(),expected);assert_eq!(b.allocated(),0);
}

#[test]fn p10b_list_preview_nonmember_never_gets_fake_own_row_and_preview_aliases_cannot_target_room_peers(){
    for n in 1..=6{
        let v=preview(n);let mut b=PreviewBook::new(canonical(9)).unwrap();let raw=preview_raw(&mut b,&v).unwrap();assert_eq!(b.allocated(),usize::from(n));
        let own=[b'J',1,0,0x10,9];assert!(!raw.windows(own.len()).any(|x|x==own));
        assert!(b.entries.iter().all(|e|e.alias>=PREVIEW_ALIAS_START&&e.alias>aliases::OWN_ENTITY_ID+aliases::MAX_ALIASES as u32));
        let mut active=aliases::Book::new(canonical(9)).unwrap();let current=[aliases::Membership{canonical:canonical(9),join_generation:10},aliases::Membership{canonical:canonical(1),join_generation:1}];
        active.stage_view(21,&current).unwrap();for e in &b.entries{assert_eq!(active.resolve_peer(21,e.alias,&current).unwrap_err(),aliases::Error::StaleAlias);}
        assert_eq!(preview_raw(&mut b,&v).unwrap(),raw);assert_eq!(b.allocated(),usize::from(n));
    }
}

#[test]fn p10b_list_preview_aliases_never_reuse_after_leave_rejoin_room_or_auth_generation_changes(){
    let mut b=PreviewBook::new(canonical(9)).unwrap();let mut v=preview(1);
    preview_raw(&mut b,&v).unwrap();let first=b.entries[0].alias;
    v.members[0].membership+=100;v.revision+=1;preview_raw(&mut b,&v).unwrap();assert!(b.entries[1].alias>first);
    v.room_key+=1;preview_raw(&mut b,&v).unwrap();assert!(b.entries[2].alias>b.entries[1].alias);
    v.members[0].canonical.auth_generation+=1;v.revision+=1;preview_raw(&mut b,&v).unwrap();assert!(b.entries[3].alias>b.entries[2].alias);
    v.members[0].canonical.auth_generation=1;v.members[0].membership=1;v.room_key=21;v.revision=1;
    let old=b.clone();assert!(preview_raw(&mut b,&v).is_err());assert_eq!(b,old); // old room revision cannot resurrect its retired alias
    v.revision=10;preview_raw(&mut b,&v).unwrap();assert_eq!(b.allocated(),5);assert!(b.entries[4].alias>b.entries[3].alias);
}

#[test]fn p10b_list_preview_own_only_room_context_history_is_bounded_and_native_id_cannot_rebind(){
    let mut b=PreviewBook::new(canonical(1)).unwrap();let mut v=preview(1);
    for room in 1..=MAX_PREVIEW_ROOMS{v.room_key=room as u64;preview_raw(&mut b,&v).unwrap();}
    assert_eq!(b.allocated(),0);let old=b.clone();v.room_key=9999;assert!(preview_raw(&mut b,&v).is_err());assert_eq!(b,old);
    v.room_key=1;v.native_room_id=18;assert!(preview_raw(&mut b,&v).is_err());assert_eq!(b,old);
}

#[test]fn p10b_list_preview_late_bad_member_duplicate_foreign_self_and_alias_exhaustion_are_atomic(){
    for poison in 0..6{
        let mut b=PreviewBook::new(canonical(1)).unwrap();let mut v=preview(6);match poison{
            0=>v.members[5].row.database_id=1,1=>v.members[5].canonical=canonical(1),2=>v.members[5].membership=0,
            3=>v.members[5].row.state=wire::PlayerState::Ready,4=>v.members[0].canonical.auth_generation+=1,
            _=>v.members[5].row.name="bad\nname".into(),
        }let old=b.clone();assert!(preview_stream(&mut b,&v).is_err());assert_eq!(b,old);
    }
    let mut b=PreviewBook::new(canonical(9)).unwrap();let mut v=preview(1);
    for membership in 1..=MAX_PREVIEW_ALIASES{v.members[0].membership=membership as u64;v.revision=membership as u64;preview_raw(&mut b,&v).unwrap();}
    let old=b.clone();v.members[0].membership=9999;v.revision=9999;assert!(preview_raw(&mut b,&v).is_err());assert_eq!(b,old);
}

#[test]fn p10b_list_preview_bounds_cover_real_count_text_source_maps_and_stream_body_limits(){
    for poison in 0..9{let mut v=listing();match poison{
        0=>v.rows[0].arena_type=999,1=>v.rows[0].players=7,2=>v.rows[0].created_seconds=f64::NAN,
        3=>v.rows[0].creator_igr_type=3,4=>v.rows[0].creator="Я".repeat(25),5=>v.rows[0].comment="x".repeat(65),
        6=>v.rows[0].creator_database_id=0,7=>v.rows.push(v.rows[0].clone()),_=>v.total=0,
    }assert!(list_stream(&v).is_err(),"poison {poison}");}
    let mut v=listing();v.total=50;v.rows=(1..=50).map(|n|{let mut r=v.rows[0].clone();r.native_room_id=n;r.creator="Я".repeat(24);r.comment="x".repeat(64);r.creator_clan_abbrev="ABCDEFGH".into();r}).collect();
    let raw=list_raw(&v).unwrap();assert!(raw.len()<=MAX_RAW);let bodies=list_stream(&v).unwrap();assert!(bodies.len()>1);assert!(bodies.iter().all(|b|b.len()<=512));
    v.rows.push(v.rows[0].clone());assert!(list_raw(&v).is_err());
}

#[test]fn p10b_list_preview_export_canonical_own_streams_for_independent_zlib_pickle_checks(){
    let export=std::env::var_os("P10B_LIST_EXPORT");
    let temporary=export.is_none();
    let out=export.map(std::path::PathBuf::from).unwrap_or_else(||std::env::temp_dir().join(format!("wot-p10b-streams-{}-{}",std::process::id(),std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos())));
    if temporary {std::fs::create_dir(&out).unwrap();}else{assert!(out.is_dir());}
    fn save(out:&std::path::Path,name:&str,raw:&[u8],bodies:&[Vec<u8>]){
        std::fs::write(out.join(format!("{name}.pickle")),raw).unwrap();let mut b=Vec::new();for body in bodies{b.extend((body.len()as u32).to_le_bytes());b.extend(body);}std::fs::write(out.join(format!("{name}.bodies")),b).unwrap();
    }
    let l=listing();save(&out,"list-one",&list_raw(&l).unwrap(),&list_stream(&l).unwrap());
    let empty=Listing{total:0,rows:Vec::new()};save(&out,"list-empty",&list_raw(&empty).unwrap(),&list_stream(&empty).unwrap());
    let mut many=listing();many.total=50;many.rows=(1..=50).map(|id|{let mut r=many.rows[0].clone();r.native_room_id=id;
        r.creator="Я".repeat(24);r.comment="x".repeat(64);r.creator_clan_abbrev="ABCDEFGH".into();r}).collect();
    save(&out,"list-many",&list_raw(&many).unwrap(),&list_stream(&many).unwrap());
    for own in [1,9]{let mut v=preview(6);v.members[0].row.name="ЯЯЯ".into();let mut b=PreviewBook::new(canonical(own)).unwrap();
        let raw=preview_raw(&mut b,&v).unwrap();let bodies=preview_stream(&mut b,&v).unwrap();save(&out,if own==1{"preview-member"}else{"preview-visitor"},&raw,&bodies);
    }
    if temporary {std::fs::remove_dir_all(out).unwrap();}
}
