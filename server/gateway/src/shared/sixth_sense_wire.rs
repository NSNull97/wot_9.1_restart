//! Candidate #717 Avatar.updateVehicleMiscStatus publication.
//!
//! The callback signature and status code are source-verified; method id 0x47
//! is only an inferred stable-sort candidate until an owner native capture.
//! UI/audio/control therefore remain NOT_RUN even when this server-side event
//! is staged.
use super::{model, wire, Phase, Session, World};
use std::io;

const METHOD_ID_CANDIDATE: u8 = 0x47;
const OBSERVED_BY_ENEMY: u8 = 1;

fn body(slot: usize) -> io::Result<Vec<u8>> {
    let mut out=vec![0x13, METHOD_ID_CANDIDATE];
    out.extend(wire::vehicle_id(slot)?.to_le_bytes());
    out.push(OBSERVED_BY_ENEMY);
    out.extend(0i32.to_le_bytes());
    out.extend(0f32.to_le_bytes());
    Ok(out)
}

pub(super) fn publish(session: &mut Session, world: &World) -> io::Result<()> {
    let c=session.shared.as_ref().ok_or_else(model::bad)?;
    if !c.spotting_enabled || c.phase != Phase::Driving || !world.original_spotting_enabled() { return Ok(()); }
    let generation=world.sixth_sense_generation(c.slot)?;
    if generation < c.sixth_sense_sent { return Err(model::bad()); }
    if generation == c.sixth_sense_sent { return Ok(()); }
    if !world.sixth_sense_eligible(c.slot)? {
        session.shared.as_mut().ok_or_else(model::bad)?.sixth_sense_sent=generation;
        return Ok(());
    }
    if !c.correction || !c.binding.is_some_and(|(_,ack)|ack) || !c.visible()[c.slot]
        || session.tx.len() >= 8 || !session.outbox.is_empty() || !c.private_pending.is_empty() { return Ok(()); }
    let bytes=body(c.slot)?;
    session.tx.enqueue_body(&bytes)?;
    session.shared.as_mut().ok_or_else(model::bad)?.sixth_sense_sent=generation;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn p07b_candidate_misc_status_has_the_source_signature_and_bounded_slot() {
        for slot in 0..model::MAX_ACTORS {
            let bytes=body(slot).unwrap();
            assert_eq!(bytes.len(),15);
            assert_eq!(&bytes[..2],&[0x13,METHOD_ID_CANDIDATE]);
            assert_eq!(&bytes[2..6],&wire::vehicle_id(slot).unwrap().to_le_bytes());
            assert_eq!(bytes[6],OBSERVED_BY_ENEMY);
            assert_eq!(&bytes[7..],&[0;8]);
        }
        assert!(body(model::MAX_ACTORS).is_err());
    }
}
