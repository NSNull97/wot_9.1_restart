"""Round 13: the native panel backgrounds and spotting messages in the owner's palette."""
from pathlib import Path
import sys
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))
import battle_ui_native_flash as native
import battle_ui_panels_flash as panels
from battle_ui_hit_flash import expanded, stmt
from test_battle_ui_ears_flash import StringMachine
from test_battle_ui_hit_flash import Clip

ORIGINAL = Path('C:/WoT_0.9.1_RU_0717_original')


class Transform:
    """flash.geom.Transform: setting colorTransform records it on the clip."""

    def __init__(self, clip):
        self.clip = clip
        self.members = self

    def __setitem__(self, name, value):
        if name == 'colorTransform':
            self.clip.members.setdefault('painted', []).append(value)


def world(**clips):
    root = Clip()
    for owner, children in clips.items():
        holder = Clip(owner)
        for child in children:
            holder.members[child] = Clip(child)
        root.members[owner] = holder
    geom = {'ColorTransform': lambda *args: args, 'Transform': Transform}
    scope = {'this': root, 'flash': {'geom': geom}}
    machine = StringMachine(root)
    machine.run(panels.sources() + b''.join(stmt(row) for row in panels.setup(7)) + b'\0', [scope])
    return machine, root


class PanelTests(unittest.TestCase):
    def test_every_background_is_painted_flat_once(self):
        machine, root = world(damagePanel=['bg'], minimap=['foreground', 'foregroundHR'])
        for owner, child in panels.PANELS:
            painted = root.members[owner].members[child].members['painted']
            self.assertEqual(painted, [(0, 0, 0, 1, 0x19, 0x21, 0x26, 0)], child)
        self.assertNotIn('projectPanelsWait', root.members, 'all there: no waiting clip')

    def test_a_missing_panel_is_waited_for_and_painted_when_it_comes(self):
        machine, root = world(damagePanel=['bg'])
        holder = root.members['projectPanelsWait']
        holder.members['_parent'] = root
        machine.invoke(holder.members['onEnterFrame'], holder, [])
        self.assertIn('onEnterFrame', holder.members)
        self.assertEqual(len(root.members['damagePanel'].members['bg'].members['painted']), 1, 'not painted twice')
        minimap = Clip('minimap')
        minimap.members['foreground'], minimap.members['foregroundHR'] = Clip('f'), Clip('h')
        root.members['minimap'] = minimap
        machine.invoke(holder.members['onEnterFrame'], holder, [])
        self.assertIsNone(holder.members['onEnterFrame'])
        self.assertEqual(len(minimap.members['foreground'].members['painted']), 1)


@unittest.skipUnless((ORIGINAL / 'res/packages/gui.pkg').is_file(), 'original client absent')
class MovieTests(unittest.TestCase):
    def test_the_spotting_message_text_takes_the_palette_colour_only_with_the_palette(self):
        with zipfile.ZipFile(ORIGINAL / 'res/packages/gui.pkg') as package:
            raw = package.read(native.MEMBER)
        at, colour = native.detection_edit(expanded(raw))
        self.assertEqual(colour.hex(), 'dfca91ff')
        plain = expanded(native.build(raw, native.actions()))
        styled = expanded(native.build(raw, native.actions(palette=True), palette=True))
        self.assertEqual(plain[at:at + 4].hex(), 'fff4b5ff')
        self.assertEqual(styled[at:at + 4].hex(), 'dfca91ff')


if __name__ == '__main__':
    unittest.main()
