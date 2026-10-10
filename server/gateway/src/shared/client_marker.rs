//! Pure diagnostic port of #717 `_FlashGunMarker._changeColor`, source line2772
//! in `scripts/client/AvatarInputHandler/control_modes.pyc`.
//!
//! Source SHA-256: d13714e51ecf56586565b382caa1ca9702911125644269bb3c6096c5ac75e6c5.
//! Canonical inspected method SHA-256:
//! f1d404c952ae6baa7f5dc2356b326f5ea1f438028205c43e92ba94d5226758c7.
//! This predicts a client marker label, not authoritative penetration, ricochet,
//! probability or damage. It is not connected to world, trace or native wire.
//! The original marker uses raw armor and distance from own vehicle position;
//! it does not use hitAngleCos, outward normals, normalization or RNG. Its
//! caller handles no-target/allied/dead-target `normal` display separately.

use std::io;

pub const PROFILE_REVISION: &str = "client-marker-717-stock-ms1-ap-v1";
pub const MAX_DISTANCE_INPUT: f64 = 100_000.0;
pub const MAX_ARMOR_INPUT: f64 = 100_000.0;
const STOCK_P100: f64 = 34.0;
const STOCK_P500: f64 = 27.0;
const STOCK_MAX_DISTANCE: f64 = 720.0;

fn invalid() -> io::Error {
    io::Error::new(io::ErrorKind::InvalidInput, "unsupported client marker input")
}

fn bounded(value: f64, maximum: f64) -> bool {
    value.is_finite() && value >= 0.0 && value <= maximum
}

/// Validated diagnostic inputs for stock MS-1 gun5892/AP2570 only. No generic
/// shell constructor is exposed. Private fields prevent silently applying the
/// measured stock contract to another shell or a different maximum distance.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ClientMarkerInput {
    distance: f64,
    armor: f64,
    p100: f64,
    p500: f64,
    max_distance: f64,
}

impl ClientMarkerInput {
    /// `distance` is the measured length from own vehicle position to the
    /// marker point, not a projectile path length or muzzle-to-contact range.
    /// `armor` must be explicitly present; absent native materials are not
    /// silently converted to armor0. A caller reproducing the separate client
    /// fallback must provide Some(0) and preserve that provenance itself.
    pub fn stock_ms1_ap(distance: f64, armor: Option<f64>) -> io::Result<Self> {
        let input = Self { distance, armor: armor.ok_or_else(invalid)?,
            p100: STOCK_P100, p500: STOCK_P500, max_distance: STOCK_MAX_DISTANCE };
        input.validate()?;
        Ok(input)
    }

    pub fn distance(self) -> f64 { self.distance }
    pub fn armor(self) -> f64 { self.armor }

    fn validate(self) -> io::Result<()> {
        if !bounded(self.distance, MAX_DISTANCE_INPUT) || !bounded(self.armor, MAX_ARMOR_INPUT)
            || self.p100 != STOCK_P100 || self.p500 != STOCK_P500
            || self.max_distance != STOCK_MAX_DISTANCE {
            return Err(invalid());
        }
        Ok(())
    }
}

/// Original UI label names only. These are not server impact outcomes.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ClientMarkerClass { GreatPierced, LittlePierced, NotPierced }

impl ClientMarkerClass {
    pub fn source_label(self) -> &'static str { match self {
        Self::GreatPierced => "great_pierced",
        Self::LittlePierced => "little_pierced",
        Self::NotPierced => "not_pierced",
    } }
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ClientMarkerEstimate {
    pub power: f64,
    /// Original `piercingPercent` expression; this is not a probability.
    pub armor_to_power_score: f64,
    pub class: ClientMarkerClass,
}

/// Preserve Python float operation order. In particular, do not replace the
/// score with armor/power*100 or clamp interpolation at500: both differ from
/// the inspected method. Native vector-derived inputs are passed as measured;
/// intermediate Python float arithmetic is binary64, not a float32 rewrite.
pub fn predict(input: ClientMarkerInput) -> io::Result<ClientMarkerEstimate> {
    input.validate()?;
    let mut power = if input.distance <= 100.0 {
        input.p100
    } else if input.max_distance > input.distance {
        input.p100 + (input.p500 - input.p100) * (input.distance - 100.0) / 400.0
    } else {
        0.0
    };
    if power < 0.0 { power = 0.0; }
    let score = if power > 0.0 {
        100.0 + (input.armor - power) / power * 100.0
    } else {
        1000.0
    };
    if !power.is_finite() || !score.is_finite() { return Err(invalid()); }
    let class = if score >= 150.0 {
        ClientMarkerClass::NotPierced
    } else if 90.0 < score && score < 150.0 {
        ClientMarkerClass::LittlePierced
    } else {
        ClientMarkerClass::GreatPierced
    };
    Ok(ClientMarkerEstimate { power, armor_to_power_score: score, class })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn estimate(distance: f64, armor: f64) -> ClientMarkerEstimate {
        predict(ClientMarkerInput::stock_ms1_ap(distance, Some(armor)).unwrap()).unwrap()
    }

    #[test]
    fn stock_distance_anchors_include_extrapolation_after_500_and_cutoff_at_720() {
        for (distance, power) in [(0.0, 34.0), (100.0, 34.0), (300.0, 30.5),
            (500.0, 27.0), (600.0, 25.25), (720.0, 0.0), (MAX_DISTANCE_INPUT, 0.0)] {
            assert_eq!(estimate(distance, 16.0).power, power, "distance={distance}");
        }
        // Binary64 reference vectors measured from the exact arithmetic order.
        // They are source-derived tests, not a claim of a native runtime run.
        assert_eq!(estimate(101.0, 16.0).power.to_bits(), 0x4040_fdc2_8f5c_28f6);
        assert_eq!(estimate(719.0, 16.0).power.to_bits(), 0x4037_2ae1_47ae_147b);
        let just_before_range = f64::from_bits(720.0f64.to_bits() - 1);
        assert!(estimate(just_before_range, 16.0).power > 23.0);
        assert_eq!(estimate(f64::from_bits(720.0f64.to_bits() + 1), 16.0).power, 0.0);
    }

    #[test]
    fn source_threshold_equalities_and_adjacent_inputs_are_distinct() {
        use ClientMarkerClass::*;
        for (armor, score_bits, class) in [
            (f64::from_bits(30.6f64.to_bits() - 1), 0x4056_8000_0000_0000, GreatPierced),
            (30.6, 0x4056_8000_0000_0000, GreatPierced),
            (f64::from_bits(30.6f64.to_bits() + 1), 0x4056_8000_0000_0001, LittlePierced),
            (f64::from_bits(51.0f64.to_bits() - 1), 0x4062_bfff_ffff_ffff, LittlePierced),
            (51.0, 0x4062_c000_0000_0000, NotPierced),
            (f64::from_bits(51.0f64.to_bits() + 1), 0x4062_c000_0000_0001, NotPierced),
        ] {
            let result = estimate(0.0, armor);
            assert_eq!(result.armor_to_power_score.to_bits(), score_bits, "armor={armor:?}");
            assert_eq!(result.class, class, "armor={armor:?}");
        }
    }

    #[test]
    fn algebraic_score_simplification_is_not_bit_identical_to_the_source() {
        let armor = f64::from_bits(30.6f64.to_bits() - 1);
        let result = estimate(0.0, armor);
        assert_eq!(result.armor_to_power_score.to_bits(), 90.0f64.to_bits());
        assert_ne!(result.armor_to_power_score.to_bits(), (armor / result.power * 100.0).to_bits());
    }

    #[test]
    fn zero_armor_is_present_but_absent_material_is_rejected() {
        assert!(ClientMarkerInput::stock_ms1_ap(0.0, None).is_err());
        let zero = estimate(0.0, 0.0);
        assert_eq!(zero.armor_to_power_score, 0.0);
        assert_eq!(zero.class, ClientMarkerClass::GreatPierced);
        // Even armor0 gets the no-power score at range cutoff. Neither UI
        // label is a penetration or no-penetration result for the server.
        let at_range = estimate(720.0, 0.0);
        assert_eq!(at_range.armor_to_power_score, 1000.0);
        assert_eq!(at_range.class, ClientMarkerClass::NotPierced);
    }

    #[test]
    fn invalid_or_unbounded_values_are_rejected_and_limits_remain_finite() {
        for invalid in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY, -1.0,
            MAX_DISTANCE_INPUT + 1.0] {
            assert!(ClientMarkerInput::stock_ms1_ap(invalid, Some(16.0)).is_err());
        }
        for invalid in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY, -1.0,
            MAX_ARMOR_INPUT + 1.0] {
            assert!(ClientMarkerInput::stock_ms1_ap(0.0, Some(invalid)).is_err());
        }
        for distance in [0.0, 100.0, 500.0, 719.0, 720.0, MAX_DISTANCE_INPUT] {
            let result = estimate(distance, MAX_ARMOR_INPUT);
            assert!(result.power.is_finite() && result.armor_to_power_score.is_finite());
        }
    }

    #[test]
    fn unsupported_profiles_cannot_enter_the_stock_kernel() {
        let stock = ClientMarkerInput::stock_ms1_ap(100.0, Some(18.0)).unwrap();
        for invalid in [ClientMarkerInput { p100: 35.0, ..stock },
            ClientMarkerInput { p500: 28.0, ..stock },
            ClientMarkerInput { max_distance: 500.0, ..stock },
            ClientMarkerInput { p100: f64::NAN, ..stock },
            ClientMarkerInput { distance: f64::NAN, ..stock },
            ClientMarkerInput { armor: f64::INFINITY, ..stock }] {
            assert!(predict(invalid).is_err());
        }
    }

    #[test]
    fn repeated_predictions_preserve_inputs_and_original_ui_label_names() {
        let input = ClientMarkerInput::stock_ms1_ap(600.0, Some(16.0)).unwrap();
        let original = input;
        let expected = predict(input).unwrap();
        for _ in 0..16 { assert_eq!(predict(input).unwrap(), expected); }
        assert_eq!(input, original);
        assert_eq!((input.distance(), input.armor()), (600.0, 16.0));
        assert_eq!(expected.armor_to_power_score.to_bits(), 0x404f_aee4_1e6a_7498);
        assert_eq!(expected.class.source_label(), "great_pierced");
        assert_eq!(estimate(0.0, 40.0).class.source_label(), "little_pierced");
        assert_eq!(estimate(0.0, 51.0).class.source_label(), "not_pierced");
        assert_eq!(PROFILE_REVISION, "client-marker-717-stock-ms1-ap-v1");
    }
}
