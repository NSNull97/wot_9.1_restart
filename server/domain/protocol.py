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
import secrets
import socket
import struct
import time

SCHEMA = "wot091-domain.v1"
# RES-30: one escaped 7..30-row result journal plus header (was 72KiB);
# must equal the gateway domain_client MAX_FRAME (MAX_RESULT_REQUEST + 8192).
MAX_FRAME = 655360 + 8192
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


CAP_REQUEST = b"wot091-domain.v1:camouflage.v1:request\0"
CAP_RESPONSE = b"wot091-domain.v1:camouflage.v1:response\0"
_CAP_HEX = re.compile(r"[0-9a-f]{64}\Z")


def _cap_text(value):
    if type(value) is not str: raise ProtocolError("capability text")
    raw = value.encode("utf-8")
    if len(raw) > MAX_HEADER: raise ProtocolError("capability text bound")
    return struct.pack(">I", len(raw)) + raw


def _cap_optional(value):
    return b"\x00" if value is None else b"\x01" + _cap_text(value)


def capability_request_proof(secret, server_nonce, header, body):
    nonce, generation = header.get("camouflage_nonce"), header.get("camouflage_generation")
    if (type(server_nonce) is not str or not _CAP_HEX.fullmatch(server_nonce)
        or type(nonce) is not str or not _CAP_HEX.fullmatch(nonce)
        or type(generation) is not str or generation != "-" and not _CAP_HEX.fullmatch(generation)
        or type(header.get("id")) is not int or not 1 <= header["id"] < 2**32
        or type(header.get("op")) is not str or type(body) is not bytes):
        raise ProtocolError("capability request shape")
    payload = (CAP_REQUEST + _cap_text(server_nonce) + _cap_text(nonce) + _cap_text(generation)
               + struct.pack(">I", header["id"]) + _cap_text(header["op"])
               + _cap_optional(header.get("account_id")) + _cap_optional(header.get("key"))
               + hashlib.sha256(body).digest())
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def capability_response_proof(secret, request_proof, generation, status, body):
    if (type(request_proof) is not str or not _CAP_HEX.fullmatch(request_proof)
        or type(generation) is not str or generation != "-" and not _CAP_HEX.fullmatch(generation)
        or type(status) is not int or not 0 <= status <= 65535 or type(body) is not bytes):
        raise ProtocolError("capability response shape")
    payload = (CAP_RESPONSE + _cap_text(request_proof) + _cap_text(generation)
               + struct.pack(">H", status) + hashlib.sha256(body).digest())
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


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
        self.secret, self.server_nonce = secret, nonce
        self.last_camouflage_generation = None

    def call(self, op, account_id=None, body=b"", key=None, *, camouflage_generation=None):
        self.serial += 1
        header = {"schema": SCHEMA, "id": self.serial, "op": op, "account_id": account_id, "key": key}
        if camouflage_generation is not None:
            header["camouflage_generation"] = camouflage_generation
            header["camouflage_nonce"] = secrets.token_hex(32)
            header["camouflage_request_proof"] = capability_request_proof(self.secret, self.server_nonce, header, body)
        request_proof = header.get("camouflage_request_proof")
        write_frame(self.stream, header, body)
        header, reply = read_frame(self.stream, self.timeout)
        if header.get("id") != self.serial: raise ProtocolError("reply id")
        if request_proof is not None:
            actual = header.get("camouflage_generation")
            expected = capability_response_proof(self.secret, request_proof, actual, header.get("status"), reply)
            if type(header.get("camouflage_proof")) is not str or not hmac.compare_digest(expected, header["camouflage_proof"]):
                raise ProtocolError("capability response authentication")
            self.last_camouflage_generation = actual
        return header["status"], header.get("error"), reply

    def close(self):
        self.stream.close()

    def __enter__(self): return self
    def __exit__(self, *_): self.close()
