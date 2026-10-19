# -*- coding: utf-8 -*-
"""v3.2 browser isolation / no unauthorized attachment tests. No Chrome or credentials required."""
import contextlib
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

src=Path(__file__).with_name('FastmarketsCollector_v3_4.py')
spec=importlib.util.spec_from_file_location('fmv32',src)
m=importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name]=m
spec.loader.exec_module(m)

class PortTests(unittest.TestCase):
    def owner(self, name='chrome.exe', profile=None, port=None, addr='127.0.0.1'):
        return {'pid':1234,'name':name,'local_address':addr,
                'command_line':f'"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port={port or m.PORT} "--user-data-dir={profile or m.CHROME_PROFILE}" --no-first-run'}

    def test_ports_distinct(self):
        self.assertEqual(m.PORT,9444)
        self.assertIn('ChromeProfile_9444', str(m.CHROME_PROFILE))

    def test_owner_valid(self):
        self.assertTrue(m.verify_chrome_owner([self.owner()]))
        self.assertTrue(m.verify_chrome_owner([self.owner(addr='::1')]))

    def test_not_edge(self):
        with self.assertRaises(m.PortOwnershipError):m.verify_chrome_owner([self.owner(name='msedge.exe')])

    def test_not_other_profile(self):
        with self.assertRaises(m.PortOwnershipError):m.verify_chrome_owner([self.owner(profile=str(m.APP_HOME/'ChromeProfile'))])

    def test_not_other_port(self):
        with self.assertRaises(m.PortOwnershipError):m.verify_chrome_owner([self.owner(port=9222)])

    def test_public_listener_rejected(self):
        with self.assertRaises(m.PortOwnershipError):m.verify_chrome_owner([self.owner(addr='0.0.0.0')])

    def test_unverifiable_owner_rejected(self):
        with self.assertRaises(m.PortOwnershipError):m.verify_chrome_owner([])
        with self.assertRaises(m.PortOwnershipError):m.verify_chrome_owner([self.owner(),self.owner(profile='C:/Other')])

    def test_profile_parser_quoted_and_unquoted(self):
        samples=['--user-data-dir="C:\\Users\\John Doe\\AppData\\ChromeProfile_9444" --no-first-run',
                 '"--user-data-dir=C:\\Users\\John Doe\\AppData\\ChromeProfile_9444" --no-first-run',
                 '--user-data-dir=C:\\Users\\John\\ChromeProfile_9444 --no-first-run']
        expected=['C:\\Users\\John Doe\\AppData\\ChromeProfile_9444']*2+['C:\\Users\\John\\ChromeProfile_9444']
        for a,b in zip(samples,expected):
            self.assertEqual(m._chrome_profile_from_cmdline(a),b)

    def test_wrong_cdp_browser_rejected(self):
        with patch.object(m,'inspect_windows_listeners',return_value=[self.owner()]):
            with patch.object(m,'cdp_version',return_value={'Browser':'Edg/155.0.1'}):
                with self.assertRaises(m.PortOwnershipError):m.ChromeSession()._validate_listener()

    def test_reusing_correct_running_chrome_does_not_spawn(self):
        fake_webdriver=MagicMock()
        fake_webdriver.webdriver=fake_webdriver
        fake_driver=MagicMock()
        fake_driver.window_handles=['1']
        fake_webdriver.Chrome.return_value=fake_driver
        fake_opt=MagicMock()
        fake_opt.Options.return_value=MagicMock()
        imports={'selenium':fake_webdriver,'selenium.webdriver':fake_webdriver,
                 'selenium.webdriver.chrome':MagicMock(), 'selenium.webdriver.chrome.options':fake_opt}
        with patch.dict(sys.modules,imports):
            with patch.object(m,'inspect_windows_listeners',return_value=[self.owner()]):
                with patch.object(m,'cdp_version',return_value={'Browser':'Chrome/155.0.8059.80'}):
                    with patch.object(m.subprocess,'Popen') as spawn:
                        session=m.ChromeSession()
                        result=session.connect()
                        self.assertIs(result,fake_driver)
                        spawn.assert_not_called()
                        self.assertEqual(fake_opt.Options.return_value.debugger_address,'127.0.0.1:9444')

    def test_wrong_port_never_connects_or_spawns(self):
        fake_webdriver=MagicMock()
        fake_webdriver.webdriver=fake_webdriver
        imports={'selenium':fake_webdriver,'selenium.webdriver':fake_webdriver,
                 'selenium.webdriver.chrome':MagicMock(), 'selenium.webdriver.chrome.options':MagicMock()}
        with patch.dict(sys.modules,imports):
            with patch.object(m,'inspect_windows_listeners',return_value=[self.owner(port=9222)]):
                with patch.object(m.subprocess,'Popen') as spawn:
                    with self.assertRaises(m.PortOwnershipError):m.ChromeSession().connect()
                    spawn.assert_not_called()
                    fake_webdriver.Chrome.assert_not_called()

    def test_browser_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(m,'BROWSER_LOCK_PATH',Path(tmp)/'lock'):
                with m.exclusive_browser_job():
                    with self.assertRaises(m.SessionError):
                        with m.exclusive_browser_job():pass
                with m.exclusive_browser_job():pass

if __name__=='__main__':unittest.main(verbosity=2)
