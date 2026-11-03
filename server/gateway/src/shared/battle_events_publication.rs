//! UI-02 publication: what this recipient learns about the shells that reached
//! its own vehicle. It reads the committed journals at the same cursors as the
//! native callbacks, so a reconnect replays nothing, and it moves no cursor.
//! Policy: docs/plans/UI02_HIT_INDICATOR.md.
//!
//! UI-03 feed records of a channel that asked for them read the same journals
//! at the channel's own cursors. Policy: docs/plans/UI03_BATTLE_FEEDS.md.
use super::*;
use crate::p06t_device_state::{Change,Condition};
use super::super::battle_events::{self,Channel,Critical,Event,FeedCursors,FeedEvent,FeedKind,HitReceived,HitShell,ShellFamily,Source,Verdict};
use crate::p06t_shells091::Family;

fn heading(world:&World,shot:u32)->Option<f32> {
    let velocity=world.projectiles.iter().find(|projectile|projectile.sequence==shot)?.velocity;
    (velocity.iter().all(|v|v.is_finite())&&(velocity[0]!=0.0||velocity[2]!=0.0)).then(||velocity[0].atan2(velocity[2]))
}
/// Damage to the recipient's own modules, crew or fire from this shot.
fn criticals(c:&Client,world:&World,shot:u32)->Vec<Critical> {
    let mut rows=Vec::new();
    for(target,event)in world.device_events.iter().skip(c.device_cursor){
        if *target!=c.slot||event.cause.shot!=shot||event.from_fire{continue;}
        let critical=match event.change{
            Change::Device{extra_index,before_condition,after_condition,repair:false,..} if before_condition!=after_condition=>match after_condition{
                Condition::Critical=>Some(Critical::Device{extra:extra_index,destroyed:false}),
                Condition::Destroyed=>Some(Critical::Device{extra:extra_index,destroyed:true}),
                Condition::Normal=>None},
            Change::Crew{extra_index,before_active:true,after_active:false,..}=>Some(Critical::Crew{extra:extra_index}),
            Change::Fire{before_active:false,after_active:true}=>Some(Critical::Fire),
            _=>None,
        };
        if let Some(critical)=critical{if rows.len()<battle_events::MAX_CRITICALS{rows.push(critical);}}
    }
    rows
}
fn verdict(event:&model::AppliedImpact)->Verdict {
    match impact_visual(event).ok().flatten().map(|(_,outcome,_)|outcome){
        Some(impact_wire::ShotOutcome::Pierced)=>Verdict::Pierced,
        Some(impact_wire::ShotOutcome::NotPierced)=>Verdict::NotPierced,
        Some(impact_wire::ShotOutcome::Ricochet)=>Verdict::Ricochet,
        None=>Verdict::Unknown,
    }
}
/// UI-03b: the shell of a hit from a shooter this recipient sees; the same rule
/// as the nominal of "Удар сдержан". Laboratory shots have no catalog shell.
fn shell(world:&World,shot:u32,source:Source)->Option<Event> {
    if source==Source::Hidden {return None;}
    let shell=world.projectiles.iter().find(|projectile|projectile.sequence==shot)?.shell?;
    let family=match shell.family {Family::ArmorPiercing=>ShellFamily::ArmorPiercing,Family::ArmorPiercingCr=>ShellFamily::ArmorPiercingCr,
        Family::HollowCharge=>ShellFamily::HollowCharge,Family::HighExplosive=>ShellFamily::HighExplosive};
    Some(Event::Shell(HitShell{shot,family,premium:shell.premium_gold_flag}))
}
fn source(c:&Client,attacker:usize)->Source {if c.visible()[attacker]{Source::Visible(attacker)}else{Source::Hidden}}
fn friendly(world:&World,own:usize,attacker:usize)->io::Result<bool> {Ok(world.team(own)?==world.team(attacker)?)}
fn hit_events(c:&Client,world:&World)->io::Result<Vec<(u32,Event)>> {
    let mut rows=Vec::new();
    for event in world.impacts.iter().skip(c.impact_cursor){
        if event.target!=c.slot||event.health_before<=0{continue;}
        let Some(yaw)=heading(world,event.shot) else {continue;};
        let damage=u16::try_from((event.health_before-event.health_after).max(0)).map_err(|_|model::bad())?;
        let verdict=verdict(event);
        let source=source(c,event.attacker);
        // "Удар сдержан": the nominal damage of the shell, a catalog fact of a
        // shooter the recipient sees. A hidden shooter's shell would tell its
        // gun, and the old MS-1 laboratory shots have no catalog shell: absent.
        let blocked=(damage==0&&matches!(verdict,Verdict::NotPierced|Verdict::Ricochet)&&source!=Source::Hidden)
            .then(||battle_ledger::nominal(world,event.shot)).flatten();
        rows.push((event.tick,Event::HitReceived(HitReceived{shot:event.shot,yaw,damage,blocked,verdict,
            friendly:friendly(world,c.slot,event.attacker)?,fatal:event.health_after<=0,source,criticals:criticals(c,world,event.shot)})));
        if let Some(row)=shell(world,event.shot,source) {rows.push((event.tick,row));}
    }
    // An HE terminal that hurt this vehicle without being its direct impact.
    for event in world.damage_events.iter().skip(c.damage_cursor){
        if event.direct||event.reason!=0||event.target!=c.slot||event.health_after>=event.health_before||event.health_before<=0
            ||world.impacts.iter().any(|impact|impact.shot==event.shot&&impact.target==c.slot){continue;}
        let Some(yaw)=heading(world,event.shot) else {continue;};
        let damage=u16::try_from(event.health_before-event.health_after).map_err(|_|model::bad())?;
        let source=source(c,event.attacker);
        rows.push((event.tick,Event::HitReceived(HitReceived{shot:event.shot,yaw,damage,blocked:None,verdict:Verdict::Splash,
            friendly:friendly(world,c.slot,event.attacker)?,fatal:event.health_after<=0,source,criticals:criticals(c,world,event.shot)})));
        if let Some(row)=shell(world,event.shot,source) {rows.push((event.tick,row));}
    }
    Ok(rows)
}
fn hp_lost(before:i16,after:i16)->io::Result<u16> {u16::try_from((i32::from(before)-i32::from(after)).max(0)).map_err(|_|model::bad())}
fn device_tick(at_ms:u64)->io::Result<u32> {u32::try_from(at_ms/100).ok().and_then(|tick|tick.checked_add(1000)).ok_or_else(||model::bad())}
/// Rows of one pass for one recipient. Every rule of disclosure lives here.
struct Feed<'a> {c:&'a Client,world:&'a World,rows:Vec<(u32,Event)>}
impl Feed<'_> {
    fn push(&mut self,tick:u32,kind:FeedKind,value:Option<u16>,vehicle:Option<usize>) {
        self.rows.push((tick,Event::Feed(FeedEvent{kind,value,vehicle})));
    }
    fn enemy(&self,slot:usize)->io::Result<bool> {Ok(slot!=self.c.slot&&!friendly(self.world,self.c.slot,slot)?)}
    /// Dealt damage: a hidden target has no name and no amount, the amount
    /// would be a fact about its HP. The event itself stays: the shot-result
    /// voice already tells the shooter that the shell hurt something.
    fn dealt(&mut self,tick:u32,kind:FeedKind,target:usize,damage:u16)->io::Result<()> {
        if damage==0||!self.enemy(target)? {return Ok(());}
        if self.c.visible()[target] {self.push(tick,kind,Some(damage),Some(target));} else {self.push(tick,kind,None,None);}
        Ok(())
    }
    /// Damage the recipient took outside a shell: its own HP, the source by the
    /// rule of UI-02.
    fn received(&mut self,tick:u32,kind:FeedKind,attacker:usize,damage:u16) {
        if damage==0 {return;}
        let vehicle=(attacker!=self.c.slot&&self.c.visible()[attacker]).then_some(attacker);
        self.push(tick,kind,Some(damage),vehicle);
    }
    /// The killer and the victim are public arena metadata (vehicle_killed).
    fn kill(&mut self,tick:u32,target:usize)->io::Result<()> {
        if self.enemy(target)? {self.push(tick,FeedKind::Kill,None,Some(target));}
        Ok(())
    }
    fn shells(&mut self,cursors:&FeedCursors)->io::Result<()> {
        let(c,world)=(self.c,self.world);
        if world.mixed_ammo() {
            for event in world.damage_events.iter().skip(cursors.damage) {
                let damage=hp_lost(event.health_before,event.health_after)?;
                if event.reason==1&&event.target==c.slot {self.received(event.tick,FeedKind::FireReceived,event.attacker,damage);}
                if event.attacker!=c.slot {continue;}
                // Owner round 9: a fire's damage is no row per tick; devices() gives one
                // Ignition row with the burned sum when that fire ends.
                if event.reason==0 {self.dealt(event.tick,FeedKind::ShotDamage,event.target,damage)?;}
                if event.lethal() {self.kill(event.tick,event.target)?;}
            }
        } else {
            for event in world.impacts.iter().skip(cursors.impacts) {
                if event.attacker!=c.slot||event.health_before<=0 {continue;}
                self.dealt(event.tick,FeedKind::ShotDamage,event.target,hp_lost(event.health_before,event.health_after)?)?;
                if event.health_after<=0 {self.kill(event.tick,event.target)?;}
            }
        }
        Ok(())
    }
    fn rams(&mut self,cursors:&FeedCursors)->io::Result<()> {
        let(c,world)=(self.c,self.world);
        for event in world.ram_damage_events.iter().skip(cursors.ram) {
            let damage=hp_lost(event.health_before,event.health_after)?;
            if event.target==c.slot {self.received(event.domain_tick,FeedKind::RamReceived,event.attacker,damage);}
            if event.attacker==c.slot {
                self.dealt(event.domain_tick,FeedKind::RamDamage,event.target,damage)?;
                if event.health_before>0&&event.health_after==0 {self.kill(event.domain_tick,event.target)?;}
            }
        }
        Ok(())
    }
    /// An ally's damage this recipient helped with: a hidden target gives the
    /// event only, the sum stays in the end-of-battle totals.
    fn assists(&mut self,cursors:&FeedCursors)->io::Result<()> {
        let(c,world)=(self.c,self.world);
        for harm in battle_ledger::harms(world,cursors.damage,cursors.impacts)? {
            let kind=match battle_ledger::assist(world,c.slot,harm)? {
                Some(battle_ledger::Assist::Track)=>FeedKind::AssistTrack,
                Some(battle_ledger::Assist::Spot)=>FeedKind::AssistSpot,
                None=>continue,
            };
            self.dealt(harm.tick,kind,harm.target,harm.amount)?;
        }
        Ok(())
    }
    /// Modules of another vehicle are facts about it: a hidden one gives none.
    /// Shell-caused own modules travel inside HitReceived, fire-caused do here.
    fn devices(&mut self,cursors:&FeedCursors)->io::Result<()> {
        let(c,world)=(self.c,self.world);
        for(target,event)in world.device_events.iter().skip(cursors.devices){
            let tick=device_tick(event.at_ms)?;
            if *target==c.slot {
                if event.from_fire&&matches!(event.change,Change::Device{before_condition,after_condition,repair:false,..}
                    if before_condition!=after_condition&&after_condition!=Condition::Normal) {
                    self.push(tick,FeedKind::FireCritical,None,None);
                }
                continue;
            }
            if usize::from(event.cause.attacker_slot)!=c.slot||!self.enemy(*target)?||!c.visible()[*target] {continue;}
            if let Change::Fire{before_active:true,after_active:false}=event.change {
                // A fire of a hidden vehicle is a module fact: no event (checked above).
                let burned=burned(world,*target,event.cause.shot,event.cause.attacker_slot);
                if burned>0 {self.push(tick,FeedKind::Ignition,Some(burned),Some(*target));}
                continue;
            }
            if event.from_fire {continue;}
            let kind=match event.change {
                Change::Device{device,before_condition,after_condition,repair:false,..} if before_condition!=after_condition=>match(device,after_condition){
                    (_,Condition::Normal)=>None,
                    (crate::p06t_device_caps::Device::LeftTrack|crate::p06t_device_caps::Device::RightTrack,Condition::Destroyed)=>Some(FeedKind::TrackDown),
                    _=>Some(FeedKind::Critical)},
                Change::Crew{before_active:true,after_active:false,..}=>Some(FeedKind::Critical),
                _=>None,
            };
            if let Some(kind)=kind {self.push(tick,kind,None,Some(*target));}
        }
        Ok(())
    }
    /// The first-spot credit of P08C and the capture ledger: laboratory rules,
    /// counted as they stand. The amount of a capture is the recipient's own.
    fn ledgers(&mut self,cursors:&FeedCursors) {
        let(c,world)=(self.c,self.world);
        for record in world.result_spots().unwrap_or(&[]).iter().skip(cursors.spots) {
            // Owner round 8: the spotted vehicle is named, by the rule of dealt damage:
            // only while the recipient sees it.
            if record.observer()==c.slot {
                let named=c.visible().get(record.target()).copied().unwrap_or(false);
                self.push(record.tick(),FeedKind::Spotted,None,named.then_some(record.target()));
            }
        }
        if let Some(state)=&world.lifecycle {
            let(capture,defence)=(state.capture_points(c.slot),state.dropped_capture_points(c.slot));
            if capture>cursors.capture {self.push(world.tick,FeedKind::CapturePoints,Some(capture-cursors.capture),None);}
            if defence>cursors.defence {self.push(world.tick,FeedKind::DefencePoints,Some(defence-cursors.defence),None);}
        }
    }
}
/// HP one fire took from `target`: its VehicleDamage ticks share the cause of the
/// shot that lit it. Saturates at the wire's u16.
fn burned(world:&World,target:usize,shot:u32,attacker:u8)->u16 {
    let sum:u32=world.device_events.iter().filter(|(t,e)|*t==target&&e.from_fire&&e.cause.shot==shot&&e.cause.attacker_slot==attacker)
        .map(|(_,e)|match e.change {Change::VehicleDamage{amount}=>u32::from(amount),_=>0}).sum();
    u16::try_from(sum).unwrap_or(u16::MAX)
}
fn current_cursors(c:&Client,world:&World)->FeedCursors {
    FeedCursors{impacts:world.impacts.len(),damage:world.damage_events.len(),ram:world.ram_damage_events.len(),
        devices:world.device_events.len(),spots:world.result_spots().map_or(0,<[_]>::len),
        capture:world.lifecycle.as_ref().map_or(0,|state|state.capture_points(c.slot)),
        defence:world.lifecycle.as_ref().map_or(0,|state|state.dropped_capture_points(c.slot))}
}
fn feed_events(channel:&mut Channel,c:&Client,world:&World,rows:&mut Vec<(u32,Event)>)->io::Result<()> {
    let Some(cursors)=channel.cursors.replace(current_cursors(c,world)) else {return Ok(());};
    let mut feed=Feed{c,world,rows:std::mem::take(rows)};
    feed.shells(&cursors)?;feed.rams(&cursors)?;feed.devices(&cursors)?;feed.assists(&cursors)?;feed.ledgers(&cursors);
    *rows=feed.rows;Ok(())
}
/// Runs before the native callbacks of this pass: a prepared client knows the
/// facts of a shell when its native hit indicator arrives.
pub(super) fn publish(c:&mut Client,outbox:&mut VecDeque<Vec<u8>>,world:&World,now:Instant,log:&mut Vec<String>)->io::Result<()> {
    let Some(mut channel)=c.battle_events.take() else {return Ok(());};
    let result=publish_on(&mut channel,c,outbox,world,now,log);
    c.battle_events=Some(channel);result
}
fn publish_on(channel:&mut Channel,c:&Client,outbox:&mut VecDeque<Vec<u8>>,world:&World,now:Instant,log:&mut Vec<String>)->io::Result<()> {
    if let Some(sequence)=channel.take_hello(){outbox.push_back(battle_events::hello_frame(sequence)?);}
    if !c.visible()[c.slot]{return Ok(());}
    let mut rows=hit_events(c,world)?;
    if channel.feed() {feed_events(channel,c,world,&mut rows)?;}
    // Stable: one tick keeps the journal order, so a kill follows its damage.
    rows.sort_by_key(|row|row.0);
    let events=rows.into_iter().map(|row|row.1).collect::<Vec<_>>();
    for batch in events.chunks(battle_events::MAX_EVENTS_PER_FRAME){
        match channel.admit(now,outbox.len(),batch.len()){
            Some(sequence)=>{
                let body=battle_events::frame(sequence,batch)?;
                log.push(format!("BATTLE_EVENTS_FRAME battle={} slot={} sequence={sequence} events={} bytes={} recipient_only=true",world.id,c.slot,batch.len(),body.len()));
                outbox.push_back(body);
            },
            None=>log.push(format!("BATTLE_EVENTS_DROPPED battle={} slot={} events={} total_dropped={}",world.id,c.slot,batch.len(),channel.dropped)),
        }
    }
    // UI-04: a frame the limits refused is due again at the next pass.
    if channel.totals_due()&&world.lifecycle.as_ref().is_some_and(|state|state.outcome().is_some()) {
        if let Some(sequence)=channel.admit(now,outbox.len(),1) {
            let sum=battle_ledger::totals(world,c.slot)?;
            let dealt=battle_ledger::dealt(world,c.slot)?;
            outbox.push_back(battle_events::frame(sequence,&[Event::Totals(battle_events::BattleTotals{dealt,blocked:sum.blocked,
                assist_spot:sum.assist_spot,assist_track:sum.assist_track,burned:sum.burned})])?);
            channel.totals_sent();
            log.push(format!("BATTLE_HISTORY_TOTALS battle={} slot={} sequence={sequence} recipient_only=true",world.id,c.slot));
        }
    }
    Ok(())
}
