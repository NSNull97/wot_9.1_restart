use super::*;
fn roster()->Vec<Summary>{vec![
    Summary{vehicle_id:10,team:1,direct_hits:1,piercings:1,damage_dealt:90,damage_received:0,kills:1,killer_id:0,death_reason:-1},
    Summary{vehicle_id:20,team:2,direct_hits:0,piercings:0,damage_dealt:0,damage_received:90,kills:0,killer_id:10,death_reason:0}]}
fn shot()->Vec<Shot>{vec![Shot{id:1,attacker:0}]}
fn hit()->Vec<Hit>{vec![Hit{shot:1,target:1}]}
fn damage()->Vec<Damage>{vec![Damage{sequence:1,shot:1,attacker:0,target:1,health_before:90,health_after:0,lethal:true,reason:0}]}
fn build()->Details{project(&roster(),&shot(),&hit(),&hit(),&damage(),&[],Some(&[Spot{observer:0,target:1,tick:1001}])).unwrap()}
#[test]fn p08c_personal_real_fact_projection_and_source_scalar_packing(){
    let d=build();assert_eq!(d.rows[0].targets[0].spotted,1);assert_eq!(d.rows[0].targets[0].damage_dealt,90);
    // Independent hand calculation: ID20, B1,b0,H1,H0,H1,H90,H0,H0,I0,H0.
    assert_eq!(d.packed(10).unwrap(),vec![20,0,0,0,1,0,1,0,0,0,1,0,90,0,0,0,0,0,0,0,0,0,0,0]);
    assert_eq!(d.packed(20).unwrap(),Vec::<u8>::new());
    assert_eq!(d.outgoing(10,"damaged"),1);assert_eq!(d.incoming(20,"piercingsReceived"),1);
}
#[test]fn p08c_personal_all_ids_precede_all_twenty_byte_rows(){
    let mut r=roster();r[0].damage_dealt=90;r[0].kills=0;r[1].killer_id=0;r[1].death_reason=-1;
    r[1].damage_received=40;r.push(Summary{vehicle_id:15,team:2,damage_received:50,..r[1]});
    let d=project(&r,&shot(),&hit(),&hit(),&[
        Damage{sequence:1,health_before:90,health_after:50,lethal:false,..damage()[0]},
        Damage{sequence:2,target:2,health_before:90,health_after:40,lethal:false,..damage()[0]},
    ],&[Splash{shot:1,target:2,clear_los:true}],None).unwrap();
    let p=d.packed(10).unwrap();assert_eq!(p.len(),48);assert_eq!(&p[..8],&[15,0,0,0,20,0,0,0]);
    assert_eq!(&p[8..16],&[0,255,0,0,1,0,0,0]);assert_eq!(&p[16..18],&[50,0]);
    assert_eq!(&p[28..36],&[0,255,1,0,0,0,1,0]);assert_eq!(&p[36..38],&[40,0]);
}
#[test]fn p08c_personal_direct_and_later_fire_preserve_original_killer(){
    let mut r=roster();r[1].death_reason=1;
    let d=project(&r,&shot(),&hit(),&hit(),&[
        Damage{sequence:1,health_after:20,lethal:false,..damage()[0]},
        Damage{sequence:2,health_before:20,reason:1,..damage()[0]}],&[],None).unwrap();
    assert_eq!(d.rows[0].targets[0].death_reason,1);assert_eq!(d.rows[0].targets[0].fire,0);
    assert_eq!(d.rows[0].targets[0].damage_dealt,90);
}
#[test]fn p08c_personal_crew_loss_can_kill_without_invented_hull_damage(){
    let mut r=roster();r[0].damage_dealt=0;r[1].damage_received=0;
    let d=project(&r,&shot(),&hit(),&hit(),&[Damage{health_after:90,..damage()[0]}],&[],None).unwrap();
    assert_eq!(d.rows[0].targets[0].damage_dealt,0);assert_eq!(d.rows[0].targets[0].death_reason,0);
}
#[test]fn p08c_personal_clear_zero_damage_splash_is_hit_blocked_is_not(){
    let mut r=roster();for s in &mut r{s.direct_hits=0;s.piercings=0;s.damage_dealt=0;s.damage_received=0;s.kills=0;s.killer_id=0;s.death_reason=-1;}
    let d=project(&r,&shot(),&[],&[],&[],&[Splash{shot:1,target:1,clear_los:true}],None).unwrap();
    assert_eq!(d.rows[0].targets[0].explosion_hits,1);
    let d=project(&r,&shot(),&[],&[],&[],&[Splash{shot:1,target:1,clear_los:false}],None).unwrap();
    assert!(d.rows[0].targets.is_empty());
}
#[test]fn p08c_personal_spot_availability_no_hit_inference_and_duplicate_refusal(){
    let d=project(&roster(),&shot(),&hit(),&hit(),&damage(),&[],None).unwrap();
    assert_eq!(d.spotting_policy,None);assert_eq!(d.rows[0].targets[0].spotted,0);
    let d=project(&roster(),&shot(),&hit(),&hit(),&damage(),&[],Some(&[])).unwrap();
    assert_eq!(d.spotting_policy.as_deref(),Some(SPOTTING_POLICY));
    let spots=[Spot{observer:0,target:1,tick:1},Spot{observer:0,target:1,tick:2}];
    assert!(project(&roster(),&shot(),&hit(),&hit(),&damage(),&[],Some(&spots)).is_err());
}
#[test]fn p08c_personal_six_actor_friendly_and_self_damage_are_not_discarded(){
    let r=(0..6).map(|n|Summary{vehicle_id:10+n,team:if n<3{1}else{2},direct_hits:1,piercings:0,
        damage_dealt:5,damage_received:5,kills:0,killer_id:0,death_reason:-1}).collect::<Vec<_>>();
    let shots=(0..6).map(|n|Shot{id:n as u32+1,attacker:n}).collect::<Vec<_>>();
    let hits=(0..6).map(|n|Hit{shot:n as u32+1,target:n}).collect::<Vec<_>>();
    let damage=(0..6).map(|n|Damage{sequence:n as u32+1,shot:n as u32+1,attacker:n,target:n,
        health_before:90,health_after:85,lethal:false,reason:0}).collect::<Vec<_>>();
    let d=project(&r,&shots,&hits,&[],&damage,&[],None).unwrap();assert_eq!(d.rows.len(),6);
    assert!(d.rows.iter().all(|r|r.targets[0].vehicle_id==r.attacker_vehicle_id));
}
#[test]fn p08c_personal_poison_never_mutates_inputs_or_omits_bad_facts(){
    let r=roster();let original=format!("{r:?}");
    assert!(project(&r,&shot(),&[hit()[0],hit()[0]],&hit(),&damage(),&[],None).is_err());
    assert!(project(&r,&shot(),&hit(),&[Hit{shot:2,target:1}],&damage(),&[],None).is_err());
    assert!(project(&r,&shot(),&hit(),&hit(),&[Damage{attacker:1,..damage()[0]}],&[],None).is_err());
    assert!(project(&r,&shot(),&hit(),&hit(),&damage(),&[Splash{shot:1,target:1,clear_los:true}],None).is_err());
    assert_eq!(format!("{r:?}"),original);build().validate(&r).unwrap();
    for n in 0..9{let mut d=build();let t=&mut d.rows[0].targets[0];match n{
        0=>t.vehicle_id=999,1=>t.damage_dealt=89,2=>t.death_reason=1,3=>t.spotted=2,
        4=>t.damage_assisted_track=1,5=>t.crits=193,6=>t.fire=11,7=>d.policy="fake".into(),_=>d.spotting_policy=None,
    }assert!(d.validate(&r).is_err(),"poison{n}");}
}

#[test]fn p06t_module_and_fire_facts_are_projected_into_personal_details(){
    let r=roster();let mut d=build();
    apply_module_facts(&mut d,&r,&[
        Module{attacker:0,target:1,extra_index:27,critical:true,fire:false},
        Module{attacker:0,target:1,extra_index:4,critical:false,fire:true},
    ]).unwrap();
    let target=&d.rows[0].targets[0];
    assert_eq!((target.crits,target.fire),(1,1));
    assert_eq!((d.outgoing(10,"crits"),d.outgoing(10,"fire")),(1,1));
    assert!(d.validate(&r).is_ok());
}

#[test]fn p06t_module_fact_can_create_a_zero_damage_target_row(){
    let mut r=roster();r[0].direct_hits=0;r[0].piercings=0;r[0].damage_dealt=0;r[0].kills=0;
    r[1].damage_received=0;r[1].killer_id=0;r[1].death_reason=-1;
    let mut d=project(&r,&shot(),&[],&[],&[],&[],None).unwrap();
    apply_module_facts(&mut d,&r,&[Module{attacker:0,target:1,extra_index:27,critical:true,fire:false}]).unwrap();
    assert_eq!(d.rows[0].targets[0].crits,1);
}

#[test]fn p06t_module_fact_rejects_bad_slot_without_partial_mutation(){
    let r=roster();let mut d=build();let before=d.clone();
    assert!(apply_module_facts(&mut d,&r,&[
        Module{attacker:0,target:1,extra_index:27,critical:true,fire:false},
        Module{attacker:2,target:1,extra_index:27,critical:true,fire:false},
    ]).is_err());
    assert_eq!(d,before);
}
