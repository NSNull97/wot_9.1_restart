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
    pub fn spec(self) -> &'static MapProfile {
        match self { Self::Karelia => &KARELIA, Self::Prohorovka => &PROHOROVKA }
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

/// Immutable source admission profiles for the two exported original #717 maps.
#[derive(Debug)]
pub struct MapProfile {
    pub terrain_manifest_sha256: &'static str,
    pub terrain_vertices_sha256: &'static str,
    pub terrain_triangles_sha256: &'static str,
    pub terrain_revision: &'static str,
    pub world_revision: &'static str,
    pub physics_manifest_sha256: &'static str,
    pub physics_triangle_count: usize,
    pub instance_count: usize,
    pub projectile_manifest_sha256: &'static str,
    pub projectile_manifest_bytes: usize,
    pub projectile_vertex_count: usize,
    pub projectile_triangle_count: usize,
    pub projectile_vertices_sha256: &'static str,
    pub projectile_triangles_sha256: &'static str,
    pub projectile_flags_sha256: &'static str,
    pub projectile_manifest_relative: &'static str,
}

const KARELIA: MapProfile = MapProfile {
    terrain_manifest_sha256: "5e23f58d4e9d78398bd9cd861f6bc09a038cce7e8f7b311731e50c30bcc958f9",
    terrain_vertices_sha256: "dc0752ceaaa6b469b36062a5c0a1d397edfa7a39815bf0d19d1290d0c8a08a92",
    terrain_triangles_sha256: "27ba25b1f81a37cb678584a898b0efed2b497ef1fc26ecb342ff852f72ec479c",
    terrain_revision: "karelia-terrain-717:5e23f58d4e9d78398bd9cd861f6bc09a038cce7e8f7b311731e50c30bcc958f9",
    world_revision: "karelia-projectile-world-717:5e23f58d4e9d78398bd9cd861f6bc09a038cce7e8f7b311731e50c30bcc958f9:ccd28d8e3320d041e569e217a8c20e0285db0459bc2ef447c5bd95dd97d80cea",
    physics_manifest_sha256: "ea6ef22aed0fdd4e4826500c280a616737f8990ce7ab7cd808b9382227ec5ffd",
    physics_triangle_count: 335551,
    instance_count: 2918,
    projectile_manifest_sha256: "ccd28d8e3320d041e569e217a8c20e0285db0459bc2ef447c5bd95dd97d80cea",
    projectile_manifest_bytes: 2190312,
    projectile_vertex_count: 538095,
    projectile_triangle_count: 179365,
    projectile_vertices_sha256: "8900634a1fd9dacbebe785d6c0289e2102f0811df7a677be473e2d0ea607db26",
    projectile_triangles_sha256: "06f3dcd079e6de79b4f653b4c6a23865b92d20449aab7480bbc8d6d2c8b85304",
    projectile_flags_sha256: "9c601f8bc5463af3dc7107d1592d984eeaffd6cb453f338b34cffdf5dc02d1a1",
    projectile_manifest_relative: "evidence/20261010-p06m-terrain-impact-01/projectile-obstacles01/01_karelia/manifest.json",
};

const PROHOROVKA: MapProfile = MapProfile {
    terrain_manifest_sha256: "d598db1dafee75e56e71a3453c1bc9824e86f32280df56854780127ceedad984",
    terrain_vertices_sha256: "4038d2967c2b8f66affdd729cc475050b1b9cadec3c1f1d187f0c99114d3fcbf",
    terrain_triangles_sha256: "27ba25b1f81a37cb678584a898b0efed2b497ef1fc26ecb342ff852f72ec479c",
    terrain_revision: "prohorovka-terrain-717:d598db1dafee75e56e71a3453c1bc9824e86f32280df56854780127ceedad984",
    world_revision: "prohorovka-projectile-world-717:d598db1dafee75e56e71a3453c1bc9824e86f32280df56854780127ceedad984:3db1ad3859ae2f5fed678ac5f148005cff38a3c915bb33dde3303de22e22bef7",
    physics_manifest_sha256: "9d358a48da303abaf15572f478dddc16971864960d9341943cc6d207b32b3265",
    physics_triangle_count: 428597,
    instance_count: 3904,
    projectile_manifest_sha256: "3db1ad3859ae2f5fed678ac5f148005cff38a3c915bb33dde3303de22e22bef7",
    projectile_manifest_bytes: 3004854,
    projectile_vertex_count: 856050,
    projectile_triangle_count: 285350,
    projectile_vertices_sha256: "e764c437c1f7676ec7916daba59e88f8ecea4fac558653d1fb3eb6fb3856de16",
    projectile_triangles_sha256: "c954bbc7bc893d80d26d720cb6be09e4059047a614ba6288af56c11803648a31",
    projectile_flags_sha256: "088d726205104d0da6a79b7a956f1e1281cd516c0b8a5248f7110dd8205f6bc5",
    projectile_manifest_relative: "evidence/20261012-p06p-prohorovka-01/import/projectile-obstacles01/05_prohorovka/manifest.json",
};
