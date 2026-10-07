# -*- coding: utf-8 -*-
"""Explicit crew-operation boundary for the current project test service.

Install before original BusinessHandler construction: it captures bound event
handlers in its constructor. Restore after original GUI disposal. Native crew,
tooltip and personal-data readers are not replaced. This is a UI limitation;
the authoritative server must independently reject unsupported mutations.
PersonalCase entry is explicitly unavailable while its unconditional tariff
readers have no project contract; this does not imply every tab would crash.
"""

NOTICE = (u'Действие с экипажем пока недоступно в тестовом стенде. '
          u'Серверный экипаж доступен для просмотра в ангаре.')
PERSONAL_CASE_NOTICE = (u'Личное дело пока недоступно в тестовом стенде. '
                        u'Серверный экипаж доступен для просмотра в ангаре.')
POLICY_VERSION = 2

# Original #717 evidence: local/evidence/20261005-p02-ms1-crew/gui/boundaries-01.
AUDITED_SOURCES = (
    ('scripts/client/gui/Scaleform/daapi/business_layer.py',
     '351ff8015a98ad2865547d9d455fc48fe580cbb512cad86710fda52f05a758be'),
    ('scripts/client/gui/Scaleform/daapi/view/lobby/hangar/Crew.py',
     '8defb03050f4d903d40e466e11fed0b04c368f8fc0450263316e0b768edba136'),
    ('scripts/client/gui/Scaleform/daapi/view/lobby/barracks/Barracks.py',
     '1c18c924c6bfb9e753dae3f637b8b8079807a25b2e08e421b895bbb83bab3f19'),
    ('scripts/client/gui/Scaleform/daapi/view/lobby/PersonalCase.py',
     '2d550383e093fd75f872a84e45fd2447a7d9e9db0637b4c0836c83740c7f7ab2'),
    ('scripts/client/gui/Scaleform/daapi/view/lobby/crewOperations/CrewOperationsPopOver.py',
     '6397971287292708969f14f342d7c8237dcb797e1b694abc450c33f80e25e6c1'),
    ('scripts/client/gui/Scaleform/daapi/view/lobby/recruitWindow/RecruitWindow.py',
     'ac81a6a0a009fbc856505395f87f76d2a6df303291a7569eb2054f01f802fc41'),
    ('scripts/client/gui/Scaleform/daapi/view/lobby/crewOperations/RetrainCrewWindow.py',
     '577989c69a8f513a3763ca8407c1fe4cb0dc321b380c2f3d4064044b87436c4d'),
)

# (class, exact native member, denied action, descriptor is staticmethod).
# Only void UI callbacks are replaced. There are no response callbacks or
# fabricated operation results; no original processor is called.
TARGETS = (
    ('BusinessHandler', '_BusinessHandler__showRecruitWindow', 'open_recruit', False),
    ('BusinessHandler', '_BusinessHandler__showRetrainCrewWindow', 'open_retrain', False),
    ('BusinessHandler', '_BusinessHandler__showExchangeFreeToTankmanXpWindow', 'open_xp_conversion', False),
    ('BusinessLobbyHandler', 'showTankmanDropSkillsWindow', 'open_drop_skills', False),
    ('BusinessLobbyHandler', 'showCrewTankmanInfo', 'open_personal_case', False),
    ('Crew', 'equipTankman', 'equip', False),
    ('Crew', 'unloadTankman', 'unload', False),
    ('Crew', 'unloadAllTankman', 'unload_all', False),
    ('Crew', 'unloadCrew', 'unload_all', True),
    ('Barracks', 'buyBerths', 'buy_berths', False),
    ('Barracks', 'dismissTankman', 'dismiss', False),
    ('Barracks', 'unloadTankman', 'unload', False),
    ('PersonalCase', 'dismissTankman', 'dismiss', False),
    ('PersonalCase', 'retrainingTankman', 'retrain', False),
    ('PersonalCase', 'unloadTankman', 'unload', False),
    ('PersonalCase', 'changeTankmanPassport', 'change_passport', False),
    ('PersonalCase', 'addTankmanSkill', 'add_skill', False),
    ('CrewOperationsPopOver', 'invokeOperation', 'crew_operation', False),
    ('RecruitWindow', 'buyTankman', 'recruit', False),
    ('RetrainCrewWindow', 'submit', 'retrain', False),
)

_guard = None


class _CrewChangeGuard(object):
    """Own exact class descriptors; injectable dependencies permit unit checks."""

    def __init__(self, classes, messages, record):
        required = set(row[0] for row in TARGETS)
        if set(classes) != required or not callable(record):
            raise ValueError('exact audited crew classes and recorder required')
        if len(TARGETS) > 32 or len(set((row[0], row[1]) for row in TARGETS)) != len(TARGETS):
            raise ValueError('crew policy binding bounds violated')
        self.messages = messages
        self.record = record
        self.active = False
        self.bindings = []
        for class_name, name, action, is_static in TARGETS:
            cls = classes[class_name]
            original = cls.__dict__[name]
            if isinstance(original, staticmethod) != is_static:
                raise TypeError('unexpected native crew descriptor: ' + class_name + '.' + name)
            function = original.__get__(None, cls) if is_static else original
            if not callable(function):
                raise TypeError('native crew callback is not callable')
            callback = class_name + '.' + name
            replacement = self._denial(callback, action)
            if is_static:
                replacement = staticmethod(replacement)
            self.bindings.append((cls, name, original, replacement, callback))

    def _denial(self, callback, action):
        guard = self

        def denied(*args, **kwargs):
            if not guard.active:
                raise RuntimeError('crew capability callback used after cleanup')
            # No caller-provided values enter diagnostics or a network command.
            # Callback/action strings come exclusively from the fixed table.
            guard.record('crew_capability_denied', policy_version=POLICY_VERSION,
                         capability='crew_personal_case' if action == 'open_personal_case' else 'crew_changes',
                         action=action, callback=callback, origin='project_test_service_policy',
                         original_callback_called=False, original_mutation_called=False)
            if guard.messages.g_instance is None:
                raise RuntimeError('original SystemMessages unavailable for crew denial')
            notice = PERSONAL_CASE_NOTICE if action == 'open_personal_case' else NOTICE
            guard.messages.pushMessage(notice, type=guard.messages.SM_TYPE.Warning)
            guard.record('crew_capability_notice', policy_version=POLICY_VERSION,
                         phase='return', action=action, callback=callback,
                         channel='original_SystemMessages_Warning')

        return denied

    def install(self):
        if self.active:
            raise RuntimeError('crew capability policy installed twice')
        for cls, name, original, replacement, callback in self.bindings:
            if cls.__dict__.get(name) is not original:
                raise RuntimeError('crew binding changed before installation: ' + callback)
        self.record('crew_capability_policy', phase='install', policy_version=POLICY_VERSION,
                    crew_changes_available=False, original_readers_preserved=True,
                    personal_case_available=False,
                    lifecycle_requirement='before_original_BusinessHandler_construction',
                    bindings=[row[4] for row in self.bindings],
                    audited_sources=[{'source': path, 'sha256': digest}
                                     for path, digest in AUDITED_SOURCES])
        for cls, name, original, replacement, callback in self.bindings:
            setattr(cls, name, replacement)
        self.active = True

    def restore(self):
        if not self.active:
            return
        # Check the complete set first: never partially overwrite third-party
        # changes, nor silently restore an unexpected callback.
        for cls, name, original, replacement, callback in self.bindings:
            if cls.__dict__.get(name) is not replacement:
                raise RuntimeError('unexpected crew binding during cleanup: ' + callback)
        for cls, name, original, replacement, callback in self.bindings:
            setattr(cls, name, original)
        self.active = False
        self.record('crew_capability_policy', phase='restore', policy_version=POLICY_VERSION,
                    original_binding_restored=True, restored_bindings=[row[4] for row in self.bindings])


def init(record):
    """Call after items init but before original GUI BusinessHandler construction."""
    global _guard
    if _guard is not None:
        raise RuntimeError('crew capability policy initialized twice')
    from gui.Scaleform.daapi.business_layer import BusinessHandler, BusinessLobbyHandler
    from gui.Scaleform.daapi.view.lobby.hangar.Crew import Crew
    from gui.Scaleform.daapi.view.lobby.barracks.Barracks import Barracks
    from gui.Scaleform.daapi.view.lobby.PersonalCase import PersonalCase
    from gui.Scaleform.daapi.view.lobby.crewOperations.CrewOperationsPopOver import CrewOperationsPopOver
    from gui.Scaleform.daapi.view.lobby.recruitWindow.RecruitWindow import RecruitWindow
    from gui.Scaleform.daapi.view.lobby.crewOperations.RetrainCrewWindow import RetrainCrewWindow
    from gui import SystemMessages
    classes = dict((cls.__name__, cls) for cls in (BusinessHandler, BusinessLobbyHandler,
                   Crew, Barracks, PersonalCase, CrewOperationsPopOver, RecruitWindow,
                   RetrainCrewWindow))
    candidate = _CrewChangeGuard(classes, SystemMessages, record)
    candidate.install()
    _guard = candidate


def fini():
    """Restore exact descriptors after original GUI listeners/views are disposed."""
    global _guard
    if _guard is not None:
        _guard.restore()
        _guard = None
