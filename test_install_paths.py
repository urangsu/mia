"""Offline restoration contracts; no Windows browser, profile or task access."""
import os
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from bring_in.RESTORE_LATEST_SOURCE import restore_source
from scripts.build_source_bundle import write_bundle


ROOT = Path(__file__).resolve().parent


class InstallPathTests(unittest.TestCase):
    def test_stable_launcher_supports_flat_checkout_and_clean_app_layout(self):
        fake_runtime = (
            'import json, sys\n'
            'def main(argv=None):\n'
            '    print(json.dumps({"runtime": __file__, "argv": sys.argv[1:] if argv is None else argv}))\n'
            '    return 17\n'
        )
        for clean in (False, True):
            with self.subTest(clean=clean), tempfile.TemporaryDirectory() as temp:
                folder = Path(temp) / '한글 source files'
                folder.mkdir()
                shutil.copyfile(ROOT / 'MIA_Collector.py', folder / 'MIA_Collector.py')
                runtime = folder / 'app' if clean else folder
                runtime.mkdir(exist_ok=True)
                (runtime / 'FastmarketsCollector_v3_7.py').write_text(fake_runtime)
                if clean:
                    (folder / 'FastmarketsCollector_v3_7.py').write_text('raise RuntimeError("wrong old root entry")')
                result = subprocess.run([sys.executable, str(folder / 'MIA_Collector.py'), '--help', 'synthetic'],
                                        cwd=Path(temp), capture_output=True, text=True)
                self.assertEqual(result.returncode, 17, result.stderr)
                payload = json.loads(result.stdout)
                self.assertEqual(payload['argv'], ['--help', 'synthetic'])
                self.assertEqual(Path(payload['runtime']).resolve(), (runtime / 'FastmarketsCollector_v3_7.py').resolve())

    def test_default_restore_uses_txt_parent_not_cwd_or_localappdata(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            incoming = root / '매크로 files'
            result = write_bundle({'app.py': b'new source'}, 'a' * 40, incoming)
            old = incoming / 'MIA_Collector'
            old.mkdir()
            (old / 'keep.txt').write_text('operating data')
            with patch.dict(os.environ, LOCALAPPDATA=str(root / 'legacy-default')):
                restore_source(result['txt'])
            self.assertTrue((incoming / 'MIA_Collector_Update/app.py').is_file())
            self.assertEqual((incoming / 'MIA_Collector_Update/app.py').read_bytes(), b'new source')
            self.assertEqual((old / 'keep.txt').read_text(), 'operating data')

    def test_existing_stable_target_is_never_merged_or_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            incoming = Path(temp)
            result = write_bundle({'app.py': b'new source'}, 'a' * 40, incoming)
            target = incoming / 'MIA_Collector_Update'
            target.mkdir()
            original = target / 'app.py'
            original.write_bytes(b'old source')
            with patch.dict(os.environ, LOCALAPPDATA=str(incoming / 'legacy-default')):
                with self.assertRaises(FileExistsError):
                    restore_source(result['txt'])
            self.assertEqual(original.read_bytes(), b'old source')
            self.assertEqual(sorted(p.name for p in target.iterdir()), ['app.py'])

    def test_cli_resolves_default_txt_beside_helper_from_unrelated_cwd(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            incoming = root / '매크로 files'
            write_bundle({'app.py': b'source'}, 'a' * 40, incoming)
            helper = incoming / 'RESTORE_LATEST_SOURCE.py'
            shutil.copyfile(ROOT / 'bring_in/RESTORE_LATEST_SOURCE.py', helper)
            elsewhere = root / 'elsewhere'
            elsewhere.mkdir()
            env = dict(os.environ, LOCALAPPDATA=str(root / 'not-the-install-location'))
            verified = subprocess.run([sys.executable, str(helper), '--verify-only'],
                                      cwd=elsewhere, env=env, capture_output=True, text=True)
            self.assertEqual(verified.returncode, 0, verified.stderr)
            self.assertFalse((incoming / 'MIA_Collector_Update').exists())
            restored = subprocess.run([sys.executable, str(helper)], cwd=elsewhere,
                                      env=env, capture_output=True, text=True)
            self.assertEqual(restored.returncode, 0, restored.stderr)
            self.assertTrue((incoming / 'MIA_Collector_Update/app.py').is_file())
            self.assertFalse((root / 'not-the-install-location').exists())
            repeated = subprocess.run([sys.executable, str(helper)], cwd=elsewhere,
                                      env=env, capture_output=True, text=True)
            self.assertEqual(repeated.returncode, 2, repeated.stderr)
            self.assertIn('--output', repeated.stderr)
            self.assertEqual((incoming / 'MIA_Collector_Update/app.py').read_bytes(), b'source')

    def test_gui_launcher_prefers_local_venv_and_forwards_arguments(self):
        cmd = (ROOT / 'RUN_GUI.cmd').read_text()
        self.assertIn('%~dp0.venv\\Scripts\\python.exe', cmd)
        self.assertLess(cmd.index('.venv\\Scripts\\python.exe'), cmd.index('py -3'))
        self.assertIn('"%~dp0MIA_Collector.py" %*', cmd)
        self.assertIn('exit /b', cmd)

    def test_restore_launcher_binds_both_input_and_output_to_its_folder(self):
        cmd = (ROOT / 'bring_in/RESTORE_LATEST_SOURCE.cmd').read_text()
        self.assertIn('"%~dp0MIA_SOURCE_CURRENT.txt"', cmd)
        self.assertIn('--output "%~dp0MIA_Collector_Update"', cmd)
        self.assertIn('exit /b', cmd)

    def test_guide_starts_from_actual_files_and_has_no_dated_install_names(self):
        guide = (ROOT / 'bring_in/MIA_COMPANY_SETUP_GUIDE_KO.txt').read_text()
        self.assertNotRegex(guide, r'MIA_(?:UPDATE|Collector)_20\d{6}')
        self.assertIn('$incoming = $root', guide)
        self.assertIn("$txt = Join-Path $incoming 'MIA_SOURCE_CURRENT.txt'", guide)
        self.assertIn("$restore = Join-Path $incoming 'RESTORE_LATEST_SOURCE.py'", guide)
        self.assertIn("$target = Join-Path $root 'MIA_Collector_Update'", guide)
        self.assertIn('Get-Item -LiteralPath $txt, $restore', guide)
        self.assertIn('FastmarketsCollectorDaily', guide)

    def test_guide_matches_clean_root_and_internal_regression_location(self):
        guide = (ROOT / 'bring_in/MIA_COMPANY_SETUP_GUIDE_KO.txt').read_text()
        self.assertIn("$entry = Join-Path $program 'MIA_Collector.py'", guide)
        self.assertIn("(Join-Path $program 'MIA_Collector.py') --diagnose", guide)
        self.assertIn('README_회사.txt', guide)
        self.assertIn("(Join-Path $program 'app')", guide)
        self.assertNotIn("(Join-Path $target 'FastmarketsCollector_v3_7.py')", guide)


if __name__ == '__main__':
    unittest.main()
