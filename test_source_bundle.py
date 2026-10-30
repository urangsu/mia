import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class SourceBundleTests(unittest.TestCase):
    def test_dom_archive_is_unpacked_inside_combined_restore(self):
        import scripts.build_source_bundle as builder
        root=Path(__file__).parent
        archive=(root/'tools/MIA_DOM_Inspector_V4/MIA_DOM_ARCHIVE_V4.txt').read_bytes()
        files={'MIA_Collector.py':b'launcher','RUN_GUI.cmd':b'gui','requirements.txt':b'',
            'requirements-desktop.txt':b'', 'bring_in/MIA_COMPANY_SETUP_GUIDE_KO.txt':b'guide',
            'tools/MIA_DOM_Inspector_V4/MIA_DOM_ARCHIVE_V4.txt':archive}
        layout=builder.company_layout(files)
        import json
        manifest=json.loads(layout['DOM_확장/manifest.json'])
        self.assertEqual(manifest['version'],'4.0.0')
        self.assertIn('DOM_확장/multi_picker.js',layout)
        self.assertEqual(len([n for n in layout if n.startswith('DOM_확장/')]),14)
        with tempfile.TemporaryDirectory() as temp:
            result=builder.write_bundle(layout,'d'*40,Path(temp)/'kit')
            from bring_in.RESTORE_LATEST_SOURCE import restore_source
            restore_source(result['txt'],Path(temp)/'restored')
            self.assertEqual((Path(temp)/'restored/DOM_확장/manifest.json').read_bytes(),layout['DOM_확장/manifest.json'])

    def test_company_layout_is_one_clean_root_with_unchanged_internal_source(self):
        import scripts.build_source_bundle as builder
        self.assertTrue(hasattr(builder, 'company_layout'), 'clean company layout missing')
        files = {
            'MIA_Collector.py': b'launcher', 'RUN_GUI.cmd': b'gui',
            'requirements.txt': b'core requirements', 'requirements-desktop.txt': b'-r requirements.txt',
            'bring_in/MIA_COMPANY_SETUP_GUIDE_KO.txt': '회사 안내'.encode(),
            'FastmarketsCollector_v3_4.py': b'core source',
            'FastmarketsCollector_v3_7.py': b'current entry',
            'test_old.py': b'unchanged tests', 'fixtures/synthetic.html': b'fixture',
            'scripts/build_source_bundle.py': b'builder',
        }
        layout = builder.company_layout(files)
        self.assertEqual({name for name in layout if '/' not in name},
                         {'MIA_Collector.py', 'RUN_GUI.cmd', 'requirements.txt',
                          'requirements-desktop.txt', 'README_회사.txt'})
        for name, content in files.items():
            self.assertEqual(layout['app/' + name], content)
        self.assertEqual(layout['README_회사.txt'], files['bring_in/MIA_COMPANY_SETUP_GUIDE_KO.txt'])
        with tempfile.TemporaryDirectory() as temp:
            result = builder.write_bundle(layout, 'b' * 40, Path(temp) / 'bundle')
            from bring_in.RESTORE_LATEST_SOURCE import restore_source
            target = Path(temp) / 'MIA_Collector_Update'
            manifest = restore_source(result['txt'], target)
            self.assertEqual(result['file_count'], len(files) + 5)
            self.assertEqual(len(manifest['files']), len(layout))
            self.assertTrue((target / 'app/test_old.py').is_file())
            self.assertTrue((target / 'app/fixtures/synthetic.html').is_file())
            self.assertFalse((target / 'FastmarketsCollector_v3_4.py').exists())

    def test_company_layout_refuses_missing_launcher_or_requirements(self):
        import scripts.build_source_bundle as builder
        self.assertTrue(hasattr(builder, 'company_layout'), 'clean company layout missing')
        with self.assertRaises(ValueError):
            builder.company_layout({'FastmarketsCollector_v3_4.py': b'core'})

    def test_builder_applies_clean_layout_and_extracts_only_current_restore_helpers(self):
        import scripts.build_source_bundle as builder
        files = {
            'MIA_Collector.py': b'launcher', 'RUN_GUI.cmd': b'gui',
            'requirements.txt': b'base', 'requirements-desktop.txt': b'-r requirements.txt',
            'bring_in/MIA_COMPANY_SETUP_GUIDE_KO.txt': '회사 안내'.encode(),
            'bring_in/RESTORE_LATEST_SOURCE.py': b'current helper',
            'bring_in/RESTORE_LATEST_SOURCE.cmd': b'current cmd',
            'bring_in/MIA_COLLECTOR_ONEFILE.txt': b'old nested archive',
            'FastmarketsCollector_v3_4.py': b'core',
            'test_old.py': b'test', 'fixtures/synthetic.html': b'fixture',
        }
        def committed_git(command):
            operation = command[3]
            if operation == 'rev-parse':
                return ('c' * 40 + '\n').encode()
            if operation == 'ls-tree':
                return ('\0'.join(sorted(files)) + '\0').encode()
            if operation == 'show':
                revision, name = command[4].split(':', 1)
                self.assertEqual(revision, 'c' * 40)
                return files[name]
            self.fail('Unexpected Git operation: ' + operation)
        with tempfile.TemporaryDirectory() as temp, patch.object(builder.subprocess, 'check_output', side_effect=committed_git):
            result = builder.build('/synthetic/repo', 'HEAD', Path(temp) / 'bundle')
            self.assertEqual(Path(result['zip']).name, 'MIA_Collector.zip')
            from bring_in.RESTORE_LATEST_SOURCE import restore_source
            target = Path(temp) / 'restored'
            manifest = restore_source(result['txt'], target)
            self.assertTrue((target / 'MIA_Collector.py').is_file())
            self.assertEqual((target / 'app/FastmarketsCollector_v3_4.py').read_bytes(), b'core')
            self.assertFalse(any('ONEFILE' in name for name in manifest['files']))
            self.assertEqual((Path(temp) / 'bundle/RESTORE_LATEST_SOURCE.py').read_bytes(), b'current helper')
            self.assertEqual(result['file_count'], len(manifest['files']))

    def test_deterministic_bundle_restore_checks_every_source_byte(self):
        from scripts.build_source_bundle import write_bundle
        from bring_in.RESTORE_LATEST_SOURCE import restore_source
        files={'app.py':b'print("source")\n','docs/readme.md':'금속 중심'.encode()}
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);result=write_bundle(files,'a'*40,root/'build')
            before=Path(result['txt']).read_bytes()
            again=write_bundle(files,'a'*40,root/'build')
            self.assertEqual(before,Path(again['txt']).read_bytes())
            destination=root/'restored';manifest=restore_source(result['txt'],destination)
            self.assertEqual(manifest['source_commit'],'a'*40)
            for path,data in files.items():self.assertEqual((destination/path).read_bytes(),data)
            with self.assertRaises(FileExistsError):restore_source(result['txt'],destination)
            corrupted=root/'corrupt.txt';corrupted.write_bytes(before[:-12]+b'AAAAAAAAAAAA')
            with self.assertRaises(ValueError):restore_source(corrupted,root/'bad')
            self.assertFalse((root/'bad').exists())

    def test_reject_unsafe_paths_before_creating_output(self):
        from scripts.build_source_bundle import write_bundle
        with tempfile.TemporaryDirectory() as t:
            for path in ('../escape.py','/absolute.py','folder\\escape.py'):
                with self.assertRaises(ValueError):write_bundle({path:b'x'},'a'*40,Path(t)/'out')


if __name__=='__main__':unittest.main()
