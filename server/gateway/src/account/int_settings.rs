//! UI-01: native IntUserSettings (#717 CMD 1600/1601, keys 0..56 of
//! IntSettingsRequester.SETTINGS). They are plain client preferences kept by
//! the server: stored apart from the revisioned profile, read at login, merged
//! into the outgoing Account state and acknowledged by an Account.update diff.
//! #717 IntUserSettings.addIntSettings keeps no local copy, so only that diff
//! (`intUserSettings` -> g_clientUpdateManager -> _SettingsCache._onResync)
//! shows the client what it just saved.
use std::{collections::BTreeMap,io};

pub const ADD:i16=1600;
pub const DELETE:i16=1601;
pub const MAX_ARGUMENTS:usize=128;
const MAX_KEY:i32=56;
const MAX_CHANGES:usize=64;
/// Client migration version key. Never written for the client: with no
/// version #717 ServerSettingsManager._updateToVersion runs
/// _initializeDefaultSettings and stores the defaults and version 11 itself.
const VERSION:i32=0;
/// Tail of every published Account state, tools/hangar_state.py `{0: 11}`.
const STATE_TAIL:&[u8]=b"U\x0fintUserSettings}(K\x00K\x0buu.";
const FIELD:&[u8]=b"U\x0fintUserSettings}(";
/// One Account.update stays inside ammo_service MAX_DELTA_BYTES.
const PAIRS_PER_UPDATE:usize=18;

pub type Map=BTreeMap<i32,i32>;

fn invalid(message:&'static str)->io::Error {io::Error::new(io::ErrorKind::InvalidData,message)}

#[derive(Debug,Clone,PartialEq,Eq,Default)]
pub struct Change {pub set:Vec<(i32,i32)>,pub delete:Vec<i32>}

/// `id` 0: settings changed in battle. The Avatar sends them without a
/// callback and the Account comes back with them, so nothing answers.
#[derive(Debug,Clone,PartialEq,Eq)]
pub struct Request {pub id:i16,pub change:Change}

impl Change {
    /// None for anything outside the closed native shape: refused, not stored.
    pub fn decode(command:i16,values:&[i32])->Option<Self> {
        let known=|key:i32|(0..=MAX_KEY).contains(&key);
        let change=match command {
            ADD if values.len()%2==0=>Self{set:values.chunks_exact(2).map(|pair|(pair[0],pair[1])).collect(),delete:Vec::new()},
            DELETE=>Self{set:Vec::new(),delete:values.to_vec()},
            _=>return None,
        };
        if change.is_empty() || change.len()>MAX_CHANGES || !change.set.iter().all(|pair|known(pair.0))
            || !change.delete.iter().all(|key|known(*key)&&*key!=VERSION) {return None;}
        let mut keys=change.keys();keys.sort_unstable();keys.dedup();
        (keys.len()==change.len()).then_some(change)
    }
    /// The Avatar record `[id:i16][command:i16][count:u32][i32...]` of doCmdIntArr.
    pub fn from_avatar(args:&[u8])->Option<Self> {
        let command=i16::from_le_bytes(args.get(2..4)?.try_into().ok()?);
        let count=u32::from_le_bytes(args.get(4..8)?.try_into().ok()?) as usize;
        if count>MAX_ARGUMENTS || args.len()!=8+count*4 {return None;}
        let values=args[8..].chunks_exact(4).map(|v|i32::from_le_bytes([v[0],v[1],v[2],v[3]])).collect::<Vec<_>>();
        Self::decode(command,&values)
    }
    pub fn is_empty(&self)->bool {self.set.is_empty()&&self.delete.is_empty()}
    fn len(&self)->usize {self.set.len()+self.delete.len()}
    fn keys(&self)->Vec<i32> {self.set.iter().map(|pair|pair.0).chain(self.delete.iter().copied()).collect()}
    pub fn apply(&self,map:&mut Map) {
        for &(key,value) in &self.set {map.insert(key,value);}
        for key in &self.delete {map.remove(key);}
    }
    /// A later change wins per key; never more than the keys that exist.
    pub fn merge(&mut self,later:&Self) {
        let keys=later.keys();
        self.set.retain(|pair|!keys.contains(&pair.0));self.delete.retain(|key|!keys.contains(key));
        self.set.extend(&later.set);self.delete.extend(&later.delete);
    }
    pub fn service_request(&self,account_id:&str,database_id:i32)->io::Result<Vec<u8>> {
        let set=self.set.iter().map(|pair|[pair.0,pair.1]).collect::<Vec<_>>();
        serde_json::to_vec(&serde_json::json!({"account_id":account_id,"native_database_id":database_id,"set":set,"delete":self.delete}))
            .map_err(|_|invalid("int settings request encoding"))
    }
}

/// The stored map of `account_id` from the Domain reply.
pub fn parse_reply(bytes:&[u8],account_id:&str)->io::Result<Map> {
    let value:serde_json::Value=serde_json::from_slice(bytes).map_err(|_|invalid("int settings reply JSON"))?;
    let object=value.as_object().filter(|o|o.len()==2).ok_or_else(||invalid("int settings reply fields"))?;
    if object.get("account_id").and_then(|v|v.as_str())!=Some(account_id) {return Err(invalid("int settings reply account"));}
    let rows=object.get("settings").and_then(|v|v.as_array()).filter(|r|r.len()<=MAX_KEY as usize+1).ok_or_else(||invalid("int settings reply rows"))?;
    let mut map=Map::new();
    for row in rows {
        let pair=row.as_array().filter(|p|p.len()==2).ok_or_else(||invalid("int settings reply row"))?;
        let number=|v:&serde_json::Value|v.as_i64().and_then(|n|i32::try_from(n).ok());
        let (Some(key),Some(value))=(number(&pair[0]),number(&pair[1])) else {return Err(invalid("int settings reply number"))};
        if !(0..=MAX_KEY).contains(&key) || map.insert(key,value).is_some() {return Err(invalid("int settings reply key"));}
    }
    Ok(map)
}

fn int(out:&mut Vec<u8>,value:i32) {out.push(b'J');out.extend(value.to_le_bytes());}

/// The published state with exactly this account's stored settings in place
/// of the fixture default `{0: 11}`. An account with nothing stored gets `{}`:
/// version 11 without sections made the client skip its defaults, and the
/// first saved item of a section zeroed every other item of it.
pub fn state_with(state:&[u8],map:&Map)->io::Result<Vec<u8>> {
    let head=state.strip_suffix(STATE_TAIL).ok_or_else(||invalid("Account state without the published settings tail"))?;
    let mut out=head.to_vec();out.extend(FIELD);
    for (&key,&value) in map {int(&mut out,key);int(&mut out,value);}
    out.extend(b"uu.");Ok(out)
}

/// Account.update diffs from `wire`: one per PAIRS_PER_UPDATE entries, each
/// advancing the connection-local cursor by one. None deletes (synchronize).
pub fn deltas(wire:i64,change:&Change)->io::Result<Vec<Vec<u8>>> {
    let entries=change.set.iter().map(|&(key,value)|(key,Some(value))).chain(change.delete.iter().map(|&key|(key,None))).collect::<Vec<_>>();
    let mut out=Vec::new();
    for (index,chunk) in entries.chunks(PAIRS_PER_UPDATE).enumerate() {
        let previous=wire.checked_add(index as i64).ok_or_else(||invalid("int settings cursor"))?;
        let cursor=|value:i64|i32::try_from(value).map_err(|_|invalid("int settings cursor"));
        let mut delta=b"\x80\x02}(U\x07prevRev".to_vec();int(&mut delta,cursor(previous)?);
        delta.extend(b"U\x03rev");int(&mut delta,cursor(previous+1)?);delta.extend(FIELD);
        for (key,value) in chunk {int(&mut delta,*key);match value {Some(value)=>int(&mut delta,*value),None=>delta.push(b'N')}}
        delta.extend(b"uu.");out.push(delta);
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    const ACCOUNT:&str="00000000-0000-0000-0000-000000000001";
    fn state()->Vec<u8> {let mut s=b"\x80\x02}(U\x03revK\x01".to_vec();s.extend(STATE_TAIL);s}
    #[test] fn native_arguments_are_closed() {
        assert_eq!(Change::decode(ADD,&[43,5,0,11]),Some(Change{set:vec![(43,5),(0,11)],delete:vec![]}));
        assert_eq!(Change::decode(DELETE,&[43]),Some(Change{set:vec![],delete:vec![43]}));
        for (command,values) in [(ADD,vec![43]),(ADD,vec![]),(ADD,vec![57,1]),(ADD,vec![-1,1]),(ADD,vec![1,1,1,2]),(DELETE,vec![0]),(DELETE,vec![57]),(DELETE,vec![]),(DELETE,vec![1,1]),(102,vec![1,1])] {
            assert_eq!(Change::decode(command,&values),None,"{command} {values:?}");
        }
    }
    #[test] fn avatar_record_needs_its_exact_length() {
        let mut args=227i16.to_le_bytes().to_vec();args.extend(ADD.to_le_bytes());args.extend(2u32.to_le_bytes());
        for value in [43,7] {args.extend((value as i32).to_le_bytes());}
        assert_eq!(Change::from_avatar(&args),Some(Change{set:vec![(43,7)],delete:vec![]}));
        let mut long=args.clone();long.push(0);assert_eq!(Change::from_avatar(&long),None);
        assert_eq!(Change::from_avatar(&args[..args.len()-1]),None);assert_eq!(Change::from_avatar(&args[..6]),None);
    }
    #[test] fn merge_keeps_the_latest_state_of_a_key() {
        let mut first=Change{set:vec![(1,1),(2,2)],delete:vec![3]};
        first.merge(&Change{set:vec![(3,3)],delete:vec![1]});
        let mut map=Map::from([(1,9),(3,9),(4,9)]);first.apply(&mut map);
        assert_eq!(map,Map::from([(2,2),(3,3),(4,9)]));
    }
    #[test] fn state_keeps_every_other_byte_and_publishes_only_what_is_stored() {
        let raw=state();crate::hangar091::validate_account_delta(&raw).unwrap();
        let merged=state_with(&raw,&Map::from([(43,-5)])).unwrap();
        crate::hangar091::validate_account_delta(&merged).unwrap();
        assert!(merged.starts_with(&raw[..raw.len()-STATE_TAIL.len()]));
        assert!(merged.ends_with(b"intUserSettings}(J+\0\0\0J\xfb\xff\xff\xffuu."));
        let fresh=state_with(&raw,&Map::new()).unwrap();crate::hangar091::validate_account_delta(&fresh).unwrap();
        assert!(fresh.ends_with(b"intUserSettings}(uu."),"no version: the client initializes its defaults");
        let own=state_with(&raw,&Map::from([(0,10)])).unwrap();assert!(own.ends_with(b"}(J\0\0\0\0J\x0a\0\0\0uu."));
        assert!(state_with(b"\x80\x02}.",&Map::new()).is_err());
    }
    #[test] fn deltas_fit_one_update_chain_and_delete_with_none() {
        let change=Change{set:(0..40).map(|key|(key,-1)).collect(),delete:vec![41]};
        let all=deltas(3,&change).unwrap();assert_eq!(all.len(),3);
        for (index,delta) in all.iter().enumerate() {
            assert!(crate::ammo_service091::response(1,delta).is_ok(),"{}",delta.len());
            let mut head=b"\x80\x02}(U\x07prevRevJ".to_vec();head.extend((3+index as i32).to_le_bytes());head.extend(b"U\x03revJ");head.extend((4+index as i32).to_le_bytes());
            assert!(delta.starts_with(&head));
        }
        assert!(all[2].ends_with(b"J)\0\0\0Nuu."));
        assert!(deltas(i64::from(i32::MAX),&Change{set:vec![(1,1)],delete:vec![]}).is_err());
    }
    #[test] fn reply_is_bound_to_the_account_and_range() {
        assert_eq!(parse_reply(format!("{{\"account_id\":\"{ACCOUNT}\",\"settings\":[[1,-2],[43,5]]}}").as_bytes(),ACCOUNT).unwrap(),Map::from([(1,-2),(43,5)]));
        for raw in ["{}","[]","{\"account_id\":\"x\",\"settings\":[]}",&format!("{{\"account_id\":\"{ACCOUNT}\",\"settings\":[[57,0]]}}"),
            &format!("{{\"account_id\":\"{ACCOUNT}\",\"settings\":[[1,1],[1,2]]}}"),&format!("{{\"account_id\":\"{ACCOUNT}\",\"settings\":[[1,4294967296]]}}")] {
            assert!(parse_reply(raw.as_bytes(),ACCOUNT).is_err(),"{raw}");
        }
    }
}
