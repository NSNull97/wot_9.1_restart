# -*- coding: utf-8 -*-
"""Project credential boundary for the original #717 login UI (Python 2.7).

Original LoginDispatcher calls password.strip(). Preserve the user's exact
UTF-8 bytes through that specific call, without replacing the dispatcher,
ConnectionManager, transport, callbacks, or authentication result.
"""
import re

try:
    text_type = unicode
except NameError:
    text_type = str


def text(value):
    if isinstance(value, text_type):
        return value
    if isinstance(value, bytes):
        return value.decode('utf8', 'strict')
    raise ValueError('credential must be text')


def canonical_email(value):
    """Match the website's explicit ASCII dot-atom email identity contract."""
    value = text(value)
    # Validate ASCII before trimming so Unicode whitespace is never accepted as
    # an alternate spelling of a website identity.
    value.encode('ascii', 'strict')
    value = value.strip(u' \t\n\r\v\f').lower()
    if len(value) > 254 or value.count('@') != 1:
        raise ValueError('email outside project identity contract')
    local, domain = value.split('@')
    if (not 1 <= len(local) <= 64 or local.startswith('.') or
            local.endswith('.') or '..' in local or
            re.match(r"\A[a-z0-9.!#$%&'*+/=?^_`{|}~-]+\Z", local) is None):
        raise ValueError('invalid email local part')
    labels = domain.split('.')
    if len(labels) < 2 or any(
            not 1 <= len(label) <= 63 or
            re.match(r'\A[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\Z', label) is None
            for label in labels):
        raise ValueError('invalid email domain')
    if re.search(r'[a-z]', labels[-1]) is None:
        raise ValueError('email domain must not be an IP literal')
    return value


def valid_email(value):
    try:
        canonical_email(value)
        return True
    except (UnicodeError, ValueError):
        return False


def password_bytes(value):
    value = text(value)
    encoded = value.encode('utf8', 'strict')
    # UTF-32 counts Unicode scalar values also on narrow Python 2 builds.
    count = len(value.encode('utf-32-le', 'strict')) // 4
    if not 15 <= count <= 128 or len(encoded) > 512:
        raise ValueError('password length outside project credential contract')
    return encoded


def valid_password(value):
    try:
        password_bytes(value)
        return True
    except (UnicodeError, ValueError):
        return False


class ExactPassword(bytes):
    """A real byte string; only the legacy dispatcher's whitespace trim differs."""
    def __new__(cls, value):
        return bytes.__new__(cls, password_bytes(value))

    def strip(self, chars=None):
        if chars is not None:
            raise ValueError('unexpected non-whitespace password transformation')
        return self


def credential_safe_logger(original):
    def log(*args, **kwargs):
        # ConnectionManager formats this message BEFORE calling LOG_DEBUG.
        # Never parse or retain the secret-bearing result in a diagnostic log.
        if args and isinstance(args[0], (bytes, text_type)):
            message = args[0]
            prefix = b'url: ' if isinstance(message, bytes) else u'url: '
            if message.startswith(prefix):
                return original('Project login requested; credential fields redacted')
        return original(*args, **kwargs)
    return log


def install(endpoint, record):
    """Install input-only adaptations before original LoginView is constructed."""
    import sys
    import external_strings_utils
    import ConnectionManager
    external_strings_utils.isAccountLoginValid = valid_email
    external_strings_utils.isPasswordValid = valid_password
    ConnectionManager.LOG_DEBUG = credential_safe_logger(ConnectionManager.LOG_DEBUG)
    from gui.Scaleform.daapi.view.login import LoginView
    dispatcher = sys.modules['gui.Scaleform.daapi.view.login.LoginDispatcher']
    dispatcher.isAccountLoginValid = valid_email
    dispatcher.isPasswordValid = valid_password
    original = LoginView.onLogin

    def submit(view, user, password, host):
        if host != endpoint:
            raise ValueError('project login is restricted to its configured numeric loopback endpoint')
        # Invalid input still reaches the original UI validation/status path.
        # Valid passwords preserve exact bytes through original .strip().
        if valid_email(user):
            # Original ConnectionManager formats a debug tuple before its logger
            # is called. Keep its validated ASCII email as native bytes so a
            # Unicode operand cannot coerce the exact UTF-8 password to ASCII.
            user = canonical_email(user).encode('ascii')
        if valid_password(password):
            password = ExactPassword(password)
        record('project_login_submit', source='original_LoginView.onLogin',
               endpoint=endpoint, credentials_logged=False)
        return original(view, user, password, host)

    LoginView.onLogin = submit
    record('project_auth_compatibility', username='project_email_ascii_up_to_254',
           password='exact_utf8_15_128_scalars_up_to_512_bytes',
           native_extended_length_support='NOT_RUN', secret_logging='redacted',
           transport='original_ConnectionManager.connect')
