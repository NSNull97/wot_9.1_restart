"""Project Sixth Sense lamp bank (owner order 2026-10-20), not original #717.

The 0.9.1 client has no lamp sound (P07B VERIFIED). The project cue plays the
existing GUI event gun_intuition, whose one-sample FSB5 bank is replaced in
res_mods by the owner's sample. The original bank fixes the format: FSB5 v1,
one mono IMA ADPCM sample (codec 7) at 48 kHz, 36-byte blocks of 64 samples,
one loop chunk and a 48-byte name table. Only the sample data, count and loop
end change; the header hash area and name table are copied unchanged.
"""
import shutil
import struct
import subprocess
from pathlib import Path

RATE = 48000
FREQUENCY_INDEX = 9  # FSB5 rate table: 9 = 48000 Hz (original bank)
CODEC_IMA = 7
MAX_SECONDS = 5
MAX_SOURCE_BYTES = 8 * 1024 * 1024
HEADER = 60
STEP = [7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97,
        107, 118, 130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796,
        876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428,
        4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487, 12635, 13899, 15289, 16818, 18500, 20350,
        22385, 24623, 27086, 29794, 32767]
INDEX = [-1, -1, -1, -1, 2, 4, 6, 8] * 2


def _nibble(pred, idx, code):
    step = STEP[idx]; diff = step >> 3
    if code & 1: diff += step >> 2
    if code & 2: diff += step >> 1
    if code & 4: diff += step
    if code & 8: diff = -diff
    return max(-32768, min(32767, pred + diff)), max(0, min(88, idx + INDEX[code]))


def ima_encode(samples):
    """Mono IMA: per 36-byte block int16 predictor, step index, 0, 32 bytes low-nibble-first."""
    out = bytearray(); pred, idx = 0, 0
    for start in range(0, len(samples), 64):
        block = list(samples[start:start + 64]); block += [block[-1]] * (64 - len(block))
        out += struct.pack('<hBB', pred, idx, 0); codes = []
        for value in block:
            step = STEP[idx]; diff = value - pred; code = 0
            if diff < 0: code = 8; diff = -diff
            if diff >= step: code |= 4; diff -= step
            if diff >= step >> 1: code |= 2; diff -= step >> 1
            if diff >= step >> 2: code |= 1
            pred, idx = _nibble(pred, idx, code); codes.append(code)
        out += bytes(codes[i] | (codes[i + 1] << 4) for i in range(0, 64, 2))
    return bytes(out)


def ima_decode(data):
    out = []
    for start in range(0, len(data) - 35, 36):
        pred, idx = struct.unpack_from('<hB', data, start)
        if idx > 88 or data[start + 3] != 0:
            raise ValueError('IMA block header')
        for byte in data[start + 4:start + 36]:
            for code in (byte & 15, byte >> 4):
                pred, idx = _nibble(pred, idx, code); out.append(pred)
    return out


def parse(raw):
    """Closed parse of the original one-sample mono IMA FSB5 v1 bank."""
    if len(raw) < HEADER or raw[:4] != b'FSB5':
        raise ValueError('FSB5 signature')
    version, count, shdr, names, size, codec = struct.unpack_from('<6I', raw, 4)
    if (version, count, shdr, codec) != (1, 1, 20, CODEC_IMA) or len(raw) != HEADER + shdr + names + size:
        raise ValueError('closed FSB5 v1 one-sample IMA bank required')
    packed, = struct.unpack_from('<Q', raw, HEADER)
    extra, freq, channels, offset, samples = packed & 1, (packed >> 1) & 15, ((packed >> 5) & 1) + 1, \
        ((packed >> 6) & 0xfffffff) * 32, packed >> 34
    chunk, = struct.unpack_from('<I', raw, HEADER + 8)
    if (extra, freq, channels, offset) != (1, FREQUENCY_INDEX, 1, 0) or chunk & 1 or chunk >> 25 != 3 \
            or (chunk >> 1) & 0xffffff != 8:
        raise ValueError('closed mono 48 kHz sample with one loop chunk required')
    loop = struct.unpack_from('<II', raw, HEADER + 12)
    if samples * 36 // 64 > size or loop[0] != 0 or loop[1] >= samples:
        raise ValueError('sample/loop bounds')
    return dict(hash_area=raw[28:HEADER], names=raw[HEADER + shdr:HEADER + shdr + names], samples=samples,
                loop=loop, data=raw[HEADER + shdr + names:])


def build(original, pcm):
    """Same header hash area/name table; new IMA data, count and loop end."""
    head = parse(original)
    if not 1 <= len(pcm) <= RATE * MAX_SECONDS:
        raise ValueError('lamp sample length bound')
    data = ima_encode(pcm); samples = len(data) // 36 * 64
    data += b'\0' * (-len(data) % 32)
    packed = 1 | (FREQUENCY_INDEX << 1) | (0 << 5) | (0 << 6) | (samples << 34)
    sample = struct.pack('<QIII', packed, (3 << 25) | (8 << 1), 0, samples - 1)
    header = b'FSB5' + struct.pack('<6I', 1, 1, len(sample), len(head['names']), len(data), CODEC_IMA) + head['hash_area']
    return header + sample + head['names'] + data


def decode_source(path, ffmpeg=None):
    """Owner-supplied file -> mono 48 kHz int16 via a bounded local ffmpeg run."""
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError('bounded local lamp source file required')
    tool = ffmpeg or shutil.which('ffmpeg')
    if not tool:
        raise ValueError('ffmpeg is required to decode the lamp source')
    run = subprocess.run([tool, '-v', 'error', '-nostdin', '-i', str(path), '-t', str(MAX_SECONDS), '-ac', '1',
                          '-ar', str(RATE), '-f', 's16le', '-'], capture_output=True, timeout=30, check=True)
    raw = run.stdout
    if not raw or len(raw) % 2 or len(raw) > RATE * MAX_SECONDS * 2:
        raise ValueError('decoded lamp PCM bound')
    return list(struct.unpack('<%dh' % (len(raw) // 2), raw))
