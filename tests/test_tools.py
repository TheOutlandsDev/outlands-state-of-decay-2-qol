from pathlib import Path
from unittest import mock
import contextlib
import io
import json
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import pak
import profile as setup


class ArchiveTests(unittest.TestCase):
    def test_pak_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'sample.pak'
            assets = [('StateOfDecay2/Content/Sample.uasset', b'example' * 100),
                      ('StateOfDecay2/metadata.json', b'{"name":"test"}')]
            pak.write_pak(path, assets)
            entries = pak.index(path)['entries']
            self.assertEqual([(e['name'], pak.payload(path, e)) for e in entries], assets)

    def test_corrupt_payload_stops(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'sample.pak'
            pak.write_pak(path, [('sample', b'payload')])
            entry = pak.index(path)['entries'][0]
            raw = bytearray(path.read_bytes())
            raw[53] ^= 1
            path.write_bytes(raw)
            with self.assertRaisesRegex(ValueError, 'payload checksum'):
                pak.payload(path, entry)

    def test_corrupt_index_stops(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'sample.pak'
            pak.write_pak(path, [('sample', b'payload')])
            raw = bytearray(path.read_bytes())
            raw[-45] ^= 1
            path.write_bytes(raw)
            with self.assertRaisesRegex(ValueError, 'index checksum'):
                pak.index(path)

    def test_lz4_literals_and_overlapping_match(self):
        self.assertEqual(pak.lz4_block(b'\x30abc'), b'abc')
        self.assertEqual(pak.lz4_block(b'\x32abc\x03\x00'), b'abcabcabc')
        self.assertEqual(pak.lz4_block(b'\xf0\x05' + b'a' * 20), b'a' * 20)

    def test_lz4_bad_input_stops(self):
        for raw in (b'\xf0', b'\x10a\x00\x00', b'\x30a'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                pak.lz4_block(raw)

    def test_patch_requires_correct_preimage_and_output(self):
        original = b'prefix' + struct.pack('<i', 4) + b'suffix'
        expected = b'prefix' + struct.pack('<i', 100) + b'suffix'
        recipe = dict(before_sha256=pak.digest(original), after_sha256=pak.digest(expected),
                      edits=[dict(offset=6, before=4, after=100, type='int32')])
        self.assertEqual(setup.patch_bytes(original, recipe), expected)
        with self.assertRaisesRegex(ValueError, 'version differs'):
            setup.patch_bytes(original + b'wrong', recipe)
        recipe['edits'][0]['before'] = 5
        with self.assertRaisesRegex(ValueError, 'preimage differs'):
            setup.patch_bytes(original, recipe)


class InstallationSafetyTests(unittest.TestCase):
    def fixture(self, root):
        saved = root / 'StateOfDecay2/Saved'
        (saved / 'Paks').mkdir(parents=True)
        (saved / 'Paks/old.pak').write_bytes(b'old mod')
        (saved / 'progress.sav').write_bytes(b'original progress')
        build = root / 'build'
        (build / 'Paks').mkdir(parents=True)
        pak.write_pak(build / 'Paks/new.pak', [('test', b'new mod')])
        result = dict(pak_manifest=[dict(file='new.pak', sha256=pak.file_hash(build / 'Paks/new.pak'))])
        return saved, build, result

    def test_backup_and_mod_only_rollback_preserve_new_progress(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            saved, build, result = self.fixture(root)
            with mock.patch.object(setup, 'game_closed'), mock.patch.object(setup, 'validate', return_value=result), contextlib.redirect_stdout(io.StringIO()):
                setup.install(build, saved, root / 'backups')
                backup = next((root / 'backups').iterdir())
                self.assertEqual((backup / 'Saved/progress.sav').read_bytes(), b'original progress')
                self.assertEqual((saved / 'progress.sav').read_bytes(), b'original progress')
                (saved / 'progress.sav').write_bytes(b'new progress after installation')
                setup.restore_mods(backup)
                self.assertEqual((saved / 'progress.sav').read_bytes(), b'new progress after installation')
                self.assertEqual((saved / 'Paks/old.pak').read_bytes(), b'old mod')

    def test_failed_deployment_restores_previous_mods(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            saved, build, result = self.fixture(root)
            result['pak_manifest'][0]['sha256'] = '0' * 64
            with mock.patch.object(setup, 'game_closed'), mock.patch.object(setup, 'validate', return_value=result), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(ValueError, 'Installed checksum'):
                    setup.install(build, saved, root / 'backups')
            self.assertEqual((saved / 'Paks/old.pak').read_bytes(), b'old mod')
            self.assertEqual((saved / 'progress.sav').read_bytes(), b'original progress')

    def test_loose_mods_refused_without_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            saved, build, result = self.fixture(root)
            (saved / 'Cooked').mkdir()
            (saved / 'Cooked/loose.uasset').write_bytes(b'existing loose mod')
            with mock.patch.object(setup, 'game_closed'), mock.patch.object(setup, 'validate', return_value=result):
                with self.assertRaisesRegex(ValueError, 'Loose Cooked'):
                    setup.install(build, saved, root / 'backups')
            self.assertFalse((root / 'backups').exists())
            self.assertTrue((saved / 'Paks/old.pak').exists())

    def test_wrong_saved_directory_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, 'must end'):
                setup.checked_saved(Path(folder))


if __name__ == '__main__':
    unittest.main()
