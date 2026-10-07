# P02 — длительный готовый ангар и родной периодический обмен

2026-10-05, отдельная карточка L после принятой T. Ночное поручение владельца;
работа только Account/Hangar, без экономики, новых выдач, арены и UI-ввода.
Evidence: `local/evidence/20261005-p02-long-hangar/`.
Native long01 PASS,20gates/55independent controls; fullaudit PASS
19326505…cf1e/14restores/54negative controls. Ordinary009 установлен,
native закрыт; независимый финальный audit review PASS:11 actual bindings,
38 negative controls, `wire/audit-review-01/result.json` SHA c8299790…617b.
Итог: `docs/research/P02_LONG_HANGAR.md`.

Цель: один настоящий cached primary login; ≥181 нормальных возвратов original
Account.receiveServerStats, между первым и последним ≥900s непрерывного ready
ангара. Это ответы CCU1/1 собственного сервера, не статистика боёв игрока.
Родной LobbyHeader назначает новый запрос спустя5s после ответа; вывод основан
на original #717 pyc и существующем gateway, не на синтетическом генераторе.
Исследование: T/data/long-hangar-feasibility-01/PROPOSAL.md и evidence.json.

1. Сохранить sources/config/profile/consistentDB baseline до правок. Normal008
   снять только после сверки всех immutable/log files с принятой T и ledger.
2. Добавить отдельный opt-in scenario, маленькую интеграцию в control/runner.
   Старые сценарии/verifiers и backend/fixtures заморожены. Считать только
   реальные normal returns того же Account через существующий passive profiler,
   не заменять обработчики и не держать frames. Посторонний account/event — FAIL.
3. Непрерывная готовность, samples≤3s gap; три bounded полных снимка
   identity/resources/fleet/crew/dossier (начало,середина,конец), два native PNG.
   ≥181ответ и≥900s вместе обязательны; только время не доказывает PASS.
4. Observer exhaustion, snapshot mismatch, native error или длительное отсутствие
   progress — FAIL и штатный native quit. Не ставить EXE timeout/kill. При полной
   остановке engine callbacks автоматический выход не гарантируется.
5. Отдельный strict verifier сопоставляет commands501/reliable delivery/CCU
   responses/native returns и ACK progress, без повторного счёта retransmits.
   Требовать полные capture/trace, точные unchanged fixture streams, один
   auth/session/Account,exit0/client_disconnect/12cleanup/rollback; negative controls.
6. До запуска перечитать capture budget (limit10000), не менять session1800s,
   использовать профиль002 и текущий backend. Игру не запускать при недостатке
   запаса. Native provenance и реальные длительности — из сохранённых evidence.
7. После опыта проверить PNG, native report, стандартный rollback; подготовить
   обычную установку009, fullmanifest/profile audit и независимый review.

Разделение: GUI владеет новым scenario/tests; wire новым verifier/tests;
root control/runner/installer integration и native; data независимым review
и новым audit. Никаких параллельных изменений общих файлов.

08:30 местного времени — стабилизация,09:00 итог. Если цель не достигнута,
сохранить фактический FAIL/NOT_RUN; не ослаблять пороги ради утреннего отчёта.
