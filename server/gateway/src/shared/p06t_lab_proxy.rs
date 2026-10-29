//! Invented, pinned LAB internal boxes, never historical #717 module volumes.
//! Input must be recomputed from the actual authoritative exterior contact.
use std::io;
use crate::p06t_device_caps::{Profile,Device,CREW};
pub const POLICY:&str="test_lab.p06t.aabb-proxy-nearest-two.v1";
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Component {Hull,Turret,Gun}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Target {Device(Device),Seat(u8)}
// BW-01 wire codec (tools/bw01_wire_gen.py): Target
impl crate::bw_wire::Wire for Target {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;match self {Self::Device(f0)=>{bw_o.tag(0);W::put(f0,bw_o);}Self::Seat(f0)=>{bw_o.tag(1);W::put(f0,bw_o);}}}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;match bw_i.tag()? {0=>Ok(Self::Device(W::get(bw_i)?)),1=>Ok(Self::Seat(W::get(bw_i)?)),t=>crate::bw_wire::variant(t)}}
}
// end BW-01 wire codec
impl Target {pub fn key(self)->usize {match self {Self::Device(d)=>d as usize,Self::Seat(s)=>9+usize::from(s)}}}
#[derive(Clone,Copy,Debug,PartialEq)]
pub struct Hit {pub target:Target,pub entry_fraction:f64}
fn bad()->io::Error {io::Error::new(io::ErrorKind::InvalidData,"LAB proxy source bounds/chord")}
fn entry(start:[f64;3],end:[f64;3],low:[f64;3],high:[f64;3])->Option<f64> {
    let mut enter:f64=0.;let mut leave:f64=1.;
    for axis in 0..3 {
        let delta=end[axis]-start[axis];
        if delta==0. {if start[axis]<low[axis]||start[axis]>high[axis] {return None;}}
        else {let a=(low[axis]-start[axis])/delta;let b=(high[axis]-start[axis])/delta;
            enter=enter.max(a.min(b));leave=leave.min(a.max(b));if enter>leave{return None;}}
    }
    (leave>=0.&&enter<=1.).then_some(enter)
}
/// Start is the actual verified component-local exterior CONTACT point; end
/// is the forward component-AABB exit. Do not blindly pass the native wire
/// impact segment's AABB entry, which can precede the exterior surface.
/// Numeric validity alone does not establish that provenance.
pub fn select(profile:Profile,component:Component,bounds:[[f32;3];2],start:[f32;3],end:[f32;3])->io::Result<Vec<Hit>> {
    if bounds.into_iter().flatten().chain(start).chain(end).any(|v|!v.is_finite()||v.abs()>100_000.)
        || (0..3).any(|i|bounds[0][i]>=bounds[1][i])
        || start==end || (0..3).any(|i|start[i]<bounds[0][i]-0.0002||start[i]>bounds[1][i]+0.0002
            ||end[i]<bounds[0][i]-0.0002||end[i]>bounds[1][i]+0.0002) {return Err(bad());}
    let n=|v:[f32;3]|std::array::from_fn(|i|(f64::from(v[i])-f64::from(bounds[0][i]))/(f64::from(bounds[1][i])-f64::from(bounds[0][i])));
    let start=n(start);let end=n(end);
    if entry(start,end,[0.;3],[1.;3]).is_none(){return Err(bad());}
    let mut boxes:Vec<(Target,[f64;3],[f64;3])>=Vec::new();
    let mut device=|d,low,high|boxes.push((Target::Device(d),low,high));
    match component {
        Component::Hull=>{
            device(Device::Engine,[0.2,0.25,0.05],[0.8,0.75,0.35]);
            device(Device::FuelTank,[0.,0.25,0.2],[0.2,0.75,0.55]);
            device(Device::AmmoBay,[0.25,0.25,0.4],[0.75,0.75,0.65]);
            device(Device::Radio,[0.6,0.6,0.7],[0.9,0.9,0.9]);
            device(Device::LeftTrack,[0.,0.,0.],[0.15,0.25,1.]);
            device(Device::RightTrack,[0.85,0.,0.],[1.,0.25,1.]);
            for (seat,c) in profile.crew().iter().enumerate() {
                if c.primary_driver {boxes.push((Target::Seat(seat as u8),[0.2,0.3,0.7],[0.45,0.6,0.95]));}
                else if c.primary_radioman {boxes.push((Target::Seat(seat as u8),[0.55,0.3,0.7],[0.8,0.6,0.95]));}
            }
        },
        Component::Turret=>{
            device(Device::TurretRotator,[0.,0.,0.],[1.,0.2,1.]);
            device(Device::SurveyingDevice,[0.,0.8,0.],[1.,1.,1.]);
            let seats:Vec<usize>=profile.crew().iter().enumerate().filter(|(_,c)|!c.primary_driver&&!c.primary_radioman).map(|(i,_)|i).collect();
            let count=seats.len() as f64;
            for (rank,seat) in seats.into_iter().enumerate() {
                let low=0.1+0.8*rank as f64/count;let high=0.1+0.8*(rank+1) as f64/count;
                boxes.push((Target::Seat(seat as u8),[low,0.25,0.2],[high,0.75,0.8]));
            }
        },
        Component::Gun=>device(Device::Gun,[0.;3],[1.;3]),
    }
    let mut hits:Vec<_>=boxes.into_iter().filter_map(|(target,low,high)|entry(start,end,low,high).map(|entry_fraction|Hit{target,entry_fraction})).collect();
    hits.sort_by(|a,b|a.entry_fraction.total_cmp(&b.entry_fraction).then(a.target.key().cmp(&b.target.key())));
    hits.truncate(2);Ok(hits)
}
