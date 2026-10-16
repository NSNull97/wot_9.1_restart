# P08B — actual restart и warm/full CAS composition

VERIFIED runtime `7ff8b30078b04942d39163116c98b295517f79b3`, отдельная зависимая
ветка `codex/p08b-restart-cas-composition` от BUILD-TEMP7d2252f. Production
поведение не менялось: добавлен ordinary Rust test, Node controller и11 Node
guards. Тест соединяет ранее отдельно проверенные HTTP/writer и Session пути.

Фактически выполнены два отдельных child процесса одного compiled test exe,
loopback port0 bridge, настоящий Config/authenticate/RunOpen, native command
парсер Session, Dispatcher/Job, Python/SQLite и Fresh fixture. Fresh isolated
seed использует существующую explicit test-only100-shell grant policy; игровой
стенд и собственные аккаунты владельца не менялись. Authenticated Session,
ACK и terminalHP0 здесь авторские: native/UI/gameplayUDP/геометрическая гибель
NOT_RUN. Сценарий использует старый AP-only profile13 contract1; аналогичная
полная composition для mixed2/loss4 не выполнялась этим тестом.

Факты SQL и Session:

- AP20 reserve остаётся active после завершения gateway child. Reopen bridge
  сам не меняет ни одной наблюдаемой строки. Новый Config получает новый run
  UUID, фактический RunOpen завершает старый reserve aborted_restart один раз.
- Ammo command unload20→19, новое Admit замораживаетAP19. Authored terminalHP0
  проходит настоящий Finish, repair90 и Account reset/Fresh; consumedAP0.
- Неверный warm100(1) atomically refused; warm100(2) отдаёт точные свежие state
  bytes. Shop/dossier sync завершают Account fullsync с wire1. Следующая actual
  unload19→18 проходит durableCAS один раз, wire1→2.
- Aggregate revision14→21, два settled reserve, active0, loaded18/depotAP+2,
  два native ammo journal rows; ресурсы/crew/research/старые ledger rows сохранены.

Current-head canonical gate:

```powershell
$env:RUST_TEST_THREADS='1'
$env:CARGO_INCREMENTAL='0'
$env:CARGO_PROFILE_DEV_DEBUG='0'
$env:CARGO_PROFILE_TEST_DEBUG='0'
python -B -X utf8 server/build.py gateway --test --cargo-temp-target --out local/build/server/gateway-p08b-composition-full02
node --test web/tests/p08b-composition-guards.test.mjs
```

Full1189PASS/0FAIL/5oldignored/buildPASS,359.74s tests,716rawsourceexact.
Focused04:1PASS/0ignored/buildPASS,47.33s. Node11PASS/0skip, включает actual
обычный/verbatim child invocation. ExeSHA
`1f7c998645b897dc22eca18e0873eacc2d23ed6f8644ffaea3947ac11f7d9b66`.
Evidence `local/evidence/20261017-p08b-composition-full02/source-after.json`,
`composition-full.json` и exact raw source archive; actual composed run
`local/test-runs/p08b-composition02/run-93308-1792177855843798200/result.json`.
Inner receipt PENDING_PARENT_FULL_GATE сохранён неизменным; outer attestation
связывает его с завершившимся полным gate, head/rawmap/testexe SHA.

Full01 и focused02/03 FAIL сохранены: Node main/root/prerequisite пути с
Windows verbatim prefix не совпадали с обычными source URL/service boundaries.
До fix actual entrypoint guard regression10PASS/1FAIL; после11PASS. Исправлена
только обвязка: normalizing обеих сторон main guard, HERE и source arguments.
Production local boundary не ослаблялась, старые FAIL не переписывались.

Приёмка: software composition PASS, P08B manual postrestart/mutation/IS7 gates
остаются NOT_RUN; в main не слито. Откат — checkpoint7d2252f или удаление только
test-only registration/новых файлов; runtime/DB не откатываются. Следующий шаг
ночного порядка — отдельная P08C conservative late-result append ветка.
