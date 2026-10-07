# P03: battle shooting — карточка loadout preparation

Дата: 2026-10-06, Asia/Yekaterinburg.

## Цель этой карточки

Подключить уже проверенный domain-only `battle/loadout.rs` к серверной
подготовке собственной боевой машины. Перед постановкой подготовки в очередь
сервер должен повторно подтвердить authenticated vehicle, установленный
turret/gun, mapping выбранного shell и положительный count. При любой потере
identity, module mapping, capacity или ammunition подготовка отклоняется
fail-closed. Внешний native packet и HUD при этом не меняются.

## Шаги

1. Снять source SHA и canonical gateway baseline в свежий `local/build` output.
2. Добавить отдельный typed battle-preparation projection поверх `loadout::validate`.
   Читать exact SHA profile/compatibility/manifest и native ammo export из
   закреплённого manifest; count брать из profile, modules/capacity из export.
   Legacy authenticated Session остаётся источником доверия: не фабриковать
   `game.account.v1` assertion и не переписывать инфраструктурный adapter.
3. Вызвать projection в ordinary `drive_join` до queue callback/worker и в
   прежнем `queue_arena_preparation` до PREBATTLE enqueue. Привязать результат
   к поколению арены, проверять до native lifecycle, очищать при cancel/return.
   Ошибка или поздний invalid compound не меняют Session/ACK/outbox/fixture.
4. Добавить отрицательные unit/contract проверки для неверного turret, gun,
   shell mapping, count, capacity и identity. Сохранить before/after SHA и
   receipt с командой, тестами и rollback.
5. Собрать canonical gateway в новом output и запустить полный Rust suite.

Финальный isolated output этой карточки —
`local/build/server/gateway-battle-shooting-after-05`; shared legacy compile/test
сохранён в `local/build/server/gateway-battle-shooting-legacy-02`.

## Границы

- Это изолированная доменная связка. Native Avatar loadout/ammo event,
  native decode, fire/reload ACK, consumption, hit/damage и второй игрок здесь
  не принимаются.
- Не печатать count или shell в HUD и не добавлять неизвестный method ID,
  packet envelope либо client command.
- Не перезапускать текущие `supervisor109740`, `identity15772`, `gateway37248`,
  сайт, БД, deployed gateway, pool или клиент. Оригинальный клиент только
  читается.
- Не менять инфраструктурные boundaries и файлы параллельной карточки.

## Приёмка

`PASS_DOMAIN_BATTLE_PREPARATION_LOADOUT` означает: canonical build и полный
Rust suite PASS; valid authenticated MS-1 доходит до typed preparation;
каждый отрицательный mapping/count/identity input отвергается до enqueue;
native compatibility, native ammo visibility и live runtime остаются
`NOT_RUN`.

## Evidence и откат

Ревизия плана после review: первая реализация только для старого PREBATTLE
с hardcoded projection получила `FAIL_ROUTE_REVIEW`, несмотря на 311 PASS.
Её build/evidence сохранены; текущая приёмка требует ordinary route и реальные
profile inputs. Legacy entrypoint также должен включать shared battle module.

Новые receipts и тестовые outputs размещать только под
`local/evidence/20261006-battle-shooting-loadout-route/` и
`local/build/server/gateway-battle-shooting-*`. Откат — удалить новый battle
preparation module, его вызов, этот plan/report и только новые evidence/build
каталоги; восстановить source files по before SHA. Старый frozen capture не
перезаписывать.

## Следующий шаг после PASS

Первый maintenance receipt оказался ошибочно готовым к запуску: отсутствие
`restore.json` у active ordinary install016 было принято за незавершённый
прогон. Неверный receipt сохранён в `rejected-01/`, prior bytes восстановлены,
а текущий audit помечен `NOT_READY_NATIVE_LOADOUT` в
`local/evidence/20261006-battle-shooting-maintenance-preflight-01/`.
Следующий шаг — offline определить настоящий native `AMMO/LOADOUT`
method/serializer/order по закреплённому клиенту и 345-пакетному capture;
owner-driven capture планировать только после этого. Пока wire payload не
декодирован, fire/reload handler не добавлять.
