from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import stereoscope_lesta_audio as audio


class StereoscopeLestaAudioTests(unittest.TestCase):
    def test_full_stream_is_read_from_validated_record(self):
        with tempfile.TemporaryDirectory() as folder:
            lesta = Path(folder)
            packages = lesta / 'res' / 'packages'
            packages.mkdir(parents=True)
            bank = b'local fixture bank'
            wem = b'local fixture Wwise media'
            header = struct.pack('<4sI5I', b'AKPK', 20, audio.MEDIA_ID, 1, len(wem), 32, 0)
            stream = header + b'\0' * 4 + wem
            with zipfile.ZipFile(packages / audio.BANK_PACKAGE, 'w') as package:
                package.writestr(audio.BANK_MEMBER, bank)
            with zipfile.ZipFile(packages / audio.STREAM_PACKAGE, 'w') as package:
                package.writestr(audio.STREAM_MEMBER, stream)
            with patch.multiple(audio, BANK_SIZE=len(bank), BANK_SHA256=audio.sha(bank),
                                STREAM_SIZE=len(stream), STREAM_HEADER_SIZE=len(header),
                                STREAM_HEADER_SHA256=audio.sha(header), STREAM_RECORD_OFFSET=8,
                                MEDIA_SIZE=len(wem), MEDIA_OFFSET=32, WEM_SHA256=audio.sha(wem)):
                self.assertEqual(audio.read_wem(lesta), wem)
                with zipfile.ZipFile(packages / audio.STREAM_PACKAGE, 'w') as package:
                    package.writestr(audio.STREAM_MEMBER, stream[:-1] + b'X')
                with self.assertRaisesRegex(ValueError, 'WEM differs'):
                    audio.read_wem(lesta)

    def test_wav_requires_hash_and_pcm_format(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / audio.WAV_NAME
            with wave.open(str(path), 'wb') as wav:
                wav.setparams((1, 2, audio.WAV_RATE, audio.WAV_FRAMES, 'NONE', ''))
                wav.writeframes(struct.pack('<h', 1024) * audio.WAV_FRAMES)
            raw = path.read_bytes()
            with self.assertRaisesRegex(ValueError, 'audited decode'):
                audio.read_wav(path)
            with patch.object(audio, 'WAV_SHA256', audio.sha(raw)):
                self.assertEqual(audio.read_wav(path), raw)
                with patch.object(audio, 'WAV_RATE', 44100):
                    with self.assertRaisesRegex(ValueError, 'mono 48 kHz'):
                        audio.read_wav(path)

    def test_extract_rejects_output_inside_lesta(self):
        with tempfile.TemporaryDirectory() as folder:
            lesta = Path(folder)
            with self.assertRaisesRegex(ValueError, 'outside the Lesta installation'):
                audio.extract(lesta, lesta / 'decoder.zip', lesta / 'res' / 'audio')

    def test_extract_rejects_mismatched_decoder_archive(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / 'decoder.zip'
            archive.write_bytes(b'invalid decoder')
            with patch.object(audio, 'read_wem', return_value=b'verified fixture'):
                with self.assertRaisesRegex(ValueError, 'published r2168'):
                    audio.extract(root / 'lesta', archive, root / 'out')
            self.assertFalse((root / 'out').exists())


if __name__ == '__main__':
    unittest.main()
