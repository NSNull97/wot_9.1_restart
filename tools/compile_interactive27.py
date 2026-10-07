# -*- coding: utf-8 -*-
"""Compile owned client compatibility sources with the pinned CPython only."""
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
        raise RuntimeError('requires pinned CPython 2.7.3 bytecode compiler')
    if os.path.exists(args.out) or os.path.exists(args.metadata):
        raise RuntimeError('compiled evidence already exists')
    py_compile.compile(args.source, args.out, os.path.basename(args.source), doraise=True)
    with open(args.out, 'rb') as stream:
        payload = stream.read()
    payload = payload[:4] + '\0\0\0\0' + payload[8:]
    with open(args.out, 'wb') as stream:
        stream.write(payload)
    with open(args.source, 'rb') as stream:
        source_sha = hashlib.sha256(stream.read()).hexdigest()
    with open(args.metadata, 'wb') as stream:
        json.dump({'compiler':sys.version, 'source':os.path.basename(args.source),
                   'source_sha256':source_sha, 'pyc_sha256':hashlib.sha256(payload).hexdigest(),
                   'magic':imp.get_magic().encode('hex'), 'source_executed':False}, stream, indent=2)


if __name__ == '__main__':
    main()
