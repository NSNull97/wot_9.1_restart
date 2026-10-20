/** Real SQLite reader/startup checks. Deliberately authored malformed schema;
 * no account ownership, HTTP traffic or native acceptance is inferred. */
import test from 'node:test';
import { spawnSync } from 'node:child_process';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { readFileSync,writeFileSync,mkdtempSync,mkdirSync } from 'node:fs';
import { dirname,join,resolve } from 'node:path';
import { fileURLToPath,pathToFileURL } from 'node:url';
import { createHash,randomBytes } from 'node:crypto';
const HERE=dirname(fileURLToPath(import.meta.url)),ROOT=resolve(HERE,'../..');
const {lateReaderFence,LATE_POLICY_SHA256}=await import(pathToFileURL(join(ROOT,'web/src/p08c-late-results.mjs')));
const {createIdentityBridge}=await import(pathToFileURL(join(ROOT,'web/src/game-adapter.mjs')));
const source=JSON.parse(readFileSync(join(ROOT,'local/night-staging/20261016/p10b-selection-http01/seed01/seed.json')));
const hash=v=>createHash('sha256').update(v).digest('hex');
const owner=source.profiles[0].account_id;
const catalog=(()=>{const d=new DatabaseSync(source.database,{readOnly:true});try{return d.prepare('SELECT * FROM p09e_schema').get();}finally{d.close();}})();
const open=(path,action)=>{const d=new DatabaseSync(path);try{return action(d);}finally{d.close();}};
const EVIDENCE=join(ROOT,'local/test-runs/p08b-owner-hold-reader-guard');mkdirSync(EVIDENCE,{recursive:true});
function fixture(kind='valid'){
 const directory=mkdtempSync(join(EVIDENCE,'run-')),database=join(directory,'game.sqlite');
 open(database,d=>{
  d.exec('PRAGMA user_version=1;CREATE TABLE game_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);CREATE TABLE game_profiles(native_id INTEGER PRIMARY KEY AUTOINCREMENT,account_id TEXT NOT NULL UNIQUE,profile_json TEXT NOT NULL);CREATE TABLE game_limits(key_hash TEXT PRIMARY KEY,hits INTEGER NOT NULL,resets_at INTEGER NOT NULL);CREATE TABLE p09e_schema(version TEXT PRIMARY KEY,catalog_sha256 TEXT NOT NULL,policy_sha256 TEXT NOT NULL);');
  d.prepare('INSERT INTO p09e_schema VALUES (?,?,?)').run(catalog.version,catalog.catalog_sha256,catalog.policy_sha256);
  d.exec('CREATE TABLE p08c_late_schema(version TEXT PRIMARY KEY,policy_sha256 TEXT NOT NULL,catalog_sha256 TEXT NOT NULL);');
  d.prepare('INSERT INTO p08c_late_schema VALUES (?,?,?)').run('p08c-late-results.v1',LATE_POLICY_SHA256,kind==='wrong-catalog'?'0'.repeat(64):catalog.catalog_sha256);
  if(kind!=='partial')d.exec('CREATE TABLE p08c_late_seal(run_id TEXT,battle_id TEXT,arena_id TEXT,seal_json TEXT,seal_sha256 TEXT);CREATE TABLE p08c_late_result(account_id TEXT,arena_id TEXT,acked INTEGER);CREATE TABLE p08c_late_command(account_id TEXT,command_key TEXT);');
 });
 return{directory,database};
}
function unchanged(path,before){assert.equal(hash(readFileSync(path)),before);open(path,d=>{assert.equal(d.prepare('PRAGMA journal_mode').get().journal_mode,'delete');assert.equal(d.prepare("SELECT count(*) AS n FROM game_meta WHERE key='native_descriptors_sha256'").get().n,0);});}
test('valid late marker is bound to the actual stored research catalog and remains readonly',()=>{
 const f=fixture(),before=hash(readFileSync(f.database));assert.doesNotThrow(()=>lateReaderFence(f.database,[owner]));unchanged(f.database,before);
});
test('well-shaped foreign catalog marker is refused before any reader result',()=>{
 const f=fixture('wrong-catalog'),before=hash(readFileSync(f.database));assert.throws(()=>lateReaderFence(f.database,[owner]),/actual catalog binding/);unchanged(f.database,before);
});
test('partial existing late namespace refuses without mutation',()=>{
 const f=fixture('partial'),before=hash(readFileSync(f.database));assert.throws(()=>lateReaderFence(f.database,[owner]),/reader namespace/);unchanged(f.database,before);
});
test('actual selected bridge startup refuses partial old late namespace BEFORE openGameStore WAL/meta writes',{timeout:15000},async()=>{
 const f=fixture('partial'),before=hash(readFileSync(f.database)),identity=join(f.directory,'identity.sqlite'),tokenFile=join(f.directory,'token.private');
 open(identity,d=>d.exec('PRAGMA user_version=2;CREATE TABLE users(id TEXT PRIMARY KEY,username TEXT,display_nickname TEXT,email TEXT,password_hash TEXT,created_at INTEGER);'));
 writeFileSync(tokenFile,randomBytes(32).toString('base64url'),{flag:'wx',mode:0o600});
 const crew=await import(pathToFileURL(join(ROOT,'web/src/p04d-crew.mjs'))),barracks=await import(pathToFileURL(join(ROOT,'web/src/p04k-crew.mjs'))),research=await import(pathToFileURL(join(ROOT,'web/src/p09e-research.mjs'))),battle=await import(pathToFileURL(join(ROOT,'web/src/p08b-battle.mjs'))),pool=await import(pathToFileURL(join(ROOT,'web/src/p04m-pool.mjs'))),mixed=await import(pathToFileURL(join(ROOT,'web/src/p06t-mixed.mjs'))),loss=await import(pathToFileURL(join(ROOT,'web/src/p06t-ammo-loss.mjs')));
 const options={version:1,port:0,web_database:identity,game_database:f.database,fixture_root:join(f.directory,'fixtures'),native_descriptors:join(source.bundle,'content/inputs/native-ms1.blob'),python_executable:spawnSync('python',['-B','-c','import sys;print(sys.executable)'],{encoding:'utf8',windowsHide:true}).stdout.trim(),token_file:tokenFile,
  ammunition_service:{version:1,bundle_root:source.bundle,original_root:source.original,account_id:owner,grant:{grant_id:'p09d-test-depot-v1',quantity_each:100}},
  crew_service:{version:1,policy_sha256:crew.CREW_POLICY_SHA256},crew_transfer:{version:1,policy_sha256:crew.TRANSFER_POLICY_SHA256},crew_cross_vehicle:{version:1,policy_sha256:crew.CROSS_CREW_POLICY_SHA256},crew_roster_recruitment:{version:1,policy_sha256:crew.ROSTER_CREW_POLICY_SHA256},crew_progression:{version:1,policy_sha256:crew.PROGRESSION_CREW_POLICY_SHA256},crew_dismissal:{version:1,policy_sha256:crew.DISMISSAL_CREW_POLICY_SHA256},crew_barracks_recruitment:{version:1,policy_sha256:barracks.BARRACKS_CREW_POLICY_SHA256},research_service:{version:1,policy_sha256:research.RESEARCH_POLICY_SHA256},
  battle_service:{version:1,policy_sha256:battle.BATTLE_POLICY_SHA256,accounts:[owner]},pool_service:{version:1,policy_sha256:pool.POOL_POLICY_SHA256,accounts:[owner]},mixed_service:{version:2,policy_sha256:mixed.MIXED_POLICY_SHA256,accounts:[owner],shell_catalog:join(ROOT,'tests/fixtures/p06t-shell-catalog.json'),terminal_policy:join(ROOT,'tests/fixtures/p06t-device-policy.json')},ammo_loss_service:{version:4,contract:loss.LOSS_CONTRACT,policy_sha256:loss.LOSS_POLICY_SHA256,accounts:[owner]},owner_hold_service:{version:5,contract:'p08b-owner-battle-hold.v1',policy_sha256:'98cdc5d657e4cdf30225c26913f2c70a89865de9ae2bb97704fa4b623efd806e',accounts:[owner]}};
 assert.equal(typeof options.python_executable,'string');await assert.rejects(createIdentityBridge(options),/Late result reader namespace/);unchanged(f.database,before);
 writeFileSync(join(f.directory,'result.json'),JSON.stringify({status:'PASS_ACTUAL_FACTORY_REFUSAL_BEFORE_GAME_STORE_MUTATION',source_database_unchanged:true,live_http_listener:'NOT_STARTED',native:'NOT_RUN',game_db_sha256:before})+'\n',{flag:'wx'});
});
