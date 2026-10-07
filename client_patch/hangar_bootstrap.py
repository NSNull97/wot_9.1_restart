# -*- coding: utf-8 -*-
"""Measured #717 GUI bootstrap for the reversible local native experiment.

No Account callback or entity is replaced. The optional local-service policy
explicitly denies the original GUI's module mutation entry point. Original
game.init is not called: it registers a replay association and starts RSS services.
The caller owns numeric-loopback configuration, the profile, transport and quit.
Runtime acceptance comes from original callbacks/UI state, never these markers.
"""
import sys
import traceback
import os
import re

_record = None
_stages = []
_gui_enabled = False
_started = False
_finished = False
_screenshot_requested = set()
_profile_requested = False


def _step(name, function, *args, **kwargs):
    _record('hangar_bootstrap_step', stage=name, phase='begin')
    try:
        result = function(*args, **kwargs)
    except Exception:
        _record('hangar_bootstrap_error', stage=name,
                traceback=traceback.format_exc())
        raise
    _stages.append(name)
    _record('hangar_bootstrap_step', stage=name, phase='return')
    return result


def _descriptors():
    from items import vehicles
    import dossiers2
    type_name = 'ussr:MS-1'
    # Original list lookup must succeed. No substitute vehicle/descriptor.
    type_id = vehicles.g_list.getIDsByName(type_name)
    desc = vehicles.VehicleDescr(typeName=type_name)
    if tuple(desc.type.id) != tuple(type_id):
        raise ValueError('original vehicle list/descriptor ID mismatch')
    dossier = dossiers2.getAccountDossierDescr('')
    components = {}
    for name in ('chassis', 'engine', 'fuelTank', 'radio', 'turret', 'gun'):
        part = getattr(desc, name)
        components[name] = {'id': part['id'], 'compact_descr': part['compactDescr']}
    _record('hangar_descriptors',
            vehicle={'type_name': desc.type.name,
                     'type_id': list(desc.type.id),
                     'type_compact_descr': desc.type.compactDescr,
                     'compact_descr_hex': desc.makeCompactDescr().encode('hex'),
                     'max_health': desc.maxHealth,
                     'crew_roles': desc.type.crewRoles,
                     'components': components},
            account_dossier_hex=dossier.makeCompDescr().encode('hex'))


def init(args, record, start_gui=False, restrict_module_changes=False, restrict_crew_changes=False):
    """Call after the original Settings instance/profile have been installed.

    start_gui=False extracts authentic resource descriptors only. True also
    initializes original GUI services, but starts the movie only after a genuine
    native LOGGED_ON callback reaches on_connection(). The interactive test
    service opts into restrict_module_changes; older research modes keep their
    prior behavior and do not require the additional compatibility module.
    """
    global _record, _gui_enabled
    if _record is not None:
        raise RuntimeError('hangar bootstrap initialized twice')
    _record = record
    _gui_enabled = bool(start_gui)
    import BigWorld
    import Settings
    if Settings.g_instance is None or len(args) < 3:
        raise ValueError('original Settings and engine arguments are required')
    _step('native_custom_settings', BigWorld.wg_initCustomSettings)
    import CommandMapping
    CommandMapping.g_instance = _step('command_mapping', CommandMapping.CommandMapping)
    import SoundGroups
    SoundGroups.g_instance = _step('sound_groups', SoundGroups.SoundGroups)
    import items
    _step('items', items.init, True, None)
    import dossiers1
    import dossiers2
    _step('dossiers1', dossiers1.init)
    _step('dossiers2', dossiers2.init)
    _step('resource_descriptors', _descriptors)
    if not _gui_enabled:
        return

    import gui
    if not gui.GUI_SETTINGS.isGuiEnabled():
        raise ValueError('original GUI is disabled in resource configuration')
    if gui.GUI_SETTINGS.loginRssFeed.show:
        raise ValueError('disable external RSS in the diagnostic resource override')
    # Original serverSettings must explicitly disable external voice/XMPP and
    # advertise only our local services. These are not client account values.
    import BattleReplay
    BattleReplay.g_replayCtrl = _step('battle_replay', BattleReplay.BattleReplay)
    import game
    game.g_replayCtrl = BattleReplay.g_replayCtrl
    # Original GUI button sounds also dispatch to the original vibration
    # manager. Its native no-device path returns normally; no handler is replaced.
    from Vibroeffects import VibroManager
    VibroManager.g_instance = _step('vibration', VibroManager.VibroManager)
    _step('vibration_connect', VibroManager.g_instance.connect)
    from messenger import MessengerEntry
    _step('messenger', MessengerEntry.g_instance.init)
    import ArenaType
    import fortified_regions
    _step('arena_resource_definitions', ArenaType.init)
    _step('fortified_resource_definitions', fortified_regions.init)
    BigWorld.worldDrawEnabled(False)
    from gui.shared import personality
    if restrict_crew_changes:
        # BusinessHandler stores bound methods in its constructor; installing
        # after personality.init would leave the old recruitment listener live.
        import crew_capabilities
        _step('crew_capabilities', crew_capabilities.init, record)
    # Original game.init supplies its fourth native engine argument when present.
    loading_screen = args[3] if len(args) > 3 else None
    _step('gui_personality', personality.init, loadingScreenGUI=loading_screen)
    if restrict_module_changes:
        import hangar_capabilities
        _step('module_capabilities', hangar_capabilities.init, record)
    # Native chunk callbacks are delegated to the original game personality.
    # Its manager must exist before the hangar starts loading any chunks.
    import AreaDestructibles
    _step('area_destructibles', AreaDestructibles.init)
    import MusicController
    _step('music', MusicController.init)
    _step('post_processing', game.g_postProcessing.init)
    from ConnectionManager import connectionManager
    connectionManager.onConnected += personality.onConnected
    connectionManager.onDisconnected += personality.onDisconnected
    _stages.append('connection_handlers')
    _record('hangar_bootstrap_ready', gui_initialized=True,
            movie_started=False, network='caller-controlled numeric loopback')


def on_connection(stage, status, server_message):
    """Delegate the real engine result; do not assign connected flags."""
    from ConnectionManager import connectionManager
    connectionManager.connectionWatcher(False, stage, status, server_message)
    _record('hangar_connection_manager', stage=stage, status=status,
            is_connected=connectionManager.isConnected())
    if stage == 1 and status == 'LOGGED_ON' and _gui_enabled:
        start()


def start():
    global _started
    if _started:
        return
    from ConnectionManager import connectionManager
    if not _gui_enabled or not connectionManager.isConnected():
        raise RuntimeError('GUI start requires actual native connection')
    from gui.shared import personality
    _step('gui_movie', personality.start)
    from Vibroeffects import VibroManager
    _step('vibration_start', VibroManager.g_instance.start)
    _started = True


def observe():
    """Return passive original-object state; this does not drive the GUI."""
    if not _gui_enabled or 'gui_personality' not in _stages:
        return {'gui_initialized': False, 'movie_started': _started}
    from gui.WindowsManager import g_windowsManager
    from gui.shared.utils.HangarSpace import g_hangarSpace
    from gui.shared import g_itemsCache
    from ConnectionManager import connectionManager
    from gui.Scaleform.Waiting import Waiting
    from gui.Scaleform.framework import ViewTypes
    window = g_windowsManager.window
    synced = bool(g_itemsCache.isSynced())
    fields = {'gui_initialized': True, 'movie_started': _started,
              'native_connected': connectionManager.isConnected(),
              'window_class': type(window).__name__ if window is not None else None,
              'hangar_space_inited': bool(g_hangarSpace.inited),
              'hangar_space_loaded': bool(g_hangarSpace.spaceInited),
              'hangar_space_loading': bool(g_hangarSpace.spaceLoading()),
              'waiting_visible': bool(Waiting.isVisible()),
              'items_cache_synced': synced}
    if window is not None:
        fields['app_initialized'] = bool(window.initialized)
        manager = window.containerManager
        fields['views'] = {}
        if manager is not None:
            for label, view_type in (('main', ViewTypes.VIEW),
                                     ('lobby_sub', ViewTypes.LOBBY_SUB)):
                container = manager.getContainer(view_type)
                view = container.getView() if container is not None else None
                if view is None:
                    fields['views'][label] = None
                else:
                    fields['views'][label] = {
                        'class_name': type(view).__name__,
                        'alias': view.settings.alias,
                        'flash_bound': view.flashObject is not None,
                        'components': sorted(str(k) for k in view.components)[:64]}
    if synced:
        # These are original cache getters over data actually received by Account.
        # They do not set a balance, inventory item, selected vehicle or UI flag.
        stats = g_itemsCache.items.stats
        fields['resources'] = {'credits': stats.credits, 'gold': stats.gold,
                               'free_xp': stats.freeXP}
        total = g_itemsCache.items.getAccountDossier().getTotalStats()
        fields['statistics'] = {'battles': total.getBattlesCount(),
                                'wins': total.getWinsCount(),
                                'losses': total.getLossesCount(),
                                'draws': total.getDrawsCount()}
        from CurrentVehicle import g_currentVehicle
        vehicle = g_currentVehicle.item
        fields['selected_inventory_id'] = g_currentVehicle.invID
        fields['vehicle'] = None if vehicle is None else {
            'inventory_id': vehicle.invID,
            'type_compact_descr': vehicle.intCD,
            'type_name': vehicle.descriptor.type.name,
            'health': vehicle.health,
            'max_health': vehicle.descriptor.maxHealth,
            'xp': vehicle.xp,
            'crew_slots': len(vehicle.crew)}
    space = g_hangarSpace.space
    if space is not None:
        appearance = space._ClientHangarSpace__vAppearance
        fields['visual_entity_id'] = space._ClientHangarSpace__vEntityId
        fields['vehicle_model_loaded'] = appearance is not None and appearance.isLoaded()
        if appearance is not None:
            models = appearance._VehicleAppearance__models
            fields['vehicle_model_count'] = len(models)
            fields['vehicle_models_visible'] = [bool(model.visible) for model in models[:16]]
    return fields


def open_own_profile():
    """One explicit diagnostic navigation through the original header handler.

    This invokes no dossier callback and assigns no account or readiness data.
    The real new account must have no clan or rare achievements, whose original
    loaders otherwise can fetch resources outside this isolated experiment.
    """
    global _profile_requested
    if _profile_requested:
        raise RuntimeError('only one diagnostic profile navigation per client run')
    if not _gui_enabled or not _started:
        raise RuntimeError('profile navigation requires initialized GUI')
    import BigWorld
    from gui.WindowsManager import g_windowsManager
    from gui.Scaleform.framework import ViewTypes
    from gui.Scaleform.daapi.settings.views import VIEW_ALIAS
    from gui.Scaleform.Waiting import Waiting
    from gui.shared import g_itemsCache
    from ConnectionManager import connectionManager
    if not connectionManager.isConnected() or not g_itemsCache.isSynced():
        raise RuntimeError('profile navigation requires real connected and synced account')
    clan_id, clan_info = g_itemsCache.items.getClanInfo(None)
    rare_count = len(g_itemsCache.items.getAccountDossier(None).getBlock('rareAchievements'))
    if clan_id != 0 or clan_info is not None or rare_count != 0:
        raise ValueError('profile resources differ from the audited empty-account contract')
    window = g_windowsManager.window
    manager = window.containerManager
    lobby = manager.getContainer(ViewTypes.VIEW).getView()
    current = manager.getContainer(ViewTypes.LOBBY_SUB).getView()
    if (type(lobby).__name__ != 'LobbyView' or
            type(current).__name__ != 'Hangar' or
            current.settings.alias != VIEW_ALIAS.LOBBY_HANGAR or Waiting.isVisible()):
        raise RuntimeError('diagnostic profile navigation requires the ready original hangar')
    header = lobby.components['lobbyHeader']
    if type(header).__name__ != 'LobbyHeader' or header.flashObject is None:
        raise RuntimeError('original lobby header is not bound')
    _profile_requested = True
    player = BigWorld.player()
    _record('diagnostic_open_profile', phase='begin',
            origin='original_lobby_header_menuItemClick', item=VIEW_ALIAS.LOBBY_PROFILE,
            database_id=player.databaseID, name=player.name,
            clan_database_id=clan_id, clan_info_is_none=clan_info is None,
            rare_achievements_count=rare_count)
    header.menuItemClick(VIEW_ALIAS.LOBBY_PROFILE)
    _record('diagnostic_open_profile', phase='return',
            origin='original_lobby_header_menuItemClick', item=VIEW_ALIAS.LOBBY_PROFILE)


def observe_profile():
    """Read original profile objects only; the caller verifies data/Flash traces."""
    fields = {'ready': False, 'navigation_requested': _profile_requested,
              'profile_view': None, 'profile_navigator': None,
              'profile_summary': None}
    if not _gui_enabled or not _started or _finished:
        return fields
    import BigWorld
    from gui.WindowsManager import g_windowsManager
    from gui.Scaleform.framework import ViewTypes
    from gui.Scaleform.daapi.settings.views import VIEW_ALIAS
    from gui.Scaleform.Waiting import Waiting
    from gui.shared import g_itemsCache
    from ConnectionManager import connectionManager
    player = BigWorld.player()
    fields['player_database_id'] = player.databaseID if player is not None else None
    fields['player_name'] = player.name if player is not None else None
    fields['waiting_visible'] = bool(Waiting.isVisible())
    fields['items_cache_synced'] = bool(g_itemsCache.isSynced())
    fields['native_connected'] = bool(connectionManager.isConnected())
    window = g_windowsManager.window
    if window is None or window.containerManager is None:
        return fields
    container = window.containerManager.getContainer(ViewTypes.LOBBY_SUB)
    page = container.getView() if container is not None else None
    if page is None or page.settings.alias != VIEW_ALIAS.LOBBY_PROFILE:
        return fields
    fields['profile_view'] = {'class_name': type(page).__name__,
                              'alias': page.settings.alias,
                              'flash_bound': page.flashObject is not None,
                              'components': sorted(str(k) for k in page.components)[:64]}
    nav = page.components.get(VIEW_ALIAS.PROFILE_TAB_NAVIGATOR)
    if nav is None:
        return fields
    fields['profile_navigator'] = {'class_name': type(nav).__name__,
                                   'flash_bound': nav.flashObject is not None,
                                   'components': sorted(str(k) for k in nav.components)[:64]}
    summary = nav.components.get(VIEW_ALIAS.PROFILE_SUMMARY_PAGE)
    if summary is None:
        return fields
    fields['profile_summary'] = {'class_name': type(summary).__name__,
                                 'flash_bound': summary.flashObject is not None,
                                 'is_active': bool(summary.isActive),
                                 'user_id': summary._userID,
                                 'database_id': summary._databaseID,
                                 'user_name': summary._userName,
                                 'battles_type': summary._battlesType}
    # This is a derived observation of real objects, not a GUI flag assignment.
    # Data acceptance additionally requires original Flash calls and pixels.
    fields['ready'] = bool(
        fields['native_connected'] and fields['items_cache_synced'] and
        not fields['waiting_visible'] and type(page).__name__ == 'ProfilePage' and
        type(nav).__name__ == 'ProfileTabNavigator' and
        type(summary).__name__ == 'ProfileSummaryPage' and
        page.flashObject is not None and nav.flashObject is not None and
        summary.flashObject is not None and summary.isActive and
        summary._userID is None and player is not None and
        summary._databaseID == player.databaseID and summary._userName == player.name)
    return fields


def capture(screenshot_dir, allowed_evidence_root, name='hangar'):
    """Request one native screenshot per audited basename in the owned directory.

    The external runner must create a fresh directory under ignored local
    evidence and put that exact path in its backed-up engine_config override.
    The marker is a request, not proof that pixels were written successfully.
    """
    if name in _screenshot_requested:
        raise RuntimeError('only one native screenshot request per basename')
    if not _gui_enabled or not _started:
        raise RuntimeError('native screenshot requires initialized GUI')
    if name not in ('hangar', 'profile'):
        raise ValueError('invalid diagnostic screenshot basename')
    if not os.path.isabs(screenshot_dir) or not os.path.isabs(allowed_evidence_root):
        raise ValueError('screenshot paths must be absolute')
    directory = os.path.normcase(os.path.realpath(screenshot_dir))
    evidence_root = os.path.normcase(os.path.realpath(allowed_evidence_root))
    if not directory.startswith(evidence_root.rstrip('\\/') + os.sep):
        raise ValueError('screenshot directory escapes local evidence')
    if not os.path.isdir(directory):
        raise ValueError('screenshot directory must exist')
    # The first request requires a fresh folder. Later requests allow only PNGs
    # from already requested native basenames and cannot target those names again.
    for entry in os.listdir(directory):
        path = os.path.join(directory, entry)
        if (not os.path.isfile(path) or os.path.islink(path) or
                not any(re.match(r'^' + re.escape(previous) + r'_[0-9]{3,10}\.png$', entry)
                        for previous in _screenshot_requested)):
            raise ValueError('screenshot directory contains an unowned entry')
    import Settings
    configured = Settings.g_instance.engineConfig.readString('screenShot/path')
    if not os.path.isabs(configured) or os.path.normcase(os.path.realpath(configured)) != directory:
        raise ValueError('native screenshot path differs from owned evidence directory')
    import BigWorld
    _record('hangar_screenshot_requested', directory=directory,
            basename=name, extension='png', writer='BigWorld.screenShot')
    _screenshot_requested.add(name)
    result = BigWorld.screenShot('png', name)
    _record('hangar_screenshot_return', result_type=type(result).__name__,
            result_repr=repr(result)[:256])


def fini():
    """Call from the engine's personality fini, before repository/trace close.

    Every cleanup error is recorded. The first one is re-raised after remaining
    initialized services have been given their original cleanup calls.
    """
    global _finished
    if _record is None or _finished:
        return
    _finished = True
    errors = []

    def close(name, function):
        try:
            function()
            _record('hangar_cleanup', stage=name, outcome='PASS')
        except Exception:
            details = traceback.format_exc()
            errors.append(details)
            _record('hangar_cleanup', stage=name, outcome='FAIL', traceback=details)

    # Match the measured game.fini order for the services initialized here.
    # The caller requests BigWorld.quit first; teardown belongs to engine fini,
    # not to a callback that may return into a still-rendering visible window.
    if 'music' in _stages:
        import MusicController
        close('music', MusicController.g_musicController.destroy)
    if 'connection_handlers' in _stages:
        from ConnectionManager import connectionManager
        from gui.shared import personality
        connectionManager.onConnected -= personality.onConnected
        connectionManager.onDisconnected -= personality.onDisconnected
    if 'messenger' in _stages:
        from messenger import MessengerEntry
        close('messenger', MessengerEntry.g_instance.fini)
    if 'post_processing' in _stages:
        import game
        close('post_processing', game.g_postProcessing.fini)
    if _gui_enabled:
        import BigWorld
        close('native_entities', lambda: BigWorld.resetEntityManager(False, False))
        close('native_spaces', BigWorld.clearAllSpaces)
    if 'gui_personality' in _stages:
        from gui.shared import personality
        close('gui_personality', personality.fini)
    if 'crew_capabilities' in _stages:
        import crew_capabilities
        close('crew_capabilities', crew_capabilities.fini)
    if 'module_capabilities' in _stages:
        import hangar_capabilities
        close('module_capabilities', hangar_capabilities.fini)
    if 'area_destructibles' in _stages:
        import AreaDestructibles
        close('area_destructibles', AreaDestructibles.clear)
    if 'vibration' in _stages:
        from Vibroeffects import VibroManager

        def destroy_vibration():
            VibroManager.g_instance.destroy()
            VibroManager.g_instance = None

        close('vibration', destroy_vibration)
    if 'battle_replay' in _stages:
        import BattleReplay
        close('battle_replay', BattleReplay.g_replayCtrl.destroy)
    if 'predefined_hosts' in sys.modules:
        close('predefined_hosts', sys.modules['predefined_hosts'].g_preDefinedHosts.fini)
    if errors:
        raise RuntimeError('original hangar cleanup failed in %d stages' % len(errors))
