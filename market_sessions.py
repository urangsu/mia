"""Source session checks, not a claim that a vendor has published a final price."""
from datetime import datetime, date, timedelta, timezone
from functools import lru_cache

KST=timezone(timedelta(hours=9))
CALENDARS=frozenset(('XKRX','XNYS','XNAS','CMES'))
GRACE_MINUTES=20


def capture_time(value=None):
    value=datetime.now(KST) if value is None else value
    stamp=value if isinstance(value,datetime) else datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if stamp.tzinfo is None:raise ValueError('수집 시각에 시간대가 필요합니다.')
    return stamp.astimezone(KST)


@lru_cache(maxsize=24)
def _calendar(name,year):
    if name not in CALENDARS:raise ValueError('지원하지 않는 거래일 캘린더: '+str(name))
    try:
        import exchange_calendars as xc
        return xc.get_calendar(name,start=f'{year-1}-01-01',end=f'{year+1}-12-31')
    except ImportError as exc:
        raise RuntimeError('exchange-calendars 설치가 필요합니다. requirements.txt를 설치하세요.') from exc


def session_finished(name,market_date,captured_at):
    stamp=capture_time(captured_at)
    day=date.fromisoformat(str(market_date))
    if day>=stamp.date():return False
    calendar=_calendar(name,day.year)
    if not calendar.is_session(day.isoformat()):return False
    return calendar.session_close(day.isoformat()).to_pydatetime()+timedelta(minutes=GRACE_MINUTES)<=stamp


def expected_pair(name,captured_at):
    stamp=capture_time(captured_at)
    calendar=_calendar(name,stamp.year)
    days=calendar.sessions_in_range((stamp.date()-timedelta(days=45)).isoformat(),stamp.date().isoformat())
    closed=[day.date().isoformat() for day in reversed(days)
            if session_finished(name,day.date().isoformat(),stamp)]
    if len(closed)<2:raise ValueError('두 종료 거래일을 확인하지 못했습니다: '+name)
    return tuple(closed[:2])
