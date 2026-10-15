//! P08C result-cache requests: pure native staging, bounded async query/ack.
//! This manager never stores a natural result: the battle finish transaction
//! already committed that snapshot atomically with the terminal reservation.
use std::{collections::{BTreeMap,VecDeque},fmt,io,sync::{Arc,mpsc},thread::{self,JoinHandle},time::{Duration,Instant}};
use serde::{Deserialize,Deserializer,de::{self,MapAccess,Visitor}};
use serde_json::Value;
use crate::{hangar091,identity091};
use super::{super::Session,lifecycle_wire::{self,Results}};

const MAX_PENDING:usize=8;
const MAX_QUERIES:usize=128;
const MAX_COMMANDS:u32=512;
const MAX_HTTP:usize=65536;
const RETRY:Duration=Duration::from_millis(500);
fn bad(reason:&'static str)->io::Error {io::Error::new(io::ErrorKind::InvalidData,format!("battle results: {reason}"))}

#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub(crate) enum Operation {Query,Ack}
impl Operation {fn label(self)->&'static str {match self{Self::Query=>"query",Self::Ack=>"ack"}}}
#[derive(Clone,Debug,PartialEq,Eq)]
pub(crate) struct Request {pub(crate) operation:Operation,pub(crate) id:i16,pub(crate) arena:u64,epoch:u32}
#[derive(Clone,Debug,Default,PartialEq,Eq)]
pub(crate) struct State {
    pending:VecDeque<Request>,inflight:Option<Request>,seen:Vec<(i16,u64)>,acked:Vec<u64>,
    counter:u32,epoch:u32,cached:Option<Arc<Results>>,avatar_pending:bool,avatar_confirmed:bool,
}
impl State {
    pub(crate) fn idle(&self)->bool {self.pending.is_empty()&&self.inflight.is_none()}
    pub(crate) fn used_id(&self,id:i16)->bool {self.seen.iter().any(|(seen,_)|*seen==id)}
    pub(crate) fn cached(&self)->Option<&Arc<Results>> {self.cached.as_ref()}
    pub(crate) fn avatar_pending(&self)->bool {self.avatar_pending}
    pub(crate) fn avatar_confirmed(&self)->bool {self.avatar_confirmed}
    /// Call when the original Account entity is recreated. Old native callback
    /// request IDs cannot be delivered into a new Account callback registry.
    pub(crate) fn begin_account_epoch(&mut self)->io::Result<()> {
        self.epoch=self.epoch.checked_add(1).ok_or_else(||bad("account epoch overflow"))?;
        self.seen.clear();self.pending.retain(|r|r.operation==Operation::Ack);Ok(())
    }
    pub(crate) fn clear_avatar_confirmation(&mut self) {self.avatar_pending=false;self.avatar_confirmed=false;}
    /// Root calls this only after enqueuing the committed natural Avatar stream.
    pub(crate) fn cache_avatar(&mut self,result:Arc<Results>,own_account:i32)->io::Result<()> {
        result.validate()?;
        if !result.participants.iter().any(|p|p.account_dbid==own_account){return Err(bad("cached result owner"));}
        if self.cached.as_ref().is_some_and(|old|old.arena_id==result.arena_id) {
            if self.cached.as_ref()!=Some(&result){return Err(bad("conflicting immutable cached result"));}
            if !self.avatar_pending&&!self.avatar_confirmed {self.avatar_pending=true;}
            return Ok(());
        }
        if self.avatar_pending{return Err(bad("unconfirmed Avatar result still pending"));}
        self.cached=Some(result);self.avatar_pending=true;self.avatar_confirmed=false;Ok(())
    }
    /// Candidate original confirmBattleResultsReceiving, zero arguments. It
    /// acknowledges only the exact owned result previously queued by the root.
    pub(crate) fn confirm_avatar(&mut self,raw:&[u8])->io::Result<bool> {
        if raw.first()!=Some(&0x87){return Ok(false);}
        if raw!=[0x87,0,0]{return Err(bad("unexpected Avatar result confirmation"));}
        if self.avatar_confirmed&&self.cached.is_some(){return Ok(true);}
        if !self.avatar_pending{return Err(bad("unexpected Avatar result confirmation"));}
        let arena=self.cached.as_ref().ok_or_else(||bad("confirmation without result"))?.arena_id;
        self.queue_ack(arena)?;self.avatar_pending=false;self.avatar_confirmed=true;Ok(true)
    }
    fn queue_ack(&mut self,arena:u64)->io::Result<()> {
        if self.acked.contains(&arena)||self.pending.iter().chain(self.inflight.iter()).any(|r|r.operation==Operation::Ack&&r.arena==arena) {
            return Ok(());
        }
        if self.pending.len()+usize::from(self.inflight.is_some())>=MAX_PENDING||self.acked.len()>=MAX_QUERIES
            ||self.counter as usize+self.pending.len()>=MAX_COMMANDS as usize {
            return Err(bad("acknowledgement queue bound"));
        }
        self.pending.push_back(Request{operation:Operation::Ack,id:202,arena,epoch:self.epoch});Ok(())
    }
    /// One complete measured Account doCmdInt3 envelope. No external effects;
    /// the enclosing Session::receive clone owns atomic frame/piggyback commit.
    pub(crate) fn stage(&mut self,raw:&[u8])->io::Result<bool> {
        if raw.first()!=Some(&0x8e)||raw.len()<7{return Ok(false);}
        let command=i16::from_le_bytes([raw[5],raw[6]]);
        if ![1500,1501].contains(&command){return Ok(false);}
        if raw.len()!=23||raw[..3]!=[0x8e,20,0]||raw[15..].iter().any(|v|*v!=0) {
            return Err(bad("native result request layout"));
        }
        let id=i16::from_le_bytes([raw[3],raw[4]]);
        let arena=i64::from_le_bytes(raw[7..15].try_into().map_err(|_|bad("native arena ID"))?);
        if arena<=0||command==1500&&id<=0||command==1501&&id!=202 {
            return Err(bad("native result request identity"));
        }
        if command==1501 {self.queue_ack(arena as u64)?;return Ok(true);}
        if self.seen.len()>=MAX_QUERIES||self.seen.iter().any(|(seen,_)|*seen==id)
            ||self.pending.len()+usize::from(self.inflight.is_some())>=MAX_PENDING
            ||self.counter as usize+self.pending.len()>=MAX_COMMANDS as usize {
            return Err(bad("query queue or request ID bound"));
        }
        self.seen.push((id,arena as u64));
        self.pending.push_back(Request{operation:Operation::Query,id,arena:arena as u64,epoch:self.epoch});Ok(true)
    }
}

#[derive(Clone)]
struct Task {session:u32,owner:Arc<identity091::Profile>,request:Request,key:String}
impl Task {
    fn body(&self)->io::Result<Vec<u8>> {
        if self.session==0||self.owner.database_id<=0||self.owner.account_id.len()!=36
            ||self.request.arena==0||self.request.arena>i64::MAX as u64
            ||self.key.is_empty()||self.key.len()>96
            ||!self.key.bytes().all(|b|b.is_ascii_alphanumeric()||[b'_',b':',b'-'].contains(&b)) {
            return Err(bad("HTTP immutable task identity"));
        }
        let raw=serde_json::to_vec(&serde_json::json!({"version":1,"operation":self.request.operation.label(),
            "account_id":self.owner.account_id,"native_database_id":self.owner.database_id,"command_key":self.key,
            "arena_id":self.request.arena.to_string()})).map_err(|_|bad("HTTP task JSON"))?;
        if raw.len()>MAX_HTTP{return Err(bad("HTTP task size"));}Ok(raw)
    }
}
struct Fields(BTreeMap<String,Value>);
impl<'de> Deserialize<'de> for Fields {
    fn deserialize<D:Deserializer<'de>>(input:D)->Result<Self,D::Error> {
        struct Unique;
        impl<'de> Visitor<'de> for Unique {
            type Value=Fields;
            fn expecting(&self,f:&mut fmt::Formatter)->fmt::Result{f.write_str("eleven unique result reply fields")}
            fn visit_map<M:MapAccess<'de>>(self,mut input:M)->Result<Self::Value,M::Error> {
                let mut fields=BTreeMap::new();while let Some((key,value))=input.next_entry::<String,Value>()? {
                    if fields.len()>=11||fields.insert(key,value).is_some(){return Err(de::Error::custom("duplicate/too many result reply fields"));}
                }Ok(Fields(fields))
            }
        }input.deserialize_map(Unique)
    }
}
#[derive(Clone,Debug,PartialEq,Eq)]
struct Reply {result:Option<Arc<Results>>,acked:bool,replayed:bool,rejected:bool}
fn reply(raw:&[u8],task:&Task)->io::Result<Reply> {
    if raw.is_empty()||raw.len()>MAX_HTTP{return Err(bad("HTTP reply size"));}
    let Fields(fields)=serde_json::from_slice(raw).map_err(|_|bad("HTTP reply JSON unique fields"))?;
    let expected=["version","operation","status","account_id","native_database_id","command_key","arena_id","acked","replayed","results_json","code"];
    if fields.len()!=11||expected.iter().any(|k|!fields.contains_key(*k))
        ||fields["version"].as_u64()!=Some(1)||fields["operation"].as_str()!=Some(task.request.operation.label())
        ||fields["account_id"].as_str()!=Some(&task.owner.account_id)
        ||fields["native_database_id"].as_i64()!=Some(task.owner.database_id as i64)
        ||fields["command_key"].as_str()!=Some(&task.key)
        ||fields["arena_id"].as_str()!=Some(&task.request.arena.to_string()) {
        return Err(bad("HTTP reply authenticated owner/task mismatch"));
    }
    let acked=fields["acked"].as_bool().ok_or_else(||bad("HTTP acked boolean"))?;
    let replayed=fields["replayed"].as_bool().ok_or_else(||bad("HTTP replayed boolean"))?;
    let status=fields["status"].as_str().ok_or_else(||bad("HTTP status string"))?;
    let rejected=status=="rejected";
    if !match task.request.operation {Operation::Query=>["found","missing","rejected"].contains(&status),Operation::Ack=>["acked","missing","rejected"].contains(&status)}
        ||task.request.operation==Operation::Query&&replayed {
        return Err(bad("HTTP reply operation/status"));
    }
    if rejected {
        if !fields["results_json"].is_null()||acked
            ||!matches!(fields["code"].as_str(),Some("RESULT_NOT_READY"|"RESULT_MISMATCH"|"DUPLICATE_PAYLOAD_MISMATCH")) {
            return Err(bad("HTTP rejected result shape"));
        }
        return Ok(Reply{result:None,acked,replayed,rejected});
    }
    if !fields["code"].is_null(){return Err(bad("HTTP result unexpected rejection code"));}
    let result=if status=="missing" {
        if !fields["results_json"].is_null()||acked||replayed{return Err(bad("HTTP missing result shape"));}None
    }else{
        let raw=fields["results_json"].as_str().ok_or_else(||bad("HTTP result string"))?;
        if raw.len()>lifecycle_wire::MAX_RESULT_BYTES{return Err(bad("HTTP result string size"));}
        let parsed:Results=serde_json::from_str(raw).map_err(|_|bad("HTTP typed result fields"))?;parsed.validate()?;
        if parsed.arena_id!=task.request.arena||!parsed.participants.iter().any(|p|p.account_dbid==task.owner.database_id)
            ||status=="acked"&&!acked{return Err(bad("HTTP result owner/arena/ack binding"));}
        Some(Arc::new(parsed))
    };
    Ok(Reply{result,acked,replayed,rejected})
}
fn response_prefix(id:i16)->io::Result<Vec<u8>> {
    if id<=0{return Err(bad("result response request ID"));}
    let mut payload=id.to_le_bytes().to_vec();payload.extend(1i16.to_le_bytes());
    payload.extend([0,4,0x80,2,b'}',b'.']);hangar091::method(0x4d,&payload)
}
fn native_reply(task:&Task,reply:&Reply)->io::Result<Vec<Vec<u8>>> {
    if task.request.operation==Operation::Ack{return Ok(Vec::new());}
    match &reply.result {
        Some(result)=>lifecycle_wire::account_result_stream(task.request.id,response_prefix(task.request.id)?,result,task.owner.database_id),
        None=>Ok(vec![hangar091::unavailable_response(task.request.id)?]),
    }
}

struct Job {receiver:mpsc::Receiver<io::Result<Reply>>,worker:Option<JoinHandle<()>>}
impl Job {
    fn start(task:&Task,config:Arc<identity091::Config>)->io::Result<Self> {
        if !config.profile13_battle{return Err(bad("result worker requires profile13 mode"));}
        let body=task.body()?;let copied=task.clone();let(sender,receiver)=mpsc::sync_channel(1);
        let worker=thread::Builder::new().name("p08c-result-cache".into()).spawn(move||{
            let result=std::panic::catch_unwind(std::panic::AssertUnwindSafe(||{
                let bytes=config.results_post(&copied.owner,&body)?;reply(&bytes,&copied)
            })).unwrap_or_else(|_|Err(bad("result worker panicked; immutable request retained")));
            println!("P08C_RESULTS_WORKER session={} operation={} arena={} success={} observer_pending=true",
                copied.session,copied.request.operation.label(),copied.request.arena,result.is_ok());
            if sender.send(result).is_err(){println!("P08C_RESULTS_OBSERVER_RETIRED session={} operation={} durable_result_retained=true",copied.session,copied.request.operation.label());}
        })?;
        Ok(Self{receiver,worker:Some(worker)})
    }
    fn poll(&mut self)->Option<io::Result<Reply>> {
        if self.worker.as_ref().is_some_and(|w|!w.is_finished()){return None;}
        let result=match self.receiver.try_recv(){Ok(value)=>value,Err(mpsc::TryRecvError::Empty)=>return None,
            Err(mpsc::TryRecvError::Disconnected)=>Err(bad("result worker ended without reply"))};
        if self.worker.take().is_some_and(|w|w.join().is_err()){return Some(Err(bad("result worker join panic")));}Some(result)
    }
}
#[derive(Default)]
pub(crate) struct Manager {task:Option<Task>,job:Option<Job>,completed:Option<Reply>,retry_at:Option<Instant>}
impl Manager {
    pub(crate) fn busy(&self)->bool {self.task.is_some()||self.job.is_some()||self.completed.is_some()}
    pub(crate) fn target_session(&self)->Option<u32> {self.task.as_ref().map(|task|task.session)}
    /// A pre-dispatch validation failure has no retained task yet. The root can
    /// still contain it to the first affected live Session instead of the service.
    pub(crate) fn failure_session(&self,sessions:&[Session])->Option<u32> {
        self.target_session().or_else(||sessions.iter().find(|s|s.active
            &&(!s.battle_results.pending.is_empty()||s.battle_results.inflight.is_some())).map(|s|s.id))
    }
    /// Polling never launches HTTP. A complete reply stays retained if its
    /// complete native output cannot atomically fit this session's queue yet.
    pub(crate) fn poll(&mut self,sessions:&mut[Session],now:Instant)->io::Result<()> {
        if let Some(outcome)=self.job.as_mut().and_then(Job::poll) {
            self.job=None;match outcome {
                Ok(reply)=>{self.completed=Some(reply);self.retry_at=None;},
                Err(error)=>{let task=self.task.as_ref().ok_or_else(||bad("worker task absent"))?;
                    println!("P08C_RESULTS_RETRY session={} operation={} arena={} error={error} immutable_task_retained=true",
                        task.session,task.request.operation.label(),task.request.arena);
                    self.retry_at=Some(now.checked_add(RETRY).ok_or_else(||bad("retry clock overflow"))?);},
            }
        }
        let Some(done)=self.completed.as_ref()else{return Ok(());};
        let task=self.task.as_ref().ok_or_else(||bad("completed result task absent"))?;
        if let Some(s)=sessions.iter_mut().find(|s|s.id==task.session&&s.identity.as_ref().is_some_and(|p|
            p.account_id==task.owner.account_id&&p.database_id==task.owner.database_id)) {
            if s.battle_results.inflight.as_ref()!=Some(&task.request){return Err(bad("session result task changed"));}
            let mut next=s.clone();
            let account=next.active&&!next.arena_base&&next.account_ready&&next.sync_mask==7
                &&next.shared.as_ref().is_some_and(|c|c.profile13_account())&&next.battle_results.epoch==task.request.epoch;
            if task.request.operation==Operation::Query&&account {
                let bodies=native_reply(task,done)?;
                if next.outbox.len()+bodies.len()>128{return Ok(());}
                next.outbox.extend(bodies);next.drain_outbox()?;
            }
            if let Some(result)=&done.result {if !next.battle_results.avatar_pending {next.battle_results.cached=Some(result.clone());}}
            if task.request.operation==Operation::Ack&&done.acked&&!next.battle_results.acked.contains(&task.request.arena) {
                if next.battle_results.acked.len()>=MAX_QUERIES{return Err(bad("retained result acknowledgement count"));}
                next.battle_results.acked.push(task.request.arena);
            }
            next.battle_results.inflight=None;
            println!("P08C_RESULTS_COMPLETE session={} operation={} arena={} found={} acked={} replayed={} rejected={} native_account_delivery={}",
                task.session,task.request.operation.label(),task.request.arena,done.result.is_some(),done.acked,done.replayed,done.rejected,
                task.request.operation==Operation::Query&&account);
            *s=next;
        }else{println!("P08C_RESULTS_RETIRED_COMPLETE session={} operation={} arena={} durable_result_retained=true",
            task.session,task.request.operation.label(),task.request.arena);}
        self.task=None;self.completed=None;self.retry_at=None;Ok(())
    }
    /// Root serializes this with battle/ammunition/auth writers. Once dispatched,
    /// retry uses this manager's immutable task even after the Session retires.
    pub(crate) fn start_if_idle(&mut self,sessions:&mut[Session],config:Arc<identity091::Config>,now:Instant)->io::Result<()> {
        self.start_with(sessions,config,now,&mut Job::start)
    }
    /// Shared production executor boundary; tests can inject an actual failed
    /// start while exercising the complete admission/reservation/retry path.
    fn start_with<F>(&mut self,sessions:&mut[Session],config:Arc<identity091::Config>,now:Instant,spawn:&mut F)->io::Result<()>
        where F:FnMut(&Task,Arc<identity091::Config>)->io::Result<Job> {
        if self.job.is_some()||self.completed.is_some(){return Ok(());}
        if self.task.is_some() {
            if self.retry_at.is_none_or(|at|now>=at) {self.spawn_retained(config,now,spawn)?;}return Ok(());
        }
        if !config.profile13_battle{return Err(bad("result manager requires profile13 mode"));}
        for s in sessions {
            let Some(request)=s.battle_results.pending.front().cloned()else{continue;};
            if s.battle_results.inflight.is_some()||!s.active{continue;}
            let owner=s.identity.clone().ok_or_else(||bad("result session owner absent"))?;
            let counter=s.battle_results.counter.checked_add(1).filter(|c|*c<=MAX_COMMANDS).ok_or_else(||bad("result command count"))?;
            let task=Task{session:s.id,owner,request:request.clone(),key:format!("p08c:{}:{}:{counter}",config.battle_run_id,s.id)};
            task.body()?;
            // Reserve the complete immutable operation before asking the OS for
            // a thread. A failed spawn is a retryable executor outcome and must
            // not lose the request or create another command key next time.
            s.battle_results.counter=counter;s.battle_results.pending.pop_front();s.battle_results.inflight=Some(request);
            self.task=Some(task);self.spawn_retained(config.clone(),now,spawn)?;return Ok(());
        }Ok(())
    }
    fn spawn_retained<F>(&mut self,config:Arc<identity091::Config>,now:Instant,spawn:&mut F)->io::Result<()>
        where F:FnMut(&Task,Arc<identity091::Config>)->io::Result<Job> {
        let task=self.task.as_ref().ok_or_else(||bad("spawn retry task absent"))?;
        match spawn(task,config) {
            Ok(job)=>{self.job=Some(job);self.retry_at=None;},
            Err(error)=>{
                println!("P08C_RESULTS_START_RETRY session={} operation={} arena={} error={error} immutable_task_retained=true",
                    task.session,task.request.operation.label(),task.request.arena);
                self.retry_at=Some(now.checked_add(RETRY).ok_or_else(||bad("spawn retry clock overflow"))?);
            },
        }Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn request(id:i16,command:i16,arena:i64)->Vec<u8> {
        let mut raw=vec![0x8e,20,0];raw.extend(id.to_le_bytes());raw.extend(command.to_le_bytes());
        raw.extend(arena.to_le_bytes());raw.extend([0;8]);raw
    }
    fn results()->Results {
        use lifecycle_wire::Participant;
        Results {arena_id:0x1_0000_0001,arena_type_id:4,created_unix:1792080000,winner_team:0,
            finish_reason:3,duration_seconds:900,participants:vec![
                Participant {vehicle_id:0x09100003,account_dbid:1,name:"owner_a".into(),team:1,
                    type_compact_descr:3329,health:90,life_time:900,death_reason:-1,..Default::default()},
                Participant {vehicle_id:0x09100005,account_dbid:2,name:"owner_b".into(),team:2,
                    type_compact_descr:3329,health:90,life_time:900,death_reason:-1,..Default::default()},
            ]}
    }
    fn owner()->Arc<identity091::Profile> {Arc::new(identity091::Profile {
        account_id:"12345678-1234-4234-8234-123456789abc".into(),database_id:1,name:"owner_a".into(),fixture_dir:std::path::PathBuf::new(),
    })}
    fn task(operation:Operation)->Task {Task{session:7,owner:owner(),request:Request{operation,id:if operation==Operation::Ack{202}else{227},
        arena:results().arena_id,epoch:0},key:"p08c:12345678-1234-4234-8234-123456789abc:7:1".into()}}
    fn response(task:&Task,status:&str)->Value {serde_json::json!({"version":1,"operation":task.request.operation.label(),
        "status":status,"account_id":task.owner.account_id,"native_database_id":task.owner.database_id,
        "command_key":task.key,"arena_id":task.request.arena.to_string(),"acked":status=="acked","replayed":false,
        "results_json":if status=="missing"{Value::Null}else{serde_json::to_string(&results()).unwrap().into()},"code":null})}
    #[test] fn p08c_native_query_ack_staging_is_bounded_and_has_no_external_effects() {
        let mut state=State::default();let raw=request(227,1500,results().arena_id as i64);
        assert!(state.stage(&raw).unwrap());assert!(state.used_id(227));assert_eq!(state.pending.len(),1);
        let before=state.clone();assert!(state.stage(&raw).is_err());assert_eq!(state,before);
        for mutation in 0..7 {
            let mut poison=request(228,1500,1);match mutation {
                0=>poison[1]=19,1=>{poison.pop();},2=>poison.push(0),3=>poison[15]=1,
                4=>poison[3..5].copy_from_slice(&0i16.to_le_bytes()),5=>poison[7..15].copy_from_slice(&0i64.to_le_bytes()),
                6=>poison[7..15].copy_from_slice(&(-1i64).to_le_bytes()),_=>unreachable!(),
            }assert!(state.stage(&poison).is_err());assert_eq!(state,before);
        }
        assert!(!state.stage(&request(228,100,1)).unwrap());assert_eq!(state,before);
        assert!(state.stage(&request(201,1501,1)).is_err());assert_eq!(state,before);
        assert!(state.stage(&request(202,1501,1)).unwrap());let acked=state.clone();
        assert!(state.stage(&request(202,1501,1)).unwrap());assert_eq!(state,acked);
        for id in 228..234 {state.stage(&request(id,1500,id as i64)).unwrap();}
        assert_eq!(state.pending.len(),8);let full=state.clone();
        assert!(state.stage(&request(234,1500,234)).is_err());assert_eq!(state,full);
        state.begin_account_epoch().unwrap();assert_eq!(state.pending.len(),1);assert!(!state.used_id(227));
        let mut limited=State{counter:MAX_COMMANDS-1,..Default::default()};
        limited.stage(&request(227,1500,1)).unwrap();let before=limited.clone();
        assert!(limited.stage(&request(228,1500,2)).is_err());assert_eq!(limited,before);
        assert!(limited.stage(&request(202,1501,3)).is_err());assert_eq!(limited,before);
    }
    #[test] fn p08c_avatar_confirmation_is_owned_pure_and_duplicate_idempotent() {
        let mut state=State::default();assert!(state.confirm_avatar(&[0x87,0,0]).is_err());
        let result=Arc::new(results());state.cache_avatar(result.clone(),1).unwrap();
        assert!(state.avatar_pending());assert!(!state.avatar_confirmed());
        let before=state.clone();assert!(state.confirm_avatar(&[0x87,1,0,0]).is_err());assert_eq!(state,before);
        assert!(!state.confirm_avatar(&[0x86,0,0]).unwrap());assert_eq!(state,before);
        let mut next=results();next.arena_id+=1;assert!(state.cache_avatar(Arc::new(next.clone()),1).is_err());assert_eq!(state,before);
        assert!(state.confirm_avatar(&[0x87,0,0]).unwrap());assert!(state.avatar_confirmed());assert!(!state.avatar_pending());
        let after=state.clone();assert!(state.confirm_avatar(&[0x87,0,0]).unwrap());assert_eq!(state,after);
        state.cache_avatar(result,1).unwrap();assert!(state.avatar_confirmed());
        state.cache_avatar(Arc::new(next),1).unwrap();assert!(state.avatar_pending());assert!(!state.avatar_confirmed());
        let before=state.clone();assert!(state.cache_avatar(Arc::new(results()),3).is_err());assert_eq!(state,before);
        let mut fetched=State{cached:Some(Arc::new(results())),..Default::default()};
        fetched.cache_avatar(Arc::new(results()),1).unwrap();assert!(fetched.avatar_pending());
    }
    #[test] fn p08c_result_reply_requires_exact_owner_task_typed_snapshot_and_native_callback_ext() {
        let task=task(Operation::Query);let value=response(&task,"found");
        let encode=|v:&Value|serde_json::to_vec(v).unwrap();
        let parsed=reply(&encode(&value),&task).unwrap();assert_eq!(parsed.result.as_deref(),Some(&results()));
        for mutation in 0..15 {
            let mut wrong=value.clone();match mutation {
                0=>wrong["version"]=true.into(),1=>wrong["operation"]="ack".into(),2=>wrong["account_id"]="foreign".into(),
                3=>wrong["native_database_id"]=2.into(),4=>wrong["command_key"]="other".into(),5=>wrong["arena_id"]="1".into(),
                6=>wrong["acked"]=0.into(),7=>wrong["replayed"]=true.into(),8=>wrong["code"]="RESULT_MISMATCH".into(),
                9=>wrong["extra"]=true.into(),10=>wrong["results_json"]=Value::Null,11=>wrong["status"]="stored".into(),
                12=>wrong["arena_id"]=(task.request.arena as i64).into(),13=>wrong["results_json"]="x".repeat(32769).into(),
                14=>{let mut result=results();result.arena_id+=1;wrong["results_json"]=serde_json::to_string(&result).unwrap().into();},_=>unreachable!(),
            }assert!(reply(&encode(&wrong),&task).is_err(),"mutation{mutation}");
        }
        let duplicate=String::from_utf8(encode(&value)).unwrap().replacen("{","{\"version\":1,",1);
        assert!(reply(duplicate.as_bytes(),&task).is_err());
        let mut duplicate_nested=value.clone();duplicate_nested["results_json"]=serde_json::to_string(&results()).unwrap().replacen("{","{\"arena_id\":1,",1).into();
        assert!(reply(&encode(&duplicate_nested),&task).is_err());
        let bodies=native_reply(&task,&parsed).unwrap();assert_eq!(&bodies[0][..3],&[0x13,0x4d,10]);
        assert_eq!(&bodies[0][3..7],&[227,0,1,0]);assert_eq!(&bodies[0][7..13],&[0,4,128,2,125,46]);
        let missing=reply(&encode(&response(&task,"missing")),&task).unwrap();
        let unavailable=native_reply(&task,&missing).unwrap();assert_eq!(&unavailable[0][5..7],&(-10i16).to_le_bytes());
        let ack=self::task(Operation::Ack);let acked=reply(&encode(&response(&ack,"acked")),&ack).unwrap();
        assert!(native_reply(&ack,&acked).unwrap().is_empty());assert!(acked.acked);
    }
    fn session(task:&Task)->Session {
        let mut s=Session::new(task.session,[0;16],"127.0.0.1:29999".parse().unwrap(),Instant::now());
        s.active=true;s.account_ready=true;s.sync_mask=7;s.identity=Some(task.owner.clone());
        let mut client=super::super::Client::new(0);
        client.profile13=Some(super::super::profile13_session::State::new("12345678-1234-4234-8234-123456789abc".into(),16).unwrap());
        s.shared=Some(client);s.battle_results.inflight=Some(task.request.clone());s
    }
    #[test] fn p08c_manager_retains_complete_delivery_and_never_sends_into_a_new_account_epoch() {
        let task=task(Operation::Query);let complete=Reply{result:Some(Arc::new(results())),acked:false,replayed:false,rejected:false};
        let mut sessions=vec![session(&task)];sessions[0].battle_results.begin_account_epoch().unwrap();
        let mut manager=Manager{task:Some(task.clone()),completed:Some(complete.clone()),..Default::default()};
        manager.poll(&mut sessions,Instant::now()).unwrap();assert!(!manager.busy());
        assert_eq!(sessions[0].tx.len(),0);assert!(sessions[0].outbox.is_empty());assert!(sessions[0].battle_results.inflight.is_none());
        let mut s=session(&task);s.outbox=std::iter::repeat_n(vec![19],128).collect();let before=s.battle_results.clone();
        let mut manager=Manager{task:Some(task.clone()),completed:Some(complete.clone()),..Default::default()};
        manager.poll(std::slice::from_mut(&mut s),Instant::now()).unwrap();assert!(manager.busy());
        assert_eq!(s.battle_results,before);assert_eq!(s.outbox.len(),128);
        s.outbox.clear();manager.poll(std::slice::from_mut(&mut s),Instant::now()).unwrap();assert!(!manager.busy());
        assert!(s.tx.len()>0);assert!(s.battle_results.inflight.is_none());
        let mut manager=Manager{task:Some(task),completed:Some(complete),..Default::default()};
        manager.poll(&mut [],Instant::now()).unwrap();assert!(!manager.busy());
    }
    #[test] fn p08c_manager_worker_exit_barrier_and_retry_keep_exact_task_bytes() {
        let task=task(Operation::Ack);let bytes=task.body().unwrap();let copy=task.clone();assert_eq!(bytes,copy.body().unwrap());
        let(sender,receiver)=mpsc::sync_channel(1);let(release,wait)=mpsc::sync_channel(1);let(sent,delivered)=mpsc::sync_channel(1);
        let worker=thread::spawn(move||{sender.send(Err(bad("authored bounded failure"))).unwrap();sent.send(()).unwrap();wait.recv().unwrap();});
        delivered.recv().unwrap();let mut manager=Manager{task:Some(task),job:Some(Job{receiver,worker:Some(worker)}),..Default::default()};
        let now=Instant::now();manager.poll(&mut [],now).unwrap();assert!(manager.job.is_some());
        release.send(()).unwrap();manager.job.as_mut().unwrap().worker.take().unwrap().join().unwrap();
        manager.poll(&mut [],now).unwrap();assert!(manager.job.is_none());assert!(manager.busy());
        assert_eq!(manager.task.as_ref().unwrap().body().unwrap(),bytes);assert_eq!(manager.retry_at,Some(now+RETRY));
    }
    #[test] fn p08c_manager_failed_first_spawn_retains_one_request_key_and_retries_after_session_dispatch() {
        let project=std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..").canonicalize().unwrap();
        let base=project.join("local/test-runs/p08c-result-start");std::fs::create_dir_all(&base).unwrap();
        let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let directory=base.join(format!("spawn-{stamp}"));std::fs::create_dir(&directory).unwrap();
        let directory=directory.canonicalize().unwrap();assert!(directory.starts_with(base.canonicalize().unwrap()));
        std::fs::write(directory.join("token.txt"),"a".repeat(43)).unwrap();
        let mut value=serde_json::json!({"login_bind":"127.0.0.1:24771","base_bind":"127.0.0.1:24772",
            "identity_endpoint":"127.0.0.1:3488","identity_token_file":directory.join("token.txt"),
            "local_root":directory,"session_duration_seconds":600});
        for flag in ["ammunition_service","crew_service","crew_transfer","crew_cross_vehicle","crew_roster_recruitment",
            "crew_progression","crew_dismissal","crew_barracks_recruitment","research_service","profile13_battle"] {value[flag]=true.into();}
        let path=directory.join("gateway.json");std::fs::write(&path,serde_json::to_vec(&value).unwrap()).unwrap();
        let config=Arc::new(identity091::Config::load(path.to_str().unwrap()).unwrap());
        let template=task(Operation::Query);let mut s=session(&template);s.battle_results=State::default();
        s.battle_results.stage(&request(221,1500,1)).unwrap();
        let now=Instant::now();let mut manager=Manager::default();let mut starts=0;let mut first_body=None;
        assert_eq!(manager.target_session(),None);assert_eq!(manager.failure_session(std::slice::from_ref(&s)),Some(7));
        let mut spawn=|task:&Task,_config:Arc<identity091::Config>|->io::Result<Job> {
            starts+=1;
            if starts==1 {first_body=Some(task.body().unwrap());return Err(io::Error::other("authored OS thread start failure"));}
            assert_eq!(task.body().unwrap().as_slice(),first_body.as_ref().unwrap().as_slice());
            let(sender,receiver)=mpsc::sync_channel(1);
            let worker=thread::spawn(move||{sender.send(Ok(Reply{result:None,acked:false,replayed:false,rejected:false})).unwrap();});
            Ok(Job{receiver,worker:Some(worker)})
        };
        manager.start_with(std::slice::from_mut(&mut s),config.clone(),now,&mut spawn).unwrap();
        assert!(manager.busy());assert_eq!(manager.target_session(),Some(7));assert!(manager.job.is_none());
        assert_eq!(manager.failure_session(&[]),Some(7));
        assert_eq!(s.battle_results.counter,1);assert!(s.battle_results.pending.is_empty());assert!(s.battle_results.inflight.is_some());
        let key=manager.task.as_ref().unwrap().key.clone();assert_eq!(manager.retry_at,Some(now+RETRY));
        manager.start_with(std::slice::from_mut(&mut s),config.clone(),now+RETRY-Duration::from_millis(1),&mut spawn).unwrap();
        assert!(manager.job.is_none());
        manager.start_with(std::slice::from_mut(&mut s),config,now+RETRY,&mut spawn).unwrap();
        assert!(manager.job.is_some());assert_eq!(manager.task.as_ref().unwrap().key,key);assert_eq!(s.battle_results.counter,1);
        drop(spawn);assert_eq!(starts,2);
        manager.job.as_mut().unwrap().worker.take().unwrap().join().unwrap();
        manager.poll(std::slice::from_mut(&mut s),now+RETRY).unwrap();
        assert!(!manager.busy());assert_eq!(manager.target_session(),None);assert!(s.battle_results.inflight.is_none());
        assert_eq!(manager.failure_session(std::slice::from_ref(&s)),None);
        assert!(s.tx.len()>0);assert_eq!(s.battle_results.counter,1);
        assert!(directory.starts_with(project.join("local/test-runs")));std::fs::remove_dir_all(directory).unwrap();
    }
    #[test] fn p08c_actual_sqlite_query_and_ack_vectors_preserve_large_arena_and_native_result_bytes() {
        use sha2::{Digest,Sha256};
        let path=std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../tests/fixtures/profile13-results-vectors.json");
        let raw=std::fs::read(path).unwrap();assert_eq!(raw.len(),5612);
        assert_eq!(format!("{:x}",Sha256::digest(&raw)),"793935ad298facc6dd68c49f56f0b4dc2cb0f28749aa14f2451f4b3ba70cc635");
        let fixture:Value=serde_json::from_slice(&raw).unwrap();assert_eq!(fixture["schema"],"p08c-actual-writer-vectors.v1");
        for (index,operation,id) in [(1,Operation::Query,221),(2,Operation::Ack,202)] {
            let vector=&fixture["vectors"][index];let request=&vector["request"];
            let task=Task{session:7,owner:Arc::new(identity091::Profile {
                account_id:request["account_id"].as_str().unwrap().into(),database_id:request["native_database_id"].as_i64().unwrap() as i32,
                name:"Авторитетный".into(),fixture_dir:std::path::PathBuf::new(),
            }),request:Request{operation,id,arena:request["arena_id"].as_str().unwrap().parse().unwrap(),epoch:0},
                key:request["command_key"].as_str().unwrap().into()};
            assert_eq!(serde_json::from_slice::<Value>(&task.body().unwrap()).unwrap(),*request);
            let parsed=reply(&serde_json::to_vec(&vector["response"]).unwrap(),&task).unwrap();
            let result=parsed.result.as_ref().unwrap();assert_eq!(result.arena_id,9007199254740993);
            let own=result.participants.iter().find(|p|p.account_dbid==task.owner.database_id).unwrap();
            assert_eq!((own.health,own.shots,own.damage_dealt,own.capture_points),(23,3,7,42));assert_eq!(own.name,"Авторитетный");
            let compact=lifecycle_wire::compact_results(result,task.owner.database_id).unwrap();
            assert_eq!(&compact[..4],&[128,2,138,8]);
            assert_eq!(i64::from_le_bytes(compact[4..12].try_into().unwrap()),9007199254740993);
            let bodies=native_reply(&task,&parsed).unwrap();
            if operation==Operation::Ack {assert!(bodies.is_empty());assert!(parsed.acked);continue;}
            assert!(!parsed.acked);assert_eq!(&bodies[0][..13],&[19,77,10,221,0,1,0,0,4,128,2,125,46]);
            assert_eq!(&bodies[0][13..18],&[52,17,0,221,0]);
            let mut compressed=Vec::new();
            for (sequence,body) in bodies.iter().enumerate() {
                let at=if sequence==0{33}else{0};assert_eq!(body[at],53);
                let length=u16::from_le_bytes([body[at+1],body[at+2]]) as usize;assert_eq!(at+3+length,body.len());
                assert_eq!(&body[at+3..at+7],&[221,0,sequence as u8,u8::from(sequence+1==bodies.len())]);
                compressed.extend(&body[at+7..]);
            }
            assert_eq!(&compressed[..3],&[0x78,1,1]);let length=u16::from_le_bytes([compressed[3],compressed[4]]) as usize;
            assert_eq!(length,compact.len());assert_eq!(u16::from_le_bytes([compressed[5],compressed[6]]),!(length as u16));
            assert_eq!(&compressed[7..7+length],compact.as_slice());assert_eq!(compressed.len(),length+11);
        }
    }
}
