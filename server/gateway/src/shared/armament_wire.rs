//! Staged #717 methods: source-derived fields, never a damage authority.
//! Existing AP wrappers are untouched. New ammo/critical/explosion UI NOT_RUN.
//! Caller must use a current actor epoch and P07B legal observer/owner routing.
use std::io;
use crate::p06t_shells091::{Family,Mount,Shell,PROFILES};

fn bad(reason:&'static str)->io::Error{io::Error::new(io::ErrorKind::InvalidData,reason)}
fn entity(id:u32)->io::Result<()>{if id==0||id>i32::MAX as u32{Err(bad("P06T bounded actual entity"))}else{Ok(())}}
fn source(id:u32)->io::Result<()>{if id>i32::MAX as u32{Err(bad("P06T source entity"))}else{Ok(())}}
fn vehicle(id:u32,method:u8)->io::Result<Vec<u8>>{entity(id)?;let mut b=vec![0x12];b.extend(id.to_le_bytes());b.push(method);Ok(b)}

/// Exact original XML order; _readShotEffectGroups uses len(list) before append.
pub const EFFECT_NAMES:[&str;23]=["autoArmorPiercing","autoAPCR","smallArmorPiercing","smallHighExplosive","smallHollowCharge","smallAPCR",
    "mediumArmorPiercing","mediumHighExplosive","mediumHollowCharge","mediumAPCR","mainArmorPiercing","mainHighExplosive","mainHollowCharge","mainAPCR",
    "largeArmorPiercing","largeHighExplosive","largeHollowCharge","largeAPCR","hugeArmorPiercing","hugeHighExplosive","hugeHollowCharge","hugeAPCR","sportHighExplosive"];
/// Use the shell frozen at launch, never the shooter's later selected shell.
pub fn effect_index(shell:Shell)->io::Result<u8>{
    if !PROFILES.iter().flat_map(|p|p.shots).any(|known|known==shell){return Err(bad("P06T shell must match closed source catalogue"));}
    EFFECT_NAMES.iter().position(|name|*name==shell.effects_resource).map(|n|n as u8).ok_or_else(||bad("P06T unknown original shell effects"))
}

#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Setting{Current,Next}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Intent{Select(Setting,u16),ReloadPartialClip}
/// One complete original Base VAR2 method. Transport framing stays elsewhere.
/// Source now proves partial reload sends code17/value0. No free replenishment.
pub fn command(record:&[u8])->io::Result<Option<Intent>>{
    if record.first()!=Some(&0x8d){return Ok(None);}
    if record.len()!=8||record[1..3]!=[5,0]{return Err(bad("P06T setting record boundary"));}
    let value=i32::from_le_bytes(record[4..8].try_into().map_err(|_|bad("P06T setting width"))?);
    match record[3]{
        0|1=>{let cd=u16::try_from(value).map_err(|_|bad("P06T shell compact width"))?;
            // Structurally bounded intents reach authority even if unmounted
            // or unknown. The domain refuses them and reconciles the actual
            // current/next; this is not a transport/channel failure.
            Ok(Some(Intent::Select(if record[3]==0{Setting::Current}else{Setting::Next},cd)))},
        17 if value==0=>Ok(Some(Intent::ReloadPartialClip)),
        2|16=>Ok(None), // retained handlers own these original settings
        _=>Err(bad("P06T unsupported original setting/value")),
    }
}

fn shot(mount:Mount,compact:u16)->io::Result<Shell>{PROFILES[mount.index()].shots.into_iter().find(|s|s.compact_descr==compact).ok_or_else(||bad("P06T shell not mounted"))}
/// quantity includes the clip under the explicitly documented server lab policy.
/// timeRemaining=0 is intentional: original shell consumer ignores this field.
pub fn ammo_row(mount:Mount,compact:u16,quantity:u16,in_clip:u8)->io::Result<Vec<u8>>{
    shot(mount,compact)?;let p=PROFILES[mount.index()];
    if quantity>p.capacity||in_clip>p.clip_count||u16::from(in_clip)>quantity||p.clip_count==1&&in_clip!=0{
        return Err(bad("P06T ammo source/capacity/clip boundary"));
    }
    let mut b=vec![0x13,0x44];b.extend(i32::from(compact).to_le_bytes());b.extend(quantity.to_le_bytes());b.push(in_clip);b.extend(0i16.to_le_bytes());Ok(b)
}
pub fn setting(mount:Mount,which:Setting,compact:u16)->io::Result<Vec<u8>>{
    shot(mount,compact)?;let mut b=vec![0x13,0x40,match which{Setting::Current=>0,Setting::Next=>1}];b.extend(i32::from(compact).to_le_bytes());Ok(b)
}
/// Full owner reconciliation, including zero stacks, current+next and clip.
/// This does not mutate state. Caller derives all fields from one snapshot.
pub fn ammo_snapshot(mount:Mount,counts:[u16;3],current:u16,next:u16,clip:u8)->io::Result<Vec<u8>>{
    let p=PROFILES[mount.index()];shot(mount,current)?;shot(mount,next)?;
    let total=counts.iter().try_fold(0u16,|n,c|n.checked_add(*c)).ok_or_else(||bad("P06T ammo total overflow"))?;
    let current_count=counts[p.shots.iter().position(|s|s.compact_descr==current).ok_or_else(||bad("P06T current source"))?];
    if total>p.capacity||clip>p.clip_count||u16::from(clip)>current_count{return Err(bad("P06T ammo total/clip source capacity"));}
    let mut b=Vec::new();
    for(i,s)in p.shots.into_iter().enumerate(){
        let visible_clip=if s.compact_descr==current&&p.clip_count>1{clip}else{0};
        b.extend(ammo_row(mount,s.compact_descr,counts[i],visible_clip)?);
    }
    b.extend(setting(mount,Setting::Current,current)?);b.extend(setting(mount,Setting::Next,next)?);Ok(b)
}
/// Original FLOAT32 timeLeft/baseTime. Only authoritative nonnegative timers
/// are emitted; negative original sentinels remain deliberately unavailable.
/// 480 is the explicit LAB source-base ceiling120 * module/crew scale4.
pub fn reload(vehicle_id:u32,time_left:f32,base_time:f32)->io::Result<Vec<u8>>{
    entity(vehicle_id)?;
    if !base_time.is_finite()||!(0.1..=480.).contains(&base_time)||!time_left.is_finite()||!(0. ..=base_time).contains(&time_left){return Err(bad("P06T bounded reload clock"));}
    let mut b=vec![0x13,0x46];b.extend(vehicle_id.to_le_bytes());b.extend(time_left.to_le_bytes());b.extend(base_time.to_le_bytes());Ok(b)
}

/// Complete ARRAY<UINT8> value for native create property7 (no VAR1 there).
pub fn modifiers_value(modifiers:&[u8])->io::Result<Vec<u8>>{
    if modifiers.len()>42{return Err(bad("P06T modifier count"));}
    let mut seen=[false;43];
    for &extra in modifiers{if extra==0||extra>42||seen[extra as usize]{return Err(bad("P06T modifier source index/duplicate"));}seen[extra as usize]=true;}
    let mut b=Vec::with_capacity(4+modifiers.len());b.extend((modifiers.len()as i32).to_le_bytes());b.extend(modifiers);Ok(b)
}
/// Full property update: select Vehicle, 0xa5 VAR1, signed32 ARRAY count, values.
/// Caller removes fire4 alone from its complete current state when extinguished.
pub fn public_modifiers(vehicle_id:u32,modifiers:&[u8])->io::Result<Vec<u8>>{
    let value=modifiers_value(modifiers)?;let mut b=vehicle(vehicle_id,0xa5)?;b.push(value.len()as u8);b.extend(value);b.push(0x13);Ok(b)
}
/// isCrewActive property index1: BOOL, fixed one byte. Positive HP can coexist
/// with inactive crew; actor death/capability/lifecycle must agree separately.
pub fn public_crew_active(vehicle_id:u32,active:bool)->io::Result<Vec<u8>>{
    let mut b=vehicle(vehicle_id,0x9f)?;b.push(u8::from(active));b.push(0x13);Ok(b)
}
/// Owner HUD handles positive HP + false as crew deactivation/postmortem.
/// Explicit -1/-2 represent original explosion/detachment states, never an
/// inferred substitute for ordinary zero HP. max_hp is source/profile owned.
pub fn owner_health(health:i16,crew_active:bool,max_hp:u16)->io::Result<Vec<u8>>{
    if max_hp==0||max_hp>i16::MAX as u16||health< -2||i32::from(health)>i32::from(max_hp){return Err(bad("P06T health source range"));}
    let mut b=vec![0x13,0x3f];b.extend(health.to_le_bytes());b.push(u8::from(crew_active));Ok(b)
}

/// Original DAMAGE_INFO_CODES namespace (0..35), not hit-effect codes.
/// These pairing guards prevent a device notification dereferencing None or a
/// crew message pointing at a non-health extra. Caller still owns true events.
pub fn damage_info(vehicle_id:u32,code:u8,extra:u8,entity_id:u32)->io::Result<Vec<u8>>{
    entity(vehicle_id)?;source(entity_id)?;
    let valid=match code{
        0|1|4|5|6|7|8|9|11|12|13|14|15|16|17|18|19|23|24|25=>(26..=34).contains(&extra),
        2|10|20|21|22=>(35..=42).contains(&extra),
        3|35=>extra==0||extra==4,
        26..=34=>extra==0,
        _=>false,
    };
    if !valid{return Err(bad("P06T damage code/extra source namespace"));}
    let mut b=vec![0x13,0x45];b.extend(vehicle_id.to_le_bytes());b.extend([code,extra]);b.extend(entity_id.to_le_bytes());Ok(b)
}
/// Vehicle splash presentation uses the launched HE shell's original effects.
/// center is authoritative and subject to existing per-recipient P07B filtering.
/// This function never calculates HP loss, radius, or a hit to an unseen module.
pub fn explosion(vehicle_id:u32,attacker_id:u32,center:[f32;3],shell:Shell)->io::Result<Vec<u8>>{
    source(attacker_id)?;
    if shell.family!=Family::HighExplosive||center.iter().any(|v|!v.is_finite()||v.abs()>100_000.){return Err(bad("P06T bounded authoritative explosion"));}
    let effects=effect_index(shell)?;let mut b=vehicle(vehicle_id,0x40)?;b.extend(attacker_id.to_le_bytes());
    for v in center{b.extend(v.to_le_bytes());}b.push(effects);b.push(0x13);Ok(b)
}
/// Codec only. A real authoritative ammo-bay explosion/detachment event is
/// required; external tank triangles do not establish an ammo-bay hit volume.
pub fn ammo_bay_explosion(vehicle_id:u32,fireball_volume:f32,projected_turret_speed:f32)->io::Result<Vec<u8>>{
    if !fireball_volume.is_finite()||!(0. ..=10_000.).contains(&fireball_volume)
        ||!projected_turret_speed.is_finite()||!(0. ..=1_000.).contains(&projected_turret_speed){return Err(bad("P06T bounded ammo-bay visual"));}
    let mut b=vehicle(vehicle_id,0x3d)?;b.extend(fireball_volume.to_le_bytes());b.extend(projected_turret_speed.to_le_bytes());b.push(0x13);Ok(b)
}
