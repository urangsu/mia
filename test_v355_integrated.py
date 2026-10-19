"""v3.5.5 regression checks for corporate Excel data shape and shared session safety."""
import unittest
from pathlib import Path
from unittest.mock import MagicMock
from datetime import datetime, timedelta, date
import tempfile
import sqlite3
import sys
import types
from unittest.mock import patch

import excel_secure as ex
import smbs_rates as fx
import FastmarketsCollector_v3_4 as fm

class TestIntegrationV355(unittest.TestCase):
    def test_excel_serial_20261019(self):
        self.assertEqual(ex._date_key(46314.0),'2026-10-19')
        self.assertEqual(ex._date_key(datetime(2026,10,19)),'2026-10-19')
    def test_creates_both_daily_sheets_and_preserves_short_sources(self):
        with tempfile.TemporaryDirectory() as p:
            folder=Path(p);db=folder/'fastmarkets_prices_v3.sqlite3'
            fx.save_rates(db,[fx.FXQuote('2026-10-19','USD','1342.40','-6.10',1)])
            sheets=ex.make_sheets([],[],fx.load_rates(db))
            for name in ('일별요약','일별시세'):
                self.assertEqual(sheets[name][0],('고시일','USD'))
                self.assertEqual(sheets[name][1],('','SMBS'))
                self.assertEqual(sheets[name][2],('2026-10-19',1342.4))
            self.assertIn('월별시세',sheets)
    def test_recurring_fx_idempotent(self):
        with tempfile.TemporaryDirectory() as p:
            db=Path(p)/'f.sqlite3'
            q=fx.FXQuote('2026-10-19','USD','1342.40','-6.10',1)
            a=fx.save_rates(db,[q]);b=fx.save_rates(db,[q])
            self.assertEqual(a['inserted'],1)
            self.assertEqual(b,{'inserted':0,'updated':0,'unchanged':1})
            with sqlite3.connect(db) as cn:
                self.assertEqual(cn.execute('select count(*) from fx_rates').fetchone()[0],1)
    def test_shared_tab_closed_after_navigation_failure(self):
        browser=MagicMock()
        handles=['fmb']
        current=['fmb']
        type(browser).window_handles=property(lambda self: list(handles))
        type(browser).current_window_handle=property(lambda self: current[0])
        def open_tab(kind):
            self.assertEqual(kind,'tab');handles.append('fx');current[0]='fx'
        def switch_to(handle):current[0]=handle
        def close():
            self.assertEqual(current[0],'fx');handles.remove('fx')
        browser.switch_to.new_window.side_effect=open_tab
        browser.switch_to.window.side_effect=switch_to
        browser.close.side_effect=close
        browser.get.side_effect=RuntimeError('navigation failed')
        # Test the controller without requiring Selenium on Linux (Windows supplies it).
        selenium=types.ModuleType('selenium')
        webdriver=types.ModuleType('selenium.webdriver')
        common=types.ModuleType('selenium.webdriver.common')
        by=types.ModuleType('selenium.webdriver.common.by');by.By=object()
        support=types.ModuleType('selenium.webdriver.support')
        ui=types.ModuleType('selenium.webdriver.support.ui');ui.WebDriverWait=object;ui.Select=object
        modules={'selenium':selenium,'selenium.webdriver':webdriver,
                 'selenium.webdriver.common':common,'selenium.webdriver.common.by':by,
                 'selenium.webdriver.support':support,'selenium.webdriver.support.ui':ui}
        with patch.dict(sys.modules,modules):
            with self.assertRaisesRegex(RuntimeError,'navigation failed'):
                fx.collect_rates(driver=browser,logger=lambda _:None)
        self.assertEqual(current[0],'fmb')
        self.assertEqual(handles,['fmb'])
        browser.quit.assert_not_called()
    def test_no_unverified_driver(self):
        with self.assertRaises(fx.FXPageError):fx.collect_rates(driver=None)
    def test_bm_pinned_js_uses_matching_row_index(self):
        self.assertIn('getAttribute(\'row-index\')===i',fm.SAMPLE_JS)
        self.assertIn('date_missing_examples',fm.__dict__['ChromeSession'].scrape.__code__.co_consts.__repr__())

if __name__=='__main__':unittest.main()

class TestPortOwnershipRetry(unittest.TestCase):
    def test_transient_cim_query_retried_not_ignored(self):
        owner={'pid':123,'name':'chrome.exe','command_line':'--remote-debugging-port=9444 --user-data-dir=X', 'local_address':'127.0.0.1'}
        with patch.object(fm,'inspect_windows_listeners',side_effect=[fm.PortOwnershipError('Windows 디버그 포트 소유자 조회 실패: PowerShell/CIM 권한 또는 실행 시간 확인'),[owner]]) as listener, \
             patch.object(fm,'verify_chrome_owner',return_value=True) as verify, \
             patch.object(fm,'cdp_version',return_value={'Browser':'Chrome/155.0.8059.80'}), \
             patch.object(fm.time,'sleep'):
            fm.ChromeSession()._validate_listener()
            self.assertEqual(listener.call_count,2)
            verify.assert_called_once()
    def test_wrong_owner_not_retried(self):
        with patch.object(fm,'inspect_windows_listeners',side_effect=fm.PortOwnershipError('PID 2 포트 프로필이 다릅니다')) as listener:
            with self.assertRaises(fm.PortOwnershipError):fm.ChromeSession()._validate_listener()
            listener.assert_called_once()
