import express from 'express';
import helmet from 'helmet';
import { fileURLToPath } from 'node:url';
import { registerCatalogRoutes, counts } from './catalog.mjs';

// The public demonstration has no account store, session, credentials or game bridge.
export function createDemoApp({ origin }) {
  const address = new URL(origin);
  if (!['http:', 'https:'].includes(address.protocol) || address.origin !== origin
    || address.username || address.password || ['0.0.0.0', '[::]', '*'].includes(address.hostname)) {
    throw new Error('An exact browser origin is required for the catalog demo');
  }
  const app = express();
  app.disable('x-powered-by');
  app.set('trust proxy', false);
  app.set('view engine', 'ejs');
  app.set('views', fileURLToPath(new URL('../views/', import.meta.url)));
  app.use(helmet({
    strictTransportSecurity: false,
    contentSecurityPolicy: { useDefaults: false, directives: {
      defaultSrc: ["'none'"], styleSrc: ["'self'"], imgSrc: ["'self'"],
      fontSrc: ["'self'"], scriptSrc: ["'none'"], connectSrc: ["'none'"],
      baseUri: ["'none'"], formAction: ["'self'"], frameAncestors: ["'none'"], objectSrc: ["'none'"],
    } },
    referrerPolicy: { policy: 'same-origin' },
  }));
  const problem = (res, status, message) => res.status(status).render('error', {
    title: status === 410 ? 'Демонстрация каталога' : 'Не получилось', status, message,
  });
  app.use((req, res, next) => {
    res.locals = { demoMode: true, user: null, csrf: '', currentPath: req.path,
      title: 'Стальной рубеж', errors: {}, values: {}, notice: '' };
    res.set('Permissions-Policy', 'camera=(), microphone=(), geolocation=()');
    if (req.headers.host !== address.host) return problem(res, 400, 'Откройте демонстрацию по её основному адресу.');
    if (req.originalUrl.length > 2048) return problem(res, 414, 'Адрес слишком длинный. Откройте каталог заново.');
    if (!['GET', 'HEAD'].includes(req.method)) {
      res.set('Allow', 'GET, HEAD');
      return problem(res, 405, 'Это демонстрация каталога. Регистрация и изменение аккаунта здесь недоступны.');
    }
    next();
  });
  app.get('/health', (_req, res) => res.json({ status: 'ok', scope: 'catalog-demo', accounts: false, game: false }));
  app.use('/assets', express.static(fileURLToPath(new URL('../public/', import.meta.url)), {
    dotfiles: 'deny', index: false, maxAge: '1h',
  }));
  app.get('/', (_req, res) => res.render('home', { title: 'Главная', catalogCounts: counts }));
  registerCatalogRoutes(app, problem);
  app.get(['/login', '/register', '/account', '/logout'], (_req, res) => problem(res, 410,
    'Здесь открыта демонстрация техники и карт. Вход, регистрация и игровой сервер в эту версию не входят.'));
  app.use('/api', (_req, res) => res.status(404).json({ error: 'catalog_demo_only' }));
  app.use((_req, res) => problem(res, 404, 'Такой страницы нет. Откройте каталог техники или атлас карт.'));
  app.use((error, _req, res, _next) => {
    if (res.headersSent) return _next(error);
    const status = [400, 404].includes(error.status) ? error.status : 500;
    if (status === 500) console.error('catalog_demo_request_failed');
    return problem(res, status, status === 404 ? 'Файл не найден.' : 'Не удалось открыть страницу. Попробуйте ещё раз позже.');
  });
  return app;
}
