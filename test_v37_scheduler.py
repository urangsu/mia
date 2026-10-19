import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

class SchedulerTests(unittest.TestCase):
    def test_task_is_interactive_not_elevated_and_recovers_missed_run(self):
        from scheduler_v37 import task_xml
        from xml.etree import ElementTree as E
        root=E.fromstring(task_xml('08:30',r'COMPANY\su',Path('C:/A&B/FastmarketsCollector_v3_7.py'),Path('C:/Python/python.exe'),datetime(2026,10,19)))
        def text(name):return root.find('.//{*}'+name).text
        self.assertEqual(text('RunLevel'),'LeastPrivilege')
        self.assertEqual(text('LogonType'),'InteractiveToken')
        self.assertEqual(text('MultipleInstancesPolicy'),'IgnoreNew')
        self.assertEqual(text('StartWhenAvailable'),'true')
        self.assertEqual(text('WakeToRun'),'true')
        self.assertEqual(text('StartBoundary'),'2026-10-19T08:30:00')
        trigger=root.find('.//{*}CalendarTrigger')
        self.assertEqual([c.tag.split('}')[-1] for c in trigger],['Enabled','StartBoundary','ScheduleByDay'])
        self.assertIn('--once',text('Arguments'))
        self.assertNotIn('9337',text('Arguments'))
        self.assertEqual(text('WorkingDirectory'),'C:/A&B')
    def test_bad_time_rejected(self):
        from scheduler_v37 import task_xml
        for time in ('7:00','24:00','08:99','08:30 & shutdown'):
            with self.assertRaises(ValueError):task_xml(time,'su',Path('x.py'),Path('python'))
    def test_nonwindows_registration_is_not_claimed(self):
        import scheduler_v37 as s
        with patch.object(s,'IS_WINDOWS',False):
            with self.assertRaises(RuntimeError):s.register('08:30')

if __name__=='__main__':unittest.main()
