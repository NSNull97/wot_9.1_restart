"""UI-06 round 13: the ears' icons from the project set of their row's colour."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))
import battle_ui_ears_flash as ears
import battle_ui_native_flash as native
from battle_ui_hit_flash import stmt
from test_battle_ui_hit_flash import Clip, Machine

NATIVE_ICON = '../maps/icons/vehicle/contour/ussr-IS-7.png'
CLIP_METHODS = ('createEmptyMovieClip', 'createTextField', 'attachMovie', 'getNextHighestDepth', 'swapDepths')


class Obj:
    """A plain AS2 object: a missing member is undefined."""

    def __init__(self, **members):
        self.members = dict(members)


class StringMachine(Machine):
    """Strings answer indexOf and substr as in AS2; a callable answers apply;
    a missing member of an object is undefined."""

    def member(self, owner, name):
        if owner is None:
            return None
        if isinstance(owner, Obj):
            return owner.members.get(name)
        if isinstance(owner, Clip) and name not in owner.members:
            if getattr(owner, 'proto', None) is not None:
                return owner.proto.members.get(name)
            # As in AS2 a missing member is undefined; the clip's own methods stay.
            if name not in CLIP_METHODS:
                return None
        if isinstance(owner, dict):
            return owner.get(name)
        if isinstance(owner, str):
            return {'indexOf': lambda text, start=0: owner.find(text, start),
                    'substr': lambda start, size=None: owner[start:] if size is None else owner[start:start + size],
                    'length': len(owner)}[name]
        if callable(owner) and name == 'apply':
            return lambda this, args: owner(this, *args)
        return Machine.member(self, owner, name)

    def invoke(self, target, this, args):
        from test_battle_ui_hit_flash import Fn
        if isinstance(target, Fn):
            local = {'this': this, 'arguments': list(args)}
            local.update(zip(target.params, args))
            return self.run(target.code, target.scope + [local])
        return Machine.invoke(self, target, this, args)


class Renderer(Clip):
    def __init__(self, side, **data):
        Clip.__init__(self, 'row')
        panel = Clip('panel')
        panel.members['m_type'] = side
        self.members['_parent'] = Clip('list')
        self.members['_parent'].members['_parent'] = panel
        self.members['data'] = Obj(icon=NATIVE_ICON, **data)


def world(defined=True):
    seen = []
    proto = Obj(update=lambda this, *args: seen.append(this.members['data'].members['icon']))
    ingame = {'PlayerListItemRenderer': Obj(prototype=proto)} if defined else {}
    scope = {'this': Clip(), '_global': {'net': {'wargaming': {'ingame': ingame}}}}
    machine = StringMachine(scope['this'])
    machine.run(ears.sources() + b''.join(stmt(row) for row in ears.setup(5)) + b'\0', [scope])
    return machine, scope, proto, seen


class EarsTests(unittest.TestCase):
    def update(self, machine, proto, row):
        row.proto = proto
        machine.invoke(proto.members['update'], row, [])

    def test_each_row_takes_the_set_of_its_colour(self):
        machine, scope, proto, seen = world()
        for row, folder in ((Renderer('left'), 'contour_ally'), (Renderer('right'), 'contour_enemy'),
                            (Renderer('left', himself=True), 'contour_own'), (Renderer('left', teamKiller=True), 'contour_tk')):
            self.update(machine, proto, row)
            self.assertEqual(seen[-1], '../maps/icons/vehicle/%s/ussr-IS-7.png' % folder)

    def test_a_rewritten_path_is_rewritten_again_without_growing(self):
        machine, scope, proto, seen = world()
        row = Renderer('right')
        self.update(machine, proto, row)
        row.members['data'].members['teamKiller'] = True
        self.update(machine, proto, row)
        self.assertEqual(seen[-1], '../maps/icons/vehicle/contour_tk/ussr-IS-7.png')

    def test_the_wrap_is_installed_once(self):
        machine, scope, proto, seen = world()
        wrapper = proto.members['update']
        machine.run(b''.join(stmt(row) for row in ears.setup(5)) + b'\0', [scope])
        self.assertIs(proto.members['update'], wrapper)

    def test_without_the_class_a_clip_waits_and_wraps_when_it_comes(self):
        machine, scope, proto, seen = world(defined=False)
        holder = scope['this'].members['projectEarsWait']
        machine.invoke(holder.members['onEnterFrame'], holder, [])
        self.assertIn('onEnterFrame', holder.members, 'still waiting')
        late = Obj(update=lambda this, *args: seen.append(this.members['data'].members['icon']))
        scope['_global']['net']['wargaming']['ingame']['PlayerListItemRenderer'] = Obj(prototype=late)
        machine.invoke(holder.members['onEnterFrame'], holder, [])
        self.assertIsNone(holder.members['onEnterFrame'])
        self.update(machine, late, Renderer('right'))
        self.assertEqual(seen[-1], '../maps/icons/vehicle/contour_enemy/ussr-IS-7.png')

    def test_the_battle_movie_carries_the_ears_only_when_asked(self):
        self.assertNotIn(b'_projectEarsWrap', native.actions())
        self.assertIn(b'_projectEarsWrap', native.actions(palette=True))


if __name__ == '__main__':
    unittest.main()
