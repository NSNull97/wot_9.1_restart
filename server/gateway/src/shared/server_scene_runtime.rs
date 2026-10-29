//! One owned IPC7 process per profile13 battle. The accepted IPC6 scalar parser
//! verifies every actor before a candidate World may cross the single scene ACK.
use super::*;
use crate::scene_worker::{self,Scene,SceneSpec,Input,TurretBody};
use super::super::ammo_detonation as rack;
use super::super::{scene_runtime::Runtime,profile13_templates::SharedResources};
use sha2::Digest;

/// Explicit LAB quantization to the existing IPC7 control alphabet. Fractional
/// steering uses a four-domain-tick duty cycle; exact transmitted inputs and
/// the domain tick are logged. No unsupported cruise values are invented.
fn duty_active(tick:u32,scale:f32)->bool {
    scale>=1. || scale>0. && (tick.saturating_sub(1000)%4)<(scale*4.).floor()as u32
}
fn actor_input(actor:&model::Actor,tick:u32,allows_actions:bool)->io::Result<Input> {
    if actor.session.is_none() || !actor.ready || !actor.alive() || !allows_actions {return Ok(Input::STOP);}
    let input=actor.input;
    if tick<1000 || !(-1..=1).contains(&input.throttle)||!(-1..=1).contains(&input.steer)
        || !crate::map_drive_worker091::partial_cruise_valid(input.throttle,false,input.speed_percent) {return Err(model::bad());}
    let Some(devices)=&actor.devices else {return Ok(Input {throttle:input.throttle,steer:input.steer,
        brake:input.throttle==0&&input.steer==0,speed_percent:input.speed_percent});};
    if devices.profile().index()!=actor.vehicle_kind().index() {return Err(model::bad());}
    let caps=devices.capabilities();caps.validate()?;
    let mut throttle=if caps.drive_scale>0. {input.throttle}else{0};
    let steer=if duty_active(tick,caps.steer_scale) {input.steer}else{0};
    let scaled=f32::from(input.speed_percent)*caps.drive_scale;
    // LAB minimum is25% when forward motion remains possible. Critical and
    // driver factors compound before flooring to the supported alphabet.
    let mut speed=if scaled>=100. {100}else if scaled>=50. {50}else{25};
    if throttle<0 && speed==25 {
        // The accepted protocol permits reverse100/50, but never reverse25.
        // Use half-duty valid reverse50 rather than emitting an invalid row.
        speed=50;if !duty_active(tick,0.5) {throttle=0;}
    }
    if throttle==0 {speed=100;}
    Ok(Input {throttle,steer,brake:throttle==0&&steer==0,speed_percent:speed})
}

pub(super) struct BatchRuntime {
    resources:Arc<SharedResources>,catalog:crate::map_drive_worker091::CatalogSpec,
    spec:Option<Arc<SceneSpec>>,runtime:Option<Runtime>,
    startup:Option<mpsc::Receiver<io::Result<(Arc<SceneSpec>,Runtime)>>>,
    sessions:Vec<u32>,started_at:Option<Instant>,dispatched:Option<Instant>,
    settled:bool,staged:Option<World>,generation:u32,held:Option<scene_worker::Frame>,lag_resync:LagResync,
}
impl BatchRuntime {
    pub(super) fn new(resources:Arc<SharedResources>,catalog:crate::map_drive_worker091::CatalogSpec)->Self{
        Self{resources,catalog,spec:None,runtime:None,startup:None,sessions:Vec::new(),started_at:None,
            dispatched:None,settled:false,staged:None,generation:1,held:None,lag_resync:LagResync::default()}
    }
    pub(super) fn blocked(&self)->bool{self.staged.is_some()||self.runtime.as_ref().is_some_and(|r|!r.prepared_ids().is_empty())}
    pub(super) fn ready_for_native(&self)->bool{self.settled&&!self.blocked()&&self.runtime.as_ref().is_some_and(|r|r.ready())}
    /// TURRET-01: install a worker trajectory into the World (and into a staged
    /// candidate that also owns that flight). A reply for no awaiting flight
    /// is a protocol fault, never dropped.
    fn install_turret(&mut self,world:&mut World)->io::Result<()>{
        let Some(t)=self.runtime.as_mut().and_then(|r|r.take_turret())else{return Ok(());};
        let trajectory=rack::Trajectory{samples:t.samples.iter().map(|(p,d)|rack::JointPose{position:*p,direction:*d}).collect(),slept:t.slept};
        let mut installed=false;
        if world.pending_turret_launches().contains(&t.slot){world.install_turret_trajectory(t.slot,trajectory.clone())?;installed=true;}
        if let Some(staged)=&mut self.staged{
            if staged.pending_turret_launches().contains(&t.slot){staged.install_turret_trajectory(t.slot,trajectory.clone())?;installed=true;}
        }
        if !installed{return Err(model::bad());}
        let rest=trajectory.samples.last().ok_or_else(||model::bad())?;
        println!("TURRET01_FLIGHT battle={} slot={} samples={} slept={} substeps={} rest_position={:?} rest_direction={:?} policy={}",
            world.id,t.slot,t.samples.len(),t.slept,t.substeps,rest.position,rest.direction,scene_worker::TURRET_POLICY);
        Ok(())
    }
    /// One body request when the worker is idle. Returns true if sent; the
    /// next advance then waits for its reply (the debris world never steps
    /// the battle world).
    fn launch_turret(&mut self,world:&World,now:Instant)->io::Result<bool>{
        let Some(runtime)=self.runtime.as_mut()else{return Ok(false);};
        if runtime.pending()||!runtime.ready(){return Ok(false);}
        let Some(slot)=world.pending_turret_launches().first().copied()else{return Ok(false);};
        let r=world.turret_launch_request(slot)?;
        let body=TurretBody{slot,position:r.joint.position,direction:r.joint.direction,linear_velocity:r.launch.linear_velocity,
            angular_velocity:r.launch.angular_velocity,turret_points:r.turret_points,gun_points:r.gun_points,wreck_slots:r.wreck_slots};
        runtime.launch_turret(&body,now)?;
        let event=world.turret_flights().iter().find(|f|f.event().target()==slot).ok_or_else(||model::bad())?.event();
        println!("TURRET01_LAUNCH battle={} slot={} shot={} attacker={} tick={} joint={:?} linear={:?} angular={:?} rng_draws={:?} turret_points={} gun_points={} wrecks={:?} policy={}",
            world.id,slot,event.shot(),event.attacker(),event.tick(),r.joint,r.launch.linear_velocity,r.launch.angular_velocity,r.launch.draws,
            body.turret_points.len(),body.gun_points.len(),body.wreck_slots,rack::JOLT_POLICY);
        Ok(true)
    }
    /// TURRET-01 test evidence: the same worker simulates the body request of
    /// an already installed flight again with the wrecks of its original
    /// request; blocks until its reply.
    #[cfg(test)]
    pub(super) fn relaunch_turret_for_test(&mut self,world:&World,slot:usize,wrecks:&[usize])->io::Result<scene_worker::TurretTrajectory>{
        let mut r=world.turret_launch_request(slot)?;r.wreck_slots=wrecks.to_vec();
        let body=TurretBody{slot,position:r.joint.position,direction:r.joint.direction,linear_velocity:r.launch.linear_velocity,
            angular_velocity:r.launch.angular_velocity,turret_points:r.turret_points,gun_points:r.gun_points,wreck_slots:r.wreck_slots};
        let runtime=self.runtime.as_mut().ok_or_else(||model::bad())?;
        let deadline=Instant::now()+Duration::from_secs(5);
        // End-of-test evidence only: a battle frame still in flight is dropped.
        while runtime.pending(){let _=runtime.poll(Instant::now())?;
            if Instant::now()>deadline{return Err(model::bad());}std::thread::sleep(Duration::from_millis(1));}
        runtime.launch_turret(&body,Instant::now())?;
        loop{runtime.poll(Instant::now())?;if let Some(t)=runtime.take_turret(){return Ok(t);}
            if Instant::now()>deadline{return Err(model::bad());}std::thread::sleep(Duration::from_millis(1));}
    }
    /// After the frozen outcome the battle world is no longer advanced, but a
    /// detonation that ended the battle still needs its body. A pending battle
    /// advance reply is consumed and discarded here (the outcome is frozen).
    pub(super) fn turrets_after_outcome(&mut self,world:&mut World,now:Instant)->io::Result<()>{
        let Some(runtime)=self.runtime.as_mut()else{return Ok(());};
        if world.pending_turret_launches().is_empty(){return Ok(());}
        if runtime.pending()&&runtime.poll(now)?.is_some(){
            println!("TURRET01_OUTCOME_FRAME_DISCARDED battle={} reason=outcome_frozen",world.id);
        }
        self.install_turret(world)?;self.launch_turret(world,now)?;Ok(())
    }
    pub(super) fn failure_snapshot(&self)->serde_json::Value{serde_json::json!({
        "process_id":self.runtime.as_ref().map(|r|r.process_id()),"startup":self.startup.is_some(),"settled":self.settled,
        "generation":self.generation,"physical_sessions":self.sessions,
        "dispatched_ms":self.dispatched.and_then(|at|self.started_at.and_then(|start|at.checked_duration_since(start))).map(|d|d.as_millis()),
        "held":self.held.as_ref().map(|f|serde_json::json!({"sequence":f.sequence,"tick":f.tick})),
        "staged":self.staged.as_ref().map(|w|serde_json::json!({"battle":w.id,"tick":w.tick,"scene":w.scene_version()})),
        "pending":self.runtime.as_ref().map(|r|r.pending()),"prepared_ids":self.runtime.as_ref().map(|r|r.prepared_ids()),
        "scene":self.runtime.as_ref().map(|r|serde_json::json!({"version":r.scene().version(),"sha256":r.scene().sha256})),
        "manifest_sha256":self.spec.as_ref().map(|s|&s.manifest_sha256)})}
    fn reconcile_departures(staged:&mut World,current:&World)->io::Result<()> {
        if staged.id!=current.id||staged.map!=current.map||staged.expected_actors()!=current.expected_actors()||staged.extended_lab()!=current.extended_lab()||staged.team_plan()!=current.team_plan()
            ||staged.actors.len()!=current.actors.len()||staged.actors.iter().zip(&current.actors).any(|(old,now)|
                old.identity!=now.identity||old.vehicle_kind()!=now.vehicle_kind()
                ||old.session!=now.session&&!(old.session.is_some()&&now.session.is_none())){return Err(model::bad());}
        for (old,now)in staged.actors.iter_mut().zip(&current.actors){
            if old.session.is_some()&&now.session.is_none(){old.session=None;old.ready=false;old.input=model::Input::STOP;old.aim.park();}
        }Ok(())
    }
    fn actor_manifest(resources:&SharedResources,slot:usize,kind:VehicleKind,version:u8)->io::Result<serde_json::Value> {
        Self::actor_manifest_for_lane(resources,slot,kind,version,slot)
    }
    fn actor_manifest_for_lane(resources:&SharedResources,slot:usize,kind:VehicleKind,version:u8,lane:usize)->io::Result<serde_json::Value> {
        Self::actor_manifest_for_roster(resources,slot,kind,version,lane,wire::MAX_NATIVE_ACTORS)
    }
    fn slot_bound(roster:usize)->usize {roster.clamp(wire::MAX_NATIVE_ACTORS,model::MAX_ACTORS)}
    /// ARENA-01: slots/lanes stay below the native six unless the World was
    /// explicitly built with a larger roster (up to model::MAX_ACTORS).
    fn actor_manifest_for_roster(resources:&SharedResources,slot:usize,kind:VehicleKind,version:u8,lane:usize,roster:usize)->io::Result<serde_json::Value> {
        if lane>=Self::slot_bound(roster) {return Err(model::bad());}
        let map=resources.maps.get(resources.slot(kind).ok_or_else(||model::bad())?).ok_or_else(||model::bad())?;
        Self::actor_manifest_placed(resources,slot,kind,version,roster,Self::lane_origin(map.spawn,lane),map.spawn_yaw)
    }
    /// One actor row at an explicit server-chosen pose (LAB lane or SPAWN-15 spot).
    fn actor_manifest_placed(resources:&SharedResources,slot:usize,kind:VehicleKind,version:u8,roster:usize,origin:[f32;3],yaw:f32)->io::Result<serde_json::Value> {
        let bound=Self::slot_bound(roster);
        if slot>=bound || !matches!(version,1|2|3) || version==1&&kind.index()>=2
            ||kind.is_extended()&&version!=3||version==3&&(resources.version!=4||resources.maps.len()!=7)
            ||kind.is_generated()&&(version!=2||resources.version!=5) {return Err(model::bad());}
        let row_slot=resources.slot(kind).ok_or_else(||model::bad())?;
        let map=resources.maps.get(row_slot).ok_or_else(||model::bad())?;
        let mut row=serde_json::json!({"slot":slot,"kind":kind.label(),
            "config":{"path":Self::physical_path(&map.config),"sha256":map.config_sha256},
            "spawn_origin":origin,"spawn_yaw":yaw});
        if version>=2 {
            row["source_profile"]=if kind.index()>=2 {
                let (path,sha256)=resources.source_profiles[row_slot].as_ref().ok_or_else(||model::bad())?;
                if version==3&&sha256!=ram_proof::Profile::for_vehicle(kind).sha(){return Err(model::bad());}
                serde_json::json!({"path":Self::physical_path(path),"sha256":sha256})
            } else {
                if resources.source_profiles[row_slot].is_some() {return Err(model::bad());}serde_json::Value::Null
            };
        }
        Ok(row)
    }
    /// LAB lanes, not historical team spawns: lanes 0..5 keep the accepted pairs
    /// (+-4 m, 12 m apart); ARENA-01 lanes 6..29 repeat that block every 36 m further
    /// back along the spawn axis (same pairs, same 12 m rows).
    fn lane_origin(spawn:[f32;3],lane:usize)->[f32;3] {
        [spawn[0]+if lane%2==0{-4.}else{4.},spawn[1],spawn[2]-12.*((lane%6)/2)as f32-36.*(lane/6)as f32]
    }
    pub(super) fn start(&mut self,world:&mut World,now:Instant)->io::Result<()> {
        if self.started_at.is_some()||!world.mixed_profiles()||world.actors.len()!=world.expected_actors()
            ||world.started.is_none()||world.map!=self.catalog.map_id(){return Err(model::bad());}
        if world.extended_lab()&&self.resources.version!=4||!world.extended_lab()&&world.actors.iter().any(|a|a.vehicle_kind().is_extended()) {
            return Err(model::bad());
        }
        let version=if world.extended_lab(){3}else if world.actors.iter().any(|actor|actor.vehicle_kind().index()>=2){2}else{1};
        // TURRET-01: this battle has a scene worker, so detached turrets are Jolt bodies.
        world.enable_turret_jolt()?;
        // SPAWN-15: each team on its own base formation; otherwise LAB lanes.
        let spots=if world.team_base_spawn() {
            let teams=(0..world.actors.len()).map(|slot|world.team(slot)).collect::<io::Result<Vec<_>>>()?;
            Some(super::super::team_spawn::placement(world.map,&teams)?)
        } else {None};
        let rows=world.actors.iter().enumerate().map(|(slot,actor)|{
            if let Some(spot)=spots.as_ref().and_then(|s|s.get(slot)) {
                return Self::actor_manifest_placed(&self.resources,slot,actor.vehicle_kind(),version,world.expected_actors(),spot.position,spot.yaw);
            }
            let lane=if world.team_plan().is_some(){world.spawn_lane(slot)?}else{slot};
            Self::actor_manifest_for_roster(&self.resources,slot,actor.vehicle_kind(),version,lane,world.expected_actors())
        })
            .collect::<io::Result<Vec<_>>>()?;
        let manifest=serde_json::json!({"version":version,"profile":"test_lab","policy":scene_worker::POLICY,
            "map":world.map.asset(),"catalog":{"path":Self::physical_path(self.catalog.path()),"sha256":self.catalog.sha256()},"actors":rows});
        let raw=serde_json::to_vec(&manifest).map_err(|_|model::bad())?;
        if raw.len()>scene_worker::MAX_INPUT{return Err(model::bad());}
        let directory=self.resources.root.join("test-runs/p05c-scenes");
        let path=directory.join(format!("battle-{}-{}-{}.json",std::process::id(),world.id,self.generation));
        
        let positions=rows.iter().map(|r|std::array::from_fn(|i|r["spawn_origin"][i].as_f64().unwrap()as f32)).collect::<Vec<_>>();
        match &spots {
            Some(spots)=>world.rebase_external_spawn_poses(&spots.iter().map(|s|(s.position,s.yaw)).collect::<Vec<_>>())?,
            None=>world.rebase_external_spawn_rows(&positions)?,
        }
        self.sessions=world.actors.iter().map(|a|a.session.ok_or_else(||model::bad())).collect::<io::Result<_>>()?;
        let resources=self.resources.clone();let generation=self.generation;
        let sha=format!("{:x}",sha2::Sha256::digest(&raw));let sha_log=sha.clone();
        let(tx,rx)=mpsc::sync_channel(1);
        std::thread::Builder::new().name("p05c-scene-start".into()).spawn(move||{
            let result=(||{fs::create_dir_all(&directory)?;use std::io::Write;let mut file=fs::OpenOptions::new().create_new(true).write(true).open(&path)?;file.write_all(&raw)?;file.sync_all()?;let spec=Arc::new(SceneSpec::load(&resources.root,&path,&sha)?);
                // The dispatcher clock owns this epoch. The background job
                // must not introduce a newer clock than the current loop turn.
                let scene=Scene::new(&spec,&[])?;let runtime=Runtime::launch(resources.artifacts.clone(),spec.clone(),generation,scene,now)?;
                Ok((spec,runtime))})();let _=tx.send(result);
        })?;
        self.startup=Some(rx);self.started_at=Some(now);
        println!("P05C_SCENE_START battle={} actors={} generation={} one_scene=true",world.id,world.actors.len(),generation);
        if spots.is_some() {println!("SPAWN15_PLACEMENT battle={} map={} policy={} actors={} manifest_sha256={sha_log}",
            world.id,world.map.asset(),super::super::team_spawn::POLICY,world.actors.len());}
        Ok(())
    }
    fn profile(kind:scene_worker::Kind,extended:bool)->io::Result<ram_proof::Profile>{
        let vehicle=if extended{kind.extended_vehicle()}else{VehicleKind::from_owned_label(kind.label()).ok_or_else(||model::bad())?};
        Ok(ram_proof::Profile::for_vehicle(vehicle))
    }
    fn physical_path(path:&Path)->String{let text=path.to_string_lossy();
        text.strip_prefix(r"\\?\").filter(|s|s.as_bytes().get(1)==Some(&b':')).unwrap_or(&text).to_owned()}
    fn checked_contacts(&self,world:&World,frame:&scene_worker::Frame)->io::Result<Vec<model::VehicleContactInput>> {
        let spec=self.spec.as_ref().ok_or_else(||model::bad())?;let scene=self.runtime.as_ref().ok_or_else(||model::bad())?.scene();
        let domain=world.fragiles.as_ref().ok_or_else(||model::bad())?;
        let mut contacts=Vec::new();
        for actor in &frame.actors {
            let rows=actor.proof["object_contacts"].as_array().ok_or_else(||model::bad())?;
            let vec3=|v:&serde_json::Value|->io::Result<[f32;3]>{let a=v.as_array().filter(|a|a.len()==3).ok_or_else(||model::bad())?;
                let mut out=[0.;3];for(i,n)in a.iter().enumerate(){out[i]=n.as_f64().filter(|x|x.is_finite()).ok_or_else(||model::bad())? as f32;}Ok(out)};
            let raw=rows.iter().map(|c|Ok(crate::map_drive_worker091::ObjectContact{
                object_id:c["object_id"].as_u64().ok_or_else(||model::bad())?.try_into().map_err(|_|model::bad())?,
                substep:c["substep"].as_u64().ok_or_else(||model::bad())?.try_into().map_err(|_|model::bad())?,
                kind:c["kind"].as_str().ok_or_else(||model::bad())?.into(),point:vec3(&c["point"])?,
                normal:vec3(&c["normal"])?,velocity:vec3(&c["velocity"])?})).collect::<io::Result<Vec<_>>>()?;
            let proof=crate::map_drive_worker091::shared_angular_proof(&actor.proof,&raw,&self.catalog,Self::profile(actor.kind,world.extended_lab())?,frame.sequence)?;
            proof.final_motion(actor.pose.linear_velocity,actor.pose.angular_velocity,actor.pose.rspeed)?;
            if frame.sequence==0{continue;}
            let context=ram_proof::Context{battle:world.id,slot:actor.slot,session:self.sessions[actor.slot],generation:self.generation,
                seq:frame.sequence,tick:frame.tick,config_sha256:spec.actors[actor.slot].config_sha256.clone(),catalog_sha256:spec.catalog_sha256().into(),
                domain_sha256:domain.catalog.sha256.clone(),scene_version:scene.version(),scene_sha256:scene.sha256.clone()};context.validate()?;
            let frame=Arc::new(ram_proof::ContextFrame{context,proof});
            for(index,receipt)in frame.proof.receipts.iter().enumerate(){let c=raw.iter().find(|c|c.object_id==receipt.object_id).ok_or_else(||model::bad())?;
                contacts.push(model::VehicleContactInput{object_id:c.object_id,substep:c.substep,point:c.point,normal:c.normal,velocity:c.velocity,
                    mass_kg:frame.proof.profile.mass(),kind:c.kind.clone(),shooter:actor.slot,proof:Some(ram_proof::ContactProof{frame:frame.clone(),index})});}
        }Ok(contacts)
    }
    pub(super) fn step(&mut self,world:&mut World,now:Instant)->io::Result<()> {
        if world.lifecycle.as_ref().is_some_and(|s|s.outcome().is_some()){return Ok(());}
        if let Some(rx)=&self.startup {
            match rx.try_recv(){Ok(result)=>{let(spec,runtime)=result?;self.spec=Some(spec);self.runtime=Some(runtime);self.startup=None;},
                Err(mpsc::TryRecvError::Empty)=>{if now.saturating_duration_since(self.started_at.ok_or_else(||model::bad())?)>Duration::from_secs(120){return Err(io::Error::new(io::ErrorKind::TimedOut,"P05C scene startup"));}return Ok(());},
                Err(mpsc::TryRecvError::Disconnected)=>return Err(model::bad())}
        }
        let Some(runtime)=&mut self.runtime else{return Err(model::bad());};
        let frame=if self.held.is_some(){self.held.take()}else{runtime.poll(now)?};
        self.install_turret(world)?;
        if self.staged.is_some(){
            if frame.is_some(){return Err(model::bad());}
            if self.runtime.as_mut().ok_or_else(||model::bad())?.take_scene_ack(){let mut staged=self.staged.take().ok_or_else(||model::bad())?;
                Self::reconcile_departures(&mut staged,world)?;
                *world=staged;self.dispatched=Some(drive_grid(world.started.ok_or_else(||model::bad())?,now)?);
                println!("P05C_SCENE_COMMIT battle={} version={} one_worker_ack=true",world.id,world.scene_version());}
            return Ok(());
        }
        if let Some(frame)=frame{
            let contacts=self.checked_contacts(world,&frame)?;
            let rows=frame.actors.iter().map(|a|(a.slot,a.pose.position,a.pose.direction,a.pose.speed)).collect::<Vec<_>>();
            let clone_span=super::super::step_profile::span(super::super::step_profile::Part::SceneClone);
            let mut candidate=world.clone();
            drop(clone_span);
            if frame.sequence==0 {
                candidate.import_external_poses(&rows)?;
                let spec=self.spec.as_ref().ok_or_else(||model::bad())?;
                for actor in &frame.actors{candidate.bind_contact_source(actor.slot,ram_proof::Source{session:self.sessions[actor.slot],generation:self.generation,
                    config_sha256:spec.actors[actor.slot].config_sha256.clone(),profile:Self::profile(actor.kind,world.extended_lab())?})?;}
                self.settled=true;println!("P05C_SCENE_READY battle={} process_id={} actors={} tick={}",world.id,self.runtime.as_ref().unwrap().process_id(),rows.len(),frame.tick);
            }else{
                // A quick reply may arrive in the current wall-clock bucket.
                // Retain the whole validated batch until the domain tick can
                // advance; never dispatch another batch or lose its contacts.
                if !candidate.advance_with_external(now,Some(&rows))?{self.held=Some(frame);return Ok(());}
                let tank_contacts=frame.tank_contacts.iter().map(|c|model::TankContactInput{slot_a:c.slot_a,slot_b:c.slot_b,substep:c.substep,point:c.point,normal:c.normal,relative_velocity:c.relative_velocity}).collect::<Vec<_>>();
                candidate.apply_tank_contacts(&tank_contacts,frame.sequence,frame.tick)?;
                candidate.apply_vehicle_contacts(&contacts)?;
                // MAPS-02: the domain decides each falling atom overlap with the
                // hash-bound profile mass; the worker only reports the overlap.
                let spec=self.spec.as_ref().ok_or_else(||model::bad())?;
                let columns=frame.column_contacts.iter().map(|c|Ok(model::ColumnContactInput{object_id:c.object_id,shooter:c.slot,substep:c.substep,
                    point:c.point,normal:c.normal,velocity:c.velocity,
                    mass_kg:Self::profile(spec.actors.get(c.slot).ok_or_else(||model::bad())?.kind,world.extended_lab())?.mass()})).collect::<io::Result<Vec<_>>>()?;
                for event in candidate.apply_column_contacts(&columns)? {
                    println!("SHARED_COLUMN_FALL battle={} slot={} object={} fallen_column={:#06x} tick={} speed_mps={:.3} policy={}",
                        world.id,event.shooter,event.object_id,event.fallen_column.unwrap_or_default(),event.tick,
                        event.velocity.iter().map(|v|v*v).sum::<f32>().sqrt(),super::super::fragiles::FALLING_ATOM_POLICY);
                }
            }
            if candidate.scene_version()!=world.scene_version()||frame.prepared {
                let spec=self.spec.as_ref().ok_or_else(||model::bad())?;let ids=candidate.fragiles.as_ref().ok_or_else(||model::bad())?.removed_ids();
                if frame.prepared_ids.iter().any(|id|ids.binary_search(id).is_err())||frame.prepared&&candidate.scene_version()==world.scene_version(){return Err(model::bad());}
                let scene=Scene::new(spec,&ids)?;self.runtime.as_mut().unwrap().sync_removed(scene,now)?;self.staged=Some(candidate);return Ok(());
            }
            *world=candidate;
        }
        if !self.settled||world.tick==1000&&world.actors.iter().any(|a|a.session.is_some()&&!a.ready){return Ok(());}
        if self.launch_turret(world,now)?{return Ok(());}
        let runtime=self.runtime.as_mut().ok_or_else(||model::bad())?;
        if runtime.pending(){return Ok(());}
        let started=world.started.ok_or_else(||model::bad())?;
        // Capture the dispatcher-side wall lag before the bounded resync in
        // drive_deadline. This is a receipt only.
        let target=match self.dispatched{Some(previous)=>previous.checked_add(crate::map_drive_worker091::STEP).ok_or_else(||model::bad())?,None=>drive_grid(started,now)?};
        if now>=target{runtime.record_scheduler_lag(now,target);}
        let deadline=drive_deadline(started,self.dispatched,now,&mut self.lag_resync)?;
        if let Some(deadline)=deadline{
            let allows_actions=world.lifecycle.as_ref().is_none_or(|s|s.allows_actions());
            let inputs=world.actors.iter().map(|a|actor_input(a,world.tick,allows_actions)).collect::<io::Result<Vec<_>>>()?;
            let seq=runtime.advance(&inputs,now)?;self.dispatched=Some(deadline);
            println!("P05C_SCENE_INPUT battle={} seq={} actors={} physical_sessions={:?} inputs={:?} world_tick={} devices_policy={}",
                world.id,seq,inputs.len(),self.sessions,inputs,world.tick,
                if world.extended_lab(){crate::p06t_device_state::POLICY_V2}else if world.actors.iter().any(|a|a.devices.is_some()){crate::p06t_device_state::POLICY}else{"legacy"});
        }Ok(())
    }
}
#[cfg(test)]
#[path="server_scene_runtime_tests.rs"]
mod tests;
#[cfg(test)]
#[path="server_scene_runtime_p04m_tests.rs"]
mod p04m_tests;
#[cfg(test)]
#[path="server_scene_runtime_p06t_tests.rs"]
mod p06t_tests;
#[cfg(test)]
#[path="p06t_extended_scene_tests.rs"]
mod extended_tests;

#[cfg(test)]
#[path="p10b_team_scene_tests.rs"]
mod p10b_team_scene_tests;
