//! Explicit original #717 map identities. Asset filename prefixes are not IDs:
//! original arena_defs/_list_.xml assigns Prohorovka arena type 4, not 5.
use std::io;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum MapId {
    #[default]
    Karelia,
    Prohorovka,
}

impl MapId {
    pub fn from_asset(asset: &str) -> io::Result<Self> {
        match asset {
            "01_karelia" => Ok(Self::Karelia),
            "05_prohorovka" => Ok(Self::Prohorovka),
            _ => Err(io::Error::new(io::ErrorKind::InvalidInput, "unsupported pinned map asset")),
        }
    }
    pub fn asset(self) -> &'static str {
        match self { Self::Karelia => "01_karelia", Self::Prohorovka => "05_prohorovka" }
    }
    pub fn arena_type_id(self) -> i32 {
        match self { Self::Karelia => 1, Self::Prohorovka => 4 }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn original_map_identity_is_explicit_and_never_inferred_from_filename_prefix() {
        assert_eq!(MapId::from_asset("01_karelia").unwrap().arena_type_id(), 1);
        assert_eq!(MapId::from_asset("05_prohorovka").unwrap().arena_type_id(), 4);
        for value in ["", "prohorovka", "5", "04_prohorovka", "05_prohorovka/../01_karelia"] {
            assert!(MapId::from_asset(value).is_err());
        }
    }
}
