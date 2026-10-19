import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from contextlib import redirect_stdout
from test_v33 import m, price


class HardeningTests(unittest.TestCase):
    def test_required_payable_codes_detected(self):
        r=m.coverage_report([price()],[{'codes':['MB-LI-0029'],'description_by_code':{},'widget':'Li'}])
        self.assertEqual(r['required_missing'],[])
        self.assertTrue(r['scope_complete'])

    def test_powershell_restricted_error_not_treated_as_empty_port(self):
        result=MagicMock(returncode=1,stdout='',stderr='policy')
        with patch.object(m,'IS_WINDOWS',True),patch.object(m.subprocess,'run',return_value=result):
            with self.assertRaises(m.PortOwnershipError):m.inspect_windows_listeners()

    def test_process_swap_after_attach_aborts(self):
        owner={'pid':1,'name':'chrome.exe','local_address':'127.0.0.1',
               'command_line':f'chrome.exe --remote-debugging-port=9444 "--user-data-dir={m.CHROME_PROFILE}"'}
        api=MagicMock();api.webdriver=api;api.Chrome.return_value=MagicMock()
        imports={'selenium':api,'selenium.webdriver':api,'selenium.webdriver.chrome':MagicMock(),
                 'selenium.webdriver.chrome.options':MagicMock()}
        import sys
        session=m.ChromeSession()
        with patch.dict(sys.modules,imports),patch.object(m,'inspect_windows_listeners',return_value=[owner]), \
             patch.object(session,'_validate_listener',side_effect=[[owner],[owner],[dict(owner,pid=2)]]):
            with self.assertRaises(m.PortOwnershipError):session.connect()
        self.assertIsNone(session.driver)

    def test_credential_roundtrip_same_service(self):
        class Vault:
            def __init__(self):self.values={}
            def get_password(self,s,k):return self.values.get((s,k))
            def set_password(self,s,k,v):self.values[(s,k)]=v
            def delete_password(self,s,k):self.values.pop((s,k),None)
        vault=Vault()
        with patch.object(m,'get_keyring',return_value=vault):
            m.credentials_set('demo@example.invalid','not-a-real-password')
            self.assertEqual(m.credentials_get(),('demo@example.invalid','not-a-real-password'))
            self.assertTrue(all(s=='FastmarketsCollector:auth.fastmarkets.com' for s,k in vault.values))
            m.credentials_delete();self.assertEqual(m.credentials_get(),('',''))

    def test_lock_released_after_failure(self):
        with tempfile.TemporaryDirectory() as t,patch.object(m,'BROWSER_LOCK_PATH',Path(t)/'lock'):
            with self.assertRaises(ValueError):
                with m.exclusive_browser_job():raise ValueError('fixture')
            with m.exclusive_browser_job():pass

    def test_dom_low_high_invalid_is_rejected(self):
        snapshot={'widgets':[{'title':'Bad','headers':[],'directCodes':['MB-LI-0029'],
            'grids':[{'index':0,'rows':[{'index':0,'cells':[
                {'colId':'date','text':'2026-10-15'},
                {'colId':'MB-LI-0029-low','text':'20'},
                {'colId':'MB-LI-0029-high','text':'10'}]}]}]}]}
        rows,_,warnings=m.read_snapshot(snapshot,0)
        self.assertEqual(rows,[])
        self.assertTrue(warnings)

    def test_official_mismatch_is_visible_warning(self):
        with tempfile.TemporaryDirectory() as t:
            folder=Path(t);f=folder/'input.csv'
            m.save_sqlite(m.path_bundle(folder)['db'],[price(mid='20')],[],
                          {'widget_count':1,'found_symbols':[],'warnings':[]})
            f.write_text('symbol,date,low,mid,high,unit,price_mode,change_pct\nMB-LI-0029,2026-10-15,14,14.8,15.6,$/kg,Actual,-5.13\n')
            _,diag=m.import_official(f,folder)
            self.assertTrue(any('불일치' in w for w in diag['warnings']))

if __name__=='__main__':unittest.main()
