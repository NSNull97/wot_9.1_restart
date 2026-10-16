# P06T — наружный формат publicStateModifiers #717

2026-10-16. Дополнение к [исходному контракту урона](P06T_DAMAGE_SOURCE.md).
Это статическое исследование следующей карточки во время автоматических gates
P04M. Runtime, клиент и HEAD исследованием не изменены; оригинальный клиент
не запускался. Визуальный пожар, звук и UI — **NOT_RUN**.

## Установленный формат

**VERIFIED STATIC:** для полного обновления `Vehicle.publicStateModifiers`
используется message ID `0xa5` и **однобайтовая наружная длина** (`VAR1`).
Длина описывает только содержимое типа, без message ID и самой длины.
Внутри содержимого ARRAY остаётся signed `i32le` count, затем элементы `UINT8`.

| Полное новое значение | Содержимое типа | Полная запись свойства |
|---|---|---|
| `[4]` | `01 00 00 00 04` | `a5 05 01 00 00 00 04` |
| `[]` | `00 00 00 00` | `a5 04 00 00 00 00` |
| `[26, 4]` | `02 00 00 00 1a 04` | `a5 06 02 00 00 00 1a 04` |
| `[26]` | `01 00 00 00 1a` | `a5 05 01 00 00 00 1a` |

Это **выведенные из оригинальных инструкций литералы**, а не перехваченные
пакеты пожара. Они относятся к уже выбранной сущности Vehicle. Существующие
`selectEntity 0x12 + entityID:u32le` и возврат выбора `selectPlayerEntity 0x13`
должны окружать запись в штатном пути публикации. Начальное создание сущности
имеет другой контейнер свойств и не получает эту дополнительную длину.

Индекс `4` — fire из исходного списка extras. Примеры с `26` показывают
сохранение другого активного modifier при удалении fire; это не новый
серверный алгоритм повреждения двигателя.

## Цепочка оригинальных инструкций

Источник — только read-only
`C:\WoT_0.9.1_RU_0717_original\WorldOfTanks.exe`, SHA256
`86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed`.
Адреса ниже — VA x86 при ImageBase `0x400000`.

1. CRT initializer `1683ec0` регистрирует строку `entityProperty`
   (`19b1720`), descriptor kind `2`, исходный length `0`, handler `1f85008`.
   `1683ee0` расширяет диапазон и сохраняет его в `2305660`.
   Свежий пересчёт исходного порядка CRT совпал с P02:
   `entityMethod = 59..157`, `entityProperty = 158..254`.
2. В `1684415` установлен обработчик доставки `d70fc0`; в `1684429` —
   callback размера `d71080`. Vtable handler `19b0ca4 + 8` ведёт в
   trampoline `d729c0`, который вызывает этот callback для соединения.
3. `d71080` вычитает property range start из message ID и вызывает
   `ServerMessageHandler + 0x30` с выбранным entity ID и индексом свойства.
   Vtable `EntityManager` (`17ca924 + 0x30`) содержит `5c89f0`.
   Тот находит сущность и вызывает `5c2a00`.
4. `5c2a00` получает property descriptor через `dc96b0`, затем вызывает
   `dc6e30`. `dc96b0` берёт индекс из отдельного client-property vector,
   а не из порядка объявления `.def`. `dc6e30` вызывает
   `property.DataType->vtable[0x24]`.
5. У SequenceDataType и обоих его производных vtable slot `+0x24` содержит
   `ded1f0`: возврат поля `+0x20`. Constructor `decd94..decda2` вычисляет
   `elementSize * fixedCount`; при результате `<= 0` записывает `-1`.
   У исходного `ARRAY<EXTRA_ID>` fixedCount отсутствует, `EXTRA_ID = UINT8`;
   результат размера этого свойства равен **`-1`**.
6. Generic descriptor resolver `ee3480` для kind `2` вызывает callback.
   Отрицательный результат он инвертирует, записывает kind `1` и
   `lengthBytes = -result`. Поэтому здесь получается **kind1 / length1**,
   а не фиксированная запись и не VAR2.
7. `ee34c0` возвращает для kind1 размер заголовка `1 + lengthBytes`.
   Reader `ee3660`, таблица `ee3768`, branch `ee369d` читает ровно
   `u8[message + 1]`. Симметричный writer `ee34f0`, branch `ee3535`,
   пишет длину туда же. Dispatcher `ed28c0` сначала читает длину, прибавляет
   размер заголовка и только затем передаёт ограниченный payload stream.
   Значит длина исключает и ID, и length field.
8. `d70fc0` доставляет индекс свойства через EntityManager slot `+0x24`
   (`5c8650`) → `5c2940` → `6194b0` → `619ab0`.
   Последний читает **полное значение типа** через `6199c0` и DataType
   slot `+0x20`, с третьим аргументом `0`.
   Sequence wrapper `ded120` поэтому минует дополнительную ветку упаковки
   и вызывает `dedc50`; `dedc90..dedc97` читает четырёхбайтовый ARRAY count.
   В начале payload здесь не требуется дополнительный property index,
   nested path, opcode изменения или строковый packed-length.

Порядок восьми Vehicle client properties повторно вычислен по свежим
`vehicle.def`/`alias.xml` и принятой P02 stable-sort схеме. Первые пять размеров:
`1, 1, 2, 2, 2`; переменные `publicInfo`, `damageStickers`,
`publicStateModifiers` сохраняют исходный взаимный порядок и получают индексы
`5, 6, 7`. Значит `158 + 7 = 165 = 0xa5`.

## Доказательства и команды

Ignored evidence:
`local/evidence/20261016-p06t-01/fire-property-proof02/`.

- `probe.py` и 14 JSON выписок: 35 новых PE windows и data tables.
- `verify.py`, `source-chain-verification.json`: каждый byte window и каждая
  инструкция сверены с оригиналом; 54 ключевых instruction assertions;
  61 прежний P02 PE файл / 131 window повторно сверен с тем же оригиналом.
- 25 исходных файлов P06T повторно проверены по точным размеру/SHA256.
- `derived-literals.json`: только статически выведенные малые полные записи.
- `result.json`: **PASS_STATIC_ENVELOPE_PROOF**, native fire **NOT_RUN**.

Реально выполнены bounded probes, затем полный статический byte/source audit:

```powershell
python -B -X utf8 local/evidence/20261016-p06t-01/fire-property-proof02/probe.py <fresh-json> --va <VA> --bytes <bounded-size>
python -B -X utf8 local/evidence/20261016-p06t-01/fire-property-proof02/verify.py
python -B -X utf8 local/evidence/20261016-p06t-01/fire-property-proof02/verify.py --check-only
```

Последняя команда повторяет read-only проверку и сверяет сохранённые receipts.
Никакие пакеты клиенту не отправлялись; собственного encoder/decoder roundtrip
в доказательстве нет.

## Ограничения и следующий шаг

Ранее обозначенный UNKNOWN наружного формата **полной малой записи** закрыт
статическими инструкциями закреплённого EXE. Это не native-приёмка пожара.
Partial/nested/slice update и escape для payload `>= 255` байт здесь
**UNKNOWN / не используются**. Не надо переносить на них приведённые литералы.
Новый серверный encoder должен иметь собственную малую границу размера и
сохранять полный текущий набор modifiers. HP, owner notification, видимость
P07B, initial creation и удаление огня должны исходить из одного fire state.

Откат — удалить это дополнение; runtime этим исследованием не менялся.
Приёмка: static proof **PASS**, native/UI/audio **NOT_RUN**.
Единственный следующий шаг: реализовать ограниченное полное обновление
modifiers по доказанному VAR1 в ветке P06T, сохранив native gate до владельца.
