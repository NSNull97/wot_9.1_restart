from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import contextlib,copy,hashlib,io,json,math,os,socket,sqlite3,subprocess,sys,unittest
from tools import content0_s5a_launch as launch
from tools import content0_s5a_scene_apply as apply
from tools.content0_s5a_stand_lock import StandLock

DOC=json.loads(apply.DOC.read_text(encoding='utf8'))
def digest(v):return hashlib.sha256(v).hexdigest()
class SceneTests(unittest.TestCase):
    def test_all_scenes_net_modes_ally_modes_and_cycle(self):
        for name in ('field180','field200','bush180'):
            for net in (False,True):
                for ally in ('team','isolated'):
                    static=apply.make_scenario(DOC,name,net,ally,'static');cycle=apply.make_scenario(DOC,name,net,ally,'cycle')
                    self.assertEqual(len(static['seats']),4);self.assertEqual(static['events'],[])
                    self.assertEqual([s['net'] for s in static['seats']],[False,net,net,net])
                    self.assertEqual([s['crew_percent'] for s in static['seats']],[None,100,100,100])
                    self.assertEqual(static['seats'][2]['position'],DOC['common_positions']['ally' if ally=='team' else 'ally_isolated'])
                    self.assertEqual([e['action'] for e in cycle['events']],['forward','stop','left','stop','shoot'])
                    self.assertEqual([e['tick'] for e in cycle['events']],[120,130,240,250,360])
        broken=copy.deepcopy(DOC);broken['scenes']['field180']['target']=broken['scenes']['field180']['observer']
        with self.assertRaises(ValueError):apply.make_scenario(broken,'field180',True,'team','static')

    def test_lock_is_exclusive(self):
        with TemporaryDirectory() as raw:
            stand=Path(raw)
            with StandLock(stand):
                with self.assertRaises(OSError):
                    with StandLock(stand):pass
            with StandLock(stand):pass

    def test_incomplete_or_failed_launch_with_live_worker_is_refused(self):
        class Gone(OSError): winerror=87
        for status in ('STARTING','FAILED_STOPPED_OWN_CHILDREN'):
            with TemporaryDirectory() as raw:
                stand=Path(raw);launch=stand/'launches'/'run';launch.mkdir(parents=True)
                log=launch/'gateway.stdout.log';log.write_text('BW01_WORKER_STARTED pid=12\n')
                exe=stand/'gateway.exe';exe.write_bytes(b'test')
                (launch/'processes.json').write_text(json.dumps({'status':status,'processes':[{'kind':'gateway','pid':11,'creation_filetime':100,'exe':str(exe),'stdout':str(log)}]}))
                def identity(pid):
                    if pid==11:raise Gone()
                    if pid==12:return {'creation_filetime':101,'image':str(exe)}
                    raise AssertionError(pid)
                with patch.object(apply,'process_identity',side_effect=identity),patch.object(apply,'current_boot_filetime',return_value=100):
                    with self.assertRaisesRegex(ValueError,'worker remains'):apply.no_own_processes(stand)

    def test_legacy_receipt_lacking_creation_refuses_live_pid(self):
        with TemporaryDirectory() as raw:
            stand=Path(raw);launch=stand/'launches'/'run';launch.mkdir(parents=True)
            (launch/'processes.json').write_text(json.dumps({'status':'FAILED_STOPPED_OWN_CHILDREN','processes':[{'kind':'domain','pid':11}]}))
            with patch.object(apply,'process_identity',return_value={'creation_filetime':101,'image':'irrelevant'}):
                with self.assertRaisesRegex(ValueError,'lacks creation identity'):apply.no_own_processes(stand)

    def test_inaccessible_pid_requires_proof_of_previous_boot(self):
        class Denied(PermissionError):winerror=5
        class Unqueryable(OSError):winerror=31
        class Gone(OSError):winerror=87

        for denied_pid in (21,22):
            for created in (99,100,101,0,None):
                with self.subTest(denied_pid=denied_pid,created=created),TemporaryDirectory() as raw:
                    stand=Path(raw);launch_dir=stand/'launches'/'old';launch_dir.mkdir(parents=True)
                    log=launch_dir/'gateway.stdout.log';log.write_text('BW01_WORKER_STARTED pid=22\n')
                    gateway={'kind':'gateway','pid':21,'stdout':str(log),'exe':str(stand/'gateway.exe')}
                    if created is not None:gateway['creation_filetime']=created
                    (launch_dir/'processes.json').write_text(json.dumps({'status':'FAILED_STOPPED_OWN_CHILDREN','processes':[gateway]}))

                    def identity(pid):
                        if pid==denied_pid:raise (Denied if pid==21 else Unqueryable)()
                        raise Gone()

                    with patch.object(apply,'process_identity',side_effect=identity),\
                         patch.object(apply,'current_boot_filetime',return_value=100),\
                         patch.object(apply.subprocess,'run',return_value=subprocess.CompletedProcess([],0,stdout='')):
                        if created==99:apply.no_own_processes(stand)
                        else:
                            with self.assertRaises(Denied if denied_pid==21 else Unqueryable):apply.no_own_processes(stand)

    def test_scene_run_junction_or_symlink_refused_before_marker(self):
        with TemporaryDirectory() as raw:
            root=Path(raw);stand,_=self.fixture(root,self.ports());outside=root/'outside';outside.mkdir()
            try:(stand/'scene-runs').symlink_to(outside,target_is_directory=True)
            except OSError:
                if os.name!='nt':raise
                result=subprocess.run(['cmd','/c','mklink','/J',str(stand/'scene-runs'),str(outside)],capture_output=True)
                if result.returncode:self.skipTest('junction creation unavailable')
            args=['scene','--stand',str(stand),'--scene','field180','--net','on','--ally','team','--script','static']
            with patch.object(apply,'ROOT',root),patch.object(apply,'verify_sources',return_value=None),patch.object(apply,'no_own_processes'),patch.object(sys,'argv',args):
                with self.assertRaisesRegex(ValueError,'linked resource'):apply.main()
            self.assertFalse((stand/'scene-update-in-progress.json').exists());self.assertEqual(list(outside.iterdir()),[])

    def test_assist_requires_three_allies_network_and_delayed_server_aim(self):
        scene=apply.make_scenario(DOC,'assist6',True,'team','assist-shot')
        self.assertEqual([s['kind'] for s in scene['seats']],['human','china-Ch17_WZ131_1_WZ132','france-AMX_13_75','usa-T71','t34','france-AMX_13_75'])
        self.assertEqual(scene['events'],[{'tick':40,'slot':4,'action':'aim_target','target_slot':1},{'tick':100,'slot':4,'action':'shoot_shared','target_slot':1}])
        self.assertEqual([s['net'] for s in scene['seats']],[False,True,True,True,True,True])
        for net,ally,script in ((False,'team','assist-shot'),(True,'isolated','assist-shot'),(True,'team','cycle')):
            with self.assertRaises(ValueError):apply.make_scenario(DOC,'assist6',net,ally,script)
        with self.assertRaises(ValueError):apply.make_scenario(DOC,'field180',True,'team','assist-shot')

    def test_bush142_shot_keeps_same_poses_and_never_moves(self):
        still=apply.make_scenario(DOC,'bush142',True,'isolated','static')
        fire=apply.make_scenario(DOC,'bush142',True,'isolated','bush-shot')
        self.assertEqual(fire['seats'],still['seats'])
        self.assertAlmostEqual(math.dist(still['seats'][0]['position'],still['seats'][1]['position']),142,places=2)
        self.assertEqual(fire['events'],[{'tick':120,'slot':1,'action':'shoot'}])
        with self.assertRaises(ValueError):apply.make_scenario(DOC,'bush142',True,'isolated','cycle')
        with self.assertRaises(ValueError):apply.make_scenario(DOC,'bush180',True,'isolated','bush-shot')
        broken=copy.deepcopy(DOC);broken['bush_shot']['events'][0]['slot']=0
        with self.assertRaisesRegex(ValueError,'unrecognised bush shot'):
            apply.make_scenario(broken,'bush142',True,'isolated','bush-shot')

    def fixture(self,root,ports):
        local=root/'local';stand=local/'stands'/'test';stand.mkdir(parents=True)
        database=stand/'game.sqlite'
        with contextlib.closing(sqlite3.connect(database)) as c:
            c.execute('create table game_snapshot(account_id text)');c.execute("insert into game_snapshot values ('test-owner')")
            c.execute('create table game_profiles(native_id integer,account_id text)');c.execute("insert into game_profiles values (5,'test-owner')");c.commit()
        (stand/'receipt.json').write_text(json.dumps({'schema':'content0-s5a-clean-operator.v1','account_id':'test-owner','game_database':str(database),'native_database_id':5}))
        values={'domain':{'database':str(database)},'bridge':{'game_database':str(database)},'gateway':{'fixed_scout_v1':{},'bots':{'kinds':[]}}}
        hashes={}
        for name,value in values.items():
            raw=json.dumps(value).encode();(stand/(name+'.json')).write_bytes(raw);hashes[name]=digest(raw)
        profile=b'{"version":5}';(stand/'battle-profiles.json').write_bytes(profile)
        (stand/'snapshot-receipt.json').write_text(json.dumps({'ports':ports,'status':'STAGED_NOT_READY'}))
        (stand/'config-receipt.json').write_text(json.dumps({'status':'CONFIGURED_NOT_LAUNCHED','operator':'test-owner','config_sha256':hashes,'battle_profiles_sha256':digest(profile)}))
        return stand,database

    def ports(self):
        sockets=[];numbers=[]
        try:
            for _ in range(5):
                s=socket.socket();s.bind(('127.0.0.1',0));sockets.append(s);numbers.append(s.getsockname()[1])
        finally:
            for s in sockets:s.close()
        return dict(zip(('login','base','bridge','domain','guard'),numbers))

    def test_stopped_apply_backs_up_and_rebinds_without_touching_source(self):
        with TemporaryDirectory() as raw:
            root=Path(raw);stand,source=self.fixture(root,self.ports());before=digest(source.read_bytes())
            args=['scene','--stand',str(stand),'--scene','field200','--net','on','--ally','isolated','--script','cycle']
            with patch.object(apply,'ROOT',root),patch.object(apply,'verify_sources',return_value=None),patch.object(apply,'no_own_processes'),patch.object(sys,'argv',args),contextlib.redirect_stdout(io.StringIO()):apply.main()
            self.assertEqual(digest(source.read_bytes()),before);domain=json.loads((stand/'domain.json').read_text());bridge=json.loads((stand/'bridge.json').read_text());gateway=json.loads((stand/'gateway.json').read_text());receipt=json.loads((stand/'config-receipt.json').read_text())
            self.assertEqual(domain['database'],bridge['game_database']);self.assertNotEqual(Path(domain['database']),source);self.assertTrue(Path(domain['database']).is_file())
            self.assertEqual(receipt['scene']['classification'],'INFERRED_NOT_JOLT_OR_NATIVE_VERIFIED');self.assertEqual(receipt['scene']['name'],'field200')
            self.assertEqual(gateway['fixed_scout_v1']['seats'][2]['position'],DOC['common_positions']['ally_isolated']);self.assertEqual(len(gateway['fixed_scout_v1']['events']),5)
            self.assertFalse((stand/'scene-update-in-progress.json').exists())
            run=Path(domain['database']).parent;self.assertTrue((run/'scene-receipt.json').is_file());self.assertEqual(json.loads((run/'domain.before.json').read_text())['database'],str(source))

    def test_occupied_port_refuses_before_writing_anything(self):
        with TemporaryDirectory() as raw, socket.socket() as listener:
            listener.bind(('127.0.0.1',0));listener.listen();ports=self.ports();ports['bridge']=listener.getsockname()[1]
            root=Path(raw);stand,_=self.fixture(root,ports);before={str(p.relative_to(stand)):digest(p.read_bytes()) for p in stand.rglob('*') if p.is_file()}
            args=['scene','--stand',str(stand),'--scene','field180','--net','off','--ally','team','--script','static']
            with patch.object(apply,'ROOT',root),patch.object(sys,'argv',args):
                with self.assertRaises(OSError):apply.main()
            after={str(p.relative_to(stand)):digest(p.read_bytes()) for p in stand.rglob('*') if p.is_file()};self.assertEqual(before,after)

    def test_stacked_foliage_is_opt_in_bound_and_preserves_legacy_source(self):
        with TemporaryDirectory() as raw:
            root=Path(raw);stand,source=self.fixture(root,self.ports())
            legacy=stand/'foliage.json'
            geometry={'instances':[{'center_world':[10,2,0],'concealment_additive':0.2}]}
            legacy_raw=json.dumps({**geometry,'schema':'content0-s5a-malinovka-bush-volumes.v1','effect_contract':'old'}).encode()
            legacy.write_bytes(legacy_raw)
            expected=(json.dumps({**geometry,'schema':'content0-s5a-malinovka-bush-volumes.v2',
                'effect_contract':'project v2: sum crossed shrubs; omit observer-near shrubs; while firing add only the strongest target-near shrub after fire attenuation'},
                sort_keys=True,separators=(',',':'))+'\n').encode()
            legacy_binding={'version':1,'file':str(legacy),'sha256':digest(legacy_raw)}
            config_path=stand/'config-receipt.json';gateway_path=stand/'gateway.json'
            config=json.loads(config_path.read_bytes());gateway=json.loads(gateway_path.read_bytes())
            gateway['foliage_v1']=legacy_binding;gateway_raw=json.dumps(gateway).encode();gateway_path.write_bytes(gateway_raw)
            config['config_sha256']['gateway']=digest(gateway_raw);config_path.write_text(json.dumps(config))
            args=['scene','--stand',str(stand),'--scene','bush180','--net','on','--ally','isolated','--script','static']
            pinned_doc=root/'source.json';pinned_doc.write_text(json.dumps({'source_pins':{'foliage_sha256':digest(legacy_raw)}}))

            def verify(stand_path, doc, gateway_data, receipt, enable):
                return apply.verify_foliage(stand_path,gateway_data['foliage_v1'],receipt.get('stacked_foliage'),digest(legacy_raw),enable)

            with patch.object(apply,'ROOT',root),patch.object(apply,'verify_sources',side_effect=verify),\
                 patch.object(apply,'FOLIAGE_STACKED_SHA256',digest(expected)),patch.object(apply,'no_own_processes'),\
                 patch.object(launch,'ROOT',root),patch.object(launch,'SCENE_DOC',pinned_doc),\
                 patch.object(launch,'FOLIAGE_STACKED_SHA256',digest(expected)),contextlib.redirect_stdout(io.StringIO()):
                with patch.object(sys,'argv',args+['--stacked-foliage','--legacy-foliage']),\
                     contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):apply.main()
                with patch.object(sys,'argv',args):apply.main()
                self.assertEqual(json.loads(gateway_path.read_bytes())['foliage_v1'],legacy_binding)
                self.assertNotIn('stacked_foliage',json.loads(config_path.read_bytes()))

                with patch.object(sys,'argv',args+['--stacked-foliage']):apply.main()
                activated=json.loads(gateway_path.read_bytes())['foliage_v1'];active_file=Path(activated['file'])
                self.assertEqual(active_file.read_bytes(),expected)
                self.assertEqual(activated['sha256'],digest(expected))
                activation_config=json.loads(config_path.read_bytes())
                activation_proof=json.loads((active_file.parent/'scene-receipt.json').read_bytes())
                self.assertEqual(activation_proof['foliage'],activation_config['stacked_foliage'])
                self.assertEqual(activation_config['stacked_foliage']['legacy_file'],str(legacy))
                launch.verify_stacked_foliage_binding(stand,activation_config,{'foliage_v1':activated})
                with self.assertRaisesRegex(ValueError,'configuration receipt missing'):
                    launch.verify_stacked_foliage_binding(stand,{}, {'foliage_v1':activated})

                with patch.object(sys,'argv',args):apply.main()
                self.assertEqual(json.loads(gateway_path.read_bytes())['foliage_v1'],activated)
                self.assertEqual(legacy.read_bytes(),legacy_raw)
                self.assertTrue(source.is_file())
                active_file.write_bytes(expected+b' ')
                with patch.object(sys,'argv',args),self.assertRaisesRegex(ValueError,'foliage hash mismatch'):
                    apply.main()
                with self.assertRaisesRegex(ValueError,'foliage hash mismatch'):
                    launch.verify_stacked_foliage_binding(stand,activation_config,{'foliage_v1':activated})
                self.assertFalse((stand/'scene-update-in-progress.json').exists())
                active_file.write_bytes(expected)

                current=Path(json.loads((stand/'domain.json').read_bytes())['database'])
                with contextlib.closing(sqlite3.connect(current)) as db:
                    db.execute('PRAGMA user_version=39')
                with patch.object(sys,'argv',args+['--legacy-foliage']):apply.main()
                rolled_back=Path(json.loads((stand/'domain.json').read_bytes())['database'])
                self.assertNotEqual(rolled_back,current)
                with contextlib.closing(sqlite3.connect(rolled_back)) as db:
                    self.assertEqual(db.execute('PRAGMA user_version').fetchone(),(39,))
                self.assertEqual(json.loads(gateway_path.read_bytes())['foliage_v1'],legacy_binding)
                self.assertNotIn('stacked_foliage',json.loads(config_path.read_bytes()))
                self.assertEqual(json.loads((rolled_back.parent/'scene-receipt.json').read_bytes())['foliage']['schema'],apply.FOLIAGE_SCHEMA_V1)

                with patch.object(sys,'argv',args+['--stacked-foliage']):apply.main()
                reactivated=json.loads(gateway_path.read_bytes())['foliage_v1']
                self.assertNotEqual(reactivated['file'],activated['file'])
                self.assertEqual(Path(reactivated['file']).read_bytes(),expected)
                self.assertEqual(active_file.read_bytes(),expected)
                self.assertEqual(legacy.read_bytes(),legacy_raw)

    def test_assist_apply_sets_six_seats_and_unique_bot_plan(self):
        with TemporaryDirectory() as raw:
            root=Path(raw);stand,_=self.fixture(root,self.ports())
            args=['scene','--stand',str(stand),'--scene','assist6','--net','on','--ally','team','--script','assist-shot']
            with patch.object(apply,'ROOT',root),patch.object(apply,'verify_sources',return_value=None),patch.object(apply,'no_own_processes'),patch.object(sys,'argv',args),contextlib.redirect_stdout(io.StringIO()):apply.main()
            gateway=json.loads((stand/'gateway.json').read_text())
            self.assertEqual((gateway['battle_players'],gateway['connection_capacity']),(6,6))
            self.assertEqual(len(gateway['bots']['kinds']),len(set(gateway['bots']['kinds'])))
            self.assertEqual(set(gateway['bots']['kinds']),{seat['kind'] for seat in gateway['fixed_scout_v1']['seats'][1:]})

    def test_backup_failure_leaves_marker_and_previous_configs(self):
        with TemporaryDirectory() as raw:
            root=Path(raw);stand,_=self.fixture(root,self.ports());before=(stand/'gateway.json').read_bytes();args=['scene','--stand',str(stand),'--scene','bush180','--net','on','--ally','team','--script','static']
            with patch.object(apply,'ROOT',root),patch.object(apply,'verify_sources',return_value=None),patch.object(apply,'no_own_processes'),patch.object(apply,'backup_database',side_effect=OSError('test')),patch.object(sys,'argv',args):
                with self.assertRaises(OSError):apply.main()
            self.assertTrue((stand/'scene-update-in-progress.json').is_file());self.assertEqual((stand/'gateway.json').read_bytes(),before)
