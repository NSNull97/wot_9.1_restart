# P08C — original #717 lifecycle and result consumers

2026-10-16. **VERIFIED_STATIC** source contract; native countdown, sounds,
capture/result UI and repeated complete battles are **NOT_RUN** on this change.
Owner explicitly deferred overnight manual checks until the morning. This does
not change their status to PASS or authorize merging an unaccepted card.

## Sources and method

Only the configured read-only original `C:/WoT_0.9.1_RU_0717_original` was read.
`tools/py27_static.py` parses bounded Python2 marshal records into ordinary data;
`tools/packed_xml.py` reads packed definitions. No original module was imported,
executed or edited. CPython opcode declaration SHA256:
`acfe212847ecb81ca28bdab976a3caacff3568b45a9e8ca78d6957f9f3ef4884`.

Ignored extraction script and complete selected disassembly:
`local/evidence/20261016-p08c-01/read_source.py` and `source-contract.json`.
Receipt SHA256 `1f489ce9300c3919c607f29e9a23cbbad4f027bbb7bd3436c5eeb8fa71386848`.
Tracked regression reads the originals again:

```powershell
python -B -X utf8 -m unittest tests.test_p08c_native_contract -v
```

| Source under `res/scripts/` | Bytes | SHA256 |
|---|---:|---|
| `common/constants.pyc` | 34396 | `1c07c2e6a956dcfef95c4020954b4ca39efd77844d328cded935307a6515eebd` |
| `common/accountcommands.pyc` | 5534 | `ba439d8badead15bba4f28708c1822630c1d58fe4699bd07d76d99db345dc2fe` |
| `common/streamids.pyc` | 3538 | `737bd163fbba40822e6c8e3493b39a62c944c7af320692c75889679cb4ce3f29` |
| `common/arenatype.pyc` | 12526 | `9b1255ac3cd08f23b429570c229337c80286253b4a97b5bf82c3c6f3744adfa0` |
| `common/battle_results_shared.pyc` | 10802 | `9fc1ef0d8b5593107426bd2308d7f235f162d331268840168fc7536b471e0f6a` |
| `client/clientarena.pyc` | 12823 | `30b21bb0e386b909d162f127b79b86e5da1aeecb65e9c6700b2b50f435dbd455` |
| `client/account_helpers/battleresultscache.pyc` | 6047 | `8f8184063abcdfc750ab3cb577add40096b1127d370be57d604cf5ecb4b17347` |
| `client/avatar.pyc` | 83656 | `c13cd58a4c5d766dfd3c5f47ae7be50c962aee6c7f8cf25b4341322381f21e0e` |
| `client/gui/scaleform/battle.pyc` | 89274 | `aa43bc6b7e1f7ae9e2bba03fa527a9e6ce95a5d41ef23f26785b1490cd6f38de` |
| `client/musiccontroller.pyc` | 10821 | `77b52fd049119c893d64f7385561e835598e64a4337c00a78e81765a75c7a84e` |
| `client/tutorial/control/battle/context.pyc` | 11676 | `3b737bd8a6f362b511e58ad29c20b748ee0b8bffd9f9c2434892e27cae435292` |
| `client/gui/scaleform/daapi/view/lobby/lobbyview.pyc` | 7898 | `6170e0a23b0bacd7c062d2c15452fdd0d03710cd6cb3ecfe447904782f8a2b57` |
| `client/gui/scaleform/daapi/view/battleresultswindow.pyc` | 48269 | `00a48371a2cdd3dccf2a6fc9c91efa786c90ed0b64ea593821ec6a51bf55d788` |
| `entity_defs/avatar.def` | 7450 | `38cf983d6ea1fcaf1bbca25fd18567fed5abc3b2e07fbe14b168f46fa883f74d` |
| `entity_defs/account.def` | 10588 | `883ec72e77675600f245e0f0aea8837e35c2c4bb9e7a5c5d70f3656d9d076674` |
| `arena_defs/05_prohorovka.xml` | 900 | `7a3898a15922ff6b350e0ba91fe5ceab53b916ad1bcfdf1a198002f9d33e863d` |
| `arena_defs/01_karelia.xml` | 864 | `8afc7d150c12b616246260e12158b2126be2872041a38603cbdf0c9a779d6bdb` |

## Arena periods, bases and death

**VERIFIED_STATIC.** `constants.ARENA_PERIOD:294`: WAITING1, PREBATTLE2,
BATTLE3, AFTERBATTLE4. `ARENA_UPDATE:305`: PERIOD3, VEHICLE_KILLED6,
AVATAR_READY7, BASE_POINTS8, BASE_CAPTURED9. `FINISH_REASON:416`:
EXTERMINATION1, BASE2, TIMEOUT3, FAILURE4, TECHNICAL5.

Existing native #717 Avatar `updateArena` method is measured at `0x58`;
its declared arguments are UINT8 updateType, STRING argStr. Existing output
envelope is `selectPlayerEntity13`, `58`, VAR1 payload length, type, short STRING.
The new encoder uses only bounded inert protocol2 literals:

| Update | Original consumer | Literal |
|---|---|---|
| PERIOD3 | `ClientArena.__onPeriodInfoUpdate:297` | `(period,endServerTime,periodLength,additionalInfo)` |
| VEHICLE_KILLED6 | `ClientArena.__onVehicleKilled:324` | `(victimVehicleID,killerVehicleID,reason)` |
| BASE_POINTS8 | `ClientArena.__onBasePointsUpdate:344` | `(team,baseID,points,capturingStopped)` |
| BASE_CAPTURED9 | `ClientArena.__onBaseCaptured:350` | `(team,baseID)` |

`Battle.__setArenaTime:841` subtracts native `BigWorld.serverTime()` from the
period deadline. PREBATTLE shows the original countdown/sound, BATTLE hides
that panel and starts the ordinary timer; Avatar also plays original start
notifications. Clock anchor/frequency already established by P02 remain
native game seconds100/frequency10; no client clock replacement is needed.

AFTERBATTLE additionalInfo must contain `(winnerTeam,finishReason)`.
`MusicController.__onArenaStateChanged:204`, offsets162–172, unconditionally
indexes additionalInfo0 and selects victory/draw/defeat music. Passing None
would throw. `ExtendedBattleClientCtx.fetch:145`, offsets124–151, names index0
`winnerTeam` and index1 `finishReason`. Winner0 denotes a draw. These are direct
consumer facts, not an inferred modern protocol.

`ClientArena.__onVehicleKilled` sets roster `isAlive=False` and fires its event.
Existing HP property, `Vehicle.onHealthChanged`, owner `updateVehicleHealth`
and bounded postmortem bind remain the source of destruction/camera state.
The new arena kill update supplements them. Native `Avatar.onRoundFinished:1734`
only logs; invoking it alone would not implement results or finish behavior.

The Prohorovka definition sets roundLength900 and CTF base XZ positions:
team1 `[-125.10002136230469,448.30010986328125]`,
team2 `[51.59999084472656,-447]`. Both base IDs are1: original
`ArenaType.__readTeamBasePositions:491` parses `int(subsection.name[8:])`, so
`position1` is stored under ID1 without subtracting1. Capture radius/rate and damage reset rules were
not recovered from this client: any server values remain explicit test policy.
The existing shared lab roster and own Avatar cell both hardcode team1 and must
be assigned consistently when integrating opposed teams. A server winner with
an unchanged allied native roster is not a complete lifecycle implementation.

## Result stream and original UI

**VERIFIED_STATIC.** `streamIDs.STREAM_ID_AVATAR_BATTLE_RESULS` is100 (the spelling
is original). `Avatar.receiveBattleResults:2545` decompresses zlib, reads the
compact protocol2 value, saves the account cache, fires
`onBattleResultsReceived(True,convertToFullForm(results))`, then calls
`base.confirmBattleResultsReceiving()`.

Compact result:

1. Arena unique ID, a signed INT64-compatible value. No u32 truncation.
2. Personal `VEH_FULL_RESULTS` list, exactly81 fields in #717 order.
3. A protocol2 STRING containing another pickle:
   `(common9, playersByAccountDBID, vehiclesByVehicleEntityID)`.

Public vehicle list41 = cell-public36 + base-public5. Personal81 adds
cell-private3 + base-private5 + full-update28 + full-private4. The tracked static
test compares every emitted field name/order with the actual original marshal
constants; an abbreviated modern dictionary is incompatible.

`COMMON_RESULTS` order: arenaTypeID, arenaCreateTime, winnerTeam, finishReason,
duration, bonusType, guiType, vehLockMode, sortieDivision. `PLAYER_INFO`:
name, clanDBID, clanAbbrev, prebattleID, team, igrType. TRAINING bonus/gui2 is
the existing explicit project mode; no reward economy is inferred.

`BattleResultsCache.convertToFullForm:176` directly indexes every list slot.
`details` is packed `VehicleInteractionDetails`, not a Python dictionary. Empty
bytes produce empty interaction details. Original result UI expects list pairs
for autoLoadCost, autoEquipCost and histAmmoCost, empty list medals/dossierPopUps,
and a dictionary for questsProgress. Premium/daily/IGR/AOGAS factors10 represent
neutral multipliers; zero credits/XP and free repair are explicit test policy.
Unsupported ancillary statistics and empty per-enemy details are disclosed
limitations, not verified historical results.

`Battle.__showFinalStatsResults:813`, called by the result event, sets
`g_battleContext.lastArenaUniqueID` and invokes original `onExitBattle` for an
active vehicle. `LobbyView.__showBattleResults:164` opens SHOW_BATTLE_RESULTS
from that retained arena ID and clears it. Thus a server Account reset before
the result callback can omit the original UI path.

Account cache fetch: `BattleResultsCache.get:64` sends
`_doCmdInt3(CMD_REQ_BATTLE_RESULTS1500, arenaID,0,0,callback)`. `__onGetResponse:87`
expects RES_STREAM1 and subscribes using the request ID. Stream completion
saves/converts the same compact payload and sends CMD_BATTLE_RESULTS_RECEIVED1501
with the received arena ID and zero reserved args. Its no-response requestID202
is `STREAM_ID_ACCOUNT_CMDS_MIN200 +2`. Native Account/Avatar
doCmdInt3 definitions declare Arg3 INT64. Retain owner/battle binding, immutable
results and explicit unavailable replies for absent/foreign results; never trust
the requested arena ID as authorization.

**INFERRED.** Zero-argument exposed Avatar
`confirmBattleResultsReceiving` is candidate VAR2 `[0x87,0,0]`: original stable
fixed-size order between measured setClientReady0x86 and vehicle_shoot0x88.
Its declaration/zero arguments are verified; its actual native packet must be
confirmed by the owner trace. Scope acceptance to the owned pending result and
handle original result-induced leave before/after this acknowledgement.

## Implementation and verification scope

`server/gateway/src/shared/lifecycle_wire.rs` owns these encoders and validated
presentation DTOs. It reuses the existing bounded hangar resource stream codec,
including zlib framing/checksums and ≤512-byte reliable bodies. Avatar uses
stream100; Account uses its positive request ID with an existing RES_STREAM
response prefix. No incoming PYTHON decoder or original client code is executed.

Five static tests PASS against the original hashes. Rust target command:

```powershell
python -B -X utf8 server/build.py gateway --test --test-filter lifecycle_wire --out local/build/server/gateway-p08c-wire04
```

The first target build `gateway-p08c-wire01` failed because serde's derive feature
is not enabled in the existing dependency set. Replaced derives with manual
strict serializers/deserializers; no dependency change. DTO deserialization
rejects duplicate/unknown fields and limits participant count to6; input file or
HTTP body limits remain the caller's responsibility. Native gates remain NOT_RUN.
Target02 caught a macro delimiter error, corrected before03. Target03 compiled
the lifecycle encoder and then stopped on temporarily incomplete concurrent
integration match arms for `RejectedBattlePeriod`; Rust tests were NOT_RUN there.
Target04: **4 Rust tests PASS, zero ignored, build PASS**. Independent inert
reader checks complete compact tuple,81/41/9/6 list sizes, original container
types and actual sample HP/damage/killer/team values; strict JSON DTO tests cover
unknown/duplicate fields and participant count. Source/test binding and logs:
`local/evidence/20261016-p08c-01/protocol-checks01.json` and
`local/build/server/gateway-p08c-wire04/`. Executable SHA256:
`f134a0605fcf69f089a43d78e9381cb8b437c54afc11f9534f904faa1fd6486c`.
