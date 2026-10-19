# Full polygon: фактический запуск 19 октября 2026

Статус: **native FAIL по столкновению/публикации HP**, main не изменён. Ветка
`codex/nightly-full-polygon-20261018`, исходный code checkpoint `356c21a`,
предыдущий docs checkpoint `ccbfaf2`. Запуск не означает приёмку всех карточек.

## Привязка и подготовка

- Gateway: сохранённый canonical `gateway-nightly-full-polygon-full03`, SHA-256
  `04f2c94262a2f9bb973cac7840f54e4885cfdbbf85fbeae126f98ea5e3208bdd`.
  Его исторический gate: **1670 PASS / 0 FAIL / 5 ignored**. Этот suite сейчас
  повторно не запускался и не подтверждает новую physics-сборку.
- Fresh stand: `D:/wot091-successor-worktree-20261018-01/local/stands/full-polygon-native-20261019-01`.
  Snapshot взят SQLite backup API из actual successor-03: ревизии аккаунтов
  A/B **131/53**, `quick_check=ok`, `integrity_check=ok`, новых grants **0**.
  Ранее подготовленный successor-05 содержал старую ревизию A=125; он сохранён,
  но для этого теста не используется.
- Physics собрана из текущего исходного дерева:
  `python -B server/build.py physics --out local/build/server/physics-nightly-polygon-native01`.
  Worker DLL SHA-256
  `277604429230f8238c22d1909abf8ebe4b604c5c6ade911592994861b1a1828c`;
  artifact manifest SHA-256
  `7a863a7804a9a79da53b7861e78d1d2243f8260d25501af65b0bfbc4467e1a0d`.
  Actual IPC7 smoke: MS-1 + IS-7, 100 advances, 7 fractures,
  sync_removed ACK, exit0/stderr0; **PASS**, native handling пока NOT_RUN.
- Bridge запущен из successor checkout в соответствии с его границей local/.
  231 используемый service source проверен на совпадение с canonical tree
  после нормализации LF/CRLF; дополнительные tools для планирования не исполняются.
  Полная binding receipt SHA-256
  `7149337cf5da4a34121422a6331a285588867e87312d5f20d9a0bcc5f39c40d0`.

## Фактический запуск

Bridge PID178564: `game_bridge_ready`, TCP3691. Gateway PID198224:
`BOUND 127.0.0.1:20330`, UDP20331, оба startup stderr пустые.
Gateway command:

```text
sr-gateway.exe legacy091-profile13 <owned-private-key> <owned-client-digest> <stand>/gateway.json <stand>/battle-profiles.json <runtime-evidence>/capture
```

`WOT091_STAB_DIAGNOSTICS_DIR` передан дочернему gateway: измерения advance,
worker CPU/stderr и scheduler lag включены; данных боя до его старта нет.

Клиентские копии: `local/clients/p03f/a` и `b`, текущие PID199752/185936.
Изменены только настройки путей: profile/trace/screenshots, preferences в
`res/engine_config.xml` и profile search path в `paths.xml`; исходные файлы
сохранены для отката. После двух обнаруженных ошибок подготовки (trace вне
разрешённого local/ и устаревший native preferences path) оба клиента загрузили
настоящий LoginView. Владелец подтвердил: **оба вошли в ангары**. В gateway
есть `P08B_ACCOUNT_FULL` и `ACCOUNT_SHOW_GUI_QUEUED` для двух сессий.

Receipts и закрытые native traces находятся на D:
`local/evidence/20261019-full-polygon-native01` в canonical checkout, а capture
и client traces — в одноимённом evidence-каталоге successor checkout.
Токены, учётные данные и клиентские ресурсы в git не включены.

## Матрица текущего прогона

1. Login обоих и загрузка настоящих ангаров: **OBSERVED PASS**, подтверждено
   владельцем и двумя серверными Account projection.
2. Подготовка двух ИС-7 через родное обслуживание: **OBSERVED PASS**.
   Начальный IS-7 БК A/B=28/0. Задание владельцу: по 15 ББ, 5 БП и 10 ОФ;
   это проверка обслуживания без выдачи ресурсов. Владелец подтвердил оба
   loadout 15/5/10; сервер сохранил `AMMO_SERVICE_RESULT serviced=true result=0`
   для обоих, durable revisions133/55. После дальнейшего резервирования очереди
   snapshot134/56: у обоих IS-7 HP2150, ammo30, crew_assigned=true.
3. Общий бой и READY обоих: **OBSERVED**, новая physics-сцена действительно
   запущена. Контакт/уклон: **FAIL**. Два реальных эпизода: IS-7/IS-7
   (оба HP2045), затем IS-7/MS-1 (HP2149/87). Оба закрылись при публикации
   `p06t_publication.rs:99:106`, projectile damage_events0/ram records2.
   Первые 553 actual advances: максимальный advance wait5805µs,
   scheduler lag91243µs, FAIL_CLOSED0 в этом ограниченном интервале.
   Диагностический sink исчерпал512KiB около63,6с: это частичная выборка,
   дальнейшие интервалы NOT_SAMPLED. Из-за нехватки места текущий sink даже не
   вместил marker усечения; отсутствие marker не означает полный trace.
   Полные failure witnesses сохранены в `contact-failures`, receipt SHA-256
   `1da6ed30315a9a01afb011a9dd5512a54579d493465c36bf8862618061590e89`.
   Независимый SAT коробок:7,2546мм/0мм, receipt SHA-256
   `b68ec8aa894738c8074c446ffee48062c433d3264ab002882d8d8c2b1e2650a6`.
   Это два снимка, не полная трасса интерполяции. Владелец уточнил, что
   визуальное проникновение связано со сбросом при лёгком касании MS-1.
   После обоих аварийных возвратов actual БД A/B137/59, IS-7 loaded30 у
   каждого; новая ветка исправления `codex/p05c-ram-health-publication`.
4. LOS/габаритные точки/переворот/визуальное 6-е чувство: **NOT_RUN** в этом
   запуске; предыдущая приёмка не заменяет regression.
5. Повреждения, отдельный таймер engine/fuel, пожар, БК/расход loaded,
   parent turret hide, лежащая башня и коллизия орудия: **NOT_RUN**.
6. Results8 обоих, ACK, естественный finish, оба ангара, повторный бой:
   **NOT_RUN**.
7. Исследование/покупка и сохранение ангарной проекции: **NOT_RUN**.

## Открытые границы

- Нового импорта всех динамических объектов карты в runtime нет. Bound catalog
  содержит прежние 1038 объектов; отдельные contract tests не доказывают полную
  разрушаемость всех карт.
- Купленные native_id>=3 пока garage-only: нет принятого полного
  crew/ammo/equipment/runtime допуска купленной машины в бой.
- `training_rooms=false`: обычный двухклиентский бой не закрывает P10B.
- Runtime profile13 использует device policy v1; отдельный curated-lab-v2
  не является переключателем этого owned stand.
- Отдельного звука лампы в исходном #717 пути нет; project audio override
  не реализован. Audio остаётся открытой границей.
- Физика detached child не имеет отдельного Jolt body. Native parent-hide,
  presentation и реальная gun collision требуют фактической проверки.

## Откат и следующий шаг

Остановить только PID этого запуска после проверки executable/start time,
восстановить `sr_interactive_settings.json`, `paths.xml` и
`res/engine_config.xml` из сохранённых before-копий. Исходный successor-03,
старый sealed-05, их БД и historical evidence не изменять и не удалять.
Main остаётся `ffce8cb`. Следующий шаг: закончить родное обслуживание обоих
ИС-7, затем один общий бой по пунктам 3–6 с фиксацией первого реального сбоя.
