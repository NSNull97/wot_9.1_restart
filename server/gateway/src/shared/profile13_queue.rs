//! Pure native queue staging; persistence runs only after Session::receive.
use super::*;
use crate::battle091::profile13::{self, NativeCommand};

impl Session {
    pub(super) fn profile13_account_payload(&mut self,payload:&[u8],events:&mut Vec<String>)->io::Result<()> {
        if payload.len()>512 {return Err(bad());}
        let mut at=0; let mut records=Vec::new(); let mut queue=false; let mut results=false;
        while at<payload.len() {
            if records.len()>=16 || payload.len()-at<3 {return Err(bad());}
            let length=u16::from_le_bytes([payload[at+1],payload[at+2]]) as usize;
            let packet=payload.get(at..at+3+length).ok_or_else(||bad())?;
            queue|=profile13::native_command(packet)?.is_some(); records.push(packet);at+=packet.len();
            results|=packet.len()>=7 && packet[..3]==[0x8e,20,0]
                && [1500i16,1501i16].contains(&i16::from_le_bytes([packet[5],packet[6]]));
        }
        if !queue && !results {return self.receive_account(payload,events);}
        for packet in records {
            if self.battle_results.stage(packet)? {
                if !self.active || !self.account_ready || self.arena_base || self.sync_mask!=7
                    || !self.shared.as_ref().is_some_and(|c|c.profile13_account()) {return Err(bad());}
                events.push(format!("P08C_RESULTS_REQUEST_STAGED session={} writer_started=false",self.id));
                continue;
            }
            let Some(command)=profile13::native_command(packet)? else {
                self.receive_account(packet,events)?;continue;
            };
            if !self.active || !self.account_ready || self.arena_base || self.sync_mask!=7
                || self.outbox.len()>125 {return Err(bad());}
            let c=self.shared.as_mut().ok_or_else(||bad())?;
            if c.phase!=Phase::Account {return Err(bad());}
            let state=c.profile13.as_mut().ok_or_else(||bad())?;
            match command {
                NativeCommand::Join{native_inventory_id,..} => {
                    let selected=native_inventory_id as u32;
                    if c.join_requested && (state.selection==Some(selected)
                        || state.reservation.as_ref().is_some_and(|r|r.native_inventory_id==selected)) {
                        events.push(format!("P08B_QUEUE_DUPLICATE session={} native_inventory_id={selected} writer_started=false",self.id));
                        continue;
                    }
                    if !self.ammo_service.as_ref().is_some_and(super::super::ammo_session::State::idle)
                        || state.in_flight || state.reservation.is_some() || state.pending_return.is_some()
                        || state.selection.is_some() {
                        c.join_requested=false;state.selection=None;
                        self.outbox.push_back(profile13::enqueue_failure("VEHICLE_RESERVED")?);
                        events.push(format!("P08B_QUEUE_BUSY session={} writer_started=false",self.id));continue;
                    }
                    state.selection=Some(selected);c.join_requested=true;
                    // onEnqueued is emitted only after the writer commits.
                },
                NativeCommand::Cancel => {
                    state.selection=None;c.join_requested=false;
                    if c.queue_announced && state.reservation.is_none() && !state.in_flight {
                        self.outbox.push_back(drive::queue_callback(false));c.queue_announced=false;
                    }
                },
                NativeCommand::QueueInfo => {
                    if c.queue_announced {self.outbox.push_back(drive::own_queue_info());}
                },
            }
            events.push(format!("P08B_QUEUE_PENDING session={} command={command:?} writer_started=false native_enqueued={}",self.id,c.queue_announced));
        }
        Ok(())
    }
}
