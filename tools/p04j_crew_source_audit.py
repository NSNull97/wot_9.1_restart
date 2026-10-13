"""Bounded pinned #717 dismissal/cache and one-method Flash compatibility audit.

Original Python and ActionScript are data only. No native execution or writes.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zipfile
import zlib

if __package__:
    from . import p04i_crew_source_audit as baseline
else:
    import p04i_crew_source_audit as baseline

static = baseline.static
ROOT = Path(__file__).resolve().parents[1]
SOURCE_BUILD, SOURCE_MANIFEST = baseline.SOURCE_BUILD, baseline.SOURCE_MANIFEST
OPCODE_PIN = baseline.OPCODE_PIN
pinned_read, write_receipt = baseline.pinned_read, baseline.write_receipt
SOURCE_PINS = dict(baseline.SOURCE_PINS, **{'client/account_helpers/diff_utils.pyc': [1194,
                                           '46c1582f244c27ed72b1b38890f86a03ca5de339af36b3d2a77b39a3e9de7517'],
 'client/account_helpers/inventory.pyc': [22611,
                                          '3d17842cc6fa9af05d53cc6d22dc286e6b0434356e58c6f74d5822c2dd3cbf19'],
 'client/gui/scaleform/daapi/view/dialogs/dismisstankmandialog.pyc': [4489,
                                                                      '75af4fee6a643ee8a5230a244060ecf6b3798562f28d594411f2e19310ac320d'],
 'client/gui/scaleform/daapi/view/dialogs/simpledialog.pyc': [3854,
                                                              '3064069511f89cf4b6d14ae82ecbfb15677052a8a721aaa005d5f1aebadf660b'],
 'client/gui/scaleform/daapi/view/lobby/barracks/barracks.pyc': [13142,
                                                                 '1c18c924c6bfb9e753dae3f637b8b8079807a25b2e08e421b895bbb83bab3f19'],
 'client/gui/scaleform/daapi/view/lobby/inputchecker/inputchecker.pyc': [3641,
                                                                         '80a2da5a05e7afc4954134f0c21a8e6ed07520727c4d6c3ac8d57a8dc3a2a2e5'],
 'client/gui/scaleform/daapi/view/lobby/personalcase.pyc': [19546,
                                                            '2d550383e093fd75f872a84e45fd2447a7d9e9db0637b4c0836c83740c7f7ab2'],
 'client/gui/scaleform/flash.pyc': [8272, '059aad4f6ed0d3ce5b82e8a819dd0f0181e403ef25c803bfc7e452a621495dc4'],
 'client/gui/scaleform/framework/application.pyc': [17315,
                                                    'da735c90a51bb78e276d005d19559b13e338c57492ed3728191e456be688aca6'],
 'client/gui/scaleform/framework/entities/daapimodule.pyc': [6524,
                                                             'a737c93d2a1168273b13e758ceee60adf17c037754fd4b5eb47932df984bbef2'],
 'client/gui/shared/gui_items/processors/plugins.pyc': [25426,
                                                        '5d19c2f421b9f4f324bebd5a66ab31e4c990ec6b9298863c07c323c61749abdd'],
 'client/gui/shared/gui_items/processors/tankman.pyc': [25844,
                                                        'ef86bdc26577dc1d34dcc0c2f97ce230c185e5ae5b5ec41aaef5766224274d21'],
 'client/gui/shared/utils/requesters/inventoryrequester.pyc': [12868,
                                                               '4e2c79a4f826740b3363b14b00dba7aeaa9a539dc3c1b32671eb5256f4103e84'],
 'client/gui/shared/utils/requesters/itemsrequester.pyc': [28259,
                                                           '41e5e9bacbb68e89202116bd267c6cd9fceeda4edb0ed605c7b87cc9315c0c44'],
 'common/accountcommands.pyc': [5534, 'ba439d8badead15bba4f28708c1822630c1d58fe4699bd07d76d99db345dc2fe']})
SOURCE_PINS = {name: tuple(pin) for name, pin in SOURCE_PINS.items()}
AUDIT_OPCODES = dict(baseline.AUDIT_OPCODES)
AUDIT_OPCODES.update({12: 'UNARY_NOT',
 60: 'STORE_SUBSCR',
 61: 'DELETE_SUBSCR',
 83: 'RETURN_VALUE',
 86: 'YIELD_VALUE',
 90: 'STORE_NAME',
 95: 'STORE_ATTR',
 100: 'LOAD_CONST',
 106: 'LOAD_ATTR',
 107: 'COMPARE_OP',
 114: 'POP_JUMP_IF_FALSE',
 115: 'POP_JUMP_IF_TRUE',
 116: 'LOAD_GLOBAL',
 124: 'LOAD_FAST',
 131: 'CALL_FUNCTION'})
# Source, qualified method, source line, arguments, whole-code SHA, semantic offsets.
ANCHORS = [('common/accountcommands.pyc',
  '<module>',
  1,
  [],
  '3e4571a793c8afc82a5932d98a31a4169141175850b197982e15c510fb610922',
  {298: ('LOAD_CONST', 306), 301: ('STORE_NAME', 'CMD_DISMISS_TMAN')}),
 ('client/account_helpers/inventory.pyc',
  '<module>.Inventory.dismissTankman',
  162,
  ['self', 'tmanInvID', 'callback'],
  '08cd662d9548083823b79784d4a1b8517df31f567f2607aca0566e251507217c',
  {86: ('LOAD_ATTR', '_doCmdInt3'),
   92: ('LOAD_ATTR', 'CMD_DISMISS_TMAN'),
   95: ('LOAD_FAST', 'tmanInvID'),
   98: ('LOAD_CONST', 0),
   101: ('LOAD_CONST', 0),
   107: ('CALL_FUNCTION', 5)}),
 ('client/account_helpers/inventory.pyc',
  '<module>.Inventory.synchronize',
  68,
  ['self', 'isFullSync', 'diff'],
  '2be8281a523c38f925ee35c6da61992abbd6e4753815f6f32539206bde6bcde1',
  {28: ('LOAD_CONST', 'inventory'),
   77: ('LOAD_GLOBAL', 'synchronizeDicts'),
   92: ('LOAD_FAST', 'itemTypeIdx'),
   98: ('CALL_FUNCTION', 2),
   101: ('CALL_FUNCTION', 2)}),
 ('client/account_helpers/diff_utils.pyc',
  '<module>.synchronizeDicts',
  7,
  ['diff', 'cache'],
  'e6f4450baa485edaf933efaab5376e9cc705879ff4df723fc8ae55cc36819993',
  {312: ('LOAD_FAST', 'value'),
   315: ('LOAD_CONST', None),
   318: ('COMPARE_OP', 8),
   327: ('LOAD_ATTR', 'pop'),
   330: ('LOAD_FAST', 'key_u'),
   333: ('LOAD_CONST', None),
   336: ('CALL_FUNCTION', 2),
   490: ('LOAD_FAST', 'value'),
   499: ('STORE_SUBSCR', None)}),
 ('client/gui/shared/gui_items/processors/tankman.pyc',
  '<module>.TankmanDismiss.__init__',
  15,
  ['self', 'tankman'],
  'de882aa745c861261459c90e05ab2a97d3ed10421dc9544143cc4e908fdd6268',
  {9: ('LOAD_ATTR', 'vehicleInvID'),
   12: ('LOAD_CONST', 0),
   15: ('COMPARE_OP', 4),
   48: ('LOAD_ATTR', 'DismissTankmanConfirmator'),
   51: ('LOAD_CONST', 'protectedDismissTankman'),
   57: ('CALL_FUNCTION', 2),
   99: ('LOAD_ATTR', 'VehicleValidator'),
   111: ('LOAD_ATTR', 'vehicleInvID'),
   114: ('LOAD_CONST', 0),
   117: ('COMPARE_OP', 4),
   120: ('CALL_FUNCTION', 257)}),
 ('client/gui/shared/gui_items/processors/tankman.pyc',
  '<module>.TankmanDismiss._request',
  44,
  ['self', 'callback'],
  'd5b71dd102db49b223aa2dcc2b4662034f45f9639c16af6023fb336dcec5ba67',
  {19: ('LOAD_ATTR', 'player'),
   25: ('LOAD_ATTR', 'inventory'),
   28: ('LOAD_ATTR', 'dismissTankman'),
   37: ('LOAD_ATTR', 'invID'),
   55: ('CALL_FUNCTION', 2)}),
 ('client/gui/scaleform/daapi/view/lobby/personalcase.pyc',
  '<module>.PersonalCase.dismissTankman',
  146,
  ['self', 'tmanInvID'],
  '1336cba4355f8d9634d8cd1f569af69211ecbf2a979c2004580ddea42b45a1b1',
  {6: ('LOAD_ATTR', 'getTankman'),
   9: ('LOAD_GLOBAL', 'int'),
   12: ('LOAD_FAST', 'tmanInvID'),
   24: ('LOAD_GLOBAL', 'TankmanDismiss'),
   39: ('LOAD_ATTR', 'request'),
   45: ('YIELD_VALUE', None)}),
 ('client/gui/scaleform/daapi/view/lobby/barracks/barracks.pyc',
  '<module>.Barracks.dismissTankman',
  304,
  ['self', 'invID'],
  '18be4364e24ced33a831e6dccc7b245a78266dd8a500f0908c31985ef0d2f5cf',
  {6: ('LOAD_ATTR', 'getTankman'),
   12: ('LOAD_FAST', 'invID'),
   27: ('LOAD_CONST', None),
   30: ('COMPARE_OP', 8),
   49: ('RETURN_VALUE', None),
   50: ('LOAD_GLOBAL', 'TankmanDismiss'),
   59: ('LOAD_ATTR', 'request'),
   65: ('YIELD_VALUE', None)}),
 ('client/gui/scaleform/daapi/view/dialogs/dismisstankmandialog.pyc',
  '<module>.DismissTankmanDialog.__prepareTankmanData',
  32,
  ['self'],
  '7d94e5124f9a43ae6385e17acb9a820e1b43444f77e337a6e2590238ab07cace',
  {34: ('LOAD_ATTR', 'dropSkillsCost'),
   65: ('LOAD_ATTR', 'dropSkillsCost'),
   129: ('LOAD_ATTR', 'roleLevel'),
   135: ('LOAD_ATTR', 'MAX_SKILL_LEVEL'),
   138: ('COMPARE_OP', 2),
   159: ('LOAD_ATTR', 'lastSkillLevel'),
   168: ('COMPARE_OP', 2),
   189: ('UNARY_NOT', None),
   196: ('LOAD_ATTR', 'as_tankManS'),
   246: ('LOAD_CONST', 'dropSkillsCost'),
   253: ('LOAD_CONST', 'hasNewSkills'),
   266: ('LOAD_CONST', 'newSkills'),
   273: ('LOAD_CONST', 'defaultSavingMode'),
   277: ('CALL_FUNCTION', 1),
   290: ('LOAD_ATTR', 'skills'),
   296: ('LOAD_CONST', 1),
   299: ('COMPARE_OP', 0),
   311: ('LOAD_ATTR', 'roleLevel'),
   314: ('LOAD_CONST', 100),
   317: ('COMPARE_OP', 0),
   347: ('LOAD_GLOBAL', 'str'),
   356: ('LOAD_ATTR', 'roleLevel'),
   365: ('STORE_ATTR', '_DismissTankmanDialog__controlNumber'),
   534: ('LOAD_GLOBAL', 'str'),
   550: ('LOAD_ATTR', 'level'),
   559: ('STORE_ATTR', '_DismissTankmanDialog__controlNumber'),
   565: ('LOAD_ATTR', '_DismissTankmanDialog__updateInputChecker'),
   568: ('CALL_FUNCTION', 0)}),
 ('client/gui/scaleform/daapi/view/dialogs/dismisstankmandialog.pyc',
  '<module>.DismissTankmanDialog.__updateInputChecker',
  84,
  ['self'],
  '4aa11895d80495ec8f40c3ac38c5845b46c74398fc4a04075af462b250eb4832',
  {21: ('LOAD_ATTR', 'setControlNumbers'),
   30: ('LOAD_ATTR', '_DismissTankmanDialog__controlNumber'),
   36: ('CALL_FUNCTION', 1),
   52: ('STORE_ATTR', 'questionBody'),
   67: ('STORE_ATTR', 'errorMsg')}),
 ('client/gui/scaleform/daapi/view/dialogs/dismisstankmandialog.pyc',
  '<module>.DismissTankmanDialog._populate',
  28,
  ['self'],
  'a72a17c6921d4b4b7f66902ef7e2d34b56f1be7867cebd136984004febbca70b',
  {22: ('LOAD_ATTR', '_DismissTankmanDialog__prepareTankmanData'), 25: ('CALL_FUNCTION', 0)}),
 ('client/gui/scaleform/daapi/view/dialogs/simpledialog.pyc',
  '<module>.SimpleDialog.__callHandler',
  22,
  ['self', 'buttonID'],
  'f47ec1bec277d73bcdbe6546a85aa3a967e65ba2b5ca5dee493ebbada38ecb48',
  {21: ('LOAD_FAST', 'buttonID'),
   27: ('LOAD_ATTR', 'SUBMIT'),
   30: ('COMPARE_OP', 2),
   33: ('CALL_FUNCTION', 1)}),
 ('client/gui/scaleform/daapi/view/dialogs/simpledialog.pyc',
  '<module>.SimpleDialog.onButtonClick',
  56,
  ['self', 'buttonID'],
  '696f4e2b6d374d6380ef1a45b02b859fd6c4e2c6726c689db7832e0779a74d74',
  {3: ('LOAD_ATTR', '_SimpleDialog__callHandler'),
   6: ('LOAD_FAST', 'buttonID'),
   9: ('CALL_FUNCTION', 1),
   16: ('LOAD_ATTR', 'destroy'),
   19: ('CALL_FUNCTION', 0)}),
 ('client/gui/scaleform/daapi/view/lobby/inputchecker/inputchecker.pyc',
  '<module>.InputChecker.setControlNumbers',
  28,
  ['self', 'controlNumber', 'formatFunction'],
  '33e2b69396228e48ef0acbf87899228ee1e01498ec8e20520fbed85785268045',
  {24: ('LOAD_ATTR', 'as_invalidUserTextS'),
   27: ('LOAD_GLOBAL', 'False'),
   88: ('STORE_ATTR', '_InputChecker__originalControlNumber'),
   94: ('LOAD_ATTR', 'as_setFormattedControlNumberS'),
   110: ('LOAD_ATTR', 'as_setOriginalControlNumberS')}),
 ('client/gui/scaleform/daapi/view/lobby/inputchecker/inputchecker.pyc',
  '<module>.InputChecker.sendUserInput',
  42,
  ['self', 'value', 'isValidSyntax'],
  'cb9e860d3ec383bec93b13a02bf48ca85f40a8dd2cab78aa3334802699f94c89',
  {6: ('LOAD_ATTR', '_InputChecker__originalControlNumber'),
   9: ('COMPARE_OP', 2),
   15: ('LOAD_FAST', 'isValidSyntax'),
   18: ('POP_JUMP_IF_FALSE', 37),
   24: ('LOAD_ATTR', 'as_invalidUserTextS'),
   27: ('LOAD_GLOBAL', 'True'),
   40: ('LOAD_ATTR', 'as_invalidUserTextS'),
   43: ('LOAD_GLOBAL', 'False')}),
 ('client/gui/shared/utils/requesters/itemsrequester.pyc',
  '<module>.ItemsRequester.invalidateCache',
  283,
  ['self', 'diff'],
  '4e67bb506dff5bd552347650786d2caa0da48a67e8d2ad5e47131851e7f61737',
  {777: ('LOAD_ATTR', 'TANKMAN'),
   780: ('COMPARE_OP', 2),
   818: ('LOAD_ATTR', 'keys'),
   824: ('CALL_FUNCTION', 1),
   868: ('LOAD_ATTR', 'getTankmanData'),
   883: ('LOAD_CONST', None),
   889: ('POP_JUMP_IF_FALSE', 841),
   895: ('LOAD_ATTR', 'vehicle'),
   898: ('LOAD_CONST', -1),
   901: ('COMPARE_OP', 3),
   923: ('LOAD_ATTR', '_ItemsRequester__getVehicleCDForTankman'),
   952: ('LOAD_ATTR', '_ItemsRequester__getTankmenIDsForTankman')}),
 ('client/gui/shared/utils/requesters/itemsrequester.pyc',
  '<module>.ItemsRequester._invalidateItems',
  573,
  ['self', 'itemTypeID', 'uniqueIDs'],
  '8dd3974a629f059706414b4f3a0992cd72c4904f95e48e687171f0b9221d1ada',
  {32: ('LOAD_ATTR', 'invalidateItem'), 41: ('CALL_FUNCTION', 2), 88: ('DELETE_SUBSCR', None)}),
 ('client/gui/shared/utils/requesters/itemsrequester.pyc',
  '<module>.ItemsRequester.__makeTankman',
  677,
  ['self', 'tmanInvID', 'tmanInvData'],
  '05405f30bd4e108f86252728360710e959830f1c935c8b5021ab90910db4d6cc',
  {12: ('LOAD_ATTR', 'getTankmanData'),
   27: ('LOAD_CONST', None),
   33: ('POP_JUMP_IF_FALSE', 124),
   99: ('LOAD_ATTR', 'compDescr'),
   124: ('LOAD_CONST', None),
   127: ('RETURN_VALUE', None)}),
 ('client/gui/shared/utils/requesters/inventoryrequester.pyc',
  '<module>.InventoryRequester.invalidateItem',
  71,
  ['self', 'itemTypeID', 'invIdx'],
  '628399676e4db0f9fd5a9d4d9088e29a8f14864ad88f06e444199a6ad494d7c0',
  {19: ('COMPARE_OP', 6), 45: ('STORE_SUBSCR', None), 52: ('DELETE_SUBSCR', None)}),
 ('client/gui/shared/utils/requesters/inventoryrequester.pyc',
  '<module>.InventoryRequester.__makeTankman',
  182,
  ['self', 'tmanInvID'],
  'f9c149a912baa3089c04b895df13eae070e8e76b5e75828b08ed138a95e3987e',
  {81: ('LOAD_CONST', 'compDescr'),
   84: ('CALL_FUNCTION', 1),
   93: ('LOAD_CONST', None),
   96: ('COMPARE_OP', 8),
   102: ('LOAD_CONST', None),
   105: ('RETURN_VALUE', None),
   118: ('LOAD_ATTR', 'TankmanDescr'),
   133: ('LOAD_CONST', -1)}),
 ('client/gui/scaleform/framework/application.pyc',
  '<module>.App.utilsManager',
  208,
  ['self'],
  'cd191e3a1561de10795069d3df295b7eaff3f51c14695fba12bee31648826dce',
  {3: ('LOAD_ATTR', '_utilsMgr'), 6: ('RETURN_VALUE', None)}),
 ('client/gui/scaleform/framework/entities/daapimodule.pyc',
  '<module>.DAAPIModule.flashObject',
  34,
  ['self'],
  'cd191e3a1561de10795069d3df295b7eaff3f51c14695fba12bee31648826dce',
  {3: ('LOAD_ATTR', '_DAAPIModule__flashObject'), 6: ('RETURN_VALUE', None)}),
 ('client/gui/shared/gui_items/processors/plugins.pyc',
  '<module>.DismissTankmanConfirmator.__init__',
  503,
  ['self', 'localeKey', 'tankman'],
  '6e3e83ce84907cd9075ee4ecee89773d8960b4201b09b53660ecc0f3218d5fee',
  {15: ('LOAD_FAST', 'localeKey'),
   18: ('LOAD_FAST', 'tankman'),
   24: ('LOAD_GLOBAL', 'True'),
   27: ('CALL_FUNCTION', 4)}),
 ('client/gui/shared/gui_items/processors/plugins.pyc',
  '<module>.DismissTankmanConfirmator._makeMeta',
  506,
  ['self'],
  '18eb1d494450bba6daa41ef675c81b62185029930ab269957fca6202879b8bcc',
  {0: ('LOAD_GLOBAL', 'DismissTankmanDialogMeta'),
   15: ('LOAD_CONST', 'focusedID'),
   21: ('LOAD_ATTR', 'SUBMIT'),
   24: ('CALL_FUNCTION', 258)}),
 ('client/gui/shared/gui_items/processors/plugins.pyc',
  '<module>.DialogAbstractConfirmator._confirm',
  451,
  ['self', 'callback'],
  'd3f2d2402fd79e0f781a72d75dcb83fbd9a7737cea2722d5ded7a686bf9b1001',
  {23: ('LOAD_ATTR', 'showDialog'),
   32: ('LOAD_ATTR', '_makeMeta'),
   41: ('YIELD_VALUE', None),
   45: ('LOAD_FAST', 'isOk'),
   48: ('POP_JUMP_IF_TRUE', 71),
   54: ('LOAD_GLOBAL', 'makeError'),
   74: ('LOAD_GLOBAL', 'makeSuccess')}),
 ('client/gui/shared/gui_items/processors/plugins.pyc',
  '<module>.AsyncConfirmator.confirm',
  83,
  ['self', 'callback'],
  '4d2749237adf506a76b52804a7b54540c0179f8ea695c63efce80aa2bde0f73c',
  {3: ('LOAD_ATTR', '_confirm'),
   6: ('CALL_FUNCTION', 0),
   9: ('YIELD_VALUE', None),
   19: ('CALL_FUNCTION', 1)})]
# Method index, QName, code offset in decompressed SWF body, size, code SHA.
FLASH_ANCHORS = [(785,
  'ClassFactory.getObject',
  1972967,
  143,
  '7042fce5972a1d3eb509c57496ce9d98709668500a401ff8fdc0456086308d09'),
 (1509, 'Utils.classFactory', 2022265, 7, '404ceb23396206f848f0e4b089e67d0ec16bcb1b67159d04889aac643ca2d25c'),
 (2445,
  'Button.handleInput',
  2060173,
  160,
  '92653ec50347a8554cb8e4101c6672718eb74fa4523e62d54e16ef241393c823'),
 (2458,
  'Button.handleMousePress',
  2062188,
  227,
  '11d111ec8774180795320452c67a41c781c2557d3056f373760cf90982dd243c'),
 (2459,
  'Button.handleMouseRelease',
  2062425,
  247,
  '3fed37b615df401ff429179f521981442d4a94885214ff1c52dbeec04add93ec'),
 (2461,
  'Button.handlePress',
  2062914,
  169,
  '95c1d1ed4f9cbc717f1e353e5e4aa63f7d4a55f9d8ad82a3e157e7f9dcb7ad15'),
 (2462,
  'Button.handleRelease',
  2063093,
  166,
  'd5d5c98613cd65ce2230b6dbc77cd8fd039db51520061d3b589faab3ebad76f9'),
 (2463,
  'Button.handleClick',
  2063268,
  43,
  '8858a937e75d6aaebf343ffbc23506a956502bdd504de3f9939b77164592ec39'),
 (3330,
  'SimpleDialog.onButtonClickHdlr',
  2116857,
  63,
  'ced11312c4c73a9f050a54b69947bed5b774aacf8f462d133a44c2dd80ad4d15'),
 (13017,
  'DismissTankmanDialog.as_tankMan',
  2631489,
  145,
  '9f35526bcb6052e7bdcbd7386051d9009e5eb46fcecb6a691a6dab99a6009fb5'),
 (13019,
  'DismissTankmanDialog.onPopulate',
  2631692,
  101,
  '644fe098e0bd66c7673e2876a0fad2ba2572c177db4e4dd8dc55a72f420a7adf'),
 (13020,
  'DismissTankmanDialog.onDispose',
  2631802,
  41,
  '63e274ebb8a481cebacfa68cd288d34038d04dc306c0d5eecc510db5f317eac6'),
 (13021,
  'DismissTankmanDialog.getBackgroundActualHeight',
  2631852,
  52,
  '973dc24c3b6b8fc5a98bbeebd10a39f91b4d3cc814b013b3ecddc1efb640c12e'),
 (13023,
  'DismissTankmanDialog.setData',
  2631934,
  155,
  'f189beb31d72f5bd1ecccf997ba10065911adc95405aa8e432a29d87e79f48d2'),
 (13024,
  'DismissTankmanDialog.onRequestFocusHandler',
  2632098,
  67,
  '51e5f70527d4a11ac0602ef89e52602c32223d6165af3d263b0f9aa14258fd33'),
 (13439,
  'InputChecker.as_invalidUserText',
  2650127,
  40,
  '76860e8204b54228a44b2157a8ccd9e0a16536548e60880eb1d66a7c79879efc'),
 (13444,
  'InputChecker.isValidControlInput',
  2650289,
  44,
  '78fd87216dcf90cae481687f8ed837d113151945c12766b0a83393a9df51ae0d'),
 (13448,
  'InputChecker.runtimeValidate',
  2650482,
  13,
  'ca01794eba82ee144e104425bbc2a3d6d0e936002c13f8a384d7c4c9c29ddeb6'),
 (13452,
  'InputChecker.userInputHandler',
  2650603,
  124,
  '027808b04ea8c07ebcf2b545436bcd99a45b00833f45e648d958118817bafa67'),
 (20636,
  'DropSkillsCost.parseFromObject',
  3116304,
  75,
  '85208199870acdc35ac1a53ea1ea37dd2350aa0c11b9ee0438fe184801a5a617'),
 (20639,
  'SkillDropModel.parseFromObject',
  3116419,
  415,
  'c5f36daf2abb65b97095712a6094d21f7a613a286999a47554a984d69cd4e35d'),
 (20640,
  'SkillDropModel.<init>',
  3116844,
  42,
  '78bfee0da2f26a49240d438a735f4886fd320371be612f92da0df8aa3375806b'),
 (20642,
  'SkillDropModel.dispose',
  3116926,
  21,
  '81ba06b80fbf78afcff23515027cfe8b1be128128a833d586d9ffb23e0925b65')]

APPLICATION_MEMBER = 'gui/flash/Application.swf'
APPLICATION_PIN = (1258376, '8c53f7cf510a3b328ee114307613c8f1416beb3360b587b6b158bb7d8ac02b62')
APPLICATION_HEADER = bytes.fromhex('4357530bad4d3200')
BODY_BYTES = 3296677
BODY_SHA256 = '5a778e0889fbb5e8b73380cd040990342deb54073176f0119d413e1492392b01'
METHOD_OFFSET, METHOD_BYTES = 2631489, 145
OLD_PREFIX = bytes.fromhex('608604d146a2bd0101')
NEW_PREFIX = bytes.fromhex('d18086040202020202')
RESULT_METHOD_SHA256 = '8a0c7901de47ad183c03a441e579177d37665ce435e82725964ce8f099b9773e'
RESULT_BODY_SHA256 = '9709fc7c32e56ba53a55aa15dda1b09f48b4df19e903904b127733dc803003dc'
MAX_SWF_BYTES = 4 * 1024 * 1024
MAX_PACKAGE_BYTES = 700 * 1024 * 1024
MAX_CENTRAL_BYTES = 16 * 1024 * 1024


class SourceAuditError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise SourceAuditError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_application(original_root: Path) -> bytes:
    """Bound the ZIP directory before ZipFile allocates its metadata objects."""
    try:
        path = static.no_links(original_root / 'res/packages/gui.pkg')
        size = path.stat().st_size
        require(22 <= size <= MAX_PACKAGE_BYTES, 'bounded gui package required')
        with path.open('rb') as source:
            source.seek(max(0, size - 65557))
            tail = source.read(65557)
        at = tail.rfind(b'PK\x05\x06')
        require(at >= 0 and len(tail) - at >= 22, 'ZIP end record required')
        _, disk, central_disk, entries_disk, entries, central_size, central_at, comment = struct.unpack(
            '<4s4H2LH', tail[at:at + 22])
        end_at = size - len(tail) + at
        require(disk == central_disk == 0 and entries_disk == entries and 1 <= entries <= 8192,
                'single disk bounded ZIP entry count required')
        require(0 < central_size <= MAX_CENTRAL_BYTES and central_at + central_size == end_at
                and at + 22 + comment == len(tail), 'bounded ZIP central directory required')
        with zipfile.ZipFile(path) as archive:
            rows = [row for row in archive.infolist() if row.filename == APPLICATION_MEMBER]
            require(len(rows) == 1, 'unique Application.swf member required')
            item = rows[0]
            require(item.file_size == APPLICATION_PIN[0] and 0 < item.compress_size <= MAX_SWF_BYTES
                    and item.compress_type in (0, 8) and not item.flag_bits & 1,
                    'bounded unencrypted Application.swf member required')
            with archive.open(item) as stream:
                raw = stream.read(APPLICATION_PIN[0] + 1)
        require(len(raw) == APPLICATION_PIN[0] and digest(raw) == APPLICATION_PIN[1], 'Application.swf pin mismatch')
        return raw
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError, struct.error) as error:
        if isinstance(error, SourceAuditError):
            raise
        raise SourceAuditError('Application.swf source read failed: ' + str(error)) from error


def swf_body(raw: bytes) -> bytes:
    require(type(raw) is bytes and 8 <= len(raw) <= MAX_SWF_BYTES, 'bounded CWS bytes required')
    require(raw[:8] == APPLICATION_HEADER, 'exact CWS header required')
    try:
        decoder = zlib.decompressobj()
        body = decoder.decompress(raw[8:], BODY_BYTES + 1)
    except zlib.error as error:
        raise SourceAuditError('invalid CWS compression') from error
    require(decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail
            and len(body) == BODY_BYTES, 'bounded complete CWS stream required')
    return body


def verify_flash_source(raw: bytes) -> dict:
    require(type(raw) is bytes and len(raw) == APPLICATION_PIN[0] and digest(raw) == APPLICATION_PIN[1],
            'Application.swf pin mismatch')
    body = swf_body(raw)
    require(digest(body) == BODY_SHA256, 'original SWF body pin mismatch')
    assertions = []
    for index, name, offset, size, sha in FLASH_ANCHORS:
        code = body[offset:offset + size]
        require(len(code) == size and digest(code) == sha, 'Flash method pin differs: ' + name)
        assertions.append({'method_index': index, 'method': name, 'offset_in_body': offset,
                           'code_bytes': size, 'code_sha256': sha})
    require(body[METHOD_OFFSET + 10:METHOD_OFFSET + 19] == OLD_PREFIX, 'model initializer bytes differ')
    return {'source_id': 'res/packages/gui.pkg!' + APPLICATION_MEMBER,
        'bytes': APPLICATION_PIN[0], 'sha256': APPLICATION_PIN[1], 'header_hex': APPLICATION_HEADER.hex(),
        'decompressed_body_bytes': BODY_BYTES, 'decompressed_body_sha256': BODY_SHA256,
        'method_assertions': assertions,
        'compatibility': {'method_index': 13017, 'method': 'DismissTankmanDialog.as_tankMan',
            'code_offset_in_body': METHOD_OFFSET, 'code_bytes': METHOD_BYTES,
            'patch_offset_in_method': 10, 'patch_bytes': 9,
            'original_hex': OLD_PREFIX.hex(), 'replacement_hex': NEW_PREFIX.hex(),
            'original_operation': 'getlex SkillDropModel; getlocal1; callproperty parseFromObject(1)',
            'replacement_operation': 'getlocal1; coerce SkillDropModel; five NOPs',
            'getlocal0_before_and_setproperty_model_after_preserved': True,
            'coerce_qname_index': 518, 'coerce_class': 'net.wg.gui.lobby.tankman.SkillDropModel',
            'method_max_stack': 3, 'method_local_count': 2, 'initial_scope_depth': 20,
            'max_scope_depth': 21, 'exceptions': [], 'branch_targets': [9, 48, 63, 126, 133],
            'branch_target_in_replacement': False, 'original_peak_stack': 3, 'replacement_peak_stack': 2,
            'stack_before': 1, 'stack_after': 2,
            'result_method_sha256': RESULT_METHOD_SHA256, 'result_body_sha256': RESULT_BODY_SHA256,
            'requires_genuine_native_typed_model': True, 'tariff_rows_supplied': False,
            'native_factory_and_confirmation_acceptance': 'NOT_RUN'}}


def verify_transformation(original: bytes, transformed: bytes) -> dict:
    """Independent full-byte oracle, without importing the production transform."""
    verify_flash_source(original)
    before, after = swf_body(original), swf_body(transformed)
    start, end = METHOD_OFFSET + 10, METHOD_OFFSET + 19
    require(after[:start] == before[:start] and after[end:] == before[end:]
            and after[start:end] == NEW_PREFIX, 'only exact nine initializer bytes may change')
    require(digest(after) == RESULT_BODY_SHA256
            and digest(after[METHOD_OFFSET:METHOD_OFFSET + METHOD_BYTES]) == RESULT_METHOD_SHA256,
            'transformed body/method digest differs')
    return {'status': 'PASS_P04J_NINE_BYTE_TRANSFORMATION', 'classification': 'VERIFIED_STATIC',
        'source_sha256': digest(original), 'transformed_sha256': digest(transformed),
        'transformed_bytes': len(transformed), 'body_sha256': digest(after),
        'method_sha256': RESULT_METHOD_SHA256, 'changed_body_offsets': list(range(start, end)),
        'all_other_uncompressed_bytes_unchanged': True,
        'original_confirmation_layout_disposal_unchanged': True,
        'no_tariff_rows_or_prices_introduced': True, 'native_typed_model_bridge': 'NOT_RUN',
        'physical_input': 'NOT_RUN'}


def verify_facts(raw_sources, table):
    require(type(raw_sources) is dict and set(raw_sources) == set(SOURCE_PINS), 'exact source set required')
    for name, (size, sha) in SOURCE_PINS.items():
        raw = raw_sources[name]
        require(type(raw) is bytes and len(raw) == size and digest(raw) == sha, 'source pin mismatch: ' + name)
    require(type(table) is dict and all(table.get(k) == v for k, v in AUDIT_OPCODES.items()),
            'opcode subset differs')
    try:
        prior = baseline.verify_facts({n: raw_sources[n] for n in baseline.SOURCE_PINS}, table)
    except baseline.SourceAuditError as error:
        raise SourceAuditError(str(error)) from error
    parsed, codes, assertions = {}, {}, []
    for source, name, line, args, code_sha, expected in ANCHORS:
        if source not in parsed:
            parsed[source] = static.inspect(raw_sources[source], table)
            codes[source] = list(static.records(static.parse_pyc(raw_sources[source])))
        rows = [r for r in parsed[source] if r['qualified_name'] == name]
        records = [r for q, r in codes[source] if q == name]
        require(len(rows) == len(records) == 1, 'ambiguous/missing source record: ' + name)
        row, code = rows[0], records[0]
        require(row['firstlineno'] == line and code['argcount'] == len(args)
                and row['varnames'][:len(args)] == args, 'source signature differs: ' + name)
        require(digest(code['code']) == code_sha, 'source code digest differs: ' + name)
        instructions = {r['offset']: r for r in row['instructions']}
        for offset, (op, value) in expected.items():
            ins = instructions.get(offset)
            require(ins is not None and ins['opname'] == op and ins.get('value', ins.get('arg')) == value,
                    'bytecode semantic anchor differs: ' + name + ':' + str(offset))
        assertions.append({'source_id': 'res/scripts/' + source, 'record': name,
            'source_filename': row['source_filename'], 'firstlineno': line,
            'marshal_offset_plus_pyc_header': code['marshal_offset'] + 8, 'argument_names': args,
            'local_names': row['varnames'], 'code_bytes': len(code['code']),
            'code_sha256': code_sha, 'verified_offsets': sorted(expected)})
    return {'vehicles': prior['vehicles'], 'native_role_ids': prior['native_role_ids'],
        'skills': prior['skills'], 'descriptor': prior['descriptor'], 'dossier': prior['dossier'],
        'commands': {'dismiss': {'id': 306, 'account_method': 'doCmdInt3',
            'arguments_after_request_id_and_command': ['tankman_inventory_id', 0, 0],
            'original_callbacks': ['PersonalCase.dismissTankman(tmanInvID)', 'Barracks.dismissTankman(invID)'],
            'processor': 'TankmanDismiss', 'confirmation': 'DismissTankmanConfirmator(protectedDismissTankman,tankman)',
            'vehicle_validator_enabled': 'tankman.vehicleInvID > 0',
            'cancel_result': 'DialogAbstractConfirmator returns makeError before request',
            'server_authority_required': True}},
        'confirmation': {'original_model': 'net.wg.gui.lobby.tankman.SkillDropModel',
            'original_factory': 'App.utilsManager.flashObject.classFactory.getObject(className, properties)',
            'factory_constructor_arguments': 0, 'factory_requires_declared_properties': True,
            'unconditional_original_price_reader': 'SkillDropModel.parseFromObject reads three dropSkillsCost rows',
            'ordinary_mode': 'no skills and primary qualification < 100',
            'protected_no_skill_control_number': 'str(roleLevel) when roleLevel >= 100',
            'protected_with_skill_control_number': 'str(last skill level)',
            'learned_zero_skill_control_number': '0',
            'validation': 'value equals originalControlNumber AND isValidSyntax',
            'python_as_invalidUserTextS_true_means_valid': True,
            'direct_python_onButtonClick_proves_enabled_button': False,
            'native_button_event_and_factory_bridge': 'NOT_RUN', 'physical_input': 'NOT_RUN'},
        'inventory_deletion': {'item_type': 8, 'descriptor_map': 'compDescr', 'assignment_map': 'vehicle',
            'dictionary_member_removal_value': None, 'dictionary_tuple_d_suffix': 'set difference, not dictionary deletion',
            'vehicle_item_type': 1, 'vehicle_crew_map': 'crew', 'empty_crew_slot': None,
            'crew_list_diff': 'list replacement preserves None slots',
            'sparse_dictionary_ids_supported': True,
            'invalidation': ['ItemsRequester.invalidateCache', 'ItemsRequester._invalidateItems',
                             'InventoryRequester.invalidateItem'],
            'missing_compact_descriptor_returns': None, 'separate_dossier_delete_required': False,
            'authoritative_tombstones_or_id_reuse_rules': 'project policy, not established by client'},
        'economy': {'freeTMenLeft_client_meaning': 'remaining free recruitment operations of this day',
            'historical_dismissal_refund': 'UNKNOWN', 'historical_daily_grant_and_reset': 'UNKNOWN',
            'historical_numeric_paid_tariffs': 'UNKNOWN',
            'test_policy_no_quota_refill_or_id_reuse': 'project rule, not historical server evidence'},
        'baseline_i_assertions': prior['bytecode_assertions'], 'bytecode_assertions': assertions}


def audit_sources(original_root: Path) -> dict:
    try:
        require(isinstance(original_root, Path) and original_root.is_absolute(), 'explicit absolute original root required')
        original_root = static.no_links(original_root).resolve(strict=True)
        require(original_root.is_dir(), 'original directory required')
        raw = {name: pinned_read(static.no_links(original_root / 'res/scripts' / name), pin)
               for name, pin in SOURCE_PINS.items()}
        application = read_application(original_root)
    except (ValueError, OSError, TypeError) as error:
        raise SourceAuditError('original source audit failed: ' + str(error)) from error
    return {'schema_version': 1, 'status': 'PASS_P04J_STATIC_SOURCE_AUDIT', 'classification': 'VERIFIED_STATIC',
        'build': SOURCE_BUILD, 'client_manifest_sha256': SOURCE_MANIFEST,
        'manifest_validation': 'target identity only; selected resources independently pinned',
        'sources': [{'source_id': 'res/scripts/' + n, 'bytes': p[0], 'sha256': p[1]}
                    for n, p in sorted(SOURCE_PINS.items())] + [
                    {'source_id': 'res/packages/gui.pkg!' + APPLICATION_MEMBER,
                     'bytes': APPLICATION_PIN[0], 'sha256': APPLICATION_PIN[1]}],
        'opcode_table': {'reference_bytes': OPCODE_PIN[0], 'reference_sha256': OPCODE_PIN[1],
                         'mode': 'audited CPython2.7.3 opcode subset'},
        'facts': verify_facts(raw, AUDIT_OPCODES), 'flash': verify_flash_source(application),
        'not_run': ['native CMD306', 'native sparse cache deletion', 'native typed model and confirmation',
                    'fresh login', 'server transaction', 'physical input'],
        'unknown': ['historical numeric paid tariffs and reset fractions', 'historical dismissal refund',
                    'daily free recruitment grant/reset parameters', 'original server validation beyond client'],
        'no_client_code_executed': True, 'no_database_or_service_access': True}


def audit(config_path):
    try:
        baseline.audit(config_path)
        config = static.json_value(static.read(static.no_links(config_path), 65536).removeprefix(b'\xef\xbb\xbf'),
                                   depth=12, nodes=1024)
        opcode = pinned_read(static.no_links(Path(config['paths']['local_artifacts_root']) /
                             'vendor/cpython-2.7.3/opcode.py'), OPCODE_PIN)
        table = static.opcode_table(opcode.decode('utf8'))
        require(all(table.get(k) == v for k, v in AUDIT_OPCODES.items()), 'opcode subset differs')
        return audit_sources(Path(config['paths']['original_client_root']))
    except baseline.SourceAuditError as error:
        raise SourceAuditError(str(error)) from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        receipt = write_receipt(audit(args.config), args.out, ROOT)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(1, 'FAIL_P04J_STATIC_SOURCE_AUDIT: ' + str(error) + '\n')
    print(json.dumps(receipt, sort_keys=True))


if __name__ == '__main__':
    main()
