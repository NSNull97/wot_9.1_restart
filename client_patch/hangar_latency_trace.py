# -*- coding: utf-8 -*-
"""Opt-in #717 timing markers. They observe calls; they do not drive the UI.

All timestamps are supplied by sr_interactive's existing Windows monotonic
clock. No command arguments, reply payloads, accounts or credentials are read.
"""
import hashlib

try:
    _integer_types = (int, long)
except NameError:
    _integer_types = (int,)

_PINS = {
    '__doCmd': (1523, 'efb40e1d1742e98179a41a6d907f06ec749d64f1e6419c414fe702535f42ec36'),
    '_update': (1451, 'dae41b7ea6209f0983a647174802481619919ee942282786430a5a7b3c7cf0ce'),
    'onCmdResponse': (291, '456efcbc74df714d8411d19391f98b90a58b2acf70b1f4c0dfa9139f91030a2b'),
    'onCmdResponseExt': (302, '37edde4729913fbb2b7fb9bc1069259ac54a9416218061eaca5166e6cb8aec48'),
}
_MAX_EVENTS = 4096
_events = 0
_truncated = False
_disabled = False


def _integer(value, minimum, maximum):
    if type(value) not in _integer_types or not minimum <= value <= maximum:
        return None
    return int(value)


def observe(frame, phase, record):
    """Record bounded metadata for verified original Account functions only.

    A __doCmd return is an application-level marker, not proof of packet send.
    Likewise response return is not proof that the visible indicator closed.
    """
    global _events, _truncated, _disabled
    if _disabled:
        return
    code = frame.f_code
    if (code.co_filename != 'scripts/client/Account.py' or code.co_name not in _PINS
            or phase not in ('call', 'return')
            or code.co_name == '__doCmd' and phase != 'return'):
        return
    line, digest = _PINS[code.co_name]
    if code.co_firstlineno != line or hashlib.sha256(code.co_code).hexdigest() != digest:
        # A diagnostic source mismatch must be visible without propagating out
        # of sys.setprofile and disabling unrelated profiling or game logic.
        _disabled = True
        record('hangar_latency_trace_source_mismatch', method=code.co_name,
               expected_line=line, observed_line=code.co_firstlineno,
               observer_disabled=True)
        return
    if _events >= _MAX_EVENTS:
        if not _truncated:
            _truncated = True
            record('hangar_latency_trace_truncated', limit=_MAX_EVENTS)
        return
    values = frame.f_locals
    fields = {'method': code.co_name, 'phase': phase}
    if code.co_name == '__doCmd':
        command = _integer(values.get('cmd'), 0, 32767)
        if command is None:
            return
        fields['command'] = command
        fields['request_id'] = _integer(values.get('requestID'), 1, 32767)
    elif code.co_name in ('onCmdResponse', 'onCmdResponseExt'):
        fields['request_id'] = _integer(values.get('requestID'), 1, 32767)
        fields['result_id'] = _integer(values.get('resultID'), -32768, 32767)
    else:
        diff = values.get('diff')
        if type(diff) is dict:
            fields['revision'] = _integer(diff.get('rev'), 0, 2147483647)
            fields['previous_revision'] = _integer(diff.get('prevRev'), 0, 2147483647)
    _events += 1
    record('hangar_latency_native', **fields)
