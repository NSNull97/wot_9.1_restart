//! Candidate32: a known garage mutation and its read-only publication are
//! separate phases. No code here can issue/reissue a mutation.
use super::*;
use std::thread::JoinHandle;
use sha2::{Digest,Sha256};

const RETRY:Duration=Duration::from_secs(2);
const OBSERVATION:Duration=Duration::from_secs(90);
const MAX_READ_ATTEMPTS:u8=3;

#[derive(Debug)]
enum Containment{MalformedKnown,ReadAttempts,ReadWorkerStart,ObservationDeadline,RecipientSourceChanged}
impl std::fmt::Display for Containment{
    fn fmt(&self,f:&mut std::fmt::Formatter<'_>)->std::fmt::Result{write!(f,"garage Fresh contained: {self:?}")}
}
impl std::error::Error for Containment{}

fn known_reply(revision:u64,wire:i64,r:&identity091::AmmoReply)->io::Result<()>{
    let next_revision=if r.serviced{revision.checked_add(1).ok_or_else(invalid)?}else{revision};
    let next_wire=if r.serviced{wire.checked_add(1).ok_or_else(invalid)?}else{wire};
    if r.revision!=next_revision||r.wire_revision!=next_wire||r.pool.is_some()
        ||!r.serviced&&(!r.update.is_empty()||r.recruitment.is_some()){return Err(invalid());}
    Ok(())
}

// Opaque channel identity, held only in memory. Deliberately no Debug,
// Display/Serialize/hash dump: gameplay observer guards never expose secrets.
struct Channel {
    key:[u8;16],login_peer:std::net::SocketAddr,base_peer:Option<std::net::SocketAddr>,
    handoff:u32,token:u32,attempt:Option<LoginAttempt>,
}
impl Channel {
    fn capture(s:&Session)->Self{Self{key:s.key,login_peer:s.login_peer,base_peer:s.base_peer,
        handoff:s.handoff,token:s.token,attempt:s.login_attempt}}
    fn matches(&self,s:&Session)->bool{self.key==s.key&&self.login_peer==s.login_peer&&self.base_peer==s.base_peer
        &&self.handoff==s.handoff&&self.token==s.token&&self.attempt==s.login_attempt}
}

struct Anchor {
    owner:Arc<identity091::Profile>,
    state_sha:[u8;32],
    command:Command,
    prefix:String,
    revision:u64,
    wire:i64,
    account_epoch:u64,
    pool:Arc<crate::p04m_companion091::Binding>,
    command_key:String,
    channel:Channel,
}
impl Anchor {
    fn capture(s:&Session,request:&Command)->io::Result<Self>{
        available(s)?;
        let state=s.ammo_service.as_ref().ok_or_else(invalid)?;
        let owner=s.identity.clone().ok_or_else(invalid)?;
        let fixtures=s.hangar.as_ref().ok_or_else(invalid)?;
        let client=s.shared.as_ref().ok_or_else(invalid)?;
        let pool=state.pool.clone().ok_or_else(invalid)?;
        if !client.profile13_garage_idle()||!pool.matches(&owner.account_id,owner.database_id,state.revision)
            ||!pool.matches_state(fixtures.state_bytes()){return Err(invalid());}
        Ok(Self{owner,state_sha:fixtures.state_sha256(),command:request.clone(),prefix:state.prefix.clone(),
            revision:state.revision,wire:state.wire_revision,account_epoch:client.account_incarnation(),
            command_key:state.command_key(request),channel:Channel::capture(s),pool})
    }
    fn recipient(&self,s:&Session)->bool{
        // Used only to select whom existing caller containment may retire.
        // A replacement/foreign Account epoch must never be closed for this
        // old observer's error or receive its cache/delta.
        self.channel.matches(s)&&s.identity.as_ref().is_some_and(|o|o.account_id==self.owner.account_id
            &&o.database_id==self.owner.database_id&&o.name==self.owner.name)
            &&s.shared.as_ref().is_some_and(|c|c.account_incarnation()==self.account_epoch)
    }
    fn current(&self,s:&Session)->bool{
        // A new Account/native epoch never inherits an old observer. Pending
        // commands and used IDs may grow while this one is in flight.
        s.active && available(s).is_ok()&&s.shared.as_ref().is_some_and(|c|c.profile13_garage_idle())
            &&s.identity.as_ref().is_some_and(|o|o.account_id==self.owner.account_id
            &&o.database_id==self.owner.database_id&&o.name==self.owner.name&&o.fixture_dir==self.owner.fixture_dir)
            &&s.hangar.as_ref().is_some_and(|h|h.state_sha256()==self.state_sha)
            &&s.shared.as_ref().is_some_and(|c|c.account_incarnation()==self.account_epoch)
            &&s.ammo_service.as_ref().is_some_and(|a|a.revision==self.revision&&a.wire_revision==self.wire
                &&a.prefix==self.prefix&&a.inflight.as_ref()==Some(&self.command)
                &&a.pool.as_deref()==Some(self.pool.as_ref()))
    }
    fn known(&self,r:&identity091::AmmoReply)->io::Result<()>{
        known_reply(self.revision,self.wire,r)
    }
}

struct Fresh {
    owner:Arc<identity091::Profile>,
    fixtures:Arc<crate::hangar091::Fixtures>,
    pool:Arc<crate::p04m_companion091::Binding>,
    revision:u64,
}
impl Fresh {
    fn load(config:&identity091::Config,owner:&identity091::Profile,revision:u64)->io::Result<Self>{
        // Fixed read-only profile endpoint. It validates original identity,
        // pool/mixed/loss/hold companions using the selected config mode.
        let next=config.refresh_battle_profile(owner)?;
        let metadata=codec::metadata_research(&next.fixture_dir,&next.account_id,next.database_id)?;
        let fixtures=crate::hangar091::Fixtures::load_p04m(&next.fixture_dir)?;
        let pool=fixtures.p04m_binding().cloned().ok_or_else(invalid)?;
        if next.fixture_dir==owner.fixture_dir||metadata.revision!=revision||metadata.wire_revision!=1
            ||!pool.matches(&next.account_id,next.database_id,revision)||!pool.matches_state(fixtures.state_bytes()){
            return Err(invalid());
        }
        Ok(Self{owner:Arc::new(next),fixtures:Arc::new(fixtures),pool,revision})
    }
}

/// Lives in the original singleton garage Job, never in a cloned receive
/// frame. Dropping an observer is not cancellation of its committed SQL.
pub(super) struct Flow {
    anchor:Anchor,
    config:Arc<identity091::Config>,
    known:Option<identity091::AmmoReply>,
    fresh:Option<Fresh>,
    reader:Option<mpsc::Receiver<io::Result<Fresh>>>,
    worker:Option<JoinHandle<()>>,
    retry_at:Instant,
    known_at:Option<Instant>,
    read_attempts:u8,
}
impl Flow {
    pub(super) fn capture(s:&Session,request:&Command,config:Arc<identity091::Config>)->io::Result<Self>{
        if !config.p04m_pool{return Err(invalid());}
        Ok(Self{anchor:Anchor::capture(s,request)?,config,known:None,fresh:None,reader:None,worker:None,
            retry_at:Instant::now(),known_at:None,read_attempts:0})
    }
    #[cfg(test)]
    pub(super) fn known_for_test(&self)->Option<(u64,i64,bool)>{self.known.as_ref().map(|r|(r.revision,r.wire_revision,r.serviced))}
    #[cfg(test)]
    pub(super) fn attempts_for_test(&self)->u8{self.read_attempts}
    fn contain(&self,session:u32,request:i16,reason:Containment)->io::Error{
        let key_sha=format!("{:x}",Sha256::digest(self.anchor.command_key.as_bytes()));
        println!("P04M_GARAGE_FRESH_CONTAINED session={session} request={request} reason={reason:?} key_sha256={key_sha} source_revision={} known_revision={} read_attempts={} reconnect_required=true mutation_reissued=false durable_ledger_retained=true",
            self.anchor.revision,self.known.as_ref().map_or(0,|r|r.revision),self.read_attempts);
        io::Error::new(io::ErrorKind::TimedOut,reason)
    }
    fn worker_running(&self)->bool{self.worker.as_ref().is_some_and(|w|!w.is_finished())}
    fn join_finished(&mut self)->io::Result<()>{
        if self.worker.as_ref().is_some_and(JoinHandle::is_finished){
            if self.worker.take().ok_or_else(invalid)?.join().is_err(){return Err(invalid());}
        }
        Ok(())
    }
    fn refresh(&mut self,session:u32,request:i16,now:Instant)->io::Result<()>{
        if self.worker_running(){return Ok(());}
        self.join_finished()?;
        if let Some(reader)=&self.reader {
            let result=match reader.try_recv(){
                Ok(result)=>result,
                Err(mpsc::TryRecvError::Empty)=>return Ok(()),
                Err(mpsc::TryRecvError::Disconnected)=>Err(invalid()),
            };
            self.reader=None;
            match result{
                Ok(fresh)=>self.fresh=Some(fresh),
                Err(error)=>{
                    self.retry_at=now+RETRY;
                    println!("P04M_GARAGE_FRESH_RETRY session={session} request={request} error={error} durable_reply_retained=true mutation_reissued=false");
                }
            }
        }
        if self.fresh.is_some()||self.reader.is_some()||now<self.retry_at{return Ok(());}
        if self.read_attempts>=MAX_READ_ATTEMPTS{return Err(self.contain(session,request,Containment::ReadAttempts));}
        let owner=self.anchor.owner.clone();let config=self.config.clone();
        let revision=self.known.as_ref().ok_or_else(invalid)?.revision;
        let(sender,receiver)=mpsc::sync_channel(1);
        let worker=thread::Builder::new().name("local-garage-fresh".into()).spawn(move||{
            let result=std::panic::catch_unwind(std::panic::AssertUnwindSafe(||Fresh::load(&config,&owner,revision)))
                .unwrap_or_else(|_|Err(invalid()));
            if sender.send(result).is_err(){println!("P04M_GARAGE_FRESH_OBSERVER_RETIRED session={session} request={request} mutation_reissued=false");}
        });
        let worker=match worker{Ok(worker)=>worker,Err(error)=>{
            println!("P04M_GARAGE_FRESH_THREAD_ERROR session={session} request={request} error={error} durable_reply_retained=true");
            return Err(self.contain(session,request,Containment::ReadWorkerStart));
        }};
        self.read_attempts+=1;self.reader=Some(receiver);self.worker=Some(worker);Ok(())
    }
    fn publish(&self,s:&mut Session,request:i16)->io::Result<bool>{
        if !self.anchor.current(s){return Err(invalid());}
        let reply=self.known.as_ref().ok_or_else(invalid)?;
        let count=if reply.serviced{2}else{1};
        if s.outbox.len()+count>128{return Ok(false);}
        let mut next=s.clone();
        let pool=if reply.serviced{
            let fresh=self.fresh.as_ref().ok_or_else(invalid)?;
            if fresh.revision!=reply.revision{return Err(invalid());}
            // Validate the old shared source cursor before swapping caches.
            // The helper updates only a garage-idle durable cursor; it never
            // creates a reservation, changes phase, resets epoch or grants.
            next.shared.as_mut().ok_or_else(invalid)?.commit_garage_source_revision(self.anchor.revision,reply.revision)?;
            next.identity=Some(fresh.owner.clone());next.hangar=Some(fresh.fixtures.clone());
            fresh.pool.clone()
        }else{self.anchor.pool.clone()};
        let copy=identity091::AmmoReply{serviced:reply.serviced,revision:reply.revision,wire_revision:reply.wire_revision,
            update:reply.update.clone(),recruitment:reply.recruitment.clone(),replayed:reply.replayed,
            result_code:reply.result_code,pool:Some(pool)};
        // apply validates delta/recruitment against OLD pool, stages0x57 before
        // callback, drains on its own clone, preserves prefix/seen/native wire.
        // No fallible operation is allowed after this final staging call.
        apply(&mut next,request,copy)?;
        *s=next;Ok(true)
    }
}

pub(super) fn complete(session:Option<&mut Session>,slot:&mut Option<Job>)->io::Result<()>{
    let job=slot.as_mut().ok_or_else(invalid)?;
    let flow=job.fresh.as_mut().ok_or_else(invalid)?;
    // Select the original recipient BEFORE observing even an unknown HTTP
    // outcome. The caller retires a Session on Err, so a replacement with the
    // same numeric SID must never inherit that error/containment decision.
    let recipient=session.as_deref().is_some_and(|s|
        s.id==job.session_id&&s.active&&flow.anchor.recipient(s));
    if flow.known.is_none(){
        let value=match job.receiver.try_recv(){
            Ok(value)=>value,
            Err(mpsc::TryRecvError::Empty)=>return Ok(()),
            Err(mpsc::TryRecvError::Disconnected)=>Err(invalid()),
        };
        let value=match value{Ok(value)=>value,Err(error)=>{
            // Unknown is not failure or success of the durable mutation.
            // Only the exact original recipient may take the established
            // ambiguous-error close path. A missing/foreign Account is not
            // touched, and no replacement UI callback is fabricated.
            let session_id=job.session_id;let request_id=job.request_id;
            slot.take();
            if recipient{return Err(error);}
            println!("P04M_GARAGE_AMBIGUOUS_OBSERVER_RETIRED session={session_id} request={request_id} sql_outcome=unknown recipient_matched=false mutation_reissued=false ui_emitted=false");
            return Ok(());
        }};
        // Store first. A malformed known reply must not become a second SQL.
        flow.known=Some(value);
        flow.known_at=Some(Instant::now());
        println!("P04M_GARAGE_REPLY_KNOWN session={} request={} readonly_refresh_next=true",job.session_id,job.request_id);
    }
    let Some(s)=session.filter(|s|s.id==job.session_id&&s.active&&flow.anchor.recipient(s))else{
        // Retain any still-running read worker until its actual exit before
        // freeing this singleton lane; never publish into a replacement epoch.
        if flow.worker_running(){return Ok(());}
        flow.join_finished()?;
        println!("P04M_GARAGE_OBSERVER_RETIRED session={} request={} durable_reply_retained_in_sql=true",job.session_id,job.request_id);
        slot.take();return Ok(());
    };
    if !flow.anchor.current(s){return Err(flow.contain(job.session_id,job.request_id,Containment::RecipientSourceChanged));}
    if Instant::now().duration_since(flow.known_at.ok_or_else(invalid)?)>=OBSERVATION{
        return Err(flow.contain(job.session_id,job.request_id,Containment::ObservationDeadline));
    }
    if Instant::now()<flow.retry_at{return Ok(());}
    if flow.anchor.known(flow.known.as_ref().ok_or_else(invalid)?).is_err(){
        return Err(flow.contain(job.session_id,job.request_id,Containment::MalformedKnown));
    }
    if flow.known.as_ref().ok_or_else(invalid)?.serviced&&flow.fresh.is_none(){
        flow.refresh(job.session_id,job.request_id,Instant::now())?;
        if flow.fresh.is_none(){return Ok(());}
    }
    match flow.publish(s,job.request_id){
        Ok(true)=>{slot.take();},
        Ok(false)=>{},
        Err(error)=>{
            flow.retry_at=Instant::now()+RETRY;
            println!("P04M_GARAGE_PUBLICATION_RETRY session={} request={} error={error} durable_reply_retained=true mutation_reissued=false",job.session_id,job.request_id);
        },
    }
    Ok(())
}

#[cfg(test)]
mod tests{
    use super::*;
    // Scalar boundary tests only. These do not manufacture ownership/Fresh
    // and are deliberately separate from the required actual HTTP producer.
    fn reply(serviced:bool,revision:u64,wire_revision:i64)->identity091::AmmoReply{
        identity091::AmmoReply{serviced,revision,wire_revision,update:Vec::new(),recruitment:None,
            replayed:false,result_code:if serviced{0}else{-10},pool:None}
    }
    #[test]fn garage_fresh32_known_success_and_replay_preserve_both_exact_cursors(){
        let mut r=reply(true,14,8);known_reply(13,7,&r).unwrap();
        r.replayed=true;known_reply(13,7,&r).unwrap();
        for(rev,wire)in[(13,8),(15,8),(14,1),(14,7),(14,9)]{
            r.revision=rev;r.wire_revision=wire;assert!(known_reply(13,7,&r).is_err());
        }
    }
    #[test]fn garage_fresh32_rejected_command_cannot_advance_or_smuggle_update(){
        let mut r=reply(false,13,7);known_reply(13,7,&r).unwrap();
        r.update.push(0x80);assert!(known_reply(13,7,&r).is_err());r.update.clear();
        r.revision=14;assert!(known_reply(13,7,&r).is_err());r.revision=13;
        r.wire_revision=8;assert!(known_reply(13,7,&r).is_err());
    }
    #[test]fn garage_fresh32_success_does_not_wrap_cursors(){
        assert!(known_reply(u64::MAX,7,&reply(true,0,8)).is_err());
        assert!(known_reply(13,i64::MAX,&reply(true,14,0)).is_err());
    }
}
