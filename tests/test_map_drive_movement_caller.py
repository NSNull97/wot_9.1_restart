# -*- coding: utf-8 -*-
"""Bounded passive caller metadata on owned functions; no native input claim."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_ms1_ammo_profile import Box, frame, load_functions, execute_trusted


class MetadataFrame(object):
    def __init__(self, source, name='owned', line=10, offset=23, parent=None):
        self.f_code=Box(co_filename=source,co_name=name,co_firstlineno=line)
        self.f_lasti,self.f_back=offset,parent

    @property
    def f_locals(self):
        raise AssertionError('caller locals must never be read')

    @property
    def f_globals(self):
        raise AssertionError('caller globals must never be read')


class MovementCallerTests(unittest.TestCase):
    def setUp(self):
        self.events,self.notes=[],[]
        self.ns=load_functions(self.events)
        self.ns['_control']={'probe_map_drive_acceptance':True}
        self.ns['sys']=Box(modules={'map_drive_acceptance':Box(note_movement_call=lambda *args:self.notes.append(args))})
        self.profile=self.ns['profile_calls']
        self.owner=Box()

    def invoke(self,parent=None,source='scripts/client/Avatar.py',line=2130):
        f=frame(source,'moveVehicle',line,self.owner,parent=parent)
        f.f_locals.update(flags=1,isKeyDown=True,other='must-not-leak')
        self.profile(f,'call',None)
        f.f_lasti=345
        self.profile(f,'return',None)
        return f

    def caller_rows(self):
        return [row for event,row in self.events if event=='native_map_drive_movement_caller']

    def test_separate_event_correlates_one_entry_without_changing_strict_data(self):
        parent=MetadataFrame('scripts/client/Avatar.py','moveVehicleByCurrentKeys',2072,30)
        self.invoke(parent)
        self.assertEqual([e for e,r in self.events],['native_map_drive_movement_call','native_map_drive_movement_caller','native_map_drive_movement_call'])
        entry,meta,returned=[r for e,r in self.events]
        self.assertEqual((entry['call_id'],entry['owner_id']),(meta['call_id'],meta['owner_id']))
        self.assertEqual(entry['call_id'],returned['call_id'])
        self.assertEqual(meta['source_line'],2130)
        self.assertEqual(meta['phase'],'call')
        self.assertEqual(meta['offset'],-1)
        self.assertEqual(meta['caller_frames'],[dict(source='scripts/client/Avatar.py',method='moveVehicleByCurrentKeys',source_line=2072,offset=30)])
        self.assertFalse(meta['truncated'])
        self.assertEqual([r['data'] for r in (entry,returned)],[dict(flags=1,is_key_down=True)]*2)
        self.assertEqual(len(self.notes),2)
        self.assertTrue(all(len(args)==7 for args in self.notes))
        self.assertEqual(self.notes[0][-1],dict(flags=1,is_key_down=True))
        self.assertNotIn('caller_frames',entry)
        self.assertNotIn('must-not-leak',json.dumps(self.events))

    def test_real_nested_owned_frames_are_read_as_metadata_only(self):
        # Execute only this explicit test fixture, never original client code.
        owned_source=('def outer(profile, child, getframe):\n'
                      '    password="fixture-secret-never-recorded"\n'
                      '    def inner():\n'
                      '        unrelated={"token":password}\n'
                      '        child.f_back=getframe()\n'
                      '        profile(child,"call",None)\n'
                      '        child.f_back=None\n'
                      '    inner()\n')
        namespace={}
        execute_trusted(compile(owned_source,'map_drive_acceptance.py','exec'),namespace)
        child=frame('scripts/client/Avatar.py','moveVehicle',2130,self.owner)
        child.f_locals.update(flags=1,isKeyDown=True)
        namespace['outer'](self.profile,child,sys._getframe)
        rows=self.caller_rows()[0]['caller_frames']
        self.assertEqual([r['source'] for r in rows[:2]],['map_drive_acceptance.py']*2)
        self.assertEqual([r['method'] for r in rows[:2]],['inner','outer'])
        self.assertTrue(all(type(r['offset']) is int and r['offset']>=0 for r in rows[:2]))
        text=json.dumps(self.events)
        self.assertNotIn('fixture-secret',text)
        self.assertNotIn('unrelated',text)
        self.assertIsNone(child.f_back)

    def test_six_frames_bounded_and_no_locals_or_globals_read(self):
        parent=None
        for i in range(12):
            parent=MetadataFrame('scripts/client/Avatar.py','level_'+str(i),i+1,i,parent)
        self.invoke(parent)
        row=self.caller_rows()[0]
        self.assertEqual(len(row['caller_frames']),6)
        self.assertEqual([r['method'] for r in row['caller_frames']],['level_'+str(i) for i in range(11,5,-1)])
        self.assertTrue(row['truncated'])
        self.assertEqual(row['depth_limit'],6)

    def test_foreign_absolute_or_escaped_paths_and_strings_are_not_logged(self):
        for value in ('C:/private/secret-folder/password.py','scripts/../private.py',
                      'scripts//client/file.py','scripts/client/secret\nname.py',
                      'scripts/'+('x'*193)+'.py',b'\xff',object()):
            self.events[:]=[]
            self.invoke(MetadataFrame(value,'private_secret_name'))
            row=self.caller_rows()[0]['caller_frames'][0]
            self.assertEqual(row['source'],'<unknown>')
            self.assertEqual(row['method'],'<unknown>')
            self.assertNotIn('private_secret',json.dumps(self.events))
        self.events[:]=[]
        self.invoke(MetadataFrame('scripts\\client\\Avatar.py'))
        self.assertEqual(self.caller_rows()[0]['caller_frames'][0]['source'],'scripts/client/Avatar.py')

    def test_unsupported_method_or_numeric_metadata_is_explicit_unknown(self):
        self.invoke(MetadataFrame('map_drive_client.py','secret\nname',True,float('nan')))
        row=self.caller_rows()[0]['caller_frames'][0]
        self.assertEqual(row['method'],'<unknown>')
        self.assertIsNone(row['source_line']);self.assertIsNone(row['offset'])

    def test_no_python_caller_is_recorded_without_fabricating_one(self):
        self.invoke()
        self.assertEqual(self.caller_rows()[0]['caller_frames'],[])
        self.assertFalse(self.caller_rows()[0]['truncated'])

    def test_normal_other_probe_false_or_truthy_nonboolean_flag_is_off(self):
        for control in (None,{}, {'probe_map_drive':True}, {'probe_map_drive_acceptance':False},
                        {'probe_map_drive_acceptance':1}):
            self.events[:]=[];self.notes[:]=[]
            self.ns['_control']=control
            if control and control.get('probe_map_drive'):
                self.ns['sys'].modules['map_drive_scenario']=Box(note_movement_call=lambda *args:None)
            self.invoke(MetadataFrame('scripts/client/Avatar.py'))
            self.assertEqual(self.caller_rows(),[])

    def test_only_exact_original_method_source_and_line_enter_this_observer(self):
        for source,line in (('foreign/Avatar.py',2130),('scripts/client/Avatar.py',2131)):
            self.events[:]=[]
            self.invoke(MetadataFrame('map_drive_acceptance.py'),source,line)
            self.assertEqual(self.caller_rows(),[])


if __name__=='__main__':
    unittest.main()
