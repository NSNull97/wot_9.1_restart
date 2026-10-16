//! Test-only relocation of immutable, SHA-pinned original fixtures into a fresh
//! C workspace. Production ownership/loaders and original source SHAs stay strict.
use serde_json::Value;
use sha2::{Digest,Sha256};
use std::{collections::BTreeMap,fs,path::{Path,PathBuf}};

fn spelling(path:&Path)->PathBuf {
    let text=path.to_str().expect("UTF-8 local path");
    PathBuf::from(text.strip_prefix(r"\\?\").unwrap_or(text))
}
fn plain(path:&Path) {
    for p in path.ancestors() {
        if p.exists() {
            let meta=fs::symlink_metadata(p).unwrap();assert!(!meta.file_type().is_symlink());
            #[cfg(windows)] {use std::os::windows::fs::MetadataExt;assert_eq!(meta.file_attributes()&0x400,0,"reparse fixture ancestor");}
        }
    }
}
fn bytes(path:&Path,max:usize)->Vec<u8> {
    plain(path);let size=fs::metadata(path).unwrap().len();assert!(size<=max as u64);
    let raw=fs::read(path).unwrap();assert_eq!(raw.len()as u64,size);raw
}
fn hash(raw:&[u8])->String {format!("{:x}",Sha256::digest(raw))}
fn allocation(workspace:&Path) {
    assert_eq!(workspace,Path::new("C:/wot091-night-20261017-01/w"),"closed short workspace only");
    let path=Path::new("C:/Users/NSNull/AppData/Local/Temp/wot091-night-workspace-kcadgetk/short-workspace01/allocation.json");
    assert_eq!(hash(&bytes(path,4096)),"677765e23e8de12beb02bfb1b57574e7f528bfe27d872582371f6037db89199e");
}
/// The old worker relocator needs original decimal spellings before it writes
/// its own per-run C configs. Read only the exact SHA-pinned original input.
pub(crate) fn original_bytes(path:&Path,expected:&str,maximum:usize)->Vec<u8> {
    let workspace=spelling(&Path::new(env!("CARGO_MANIFEST_DIR")).join("../..").canonicalize().unwrap());
    let path=spelling(&path.canonicalize().unwrap());
    let source=if workspace==Path::new("D:/WoT_9.1_Server"){path}
        else {allocation(&workspace);let rel=path.strip_prefix(&workspace).unwrap();assert!(rel.starts_with("local"));Path::new("D:/WoT_9.1_Server").join(rel)};
    let raw=bytes(&source,maximum);assert_eq!(hash(&raw),expected,"original source bytes");raw
}
fn replace_tokens(raw:&[u8],before:&Value,after:&Value)->Vec<u8> {
    fn collect(a:&Value,b:&Value,changes:&mut BTreeMap<String,(String,usize)>) {
        match(a,b){
            (Value::Object(a),Value::Object(b))=>{assert_eq!(a.keys().collect::<Vec<_>>(),b.keys().collect::<Vec<_>>());for(k,x)in a{collect(x,&b[k],changes);}},
            (Value::Array(a),Value::Array(b))=>{assert_eq!(a.len(),b.len());for(x,y)in a.iter().zip(b){collect(x,y,changes);}},
            _ if a==b=>(),
            (Value::String(a),Value::String(b))=>{let old=serde_json::to_string(a).unwrap();let new=serde_json::to_string(b).unwrap();
                let row=changes.entry(old).or_insert((new.clone(),0));assert_eq!(row.0,new);row.1+=1;},
            _=>panic!("numeric/non-string relocation forbidden")
        }
    }
    let mut changes=BTreeMap::new();collect(before,after,&mut changes);
    let mut text=std::str::from_utf8(raw).unwrap().to_owned();
    for(old,(new,count))in changes{assert_eq!(text.matches(&old).count(),count,"complete JSON token count");text=text.replace(&old,&new);}
    text.into_bytes()
}

/// Verifies the original source SHA, then independently validates that derived
/// runtime containers differ only in closed paths and corresponding child SHAs.
/// The returned hash is the new C document hash, never the old source hash.
pub(crate) fn verified(path:&Path,source_sha:Option<&str>)->(PathBuf,String) {
    let workspace=spelling(&Path::new(env!("CARGO_MANIFEST_DIR")).join("../..").canonicalize().unwrap());
    let path=spelling(&path.canonicalize().unwrap());
    if workspace==Path::new("D:/WoT_9.1_Server") {
        let raw=bytes(&path,256*1024*1024);let h=hash(&raw);
        if let Some(expected)=source_sha {assert_eq!(h,expected,"original fixture source SHA");}
        return(path,h)
    }
    assert!(path.starts_with(&workspace),"fixture must belong to current source workspace");
    let parent=Path::new("C:/Users/NSNull/AppData/Local/Temp/wot091-night-workspace-kcadgetk");
    allocation(&workspace);
    let allocation:Value=serde_json::from_slice(&bytes(&parent.join("short-workspace01/allocation.json"),4096)).unwrap();
    assert_eq!(allocation["schema"],"wot091-fresh-short-workspace.v1");
    assert_eq!(Path::new(allocation["workspace"].as_str().unwrap()),workspace);
    assert_eq!(allocation["source_root"],"D:\\WoT_9.1_Server");
    let context:Value=serde_json::from_slice(&bytes(&parent.join("dependencies-short02/resource-context.json"),1024*1024)).unwrap();
    assert_eq!(context["schema"],"wot091-c-fixture-context.v1");
    assert_eq!(Path::new(context["workspace"].as_str().unwrap()),workspace);
    assert_eq!(Path::new(context["source_root"].as_str().unwrap()),Path::new("D:/WoT_9.1_Server"));
    assert_eq!(context["allocation_sha256"],hash(&bytes(&parent.join("short-workspace01/allocation.json"),4096)));
    let rel=path.strip_prefix(&workspace).unwrap().to_string_lossy().replace('\\',"/");
    let mut verifier=Verifier{workspace:&workspace,rows:context["files"].as_object().unwrap(),done:BTreeMap::new()};
    let actual=verifier.file(&rel,source_sha,0);(path,actual)
}
struct Verifier<'a>{workspace:&'a Path,rows:&'a serde_json::Map<String,Value>,done:BTreeMap<String,String>}
impl Verifier<'_>{
    fn reference(&mut self,row:&mut Value,path_key:&str,hash_key:&str,depth:usize) {
        let old=PathBuf::from(row[path_key].as_str().unwrap());
        let rel=old.strip_prefix("D:/WoT_9.1_Server").expect("source reference confined to original local tree").to_string_lossy().replace('\\',"/");
        assert!(rel.starts_with("local/"));let expected=row[hash_key].as_str().unwrap().to_owned();
        let actual=self.file(&rel,Some(&expected),depth+1);
        row[path_key]=self.workspace.join(&rel).to_str().unwrap().into();row[hash_key]=actual.into();
    }
    fn file(&mut self,rel:&str,expected:Option<&str>,depth:usize)->String {
        assert!(depth<=12&&self.rows.len()<=1024);let row=self.rows.get(rel).expect("finite published fixture").clone();
        let source=PathBuf::from(row["source"].as_str().unwrap());
        assert_eq!(source,Path::new("D:/WoT_9.1_Server").join(rel));
        let raw=bytes(&source,256*1024*1024);let source_hash=hash(&raw);
        assert_eq!(source_hash,row["source_sha256"]);if let Some(h)=expected {assert_eq!(source_hash,h,"original source fixture SHA retained");}
        if let Some(done)=self.done.get(rel) {return done.clone()}
        let target=self.workspace.join(rel);assert_eq!(Path::new(row["path"].as_str().unwrap()),target);
        let published=bytes(&target,256*1024*1024);let actual=hash(&published);assert_eq!(actual,row["sha256"]);
        match row["kind"].as_str().unwrap() {
            "immutable"=>assert_eq!(raw,published,"immutable numeric/source resources stay byte exact"),
            kind=>{
                assert!(raw.len()<=1024*1024&&published.len()<=1024*1024);
                let mut value:Value=serde_json::from_slice(&raw).unwrap();
                match kind {
                    "template"=>{
                        self.reference(&mut value["catalog"],"path","sha256",depth);
                        for item in value["profiles"].as_array_mut().unwrap(){self.reference(&mut item["pool"],"path","sha256",depth);self.reference(&mut item["geometry"],"path","sha256",depth);}
                        if value.get("shared_physics").is_some(){self.reference(&mut value["shared_physics"],"path","sha256",depth);}
                    },
                    "pool"=>{
                        for item in value["maps"].as_array_mut().unwrap(){self.reference(item,"config","config_sha256",depth);}
                        self.reference(&mut value["vehicle_profile"],"path","sha256",depth);
                        self.reference(&mut value["worker"],"artifact_manifest","artifact_manifest_sha256",depth);
                        let old=PathBuf::from(value["worker"]["executable"].as_str().unwrap());let suffix=old.strip_prefix("D:/WoT_9.1_Server").unwrap();
                        let key=suffix.to_string_lossy().replace('\\',"/");self.file(&key,None,depth+1);
                        value["worker"]["executable"]=self.workspace.join(suffix).to_str().unwrap().into();
                    },
                    "config"=>{self.reference(&mut value["terrain"],"path","sha256",depth);self.reference(&mut value["obstacles"],"path","sha256",depth);},
                    "seed"=>{
                        for name in ["database","bundle"] {let old=PathBuf::from(value[name].as_str().unwrap());let suffix=old.strip_prefix("D:/WoT_9.1_Server").unwrap();value[name]=self.workspace.join(suffix).to_str().unwrap().into();}
                    },
                    _=>panic!("unrecognized fixture derivation")
                }
                let actual_value=serde_json::from_slice::<Value>(&published).unwrap();
                assert_eq!(value,actual_value,"only closed runtime references may change");
                assert_eq!(replace_tokens(&raw,&serde_json::from_slice::<Value>(&raw).unwrap(),&value),published,
                    "all original nonpath raw bytes and decimal spelling survive");
            }
        }
        self.done.insert(rel.to_owned(),actual.clone());actual
    }
}

#[test] fn portable_fixture_source_shas_and_numeric_fields_survive_runtime_relocation(){
    let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local");
    verified(&root.join("evidence/20261016-p04m-runtime01/domain-fixture01/battle-profiles-five.json"),
        Some("b7f272aace7a7746643bf00f0a49d343931d139477765ab30fcacbbf24c668e4"));
    verified(&root.join("evidence/20261016-p06t-world07/resources01/battle-profiles-seven.json"),
        Some("76f198a10768c24082e49cb3d7c850f13eab1a1a249de559f96025c355f933e6"));
}
#[test] fn portable_fixture_token_relocation_preserves_decimal_spelling_and_denies_extra_or_numeric_changes(){
    let raw=br#"{ "path":"D:\\old", "number":[1e-007,-0.0,1.0385702341794967] }"#;
    let before:Value=serde_json::from_slice(raw).unwrap();let mut after=before.clone();after["path"]="C:\\own".into();
    assert_eq!(replace_tokens(raw,&before,&after),br#"{ "path":"C:\\own", "number":[1e-007,-0.0,1.0385702341794967] }"#);
    let mut bad=after.clone();bad["number"][0]=99.into();assert!(std::panic::catch_unwind(||replace_tokens(raw,&before,&bad)).is_err());
    let duplicate=[raw.as_slice(),raw.as_slice()].concat();assert!(std::panic::catch_unwind(||replace_tokens(&duplicate,&before,&after)).is_err());
}
#[test] fn portable_fixture_context_cannot_relabel_changed_immutable_bytes_or_foreign_paths(){
    let workspace=spelling(&Path::new(env!("CARGO_MANIFEST_DIR")).join("../..").canonicalize().unwrap());
    let dir=workspace.join(format!("local/test-runs/portable-negative-{}-{}",std::process::id(),std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos()));
    fs::create_dir_all(&dir).unwrap();let key="local/stands/p09e-main-01/native-ms1.json";
    let source=Path::new("D:/WoT_9.1_Server").join(key);let original=bytes(&source,65536);let mut forged=original.clone();forged.push(b' ');
    let target=dir.join(key);fs::create_dir_all(target.parent().unwrap()).unwrap();fs::write(&target,&forged).unwrap();
    let mut rows=serde_json::Map::new();rows.insert(key.into(),serde_json::json!({"source":source,"source_sha256":hash(&original),"path":target,"sha256":hash(&forged),"kind":"immutable"}));
    assert!(std::panic::catch_unwind(std::panic::AssertUnwindSafe(||Verifier{workspace:&dir,rows:&rows,done:BTreeMap::new()}.file(key,Some(&hash(&original)),0))).is_err());
    let mut value=serde_json::json!({"path":"D:/foreign/input.json","sha256":"a".repeat(64)});
    assert!(std::panic::catch_unwind(std::panic::AssertUnwindSafe(||Verifier{workspace:&dir,rows:&rows,done:BTreeMap::new()}.reference(&mut value,"path","sha256",0))).is_err());
}
