"""Independent six-command #717 dismissal/sparse-crew, source, wire and immutable DB verifier.

Only bounded evidence readers and independent historical descriptor checks are
reused. No production dismissal codec, projection or store is imported.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
from contextlib import closing
import sqlite3
import json
import math
from pathlib import Path
import re
import struct
import zlib
import zipfile
from cryptography.hazmat.primitives import serialization
from p04d_native_crew_verify import (EvidenceError, require, integer, digest, canonical, read,
    owned, json_value, rows, capture, literal, same_literal, ROOT, LOCAL, PINS)
from p04f_native_crew_verify import database as table_database, only, document, validate_ammunition
from p04h_native_crew_verify import expected_descriptor, decode_descriptor as decode_unskilled
from p04j_crew_source_audit import audit_sources, read_application, swf_body
from p04i_native_crew_verify import decode_descriptor, LEARNING, HIRES, ROLE_IDS

SCHEMA = 'p04j-native-crew-dismissal.v1'
COMMAND = 'p04j.crew_transfer.v1'
RECRUIT_COMMAND = 'p04j.recruit_assign.v1'
DISMISS_COMMAND = 'p04j.dismiss.v1'
COMMANDS = {105: COMMAND, 306: DISMISS_COMMAND, 309: RECRUIT_COMMAND}
STATUSES = {105: 'transferred', 306: 'dismissed', 309: 'recruited'}
POLICY = 'c7f6d05be033d7ea75b8be50b3a4578d6a4167a9d3d5dc4ea8975878633c74b2'
PREVIOUS_SCHEMA = 'p04i-native-crew-progression.v1'
PREVIOUS_POLICY = 'fd79729bbaf926fe2567382be086c5e730c7c6474debe338b3052bb12ba62184'
PREVIOUS_AUDIT = 'dda516c73da6cda8d838e3366888d4fca58f06bc798fa5de4f8425ec2020fa48'
RETAINED_AUDITS = {
 'p04d': ('crew_source_audit_sha256','27963458df43427b14c8bdc990f53a3c30154a8582c6db876560822eeed4e3ca'),
 'p04f': ('crew_transfer_source_audit_sha256','b4a7dd9dd4bdb5f106460a9f5b681b0b1944fd83bf05662e2bba4e9f1f0164d3'),
 'p04g': ('crew_cross_source_audit_sha256','e0693e0e36d2b5ca0c72e584684439b3b1c6eecfa9709b06820cbbc8832c7cb9'),
 'p04h': ('crew_roster_source_audit_sha256','db7179a139d7caabd92aa1026f20e163c5a8583267bb0a1aa95541d248abf585'),
 'p04i': ('crew_progression_source_audit_sha256',PREVIOUS_AUDIT)}
UI_POLICY = 'test_lab.ms1_is7.dismissal.sparse16.no_refund.v1'
ROLES = {1:('commander','driver'),2:('commander','gunner','driver','loader','loader')}
STEPS = (('dismiss_learned_3','GUI.handleKeyEvent',['KEY_RETURN','down','up'],[3,0,0],306),
 ('dismiss_seated_5','GUI.handleKeyEvent',['KEY_RETURN','down','up'],[5,0,0],306),
 ('hire_driver_11','RecruitWindow.buyTankman',[0,13,'driver',0,1],[3,1,1,0],309),
 ('seat_learned_2','Crew.equipTankman',[2,1],[1,1,2],105),
 ('unload_learned_2','Crew.unloadTankman',[2],[1,1,-1],105),
 ('restore_driver_11','Crew.equipTankman',[11,1],[1,1,11],105))
INITIAL_SEATS = {1:[4,5],2:[6,7,8,10,9]}
FINAL_SEATS = {1:[4,11],2:[6,7,8,10,9]}
REQUIRED_SOURCES = {'client_patch/'+name+'.py' for name in (
 'p04j_crew_ui','p04i_crew_ui','p04h_crew_ui','p04g_crew_ui','p04f_crew_ui','p04d_crew_ui','p09d_ammo_ui',
 'sr_interactive','crew_capabilities','hangar_bootstrap')}
MEMBER_FIELDS = {'native_id','crew_id','role','descriptor_hex','vehicle_native_id','seat'}
RESPONSE_FIELDS = {'status','account_id','native_database_id','command_key','revision','wire_revision','update_hex','replayed','result_code'}
IMPLEMENTATION_SOURCES = tuple(sorted(REQUIRED_SOURCES | {
 'tools/p04j_native_crew_verify.py','tools/p04j_crew_source_audit.py','tools/p04j_dismissal_flash.py',
 'tools/p04j_crew_store.py','tools/p04j_crew_projection.py','server/gateway/src/account/crew_dismissal.rs','web/src/p04j-crew.mjs',
 'tools/p04i_native_crew_verify.py','tools/p04h_native_crew_verify.py','tools/p04f_native_crew_verify.py','tools/p04d_native_crew_verify.py',
 'tools/p04i_crew_source_audit.py','tools/p04i_tankman_descriptor.py','tools/p04i_crew_store.py','tools/p04i_crew_projection.py',
 'tools/p04h_tankman_descriptor.py','tools/p04h_crew_store.py','tools/p04h_crew_projection.py',
 'tools/p04f_crew_store.py','tools/p04g_crew_store.py','tools/interactive_client.py',
 'server/gateway/src/account/ammo_session.rs','server/gateway/src/account/crew_service.rs',
 'server/gateway/src/account/crew_transfer.rs','server/gateway/src/account/crew_progression.rs',
 'server/gateway/src/account/hangar.rs','server/gateway/src/account/identity.rs','server/gateway/src/session.rs',
 'server/gateway/src/main.rs','web/src/game-adapter.mjs','web/src/p04d-crew.mjs','web/src/p04i-crew.mjs'}))

def implementation_sources():
    # Current source provenance only. The gateway executable/build and process chain
    # are intentionally separate receipts; file hashes alone do not prove execution.
    pins=[]
    for name in IMPLEMENTATION_SOURCES:
        raw=read(ROOT/name)
        pins.append(dict(path=name,bytes=len(raw),sha256=digest(raw)))
    return pins




INPUT_SOURCE_PINS = {
    'client/gui/shared/utils/key_mapping.pyc':(4997,'940d65e05aef49045491f5bd2e8ae81d750853f259a05c99e9645b4f87034d4e'),
    'client/game.pyc': (15663, '2f2057748cbbbaefe21c5fd434cc1492bd08521f705f43832e45e493af6896c1'),
    'client/webbrowser.pyc': (19675, 'bf3d996a715775cfe0d97e3c1205ed474f2e4413d9c3db1961587d917c0b55de'),
    'client/gui/scaleform/daapi/view/meta/simpledialogmeta.pyc':
        (1944,'5456c520c313033f6049a58691774fec5db15ca5d148a3bfc35cb0ca9ac7291c')}
INPUT_ANCHORS = (
    ('client/gui/shared/utils/key_mapping.pyc','<module>',2,
        {829:('LOAD_ATTR','KEY_RETURN'),979:('LOAD_ATTR','KEY_LEFTARROW')}),
    ('client/webbrowser.pyc','<module>.WebBrowser.__init__',55,
        {91:('LOAD_GLOBAL','Keys'),94:('LOAD_ATTR','KEY_LEFTARROW')}),
    ('client/game.pyc','<module>.handleKeyEvent',401,
        {188:('LOAD_GLOBAL','GUI'),191:('LOAD_ATTR','handleKeyEvent'),194:('LOAD_FAST','event'),197:('CALL_FUNCTION',1)}),
    ('client/webbrowser.pyc','<module>.WebBrowser.browserDown',223,
        {122:('LOAD_GLOBAL','BigWorld'),125:('LOAD_ATTR','KeyEvent'),131:('LOAD_ATTR','KEY_LEFTMOUSE'),
         134:('LOAD_CONST',0),137:('LOAD_CONST',0),140:('LOAD_CONST',None),143:('LOAD_FAST','x'),146:('LOAD_FAST','y'),152:('CALL_FUNCTION',5)}),
    ('client/webbrowser.pyc','<module>.WebBrowser.browserUp',241,
        {53:('LOAD_GLOBAL','BigWorld'),56:('LOAD_ATTR','KeyEvent'),62:('LOAD_ATTR','KEY_LEFTMOUSE'),
         65:('LOAD_CONST',-1),68:('LOAD_CONST',0),71:('LOAD_CONST',None),74:('LOAD_FAST','x'),77:('LOAD_FAST','y'),83:('CALL_FUNCTION',5)}),
    ('client/gui/scaleform/daapi/view/meta/simpledialogmeta.pyc','<module>.SimpleDialogMeta.as_setButtonFocusS',59,
        {3:('LOAD_ATTR','_isDAAPIInited'),15:('LOAD_ATTR','flashObject'),18:('LOAD_ATTR','as_setButtonFocus'),
         21:('LOAD_FAST','id'),24:('CALL_FUNCTION',1)}))


def input_source_audit(original_root):
    """Acceptance companion; never changes the domain J source audit digest."""
    from p04j_crew_source_audit import static, pinned_read
    root=Path(original_root)
    require(root.is_absolute(),'absolute original input source root')
    raw={name:pinned_read(static.no_links(root/'res/scripts'/name),pin) for name,pin in INPUT_SOURCE_PINS.items()}
    # Only instructions needed for these exact pinned anchors are decoded.
    table={100:'LOAD_CONST',106:'LOAD_ATTR',116:'LOAD_GLOBAL',124:'LOAD_FAST',131:'CALL_FUNCTION'}
    proofs=[]
    for source,name,line,expected in INPUT_ANCHORS:
        found=[row for row in static.inspect(raw[source],table) if row['qualified_name']==name]
        require(len(found)==1 and found[0]['firstlineno']==line,'original input source record')
        ins={r['offset']:r for r in found[0]['instructions']}
        for offset,(op,value) in expected.items():
            require(offset in ins and ins[offset]['opname']==op and ins[offset].get('value',ins[offset].get('arg'))==value,'original input source semantic anchor')
        proofs.append(dict(source_id='res/scripts/'+source,record=name,firstlineno=line,verified_offsets=sorted(expected)))
    movie=read_application(root);body=swf_body(movie)
    focus=[]
    for index,name,offset,size,sha in (
        (620,'UIComponent.focused.set',1965420,255,'20091b8108d0231e41cc3d1c96ebfb66e555ad190465aee9d9057bc11e17f8c9'),
        (619,'UIComponent.focused.get',1965403,7,'169c75e9d2c3b329d2f7a7533f5bb2e6aa17f6ea2b3c27f1b5b288ca0f675c11'),
        (2445,'Button.handleInput',2060173,160,'92653ec50347a8554cb8e4101c6672718eb74fa4523e62d54e16ef241393c823'),
        (2461,'Button.handlePress',2062914,169,'95c1d1ed4f9cbc717f1e353e5e4aa63f7d4a55f9d8ad82a3e157e7f9dcb7ad15'),
        (2462,'Button.handleRelease',2063093,166,'d5d5c98613cd65ce2230b6dbc77cd8fd039db51520061d3b589faab3ebad76f9'),
        (3308,'SimpleDialog.as_setButtonFocus',2115661,19,'b4a0f355c65486ffe2021d8a43ef69d4e151e82b3db346048a152caa2c0c423f'),
        (3316,'SimpleDialog.draw',2115976,344,'89407d7f0f4eff9a0258322ec37ce1621e8a74b63f3e5382f723a444920a46e8'),
        (13024,'DismissTankmanDialog.onRequestFocusHandler',2632098,67,'51e5f70527d4a11ac0602ef89e52602c32223d6165af3d263b0f9aa14258fd33')):
        require(digest(body[offset:offset+size])==sha,'original Application Flash button focus method')
        focus.append(dict(method_index=index,method=name,offset_in_body=offset,bytes=size,sha256=sha))
    return dict(flash_focus=focus,flash_resource=APPLICATION_RESOURCE,flash_sha256=digest(movie),status='PASS_STATIC_ORIGINAL_KEYEVENT_BRIDGE',sources=[dict(source_id='res/scripts/'+n,bytes=p[0],sha256=p[1]) for n,p in sorted(INPUT_SOURCE_PINS.items())],
        assertions=proofs,constructor='BigWorld.KeyEvent(key, down0_or_up_minus1, 0, None, (x,y))',
        source_constructor_use='original WebBrowser left mouse event',dispatcher='GUI.handleKeyEvent(event)',
        keyboard_enter_for_original_confirmation='INFERRED_UNTIL_NATIVE_CAPTURE',physical_input='NOT_RUN')


APPLICATION_RESOURCE = 'gui/flash/Application.swf'
REGISTERED_DIALOG = 'gui/flash/dismissTankmanDialog.swf'
REGISTERED_DIALOG_SHA = '33a92ccdcf2ef278e41e5ca1dd349e2eff3f323486e9a1c3065d0809336fffe5'
REGISTERED_DIALOG_BODY_SHA = '2d10a1d4c6b92cc4c8c4408684026fd934aaffd21631ec6467d3057539eb95c5'


def read_registered_dialog(original_root):
    # The inherited reader bounds the package and its central directory before
    # opening it. The second exact member is also bounded and pinned before use.
    root=Path(original_root);read_application(root)
    with zipfile.ZipFile(root/'res/packages/gui.pkg') as archive:
        entries=[info for info in archive.infolist() if info.filename==REGISTERED_DIALOG]
        require(len(entries)==1 and entries[0].file_size==132797 and entries[0].compress_size<=132797,
            'original registered dismissal resource member bounds')
        raw=archive.read(entries[0])
    require(len(raw)==132797 and digest(raw)==REGISTERED_DIALOG_SHA,'original registered dismissal resource pin')
    return raw


def registered_dialog_source_audit(original_root):
    from p04j_crew_source_audit import static,pinned_read
    pins={
        'client/gui/scaleform/daapi/settings/__init__.pyc':
            (15074,'eb47b23db5f7a3b56928a21c324266e32a1e588c3e15b04b69cac2281e509c1f'),
        'client/gui/scaleform/daapi/settings/views.pyc':
            (4166,'5c7984c7c246f60155b229d3202bd1786374b23ddd0fd866e3bf4fe80adeab8b'),
        'client/gui/scaleform/daapi/view/meta/dismisstankmandialogmeta.pyc':
            (758,'0ce280e7a068a1dc24485a3795505129ca2428bd18b27e3031d98ef5157caa5e')}
    anchors=(
        ('client/gui/scaleform/daapi/settings/__init__.pyc','<module>',
         {2910:('LOAD_NAME','GroupedViewSettings'),2916:('LOAD_ATTR','DISMISS_TANKMAN_DIALOG'),
          2919:('LOAD_NAME','DismissTankmanDialog'),2922:('LOAD_CONST','dismissTankmanDialog.swf'),
          2928:('LOAD_ATTR','TOP_WINDOW'),2943:('CALL_FUNCTION',7)}),
        ('client/gui/scaleform/daapi/settings/views.pyc','<module>.VIEW_ALIAS',
         {384:('LOAD_CONST','dismissTankmanDialog'),387:('STORE_NAME','DISMISS_TANKMAN_DIALOG')}),
        ('client/gui/scaleform/daapi/view/meta/dismisstankmandialogmeta.pyc','<module>.DismissTankmanDialogMeta.as_tankManS',
         {3:('LOAD_ATTR','_isDAAPIInited'),15:('LOAD_ATTR','flashObject'),18:('LOAD_ATTR','as_tankMan'),
          21:('LOAD_FAST','value'),24:('CALL_FUNCTION',1)}))
    table={90:'STORE_NAME',100:'LOAD_CONST',101:'LOAD_NAME',106:'LOAD_ATTR',124:'LOAD_FAST',131:'CALL_FUNCTION'}
    proof=[]
    for name,qualified,expected in anchors:
        raw=pinned_read(static.no_links(Path(original_root)/'res/scripts'/name),pins[name])
        found=[row for row in static.inspect(raw,table) if row['qualified_name']==qualified]
        require(len(found)==1,'original registered dialog source record')
        instructions={row['offset']:row for row in found[0]['instructions']}
        for offset,(op,value) in expected.items():
            require(offset in instructions and instructions[offset]['opname']==op
                and instructions[offset].get('value',instructions[offset].get('arg'))==value,
                'original registered dialog source semantic anchor')
        proof.append(dict(source_id='res/scripts/'+name,bytes=len(raw),sha256=digest(raw),
            record=qualified,firstlineno=found[0]['firstlineno'],verified_offsets=sorted(expected)))
    raw=read_registered_dialog(original_root)
    return dict(status='PASS_STATIC_REGISTERED_DISMISSAL_MOVIE',sources=proof,
        resource=dict(path=REGISTERED_DIALOG,bytes=len(raw),sha256=digest(raw)),
        original_alias='dismissTankmanDialog',original_setter='flashObject.as_tankMan(value)',
        same_named_application_class_is_not_runtime_proof=True,actual_loaded_class_domain='UNKNOWN_UNTIL_NATIVE_WINDOW')


def validation_source_audit(original_root):
    """Separate source proof of control equality; not a fabricated syntax flag."""
    from p04j_crew_source_audit import static,pinned_read
    pins={
        'client/gui/scaleform/daapi/view/meta/inputcheckermeta.pyc':(2203,'f4b22719abbaf8c696d56cc4848c495baa9a47041a4070f239fc63ab39944c4b'),
        'client/gui/scaleform/daapi/view/lobby/inputchecker/inputchecker.pyc':(3641,'80a2da5a05e7afc4954134f0c21a8e6ed07520727c4d6c3ac8d57a8dc3a2a2e5')}
    raw={name:pinned_read(static.no_links(Path(original_root)/'res/scripts'/name),pin) for name,pin in pins.items()}
    observers=[]
    for source,method,line,sha in (
        ('client/gui/scaleform/daapi/view/meta/inputcheckermeta.pyc','as_setFormattedControlNumberS',50,'a07a7ee689046d4e29fdf9eec47a9e62036dd61fc57ba9dd88615e7fbac06313'),
        ('client/gui/scaleform/daapi/view/meta/inputcheckermeta.pyc','as_setOriginalControlNumberS',59,'a07a7ee689046d4e29fdf9eec47a9e62036dd61fc57ba9dd88615e7fbac06313'),
        ('client/gui/scaleform/daapi/view/lobby/inputchecker/inputchecker.pyc','sendUserInput',42,'cb9e860d3ec383bec93b13a02bf48ca85f40a8dd2cab78aa3334802699f94c89'),
        ('client/gui/scaleform/daapi/view/meta/inputcheckermeta.pyc','as_invalidUserTextS',68,'a07a7ee689046d4e29fdf9eec47a9e62036dd61fc57ba9dd88615e7fbac06313')):
        found=[r for _,r in static.records(static.parse_pyc(raw[source])) if r['name'].decode()==method and r['firstlineno']==line]
        require(len(found)==1 and digest(found[0]['code'])==sha,'original passive input observer source')
        observers.append(dict(source_id='res/scripts/'+source,method=method,line=line,code_sha256=sha))
    movie=read_application(Path(original_root));body=swf_body(movie);methods=[]
    for index,name,offset,size,sha in (
        (1044, 'Locale.parseFormattedInteger', 2004352, 157, '2156ed7e214c82eafcd797c862e796b25089a6784264d24cad62448e853d0db2'),
        (5581, 'UserInputControl.cmpFormatUserInputString', 2228090, 216, '8a1a2e920ea436613e5d3a6bd18d98c402d8b5f5b7fb994ce99cc564c3dae346'),
        (13439, 'InputChecker.as_invalidUserText', 2650127, 40, '76860e8204b54228a44b2157a8ccd9e0a16536548e60880eb1d66a7c79879efc'),
        (13440, 'InputChecker.as_setFormattedControlNumber', 2650176, 26, '7ed62b9ade685756c45cea31a2fa225faa359e2a14fdcc42c8c0293ae4c92344'),
        (13441, 'InputChecker.as_setOriginalControlNumber', 2650211, 8, '1adfc78aeacc121d6a8089b7ecd290f0dbc6569e2ac55f5d69d2ce081bb3ff78'),
        (13442, 'InputChecker.getUserText', 2650228, 36, '35ac0e74896628a70a7abcc491a167ae7cb478baa0c564831dfc9d4f8f12864f'),
        (13443, 'InputChecker.isInvalidUserText', 2650273, 7, '9163f32e18af39cb671a1770308d5e1a9bcb8392db28f706e055592d2c39e984'),
        (13444, 'InputChecker.isValidControlInput', 2650289, 44, '78fd87216dcf90cae481687f8ed837d113151945c12766b0a83393a9df51ae0d'),
        (13445, 'InputChecker.formattedControlText', 2650342, 7, 'ec278690ca9148d414466ebb0dc19c199e93fec3fd0baf3435472380aaa5aad3'),
        (13447, 'InputChecker.configUI', 2650433, 40, 'f3204226fdf52a8bff04fc3f93dc44f6fb5722b574981a293e0a721037df83b2'),
        (13448, 'InputChecker.runtimeValidate', 2650482, 13, 'ca01794eba82ee144e104425bbc2a3d6d0e936002c13f8a384d7c4c9c29ddeb6'),
        (13452, 'InputChecker.userInputHandler', 2650603, 124, '027808b04ea8c07ebcf2b545436bcd99a45b00833f45e648d958118817bafa67'),
):
        require(digest(body[offset:offset+size])==sha,'original input validator source pin')
        methods.append(dict(method_index=index,method=name,offset_in_body=offset,bytes=size,sha256=sha))
    return dict(status='PASS_STATIC_ORIGINAL_CONTROL_VALIDATION',resource=APPLICATION_RESOURCE,
        source_sha256=digest(movie),methods=methods,observers=observers,
        sources=[dict(source_id='res/scripts/'+n,bytes=p[0],sha256=p[1]) for n,p in pins.items()],
        assertions=['isValidControlInput is public Boolean getter, not a numeric syntax classifier',
            'creditsParseResult must exist before comparison against original/formatted control text',
            'the comparator accepts exact control text and rejects unrelated numeric text',
            'parseFormattedInteger constructs an object even for zero',
            'runtimeValidate is private and only updates error state',
            'native KEY_UP handler computes getUserText and validity before sendUserInputS'],
        runtime_initialization='REQUIRES_NATIVE_SETTER_AND_CALLBACK_EVIDENCE')


def rendered_source_audit(original_root):
    """Pin the unchanged native model-to-visible-widget chain independently."""
    movie=read_application(Path(original_root));body=swf_body(movie);methods=[]
    for index,name,offset,size,sha in (
        (6680, 'SkillItemViewMini.<class_init>', 2282990, 98, 'fc5383933bea42fef89cd97bc0dd0e493770ea647ac907a3b7602a8bd961d643'),
        (6681, 'SkillItemViewMini.<init>', 2283097, 6, '8ff32749a852a1d83829c6a3fac8ec00822f06b5c7177f9ebb43a09287b2101a'),
        (6682, 'SkillItemViewMini.onDispose', 2283112, 21, 'bbf27b75f762c94a21bc703b1918d0449f074caeccfe38ce575439d81806396f'),
        (6683, 'SkillItemViewMini.text', 2283142, 7, '9189595866a57d18824ecacb6f9448602a957372da829e1e63d2269c7bbc7751'),
        (6684, 'SkillItemViewMini.text', 2283158, 19, '5bddbea36c95814528e7d6788ecbc95c3ede8460355f5b66ffc025f6481d318b'),
        (6685, 'SkillItemViewMini.level', 2283186, 7, '6d2022478f038a3381596aec02077eb3fce78b4403cff528f2da8489d11126e6'),
        (6686, 'SkillItemViewMini.level', 2283202, 50, '92e6352eab8f8d2ce0a902b4c2bc841648e57b6c5c573726eb1d091ea524c606'),
        (6687, 'SkillItemViewMini.count', 2283261, 7, '15e464646114b7ff87413e80fc5a2a94d1db06a5ea1c2aec49d19193604a93ba'),
        (6688, 'SkillItemViewMini.count', 2283277, 26, 'e2f1d508958eaf0a2d068c3b50264c425724802b73a1681c790e499879569c93'),
        (6689, 'SkillItemViewMini.type', 2283312, 7, '65d8394c578c52b12436cd5865e0fde42cbbb254c19d9d8dc960b5c0254ae300'),
        (6690, 'SkillItemViewMini.type', 2283328, 23, 'bc046eee67cae6126c789a01a9cfdc0dc355303fdb5fd0390ea3b93f9090333e'),
        (6691, 'SkillItemViewMini.updateType', 2283360, 64, 'b4c27ddfcb1848b98ba4b89b2cda7ba1accc012bc615de9e6f70de7af1046558'),
        (6692, 'SkillItemViewMini.iconSource', 2283433, 10, '75848d3f2221bb5e4fc0f6876d857198eab80a00b0dceab01e3bf6370b8cfecb'),
        (6693, 'SkillItemViewMini.iconSource', 2283452, 24, '4ca19a2d255fe1d9a53d09ba5f286f022adaec4310dff83be62859ffeb0c3d55'),
        (20536, 'TankmanSkillsInfoBlock.<class_init>', 3110580, 3, 'a968960b201420953c59656517f78c74a88e3e2aebf37839d8e70f6e531134c4'),
        (20537, 'TankmanSkillsInfoBlock.<init>', 3110593, 6, '8ff32749a852a1d83829c6a3fac8ec00822f06b5c7177f9ebb43a09287b2101a'),
        (20538, 'TankmanSkillsInfoBlock.onDispose', 3110609, 107, 'ec5080a588241ad64c2aa80d03608ec9a2e1f7533da99b3963512ca3e0b7b7bb'),
        (20539, 'TankmanSkillsInfoBlock.configUI', 3110726, 8, '4740c1b64c3a7d34985f93a6bcadec12897b0bd97b35aa5e09d8ed078eb5399b'),
        (20540, 'TankmanSkillsInfoBlock.setTestViewData', 3110745, 141, 'a2646104c24851c1dd2be61ef2115b2464140fe33067fe622bf633669ccc3902'),
        (20541, 'TankmanSkillsInfoBlock.portraitSource', 3110896, 11, '5c6a4fd20f30cc4ef72ec6afb6bfda10185bd052dcd3f02f4e1ecbe8607f6279'),
        (20542, 'TankmanSkillsInfoBlock.portraitSource', 3110917, 12, 'ed96818ddaf1ea490788309e2b17076e5210378a6ad621f2a74d84f6c3ca1a08'),
        (20543, 'TankmanSkillsInfoBlock.roleSource', 3110939, 10, '632061b68d3d8259af86e933530b633db395ae6bc501a2ea2cce6660d3d3bd45'),
        (20544, 'TankmanSkillsInfoBlock.roleSource', 3110959, 11, '41a834a4a4d9301a18c942461a4c8ee645f14a84049157823767625d487987d5'),
        (20545, 'TankmanSkillsInfoBlock.tankmanName', 3110980, 10, 'f28b6e6830a8835299622b12f16af7f7ec12ce2198ad0fc85b1c410a4d291db2'),
        (20546, 'TankmanSkillsInfoBlock.tankmanName', 3111000, 11, '30bf72152603230f78322ec1288e837f18dea15d2e6345c2e674bfc8ef8a3818'),
        (20547, 'TankmanSkillsInfoBlock.nation', 3111021, 8, 'd5ecab3bcf532935d08cf5c393652b3f4ba391ce3422ce564024b7bbf759b139'),
        (20548, 'TankmanSkillsInfoBlock.nation', 3111039, 24, '2277ea7a1e16bf05ee25ec93b0cc4c987cb5898662c0b5a268ac5af330027516'),
        (20549, 'TankmanSkillsInfoBlock.setRoleLevel', 3111073, 94, 'd7ee115eb281fe069984fee01d37772a666defec8ccb4e9d60a82b0d9bec5f72'),
        (20550, 'TankmanSkillsInfoBlock.setSkills', 3111178, 269, '6522ce4c944578bfdf00f0a9a33e6695d2ef37c63717919e53568aa62a5c4c81'),
        (20551, 'TankmanSkillsInfoBlock.buildCurrentSkill', 3111457, 56, 'bcc858df776928779acf3e8ec663c160faddc9c78263829a52b23417cbf01ad7'),
        (20552, 'TankmanSkillsInfoBlock.buildSkillsPack', 3111523, 99, 'fdb06651d14ba8be6367527cb21e059db2177b8cffde2cee213e7140a5f6f97f'),
        (13018, 'DismissTankmanDialog.draw', 2631643, 40, '08a59e1e4161fe33329fa84e23c7d7d998f2fe72791e7f6a808cab831ef0fa84'),
        (13023, 'DismissTankmanDialog.setData', 2631934, 155, 'f189beb31d72f5bd1ecccf997ba10065911adc95405aa8e432a29d87e79f48d2'),
    ):
        require(digest(body[offset:offset+size])==sha,'original rendered widget source pin')
        methods.append(dict(method_index=index,method=name,offset_in_body=offset,bytes=size,sha256=sha))
    return dict(status='PASS_STATIC_ORIGINAL_RENDER_CHAIN',resource=APPLICATION_RESOURCE,
        source_sha256=digest(movie),methods=methods,
        assertions=['original draw requires truthy native model before setData',
            'original setData reads name/portrait/role/nation and skill/qualification fields',
            'qualification setter writes native text percentage and frontPosition',
            'single learned0 skill uses visible current_skill/icon/level0 and original count default0',
            'simple50 confirmation passes minus1 skill count and hides all four skill widgets'],
        typed_model_getter='RUNTIME_AVAILABILITY_RECORDED_SEPARATELY')


TERMINAL_TRIGGERS = {name: "CREATE TRIGGER " + name + " BEFORE " + action +
    " ON p04j_retired_member BEGIN SELECT RAISE(ABORT,'terminal crew is immutable'); END"
    for name,action in (('p04j_retired_no_update','UPDATE'),('p04j_retired_no_delete','DELETE'))}


def database(path):
    result=table_database(path);location=owned(path)
    with closing(sqlite3.connect(location.as_uri()+'?mode=ro&immutable=1',uri=True)) as connection:
        connection.set_progress_handler(lambda:1,100000)
        values=connection.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' AND tbl_name='p04j_retired_member' ORDER BY name LIMIT 5").fetchall()
    require(len(values)==2 and dict(values)==TERMINAL_TRIGGERS,'exact terminal immutability triggers required')
    require(digest(read(location))==result['sha256'],'database changed during schema audit')
    result['terminal_triggers']=dict(values)
    return result


def decode_request(body):
    require(type(body) is bytes and len(body) in (23,27),'bounded native crew request')
    if body[:3]==b'\x8e\x14\0' and len(body)==23:
        rid,cmd,*layout=struct.unpack_from('<hhqii',body,3)
        require(cmd in (105,306),'Int3 command')
    elif body[:3]==b'\x90\x18\0' and len(body)==27:
        rid,cmd,*layout=struct.unpack_from('<hhqiii',body,3)
        require(cmd==309,'Int4 command')
    else:raise EvidenceError('native Int3/Int4 VAR2 framing')
    require(integer(rid,1,32767) and any(cmd==s[4] and same_literal(layout,s[3]) for s in STEPS),'dismissal scenario request selection')
    return rid,cmd,layout


def crew_seats(value,account):
    require(type(value) is dict and set(value)=={'policy_sha256','free_recruitment_left','next_native_id','configuration_revision','members','retired_members'},'sparse crew inventory fields')
    require(value['policy_sha256']==POLICY and integer(value['next_native_id'],11,12)
        and type(value['free_recruitment_left']) is int and value['free_recruitment_left']==17-value['next_native_id']
        and integer(value['configuration_revision'],39,45),'lifetime allocator/quota/configuration')
    seats={1:[None]*2,2:[None]*5};seen=set();crew_ids=set()
    for kind in ('members','retired_members'):
        members=value[kind];require(type(members) is list and len(members)<=11,'bounded sparse membership')
        previous=0
        for row in members:
            require(type(row) is dict and set(row)==MEMBER_FIELDS and integer(row['native_id'],1,11),'member identity fields')
            n=row['native_id'];require(n>previous and n not in seen,'sorted disjoint lifetime IDs');previous=n;seen.add(n)
            encoded=row['descriptor_hex'];require(type(encoded) is str and re.fullmatch(r'[0-9a-f]{50}(?:[0-9a-f]{2})?',encoded),'canonical descriptor')
            raw=bytes.fromhex(encoded);desc=decode_descriptor(raw)
            if n<=3:
                role='commander' if n==1 else 'driver'
                identity=account+':ms1-'+role+'-v1' if n<3 else account+':recruit-ms1-driver:3'
                require(digest(bytes.fromhex(desc['plain_hex']))==PINS[0 if n==1 else 1]
                    and desc['skill_indices']==[LEARNING[n][1]],'retained learned descriptor/passport')
            else:
                vehicle,_,role=HIRES[n-4] if n<=10 else (1,1,'driver')
                identity=account+':recruit-crew:'+str(n)
                require(raw==expected_descriptor(n,{1:13,2:28}[vehicle],role),'source-derived hired passport/level')
            require(row['crew_id']==identity and row['crew_id'] not in crew_ids and row['role']==desc['role']==role,'unique domain identity/role')
            crew_ids.add(identity);vehicle,seat=row['vehicle_native_id'],row['seat']
            require(type(vehicle) is int and vehicle in (-1,1,2),'owned assignment')
            if vehicle==-1:require(seat is None,'barracks null seat')
            else:
                require(integer(seat,0,len(ROLES[vehicle])-1) and ROLES[vehicle][seat]==role,'primary-compatible seat')
                if kind=='members':
                    require(seats[vehicle][seat] is None,'unique active seat');seats[vehicle][seat]=n
            if kind=='retired_members':require(n in (3,5),'only expected retired identities')
    require(seen==set(range(1,value['next_native_id'])),'complete active/retired lifetime partition')
    return seats


def expected_transition(before,step,account):
    value=deepcopy(before);crew_seats(value,account)
    layout,cmd=step[3],step[4];by_id={m['native_id']:m for m in value['members']}
    if cmd==306:
        require(layout[1:]==[0,0] and layout[0] in by_id,'owned active dismissal')
        row=by_id[layout[0]];value['members'].remove(row);value['retired_members'].append(row)
        value['retired_members'].sort(key=lambda m:m['native_id'])
    else:
        if cmd==309:
            require(layout==[3,1,1,0] and value['next_native_id']==11 and value['free_recruitment_left']==6,'one monotonic free hire')
            vehicle,seat,identity=1,1,11
            raw=expected_descriptor(11,13,'driver')
            row=dict(native_id=11,crew_id=account+':recruit-crew:11',role='driver',descriptor_hex=raw.hex(),vehicle_native_id=-1,seat=None)
            value['members'].append(row);by_id[11]=row
            value.update(next_native_id=12,free_recruitment_left=5)
        else:
            require(cmd==105,'supported transfer');vehicle,seat,identity=layout
        for row in value['members']:
            if row['vehicle_native_id']==vehicle and row['seat']==seat:row.update(vehicle_native_id=-1,seat=None)
        if identity!=-1:
            require(identity in by_id and by_id[identity]['vehicle_native_id']==-1,'barracks selectable retained identity')
            by_id[identity].update(vehicle_native_id=vehicle,seat=seat)
    value['configuration_revision']+=1;crew_seats(value,account)
    return value


def check_delta(raw,wire_revision,before,after,account,command):
    require(type(raw) is bytes and 1<=len(raw)<=240 and integer(wire_revision,2),'bounded dismissal delta')
    seats=crew_seats(after,account);crew_seats(before,account)
    old={m['native_id']:m for m in before['members']};new={m['native_id']:m for m in after['members']}
    removed=set(old)-set(new);added=set(new)-set(old)
    expected={b'prevRev':wire_revision-1,b'rev':wire_revision,b'inventory':{1:{b'crew':seats},8:{}}}
    if command==306:
        require(len(removed)==1 and not added,'one dismissal descriptor deletion')
        identity=next(iter(removed));expected[b'inventory'][8]={b'compDescr':{identity:None},b'vehicle':{identity:None}}
    else:
        require(not removed and len(added)==int(command==309),'incremental membership delta')
        assignments={n:m['vehicle_native_id'] for n,m in new.items() if n not in old or any(m[k]!=old[n][k] for k in ('vehicle_native_id','seat'))}
        require(assignments,'assignment mutation');expected[b'inventory'][8][b'vehicle']=assignments
        if command==309:
            require(added=={11},'monotonic new ID');expected[b'inventory'][8][b'compDescr']={11:bytes.fromhex(new[11]['descriptor_hex'])}
            expected[b'stats']={b'freeTMenLeft':5}
        else:require(command==105,'supported delta command')
    require(same_literal(literal(raw),expected),'exact native deletion/hire/assignment delta')


def verify_databases(before, after, relogin, source_audit_sha):
    require(type(source_audit_sha) is str and re.fullmatch(r"[0-9a-f]{64}", source_audit_sha), "source audit digest required")
    require(all(d.get("terminal_triggers")==TERMINAL_TRIGGERS for d in (before,after,relogin)),"terminal trigger provenance")
    b, a, r = [d["tables"] for d in (before, after, relogin)]
    require(set(b) == set(a) == set(r), "database schema tables changed")
    mutable = {"game_snapshot", "game_profiles", "p04d_crew_meta", "p04d_crew_member", "game_command_ledger", "p09d_native_command", "game_limits", "p04j_retired_member"}
    for name in b:
        if name not in mutable:
            require(same_literal(b[name], a[name]), "unrelated table changed during transfer: " + name)
        if name != "game_limits":
            require(same_literal(a[name], r[name]), "table changed across fresh login: " + name)
    for tables in (b, a, r):
        require(all(only(tables, name) == {"version": SCHEMA} for name in ("p04j_schema", "p04i_schema", "p04h_schema", "p04g_schema", "p04f_schema", "p04d_schema")), "profile11 crew schema")
    snapshots = [document(only(t, "game_snapshot"), "snapshot_json", "snapshot_sha256") for t in (b, a)]
    profiles = [document(only(t, "game_profiles"), "profile_json") for t in (b, a)]
    account = only(b, "game_snapshot")["account_id"]
    require(type(account) is str and re.fullmatch(r"[0-9a-f-]{36}", account), "account identity")
    fmeta, meta0, meta1 = only(a,"p04j_crew_meta"), only(b,"p04d_crew_meta"), only(a,"p04d_crew_meta")
    require(fmeta.get('account_id')==account and fmeta.get('source_audit_sha256')==source_audit_sha,'J source audit binding')
    imported=only(b,'p09d_import');bundle_sha=imported.get('bundle_sha256')
    require(type(bundle_sha) is str and re.fullmatch(r'[0-9a-f]{64}',bundle_sha)
        and imported.get('account_id')==account and fmeta.get('source_bundle_sha256')==bundle_sha,'migration source bundle chain')
    for prefix,(aggregate_key,expected_sha) in RETAINED_AUDITS.items():
        retained=only(b,prefix+'_crew_meta')
        require(retained.get('account_id')==account and retained.get('source_bundle_sha256')==bundle_sha
            and retained.get('source_audit_sha256')==expected_sha,'retained source audit and bundle chain: '+prefix)
        require(all(snapshot.get(aggregate_key)==expected_sha for snapshot in snapshots),'retained aggregate source binding: '+prefix)
    previous_profile=deepcopy(profiles[0]);previous_profile.update(profile_version=10,snapshot_revision=48)
    previous_profile['crew_service'].update(schema=PREVIOUS_SCHEMA,policy_sha256=PREVIOUS_POLICY)
    require(same_literal(document(fmeta,'base_profile_json','base_profile_sha256'),previous_profile)
        and fmeta['base_profile_sha256']==digest(canonical(previous_profile)),'migration predecessor profile bytes/digest')
    initial, final = [s["crew_inventory"] for s in snapshots]
    require(crew_seats(initial, account) == INITIAL_SEATS and crew_seats(final, account) == FINAL_SEATS, "initial/final scenario assignments")
    base_crew=deepcopy(initial);base_crew['policy_sha256']=PREVIOUS_POLICY;base_crew.pop('retired_members')
    require(same_literal(document(fmeta,'base_crew_json','base_crew_sha256'),base_crew)
        and fmeta['base_crew_sha256']==digest(canonical(base_crew)),'migration predecessor crew bytes/state')
    require(not initial['retired_members'] and [m['native_id'] for m in initial['members']]==list(range(1,11)), 'initial accepted ten live members')
    require(initial["configuration_revision"] == 39 and final["configuration_revision"] == 45, "six configuration increments")
    first_revision = snapshots[0]["revision"]
    require(type(first_revision) is int and first_revision == 49
            and type(snapshots[1]["revision"]) is int and snapshots[1]["revision"] == 55
            and snapshots[1]["revision"] == first_revision + 6 and type(fmeta["base_revision"]) is int
            and fmeta["base_revision"] + 1 == first_revision, "six aggregate increments")
    unchanged0, unchanged1 = deepcopy(snapshots[0]), deepcopy(snapshots[1])
    for value in (unchanged0, unchanged1):
        value.pop("crew_inventory"); value.pop("revision")
    require(same_literal(unchanged0, unchanged1), "non-crew aggregate changed")
    for tables, snapshot, profile, inv, meta in zip((b, a), snapshots, profiles, (initial, final), (meta0, meta1)):
        srow, prow = only(tables, "game_snapshot"), only(tables, "game_profiles")
        require(srow["account_id"] == prow["account_id"] == profile["account_id"] == account
                and type(srow["revision"]) is int and srow["revision"] == snapshot["revision"]
                and type(profile["profile_version"]) is int and profile["profile_version"] == 11
                and type(profile["snapshot_revision"]) is int and profile["snapshot_revision"] == snapshot["revision"]
                and integer(profile["native_database_id"], 1) and prow["native_id"] == profile["native_database_id"], "profile identity/revision")
        require(snapshot['crew_schema']==SCHEMA and snapshot['crew_dismissal_source_audit_sha256']==source_audit_sha,
            'aggregate J source/policy binding')
        require(meta["account_id"] == account and meta["policy_sha256"] == POLICY and meta["free_left"] == inv["free_recruitment_left"]
                and meta["next_native_id"] == inv["next_native_id"] and meta["configuration_revision"] == inv["configuration_revision"], "crew metadata projection")
        members = sorted(tables["p04d_crew_member"], key=lambda x:x["native_id"])
        require(same_literal(members, [{"account_id":account, **m} for m in inv["members"]]), "member table differs from snapshot")
        retired=sorted(tables['p04j_retired_member'],key=lambda row:row['native_id'])
        require(same_literal([{k:row[k] for k in MEMBER_FIELDS} for row in retired],inv['retired_members']),
            'terminal member table differs from aggregate')
        for terminal in retired:
            require(set(terminal)==MEMBER_FIELDS|{'account_id','command_key','dismissed_revision','configuration_revision','member_sha256'}
                and terminal['account_id']==account and terminal['member_sha256']==digest(canonical({k:terminal[k] for k in MEMBER_FIELDS})),
                'terminal immutable member digest')

        require(type(profile["inventory"]) is list and len(profile["inventory"]) == 2, "two retained public vehicles")
        vehicle_ids = {n: profile["inventory"][n-1]["inventory_id"] for n in (1,2)}
        require(vehicle_ids == {1:account+":starter-vehicle-v1",2:account+":test-is7-v1"}
                and [v["vehicle_definition_id"] for v in profile["inventory"]]==["vehicle:ms1","vehicle:is7"],
                "retained MS1/IS7 public vehicle identities")
        expected_crew = [{"crew_id":m["crew_id"], "vehicle_inventory_id":vehicle_ids.get(m["vehicle_native_id"]),
                         "role":m["role"], "role_level":decode_descriptor(bytes.fromhex(m["descriptor_hex"]))["role_level"], "skills":[{"skill_id":name,"level":0} for name in decode_descriptor(bytes.fromhex(m["descriptor_hex"]))["skills"]]} for m in inv["members"]]
        require(same_literal(profile["crew"], expected_crew), "public crew projection")
        require(same_literal(profile.get("crew_service"), {"schema": SCHEMA, "policy_sha256": POLICY,
            "free_recruitment_left": inv["free_recruitment_left"], "configuration_revision": inv["configuration_revision"], "battle": False}),
            "public crew service projection")
        for n, seats in crew_seats(inv, account).items():
            require(profile["inventory"][n-1]["crew_assigned"] is all(v is not None for v in seats), "public partial crew flag")
    u0, u1 = deepcopy(profiles[0]), deepcopy(profiles[1])
    for value in (u0, u1):
        value.pop("crew"); value.pop("snapshot_revision")
        value["crew_service"].pop("configuration_revision");value["crew_service"].pop("free_recruitment_left")
        for vehicle in value["inventory"]: vehicle.pop("crew_assigned")
    require(same_literal(u0, u1), "public balances/ammunition/other fields changed")
    m0, m1 = dict(meta0), dict(meta1)

    for value in (m0,m1):
        for field in ("configuration_revision","free_left","next_native_id"):value.pop(field)
    require(same_literal(m0, m1), "crew metadata besides revision changed")
    require(not any(row["command_type"].startswith("p04j.") for row in b["game_command_ledger"]),"before scenario must contain no J command")
    ledger = [row for row in a["game_command_ledger"] if row["command_type"] in tuple(COMMANDS.values())]
    require(len(ledger) == 6 and not any(row["command_type"] in tuple(COMMANDS.values()) for row in b["game_command_ledger"]), "exact six new transfer commands")
    require(same_literal(b["game_command_ledger"], [row for row in a["game_command_ledger"] if row["command_type"] not in tuple(COMMANDS.values())]), "other command ledger changed")
    ledger.sort(key=lambda row:row["source_revision"])
    native = {row["command_id"]:row for row in a["p09d_native_command"]}
    require(len(native)==len(a["p09d_native_command"]), "unique native command identities")
    new_ids = {row["command_id"] for row in ledger}
    require(len(new_ids) == 6 and same_literal(b["p09d_native_command"], [row for row in a["p09d_native_command"] if row["command_id"] not in new_ids]), "native command count/provenance changed")
    operations, prior, wire_prior, session_nonce = [], initial, None, None
    for index, (row, step) in enumerate(zip(ledger, STEPS)):
        result = document(row, "result_json", "p09c_result_sha256")
        require(type(result) is dict and set(result) == {"schema", "command", "source_revision", "destination_revision", "before_crew", "after_crew", "response"}, "durable transfer result fields")
        match = re.fullmatch(r"p04j:([0-9a-f]{32}):([1-9][0-9]{0,4})", row["command_id"])
        require(match is not None and integer(int(match[2]), 1, 32767), "gateway command key")
        if session_nonce is None: session_nonce=match[1]
        require(match[1]==session_nonce, "single gateway session nonce required")
        require(row["account_id"] == account and result["schema"] == SCHEMA and result["command"] == row["command_type"] == COMMANDS[step[4]]
                and type(row["source_revision"]) is int and row["source_revision"] == first_revision + index
                and integer(result["source_revision"], 49) and integer(result["destination_revision"], 50)
                and result["source_revision"] == row["source_revision"] and row["destination_revision"] == row["source_revision"] + 1
                and result["destination_revision"] == row["destination_revision"], "ledger revision/order binding")
        expected = expected_transition(prior,step,account)
        require(same_literal(result["before_crew"], prior) and same_literal(result["after_crew"], expected), "exact six-step assignment transition")
        response = result["response"]
        require(type(response) is dict and set(response) == RESPONSE_FIELDS and response["status"] == STATUSES[step[4]]
                and response["account_id"] == account and response["command_key"] == row["command_id"]
                and type(response["native_database_id"]) is int and response["native_database_id"] == profiles[0]["native_database_id"]
                and type(response["revision"]) is int and response["revision"] == row["destination_revision"]
                and integer(response["wire_revision"], 2) and response["replayed"] is False
                and type(response["result_code"]) is int and response["result_code"] == 0, "durable transfer response")
        wire = response["wire_revision"]
        require(wire_prior is None or wire == wire_prior + 1, "six shared wire revision increments")
        req = dict(account_id=account, native_database_id=response["native_database_id"], command_key=row["command_id"],
                   expected_revision=row["source_revision"], wire_revision=wire-1, layout=step[3])
        nrow = native.get(row["command_id"])
        require(nrow is not None and nrow["account_id"] == account and nrow["request_sha256"] == digest(canonical(req))
                and row["payload_sha256"] == digest(canonical({"schema":SCHEMA,"policy_sha256":POLICY,"command":row["command_type"],"request":req})), "durable request/policy digest")
        require(same_literal(document(nrow, "response_json", "response_sha256"), response), "native ledger response differs")
        encoded = response["update_hex"]
        require(type(encoded) is str and re.fullmatch(r"(?:[0-9a-f]{2}){1,240}", encoded), "update hex bound")
        update = bytes.fromhex(encoded)
        check_delta(update, wire, prior, expected, account, step[4])
        if step[4]==306:
            terminal=next((m for m in a['p04j_retired_member'] if m['native_id']==step[3][0]),None)
            original=next(m for m in prior['members'] if m['native_id']==step[3][0])
            require(terminal is not None and terminal['command_key']==row['command_id']
                and type(terminal['dismissed_revision']) is int and terminal['dismissed_revision']==row['destination_revision']
                and type(terminal['configuration_revision']) is int and terminal['configuration_revision']==expected['configuration_revision']
                and same_literal({k:terminal[k] for k in MEMBER_FIELDS},original),'terminal dismissal journal provenance')
        operations.append(dict(request_id=int(match[2]), layout=step[3], native_cmd=step[4], response=response, update=update, before=prior, after=expected))
        prior, wire_prior = expected, wire
    require(same_literal(prior, final) and len({op["request_id"] for op in operations}) == 6, "final ledger/assignment identity")
    return {"account":account,"profile":profiles[1],"initial":initial,"final":final,"operations":operations,
        "database_proof": {"before":{k:v for k,v in before.items() if k!="tables"},"after":{k:v for k,v in after.items() if k!="tables"},
            "relogin":{k:v for k,v in relogin.items() if k!="tables"}, "source_revision":first_revision,"destination_revision":first_revision+6,
            "source_configuration_revision":39,"destination_configuration_revision":45,"source_audit_sha256":source_audit_sha,
            "same_relogin_tables":[n for n in a if n!="game_limits"],"rate_limit_table_excluded":"game_limits",
            "unchanged_ammunition_balances_passports_dossiers":True,"surviving_native_ids":[1,2,4,6,7,8,9,10],"new_native_ids":[11],"retired_native_ids":[3,5],"quota_before":6,"quota_after":5}}



def is_crew_command(body):
    return type(body) is bytes and body[:1] in (b'\x8e',b'\x90') and len(body)>=7 and struct.unpack_from('<h',body,5)[0] in (105,151,306,309)

def wire_evidence(frames, durable):
    operations = durable["operations"]
    found = {op["request_id"]:{"command":[],"update":[],"success":[]} for op in operations}
    by_id = {op["request_id"]:op for op in operations}
    seen = {}
    for order, frame in enumerate(frames):
        body, direction = frame["body"], frame["direction"]
        kind, rid = None, None
        if direction == "base_client_to_server" and is_crew_command(body):
            rid, cmd, layout = decode_request(body)
            require(rid in by_id and cmd==by_id[rid]["native_cmd"] and same_literal(layout, by_id[rid]["layout"]), "unexpected native transfer command")
            kind = "command"
        elif direction == "base_server_to_client" and body[:2] == b"\x13\x57":
            require(len(body)>=4 and len(body)==body[2]+3 and body[3]==len(body)-4, "update envelope")
            matching = [op["request_id"] for op in operations if op["update"] == body[4:]]
            require(len(matching)<=1, "ambiguous update revision")
            if matching:
                rid, kind = matching[0], "update"
        elif direction == "base_server_to_client" and body[:2] == b"\x13\x4d":
            require(len(body)>=7, "response truncated")
            candidate, code = struct.unpack_from("<hh",body,3)
            if candidate in by_id:
                require(len(body)==body[2]+3 and code==0 and body[7:]==b"\0\x04\x80\x02}.", "successful empty transfer extension")
                rid, kind = candidate, "success"
        if kind is None:
            continue
        sequence = frame["sequence"]
        require(integer(sequence,0,2**32-1), "reliable transfer sequence required")
        key = (direction,frame["session"],sequence)
        if key in seen:
            require(seen[key]==body, "conflicting retransmission")
            continue
        seen[key]=body
        found[rid][kind].append({"frame_order":order,**frame["proof"]})
    proofs=[]
    for op in operations:
        row=found[op["request_id"]]
        require(all(len(v)==1 for v in row.values()), "one command/update/success per transfer required")
        command, update, success=[row[k][0] for k in ("command","update","success")]
        require(command["session"]==update["session"]==success["session"]
                and command["frame_order"]<update["frame_order"]<success["frame_order"]
                and update["sequence"]<success["sequence"], "update-before-success ordering/session")
        if proofs:
            require(command["session"]==proofs[-1]["command"]["session"]
                    and command["frame_order"]>proofs[-1]["success"]["frame_order"], "native sequential transfer order")
        proofs.append({"request_id":op["request_id"],"layout":op["layout"],"native_cmd":op["native_cmd"],"command":command,"update":update,"success":success,
            "delta_bytes":len(op["update"]),"delta_sha256":digest(op["update"]),"update_before_success":True})
    return {"observed_methods":{"306":"0x8e VAR2 length20","105":"0x8e VAR2 length20","309":"0x90 VAR2 length24"},"dismissals":2,"hires":1,"transfers":3,"operations":proofs}


def expected_snapshot(durable, crew, selected=1):
    seats=crew_seats(crew,durable["account"])
    require(type(selected) is int and selected in (1,2),"selected native vehicle")
    return dict(database_id=durable["profile"]["native_database_id"],selected_inventory_id=selected,free_quota=crew["free_recruitment_left"],
        credits=durable["profile"]["resources"]["credits"],gold=durable["profile"]["resources"]["gold"],ms1_crew=seats[1],is7_crew=seats[2],
        tankmen=[dict(inventory_id=m["native_id"],vehicle_inventory_id=m["vehicle_native_id"],slot=m["seat"] if m["seat"] is not None else -1,
            sha256=digest(bytes.fromhex(m["descriptor_hex"])),nation_id=0,vehicle_type_id=decode_descriptor(bytes.fromhex(m["descriptor_hex"]))["vehicle_type_id"],
            role=m["role"],role_level=100 if m["native_id"]<=3 else 50,skills=decode_descriptor(bytes.fromhex(m["descriptor_hex"]))["skills"],last_skill_level=0,free_xp=0,dossier_bytes=6,dossier_sha256=digest(bytes.fromhex("420000000000"))) for m in crew["members"]])


def expected_efficiency(crew):
    result=[]
    for m in crew["members"]:
        desc=decode_descriptor(bytes.fromhex(m["descriptor_hex"]));level=desc["role_level"];vehicle=m["vehicle_native_id"]
        assigned_type={1:13,2:28}.get(vehicle)
        result.append(dict(inventory_id=m["native_id"],vehicle_inventory_id=vehicle,trained_vehicle_type_id=desc["vehicle_type_id"],
            base_role_level=level,efficiency_role_level=level if assigned_type in (None,desc["vehicle_type_id"]) else level//2))
    return result


def expected_readiness(durable,crew):
    return [dict(vehicle_inventory_id=v,is_crew_full=all(n is not None for n in seats),
        original_value=len(seats) if all(n is not None for n in seats) else False,battle_admission=False)
        for v,seats in crew_seats(crew,durable["account"]).items()]


DISPLAY_MULTINAMES = (('nationID',3800),('tankmanName',11051),('tankmanIcon',19359),
    ('roleIcon',9342),('roleLevel',6318),('skillsCount',19360),('lastSkill',19361),
    ('lastSkillLevel',13266),('preLastSkill',19362),('hasNewSkill',6325),
    ('newSkillsCount',15826),('lastNewSkillLevel',19363))


def verify_native_model_transformation(original,transformed):
    """Independent Application model-prefix oracle; original confirmation untouched.

    Native08/09/10 distinguished the shared-domain parent method from the
    registered child's duplicate. Those diagnostic return/marker bodies are
    never accepted here. Only this bounded native constructor is admissible.
    """
    require(type(original) is bytes and len(original)==1258376
        and digest(original)=='8c53f7cf510a3b328ee114307613c8f1416beb3360b587b6b158bb7d8ac02b62',
        'original Application movie pin')
    before=swf_body(original)
    require(type(transformed) is bytes and 8<len(transformed)<=4*1024*1024
        and transformed[:4]==original[:4],'bounded transformed CWS header')
    def u30(number):
        encoded=bytearray()
        while number>=128:encoded.append((number&127)|128);number>>=7
        encoded.append(number);return bytes(encoded)
    prefix=b'\x60'+u30(518)+b'\x42\x00'
    for _,index in DISPLAY_MULTINAMES:
        prefix+=b'\x2a\xd1\x66'+u30(index)+b'\x61'+u30(index)
    require(len(prefix)==111,'independent display initializer size')
    method_start=2631489;old_method=before[method_start:method_start+145]
    require(digest(old_method)=='9f35526bcb6052e7bdcbd7386051d9009e5eb46fcecb6a691a6dab99a6009fb5'
        and old_method[10:19]==bytes.fromhex('608604d146a2bd0101'),'original Application model parser prefix')
    replacement=old_method[:10]+prefix+old_method[19:]
    expected=bytearray(before[:method_start]+replacement+before[method_start+145:])
    require(len(replacement)==247 and len(expected)==len(before)+102,'bounded one-method growth')
    require(before[2631483:2631484]==b'\x03' and before[2631487:2631489]==u30(145)
        and int.from_bytes(before[45441:45445],'little')==3251140,'original ABC metadata pins')
    expected[2631483]=4;expected[2631487:2631489]=u30(247)
    expected[45441:45445]=(3251242).to_bytes(4,'little')
    require(int.from_bytes(transformed[4:8],'little')==len(expected)+8,'transformed SWF declared length')
    decoder=zlib.decompressobj();after=decoder.decompress(transformed[8:],len(expected)+1)
    require(decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail
        and len(after)==len(expected),'bounded complete transformed CWS stream')
    require(after==bytes(expected),'only native model constructor and exact metadata lengths may change')
    return dict(status='PASS_P04J_SAME_METHOD_NATIVE_CONSTRUCTION',classification='VERIFIED_STATIC',
        source_sha256=digest(original),transformed_sha256=digest(transformed),transformed_bytes=len(transformed),
        body_sha256=digest(after),method_sha256=digest(replacement),source_member=APPLICATION_RESOURCE,method_bytes=247,method_growth=102,
        maxstack=4,constructor_qname=518,display_fields=[dict(name=n,multiname=i) for n,i in DISPLAY_MULTINAMES],
        original_confirmation_layout_disposal_unchanged=True,original_branch_operands_unchanged=True,
        all_other_methods_tags_constant_pool_unchanged=True,no_tariff_rows_or_prices_introduced=True,
        native_model_construction='REQUIRES_ORIGINAL_RENDERED_WIDGET_EVIDENCE',physical_input='NOT_RUN')


def install_bindings(plans, trace_paths, original_dialog):
    require(len(plans)==len(trace_paths) and len(plans) in (1,2),"matching native install plans required")
    expected={Path(p).parent.resolve() for p in trace_paths}
    matched,proof=set(),[]
    for supplied in plans:
        path=owned(supplied);raw=read(path,1024*1024);plan=json_value(raw)
        settings=plan.get("settings",{});trace=owned(settings.get("trace_dir",""),True)
        require(trace in expected and trace not in matched and all(settings.get(flag) is True for flag in ("enable_crew_dismissal", "enable_crew_progression", "enable_roster_recruitment", "enable_cross_vehicle_crew", "enable_crew_transfer", "enable_crew_recruitment", "enable_p09d_ammo_service")),"install trace/feature binding")
        matched.add(trace)
        sources=plan.get("sources")
        require(type(sources) is list and len(sources)<=64 and all(type(item) is dict for item in sources),"install sources bound")
        files=plan.get("files")
        require(type(files) is list and 1<=len(files)<=128 and all(type(item) is dict for item in files)
                and all(type(item.get("path")) is str for item in files)
                and len({item["path"] for item in files})==len(files),"install files bound")
        ledger=json_value(read(owned(path.parent/"patch-ledger.json"),1024*1024))
        require(ledger.get("plan_sha256")==digest(raw) and same_literal(ledger.get("files"),files)
                and same_literal(ledger.get("sources"),sources) and same_literal(ledger.get("settings"),settings),
                "installed patch ledger plan binding")
        pins=[]
        names = [item.get("path") for item in sources]
        require(all(type(name) is str and re.fullmatch(r"client_patch/[a-z0-9_]+\.py", name) for name in names)
                and len(set(names)) == len(names) and REQUIRED_SOURCES <= set(names), "audited source set")
        for source_name in names:
            found=[s for s in sources if s.get("path")==source_name]
            require(len(found)==1,"installed source binding")
            item=found[0];current=read(ROOT/source_name)
            require(digest(current)==item.get("sha256"),"installed source differs from audited current source")
            compiled=owned(path.parent/item["compiled"]);metadata=owned(path.parent/item["metadata"])
            require(compiled.is_relative_to(path.parent) and metadata.is_relative_to(path.parent),"compiled provenance escaped plan")
            pyc=read(compiled);meta=json_value(read(metadata,65536))
            require(pyc[:4]==b"\x03\xf3\x0d\x0a" and meta.get("magic")=="03f30d0a"
                    and meta.get("source_sha256")==item["sha256"] and meta.get("pyc_sha256")==digest(pyc)
                    and meta.get("source_executed") is False and meta.get("compiler","").startswith("2.7.3 "),"actual Python2.7 compiled source provenance")
            target="res_mods/0.9.1/scripts/client/"+Path(source_name).stem+".pyc"
            installed_files=[entry for entry in files if entry.get("path")==target]
            require(len(installed_files)==1,"compiled target file binding")
            entry=installed_files[0]
            bundle=owned(path.parent/"bundle"/target)
            require(bundle.is_relative_to(path.parent/"bundle") and entry.get("installed_sha256")==digest(pyc)
                    and type(entry.get("bytes")) is int and entry["bytes"]==len(pyc)
                    and entry.get("runtime_mutable") is False and read(bundle)==pyc,"installed bundle differs from audited compiled source")
            pins.append({"source":source_name,"source_sha256":item["sha256"],"pyc_sha256":digest(pyc),"installed_path":target})
        installed=json_value(read(owned(path.parent/"install.json"),65536))
        require(installed.get("status")=="PASS" and installed.get("client_exe_modified") is False,"successful owned installation receipt")
        target='res_mods/0.9.1/'+APPLICATION_RESOURCE
        require(not any(entry['path']=='res_mods/0.9.1/'+REGISTERED_DIALOG for entry in files),
            'registered child must remain the pinned original resource')
        transformed=read(owned(path.parent/'bundle'/target),4*1024*1024)
        swf=verify_native_model_transformation(original_dialog,transformed)
        entries=[entry for entry in files if entry.get('path')==target]
        require(len(entries)==1 and entries[0].get('installed_sha256')==digest(transformed)
            and type(entries[0].get('bytes')) is int and entries[0]['bytes']==len(transformed)
            and entries[0].get('runtime_mutable') is False,'transformed Flash immutable bundle binding')
        resource=plan.get('resources',{}).get('crew_dismissal_flash',{})
        require(resource.get('source_sha256')==digest(original_dialog) and resource.get('installed_sha256')==digest(transformed)
            and resource.get('tool_sha256')==digest(read(ROOT/'tools/p04j_dismissal_flash.py')),'Flash transform source/tool plan binding')
        restored=json_value(read(owned(path.parent/'restore.json'),1024*1024))
        restored_files=restored.get('files')
        require(restored.get('status')=='PASS' and type(restored_files) is list and len(restored_files)==len(files)
            and all(type(entry) is dict and type(entry.get('path')) is str for entry in restored_files)
            and len({entry['path'] for entry in restored_files})==len(files),'complete owned installation restore receipt')
        original_files={entry['path']:entry for entry in files}
        client_root=owned(plan['research_root'],True)
        for restored_entry in restored_files:
            entry=original_files.get(restored_entry['path']);require(entry is not None,'restored unknown file')
            require(same_literal({k:v for k,v in restored_entry.items() if k!='postrun_sha256'},entry),'restore entry differs from plan')
            target_path=(client_root/entry['path']).resolve()
            require(target_path.is_relative_to(client_root),'restore target escaped owned client')
            current=digest(read(target_path)) if target_path.is_file() else None
            require(current==entry['before_sha256'],'owned client final rollback hash')
            if not entry['runtime_mutable']:
                require(restored_entry.get('postrun_sha256')==entry['installed_sha256'],'installed immutable file changed during runtime')
                require(digest(read(owned(path.parent/'postrun'/entry['path'])))==entry['installed_sha256'],'postrun preserved installed file binding')
            if entry['before_sha256'] is not None:
                require(digest(read(owned(path.parent/'backup'/entry['path'])))==entry['before_sha256'],'backup preinstallation hash binding')
        proof.append({"path":str(path),"sha256":digest(raw),"trace_directory":str(trace),"sources":pins,"flash":swf,"restore_sha256":digest(canonical(restored))})
    require(matched==expected,"all native traces bound to install plans")
    return proof


def readback(event, durable, crew, vehicle, ammo=None, details=False):
    require(same_literal(event.get('snapshot'), expected_snapshot(durable, crew, vehicle)), 'native sparse crew snapshot')
    require(event.get('native_descriptor_parse_repack') is True
        and type(event.get('native_descriptor_count')) is int and event['native_descriptor_count']==len(crew['members']),
        'original descriptor parse/repack observation')
    if ammo is not None:
        require(same_literal(event.get('ammunition'), ammo), 'native ammunition readback')
    if details:
        require(same_literal(event.get('efficiency'), expected_efficiency(crew))
            and same_literal(event.get('readiness'), expected_readiness(durable, crew)), 'native efficiency/readiness readback')



def preflight_databases(before,after,source_sha):
    require(before.get('terminal_triggers')==after.get('terminal_triggers')==TERMINAL_TRIGGERS,'preflight terminal trigger provenance')
    b,a=before['tables'],after['tables'];require(set(b)==set(a),'preflight schema unchanged')
    for table in b:
        if table!='game_limits':require(same_literal(b[table],a[table]),'preflight mutated durable table: '+table)
    snapshot=document(only(b,'game_snapshot'),'snapshot_json','snapshot_sha256')
    profile=document(only(b,'game_profiles'),'profile_json');account=profile['account_id'];crew=snapshot['crew_inventory']
    require(crew_seats(crew,account)==INITIAL_SEATS and len(crew['members'])==10 and not crew['retired_members']
        and crew['configuration_revision']==39 and crew['free_recruitment_left']==6 and crew['next_native_id']==11,'unchanged preflight roster')
    require(profile['profile_version']==11 and type(profile['snapshot_revision']) is int and profile['snapshot_revision']==49
        and type(snapshot['revision']) is int and snapshot['revision']==49 and snapshot['crew_schema']==SCHEMA
        and snapshot['crew_dismissal_source_audit_sha256']==source_sha,'preflight schema/revision/source')
    meta=only(b,'p04j_crew_meta');bundle=only(b,'p09d_import')['bundle_sha256']
    require(meta.get('source_audit_sha256')==source_sha and meta.get('source_bundle_sha256')==bundle
        and meta.get('account_id')==account and type(meta.get('base_revision')) is int and meta['base_revision']==48,'preflight migration binding')
    previous=deepcopy(profile);previous.update(profile_version=10,snapshot_revision=48)
    previous['crew_service'].update(schema=PREVIOUS_SCHEMA,policy_sha256=PREVIOUS_POLICY)
    base=deepcopy(crew);base.pop('retired_members');base['policy_sha256']=PREVIOUS_POLICY
    require(same_literal(document(meta,'base_profile_json','base_profile_sha256'),previous)
        and same_literal(document(meta,'base_crew_json','base_crew_sha256'),base),'preflight migration predecessor')
    for prefix,(key,pin) in RETAINED_AUDITS.items():
        row=only(b,prefix+'_crew_meta')
        require(row.get('source_audit_sha256')==pin and row.get('source_bundle_sha256')==bundle
            and row.get('account_id')==account and snapshot.get(key)==pin,'preflight retained source chain')
    require(not any(row['command_type'].startswith('p04j.') for row in b['game_command_ledger']),'preflight has no J commands')
    require(not b['p04j_retired_member'],'preflight has no retired members')
    require(same_literal(sorted(b['p04d_crew_member'],key=lambda m:m['native_id']),[dict(account_id=account,**m) for m in crew['members']]),'preflight member table')
    return dict(account=account,profile=profile,initial=crew,final=crew,operations=[],database_proof=dict(
        before={k:v for k,v in before.items() if k!='tables'},after={k:v for k,v in after.items() if k!='tables'},
        unchanged_tables=[name for name in b if name!='game_limits'],revision=49,configuration_revision=39,quota=6))


def runtime_trace_header(path,records):
    process=re.fullmatch(r'native-([1-9][0-9]*)-([0-9]+)\.jsonl',Path(path).name)
    require(process is not None,'native process trace filename')
    init=[r for r in records if r.get('event')=='init']
    require(len(init)==1 and init[0].get('sys_version','').startswith('2.7.3 ')
        and type(init[0].get('pointer_bytes')) is int and init[0]['pointer_bytes']==4,'native #717 runtime')
    require(not any(r.get('phase') in ('exception','error') or r.get('event') in
        ('exception','python_exception','observation_error','observation_limit','p09d_trace_truncated',
         'p04j_dismissal_trace_truncated','p04j_dismissal_error','p04j_dismissal_exception',
         'p04j_transfer_denied','p04j_personal_denied') for r in records),
        'native failure/truncated trace')
    return int(process[1])


DISPLAY_NAMES = {3:'Алексей Петров',5:'Аркадий Егоров'}


def expected_display(identity):
    require(type(identity) is int and identity in (3,5),'fixed native preflight identity')
    learned=identity==3;icon=2 if learned else 5;prefix='../maps/icons/tankmen/'
    return dict(nationID=0,tankmanName=DISPLAY_NAMES[identity],tankmanIcon=prefix+'icons/big/ussr-'+str(icon)+'.png',
        roleIcon=prefix+'roles/small/driver.png',roleLevel=100 if learned else 50,skillsCount=int(learned),
        lastSkill=prefix+'skills/small/repair.png' if learned else None,lastSkillLevel=0,preLastSkill=None,
        hasNewSkill=False,newSkillsCount=0,lastNewSkillLevel=0)


def display_source_audit(original_root):
    """Independent bounded catalogs/localization; no trace supplies expected labels."""
    from packed_xml import decode,walk
    from p04j_crew_source_audit import pinned_read,static
    root=Path(original_root)
    pins={
        'res/scripts/item_defs/tankmen/ussr.xml':(45148,'7277417f9ffac7f742cd6b1bfce02cc7a182558fbdf7db137604323403552cee'),
        'res/scripts/item_defs/tankmen/tankmen.xml':(5456,'a8604e50bf829072d083535ea3339302a1584582d42e62814a3a871e310ea73b'),
        'res/text/lc_messages/ussr_tankmen.mo':(58546,'26b86cc11077e36688d0c7e97fadfec3e257b55254b61383ca8b82e378c0e7fe'),
        'res/scripts/client/gui/shared/gui_items/tankman.pyc':(15745,'07645906b7cac95bc482c0e9548b37c598d3ec440752f7f19058688f981fa364'),
        'res/scripts/client/gui/shared/gui_items/serializers.pyc':(5658,'749777fb24499f4df6c75f4ed89408c0594f5ed90f1b7892cc2a8be0816517cc'),
        'res/scripts/client/helpers/i18n.pyc':(3358,'7181c2b690cae5ca78ca2ebae3b6b232815c27ee253120716fb7d6a5ab3e4c4b'),
        'res/scripts/common/nations.pyc':(565,'34392915b0d2a70a3df0b8151e0fdbb9cb58aad6a708ffc85843c45c596a4562'),
        'res/scripts/client/gui/scaleform/managers/utilsmanager.pyc':(2639,'86fdf191959d3e0297c38c3b55868c07cfe053e20a5fadc16f6097b72603a98a')}
    raw={name:pinned_read(static.no_links(root/name),pin) for name,pin in pins.items()}
    catalog=dict(walk(decode(raw['res/scripts/item_defs/tankmen/ussr.xml'],max_bytes=65536,max_nodes=12000,max_depth=12)))
    skills=dict(walk(decode(raw['res/scripts/item_defs/tankmen/tankmen.xml'],max_bytes=65536,max_nodes=12000,max_depth=12)))
    mo=raw['res/text/lc_messages/ussr_tankmen.mo']
    magic,version,count,keys,values,_,_=struct.unpack_from('<7I',mo)
    require(magic==0x950412de and version==0 and 0<count<=2000 and keys+8*count<=len(mo)
        and values+8*count<=len(mo),'bounded original localization table')
    messages={}
    for index in range(count):
        pair=[]
        for table in (keys,values):
            size,offset=struct.unpack_from('<2I',mo,table+index*8)
            require(size<=65536 and offset+size<len(mo) and mo[offset+size]==0,'bounded localization entry')
            pair.append(mo[offset:offset+size].decode('utf8'))
        require(pair[0] not in messages,'unique localization key');messages[pair[0]]=pair[1]
    require(skills['/roles[1]/driver[1]/icon[1]']=='driver.png'
        and skills['/skills[1]/repair[1]/icon[1]']=='repair.png','original role and skill asset names')
    # The complete pinned GUI source supplies these class constants; inspect it as data.
    table={100:'LOAD_CONST',90:'STORE_NAME'};records=static.inspect(raw['res/scripts/client/gui/shared/gui_items/tankman.pyc'],table)
    for owner,field,wanted in (('Tankman','PORTRAIT_ICON_PATH_BIG','../maps/icons/tankmen/icons/big'),
            ('Tankman','ROLE_ICON_PATH_SMALL','../maps/icons/tankmen/roles/small'),
            ('TankmanSkill','ICON_PATH_SMALL','../maps/icons/tankmen/skills/small')):
        record=next(r for r in records if r['qualified_name']=='<module>.'+owner)
        hits=[i for i,r in enumerate(record['instructions']) if r['opname']=='STORE_NAME' and r.get('value')==field]
        require(len(hits)==1 and hits[0]>0 and record['instructions'][hits[0]-1].get('value')==wanted,'original icon prefix')
    for identity,number in ((3,2),(5,5)):
        base='/normalGroups[1]/men1[1]/';names=[]
        for field in ('firstNames','lastNames'):
            value=catalog[base+field+'[1]/_'+str(number)+'[1]']
            require(value.startswith('#ussr_tankmen:'),'original name localization domain')
            names.append(messages[value.split(':',1)[1]])
        require(' '.join(names)==DISPLAY_NAMES[identity] and catalog[base+'icons[1]/_'+str(number)+'[1]']=='ussr-'+str(number)+'.png',
            'original passport-derived name and portrait')
    return dict(status='PASS_STATIC_PASSPORT_DISPLAY_ORACLE',sources=[dict(path=n,bytes=p[0],sha256=p[1]) for n,p in pins.items()],
        expected=[dict(inventory_id=n,display_fields=expected_display(n)) for n in (3,5)],runtime_trace_used_as_oracle=False)


def rendered_observation(event,display,identity):
    require(event.get('source_bound_native_rendering') is True
        and type(event.get('actual_model_readback')) is bool,'original widget evidence required')
    expected_status='AVAILABLE_VERIFIED' if event['actual_model_readback'] else 'UNAVAILABLE_OBSERVED'
    require(event.get('typed_model_readback')==expected_status,'typed model observation must be reported honestly')
    learned=identity==3
    wanted=dict(tankman_name=display['tankmanName'],portrait=display['tankmanIcon'],role_icon=display['roleIcon'],
        role_level_text=str(display['roleLevel'])+'%',role_level_bar=display['roleLevel'],nation='ussr',
        skills=dict(main=learned,additional=False,free1=False,free2=False),
        main_skill=dict(icon=display['lastSkill'],type='current_skill',level=0,count=0) if learned else None)
    require(same_literal(event.get('rendered_fields'),wanted),'exact original rendered identity qualification and skills')
    return dict(typed_model_readback=expected_status,source_bound_native_rendering=True)


def confirmation_observation(value,identity,stage):
    fields={'inventory_id','protected','display_fields','input_visible','submit_id','input_text',
        'original_control','raw_boolean_observations','boolean_readback','source_bound_validation','actual_model_readback','typed_model_readback',
        'source_bound_native_rendering','rendered_fields','supplied_tariff_rows','python_formatted_control',
        'formatted_control_text','checker_owner_id','input_focus','native_validation_semantics'}
    require(type(value) is dict and set(value)==fields and type(value['inventory_id']) is int and value['inventory_id']==identity,
        'exact original confirmation readback fields')
    require(value['supplied_tariff_rows'] is False and value['submit_id']=='submit',
        'original confirmation identity without fabricated tariff data')
    for name in ('protected','input_visible'):
        require(type(value[name]) is bool,'native confirmation Boolean field')
    raw=value['raw_boolean_observations']
    require(type(raw) is dict and set(raw)=={'submit_enabled','native_control_match','native_validation_accepted'}
        and all(type(v) is bool for v in raw.values()) and value['boolean_readback']=='UNAVAILABLE_OBSERVED',
        'unreliable reflected Booleans retained without effective-state claim')
    require(integer(value['checker_owner_id'],1,2**64-1) and integer(value['input_focus'],0,2**31-1)
        and value['native_validation_semantics']=='control_value_match','native input owner focus and semantics')
    for name in ('input_text','original_control','python_formatted_control','formatted_control_text'):
        require(type(value[name]) is str and len(value[name])<=64,'bounded native input strings')
    display=value['display_fields'];require(type(display) is dict and set(display)=={'nationID','tankmanName','tankmanIcon','roleIcon','roleLevel','skillsCount','lastSkill','lastSkillLevel','preLastSkill','hasNewSkill','newSkillsCount','lastNewSkillLevel'},'typed display property set')
    require(type(display['nationID']) is int and display['nationID']==0 and type(display['roleLevel']) is int
        and display['roleLevel']==(100 if identity==3 else 50) and type(display['skillsCount']) is int
        and display['skillsCount']==int(identity==3) and display['hasNewSkill'] is False
        and type(display['lastSkillLevel']) is int and display['lastSkillLevel']==0
        and type(display['newSkillsCount']) is int and display['newSkillsCount']==0
        and type(display['lastNewSkillLevel']) is int and display['lastNewSkillLevel']==0,'actual dismissal qualification/skill data')
    require(display['preLastSkill'] is None,'one or zero learned skills')
    for field in ('tankmanName','tankmanIcon','roleIcon'):
        require(type(display[field]) is str and 1<=len(display[field])<=2048,'bounded actual native display field')
    require((type(display['lastSkill']) is str and 1<=len(display['lastSkill'])<=2048) if identity==3 else display['lastSkill'] is None,'actual last skill display')
    require(same_literal(display,expected_display(identity)),'source-derived passport name portrait role and skill')
    rendered_observation(value,display,identity)
    if identity==3:
        require(value['protected'] is True and value['input_visible'] is True and value['original_control']=='0'
            and value['python_formatted_control']==value['formatted_control_text']=='0','learned zero skill protected input and initialized control')
        expected_text={'wrong':'100','correct':'0'}.get(stage,'')
        require(value['input_text']==expected_text,'native original input text')
        if stage in ('wrong','correct'):
            require(same_literal(value['source_bound_validation'],dict(text=expected_text,
                native_callback_valid=stage=='correct',original_meta_value=stage=='correct',
                checker_owner_id=value['checker_owner_id'],original_callback_returned=True,original_meta_returned=True)),
                'original callback and Meta completion required for control-number validation')
        else:
            require(value['source_bound_validation'] is None,'initial input has no invented native callback')
    else:
        require(identity==5 and not value['protected'] and not value['input_visible']
            and value['source_bound_validation'] is None,'ordinary50 original confirmation without fabricated validation')
    return dict(inventory_id=identity,stage=stage,protected=value['protected'],
        raw_boolean_observations=raw,boolean_readback=value['boolean_readback'],input_text=value['input_text'],
        source_bound_validation=value['source_bound_validation'])


def preflight_trace(path,records,sha,durable):
    pid=runtime_trace_header(path,records);indexed=list(enumerate(records,1))
    def events(name):return [(i,r) for i,r in indexed if r.get('event')==name]
    require(not events('p04j_native_dismissal_request') and not any(r.get('native_cmd') in (105,151,306,309)
        and 'request' in str(r.get('event')) for r in records),'preflight contains no native crew request')
    before=events('p04j_preflight_before');final=events('p04j_dismissal_preflight')
    require(len(before)==len(final)==1 and before[0][0]<final[0][0],'preflight initial/final observation')
    ammo=before[0][1].get('ammunition');validate_ammunition(ammo)
    readback(before[0][1],durable,durable['initial'],1,ammo)
    readback(final[0][1],durable,durable['initial'],1,ammo)
    result=final[0][1]
    require(same_literal(result.get('cancelled'),[3,5]) and type(result.get('native_mutations')) is int and result['native_mutations']==0
        and result.get('submit_called') is False and result.get('physical_pointer_input') is False
        and result.get('action')=='original_confirmation_cancel_only','original cancel-only completion')
    observed=events('p04j_confirmation_observed');expected=((3,'initial'),(3,'protected'),(3,'wrong'),(3,'correct'),(5,'initial'),(5,'simple'))
    require(len(observed)==len(expected),'exact protected/wrong/correct/simple observation sequence')
    sent,models=events('p04j_dismissal_model_sent'),events('p04j_dismissal_model')
    require(len(sent)==len(models)==2,'two bounded original native model constructions')
    for index,identity in enumerate((3,5)):
        send_line,send=sent[index];model_line,model=models[index]
        initial_line,initial_event=observed[0 if index==0 else 4]
        member=next(m for m in durable['initial']['members'] if m['native_id']==identity)
        require(before[0][0]<send_line<model_line<initial_line and send.get('inventory_id')==identity
            and model.get('inventory_id')==identity and type(send.get('inventory_id')) is int
            and type(model.get('inventory_id')) is int,'native model/input observation order')
        for event in (send,model):
            require(event.get('native_class')=='net.wg.gui.lobby.tankman.SkillDropModel'
                and event.get('native_constructor_in_flash') is True and event.get('supplied_tariff_rows') is False
                and same_literal(event.get('display_fields'),initial_event.get('observation',{}).get('display_fields')),
                'actual native constructor/display fields without tariff data')
        require(send.get('original_meta_called') is True and send.get('daapi_inited_before') is True
            and send.get('source_argument')=='actual_primitive_display_fields' and send.get('typed_object_bridge') is False
            and send.get('descriptor_sha256')==digest(bytes.fromhex(member['descriptor_hex'])),
            'original setter bound to actual member descriptor')
        rendered_observation(model,initial_event['observation']['display_fields'],identity)
        require(model.get('original_confirmation_preserved') is True
            and type(model.get('pending_observations')) is int and 0<=model['pending_observations']<=2,
            'original renderer must be observed after bounded construction')
    proof=[]
    for (line,event),(identity,stage) in zip(observed,expected):
        require(before[0][0]<line<final[0][0] and event.get('stage')==stage and event.get('policy')==UI_POLICY,'confirmation stage ordering/policy')
        readback(event,durable,durable['initial'],1)
        proof.append(dict(line=line,**confirmation_observation(event.get('observation'),identity,stage)))
    cancelled=events('p04j_confirmation_cancel');require(len(cancelled)==2,'two original cancellations')
    for index,((line,event),identity) in enumerate(zip(cancelled,(3,5))):
        require(type(event.get('inventory_id')) is int and event['inventory_id']==identity and event.get('submit_called') is False
            and event.get('original_callback')=='SimpleDialog.onWindowClose' and event.get('policy')==UI_POLICY,'original cancellation callback')
        require(observed[3 if index==0 else 5][0]<line<(observed[4][0] if index==0 else final[0][0]),'cancellation observation order')
    checker=observed[0][1]['observation']['checker_owner_id']
    require(all(r['observation']['checker_owner_id']==checker for _,r in observed[:4]),'one original protected checker')
    input_proof=protected_input_pipeline(indexed,checker,observed[1][0],observed[2][0],observed[3][0])
    return dict(trace=str(path),trace_sha256=sha,process_id=pid,confirmation=proof,cancelled=[3,5],native_mutations=0,
        physical_input='NOT_RUN',positive_button_event='NOT_RUN',input_validation=input_proof,unchanged_ammunition_sha256=digest(canonical(ammo)))



def protected_input_pipeline(indexed,checker,start_line,wrong_line,correct_line,allow_extra=False):
    def events(name):return [(i,r) for i,r in indexed if r.get('event')==name]
    inputs=events('p04j_confirmation_input');require(len(inputs)==2,'two protected text entries')
    callbacks=events('p04j_confirmation_input_callback')
    require(len(callbacks)==2,'two source-observed native input completions')
    apis=events('p04j_native_input_api');require(len(apis)==2,'native input API observed for each text entry')
    key_events=events('p04j_validation_key_input')
    require(len(key_events)==8,'exact bounded validation key sequence')
    initialization=events('p04j_native_input_initialization')
    for method,source_line in (('as_setFormattedControlNumberS',50),('as_setOriginalControlNumberS',59)):
        owned_initialization=[(i,r) for i,r in initialization if r.get('method')==method and r.get('checker_owner_id')==checker]
        require(all(r.get('value') in ('None','0') for _,r in owned_initialization),'bounded original pre-model control initialization')
        pair=[(i,r) for i,r in owned_initialization if r.get('value')=='0']
        require(all(i<pair[0][0] for i,r in owned_initialization if r.get('value')=='None') if pair else False,
            'original pre-model initialization precedes real control')
        require(len(pair)==2 and pair[0][0]<pair[1][0]<inputs[0][0]
            and [r.get('phase') for _,r in pair]==['call','return'],'original input initialization call/return pair')
        for _,event in pair:
            require(event.get('source')=='scripts/client/gui/Scaleform/daapi/view/meta/InputCheckerMeta.py'
                and type(event.get('source_line')) is int and event['source_line']==source_line
                and event.get('value')=='0' and event.get('value_type') in ('str','unicode')
                and event.get('original_called') is True and event.get('passive') is True
                and event.get('daapi_inited') is True,'original ready input setter received actual string control')
        require(pair[1][1].get('formatted_control_text') in ('','0'),'bounded immediate formatted-control observation')
        # Native13 observed the original setter return before this public getter
        # reflected its value. Later observation/input gates require actual '0'.
    focus_events=events('p04j_confirmation_focus')
    require(4<=len(focus_events)<=302,'bounded public focus request/readback evidence')
    require(sum(r.get('phase')=='request' for _,r in focus_events)==2,'one focus request per protected text entry')
    passive=events('p04j_native_input_callback')
    require(len(passive)==4 if not allow_extra else 4<=len(passive)<=16,'bounded original validation callback pairs')
    dialog_owner=None;key_number=None;return_number=None
    for n,((line,event),text,lo,hi) in enumerate(zip(inputs,('100','0'),(start_line,wrong_line),(wrong_line,correct_line))):
        valid=text=='0';done_line,done=callbacks[n]
        require(lo<line<done_line<hi and event.get('inventory_id')==3 and type(event.get('inventory_id')) is int and event.get('text')==text
            and event.get('original_flash_callback')=='InputChecker.userInputHandler -> InputCheckerMeta.sendUserInputS'
            and type(event.get('native_syntax_valid')) is bool and event.get('syntax_source')=='InputChecker.isValidControlInput'
            and event.get('validation_semantics')=='control_value_match' and event.get('formatted_control_text')=='0'
            and event.get('checker_owner_id')==checker and integer(event.get('input_focus'),1,2**31-1)
            and event.get('callback_boolean_supplied') is False and event.get('physical_keyboard_input') is False,
            'native focused input dispatch without Python supplied validation')
        focus=[(i,r) for i,r in focus_events if lo<i<line]
        require(len(focus)>=2 and focus[0][1].get('phase')=='request'
            and all(r.get('phase')=='readback' for _,r in focus[1:]),'focus request and later native readback before input')
        requested=focus[0][1]
        require(requested.get('inventory_id')==3 and type(requested.get('inventory_id')) is int
            and requested.get('checker_owner_id')==checker and integer(requested.get('previous_focus'),0,2**31-1)
            and type(requested.get('requested_focus')) is int and requested['requested_focus']==1
            and requested.get('source')=='UIComponent.focused public setter620'
            and requested.get('control_numbers_changed') is False and requested.get('submit_enabled_changed') is False,
            'public focus setter only changes input focus')
        for _,focus_read in focus[1:]:
            require(focus_read.get('inventory_id')==3 and type(focus_read.get('inventory_id')) is int
                and focus_read.get('checker_owner_id')==checker and integer(focus_read.get('input_focus'),0,2**31-1)
                and focus_read.get('source')=='UIComponent.focused public getter'
                and focus_read.get('later_native_tick') is True,'later native public focus readback')
        require(focus[-1][1]['input_focus']>0 and all(r['input_focus']==0 for _,r in focus[1:-1]),
            'native key waits for actual positive input focus')
        keys=key_events[n*4:n*4+4]
        api_line,api=apis[n]
        require(line<api_line<keys[0][0] and api.get('left_name')=='KEY_LEFTARROW' and api.get('return_name')=='KEY_RETURN'
            and integer(api.get('left_key'),1,65535) and integer(api.get('return_key'),1,65535)
            and api['left_key']!=api['return_key'] and api.get('key_constructor_callable') is True
            and api.get('dispatcher_callable') is True and api.get('symbol_source')=='scripts/client/gui/shared/utils/key_mapping.py'
            and api.get('symbol_source_sha256')=='940d65e05aef49045491f5bd2e8ae81d750853f259a05c99e9645b4f87034d4e'
            and all(type(api.get(k)) is str and 1<=len(api[k])<=64 for k in ('key_constructor_type','dispatcher_type')),
            'source-bound native key symbols and callable dispatcher')
        if return_number is None:return_number=api['return_key']
        require(api['return_key']==return_number,'one native Return key code across protected input')
        require([r.get('phase') for _,r in keys]==['dispatch','return','dispatch','return']
            and [r.get('key_down') for _,r in keys]==[True,True,False,False]
            and all(line<i<done_line for i,_ in keys),'native validation key down/up order')
        for key_line,key in keys:
            require(type(key.get('key_down')) is bool and key.get('inventory_id')==3 and type(key.get('inventory_id')) is int
                and key.get('text')==text and key.get('key_name')=='KEY_LEFTARROW' and integer(key.get('key'),1,65535)
                and key.get('physical_input') is False,'bounded engine validation key')
            if key_number is None:key_number=key['key']
            require(key['key']==key_number==api['left_key'],'one original key code')
            if key['phase']=='dispatch':
                require(key.get('checker_owner_id')==checker and integer(key.get('dialog_owner_id'),1,2**64-1)
                    and key.get('source')=='BigWorld.KeyEvent -> GUI.handleKeyEvent','original engine dispatch target')
                if dialog_owner is None:dialog_owner=key['dialog_owner_id']
                require(key['dialog_owner_id']==dialog_owner,'one protected dialog owner')
        pair=[(i,r) for i,r in passive if line<i<done_line]
        require(len(pair)==2,'one original callback pair for this validation key')
        require(keys[2][0]<pair[0][0]<pair[1][0]<done_line
            and [r.get('phase') for _,r in pair]==['call','return'],'native KEY_UP precedes original validation callback')
        for _,callback in pair:
            require(callback.get('source')=='scripts/client/gui/Scaleform/daapi/view/lobby/inputChecker/InputChecker.py'
                and type(callback.get('source_line')) is int and callback['source_line']==42 and callback.get('method')=='sendUserInput'
                and callback.get('checker_owner_id')==checker and callback.get('dialog_owner_id')==dialog_owner
                and callback.get('inventory_id')==3 and type(callback.get('inventory_id')) is int
                and callback.get('value')==text and callback.get('value_type') in ('str','unicode')
                and callback.get('native_callback_valid') is valid and callback.get('daapi_inited') is True
                and callback.get('original_called') is True and callback.get('passive') is True,'source-pinned native validation callback')
        response=[(i,r) for i,r in events('p04j_native_input_validation_setter') if pair[0][0]<i<pair[1][0]]
        require(len(response)==2 and [r.get('phase') for _,r in response]==['call','return'],
            'original Python validation response call/return inside callback')
        for _,setter in response:
            require(setter.get('source')=='scripts/client/gui/Scaleform/daapi/view/meta/InputCheckerMeta.py'
                and type(setter.get('source_line')) is int and setter['source_line']==68 and setter.get('method')=='as_invalidUserTextS'
                and setter.get('checker_owner_id')==checker and setter.get('dialog_owner_id')==dialog_owner
                and setter.get('inventory_id')==3 and type(setter.get('inventory_id')) is int
                and setter.get('value') is valid and setter.get('value_type')=='bool'
                and setter.get('daapi_inited') is True and setter.get('passive') is True and setter.get('original_called') is True
                and type(setter.get('native_validation_accepted')) is bool,'source-pinned native validation result setter')
        # Immediate reflected properties can be stale (actual15). Only the
        # original callback/result pair closes validation. Real Enter behavior is
        # checked separately in the full mode; reflected Booleans stay raw.
        require(done.get('inventory_id')==3 and type(done.get('inventory_id')) is int and done.get('text')==text
            and done.get('checker_owner_id')==checker and done.get('native_callback_valid') is valid
            and done.get('passive') is True and done.get('callback_boolean_supplied') is False,'passive input completion agrees with original callback')
    return dict(checker_owner_id=checker,dialog_owner_id=dialog_owner,key_number=key_number,return_key=return_number,
        native_callback_values=[False,True],raw_boolean_readback='UNAVAILABLE_OBSERVED')

def native_flash_binding(records,installed):
    observations=[(i,r) for i,r in enumerate(records,1) if r.get('event')=='p04j_native_flash_resource']
    require(len(observations)==1,'one native engine Flash resource resolution')
    line,event=observations[0];flash=installed['flash']
    require(event.get('resource')==APPLICATION_RESOURCE and event.get('read_only') is True
        and event.get('matches_transformed') is True and type(event.get('bytes')) is int
        and event['bytes']==flash['transformed_bytes'] and event.get('sha256')==flash['transformed_sha256']
        and event.get('expected_sha256')==flash['transformed_sha256'],'native resolved Flash differs from verified installed bundle')
    dependencies=[(i,r) for i,r in enumerate(records,1) if r.get('event')=='p04j_native_flash_dependency']
    require(len(dependencies)==1,'one original child dependency observation')
    child_line,child=dependencies[0]
    require(child_line>line and child.get('resource')==REGISTERED_DIALOG and child.get('read_only') is True
        and child.get('unchanged_original') is True and type(child.get('bytes')) is int and child['bytes']==132797
        and child.get('sha256')==child.get('expected_sha256')==REGISTERED_DIALOG_SHA,'native registered child must remain original')
    model_lines=[i for i,r in enumerate(records,1) if r.get('event')=='p04j_dismissal_model']
    require(model_lines and all(i>child_line for i in model_lines),'native resource read precedes original model observations')
    return dict(line=line,bytes=event['bytes'],sha256=event['sha256'],engine_resource=event['resource'],read_only=True,
        original_child=dict(line=child_line,bytes=child['bytes'],sha256=child['sha256'],resource=child['resource']))


def native_command_receipt(indexed,request,callback,operation):
    request_line,req=request;callback_line,cb=callback
    rid,command,layout=operation['request_id'],operation['native_cmd'],operation['layout']
    require(request_line<callback_line and integer(req.get('request_id'),1,32767) and req['request_id']==rid
        and type(req.get('native_cmd')) is int and req['native_cmd']==command and same_literal(req.get('layout'),layout)
        and req.get('source')=='scripts/client/Account.py' and req.get('method')=='__doCmd'
        and type(req.get('source_line')) is int and req['source_line']==1523 and req.get('phase')=='return'
        and integer(req.get('owner_id'),1,2**64-1),'original Account request source/identity')
    owner=req['owner_id'];wire=operation['response']['wire_revision']
    updates=[(i,r) for i,r in indexed if request_line<i<callback_line and r.get('event')=='p09d_native_ammo_call'
        and r.get('method')=='_update' and r.get('phase')=='return' and r.get('revision')==wire]
    successes=[(i,r) for i,r in indexed if request_line<i<callback_line and r.get('event')=='p09d_native_ammo_call'
        and r.get('method')=='onCmdResponseExt' and r.get('phase')=='return' and r.get('requestID')==rid]
    require(len(updates)==len(successes)==1 and updates[0][0]<successes[0][0],'native delta before correlated success')
    update,success=updates[0][1],successes[0][1]
    require(type(update.get('owner_id')) is int and type(success.get('owner_id')) is int
        and update['owner_id']==success['owner_id']==owner
        and update.get('source')==success.get('source')=='scripts/client/Account.py'
        and type(update.get('revision')) is int and type(update.get('previous_revision')) is int
        and update['previous_revision']==wire-1 and update.get('has_inventory') is True
        and type(success.get('requestID')) is int and type(success.get('resultID')) is int
        and success['resultID']==0,'native update/result account owner and revision')
    require(type(cb.get('request_id')) is int and cb['request_id']==rid and type(cb.get('native_cmd')) is int
        and cb['native_cmd']==command and same_literal(cb.get('layout'),layout)
        and type(cb.get('result')) is int and cb['result']==0 and cb.get('update_before_success') is True
        and type(cb.get('revision')) is int and cb['revision']==wire and type(cb.get('previous_revision')) is int
        and cb['previous_revision']==wire-1,'scenario callback agrees with native receipt')
    return dict(owner_id=owner,request_id=rid,request_line=request_line,update_line=updates[0][0],
        success_line=successes[0][0],callback_line=callback_line)



BUTTON_SOURCE = 'scripts/client/gui/Scaleform/daapi/view/dialogs/SimpleDialog.py'
BUTTON_SHA = '696f4e2b6d374d6380ef1a45b02b859fd6c4e2c6726c689db7832e0779a74d74'


def retired_readback(event, crew):
    require(same_literal(event.get('retired_absent'),
        sorted(m['native_id'] for m in crew['retired_members'])), 'actual native retired item absence')


def original_engine_pair(indexed, stage, identity, owner, lo, hi, positive,return_key,checker=None):
    values = [(i, r) for i, r in indexed if lo < i < hi
        and r.get('event') == 'p04j_engine_key_input' and r.get('stage') == stage]
    require(len(values) == 4, 'exact original engine key down/up dispatch and return')
    key = values[0][1].get('key')
    require(integer(key, 1, 65535) and key==return_key, 'Enter uses the actual source-bound native Return key')
    for (_, event), (phase, down) in zip(values,
            (('dispatch', True), ('return', True), ('dispatch', False), ('return', False))):
        require(event.get('phase') == phase and event.get('key_down') is down
            and event.get('physical_input') is False and event.get('key_name') == 'KEY_RETURN'
            and type(event.get('key')) is int and event['key'] == key
            and type(event.get('inventory_id')) is int and event['inventory_id'] == identity
            and type(event.get('dialog_owner_id')) is int and event['dialog_owner_id'] == owner,
            'original engine input identity and phase')
        if phase == 'dispatch':
            require(event.get('source') == 'BigWorld.KeyEvent -> GUI.handleKeyEvent'
                and type(event.get('cached_submit_enabled')) is bool
                and event.get('boolean_readback')=='UNAVAILABLE_OBSERVED'
                and integer(event.get('submit_focus_observed'), 0, 2**32-1), 'raw original submit observations')
            validation=event.get('source_bound_validation')
            if identity==3:
                require(type(validation) is dict and integer(checker,1,2**64-1)
                    and validation.get('checker_owner_id')==checker
                    and same_literal(validation,dict(text='0' if positive else '100',native_callback_valid=positive,
                        original_meta_value=positive,checker_owner_id=validation['checker_owner_id'],
                        original_callback_returned=True,original_meta_returned=True)), 'engine input follows original validation')
            else:
                require(validation is None,'simple input has no invented validation')
        else:
            require(event.get('result_type') in ('NoneType', 'bool', 'int')
                and (event.get('handled') is None if event['result_type'] == 'NoneType' else
                     type(event.get('handled')) is (bool if event['result_type'] == 'bool' else int)),
                'native GUI dispatch result type')
    return dict(key=key, down_dispatch=values[0][0], down_return=values[1][0],
        up_dispatch=values[2][0], up_return=values[3][0])


def elapsed_between(indexed,first,last,lower,upper):
    records=dict(indexed);a,b=(records[i].get('elapsed_seconds') for i in (first,last))
    require(all(type(t) in (int,float) and math.isfinite(t) and t>=0 for t in (a,b))
        and lower<=b-a<=upper,'bounded native asynchronous interval')
    return b-a


def positive_confirmation(indexed, before, action, request, callback, operation, durable,return_key):
    lo, hi = before[0], callback[0]
    identity = operation['layout'][0]
    stage = 'correct' if identity == 3 else 'simple'
    act = action[1]
    owner = act.get('dialog_owner_id')
    require(integer(owner, 1, 2**64-1) and act.get('direct_python_submit') is False
        and type(act.get('inventory_id')) is int and act['inventory_id'] == identity,
        'positive dismissal uses actual original engine input')
    def selected(name):
        return [(i, r) for i, r in indexed if lo < i < hi and r.get('event') == name]
    opened = selected('p04j_dismissal_open')
    require(len(opened) == 1 and opened[0][0] < action[0]
        and opened[0][1].get('inventory_id') == identity
        and opened[0][1].get('original_callback') == 'PersonalCase.dismissTankman'
        and opened[0][1].get('original_called') is True, 'original dismissal processor entry')
    observations = selected('p04j_confirmation_observed')
    require(len(observations) == 1 and opened[0][0] < observations[0][0] < action[0]
        and observations[0][1].get('stage') == stage, 'actual original positive confirmation state')
    confirmation_observation(observations[0][1].get('observation'), identity, stage)
    readback(observations[0][1], durable, operation['before'], 1)
    checker=observations[0][1]['observation']['checker_owner_id']
    pair = original_engine_pair(indexed, stage, identity, owner, action[0], hi, True,return_key,checker)
    buttons = selected('p04j_native_confirmation_button')
    require(len(buttons) == 1, 'exactly one original enabled confirmation callback')
    line, button = buttons[0]
    require(pair['up_dispatch'] < line < request[0],
        'original key release invokes button before its correlated native command')
    elapsed_between(indexed,pair['up_dispatch'],request[0],0,5)
    focuses=selected('p04j_submit_focus_requested')
    require(len(focuses)==(2 if identity==3 else 1),'one original button focus request per Enter trial')
    for focus_line,focus in focuses:
        require(focus.get('dialog_owner_id')==owner and type(focus.get('dialog_owner_id')) is int
            and focus.get('inventory_id')==identity and type(focus.get('inventory_id')) is int
            and focus.get('button_id')=='submit' and focus.get('original_callback')=='SimpleDialogMeta.as_setButtonFocusS'
            and focus.get('enabled_changed') is False,'original focus API does not change enabled state')
    require(focuses[-1][0]<pair['down_dispatch'],'original submit focus before positive engine input')
    require(button.get('source') == BUTTON_SOURCE and button.get('source_code_sha256') == BUTTON_SHA
        and type(button.get('source_line')) is int and button['source_line'] == 56
        and button.get('method') == 'onButtonClick' and button.get('phase') == 'call'
        and type(button.get('owner_id')) is int and button['owner_id'] == owner
        and type(button.get('dialog_owner_id')) is int and button['dialog_owner_id'] == owner
        and type(button.get('inventory_id')) is int and button['inventory_id'] == identity
        and button.get('button_id') == 'submit', 'source-pinned passive native button observation')
    if identity == 3:
        blocked = selected('p04j_confirmation_wrong_blocked')
        require(len(blocked) == 1 and opened[0][0] < blocked[0][0] < observations[0][0],
            'wrong input is observed blocked before correct input')
        wrong = original_engine_pair(indexed, 'wrong', 3, owner, opened[0][0], blocked[0][0], False,return_key,checker)
        event = blocked[0][1]
        require(type(event.get('button_events')) is int and event['button_events'] == 0
            and type(event.get('native_requests')) is int and event['native_requests'] == 0
            and event.get('inventory_id') == 3 and event.get('dialog_owner_id') == owner,
            'wrong input must not trigger original button or native request')
        confirmation_observation(event.get('observation'), 3, 'wrong')
        readback(event, durable, operation['before'], 1)
        require(not any(wrong['down_dispatch'] < i < blocked[0][0] and r.get('event') in
            ('p04j_native_confirmation_button', 'p04j_native_dismissal_request') for i, r in indexed),
            'wrong engine input has no native side effect')
        require(wrong['key'] == pair['key'], 'same native key symbol for negative and positive input')
        require(focuses[0][0]<wrong['down_dispatch']<blocked[0][0]<focuses[1][0], 'wrong/correct focus request order')
        elapsed_between(indexed,wrong['up_return'],blocked[0][0],1.9,10)
        scoped=[(i,r) for i,r in indexed if lo<i<action[0]]
        input_proof=protected_input_pipeline(scoped,observations[0][1]['observation']['checker_owner_id'],
            opened[0][0],blocked[0][0],observations[0][0],allow_extra=True)
        require(input_proof['dialog_owner_id']==owner and input_proof['return_key']==return_key,
            'full input validation belongs to the submitted dialog and native Return key')
    else:
        require(not selected('p04j_confirmation_wrong_blocked'), 'simple confirmation has no protected-input simulation')
    return dict(inventory_id=identity, dialog_owner_id=owner, original_button_line=line, **pair)


def trace_evidence(traces, durable):
    scenarios, relogins, files, shared_ammo = [], [], [], None
    for path, records, sha in traces:
        pid = runtime_trace_header(path, records)
        indexed = list(enumerate(records, 1))
        def events(name):
            return [(i, r) for i, r in indexed if r.get('event') == name]
        actions = events('p04j_dismissal_action')
        proof = []
        if actions:
            end = events('p04j_dismissal_preflight')
            require(len(end) == 1, 'full native scenario starts with cancel-only preflight')
            preflight = preflight_trace(path, records[:end[0][0]], sha, durable)
            initial = events('p04j_preflight_before')[0][1]
            ammo = initial['ammunition']
            before, after = events('p04j_dismissal_before'), events('p04j_dismissal_after')
            requests, callbacks = events('p04j_native_dismissal_request'), events('p04j_dismissal_callback')
            require(len(actions) == len(before) == len(after) == len(requests) == len(callbacks) == 6,
                'exact six original native operations')
            for n, (step, op) in enumerate(zip(STEPS, durable['operations'])):
                b, act, req, cb, aft = before[n], actions[n], requests[n], callbacks[n], after[n]
                require(end[0][0] < b[0] < act[0] < req[0] < cb[0] < aft[0]
                    and (n == 0 or after[n-1][0] < b[0]), 'native six-step causal order')
                for _, event in (b, act, cb, aft):
                    require(type(event.get('step')) is int and event['step'] == n
                        and event.get('policy') == UI_POLICY, 'native step and policy')
                require(b[1].get('name') == act[1].get('name') == aft[1].get('name') == step[0]
                    and act[1].get('original_callback') == step[1]
                    and same_literal(act[1].get('arguments'), step[2])
                    and type(act[1].get('native_cmd')) is int and act[1]['native_cmd'] == step[4]
                    and same_literal(act[1].get('layout'), step[3]), 'original callback and arguments')
                readback(b[1], durable, op['before'], 1, ammo)
                readback(aft[1], durable, op['after'], 1, ammo, True)
                retired_readback(b[1], op['before']); retired_readback(aft[1], op['after'])
                receipt = native_command_receipt(indexed, req, cb, op)
                if step[4] == 306:
                    receipt['original_confirmation'] = positive_confirmation(indexed, b, act, req, cb, op, durable,
                        preflight['input_validation']['return_key'])
                proof.append(dict(step=n, before_line=b[0], action_line=act[0], after_line=aft[0], **receipt))
            require(len({r['owner_id'] for r in proof}) == 1, 'single native Account owner for all six commands')
            require(len(events('p04j_native_confirmation_button')) == 2
                and len(events('p04j_engine_key_input')) == 12, 'exact positive and negative native input events')
            hires = events('p04j_dismissal_recruit_window')
            require(len(hires) == 1 and before[2][0] < hires[0][0] < actions[2][0], 'original hire11 window before native request')
            readback(hires[0][1], durable, durable['operations'][2]['before'], 1)
            require(same_literal(hires[0][1].get('observation'), dict(vehicle=1, slot=1, role='driver',
                role_level=50, tariff=0, free_quota=6, label='50%, бесплатно: 6', paid_controls_hidden=True,
                original_window_title_preserved=True)), 'original hire11 free50 controls')
            final = events('p04j_dismissal_final')
            require(len(final) == 1 and after[-1][0] < final[0][0], 'native six-command final readback')
            result = final[0][1]
            for key, value in dict(operations=6, dismissals=2, hires=1, transfers=3).items():
                require(type(result.get(key)) is int and result[key] == value, 'native operation counts')
            require(result.get('actual_engine_input') is True and result.get('physical_pointer_input') is False,
                'actual engine events distinguished from physical input')
            readback(result, durable, durable['final'], 1, ammo, True); retired_readback(result, durable['final'])
            scenarios.append(dict(trace=str(path), process_id=pid, preflight=preflight, steps=proof, final_line=final[0][0]))
        else:
            views, selections = events('p04j_dismissal_relogin_view'), events('p04j_dismissal_select')
            require(len(views) == len(selections) == 2 and [r.get('vehicle') for _, r in views] == [2, 1]
                and [r.get('vehicle') for _, r in selections] == [2, 1], 'fresh login observes both vehicles')
            require(selections[0][0] < views[0][0] < selections[1][0] < views[1][0], 'fresh native carousel order')
            ammo = views[0][1].get('ammunition'); validate_ammunition(ammo)
            for (line, select), (_, event), vehicle in zip(selections, views, (2, 1)):
                require(select.get('original_callback') == 'TankCarousel.vehicleChange'
                    and select.get('policy') == UI_POLICY, 'original fresh-login selection')
                readback(event, durable, durable['final'], vehicle, ammo, True); retired_readback(event, durable['final'])
            require(not events('p04j_native_dismissal_request') and not events('p04j_native_confirmation_button')
                and not events('p04j_engine_key_input'), 'fresh login contains no mutation or submit input')
            final = events('p04j_dismissal_relogin')
            require(len(final) == 1 and final[0][0] > views[-1][0], 'fresh login final observation')
            result = final[0][1]
            require(type(result.get('operations')) is int and result['operations'] == 0
                and result.get('action') == 'read_only' and result.get('exact_snapshot_match') is True
                and same_literal(result.get('vehicles_observed'), [2, 1]), 'read-only fresh-login completion')
            readback(result, durable, durable['final'], 1, ammo, True); retired_readback(result, durable['final'])
            relogins.append(dict(trace=str(path), process_id=pid, line=final[0][0], vehicles_observed=[2, 1]))
        if shared_ammo is None:
            shared_ammo = ammo
        require(same_literal(shared_ammo, ammo), 'unchanged ammunition across native processes')
        files.append(dict(path=str(path), sha256=sha, records=len(records)))
    require(len(scenarios) == len(relogins) == 1 and scenarios[0]['process_id'] != relogins[0]['process_id'],
        'actual scenario and fresh native process required')
    return dict(scenario=scenarios[0], relogin=relogins[0], files=files,
        unchanged_ammunition_sha256=digest(canonical(shared_ammo)), physical_input='NOT_RUN')



PREFLIGHT_PIXEL_STAGES=dict({name:'p04j_preflight_'+name for name in ('protected','wrong','correct','simple')},cancel='p04j_preflight_final')
FULL_PIXEL_STAGES=dict(PREFLIGHT_PIXEL_STAGES,dismiss_wrong='p04j_dismiss_wrong_input',
    dismiss3='p04j_dismiss_confirm_3',dismiss5='p04j_dismiss_confirm_5',final='p04j_restore_driver_11')
RELOGIN_PIXEL_STAGES={'ms1':'p04j_relogin_ms1','is7':'p04j_relogin_is7'}


def png_container(raw):
    require(45<=len(raw)<=16*1024*1024 and raw[:8]==b'\x89PNG\r\n\x1a\n','bounded actual PNG signature')
    offset=8;count=0;dimensions=None;data=0;ended=False
    while offset<len(raw):
        require(count<1024 and offset+12<=len(raw),'bounded PNG chunk framing')
        length=struct.unpack_from('>I',raw,offset)[0];end=offset+12+length
        require(end<=len(raw),'PNG chunk bounds')
        kind=raw[offset+4:offset+8];body=raw[offset+8:end-4]
        require(zlib.crc32(kind+body)&0xffffffff==struct.unpack_from('>I',raw,end-4)[0],'PNG chunk CRC')
        if count==0:
            require(kind==b'IHDR' and length==13,'PNG header first')
            w,h,depth,color,compression,filtering,interlace=struct.unpack('>IIBBBBB',body)
            require(1<=w<=16384 and 1<=h<=16384 and depth in {0:(1,2,4,8,16),2:(8,16),3:(1,2,4,8),4:(8,16),6:(8,16)}.get(color,())
                and compression==filtering==0 and interlace in (0,1),'bounded PNG image format')
            dimensions=[w,h]
        else:require(kind!=b'IHDR','one PNG header')
        if kind==b'IDAT':data+=length
        if kind==b'IEND':
            require(length==0 and end==len(raw) and data>0,'complete PNG image terminator');ended=True
        offset=end;count+=1
    require(ended,'complete PNG required')
    return dimensions


def pixel_evidence(trace,records,trace_sha,review_path,stages):
    trace=owned(trace);events=[(i,r) for i,r in enumerate(records,1) if r.get('event')=='p04j_dismissal_screenshot']
    require(1<=len(events)<=64,'bounded native screenshots required')
    captures={};proof=[]
    for line,event in events:
        item=event.get('screenshot')
        require(type(item) is dict and set(item)=={'basename','path','bytes','sha256','dimensions','png_container_valid','native_pixels_review'},'exact native screenshot fields')
        base=item['basename'];require(type(base) is str and re.fullmatch(r'p04j_[a-z0-9_]{1,64}',base),'native screenshot basename')
        path=owned(item['path'])
        require(path.parent==trace.parent/'screenshots' and re.fullmatch(re.escape(base)+r'_[0-9]{3,10}\.png',path.name),'native screenshot bound to this trace directory')
        raw=read(path,16*1024*1024);dimensions=png_container(raw)
        require(type(item['bytes']) is int and item['bytes']==len(raw) and item['sha256']==digest(raw)
            and same_literal(item['dimensions'],dimensions) and item['png_container_valid'] is True
            and item['native_pixels_review']=='NOT_RUN','native PNG metadata binding without invented visual review')
        require(base not in captures,'one screenshot per named stage');captures[base]=(line,item)
        proof.append(dict(line=line,path=str(path),bytes=len(raw),sha256=digest(raw),dimensions=dimensions,basename=base))
    review_path=owned(review_path);review_raw=read(review_path,65536);review=json_value(review_raw)
    review_fields={'status','reviewer','trace_sha256','stages'}
    require(type(review) is dict and review_fields<=set(review)<=review_fields|{'physical_owner_input','scope'}
        and review['status']=='PASS_ROOT_NATIVE_PIXELS' and review['reviewer']=='root_model_visual_inspection'
        and review['trace_sha256']==trace_sha and type(review['stages']) is dict and set(review['stages'])==set(stages),
        'exact current-trace independent pixel inspection receipt')
    require(review.get('physical_owner_input','NOT_RUN')=='NOT_RUN'
        and type(review.get('scope','')) is str and len(review.get('scope',''))<=4096,'pixel review scope is bounded and distinct from physical input')
    for stage,basename in stages.items():
        require(basename in captures,'required native screenshot stage missing')
        row=review['stages'][stage]
        require(type(row) is dict and {'screenshot_sha256','outcome','observation'}<=set(row)<={'screenshot_sha256','outcome','observation','path'} and row['outcome']=='PASS'
            and row['screenshot_sha256']==captures[basename][1]['sha256'] and type(row['observation']) is str
            and 1<=len(row['observation'])<=4096,'visual inspection bound to exact stage PNG')
        if 'path' in row:
            p=Path(row['path']);p=p if p.is_absolute() else ROOT/p
            require(owned(p)==owned(captures[basename][1]['path']),'reviewed PNG path binding')
        if stage in ('protected','wrong','correct','simple'):
            observed=[i for i,r in enumerate(records,1) if r.get('event')=='p04j_confirmation_observed' and r.get('stage')==stage]
            require(observed and captures[basename][0]<observed[0],'PNG captured before corresponding confirmation observation')
    return dict(status='PASS_CAPTURE_BINDINGS_WITH_ROOT_VISUAL_REVIEW',images=proof,review_path=str(review_path),
        review_sha256=digest(review_raw),reviewer=review['reviewer'],stages=review['stages'],physical_input='NOT_RUN')


def verify(wires,traces,private_key,before_database,database_path,relogin_database,original_root,install_plans,pixel_reviews):
    require(len(wires)==len(traces)==len(install_plans)==len(pixel_reviews)==2,'scenario and fresh-login inputs required')
    source=audit_sources(Path(original_root));source_sha=digest(canonical(source))
    durable=verify_databases(database(before_database),database(database_path),database(relogin_database),source_sha)
    private=serialization.load_pem_private_key(read(owned(private_key),16384),None)
    require(private.key_size==1024,'capture key size')
    trace_rows=[(owned(p),*rows(owned(p))) for p in traces]
    native=trace_evidence(trace_rows,durable)
    plans=install_bindings(install_plans,traces,read_application(Path(original_root)))
    captures=[];matching=[];pixels=[]
    for wire,(path,records,sha),review in zip(wires,trace_rows,pixel_reviews):
        frames,proof=capture(wire,private);captures.append(proof)
        has_commands=any(f['direction']=='base_client_to_server' and is_crew_command(f['body']) for f in frames)
        scenario=any(r.get('event')=='p04j_dismissal_action' for r in records)
        require(has_commands is scenario,'wire capture and trace operation mode must agree')
        if scenario:
            matching.append(wire_evidence(frames,durable))
            plan=next(p for p in plans if Path(p['trace_directory'])==path.parent)
            native['scenario']['resolved_flash']=native_flash_binding(records,plan)
        else:require(any(f['direction']=='base_server_to_client' for f in frames),'fresh login authenticated data required')
        pixels.append(pixel_evidence(path,records,sha,review,FULL_PIXEL_STAGES if scenario else RELOGIN_PIXEL_STAGES))
    require(len(matching)==1,'one six-command capture required')
    return dict(status='PASS_NATIVE_DISMISSAL_SPARSE_CREW_WIRE_RELOGIN',classification='OBSERVED_NATIVE_717',
        wire=matching[0],captures=captures,native=native,database=durable['database_proof'],install_plans=plans,
        pixels=pixels,current_implementation_sources=implementation_sources(),source_audit_sha256=source_sha,
        input_source=input_source_audit(original_root),validation_source=validation_source_audit(original_root),
        display_source=display_source_audit(original_root),registered_movie_source=registered_dialog_source_audit(original_root),
        rendered_source=rendered_source_audit(original_root),final_ms1_crew=[4,11],final_is7_crew=[6,7,8,10,9],
        retired_ids=[3,5],next_native_id=12,free_quota=5,physical_input='NOT_RUN',
        boolean_readback='UNAVAILABLE_OBSERVED',limits=[
            'Original native engine events are diagnostic input, not physical owner keyboard or mouse input.',
            'Raw reflected Boolean properties are not accepted as enabled/validation state; original callbacks, setters and Enter behavior are required.',
            'Visual inspection is separately attributed to the root reviewer and bound to exact PNG files.',
            'No tariff, reset, retraining, dismissal recovery or combat behavior is accepted.'])

def verify_preflight(wire,trace,private_key,before_database,after_database,original_root,install_plan,pixel_review):
    source=audit_sources(Path(original_root));source_sha=digest(canonical(source))
    durable=preflight_databases(database(before_database),database(after_database),source_sha)
    private=serialization.load_pem_private_key(read(owned(private_key),16384),None)
    require(private.key_size==1024,'capture key size')
    frames,proof=capture(wire,private)
    require(not any(f['direction']=='base_client_to_server' and is_crew_command(f['body']) for f in frames),
        'preflight capture must contain no native crew mutation')
    require(any(f['direction']=='base_server_to_client' for f in frames),'preflight authenticated server data required')
    path=owned(trace);records,sha=rows(path)
    native=preflight_trace(path,records,sha,durable)
    plans=install_bindings([install_plan],[trace],read_application(Path(original_root)))
    native['resolved_flash']=native_flash_binding(records,plans[0])
    return dict(status='PASS_NATIVE_DISMISSAL_CONFIRMATION_CANCEL_ONLY',classification='OBSERVED_NATIVE_717',
        native=native,capture=proof,database=durable['database_proof'],install_plans=plans,
        source_audit_sha256=source_sha,input_source=input_source_audit(original_root),
        validation_source=validation_source_audit(original_root),display_source=display_source_audit(original_root),
        registered_movie_source=registered_dialog_source_audit(original_root),rendered_source=rendered_source_audit(original_root),
        current_implementation_sources=implementation_sources(),native_dismissal='NOT_RUN',
        positive_button_event='NOT_RUN',fresh_login='NOT_RUN',
        pixels=pixel_evidence(path,records,sha,pixel_review,PREFLIGHT_PIXEL_STAGES),physical_input='NOT_RUN')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('preflight','full'),required=True)
    for name in ('wire','trace','install-plan','pixel-review'):parser.add_argument('--'+name,action='append',required=True)
    for name in ('private-key','before-database','database','original-root','out'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--relogin-database')
    args=parser.parse_args();out=Path(args.out).resolve()
    require(out.is_relative_to(LOCAL.resolve()) and not out.exists(),'fresh owned output required')
    out.mkdir(parents=True)
    try:
        if args.mode=='preflight':
            require(len(args.wire)==len(args.trace)==len(args.install_plan)==len(args.pixel_review)==1 and args.relogin_database is None,'one preflight input set required')
            result=verify_preflight(args.wire[0],args.trace[0],args.private_key,args.before_database,args.database,args.original_root,args.install_plan[0],args.pixel_review[0])
        else:
            require(args.relogin_database is not None,'full acceptance requires fresh-login database')
            result=verify(args.wire,args.trace,args.private_key,args.before_database,args.database,args.relogin_database,args.original_root,args.install_plan,args.pixel_review)
    except Exception as error:
        result=dict(status='FAIL',error_type=type(error).__name__,reason=str(error) if type(error) is EvidenceError else 'Malformed, missing or inconsistent bounded evidence')
    (out/'receipt.json').write_bytes(canonical(result))
    print(json.dumps(dict(status=result['status'],receipt=str(out/'receipt.json'))))
    return 0 if result['status'].startswith('PASS_') else 1


if __name__=='__main__':
    raise SystemExit(main())
