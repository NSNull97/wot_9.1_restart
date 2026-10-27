//! Pure bounded bookkeeping for native AoI hooks, not an AoI encoder.
//!
//! Root must stage native enqueue and mark_queued in the same Session clone,
//! and pass only transport-validated ACKs. Retries reuse transport bytes/seq;
//! they must never enqueue another enter. Creation ACKs remain outside this
//! book and must belong to the current announcement_sequence, not an old cycle.
use std::io;

pub(crate) const MAX_ENTRIES: usize = super::model::MAX_ACTORS;
pub(crate) const MAX_SELECTIVE_ACKS: usize = 256;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub(crate) enum Entry {
    #[default] Hidden,
    Announced { enter_seq: u32 },
    Leaving { leave_seq: u32 },
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum Kind { Enter, Leave }

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct Action {
    pub slot: usize,
    pub kind: Kind,
    revision: u64,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct Book {
    own: usize,
    active: [bool; MAX_ENTRIES],
    desired: [bool; MAX_ENTRIES],
    entries: [Entry; MAX_ENTRIES],
    after_leave: [Option<u32>; MAX_ENTRIES],
    revision: u64,
    last_queued: Option<u32>,
}

fn invalid(message: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData,message)
}

impl Book {
    pub(crate) fn new(own: usize) -> io::Result<Self> {
        if own >= MAX_ENTRIES {return Err(invalid("interest own slot outside bound"));}
        Ok(Self {own,active:[false;MAX_ENTRIES],desired:[false;MAX_ENTRIES],
            entries:[Entry::Hidden;MAX_ENTRIES],after_leave:[None;MAX_ENTRIES],revision:0,last_queued:None})
    }

    /// One coherent desired snapshot. The owner must remain active/interested.
    /// A failed update leaves all transitions and pending barriers unchanged.
    pub(crate) fn set_desired(&mut self, active: [bool;MAX_ENTRIES], desired: [bool;MAX_ENTRIES]) -> io::Result<()> {
        if !active[self.own] || !desired[self.own] || desired.iter().zip(active).any(|(want,present)|*want&&!present) {
            return Err(invalid("interest desired must be active and retain own slot"));
        }
        if self.active!=active || self.desired!=desired {
            let revision=self.revision.checked_add(1).ok_or_else(||invalid("interest desired revision exhausted"))?;
            self.active=active;self.desired=desired;self.revision=revision;
        }
        Ok(())
    }

    pub(crate) fn entry(&self, slot: usize) -> Option<Entry> {self.entries.get(slot).copied()}

    /// Bounded proposals only. No phase changes until enqueue succeeds.
    pub(crate) fn transitions(&self) -> Vec<Action> {
        let mut actions=Vec::with_capacity(MAX_ENTRIES);
        for slot in 0..MAX_ENTRIES {
            let kind=match (self.entries[slot],self.desired[slot]) {
                (Entry::Hidden,true)=>Some(Kind::Enter),
                (Entry::Announced{..},false)=>Some(Kind::Leave),
                _=>None,
            };
            if let Some(kind)=kind {actions.push(Action{slot,kind,revision:self.revision});}
        }
        actions
    }

    /// Call only with the actual reliable sequence returned by native enqueue.
    /// Several actions in one native compound may share the same sequence.
    /// An exact repeat mark is harmless; a new enter for an announced/leaving
    /// entity is rejected, preventing native enter-count stacking.
    pub(crate) fn mark_queued(&mut self, action: Action, sequence: u32) -> io::Result<()> {
        if action.slot>=MAX_ENTRIES || action.revision!=self.revision {
            return Err(invalid("interest stale action/slot/reliable sequence"));
        }
        let slot=action.slot;
        if matches!((action.kind,self.entries[slot]),
            (Kind::Enter,Entry::Announced{enter_seq}) if enter_seq==sequence&&self.desired[slot])
            || matches!((action.kind,self.entries[slot]),
                (Kind::Leave,Entry::Leaving{leave_seq}) if leave_seq==sequence&&!self.desired[slot]) {
            return Ok(());
        }
        if self.last_queued.is_some_and(|last|sequence<last) {return Err(invalid("interest reliable queue sequence regressed"));}
        let next=match (action.kind,self.entries[slot],self.desired[slot]) {
            (Kind::Enter,Entry::Hidden,true) if self.active[slot]&&self.after_leave[slot].is_none_or(|after|sequence>after)=>Entry::Announced{enter_seq:sequence},
            (Kind::Leave,Entry::Announced{enter_seq},false) if slot!=self.own&&sequence>enter_seq=>Entry::Leaving{leave_seq:sequence},
            _=>return Err(invalid("interest queued action no longer matches desired phase")),
        };
        self.entries[slot]=next;self.last_queued=Some(sequence);Ok(())
    }

    pub(crate) fn announcement_sequence(&self, slot: usize) -> Option<u32> {
        match self.entry(slot) {Some(Entry::Announced{enter_seq})=>Some(enter_seq),_=>None}
    }

    fn interested_announced(&self, slot: usize) -> bool {
        slot<MAX_ENTRIES&&self.active[slot]&&self.desired[slot]&&matches!(self.entries[slot],Entry::Announced{..})
    }

    /// Enter must already be queued before create, but no extra enter-ACK wait
    /// is imposed: the original request may precede a separate ACK datagram.
    pub(crate) fn request_allowed(&self, slot: usize) -> bool {
        self.interested_announced(slot)
    }

    /// creation_acked must refer to the current announcement_sequence. Root
    /// clears the old creation state when queuing leave/new enter.
    pub(crate) fn publish_allowed(&self, slot: usize, creation_acked: bool) -> bool {
        creation_acked&&self.interested_announced(slot)
    }

    /// Matches existing shared::Client ACK semantics: cumulative > sequence,
    /// or exact membership in selective ACKs. Equality alone does not ACK.
    /// Only leave ACK clears a phase; a desired=true flap still waits for it.
    /// Returned slots let root clear external creation/publication state.
    pub(crate) fn acknowledge(&mut self, cumulative: u32, selective: &[u32]) -> io::Result<Vec<usize>> {
        if selective.len()>MAX_SELECTIVE_ACKS {
            return Err(invalid("interest selective ACK vector bound"));
        }
        let mut cleared=Vec::with_capacity(MAX_ENTRIES);
        for slot in 0..MAX_ENTRIES {
            if let Entry::Leaving{leave_seq}=self.entries[slot] {
                if cumulative>leave_seq || selective.contains(&leave_seq) {
                    self.entries[slot]=Entry::Hidden;self.after_leave[slot]=Some(leave_seq);cleared.push(slot);
                }
            }
        }
        Ok(cleared)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn mask(slots:&[usize])->[bool;MAX_ENTRIES] {std::array::from_fn(|slot|slots.contains(&slot))}
    fn started()->Book {
        let mut book=Book::new(0).unwrap();book.set_desired(mask(&[0,1]),mask(&[0,1])).unwrap();
        for action in book.transitions(){book.mark_queued(action,10).unwrap();}book
    }
    #[test] fn native_first_sequence_zero_and_selective_ack_zero_are_valid() {
        let mut book=Book::new(0).unwrap();book.set_desired(mask(&[0,1]),mask(&[0,1])).unwrap();
        for action in book.transitions() {book.mark_queued(action,0).unwrap();}
        assert_eq!(book.announcement_sequence(0),Some(0));assert_eq!(book.announcement_sequence(1),Some(0));
        assert!(book.request_allowed(1));assert!(!book.publish_allowed(1,false));
        let before=book.clone();assert!(book.acknowledge(0,&[0]).unwrap().is_empty());assert_eq!(book,before);
        book.set_desired(mask(&[0,1]),mask(&[0])).unwrap();let leave=book.transitions()[0];book.mark_queued(leave,1).unwrap();
        let before=book.clone();assert!(book.acknowledge(1,&[0]).unwrap().is_empty());assert_eq!(book,before);
        assert_eq!(book.acknowledge(1,&[1]).unwrap(),vec![1]);book.set_desired(mask(&[0,1]),mask(&[0,1])).unwrap();
        let enter=book.transitions()[0];let before=book.clone();assert!(book.mark_queued(enter,1).is_err());assert_eq!(book,before);
        book.mark_queued(enter,2).unwrap();assert_eq!(book.announcement_sequence(1),Some(2));
    }
    #[test] fn balanced_hide_reenter_cycles_use_real_leave_ack_barriers() {
        let mut book=started();assert!(book.request_allowed(1));
        assert!(!book.publish_allowed(1,false));assert!(book.publish_allowed(1,true));
        for (leave_seq,enter_seq) in [(11,12),(13,14)] {
            book.set_desired(mask(&[0,1]),mask(&[0])).unwrap();
            assert!(!book.request_allowed(1));assert!(!book.publish_allowed(1,true));
            let leave=book.transitions();assert_eq!(leave.len(),1);assert_eq!(leave[0].kind,Kind::Leave);
            book.mark_queued(leave[0],leave_seq).unwrap();
            book.set_desired(mask(&[0,1]),mask(&[0,1])).unwrap();assert!(book.transitions().is_empty());
            assert!(!book.publish_allowed(1,true));assert!(book.acknowledge(leave_seq,&[]).unwrap().is_empty());
            assert_eq!(book.acknowledge(leave_seq,&[leave_seq]).unwrap(),vec![1]);
            assert_eq!(book.entry(1),Some(Entry::Hidden));assert!(!book.request_allowed(1));
            let enter=book.transitions();assert_eq!(enter.len(),1);book.mark_queued(enter[0],enter_seq).unwrap();
            assert_eq!(book.announcement_sequence(1),Some(enter_seq));assert!(!book.publish_allowed(1,false));
        }
    }
    #[test] fn rapid_los_flaps_invalidate_unqueued_plans_without_stacking_native_enters() {
        let mut book=started();book.set_desired(mask(&[0,1]),mask(&[0])).unwrap();let stale=book.transitions()[0];
        book.set_desired(mask(&[0,1]),mask(&[0,1])).unwrap();let before=book.clone();
        assert!(book.mark_queued(stale,11).is_err());assert_eq!(book,before);assert!(book.transitions().is_empty());
        book.set_desired(mask(&[0,1]),mask(&[0])).unwrap();let leave=book.transitions()[0];book.mark_queued(leave,11).unwrap();
        for _ in 0..3 {
            book.set_desired(mask(&[0,1]),mask(&[0,1])).unwrap();assert!(book.transitions().is_empty());
            book.set_desired(mask(&[0,1]),mask(&[0])).unwrap();assert!(book.transitions().is_empty());
        }
        book.set_desired(mask(&[0,1]),mask(&[0,1])).unwrap();book.acknowledge(12,&[]).unwrap();
        let enter=book.transitions();assert_eq!(enter.len(),1);assert_eq!(enter[0].kind,Kind::Enter);
        book.mark_queued(enter[0],12).unwrap();assert!(book.transitions().is_empty());
    }
    #[test] fn retries_are_idempotent_and_old_actions_sequences_or_unrelated_acks_cannot_reenter() {
        let mut book=Book::new(0).unwrap();book.set_desired(mask(&[0,1]),mask(&[0,1])).unwrap();
        assert!(!book.request_allowed(1));
        let actions=book.transitions();for &action in &actions {book.mark_queued(action,10).unwrap();}
        assert!(book.request_allowed(1));assert!(!book.publish_allowed(1,false));
        let before=book.clone();book.mark_queued(actions[1],10).unwrap();assert_eq!(book,before);
        assert!(book.mark_queued(actions[1],11).is_err());assert_eq!(book,before);
        book.set_desired(mask(&[0,1]),mask(&[0])).unwrap();let leave=book.transitions()[0];book.mark_queued(leave,11).unwrap();
        let before=book.clone();book.mark_queued(leave,11).unwrap();assert_eq!(book,before);
        assert!(book.mark_queued(actions[1],10).is_err());assert_eq!(book,before);
        assert!(book.acknowledge(11,&[12]).unwrap().is_empty());assert_eq!(book,before);
        book.acknowledge(12,&[]).unwrap();book.set_desired(mask(&[0,1]),mask(&[0,1])).unwrap();let enter=book.transitions()[0];
        let before=book.clone();assert!(book.mark_queued(enter,11).is_err());assert_eq!(book,before);
        book.mark_queued(enter,12).unwrap();let before=book.clone();assert!(book.mark_queued(leave,11).is_err());assert_eq!(book,before);
    }
    #[test] fn invalid_owner_masks_and_ack_vectors_fail_without_mutation() {
        assert!(Book::new(MAX_ENTRIES).is_err());let mut book=started();let before=book.clone();
        for (active,desired) in [(mask(&[0,1]),mask(&[1])),(mask(&[1]),mask(&[0,1])),(mask(&[0]),mask(&[0,1]))] {
            assert!(book.set_desired(active,desired).is_err());assert_eq!(book,before);
        }
        assert!(!book.request_allowed(usize::MAX));assert!(!book.publish_allowed(MAX_ENTRIES,true));assert_eq!(book.entry(MAX_ENTRIES),None);
        book.set_desired(mask(&[0,1]),mask(&[0])).unwrap();let leave=book.transitions()[0];book.mark_queued(leave,11).unwrap();let before=book.clone();
        assert!(book.acknowledge(11,&[0]).unwrap().is_empty());assert_eq!(book,before);
        assert!(book.acknowledge(12,&vec![11;MAX_SELECTIVE_ACKS+1]).is_err());assert_eq!(book,before);
    }
    #[test] fn six_books_keep_six_slots_bounded_and_preserve_each_owner_through_bulk_reentry() {
        let all=mask(&[0,1,2,3,4,5]);
        for own in 0..6 {
            let mut book=Book::new(own).unwrap();book.set_desired(all,all).unwrap();let enters=book.transitions();assert_eq!(enters.len(),6);
            for action in enters {book.mark_queued(action,20).unwrap();}
            for slot in 0..6 {assert!(book.request_allowed(slot));}
            book.set_desired(all,mask(&[own])).unwrap();let leaves=book.transitions();assert_eq!(leaves.len(),5);
            assert!(leaves.iter().all(|a|a.slot!=own));for action in leaves {book.mark_queued(action,21).unwrap();}
            book.set_desired(all,all).unwrap();assert!(book.transitions().is_empty());
            assert_eq!(book.acknowledge(22,&[]).unwrap().len(),5);let reenter=book.transitions();assert_eq!(reenter.len(),5);
            for action in reenter {book.mark_queued(action,22).unwrap();assert!(book.request_allowed(action.slot));assert!(!book.publish_allowed(action.slot,false));}
            assert_eq!(book.announcement_sequence(own),Some(20));assert!(book.transitions().is_empty());
        }
    }
}
