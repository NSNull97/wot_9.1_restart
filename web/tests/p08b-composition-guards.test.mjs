import test from 'node:test';
import assert from 'node:assert/strict';
import { allocationRecord, localSpelling } from './helpers/p08b-restart-cas.mjs';
function fixture() {
 const metadata={schema:'wot091-cargo-temp-target.v1',default_os_temp:'C:\\Users\\Own\\AppData\\Local\\Temp',
  target:'C:\\Users\\Own\\AppData\\Local\\Temp\\wot091-cargo-authored',created_utc:'2026-10-16T00:00:00+00:00',
  retained_for_audit:true,automatic_delete:false,source:'tempfile.gettempdir(); fresh mkdtemp; no caller path'};
 const output='D:\\WoT_9.1_Server\\local\\build\\server\\authored-only';
 const environment={CARGO_TARGET_DIR:metadata.target,CARGO_INCREMENTAL:'0',RUST_TEST_THREADS:'1'};
 return {origin:{output,...metadata},metadata,environment,facts:{output,target:metadata.target,temp:metadata.default_os_temp,env:{...environment}}};
}
function check(x){allocationRecord(x.origin,x.metadata,x.environment,x.facts);}
test('authored allocation metadata matches closed ABI (no filesystem/target claim)',()=>check(fixture()));
test('allocation cannot switch the output without identical origin binding',()=>{const x=fixture();x.origin.output='D:\\elsewhere';assert.throws(()=>check(x));});
test('target must remain direct child of the observed OS temp',()=>{const x=fixture();x.origin.target=x.metadata.target=x.facts.target=x.metadata.target+'\\nested';x.environment.CARGO_TARGET_DIR=x.facts.env.CARGO_TARGET_DIR=x.facts.target;assert.throws(()=>check(x));});
test('another-drive allocation cannot be relabelled as normal same-drive target',()=>{const x=fixture();x.origin.output=x.facts.output='C:\\project\\local\\build\\authored';assert.throws(()=>check(x));});
test('retention/source provenance cannot be invented',()=>{for(const key of ['automatic_delete','source']){const x=fixture();x.origin[key]=x.metadata[key]=key==='source'?'caller supplied path':true;assert.throws(()=>check(x));}});
test('unexpected environment secret key is rejected',()=>{const x=fixture();x.environment.NOT_ALLOWED='authored';x.facts.env.NOT_ALLOWED='authored';assert.throws(()=>check(x));});
test('saved target and actual inherited target must agree',()=>{const x=fixture();x.facts.env.CARGO_TARGET_DIR='C:\\another';assert.throws(()=>check(x));});
test('extra/missing metadata fields and wrong timestamp fail closed',()=>{for(const change of [x=>{x.metadata.extra=1;},x=>{delete x.origin.created_utc;},x=>{x.metadata.created_utc=x.origin.created_utc='not a timestamp';}]){const x=fixture();change(x);assert.throws(()=>check(x));}});
test('Rust verbatim local-drive path is normalized without granting UNC paths',()=>{
 assert.equal(localSpelling('\\\\?\\D:\\WoT_9.1_Server'),localSpelling('D:\\WoT_9.1_Server'));
 assert.throws(()=>localSpelling('\\\\?\\UNC\\server\\share'));
});

// Real child invocations must reach argument validation, not silently skip main.
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
const helper = fileURLToPath(new URL('./helpers/p08b-restart-cas.mjs', import.meta.url));
for (const [label,path] of [['ordinary',helper],['Windows verbatim','\\\\?\\'+helper]]) {
 test(`actual controller ${label} invocation cannot skip its main entrypoint`,()=>{
  const result=spawnSync(process.execPath,[path],{encoding:'utf8',windowsHide:true,timeout:10000});
  assert.equal(result.error,undefined);
  assert.notEqual(result.status,0,'Missing --parent-full must reject before any SQL/HTTP action');
  assert.match(result.stderr,/regular parent full-suite context/);
 });
}
