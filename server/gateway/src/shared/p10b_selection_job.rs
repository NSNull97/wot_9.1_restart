//! One bounded read-only readiness worker, dispatched after the native frame TX.
//! Its completion never changes Registry/Session by itself; the immutable room,
//! membership, revision and channel origin remain owned by the coordinator.
use std::{io,sync::{Arc,mpsc,atomic::{AtomicBool,Ordering}},thread::{self,JoinHandle}};
use crate::identity091::{self,room_selection::SelectionSnapshot};

static ACTIVE:AtomicBool=AtomicBool::new(false);
fn bad(message:&'static str)->io::Error{io::Error::new(io::ErrorKind::InvalidData,message)}

#[derive(Clone)]
pub(super) struct Task{
    pub(super) session:u32,
    pub(super) owner:Arc<identity091::Profile>,
    pub(super) expected_revision:u64,
    pub(super) native_inventory_id:u32,
    pub(super) run_id:String,
}
pub(super) struct Completion{pub(super) task:Task,pub(super) snapshot:SelectionSnapshot}
pub(super) struct Job{
    receiver:Option<mpsc::Receiver<io::Result<Completion>>>,worker:Option<JoinHandle<()>>,
}
impl Job{
    pub(super) fn start(task:Task,config:Arc<identity091::Config>)->io::Result<Self>{
        if task.session==0||!config.p06t_mixed_ammo||!config.profile13_battle||task.run_id!=config.battle_run_id
            ||!(13..=i32::MAX as u64).contains(&task.expected_revision)
            ||!(1..=i32::MAX as u32).contains(&task.native_inventory_id){return Err(bad("P10B selection worker origin"));}
        if ACTIVE.compare_exchange(false,true,Ordering::AcqRel,Ordering::Acquire).is_err(){
            return Err(bad("P10B readiness worker already active"));
        }
        let(sender,receiver)=mpsc::sync_channel(1);
        let started=thread::Builder::new().name("p10b-owned-selection".into()).spawn(move||{
            struct Guard;impl Drop for Guard{fn drop(&mut self){ACTIVE.store(false,Ordering::Release);}}let _guard=Guard;
            let result=std::panic::catch_unwind(std::panic::AssertUnwindSafe(||{
                let snapshot=config.select_room_loadout(&task.owner,task.expected_revision,task.native_inventory_id)?;
                Ok(Completion{task,snapshot})
            })).unwrap_or_else(|_|Err(bad("P10B readiness worker panic; no ready published")));
            if sender.send(result).is_err(){println!("P10B_SELECTION_OBSERVER_RETIRED ready_published=false reserve_started=false");}
        });
        let worker=match started{Ok(worker)=>worker,Err(error)=>{ACTIVE.store(false,Ordering::Release);return Err(error);}};
        Ok(Self{receiver:Some(receiver),worker:Some(worker)})
    }
    pub(super) fn poll(&mut self)->Option<io::Result<Completion>>{
        if self.worker.as_ref().is_some_and(|w|!w.is_finished()){return None;}
        let result=match self.receiver.as_ref()?.try_recv(){
            Ok(result)=>result,Err(mpsc::TryRecvError::Empty)=>return None,
            Err(mpsc::TryRecvError::Disconnected)=>Err(bad("P10B readiness worker disconnected")),
        };
        self.receiver=None;
        if self.worker.take().is_some_and(|w|w.join().is_err()){
            return Some(Err(bad("P10B readiness worker join failed")));
        }
        Some(result)
    }
}
