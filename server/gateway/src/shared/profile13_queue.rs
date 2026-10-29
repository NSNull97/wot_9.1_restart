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
            let own=if matches!(command,NativeCommand::QueueInfo) {self.queue_vehicle_class()?} else {None};
            let c=self.shared.as_mut().ok_or_else(||bad())?;
            if c.phase!=Phase::Account {return Err(bad());}
            let state=c.profile13.as_mut().ok_or_else(||bad())?;
            match command {
                NativeCommand::Join{native_inventory_id,..} => {
                    let selected=native_inventory_id as u32;
                    if c.join_requested && (state.selection==Some(selected)
                        || state.reservation_native_inventory_id()==Some(selected)) {
                        events.push(format!("P08B_QUEUE_DUPLICATE session={} native_inventory_id={selected} writer_started=false",self.id));
                        continue;
                    }
                    if !self.ammo_service.as_ref().is_some_and(super::super::ammo_session::State::idle)
                        || state.in_flight || state.has_reservation() || state.has_pending_return()
                        || state.selection.is_some() {
                        self.outbox.push_back(profile13::enqueue_failure("VEHICLE_RESERVED")?);
                        events.push(format!("P08B_QUEUE_BUSY session={} writer_started=false",self.id));continue;
                    }
                    if !state.can_admit_command() {
                        self.outbox.push_back(profile13::enqueue_failure("BATTLE_BUSY")?);
                        events.push(format!("P08B_SESSION_COMMAND_LIMIT session={} reconnect_required=true writer_started=false",self.id));continue;
                    }
                    state.selection=Some(selected);c.join_requested=true;
                    // onEnqueued is emitted only after the writer commits.
                },
                NativeCommand::Cancel => {
                    state.selection=None;c.join_requested=false;
                    if c.queue_announced && !state.has_reservation() && !state.has_pending_return() && !state.in_flight {
                        self.outbox.push_back(drive::queue_callback(false));c.queue_announced=false;
                    }
                },
                NativeCommand::QueueInfo => {
                    let reply=state.queue_info_reply(own);
                    if c.queue_announced {self.outbox.push_back(reply);}
                },
            }
            events.push(format!("P08B_QUEUE_PENDING session={} command={command:?} writer_started=false native_enqueued={}",self.id,c.queue_announced));
        }
        Ok(())
    }
    /// The vehicle this player queues with: the reserved kind, else the selected
    /// native row (p04m pool label, or the built-in MS-1 / IS-7 rows).
    pub(super) fn queue_vehicle_kind(&self)->Option<super::vehicle_profile::VehicleKind> {
        let state=self.shared.as_ref()?.profile13.as_ref()?;
        if let Some(kind)=state.reservation_kind() {return Some(kind);}
        let native=state.selection?;
        self.hangar.as_ref().and_then(|f|f.p04m_binding()).and_then(|b|b.kind_label(native))
            .or(match native {1=>Some("ms1"),2=>Some("is7"),_=>None})
            .and_then(super::vehicle_profile::VehicleKind::from_owned_label)
    }
    /// Client `VEHICLE_CLASSES` index of that vehicle (`battle_profiles.v1.json`).
    fn queue_vehicle_class(&self)->io::Result<Option<u8>> {
        Ok(match self.queue_vehicle_kind() {Some(kind)=>kind.queue_profile()?.map(|(_,class)|class),None=>None})
    }
}
