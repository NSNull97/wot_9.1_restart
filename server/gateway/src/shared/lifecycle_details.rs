//! Versioned authoritative interaction presentation. No ownership/HP mutation.
//! Source #717 VehicleInteractionDetails packs ALL target IDs before ALL rows.
use std::{collections::{BTreeMap,BTreeSet},io};
pub const POLICY:&str="test_lab.authoritative-interactions.v1";
pub const SPOTTING_POLICY:&str="test_lab.p08c.first-visible-enemy-lowest-slot.v1";
pub const MAX_ACTORS:usize=super::model::MAX_ACTORS;
fn bad()->io::Error{io::Error::new(io::ErrorKind::InvalidData,"authoritative result interactions")}
#[derive(Clone,Debug,Default,PartialEq,Eq)]
pub struct Target {
    pub vehicle_id:u32,pub spotted:u8,pub death_reason:i8,pub direct_hits:u16,
    pub explosion_hits:u16,pub piercings:u16,pub damage_dealt:u16,
    pub damage_assisted_track:u16,pub damage_assisted_radio:u16,pub crits:u32,pub fire:u16,
}
impl Target {
    fn empty(vehicle_id:u32)->Self{Self{vehicle_id,death_reason:-1,..Self::default()}}
    fn has_facts(&self)->bool{self.spotted!=0||self.death_reason!=-1||self.direct_hits!=0
        ||self.explosion_hits!=0||self.piercings!=0||self.damage_dealt!=0
        ||self.crits!=0||self.fire!=0}
}
#[derive(Clone,Debug,PartialEq,Eq)]
pub struct Row{pub attacker_vehicle_id:u32,pub targets:Vec<Target>}
#[derive(Clone,Debug,PartialEq,Eq)]
pub struct Details{pub version:u8,pub policy:String,pub spotting_policy:Option<String>,pub rows:Vec<Row>}
#[derive(Clone,Copy,Debug)]
pub struct Summary{pub vehicle_id:u32,pub team:u8,pub direct_hits:u16,pub piercings:u16,
    pub damage_dealt:u32,pub damage_received:u32,pub kills:u8,pub killer_id:u32,pub death_reason:i8}
#[derive(Clone,Copy,Debug)]
pub struct Shot{pub id:u32,pub attacker:usize}
#[derive(Clone,Copy,Debug)]
pub struct Hit{pub shot:u32,pub target:usize}
#[derive(Clone,Copy,Debug)]
pub struct Splash{pub shot:u32,pub target:usize,pub clear_los:bool}
#[derive(Clone,Copy,Debug)]
pub struct Damage{pub sequence:u32,pub shot:u32,pub attacker:usize,pub target:usize,
    pub health_before:i16,pub health_after:i16,pub lethal:bool,pub reason:u8}
/// The domain clock orders projectile/fire damage with other health causes.
/// A physics worker's private fixed-step tick must never be used here.
#[derive(Clone,Copy,Debug)]
pub struct TimedDamage{pub tick:u32,pub damage:Damage}
/// Committed contact damage has no projectile, direct hit or piercing identity.
#[derive(Clone,Copy,Debug)]
pub struct RamDamage{pub sequence:u32,pub tick:u32,pub attacker:usize,pub target:usize,
    pub health_before:i16,pub health_after:i16}
#[derive(Clone,Copy,Debug)]
pub struct Spot{pub observer:usize,pub target:usize,pub tick:u32}
/// A committed module/crew/fire transition projected into native personal details.
/// This is presentation only; the authoritative device journal remains in World.
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub struct Module{pub attacker:usize,pub target:usize,pub extra_index:u8,pub critical:bool,pub fire:bool}
fn add(v:&mut u16,n:u16)->io::Result<()>{*v=v.checked_add(n).ok_or_else(bad)?;Ok(())}
impl Details {
    pub fn validate(&self,roster:&[Summary])->io::Result<()>{
        if !(2..=MAX_ACTORS).contains(&roster.len())||self.version!=1||self.policy!=POLICY
            ||self.spotting_policy.as_deref().is_some_and(|p|p!=SPOTTING_POLICY)
            ||self.rows.len()!=roster.len(){return Err(bad());}
        let mut ids=BTreeSet::new();
        for s in roster{if s.vehicle_id==0||s.vehicle_id>i32::MAX as u32||!(1..=2).contains(&s.team)
            ||!ids.insert(s.vehicle_id){return Err(bad());}}
        let mut attackers=BTreeSet::new();let mut spotted=BTreeSet::new();let mut dead=BTreeSet::new();
        let mut received:BTreeMap<u32,u32>=BTreeMap::new();
        for row in &self.rows{
            let own=roster.iter().find(|s|s.vehicle_id==row.attacker_vehicle_id).ok_or_else(bad)?;
            if !attackers.insert(own.vehicle_id)||row.targets.len()>roster.len(){return Err(bad());}
            let(mut previous,mut hits,mut pierced,mut damage,mut kills)=(0,0u32,0u32,0u32,0u32);
            for t in &row.targets{
                let target=roster.iter().find(|s|s.vehicle_id==t.vehicle_id).ok_or_else(bad)?;
                if t.vehicle_id<=previous||t.spotted>1||!(-1..=10).contains(&t.death_reason)
                    ||t.piercings>t.direct_hits||t.damage_assisted_track!=0||t.damage_assisted_radio!=0
                    ||t.crits>192||t.fire>10||!t.has_facts(){return Err(bad());}
                previous=t.vehicle_id;
                if t.spotted!=0&&(self.spotting_policy.is_none()||own.team==target.team
                    ||!spotted.insert(t.vehicle_id)){return Err(bad());}
                if t.death_reason!=-1{
                    if target.killer_id!=own.vehicle_id||target.death_reason!=t.death_reason
                        ||!dead.insert(t.vehicle_id){return Err(bad());}kills+=1;
                }
                hits+=u32::from(t.direct_hits);pierced+=u32::from(t.piercings);damage+=u32::from(t.damage_dealt);
                *received.entry(t.vehicle_id).or_default()+=u32::from(t.damage_dealt);
            }
            if hits!=u32::from(own.direct_hits)||pierced!=u32::from(own.piercings)
                ||damage!=own.damage_dealt||kills!=u32::from(own.kills){return Err(bad());}
        }
        for s in roster{if received.get(&s.vehicle_id).copied().unwrap_or(0)!=s.damage_received
            ||s.killer_id!=0&&!dead.contains(&s.vehicle_id){return Err(bad());}}
        Ok(())
    }
    pub fn row(&self,id:u32)->Option<&Row>{self.rows.iter().find(|r|r.attacker_vehicle_id==id)}
    /// Call only after validate: 4*N ID bytes, then 20*N scalar bytes, no header.
    pub fn packed(&self,id:u32)->io::Result<Vec<u8>>{
        let row=self.row(id).ok_or_else(bad)?;if row.targets.len()>MAX_ACTORS{return Err(bad());}
        let mut out=Vec::with_capacity(row.targets.len()*24);
        for t in &row.targets{out.extend(t.vehicle_id.to_le_bytes());}
        for t in &row.targets{
            out.extend([t.spotted,t.death_reason as u8]);
            for n in [t.direct_hits,t.explosion_hits,t.piercings,t.damage_dealt,t.damage_assisted_track,t.damage_assisted_radio]{out.extend(n.to_le_bytes());}
            out.extend(t.crits.to_le_bytes());out.extend(t.fire.to_le_bytes());
        }Ok(out)
    }
    pub fn outgoing(&self,id:u32,field:&str)->u32{self.row(id).map_or(0,|r|r.targets.iter().map(|t|match field{
        "spotted"=>u32::from(t.spotted),"damaged"=>u32::from(t.damage_dealt>0),
        "explosionHits"=>u32::from(t.explosion_hits),"crits"=>t.crits,"fire"=>u32::from(t.fire),_=>0}).sum())}
    pub fn incoming(&self,id:u32,field:&str)->u32{self.rows.iter().flat_map(|r|&r.targets).filter(|t|t.vehicle_id==id).map(|t|match field{
        "directHitsReceived"=>u32::from(t.direct_hits),"explosionHitsReceived"=>u32::from(t.explosion_hits),
        "piercingsReceived"=>u32::from(t.piercings),_=>0}).sum()}
}
/// Bounded adapter inputs must come from committed World/Trace journals. This
/// component checks cross-ledger identities and totals; it grants no authority.
pub fn project(roster:&[Summary],shots:&[Shot],direct:&[Hit],pierced:&[Hit],
    damage:&[Damage],splash:&[Splash],spots:Option<&[Spot]>)->io::Result<Details>{
    let timed=damage.iter().map(|d|TimedDamage{tick:d.sequence,damage:*d}).collect::<Vec<_>>();
    project_with_ram(roster,shots,direct,pierced,&timed,&[],splash,spots)
}
/// Project the two typed authoritative journals together. Sorting the committed
/// records by domain tick and descending pre-damage HP preserves the actual
/// chain when a shot and contact are committed during the same domain frame.
/// It does not supply a missing shot identity to a contact.
pub fn project_with_ram(roster:&[Summary],shots:&[Shot],direct:&[Hit],pierced:&[Hit],
    damage:&[TimedDamage],ram:&[RamDamage],splash:&[Splash],spots:Option<&[Spot]>)->io::Result<Details>{
    if !(2..=MAX_ACTORS).contains(&roster.len())||shots.len()>960||direct.len()>960
        ||pierced.len()>960||damage.len()>15360||splash.len()>5760
        ||ram.len()>36000*MAX_ACTORS*(MAX_ACTORS-1)
        ||spots.is_some_and(|s|s.len()>MAX_ACTORS){return Err(bad());}
    let mut shotmap=BTreeMap::new();for s in shots{if s.id==0||s.attacker>=roster.len()
        ||shotmap.insert(s.id,s.attacker).is_some(){return Err(bad());}}
    let mut matrix:BTreeMap<(usize,usize),Target>=BTreeMap::new();
    let mut directs=BTreeSet::new();let mut direct_shots=BTreeSet::new();
    for h in direct{let a=*shotmap.get(&h.shot).ok_or_else(bad)?;
        if h.target>=roster.len()||!directs.insert((h.shot,h.target))||!direct_shots.insert(h.shot){return Err(bad());}
        add(&mut matrix.entry((a,h.target)).or_insert_with(||Target::empty(roster[h.target].vehicle_id)).direct_hits,1)?;
    }
    let mut piercings=BTreeSet::new();for h in pierced{let a=*shotmap.get(&h.shot).ok_or_else(bad)?;
        if !directs.contains(&(h.shot,h.target))||!piercings.insert((h.shot,h.target)){return Err(bad());}
        add(&mut matrix.get_mut(&(a,h.target)).ok_or_else(bad)?.piercings,1)?;
    }
    let mut splashkeys=BTreeSet::new();for h in splash{let a=*shotmap.get(&h.shot).ok_or_else(bad)?;
        if h.target>=roster.len()||directs.contains(&(h.shot,h.target))||!splashkeys.insert((h.shot,h.target)){return Err(bad());}
        if h.clear_los{add(&mut matrix.entry((a,h.target)).or_insert_with(||Target::empty(roster[h.target].vehicle_id)).explosion_hits,1)?;}
    }
    let mut sequence=0;let mut tick=0;
    let mut events=Vec::with_capacity(damage.len()+ram.len());
    for timed in damage{let d=&timed.damage;
        if d.sequence<=sequence||timed.tick==0||timed.tick<tick||d.target>=roster.len()
            ||shotmap.get(&d.shot)!=Some(&d.attacker)
            ||d.health_before<0||d.health_before>10000||d.health_after<0||d.health_after>d.health_before
            ||d.reason>10||d.health_before==d.health_after&&!d.lethal
            ||!d.lethal&&d.health_after==0
            ||!directs.contains(&(d.shot,d.target))&&!splashkeys.contains(&(d.shot,d.target)){return Err(bad());}
        sequence=d.sequence;tick=timed.tick;
        events.push((timed.tick,d.attacker,d.target,d.health_before,d.health_after,d.lethal,d.reason));
    }
    let mut keys=BTreeSet::new();let mut sequence=0;let mut tick=0;
    for r in ram{
        if r.sequence==0||r.sequence<sequence||r.tick==0||r.tick<tick||r.attacker>=roster.len()
            ||r.target>=roster.len()||r.attacker==r.target||r.health_before<=0||r.health_before>10000
            ||r.health_after<0||r.health_after>=r.health_before
            ||!keys.insert((r.sequence,r.attacker,r.target)){return Err(bad());}
        sequence=r.sequence;tick=r.tick;
        events.push((r.tick,r.attacker,r.target,r.health_before,r.health_after,r.health_after==0,2));
    }
    events.sort_by_key(|&(tick,_,target,before,_,lethal,_)|(tick,target,std::cmp::Reverse(before),lethal));
    let mut lethals=BTreeSet::new();let mut health=BTreeMap::new();
    for (_,attacker,target,before,after,lethal,reason) in events{
        if lethals.contains(&target)||health.get(&target).is_some_and(|previous|*previous!=before){return Err(bad());}
        health.insert(target,after);
        let t=matrix.entry((attacker,target)).or_insert_with(||Target::empty(roster[target].vehicle_id));
        add(&mut t.damage_dealt,(before-after)as u16)?;
        if lethal{if !lethals.insert(target){return Err(bad());}t.death_reason=reason as i8;}
    }
    if let Some(spots)=spots{let mut targets=BTreeSet::new();for s in spots{
        if s.observer>=roster.len()||s.target>=roster.len()||s.tick==0
            ||roster[s.observer].team==roster[s.target].team||!targets.insert(s.target){return Err(bad());}
        matrix.entry((s.observer,s.target)).or_insert_with(||Target::empty(roster[s.target].vehicle_id)).spotted=1;
    }}
    let rows=(0..roster.len()).map(|a|{let mut targets=matrix.iter().filter(|((attacker,_),_)|*attacker==a)
        .map(|(_,t)|t.clone()).collect::<Vec<_>>();targets.sort_by_key(|t|t.vehicle_id);
        Row{attacker_vehicle_id:roster[a].vehicle_id,targets}}).collect();
    let result=Details{version:1,policy:POLICY.into(),spotting_policy:spots.map(|_|SPOTTING_POLICY.into()),rows};
    result.validate(roster)?;Ok(result)
}

/// Add committed module/fire facts to a previously validated details snapshot.
/// Device names/HP are intentionally not exported here; the original packed
/// contract exposes only the critical and fire counters in this section.
pub fn apply_module_facts(details:&mut Details,roster:&[Summary],modules:&[Module])->io::Result<()> {
    if modules.len()>MAX_ACTORS*192{return Err(bad());}
    let mut next=details.clone();
    for module in modules {
        if module.attacker>=roster.len()||module.target>=roster.len()
            ||!(module.extra_index==4||(26..=42).contains(&module.extra_index)) {return Err(bad());}
        let target_id=roster[module.target].vehicle_id;
        let row=next.rows.iter_mut().find(|row|row.attacker_vehicle_id==roster[module.attacker].vehicle_id).ok_or_else(bad)?;
        if let Some(target)=row.targets.iter_mut().find(|target|target.vehicle_id==target_id) {
            if module.critical {target.crits=target.crits.checked_add(1).ok_or_else(bad)?;}
            if module.fire {target.fire=target.fire.checked_add(1).ok_or_else(bad)?;}
        } else {
            if row.targets.len()>=roster.len(){return Err(bad());}
            let mut target=Target::empty(target_id);
            if module.critical {target.crits=1;}
            if module.fire {target.fire=1;}
            row.targets.push(target);
            row.targets.sort_by_key(|target|target.vehicle_id);
        }
    }
    next.validate(roster)?;
    *details=next;
    Ok(())
}

#[cfg(test)]
#[path="lifecycle_details_tests.rs"]mod tests;
