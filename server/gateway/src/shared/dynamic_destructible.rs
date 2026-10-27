//! Map-agnostic authoritative contract for dynamic map objects.
//!
//! A map fixture supplies object identity and physical policy.  This module
//! does not know a map name, native entity id, packet id, position, or client
//! callback.  It accepts only a server-produced contact receipt, applies one
//! bounded state transition, and exposes a deliberately small public delta for
//! observers.  Native publication and worker scene ACKs remain integration
//! responsibilities of `shared::server`.
use std::{io, sync::Arc};

pub const MAX_OBJECTS: usize = 2048;
pub const MAX_CONTACTS: usize = 16_384;
pub const MAX_DESTRUCTION_EVENTS: usize = MAX_OBJECTS;
pub const MAX_ACTORS: usize = super::model::MAX_ACTORS;
pub const MAX_MAP_ASSET_BYTES: usize = 128;
pub const MAX_REVISION_BYTES: usize = 128;
pub const MAX_MASS_KG: f32 = 1_000_000.;
pub const MAX_SPEED_MPS: f32 = 250.;
pub const MAX_DAMAGE: u32 = 1_000_000;
pub const POLICY_REVISION: &str = "server-dynamic-destructible-v1";

fn bad() -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, "dynamic destructible contract")
}

fn bounded_text(value: &str, max: usize) -> bool {
    !value.is_empty() && value.len() <= max && !value.chars().any(char::is_control)
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum ObjectKind {
    Fragile,
    Tree,
    Fence,
    /// Whole-instance structure only; module/rubble semantics are out of scope.
    Structure,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum ContactKind {
    Projectile,
    Hull,
    Wheel,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ContactMask(u8);

impl ContactMask {
    pub const PROJECTILE: Self = Self(1 << 0);
    pub const HULL: Self = Self(1 << 1);
    pub const WHEEL: Self = Self(1 << 2);
    pub const PROJECTILE_OR_HULL: Self = Self(Self::PROJECTILE.0 | Self::HULL.0);
    pub const ALL: Self = Self(Self::PROJECTILE.0 | Self::HULL.0 | Self::WHEEL.0);

    pub const fn allows(self, kind: ContactKind) -> bool {
        let bit = match kind {
            ContactKind::Projectile => Self::PROJECTILE.0,
            ContactKind::Hull => Self::HULL.0,
            ContactKind::Wheel => Self::WHEEL.0,
        };
        self.0 & bit != 0
    }

    fn valid(self) -> bool {
        self.0 != 0 && self.0 & !Self::ALL.0 == 0
    }
}

/// Source-bound fixture row. `mass_kg` is the object's pinned mass used by the
/// physics adapter; it is not a value that the client may supply or mutate.
#[derive(Clone, Debug, PartialEq)]
pub struct ObjectSpec {
    pub object_id: u32,
    pub material_kind: u16,
    pub mass_kg: f32,
    pub durability: u32,
    pub kind: ObjectKind,
    pub contact_mask: ContactMask,
}

impl ObjectSpec {
    fn validate(&self) -> io::Result<()> {
        if self.object_id == 0
            || !self.mass_kg.is_finite()
            || !(self.mass_kg > 0. && self.mass_kg <= MAX_MASS_KG)
            || self.durability == 0
            || self.durability > MAX_DAMAGE
            || !self.contact_mask.valid()
        {
            return Err(bad());
        }
        Ok(())
    }
}

/// A map can use this catalog shape for Karelia, Prohorovka, or a future map;
/// no map-specific branch is allowed in the domain transition below.
#[derive(Clone, Debug, PartialEq)]
pub struct Catalog {
    map_asset: String,
    revision: String,
    objects: Vec<ObjectSpec>,
}

impl Catalog {
    pub fn new(map_asset: impl Into<String>, revision: impl Into<String>, objects: Vec<ObjectSpec>) -> io::Result<Self> {
        let catalog = Self { map_asset: map_asset.into(), revision: revision.into(), objects };
        catalog.validate()?;
        Ok(catalog)
    }

    fn validate(&self) -> io::Result<()> {
        if !bounded_text(&self.map_asset, MAX_MAP_ASSET_BYTES)
            || !bounded_text(&self.revision, MAX_REVISION_BYTES)
            || self.objects.is_empty()
            || self.objects.len() > MAX_OBJECTS
            || self.objects.windows(2).any(|pair| pair[0].object_id >= pair[1].object_id)
        {
            return Err(bad());
        }
        for object in &self.objects {
            object.validate()?;
        }
        Ok(())
    }

    pub fn map_asset(&self) -> &str { &self.map_asset }
    pub fn revision(&self) -> &str { &self.revision }
    pub fn objects(&self) -> &[ObjectSpec] { &self.objects }

    fn index(&self, object_id: u32) -> io::Result<usize> {
        self.objects.binary_search_by_key(&object_id, |object| object.object_id)
            .map_err(|_| bad())
    }
}

/// This is intentionally a server-side type.  The transport layer must create
/// it only after its bounded worker/trace receipt has been checked.
#[derive(Clone, Debug, PartialEq)]
pub struct ServerContact {
    pub contact_id: u64,
    pub object_id: u32,
    pub material_kind: u16,
    pub kind: ContactKind,
    pub source_slot: usize,
    pub tick: u32,
    pub damage: u32,
    pub mass_kg: f32,
    pub closing_speed_mps: f32,
}

impl ServerContact {
    pub fn projectile(contact_id: u64, object_id: u32, material_kind: u16, source_slot: usize,
                      tick: u32, damage: u32) -> io::Result<Self> {
        let contact = Self { contact_id, object_id, material_kind, kind: ContactKind::Projectile,
            source_slot, tick, damage, mass_kg: 0., closing_speed_mps: 0. };
        contact.validate()?;
        Ok(contact)
    }

    pub fn vehicle(contact_id: u64, object_id: u32, material_kind: u16, kind: ContactKind,
                   source_slot: usize, tick: u32, damage: u32, mass_kg: f32,
                   closing_speed_mps: f32) -> io::Result<Self> {
        if !matches!(kind, ContactKind::Hull | ContactKind::Wheel) {
            return Err(bad());
        }
        let contact = Self { contact_id, object_id, material_kind, kind,
            source_slot, tick, damage, mass_kg, closing_speed_mps };
        contact.validate()?;
        Ok(contact)
    }

    fn validate(&self) -> io::Result<()> {
        if self.contact_id == 0
            || self.object_id == 0
            || self.source_slot >= MAX_ACTORS
            || self.tick == 0
            || self.damage > MAX_DAMAGE
            || !self.mass_kg.is_finite()
            || !self.closing_speed_mps.is_finite()
            || self.mass_kg < 0.
            || self.mass_kg > MAX_MASS_KG
            || self.closing_speed_mps < 0.
            || self.closing_speed_mps > MAX_SPEED_MPS
        {
            return Err(bad());
        }
        match self.kind {
            ContactKind::Projectile if self.mass_kg == 0. && self.closing_speed_mps == 0. => Ok(()),
            ContactKind::Hull | ContactKind::Wheel if self.mass_kg > 0. => Ok(()),
            _ => Err(bad()),
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DestructionEvent {
    pub contact_id: u64,
    pub object_id: u32,
    pub source_slot: usize,
    pub tick: u32,
    pub contact_kind: ContactKind,
    pub scene_before: u32,
    pub scene_after: u32,
    pub catalog_revision: String,
}

/// The only state sent to an observer.  It deliberately omits map coordinates,
/// object mass, remaining durability, and the actor that supplied the contact.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PublicDestruction {
    pub catalog_revision: String,
    pub object_id: u32,
    pub scene_version: u32,
    pub destroyed: bool,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PublicObjectState {
    pub catalog_revision: String,
    pub object_id: u32,
    pub scene_version: u32,
    pub destroyed: bool,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PersistedObject {
    pub object_id: u32,
    pub remaining_durability: u32,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Snapshot {
    pub catalog_revision: String,
    pub scene_version: u32,
    pub objects: Vec<PersistedObject>,
}

#[derive(Clone, Debug, PartialEq)]
pub enum ApplyResult {
    DuplicateContact,
    AlreadyDestroyed,
    NoDamage,
    Damaged { object_id: u32, remaining_durability: u32 },
    Destroyed(DestructionEvent),
}

#[derive(Clone, Debug, PartialEq)]
pub struct State {
    catalog: Arc<Catalog>,
    remaining: Vec<u32>,
    seen_contacts: Vec<u64>,
    events: Vec<DestructionEvent>,
    scene_version: u32,
}

impl State {
    pub fn new(catalog: Arc<Catalog>) -> Self {
        let remaining = catalog.objects.iter().map(|object| object.durability).collect();
        Self { catalog, remaining, seen_contacts: Vec::new(), events: Vec::new(), scene_version: 0 }
    }

    pub fn catalog(&self) -> &Catalog { &self.catalog }
    pub fn scene_version(&self) -> u32 { self.scene_version }
    pub fn is_destroyed(&self, object_id: u32) -> io::Result<bool> {
        let index = self.catalog.index(object_id)?;
        Ok(self.remaining[index] == 0)
    }
    pub fn remaining_durability(&self, object_id: u32) -> io::Result<u32> {
        let index = self.catalog.index(object_id)?;
        Ok(self.remaining[index])
    }

    /// Apply one server-admitted contact. Validation completes before any
    /// state is changed; a failed receipt cannot leave a half-committed object.
    pub fn apply_contact(&mut self, contact: ServerContact) -> io::Result<ApplyResult> {
        contact.validate()?;
        if self.seen_contacts.contains(&contact.contact_id) {
            return Ok(ApplyResult::DuplicateContact);
        }
        if self.seen_contacts.len() >= MAX_CONTACTS {
            return Err(bad());
        }
        let index = self.catalog.index(contact.object_id)?;
        let object = &self.catalog.objects[index];
        if object.material_kind != contact.material_kind || !object.contact_mask.allows(contact.kind) {
            return Err(bad());
        }
        let before = self.remaining[index];
        if before == 0 {
            self.seen_contacts.push(contact.contact_id);
            return Ok(ApplyResult::AlreadyDestroyed);
        }
        if contact.damage == 0 {
            self.seen_contacts.push(contact.contact_id);
            return Ok(ApplyResult::NoDamage);
        }
        let after = before.saturating_sub(contact.damage);
        let destroyed = after == 0;
        if destroyed && self.events.len() >= MAX_DESTRUCTION_EVENTS {
            return Err(bad());
        }

        self.seen_contacts.push(contact.contact_id);
        self.remaining[index] = after;
        if !destroyed {
            return Ok(ApplyResult::Damaged { object_id: contact.object_id, remaining_durability: after });
        }

        let scene_before = self.scene_version;
        self.scene_version += 1;
        let event = DestructionEvent {
            contact_id: contact.contact_id,
            object_id: contact.object_id,
            source_slot: contact.source_slot,
            tick: contact.tick,
            contact_kind: contact.kind,
            scene_before,
            scene_after: self.scene_version,
            catalog_revision: self.catalog.revision.clone(),
        };
        self.events.push(event.clone());
        Ok(ApplyResult::Destroyed(event))
    }

    pub fn public_events_since(&self, after_scene_version: u32, limit: usize) -> io::Result<Vec<PublicDestruction>> {
        if after_scene_version > self.scene_version || limit > MAX_DESTRUCTION_EVENTS {
            return Err(bad());
        }
        Ok(self.events.iter().skip(after_scene_version as usize).take(limit).map(|event| PublicDestruction {
            catalog_revision: event.catalog_revision.clone(), object_id: event.object_id,
            scene_version: event.scene_after, destroyed: true,
        }).collect())
    }

    pub fn public_snapshot(&self) -> Vec<PublicObjectState> {
        self.catalog.objects.iter().zip(&self.remaining).filter_map(|(object, remaining)|
            (*remaining == 0).then_some(PublicObjectState {
                catalog_revision: self.catalog.revision.clone(), object_id: object.object_id,
                scene_version: self.scene_version, destroyed: true,
            })).collect()
    }

    pub fn snapshot(&self) -> Snapshot {
        Snapshot { catalog_revision: self.catalog.revision.clone(), scene_version: self.scene_version,
            objects: self.catalog.objects.iter().zip(&self.remaining).map(|(object, remaining)|
                PersistedObject { object_id: object.object_id, remaining_durability: *remaining }).collect() }
    }

    pub fn restore(catalog: Arc<Catalog>, snapshot: Snapshot) -> io::Result<Self> {
        if snapshot.catalog_revision != catalog.revision
            || snapshot.objects.len() != catalog.objects.len()
            || snapshot.objects.windows(2).any(|pair| pair[0].object_id >= pair[1].object_id)
        {
            return Err(bad());
        }
        let mut remaining = Vec::with_capacity(catalog.objects.len());
        for (object, saved) in catalog.objects.iter().zip(snapshot.objects) {
            if object.object_id != saved.object_id || saved.remaining_durability > object.durability {
                return Err(bad());
            }
            remaining.push(saved.remaining_durability);
        }
        let destroyed = remaining.iter().filter(|value| **value == 0).count() as u32;
        if destroyed != snapshot.scene_version {
            return Err(bad());
        }
        Ok(Self { catalog, remaining, seen_contacts: Vec::new(), events: Vec::new(), scene_version: snapshot.scene_version })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn catalog(map: &str) -> Arc<Catalog> {
        Arc::new(Catalog::new(map, "fixture-r1", vec![
            ObjectSpec { object_id: 10, material_kind: 73, mass_kg: 120., durability: 20,
                kind: ObjectKind::Fragile, contact_mask: ContactMask::PROJECTILE_OR_HULL },
            ObjectSpec { object_id: 11, material_kind: 71, mass_kg: 800., durability: 30,
                kind: ObjectKind::Tree, contact_mask: ContactMask::HULL },
        ]).unwrap())
    }

    #[test]
    fn catalog_is_map_agnostic_but_bounded_and_ordered() {
        assert_ne!(catalog("karelia").map_asset(), catalog("05_prohorovka").map_asset());
        assert_eq!(catalog("karelia").objects(), catalog("05_prohorovka").objects());
        let invalid = vec![
            Catalog::new("", "r1", vec![ObjectSpec { object_id: 1, material_kind: 1, mass_kg: 1., durability: 1, kind: ObjectKind::Fence, contact_mask: ContactMask::ALL }]),
            Catalog::new("map", "r1", vec![ObjectSpec { object_id: 2, material_kind: 1, mass_kg: f32::NAN, durability: 1, kind: ObjectKind::Fence, contact_mask: ContactMask::ALL }]),
            Catalog::new("map", "r1", vec![ObjectSpec { object_id: 2, material_kind: 1, mass_kg: 1., durability: 1, kind: ObjectKind::Fence, contact_mask: ContactMask::ALL }, ObjectSpec { object_id: 1, material_kind: 1, mass_kg: 1., durability: 1, kind: ObjectKind::Fence, contact_mask: ContactMask::ALL }]),
        ];
        assert!(invalid.into_iter().all(|result| result.is_err()));
    }

    #[test]
    fn contact_admission_checks_material_and_contact_policy_before_mutation() {
        let mut state = State::new(catalog("karelia"));
        let before = state.clone();
        let wrong_material = ServerContact::projectile(1, 10, 71, 0, 1, 20).unwrap();
        assert!(state.apply_contact(wrong_material).is_err());
        let wrong_kind = ServerContact::vehicle(2, 11, 71, ContactKind::Wheel, 0, 2, 30, 800., 12.).unwrap();
        assert!(state.apply_contact(wrong_kind).is_err());
        assert_eq!(state, before);
    }

    #[test]
    fn destruction_is_authoritative_once_and_duplicate_contacts_are_idempotent() {
        let mut state = State::new(catalog("karelia"));
        let first = ServerContact::projectile(10, 10, 73, 0, 10, 7).unwrap();
        assert_eq!(state.apply_contact(first.clone()).unwrap(), ApplyResult::Damaged { object_id: 10, remaining_durability: 13 });
        assert_eq!(state.apply_contact(first).unwrap(), ApplyResult::DuplicateContact);
        let destroy = ServerContact::projectile(11, 10, 73, 0, 11, 13).unwrap();
        let event = match state.apply_contact(destroy.clone()).unwrap() { ApplyResult::Destroyed(event) => event, other => panic!("unexpected result: {other:?}") };
        assert_eq!((event.scene_before, event.scene_after, state.scene_version()), (0, 1, 1));
        assert_eq!(state.apply_contact(destroy).unwrap(), ApplyResult::DuplicateContact);
        let after_destroy = ServerContact::projectile(12, 10, 73, 0, 12, 1).unwrap();
        assert_eq!(state.apply_contact(after_destroy).unwrap(), ApplyResult::AlreadyDestroyed);
        assert_eq!(state.scene_version(), 1);
    }

    #[test]
    fn public_delta_and_snapshot_omit_hidden_object_facts_and_survive_reload() {
        let mut state = State::new(catalog("05_prohorovka"));
        let contact = ServerContact::vehicle(20, 11, 71, ContactKind::Hull, 1, 20, 30, 800., 15.).unwrap();
        let _ = state.apply_contact(contact).unwrap();
        let public = state.public_events_since(0, 10).unwrap();
        assert_eq!(public, vec![PublicDestruction { catalog_revision: "fixture-r1".into(), object_id: 11, scene_version: 1, destroyed: true }]);
        assert!(!format!("{:?}", public).contains("mass_kg"));
        let restored = State::restore(catalog("05_prohorovka"), state.snapshot()).unwrap();
        assert_eq!(restored.public_snapshot(), state.public_snapshot());
        assert!(State::restore(catalog("05_prohorovka"), Snapshot { catalog_revision: "other".into(), ..state.snapshot() }).is_err());
    }

    #[test]
    fn malformed_server_contact_is_rejected_without_state_change() {
        let mut state = State::new(catalog("karelia"));
        let before = state.clone();
        let malformed = ServerContact { contact_id: 30, object_id: 10, material_kind: 73, kind: ContactKind::Projectile,
            source_slot: 0, tick: 30, damage: 1, mass_kg: 1., closing_speed_mps: 0. };
        assert!(state.apply_contact(malformed).is_err());
        assert_eq!(state, before);
        assert!(state.public_events_since(1, 0).is_err());
    }
}
