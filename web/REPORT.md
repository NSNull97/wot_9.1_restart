# WEB-01 · отчёт о локальном веб-модуле

Исторический отчёт о первой реализации. Последующее оформление и собственное
название «Стальной рубеж» описаны в [REDESIGN_REPORT.md](REDESIGN_REPORT.md).
Текущие изображения и эмблема перечислены в [ASSETS.md](ASSETS.md).

Дата: 2026-10-04, Asia/Yekaterinburg.

## Цель и результат

Реализован самостоятельный локальный сайт: главная, регистрация собственного
веб-аккаунта, вход/выход, защищённый кабинет, сохранение имени/описания в SQLite
после перезапуска. Это разрешённая отдельная карточка WEB-01.
Приёмка веб-среза — **PASS локально**; приёмка игрового сервера не меняется.

Изолированный Node/Express процесс, серверные EJS-формы без клиентского JS,
SQLite schema v1. UI адаптивный, тёмный с тёплым акцентом и собственной
декоративной SVG-графикой; игровые ресурсы/логотипы не использованы.

## Изменённые файлы

Все исходники новые и находятся только в `web/`:

- `.gitignore`, `.npmrc`, `package.json`, `package-lock.json` — окружение/изоляция.
- `src/app.mjs`, `src/server.mjs`, `src/store.mjs`, `src/security.mjs`,
  `src/game-adapter.mjs` — HTTP, права/сессии/CSRF, loopback, SQLite, KDF,
  явное отсутствие подключения к игре.
- `migrations/001_web_profile.sql` — атомарная версионированная схема v1.
- `views/home.ejs`, `views/auth.ejs`, `views/account.ejs`, `views/error.ejs`,
  `views/partials/header.ejs`, `views/partials/footer.ejs` — страницы/формы.
- `public/site.css`, `public/mark.svg`, `public/contours.svg` — адаптивный UI.
- `tests/helpers.mjs`, `tests/portal.test.mjs`, `tests/restart.test.mjs`,
  `scripts/verify.mjs` — HTTP/restart проверки и воспроизводимый evidence runner.
- `PLAN.md`, `README.md`, `GAME_ADAPTER.md`, `REPORT.md` — план/запуск/граница/отчёт.

Локальные зависимости/cache — `web/node_modules/`, `web/.npm-cache/`.
Локальные БД, скриншоты и отчёты — исключительно `local/web/`.
Корневые STATUS/config/tools/client_patch/AGENTS/.gitignore/серверные файлы
этой работой не изменялись. Обе клиентские копии не читались и не запускались.

## Факты и предположения

- **VERIFIED:** SQL/HTTP реализация сохраняет только собственный профиль.
  Оба пользователя в тесте имеют разные стабильные UUID; чужой ID из запроса
  не меняет субъект авторизации. Ни пароль, ни его хеш не выходят через API.
- **VERIFIED:** scrypt N=131072/r=8/p=1, соль 16 bytes, digest 64 bytes;
  в БД сессии — SHA-256 случайного ID. Cookie HttpOnly/SameSite=Strict.
- **OBSERVED:** Windows x64, Node 24.21.0, SQLite 3.53.4,
  Express 5.2.1, EJS 3.1.10, Helmet 8.3.0.
- **OBSERVED:** реальные формы работают в Codex in-app browser после
  исправления Referrer-Policy; зафиксированы desktop/mobile screenshots.
- **INFERRED:** один процесс и SQLite достаточны для небольшого локального
  профиля. Это не результат нагрузки или доказательство публичной эксплуатации.
- **UNKNOWN:** upstream Account API, процедура связывания identity,
  публичные названия. Их нет в проверенном серверном контракте этой карточки.

## Реальные проверки

| Проверка | Результат | Evidence |
|---|---|---|
| Синтаксис пяти серверных модулей | PASS | `local/web/checks/syntax.txt` |
| HTTP suite: 16 сценариев + отдельный реальный process restart | PASS | последний успешный `local/web/evidence/*/http-tests.tap` |
| Node test totals (включая родительский test) | 18 PASS / 0 FAIL | `summary.json` и TAP |
| Регистрация/дубликат/неверный пароль/вход/выход/защита кабинета в браузере | PASS | `local/web/browser/summary.json` |
| Имя и описание сохраняются после фактического restart браузерного сервера | PASS | `account-after-restart.jpg`, browser summary |
| Мобильный 390, узкий 320 и планшетный 768 px | PASS в проверенных страницах | browser summary / `home-320.jpg`, `home-tablet.jpg`, `account-mobile.jpg` |
| Видимые поля имеют labels, ошибки связаны через aria-describedby | PASS по DOM/кодовой проверке | browser summary и HTTP checks |
| npm audit production dependency tree | PASS, 0 reported vulnerabilities | `local/web/checks/npm-audit.json` |
| Git ignore для dependencies/cache/env/БД/ключей/evidence | PASS | `local/web/checks/git-ignore.txt` |
| Listener только 127.0.0.1:3091 | PASS | `local/web/checks/listener.json` |
| Firefox/Safari, физическое мобильное устройство, screen reader, нагрузка | NOT_RUN | Нет |
| Native 0.9.1 compatibility, вход в игру, Account API | NOT_RUN | Вне карточки |

HTTP suite дополнительно проверяет CSRF/Origin/Host, no-store/CSP, XSS escaping,
запрет лишних/повторных полей, форму >8 KiB, compressed input, JSON вместо
формы, чужой профиль, поддельный/отозванный/просроченный session ID,
лимит входа и его сохранение после restart. Пароли тестов случайные,
одноразовые и не попадают в отчёты. Базы автоматических тестов удаляет teardown.

## Найденное и исправленное

1. Первый HTTP-run FAIL: Fetch не отправлял заданный Host. Проверка заменена
   на настоящий `node:http` request с поддельным Host; сервер возвращает 400.
   Исходный неуспешный TAP сохранён, не выдаётся за PASS.
2. Первый реальный browser POST вернул 403: no-referrer обнулял Origin
   обычной HTML-формы. Сессия и CSRF были корректны. Исправлено на same-origin;
   требование точного Origin/CSRF не ослаблялось. Формы повторно пройдены.
   Поведение описано в [MDN](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referrer-Policy#effect_on_the_origin_header).
3. Исправлен пробел при скрытом desktop line break в заголовке кабинета.

## Команды запуска и повторения

```powershell
Set-Location -LiteralPath 'D:\WoT_9.1_Server\web'
npm.cmd ci
npm.cmd start
```

URL: `http://127.0.0.1:3091`. Для другого порта — `$env:WEB_PORT = '3092'`.
SQLite по умолчанию: `local/web/runtime/portal.sqlite`.
Foreground stop: Ctrl+C. В этой сессии процесс поднят скрытым Start-Process;
его PID записан в `local/web/runtime/server.pid`, stdout/stderr лежат рядом.
Команды проверки из `web/`: `npm.cmd run check`, `npm.cmd run evidence`,
`npm.cmd audit --omit=dev`. `npm ci` / runtime/tests требуют только web/local/web.

## Ограничения и откат

HTTP предназначен только для loopback: Secure cookie/HSTS отсутствуют.
Публичная публикация, TLS deployment, почта, recovery/смена пароля, 2FA,
экономика, платежи, launcher и управление игровыми данными не реализованы.
Кабинет честно показывает `not_connected`, без вымышленных балансов/танков.
Логин/сессия сайта не являются игровым Account. Независимый security audit NOT_RUN.

Для отката остановить только проверенный процесс сайта, убрать новый `web/`.
`local/web/` можно сохранить для возврата локальных профилей. Если данные
не нужны, удалить эту область после остановки процесса. Не удалять активную
SQLite/WAL/SHM и не применять общий git clean/reset в корне.
Игра и исследовательские порты 20014–20017 отката не требуют.

**Статус приёмки: WEB-01 PASS локально. Серверный STATUS не менялся.**

**Единственный следующий рекомендуемый шаг:** согласовать read-only контракт
и безопасную процедуру связи веб-профиля с будущим авторитетным Account API
по `GAME_ADAPTER.md`, когда серверная сторона предоставит проверяемый API.
