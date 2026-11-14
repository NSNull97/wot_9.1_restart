//! Explicit closed test-lab roster and requested physical spawn points.
//! Poses are proposed scene inputs, not historical spawns or proof of settling.
use std::io;
use super::{team_spawn::Spot,vehicle_profile::VehicleKind};
use serde_json::Value;

#[derive(Clone,Debug,PartialEq)]
pub(crate) struct Seat {pub kind:Option<VehicleKind>,pub position:[f32;3],pub yaw:f32,pub net:bool,pub crew_percent:Option<u8>}
impl crate::bw_wire::Wire for Seat {
    fn put(&self,w:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire;self.kind.put(w);self.position.put(w);self.yaw.put(w);self.net.put(w);self.crew_percent.put(w);}
    fn get(r:&mut crate::bw_wire::Dec)->io::Result<Self>{use crate::bw_wire::Wire;Ok(Self{kind:Wire::get(r)?,position:Wire::get(r)?,yaw:Wire::get(r)?,net:Wire::get(r)?,crew_percent:Wire::get(r)?})}
}
#[derive(Clone,Debug,PartialEq)]
pub(crate) struct Event {pub tick:u32,pub slot:u8,pub action:u8,pub target:Option<u8>}
impl crate::bw_wire::Wire for Event {
    fn put(&self,w:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire;self.tick.put(w);self.slot.put(w);self.action.put(w);self.target.put(w);}
    fn get(r:&mut crate::bw_wire::Dec)->io::Result<Self>{use crate::bw_wire::Wire;Ok(Self{tick:Wire::get(r)?,slot:Wire::get(r)?,action:Wire::get(r)?,target:Wire::get(r)?})}
}
#[derive(Clone,Debug,PartialEq)]
pub(crate) struct Scenario {pub seats:Vec<Seat>,pub events:Vec<Event>}
impl crate::bw_wire::Wire for Scenario {
    fn put(&self,w:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire;self.seats.put(w);self.events.put(w);}
    fn get(r:&mut crate::bw_wire::Dec)->io::Result<Self>{use crate::bw_wire::Wire;let value=Self{seats:Wire::get(r)?,events:Wire::get(r)?};value.validate()?;Ok(value)}
}
fn bad()->io::Error{io::Error::new(io::ErrorKind::InvalidData,"fixed scout scenario invalid")}
impl Scenario {
    pub(crate) fn parse(v:&Value)->io::Result<Self>{
        let m=v.as_object().filter(|m|m.len()==4&&m.get("version")==Some(&Value::from(1))&&m.get("map").and_then(Value::as_str)==Some("02_malinovka")).ok_or_else(bad)?;
        let rows=m.get("seats").and_then(Value::as_array).ok_or_else(bad)?;
        let mut seats=Vec::new();
        for (index,row) in rows.iter().enumerate(){
            let r=row.as_object().filter(|r|r.len()==5&&r.contains_key("kind")&&r.contains_key("position")&&r.contains_key("yaw")&&r.contains_key("net")&&r.contains_key("crew_percent")).ok_or_else(bad)?;
            let kind=if index==0&&r["kind"]=="human" {None} else {Some(r["kind"].as_str().and_then(VehicleKind::from_owned_label).ok_or_else(bad)?)};
            let coords=r["position"].as_array().filter(|v|v.len()==3).ok_or_else(bad)?;
            let mut p=[0.;3];for(i,x)in coords.iter().enumerate(){p[i]=x.as_f64().filter(|x|x.is_finite()&&x.abs()<=500.).ok_or_else(bad)? as f32;}
            let yaw=r["yaw"].as_f64().filter(|x|x.is_finite()&&x.abs()<=std::f64::consts::PI).ok_or_else(bad)? as f32;
            let net=r["net"].as_bool().ok_or_else(bad)?;
            let crew_percent=if r["crew_percent"].is_null(){None}else{Some(u8::try_from(r["crew_percent"].as_u64().ok_or_else(bad)?).map_err(|_|bad())?)};
            seats.push(Seat{kind,position:p,yaw,net,crew_percent});
        }
        let rows=m.get("events").and_then(Value::as_array).filter(|v|v.len()<=64).ok_or_else(bad)?;
        let mut events=Vec::new();for row in rows {
            let r=row.as_object().filter(|r|matches!(r.len(),3|4)).ok_or_else(bad)?;
            let tick=u32::try_from(r.get("tick").and_then(Value::as_u64).ok_or_else(bad)?).map_err(|_|bad())?;
            let slot=u8::try_from(r.get("slot").and_then(Value::as_u64).ok_or_else(bad)?).map_err(|_|bad())?;
            let action=match r.get("action").and_then(Value::as_str){Some("forward")=>1,Some("left")=>2,Some("right")=>3,Some("stop")=>4,Some("shoot")=>5,Some("aim_target")=>6,Some("shoot_shared")=>7,_=>return Err(bad())};
            let target=if action>=6 {if r.len()!=4{return Err(bad());}Some(u8::try_from(r.get("target_slot").and_then(Value::as_u64).ok_or_else(bad)?).map_err(|_|bad())?)}else{if r.len()!=3{return Err(bad());}None};
            events.push(Event{tick,slot,action,target});
        }
        let value=Self{seats,events};value.validate()?;Ok(value)
    }
    pub(crate) fn validate(&self)->io::Result<()> {
        if !matches!(self.seats.len(),4|6)||self.seats[0].kind.is_some()||self.seats[0].net||self.seats[0].crew_percent.is_some()||self.seats[1..].iter().any(|s|s.kind.is_none()||s.crew_percent!=Some(100)) {return Err(bad());}
        if self.events.len()>64{return Err(bad());}
        let mut moving=[None;6];let mut aimed=[None;6];let mut previous=None;
        for e in &self.events {
            if !(1..=3000).contains(&e.tick)||e.slot==0||usize::from(e.slot)>=self.seats.len()||!(1..=7).contains(&e.action)
                ||previous.is_some_and(|v|v>=(e.tick,e.slot)){return Err(bad());}
            previous=Some((e.tick,e.slot));
            if e.action>=6 {
                let target=e.target.ok_or_else(bad)?;
                if usize::from(target)>=self.seats.len() || target%2==e.slot%2 {return Err(bad());}
                if e.action==6 {aimed[usize::from(e.slot)]=Some((e.tick,target));}
                else if aimed[usize::from(e.slot)].take().is_none_or(|(tick,old)|old!=target||e.tick.saturating_sub(tick)<30) {return Err(bad());}
            } else if e.target.is_some(){return Err(bad());}
            let state=&mut moving[usize::from(e.slot)];
            match e.action {1..=3=>{if state.is_some(){return Err(bad());}*state=Some(e.tick);},4=>{
                let start=state.take().ok_or_else(bad)?;if e.tick-start>50{return Err(bad());}
            },_=>{}}
        }
        if moving.iter().any(Option::is_some){return Err(bad());}
        for (i,a) in self.seats.iter().enumerate(){
            if !a.position.iter().all(|x|x.is_finite()&&x.abs()<=500.)||!a.yaw.is_finite()||a.yaw.abs()>std::f32::consts::PI{return Err(bad());}
            for b in &self.seats[..i]{if (a.position[0]-b.position[0]).hypot(a.position[2]-b.position[2])<10. {return Err(bad());}}
        } Ok(())
    }
    pub(crate) fn spot(&self,slot:usize)->io::Result<Spot>{let s=self.seats.get(slot).ok_or_else(bad)?;Ok(Spot{position:s.position,yaw:s.yaw})}
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn strict_bounded_roster_is_fail_closed(){
        let row=|kind:&str,x:i32|serde_json::json!({"kind":kind,"position":[x,0,0],"yaw":0,"net":false,"crew_percent":if kind=="human"{None}else{Some(100)}});
        let good=serde_json::json!({"version":1,"map":"02_malinovka","seats":[row("human",0),row("ms1",20),row("ms1",40),row("ms1",60)],"events":[]});
        let value=Scenario::parse(&good).unwrap();assert_eq!(value.seats.len(),4);assert!(value.seats[0].kind.is_none());
        let mut invalid=good.clone();invalid["seats"][1]["position"]=serde_json::json!([2,0,0]);assert!(Scenario::parse(&invalid).is_err());
        let mut invalid=good.clone();invalid["map"]="01_karelia".into();assert!(Scenario::parse(&invalid).is_err());
        let mut invalid=good.clone();invalid["seats"][1]["kind"]="human".into();assert!(Scenario::parse(&invalid).is_err());
        let mut invalid=good.clone();invalid["seats"][1]["yaw"]=4.into();assert!(Scenario::parse(&invalid).is_err());
    }
    #[test] fn content0_s5a_shared_aim_parse_and_wire_fail_closed(){
        let row=|kind:&str,x:i32|serde_json::json!({"kind":kind,"position":[x,0,0],"yaw":0,"net":false,"crew_percent":if kind=="human"{None}else{Some(100)}});
        let mut good=serde_json::json!({"version":1,"map":"02_malinovka","seats":[row("human",0),row("ms1",20),row("ms1",40),row("ms1",60),row("t34",80),row("ms1",100)],"events":[{"tick":40,"slot":4,"action":"aim_target","target_slot":1},{"tick":100,"slot":4,"action":"shoot_shared","target_slot":1}]});
        let scenario=Scenario::parse(&good).unwrap();
        let now=std::time::Instant::now();let mut writer=crate::bw_wire::Arcs::new(false);let bytes=crate::bw_wire::encode(&scenario,now,&mut writer).unwrap();
        let mut reader=crate::bw_wire::Arcs::new(false);assert_eq!(crate::bw_wire::decode::<Scenario>(&bytes,now,&mut reader).unwrap(),scenario);
        good["events"][1]["tick"]=69.into();assert!(Scenario::parse(&good).is_err());
        good["events"][1]["tick"]=100.into();good["events"][1]["target_slot"]=3.into();assert!(Scenario::parse(&good).is_err());
        good["events"][1]["target_slot"]=4.into();assert!(Scenario::parse(&good).is_err());
        good["events"][1]["target_slot"]=1.into();good["events"][1]["position"]=serde_json::json!([0,0,0]);assert!(Scenario::parse(&good).is_err());
    }
}
