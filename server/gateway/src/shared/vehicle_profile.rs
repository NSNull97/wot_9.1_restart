//! Closed #717 mounted profiles for the homogeneous temporary laboratory.
//! Source/native pins: P03M gateway-audit/source-fields.json and P03I
//! native-profile-04/native-catalog-01.json. This is not an inventory/crew grant.
use std::f32::consts::PI;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum VehicleKind { #[default] Ms1, Is7 }

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
    pub fn label(self) -> &'static str { match self { Self::Ms1 => "ms1", Self::Is7 => "is7" } }
    pub fn name(self) -> &'static str { match self { Self::Ms1 => "ussr:MS-1", Self::Is7 => "ussr:IS-7" } }
    pub fn descriptor(self) -> &'static [u8] { match self {
        Self::Ms1 => crate::arena_vehicle091::MS1_DESCRIPTOR,
        Self::Is7 => &[0x01,0x1c,0x3a,0x00,0x24,0x00,0xcd,0x00,0x0b,0x00,0x2f,0x00,0x3a,0x00,0x00],
    } }
    pub fn vehicle_compact_id(self) -> u32 { match self { Self::Ms1 => 3329, Self::Is7 => 7169 } }
    pub fn gun_compact_id(self) -> u32 { match self { Self::Ms1 => 5892, Self::Is7 => 14852 } }
    pub fn shell_compact_id(self) -> u32 { match self { Self::Ms1 => 2570, Self::Is7 => 14602 } }
    pub fn max_health(self) -> i16 { match self { Self::Ms1 => 90, Self::Is7 => 2150 } }
    pub fn mass_kg(self) -> f64 { match self { Self::Ms1 => 4691., Self::Is7 => 68190. } }
    /// Explicit AP-only temporary lab ammunition, not owned inventory.
    pub fn initial_ammo(self) -> u16 { match self { Self::Ms1 => 20, Self::Is7 => 30 } }
    /// Mounted native source capacity; the owned route uses its writer receipt.
    pub fn ammo_limit(self) -> u16 { match self { Self::Ms1 => 96, Self::Is7 => 30 } }
    pub fn battle_shot_limit(self) -> usize { 2 * self.ammo_limit() as usize }
    pub fn reload_seconds(self) -> f32 { match self { Self::Ms1 => 2.5, Self::Is7 => 13.7 } }
    pub fn panel_rows(self) -> [(u32, u16); 3] { match self {
        Self::Ms1 => crate::battle091::native_ammo::MS1_PANEL_ROWS,
        Self::Is7 => [(14602, 30), (14858, 0), (15114, 0)],
    } }
    pub fn shell(self) -> ShellSpec {
        let (caliber,damage,power_100,power_500,raw_speed,effects) = match self {
            Self::Ms1 => (37.,30,34.,27.,442.,2), Self::Is7 => (130.,490,250.,240.,900.,14),
        };
        ShellSpec { caliber,damage,power_100,power_500,raw_speed,effects,
            gravity:9.81,speed_factor:0.8,max_distance:720. }
    }
    pub fn damage(self) -> u16 { self.shell().damage }
    pub fn aim(self) -> AimSpec { match self {
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
    } }
}

#[cfg(test)]
mod tests {
    use super::*;
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
