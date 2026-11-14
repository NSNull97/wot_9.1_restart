# VISUAL-03 — опытная партия советских текстур: альфа и mip

Состояние на 2026-11-14: партия установлена в существующую копию. **OBSERVED:**
владелец осмотрел МС-1 и СУ-8, затем сообщил: «Проверил МС-1 и СУ-8 в бою,
всё нормально, гусеницы не мерцают». Критерий пробы по игровому показу и бою
подтверждён владельцем. Загрузка именно новых DDS клиентом не инструментирована,
номера боёв и замеры FPS/памяти **UNKNOWN/NOT_RUN**; приёмка не распространяется
на другие машины и режимы. Текущую CONTENT-0 не менять.

## Состав и исследование исходника #717

Источники: разрешённая копия `D:/WoT_9.1_Server/local/clients/p03f/a`, точные
DDS из `res/packages/vehicles_russian.pkg`. Три пути и SHA закреплены в
`tools/visual03_batch.py`; полная опись исходных mip и распределений альфы —
`D:/WoT_9.1_Server/local/evidence/visual03-alpha-research-20261114/selected-mips.json`
(SHA-256 `d61aef6b19c3f9c4e9c1484a96f2f55aae78098735055cdbdac9e0238f0fe8c4`).

| Текстура / использование | Исходник | Альфа на всех mip |
|---|---|---|
| `R11_MS-1/MS-1.dds`, МС-1 и Observer | DXT1 2048×1024, 8 уровней до 16×8 | только 255 |
| `tracks/MS-1_track.dds`, МС-1, СУ-18, Observer | DXT3 256², 9 уровней | переменная; на 1×1 — 238 |
| `tracks/SU-14_track.dds`, СУ-8, СУ-14, СУ-14-1, Т-127 | DXT5 256², 9 уровней | переменная; 252 значения наверху, на 1×1 — 209 |

**VERIFIED:** `Chassis.visual` МС-1 и СУ-8 связывает соответствующую карту с
`diffuseMap`; материал содержит `alphaTestEnable=true` и `alphaReference=16`,
шейдер `PBS_tank_old_uvtransform_skinned.fx`. Доказательства и хеши —
`local/evidence/visual03-alpha-research-20261114/materials.json`. Исходника
шейдера в проверенном клиенте не найдено. **INFERRED:** альфа diffuse участвует
в отсечении; точная формула и runtime — **UNKNOWN**, как и визуальное влияние.

## Метод и результат

Партия: `local/evidence/visual03-batch-20261114/manifest.json`, RGB нового верхнего
уровня = 80% Lanczos и 20% Real-ESRGAN x4plus, без общего сдвига цвета. DDS
сохраняет исходный DXT1/DXT3/DXT5. Для каждой текстуры добавлен один 2× top-mip;
все исходные сжатые уровни целиком перенесены побайтово на уровни 1…N. Поэтому
цепочка МС-1 8→9 по-прежнему заканчивается на 16×8, а гусеницы 9→10 на 1×1.
Альфа нового mip DXT3/DXT5 построена из исходных блоков с точным повторением
значения каждого текселя 2×2, без перекодирования alpha endpoints/selectors.

| Выход | SHA-256 |
|---|---|
| `MS-1.dds` | `1ff56450bb7d70f974b56fe2be5db48ed1f61261947d7099c0cc614c268e7d5d` |
| `MS-1_track.dds` | `1c8adaae9268fea89ca44fadcc8ac769d38a6c88bf0f5a9a0c3b52319dfb5025` |
| `SU-14_track.dds` | `0c38182c29d7f6656a2171edf0e43f3f67a6828e3e43507da4ec9ef6655f9729` |

Все исходные уровни сохранены побайтово; обе гусеницы независимо собраны вторым
алгоритмом с идентичными файлами. Независимое декодирование ImageMagick: у каждой
гусеницы все 262144 alpha-пикселя нового уровня равны исходнику, увеличенному
nearest 2×. Texconv прочитал все три DDS и распаковал верхние mip. Код/команды и
данные инструментов — в `manifest.json`, `build-log.json` и
`local/evidence/visual03-alpha-probe/REPORT.md`. Сравнение текселей не доказывает
эквивалентность bilinear/trilinear фильтрации: мерцание и переходы LOD требуют
наблюдения в игре. RGB нейросети — не подтверждение исторически точных деталей.

## Запуск и откат

Код: `tools/visual03_mips.py`, `tools/visual03_batch.py`, `tools/visual03_install.py`;
тесты `tests/test_visual03_mips.py`, `tests/test_visual03_install.py`.
Пакет создаётся только в новом каталоге `local/evidence`; client source read-only.

```powershell
python -B -X utf8 -m unittest tests.test_visual03_mips tests.test_visual03_install tests.test_visual02_dds tests.test_visual02_inventory -v
python -B -X utf8 -m tools.visual03_batch --client D:/WoT_9.1_Server/local/clients/p03f/a --out-dir D:/WoT_9.1_Server/local/evidence/visual03-new-run
python -B -X utf8 -m tools.visual03_install install
python -B -X utf8 -m tools.visual03_install rollback --receipt D:/WoT_9.1_Server/local/evidence/visual03-batch-20261114/install-809e3b85ff134d8db14ea02be2ce9af2.json
```

Установка и откат рассчитаны только на конкретную существующую копию
`local/clients/content0-scoped-24` и три перечисленных файла. Проверено на этой
копии: install → rollback → повторный install, все три квитанции PASS. После
отката все три подмены отсутствовали, backup и хеши совпали; принятая текстура
КВ-1С осталась `62b45cd1bf7564b340fc1bd493bcf6e8ec10955bc878c60290420f96285291e2`.
Квитанция установки для просмотра — `local/evidence/visual03-batch-20261114/`
`install-809e3b85ff134d8db14ea02be2ce9af2.json`, пробного отката —
`rollback-581f80c9d7c14aa1b3dd4dbc317fe4ce.json`. Перед откатом закрыть именно
эту копию клиента; чужие процессы и подмены не изменять.

После повторной установки запущен `WorldOfTanks.exe` этой копии, процесс отвечает;
захват окна дважды завершился тайм-аутом. После этого владелец осмотрел обе машины,
а затем проверил МС-1 и СУ-8 в бою: по его словам, всё нормально, гусеницы не
мерцают. Записи ответов — `local/evidence/visual03-batch-20261114/`
`owner-visual-inspection-20261114.json` и `owner-battle-20261114.json`.
Загрузка именно новых DDS не инструментирована; это приёмка владельца на
существующей локальной копии, а не доказательство всех режимов и платформ.
Если питание/процесс оборвётся во
время операции, lock и незавершённая квитанция блокируют следующие операции до
ручной проверки; не удалять неизвестные файлы и lock вслепую. Перенос в штатный
`prepare`, массовый апскейл и распространение ресурсов вне цели этой карточки.
Не публиковать клиентские DDS и производные ресурсы без проверки прав.
