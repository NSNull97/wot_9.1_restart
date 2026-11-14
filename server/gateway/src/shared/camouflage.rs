//! CONTENT-0 5a opt-in open-field project calibration. These values and the
//! formula are not recovered 0.9.1 server rules. No foliage is inferred here.
use std::{io, sync::OnceLock};

pub const POLICY: &str = "content0-s5a-project-camouflage.v1";
pub const NET: u16 = 1785; // #717 raw optional-device ID 6, compact (6 << 8) | 249.

#[derive(Clone, Copy, Debug)]
pub struct Calibration { pub still: [f32; 5], pub moving: [f32; 5], pub net: [f32; 5], pub fire: f32, pub fire_window_ms: u64, pub net_delay_ms: u64 }

fn bad() -> io::Error { io::Error::new(io::ErrorKind::InvalidData, "invalid 5a project camouflage calibration") }

fn load() -> io::Result<Calibration> {
    let v: serde_json::Value = serde_json::from_str(include_str!("../../../../config/rulesets/content0-s5a-camouflage.v1.json")).map_err(|_|bad())?;
    if v["schema"] != POLICY || v["classification"] != "PROJECT_CALIBRATION_NOT_HISTORICAL"
        || v["class_order"] != serde_json::json!(["lightTank", "mediumTank", "heavyTank", "SPG", "AT-SPG"]) { return Err(bad()); }
    let row = |key: &str| -> io::Result<[f32;5]> {
        let data = v[key].as_array().filter(|x|x.len()==5).ok_or_else(bad)?;
        let mut values=[0.;5];
        for (out, item) in values.iter_mut().zip(data) {
            let value=item.as_f64().filter(|x|x.is_finite() && (0. ..=1.).contains(x)).ok_or_else(bad)?;
            *out=value as f32;
        }
        Ok(values)
    };
    let fire=v["fire_multiplier"].as_f64().filter(|x|(0. ..=1.).contains(x)).ok_or_else(bad)? as f32;
    let window=v["fire_window_ms"].as_u64().filter(|x|*x<=60_000).ok_or_else(bad)?;
    let delay=v["net_delay_ms"].as_u64().filter(|x|*x==3000).ok_or_else(bad)?;
    Ok(Calibration{still:row("still")?,moving:row("moving")?,net:row("net_bonus")?,fire,fire_window_ms:window,net_delay_ms:delay})
}

pub fn calibration() -> io::Result<Calibration> {
    static CONFIG: OnceLock<Option<Calibration>> = OnceLock::new();
    CONFIG.get_or_init(||load().ok()).ok_or_else(bad)
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Components { pub base: f32, pub net: f32, pub fire_multiplier: f32, pub effective: f32 }

pub fn components(class: u8, moving: bool, net: bool, fire: bool) -> io::Result<Components> {
    let c=calibration()?;
    let class=usize::from(class); if class>=5 {return Err(bad());}
    let base=if moving {c.moving[class]} else {c.still[class]};
    let net=if net {c.net[class]} else {0.};
    let fire_multiplier=if fire {c.fire} else {1.};
    Ok(Components {base,net,fire_multiplier,effective:((base+net)*fire_multiplier).clamp(0.,1.)})
}

pub fn threshold(view: f32, maximum: f32, proximity: f32, camouflage: f32) -> io::Result<f32> {
    if ![view,maximum,proximity,camouflage].into_iter().all(f32::is_finite) || view<0. || maximum<0. || proximity<0. || proximity>maximum || !(0. ..=1.).contains(&camouflage) { return Err(bad()); }
    Ok((proximity+(view-proximity).max(0.)*(1.-camouflage)).min(maximum))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn project_calibration_and_detection_boundaries() {
        let still=components(0,false,false,false).unwrap();
        let moving=components(0,true,false,false).unwrap();
        assert_eq!(still.base,moving.base); // project LT policy, not historical proof
        let armed=components(0,false,true,false).unwrap();
        let fired=components(0,false,true,true).unwrap();
        assert!(armed.effective>still.effective && fired.effective<still.effective);
        assert!(threshold(400.,445.,50.,armed.effective).unwrap()<threshold(400.,445.,50.,still.effective).unwrap());
        assert_eq!(threshold(600.,445.,50.,0.).unwrap(),445.);
        assert_eq!(threshold(20.,445.,50.,1.).unwrap(),50.);
        assert!(components(5,false,false,false).is_err());
        assert!(threshold(f32::NAN,445.,50.,0.).is_err());
    }
    #[test] fn every_embedded_admitted_kind_has_a_class_for_calibration() {
        use super::super::{generated_vehicles, vehicle_profile::VehicleKind};
        for kind in VehicleKind::SUPPORTED {
            assert!(kind.queue_profile().unwrap().is_some(),"{}",kind.name());
        }
        for entry in generated_vehicles::registry().unwrap().entries() {
            assert!(generated_vehicles::profile(&entry.vehicle_id).unwrap().is_some(),"{}",entry.vehicle_id);
        }
    }
}
