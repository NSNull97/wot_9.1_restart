import express from 'express';
import helmet from 'helmet';
import { fileURLToPath } from 'node:url';
import { openStore } from './store.mjs';
import { hashPassword, verifyPassword, validPassword, token, sessionCookie, equalToken, textField, nicknameField, emailField } from './security.mjs';
import { createGameReader } from './game-adapter.mjs';
import { registerCatalogRoutes, counts as catalogCounts } from './catalog.mjs';
import { validateOrigins } from './network.mjs';

const MINUTE = 60_000;
const cookieOptions = { httpOnly: true, sameSite: 'strict', secure: false, path: '/' };
const fieldNames = {
  register: ['csrf', 'email', 'nickname', 'display_name', 'password', 'password_confirm'],
  login: ['csrf', 'email', 'password'],
  profile: ['csrf', 'display_name', 'bio'],
  email: ['csrf', 'email', 'current_password'],
};

export async function createApp({ databasePath, origin, allowedOrigins = [origin], now = Date.now,
  gameBridgeOrigin = process.env.GAME_BRIDGE_ORIGIN, gameBridgeTokenFile = process.env.GAME_BRIDGE_TOKEN_FILE }) {
  const originsByHost = validateOrigins(allowedOrigins);
  if (!Array.from(originsByHost.values()).includes(origin)) throw new Error('Primary origin must be in allowedOrigins');
  const readGameOverview = createGameReader({ origin: gameBridgeOrigin, tokenFile: gameBridgeTokenFile });
  const dummyHash = await hashPassword(token());
  const store = openStore(databasePath, now);
  const app = express();
  app.disable('x-powered-by');
  app.set('trust proxy', false);
  app.set('view engine', 'ejs');
  app.set('views', fileURLToPath(new URL('../views/', import.meta.url)));
  app.use(helmet({
    strictTransportSecurity: false,
    contentSecurityPolicy: { useDefaults: false, directives: {
      defaultSrc: ["'none'"], styleSrc: ["'self'"], imgSrc: ["'self'"],
      fontSrc: ["'self'"], scriptSrc: ["'none'"], connectSrc: ["'self'"],
      baseUri: ["'none'"], formAction: ["'self'"], frameAncestors: ["'none'"], objectSrc: ["'none'"],
    } },
    // no-referrer nulls Origin on HTML form POSTs; preserve it on our own forms.
    referrerPolicy: { policy: 'same-origin' },
  }));
  app.use((req, res, next) => {
    res.set('Cache-Control', 'no-store');
    res.set('Permissions-Policy', 'camera=(), microphone=(), geolocation=()');
    res.locals = { user: null, csrf: '', currentPath: req.path, title: 'Личный кабинет', errors: {}, values: {}, notice: '' };
    req.webOrigin = originsByHost.get(req.headers.host);
    if (!req.webOrigin) return problem(res, 400, 'Откройте сайт по одному из адресов, указанных при запуске.');
    if (req.get('sec-fetch-site') === 'cross-site') return problem(res, 403, 'Переход с другого сайта заблокирован. Откройте локальный адрес напрямую.');
    next();
  });
  app.use('/assets', express.static(fileURLToPath(new URL('../public/', import.meta.url)), { dotfiles: 'deny', index: false, maxAge: 0 }));
  app.get('/health', (_req, res) => res.json({ status: 'ok', scope: 'web-profile' }));
  app.use(express.urlencoded({ extended: false, limit: '8kb', parameterLimit: 8, inflate: false }));
  app.use((req, res, next) => {
    req.webSession = store.session(sessionCookie(req.headers.cookie));
    if (req.webSession?.user_id) {
      req.user = store.profile(req.webSession.user_id);
      if (!req.user) { store.revokeSession(req.webSession.token_hash); req.webSession = null; }
    }
    res.locals.user = req.user || null;
    res.locals.csrf = req.webSession?.csrf || '';
    next();
  });

  function problem(res, status, message) {
    return res.status(status).render('error', { title: 'Не получилось', status, message });
  }
  function allowed(req, res, key, maximum, windowMs) {
    const decision = store.limit(key, maximum, windowMs);
    if (decision.allowed) return true;
    res.set('Retry-After', String(decision.retryAfter));
    problem(res, 429, `Слишком много попыток. Повторите через ${Math.ceil(decision.retryAfter / 60)} мин.`);
    return false;
  }
  function setSession(req, res, userId) {
    const session = store.createSession(userId, req.webSession?.token_hash);
    res.cookie('web_sid', session.raw, { ...cookieOptions, maxAge: session.ttl });
    req.webSession = session;
    res.locals.csrf = session.csrf;
  }
  function formSession(req, res, next) {
    if (!req.webSession) {
      if (!allowed(req, res, `forms:${req.ip}`, 60, 60 * MINUTE)) return;
      setSession(req, res, null);
    }
    next();
  }
  function requireUser(req, res, next) {
    if (!req.user) {
      if (req.path.startsWith('/api/')) return res.status(401).json({ error: 'authentication_required' });
      return res.redirect(303, '/login?required=1');
    }
    next();
  }
  function csrf(req, res, next) {
    if (!req.is('application/x-www-form-urlencoded')) return problem(res, 415, 'Эта форма принимает только обычные поля.');
    if (req.get('origin') !== req.webOrigin || !req.webSession || !equalToken(req.body?.csrf, req.webSession.csrf)) {
      return problem(res, 403, 'Срок действия формы истёк или запрос не подтверждён. Откройте форму заново и повторите.');
    }
    next();
  }
  function fields(kind) {
    return (req, res, next) => {
      if (Object.keys(req.body).some(name => !fieldNames[kind].includes(name))
        || Object.values(req.body).some(value => typeof value !== 'string')) {
        return problem(res, 400, 'В форме есть неподдерживаемые или повторяющиеся поля.');
      }
      next();
    };
  }
  const loggedInRedirect = (req, res, next) => req.user ? res.redirect(303, '/account') : next();
  const renderAuth = (res, kind, status = 200, errors = {}, values = {}) =>
    res.status(status).render('auth', { title: kind === 'register' ? 'Создать аккаунт' : 'Войти', kind, errors, values });

  app.get('/', formSession, (_req, res) => res.render('home', { title: 'Главная', catalogCounts }));
  registerCatalogRoutes(app, problem);
  app.get('/register', loggedInRedirect, formSession, (_req, res) => renderAuth(res, 'register'));
  app.get('/login', loggedInRedirect, formSession, (req, res) => {
    res.locals.notice = req.query.required === '1' ? 'Войдите, чтобы открыть личный кабинет.' : req.query.logged_out === '1' ? 'Вы вышли из аккаунта.' : '';
    renderAuth(res, 'login');
  });
  app.post('/register', loggedInRedirect, csrf, fields('register'), async (req, res) => {
    if (!allowed(req, res, `register:${req.ip}`, 5, 60 * MINUTE)) return;
    const nickname = nicknameField(req.body.nickname);
    const email = emailField(req.body.email);
    const displayName = textField(req.body.display_name ?? nickname?.display, 2, 48);
    const errors = {};
    if (!nickname) errors.nickname = 'Ник: 3–24 символа, латинские или русские буквы, цифры и _.';
    if (!email) errors.email = 'Укажите почту латинскими символами, например player@example.com.';
    if (!displayName) errors.display_name = 'Укажите имя от 2 до 48 символов без служебных знаков.';
    if (!validPassword(req.body.password)) errors.password = 'От 15 до 128 символов. Подойдёт длинная фраза.';
    if (req.body.password_confirm !== req.body.password) errors.password_confirm = 'Пароли не совпадают.';
    const values = { email: req.body.email, nickname: req.body.nickname, display_name: req.body.display_name };
    if (Object.keys(errors).length) return renderAuth(res, 'register', 422, errors, values);
    const duplicate = () => store.findUser(nickname.key) ? { nickname: 'Этот ник уже занят. Выберите другой.' }
      : store.findByEmail(email) ? { email: 'Эта почта уже зарегистрирована. Войдите в аккаунт.' } : null;
    let conflict = duplicate();
    if (conflict) return renderAuth(res, 'register', 409, conflict, values);
    const hash = await hashPassword(req.body.password);
    // Another request may have registered either key while scrypt was running.
    conflict = duplicate();
    if (conflict) return renderAuth(res, 'register', 409, conflict, values);
    const user = store.createUser({ nickname, email, displayName, passwordHash: hash });
    setSession(req, res, user.id);
    return res.redirect(303, '/account?welcome=1');
  });
  app.post('/login', loggedInRedirect, csrf, fields('login'), async (req, res) => {
    if (!allowed(req, res, `login-ip:${req.ip}`, 30, 15 * MINUTE)) return;
    const email = emailField(req.body.email);
    if (email && !allowed(req, res, `login-email:${email}`, 5, 15 * MINUTE)) return;
    const user = email ? store.findByEmail(email) : null;
    const eligible = validPassword(req.body.password);
    // Unknown users and invalid inputs still perform the same bounded KDF work.
    const matches = await verifyPassword(eligible ? req.body.password : 'invalid-password-input', user?.password_hash || dummyHash);
    if (!user || !eligible || !matches) return renderAuth(res, 'login', 401, { form: 'Неверная почта или пароль.' }, { email: req.body.email });
    store.login(user.id);
    setSession(req, res, user.id);
    return res.redirect(303, '/account');
  });
  app.get('/account', requireUser, async (req, res) => {
    res.render('account', {
      title: 'Мой профиль', game: await readGameOverview(req.user.id),
      values: req.user, saved: req.query.saved === '1', welcome: req.query.welcome === '1',
    });
  });
  app.post('/account/profile', requireUser, csrf, fields('profile'), async (req, res) => {
    if (!allowed(req, res, `profile:${req.user.id}`, 30, MINUTE)) return;
    const displayName = textField(req.body.display_name, 2, 48);
    const bio = textField(req.body.bio, 0, 240);
    const errors = {};
    if (!displayName) errors.display_name = 'Имя должно содержать от 2 до 48 символов без служебных знаков.';
    if (bio === null) errors.bio = 'До 240 символов, одной строкой, без служебных знаков.';
    if (Object.keys(errors).length) return res.status(422).render('account', {
      title: 'Мой профиль', game: await readGameOverview(req.user.id),
      values: { display_name: req.body.display_name, bio: req.body.bio }, errors, saved: false, welcome: false,
    });
    if (store.updateProfile(req.user.id, displayName, bio) !== 1) throw new Error('Profile update failed');
    return res.redirect(303, '/account?saved=1#profile');
  });
  app.post('/account/email', requireUser, csrf, fields('email'), async (req, res) => {
    if (!allowed(req, res, `bind-email:${req.user.id}`, 5, 15 * MINUTE)) return;
    const email = emailField(req.body.email);
    const eligible = validPassword(req.body.current_password);
    const matches = await verifyPassword(eligible ? req.body.current_password : 'invalid-password-input',
      store.passwordRecord(req.user.id).password_hash);
    if (!eligible || !matches) return problem(res, 401, 'Текущий пароль не подошёл.');
    if (!email) return problem(res, 422, 'Укажите корректную почту латинскими символами.');
    try { store.bindEmail(req.user.id, email); }
    catch (error) {
      if (['email_taken', 'already_bound'].includes(error.code)) return problem(res, 409,
        'Эту почту нельзя привязать: адрес уже занят или у аккаунта уже есть другой адрес.');
      throw error;
    }
    return res.redirect(303, '/account?email_bound=1#email');
  });
  app.post('/logout', requireUser, csrf, (req, res) => {
    store.revokeSession(req.webSession.token_hash);
    res.clearCookie('web_sid', cookieOptions);
    res.redirect(303, '/login?logged_out=1');
  });
  app.get('/api/profile', requireUser, (req, res) => res.json({ schemaVersion: 'web-profile.v2', profile: {
    id: req.user.id, username: req.user.username, nickname: req.user.display_nickname, email: req.user.email, displayName: req.user.display_name,
    bio: req.user.bio, createdAt: new Date(req.user.created_at).toISOString(),
    updatedAt: new Date(req.user.updated_at).toISOString(),
  } }));
  app.get('/api/game', requireUser, async (req, res) => res.json(await readGameOverview(req.user.id)));
  app.use((_req, res) => problem(res, 404, 'Такой страницы нет. Вернитесь на главную или в личный кабинет.'));
  app.use((error, _req, res, _next) => {
    const safeStatuses = [400, 413, 415, 503];
    const status = safeStatuses.includes(error.status) ? error.status : 500;
    // No request bodies, cookies, identifiers, password hashes or raw exception messages.
    if (status === 500) console.error('web_request_failed: internal_error');
    if (status === 503) res.set('Retry-After', '3');
    problem(res, status, status === 413 ? 'Форма слишком большая. Сократите поля и повторите.'
      : status === 503 ? 'Сервис занят. Подождите несколько секунд и повторите.'
      : status === 500 ? 'Не удалось обработать запрос. Попробуйте ещё раз позже.' : 'Не удалось прочитать форму. Откройте её заново.');
  });
  const cleanup = setInterval(() => store.cleanup(), 5 * MINUTE);
  cleanup.unref();
  return { app, store, close() { clearInterval(cleanup); store.close(); } };
}
