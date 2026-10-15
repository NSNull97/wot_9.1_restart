//! P05C component coordinator. World/native integration remains in shared/server.
//! This module never accepts a partial actor frame or commits damage by itself.
use std::{io,sync::Arc,time::Instant};
use crate::scene_worker::{Artifacts,Frame,Input,Scene,SceneSpec,Worker};
pub struct Runtime{worker:Worker,last_frame:u32,last_tick:u32}
impl Runtime{
    pub fn launch(artifacts:Artifacts,spec:Arc<SceneSpec>,generation:u32,scene:Scene,now:Instant)->io::Result<Self>{
        Ok(Self{worker:Worker::launch(artifacts,spec,generation,scene,now)?,last_frame:0,last_tick:180})}
    pub fn process_id(&self)->u32{self.worker.process_id()}
    pub fn advance(&mut self,inputs:&[Input],now:Instant)->io::Result<u32>{self.worker.advance(inputs,now)}
    pub fn poll(&mut self,now:Instant)->io::Result<Option<Frame>>{
        let Some(frame)=self.worker.poll(now)? else{return Ok(None);};
        if frame.sequence!=0&&(frame.sequence!=self.last_frame+1||frame.tick!=self.last_tick+6){
            return Err(io::Error::new(io::ErrorKind::InvalidData,"shared scene complete batch skipped/regressed"));}
        self.last_frame=frame.sequence;self.last_tick=frame.tick;Ok(Some(frame))
    }
    /// Caller validates per-actor scalar evidence and stages its domain candidate
    /// before asking for this physical commit. No following advance until ACK.
    pub fn sync_removed(&mut self,scene:Scene,now:Instant)->io::Result<()>{self.worker.sync_removed(scene,now)}
    pub fn take_scene_ack(&mut self)->bool{self.worker.take_scene_ack()}
    pub fn scene(&self)->&Scene{self.worker.scene()}
    pub fn prepared_ids(&self)->&[u32]{self.worker.prepared_ids()}
    pub fn pending(&self)->bool{self.worker.pending()}
    pub fn ready(&self)->bool{self.worker.ready()}
    pub fn shutdown(self)->io::Result<()>{self.worker.shutdown()}
}
