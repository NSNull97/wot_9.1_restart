# P02 — настоящие поздние BaseApp packets закрытого аккаунта

2026-10-05, карточка T — PASS. Native verifier, final audit и независимый финальный
review завершены PASS. Ручная приёмка NOT_RUN. Область: собственный loopback стенд,
один EXE и существующие аккаунты A→B→A. Арена, экономика и клиентский протокол
не менялись. Backend и все13 клиентских модулей заморожены со времени принятого S.

## Проверенный результат

VERIFIED в replay01: настоящий клиент PID96040 закрыл первый аккаунт A и вошёл
в B. Прежний UDP endpoint127.0.0.1:55682 действительно освободился. Отдельный
host-side инструмент занял именно его эксклюзивно, без SO_REUSEADDR/fallback,
и отправил на свой BaseApp127.0.0.1:20016 ровно3 исходных datagrams первого A
этого же EXE: tokenless feedback16B и original authenticated logout24B дважды.

Все3 попытки дали собственные ingress и точный
`REJECT reason=retired_base_peer policy=RetiredPeerForKey`. Возраст пакетов
относительно первого logout на единой capture clock:5.740/5.834/5.869s, внутри
120s retirement window. B сохранил свой ангар; после отправок появилась новая
ready запись452, позже третьего after-prefix448. Затем клиент штатно вернулся
в A. Три ready интервала:16.1248358 /16.0745999 /16.0902223s, по17 samples.

Полный capture —280 packets/13926B. Явно выделены только3 replay ingress
indices603/605/606 (source packet475 и556×2). Оставшиеся277 packets/13862B
переданы замороженному S verifier как **производное представление анализа**,
не как второй запуск. Полные исходные capture/outcome/ledger/trace не менялись.
Каждому исходному пакету соответствует ровно одна запись native/replay;
все15283B backend span учтены как15112B native +171B трёх точных reject lines.

Независимые auth/Account/streams и snapshots A→B→A: nativeIDs1→2→1,
машины2→1→2,танкисты2→0→2. Три PNG просмотрены и связаны с исходной trace.
Native exit0,0 trace/0 свежих Python errors,12cleanup, capture/restore PASS;
процесс прожил85.9613133s. Игра не закрывалась внешним таймером или kill.

## Инструменты и выполненные проверки

- `tools/retired_base_probe.py` SHA256
  `61b419118eb6d980604ce830aa187abd5406216110eb8d3c87e8fcc9dfcb8720`.
 27unit checks PASS,25 independent sender controls PASS. Перед каждым send
 проверяются actual client/gateway PID, live image, configuration, ранний Bready,
 current-run key/nonce relationship в RAM, исходные bytes и точный old peer.
 Частичная отправка — FAIL; занятый source peer до отправок — NOT_RUN.
- `tools/verify_retired_base_replay.py` SHA256
  `f6503fd5ee353ddd4d9b097a2005480cd3c138aa2711c1ea011a4524859762f3`.
 59unit/native-evidence controls PASS. Требует14 обязательных gates; никакая
 четвёртая отправка, лишний отброшенный пакет/лог, другой reject, иной peer,
 stale/fini/logout B, потерянные bytes или private metadata не засчитываются.
- Новый локальный `T/final_audit.py` проверяет восемь исходных документов,
 trace, partition, derived child/outcome и последующие filesystem/profile
 snapshots. Это отдельная проверка сохранности, не замена wire verifier.
- Независимый GUI review:58/58 controls и полный повтор14gates PASS;
 `T/gui/verifier-review-01/FINDINGS.md`, SHA256
 `333452aa43ca9d5ddf080f0b94761aad6221944f266750bfbd5803e45800e965`.
 Manifest SHA256 `a3890a1f6b702883ca7991cf9db7162d89d91cde6f5eff63e60a62e8fec3623b`.
- Независимый audit review:actual completed native binding PASS,17negative
 controls отвергнуты, включая5 ранее найденных gaps. `T/data/audit-review-02/result.json`,
 SHA256 `6346d05451613a9e2e5b1a5149090692b4972124ce70c38289f3265a83f0e964`.
 Проверенный helper SHA256 `6361d3d9793bb11503fe873142191c4343df98190a39fa08142c4ed9caacd835`.

До запуска найдены и закрыты ошибки самого sender: pin опечатка, недостаточные
границы control metadata, пропуск fini_enter и повторной проверки живого backend.
Они не выдавались за клиентские дефекты. Первый полный verifier-report FAIL:
записанный sender TTL120.0 был ошибочно отвергнут проверщиком, требовавшим int120.
Поправлен finite exact numeric gate с контролями bool/120.1/NaN/infinity;
первый report и исходники сохранены. Native повтор не понадобился.

Первый full audit тоже сохранён FAIL: reader ожидал trace.file вместо фактического
trace.path. Исправлен только путь схемы и усилена привязка size/parent/hash;
повторный audit02 PASS. Файлы клиента и профили при исправлении не менялись.

## Доказательства

T = `local/evidence/20261005-p02-retired-base-replay/`.

| Доказательство | Путь и SHA256 |
|---|---|
| Original run | `T/replay01-prepare/native-outcome.json`, `39df5cc971dad1f3e901e6a67f3ac969d21510fa83b0b73bebdad5551e241315` |
| Полный original capture | `T/replay01-prepare/wire/capture.json`, `691f18360219ef9fb8795ebb7c846745c0e1a792b3bd04e956f291315c040fe1` |
| Исходная native trace | `T/replay01-runtime/native-96040-1791163033784.jsonl`, `0353d63efa8580929756732117d2f074ee1c910d691007f37fd3962d011ff180` |
| Sender ledger | `T/probe01/`: armed,before-send,3×before/sent/after,result; fullcorpus hashes в final verifier |
| Итоговый native verifier | `T/wire/verify-replay01-02/retired-base-replay-verification.json`, `8a7274f8f6742af1dd2a3d343d8a52817ac2c5f7c0bb85d019a86a44ae0f72f5` |
| Повтор root | `T/root-verification-01/retired-base-replay-verification.json`, `5f5431efe531802aa42b4c28ce6bfe09100b57fdd0ec98539ff8564569fae174` |
| Полное распределение evidence | `T/wire/verify-replay01-02/native-only-install/partition.json`, `70f3ea848f5a948ebb7d992569962ec2e4a780488ef5e4d0273ae62c17fc4596` |
| Frozen S child | `T/wire/verify-replay01-02/switch-proof/account-switch-verification.json`, `ab748edaf8e9d4fff5bd7062aa1d9c2c8ccbe9b2b1943b44386718efca9c4a72` |
| Финальный audit02 | `T/final-audit-02/final-state-audit.json`, `05a209133d77e92aa51864083ff59dcdf86c846cf55829234567be4b2af9a066` |

Audit02: original3469/research3487,0unexpected,13completed diagnostic restores,
28negative controls; normal00813modules/22immutable+3ownerlogs,29backend/4config/
оба profiles/fixtures прежние. Live gateway image/source соответствует принятому
R build. Normal008 установлен, без control/autologin/autoquit/capture.
Native и probe завершены; сервер и сайт остаются запущенными.

## Команды повтора и откат

Read-only проверка сохранённого corpus из корня проекта; out должен быть новым:

```powershell
python -B -X utf8 tools/verify_retired_base_replay.py --install local/evidence/20261005-p02-retired-base-replay/replay01-prepare --probe local/evidence/20261005-p02-retired-base-replay/probe01 --out local/evidence/20261005-p02-retired-base-replay/recheck-01
python -B -X utf8 -m unittest discover -s tests -p test_retired_base_probe.py -v
python -B -X utf8 -m unittest discover -s tests -p test_retired_base_replay_verifier.py -v
```

Новый native run требует свободного mutex, проверенного rollback текущей обычной
установки и свежего номера. После `prepare_run.py --name replay02` сначала
отдельно запустить probe, дождаться armed.json, затем native runner:

```powershell
python -B -X utf8 local/evidence/20261005-p02-retired-base-replay/prepare_run.py --name replay02
python -B -X utf8 tools/retired_base_probe.py --install local/evidence/20261005-p02-retired-base-replay/replay02-prepare --service local/server/service.json --private-key local/server/native-private.pem --out local/evidence/20261005-p02-retired-base-replay/probe02
# В отдельном процессе после probe02/armed.json:
python -B -X utf8 tools/diagnostic_client_run.py --install local/evidence/20261005-p02-retired-base-replay/replay02-prepare --service local/server/service.json
```

Deadline180s относится только к observer; он не останавливает EXE. Если armed
не появился, а probe result уже FAIL, запуск клиента не является продолжением
этого опыта. Все служебные background processes root запускала Hidden.

После закрытия клиента и проверки актуального ledger, откат ordinary008:

```powershell
python -B -X utf8 tools/interactive_client.py rollback --out local/client-install-008
```

## Граница вывода

Подтверждён один настоящий bounded replay из закрытого peer на own loopback.
Это не доказательство всех вариантов сетевой атаки: TTL/restart, переписанный
source address, другие реальные сети, бесконечные повторения — NOT_RUN.
Не утверждается прямое измерение каждого внутреннего ACK-window field: порядок
guard до receive проверен исходниками/unit controls, а native corpus подтверждает
реальный reject и продолжение собственного B без нарушения Account/streams.
Кириллический header clipping/цветное зерно PNG не исправлялись. Ручная приёмка
и полноценная многопользовательская игра — NOT_RUN, полный P02 PARTIAL.

Следующий отдельный проверяемый шаг: более длительный
готовый ангар с подтверждёнными periodic server updates и прежними данными.
