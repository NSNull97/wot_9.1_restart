//! Test-only fresh output compression. No recursive operation, arbitrary path,
//! production path-policy change, old file compression, cleanup or process.
use std::{fs,io,path::{Component,Path,PathBuf},time::{SystemTime,UNIX_EPOCH}};
const NAMESPACES:[&str;6]=["p08b-composition02","p08c-late-composition05","p10b-loss-composition09","p08b-owner-hold-composition10","p08b-owner-hold-composition17","composition-storage22"];
const FRESH_NS:u128=30_000_000_000;
fn bad(reason:&'static str)->io::Error{io::Error::new(io::ErrorKind::InvalidInput,reason)}
fn now_ns()->io::Result<u128>{SystemTime::now().duration_since(UNIX_EPOCH).map(|v|v.as_nanos()).map_err(|_|bad("system clock before UNIX epoch"))}
fn plain(path:&Path)->io::Result<PathBuf>{
    if !path.is_absolute(){return Err(bad("absolute local composition path required"));}
    #[cfg(windows)]{
        if !matches!(path.components().next(),Some(Component::Prefix(prefix))if matches!(prefix.kind(),std::path::Prefix::Disk(_)|std::path::Prefix::VerbatimDisk(_))){
            return Err(bad("local drive required; UNC/device paths refused before probing"));
        }
    }
    let mut cursor=PathBuf::new();
    for part in path.components(){
        if matches!(part,Component::ParentDir|Component::CurDir){return Err(bad("noncanonical composition path"));}
        cursor.push(part.as_os_str());
        if matches!(part,Component::Normal(_)){
            let info=fs::symlink_metadata(&cursor)?;if info.file_type().is_symlink(){return Err(bad("linked composition path refused"));}
            #[cfg(windows)]{use std::os::windows::fs::MetadataExt;if info.file_attributes()&0x400!=0{return Err(bad("reparse composition path refused"));}}
        }
    }path.canonicalize()
}
fn empty(path:&Path)->io::Result<()>{if fs::read_dir(path)?.next().is_some(){return Err(bad("nonempty composition output refused"));}Ok(())}
fn scope(root:&Path,output:&Path)->io::Result<(PathBuf,PathBuf,String)>{
    let root=plain(root)?;let manifest=PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let compiled=plain(manifest.parent().and_then(Path::parent).ok_or_else(||bad("compiled manifest root"))?)?;
    if root!=compiled{return Err(bad("exact compiled project root required"));}
    let output=plain(output)?;let base=root.join("local/test-runs");let relative=output.strip_prefix(&base).map_err(|_|bad("output outside local/test-runs"))?;
    let parts=relative.components().collect::<Vec<_>>();if parts.len()!=2{return Err(bad("exact composition output depth required"));}
    let namespace=parts[0].as_os_str().to_str().ok_or_else(||bad("namespace encoding"))?;
    if !NAMESPACES.contains(&namespace){return Err(bad("unapproved composition namespace"));}
    let name=parts[1].as_os_str().to_str().ok_or_else(||bad("output encoding"))?;let prefix=format!("run-{}-",std::process::id());
    let nonce=name.strip_prefix(&prefix).ok_or_else(||bad("actual current PID required"))?;
    if nonce.is_empty()||nonce.len()>39||!nonce.bytes().all(|c|c.is_ascii_digit()){return Err(bad("bounded output nonce required"));}
    let nonce=nonce.parse::<u128>().map_err(|_|bad("output nonce width"))?;let now=now_ns()?;
    if nonce>now||now-nonce>FRESH_NS{return Err(bad("fresh current output nonce required"));}
    let namespace=namespace.to_owned();if !output.is_dir(){return Err(bad("fresh directory required"));}empty(&output)?;Ok((root,output,namespace))
}

/// Call immediately AFTER fs::create_dir(output), before the first file. The
/// first file this helper writes is its proof. Any failure retains the newly
/// created directory; compression may already have applied, never claim none.
pub(crate) fn compress_fresh_output(root:&Path,output:&Path)->io::Result<()>{
    let(root,output,namespace)=scope(root,output)?;
    #[cfg(windows)]{
        let proof=win::compress(&root,&output)?;
        let value=serde_json::json!({"schema":"wot091-fresh-composition-compression.v1","root":root,"directory":output,"namespace":namespace,
            "pid":std::process::id(),"mode":"Win32 FSCTL_SET_COMPRESSION DEFAULT; directory only","filesystem":"NTFS",
            "attributes_before":proof.0,"attributes_after":proof.1,"creation_filetime_100ns":proof.2,
            "compressed":true,"empty_before":true,"recursive":false,"existing_data_compressed":false,"deleted_or_moved":false});
        use io::Write;let mut file=fs::OpenOptions::new().write(true).create_new(true).open(output.join("directory-compression.json"))?;
        file.write_all(&serde_json::to_vec_pretty(&value).map_err(|_|bad("compression proof JSON"))?)?;file.write_all(b"\n")?;file.sync_all()?;Ok(())
    }
    #[cfg(not(windows))]{let _=(root,output,namespace);Err(io::Error::new(io::ErrorKind::Unsupported,"pinned Windows NTFS composition storage required"))}
}

#[cfg(windows)]
mod win{
    use super::*;use std::{ffi::c_void,os::windows::ffi::OsStrExt};
    type Handle=*mut c_void;
    #[repr(C)]#[derive(Default,Clone,Copy)]struct FileTime{low:u32,high:u32}
    #[repr(C)]#[derive(Default)]struct Info{attributes:u32,creation:FileTime,access:FileTime,write:FileTime,volume:u32,size_high:u32,size_low:u32,links:u32,index_high:u32,index_low:u32}
    #[link(name="kernel32")]
    unsafe extern "system"{
        fn CreateFileW(name:*const u16,access:u32,share:u32,security:*mut c_void,disposition:u32,flags:u32,template:Handle)->Handle;
        fn GetFileInformationByHandle(handle:Handle,info:*mut Info)->i32;
        fn DeviceIoControl(handle:Handle,code:u32,input:*mut c_void,input_len:u32,output:*mut c_void,output_len:u32,returned:*mut u32,overlapped:*mut c_void)->i32;
        fn CloseHandle(handle:Handle)->i32;
        fn GetVolumeInformationW(root:*const u16,name:*mut u16,name_len:u32,serial:*mut u32,max_component:*mut u32,flags:*mut u32,filesystem:*mut u16,filesystem_len:u32)->i32;
        fn GetCompressedFileSizeW(name:*const u16,high:*mut u32)->u32;
        fn SetLastError(error:u32);
        fn GetLastError()->u32;
    }
    struct Owned(Handle);impl Drop for Owned{fn drop(&mut self){unsafe{CloseHandle(self.0);}}}
    fn wide(path:&Path)->io::Result<Vec<u16>>{let mut out=path.as_os_str().encode_wide().collect::<Vec<_>>();if out.contains(&0){return Err(bad("NUL path refused"));}out.push(0);Ok(out)}
    fn info(handle:Handle)->io::Result<Info>{let mut row=Info::default();if unsafe{GetFileInformationByHandle(handle,&mut row)}==0{return Err(io::Error::last_os_error());}Ok(row)}
    fn identity(row:&Info)->(u32,u32,u32){(row.volume,row.index_high,row.index_low)}
    pub(super) fn compress(root:&Path,output:&Path)->io::Result<(u32,u32,u64)>{
        let drive=wide(root.ancestors().last().ok_or_else(||bad("local volume root"))?)?;let mut filesystem=[0u16;32];let mut flags=0;
        if unsafe{GetVolumeInformationW(drive.as_ptr(),std::ptr::null_mut(),0,std::ptr::null_mut(),std::ptr::null_mut(),&mut flags,filesystem.as_mut_ptr(),32)}==0{return Err(io::Error::last_os_error());}
        let n=filesystem.iter().position(|c|*c==0).ok_or_else(||bad("filesystem name bound"))?;
        if String::from_utf16(&filesystem[..n]).map_err(|_|bad("filesystem name"))? != "NTFS"||flags&0x10==0{return Err(bad("NTFS file compression support required"));}
        let name=wide(output)?;let raw=unsafe{CreateFileW(name.as_ptr(),0xc0000000,3,std::ptr::null_mut(),3,0x02200000,std::ptr::null_mut())};
        if raw as isize == -1{return Err(io::Error::last_os_error());}let handle=Owned(raw);let before=info(handle.0)?;
        if before.attributes&0x10==0||before.attributes&0x400!=0{return Err(bad("actual nonreparse directory handle required"));}
        let created=(u64::from(before.creation.high)<<32)|u64::from(before.creation.low);
        let unix=u128::from(created.checked_sub(116444736000000000).ok_or_else(||bad("directory creation epoch"))?)*100;let now=now_ns()?;
        if unix>now||now-unix>FRESH_NS{return Err(bad("old directory refused"));}empty(output)?;
        let mut mode=1u16;let mut returned=0u32;
        if unsafe{DeviceIoControl(handle.0,0x0009c040,(&mut mode as *mut u16).cast(),2,std::ptr::null_mut(),0,&mut returned,std::ptr::null_mut())}==0{return Err(io::Error::last_os_error());}
        let after=info(handle.0)?;if identity(&before)!=identity(&after)||after.attributes&0x800==0{return Err(bad("same compressed directory identity not verified"));}
        if plain(output)?!=output{return Err(bad("directory path changed"));}empty(output)?;Ok((before.attributes,after.attributes,created))
    }
    pub(super) fn allocated(path:&Path)->io::Result<u64>{let name=wide(path)?;let mut high=0;unsafe{SetLastError(0)};let low=unsafe{GetCompressedFileSizeW(name.as_ptr(),&mut high)};
        if low==u32::MAX&&unsafe{GetLastError()}!=0{return Err(io::Error::last_os_error());}Ok((u64::from(high)<<32)|u64::from(low))}
}

#[cfg(test)]
mod tests{
    use super::*;use sha2::{Digest,Sha256};
    fn root()->PathBuf{PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..").canonicalize().unwrap()}
    fn output(namespace:&str)->PathBuf{let base=root().join("local/test-runs").join(namespace);fs::create_dir_all(&base).unwrap();let out=base.join(format!("run-{}-{}",std::process::id(),now_ns().unwrap()));fs::create_dir(&out).unwrap();out}
    #[test]fn composition_storage_fresh_ntfs_keeps_authored_bytes_and_uses_less_disk(){
        let out=output("composition-storage22");compress_fresh_output(&root(),&out).unwrap();assert_eq!(fs::read_dir(&out).unwrap().count(),1);
        let raw=vec![0u8;1024*1024];let path=out.join("authored-zeroes.bin");{use io::Write;let mut file=fs::OpenOptions::new().write(true).create_new(true).open(&path).unwrap();file.write_all(&raw).unwrap();file.sync_all().unwrap();}
        let read=fs::read(&path).unwrap();assert_eq!(read,raw);assert_eq!(Sha256::digest(&read),Sha256::digest(&raw));
        #[cfg(windows)]{assert!(win::allocated(&path).unwrap()<raw.len()as u64);use std::os::windows::fs::MetadataExt;assert_ne!(fs::metadata(&path).unwrap().file_attributes()&0x800,0);}
        let proof:serde_json::Value=serde_json::from_slice(&fs::read(out.join("directory-compression.json")).unwrap()).unwrap();assert_eq!(proof["compressed"],true);assert_eq!(proof["recursive"],false);
    }
    #[test]fn composition_storage_nonempty_refuses_without_changing_file_or_attrs(){
        let out=output("composition-storage22");let file=out.join("preserve.bin");fs::write(&file,b"AUTHORED-PRESERVE").unwrap();
        #[cfg(windows)]let attributes={use std::os::windows::fs::MetadataExt;fs::metadata(&out).unwrap().file_attributes()};
        assert!(compress_fresh_output(&root(),&out).is_err());assert_eq!(fs::read(file).unwrap(),b"AUTHORED-PRESERVE");assert!(!out.join("directory-compression.json").exists());
        #[cfg(windows)]{use std::os::windows::fs::MetadataExt;assert_eq!(fs::metadata(&out).unwrap().file_attributes(),attributes);}
    }
    #[test]fn composition_storage_foreign_namespace_and_old_pid_refuse(){
        let out=output("composition-storage22-foreign");assert!(compress_fresh_output(&root(),&out).is_err());assert_eq!(fs::read_dir(&out).unwrap().count(),0);
        let base=root().join("local/test-runs/composition-storage22");fs::create_dir_all(&base).unwrap();let other=base.join(format!("run-0-{}",now_ns().unwrap()));fs::create_dir(&other).unwrap();
        assert!(compress_fresh_output(&root(),&other).is_err());assert_eq!(fs::read_dir(other).unwrap().count(),0);
    }
    #[test]fn composition_storage_existing_windows_junction_is_readonly_refused(){
        #[cfg(windows)]{use std::os::windows::fs::MetadataExt;let path=PathBuf::from(std::env::var_os("USERPROFILE").unwrap()).join("Application Data");
            let before=fs::symlink_metadata(&path).unwrap();assert_ne!(before.file_attributes()&0x400,0);assert!(compress_fresh_output(&root(),&path).is_err());assert_eq!(fs::symlink_metadata(path).unwrap().file_attributes(),before.file_attributes());}
        #[cfg(not(windows))]panic!("pinned Windows junction required; no silent skip");
    }
}
