"""UI-independent commands. Caller owns a single worker; no Qt dependency here."""
from contextlib import closing
from copy import deepcopy
from pathlib import Path
import json
import sqlite3
import threading

import FastmarketsCollector_v3_4 as core
from app_settings import validate, report_filters

STATES = {'complete', 'partial', 'failed', 'cancelled', 'needs_action'}


class CollectorService:
    def __init__(self, settings=None, logger=None):
        self.settings = deepcopy(settings if settings is not None else core.config_load())
        self.logger = logger or (lambda message: None)
        self._redactions = []
        self.browser = core.ChromeSession(self._log, driver_path=self.settings.get('driver_path'))
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._pending = None
        self._pending_settings = None

    def _safe(self, value):
        text = str(value)
        for secret in self._redactions:
            if secret:
                text = text.replace(secret, '[비공개]')
        return text

    def _log(self, message):
        # Logging failure must never interrupt the actual operation or recovery.
        try:
            self.logger(self._safe(message))
        except Exception:
            pass

    def _result(self, status, message, data=None, warnings=()):
        return dict(status=status if status in STATES else 'failed',
                    message=self._safe(message), data=data or {},
                    warnings=[self._safe(w) for w in warnings])

    def cancel(self):
        self._cancel.set()

    def close(self):
        if not self._lock.acquire(blocking=False):
            raise RuntimeError('진행 중인 작업이 있습니다. 중단 후 종료하세요.')
        try:
            self.browser.detach()
        finally:
            self._lock.release()

    def run(self, action, settings=None, **payload):
        if not self._lock.acquire(blocking=False):
            return self._result('needs_action', '진행 중인 작업이 끝난 뒤 다시 실행하세요.')
        self._cancel.clear()
        self._redactions = [str(payload.get(k) or '') for k in ('password',)]
        try:
            values=deepcopy(settings if settings is not None else self.settings)
            if action=='collect_public':
                values.update(fmb_enabled=False,fx_enabled=False,naver_enabled=False,fdr_enabled=True)
            cfg = validate(values, 'collect' if action=='collect_public' else action)
            if cfg.get('_settings_warning') and action not in ('save_settings','snapshot','history','diagnose','schedule_status'):
                return self._result('needs_action', cfg['_settings_warning'] + ' 설정을 확인하고 저장하세요.')
            if action in ('collect','connect','diagnose'):
                path = cfg.get('driver_path') or ''
                if (self.browser.driver_path or '') != path:
                    self.browser.detach()
                    self.browser.driver_path = path
            self._log('작업 시작: ' + action)
            result = self._execute(action, cfg, payload)
            self._log(result['message'])
            return result
        except Exception as exc:
            result = self._result('failed', str(exc) or type(exc).__name__)
            self._log('작업 실패: ' + result['message'])
            return result
        finally:
            self._redactions = []
            self._lock.release()

    def _execute(self, action, cfg, payload):
        folder = Path(cfg.get('data_dir') or '.')
        if action == 'save_settings':
            core.config_save(cfg)
            cfg.pop('_settings_warning', None)
            self.settings = deepcopy(cfg)
            self._pending = None
            return self._result('complete','설정을 저장했습니다. 다음 작업부터 적용합니다.',{'settings':deepcopy(cfg)})
        if action == 'snapshot':
            from report_model import build_context
            from app_settings import reporting_identity
            _,active = reporting_identity(cfg)
            context = build_context(folder, workspace_id=active)
            data = dict(tables=context.tables, as_of=context.as_of,
                        snapshot_id=context.snapshot_id, warnings=list(context.warnings))
            from metal_dashboard import dashboard_data
            data['metals']=dashboard_data(context)
            data['source_dates']=dict(context.source_dates)
            return self._result('partial' if context.warnings else 'complete',
                                '저장된 자료를 읽었습니다.',data,context.warnings)
        if action == 'history':
            return self._result('complete','실행 기록을 읽었습니다.',{'runs':self._history(folder)})
        if action == 'connect':
            user, password = payload.get('username') or '', payload.get('password') or ''
            if not user and not password:
                user, password = core.credentials_get()
            elif not user or not password:
                raise ValueError('이번 로그인에 사용할 이메일과 비밀번호를 모두 입력하세요.')
            self._redactions.append(password)
            with core.exclusive_browser_job(), core.workspace_scope(cfg.get('workspace_url')):
                connected = self.browser.open_workspace(user, password)
            if not connected:
                return self._result('needs_action','Chrome에서 로그인·추가 인증을 완료한 뒤 다시 연결하세요.')
            return self._result('complete','Chrome 9444 작업공간 연결을 확인했습니다.')
        if action == 'credentials_save':
            core.credentials_set(payload.get('username'), payload.get('password'))
            return self._result('complete','계정을 OS 자격 증명 저장소에 저장했습니다.')
        if action == 'credentials_delete':
            core.credentials_delete()
            return self._result('complete','저장된 계정을 삭제했습니다.')
        if action == 'diagnose':
            return self._diagnose(cfg)
        if action in ('collect','collect_public','export','reports'):
            import pipeline_v37
            self._pending = None
            if action in ('collect','collect_public'):
                raw = pipeline_v37.run_collection(cfg, self.browser, self._cancel, self._log)
                diag = raw.get('diag', {})
                state = 'cancelled' if raw.get('cancelled') else diag.get('status','failed')
                warnings = diag.get('warnings', [])
            else:
                clean = {k:v for k,v in cfg.items() if k not in ('reports_only','report_start','report_end','report_series','start','end','series')}
                if action == 'reports':
                    clean.update(report_filters(payload.get('start'), payload.get('end'), payload.get('series')))
                raw = pipeline_v37.export_only(clean)
                state = raw.get('status','failed')
                warnings = raw.get('warnings', [])
            label = {'collect':'수집·누적','collect_public':'공개 종가 수집','export':'Excel·보고서 출력','reports':'선택 기간 보고서'}[action]
            message = label + ' ' + {'complete':'완료','partial':'부분 완료','failed':'실패','cancelled':'중단'}.get(state,'실패')
            if warnings:
                message += ': ' + str(warnings[0])
            return self._result(state,message,raw,warnings)
        if action in ('schedule_register','schedule_status','schedule_remove'):
            import scheduler_v37
            if action == 'schedule_register':
                # A registered task reads saved config, never unsaved desktop drafts.
                if cfg != self.settings:
                    return self._result('needs_action','자동 실행에 적용할 설정을 먼저 저장하세요.')
                value = scheduler_v37.register(cfg.get('v37_auto_time','08:30'))
            elif action == 'schedule_remove':
                value = scheduler_v37.remove()
            else:
                value = scheduler_v37.status()
            return self._result('complete',str(value),{'text':str(value)})
        if action in ('ecm_preview','ecm_apply'):
            return self._ecm(action,cfg,payload)
        raise ValueError('지원하지 않는 작업: ' + action)

    def _ecm(self, action, cfg, payload):
        from ecm_excel_sync import prepare_ecm_plan, apply_ecm_plan
        from ecm_binding import bind_open
        from ecm_automation import execute, exclusive_ecm_job
        folder = Path(cfg['data_dir'])
        target = cfg.get('workbook_path') or str(core.path_bundle(folder)['xlsx'])
        identity = json.dumps(cfg,ensure_ascii=False,sort_keys=True,allow_nan=False)
        if action == 'ecm_preview':
            self._pending = None
            bound = bind_open(folder,cfg['ecm_title'],target,lambda:execute(
                self._log,search_text=cfg['ecm_search'],target_title=cfg['ecm_title']))
            with core.workspace_scope(cfg.get('workspace_url')):
                plan = prepare_ecm_plan(folder,cfg['ecm_title'],local_path=target,
                    target_fullname=bound['full_name'],target_hwnd=bound['excel_hwnd'],log=self._log)
            self._pending = deepcopy(plan)
            self._pending_settings = identity
            return self._result('needs_action','변경 셀과 실제 문서 경로를 확인한 뒤 승인하세요.',plan)
        if self._pending is None or payload.get('plan') != self._pending or identity != self._pending_settings:
            raise ValueError('현재 설정으로 발급된 ECM 미리보기가 없습니다. 다시 확인하고 승인하세요.')
        plan = self._pending
        self._pending = None  # One approval authorizes one attempt only.
        with exclusive_ecm_job(), core.workspace_scope(cfg.get('workspace_url')):
            result = apply_ecm_plan(folder,cfg['ecm_title'],plan,local_path=target,log=self._log)
        return self._result('complete','Excel 저장을 확인했습니다. ECM 서버 체크인은 별도 확인이 필요합니다.',result)

    def _history(self, folder):
        path = core.path_bundle(folder)['db']
        if not path.exists():
            return []
        with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as cx:
            cx.row_factory = sqlite3.Row
            names = {r[0] for r in cx.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'v37_runs' not in names:
                return []
            runs = [dict(r) for r in cx.execute('SELECT run_id,started_at,finished_at,status FROM v37_runs ORDER BY started_at DESC LIMIT 30')]
            for run in runs:
                run['stages'] = []
                if 'v37_stages' in names:
                    for row in cx.execute('SELECT stage,status,elapsed_seconds,result_json FROM v37_stages WHERE run_id=? ORDER BY rowid',(run['run_id'],)):
                        stage = dict(row)
                        try:
                            detail = json.loads(stage.pop('result_json') or '{}')
                        except (ValueError, TypeError):
                            detail = {'error':'단계 진단 기록의 JSON 형식을 읽지 못했습니다.'}
                        if isinstance(detail,dict):
                            stage.update({k:detail[k] for k in ('error','message','warnings') if k in detail})
                        run['stages'].append(stage)
            return runs

    def _diagnose(self, cfg):
        if not core.IS_WINDOWS:
            return self._result('needs_action','Chrome/Driver 소유 검증은 회사 Windows에서 실행하세요. 이 컴퓨터의 브라우저는 변경하지 않았습니다.')
        with core.exclusive_browser_job():
            owners = core.inspect_windows_listeners()
            if not owners:
                return self._result('needs_action','Fastmarkets 전용 Chrome 9444가 실행 중이 아닙니다. 연결·로그인을 실행하세요.',{'port':9444})
            core.verify_chrome_owner(owners)
            metadata = core.cdp_version()
            if not str((metadata or {}).get('Browser','')).startswith('Chrome/'):
                raise ValueError('9444가 Chrome CDP인지 확인하지 못했습니다.')
            check = core.ChromeSession(self._log,driver_path=cfg.get('driver_path'))
            driver = check._attach_driver(owners=owners)
            try:
                capabilities = driver.capabilities
                version = capabilities.get('chrome',{}).get('chromedriverVersion','')
                result = dict(port=9444,chrome=metadata['Browser'],driver_version=version,
                              untouched_ports=[9222,9337])
            finally:
                driver.service.stop()
            return self._result('complete','Chrome·Driver·9444 소유 검증을 통과했습니다. 로그인 여부는 연결 버튼으로 확인하세요.',result)
