# P02 — поздние пакеты закрытого BaseApp peer

2026-10-05. Отдельная карточка T после принятого switch02/normal007.
Разрешена ночным поручением владельца продолжать текущий Account/Hangar.
Evidence: `local/evidence/20261005-p02-retired-base-replay/`.
Закрыта06:42: native network replay PASS, verifier59 tests/58 independent controls,
full audit и independent audit binding/17negative controls PASS.
Итог: `docs/research/P02_RETIRED_BASE_REPLAY.md`. Normal008 установлен, клиент закрыт.

Цель: на собственном loopback gateway подтвердить отказ реальным datagrams
первого закрытого аккаунта A, пока второй аккаунт B жив в том же EXE.
Проверка не касается арены, экономики, чужих серверов или чужих credentials.

VERIFIED: проверенный клиент переиспользует cipher key внутри EXE, меняя nonce
и endpoints. Gateway retirement guard стоит до decrypt/receive. Unit-тесты
этого порядка прошли в R; настоящий сетевой replay затем выполнен в этой карточке.
Read-only основание: S/data/NEXT_RETIRED_NETWORK_CHECK.md, SHA256
`c2870bfb45899172c9d588723302cb586d93071abbf5507f3399cb7c93f2f134`.

1. Сохранить source/config/profile/DB baseline и полное принятое normal007
   состояние до снятия установки. Существующие backend/client sources,
   verifiers S/R, генераторы, fixtures и настройки заморожены.
2. Использовать тот же уже проверенный сценарий A→B→A, profile002 и credentials.
   Не менять client patch ради увеличения окна теста. Отдельный helper наблюдает
   фактические события свежего native run; ввод пользователя не автоматизирует.
3. Из capture первого A именно этого EXE выбрать реальный tokenless feedback
   и original authenticated logout. Только исходные байты, не выдуманные сообщения.
4. Когда B действительно готов, bind только на освобождённый прежний A endpoint.
   SO_REUSEADDR запрещён. Если порт занят или native условие не выполнено —
   replay NOT_RUN; не подменять source peer и не завершать чужой процесс.
5. Отправить строго3 datagrams: feedback один раз, logout дважды. Destination
   только свой numeric127.0.0.1:20016, source из проверенного текущего capture.
   Требовать действие внутри TTL120s, пока B жив; bounded counts/bytes/time.
   Никаких дополнительных LoginRequests: session_busy раньше retirement не
   доказал бы проверку nonce и являлся бы другим экспериментом.
6. Сохранить полную capture без удаления injected packets. Отдельно явно
   сопоставить3 replay sends→3 ingress records→3 retired_base_peer rejections.
   Каждый исходный/native и injected пакет учесть ровно один раз; derivative
   native-only corpus для frozen S verifier должен иметь полную index/hash
   привязку. Не скрывать FAIL фильтрацией.
7. Проверить сохранение B и возвращение A: три точных Account/stream sets,
   snapshots/PNGs/ресурсы/cache и штатный exit. Совпадение балансов не proof.
8. Независимый verifier + meaningful negative controls. Исходный FAIL сохранять.
   После native close стандартный rollback, ordinary пакет, full manifests/audit,
   два профиля и оригинал прежние. Native не закрывать по внешнему таймеру.

Ограничения: endpoint binding был UNKNOWN до запуска, replay01 подтвердил его;
3 датаграммы не доказывают
неограниченную replay-защиту. TTL/restart/source spoofing остаются отдельными
границами. Ручная приёмка ночью NOT_RUN.
