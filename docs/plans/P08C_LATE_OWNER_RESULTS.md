# P08C — итоги для игрока, уже вернувшегося в ангар

Зависимая ветка `codex/p08c-late-owner-results` от P08B checkpoint6289216.
Ночное разрешение владельца до17.10 09:00: продолжать без manual questions;
native/UI/звук/управление остаются NOT_RUN, main не меняется.

OBSERVED: при ручном выходе первого игрока его inventory Finish уже сохранён,
но естественный итог оставшегося игрока не создаёт owner row первого. Связь
резерва теряется с Session, а World может замениться до сборки итогов.
Планы03/04 и original#717 static evidence находятся в ignored night-staging.

1. Сохранить immutable actual admission/release links ≤6 и один final seal
   перед World replacement независимо от текущей Session. Только actual
   Finished completion + отдельный readonly source stamp дают release proof.
   Pending Finish, invented terminal hash или repaired garage не являются proof.
2. Новый versioned conservative append `p08c-late-result-append.v1` в отдельном
   SQLite namespace, fixed private endpoint и strict owner/run/arena/reservation/
   frozen/release SHA. Старый Finish/revision/inventory/depot/rewards/terminal
   не меняется. Old result validators/reply shapes сохраняются через отдельные
   reader facades. Query/actual1501 ack и durable pending rows атомарны;
   idempotence key fenced между old и new ACK ledgers.
3. Допуск только при source-valid идентичных release/final HP, crew, devices,
   fire, per-stack remaining/fired/lost и detonation cause. Изменённый после
   выхода parked actor даёт LATE_ACTOR_STATE_CHANGED, не fabricated result или
   позднее списание с новой машины. All-N escrow/reservation change вне этого
   узкого компонента; limitation сохраняется явно.
4. Bounded serial actual HTTP worker/retries и registry вне Session, отдельный
   trusted Config owner allowlist1..6 согласован с bridge. Disabled owner не
   вызывает бесконечный retry/падение здорового боя. Committed pending discovery
   ≤8/page с key cursor, no ACK-on-query; crash до append/между owner appends
   не восстанавливает ещё не сохранённые owner rows. Fifth seal-link recovery
   table/reconciler здесь не создаётся. Существующие pending rows survive reopen.
5. Native Chat22 notice source primitive fields/shortVAR1 + Account epoch и
   bounded queue staging только под отдельным experimental flag defaultfalse.
   Mapping0x4b INFERRED, фактическая notification/UI/1500 button chain NOT_RUN.
   Нельзя выдавать отправку/transport ACK за native1501 result acknowledgement.
6. Root review frozen candidates, SQLite/HTTP actual positives/negatives/reopen,
   ordinary ammo/crew compatibility, source-backed Rust codec/registry/worker
   regressions. Затем canonical full с raw source before/after и C-temp target,
   commit/report и переход дальше по ночному порядку.

Границы: только project source/new ignored fixtures; original#717 read-only,
old stand/DB/клиенты не менять. Конкретные source/runtime candidates до promotion
NOT_COMPILED. Source proofs/SQL vectors не доказывают native совместимость.

Откат: disable до первой committed late row допустим. После append нельзя
скрывать историю old reader: сохранять новый reader и DB; startup должен
отказать config-off для committed late owners (включая acked). Старую DB
поверх новой не восстанавливать — это вернуло бы потерянный БК. Для runtime
rollback6289216 с такой DB требуется явная совместимая result reader миграция,
а не молчаливая потеря итогов. Единственный следующий шаг — review/promotion04.

Runtime04 frozen receipt da5cc51481b77ebb7934bd1647e1474bca1ac58ad6c5521ca3036fba695bd269:
20files promoted после7rawbaseline checks. Commit332ea1a: canonicalfocused
gateway-p08c-late-focused01 --test-filter late_results --cargo-temp-target,
34PASS/0FAIL/0ignored/buildPASS,729rawsourcebefore/afterexact. Component включает
actual savedSQL DTO/sourceWorld adapter и authored Lifecycle/Session pressure;
actual Runtime→HTTP/SQL/Native ещё NOT_RUN. Evidence20261017-p08c-late-focused01.
Из peer-review исправлены emptyCapture registry leak, globalpage noticecap
starvation и worker-exit barrier доjoin. Writer04 final08 и coherent composition05
пока независимые ignored candidates; card/full gate ещё не завершены.
