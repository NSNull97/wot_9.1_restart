//! Bounded native training-room foundation. Numeric protocol IDs are kept in
//! codecs. Auth/ownership/writer receipts must come from the real Session adapter.
//! These modules do not activate a room route until an explicit server opt-in.
pub mod domain;
pub mod wire;
pub mod aliases;
pub mod adapter;
pub mod current_room;
#[path="ingress.rs"]
pub mod ingress;
#[cfg(test)]mod transport_tests;
#[cfg(test)]mod integration_tests;
