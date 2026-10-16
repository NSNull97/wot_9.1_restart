# -*- coding: utf-8 -*-
"""Owned client endpoint policy; pure Python 2.7, no engine or network imports.

lan-test-v1 is a bounded private-network laboratory policy. The absence of this
setting keeps the historical numeric 127.0.0.1 preparation contract.
"""
import re

try:
    string_types = (basestring,)
except NameError:
    string_types = (str,)

POLICY = 'lan-test-v1'
VERSION = 1
DEFAULT_REGISTRATION = 'http://127.0.0.1:3092/register'


def _ascii(value):
    if not isinstance(value, string_types):
        raise ValueError('endpoint policy requires text')
    try:
        value.encode('ascii', 'strict')
    except UnicodeError:
        raise ValueError('endpoint policy requires ASCII text')
    return value


def validate_endpoint(endpoint, policy=None):
    endpoint = _ascii(endpoint)
    if policy is None:
        if (re.match(r'\A127\.0\.0\.1:[0-9]{1,5}\Z', endpoint) is None
                or not 1024 <= int(endpoint.rsplit(':', 1)[1]) <= 65535):
            raise ValueError('endpoint must be numeric IPv4 loopback with unprivileged port')
        return endpoint
    if not isinstance(policy, string_types) or policy != POLICY:
        raise ValueError('unsupported client network policy')
    if len(endpoint) > 21 or endpoint.count(':') != 1:
        raise ValueError('LAN endpoint must be canonical RFC1918 IPv4:port')
    host, port = endpoint.split(':')
    octets = host.split('.')
    if (len(octets) != 4 or any(
            re.match(r'\A(?:0|[1-9][0-9]{0,2})\Z', part) is None
            or int(part) > 255 for part in octets)
            or re.match(r'\A[1-9][0-9]{3,4}\Z', port) is None
            or not 1024 <= int(port) <= 65535):
        raise ValueError('LAN endpoint must be canonical RFC1918 IPv4:port')
    values = [int(part) for part in octets]
    if not (values[0] == 10 or values[:2] == [192, 168]
            or values[0] == 172 and 16 <= values[1] <= 31):
        raise ValueError('LAN endpoint must be an RFC1918 address')
    return endpoint


def prepare_options(endpoint, policy=None, registration_url=None,
                    profile13=False, mixed_ammo=False):
    endpoint = validate_endpoint(endpoint, policy)
    if policy is not None:
        if profile13 is not True or mixed_ammo is not True:
            raise ValueError('LAN policy requires the explicit profile13/mixed-ammo mode')
        if registration_url not in (None, ''):
            raise ValueError('LAN registration is unavailable; use pre-created own accounts')
        return {'endpoint': endpoint, 'registration_url': '', 'network_policy': POLICY}
    url = DEFAULT_REGISTRATION if registration_url is None else _ascii(registration_url)
    if (re.match(r'\Ahttp://127\.0\.0\.1:[0-9]{1,5}/register\Z', url) is None
            or not 1024 <= int(url.split(':')[2].split('/')[0]) <= 65535):
        raise ValueError('registration URL must be the owned numeric loopback /register route')
    return {'endpoint': endpoint, 'registration_url': url}


def validate_settings(settings):
    policy = settings.get('network_policy')
    validate_endpoint(settings['endpoint'], policy)
    if policy is not None and (settings.get('enable_profile13_battle') is not True
                              or settings.get('enable_p06t_mixed_ammo') is not True):
        raise ValueError('LAN policy requires the explicit profile13/mixed-ammo mode')
    return policy
