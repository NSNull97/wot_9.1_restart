# P10B — original #717 training-room contract

2026-10-16. **VERIFIED_STATIC** for the bytecode/definition facts below;
**INFERRED** for new numeric method IDs derived from the method-order model.
Native room creation, callbacks, UI, start, return and isolation are **NOT_RUN**.
This is research for roadmap item8, after P08C/P05C/P07B/P04M/P06T; it does not
activate P10B or implement a room in another interface.

## Scope, source pins and evidence

Read only `C:/WoT_0.9.1_RU_0717_original`. The original modules were not imported,
executed, edited or installed into another client. The bounded marshal reader
`tools/py27_static.py` produced ordinary data/disassembly; packed definitions
were read by `tools/packed_xml.py`. Historical opcode declarations are pinned
to SHA256 `acfe212847ecb81ca28bdab976a3caacff3568b45a9e8ca78d6957f9f3ef4884`.
No external servers or accounts were used. No native process was started.

Ignored evidence root: `local/evidence/20261016-p10b-01/`.

| Receipt | Bytes | SHA256 |
|---|---:|---|
| `source-contract.json` — 21 source entries | 3199141 | `0437c033a8523c59d48d97d1709e1985c6416cdf4b1119f0a6dd005eca75ea3e` |
| `source-supplement.json` — 6 entries, including the same Account | 588014 | `12152c3068b2a4ade52cde750891ed095a7da215889701b4805abe9944673869` |
| `facts.json` — constants and Account method-order candidates | 450959 | `da2fc31965e8db54edf23917e68b4db69f6310051a216a60c367caeed0a353bc` |
| `source-checks03.json` — 27 pinned entries / 26 unique files; 26 bytecode assertions | 21228 | `480421eb3e660fa7fa98ad495f878b7361f3e48a45364a9ecedf8ef5be2376cb` |
| `pe-framing.json` — three bounded original PE windows | 25377 | `abfcfd16ab21bf4c5bf072f00d62106c28d88a919c38a1f5a28d80e2f9d98213` |
| `pe-framing02.json` — extended-length dispatch and receive | 45324 | `3b75a09fd736fa33b885df37d290b8d3a04bb6e5990204d889aa40c1772dcdef` |
| `pe-framing03.json` — extended-length send | 12376 | `fcf78d94ea8ed70c29aa71eb48a1c0e6b2b191b3226855ed938b25035e06ccf1` |

The first `source-checks.json` had an incorrect displayed assertion count27;
`source-checks02.json` corrects that accounting to25. `source-checks03.json`
records every assertion explicitly and adds the ten-field preview assertion.
All source entries with exact hashes are in the receipts.
Principal pins, relative to original `res/scripts/`:

| Source | Bytes | SHA256 |
|---|---:|---|
| `client/account.pyc` | 45998 | `bb6e88e4aec03161212847ffc3601d16917610b8f7815c42f91f610693f4d0ef` |
| `client/clientprebattle.pyc` | 6155 | `c74fc3070d15fb7099e2fba95f955483b09df174596d9f6d118db0956ab9decb` |
| `common/prebattle_shared.pyc` | 7340 | `8604de7b52ec6e615698bd3f95ccc8010681ac15c4f8c31c168b7f6580d446c1` |
| `common/accountcommands.pyc` | 5534 | `ba439d8badead15bba4f28708c1822630c1d58fe4699bd07d76d99db345dc2fe` |
| `common/constants.pyc` | 34396 | `1c07c2e6a956dcfef95c4020954b4ca39efd77844d328cded935307a6515eebd` |
| `client/gui/prb_control/functional/training.pyc` | 14787 | `7f3108df25ec269442596e292753b0014c88bcc54f9d60e6e77558764c4eb4bf` |
| `client/gui/prb_control/functional/default.pyc` | 32735 | `5f0dfde838e96f20775326281fa42fc696d33443a25dbc67e8f7fe527a4361c0` |
| `client/gui/prb_control/settings.pyc` | 11928 | `4df22b924ec40cf1a435fd765216fbcf4f95caeb93d66db2dba1f14f3a4bf2c2` |
| `client/gui/prb_control/restrictions/permissions.pyc` | 14399 | `1e2e478f19d41e1f54d2d9bba8db953bcb66660012648e13d2e086f4dae8ec0e` |
| `client/gui/prb_control/restrictions/limits.pyc` | 11655 | `674f0e2286d85f63813b205c762591f087aefcea47bcba58847039216f88b215` |
| `client/gui/prb_control/context/prb_ctx.pyc` | 27746 | `285f6f45006466284c0624dfee18c21e7797407379e7c98096915fc03e338be9` |
| `client/gui/prb_control/items/prb_seqs.pyc` | 5553 | `716e9c4cc954296f243c1e6196468c545287f71a38e4c7a0a84ec43b697d5957` |
| `client/gui/scaleform/daapi/view/lobby/trainings/trainingroom.pyc` | 18298 | `a0647da875489f330281d614d24cddc9d8c08b79245e0064c47fd2b4a57f3970` |
| `client/gui/scaleform/daapi/view/lobby/trainings/trainingsettingswindow.pyc` | 5308 | `5e6782ff109480cf65d481e8d4f25a5d8db68d22179eacee45b869e5ec8c85a8` |
| `entity_defs/account.def` | 10588 | `883ec72e77675600f245e0f0aea8837e35c2c4bb9e7a5c5d70f3656d9d076674` |
| `entity_defs/prebattle.def` | 1920 | `115d555f1d13aa720c8ed4ee2240ef704788695614f1bd51671ae11c4e8a9dd8` |
| `entity_defs/alias.xml` | 5987 | `14d5fcce8d979de6c24c50b3ff94d3ddf464f4ad27f2ef68c063407b4bbbc746` |

Original EXE SHA256:
`86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed`.
Static x86 windows `0xdd0880`, `0xee3480`, `0xee3660` reproduce the established
fixed-size / one-byte variable client-method framing boundary. They do not
measure a running Account table or turn an uncalled method index into a native
observation. Previously measured ranges start client methods at0x3b and Base
methods at0x86. See [P02_ACCOUNT_READY](P02_ACCOUNT_READY.md) and the preserved
`local/evidence/20261005-p02-map-drive/wire/CONTRACT-02.md`.

## Account carries the native room

**VERIFIED_STATIC.** `Account.PlayerAccount.onPrebattleJoined:481` constructs
`ClientPrebattle.ClientPrebattle(prebattleID)` and emits `events.onPrebattleJoined`.
`ClientPrebattle` is a Python state holder, not a native BigWorld player entity.
`Account.updatePrebattle:686` forwards updates only when `self.prebattle` exists.
Therefore Joined must precede room updates; an update sent first is dropped.
`onPrebattleLeft:494` and `onKickedFromPrebattle:552` clear the holder and fire the
corresponding events.

`Prebattle.def` describes server-side internal room methods, including MAILBOX
arguments and non-exposed `setPlayerReady`, `changePlayerRoster`, `setTeamReady`.
It is not a list of messages sent directly by the native training-room UI.
The UI uses exposed **Account** methods and ordinary Account callbacks below.
No `Prebattle` client entity type ID is needed for the observed Python path.
This does not establish the architecture of the unavailable original server.

## Incoming commands and callback arity

**VERIFIED_STATIC.** Account lines962–1248 establish these exact calls. Integer
triples use the already native-verified `doCmdInt3`0x8e, VAR2 with
`INT16 requestID, INT16 command, INT64 arg1, INT32 arg2, INT32 arg3` (20 payload
bytes). Do not truncate room/Account IDs to a narrower type during parsing.

| Action | Original call / line | Command | Arguments after command | Reply |
|---|---|---:|---|---|
| Create training | `prb_createTraining:962 → base.createTraining` | dedicated RPC | arenaTypeID INT32, roundLength INT32, isOpened BOOL, comment STRING | Joined or JoinFailure; no request callback |
| Join | `prb_join:1027` | 400 | roomID,0,0 | requestID202; Joined or JoinFailure |
| Leave | `prb_leave:1039` | 401 | 0,0,0 | plain response + room-left event |
| Ready / selected tank | `prb_ready:1052` | 402 | own vehicle inventory ID,0,0 | plain response |
| Not ready | `prb_notReady:1065` | 403 | PREBATTLE_ACCOUNT_STATE,0,0 | plain response |
| Assign side/bench | `prb_assign:1085` | 404 | Account entity ID,encoded roster,0 | plain response |
| Swap teams | `prb_swapTeams:1097` | 405 | 0,0,0 | plain response |
| Change map | `prb_changeArena:1110` | 406 | arenaTypeID,0,0 | plain response |
| Change duration | `prb_changeRoundLength:1123` | 407 | seconds,0,0 | plain response |
| Open/closed | `prb_changeOpenStatus:1137` | 408 | boolean converted to0/1,0,0 | plain response |
| Comment | `prb_changeComment:1150` | 409 | `doCmdStr` with comment STRING | plain response |
| Arena voice | `prb_changeArenaVoip:1165` | 410 | channel mask,0,0 | plain response |
| Team ready / start | `prb_teamReady:1182` | 411 | team,force converted to0/1,0 | plain response |
| Team not ready | `prb_teamNotReady:1204` | 412 | team,0,0 | plain response |
| Kick | `prb_kick:1217` | 414 | Account entity ID,0,0 | plain response |
| Accept / decline invite | `prb_acceptInvite:1008` / `prb_declineInvite:1017` | 417 / 418 | roomID,peripheryID,0 | requestID202; no request callback |

`REQUEST_ID_NO_RESPONSE = STREAM_ID_ACCOUNT_CMDS_MIN200 +2 =202`. Commands with
callbacks use Account's incrementing request counter (`__getRequestID:1509`),
starting above reserved minimum220 and wrapping within the original range.
The server must correlate the received ID, not assume one hardcoded ID per
action. Account entity ID (`accID`) differs from account database ID (`dbID`);
team assignment targets the former, permissions are keyed by the latter.

`TrainingSettingsWindow.updateTrainingRoom:109`, offsets28–35, multiplies the UI
duration by60 before `setRoundLen`. The wire and settings duration is seconds.
The private checkbox is inverted before `setOpened`; it is not a password field.

Every listed prb callback lambda takes exactly
`(requestID,resultID,errorStr)`. `prb_teamReady` forwards resultID **and** errorStr;
other proxies normally forward resultID alone. `Account.onCmdResponse:291`
calls the stored callback with3 arguments at bytecode offset45.
`onCmdResponseExt:302` calls it with4 at offset109. An empty Ext dictionary does
not fix the arity: replying through existing Ext0x4d would raise TypeError.
RES_SUCCESS0, RES_FAILURE-1, RES_WRONG_ARGS-2, RES_COOLDOWN-5 and
RES_NOT_AVAILABLE-10 are declared original result codes. Exact original server
error choices for each denial remain UNKNOWN; do not label a refusal success.

## Numeric method candidates and framing

`facts.py` reads original Account plus inherited Chat/AccountEditor/TransactionUser
definitions and alias widths, then applies the established stable ordering:
fixed payloads ascending by size, followed by variable methods in declaration
order. The existing measured doCmdInt3 and Ext indices agree. New entries below
are **INFERRED numeric candidates**, not measured P10B packets.

| Direction | Method | Slot | Message | Shape / native framing |
|---|---|---:|---:|---|
| server→Account | onPrebattleLeft | 1 | 0x3c | fixed0; no length byte |
| server→Account | onPrebattleJoinFailure | 7 | 0x42 | fixed1 UINT8 |
| server→Account | onKickedFromPrebattle | 9 | 0x44 | fixed1 UINT8 |
| server→Account | onPrebattleJoined | 11 | 0x46 | fixed4 OBJECT_ID |
| server→Account | **onCmdResponse** | **17** | **0x4c** | **VAR1**, INT16/INT16/STRING |
| server→Account | onCmdResponseExt | 18 | 0x4d | VAR1, measured previously |
| server→Account | updatePrebattle | 27 | 0x56 | VAR1, UINT8/STRING |
| client→Account Base | doCmdInt3 | 8 | 0x8e | VAR2, fixed20 payload, measured previously |
| client→Account Base | doCmdStr | 15 | 0x95 | VAR2, INT16/INT16/STRING |
| client→Account Base | doCmdInt2Str | 16 | 0x96 | VAR2, INT16/INT16/INT64/INT32/STRING |
| client→Account Base | doCmdIntArr | 17 | 0x97 | VAR2, INT16/INT16/ARRAY<INT32>, measured previously |
| client→Account Base | createTraining | 20 | 0x9a | VAR2, INT32/INT32/BOOL/STRING |

With current player selection0x13, an empty-error plain reply candidate is
`13 4c 05 <requestID:LE16> <resultID:LE16> 00`. Joined candidate is
`13 46 <roomID:LE32>`, without a length field. These are candidate bytes for
a controlled native gate; no successful client processing is claimed here.
Update framing needs its measured client VAR1 format respected. The ordinary
one-byte length encodes payloads0..254;255 is a sentinel, not a usable literal
payload length. Original PE `0xee34f0` routes the sentinel to `0xee37b0` on send;
`0xee3660` routes it to `0xee38c0` on receive. The sender writes all length-field
bytes0xff, saves the payload's original first4 bytes in an appended4-byte tail,
and replaces those first4 bytes with the full little-endian payload length.
The receiver reads that length and restores the original first4 bytes from the
tail. `0xee39c0` traverses packet links when advancing that cursor.

**INFERRED encoder layout:** for payload P of length L≥255, a VAR1 message has
`methodID,ff,LE32(L),P[4:],P[:4]`. This static data flow is not a tested gateway
implementation; packet fragmentation, extension overhead and original native
consumption must receive their own test before use. Replacing VAR1 by VAR2 is
incompatible. A bounded first slice can keep SETTINGS below255, send an initial
ROSTER containing the recipient, then separate PLAYER_ADDED updates for peers.
That smaller-message strategy is a proposed protocol sequence and remains
native NOT_RUN; validate all encoded lengths and preserve complete queueing.

## Exact ClientPrebattle update literals

**VERIFIED_STATIC.** `constants.PREBATTLE_UPDATE:559` dispatches through
`ClientPrebattle.update:161`; the individual consumers call original
`cPickle.loads(argStr)`. Outgoing server data should use a bounded inert
protocol2 literal encoder, with no GLOBAL/REDUCE/object construction.

| Code | Meaning / consumer line | Decoded literal |
|---:|---|---|
| 1 | ROSTER /184 | list of account-info tuples |
| 2 | PLAYER_ADDED /199 | one account-info tuple |
| 3 | PLAYER_REMOVED /210 | `(accID,roster)` |
| 4 | PLAYER_STATE /220 | `(accID,roster,state,vehCompDescr,igrType,clanDBID,clanAbbrev)` |
| 5 | PLAYER_ROSTER /237 | `(accID,previousRoster,newRoster,actorAccID)` |
| 6 | TEAM_STATES /248 | `(team1State,team2State)` |
| 7 | SETTINGS /257 | settings dictionary |
| 8 | SETTING /265 | `(settingName,value)` |
| 9 | KICKED_FROM_QUEUE /293 | argument ignored by this consumer |
| 10 | PROPERTIES /275 | properties value retained by holder |
| 11 | PROPERTY /283 | `(propertyName,value)` |

Account-info tuple is exactly10 fields (`__accInfoAsDict:168`):
`(accID,name,dbID,roster,state,time,vehCompDescr,igrType,clanDBID,clanAbbrev)`.
`vehCompDescr` is the full vehicle descriptor byte string, not its type integer.
`PlayerPrbInfo.getVehicle:74` constructs the original vehicle view from it.
`time` is retained/displayed as server-provided numeric data; exact original
join-time policy has not been recovered.

`prebattle_shared.decodeRoster:16` returns
`(roster &15, not(roster &240))`; `encodeRoster:24` returns
`team | ((not assigned)<<4)`. Native assigned team1/2 are1/2; unassigned team1/2
are17/18. The room's third visible list combines unassigned players. Moving a
player to the bench preserves its low team nibble (`TrainingRoom.changeTeam:187`).
Do not invent a third combat team from the UI's bench.

PREBATTLE_ACCOUNT_STATE: UNKNOWN0, NOT_READY1, AFK3, READY4, IN_BATTLE8,
OFFLINE16. PREBATTLE_TEAM_STATE: NOT_READY1, READY2, LOCKED3.
The holder's team states list is `[None,team1,team2]`.

## Settings, permissions, initialization and actual start

**VERIFIED_STATIC.** `PrbInitFunctional:48` waits for SETTINGS and ROSTER.
The factory then selects `TrainingFunctional` from settings `type=TRAINING2`.
Sending only a Joined callback leaves initialization incomplete. Recommended
initial ordering is Joined, SETTINGS, ROSTER, TEAM_STATES; the exact ordering of
the last three on the original server is UNKNOWN.

`makePrebattleSettings:365` wraps the received dictionary in original
`PrebattleSettings`, whose missing keys fall back to SETTING_DEFAULTS.
Supply explicit `type2`, `arenaGuiType2`, `creator`, `arenaTypeID`,
`roundLength` (seconds), `isOpened`, `comment`, `defaultRoster`, `roles`,
`clanRoles`, `teamRoles`, `limits`, `destroyIfCreatorOut`, `arenaVoipChannels`.
These keys are source names, not a statement that the original server sends
exactly this minimal dictionary. Use disabled voice0 and explicit lab policy
for owner transfer/destruction; do not claim the original server policy.

`limits` must contain integer keys0/1/2; TeamLimits directly indexes each team
dictionary. `minCount` defaults1 per team. `maxCount` has **no** shared fallback:
the assigned/unassigned pair is indexed by `getMaxSizeLimits:227` and MaxCount.
A concrete lab policy may send `limits:{0:{minCount:1,maxCount:(teamCapacity,
benchCapacity)},1:{},2:{}}` and impose a separate authoritative total N cap.
Historical capacity and disconnect deadlines are not established by this audit.

`PrbFunctional.getRoles:423` checks `roles[accountDBID]`, then clanRoles, then
teamRoles. TRAINING_DEFAULT=96; TRAINING_CREATOR=65151 (0xfe7f), formed by the
original PREBATTLE_ROLE:462 bitwise-OR expression. Crucially,
`TrainingPrbPermissions.isCreator:103` tests **equality** with TRAINING_CREATOR,
not bit inclusion. The owner gets that exact mask; other participants get
TRAINING_DEFAULT or a deliberately documented restricted role. UI permissions
never replace server authorization of owner-only actions.

Entering the training room invokes `setPlayerState(True)` and
`prb_ready(currentVehicle.invID)` (`TrainingFunctional.__enterTrainingRoom:396`).
Opening other lobby pages invokes not-ready (`__handleViewLoad:424`); reentering
readies the current selection again. Do not assume a manual ready toggle is the
only source of402/403. On success publish the authoritative selected descriptor
and READY state; validate inventory ownership, crew, ammo, admission and busy
vehicle before acknowledging it.

The native Start button is **not** one custom start RPC.
`TrainingRoom.__doStartTraining:143` sends SetTeamStateCtx(1,True), waits for
success, then SetTeamStateCtx(2,True). Both become CMD411; if team2 fails it sends
SetTeamStateCtx(1,False), i.e. CMD412 rollback. `SetTeamStateCtx` defaults force=True
in this original UI path. `prb_teamReady` sends the force bit; a server must still
validate teams and the authenticated owner's authority. Start only after both
team-ready transitions and all server predicates/reserves commit. Replying to
the first411 by immediately replacing Account with Avatar would interrupt the
second awaited command. Both team READY/LOCKED states affect original controls.

TrainingLimits validates both sides via TeamNoPlayersInBattle and TeamIsValid.
The common `isTeamValid:115` counts only READY players and checks per-team limits.
At least one ready assigned player per side is the default client predicate;
an empty side must fail clearly rather than form an eternal waiting battle.

## Room listing and preview use existing resource streams

**VERIFIED_STATIC.** Every5 seconds TrainingListRequester sends
`requestPrebattles(TRAINING2,CREATE_TIME7,False,0,50)`. Account sends
doCmdIntArr(requestID200,CMD_REQ_PREBATTLES520,[2,7,0,0,50]). Name filtering uses
doCmdInt2Str(requestID200,CMD_REQ_PREBATTLES_BY_CREATOR521,type,idle,creatorMask).
Preview sends doCmdInt3(requestID201,CMD_REQ_PREBATTLE_ROSTER523,roomID,0,0).
Original Account class maps stream200→receivePrebattles and
stream201→receivePrebattleRoster directly, without dynamic request callbacks.

`receivePrebattles:642` expects zlib of pickle
`(prebattleType,totalCount,[(time,roomID,infoDictionary),...])`.
PrbListItem:47 reads integer PREBATTLE_CACHE_KEY entries: ARENA_TYPE_ID11,
CREATOR6, PLAYER_COUNT5, IS_OPENED2, COMMENT9, CREATOR_CLAN_ABBREV15,
DIVISION16, CREATOR_IGR_TYPE17, CREATOR_DB_ID18. Supply usable map, creator,
count and privacy data rather than an empty list that bypasses joining.

`receivePrebattleRoster:658` expects zlib of pickle `(roomID,rosterAsList)`.
`RosterIterator:15`, offset10, requires **ten** preview fields:
`(accID,name,dbID,roster,state,time,vehCompDescr,igrType,clanDBID,clanAbbrev)`;
this matches the in-room tuple. Its local variable name `roster` is reused for
the decoded roster value; reading only the function's varnames can miss that
field, so the exact UNPACK_SEQUENCE10 and stores are checked in the receipt.
Reuse the bounded, checksum-verified gateway resource stream codec; no general
incoming pickle parser is needed for these outgoing payloads.

## Concrete implementation boundary and remaining unknowns

**INFERRED implementation plan.** Keep native protocol IDs in a narrow Account
room adapter. Parse create/list/join/assign/player-ready/team-ready/leave into
domain commands. Maintain server-owned room membership, owner, side assignment,
selected inventory IDs, revision and start state, with one active room/battle
claim per authenticated account. Stage receive mutations before external writer
work, reuse P08B durable reserve and P08C battle/results transport, and publish
native callbacks only after successful authoritative transitions. N must remain
bounded by the current tested physics/admission capability.

On create/join, bind membership then emit Joined/settings/roster/team states.
For a second player publish PLAYER_ADDED to existing members. On assignment
publish PLAYER_ROSTER; on ready publish PLAYER_STATE with the real descriptor.
Keep the two-phase native Start conversation alive until both callbacks have
been queued; atomically claim all admitted participants before Account→Avatar.
Leave/kick/disconnect must free membership and any start reservation exactly
once, with actual Left/Kicked events and explicit failed callbacks as needed.
These are proposed server rules, not recovered original server code.

**UNKNOWN / NOT_RUN:** new numeric IDs against original dispatch; original
ordering of success callback vs roster/event updates; native extended-length
in-room payload transport; exact room persistence/return after battle and reconnect; native
invite/periphery behavior, creator disconnect policy and start/cancel races.
The bytecode establishes the original UI's consumers, not original server
implementation or actual correctness of a replacement. P10B must not be marked
accepted from this audit or from a separate web room.

## Verification, rollback and next step

Executed source extraction, 26 exact bytecode checks, all27 source pin checks,
method-order derivation and the bounded PE reads. **PASS_STATIC**. No Rust build,
server/client launch, native callback/UI test or heavy physics task was run.
Research commands (new evidence directory is required for an append-only rerun):

```powershell
python -B -X utf8 local/evidence/20261016-p10b-01/read_source.py
python -B -X utf8 local/evidence/20261016-p10b-01/supplement.py
python -B -X utf8 local/evidence/20261016-p10b-01/facts.py
python -B -X utf8 local/evidence/20261016-p10b-01/verify_source.py
python -B -X utf8 local/evidence/20261016-p10b-01/read_pe.py
```

Changed tracked file: this report only. Ignored source bytes/disassembly stay
under local evidence. Rollback: remove this report; no runtime behavior changes.
Acceptance: **P10B NOT_RUN / research only**. Single next step when P10B becomes
active: implement the bounded native Account adapter with these source guards,
then measure one controlled create/join/start/leave trace including plain0x4c.

## Fresh original recheck and narrow short-message path

2026-10-16, second read-only pass while P06T is active. This addendum changes
research only. Freshly rehashed **26 original source files**, inspected **38
methods /18 exact bytecode assertions**, and checked **17 original PE
instructions** for method ordering. A second source check adds **5 UI methods
/6 assertions**. The generic envelope proof freshly checks **54 PE instructions
and10 pointers**, including the entityMethod range59..157 (base0x3b).
The original modules were not imported or executed. No gateway build or client
process was started for this pass.

Ignored evidence `local/evidence/20261016-p10b-02/`:

| File | SHA256 |
|---|---|
| `audit.py` | `423287906644038fac1d9bcc923e65e825811e347fb1d28401d4f8b8384dbd20` |
| `result.json` | `a64db23d1997d3e8c7f278a647c11dbfff3856332691cb30770884467c143e0a` |
| `literal-candidates.json` | `b107e7d1d66c6d5b18289db8752a2a77ea84dda6af964afe2bd73b5698356fe3` |
| `source-extra.json` | `a633e2f6b663628f8ef24c48211806356090e0f543f4dea3d024c72f708f5350` |
| `generic-envelope.json` | `1b65f33f4964359f7ef99849eeb8a4c302f20c50c0f8407ff23fc021779164c0` |

**VERIFIED_STATIC ordering mechanism.** Original0xdc9970 invokes the method
table assignment0xdd2b70; that routine sorts the exposed index vector and
calls0xdd1890, which stores each resulting index at MethodDescription+0x4c.
The comparator obtains the stream size from0xdd0880: fixed sizes are
nonnegative, variable sizes return-1. Insertion0xdd3100 uses a strict
comparison and stops on equality; merge0xdd3310 selects its left run when the
two keys compare equal. Thus equal variable methods keep declaration order.
The fresh Account/interface definitions put plain `onCmdResponse` immediately
before Ext in that group. Result: **slot17 /0x4c /VAR1**, with exactly
`INT16,INT16,STRING`. Ext remains slot18 /0x4d. The three-argument callback and
four-argument Ext callback were independently rechecked in original bytecode.

The numeric0x4c is therefore a strong **INFERRED static derivation** tied to the
original definition and native sorting code. It still has no P10B native packet
observation: the roadmap's "not measured" qualification remains true. Do not
replace the plain reply by Ext or claim the UI accepted it from this evidence.
The same fresh derivation reproduces dedicated Base `createTraining`0x9a with
`INT32,INT32,BOOL,STRING`. The packed BOOL token's lossless XML representation
is `{"base64":"BOOL"}`; its scalar type name is BOOL, not a variable object.

**VERIFIED_STATIC initialization gates.** `ClientPrebattle.__onSettingsReceived`
replaces its settings dictionary. `__onSettingUpdated` unpacks `(name,value)`
and writes directly into that same dictionary. `PrbInitFunctional` waits for
both SETTINGS and ROSTER before emitting `onPrebattleInited`. Consequently a
concrete **INFERRED** first implementation can queue this entire native sequence
in reliable order:

1. `onPrebattleJoined(roomID)` creates the original Python holder.
2. SETTINGS7 contains only `{'type':2}`.
3. Separate SETTING8 messages populate every required setting before ROSTER.
4. TEAM_STATES6 supplies `(1,1)`.
5. ROSTER1 initially contains the recipient; this closes the init barrier.
6. PLAYER_ADDED2 adds each other member using the complete ten-field tuple.

This makes extended-length VAR1 unnecessary for the first bounded room path.
It is an alternative to the earlier single-SETTINGS recommendation; it is not
an observed original-server ordering. Do not emit ROSTER before the required
settings patches: that would expose incomplete map/permissions/limits to the
original factory and view. Each member's initial stream must be staged as a
whole; queue exhaustion must not commit partial membership initialization.

The candidate emits explicit arenaGuiType, arenaTypeID, roundLength, creator,
creatorDBID, creatorClanDBID, creatorClanAbbrev, creatorIGRType, isOpened,
comment, defaultRoster, roles, clanRoles, teamRoles, limits,
destroyIfCreatorOut, arenaVoipChannels and startIfReady. The last two are0 and
False for the first laboratory policy. Limits are
`{0:{'minCount':1,'maxCount':(3,6)},1:{},2:{}}`; total membership<=6 is enforced
independently by the server. Owner roles are exactly65151, other roles96;
`defaultRoster=17` places new ordinary members on the unassigned bench. These
are explicit proposed laboratory choices, not recovered historical policy.

The memo-free, primitive-only protocol2 candidates include **29 complete
update bodies**. They reject executable pickle opcodes; no general inbound
pickle parser is proposed. With six members, a14-byte stock descriptor and
24 Unicode-codepoint names taking up to96 UTF-8 bytes, maximum update payload
is **154B**, below the ordinary VAR1 ceiling254. Initial SETTINGS payload16B,
largest one-setting patch117B, initial one-member roster154B, peer-added151B,
ready-state39B and team assignment21B. These byte counts are verified for the
authored candidates; original native consumption is **NOT_RUN**. A larger
comment/name/room shape must be rejected or separately encoded and qualified,
not silently cross the255 sentinel.

The96-byte name is a conservative framing stress input, **not** a proposal to
widen authenticated names. Current `account/identity.rs::valid_name` requires
3..24 codepoints and<=48 UTF-8 bytes; `lifecycle_wire.rs` independently rejects
participant names longer than48 bytes. The room must reuse the trusted bounded
Identity name unchanged. A second96-byte-only room identity would fail existing
battle/results contracts. The154B stress ceiling remains conservative for the
actual accepted names.

Additional source constraints matter for the first domain adapter:

- `creator` is a display name, while `creatorDBID` and the `roles` keys use
  database IDs. Assigned-player commands404/414 use Account entity IDs. Native
  roomID arrives as OBJECT_ID/fixed4 in Joined; allocate a positive signed32
  room ID independently of the potentially64-bit battle/journal ID, preserving
  the mapping. Incoming CMD400/523 INT64 arg1 must validate this room namespace.
- `TrainingRoom.__showSettings:316` looks up `ArenaType.g_cache` and later
  dereferences `.name` without a None guard. Accept only qualified source map
  IDs (currently Karelia1 /Prohorovka4), not a mesh ID or arbitrary map number.
- A new member starts NOT_READY1 with empty `vehCompDescr` until actual CMD402
  validates its selected inventory vehicle. `__makeAccountsData:398` calls
  `getVehicle` only when `isVehicleSpecified` is true, and that predicate is
  READY or IN_BATTLE. Thus initial joining needs no fabricated selected tank.
  The size candidates deliberately use the larger14-byte descriptor as a
  worst case. READY4 must carry the actual validated full descriptor.

The narrow production boundary remains native Account create/list/preview/
join/assign/ready/two-stage team-ready/leave, a bounded authoritative room
registry, existing v2 reserve/finish and native Account→Avatar transport.
Start must accept both sequential411 callbacks before the player entity changes;
if the second team's predicate fails, preserve the original412 rollback path.
One ready assigned player per side and N<=6 must be checked on the server even
when `force=True`. Wrong owner, unknown room, busy/reserved vehicle, bad team or
unsupported command must produce a real failure/JoinFailure; no success stub.

**Still UNKNOWN / NOT_RUN:** native0x4c dispatch observation; processing of the
proposed split initial settings sequence; callback/event ordering in the absent
original server; postbattle room retention/rejoin and creator-disconnect policy;
concurrent starts/cancels/joins across actual clients. A room retained by the new
server would need to reinitialize its holder after a new Account is created;
that is an explicit new policy pending implementation, not an original-server
claim. No P10B production file was changed. Existing P06T/Rust sources and the
original client were untouched by this pass.

Executed commands:

```powershell
python -B -X utf8 local/evidence/20261016-p10b-02/audit.py
python -B -X utf8 local/evidence/20261016-p10b-02/extra.py
```

Acceptance remains **research-only /P10B native NOT_RUN**. Rollback is removal of
this addendum and its ignored proof directory. Single next step after P06T is
committed: implement the bounded native room adapter against these closed
contracts, keeping the initial controlled native trace as an outstanding gate.

## 2026-10-16 — promoted bounded foundation

Branch codex/p10b-native-training-room starts after P06T full06/1162PASS/
725sourceexact. Domain, nativecallbacks/init, recipientaliases/current-room
adapter and typed primitive ingress were reviewed/promoted in training/.
The actual hangar::requests_training_with shim composes the unchanged selected
legacy decoder once, preserves native record order and rejects cross-record
callback/stream collisions and late poison atomically. Old Incoming/API/old
modes are unchanged. The route is not activated. Protocol numbers remain
INFERRED/VERIFIED_STATIC as above; no native PRB capture was performed.

Focused01: **51PASS/0FAIL/0ignored/buildPASS**,0.03с tests, exeSHA
6aceeb0557d1b986d2247468043f0660c8fc84fa837e54cee7e77be22a68dcce.
Proof local/evidence/20261016-p10b-foundation01/ and build gateway-p10b-focused01.
Includes actual promoted hangar shim and real transport Window counterexample:
retry same body/seq can carry newer cumulative ACK, therefore ACK does not
prove UI-origin. Explicit current-room-at-receipt handles new authenticated
unscoped commands in current room; peeraliases tombstoned, async jobs retain
room/revision/membership/channel/source/request. Fresh semantically old Leave
may leave current lobby; this is disclosed laboratory policy, not historical.
World teams, frozen selected identity order, wholeSession/Registry publication
transaction, actual readiness/reserve saga and native UI/flow remain NOT_RUN.
