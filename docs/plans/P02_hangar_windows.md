# P02 — честные границы неподключённых окон ангара

2026-10-05. Следующая небольшая карточка автономной ночной доводки после
accepted crew02→03 и limits02→03. Цель — закрыть подтверждённое падение
«Внешнего вида» и вход в ещё неподдерживаемые операции обслуживания.

Основание: `local/evidence/20261005-p02-hangar-limits/gui/appearance-audit-01.md`.
Original `getInscriptionsGroupHiddens` индексирует отсутствующий каталог;
это совпадает с traceback самостоятельного пользовательского normal003.
Падение обслуживания UNKNOWN, но его ремонт/пополнение/настройки реальны
и пока не реализованы своим сервером. Не подставлять выдуманные каталоги/цены.

1. После принятого normal004 сохранить новый source/config/profile snapshot.
   Не менять frozen backend/генераторы/БД/fixtures. Original только читать.
2. Точечно, обратимо закрыть два измеренных callbacks AmmunitionPanel:
   showCustomization(self), showTechnicalMaintenance(self), до fireEvent.
   Родное Warning объясняет недоступность; не подменять общий dispatcher,
   BusinessLobbyHandler.showLobbyView или данные самой машины.
3. Тестировать exactsource/signature, install/restore, ошибки/чужие bindings,
   отсутствие native event/mutation и сохранение module-details callbacks.
4. Native one-shot diagnostic своим аккаунтом: вызовы только установленных
   guards, реальные Warning/PNG, неизменные данные/crew, отсутствие окон,
   CMD108 и других мутаций. Штатное завершение по результату без timer/kill.
5. Повторный native вход, независимая сверка и rollback. Сохранить normal005
   без control/autologin/autoquit/capture, обновить STATUS/отчёт/манифесты.

Разработка интерфейса найма, ремонтной экономики, каталога кастомизации,
боекомплекта, очереди и арены вне этой карточки. Не объявлять весь ангар или
боевой сервер готовым. Физические клики/ручная приёмка владельцем NOT_RUN.
Evidence: `local/evidence/20261005-p02-hangar-windows/`.
Статус: PASS узкой карточки; полный P02 PARTIAL. Baseline280 sources/14local/2DB.
Windows01→02 native/cached pair PASS: по78packets/3PNG/3crew/12cleanup,
exit0/restore,0 свежих ошибок и0 команд мутации. Report SHA
62a206bf7c208a313900b12e5cfdcf30b4a7690d01676ae8e7ea81a4d78903ec.
Policy110/Scenario31/Runner33/Verifier53 tests PASS. Normal005 установлен;
original3469/research3485 exact audit PASS,9 restores,13 negative controls.
Ручная приёмка и отдельный запуск normal005 NOT_RUN.
Подробности: [отчёт и воспроизведение](../research/P02_HANGAR_WINDOWS.md).
