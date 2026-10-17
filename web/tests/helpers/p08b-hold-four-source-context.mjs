/** Closed test-only source/C-context distinction. Passive import, no SQL/writes. */
import assert from 'node:assert/strict';
import {readFileSync,lstatSync,realpathSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {resolve,relative,isAbsolute,dirname,join} from 'node:path';
export const ORIGINAL_ROOT='D:/WoT_9.1_Server',SHORT_ROOT='C:/wot091-night-20261017-01/w';
const ALLOCATION='C:/Users/NSNull/AppData/Local/Temp/wot091-night-workspace-kcadgetk/short-workspace01/allocation.json';
const ALLOCATION_SHA='677765e23e8de12beb02bfb1b57574e7f528bfe27d872582371f6037db89199e';
const CONTEXT='C:/Users/NSNull/AppData/Local/Temp/wot091-night-workspace-kcadgetk/dependencies-short02/resource-context.json';
const CONTEXT_SHA='a44579f46813ab449ee8107880e50ff11d1d7a68775abbd764683e6aed1a79bc';
export const SOURCE_SPECS=[
 ['local/evidence/20261016-p06t-owned01/seed01/seed.json','56ecea1b3548a13efbac9d3870ee27fa96dc639557b124bd608a0abbcffe0e4b','f4c7f9174b208e9c42d6668cf7796a9026693c1ebea87bbd0eeeadd581f2debf'],
 ['local/night-staging/20261016/p10b-selection-http01/seed01/seed.json','50d4c10623d94b63a50621650429b34beffdbc48dee2176028e2f62b07da3287','a04216d90e8e9e8b379fc2d34a0fed9f400e373d8d4c591d723bb00a1accc2cf'],
];
const sha=raw=>createHash('sha256').update(raw).digest('hex');
function plain(value){
 assert.ok(isAbsolute(value)&&!value.startsWith('\\\\')&&!value.split(/[\\/]/).includes('..'),'C33_ABSOLUTE_LOCAL');
 let p=resolve(value);for(let q=p;;q=dirname(q)){assert.equal(lstatSync(q).isSymbolicLink(),false,'C33_LINK');if(dirname(q)===q)break;}
 return realpathSync.native(p);
}
function read(path,limit){const p=plain(path),size=lstatSync(p).size;assert.ok(size>0&&size<=limit,'C33_BOUNDED_INPUT');const raw=readFileSync(p);assert.equal(raw.length,size);return raw;}
function closedRoot(root){
 const actual=plain(root);assert.ok([ORIGINAL_ROOT,SHORT_ROOT].map(p=>resolve(p)).includes(actual),'C33_CLOSED_ROOT');
 if(actual===resolve(SHORT_ROOT)){
  const raw=read(ALLOCATION,4096);assert.equal(sha(raw),ALLOCATION_SHA,'C33_ALLOCATION_PIN');const a=JSON.parse(raw);
  assert.equal(a.schema,'wot091-fresh-short-workspace.v1');assert.equal(resolve(a.workspace),actual);assert.equal(resolve(a.source_root),resolve(ORIGINAL_ROOT));
  assert.equal(a.source_head,'3675a486e3cadee5fd08277dee97e32a7d909a02');assert.equal(a.old_data_touched,false);
 }
 return actual;
}
export function deriveMetadata(originalRaw,root){
 assert.ok([ORIGINAL_ROOT,SHORT_ROOT].map(p=>resolve(p)).includes(resolve(root)),'C33_CLOSED_ROOT');
 const original=JSON.parse(originalRaw),changed={...original};let text=originalRaw.toString('utf8');
 for(const key of ['database','bundle']){
  const suffix=relative(resolve(ORIGINAL_ROOT),resolve(original[key]));assert.ok(suffix&&!suffix.startsWith('..')&&!isAbsolute(suffix)&&suffix.split(/[\\/]/)[0]==='local','C33_METADATA_RUNTIME_SCOPE');
  const value=join(root,suffix),token=JSON.stringify(original[key]),replacement=JSON.stringify(value);assert.equal(text.split(token).length-1,1,'C33_METADATA_TOKEN_COUNT');text=text.replace(token,replacement);changed[key]=value;
 }
 assert.deepEqual(JSON.parse(text),changed);return Buffer.from(text,'utf8');
}
export function validateMetadataBytes(original,current,root){
 assert.ok([ORIGINAL_ROOT,SHORT_ROOT].map(p=>resolve(p)).includes(resolve(root)),'C33_CLOSED_ROOT');
 const expected=resolve(root)===resolve(ORIGINAL_ROOT)?original:deriveMetadata(original,root);
 assert.deepEqual(current,expected,'C33_DERIVED_METADATA_BYTES');return JSON.parse(current);
}
export function sourceContext(index,root,seedPath){
 assert.ok(Number.isInteger(index)&&index>=0&&index<2,'C33_INDEX');const runtime=closedRoot(root),[rel,originalSHA,dbSHA]=SOURCE_SPECS[index];
 const originalPath=plain(join(ORIGINAL_ROOT,rel)),original=read(originalPath,65536);assert.equal(sha(original),originalSHA,'C33_ORIGINAL_METADATA_PIN');
 const path=plain(seedPath);assert.equal(path,plain(join(runtime,rel)),'C33_EXACT_CONTEXT_SEED');const raw=read(path,65536);
 const metadata=validateMetadataBytes(original,raw,runtime);
 const database=plain(metadata.database);assert.equal(database,join(dirname(path),'game.sqlite'));assert.equal(sha(read(database,16*1024*1024)),dbSHA,'C33_CONTEXT_DB_PIN');
 if(runtime===resolve(SHORT_ROOT)){
  const context=read(CONTEXT,1024*1024);assert.equal(sha(context),CONTEXT_SHA,'C33_RESOURCE_CONTEXT_PIN');const row=JSON.parse(context).files[rel];
  assert.equal(row.source_sha256,originalSHA);assert.equal(row.sha256,sha(raw));assert.equal(plain(row.path),path);assert.equal(plain(row.source),originalPath);
  assert.equal(row.kind,'seed');assert.deepEqual([...row.changes].sort(),['/bundle','/database']);
 }
 return {metadata,context_seed:{path,sha256:sha(raw),original_sha256:originalSHA,derivation:runtime===resolve(ORIGINAL_ROOT)?'original-source':'short-c-runtime-paths.v1'},original_path:originalPath};
}
