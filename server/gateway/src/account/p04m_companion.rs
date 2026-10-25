//! Versioned five-stock-profile garage capability. This is never a battle grant.
//! Source kinds come from the authenticated writer projection, never inventory ID.
use std::{io,path::Path};
use serde::{Deserialize,Deserializer,de::{self,MapAccess,SeqAccess,Visitor}};
use serde_json::Value;
use sha2::{Digest,Sha256};

pub const SCHEMA:&str="p04m-curated-stock-pool.v1";
pub const DEFINITION_SHA256:&str="90b07e5bf9d7ed416743666174f568b64ed1397b4cc55d1cfe9582e13afa0cac";
pub const REGISTRY_SHA256:&str="e2f4ac21fe8970f3c5d29f6a45d845f9d80e4d2759f0e662c9f3bb9ac04c7b34";
pub const POLICY_SHA256:&str="d1acd5590309c80b65307758bbee6f7f6de117f899668a00b1fad96ae6a13d3f";
pub const CREW_POLICY_SHA256:&str="6621ad7d3ccb86ebe8cc9db43b135d88155762ed3428e2a12b4002aba431a99b";
pub const CREW_V2_POLICY_SHA256:&str="7ff51fd896ab4e9f97c1a4dc7b46e75da08876f025a9afe7408f611f8d8caa1d";
/// The writer's stored crew contract (tools/p04m_pool_crew.py): policy and its
/// lifetime allocator. v2 exists only after the owner's explicit migration;
/// 192 keeps identities and freeTMenLeft in one pickle BININT1 byte.
const CREW_CONTRACTS:[(&str,i64);2]=[(CREW_POLICY_SHA256,16),(CREW_V2_POLICY_SHA256,192)];
/// Source name/surname/icon catalogue bounds of the free50 passport.
const NAME_BOUNDS:[u16;3]=[112,1036,30];
pub const AMMO_CATALOG_SHA256:&str="5e9d023c4d02f377e51a2d6bc07c7a5880f5f8808aaa8028f060ccb7bcf91e33";
fn bad(reason:&'static str)->io::Error{io::Error::new(io::ErrorKind::InvalidData,format!("P04M companion: {reason}"))}

// No procedural-macro dependency and no duplicate-key last-value semantics.
// Input is bounded before parsing; the JSON reader retains its recursion guard.
struct Unique(Value);
impl<'de> Deserialize<'de> for Unique {
    fn deserialize<D:Deserializer<'de>>(d:D)->Result<Self,D::Error>{
        struct Read;
        impl<'de> Visitor<'de> for Read {
            type Value=Unique;
            fn expecting(&self,f:&mut std::fmt::Formatter)->std::fmt::Result{f.write_str("bounded unique primitive JSON")}
            fn visit_bool<E:de::Error>(self,v:bool)->Result<Unique,E>{Ok(Unique(v.into()))}
            fn visit_i64<E:de::Error>(self,v:i64)->Result<Unique,E>{Ok(Unique(v.into()))}
            fn visit_u64<E:de::Error>(self,v:u64)->Result<Unique,E>{Ok(Unique(v.into()))}
            fn visit_unit<E:de::Error>(self)->Result<Unique,E>{Ok(Unique(Value::Null))}
            fn visit_str<E:de::Error>(self,v:&str)->Result<Unique,E>{if v.len()>512{return Err(E::custom("string bound"));}Ok(Unique(v.into()))}
            fn visit_string<E:de::Error>(self,v:String)->Result<Unique,E>{self.visit_str(&v)}
            fn visit_seq<A:SeqAccess<'de>>(self,mut a:A)->Result<Unique,A::Error>{
                let mut v=Vec::new();while let Some(Unique(row))=a.next_element()?{if v.len()>=256{return Err(de::Error::custom("array bound"));}v.push(row);}Ok(Unique(v.into()))
            }
            fn visit_map<M:MapAccess<'de>>(self,mut m:M)->Result<Unique,M::Error>{
                let mut v=serde_json::Map::new();while let Some((k,Unique(row)))=m.next_entry::<String,Unique>()?{
                    if k.len()>64||v.len()>=16||v.insert(k,row).is_some(){return Err(de::Error::custom("duplicate/object bound"));}
                }Ok(Unique(Value::Object(v)))
            }
        }d.deserialize_any(Read)
    }
}
fn keys(v:&Value,expected:&[&str])->io::Result<()>{let o=v.as_object().ok_or_else(||bad("object"))?;
    if o.len()!=expected.len()||expected.iter().any(|k|!o.contains_key(*k)){return Err(bad("exact fields"));}Ok(())}
fn string<'a>(v:&'a Value,k:&str)->io::Result<&'a str>{v[k].as_str().ok_or_else(||bad("string type"))}
fn hash(v:&str)->bool{v.len()==64&&v.bytes().all(|b|b.is_ascii_digit()||(b'a'..=b'f').contains(&b))}

#[derive(Clone,Copy,Debug,PartialEq,Eq,PartialOrd,Ord)]
pub enum Kind{Ms1,Is7,T26,T34,T3485}
impl Kind{
    pub fn parse(v:&str)->Option<Self>{match v{"ms1"=>Some(Self::Ms1),"is7"=>Some(Self::Is7),"t26"=>Some(Self::T26),"t34"=>Some(Self::T34),"t3485"=>Some(Self::T3485),_=>None}}
    pub fn label(self)->&'static str{match self{Self::Ms1=>"ms1",Self::Is7=>"is7",Self::T26=>"t26",Self::T34=>"t34",Self::T3485=>"t3485"}}
    pub fn type_cd(self)->i32{match self{Self::Ms1=>3329,Self::Is7=>7169,Self::T26=>4609,Self::T34=>1,Self::T3485=>2561}}
    fn primary_roles(self)->&'static[i32]{match self{Self::Ms1=>&[1,3],Self::Is7=>&[1,4,3,5,5],Self::T26=>&[1,3,4],Self::T34=>&[1,2,3,5],Self::T3485=>&[1,4,2,3,5]}}
    fn ammo(self)->([i32;3],u32){match self{Self::Ms1=>([2570,2826,3082],96),Self::Is7=>([14602,14858,15114],30),Self::T26=>([1034,1290,1546],160),Self::T34=>([7178,7434,7690],77),Self::T3485=>([7946,8202,8458],68)}}
    fn new(self)->bool{!matches!(self,Self::Ms1|Self::Is7)}
}
#[derive(Clone,Debug,PartialEq,Eq)]
struct Capability{native:i32,kind:Option<Kind>}
#[derive(Clone,Debug,PartialEq,Eq)]
pub struct Binding{account:String,database:i32,pub revision:u64,state_sha:String,capabilities:Vec<Capability>,capacity:i64}
pub enum Request{Ammo(crate::ammo_service091::Request),Crew(crate::crew_service091::Request),Transfer(crate::crew_transfer091::Request),Barracks(crate::crew_barracks091::Request),
    Dismiss(crate::crew_dismissal091::Request),Skill(crate::crew_progression091::Request)}
impl Binding{
    pub fn parse(raw:&[u8],account:&str,database:i32,revision:u64,state_sha:&str)->io::Result<Self>{
        crate::crew_service091::identity(account,database)?;
        if raw.is_empty()||raw.len()>65536||!(13..i32::MAX as u64).contains(&revision)||!hash(state_sha){return Err(bad("size/revision/state"));}
        let Unique(v)=serde_json::from_slice(raw).map_err(|_|bad("unique bounded JSON"))?;
        keys(&v,&["version","schema","definition_sha256","registry_sha256","policy_sha256","crew_policy_sha256","ammo_catalog_sha256","account_id","native_database_id","revision","state_sha256","crew_capacity","capabilities"])?;
        if v["version"].as_u64()!=Some(1)||string(&v,"schema")?!=SCHEMA||string(&v,"definition_sha256")?!=DEFINITION_SHA256
            ||string(&v,"registry_sha256")?!=REGISTRY_SHA256||string(&v,"policy_sha256")?!=POLICY_SHA256
            ||string(&v,"ammo_catalog_sha256")?!=AMMO_CATALOG_SHA256||string(&v,"account_id")?!=account||v["native_database_id"].as_i64()!=Some(database as i64)
            ||v["revision"].as_u64()!=Some(revision)||string(&v,"state_sha256")?!=state_sha{return Err(bad("identity/source/policy/state binding"));}
        let crew=string(&v,"crew_policy_sha256")?;
        let capacity=CREW_CONTRACTS.iter().find(|(sha,_)|*sha==crew).map(|(_,capacity)|*capacity)
            .filter(|capacity|v["crew_capacity"].as_i64()==Some(*capacity)).ok_or_else(||bad("crew contract/capacity binding"))?;
        let rows=v["capabilities"].as_array().filter(|r|(2..=256).contains(&r.len())).ok_or_else(||bad("capability count"))?;
        let mut capabilities=Vec::new();let mut kinds=std::collections::BTreeSet::new();
        for r in rows{
            keys(r,&["native_inventory_id","vehicle_inventory_id","kind","assembly_id","readiness_code","admission"])?;
            let native=r["native_inventory_id"].as_i64().and_then(|i|i32::try_from(i).ok()).filter(|i|*i>0).ok_or_else(||bad("native inventory"))?;
            if capabilities.last().is_some_and(|old:&Capability|old.native>=native){return Err(bad("inventory order/duplicate"));}
            let kind=if r["kind"].is_null(){None}else{Some(Kind::parse(string(r,"kind")?).ok_or_else(||bad("closed source kind"))?)};
            let suffix=match native{1=>":starter-vehicle-v1".into(),2=>":test-is7-v1".into(),_=>format!(":p09e-vehicle:{native}")};
            if string(r,"vehicle_inventory_id")?!=format!("{account}{suffix}")
                ||(native==1&&kind.is_some_and(|k|k!=Kind::Ms1))||(native==2&&kind.is_some_and(|k|k!=Kind::Is7))
                ||(native>2&&matches!(kind,Some(Kind::Ms1|Kind::Is7))){return Err(bad("owned inventory/source type"));}
            let admission=r["admission"].as_bool().ok_or_else(||bad("admission boolean"))?;
            let code=r["readiness_code"].as_str();
            let stock=!r["assembly_id"].is_null();
            if let Some(kind)=kind{
                if !kinds.insert(kind)||stock&&r["assembly_id"].as_str()!=Some(format!("{}-stock",kind.label()).as_str()){return Err(bad("assembly/duplicate kind"));}
                if !stock{if admission||code!=Some("BATTLE_PROFILE_UNSUPPORTED"){return Err(bad("non-stock capability remains unsupported"));}}
                else if kind.new(){if admission||code!=Some("OWNER_ACCEPTANCE_REQUIRED"){return Err(bad("new battle admission remains closed"));}}
                else if admission{if !r["readiness_code"].is_null(){return Err(bad("admitted readiness"));}}
                else if !matches!(code,Some("BATTLE_PROFILE_UNSUPPORTED"|"INCOMPLETE_CREW"|"AMMUNITION_EMPTY"|"AMMUNITION_UNSUPPORTED"|"VEHICLE_RESERVED")){return Err(bad("readiness rejection"));}
            }else if admission||!r["assembly_id"].is_null()||code!=Some("BATTLE_PROFILE_UNSUPPORTED"){return Err(bad("unsupported capability"));}
            capabilities.push(Capability{native,kind});
        }
        if capabilities.get(0).map(|c|c.native)!=Some(1)||capabilities.get(1).map(|c|c.native)!=Some(2){return Err(bad("missing base inventory"));}
        Ok(Self{account:account.into(),database,revision,state_sha:state_sha.into(),capabilities,capacity})
    }
    pub fn metadata(directory:&Path,account:&str,database:i32,revision:u64)->io::Result<Self>{
        let read=crate::crew_service091::fixture_file;
        let state=read(directory,"state.bin",crate::research_service091::MAX_STATE_BYTES)?;
        let raw=read(directory,"p04m-pool.json",65536)?;
        Self::parse(&raw,account,database,revision,&format!("{:x}",Sha256::digest(&state)))
    }
    pub fn matches(&self,account:&str,database:i32,revision:u64)->bool{self.account==account&&self.database==database&&self.revision==revision}
    pub fn matches_state(&self,state:&[u8])->bool{self.state_sha==format!("{:x}",Sha256::digest(state))}
    /// Lifetime tankman identities of the stored crew contract (16 or 192).
    pub fn capacity(&self)->i64{self.capacity}
    fn kind(&self,native:i64)->io::Result<Kind>{self.capabilities.iter().find(|c|c.native as i64==native).and_then(|c|c.kind).ok_or_else(||bad("unsupported owned selection"))}
    pub fn ammo_layout(&self,r:&crate::ammo_service091::Request)->io::Result<[crate::ammo_service091::ShellCount;3]>{
        // This is a bounded source shape, never a whole-assembly admission or
        // mounted-gun ownership proof. A legal chassis upgrade must not prevent
        // unloading. The writer independently checks actual owned turret/gun.
        let (shells,capacity)=self.kind(r.vehicle_inventory_id() as i64)?.ammo();r.layout_for_catalog(shells,capacity,5)
    }
    pub fn recruit(&self,r:crate::crew_service091::Request)->io::Result<()>{
        let roles=self.kind(r.vehicle_inventory_id as i64)?.primary_roles();
        if r.id<=0||r.shop_revision!=3||r.tariff_index!=0||r.slot<0||r.slot as usize>=roles.len(){return Err(bad("recruit source seat/layout"));}Ok(())
    }
    pub fn transfer(&self,r:crate::crew_transfer091::Request)->io::Result<()>{
        let maximum=self.kind(r.vehicle_inventory_id)?.primary_roles().len() as i32-1;
        if r.id<=0||!(-1..=maximum).contains(&r.slot)||!(r.tankman_inventory_id==-1||(1..=self.capacity).contains(&(r.tankman_inventory_id as i64)))
            ||r.slot==-1&&r.tankman_inventory_id!=-1{return Err(bad("transfer source seat/layout"));}Ok(())
    }
    pub fn dismiss(&self,r:crate::crew_dismissal091::Request)->io::Result<()>{
        if r.id<=0||!(1..=self.capacity).contains(&r.tankman_inventory_id)||r.reserved_a!=0||r.reserved_b!=0{return Err(bad("dismissal identity/layout"));}Ok(())
    }
    pub fn learn(&self,r:crate::crew_progression091::Request)->io::Result<()>{
        // Same layout as P04I; skill eligibility/qualification stays with the writer.
        if r.id<=0||!(1..=self.capacity).contains(&r.tankman_inventory_id)||!(1..=255).contains(&r.skill_index)||r.skill_index==18||r.reserved!=0{
            return Err(bad("skill identity/layout"));}Ok(())
    }
    pub fn barracks(&self,r:crate::crew_barracks091::Request)->io::Result<()>{
        let kind=[Kind::Ms1,Kind::Is7,Kind::T26,Kind::T34,Kind::T3485].into_iter().find(|k|k.type_cd()==r.vehicle_type).ok_or_else(||bad("barracks source type"))?;
        if r.id<=0||r.shop_revision!=3||r.cost!=0||!kind.primary_roles().contains(&r.role){return Err(bad("barracks source primary role"));}Ok(())
    }
    pub fn service_request(&self,key:&str,revision:u64,wire:i64,layout:&[i64])->io::Result<Vec<u8>>{
        if revision<self.revision||!(13..i32::MAX as u64).contains(&revision)||!(1..i32::MAX as i64).contains(&wire)||!(1..=96).contains(&key.len())
            ||!key.bytes().all(|b|b.is_ascii_alphanumeric()||b"-_:".contains(&b))||layout.len()>16{return Err(bad("service cursor/key/layout"));}
        serde_json::to_vec(&serde_json::json!({"account_id":self.account,"native_database_id":self.database,"command_key":key,
            "expected_revision":revision,"wire_revision":wire,"layout":layout})).map_err(|_|bad("request encoding"))
    }
    pub fn validate_recruitment(&self,member:&crate::crew_barracks091::Recruitment,r:crate::crew_barracks091::Request,wire:i64,delta:&[u8])->io::Result<()>{
        self.barracks(r)?;let id=member.tankman_id;
        if !(4..=self.capacity).contains(&(id as i64))||!(1..i32::MAX as i64).contains(&wire){return Err(bad("recruitment identity/cursor"));}
        // ((id-1) mod bound)+1 per name/surname/icon: equal to id for 1..16.
        let names=NAME_BOUNDS.map(|bound|((id as u16-1)%bound+1).to_le_bytes());
        let expected=[8,(r.vehicle_type>>8)as u8,r.role as u8,50,0,0,0,names[0][0],names[0][1],names[1][0],names[1][1],names[2][0],names[2][1],0x40,6,0,0,0,0,66,0,0,0,0,0];
        if member.descriptor!=expected{return Err(bad("recruitment source passport"));}
        let mut out=b"\x80\x02}(U\x07prevRev".to_vec();integer(&mut out,wire as i32);out.extend(b"U\x03rev");integer(&mut out,wire as i32+1);
        // The versioned Pool writer emits vehicle before compDescr. This exact
        // layout is pinned by an actual SQLite CMD303 vector, independently of
        // the retained P04K encoder's different dictionary insertion order.
        out.extend(b"U\x09inventory}(K\x08}(U\x07vehicle}(K");out.push(id);out.extend(b"J\xff\xff\xff\xffuU\x09compDescr}(K");
        out.push(id);out.extend(b"U\x19");out.extend(expected);out.extend(b"uuuU\x05stats}(U\x0cfreeTMenLeftK");out.push((self.capacity-id as i64) as u8);out.extend(b"uu.");
        if delta!=out{return Err(bad("recruitment delta/ext binding"));}crate::hangar091::validate_account_delta(delta)
    }
}
fn integer(out:&mut Vec<u8>,v:i32){if (0..=255).contains(&v){out.extend([b'K',v as u8]);}else if (0..=65535).contains(&v){out.push(b'M');out.extend((v as u16).to_le_bytes());}else{out.push(b'J');out.extend(v.to_le_bytes());}}

#[cfg(test)]
pub(crate) fn test_value(account:&str,revision:u64)->Value{
    // Codec fixture only; actual writer fixture tests are separate.
    let caps=[(1,Kind::Ms1),(2,Kind::Is7),(3,Kind::T34),(4,Kind::T3485),(7,Kind::T26)].map(|(native,kind)|{
        let suffix=match native{1=>":starter-vehicle-v1".into(),2=>":test-is7-v1".into(),_=>format!(":p09e-vehicle:{native}")};
        serde_json::json!({"native_inventory_id":native,"vehicle_inventory_id":format!("{account}{suffix}"),"kind":kind.label(),
            "assembly_id":format!("{}-stock",kind.label()),"readiness_code":if kind.new(){Some("OWNER_ACCEPTANCE_REQUIRED")}else{None},"admission":!kind.new()})
    });
    serde_json::json!({"version":1,"schema":SCHEMA,"definition_sha256":DEFINITION_SHA256,"registry_sha256":REGISTRY_SHA256,
        "policy_sha256":POLICY_SHA256,"crew_policy_sha256":CREW_POLICY_SHA256,"ammo_catalog_sha256":AMMO_CATALOG_SHA256,
        "account_id":account,"native_database_id":900001,"revision":revision,"state_sha256":format!("{:x}",Sha256::digest(b"\x80\x02}.")),
        "crew_capacity":16,"capabilities":caps})
}
#[cfg(test)]
pub(crate) fn test_binding(account:&str,revision:u64)->Binding{
    let v=test_value(account,revision);Binding::parse(&serde_json::to_vec(&v).unwrap(),account,900001,revision,v["state_sha256"].as_str().unwrap()).unwrap()
}
#[cfg(test)]
#[path="p04m_companion_tests.rs"]
mod p04m_tests;
