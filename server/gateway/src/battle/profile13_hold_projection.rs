//! The v5 writer's closed, hash-bound companion. It supplies actual SQL layout
//! signs/mount keys; this module never unpickles a native account snapshot.
use std::io;
use serde_json::Value;
use crate::{profile13_hold091 as hold,profile13_loss091 as loss,profile13_v2091 as base};
fn bad(s:&'static str)->io::Error{io::Error::new(io::ErrorKind::InvalidData,format!("hold5 projection: {s}"))}
fn keys(v:&Value,ks:&[&str])->io::Result<()>{if v.as_object().is_none_or(|o|o.len()!=ks.len()||ks.iter().any(|k|!o.contains_key(*k))){return Err(bad("exact fields"));}Ok(())}
fn digest(s:&str)->bool{s.len()==64&&s.bytes().all(|c|c.is_ascii_digit()||(b'a'..=b'f').contains(&c))}

#[derive(Clone,Debug,PartialEq,Eq)]
pub struct NativeLayout{native:u32,turret:u16,gun:u16,layout:[i32;6]}
impl NativeLayout{
    pub fn native_inventory_id(&self)->u32{self.native}
    pub fn counts(&self)->[u16;3]{std::array::from_fn(|i|self.layout[2*i+1] as u16)}
    pub fn signed_layout(&self)->[i32;6]{self.layout}
    pub fn mount(&self)->(u16,u16){(self.turret,self.gun)}
}
#[derive(Clone,Debug,PartialEq,Eq)]
pub struct Binding{account:String,database:i32,revision:u64,state_sha256:String,layouts:Vec<NativeLayout>}
impl Binding{
    pub fn revision(&self)->u64{self.revision}
    pub fn matches(&self,account:&str,database:i32,revision:u64,state_sha256:&str)->bool{
        self.account==account&&self.database==database&&self.revision==revision&&self.state_sha256==state_sha256
    }
    pub fn layout_for(&self,f:&hold::FrozenHold,counts:[u16;3])->io::Result<&NativeLayout>{
        f.validate_owned(&self.account)?;let source=&f.loss().base;
        let layout=self.layouts.iter().find(|l|l.native==source.native_inventory_id).ok_or_else(||bad("actual owned source layout missing"))?;
        let (turret,gun)=match source.kind.label(){"ms1"=>(5891,5892),"is7"=>(12035,14852),_=>return Err(bad("owned hold5 remains source stock two"))};
        if layout.turret!=turret||layout.gun!=gun||layout.counts()!=counts||counts.iter().map(|n|u32::from(*n)).sum::<u32>()>u32::from(source.capacity)
            ||(0..3).any(|i|layout.layout[2*i].unsigned_abs()!=u32::from(source.ammunition[i].shell_compact_id)){
            return Err(bad("actual SQL layout disagrees with frozen source/remaining"));
        }Ok(layout)
    }
}
pub fn parse(raw:&[u8],account:&str,database:i32,revision:u64,state_sha256:&str)->io::Result<Binding>{
    let v=base::bounded_json(raw,4096)?;
    keys(&v,&["version","contract","policy_sha256","base_loss_policy_sha256","account_id","native_database_id","revision","state_sha256","native_layouts"])?;
    if database<=0||!(13..i32::MAX as u64).contains(&revision)||!digest(state_sha256)
        ||v["version"]!=hold::VERSION||v["contract"]!=hold::CONTRACT||v["policy_sha256"]!=hold::POLICY_SHA256||v["base_loss_policy_sha256"]!=loss::POLICY_SHA256
        ||v["account_id"]!=account||v["native_database_id"].as_i64()!=Some(i64::from(database))||v["revision"].as_u64()!=Some(revision)||v["state_sha256"]!=state_sha256{
        return Err(bad("source identity/policy/current state SHA"));}
    let rows=v["native_layouts"].as_array().ok_or_else(||bad("layout array"))?;
    if rows.len()>2{return Err(bad("source two-layout maximum"));}
    let mut layouts=Vec::with_capacity(rows.len());let mut previous=0;
    for r in rows{
        keys(r,&["native_inventory_id","turret_compact_id","gun_compact_id","shells_layout"])?;
        let native=u32::try_from(r["native_inventory_id"].as_u64().ok_or_else(||bad("native ID"))?).map_err(|_|bad("native width"))?;
        let turret=u16::try_from(r["turret_compact_id"].as_u64().ok_or_else(||bad("turret"))?).map_err(|_|bad("turret width"))?;
        let gun=u16::try_from(r["gun_compact_id"].as_u64().ok_or_else(||bad("gun"))?).map_err(|_|bad("gun width"))?;
        let source=match native{1=>(5891,5892,[2570,2826,3082],96u32),2=>(12035,14852,[14602,14858,15114],30),_=>return Err(bad("unknown stock native ID"))};
        if native<=previous||(turret,gun)!=(source.0,source.1){return Err(bad("source mount or order"));}
        let input=r["shells_layout"].as_array().ok_or_else(||bad("layout list"))?;
        if input.len()!=6{return Err(bad("three signed layout pairs"));}
        let mut layout=[0i32;6];for(i,n)in input.iter().enumerate(){layout[i]=i32::try_from(n.as_i64().ok_or_else(||bad("layout integer"))?).map_err(|_|bad("layout width"))?;}
        if (0..3).any(|i|layout[2*i]==0||layout[2*i].unsigned_abs()!=source.2[i]||layout[2*i+1]<0||layout[2*i+1] as u32>source.3)
            ||(0..3).map(|i|layout[2*i+1] as u32).sum::<u32>()>source.3{return Err(bad("actual source layout/capacity"));}
        layouts.push(NativeLayout{native,turret,gun,layout});previous=native;
    }
    Ok(Binding{account:account.into(),database,revision,state_sha256:state_sha256.into(),layouts})
}

/// Fixed inert protocol2 primitives. Output shape follows original #717
/// recursive diff semantics: None removes only this vehicle's ON_ARENA lock.
/// No inventory10/depot entry is present, so warehouse stock cannot change.
pub fn final_delta(layout:&NativeLayout,wire_revision:i64)->io::Result<Vec<u8>>{
    if !(1..i64::from(i32::MAX)-1).contains(&wire_revision){return Err(bad("native cursor"));}
    struct P(Vec<u8>);impl P{
        fn int(&mut self,n:i32){if (0..=255).contains(&n){self.0.extend([b'K',n as u8]);}
            else if (0..=65535).contains(&n){self.0.push(b'M');self.0.extend((n as u16).to_le_bytes());}
            else{self.0.push(b'J');self.0.extend(n.to_le_bytes());}}
        fn key(&mut self,s:&[u8]){self.0.extend([b'U',s.len() as u8]);self.0.extend(s);}
        fn list(&mut self,a:[i32;6]){self.0.extend(b"](");for n in a{self.int(n);}self.0.push(b'e');}
    }
    let mut p=P(b"\x80\x02}(".to_vec());
    p.key(b"prevRev");p.int(wire_revision as i32);p.key(b"rev");p.int(wire_revision as i32+1);
    p.key(b"inventory");p.0.extend(b"}(");p.int(1);p.0.extend(b"}(");
    p.key(b"shells");p.0.extend(b"}(");p.int(layout.native as i32);
    p.list(std::array::from_fn(|i|if i%2==0{layout.layout[i].abs()}else{layout.layout[i]}));p.0.push(b'u');
    p.key(b"shellsLayout");p.0.extend(b"}(");p.int(layout.native as i32);p.0.extend(b"}(");
    p.0.push(b'(');p.int(i32::from(layout.turret));p.int(i32::from(layout.gun));p.0.push(b't');p.list(layout.layout);p.0.extend(b"uu");
    p.key(b"lock");p.0.extend(b"}(");p.int(layout.native as i32);p.0.extend(b"Nuuuu.");
    if p.0.len()>crate::ammo_service091::MAX_DELTA_BYTES{return Err(bad("native delta short envelope"));}
    crate::hangar091::validate_account_delta(&p.0)?;Ok(p.0)
}
/// Server-origin Account.update STRING only; no invented callback/request ID.
pub fn final_update(layout:&NativeLayout,wire_revision:i64)->io::Result<Vec<u8>>{
    let delta=final_delta(layout,wire_revision)?;let mut body=vec![delta.len() as u8];body.extend(delta);
    crate::hangar091::method(0x57,&body)
}

#[cfg(test)]
#[path="profile13_hold_projection_tests.rs"]
mod tests;
