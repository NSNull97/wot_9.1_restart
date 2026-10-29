//! Generated numeric source caps after fresh original-file checks. No historical damage algorithm.
pub const SOURCE_SHA256:&str="3c4219c2adda799677dea310e84765bbfebca6edfa06aa3db450a7ddfb4875b5";
pub const SOURCE_V2_SHA256:&str="2d74a8e8f272e6305d6779d887cac44ad9794c4ec40807ddf76a5139e3db9da4";
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Profile {Ms1,Is7,T26,T34,T3485,Wt128,Fv183,
/// BATTLE-ANY generated assembly: caps/crew from the verified registry.
Generated(crate::gateway091::shared::generated_vehicles::GeneratedId)}
// BW-01 wire codec (tools/bw01_wire_gen.py): Profile
impl crate::bw_wire::Wire for Profile {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;match self {Self::Ms1=>bw_o.tag(0),Self::Is7=>bw_o.tag(1),Self::T26=>bw_o.tag(2),Self::T34=>bw_o.tag(3),Self::T3485=>bw_o.tag(4),Self::Wt128=>bw_o.tag(5),Self::Fv183=>bw_o.tag(6),Self::Generated(f0)=>{bw_o.tag(7);W::put(f0,bw_o);}}}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;match bw_i.tag()? {0=>Ok(Self::Ms1),1=>Ok(Self::Is7),2=>Ok(Self::T26),3=>Ok(Self::T34),4=>Ok(Self::T3485),5=>Ok(Self::Wt128),6=>Ok(Self::Fv183),7=>Ok(Self::Generated(W::get(bw_i)?)),t=>crate::bw_wire::variant(t)}}
}
// end BW-01 wire codec
impl Profile {
    /// Existing World/v1 policy deliberately retains exactly these five.
    pub const ALL:[Self;5]=[Self::Ms1,Self::Is7,Self::T26,Self::T34,Self::T3485];
    pub const SUPPORTED:[Self;7]=[Self::Ms1,Self::Is7,Self::T26,Self::T34,Self::T3485,Self::Wt128,Self::Fv183];
    pub fn index(self)->usize{match self{Self::Ms1=>0,Self::Is7=>1,Self::T26=>2,Self::T34=>3,Self::T3485=>4,Self::Wt128=>5,Self::Fv183=>6,Self::Generated(id)=>7+id.get()}}
    pub fn is_legacy(self)->bool{self.index()<Self::ALL.len()}
    fn generated(self)->Option<&'static crate::gateway091::shared::generated_vehicles::Entry>{match self{Self::Generated(id)=>Some(crate::gateway091::shared::generated_vehicles::entry(id)),_=>None}}
    pub fn caps(self)->&'static [Cap;9]{self.generated().map_or_else(||&CAPS[self.index()],|e|&e.caps)}
    pub fn crew(self)->&'static [Seat]{self.generated().map_or_else(||CREW[self.index()],|e|&e.crew)}
    pub fn max_hp(self)->u16{self.generated().map_or_else(||MAX_HP[self.index()],|e|e.max_hp as u16)}
    pub fn engine_fire_chance(self)->f64{self.generated().map_or_else(||ENGINE_FIRE_CHANCE[self.index()],|e|e.engine_fire_chance)}
    /// Owned device profile of a battle kind: the five legacy kinds or a generated one.
    pub fn for_owned(kind:crate::gateway091::shared::vehicle_profile::VehicleKind)->Option<Self>{use crate::gateway091::shared::vehicle_profile::VehicleKind as K;
        match kind{K::Generated(id)=>Some(Self::Generated(id)),_=>Self::ALL.get(kind.index()).copied()}}
    /// Per-profile source provenance; a v2 State separately binds the complete
    /// seven-profile source manifest even when its selected profile is old.
    pub fn source_sha(self)->&'static str{if self.is_legacy(){SOURCE_SHA256}else{SOURCE_V2_SHA256}}
    pub fn label(self)->&'static str{match self{Self::Ms1=>"ms1",Self::Is7=>"is7",Self::T26=>"t26",Self::T34=>"t34",Self::T3485=>"t3485",Self::Wt128=>"wt-e100-128",Self::Fv183=>"fv215b-183",
        Self::Generated(id)=>&crate::gateway091::shared::generated_vehicles::entry(id).label}}
}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
#[repr(usize)]
pub enum Device {Engine,AmmoBay,FuelTank,Radio,LeftTrack,RightTrack,Gun,TurretRotator,SurveyingDevice}
// BW-01 wire codec (tools/bw01_wire_gen.py): Device
impl crate::bw_wire::Wire for Device {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){match self {Self::Engine=>bw_o.tag(0),Self::AmmoBay=>bw_o.tag(1),Self::FuelTank=>bw_o.tag(2),Self::Radio=>bw_o.tag(3),Self::LeftTrack=>bw_o.tag(4),Self::RightTrack=>bw_o.tag(5),Self::Gun=>bw_o.tag(6),Self::TurretRotator=>bw_o.tag(7),Self::SurveyingDevice=>bw_o.tag(8),}}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{match bw_i.tag()? {0=>Ok(Self::Engine),1=>Ok(Self::AmmoBay),2=>Ok(Self::FuelTank),3=>Ok(Self::Radio),4=>Ok(Self::LeftTrack),5=>Ok(Self::RightTrack),6=>Ok(Self::Gun),7=>Ok(Self::TurretRotator),8=>Ok(Self::SurveyingDevice),t=>crate::bw_wire::variant(t)}}
}
// end BW-01 wire codec
impl Device {pub const ALL:[Self;9]=[Self::Engine,Self::AmmoBay,Self::FuelTank,Self::Radio,Self::LeftTrack,Self::RightTrack,Self::Gun,Self::TurretRotator,Self::SurveyingDevice];pub fn extra(self)->u8{26+self as u8}}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub struct Cap {pub max:u16,pub regen:u16}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub struct Seat {pub extra:u8,pub roles:u8,pub primary_driver:bool,pub primary_radioman:bool}
pub const MAX_HP:[u16;7]=[90,2150,150,400,670,2000,2000];
pub const ENGINE_FIRE_CHANCE:[f64;7]=[0.2,0.15,0.2,0.15,0.15,0.15,0.2];
pub const MIN_FIRE_STARTING_DAMAGE:u16=21;
pub const CAPS:[[Cap;9];7]=[
[Cap{max:25,regen:17},Cap{max:60,regen:40},Cap{max:100,regen:40},Cap{max:90,regen:75},Cap{max:40,regen:30},Cap{max:40,regen:30},Cap{max:54,regen:27},Cap{max:50,regen:25},Cap{max:30,regen:15}],
[Cap{max:360,regen:180},Cap{max:210,regen:140},Cap{max:200,regen:80},Cap{max:250,regen:75},Cap{max:250,regen:190},Cap{max:250,regen:190},Cap{max:210,regen:105},Cap{max:170,regen:85},Cap{max:120,regen:60}],
[Cap{max:40,regen:20},Cap{max:75,regen:50},Cap{max:100,regen:40},Cap{max:100,regen:49},Cap{max:50,regen:40},Cap{max:50,regen:40},Cap{max:54,regen:27},Cap{max:60,regen:30},Cap{max:40,regen:20}],
[Cap{max:105,regen:52},Cap{max:130,regen:85},Cap{max:150,regen:60},Cap{max:110,regen:55},Cap{max:90,regen:70},Cap{max:90,regen:70},Cap{max:106,regen:53},Cap{max:100,regen:50},Cap{max:70,regen:35}],
[Cap{max:145,regen:72},Cap{max:140,regen:90},Cap{max:150,regen:60},Cap{max:110,regen:55},Cap{max:110,regen:85},Cap{max:110,regen:85},Cap{max:130,regen:65},Cap{max:120,regen:60},Cap{max:80,regen:40}],
[Cap{max:360,regen:170},Cap{max:280,regen:190},Cap{max:200,regen:70},Cap{max:250,regen:75},Cap{max:300,regen:225},Cap{max:300,regen:225},Cap{max:240,regen:120},Cap{max:100,regen:50},Cap{max:120,regen:60}],
[Cap{max:320,regen:160},Cap{max:260,regen:180},Cap{max:200,regen:70},Cap{max:180,regen:108},Cap{max:250,regen:190},Cap{max:250,regen:190},Cap{max:280,regen:140},Cap{max:170,regen:85},Cap{max:120,regen:60}],
];
pub const CREW:[&[Seat];7]=[
&[Seat{extra:35,roles:27,primary_driver:false,primary_radioman:false},Seat{extra:36,roles:4,primary_driver:true,primary_radioman:false}],
&[Seat{extra:35,roles:1,primary_driver:false,primary_radioman:false},Seat{extra:39,roles:2,primary_driver:false,primary_radioman:false},Seat{extra:36,roles:4,primary_driver:true,primary_radioman:false},Seat{extra:41,roles:8,primary_driver:false,primary_radioman:false},Seat{extra:42,roles:24,primary_driver:false,primary_radioman:false}],
&[Seat{extra:35,roles:17,primary_driver:false,primary_radioman:false},Seat{extra:36,roles:4,primary_driver:true,primary_radioman:false},Seat{extra:39,roles:10,primary_driver:false,primary_radioman:false}],
&[Seat{extra:35,roles:3,primary_driver:false,primary_radioman:false},Seat{extra:37,roles:16,primary_driver:false,primary_radioman:true},Seat{extra:36,roles:4,primary_driver:true,primary_radioman:false},Seat{extra:41,roles:8,primary_driver:false,primary_radioman:false}],
&[Seat{extra:35,roles:1,primary_driver:false,primary_radioman:false},Seat{extra:39,roles:2,primary_driver:false,primary_radioman:false},Seat{extra:37,roles:16,primary_driver:false,primary_radioman:true},Seat{extra:36,roles:4,primary_driver:true,primary_radioman:false},Seat{extra:41,roles:8,primary_driver:false,primary_radioman:false}],
&[Seat{extra:35,roles:1,primary_driver:false,primary_radioman:false},Seat{extra:39,roles:2,primary_driver:false,primary_radioman:false},Seat{extra:36,roles:4,primary_driver:true,primary_radioman:false},Seat{extra:37,roles:16,primary_driver:false,primary_radioman:true},Seat{extra:41,roles:8,primary_driver:false,primary_radioman:false},Seat{extra:42,roles:8,primary_driver:false,primary_radioman:false}],
&[Seat{extra:35,roles:17,primary_driver:false,primary_radioman:false},Seat{extra:39,roles:2,primary_driver:false,primary_radioman:false},Seat{extra:36,roles:4,primary_driver:true,primary_radioman:false},Seat{extra:41,roles:8,primary_driver:false,primary_radioman:false},Seat{extra:42,roles:8,primary_driver:false,primary_radioman:false}],
];
