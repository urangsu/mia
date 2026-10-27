"""One non-secret settings contract shared by desktop, CLI and scheduled runs."""
from copy import deepcopy
from datetime import date
from pathlib import Path
import json
import re
from urllib.parse import urlsplit, parse_qsl

EXTRA_DEFAULTS = dict(settings_version=1, fmb_enabled=True, fx_enabled=True,
                      naver_enabled=True,lme_enabled=True, report_dir='', driver_path='',
                      representative_symbols=[],fdr_enabled=False,
                      fdr_stock_codes=['005490'],fdr_timeout=20)
SECRET = re.compile(r'password|passwd|token|cookie|secret|authorization|api[_-]?key|access[_-]?key', re.I)


def ensure_nonsecret(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if SECRET.search(str(key)):
                raise ValueError('비밀번호·인증정보는 설정 파일에 저장할 수 없습니다. 자격 증명 저장을 사용하세요.')
            ensure_nonsecret(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            ensure_nonsecret(item)
    elif isinstance(value, str) and value.strip().lower().startswith(('https://','http://')):
        parsed = urlsplit(value.strip())
        if parsed.username or parsed.password or any(SECRET.search(key) for key,_ in parse_qsl(parsed.query)):
            raise ValueError('인증정보가 포함된 URL은 설정에 저장할 수 없습니다.')


def load(path, defaults):
    result = dict(deepcopy(defaults), **deepcopy(EXTRA_DEFAULTS))
    path = Path(path)
    if not path.exists():
        return result
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise ValueError('JSON 객체가 아닙니다')
        ensure_nonsecret(data)
        result.update(data)
        if 'v37_auto_time' not in data and 'auto_time' in data:
            result['v37_auto_time'] = data['auto_time']
    except (OSError, ValueError, TypeError) as exc:
        result['_settings_warning'] = '설정 파일을 읽지 못했습니다. 원본을 유지했습니다: ' + str(exc)
    return result


def save(path, values):
    ensure_nonsecret(values)
    data = {k: v for k, v in deepcopy(values).items() if not k.startswith('_')}
    data['settings_version'] = 1
    # Validate serializability before touching the existing file.
    text = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)
    from FastmarketsCollector_v3_4 import atomic_text
    with atomic_text(Path(path)) as stream:
        stream.write(text)


def validate(values, action):
    """Return a snapshot; unrelated sources/documents do not gate an action."""
    cfg = deepcopy(values)
    ensure_nonsecret(cfg)
    for key in ('fmb_enabled', 'fx_enabled', 'naver_enabled','fdr_enabled','lme_enabled'):
        if key in cfg and type(cfg[key]) is not bool:
            raise ValueError(key + ': 사용 여부는 참/거짓이어야 합니다.')
    if action in ('collect', 'export', 'reports', 'snapshot', 'history', 'ecm_preview', 'ecm_apply', 'save_settings'):
        if not str(cfg.get('data_dir') or '').strip():
            raise ValueError('자료 저장 폴더를 지정하세요.')
        cfg['data_dir'] = str(Path(cfg['data_dir']).expanduser())
    if action in ('save_settings', 'collect'):
        try:
            days = int(cfg.get('lookback_days', 31))
        except (ValueError, TypeError):
            raise ValueError('수집 기간은 0~3650일 정수로 입력하세요.') from None
        if not 0 <= days <= 3650:
            raise ValueError('수집 기간은 0~3650일로 입력하세요.')
        cfg['lookback_days'] = days
    if action in ('save_settings','collect'):
        from fdr_provider import instruments
        codes=cfg.get('fdr_stock_codes',['005490'])
        if isinstance(codes,str):codes=[s.strip() for s in codes.split(',') if s.strip()]
        if not isinstance(codes,list):raise ValueError('FDR 관심종목은 코드 목록이어야 합니다.')
        instruments(codes)
        cfg['fdr_stock_codes']=list(dict.fromkeys(codes))
        value=cfg.get('fdr_timeout',20)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not 1<=value<=120:
            raise ValueError('FDR 시간 제한은 1~120초입니다.')
        cfg['fdr_timeout']=value
    if action == 'collect' and not (any(cfg.get(k, True) for k in ('fmb_enabled', 'fx_enabled', 'naver_enabled')) or cfg.get('fdr_enabled',False) or cfg.get('lme_enabled',False)):
        raise ValueError('수집할 출처를 하나 이상 선택하세요.')
    if action == 'connect' or (action == 'collect' and cfg.get('fmb_enabled', True)):
        from FastmarketsCollector_v3_4 import verify_workspace_url
        cfg['workspace_url'] = verify_workspace_url(cfg.get('workspace_url'))[0]
    if action in ('save_settings', 'collect', 'export'):
        target = cfg.get('workbook_path', '')
        if target and Path(target).suffix.lower() != '.xlsx':
            raise ValueError('누적 Excel 파일은 .xlsx 형식이어야 합니다.')
    if action in ('ecm_preview', 'ecm_apply'):
        name = str(cfg.get('ecm_title') or '').strip()
        if not name.lower().endswith('.xlsx') or '/' in name or '\\' in name:
            raise ValueError('ECM 실제 파일명을 .xlsx 확장자까지 입력하세요.')
        if not str(cfg.get('ecm_search') or '').strip():
            raise ValueError('ECM 검색어를 입력하세요.')
    if action in ('schedule_register', 'save_settings'):
        if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', str(cfg.get('v37_auto_time', '08:30'))):
            raise ValueError('예약 시각은 HH:MM 형식으로 입력하세요.')
    return cfg


def report_filters(start=None, end=None, series=None):
    for value in (start, end):
        if value:
            date.fromisoformat(value)
    if start and end and start > end:
        raise ValueError('보고서 시작일이 종료일보다 늦습니다.')
    if isinstance(series, str):
        series = [item.strip() for item in series.split(',') if item.strip()]
    return dict(reports_only=True, report_start=start or None,
                report_end=end or None, report_series=series or None)


def reporting_identity(values):
    """Disabled FMB cannot block public sources or select an unrelated FMB DB view."""
    from FastmarketsCollector_v3_4 import verify_workspace_url, WORKSPACE_URL
    try:
        return verify_workspace_url(values.get('workspace_url') or WORKSPACE_URL)
    except ValueError:
        if values.get('fmb_enabled', True):
            raise
        # The scope needs a valid browser-free namespace, while this sentinel
        # explicitly excludes all stored FMB workspaces from report numbers.
        return WORKSPACE_URL, '__FMB_DISABLED_NO_WORKSPACE__'
