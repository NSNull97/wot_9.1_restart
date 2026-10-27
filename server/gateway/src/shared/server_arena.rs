//! ARENA-01: one arena = World + its participants' places + its own Jolt scene
//! runtime + the immutable template it resets from. The gateway thread keeps
//! sockets, sessions and account writers; an arena step crosses only the typed
//! `Command`/`Event` boundary below. With one arena the loop behaves exactly as
//! the single-World service did (every routing helper answers arena 0).
use super::*;
use std::panic::{self,AssertUnwindSafe};

/// Per-arena journal cursors for contact/impact/fragile log lines.
#[derive(Clone,Copy,Default)]
pub(super) struct Cursors {pub(super) contact:usize,pub(super) terrain:usize,pub(super) impact:usize,pub(super) fragile:usize}
impl Cursors {pub(super) fn reset(&mut self){*self=Self::default();}}

pub(super) struct Arena {
    pub(super) index:usize,
    pub(super) world:World,
    pub(super) integrated:Option<IntegratedRuntime>,
    pub(super) template:BattleTemplate,
    pub(super) cursors:Cursors,
}

/// Gateway -> arena. BW-01 carries the same messages over a local socket.
#[derive(Clone,Copy,Debug)]
pub(super) enum Command {Step{now:Instant,start:bool}}
/// Arena -> gateway. A panic inside the step is reported, never propagated.
#[derive(Debug)]
pub(super) enum Event {Stepped,Failed{stage:&'static str,error:io::Error}}

/// Battle ids of K arenas never meet: arena k counts up from r + k*2^56.
pub(super) const ARENA_ID_STRIDE:u64=1<<56;
pub(super) fn arena_ids(count:usize,random:u64)->io::Result<Vec<u64>> {
    if !(1..=crate::identity091::MAX_ARENAS).contains(&count) {return Err(model::bad());}
    let base=(random%(ARENA_ID_STRIDE-1))+1;
    (0..count as u64).map(|k|k.checked_mul(ARENA_ID_STRIDE).and_then(|o|o.checked_add(base))
        .filter(|id|*id<=i64::MAX as u64).ok_or_else(||model::bad())).collect()
}

impl Arena {
    pub(super) fn new(index:usize,world:World,integrated:Option<IntegratedRuntime>,template:BattleTemplate)->Self {
        Self{index,world,integrated,template,cursors:Cursors::default()}
    }
    /// One more arena from the same validated template, with its own battle id.
    pub(super) fn from_template(index:usize,template:&BattleTemplate,id:u64,now:Instant)->io::Result<Self> {
        // select() keeps this id: a clone for the template's own id, else a fresh battle.
        let mut world=World::new(id,now)?;let mut integrated=None;
        template.select(&mut world,&mut integrated,now)?;
        Ok(Self::new(index,world,integrated,template.clone()))
    }
    pub(super) fn started(&self)->bool {self.world.started.is_some()}
    pub(super) fn native_ready(&self)->bool {self.integrated.as_ref().is_none_or(IntegratedRuntime::ready_for_native)}
    pub(super) fn blocked(&self)->bool {self.integrated.as_ref().is_some_and(IntegratedRuntime::blocked)}
    pub(super) fn has_session(&self,id:u32)->bool {self.world.actors.iter().any(|a|a.session==Some(id))}
    pub(super) fn handle(&mut self,command:Command)->Event {
        let Command::Step{now,start}=command;
        let (world,integrated)=(&mut self.world,&mut self.integrated);
        match panic::catch_unwind(AssertUnwindSafe(||advance_battle(world,integrated,now,start))) {
            Ok(Ok(()))=>Event::Stepped,
            Ok(Err(error))=>Event::Failed{stage:"world_step",error},
            Err(_)=>Event::Failed{stage:"world_step_panic",error:io::Error::other("arena step panicked; arena contained")},
        }
    }
}

/// Runs each arena's command; arenas with simulation work run on their own
/// scoped thread when more than one has work, otherwise inline (old path).
pub(super) fn step_all(arenas:&mut [Arena],commands:&[Option<Command>])->Vec<Option<Event>> {
    debug_assert_eq!(arenas.len(),commands.len());
    let busy=arenas.iter().zip(commands).filter(|(a,c)|matches!(c,Some(Command::Step{start,..}) if *start||a.started())).count();
    if busy<2 {return arenas.iter_mut().zip(commands).map(|(a,c)|c.map(|c|a.handle(c))).collect();}
    std::thread::scope(|scope|{
        let handles=arenas.iter_mut().zip(commands).map(|(a,c)|c.map(|c|{
            if matches!(c,Command::Step{start:false,..})&&!a.started() {return Err(a.handle(c));}
            Ok(scope.spawn(move||a.handle(c)))
        })).collect::<Vec<_>>();
        handles.into_iter().map(|h|h.map(|h|match h {
            Err(inline)=>inline,
            // handle() already catches panics; a join error is the thread itself failing.
            Ok(join)=>join.join().unwrap_or_else(|_|Event::Failed{stage:"world_step_panic",error:io::Error::other("arena thread failed")}),
        })).collect()
    })
}

/// The arena this session belongs to: where it has an actor, whose battle its
/// native view shows, or whose battle it holds a reservation for. None = hangar.
pub(super) fn arena_of(s:&Session,arenas:&[Arena])->Option<usize> {
    if arenas.len()==1 {return Some(0);}
    if let Some(i)=arenas.iter().position(|a|a.has_session(s.id)) {return Some(i);}
    let c=s.shared.as_ref()?;
    if let Some(i)=c.view.as_ref().and_then(|v|arenas.iter().position(|a|a.world.id==v.id)) {return Some(i);}
    let battle=c.profile13.as_ref().and_then(|p|p.reservation_battle())?;
    arenas.iter().position(|a|a.world.id==battle)
}
pub(super) fn home(s:&Session,arenas:&[Arena],lobby:usize)->usize {arena_of(s,arenas).unwrap_or(lobby)}

/// Arena that takes the next Join reservation: first unstarted arena with a
/// free place, else first unstarted, else 0 (then every arena is running).
pub(super) fn lobby(arenas:&[Arena],table:&Table,retained:&[Session])->usize {
    if arenas.len()==1 {return 0;}
    arenas.iter().position(|a|!a.started()&&table.arena_admission_open(retained,&a.world))
        .or_else(||arenas.iter().position(|a|!a.started())).unwrap_or(0)
}
/// Sessions attached to an arena other than `except`.
pub(super) fn attached_outside(arenas:&[Arena],except:usize)->Vec<u32> {
    arenas.iter().filter(|a|a.index!=except).flat_map(|a|a.world.actors.iter().filter_map(|x|x.session)).collect()
}

#[cfg(test)]
#[path="server_arena_tests.rs"]
mod tests;
