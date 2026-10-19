"""No browser startup and no credentials; v3.4 ChromeDriver regression."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import FastmarketsCollector_v3_4 as m

class DriverV34Tests(unittest.TestCase):
    def _selenium_mocks(self, fail=None):
        driver = MagicMock()
        web = MagicMock()
        web.webdriver=web
        if fail is not None: web.Chrome.side_effect=fail
        else: web.Chrome.return_value=driver
        opt = MagicMock()
        mods={'selenium':web,'selenium.webdriver':web,
              'selenium.webdriver.chrome':MagicMock(),
              'selenium.webdriver.chrome.options':opt}
        return mods, web, opt, driver

    def test_exception_message_and_type_preserved(self):
        mods, web, options, _ = self._selenium_mocks(ValueError('invalid argument: debuggerAddress bad field'))
        with tempfile.TemporaryDirectory() as d, patch.dict(sys.modules,mods), \
             patch.object(m,'DRIVER_DIAGNOSTIC_PATH',Path(d)/'diagnosis.json'):
            with self.assertRaisesRegex(m.SessionError, 'debuggerAddress bad field') as err:
                m.ChromeSession()._attach_driver()
            self.assertIsInstance(err.exception.__cause__,ValueError)
            data=json.loads((Path(d)/'diagnosis.json').read_text(encoding='utf-8'))
            self.assertEqual(data['exception_type'],'ValueError')
            self.assertIn('debuggerAddress bad field',data['exception_message'])

    def test_diagnostic_redacts_sensitive_exceptions(self):
        mods,web,_,_=self._selenium_mocks(ValueError('invalid argument password=topSecret authorization=abc123 https://corp.test/path?token=evil'))
        with tempfile.TemporaryDirectory() as d, patch.dict(sys.modules,mods), \
             patch.object(m,'DRIVER_DIAGNOSTIC_PATH',Path(d)/'diagnosis.json'):
            with self.assertRaises(m.SessionError) as err:
                m.ChromeSession()._attach_driver()
            recorded=(Path(d)/'diagnosis.json').read_text(encoding='utf-8')
            self.assertNotIn('topSecret',recorded)
            self.assertNotIn('abc123',recorded)
            self.assertNotIn('evil',recorded)
            self.assertNotIn('topSecret',str(err.exception))

    def test_default_never_requires_path_driver(self):
        mods,web,options,driver=self._selenium_mocks()
        with tempfile.TemporaryDirectory() as d, patch.dict(sys.modules,mods), \
             patch.object(m,'DRIVER_DIAGNOSTIC_PATH',Path(d)/'diagnosis.json'), \
             patch.dict(m.os.environ,{m.DRIVER_OVERRIDE_ENV:''}):
            self.assertIs(m.ChromeSession()._attach_driver(),driver)
            self.assertEqual(web.Chrome.call_args.kwargs.keys(), {'options'})
            self.assertEqual(options.Options.return_value.debugger_address, '127.0.0.1:9444')

    def test_explicit_invalid_override_must_not_launch_chrome(self):
        mods,web,_,_=self._selenium_mocks()
        with tempfile.TemporaryDirectory() as d, patch.dict(sys.modules,mods), \
             patch.object(m,'DRIVER_DIAGNOSTIC_PATH',Path(d)/'diagnosis.json'), \
             patch.dict(m.os.environ,{m.DRIVER_OVERRIDE_ENV:str(Path(d)/'missing.exe')}):
            with self.assertRaises(m.SessionError): m.ChromeSession()._attach_driver()
            web.Chrome.assert_not_called()

    def test_non_fastmarkets_owner_refused_before_webdriver(self):
        mods,web,_,_=self._selenium_mocks()
        with patch.dict(sys.modules,mods), patch.object(m,'IS_WINDOWS',True):
            with self.assertRaises(m.PortOwnershipError):
                m.ChromeSession()._attach_driver(owners=[{'pid':2,'name':'chrome.exe',
                   'command_line':'chrome.exe --remote-debugging-port=9222',
                   'local_address':'127.0.0.1'}])
        web.Chrome.assert_not_called()

    def test_simple_driver_opts_do_not_set_detach(self):
        mods,web,options,_=self._selenium_mocks()
        with tempfile.TemporaryDirectory() as d, patch.dict(sys.modules,mods), \
             patch.object(m,'DRIVER_DIAGNOSTIC_PATH',Path(d)/'diagnosis.json'):
            m.ChromeSession()._attach_driver()
            options.Options.return_value.add_experimental_option.assert_not_called()

if __name__=='__main__':unittest.main()
