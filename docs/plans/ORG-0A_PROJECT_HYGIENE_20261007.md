# ORG-0A — project hygiene and baseline (2026-10-07)

## Цель

Зафиксировать первый воспроизводимый Git baseline проекта WoT 0.9.1 Server,
сделать один канонический gate текущего этапа и свести evidence-index для P03.
Карточка организационная: она не меняет протокол, battle/fire/reload, физику,
deployed service или клиентские копии.

## Факты на входе

- Рабочее дерево инициализировано Git, но `main` не имел коммитов.
- `origin` перед карточкой не задан; GitHub-репозиторий владельца пустой.
- P03D принят владельцем как `PASS_OWNER_NATIVE_AMMO_PANEL_HUD`.
- P03E принят владельцем как `PASS_OWNER_NATIVE_FIRE_RELOAD_CONSUMPTION`;
  это подтверждено последним owner-run (5 выстрелов, 20 -> 15 AP, пять
  завершённых reload callbacks). Старые `NOT_RUN` записи в STATUS остаются
  историей и не переопределяют свежий receipt.
- Полный P03 остаётся `IN_PROGRESS`: второй независимый клиент, общий
  авторитетный мир, projectile/hit/damage и полный боевой цикл не приняты.

## Граница файлов baseline

В allowlist входят только корневые проектные документы и исходники в
`client_patch/`, `config/`, `docs/`, `prompts/`, `server/`, `templates/`,
`tests/`, `tools/`, `web/`, плюс `.gitignore`. `local/`, `.npm-cache/`,
обе копии клиента, node_modules, `bin/`, `obj/`, `target/`, caches, dumps,
captures, secrets, базы и производные бинарники исключаются. Исключения и
полный список staged-файлов записываются в evidence receipt до commit.

Никакого `git add -A`, reset, force-push, удаления или отката дерева не будет.
Исходные/исследовательские клиенты и активные процессы не изменяются.

## Порядок

1. Проверить `.gitignore`, путь-владельца `server/layout.json`, remote и Git
   identity; при необходимости добавить только организационные ignore-паттерны.
2. Сохранить фактические результаты layout/unittest/link/allowlist checks в
   `local/evidence/20261007-org-0a-project-hygiene-01/`.
3. Создать `ACTIVE_GATE.md`, P03/P03D/P03E evidence-index и отчёт stale paths.
4. Explicit allowlist: сформировать список файлов, проверить его на запрещённые
   пути/расширения, staged names и `git diff --cached` до commit.
5. Создать первый исторический baseline commit и аннотированный тег
   `baseline-2026-10-07`, затем ветку `codex/org-0a-project-hygiene`.
   Организационные изменения документов, уже подготовленные до уточнения
   владельца, остаются в working tree; в initial index сохранены их тексты
   до ORG-0A (обратные точечные изменения только index). Runtime не меняется.
   Safety `.gitignore` включён до первого commit. Не переписывать тег.
6. Подключить `origin` только если его не было, обычным URL владельца.
   Попробовать `git push -u origin main`, затем `git push origin
   baseline-2026-10-07`; credentials/network failure записать буквально как
   `NOT_RUN`, локальные commit/tag сохранить.
7. После проверок head ORG-0A выполнить обычный merge --no-ff в main, push,
   проверить `git ls-files`, `git status` и `git ls-remote`. Если push не прошёл,
   сохранить точную ошибку и локальную историю. ORG-0B не выполняется в этой карточке.

## Проверки и критерий

- `python -B -X utf8 server/check_layout.py`
- `python -B -X utf8 -m unittest discover -s tests -q`
- bounded local-link/path scan и stale-path inventory
- explicit Git allowlist scan до и после commit
- remote heads check после push, если он состоялся

PASS означает только фактически выполненную проверку. Ошибки/пропуски
unittest не исправляются здесь: они становятся отдельным ORG-0B backlog с
точными именами тестов и выводом.

## Откат

Рабочее дерево не откатывается и не очищается. Организационные изменения
откатываются отдельным проверенным revert-коммитом только по явному решению
владельца; baseline/tag и история сохраняются как точка возврата.
Remote force-push не используется. При неуспешной аутентификации remote push
остаётся NOT_RUN, локальные commit/tag не удаляются.

## Единственный следующий шаг после ORG-0A

`ORG-0B`: отдельно классифицировать текущие failing/skipped unittest и
сформировать минимальный план исправлений без изменения P03 battle-кода.
## Уточнения allowlist и авторства

`web/data/` исключён из baseline как локальные выгрузки клиентского каталога
и производные datasets без завершённой проверки распространения. Файлы на
диске сохранены; bare clone не содержит этих runtime inputs. Четыре PNG
`web/public/images/` — собственные image_gen иллюстрации, происхождение
проверено по `web/ASSETS.md`; они включаются по точному allowlist.
Автор коммитов явно указан владельцем: NSNull / programmist.ios@gmail.com;
используется только local Git config, глобальные настройки не меняются.
