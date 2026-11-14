"""Prepare a separate FMOD 4.44 project for the local stereoscope cue."""

from hashlib import sha256
from pathlib import Path
import struct

from client_audit import read_limited
from fsb5_lamp import build as build_bank
from stereoscope_lesta_audio import WAV_FRAMES, WAV_RATE, WAV_SHA256, read_wav

PROJECT_NAME = 'SCP'
PROJECT_PATH = 'res/audio/scp.fev'
BANK_PATH = 'res/audio/scp_notifications_fx_intuition.fsb'
GUI_PROJECT_SHA256 = '967c482626900e0b432b6671c5e6390d382c6cf69342889fd03e25f31542e66e'
GUI_BANK_SHA256 = '19723267ade7c5681a7af0c902c7b65a0d23f9b7a23080d65f6d6a78bd9633e1'
def pinned_read(path, limit, expected):
    data = read_limited(path, limit)
    if sha256(data).hexdigest() != expected:
        raise ValueError(f'Unexpected stereoscope source digest for {path.name}')
    return data


def payloads(original, source):
    original = Path(original)
    pcm = struct.unpack_from(f'<{WAV_FRAMES}h', read_wav(source), 44)

    project = pinned_read(original / 'res/audio/gui.fev', 32 * 1024, GUI_PROJECT_SHA256)
    for old, new, count in (
        (b'GUI\0', b'SCP\0', 2),
        (b'GUI_notifications_FX_intuition\0', b'SCP_notifications_FX_intuition\0', 1),
        (b'gun_intuition\0', b'scope_enabled\0', 1),
    ):
        if len(old) != len(new) or project.count(old) != count:
            raise ValueError('Unexpected #717 FMOD project layout')
        project = project.replace(old, new)
    bank = pinned_read(original / 'res/audio/gui_notifications_fx_intuition.fsb', 32 * 1024, GUI_BANK_SHA256)
    files = {PROJECT_PATH: project, BANK_PATH: build_bank(bank, pcm)}
    receipt = {'wav_sha256': WAV_SHA256, 'wav_frames': WAV_FRAMES, 'wav_rate': WAV_RATE,
               'source_event': 'stereo_trumpet_start', 'stop_event': 'stereo_trumpet_stop',
               'project': PROJECT_NAME, 'paths': {path: sha256(data).hexdigest() for path, data in files.items()},
               'native_audio_check': 'NOT_RUN'}
    return files, receipt
