# NET-02 — explicit private LAN and repeatable two-PC stand

Ночное разрешение владельца 2026-10-16: отдельная зависимая ветка
`codex/net-02-private-lan` от P10B docshead6c6b7b7/runtimee55ba01.
Предыдущие native gates остаются NOT_RUN; mainffce8cb не изменять.
Порядок: [IMPLEMENTATION_ORDER](../IMPLEMENTATION_ORDER.md), пункт9.

## Цель и границы

Два собственных проверенных клиента #717 подключаются родным Login/Base UDP
к одному явно выбранному частному IPv4 стенду, входят в owned profile13/P10B
комнату/бой и возвращаются с настоящим durable результатом. Служебные HTTP
интерфейсы остаются на127.0.0.1. Родной протокол/транспорт сохраняется;
собственные минимальные auth/address compatibility изменения версионируются.
Не создавать свой сетевой API, копии ресурсов клиента, сайт или экономику.

Первая фаза LANv1: concrete RFC1918 IPv4, Login/Base один host/разные
порты1024..65535, advertisedBase строго Basebind,1..24 exact /32 peers.
Только реальный shared owned profile13+p04m_pool+p06t_mixed_ammo; диагностика
и qualification modes остаются loopback. Стенд дополнительно требует
training_rooms/visibility и client training flag. WAN/NAT/IPv6/relay/public
hosting ещё не поддерживаются и не закрываются этим parser gate.

## Разрешённые пути и исходные доказательства

Только этот репозиторий: identity/network/redirect/shared/session Rust modules,
tools/interactive_client.py, client_patch/project_auth.py/sr_interactive.py/
project_network.py, соответствующие tests/docs. Новые own stand/preparation
только local/stands и local/night-staging, без тяжёлых copies/junction/symlink.
Оригинал C:\WoT_0.9.1_RU_0717_original только read-only; текущие установленные
coreV7 клиенты и их ledger не менять до утренней core приёмки.

Frozen ignored candidates: net02-implementation01 receipt e2ca2ac83368342455c9618c84921e0fe88ea414add77a02e6c7e2733900162c;
net02-client01 receipt460909783b3cfa595022afe9138058a52279cb9e078effefefa5561135989597.
Readonly crossreviewf5343dc6cd9512e691e437f96868269bbde93770f4e81a57f13838f709e155d4.
Rust isolated8PASS; client CPython2.7.3 15PASS/prepare5PASS/3compiled.
Это component evidence, active promotion/full/native ещё NOT_RUN.

## Порядок выполнения

1. Сверить каждый raw baseline и frozen receipt, перенести точные узкие изменения.
   Config streaming visitor обязан видеть nested duplicate keys до Value;
   сохранить4096bytes/top23/HTTP16/fixture64 bounds. Отсутствующая LAN policy
   сохраняет старые loopback paths и exact redirect bytes.
2. Проверить все12 Config loaders и common runtime guards до bind/capture/worker.
   Allowlist до rate/capture/fragments/crypto; aggregate256/s прежний, без
   обещаний fairness. First Base проверяет IP authenticated Login; token/key/
   exact live peer/retirement и серверная авторитетность сохраняются.
3. Клиент: explicit lan-test-v1, exact numeric endpoint, полная modechain;
   original LoginDispatcher/ConnectionManager и submitted-host equality.
   Только public PEM и свои compatibility sources/settings; никакого private
   HTTP/token/DB/fixture в client pack. LAN registrationURL пустой, own accounts
   заранее созданы; original handler возвращается до браузера (sourceverified).
4. Meaningful focused net02_ tests не могут быть нулевыми. Проверить config
   duplicates/budgets/24vs25, real entrypoint refusals, Table firstBase peers и
   независимые redirect literals. CPython/prepare/old auth/network regressions.
   Затем clean committed head, canonical full gateway и source-before/after.
5. Отдельный source/binary/config-bound LAN runner и paired manifest для A/B.
   Не переиспользовать loopback-only room runner или A-local пути наB. Read-only
   actual interface inventory; второй PC/IP пока UNKNOWN. На текущей машине
   интерфейс Public OBSERVED; Private-only rule там не действует. Не менять
   профиль сети/брандмауэр незаметно. Подготовить конкретную own rule/rollback
   после actual адресов; keep HTTP loopback. Сначала допускается own-host
   socket gate, он не доказывает второй PC/native/firewall routing.
6. Утром единый exact2PC сценарий: Login→advertisedBase→Account→room→Ready→
   sides/start→move/aim/fire/visibility→leave/results→hangar/repeat; обрыв до и
   после commit, zero active reserves/точный БК, private TCP unreachable fromB.
   Отдельно фиксировать RTT/retransmission/gaps;6players/audioUI NOT_RUN без
   actual checks. Хостинг/WAN — следующий явный perimeter gate после LAN.

## Приёмка, evidence и откат

VERIFIED — source hashes/primary original static evidence/actual test logs.
OBSERVED — конкретный interface/runtime/socket сценарий. INFERRED — ожидаемая
совместимость до native. UNKNOWN — второйPC/remoteperimeter/WAN. Не объявлять
боевой тест готовым по offline parser/build или local socket success.

Evidence сохранять в local/evidence/20261016-net02-* и fresh build output;
public docs только counters/SHA/commands, без секретов/ресурсов/локальных links.
Перед activation paired manifest проверяет source/exe/config/publicPEM,
server Login==оба client endpoints, Baseadvertisement и actualpeer/32.
Откат: own process receipt stop, только собственная firewall rule/overlay ledger,
whole SQLite backup/durable recovery без удаления reservations. Software:
сохранённый P10B tag p10b-host-20261016-02; source restore guards не обходить.
Обязательный native/twoPC NOT_RUN оставляет карточку в ветке, не main.

Исполнение и фактические ограничения сохранены ниже; checkpoints не подменяют
обязательную native/twoPC приёмку.

## Сохранённый итог реализации

Runtime608bb23/tag net02-private-lan-20261016-01: focused17/build и canonical
full1414/5oldignored/build/794rawexact PASS. Actual ownhost02 Login/Base/Account/
room/две readonlyReady/обаLeave/retire PASS45.391с. NET C44/D45, ammo unchanged,
active0; actualUDP на выбранномIP/HTTP127, ownstop. Source capture4/audit794/
changes0 PASS; applyNOT_RUN. Первый operator30s startup FAIL сохранён; successor
fixed90s завершилactualBOUND30.736с/total42.718с без runtime budget changes.

Публичные исходники только проектные; local helper/evidence/DB/secret/resources
не публиковались. B/IP/category/overlay ещё неизвестны, A Public; paired LAN
plan остаётся UNBOUND, firewall/routing/WAN не менялись. Не повторять consumed
ownhost initial43/44 proof на44/45 и не сбрасывать SQL ради зелёного сценария.
Откат — saved P10Btag, own process receipts/wholeDBbackup/overlayledger.
Карточка не принята: обязательные native/twoPC/hosting NOT_RUN, mainffce8cb.
Единственный следующий шаг приёмки — сохранённый owner coreV7 native сценарий,
затем явные actualB данные и отдельный paired stand после предыдущих native gates.

## Дополнительные независимые проверки после утреннего отчёта

Heartbeat 2026-10-16 разрешает продолжить без ручных вопросов. Новый узкий gate:
отдельный gateway-only ingress стенд с новыми UDP20242/20243 и прежними80refs,
без HTTP bridge, Login/auth и изменения БД. Разрешённый ownIP передаёт только
malformed positive controls; запрещённый source127 и oversize1554/1025 должны
отсутствовать в capture. Перед отрицательным выводом отдельный own canary20244
обязан фактически подтвердить доставку loopback→ownprivateIP. До/после — positive
controls, source794/exe/full proof, bounded time/traffic и receipt-owned stop.
Это дополнительная проверка ingress/observer, не native/twoPC/firstBase-IP gate;
consumed stand43/44 и его guards не переиспользуются и не ослабляются.

Одновременно readonly аудит выявил маршрутную ошибку старой P04M матрицы:
rollback ссылается на PREPARED планы без install ledger. Отдельный successor
supplement должен использовать фактически установленные coreV7 ledgers и
проверенный full02/raw634. Exact восстановление исходников допустимо только
если все634 original raw pins воспроизводимы из Git или существующих retained
bytes; отсутствие материала остаётся BLOCKED/NOT_RUN, fullproof не переписывать.
Frozen инструкции/старые helpers сохраняются; actual overlay rollback, source
apply и native проверки по-прежнему NOT_RUN.
