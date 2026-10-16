//! #717 DetachedTurret boundary. Type8 is the PE-bound client-script index,
//! not entities.xml ordinal42. Native execution remains a separate gate.
//! Callers own terminal/physics/visibility authority and stage this book with
//! the actual Session/Window clone; no coordinates or native IDs enter domain.
use std::{f32::consts::PI,io};
use super::vehicle_profile::VehicleKind;

pub(super) const MAX_TURRETS:usize=6;
pub(super) const CLIENT_TYPE:u16=8;
const MAX_SELECTIVE:usize=256;
const ID_BASE:u32=0x0912_0001;
const ALIAS_BASE:u8=248;
fn bad(why:&'static str)->io::Error{io::Error::new(io::ErrorKind::InvalidData,why)}
fn slot_ok(slot:usize)->io::Result<()>{if slot<MAX_TURRETS{Ok(())}else{Err(bad("detached turret slot bound"))}}

#[derive(Clone,Copy,Debug,PartialEq)]
pub(super) struct Pose {
    pub position:[f32;3],
    /// Server pose order yaw/pitch/roll. Volatile wire order differs.
    pub direction:[f32;3],
}
impl Pose {
    pub(super) fn validate(self)->io::Result<()>{
        if self.position.iter().any(|x|!x.is_finite()||x.abs()>2000.)
            ||self.direction.iter().any(|x|!x.is_finite()||x.abs()>PI){return Err(bad("detached turret finite local pose"));}
        Ok(())
    }
}
pub(super) fn entity_id(slot:usize)->io::Result<u32>{slot_ok(slot)?;Ok(ID_BASE+slot as u32)}
pub(super) fn alias(slot:usize)->io::Result<u8>{slot_ok(slot)?;Ok(ALIAS_BASE+slot as u8)}
pub(super) fn enter(slot:usize)->io::Result<Vec<u8>>{
    let mut b=vec![0x0a];b.extend(entity_id(slot)?.to_le_bytes());b.push(alias(slot)?);Ok(b)
}
/// None means a well-formed request belongs to another entity namespace.
/// No request alone grants visibility, creation, ownership or a descriptor.
pub(super) fn request(raw:&[u8])->io::Result<Option<usize>>{
    if raw.first()!=Some(&8){return Ok(None);}
    if raw.len()!=7||raw[..3]!=[8,4,0]{return Err(bad("detached turret request fixed shape"));}
    let id=u32::from_le_bytes(raw[3..7].try_into().map_err(|_|bad("turret request ID"))?);
    Ok(id.checked_sub(ID_BASE).filter(|n|*n<MAX_TURRETS as u32).map(|n|n as usize))
}
fn f3(b:&mut Vec<u8>,v:[f32;3]){for x in v{b.extend(x.to_le_bytes());}}
pub(super) fn create(slot:usize,kind:VehicleKind,pose:Pose,underwater:bool,colliding:bool)->io::Result<Vec<u8>>{
    slot_ok(slot)?;pose.validate()?;
    let descriptor=kind.descriptor();
    if descriptor.is_empty()||descriptor.len()>=255{return Err(bad("detached turret curated descriptor"));}
    let mut p=vec![0];p.extend(entity_id(slot)?.to_le_bytes());p.extend(CLIENT_TYPE.to_le_bytes());
    f3(&mut p,pose.position);f3(&mut p,pose.direction);
    p.extend([4,0,u8::from(underwater),1,u8::from(colliding),2]);
    p.extend(super::wire::vehicle_id(slot)?.to_le_bytes());
    p.extend([3,descriptor.len()as u8]);p.extend(descriptor);
    if p.len()>500{return Err(bad("detached turret create body budget"));}
    let mut b=vec![9];b.extend((p.len()as u16).to_le_bytes());b.extend(p);Ok(b)
}
pub(super) fn pose(slot:usize,tick:u32,value:Pose)->io::Result<Vec<u8>>{
    value.validate()?;if !(1000..=37_000).contains(&tick){return Err(bad("detached turret tick bound"));}
    let mut b=vec![0x0d,tick as u8,0x15];b.extend(entity_id(slot)?.to_le_bytes());f3(&mut b,value.position);
    f3(&mut b,[value.direction[2],value.direction[1],value.direction[0]]);Ok(b)
}
pub(super) fn leave(slot:usize)->io::Result<Vec<u8>>{
    let mut b=vec![0x0c,4,0];b.extend(entity_id(slot)?.to_le_bytes());Ok(b)
}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub(super) enum DeathKind{Exploded,Detached}
impl DeathKind{pub(super) fn native_health(self)->i16{match self{Self::Exploded=>-1,Self::Detached=>-2}}}
/// Parent Vehicle presentation only. Caller must already have committed one
/// actual terminal event; domain/result/owner HUD HP stays0, never negative.
/// None attacker reveals no entity reference when the real attacker is hidden.
pub(super) fn terminal_health(slot:usize,attacker:Option<usize>,reason:u8,kind:DeathKind)->io::Result<Vec<u8>>{
    if reason>10{return Err(bad("detached turret attack reason bound"));}
    let id=super::wire::vehicle_id(slot)?;let hp=kind.native_health();
    let mut b=vec![0x12];b.extend(id.to_le_bytes());b.push(0xa1);b.extend(hp.to_le_bytes());
    b.push(0x3c);b.extend(hp.to_le_bytes());
    b.extend(attacker.map(super::wire::vehicle_id).transpose()?.unwrap_or(0).to_le_bytes());b.extend([reason,0x13]);Ok(b)
}
/// Vehicle.showAmmoBayExplosion FIXED8, distinct from DetachedTurret creation.
/// These finite caps are codec budgets, not a historical launch/volume model.
pub(super) fn explosion(slot:usize,volume:f32,projected_speed:f32)->io::Result<Vec<u8>>{
    if !volume.is_finite()||!(0. ..=1_000_000.).contains(&volume)
        ||!projected_speed.is_finite()||!(0. ..=1000.).contains(&projected_speed){return Err(bad("ammo bay explosion finite FX inputs"));}
    let mut b=vec![0x12];b.extend(super::wire::vehicle_id(slot)?.to_le_bytes());b.push(0x3d);
    b.extend(volume.to_le_bytes());b.extend(projected_speed.to_le_bytes());b.push(0x13);Ok(b)
}

#[derive(Clone,Copy,Debug,Default,PartialEq,Eq)]
struct Desired{parent_epoch:Option<u32>,parent_created_acked:bool,parent_visible:bool,turret_visible:bool}
impl Desired{fn allowed(self)->bool{self.parent_epoch.is_some()&&self.parent_created_acked&&self.parent_visible&&self.turret_visible}}
#[derive(Clone,Copy,Debug,Default,PartialEq,Eq)]
pub(super) enum Entry{
    #[default] Hidden,
    Announced{parent_epoch:u32,enter_seq:u32,requested:bool},
    Created{parent_epoch:u32,enter_seq:u32,create_seq:u32,acked:bool},
    Leaving{leave_seq:u32},
}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub(super) enum ActionKind{Enter,Create,Leave}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub(super) struct Action{pub slot:usize,pub kind:ActionKind,revision:u64}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub(super) enum RequestDisposition{Queued,Duplicate,Stale}
#[derive(Clone,Debug,PartialEq,Eq)]
pub(super) struct Book{
    desired:[Desired;MAX_TURRETS],entries:[Entry;MAX_TURRETS],
    after_leave:[Option<u32>;MAX_TURRETS],revision:u64,last_queued:Option<u32>,
}
impl Default for Book{fn default()->Self{Self::new()}}
impl Book{
    pub(super) fn new()->Self{Self{desired:[Desired::default();MAX_TURRETS],entries:[Entry::Hidden;MAX_TURRETS],
        after_leave:[None;MAX_TURRETS],revision:0,last_queued:None}}
    pub(super) fn entry(&self,slot:usize)->Option<Entry>{self.entries.get(slot).copied()}
    pub(super) fn set_visibility(&mut self,slot:usize,parent_epoch:Option<u32>,parent_created_acked:bool,
        parent_visible:bool,turret_visible:bool)->io::Result<()>{
        slot_ok(slot)?;if parent_created_acked&&parent_epoch.is_none(){return Err(bad("turret parent ACK without epoch"));}
        let desired=Desired{parent_epoch,parent_created_acked,parent_visible,turret_visible};
        if self.desired[slot]!=desired{let rev=self.revision.checked_add(1).ok_or_else(||bad("turret book revision exhausted"))?;
            self.desired[slot]=desired;self.revision=rev;}Ok(())
    }
    fn current(&self,slot:usize,epoch:u32)->bool{self.desired[slot].allowed()&&self.desired[slot].parent_epoch==Some(epoch)}
    fn action_kind(&self,slot:usize)->Option<ActionKind>{match self.entries[slot]{
        Entry::Hidden if self.desired[slot].allowed()=>Some(ActionKind::Enter),
        Entry::Announced{parent_epoch,..}|Entry::Created{parent_epoch,..}if !self.current(slot,parent_epoch)=>Some(ActionKind::Leave),
        Entry::Announced{parent_epoch,requested:true,..}if self.current(slot,parent_epoch)=>Some(ActionKind::Create),
        _=>None,
    }}
    pub(super) fn transitions(&self)->Vec<Action>{(0..MAX_TURRETS).filter_map(|slot|self.action_kind(slot)
        .map(|kind|Action{slot,kind,revision:self.revision})).collect()}
    pub(super) fn propose(&self)->Option<Action>{self.transitions().into_iter().next()}
    /// Called ONLY after an actual authenticated native08 record was parsed.
    /// Enter being queued suffices; no invented enter-ACK barrier is imposed.
    pub(super) fn on_request(&mut self,slot:usize)->io::Result<RequestDisposition>{
        slot_ok(slot)?;let result=match self.entries[slot]{
            Entry::Announced{parent_epoch,enter_seq,requested}if self.current(slot,parent_epoch)=>{
                if requested{RequestDisposition::Duplicate}else{
                    self.entries[slot]=Entry::Announced{parent_epoch,enter_seq,requested:true};RequestDisposition::Queued}},
            Entry::Created{parent_epoch,..}if self.current(slot,parent_epoch)=>RequestDisposition::Duplicate,
            _=>RequestDisposition::Stale,
        };Ok(result)
    }
    /// Mark only after native enqueue returned this actual reliable sequence.
    /// Retransmission reuses Window bytes; it does not propose another enter.
    pub(super) fn mark_queued(&mut self,action:Action,sequence:u32)->io::Result<()>{
        slot_ok(action.slot)?;if action.revision!=self.revision{return Err(bad("stale turret action revision"));}
        let slot=action.slot;
        let repeat=match(self.entries[slot],action.kind){
            (Entry::Announced{enter_seq,..},ActionKind::Enter)=>enter_seq==sequence,
            (Entry::Created{create_seq,..},ActionKind::Create)=>create_seq==sequence,
            (Entry::Leaving{leave_seq},ActionKind::Leave)=>leave_seq==sequence,_=>false,
        };
        if repeat{return Ok(());}
        if self.action_kind(slot)!=Some(action.kind)||self.last_queued.is_some_and(|last|sequence<last){return Err(bad("turret queued action/sequence changed"));}
        let entry=match(action.kind,self.entries[slot]){
            (ActionKind::Enter,Entry::Hidden)if self.after_leave[slot].is_none_or(|last|sequence>last)=>Entry::Announced{
                parent_epoch:self.desired[slot].parent_epoch.ok_or_else(||bad("turret enter without parent"))?,enter_seq:sequence,requested:false},
            (ActionKind::Create,Entry::Announced{parent_epoch,enter_seq,requested:true})if sequence>enter_seq=>Entry::Created{parent_epoch,enter_seq,create_seq:sequence,acked:false},
            (ActionKind::Leave,Entry::Announced{enter_seq,..})if sequence>enter_seq=>Entry::Leaving{leave_seq:sequence},
            (ActionKind::Leave,Entry::Created{create_seq,..})if sequence>create_seq=>Entry::Leaving{leave_seq:sequence},
            _=>return Err(bad("turret queue phase or leave sequence barrier")),
        };self.entries[slot]=entry;self.last_queued=Some(sequence);Ok(())
    }
    /// Only validated transport ACKs. Cumulative equality does not ACK its
    /// sequence; selective ACK0 is valid. Return slots whose leave completed.
    pub(super) fn ack(&mut self,cumulative:u32,selective:&[u32])->io::Result<Vec<usize>>{
        if selective.len()>MAX_SELECTIVE{return Err(bad("turret selective ACK bound"));}
        let mut left=Vec::with_capacity(MAX_TURRETS);
        for slot in 0..MAX_TURRETS{match self.entries[slot]{
            Entry::Created{parent_epoch,enter_seq,create_seq,acked:false}if cumulative>create_seq||selective.contains(&create_seq)=>{
                self.entries[slot]=Entry::Created{parent_epoch,enter_seq,create_seq,acked:true};},
            Entry::Leaving{leave_seq}if cumulative>leave_seq||selective.contains(&leave_seq)=>{
                self.entries[slot]=Entry::Hidden;self.after_leave[slot]=Some(leave_seq);left.push(slot);},_=>{},
        }}Ok(left)
    }
    pub(super) fn pose_allowed(&self,slot:usize)->bool{slot<MAX_TURRETS&&matches!(self.entries[slot],
        Entry::Created{parent_epoch,acked:true,..}if self.current(slot,parent_epoch))}
}

#[cfg(test)]
#[path="detached_turret_tests.rs"]mod tests;
