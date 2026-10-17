# BUILD: восстановлены legacy сборочные входы

VERIFIED runtime64767ecdc4af5c45a152309816da381709f20022,
codex/build-legacy-entrypoints отbf499c2; mainffce8cb сохранён.
Изменены только tools/wg_probe/src/main.rs, tools/map_drive_worker/
MapDriveWorker.csproj и CRLF attributes. Старые runtime файлы используются
напрямую:24недостающих root declaration/alias,17C#Compile и2EmbeddedResource
с canonical LogicalNames. Старые CLI/functions/tests tail, пакеты и lock прежние.

Реальный baseline RED сохранён:384Rust compilererrors и8C#errors при PASS
offline locked restore. Это старые результаты legacy-diag49, не новый PASS.
После исправления на committed64767ec:

- **Gateway legacy build PASS; capture_cli_tests3PASS/0FAIL/0ignored**,1611filtered.
  Все три исходных имени и прежняя argv/defaults семантика проверены. Полный
  legacy suite не запускался и этим результатом не закрывается.
- **Physics legacy locked build PASS**, DLL SHA
  `3caa9d5788959dffd65f545b866793ed0c7c98c820c2ff6b9a510a9527a8052e`.
- **Actual BattleScene IPC7 smoke PASS**: T26+FV183, stock+extended встроенные
  definitions, настоящая геометрия/Jolt bodies/native getters и независимая
  mass/inertia проверка, restore tick180→advance6/state186. Ровно2frames,
  child завершён по собственному handle; no network/auth/client/owned admission.
-925rawsource/HEAD/attributes до/между/после сборок и smoke совпали.

Команды из C:/wot091-night-20261017-01/w:

```powershell
python -B -X utf8 server/build.py gateway --legacy --test --test-filter capture_cli_tests --out local/build/server/gateway-legacy-capture54
python -B -X utf8 server/build.py physics --legacy --out local/build/server/physics-legacy-fixed02
```

Smoke запускает pinned54 successor02 через root-driver55 с actual build receipt
и ожидаемыми SHA apphost/DLL/result; старый54/01 не используется. Exact argv и
pins сохранены в local/evidence/20261017-legacy-entrypoints55/build01/result.json,
SHA59032471a0a4f7c8a0ae28cc008c9fab943a1762b68b5e23c614b2eccefde242.
Actual smoke local/evidence/20261017-legacy-physics-smoke54/legacy-fixed02/result.json,
SHAe4594ff61c7e7a08ee47717da76978275a0264d3dfd20846fb6ea52862351402.
Исходные байты двух файлов сохранены в отдельном promotion01; старые outputs
не заменялись. Source gate reader05 использован без ослабления.

Targeted build/IPC software PASS. Canonical jointfull925 следующим шагом;
Linux, вся legacy game сессия/native UI/qualification/runtime equivalence NOT_RUN.
Непринятые родители оставляют карточку вне main. Откат — остановить собственные
службы и revert два source файла/не использовать ветку; DB/пакеты не менялись.
Следующий шаг — final canonical full, затем свежие утренние стенды и Python43.
