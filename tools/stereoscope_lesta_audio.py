"""Prepare the private stereoscope cue from the pinned local Lesta installation.

    python -B tools/stereoscope_lesta_audio.py --lesta D:/Games/Tanki \
        --vgmstream-zip local/toolchains/vgmstream-r2168/vgmstream-win64.zip \
        --out local/ui-borrowed/stereoscope

The WAV and its manifest stay in the ignored local directory. The decoder is
the Windows x64 asset at https://github.com/vgmstream/vgmstream/releases/tag/r2168.
"""

import argparse
import hashlib
import io
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import wave
import zipfile


BANK_PACKAGE = 'audioww-part3.pkg'
BANK_MEMBER = 'audioww/damaged_modules.bnk'
BANK_SIZE = 210835
BANK_SHA256 = 'd35ecf0429ce053f0eaf6555f28c0689708240589f99c24658f4bc5e4818c035'

STREAM_PACKAGE = 'audioww-part1.pkg'
STREAM_MEMBER = 'audioww/streams.pck'
STREAM_SIZE = 31600415
STREAM_HEADER_SIZE = 4720
STREAM_HEADER_SHA256 = 'e64f11c359a63c4fec813b36ced7d0538b1fcfd6b0ca6ebabcd40bdab28ee622'
STREAM_RECORD_OFFSET = 4656
MEDIA_ID = 1064042675
MEDIA_SIZE = 14377
MEDIA_OFFSET = 31473862
WEM_SHA256 = '23a388f7040e51b2d2f66f5c4e99b1e98605c532ea844c3bc4ce6faf50c41747'

DECODER_RELEASE = 'https://github.com/vgmstream/vgmstream/releases/tag/r2168'
DECODER_ZIP_SIZE = 4574355
DECODER_ZIP_SHA256 = '692d45070852a35c1fa42726aa3c9de528e44eec925d37d99b1074256b99a229'
WAV_NAME = 'stereo_trumpet_start.full.wav'
WAV_FRAMES = 29064
WAV_RATE = 48000
WAV_SIZE = 44 + 2 * WAV_FRAMES
WAV_SHA256 = '1e10d0958c1996b8c48131690296f146f8a328d3421016e6acd4af400f02d726'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_wem(lesta):
    """Read the exact stream referenced by the audited bank's play action."""
    packages = Path(lesta) / 'res' / 'packages'
    with zipfile.ZipFile(packages / BANK_PACKAGE) as package:
        member = package.getinfo(BANK_MEMBER)
        if member.file_size != BANK_SIZE or sha(package.read(member)) != BANK_SHA256:
            raise ValueError('Lesta damaged_modules.bnk differs from the audited build')

    with zipfile.ZipFile(packages / STREAM_PACKAGE) as package:
        member = package.getinfo(STREAM_MEMBER)
        if member.file_size != STREAM_SIZE:
            raise ValueError('Lesta streams.pck size differs from the audited build')
        with package.open(member) as stream:
            header = stream.read(STREAM_HEADER_SIZE)
            if header[:8] != struct.pack('<4sI', b'AKPK', STREAM_HEADER_SIZE - 8):
                raise ValueError('unexpected AKPK header')
            if sha(header) != STREAM_HEADER_SHA256:
                raise ValueError('Lesta streams.pck header differs from the audited build')
            record = struct.unpack_from('<5I', header, STREAM_RECORD_OFFSET)
            if record != (MEDIA_ID, 1, MEDIA_SIZE, MEDIA_OFFSET, 0):
                raise ValueError('stereoscope WEM reference differs from the audited build')
            stream.seek(MEDIA_OFFSET)
            media = stream.read(MEDIA_SIZE)

    if len(media) != MEDIA_SIZE or sha(media) != WEM_SHA256:
        raise ValueError('stereoscope WEM differs from the audited build')
    return media


def read_wav(path):
    """Validate and return the exact decoded PCM sample."""
    path = Path(path)
    with path.open('rb') as source:
        raw = source.read(WAV_SIZE + 1)
        if len(raw) != WAV_SIZE or sha(raw) != WAV_SHA256:
            raise ValueError('stereoscope WAV differs from the audited decode')
        source.seek(0)
        with wave.open(source) as audio:
            if audio.getparams()[:5] != (1, 2, WAV_RATE, WAV_FRAMES, 'NONE'):
                raise ValueError('stereoscope WAV must be mono 48 kHz 16-bit PCM')
    return raw


def extract(lesta, decoder_zip, out):
    lesta, decoder_zip, out = Path(lesta).resolve(), Path(decoder_zip), Path(out).resolve()
    audio_path, manifest_path = out / WAV_NAME, out / 'manifest.json'
    if any(lesta == target or lesta in target.parents
           for target in (out, audio_path.resolve(), manifest_path.resolve())):
        raise ValueError('write decoded assets outside the Lesta installation')
    media = read_wem(lesta)
    with decoder_zip.open('rb') as source:
        archive = source.read(DECODER_ZIP_SIZE + 1)
    if len(archive) != DECODER_ZIP_SIZE or sha(archive) != DECODER_ZIP_SHA256:
        raise ValueError('vgmstream archive does not match the published r2168 Windows x64 digest')

    with tempfile.TemporaryDirectory(prefix='wot091-stereoscope-') as folder:
        scratch = Path(folder)
        source = scratch / 'stereo_trumpet_start.wem'
        target = scratch / WAV_NAME
        source.write_bytes(media)
        with zipfile.ZipFile(io.BytesIO(archive)) as decoder:
            decoder.extractall(scratch)
        subprocess.run([str(scratch / 'vgmstream-cli.exe'), '-i', '-o', str(target), str(source)],
                       cwd=scratch, check=True, timeout=30)
        decoded = read_wav(target)

    out.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(decoded)
    manifest = {
        'source_client': 'Lesta v1.46.0.0 #2320',
        'bank': {'package': BANK_PACKAGE, 'member': BANK_MEMBER, 'sha256': BANK_SHA256},
        'start': {'event': 'stereo_trumpet_start', 'event_id': 326256530, 'play_action_id': 535668376,
                  'container_id': 121633075, 'sound_id': 895804840},
        'stop': {'event': 'stereo_trumpet_stop', 'event_id': 2641540682, 'stop_action_id': 97209945,
                 'container_id': 121633075, 'fade_ms': 500, 'separate_sample': False},
        'media': {'id': MEDIA_ID, 'package': STREAM_PACKAGE, 'member': STREAM_MEMBER, 'offset': MEDIA_OFFSET,
                  'size': MEDIA_SIZE, 'sha256': WEM_SHA256, 'codec': 'Wwise Vorbis'},
        'decoder': {'release': DECODER_RELEASE, 'archive_sha256': DECODER_ZIP_SHA256},
        'wav': {'name': WAV_NAME, 'sha256': WAV_SHA256, 'format': 'PCM signed 16-bit little-endian',
                'channels': 1, 'sample_rate': WAV_RATE, 'frames': WAV_FRAMES},
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return audio_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lesta', type=Path, required=True)
    parser.add_argument('--vgmstream-zip', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(extract(args.lesta, args.vgmstream_zip, args.out))


if __name__ == '__main__':
    main()
