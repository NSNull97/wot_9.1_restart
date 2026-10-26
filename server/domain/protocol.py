"""Bounded loopback framing for the Domain/Account service (schema wot091-domain.v1).

frame   = u32 BE length (1..MAX_FRAME) || payload
payload = u16 BE header length (1..MAX_HEADER) || header || body

The header is a flat ASCII JSON object with unique keys; the body is opaque
bytes (the same request/reply JSON the bridge carried). Nothing here executes
or imports decoded data. Authentication is an HMAC-SHA256 challenge over the
per-process shared secret; it binds a loopback peer to the operator's secret
file, it does not encrypt (loopback only).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import socket
import struct
import time

SCHEMA = "wot091-domain.v1"
MAX_FRAME = 73728
MAX_HEADER = 1024
MAX_HEADER_FIELDS = 8
SECRET_LENGTH = 43
_SECRET = re.compile(rb"[A-Za-z0-9_-]{43}\Z")
_PROOF_PREFIX = (SCHEMA + ":").encode("ascii")


class ProtocolError(ValueError):
    """Malformed, oversized or unauthenticated traffic; the connection is closed."""


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value: raise ProtocolError("duplicate header field")
        value[key] = item
    return value


def encode(header, body=b""):
    if type(body) is not bytes: raise ProtocolError("body bytes")
    raw = json.dumps(header, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")
    if not 0 < len(raw) <= MAX_HEADER or 2 + len(raw) + len(body) > MAX_FRAME: raise ProtocolError("frame bound")
    return struct.pack(">H", len(raw)) + raw + body


def decode(payload):
    if type(payload) is not bytes or len(payload) < 3: raise ProtocolError("payload bound")
    (size,) = struct.unpack(">H", payload[:2])
    if not 0 < size <= MAX_HEADER or 2 + size > len(payload): raise ProtocolError("header bound")
    raw = payload[2:2 + size]
    if not raw.isascii(): raise ProtocolError("header encoding")
    try:
        header = json.loads(raw, object_pairs_hook=_unique, parse_constant=lambda _: _fail("nonfinite"))
    except (UnicodeError, RecursionError, json.JSONDecodeError) as error:
        raise ProtocolError("header JSON") from error
    if type(header) is not dict or len(header) > MAX_HEADER_FIELDS: raise ProtocolError("header object")
    for value in header.values():
        if value is not None and type(value) not in (str, int, bool): raise ProtocolError("flat header")
        if type(value) is str and len(value) > 256: raise ProtocolError("header string bound")
    if header.get("schema") != SCHEMA: raise ProtocolError("schema")
    return header, payload[2 + size:]


def _fail(message):
    raise ProtocolError(message)


def _receive(stream, count, deadline):
    parts, need = [], count
    while need:
        remaining = deadline - time.monotonic()
        if remaining <= 0: raise ProtocolError("frame deadline")
        stream.settimeout(remaining)
        try: part = stream.recv(min(need, 65536))
        except socket.timeout as error: raise ProtocolError("frame deadline") from error
        if not part: raise ConnectionError("peer closed")
        parts.append(part); need -= len(part)
    return b"".join(parts)


def read_frame(stream, timeout):
    """One complete frame within ``timeout`` seconds; EOF before a length is ConnectionError."""
    deadline = time.monotonic() + timeout
    (length,) = struct.unpack(">I", _receive(stream, 4, deadline))
    if not 0 < length <= MAX_FRAME: raise ProtocolError("frame length")
    return decode(_receive(stream, length, deadline))


def write_frame(stream, header, body=b""):
    payload = encode(header, body)
    stream.sendall(struct.pack(">I", len(payload)) + payload)


def load_secret(path):
    with open(path, "rb") as stream: raw = stream.read(SECRET_LENGTH + 1)
    if not _SECRET.fullmatch(raw): raise ProtocolError("secret must be exactly 43 base64url characters")
    return raw


def proof(secret, nonce_hex):
    return hmac.new(secret, _PROOF_PREFIX + nonce_hex.encode("ascii"), hashlib.sha256).hexdigest()


def proof_matches(secret, nonce_hex, value):
    return type(value) is str and hmac.compare_digest(proof(secret, nonce_hex), value)


class Client:
    """Synchronous client (tests, benches, the bridge's Python peers)."""

    def __init__(self, address, secret, timeout=20.0):
        self.timeout = timeout
        self.stream = socket.create_connection(address, timeout=min(timeout, 2.0))
        self.stream.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        challenge, _ = read_frame(self.stream, 5.0)
        nonce = challenge.get("nonce")
        if type(nonce) is not str or not re.fullmatch(r"[0-9a-f]{64}", nonce): raise ProtocolError("challenge")
        write_frame(self.stream, {"schema": SCHEMA, "op": "hello", "proof": proof(secret, nonce)})
        ready, _ = read_frame(self.stream, 5.0)
        if ready.get("status") != 200: raise ProtocolError("authentication refused")
        self.serial = 0

    def call(self, op, account_id=None, body=b"", key=None):
        self.serial += 1
        write_frame(self.stream, {"schema": SCHEMA, "id": self.serial, "op": op, "account_id": account_id, "key": key}, body)
        header, reply = read_frame(self.stream, self.timeout)
        if header.get("id") != self.serial: raise ProtocolError("reply id")
        return header["status"], header.get("error"), reply

    def close(self):
        self.stream.close()

    def __enter__(self): return self
    def __exit__(self, *_): self.close()
