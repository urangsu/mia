"""Check source-session freshness without replacing any observed NAVER close.

Call only for the new source-bound daily-table pairs. A verified historical close
is not necessarily the latest expected session. No network, DB or browser writes.
"""
from copy import deepcopy
import re

from market_sessions import expected_pair


CALENDARS = {
    'KOSPI': 'XKRX', 'KOSDAQ': 'XKRX',
    'SP500': 'XNYS', 'NASDAQ': 'XNAS',
    'GOLD': 'CMES', 'WTI': 'CMES',
}


def check_pair(pair, captured_at):
    """Return (copied_pair, warnings), retaining observed values and provenance."""
    result = deepcopy(pair)
    if result.get('status') != 'close_pair':
        return result, []
    identity = result.get('instrument_id')
    stock_code = result.get('stock_code')
    calendar = CALENDARS.get(identity)
    if identity is None and isinstance(stock_code, str) and re.fullmatch(r'\d{6}', stock_code):
        identity, calendar = stock_code, 'XKRX'
    if calendar is None:
        result['status'] = 'calendar_unverified'
        result['freshness_calendar'] = None
        return result, [str(identity or stock_code) + ': latest calendar unverified; '
                        'actual source dates retained, no stock calendar substituted for bond holidays']
    result['freshness_calendar'] = calendar
    try:
        previous, prior = expected_pair(calendar, captured_at)
    except Exception as exc:
        result['status'] = 'calendar_unverified'
        return result, [str(identity) + ': expected source sessions unavailable (' + type(exc).__name__ +
                        '); observed historical prices retained, not confirmed current']
    result['expected_previous_date'] = previous
    result['expected_prior_date'] = prior
    if (result.get('previous_date'), result.get('prior_date')) != (previous, prior):
        result['status'] = 'stale_history'
        return result, [str(identity) + ': stale_history; expected ' + previous + '/' + prior +
                        ', observed ' + str(result.get('previous_date')) + '/' + str(result.get('prior_date')) +
                        '; observed values retained without replacement']
    return result, []
