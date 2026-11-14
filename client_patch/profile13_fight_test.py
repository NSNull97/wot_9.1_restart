# -*- coding: utf-8 -*-
"""Explicit one-shot native FightButton test; never move or quit the client.

This diagnostic is armed only by the owned one-shot control. It calls the
already installed original-bound button, not a fabricated network request.
Callback return alone is not evidence of server admission or visual success.
"""
import hashlib
import os
import re

try:
    integers = (int, long)
    strings = (str, unicode)
except NameError:
    integers = (int,)
    strings = (str,)


class NotReady(Exception):
    """A bounded wait for native GUI/cache setup, not a permission failure."""


def checked(value, settings):
    keys = set(('account','database_id','inventory_id','compact_id','descriptor_sha256','timeout_seconds','screenshot'))
    if type(value) is not dict or set(value) != keys:
        raise ValueError('exact test fight settings required')
    debug = settings.get('visibility_debug')
    binding = settings.get('profile13_fight_binding')
    if (settings.get('enable_profile13_battle') is not True
            or settings.get('enable_profile13_fight_test') is not True or type(debug) is not dict
            or type(binding) is not dict or set(binding)!=set(('account','database_id','receipt_sha256'))
            or value['account'] != debug.get('account') or value['account'] != binding.get('account')
            or value['database_id'] != binding.get('database_id') or value['screenshot'] is not True):
        raise ValueError('explicit profile13 operator test and screenshot required')
    if (not isinstance(binding['receipt_sha256'],strings)
            or re.match(r'\A[0-9a-f]{64}\Z',binding['receipt_sha256']) is None):
        raise ValueError('verified stand binding required')
    for key,maximum in (('database_id',2147483647),('inventory_id',2147483647),('compact_id',65535)):
        if type(value[key]) not in integers or not 1 <= value[key] <= maximum:
            raise ValueError('test fight identity bound')
    if (not isinstance(value['descriptor_sha256'],strings)
            or re.match(r'\A[0-9a-f]{64}\Z',value['descriptor_sha256']) is None
            or type(value['timeout_seconds']) is not int or not 20 <= value['timeout_seconds'] <= 300):
        raise ValueError('test fight descriptor/timeout bound')
    return dict(value)


class Native(object):
    def __init__(self, settings, expected):
        self.settings,self.expected=settings,expected

    def checked_button(self):
        import Account, BigWorld
        import map_drive_client as ordinary
        from ConnectionManager import connectionManager
        from CurrentVehicle import g_currentVehicle
        from gui.shared import g_itemsCache
        from gui.WindowsManager import g_windowsManager
        from gui.Scaleform.framework import ViewTypes
        from gui.Scaleform.Waiting import Waiting
        from gui.Scaleform.daapi.view.lobby.hangar.Hangar import Hangar
        from gui.Scaleform.daapi.view.lobby.LobbyView import LobbyView
        from gui.Scaleform.daapi.view.lobby.header.LobbyHeader import LobbyHeader
        from gui.Scaleform.daapi.view.lobby.header.FightButton import FightButton
        expected=self.expected;player=BigWorld.player()
        if (player is None or not connectionManager.isConnected() or not g_itemsCache.isSynced()
                or not ordinary.is_active()):
            raise NotReady('native account/cache not ready')
        if type(player) is not Account.PlayerAccount or player.databaseID!=expected['database_id']:
            raise RuntimeError('bound profile13 account identity differs')
        current=g_currentVehicle;item=current.item
        if item is None:raise NotReady('vehicle selection not ready')
        if (current.invID!=expected['inventory_id'] or item.invID!=expected['inventory_id']
                or item.intCD!=expected['compact_id']
                or hashlib.sha256(item.descriptor.makeCompactDescr()).hexdigest()!=expected['descriptor_sha256']):
            raise RuntimeError('selected native vehicle identity changed')
        controller=ordinary._controller;controller._require_owned()
        state=controller._eligibility()
        if state.get('queued') is not False:
            raise RuntimeError('native account already queued or queue state invalid')
        if state.get('allowed') is not True:
            raise NotReady('owned native vehicle not yet eligible')
        app=g_windowsManager.window
        if app is None or app.containerManager is None or Waiting.isVisible():
            raise NotReady('native hangar loading')
        sub=app.containerManager.getContainer(ViewTypes.LOBBY_SUB)
        page=sub.getView() if sub is not None else None
        if page is None or page.flashObject is None:raise NotReady('Hangar not bound')
        if type(page) is not Hangar:raise RuntimeError('original Hangar required')
        main=app.containerManager.getContainer(ViewTypes.VIEW)
        lobby=main.getView() if main is not None else None
        if lobby is None or lobby.flashObject is None:raise NotReady('LobbyView not bound')
        if type(lobby) is not LobbyView:raise RuntimeError('original LobbyView required')
        header=lobby.components.get('lobbyHeader')
        if header is None or header.flashObject is None:raise NotReady('LobbyHeader not bound')
        if type(header) is not LobbyHeader:raise RuntimeError('original LobbyHeader required')
        button=header.components.get('fightButton')
        if button is None or button.flashObject is None:raise NotReady('FightButton not bound')
        if type(button) is not FightButton:raise RuntimeError('original FightButton required')
        if button.flashObject.button.enabled is not True:raise NotReady('FightButton not enabled')
        return button

    def captcha(self):
        import map_drive_client as ordinary
        import map_drive_acceptance as existing
        import arena_entry_probe as probe
        from gui import game_control
        from gui.game_control.captcha_control import CaptchaController
        from gui.shared import g_itemsCache
        ordinary._captcha_guard.require_ready()
        captcha,stats=game_control.g_instance.captcha,g_itemsCache.items.stats
        if captcha is None or stats is None:raise NotReady('CAPTCHA state pending')
        if type(captcha) is not CaptchaController:raise RuntimeError('original CAPTCHA controller required')
        probe._code_contract(captcha.isCaptchaRequired,existing.CAPTCHA_REQUIRED_METHOD,existing.CAPTCHA_REQUIRED_SOURCE)
        probe._code_contract(stats.getCacheValue,existing.CACHE_GETTER_METHOD,existing.CACHE_GETTER_SOURCE)
        counter=stats.getCacheValue('battlesTillCaptcha',None)
        if counter is None:raise NotReady('CAPTCHA counter pending')
        return existing._checked_captcha(dict(battles_till_captcha=counter,
            captcha_required=captcha.isCaptchaRequired(),controller_owner_id=id(captcha),stats_owner_id=id(stats),
            guard_blocked_calls=ordinary._captcha_guard.blocked_calls))

    def click(self, expected_owner):
        button=self.checked_button()
        if id(button)!=expected_owner:raise RuntimeError('native FightButton changed')
        self.captcha()
        button.fightClick(0, '')

    def rendered_snapshot(self):
        import project_visibility_debug
        return project_visibility_debug.rendered_snapshot()

    def screenshot_file(self, basename):
        from project_preferences import owned
        directory=owned(self.settings['screenshot_dir'],self.settings['local_root'])
        names=os.listdir(directory)
        if len(names)>128:raise ValueError('screenshot count bound')
        pattern=re.compile(r'\A'+re.escape(basename)+r'_[0-9]{3,10}\.png\Z')
        matches=[name for name in names if pattern.match(name)]
        if len(matches)>1:raise ValueError('ambiguous screenshot')
        if not matches:return None
        path=os.path.join(directory,matches[0])
        if os.path.islink(path) or not os.path.isfile(path) or os.path.getsize(path)>32*1024*1024:
            raise ValueError('invalid screenshot output')
        if os.path.getsize(path)<20:return None
        with open(path,'rb') as stream:
            if stream.read(8)!=b'\x89PNG\r\n\x1a\n':raise ValueError('invalid screenshot signature')
            stream.seek(-12,2)
            if stream.read(8)[4:]!=b'IEND':return None
        return path


class Scenario(object):
    def __init__(self, expected, settings, native, record, now, capture):
        self.expected=checked(expected,settings);self.native=native;self.record=record
        self.now=now;self.capture=capture;self.deadline=now()+expected['timeout_seconds']
        self.attempted=False;self.done=False;self.shot=None

    def observer_failed(self, error):
        if self.done:return
        self.done=True
        self.record('profile13_fight_test_failed',error_type=type(error).__name__,
                    attempted=self.attempted,source='observer',visual_review='NOT_RUN')

    def tick(self, hangar_ready=False, avatar=False):
        if self.done:return
        if self.now()>=self.deadline:
            self.done=True;self.record('profile13_fight_test_timeout',attempted=self.attempted,
                                      screenshot_requested=self.shot is not None)
            return
        try:
            if not self.attempted and hangar_ready:
                button=self.native.checked_button();owner=id(button);self.native.captcha()
                # A second call could dequeue. Fence retries before invoking any callback.
                self.attempted=True
                self.record('profile13_fight_test_begin',button_owner_id=owner,
                            database_id=self.expected['database_id'],inventory_id=self.expected['inventory_id'])
                self.native.click(owner)
                self.record('profile13_fight_test_return',button_owner_id=owner,server_admission='NOT_CONFIRMED')
            if self.attempted and avatar:
                if self.shot is None:
                    metadata=self.native.rendered_snapshot()
                    if metadata is None:return
                    basename='visibility_test_%d_%s_%d' % (os.getpid(),metadata['battle'],metadata['tick'])
                    self.capture(basename)
                    self.shot=(basename,metadata)
                    self.record('profile13_screenshot_requested',scan_tick=metadata['tick'],battle=metadata['battle'],run=metadata['run'],
                                screenshot_frame_tick='MAY_ADVANCE',visual_review='NOT_RUN')
                path=self.native.screenshot_file(self.shot[0])
                if path is not None:
                    self.done=True
                    self.record('profile13_screenshot_saved',path=path,scan_tick=self.shot[1]['tick'],
                                battle=self.shot[1]['battle'],run=self.shot[1]['run'],screenshot_frame_tick='MAY_ADVANCE',
                                visual_review='NOT_RUN')
        except NotReady:
            if self.attempted:
                self.done=True;self.record('profile13_fight_test_failed',error_type='NotReadyAfterFence',
                                          attempted=True,visual_review='NOT_RUN')
        except Exception as error:
            # Any native contract failure is explicit and cannot trigger a second click.
            self.done=True;self.record('profile13_fight_test_failed',error_type=type(error).__name__,
                                      attempted=self.attempted,visual_review='NOT_RUN')


def arm(value, settings, record, now, capture):
    expected=checked(value,settings)
    return Scenario(expected,settings,Native(settings,expected),record,now,capture)
