# P08C — authoritative cycle and durable native results

Дата: 2026-10-16. IMPLEMENTED_CANDIDATE; native/UI/audio NOT_RUN до утра.
Ветка codex/p08c-battle-lifecycle зависит от P08B c7999e6 по прямому ночному
разрешению владельца. Main не изменён. Source facts —
[P08C_NATIVE_LIFECYCLE](P08C_NATIVE_LIFECYCLE.md).

## Реализация и явная test_lab policy

`shared/lifecycle.rs` не получает native IDs/client clocks/HP/positions: только
committed server actors/poses/damage epochs. Цикл включён в profile13; старые
laboratory modes сохраняют accepted drive route без него.

- Waiting ограничено90с; все ready → prebattle30с → battle900с → afterbattle8с.
  900с и base coordinates взяты из #717; остальные интервалы — test_lab policy.
- Team=slot%2+1, native own-team/roster согласованы. Две прежние стартовые полосы
  сохранены для короткого стенда; исторический spawn не утверждается.
- Capture original baseID1, центры team1(-125.100021,448.300110),
  team2(51.599991,-447). Radius50м,1point/sec/capturer, до3. Defender в зоне
  останавливает progress; пустая зона/новый урон capturer сбрасывают team progress.
  Один reset credit получает последний damager первого damaged capturer.
  Это документированное приближение, не восстановленный исторический сервер.
- Исход заморожен: elimination, technical forfeit, capture100, timeout draw;
  такой же порядок событий committed кадра. Одновременные100 дают draw.
  Обрыв живого танка не подменяется уничтожением: native finish5 technical.
- До/после Battle Move/Fire не применяются и БК не расходуется; aim/leave доступны.
  После исхода поздние projectile/HP изменения запрещены. Погибший остаётся
  в исходном native postmortem пути. Scene ACK transaction не обходится новым
  lifecycle state: staged clone не перезапишет уже замороженный исход.

## Durable result и native return

Natural finish требует bounded results_json. Тот же SQLite writer одной
транзакцией сохраняет full result, AP/HP, освобождение машины, projection,
finish ledger. Failpoints откатывают весь набор. Replay сверяет реальный result
row, не возвращает fake success по одной квитанции. Credits/XP0 и free repair —
прежняя test_lab policy. Старые manual/cancel/disconnect/restart P08B сохранены.

Фактические shots/hits/piercings/damage/kills/HP/lifetime/mileage/capture берутся
из server World до detach. Avatar stream100 ставится после durable finish;
Account reset ждёт scoped confirm0x87. Точный повтор идемпотентен. Original handler
может отправить Leave и confirm в одном compound; валидируется весь кадр.
Confirm ID пока INFERRED по pinned method ordering, native доставка NOT_RUN.
Через30с без подтверждения закрывается только эта сессия, durable result остаётся.

Account1500/1501 чисто ставятся в cloned receive, HTTP запускается после commit.
Fixed private endpoint коррелирует owner/nativeID/key/arena и INT64 arena string
без Node rounding. Новый Account epoch не получает старый callback. Очереди,
workers, JSON и native streams ограничены; прежние service budgets не расширены.

## Выполнено

Static #717 contract5 PASS (marshal/dis без исполнения клиента); lifecycle
integration16 PASS/build (`gateway-p08c-integration02`); result manager/HTTPbudget6
PASS/build (`gateway-p08c-results01`). Writer10 PASS/0skip, прежний P08B writer18
PASS/0skip, настоящий новый/старый HTTP→Python→SQLite PASS; vectors6 PASS/0skip.
Логи — `local/evidence/20261016-p08c-*`, сборки — `local/build/server/`.

`tests/fixtures/profile13-results-vectors.json`: actual fresh SQLite finish,
immediate query, ack; 5612bytes/SHA
793935ad298facc6dd68c49f56f0b4dc2cb0f28749aa14f2451f4b3ba70cc635.
Входная статистика synthetic bounded, ответы настоящего writer; это не nativeplay.
Промежуточные FAIL сохранены. Итоговый full/current-source gate будет записан
отдельно; предыдущие targets не проверяют более поздние изменения интеграции.

## Утро, ограничения, откат

NOT_RUN: original countdown/audio/capture panel/postmortem/results, победа/ничья,
повторные полные бои. Ancillary metrics/medals/quests пусты по test policy;
полная экономика и исторические capture/RNG не восстановлены.
P05C mixed/Nactors, P07B visibility, P06T families не входят в P08C.
Утром проверить countdown30, ручной выход/technical outcome, уничтожение,
capture, natural results→hangar→repeat, отдельно900с draw либо явный fast test.
Откат — commits/ветка P08C, pre-card SQLite backup, client install ledger.
