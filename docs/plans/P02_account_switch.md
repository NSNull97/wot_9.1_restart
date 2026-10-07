# P02 — изоляция аккаунтов при переключении внутри EXE

2026-10-05. Отдельная карточка после принятого R02/normal006. Разрешена
ночным поручением владельца продолжать узкие проверки существующего
Account/Hangar без его участия. Арена, бой, экономика и новые выдачи вне объёма.

Цель: один настоящий EXE и прежний profile002, primary → secondary → primary.
Проверить, что UUID/nativeID/name, машины, экипаж, dossier и кэш соответствуют
текущему аккаунту; два одинаковых баланса сами по себе изоляцию не доказывают.

VERIFIED: primary profile3, nativeID1, МС-1+ИС-7 и два танкиста МС-1;
secondary profile1, nativeID2, один МС-1 без экипажа. Их собственные credentials
существуют, новый аккаунт создавать не требуется. Старый native secondary PASS
не покрывает нынешний r1-catalog2; эта совместимость пока UNKNOWN/NOT_RUN.
Read-only обоснование: `local/evidence/20261005-p02-inprocess-relogin/data/next-check.md`.

1. До правок сохранить source/config/profile и consistent backups двух БД.
   Baseline обычного клиента — normal006 и полный принятый manifest R.
2. Только новый opt-in сценарий и узкая интеграция. Старые accepted сценарии,
   verifier, gateway, генераторы, fixtures и journal hashes заморожены.
3. Три настоящих login через original LoginView/собственную авторизацию;
   перед следующим — original logoff, реальный disconnected/LoginView и
   repository=None. Watcher и lifecycle вручную не вызываются.
4. Каждый Account получает свои точные три серверных stream. Проверяется
   настоящий Hangar/current vehicle/inventory/crew/name, минимум15s
   непрерывной готовности и native PNG в каждой фазе. Primary tankmen/ИС-7
   отсутствуют у secondary и возвращаются только при новом primary login.
5. Credentials лишь в consumed control и временной памяти явной диагностики;
   значения/производные секретов не логировать. Очистить ссылки после нужного
   submit/ошибки/fini. В normal не добавлять автологин или автоматический logout.
6. Независимый verifier разделяет ровно три последовательных wire sessions,
   проверяет fresh auth, retirement, реальные cache hints каждого аккаунта,
   source/build/runtime provenance, exact payloads и отсутствие мутаций.
   Не считать synthetic/mock успехом клиента. Сохранить любые FAIL.
7. Штатный native quit только после завершённого условия или наблюдаемой
   ошибки; без таймера/kill/мыши/клавиатуры. Каждый diagnostic ledger откатывается.
8. Оба сохранённых profile/fixtures должны остаться побайтово прежними.
   После приёмки — ordinary пакет, full manifests/audit, STATUS/отчёт/откат.

Если выявлен реальный несовместимый контракт, сначала доказательство и узкая
поправка плана; не менять профиль secondary заранее ради удобства сценария.
Same key/retired endpoint отказ не обходить ожиданием или удалением кэша.
Никаких подключений к внешним игровым серверам. Original только чтение.

Evidence: `local/evidence/20261005-p02-account-switch/` (S).
Статус PASS: switch02 PID7600,279packets/3auth/3Account/3PNG,0ошибок,
primary→secondary→primary state/cache isolation. Первый switch01 prepareFAIL
до изменений сохранён; normal006 guard/rollbackPASS. Native exit0/restorePASS.
Normal007 установлен, full audit original3469/research3487/0unexpected PASS.
Final native report530dd127…12dd6, final audit5f3f202c…02c42.
Independent31 review controls PASS; полный отчёт research/P02_ACCOUNT_SWITCH.md.
Ручная приёмка ночью NOT_RUN. Многократные циклы и активный network replay NOT_RUN.
