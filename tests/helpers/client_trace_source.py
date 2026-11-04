"""Trusted client patch functions for the AST-extraction tests, wherever REFACTOR R7 put them.

The diagnostic profiler moved from client_patch/sr_interactive.py to
client_patch/native_call_trace.py; there it reads host values as `_host.X`.
Tests keep one flat namespace of stubs: `bind_host` makes `_host` a live view
of that same namespace, so a stub set or changed later is what the code sees.
Python 2 compatible (test_ms1_ammo_profile also runs on CPython 2.7).
"""
import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SOURCES = tuple(os.path.join(ROOT, 'client_patch', name) for name in ('sr_interactive.py', 'native_call_trace.py'))


class LiveHost(object):
    """The `_host` the moved profiler reads: the test's own namespace, live."""

    def __init__(self, namespace):
        object.__setattr__(self, '_namespace', namespace)

    def __getattr__(self, name):
        try:
            return self._namespace[name]
        except KeyError:
            raise AttributeError(name)


def nodes(names):
    """Top-level function definitions with these names, from both sources; each exactly once."""
    found = []
    for path in SOURCES:
        with open(path, 'rb') as stream:
            tree = ast.parse(stream.read(), filename=path)
        found += [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    if sorted(node.name for node in found) != sorted(names):
        raise AssertionError('expected each trusted client function exactly once: %r' % sorted(names))
    return found


def bind_host(namespace):
    namespace['_host'] = LiveHost(namespace)
    return namespace
