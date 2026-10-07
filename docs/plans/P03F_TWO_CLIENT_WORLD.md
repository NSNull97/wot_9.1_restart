# P03F — two native clients in one test_lab world

Status: `PASS_NATIVE_SAME_PC_DATA_PLANE_OWNER_CONTROL_PENDING`.
Same-PC native observations and abrupt reconnect recorded; mandatory owner
control confirmation and two-PC repeat remain open. See
[receipt](../evidence-index/P03F.md). Branch stays unmerged.
Base: `3e59991f41d4459bbe571afcec04207ce2c20e12`.
Branch: `codex/p03f-two-client-world`.

## Intended result and limits

Two independently authenticated native #717 clients share a battle ID, server
clock and two distinct allied MS-1 entities. Closing either client stops only
its controller; the other session and world continue. Reconnection uses the
same account's parked entity and server-owned ammunition. The ordinary accepted
single-player map-drive/P03D/P03E routes remain available.

This is an explicitly selected local `test_lab` mode: two temporary server-assigned
MS-1s, bounded kinematic movement, no terrain/contact simulation, enemies,
projectiles, hits, damage, equipment, progression or changes to garage inventory.
The second existing test account has no crew/ammo in its garage. Do not silently
promote that fixture or present a laboratory assignment as owned inventory.
The server waits for two fully authenticated hangars and then enters the lab
automatically. This avoids inventing a new client command or changing Fight UI.
Full P03 and a two-PC repeat stay open until actual evidence exists.

## Inputs and permitted paths

- Canonical source: `server/gateway/src/`, CLI, relevant regression tests/tools.
- Research copy: `D:\WoT_9.1_Server\WoT_0.9.1_RU_0717_research`.
- Original: `D:\WoT_9.1_Server\WoT_0.9.1_RU_0717_original`, read only.
- Evidence, isolated builds/configs and additional independent client copies:
  strictly below `D:\WoT_9.1_Server\local\` with explicit manifests and rollback.
- No deployed binary replacement, database grants, global settings, firewall
  opening, neighbouring projects or remote game-operator connections.

## Execution

1. Record the singleton/session and fixed-entity assumptions. Bind research
   findings to the pinned client/defs and accepted P03D/P03E evidence.
2. Add an opt-in two-session dispatcher. Route handshakes by random handoff and
   encrypted traffic by exclusive bound peer. Bound active sessions, auth jobs,
   retirement capacity, queues and lifetime; preserve credential verification.
3. Add one shared authoritative test world and identity-specific native codecs.
   Validate whole incoming envelopes before applying intents; never use client
   position or time as state. Distinct IDs and per-peer creation/ACK gates.
4. Test wrong peer/key/token, duplicate account/attempt, retirement reservation,
   malformed compound atomicity, ammo/reload separation, shared snapshots and
   disconnect/reconnect isolation. Build canonical and legacy shared sources;
   run source layout and applicable Python checks.
5. Prepare two isolated native runs. Research the actual instance mutex before
   any reversible second-copy compatibility change; preserve hashes/backups.
   Start the server/clients when the concrete stand is ready. Record native
   traces and owner-visible results; no mock/UI acceptance substitution.

## Evidence and assumptions

Evidence root: `local/evidence/20261007-p03f-two-client-world-01/`.
Tracked research receipt: `docs/research/P03F_TWO_CLIENT_WORLD.md`.

VERIFIED: `session.rs` currently has one `Option<Session>` and rejects the second
attempt; drive/vehicle codecs hard-code the primary ID/profile. P03D/P03E have
their own native owner receipts. The original EXE contains `wot_client_mutex`.
OBSERVED: the secondary owned fixture has no crew/ammo; only the existing legacy
gateway process was running at this card's start.
INFERRED: the verified message layouts support two independent entity IDs; this
requires real native reception, not only encoder tests.
UNKNOWN at planning: simultaneous native lifecycle ordering, visual remote-vehicle
update, second-instance/profile isolation and two-PC behavior. The subsequent
[research](../research/P03F_TWO_CLIENT_WORLD.md) records actual run01 failure,
run02 observations and the remaining owner/two-PC boundary.

## Acceptance and rollback

Mandatory: both real clients see two separately owned vehicles in one battle,
server movement is visible in both, one client's closure does not stop the
other, and reconnection does not reset the survivor or grant fresh ammunition.
Capture the native run and owner observations. Pending native acceptance keeps
the card unmerged; successful unit/build checks alone are insufficient.

Stop only this card's recorded PIDs. Restore client/config files from the exact
manifest after checking current hashes; never remove evidence or original client.
Return to the prior accepted isolated build/endpoint. Code rollback is a reviewed
revert on a separate branch; no history rewrite or force push.
