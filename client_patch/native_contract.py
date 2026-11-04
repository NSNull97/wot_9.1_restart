"""The exact #717 method a project module wraps: file, name, first line, arguments, bytecode.

Client-side (CPython 2.7 in #717) and in the Python 3 tests. A module records the
facts of each native method it wraps and refuses to install on any difference,
so a different client build keeps its own behaviour instead of a wrong wrapper.
The modules import it inside their check: prepare loads them by file path for
their settings, without client_patch on sys.path, and never runs the check.
"""
import hashlib


def check(function, filename, name, line, args, digest, what, flags=True):
    """Raise RuntimeError('original #717 <what> differs: <name>') unless the
    function is that native one. `flags`: also refuse *args/**kwargs."""
    code = getattr(function, 'func_code', getattr(function, '__code__', None))
    if (code is None or code.co_filename.replace('\\', '/') != filename or code.co_name != name
            or code.co_firstlineno != line or code.co_argcount != len(args)
            or tuple(code.co_varnames[:len(args)]) != args or (flags and code.co_flags & 12)
            or hashlib.sha256(code.co_code).hexdigest() != digest):
        raise RuntimeError('original #717 %s differs: %s' % (what, name))
