//! P05C component coordinator. World/native integration remains in shared/server.
//! This module never accepts a partial actor frame or commits damage by itself.
use std::{io,sync::Arc,time::Instant};
use crate::scene_worker::{Artifacts,Frame,Input,Scene,SceneSpec,TurretBody,TurretTrajectory,Worker};
pub struct Runtime{worker:Worker,last_frame:u32,last_tick:u32}
impl Runtime{
    pub fn launch(artifacts:Artifacts,spec:Arc<SceneSpec>,generation:u32,scene:Scene)->io::Result<Self>{
        Ok(Self{worker:Worker::launch(artifacts,spec,generation,scene,Instant::now())?,last_frame:0,last_tick:180})}
    pub fn process_id(&self)->u32{self.worker.process_id()}
    pub fn record_scheduler_lag(&self,now:Instant,deadline:Instant){self.worker.record_scheduler_lag(now,deadline)}
    // IPC wall time belongs to this process. The simulation's step instant
    // can predate dispatch by a gateway stall or a BW-01 transfer.
    pub fn advance(&mut self,inputs:&[Input])->io::Result<u32>{self.worker.advance(inputs,Instant::now())}
    pub fn poll(&mut self)->io::Result<Option<Frame>>{
        let Some(frame)=self.worker.poll(Instant::now())? else{return Ok(None);};
        if frame.sequence!=0&&(frame.sequence!=self.last_frame+1||frame.tick!=self.last_tick+6){
            return Err(io::Error::new(io::ErrorKind::InvalidData,"shared scene complete batch skipped/regressed"));}
        self.last_frame=frame.sequence;self.last_tick=frame.tick;Ok(Some(frame))
    }
    /// Caller validates per-actor scalar evidence and stages its domain candidate
    /// before asking for this physical commit. No following advance until ACK.
    pub fn sync_removed(&mut self,scene:Scene)->io::Result<()>{self.worker.sync_removed(scene,Instant::now())}
    pub fn take_scene_ack(&mut self)->bool{self.worker.take_scene_ack()}
    /// TURRET-01: one detached-turret body simulation; the reply is taken
    /// with `take_turret` after a later `poll` returned no frame.
    pub fn launch_turret(&mut self,body:&TurretBody)->io::Result<()>{self.worker.launch_turret(body,Instant::now())}
    pub fn take_turret(&mut self)->Option<TurretTrajectory>{self.worker.take_turret()}
    pub fn scene(&self)->&Scene{self.worker.scene()}
    pub fn prepared_ids(&self)->&[u32]{self.worker.prepared_ids()}
    pub fn pending(&self)->bool{self.worker.pending()}
    pub fn ready(&self)->bool{self.worker.ready()}
    pub fn shutdown(self)->io::Result<()>{self.worker.shutdown()}
}
