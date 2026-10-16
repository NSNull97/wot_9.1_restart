//! Outgoing P10B primitive source-shape codec. No incoming pickle or storage.
//! Recipient aliases are explicit LAB policy; historical server IDs UNKNOWN.
use std::{collections::BTreeSet,io};
use super::{aliases,wire};
pub const MAX_RAW:usize=16384;
pub const MAX_LIST_ROWS:usize=50;
pub const MAX_PREVIEW_ALIASES:usize=512;
pub const MAX_PREVIEW_ROOMS:usize=512;
pub const PREVIEW_ALIAS_START:u32=aliases::OWN_ENTITY_ID+1024;
fn bad()->io::Error{io::Error::new(io::ErrorKind::InvalidData,"bounded native training list/preview")}
type Result<T>=io::Result<T>;
fn id(n:u32)->bool{n>0&&n<=i32::MAX as u32}
fn name(s:&str)->bool{(3..=24).contains(&s.chars().count())&&s.len()<=48&&!s.chars().any(char::is_control)}
fn time(n:f64)->bool{n.is_finite()&&(0. ..=1e12).contains(&n)}

#[derive(Clone,Debug,PartialEq)]pub struct ListRow{
    pub native_room_id:u32,pub created_seconds:f64,pub arena_type:i32,pub creator:String,pub creator_database_id:i32,
    pub players:u8,pub opened:bool,pub comment:String,pub creator_clan_abbrev:String,pub creator_igr_type:u8,
}
#[derive(Clone,Debug,PartialEq)]pub struct Listing{pub total:u32,pub rows:Vec<ListRow>}
#[derive(Clone,Debug,PartialEq)]pub struct PreviewMember{
    pub canonical:aliases::Canonical,pub membership:u64,pub row:wire::Member,
}
#[derive(Clone,Debug,PartialEq)]pub struct Preview{
    pub room_key:u64,pub native_room_id:u32,pub revision:u64,pub members:Vec<PreviewMember>,
}
#[derive(Clone,Debug,PartialEq,Eq)]struct Entry{room:u64,canonical:aliases::Canonical,membership:u64,alias:u32,active:bool}
#[derive(Clone,Debug,PartialEq,Eq)]struct View{room:u64,native:u32,revision:u64,members:Vec<(aliases::Canonical,u64)>}
#[derive(Clone,Debug,PartialEq,Eq)]pub struct PreviewBook{recipient:aliases::Canonical,entries:Vec<Entry>,views:Vec<View>}
impl PreviewBook{
    pub fn new(recipient:aliases::Canonical)->Result<Self>{
        if recipient.account==[0;16]||recipient.auth_generation==0{return Err(bad());}Ok(Self{recipient,entries:Vec::new(),views:Vec::new()})
    }
    pub fn allocated(&self)->usize{self.entries.len()}
    fn alias(&mut self,room:u64,member:&PreviewMember)->Result<u32>{
        if member.canonical==self.recipient{return Ok(aliases::OWN_ENTITY_ID);}
        if let Some(e)=self.entries.iter().find(|e|e.active&&e.room==room&&e.canonical==member.canonical&&e.membership==member.membership){return Ok(e.alias);}
        if self.entries.len()>=MAX_PREVIEW_ALIASES{return Err(bad());}
        let alias=PREVIEW_ALIAS_START.checked_add(self.entries.len()as u32).ok_or_else(bad)?;
        if !id(alias){return Err(bad());}self.entries.push(Entry{room,canonical:member.canonical,membership:member.membership,alias,active:true});Ok(alias)
    }
    fn view(&mut self,p:&Preview)->Result<()>{
        let members=p.members.iter().map(|m|(m.canonical,m.membership)).collect::<Vec<_>>();
        if let Some(old)=self.views.iter_mut().find(|v|v.room==p.room_key){
            if old.native!=p.native_room_id||old.revision>p.revision||old.revision==p.revision&&old.members!=members{return Err(bad());}
            old.revision=p.revision;old.members=members.clone();
        }else{
            if self.views.len()>=MAX_PREVIEW_ROOMS{return Err(bad());}
            self.views.push(View{room:p.room_key,native:p.native_room_id,revision:p.revision,members:members.clone()});
        }
        for e in self.entries.iter_mut().filter(|e|e.room==p.room_key){e.active&=members.contains(&(e.canonical,e.membership));}
        Ok(())
    }
}
struct P{b:Vec<u8>}
impl P{
    fn new()->Self{Self{b:vec![0x80,2]}}
    fn raw(&mut self,b:&[u8])->Result<()>{if self.b.len()+b.len()>MAX_RAW{return Err(bad());}self.b.extend(b);Ok(())}
    fn n(&mut self,n:i32)->Result<()>{if(0..=255).contains(&n){self.raw(&[b'K',n as u8])}else if(0..=65535).contains(&n){self.raw(&[b'M',(n as u16)as u8,((n as u16)>>8)as u8])}else{self.raw(&[b'J'])?;self.raw(&n.to_le_bytes())}}
    fn f(&mut self,n:f64)->Result<()>{if !time(n){return Err(bad());}self.raw(b"G")?;self.raw(&n.to_be_bytes())}
    fn u(&mut self,s:&str)->Result<()>{self.raw(b"X")?;self.raw(&(s.len()as u32).to_le_bytes())?;self.raw(s.as_bytes())}
    fn s(&mut self,s:&str)->Result<()>{if s.len()>8||!s.is_ascii()||s.bytes().any(|b|b.is_ascii_control()){return Err(bad());}self.raw(&[b'U',s.len()as u8])?;self.raw(s.as_bytes())}
    fn boolean(&mut self,b:bool)->Result<()>{self.raw(&[if b{0x88}else{0x89}])}
    fn finish(mut self)->Result<Vec<u8>>{self.raw(b".")?;Ok(self.b)}
}

pub fn list_raw(list:&Listing)->Result<Vec<u8>>{
    if list.rows.len()>MAX_LIST_ROWS||list.total>i32::MAX as u32||list.total<(list.rows.len()as u32){return Err(bad());}
    let mut seen=BTreeSet::new();
    for r in &list.rows{
        if !id(r.native_room_id)||!seen.insert(r.native_room_id)||!time(r.created_seconds)||![1,4].contains(&r.arena_type)
            ||!name(&r.creator)||r.creator_database_id<=0||!(1..=6).contains(&r.players)||r.comment.len()>64
            ||r.comment.chars().any(char::is_control)||r.creator_igr_type>2{return Err(bad());}
    }
    let mut p=P::new();p.raw(b"(")?;p.n(2)?;p.n(list.total as i32)?;p.raw(b"](")?;
    for r in &list.rows{p.raw(b"(")?;p.f(r.created_seconds)?;p.n(r.native_room_id as i32)?;p.raw(b"}(")?;
        // Exact source cache keys. Division intentionally omitted: the original
        // consumer's default0 applies; no historical division is fabricated.
        p.n(2)?;p.boolean(r.opened)?;p.n(5)?;p.n(i32::from(r.players))?;p.n(6)?;p.u(&r.creator)?;
        p.n(9)?;p.u(&r.comment)?;p.n(11)?;p.n(r.arena_type)?;p.n(15)?;p.s(&r.creator_clan_abbrev)?;
        p.n(17)?;p.n(i32::from(r.creator_igr_type))?;p.n(18)?;p.n(r.creator_database_id)?;p.raw(b"ut")?;
    }p.raw(b"et")?;p.finish()
}

pub fn preview_raw(book:&mut PreviewBook,preview:&Preview)->Result<Vec<u8>>{
    if preview.room_key==0||!id(preview.native_room_id)||preview.revision==0||preview.members.is_empty()||preview.members.len()>6{return Err(bad());}
    let(mut accounts,mut databases)=(BTreeSet::new(),BTreeSet::new());let mut staged=book.clone();let mut p=P::new();
    staged.view(preview)?;
    p.raw(b"(")?;p.n(preview.native_room_id as i32)?;p.raw(b"](")?;
    for m in &preview.members{
        if m.canonical.account==[0;16]||m.canonical.auth_generation==0||m.membership==0
            ||m.canonical.account==book.recipient.account&&m.canonical!=book.recipient
            ||!accounts.insert(m.canonical.account)||!databases.insert(m.row.database_id){return Err(bad());}
        let mut row=m.row.clone();row.entity_id=staged.alias(preview.room_key,m)?;
        // Reuse the existing source-bound ten-field primitive row encoder and
        // all its identity/descriptor/roster/state bounds. Only OUR freshly
        // generated fixed envelope is unwrapped; no incoming pickle is parsed.
        let body=wire::player_added(&row).map_err(|_|bad())?;
        if body.len()<8||body[..2]!=[0x13,0x56]||body[3]!=2||body[5..7]!=[0x80,2]||body.last()!=Some(&b'.'){return Err(bad());}
        p.raw(&body[7..body.len()-1])?;
    }p.raw(b"et")?;let raw=p.finish()?;*book=staged;Ok(raw)
}
pub fn list_stream(list:&Listing)->Result<Vec<Vec<u8>>>{
    crate::hangar091::stream_with_budget(200,&list_raw(list)?,Vec::new(),MAX_RAW)
}
pub fn preview_stream(book:&mut PreviewBook,preview:&Preview)->Result<Vec<Vec<u8>>>{
    let mut staged=book.clone();let raw=preview_raw(&mut staged,preview)?;
    let bodies=crate::hangar091::stream_with_budget(201,&raw,Vec::new(),MAX_RAW)?;*book=staged;Ok(bodies)
}

#[cfg(test)]#[path="list_preview_tests.rs"]mod tests;
