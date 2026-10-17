# Current gate: P10B private Hold5 selection bridge

Branch codex/p10b-hold-selection-bridge from reviewed CLI63 ed53adde.
Primary200/raw925 remains untouched; own worktree source935 has no full gate.
[Plan](plans/P10B_HOLD_SELECTION_BRIDGE.md). New optional closed private
room_selection_hold_service enables only /internal/native/room-selection-hold.
Real CLI63 plus strict Request9/Stamp11/Reply15/FrozenHold3; existing Hold reader
and writer/startup fences remain in force. No gateway/Config/native flag changes.
Candidate HTTP2 PASS on real C/D setup; committed-source rerun pending.
Native Training+Hold5 remains FORBIDDEN_UNIMPLEMENTED. No main merge/push yet.
Rollback only this additive optional bridge card; never restore/rewrite DBs.
