//! Committed-only durable notice discovery. ONE page<=8, strict lexical cursor.
//! A page never ACKs records. It is bound to actual owner/key/Account epoch;
//! creating a new Account makes stale completions unusable for publication.
use std::{collections::{BTreeMap,BTreeSet},io,sync::{Arc,mpsc},thread::{self,JoinHandle},time::{Duration,Instant}};
use serde_json::{Value,json};use sha2::{Digest,Sha256};
use crate::identity091;use super::{super::Session,Phase,late_results_capture::canonical,late_results_protocol::{CONTRACT,POLICY_SHA256}};
pub(super) const ENDPOINT:&str="/internal/native/late-result-pending";
fn bad(why:&'static str)->io::Error{io::Error::new(io::ErrorKind::InvalidData,format!("late result pending: {why}"))}
fn keys(v:&Value,names:&[&str])->io::Result<()>{if v.as_object().is_none_or(|m|m.len()!=names.len()||names.iter().any(|k|!m.contains_key(*k))){return Err(bad("closed unique fields"));}Ok(())}
fn arena(v:&Value)->io::Result<u64>{let s=v.as_str().ok_or_else(||bad("arena string"))?;let n=s.parse::<u64>().map_err(|_|bad("arena syntax"))?;
    if n==0||n>i64::MAX as u64||s!=n.to_string(){return Err(bad("canonical signed arena"));}Ok(n)}
fn hash(s:&str)->bool{s.len()==64&&s.bytes().all(|b|b.is_ascii_digit()||(b'a'..=b'f').contains(&b))}
#[derive(Clone,Debug,PartialEq,Eq)]
pub(super) struct Row{pub(super) arena:u64,pub(super) seal:String,pub(super) map:i32,pub(super) created_unix:u32,
    pub(super) winner:u8,pub(super) own_team:u8,pub(super) vehicle:u32}
#[derive(Clone,Debug,PartialEq,Eq,PartialOrd,Ord)]
struct Context{session:u32,key:[u8;16],epoch:u32,owner:String,native:i32}
fn current(s:&Session)->Option<Context>{if !s.active||s.arena_base||!s.account_ready||s.sync_mask!=7||s.base_peer.is_none()
    ||!s.shared.as_ref().is_some_and(|c|c.phase==Phase::Account){return None;}
    let owner=s.identity.as_ref()?;Some(Context{session:s.id,key:s.key,epoch:s.battle_results.account_epoch(),owner:owner.account_id.clone(),native:owner.database_id})}
#[derive(Clone)]
struct Query{context:Context,owner:Arc<identity091::Profile>,request:Value,body:Vec<u8>,sha:String}
impl Query{
    fn new(s:&Session,cursor:Option<u64>,counter:u32)->io::Result<Self>{let context=current(s).ok_or_else(||bad("not actual ready Account"))?;
        let owner=s.identity.clone().ok_or_else(||bad("missing owner"))?;
        let key=format!("p08c:pending:{}:{}:{}",context.session,context.epoch,counter);
        let request=json!({"version":1,"contract":CONTRACT,"operation":"pending","account_id":context.owner,"native_database_id":context.native,
            "command_key":key,"after_arena_id":cursor.map(|n|n.to_string())});
        let body=canonical(&request)?.into_bytes();if body.len()>2048||key.len()>96{return Err(bad("fixed pending request budget"));}
        let sha=format!("{:x}",Sha256::digest(&body));Ok(Self{context,owner,request,body,sha})
    }
    fn parse(&self,raw:&[u8])->io::Result<Page>{let v=crate::profile13_v2091::bounded_json(raw,4096)?;
        keys(&v,&["version","contract","operation","account_id","native_database_id","command_key","after_arena_id","request_sha256","policy_sha256","status","replayed","code","rows","next_arena_id"])?;
        for name in["version","contract","operation","account_id","native_database_id","command_key","after_arena_id"]{
            if v[name]!=self.request[name]{return Err(bad("reply immutable owner/request/cursor"));}}
        if v["request_sha256"]!=self.sha||v["policy_sha256"]!=POLICY_SHA256||v["replayed"]!=false{return Err(bad("reply canonical policy/request hash"));}
        let rows=v["rows"].as_array().ok_or_else(||bad("rows type"))?;if rows.len()>8{return Err(bad("page bound8"));}
        if v["status"]=="rejected"{let code=v["code"].as_str().ok_or_else(||bad("denial type"))?;
            if !rows.is_empty()||!v["next_arena_id"].is_null()||!["RELEASE_NOT_READY","RESULT_MISMATCH","LATE_ACTOR_STATE_CHANGED","RUN_FENCED","FOREIGN_ACCOUNT","DUPLICATE_PAYLOAD_MISMATCH","UNSUPPORTED_LATE_RESULTS_SCHEMA","INVALID_INPUT"].contains(&code){return Err(bad("closed denial"));}
            return Ok(Page{rows:Vec::new(),next:None,rejected:Some(code.into())});}
        if v["status"]!="pending"||!v["code"].is_null(){return Err(bad("success status"));}
        let mut out=Vec::new();let mut prior=self.request["after_arena_id"].as_str().unwrap_or("").to_owned();
        for row in rows{keys(row,&["arena_id","seal_sha256","arena_type_id","created_unix","winner_team","own_team","vehicle_type_compact_id"])?;
            let n=arena(&row["arena_id"])?;let spelling=n.to_string();if spelling<=prior{return Err(bad("strict ASCII lexical arena cursor"));}prior=spelling;
            let seal=row["seal_sha256"].as_str().filter(|s|hash(s)).ok_or_else(||bad("seal hash"))?.into();
            let map=row["arena_type_id"].as_i64().and_then(|n|i32::try_from(n).ok()).filter(|n|*n>0).ok_or_else(||bad("arena type"))?;
            let created_unix=row["created_unix"].as_u64().and_then(|n|u32::try_from(n).ok()).filter(|n|*n>0).ok_or_else(||bad("creation UTC"))?;
            let winner=row["winner_team"].as_u64().and_then(|n|u8::try_from(n).ok()).filter(|n|*n<=2).ok_or_else(||bad("winner"))?;
            let own_team=row["own_team"].as_u64().and_then(|n|u8::try_from(n).ok()).filter(|n|(1..=2).contains(n)).ok_or_else(||bad("owner team"))?;
            let vehicle=row["vehicle_type_compact_id"].as_u64().and_then(|n|u32::try_from(n).ok()).filter(|n|*n>0&&*n<=u16::MAX as u32).ok_or_else(||bad("vehicle source compact width"))?;
            out.push(Row{arena:n,seal,map,created_unix,winner,own_team,vehicle});
        }
        let next=if v["next_arena_id"].is_null(){None}else{let n=arena(&v["next_arena_id"])?;
            if out.len()!=8||out.last().is_none_or(|r|r.arena!=n){return Err(bad("next cursor requires full page and exact last arena"));}Some(n)};
        Ok(Page{rows:out,next,rejected:None})
    }
}
struct Page{rows:Vec<Row>,next:Option<u64>,rejected:Option<String>}
struct Job{rx:mpsc::Receiver<io::Result<Page>>,handle:JoinHandle<()>}
impl Job{fn start(query:&Query,config:Arc<identity091::Config>)->io::Result<Self>{let query=query.clone();let(tx,rx)=mpsc::channel();
    let handle=thread::Builder::new().name("p08c-late-pending".into()).spawn(move||{let out=config.late_results_pending_post(&query.owner,&query.body).and_then(|raw|query.parse(&raw));let _=tx.send(out);})?;Ok(Self{rx,handle})}
    fn poll(&mut self)->Option<io::Result<Page>>{if !self.handle.is_finished(){return None;}match self.rx.try_recv(){Ok(v)=>Some(v),Err(mpsc::TryRecvError::Empty)=>None,Err(mpsc::TryRecvError::Disconnected)=>Some(Err(bad("worker ended; exact pending request retained")))}}
}
#[derive(Default)]
struct Sweep{cursor:Option<u64>,next_at:Option<Instant>,seen:BTreeSet<u64>,disabled:bool}
/// At most6 configured owners, one immutable page query and8 held rows total.
#[derive(Default)]
pub(super) struct Discovery{states:BTreeMap<Context,Sweep>,query:Option<Query>,job:Option<Job>,page:Option<Page>,retry:Option<Instant>,counter:u32}
impl Discovery{
    pub(super) fn worker_running(&self)->bool{self.job.is_some()}
    fn publish_page(&mut self,sessions:&mut[Session],now:Instant,sent_unix:u32)->io::Result<bool>{
        let(Some(query),Some(page))=(&self.query,&self.page)else{return Ok(false);};
        let Some(s)=sessions.iter_mut().find(|s|current(s).as_ref()==Some(&query.context))else{
            self.query=None;self.page=None;self.retry=None;return Ok(true);
        };
        let state=self.states.entry(query.context.clone()).or_default();
        if let Some(code)=&page.rejected{println!("P08C_LATE_PENDING_REJECTED session={} code={code}",s.id);state.disabled=true;self.query=None;self.page=None;return Ok(true);}
        if page.rows.iter().filter(|r|!state.seen.contains(&r.arena)).count()+state.seen.len()>128{
            state.disabled=true;
            println!("P08C_LATE_NOTICE_ACCOUNT_DISABLED session={} code=ACCOUNT_OFFER_BUDGET128 durable_pending_unchanged=true",s.id);
            self.query=None;self.page=None;self.retry=None;return Ok(true);
        }
        let mut next=s.clone();let mut seen=state.seen.clone();
        for row in &page.rows{if seen.contains(&row.arena){continue;}if seen.len()>=128{return Err(bad("Account notice budget128; pending durable rows retained"));}
            if next.outbox.len()>=128{return Err(bad("native outbox full; durable pending page retained"));}
            next.outbox.push_back(super::late_results_notice::candidate_pending(row,sent_unix)?);seen.insert(row.arena);}
        next.drain_outbox()?;
        *s=next;state.seen=seen;state.cursor=page.next;state.next_at=Some(if page.next.is_some(){now}else{now+Duration::from_secs(30)});
        self.query=None;self.page=None;self.retry=None;Ok(true)
    }
    pub(super) fn poll(&mut self,sessions:&mut[Session],accounts:&BTreeSet<String>,config:Arc<identity091::Config>,now:Instant,can_start:bool,sent_unix:u32){
        self.states.retain(|context,_|sessions.iter().any(|s|current(s).as_ref()==Some(context)));
        if let Some(reply)=self.job.as_mut().and_then(Job::poll){let job=self.job.take().expect("polled job");let _=job.handle.join();
            match reply{Ok(page)=>{self.page=Some(page);self.retry=None;},Err(error)=>{println!("P08C_LATE_PENDING_RETRY error={error} same_request=true");self.retry=Some(now+Duration::from_secs(2));}}}
        if let Some(query)=&self.query{
            if !sessions.iter().any(|s|current(s).as_ref()==Some(&query.context)){
                // A running read is still joined/drained before another job;
                // its obsolete callback cannot enter the new Account epoch.
                if self.job.is_none(){self.query=None;self.page=None;self.retry=None;}return;
            }
        }
        // Whole page/Session clone is committed once. A late failure must not
        // resend the first successfully staged notice on the next attempt.
        if let Err(error)=self.publish_page(sessions,now,sent_unix){
            // Drop only this read-only volatile page, NEVER its SQL rows or
            // cursor/seen state. Deferring one owner's full native queue must
            // leave another owner's discovery runnable in the same channel
            // manager. A later sweep re-reads this unchanged cursor.
            if let Some(query)=&self.query{
                self.states.entry(query.context.clone()).or_default().next_at=Some(now+Duration::from_secs(2));
                println!("P08C_LATE_NOTICE_DEFERRED session={} error={error} durable_pending_unchanged=true native=NOT_RUN",query.context.session);
            }
            self.query=None;self.page=None;self.retry=None;
        }
        if self.job.is_some()||!can_start||self.retry.is_some_and(|at|now<at){return;}
        if self.query.is_none(){
            for s in sessions{let Some(context)=current(s)else{continue;};if !accounts.contains(&context.owner){continue;}
                if !self.states.contains_key(&context)&&self.states.len()>=6{continue;}
                let state=self.states.entry(context).or_default();if state.disabled||state.next_at.is_some_and(|at|now<at){continue;}
                let Some(counter)=self.counter.checked_add(1)else{println!("P08C_LATE_PENDING_DISABLED reason=counter_exhausted");return;};
                match Query::new(s,state.cursor,counter){Ok(query)=>{self.counter=counter;self.query=Some(query);break;},Err(error)=>{state.disabled=true;println!("P08C_LATE_PENDING_UNSUPPORTED error={error}");}}
            }
        }
        if let Some(query)=&self.query{match Job::start(query,config){Ok(job)=>{self.job=Some(job);self.retry=None;},Err(error)=>{println!("P08C_LATE_PENDING_SPAWN_RETRY error={error} same_request=true");self.retry=Some(now+Duration::from_secs(2));}}}
    }
}
#[cfg(test)]
#[path="late_results_pending_tests.rs"]mod tests;
