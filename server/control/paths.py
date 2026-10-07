"""Small server-owned path/read helpers; no dependency on client audit/config."""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAX_FILE = 64 * 1024 * 1024


def sha256(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_limited(path: Path, maximum=MAX_FILE) -> bytes:
    if path.stat().st_size > maximum:
        raise ValueError(f'file too large: {path}')
    with path.open('rb') as stream:
        data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError('file grew beyond limit')
    return data
