# CONTENT-0 2.6: автоматические пушки 0.9.1

Источник: оригинальный клиент `C:/WoT_0.9.1_RU_0717_original` (путь из
`local/stands/full-test-20261111-17/bridge.json` → `ammunition_service.original_root`),
только чтение. XML — `tools/packed_xml.py`, байткод — `tools/py27_static.py` как данные
(без import/exec). Дата: 2026-11-12.

## 1. Какие машины

До 2.6 генератор (`tools/battle_any_profiles.py`) отказывал 21 машине кодом
`AUTOMATIC_GUN_UNSUPPORTED` (`config/test_lab/battle_profiles.v1.json`, поле `refusal`).

## 2. Загрузчик 0.9.1 (VERIFIED, `res/scripts/common/items/vehicles.pyc`)

- `_readGunClipBurst(xmlCtx, section, type)`: `count = readInt(type+'/count', 1)`,
  `interval = 60.0 / readPositiveFloat(type+'/rate')`, возврат `(count, interval if count > 1 else 0.0)`.
- `_readGun` (общий раздел `shared`): нет раздела `burst`/`clip` → `(1, 0.0)`.
- `_readGunLocals` (раздел пушки в xml машины): если в машине есть раздел `burst`/`clip`,
  он **целиком** заменяет общий (`hasOverride = True`), иначе берётся общий. Поля по одному
  не смешиваются.
- Оба места: `burst[0] > clip[0] > 1` → `raiseWrongXml('burst/count is larger than clip/count')`.
  Очередь при `clip == 1` загрузчик не запрещает.
- `clip[0] == 1` снимает тег `clip`, иначе добавляет.

## 3. Значения 21 машины (VERIFIED, раздел машины или `components/guns.xml`)

Интервал = 60/rate. «Перезарядка» и «боезапас» — из xml машины.

| машина | пушка | clip count/rate | burst count/rate | перезарядка, с | боезапас | 2.6 test_lab |
|---|---|---|---|---|---|---|
| germany:PzI | _20mm_KwK_30 | 10/280 общ. | 2/280 общ. | 4.3 | 240 | generated |
| germany:PzII | _20mm_KwK_30 | 10/280 общ. | 2/280 общ. | 4.3 | 260 | generated |
| germany:PzII_J | _20mm_KwK_38_L55A | 10/450 маш. | 2/450 маш. | 3 | 400 | generated |
| germany:PzII_Luchs | _20mm_KwK_38_L55 | 10/450 общ. | 2/450 общ. | 3 | 330 | generated |
| germany:PzI_ausf_C | _20mm_KwK_38_L55 | 10/450 общ. | 2/450 общ. | 3.9 | 260 | refused: PHYSICS_ENVELOPE_EXCEEDED (max_forward 21.9 м/с) |
| germany:Pz_II_AusfG | _20mm_KwK_38_L55 | 10/450 общ. | 2/450 общ. | 3.9 | 320 | generated |
| germany:VK1602 | _20mm_Flak_38_L112 | 10/450 общ. | 2/450 общ. | 2.7 | 420 | generated |
| japan:Chi_Ni | _13.2mm_Type93 | 30/450 маш. | 5/450 общ. | 10 | 900 | generated |
| uk:GB58_Cruiser_Mk_III | _15mm_Machine_gun_BESA | 40/430 маш. | 5/430 маш. | 18 | 400 | generated |
| uk:GB75_AT7 | QF_6_pounder_Mk_V_AT | 10/55 маш. | нет (1, 0) | 12 | 120 | generated (длинный барабан без очереди) |
| uk:GB76_Mk_VIC | _15mm_Machine_gun_BESA_ | 40/430 общ. | 5/430 общ. | 18 | 400 | generated |
| usa:M2_lt | _12.7mm_MG_HB_M2 | 40/550 общ. | 5/550 общ. | 22.9 | 1800 | generated |
| usa:M3_Stuart | _20mm_Hispano_Suiza_Birgikt_gun | 15/600 общ. | 3/600 общ. | 7.7 | 750 | generated |
| usa:M5_Stuart | _20mm_Hispano_Suiza_Birgikt_gun | 15/600 общ. | 3/600 общ. | 6.9 | 870 | generated |
| usa:MTLS-1G14 | _37mm_44_caliber_automatic_cannon | 10/480 маш. | 2/480 маш. | 15.2 | 700 (общ.) | generated |
| usa:T1_E6 | _37mm_semiautomatic_gun_M1924A1 | 5/120 общ. | 1/120 общ. | 5 | 80 | generated (барабан) |
| usa:T23 | _12.7mm_T23 | 40/550 общ. | 5/550 общ. | 1.5 | 1800 (общ.) | generated |
| usa:T2_lt | _20mm_Hispano_Suiza_Birgikt_gun_A | 15/600 общ. | 3/600 общ. | 7.66 | 1200 | refused: PHYSICS_ENVELOPE_EXCEEDED (max_forward 20.00016 м/с) |
| usa:T2_med | _37mm_semiautomatic_gun_M1924 | 5/120 общ. | 1/120 общ. | 5.7 | 110 | generated (барабан) |
| usa:T7_Combat_Car | _12.7mm_MG_HB_M2_A | 50/550 маш. | 5/550 общ. | 24 | 1350 | generated |
| ussr:T-60 | _12.7mm_DSHK | 50/600 общ. | 5/600 общ. | 33 | 1000 | generated |

OBSERVED (сборка генератора в память, без записи): 19 из 21 становятся `generated`, две
отказаны физическим конвертом (независимый от пушки код). Ни одна строка не нарушает
`burst ≤ clip`; все очереди делят обойму нацело. T-60/T7: обойма 50 — потолок 2.6 `MAX_CLIP=64`.

## 4. Клиентская сторона (VERIFIED, `res/scripts/client/*.pyc`)

- `Vehicle.showShooting(burstCount, isPredictedShot=False)` (`vehicle.pyc`, стр. 165): серверный
  вызов для своего танка без ожидания выстрела (`isWaitingForShot`) игнорируется; иначе
  `extra.startFor(self, burstCount)` и `cancelWaitingForShot`.
- `vehicle_extras.ShowShooting._start/__doShot`: `data['_burst'] = (burstCount, gun['burst'][1])`;
  эффект выстрела проигрывается `burstCount` раз через `BigWorld.callback(burstInterval, …)`,
  интервал — **из дескриптора пушки клиента**, не из сообщения. Отдача, вибрация, наземная
  волна и `getOwnVehicleShotDispersionAngle(…, 2)` — на каждый эффект.
- `PlayerAvatar.__showTimedOutShooting` (предсказание при задержке ответа сервера):
  `burstCount = gun['burst'][0]`, урезается до `totalShots`, а при `clip[0] > 1` — до
  `shotsInClip`; затем `showShooting(burstCount, True)`.
- `PlayerAvatar.__processVehicleAmmo(compactDescr, quantity, quantityInClip, …)`: счётчик —
  снаряды, не очереди; `setShellQuantityInSlot(idx, quantity, quantityInClip)`; при первом
  появлении строки `aim.setClipParams(clipCapacity, burst)` из дескриптора клиента.
- `Aim._getClipState`: при `burst > 1` прицел считает очереди: `ceil(capacity/burst)`,
  `ceil(quantityInClip/burst)`; предупреждение при ≤ половины, «critical» при 1 оставшейся.

Следствие (INFERRED): на одну очередь сервер шлёт один `showShooting(N)`; клиент сам
проигрывает N вспышек. `updateVehicleAmmo` несёт число снарядов в стеке и в обойме.
Сколько раз оригинальный сервер слал `updateVehicleAmmo`/`updateVehicleGunReloadTime` за
очередь и что было в `timeLeft/baseTime` — UNKNOWN (серверного кода нет).

## 5. Решения 2.6 (INFERRED, test_lab, проверка владельцем в бою)

- Одно принятое `vehicle_shoot` открывает очередь `min(burst, clip, стек)` (как предсказание
  клиента). Первый снаряд — сразу, остальные — шагом мира по серверному времени с шагом
  60/burst_rate (квантуется шагом мира 100 мс; догоняющий шаг выпускает все созревшие по
  своему расписанию). Каждый снаряд — отдельный снаряд/трассер/попадание.
- `showShooting(N)` — только с первым снарядом очереди (`Shot.burst = N`), у остальных
  `burst = 0` и вспышки нет: у своего клиента второй серверный вызов был бы проигнорирован,
  у соседей клиент уже играет N вспышек.
- Следующая очередь — через интервал обоймы (60/clip_rate) от последнего снаряда; пустая
  обойма — полная перезарядка от последнего снаряда. Часы перезарядки, которые видит клиент,
  — одна дуга от первого снаряда до готовности (`base_reload_seconds = burst_span`).
- Во время очереди: повторный выстрел, смена текущего снаряда и ручная перезарядка
  отказываются (`Reloading`), выбор следующего снаряда разрешён. Модификатор перезарядки
  (заряжающий, повреждение) масштабирует только перезарядку после последнего снаряда.
- Очередь прерывается без потери снарядов, если стрелять нельзя (пушка/экипаж), машина
  уехала из боя, умерла, период боя закрыт или журнал выстрелов полон.
- Очередь при `clip == 1` и `burst > clip` сервер не принимает (fail closed; в 0.9.1 таких
  строк среди этих 21 нет).

## 6. Открытые вопросы (UNKNOWN)

- Реальная серверная схема 0.9.1: выпускались ли снаряды очереди по времени или пачкой,
  какой `timeLeft/baseTime` слался после очереди.
- Разброс внутри очереди: сейчас каждый снаряд увеличивает круг как обычный выстрел
  (`after_shot`); исторический закон для очереди не исследован.
- Ёмкость: `MAX_AMMO_PER_ACTOR=160` и `MAX_BATTLE_SHOTS=4800` (журнал выстрелов, трассеры,
  `fragiles.bind_ammo_capacity`), доменный `finish` и `profile13_hold/loss` отвергают стек
  > 160. Автопушки везут до 1800 снарядов. 2.6 лишь ограничила потолок мира `MAX_BATTLE_SHOTS`
  (иначе любой выстрел в большом составе отвергался бы); решение по ёмкости — владельцу.
