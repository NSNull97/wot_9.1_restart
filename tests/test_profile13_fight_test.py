"""One-shot test control and screenshot bookkeeping, no native battle claimed."""
import ast
import hashlib
import os
import sys
import tempfile
import traceback
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'client_patch'))
import profile13_fight_test as fight

ACCOUNT='12345678-1234-4234-8234-123456789abc'
SHA=hashlib.sha256(b'descriptor').hexdigest()


def config():
    return {'account':ACCOUNT,'database_id':5,'inventory_id':1,'compact_id':3329,
            'descriptor_sha256':SHA,'timeout_seconds':120,'screenshot':True}


def settings():
    return {'enable_profile13_battle':True,'enable_profile13_fight_test':True,
            'visibility_debug':{'account':ACCOUNT},
            'profile13_fight_binding':{'account':ACCOUNT,'database_id':5,'receipt_sha256':'a'*64}}


class FakeNative:
    def __init__(self):
        self.button=object();self.clicks=0;self.fail=False;self.snapshot=None;self.path=None
    def checked_button(self):return self.button
    def captcha(self):return {'safe':True}
    def click(self,owner):
        assert owner==id(self.button);self.clicks+=1
        if self.fail:raise RuntimeError('after enqueue')
    def rendered_snapshot(self):return self.snapshot
    def screenshot_file(self,basename):return self.path


class FightTest(unittest.TestCase):
    def make(self,native):
        self.events=[];self.shots=[];self.clock=[1.]
        return fight.Scenario(config(),settings(),native,
                              lambda name,**fields:self.events.append((name,fields)),
                              lambda:self.clock[0],self.shots.append)

    def test_requires_explicit_operator_test_and_bounded_identity(self):
        self.assertEqual(fight.checked(config(),settings()),config())
        for key,value in (('account','foreign'),('database_id',True),('inventory_id',0),
                          ('compact_id',65536),('descriptor_sha256','bad'),
                          ('timeout_seconds',301),('screenshot',False)):
            bad=config();bad[key]=value
            with self.subTest(key=key):
                with self.assertRaises(ValueError):fight.checked(bad,settings())
        off=settings();off.pop('enable_profile13_fight_test')
        with self.assertRaises(ValueError):fight.checked(config(),off)
        wrong=settings();wrong['profile13_fight_binding']['database_id']=6
        with self.assertRaises(ValueError):fight.checked(config(),wrong)

    def test_click_is_once_then_waits_for_rendered_tick_and_saved_png(self):
        native=FakeNative();scenario=self.make(native)
        scenario.tick();self.assertEqual(native.clicks,0)
        scenario.tick(hangar_ready=True);scenario.tick(hangar_ready=True)
        self.assertEqual(native.clicks,1)
        scenario.tick(avatar=True);self.assertEqual(self.shots,[])
        native.snapshot={'tick':123,'battle':'42','run':'run'}
        scenario.tick(avatar=True);self.assertEqual(self.shots,['visibility_test_%d_42_123' % os.getpid()])
        native.path='owned/'+self.shots[0]+'_123.png';scenario.tick(avatar=True)
        self.assertTrue(scenario.done)
        saved=[fields for name,fields in self.events if name=='profile13_screenshot_saved'][0]
        self.assertEqual((saved['scan_tick'],saved['path'],saved['visual_review']),
                         (123,native.path,'NOT_RUN'))
        self.assertEqual(saved['screenshot_frame_tick'],'MAY_ADVANCE')

    def test_throw_after_callback_never_clicks_again_and_timeout_never_quits(self):
        native=FakeNative();native.fail=True;scenario=self.make(native)
        scenario.tick(hangar_ready=True);scenario.tick(hangar_ready=True)
        self.assertEqual(native.clicks,1)
        self.assertTrue(scenario.done)
        self.assertTrue(any(name=='profile13_fight_test_failed' and fields['attempted']
                            for name,fields in self.events))
        other=FakeNative();scenario=self.make(other);self.clock[0]=122.
        scenario.tick(hangar_ready=True)
        self.assertEqual(other.clicks,0)
        self.assertEqual(self.events[-1][0],'profile13_fight_test_timeout')

    def test_transient_gui_waits_until_ready_or_bounded_timeout(self):
        native=FakeNative();scenario=self.make(native);attempts=[0]
        def loading():
            attempts[0]+=1
            if attempts[0]<3:raise fight.NotReady('header pending')
            return native.button
        native.checked_button=loading
        scenario.tick(hangar_ready=True);scenario.tick(hangar_ready=True)
        self.assertFalse(scenario.done);self.assertEqual(native.clicks,0)
        scenario.tick(hangar_ready=True);self.assertEqual(native.clicks,1)
        self.clock[0]=122.;scenario.tick(avatar=True)
        self.assertTrue(scenario.done);self.assertEqual(native.clicks,1)
        self.assertEqual(self.events[-1][0],'profile13_fight_test_timeout')

    def test_transient_failure_after_attempt_fence_never_retries(self):
        native=FakeNative();scenario=self.make(native);attempts=[]
        def changed(owner):attempts.append(owner);raise fight.NotReady('lost readiness')
        native.click=changed
        scenario.tick(hangar_ready=True);scenario.tick(hangar_ready=True)
        self.assertEqual(len(attempts),1);self.assertTrue(scenario.done)
        self.assertEqual(self.events[-1][1]['error_type'],'NotReadyAfterFence')

    def test_real_observer_exception_ends_scenario_before_and_after_click(self):
        source=(ROOT/'client_patch/sr_interactive.py').read_text(encoding='utf8')
        tree=ast.parse(source);node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='observe')
        code=compile(ast.Module(body=[node],type_ignores=[]),'<trusted observer>','exec')
        for after_click in (False,True):
            native=FakeNative();scenario=self.make(native)
            if after_click:scenario.tick(hangar_ready=True)
            calls=[]
            def broken():raise RuntimeError('native observer failed')
            ns={'_fini':False,'_observations':0,'_stream':SimpleNamespace(tell=lambda:0),
                'observation_byte_limit':lambda:100,'current_views':broken,
                '_profile13_fight_scenario':scenario,'record':lambda *a,**k:calls.append(a[0]),
                '_control':{'quit_when':None},'traceback':traceback,'quit_client':lambda:calls.append('quit')}
            exec(code,ns);ns['observe']()
            self.assertTrue(scenario.done)
            self.assertTrue(any(name=='profile13_fight_test_failed' and fields['source']=='observer'
                                and fields['attempted']==after_click for name,fields in self.events))
            self.assertNotIn('quit',calls)

    def test_profile13_capture_accepts_unrelated_files_and_refuses_reuse(self):
        source=(ROOT/'client_patch/sr_interactive.py').read_text(encoding='utf8')
        node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='capture_profile13_screenshot')
        code=compile(ast.Module(body=[node],type_ignores=[]),'<trusted capture>','exec')
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);(folder/'shared-5860-030_003.png').write_bytes(b'existing')
            calls=[];settings_module=SimpleNamespace(g_instance=SimpleNamespace(engineConfig=SimpleNamespace(readString=lambda key:temp)))
            ns={'os':os,'_settings':{'screenshot_dir':temp,'local_root':temp},
                'owned':lambda path,root:os.path.normcase(os.path.realpath(path)),
                'record':lambda *a,**k:None,'primitive':lambda value:value,
                'BigWorld':SimpleNamespace(screenShot=lambda ext,name:calls.append((ext,name)))}
            with patch.dict(sys.modules,{'Settings':settings_module}):
                exec(code,ns);capture=ns['capture_profile13_screenshot']
                name='visibility_test_5860_42_123';capture(name)
                self.assertEqual(calls,[('png',name)])
                (folder/(name+'_001.png')).write_bytes(b'own')
                with self.assertRaises(ValueError):capture(name)
                with self.assertRaises(ValueError):capture('../bad')
                settings_module.g_instance.engineConfig.readString=lambda key:temp+'-foreign'
                with self.assertRaises(ValueError):capture('visibility_test_5860_42_124')
            self.assertEqual((folder/'shared-5860-030_003.png').read_bytes(),b'existing')
            self.assertEqual(len(calls),1)

    def test_only_completed_owned_png_is_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);s=settings();s.update(screenshot_dir=str(folder),local_root=str(folder))
            native=fight.Native(s,config());file=folder/'visibility_tick_123_456.png'
            mock=SimpleNamespace(owned=lambda path,root:str(Path(path).resolve()))
            with patch.dict(sys.modules,{'project_preferences':mock}):
                self.assertIsNone(native.screenshot_file('visibility_tick_123'))
                file.write_bytes(b'\x89PNG\r\n\x1a\n'+b'0123456789ABCDEF')
                self.assertIsNone(native.screenshot_file('visibility_tick_123'))
                file.write_bytes(b'\x89PNG\r\n\x1a\n'+b'abcdefgh'+b'\0\0\0\0IEND\xaeB`\x82')
                self.assertEqual(native.screenshot_file('visibility_tick_123'),str(file))

    def test_native_button_check_uses_profile13_eligibility_and_identity(self):
        class Account:pass
        player=Account();player.databaseID=5
        item=SimpleNamespace(invID=1,intCD=3329,descriptor=SimpleNamespace(makeCompactDescr=lambda:b'descriptor'))
        current=SimpleNamespace(invID=1,item=item)
        class Hangar:pass
        class Lobby:pass
        class Header:pass
        class Button:pass
        page=Hangar();page.flashObject=object();button=Button();button.flashObject=SimpleNamespace(button=SimpleNamespace(enabled=True))
        header=Header();header.flashObject=object();header.components={'fightButton':button}
        lobby=Lobby();lobby.flashObject=object();lobby.components={'lobbyHeader':header}
        containers={'sub':SimpleNamespace(getView=lambda:page),'main':SimpleNamespace(getView=lambda:lobby)}
        manager=SimpleNamespace(window=SimpleNamespace(containerManager=SimpleNamespace(getContainer=lambda key:containers[key])))
        state={'allowed':True,'queued':False};controller=SimpleNamespace(_require_owned=lambda:None,_eligibility=lambda:state)
        modules={'Account':SimpleNamespace(PlayerAccount=Account),'BigWorld':SimpleNamespace(player=lambda:player),
                 'map_drive_client':SimpleNamespace(is_active=lambda:True,_controller=controller),
                 'ConnectionManager':SimpleNamespace(connectionManager=SimpleNamespace(isConnected=lambda:True)),
                 'CurrentVehicle':SimpleNamespace(g_currentVehicle=current),
                 'gui.shared':SimpleNamespace(g_itemsCache=SimpleNamespace(isSynced=lambda:True)),
                 'gui.WindowsManager':SimpleNamespace(g_windowsManager=manager),
                 'gui.Scaleform.framework':SimpleNamespace(ViewTypes=SimpleNamespace(LOBBY_SUB='sub',VIEW='main')),
                 'gui.Scaleform.Waiting':SimpleNamespace(Waiting=SimpleNamespace(isVisible=lambda:False)),
                 'gui.Scaleform.daapi.view.lobby.hangar.Hangar':SimpleNamespace(Hangar=Hangar),
                 'gui.Scaleform.daapi.view.lobby.LobbyView':SimpleNamespace(LobbyView=Lobby),
                 'gui.Scaleform.daapi.view.lobby.header.LobbyHeader':SimpleNamespace(LobbyHeader=Header),
                 'gui.Scaleform.daapi.view.lobby.header.FightButton':SimpleNamespace(FightButton=Button)}
        with patch.dict(sys.modules,modules):
            native=fight.Native(settings(),config())
            self.assertIs(native.checked_button(),button)
            state['queued']=True
            with self.assertRaises(RuntimeError):native.checked_button()
            state['queued']=False;player.databaseID=6
            with self.assertRaises(RuntimeError):native.checked_button()


if __name__=='__main__':unittest.main()
