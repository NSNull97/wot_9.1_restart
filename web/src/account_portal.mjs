/** Opt-in portal for identity.account.v1. It has no game database imports. */
import express from 'express';
import helmet from 'helmet';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { timingSafeEqual } from 'node:crypto';
import { createIdentityClient, IdentityError } from '../../server/contracts/identity_client.mjs';

const TOKEN = /^[A-Za-z0-9_-]{43}$/;
const cookieOptions = { httpOnly: true, sameSite: 'strict', secure: false, path: '/' };
const formFields = {
  register: ['csrf', 'email', 'nickname', 'display_name', 'password', 'password_confirm'],
  login: ['csrf', 'email', 'password'],
  profile: ['csrf', 'display_name', 'bio'],
};

function sameToken(left, right) {
  if (typeof left !== 'string' || typeof right !== 'string') return false;
  const a = Buffer.from(left); const b = Buffer.from(right);
  return a.length === b.length && timingSafeEqual(a, b);
}

function cookieValue(header) {
  if (typeof header !== 'string' || header.length > 4096) return null;
  const matches = header.split(';').map(value => value.trim()).filter(value => value.startsWith('web_sid='));
  if (matches.length !== 1) return null;
  const value = matches[0].slice('web_sid='.length);
  return TOKEN.test(value) ? value : null;
}

function escape(value) {
  return String(value ?? '').replace(/[&<>'"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char]));
}

function page(title, body) {
  return `<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escape(title)}</title></head><body><main><h1>${escape(title)}</h1>${body}</main></body></html>`;
}

function message(error) {
  if (error?.code === 'invalid_credentials') return 'Неверная почта или пароль.';
  if (error?.code === 'email_taken') return 'Эта почта уже зарегистрирована.';
  if (error?.code === 'nickname_taken') return 'Этот ник уже занят.';
  if (error?.code === 'invalid_fields') return 'Проверьте поля формы.';
  if (error?.code === 'rate_limited') return 'Слишком много попыток. Повторите позже.';
  if (error?.code === 'invalid_session') return 'Сессия истекла. Откройте форму заново.';
  return 'Сервис авторизации временно недоступен.';
}

function originOf(value) {
  const url = new URL(value);
  if (url.protocol !== 'http:' || url.hostname !== '127.0.0.1' || !url.port || url.pathname !== '/' || url.search || url.hash || url.username || url.password) throw new TypeError('Portal origin must be numeric loopback HTTP');
  return url.origin;
}

export function createAccountPortalApp({ origin, identityOrigin, identitySecret, identityClient, timeoutMs = 2500 } = {}) {
  const portalOrigin = originOf(origin);
  const identity = identityClient || createIdentityClient({ origin: identityOrigin, secret: identitySecret, role: 'portal', timeoutMs });
  const app = express();
  app.disable('x-powered-by');
  app.set('trust proxy', false);
  app.use(helmet({ strictTransportSecurity: false, contentSecurityPolicy: { useDefaults: false, directives: {
    defaultSrc: ["'none'"], styleSrc: ["'unsafe-inline'"], imgSrc: ["'self'"], formAction: ["'self'"], frameAncestors: ["'none'"], objectSrc: ["'none'"], baseUri: ["'none'"],
  } } }));
  app.use((req, res, next) => {
    res.set('Cache-Control', 'no-store');
    res.set('Permissions-Policy', 'camera=(), microphone=(), geolocation=()');
    if (req.headers.host !== new URL(portalOrigin).host || req.get('sec-fetch-site') === 'cross-site') return res.status(403).send(page('Запрос отклонён', '<p>Откройте локальный адрес напрямую.</p>'));
    next();
  });
  app.get('/health', (_req, res) => res.json({ status: 'ok', scope: 'identity-account-portal', contract: 'identity.account.v1' }));
  app.use(express.urlencoded({ extended: false, limit: '8kb', parameterLimit: 8, inflate: false }));

  async function session(req, res, next) {
    try {
      const raw = cookieValue(req.headers.cookie);
      const value = raw ? await identity.call('session/read', { session_token: raw }) : await identity.call('session/open', { session_token: null });
      req.identitySession = value;
      if (!raw) res.cookie('web_sid', value.session_token, { ...cookieOptions, maxAge: Math.max(1, value.expires_at - Date.now()) });
      res.locals = { csrf: value.csrf, profile: value.profile };
      next();
    } catch (error) {
      if (error instanceof IdentityError && error.code === 'invalid_session') return res.status(401).send(page('Сессия истекла', '<p>Откройте вход заново.</p><p><a href="/login">Войти</a></p>'));
      return res.status(503).send(page('Авторизация недоступна', '<p>Попробуйте позже.</p>'));
    }
  }
  function csrf(req, res, next) {
    if (req.get('origin') !== portalOrigin || !req.identitySession || !sameToken(req.body?.csrf, req.identitySession.csrf)) return res.status(403).send(page('Запрос отклонён', '<p>Форма устарела. Откройте её заново.</p>'));
    next();
  }
  function fields(kind) {
    return (req, res, next) => {
      const allowed = formFields[kind];
      if (!allowed || Object.keys(req.body || {}).some(name => !allowed.includes(name)) || Object.values(req.body || {}).some(value => typeof value !== 'string')) return res.status(400).send(page('Неверная форма', '<p>Есть неподдерживаемые поля.</p>'));
      next();
    };
  }
  const form = (kind, csrfToken, values = {}, error = '') => {
    const registration = kind === 'register';
    const fieldsHtml = registration
      ? `<label>Почта <input name="email" value="${escape(values.email)}" autocomplete="email" required></label><label>Ник <input name="nickname" value="${escape(values.nickname)}" required></label><label>Имя <input name="display_name" value="${escape(values.display_name)}" required></label>`
      : '<label>Почта <input name="email" autocomplete="email" required></label>';
    return page(registration ? 'Создать аккаунт' : 'Войти', `${error ? `<p role="alert">${escape(error)}</p>` : ''}<form method="post" action="/${registration ? 'register' : 'login'}"><input type="hidden" name="csrf" value="${escape(csrfToken)}">${fieldsHtml}<label>Пароль <input type="password" name="password" autocomplete="${registration ? 'new-password' : 'current-password'}" required></label>${registration ? '<label>Пароль ещё раз <input type="password" name="password_confirm" autocomplete="new-password" required></label>' : ''}<button type="submit">${registration ? 'Создать' : 'Войти'}</button></form><p><a href="/${registration ? 'login' : 'register'}">${registration ? 'Уже есть аккаунт' : 'Создать аккаунт'}</a></p>`);
  };
  function requireProfile(req, res, next) { if (!req.identitySession?.profile) return res.redirect(303, '/login'); next(); }

  app.get('/', session, (req, res) => res.redirect(303, req.identitySession.profile ? '/account' : '/login'));
  app.get('/register', session, (req, res) => res.send(form('register', req.identitySession.csrf)));
  app.get('/login', session, (req, res) => res.send(form('login', req.identitySession.csrf)));
  app.post('/register', session, csrf, fields('register'), async (req, res) => {
    if (req.body.password !== req.body.password_confirm) return res.status(422).send(form('register', req.identitySession.csrf, req.body, 'Пароли не совпадают.'));
    try {
      const value = await identity.call('register', { session_token: req.identitySession.session_token, csrf: req.identitySession.csrf, email: req.body.email, nickname: req.body.nickname, display_name: req.body.display_name, password: req.body.password });
      res.cookie('web_sid', value.session_token, { ...cookieOptions, maxAge: Math.max(1, value.expires_at - Date.now()) });
      return res.redirect(303, '/account');
    } catch (error) { const status = error instanceof IdentityError && [409, 422, 429].includes(error.status) ? error.status : error.code === 'invalid_credentials' ? 401 : 503; return res.status(status).send(form('register', req.identitySession.csrf, req.body, message(error))); }
  });
  app.post('/login', session, csrf, fields('login'), async (req, res) => {
    try {
      const value = await identity.call('login', { session_token: req.identitySession.session_token, csrf: req.identitySession.csrf, email: req.body.email, password: req.body.password });
      res.cookie('web_sid', value.session_token, { ...cookieOptions, maxAge: Math.max(1, value.expires_at - Date.now()) });
      return res.redirect(303, '/account');
    } catch (error) { const status = error instanceof IdentityError && [401, 429].includes(error.status) ? error.status : 503; return res.status(status).send(form('login', req.identitySession.csrf, req.body, message(error))); }
  });
  app.get('/account', session, requireProfile, (req, res) => {
    const p = req.identitySession.profile;
    res.send(page('Личный кабинет', `<p>Ник: ${escape(p.nickname)}</p><p>Почта: ${escape(p.email)}</p><p>Игровой профиль: <strong>not_connected</strong></p><form method="post" action="/profile"><input type="hidden" name="csrf" value="${escape(req.identitySession.csrf)}"><label>Имя <input name="display_name" value="${escape(p.display_name)}" required></label><label>О себе <textarea name="bio">${escape(p.bio)}</textarea></label><button type="submit">Сохранить</button></form><form method="post" action="/logout"><input type="hidden" name="csrf" value="${escape(req.identitySession.csrf)}"><button type="submit">Выйти</button></form>`));
  });
  app.post('/profile', session, requireProfile, csrf, fields('profile'), async (req, res) => {
    try { await identity.call('profile/update', { session_token: req.identitySession.session_token, csrf: req.identitySession.csrf, display_name: req.body.display_name, bio: req.body.bio }); return res.redirect(303, '/account'); }
    catch (error) { return res.status(error instanceof IdentityError && error.status === 422 ? 422 : 503).send(page('Профиль не сохранён', `<p>${escape(message(error))}</p><p><a href="/account">Назад</a></p>`)); }
  });
  app.post('/logout', session, requireProfile, csrf, async (req, res) => { try { await identity.call('session/revoke', { session_token: req.identitySession.session_token, csrf: req.identitySession.csrf }); } catch { /* revocation failure is surfaced as unavailable below */ return res.status(503).send(page('Сервис недоступен', '<p>Повторите выход позже.</p>')); } res.clearCookie('web_sid', cookieOptions); res.redirect(303, '/login'); });
  app.get('/api/profile', session, requireProfile, (req, res) => res.json({ schemaVersion: 'identity.account.v1', profile: req.identitySession.profile }));
  app.use((_req, res) => res.status(404).send(page('Страница не найдена', '<p><a href="/">На главную</a></p>')));
  return { app, identity };
}

export { cookieValue };
