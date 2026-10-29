//! BW-01: the ARENA-01 step of one arena runs in its own worker process. The
//! worker is this executable in `bw01-battle-worker` mode: it owns the arena's
//! Jolt scene runtime and runs `advance_battle`; the gateway keeps the World
//! between steps (membership, client input, publication, results, STAB-02
//! containment) and ships it across a loopback socket for each step. A lost
//! worker (exit, kill, EOF, malformed frame, timeout) is a battle failure of
//! that arena only: `contain_arena` returns its players to the hangar and
//! releases their reservations; the next battle starts a new worker.
use super::*;
use crate::bw_wire::{self,Arcs,Dec,Enc,Wire};
use rsa::rand_core::{OsRng,RngCore};
use std::{io::{Read,Write},net::{Ipv4Addr,TcpListener,TcpStream},process::{Child,Stdio},sync::OnceLock};
use std::panic::{self,AssertUnwindSafe};

pub(crate) const POLICY:&str="project.bw01.process-per-arena.v1";
const MAGIC:[u8;4]=*b"BW01";
/// One frame. The first step of a connection carries the map resources once
/// (terrain, obstacle meshes, vehicle geometry); later steps name them by id.
pub(crate) const MAX_FRAME:usize=256<<20;
const HANDSHAKE:Duration=Duration::from_secs(10);
/// A worker that could not start is not respawned every 5 ms tick.
const RESPAWN_BACKOFF:Duration=Duration::from_secs(1);
const TOKEN:usize=32;
const AUTH:u8=1;const HELLO:u8=2;const READY:u8=3;const STEP:u8=4;const STEPPED:u8=5;

#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub(crate) struct Settings {pub(crate) step_timeout:Duration,pub(crate) startup_timeout:Duration,pub(crate) catalog_v1:bool}
impl Settings {
    pub(crate) fn from_config(c:&crate::identity091::BattleWorker,catalog_v1:bool)->Self {
        Self{step_timeout:c.step_timeout,startup_timeout:c.startup_timeout,catalog_v1}
    }
}

/// The arena's Jolt runtime as the gateway's own (never started) object names
/// it. A new generation (every `select`/`replace`) rebuilds it in the worker.
pub(super) struct RuntimeSpec {
    generation:u64,map:MapId,pool:Arc<crate::map_drive_worker091::Pool>,
    removal:Option<crate::map_drive_worker091::RemovalSpec>,catalog:Option<crate::map_drive_worker091::CatalogSpec>,
    shared:Option<Arc<super::super::profile13_templates::SharedResources>>,
}
// BW-01 wire codec (tools/bw01_wire_gen.py): RuntimeSpec
impl crate::bw_wire::Wire for RuntimeSpec {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{generation,map,pool,removal,catalog,shared}=self;W::put(generation,bw_o);W::put(map,bw_o);W::put(pool,bw_o);W::put(removal,bw_o);W::put(catalog,bw_o);W::put(shared,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{generation:W::get(bw_i)?,map:W::get(bw_i)?,pool:W::get(bw_i)?,removal:W::get(bw_i)?,catalog:W::get(bw_i)?,shared:W::get(bw_i)?})}
}
// end BW-01 wire codec
impl RuntimeSpec {
    fn of(r:&IntegratedRuntime)->Self {
        Self{generation:r.generation,map:r.map_id,pool:r.pool.clone(),removal:r.removal.clone(),catalog:r.catalog.clone(),
            shared:r.batch.as_ref().map(|b|b.resources().clone())}
    }
    /// Same construction as `BattleTemplate::runtime`, keeping the gateway's generation.
    fn build(self)->io::Result<IntegratedRuntime> {
        let mut r=IntegratedRuntime::new_for_map(self.pool,self.map);
        r.removal=self.removal;r.catalog=self.catalog;r.generation=self.generation;
        if let Some(shared)=self.shared {r.batch=Some(BatchRuntime::new(shared,r.catalog.clone().ok_or_else(||model::bad())?));}
        Ok(r)
    }
}

/// SHA-256 of this executable: gateway and worker must be the same build.
fn build_sha256()->io::Result<&'static str> {
    static BUILD:OnceLock<Result<String,String>>=OnceLock::new();
    BUILD.get_or_init(||(||->io::Result<String> {
        let mut file=fs::File::open(std::env::current_exe()?)?;let mut hash=Sha256::new();let mut chunk=vec![0u8;1<<20];
        loop {let n=file.read(&mut chunk)?;if n==0 {break;}hash.update(&chunk[..n]);}
        Ok(format!("{:x}",hash.finalize()))
    })().map_err(|e|e.to_string())).as_deref().map_err(|e|io::Error::other(format!("bw01 build hash: {e}")))
}

fn lost(what:impl std::fmt::Display)->io::Error {io::Error::new(io::ErrorKind::BrokenPipe,format!("battle worker: {what}"))}

fn write_frame(s:&mut TcpStream,kind:u8,payload:&[u8],deadline:Instant)->io::Result<()> {
    if payload.len()>MAX_FRAME {return Err(bw_wire::bad("frame size"));}
    let left=deadline.checked_duration_since(Instant::now()).filter(|d|!d.is_zero()).ok_or_else(||io::Error::new(io::ErrorKind::TimedOut,"battle worker: write deadline"))?;
    s.set_write_timeout(Some(left))?;
    let mut head=[0u8;9];head[..4].copy_from_slice(&MAGIC);head[4]=kind;head[5..].copy_from_slice(&(payload.len() as u32).to_le_bytes());
    s.write_all(&head)?;s.write_all(payload)?;s.flush()
}
/// Exactly `buf.len()` bytes before `deadline` (None: wait without limit).
fn read_exact_until(s:&mut TcpStream,buf:&mut [u8],deadline:Option<Instant>)->io::Result<()> {
    let mut done=0;
    while done<buf.len() {
        let left=match deadline {
            None=>None,
            Some(d)=>Some(d.checked_duration_since(Instant::now()).filter(|d|!d.is_zero())
                .ok_or_else(||io::Error::new(io::ErrorKind::TimedOut,"battle worker: reply deadline"))?),
        };
        s.set_read_timeout(left)?;
        match s.read(&mut buf[done..]) {
            Ok(0)=>return Err(io::Error::new(io::ErrorKind::UnexpectedEof,"battle worker: connection closed")),
            Ok(n)=>done+=n,
            Err(e) if e.kind()==io::ErrorKind::Interrupted=>{},
            Err(e) if matches!(e.kind(),io::ErrorKind::WouldBlock|io::ErrorKind::TimedOut)=>
                return Err(io::Error::new(io::ErrorKind::TimedOut,"battle worker: reply deadline")),
            Err(e)=>return Err(e),
        }
    }
    Ok(())
}
fn read_frame(s:&mut TcpStream,kind:u8,deadline:Option<Instant>)->io::Result<Vec<u8>> {
    let mut head=[0u8;9];read_exact_until(s,&mut head,deadline)?;
    let len=u32::from_le_bytes(head[5..].try_into().expect("four bytes")) as usize;
    if head[..4]!=MAGIC||head[4]!=kind||len>MAX_FRAME {return Err(bw_wire::bad("frame header"));}
    // Grow with the bytes that actually arrive, never by the announced length alone.
    let mut payload=Vec::new();let mut filled=0;
    while filled<len {
        let step=(len-filled).min(1<<20);payload.resize(filled+step,0);
        read_exact_until(s,&mut payload[filled..filled+step],deadline)?;filled+=step;
    }
    Ok(payload)
}

/// Gateway side of one live worker process.
/// `sent`: runtime generation whose full spec this worker already has.
pub(super) struct Link {child:Child,pid:u32,stream:TcpStream,arcs:Arcs,anchor:Instant,seq:u32,primed:bool,sent:Option<u64>}
impl Drop for Link {fn drop(&mut self){let _=self.child.kill();let _=self.child.wait();}}

#[cfg(not(test))]
fn worker_command(port:u16)->io::Result<std::process::Command> {
    let mut c=std::process::Command::new(std::env::current_exe()?);c.arg("bw01-battle-worker").arg(port.to_string());Ok(c)
}
/// Test binaries have no service `main`: the worker is the ignored entry test below.
#[cfg(test)]
fn worker_command(port:u16)->io::Result<std::process::Command> {
    let mut c=std::process::Command::new(std::env::current_exe()?);
    c.args(["--exact","gateway091::shared::server::battle_worker::tests::bw01_worker_process_entry","--ignored","--nocapture","--test-threads=1","-q"])
        .env("BW01_WORKER_PORT",port.to_string());Ok(c)
}

impl Link {
    fn spawn(settings:&Settings)->io::Result<Self> {
        let build=build_sha256()?;
        let listener=TcpListener::bind((Ipv4Addr::LOCALHOST,0))?;let port=listener.local_addr()?.port();
        let mut token=[0u8;TOKEN];OsRng.fill_bytes(&mut token);
        let mut child=worker_command(port)?.stdin(Stdio::piped()).stdout(Stdio::inherit()).stderr(Stdio::inherit()).spawn()?;
        let pid=child.id();
        let connected=(||->io::Result<(TcpStream,Instant)> {
            // The token goes through the child's stdin, never its command line.
            let hex=token.iter().map(|b|format!("{b:02x}")).collect::<String>();
            {let mut stdin=child.stdin.take().ok_or_else(||lost("stdin"))?;stdin.write_all(hex.as_bytes())?;}
            let deadline=Instant::now()+HANDSHAKE;listener.set_nonblocking(true)?;
            let mut stream=loop {
                match listener.accept() {
                    Ok((s,peer)) if peer.ip().is_loopback()=>break s,
                    Ok(_)=>continue,
                    Err(e) if e.kind()==io::ErrorKind::WouldBlock=>{
                        if let Some(status)=child.try_wait()? {return Err(lost(format!("exited during handshake: {status}")));}
                        if Instant::now()>=deadline {return Err(io::Error::new(io::ErrorKind::TimedOut,"battle worker: handshake deadline"));}
                        std::thread::sleep(Duration::from_millis(2));
                    },
                    Err(e)=>return Err(e),
                }
            };
            stream.set_nonblocking(false)?;stream.set_nodelay(true)?;
            let mut arcs=Arcs::new(false);let anchor=Instant::now();
            let (got,their):([u8;TOKEN],String)=bw_wire::decode(&read_frame(&mut stream,AUTH,Some(deadline))?,anchor,&mut arcs)?;
            if got!=token {return Err(lost("token mismatch"));}
            if their!=build {return Err(lost("build mismatch"));}
            // The worker takes its anchor on receipt: instants differ by the transit time only.
            let anchor=Instant::now();
            write_frame(&mut stream,HELLO,&bw_wire::encode(&(build.to_owned(),settings.catalog_v1),anchor,&mut arcs)?,deadline)?;
            let _:String=bw_wire::decode(&read_frame(&mut stream,READY,Some(deadline))?,anchor,&mut arcs)?;
            Ok((stream,anchor))
        })();
        match connected {
            Ok((stream,anchor))=>{
                println!("BW01_WORKER_STARTED pid={pid} port={port} build_sha256={build} policy={POLICY}");
                Ok(Self{child,pid,stream,arcs:Arcs::new(false),anchor,seq:0,primed:false,sent:None})
            },
            Err(e)=>{let _=child.kill();let _=child.wait();Err(e)},
        }
    }
    pub(super) fn pid(&self)->u32 {self.pid}
}

/// Per-arena worker state kept by the gateway.
pub(super) struct Remote {
    pub(super) settings:Settings,
    pub(super) link:Option<Link>,
    retry_at:Option<Instant>,
    /// Generation of the worker's runtime that `native_ready`/`blocked` describe.
    generation:Option<u64>,native_ready:bool,blocked:bool,
    pending:Option<(u32,Instant)>,
    pub(super) steps:u64,pub(super) step_ns:u64,pub(super) frame_bytes:(usize,usize),
}
impl Remote {
    pub(super) fn new(settings:Settings)->Self {
        Self{settings,link:None,retry_at:None,generation:None,native_ready:false,blocked:false,pending:None,steps:0,step_ns:0,frame_bytes:(0,0)}
    }
    /// The worker's view of the runtime, when it describes the current one.
    pub(super) fn reports(&self,r:&IntegratedRuntime)->Option<(bool,bool)> {
        (self.generation==Some(r.generation)).then_some((self.native_ready,self.blocked))
    }
    pub(super) fn pid(&self)->Option<u32> {self.link.as_ref().map(Link::pid)}
    fn drop_link(&mut self,arena:usize,battle:u64,why:&io::Error) {
        if let Some(link)=self.link.take() {
            println!("BW01_WORKER_LOST arena={arena} battle={battle} pid={} error={why} worker_killed=true",link.pid);
        }
        self.pending=None;self.generation=None;
    }
}

/// Send the step. `Err(event)` = settled here (nothing to ship, or failed).
pub(super) fn begin(a:&mut arena::Arena,command:arena::Command)->Result<(),arena::Event> {
    let arena::Command::Step{now,start}=command;
    let (index,battle)=(a.index,a.world.id);
    let Some(w)=a.worker.as_deref_mut() else {return Err(a.handle(command));};
    // An unstarted World without a start is a no-op step in any process;
    // a new worker still takes it once, to receive the map resources early.
    let idle=!start&&a.world.started.is_none();
    if idle&&w.link.as_ref().is_none_or(|l|l.primed) {
        if w.link.is_some()||w.retry_at.is_some_and(|t|Instant::now()<t) {return Err(arena::Event::Stepped);}
    }
    if w.link.is_none() {
        if !idle&&w.retry_at.is_some_and(|t|Instant::now()<t) {
            return Err(arena::Event::Failed{stage:"battle_worker_spawn",error:lost("respawn backoff after a failed start")});
        }
        match Link::spawn(&w.settings) {
            Ok(link)=>{w.link=Some(link);w.retry_at=None;},
            Err(e)=>{
                w.retry_at=Some(Instant::now()+RESPAWN_BACKOFF);
                println!("BW01_WORKER_SPAWN_FAILED arena={index} battle={battle} error={e} retry_ms={}",RESPAWN_BACKOFF.as_millis());
                return Err(if idle {arena::Event::Stepped} else {arena::Event::Failed{stage:"battle_worker_spawn",error:e}});
            },
        }
    }
    let link=w.link.as_mut().expect("link set above");
    link.seq=link.seq.wrapping_add(1);
    let mut out=Enc::new(link.anchor,&mut link.arcs);
    link.seq.put(&mut out);now.put(&mut out);start.put(&mut out);
    // Runtime: 0 none, 1 the generation the worker already holds, 2 a full spec (new generation).
    match &a.integrated {
        None=>{out.tag(0);link.sent=None;},
        Some(r) if link.sent==Some(r.generation)=>{out.tag(1);r.generation.put(&mut out);},
        Some(r)=>{out.tag(2);RuntimeSpec::of(r).put(&mut out);link.sent=Some(r.generation);},
    }
    a.world.put(&mut out);
    let timeout=if link.primed {w.settings.step_timeout} else {w.settings.startup_timeout};
    let deadline=Instant::now()+timeout;
    let sent=out.finish().and_then(|frame|{w.frame_bytes.0=frame.len();write_frame(&mut link.stream,STEP,&frame,deadline)});
    match sent {
        Ok(())=>{w.pending=Some((link.seq,deadline));Ok(())},
        Err(e)=>{w.drop_link(index,battle,&e);Err(arena::Event::Failed{stage:"battle_worker_lost",error:e})},
    }
}

/// Wait for the step sent by `begin`; the returned World replaces the gateway's.
pub(super) fn finish(a:&mut arena::Arena)->arena::Event {
    let (index,battle)=(a.index,a.world.id);
    let Some(w)=a.worker.as_deref_mut() else {return arena::Event::Failed{stage:"battle_worker_lost",error:lost("no worker state")};};
    let received=(||->io::Result<(u8,String,Option<World>)> {
        let (seq,deadline)=w.pending.take().ok_or_else(||lost("no step in flight"))?;
        let link=w.link.as_mut().ok_or_else(||lost("no link"))?;
        let frame=read_frame(&mut link.stream,STEPPED,Some(deadline))?;w.frame_bytes.1=frame.len();
        let mut r=Dec::new(&frame,link.anchor,&mut link.arcs);
        let (got,outcome,error,generation,native_ready,blocked,step_ns)=<(u32,u8,String,Option<u64>,bool,bool,u64)>::get(&mut r)?;
        let world=Option::<World>::get(&mut r)?;r.done()?;
        if got!=seq||outcome>3 {return Err(bw_wire::bad("reply"));}
        // A runtime the worker could not build is not held there: send the full spec again.
        if outcome==3 {link.sent=None;}
        link.primed=true;w.generation=generation;w.native_ready=native_ready;w.blocked=blocked;
        w.steps+=1;w.step_ns=step_ns;
        Ok((outcome,error,world))
    })();
    match received {
        Ok((outcome,error,world))=>{
            if let Some(world)=world {a.world=world;}
            match outcome {
                0=>arena::Event::Stepped,
                1=>arena::Event::Failed{stage:"world_step",error:io::Error::other(error)},
                2=>arena::Event::Failed{stage:"world_step_panic",error:io::Error::other(error)},
                _=>arena::Event::Failed{stage:"battle_worker_runtime",error:io::Error::other(error)},
            }
        },
        Err(e)=>{w.drop_link(index,battle,&e);arena::Event::Failed{stage:"battle_worker_lost",error:e}},
    }
}

/// All arenas: every remote step is sent before any reply is awaited, so
/// workers run in parallel like the ARENA-01 scoped threads.
pub(super) fn step_all(arenas:&mut [arena::Arena],commands:&[Option<arena::Command>])->Vec<Option<arena::Event>> {
    let mut events:Vec<Option<Option<arena::Event>>>=arenas.iter_mut().zip(commands).map(|(a,c)|match c {
        None=>Some(None),
        Some(c)=>match begin(a,*c) {Ok(())=>None,Err(event)=>Some(Some(event))},
    }).collect();
    for (a,e) in arenas.iter_mut().zip(events.iter_mut()) {if e.is_none() {*e=Some(Some(finish(a)));}}
    events.into_iter().map(|e|e.flatten()).collect()
}

/// The worker process: `sr-gateway bw01-battle-worker PORT`, token on stdin.
pub fn run(port:u16)->io::Result<()> {
    // Ids decoded from the gateway are checked against this process's registry.
    super::super::generated_vehicles::registry()?;
    let build=build_sha256()?;
    let mut hex=String::new();io::stdin().take(TOKEN as u64*2+1).read_to_string(&mut hex)?;
    if hex.len()!=TOKEN*2 {return Err(lost("token"));}
    let mut token=[0u8;TOKEN];
    for (k,b) in token.iter_mut().enumerate() {*b=u8::from_str_radix(&hex[2*k..2*k+2],16).map_err(|_|lost("token"))?;}
    let mut s=TcpStream::connect((Ipv4Addr::LOCALHOST,port))?;s.set_nodelay(true)?;
    let mut arcs=Arcs::new(true);let deadline=Instant::now()+HANDSHAKE;
    write_frame(&mut s,AUTH,&bw_wire::encode(&(token,build.to_owned()),Instant::now(),&mut arcs)?,deadline)?;
    let hello=read_frame(&mut s,HELLO,Some(deadline))?;let anchor=Instant::now();
    let (their,catalog_v1):(String,bool)=bw_wire::decode(&hello,anchor,&mut arcs)?;
    if their!=build {return Err(lost("build mismatch"));}
    if catalog_v1 {crate::profile13_v2091::enable_catalog_v1()?;}
    write_frame(&mut s,READY,&bw_wire::encode(&build.to_owned(),anchor,&mut arcs)?,deadline)?;
    let mut runtime:Option<IntegratedRuntime>=None;
    loop {
        // The gateway may leave an idle arena unstepped for long; EOF ends the worker.
        let frame=match read_frame(&mut s,STEP,None) {
            Ok(f)=>f,
            Err(e) if e.kind()==io::ErrorKind::UnexpectedEof=>return Ok(()),
            Err(e)=>return Err(e),
        };
        let mut r=Dec::new(&frame,anchor,&mut arcs);
        let (seq,now,start)=<(u32,Instant,bool)>::get(&mut r)?;
        let spec=match r.tag()? {
            0=>None,
            1=>{let g=u64::get(&mut r)?;if runtime.as_ref().is_none_or(|x|x.generation!=g) {return Err(bw_wire::bad("runtime generation"));}Some(Err(g))},
            2=>Some(Ok(RuntimeSpec::get(&mut r)?)),
            _=>return Err(bw_wire::bad("runtime tag")),
        };
        let mut world=World::get(&mut r)?;r.done()?;
        let rebuilt=match spec {
            None=>{runtime=None;Ok(())},
            Some(Err(_))=>Ok(()),
            Some(Ok(spec)) if runtime.as_ref().is_some_and(|r|r.generation==spec.generation)=>Ok(()),
            // Drop the old runtime (its scene process) before the new one, as `replace` does.
            Some(Ok(spec))=>{runtime=None;spec.build().map(|r|{runtime=Some(r);})},
        };
        let t=Instant::now();
        let (outcome,error)=match rebuilt {
            Err(e)=>(3u8,e.to_string()),
            Ok(())=>match panic::catch_unwind(AssertUnwindSafe(||advance_battle(&mut world,&mut runtime,now,start))) {
                Ok(Ok(()))=>(0,String::new()),
                Ok(Err(e))=>(1,e.to_string()),
                Err(_)=>(2,"arena step panicked in battle worker; arena contained".to_owned()),
            },
        };
        let step_ns=u64::try_from(t.elapsed().as_nanos()).unwrap_or(u64::MAX);
        let state=runtime.as_ref().map(|r|(r.ready_for_native(),r.blocked(),Some(r.generation))).unwrap_or((true,false,None));
        let mut out=Enc::new(anchor,&mut arcs);
        (seq,outcome,error,state.2,state.0,state.1,step_ns).put(&mut out);out.bytes(&[1]);world.put(&mut out);
        write_frame(&mut s,STEPPED,&out.finish()?,Instant::now()+HANDSHAKE)?;
    }
}

#[cfg(test)]
pub(super) mod tests {
    use super::*;
    /// The worker process of test builds (`worker_command`); a no-op unless a
    /// gateway under test started this binary with its port.
    #[test]
    #[ignore]
    fn bw01_worker_process_entry() {
        let Some(port)=std::env::var("BW01_WORKER_PORT").ok().and_then(|p|p.parse::<u16>().ok()) else {return;};
        if let Err(e)=run(port) {eprintln!("BW01_WORKER_FAILED error={e}");std::process::exit(3);}
    }
    pub(crate) fn settings()->Settings {
        Settings{step_timeout:Duration::from_millis(2000),startup_timeout:Duration::from_millis(30000),catalog_v1:false}
    }
    /// The live worker of an arena, killed from outside like `taskkill /F`.
    pub(crate) fn kill(a:&arena::Arena)->u32 {
        let pid=a.worker.as_ref().and_then(|w|w.pid()).expect("live worker");
        let status=std::process::Command::new("taskkill").args(["/F","/PID",&pid.to_string()]).stdout(Stdio::null()).status().unwrap();
        assert!(status.success(),"taskkill {pid}");pid
    }
}
