//! Actual async readonly selection driver. All publication commits clone Sessions
//! and Controller; worker execution starts only after native receive has committed.
use super::*;
use std::collections::{BTreeMap,VecDeque};
use crate::training091::{domain as d,controller::{Controller,Call,ReadyTask,Batch},adapter::NativeFacts,current_room::{Channel,ProfileStamp}};
use super::super::{p10b_selection_job as query,p10b_writer::ReadySelection};

fn bad(message:&'static str)->io::Error{io::Error::new(io::ErrorKind::InvalidData,message)}
pub(super) fn account(text:&str)->io::Result<d::Account>{
    let bytes=text.as_bytes();if bytes.len()!=36{return Err(bad("P10B owner UUID"));}
    let mut compact=String::new();for(i,&b)in bytes.iter().enumerate(){if[8,13,18,23].contains(&i){if b!=b'-'{return Err(bad("P10B UUID separators"));}}else{compact.push(char::from(b));}}
    let mut out=[0;16];for(i,pair)in compact.as_bytes().chunks_exact(2).enumerate(){
        let s=std::str::from_utf8(pair).map_err(|_|bad("P10B UUID UTF8"))?;
        out[i]=u8::from_str_radix(s,16).map_err(|_|bad("P10B UUID hex"))?;
    }if out==[0;16]{return Err(bad("P10B zero owner"));}Ok(d::Account(out))
}
pub(super) fn source_binding(s:&Session)->io::Result<[u8;32]>{
    let owner=s.identity.as_ref().ok_or_else(||bad("P10B identity absent"))?;
    let text=crate::identity091::room_selection::source_binding(owner)?;
    if text.len()!=64{return Err(bad("P10B source hash length"));}let mut bytes=[0;32];
    for(i,pair)in text.as_bytes().chunks_exact(2).enumerate(){bytes[i]=u8::from_str_radix(std::str::from_utf8(pair).map_err(|_|bad("P10B source hash UTF8"))?,16).map_err(|_|bad("P10B source hash hex"))?;}
    if bytes==[0;32]{return Err(bad("P10B empty source hash"));}Ok(bytes)
}
pub(super) fn current_call(s:&Session,source:[u8;32])->io::Result<Call>{
    if !s.training_account_ready(){return Err(bad("P10B actual Account unavailable"));}
    let owner=s.identity.as_ref().ok_or_else(||bad("P10B identity absent"))?;
    let revision=u32::try_from(s.ammo_service.as_ref().ok_or_else(||bad("P10B ammo metadata absent"))?.revision()).map_err(|_|bad("P10B revision width"))?;
    Ok(Call{caller:d::AuthLease{account:account(&owner.account_id)?,generation:u64::from(s.id)},
        channel:Channel{session:s.id,generation:s.training_account_generation()},profile:ProfileStamp{revision,source_binding:source},expected_revision:revision})
}
#[derive(Clone)]pub(super) struct Accepted{pub(super) task:ReadyTask,pub(super) selection:ReadySelection}
#[derive(Default)]pub(super) struct Manager{
    queued:VecDeque<ReadyTask>,pending:Option<(ReadyTask,query::Job)>,
    completed:Option<(ReadyTask,Result<query::Completion,String>)>,
    pub(super) accepted:BTreeMap<d::Account,Accepted>,
}
impl Manager{
    pub(super) fn busy(&self)->bool{self.pending.is_some()||self.completed.is_some()||!self.queued.is_empty()}
    pub(super) fn can_enqueue(&self,tasks:&[ReadyTask])->io::Result<()>{
        if self.queued.len()+usize::from(self.pending.is_some()||self.completed.is_some())+tasks.len()>d::MAX_ACCOUNTS{return Err(bad("P10B readiness queue full"));}
        Ok(())
    }
    pub(super) fn enqueue(&mut self,tasks:Vec<ReadyTask>)->io::Result<()>{self.can_enqueue(&tasks)?;self.queued.extend(tasks);Ok(())}
    pub(super) fn facts(&self,sessions:&[Session],engine:&Controller)->io::Result<BTreeMap<d::Account,NativeFacts>>{
        let mut facts=BTreeMap::new();
        for s in sessions{
            let Some(owner)=s.identity.as_ref()else{continue;};let who=account(&owner.account_id)?;
            let ready=engine.registry().claim(who).and_then(|claim|if let d::Claim::Room(room)=claim{engine.registry().room(room)}else{None})
                .and_then(|room|room.members().find(|m|m.account()==who)).and_then(|m|m.ready());
            let accepted=self.accepted.get(&who).filter(|a|Some(a.selection.reference())==ready);
            let(selected,descriptor)=match accepted{Some(a)=>(Some(a.selection.reference().clone()),a.selection.frozen().descriptor.clone()),None=>(None,Vec::new())};
            if ready.is_some()&&selected.is_none(){return Err(bad("P10B room lost verified ready selection"));}
            facts.insert(who,NativeFacts{database_id:owner.database_id,selected,descriptor,igr_type:0,clan_database_id:0,clan_abbrev:String::new()});
        }Ok(facts)
    }
    fn publish(sessions:&mut Vec<Session>,engine:&Controller,batch:&Batch)->io::Result<()>{
        for(who,bodies)in &batch.bodies{
            let target=sessions.iter_mut().find(|s|s.identity.as_ref().is_some_and(|p|account(&p.account_id).ok()==Some(*who))).ok_or_else(||bad("P10B callback recipient missing"))?;
            let owner=target.identity.as_ref().ok_or_else(||bad("P10B callback owner absent"))?;
            if !engine.is_current_recipient(d::AuthLease{account:*who,generation:u64::from(target.id)},Channel{session:target.id,generation:target.training_account_generation()},owner.database_id){return Err(bad("P10B callback Account incarnation changed"));}
            if target.outbox.len()+bodies.len()>128||target.outbox.iter().chain(bodies).map(Vec::len).sum::<usize>()>65536{return Err(bad("P10B publication queue full"));}
            target.outbox.extend(bodies.iter().cloned());
        }for session in sessions.iter_mut(){session.drain_outbox()?;}Ok(())
    }
    fn fail(&mut self,task:&ReadyTask,sessions:&mut Vec<Session>,engine:&mut Controller)->io::Result<()>{
        let mut next_engine=engine.clone();let mut next_sessions=sessions.clone();
        let batch=next_engine.finish_ready_failure(task).map_err(|_|bad("P10B readiness failure stale"))?;
        Self::publish(&mut next_sessions,&next_engine,&batch)?;
        *engine=next_engine;*sessions=next_sessions;Ok(())
    }
    pub(super) fn poll(&mut self,sessions:&mut Vec<Session>,engine:&mut Controller,now_ms:u64)->io::Result<()>{
        if let Some(result)=self.pending.as_mut().and_then(|(_,job)|job.poll()){
            let(task,_)=self.pending.take().ok_or_else(||bad("P10B readiness task vanished"))?;
            self.completed=Some((task,result.map_err(|e|e.to_string())));
        }
        let Some((task,result))=self.completed.as_ref()else{return Ok(());};let task=task.clone();
        let result=result.clone();
        let accepted=(||->io::Result<(Vec<Session>,Controller,Accepted,Batch)>{
            let completion=result.map_err(|e|io::Error::new(io::ErrorKind::InvalidData,e))?;
            let mut next_sessions=sessions.clone();let mut next_engine=engine.clone();
            let target=next_sessions.iter_mut().find(|s|s.id==task.channel().session).ok_or_else(||bad("P10B readiness Session retired"))?;
            let current=current_call(target,source_binding(target)?)?;
            if current.caller!=task.caller()||current.channel!=task.channel()||current.profile!=task.profile()||current.expected_revision!=task.expected_revision()
                ||completion.task.session!=target.id||completion.task.expected_revision!=u64::from(task.expected_revision())||completion.task.native_inventory_id!=task.native_inventory()
                ||completion.task.owner.account_id!=target.identity.as_ref().ok_or_else(||bad("P10B readiness owner lost"))?.account_id
                ||!target.ammo_service.as_ref().is_some_and(ammo_session::State::idle)
                ||!target.shared.as_ref().and_then(|c|c.profile13.as_ref()).is_some_and(|p|p.garage_idle()){
                return Err(bad("P10B readonly selection origin changed"));
            }
            let snapshot=completion.snapshot;
            let old=target.identity.as_ref().ok_or_else(||bad("P10B current owner missing"))?;
            let request=snapshot.selection.request();
            if snapshot.binding.revision!=u64::from(task.expected_revision())||snapshot.owner.database_id!=old.database_id
                ||snapshot.owner.account_id!=old.account_id||snapshot.owner.name!=old.name
                ||completion.task.owner.database_id!=old.database_id||completion.task.run_id!=request.run_id
                ||request.projection_stamp.native_state_sha256!=snapshot.fixtures.state_sha256().iter().map(|b|format!("{b:02x}")).collect::<String>()
                ||request.projection_stamp.owner_source_sha256!=task.profile().source_binding.iter().map(|b|format!("{b:02x}")).collect::<String>(){
                return Err(bad("P10B fresh selection CAS/native/source mismatch"));}

            let selection=ReadySelection::from_selection(snapshot.owner.clone(),target.id,snapshot.selection)?;
            let item=Accepted{task:task.clone(),selection};
            target.identity=Some(snapshot.owner);target.hangar=Some(snapshot.fixtures);
            target.ammo_service.as_mut().ok_or_else(||bad("P10B ammo state lost"))?.replace_pool(target.hangar.as_ref().and_then(|f|f.p04m_binding()).cloned())?;
            target.shared.as_mut().and_then(|c|c.profile13.as_mut()).ok_or_else(||bad("P10B profile state missing"))?.revision=snapshot.binding.revision;
            let mut facts=self.facts(&next_sessions,&next_engine)?;
            facts.retain(|who,fact|next_sessions.iter().any(|s|s.identity.as_ref().is_some_and(|p|account(&p.account_id).ok()==Some(*who))
                &&next_engine.is_current_recipient(d::AuthLease{account:*who,generation:u64::from(s.id)},Channel{session:s.id,generation:s.training_account_generation()},fact.database_id)));
            facts.insert(task.caller().account,NativeFacts{database_id:target_database(&next_sessions,task.channel().session)?,selected:Some(item.selection.reference().clone()),descriptor:item.selection.frozen().descriptor.clone(),igr_type:0,clan_database_id:0,clan_abbrev:String::new()});
            let batch=next_engine.complete_ready(&task,current,task.native_inventory(),item.selection.reference().clone(),&facts,now_ms).map_err(|_|bad("P10B readiness Controller origin changed"))?;
            Ok((next_sessions,next_engine,item,batch))
        })();
        match accepted{
            Ok((mut next_sessions,next_engine,item,batch))=>{Self::publish(&mut next_sessions,&next_engine,&batch)?;*sessions=next_sessions;*engine=next_engine;self.accepted.insert(task.caller().account,item);println!("P10B_READY session={} room={} revision={} owned_readonly=true",task.channel().session,task.room().0,task.expected_revision());},
            Err(error)=>{println!("P10B_READY_REFUSED session={} error={error} reserve_started=false",task.channel().session);self.fail(&task,sessions,engine)?;},
        }self.completed=None;Ok(())
    }
    pub(super) fn start(&mut self,sessions:&mut Vec<Session>,engine:&mut Controller,config:Arc<crate::identity091::Config>,external_idle:bool)->io::Result<()>{
        if !external_idle||self.pending.is_some()||self.completed.is_some(){return Ok(());}let Some(task)=self.queued.pop_front()else{return Ok(());};
        let started=(||->io::Result<query::Job>{
            let s=sessions.iter().find(|s|s.id==task.channel().session).ok_or_else(||bad("P10B readonly queued Session missing"))?;
            let call=current_call(s,source_binding(s)?)?;
            if call.caller!=task.caller()||call.channel!=task.channel()||call.profile!=task.profile()
                ||!s.ammo_service.as_ref().is_some_and(ammo_session::State::idle)
                ||!s.shared.as_ref().and_then(|c|c.profile13.as_ref()).is_some_and(|p|p.garage_idle()){
                return Err(bad("P10B queued readiness stale/busy"));}
            query::Job::start(query::Task{session:s.id,owner:s.identity.clone().ok_or_else(||bad("P10B identity missing"))?,expected_revision:u64::from(task.expected_revision()),native_inventory_id:task.native_inventory(),run_id:config.battle_run_id.clone()},config)
        })();
        match started{Ok(job)=>self.pending=Some((task,job)),Err(error)=>{println!("P10B_READY_START_REFUSED error={error}");self.completed=Some((task,Err(error.to_string())));}}Ok(())
    }
}
fn target_database(sessions:&[Session],id:u32)->io::Result<i32>{sessions.iter().find(|s|s.id==id).and_then(|s|s.identity.as_ref()).map(|p|p.database_id).ok_or_else(||bad("P10B native database absent"))}
