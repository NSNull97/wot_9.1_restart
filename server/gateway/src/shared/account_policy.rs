//! Explicit shared-lab Account service projection for the two frozen profiles.
//! Only stats.battlesTillCaptcha changes in the outgoing stream. Inventory,
//! crew, ammunition, source fixture hashes and the ordinary drive stay intact.
use std::io;
use sha2::{Digest,Sha256};
use crate::{account091::Request,hangar091::Fixtures,identity091::Profile};

pub(super) const SECONDARY_ACCOUNT:&str="271022a3-41e0-406e-b6fa-59930c320442";
const SECONDARY_NAME:&str="Танкист_Ёж_e91322";
const SECONDARY_SOURCE:&str="aa8555869362a25133be64f8065c32675d723e3f83f0b0dac3ac8ed7ebdb9d75";
const SECONDARY_OUTGOING:&str="d9b8e474f355b70ac2e2a4b3a29c44f78c4585c3eee623a9b4889d283f6aefb7";
const SECONDARY_BYTES:usize=1106;
const SECONDARY_VALUE:usize=605;

fn invalid()->io::Error {io::Error::new(io::ErrorKind::InvalidData,"unverified shared-lab Account service policy")}
fn hex(raw:&[u8])->String {raw.iter().map(|byte|format!("{byte:02x}")).collect()}

fn project_secondary(identity:&Profile,source:&[u8])->io::Result<Vec<u8>> {
    if identity.account_id!=SECONDARY_ACCOUNT || identity.database_id!=2 || identity.name!=SECONDARY_NAME
        || !identity.fixture_dir.is_absolute()
        || identity.fixture_dir.file_name().and_then(|name|name.to_str())!=Some("r1-catalog2")
        || identity.fixture_dir.parent().and_then(|path|path.file_name()).and_then(|name|name.to_str())!=Some(SECONDARY_ACCOUNT)
        || source.len()!=SECONDARY_BYTES || hex(&Sha256::digest(source))!=SECONDARY_SOURCE
        || source.get(584..606)!=Some(b"U\x12battlesTillCaptchaK\x00") {return Err(invalid());}
    let mut outgoing=source.to_vec();outgoing[SECONDARY_VALUE]=1;
    if hex(&Sha256::digest(&outgoing))!=SECONDARY_OUTGOING {return Err(invalid());}
    Ok(outgoing)
}

pub(super) fn response(identity:&Profile,fixtures:&Fixtures,request:&Request,session:u32)
    ->io::Result<(Vec<Vec<u8>>,String)> {
    let (bodies,source,outgoing,bytes)=if identity.account_id==crate::arena_vehicle091::PRIMARY_ACCOUNT {
        let policy=crate::map_drive_service091::AccountPolicy::for_mode(true,identity,fixtures)?.ok_or_else(invalid)?;
        (policy.response(request,identity,fixtures)?,crate::arena_vehicle091::PRIMARY_STATE_SHA256,
            crate::map_drive_service091::OUTGOING_STATE_SHA256,fixtures.state_bytes().len())
    } else {
        let outgoing=project_secondary(identity,fixtures.state_bytes())?;
        (crate::hangar091::response_state(request,&outgoing)?,SECONDARY_SOURCE,SECONDARY_OUTGOING,SECONDARY_BYTES)
    };
    let event=format!("SHARED_ACCOUNT_POLICY_STREAM session={session} request={} command=100 policy_version=1 source_state_sha256={source} outgoing_state_sha256={outgoing} raw_bytes={bytes} field=stats.battlesTillCaptcha source_value=0 outgoing_value=1 full_stream=true inventory_changed=false persisted=false captcha_answer_generated=false",request.id);
    Ok((bodies,event))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::Path;

    pub(super) fn secondary()->(Profile,Fixtures) {
        let directory=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/server/fixtures")
            .join(SECONDARY_ACCOUNT).join("r1-catalog2").canonicalize().unwrap();
        let fixtures=Fixtures::load_interactive(&directory).unwrap();
        (Profile{account_id:SECONDARY_ACCOUNT.into(),database_id:2,name:SECONDARY_NAME.into(),fixture_dir:directory},fixtures)
    }

    #[test]
    fn both_shared_profiles_publish_only_the_frozen_service_counter_delta() {
        for ((identity,fixtures),offset) in [(crate::map_drive_service091::tests::actual(),802),(secondary(),SECONDARY_VALUE)] {
            let before=fixtures.state_sha256();let request=Request{id:226,command:100};
            let (bodies,event)=response(&identity,&fixtures,&request,1).unwrap();
            let raw=crate::map_drive_service091::tests::assembled(&bodies,226);
            let differences=fixtures.state_bytes().iter().zip(&raw).enumerate()
                .filter(|(_, (source,target))|source!=target).map(|(index,_)|index).collect::<Vec<_>>();
            assert_eq!(differences,vec![offset]);assert_eq!(raw[offset],1);
            assert_eq!(fixtures.state_sha256(),before);assert!(event.contains("inventory_changed=false"));
            let mut inverse=raw;inverse[offset]=0;assert_eq!(inverse,fixtures.state_bytes());
        }
    }

    #[test]
    fn secondary_policy_rejects_every_source_byte_mutation_and_wrong_identity() {
        let (identity,fixtures)=secondary();let source=fixtures.state_bytes();
        for index in 0..source.len() {let mut changed=source.to_vec();changed[index]^=1;
            assert!(project_secondary(&identity,&changed).is_err());}
        assert!(project_secondary(&identity,&source[..source.len()-1]).is_err());
        let mut extended=source.to_vec();extended.push(0);assert!(project_secondary(&identity,&extended).is_err());
        for change in 0..5 {let mut wrong=Profile{account_id:identity.account_id.clone(),database_id:2,
            name:identity.name.clone(),fixture_dir:identity.fixture_dir.clone()};
            match change {0=>wrong.account_id="other".into(),1=>wrong.database_id=1,2=>wrong.name="other".into(),
                3=>wrong.fixture_dir="relative".into(),4=>{wrong.fixture_dir.pop();wrong.fixture_dir.push("r4-catalog3");},_=>unreachable!()}
            assert!(project_secondary(&wrong,source).is_err());
        }
        let (primary,primary_fixtures)=crate::map_drive_service091::tests::actual();
        let request=Request{id:226,command:100};
        assert!(response(&identity,&primary_fixtures,&request,1).is_err());
        assert!(response(&primary,&fixtures,&request,1).is_err());
    }
}
