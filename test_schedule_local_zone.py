import unittest
from datetime import timedelta
from unittest.mock import patch
import scheduler_v37 as scheduler


class ScheduleZoneTests(unittest.TestCase):
    def test_registration_rejects_non_kst_before_touching_task_scheduler(self):
        with patch.object(scheduler,'IS_WINDOWS',True),patch.object(scheduler,'datetime') as clock,patch.object(scheduler,'_run') as run:
            clock.now.return_value.astimezone.return_value.utcoffset.return_value=timedelta(0)
            with self.assertRaisesRegex(RuntimeError,'한국시간'):
                scheduler.register('08:30')
        run.assert_not_called()

if __name__=='__main__':unittest.main()
