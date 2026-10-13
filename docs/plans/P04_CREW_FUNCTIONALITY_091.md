# P04 crew — complete original 0.9.1 behavior

Owner expanded the task on2026-10-13 while P04H was in progress: continue
overnight toward the complete historical crew feature set, including perks
and other crew operations. This authorizes successive independently reviewed
cards, not one unbounded branch. Preserve one card/branch/tested no-ff merge.
Manual owner tests are deferred until after2026-10-14 09:00 Asia/Yekaterinburg.
Do not convert an outstanding manual gate into PASS or wake the owner for
routine implementation choices. Continue independent source research and tests.

## Rules and scope

Use only pinned original v.0.9.1 #717 resources/bytecode and historical sources
whose version is established. Keep VERIFIED/OBSERVED/INFERRED/UNKNOWN distinct.
The authoritative server owns roster, qualification, experience, prices,
eligibility and mutations. Retain native dialogs, callbacks and protocol.
No original client writes, P05 changes or unrelated stand deployment.

Owner exceptions to historical behavior:

- New free recruits start at50%; existing100% tankmen keep their qualification.
  Paid choices were deferred at the start of H; their verified historical
  behavior belongs to a later card in this expanded scope.
- Sixth Sense is an always-active base perk requiring no learning, including
  a50% crew. Preserve this explicit exception when implementing skill/perk
  progression and the future combat effect. Its actual detection signal,
  timing and display still require source/protocol verification.
- Ordinary skill selection requires100% primary qualification of the tankman;
  the owner explicitly reiterated this on2026-10-13. Keep this validation in
  both the original UI adapter and the authoritative writer.

## Ordered work and gates

1. Finish current P04H: all primary-role hires on MS-1/IS-7, two distinct
   loaders, retained transfers, durable quota and complete native rosters.
2. Audit the original complete crew operation surface: personal file,
   qualification/retraining, skill learning/reset, dismissal, barracks,
   bulk operations and personalization. Map each original command and dialog
   to source facts, bounded server inputs and explicit unsupported behavior.
3. Choose the next smallest coherent card from that audit; write its contract
   and acceptance before implementation. Repeat this process until all
   requested operations are covered. Do not silently invent missing tariffs,
   experience thresholds, skill effects or recovery rules.
4. For each card run applicable current-source regression and actual native
   callback/wire/persistence verification. Keep immutable failed attempts,
   clean up owned processes/installations and record rollback.
5. Prepare one owner test checklist for the finished interactions after09:00.
   Native automated callback acceptance and manual acceptance remain separate.
   Combat-dependent perk effects cannot be accepted from a hangar icon alone.

Status: IN_PROGRESS. P04H native recruitment and P04I PersonalCase/first-skill
selection and P04J original dismissal are accepted. I proves original CMD151
and persistence at0% skill, not battle XP or combat effects. J proves native
confirmation, sparse retirement, subsequent hire/transfer and fresh login.
Next card: original Barracks recruitment through CMD303, native counts/filters,
free50 policy and monotonic allocation. Qualification/retraining,
reset, paid recruitment, personalization, barracks/bulk operations and combat
effects remain separate outstanding work; no whole-crew PASS is claimed.

## Read-only research prepared for later cards

The owned evidence root `local/evidence/20261013-crew-complete-research-01/`
now contains the following source-bound findings. These are implementation
inputs, not runtime acceptance or permission to invent unresolved parameters.

- `qualification-next/`: original reset/retraining request layouts, retained
  skill/qualification transitions and actual CPython2.7.3 arithmetic checks.
  `tariffs01/` separates historical official indexed leads from unavailable
  source documents; exact served #717 numeric tariff rows remain UNKNOWN.
- `perk-effects-next/`: all24 learnables (15 continuous skills,9 perks),
  source constants, original localized aggregation descriptions and unresolved
  combat semantics. Seven original sources and20 authored arithmetic cases
  on CPython2.7.3 are pinned. Base Sixth Sense18 and inactive woodHunter41
  are excluded from this learned-skill set.
- `sixth-next/`: original own-vehicle misc-status handling invokes the battle
  indicator without checking learned skills or qualification. Source delay3s
  is established; actual wire method, authoritative observation scheduling,
  repeat/death behavior and complete display timing remain unaccepted.
- `next-small-card01/`: proposed next operation after accepted J is original
  Barracks recruitment through CMD303, reusing the owner's free50 policy and
  sparse lifetime allocator. Exact shop revision/callback binding and native
  Barracks proof are prerequisites. ReturnCrew157 is deferred because original
  client reads do not establish authoritative lastCrew update timing.

Current implementation still stores only a first selected skill at0% and no
earned/free crew XP. The requested complete crew system is not complete.
