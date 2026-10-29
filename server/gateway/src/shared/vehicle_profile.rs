//! Closed #717 mounted profiles for the homogeneous temporary laboratory.
//! Source/native pins: P03M gateway-audit/source-fields.json and P03I
//! native-profile-04/native-catalog-01.json. This is not an inventory/crew grant.
use std::f32::consts::PI;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum VehicleKind { #[default] Ms1, Is7, T26, T34, T3485, Wt128, Fv183,
    /// BATTLE-ANY: a stock assembly generated from #717 sources; data comes
    /// from the verified registry (`generated_vehicles`), never a fallback arm.
    Generated(super::generated_vehicles::GeneratedId) }
// BW-01 wire codec (tools/bw01_wire_gen.py): VehicleKind
impl crate::bw_wire::Wire for VehicleKind {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;match self {Self::Ms1=>bw_o.tag(0),Self::Is7=>bw_o.tag(1),Self::T26=>bw_o.tag(2),Self::T34=>bw_o.tag(3),Self::T3485=>bw_o.tag(4),Self::Wt128=>bw_o.tag(5),Self::Fv183=>bw_o.tag(6),Self::Generated(f0)=>{bw_o.tag(7);W::put(f0,bw_o);}}}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;match bw_i.tag()? {0=>Ok(Self::Ms1),1=>Ok(Self::Is7),2=>Ok(Self::T26),3=>Ok(Self::T34),4=>Ok(Self::T3485),5=>Ok(Self::Wt128),6=>Ok(Self::Fv183),7=>Ok(Self::Generated(W::get(bw_i)?)),t=>crate::bw_wire::variant(t)}}
}
// end BW-01 wire codec
use super::generated_vehicles as generated;

#[derive(Clone, Copy, Debug)]
pub struct ShellSpec {
    pub caliber: f64, pub damage: u16, pub power_100: f64, pub power_500: f64,
    pub raw_speed: f32, pub gravity: f32, pub speed_factor: f32,
    pub max_distance: f32, pub effects: u8,
}
impl ShellSpec {
    pub fn speed(self) -> f32 { self.raw_speed * self.speed_factor }
    pub fn effective_gravity(self) -> f32 { self.gravity * self.speed_factor * self.speed_factor }
}

#[derive(Clone, Copy, Debug)]
pub struct AimSpec {
    pub yaw_rate: f32, pub pitch_rate: f32, pub min_pitch: f32, pub max_pitch: f32,
    pub max_pitch_degrees: f32, pub rear_sector_degrees: f32, pub rear_max_degrees: f32,
    pub pivot: [f32; 3], pub gun: [f32; 3],
    pub turret_dispersion: f32, pub movement_dispersion: f32,
    pub hull_dispersion: f32, pub aiming_time: f32,
}

impl VehicleKind {
    pub const ALL:[Self;5]=[Self::Ms1,Self::Is7,Self::T26,Self::T34,Self::T3485];
    /// Explicit component/qualification discovery. ALL and legacy parsers stay five-only.
    pub const SUPPORTED:[Self;7]=[Self::Ms1,Self::Is7,Self::T26,Self::T34,Self::T3485,Self::Wt128,Self::Fv183];
    pub fn is_extended(self)->bool {matches!(self,Self::Wt128|Self::Fv183)}
    pub fn from_extended_label(value:&str)->Option<Self> {Self::SUPPORTED.into_iter().find(|kind|kind.label()==value)}
    pub fn from_extended_vehicle_compact_id(value:u32)->Option<Self> {Self::SUPPORTED.into_iter().find(|kind|kind.vehicle_compact_id()==value)}
    pub fn source_aim(self)->Option<super::aim::source_aim::SourceAim> {
        use super::aim::source_aim::SourceAim;
        match self {Self::Wt128=>Some(SourceAim::wt128()),Self::Fv183=>Some(SourceAim::fv183()),
            Self::Generated(id)=>Some(generated::entry(id).source_aim),_=>None}
    }
    /// Legacy kinds 0..=6; generated kinds follow (7 + registry id) and never
    /// index a closed seven-element array.
    pub fn index(self)->usize {match self {Self::Ms1=>0,Self::Is7=>1,Self::T26=>2,Self::T34=>3,Self::T3485=>4,Self::Wt128=>5,Self::Fv183=>6,
        Self::Generated(id)=>7+id.get()}}
    pub fn is_generated(self)->bool{matches!(self,Self::Generated(_))}
    pub fn generated(self)->Option<&'static generated::Entry>{match self{Self::Generated(id)=>Some(generated::entry(id)),_=>None}}
    pub fn mount(self)->crate::p06t_shells091::Mount {use crate::p06t_shells091::Mount;
        match self{Self::Ms1=>Mount::Ms1Stock,Self::Is7=>Mount::Is7Stock,Self::T26=>Mount::T26Stock,Self::T34=>Mount::T34Stock,Self::T3485=>Mount::T3485Stock,Self::Wt128=>Mount::WtE100128,Self::Fv183=>Mount::Fv215b183,
            Self::Generated(id)=>Mount::Generated(id)}}
    pub fn from_label(value:&str)->Option<Self> {Self::ALL.into_iter().find(|kind|kind.label()==value)}
    /// Owned battle labels: the five legacy kinds, then generated kinds.
    pub fn from_owned_label(value:&str)->Option<Self> {
        Self::from_label(value).or_else(||generated::registry().ok()?.by_label(value).map(Self::Generated))
    }
    /// MM-01: client tier (`list.xml` level) from the embedded battle-profile table.
    pub fn tier(self)->std::io::Result<Option<u8>> {generated::tier(&format!("vehicle:{}",self.name()))}
    /// MM-01: (tier, client `VEHICLE_CLASSES` index) of the same table row.
    pub fn queue_profile(self)->std::io::Result<Option<(u8,u8)>> {generated::profile(&format!("vehicle:{}",self.name()))}
    pub fn from_vehicle_compact_id(value:u32)->Option<Self> {Self::ALL.into_iter().find(|kind|kind.vehicle_compact_id()==value)}
    /// Source/component readiness never grants owner/native admission.
    pub fn battle_admission(self)->bool {matches!(self,Self::Ms1|Self::Is7)}
    pub fn label(self) -> &'static str { match self { Self::Ms1 => "ms1", Self::Is7 => "is7",Self::T26=>"t26",Self::T34=>"t34",Self::T3485=>"t3485",Self::Wt128=>"wt-e100-128",Self::Fv183=>"fv215b-183",
        Self::Generated(id)=>&generated::entry(id).label } }
    pub fn name(self) -> &'static str { match self { Self::Ms1 => "ussr:MS-1", Self::Is7 => "ussr:IS-7",Self::T26=>"ussr:T-26",Self::T34=>"ussr:T-34",Self::T3485=>"ussr:T-34-85",Self::Wt128=>"germany:Waffentrager_E100",Self::Fv183=>"uk:GB48_FV215b_183",
        Self::Generated(id)=>generated::entry(id).vehicle_id.trim_start_matches("vehicle:") } }
    pub fn descriptor(self) -> &'static [u8] { match self {
        Self::Ms1 => crate::arena_vehicle091::MS1_DESCRIPTOR,
        Self::Is7 => &[0x01,0x1c,0x3a,0x00,0x24,0x00,0xcd,0x00,0x0b,0x00,0x2f,0x00,0x3a,0x00,0x00],
        Self::T26=>&[0x01,0x12,0x24,0x00,0x13,0x00,0xc9,0x00,0x01,0x00,0x1e,0x00,0x10,0x00,0x00],
        Self::T34=>&[0x01,0x00,0x00,0x00,0x00,0x00,0xcb,0x00,0x03,0x00,0x00,0x00,0x00,0x00,0x00],
        Self::T3485=>&[0x01,0x0a,0x14,0x00,0x01,0x00,0xcb,0x00,0x03,0x00,0x11,0x00,0x06,0x00,0x00],
        Self::Wt128=>&[0x11,0x42,0xa1,0x00,0x2c,0x00,0xcd,0x00,0x0d,0x00,0x86,0x00,0x5a,0x00,0x00],
        Self::Fv183=>&[0x51,0x24,0x4f,0x00,0x3f,0x00,0xcd,0x00,0x14,0x00,0x45,0x00,0x36,0x00,0x00],
        Self::Generated(id)=>&generated::entry(id).descriptor,

    } }
    pub fn vehicle_compact_id(self) -> u32 { match self { Self::Ms1 => 3329, Self::Is7 => 7169,Self::T26=>4609,Self::T34=>1,Self::T3485=>2561,Self::Wt128=>16913,Self::Fv183=>9297,Self::Generated(id)=>generated::entry(id).type_compact_id } }
    pub fn gun_compact_id(self) -> u32 { match self { Self::Ms1 => 5892, Self::Is7 => 14852,Self::T26=>4100,Self::T34=>4,Self::T3485=>1540,Self::Wt128=>23060,Self::Fv183=>13908,Self::Generated(id)=>generated::entry(id).gun_compact_id } }
    pub fn shell_compact_id(self) -> u32 { match self { Self::Ms1 => 2570, Self::Is7 => 14602,Self::T26=>1034,Self::T34=>7178,Self::T3485=>7946,Self::Wt128=>13850,Self::Fv183=>20826,Self::Generated(id)=>u32::from(generated::entry(id).gun.shots[0].compact_descr) } }
    pub fn max_health(self) -> i16 { match self { Self::Ms1 => 90, Self::Is7 => 2150,Self::T26=>150,Self::T34=>400,Self::T3485=>670,Self::Wt128=>2000,Self::Fv183=>2000,Self::Generated(id)=>generated::entry(id).max_hp } }
    pub fn mass_kg(self) -> f64 { match self { Self::Ms1 => 4691., Self::Is7 => 68190.,Self::T26=>9302.,Self::T34=>27940.,Self::T3485=>32370.,Self::Wt128=>100000.0,Self::Fv183=>60000.0,Self::Generated(id)=>generated::entry(id).mass_kg } }
    /// Selected #717 stock turret circularVisionRadius: T-18_Standart/IS-7.
    /// Source binding: local/evidence/20261016-p07b-01/viewrange-binding02.json.
    /// Effective spotting still uses a separate, explicit test_lab LOS policy.
    pub fn view_range(self) -> f32 { match self { Self::Ms1 => 240., Self::Is7 => 400.,Self::T26=>280.,Self::T34=>240.,Self::T3485=>350.,Self::Wt128=>420.0,Self::Fv183=>400.0,Self::Generated(id)=>generated::entry(id).view_range } }
    /// Explicit AP-only temporary lab ammunition, not owned inventory.
    pub fn initial_ammo(self) -> u16 { match self { Self::Ms1 => 20, Self::Is7 => 30,Self::T26|Self::T34|Self::T3485=>20,Self::Wt128|Self::Fv183|Self::Generated(_)=>0 } }
    /// Mounted native source capacity; the owned route uses its writer receipt.
    pub fn ammo_limit(self) -> u16 { match self { Self::Ms1 => 96, Self::Is7 => 30,Self::T26=>160,Self::T34=>77,Self::T3485=>68,Self::Wt128=>60,Self::Fv183=>12,Self::Generated(id)=>generated::entry(id).gun.capacity } }
    pub fn battle_shot_limit(self) -> usize { 2 * self.ammo_limit() as usize }
    pub fn reload_seconds(self) -> f32 { match self { Self::Ms1 => 2.5, Self::Is7 => 13.7,Self::T26=>2.3,Self::T34=>6.,Self::T3485=>4.1,Self::Wt128=>60.0,Self::Fv183=>30.0,Self::Generated(id)=>generated::entry(id).gun.reload_seconds as f32 } }
    pub fn panel_rows(self) -> [(u32, u16); 3] { match self {
        Self::Ms1 => crate::battle091::native_ammo::MS1_PANEL_ROWS,
        Self::Is7 => [(14602, 30), (14858, 0), (15114, 0)],
        // Source shell identities only; owned stack quantities are supplied by
        // the frozen battle loadout. No unowned shell is granted here.
        Self::T26=>[(1034,0),(1290,0),(1546,0)],
        Self::T34=>[(7178,0),(7434,0),(7690,0)],
        Self::T3485=>[(7946,0),(8202,0),(8458,0)],
        Self::Wt128=>[(13850,0),(14106,0),(14362,0)],
        Self::Fv183=>[(20826,0),(21082,0),(21338,0)],
        Self::Generated(id)=>generated::entry(id).gun.shots.map(|s|(u32::from(s.compact_descr),0)),
    } }
    pub fn shell(self) -> ShellSpec {
        if let Self::Generated(id)=self {return generated::entry(id).shell_spec();}
        let (caliber,damage,power_100,power_500,raw_speed,effects) = match self {
            Self::Ms1 => (37.,30,34.,27.,442.,2), Self::Is7 => (130.,490,250.,240.,900.,14),
            Self::T26=>(37.,36,40.,33.,670.,2),Self::T34=>(76.,110,68.,62.,612.,6),Self::T3485=>(76.,115,125.,115.,816.,6),
            Self::Wt128=>(128.,560,276.,261.,1200.,14),Self::Fv183=>(182.9,1150,310.,300.,830.,18),
            Self::Generated(_)=>unreachable!("returned above"),
        };
        ShellSpec { caliber,damage,power_100,power_500,raw_speed,effects,
            gravity:9.81,speed_factor:0.8,max_distance:720. }
    }
    pub fn damage(self) -> u16 { self.shell().damage }
    pub fn aim(self) -> AimSpec { match self {
        Self::Generated(id)=>generated::entry(id).aim,
        Self::Ms1 => AimSpec { yaw_rate:39.*PI/180.,pitch_rate:52.5*PI/180.,
            min_pitch:-25.*PI/180.,max_pitch:8.*PI/180.,max_pitch_degrees:8.,
            rear_sector_degrees:35.,rear_max_degrees:1.,
            pivot:[0.001778,1.316402,0.033775],gun:[-0.238144,0.234668,0.410043],
            turret_dispersion:0.16/1f32.to_radians(),movement_dispersion:0.42*3.6,
            hull_dispersion:0.42/1f32.to_radians(),aiming_time:2.5 },
        // Mounted IS-7 overrides shared S-70 reload/maxAmmo/aimingTime.
        Self::Is7 => AimSpec { yaw_rate:25.*PI/180.,pitch_rate:26.25*PI/180.,
            min_pitch:-18.*PI/180.,max_pitch:6.*PI/180.,max_pitch_degrees:6.,
            rear_sector_degrees:45.,rear_max_degrees:1.,
            pivot:[0.000496,1.601943,0.528197],gun:[-0.046945,0.250257,1.01802],
            turret_dispersion:0.08/1f32.to_radians(),movement_dispersion:0.21*3.6,
            hull_dispersion:0.21/1f32.to_radians(),aiming_time:3.4 },
        // Source stock assemblies p04m-battle-source.v1; turret joint is hull
        // offset + relative turret pivot, as in the accepted MS-1/IS-7 route.
        Self::T26=>AimSpec {yaw_rate:44.*PI/180.,pitch_rate:43.75*PI/180.,
            min_pitch:-25.*PI/180.,max_pitch:8.*PI/180.,max_pitch_degrees:8.,
            rear_sector_degrees:0.,rear_max_degrees:8.,
            pivot:[-0.1449889987707138,0.978368+0.5241559743881226,-0.10165+0.053718000650405884],
            gun:[0.015381000004708767,0.36966198682785034,0.6166329979896545],
            turret_dispersion:0.16/1f32.to_radians(),movement_dispersion:0.25*3.6,
            hull_dispersion:0.25/1f32.to_radians(),aiming_time:2.3},
        Self::T34=>AimSpec {yaw_rate:40.*PI/180.,pitch_rate:39.375*PI/180.,
            min_pitch:-17.*PI/180.,max_pitch:6.*PI/180.,max_pitch_degrees:6.,
            rear_sector_degrees:42.,rear_max_degrees:1.,
            pivot:[-0.012+0.018293000757694244,0.7449+0.7911549806594849,0.6135830283164978],
            gun:[-0.01709200069308281,0.31865400075912476,0.6391170024871826],
            turret_dispersion:0.16/1f32.to_radians(),movement_dispersion:0.28*3.6,
            hull_dispersion:0.28/1f32.to_radians(),aiming_time:2.9},
        Self::T3485=>AimSpec {yaw_rate:46.*PI/180.,pitch_rate:39.375*PI/180.,
            min_pitch:-22.*PI/180.,max_pitch:7.*PI/180.,max_pitch_degrees:7.,
            rear_sector_degrees:0.,rear_max_degrees:7.,
            pivot:[0.0015569999814033508,0.9230780005455017+0.6163769960403442,0.6951969861984253],
            gun:[-0.001609,0.456677,1.02193],
            turret_dispersion:0.16/1f32.to_radians(),movement_dispersion:0.24*3.6,
            hull_dispersion:0.24/1f32.to_radians(),aiming_time:2.9},
        // Closed #717 source seven-combat manifest b1bd8eaa; no inventory grant.
        // Extended authority uses SourceEnvelope for BOTH pitch bounds and yaw.
        Self::Wt128=>AimSpec {yaw_rate:22.0*PI/180.,pitch_rate:26.25*PI/180.,
            min_pitch:-15.*PI/180.,max_pitch:5.*PI/180.,max_pitch_degrees:5.,
            rear_sector_degrees:37.0,rear_max_degrees:5.,
            pivot:[0.0,1.379118,-1.71333],gun:[0.0,1.37102,-0.690134],
            turret_dispersion:0.25/1f32.to_radians(),movement_dispersion:0.16*3.6,
            hull_dispersion:0.16/1f32.to_radians(),aiming_time:1.5},
        // Closed #717 source seven-combat manifest b1bd8eaa; no inventory grant.
        // Extended authority uses SourceEnvelope for BOTH pitch bounds and yaw.
        Self::Fv183=>AimSpec {yaw_rate:16.0*PI/180.,pitch_rate:23.625*PI/180.,
            min_pitch:-15.*PI/180.,max_pitch:5.*PI/180.,max_pitch_degrees:5.,
            rear_sector_degrees:0.0,rear_max_degrees:5.,
            pivot:[0.0,1.718248,-1.49516],gun:[0.0,0.583916,1.59175],
            turret_dispersion:0.4/1f32.to_radians(),movement_dispersion:0.26*3.6,
            hull_dispersion:0.26/1f32.to_radians(),aiming_time:3.4},
    } }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn p07b_stock_view_range_is_bound_to_each_selected_source_turret() {
        assert_eq!(VehicleKind::Ms1.view_range(),240.);
        assert_eq!(VehicleKind::Is7.view_range(),400.);
    }
    #[test] fn profile13_capacity_is_distinct_from_temporary_lab_grant() {
        assert_eq!((VehicleKind::Ms1.initial_ammo(),VehicleKind::Ms1.ammo_limit(),VehicleKind::Ms1.battle_shot_limit()),(20,96,192));
        assert_eq!((VehicleKind::Is7.initial_ammo(),VehicleKind::Is7.ammo_limit(),VehicleKind::Is7.battle_shot_limit()),(30,30,60));
    }
    #[test] fn mounted_is7_overrides_and_ap_only_loadout_are_consistent() {
        let k=VehicleKind::Is7;
        assert_eq!(k.descriptor(), &[1,28,58,0,36,0,205,0,11,0,47,0,58,0,0]);
        assert_eq!((k.vehicle_compact_id(),k.gun_compact_id(),k.shell_compact_id()),(7169,14852,14602));
        assert_eq!((k.max_health(),k.initial_ammo(),k.ammo_limit(),k.battle_shot_limit()),(2150,30,30,60));
        assert_eq!(k.reload_seconds(),13.7); assert_eq!(k.aim().aiming_time,3.4);
        assert_eq!(k.panel_rows(),[(14602,30),(14858,0),(15114,0)]);
        assert_eq!(k.shell().speed(),720.); assert_eq!(k.damage(),490);
    }
}

#[cfg(test)]
#[path = "vehicle_profile_tests.rs"]
mod runtime_tests;

#[cfg(test)]
#[path="p04m_combat_profile_tests.rs"]
mod p04m_combat_profile_tests;

#[cfg(test)]
#[path="p06t_extended_vehicle_tests.rs"]
mod extended_tests;
