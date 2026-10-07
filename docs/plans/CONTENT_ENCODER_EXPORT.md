# План карточки: versioned server content/encoder export

## Цель

Собрать отдельный переносимый `server-content.v1` bundle для уже принятых
MS-1 profile1/profile4 входов. Bundle должен содержать только измеренную
замкнутую выборку ресурсов, profile/fixture/native-export blobs и относительную
provenance. Проверка и тестовый генератор должны читать bundle без обращения к
установленному клиенту, его SQLite или live-сервису.

## Границы

- Scope: `test_lab`, client build `v.0.9.1 #717`, catalog revision 2, только
  существующая MS-1 closure и profile1/profile4 chain.
- Старые `tools/hangar_state.py`, profile validators, fixtures и их absolute
  provenance не редактируются и остаются frozen.
- Копируются только выбранные XML, descriptor/profile/fixture/native-export
  blobs. Пароли, email, sessions, live DB/WAL, активные конфиги и целый клиент
  в bundle не попадают.
- License/redistribution остаётся `UNKNOWN; local-only`, пока владелец не
  проверит происхождение и право копирования ресурсов.
- Это не native acceptance и не переключение live backend.

## Шаги

1. Зафиксировать read-only baseline и первоначальный аудит в отдельной evidence
   папке.
2. Экспортировать bundle с относительными content IDs, digest каждого файла,
   digest полной client manifest и точной цепочкой frozen encoder dependencies.
3. Проверить bundle без installed client: path/digest/size bounds, отсутствие
   абсолютных путей и запрещённых файлов.
4. Запустить portable MS-1 generator из bundle и сравнить `state.bin`,
   `shop.bin`, `dossier.bin` с принятым profile1-catalog2 receipt. Это сравнение
   ограничено локальным byte equivalence; native compatibility остаётся
   `NOT_RUN`.
5. Записать after-manifest, команды, результаты и rollback. Старые fixtures и
   validators не переписывать.

## Откат

Удаляется только новая ignored-папка
`local/evidence/20261006-content-export/portable-bundle-*` и новые исходники
этой карточки по after-manifest. Existing evidence, client copies, live DB и
runtime не изменяются.
