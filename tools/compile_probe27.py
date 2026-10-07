# -*- coding: utf-8 -*-
"""Run only under pinned CPython 2.7.3 to compile our own diagnostic source.

No incoming network data, client bytecode loading, or source execution.
"""
import argparse
import hashlib
import imp
import json
import os
import py_compile
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--metadata', required=True)
    args = parser.parse_args()
    if sys.version_info[:3] != (2, 7, 3) or imp.get_magic() != '\x03\xf3\x0d\x0a':
        raise RuntimeError('requires CPython 2.7.3 / expected pyc magic')
    if os.path.exists(args.out) or os.path.exists(args.metadata):
        raise RuntimeError('refusing to overwrite compiled evidence')
    py_compile.compile(args.source, args.out, 'p01_probe.py', doraise=True)
    with open(args.out, 'rb') as stream:
        payload = stream.read()
    payload = payload[:4] + '\0\0\0\0' + payload[8:]
    with open(args.out, 'wb') as stream:
        stream.write(payload)
    with open(args.source, 'rb') as stream:
        source_hash = hashlib.sha256(stream.read()).hexdigest()
    with open(args.metadata, 'wb') as stream:
        json.dump({'compiler': sys.version, 'executable': sys.executable,
            'magic': imp.get_magic().encode('hex'), 'source_sha256': source_hash,
            'pyc_sha256': hashlib.sha256(payload).hexdigest(),
            'source_executed': False, 'header_timestamp': 0}, stream, indent=2)


if __name__ == '__main__':
    main()
