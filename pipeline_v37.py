"""Independent source stages, durable run journal, one frozen report snapshot.

run_collection(settings, browser, cancelled, logger=print) keeps the v3.6 GUI
return contract. cancelled may be threading.Event or a zero-argument predicate.
export_only(settings) is browser-free; report_start/report_end/report_series
(or start/end/series) filter one immutable context shared by every format.
"""
import os
import time
import json
from pathlib import Path

import FastmarketsCollector_v3_4 as core
import excel_secure
import naver_markets
import report_exports
import report_model
import storage_runtime

IS_WINDOWS=os.name=='nt'


class _Cancel:
    def __init__(self,value): self.value=value
    def is_set(self):
        return bool(self.value.is_set() if hasattr(self.value,'is_set') else self.value())
    def __call__(self): return self.is_set()


def export_only(settings,*,_lock_held=False):
    """Never use an unpreserving non-Windows writer on an existing workbook."""
    from app_settings import reporting_identity
    workspace_url,workspace_id=reporting_identity(settings)
    if not _lock_held:
        with core.exclusive_browser_job(),core.workspace_scope(workspace_url):
            return export_only(settings,_lock_held=True)
    folder=Path(settings['data_dir']).expanduser()
    target=Path(settings.get('workbook_path') or core.path_bundle(folder)['xlsx']).expanduser()
    output={'workbook':None,'reports':{},'warnings':[],'snapshot_id':None,'status':'failed'}
    reports_only=bool(settings.get('reports_only',False))
    filters=('report_start','report_end','report_series','start','end','series')
    if not reports_only and any(settings.get(k) for k in filters):
        output['warnings'].append('필터가 지정된 누적 Excel 갱신은 금지됩니다. 보고서 전용 출력을 선택하세요.')
        return output
    try:
        context=report_model.build_context(folder,
            start=settings.get('report_start',settings.get('start')) or None,
            end=settings.get('report_end',settings.get('end')) or None,
            series=settings.get('report_series',settings.get('series')),
            workspace_id=settings.get('workspace_id') or workspace_id)
    except Exception as exc:
        output['warnings'].append('불변 보고 스냅샷 생성 실패: '+str(exc))
        return output
    output['snapshot_id']=context.snapshot_id
    output['warnings'].extend(context.warnings)
    if not reports_only:
        try:
            sheets=report_model.make_workbook_sheets(context)
            if IS_WINDOWS:
                output['workbook']=str(excel_secure.write_com_sheets(target,sheets))
            elif target.exists():
                raise RuntimeError('기존 누적 Excel 보존: 비 Windows에서는 기존 파일 갱신을 지원하지 않습니다. Windows Excel COM으로 갱신하세요.')
            else:
                target.parent.mkdir(parents=True,exist_ok=True)
                output['workbook']=str(report_exports.export_excel(context,target))
        except Exception as exc:
            output['warnings'].append('누적 Excel 갱신 실패: '+str(exc))
    try:
        output['reports']=report_exports.export_reports(context,
            Path(settings.get('report_dir') or folder/'reports').expanduser(),include_excel=False)
    except Exception as exc:
        output['warnings'].append('HTML/PPTX/JSON 보고서 출력 실패: '+str(exc))
    output['status']='partial' if output['warnings'] else 'complete'
    if output['workbook'] is None and not output['reports']:output['status']='failed'
    return output


def run_collection(settings,browser,cancelled,logger=print):
    """FMB/SMBS/NAVER failures are isolated; completed SQLite writes survive."""
    folder=Path(settings['data_dir']).expanduser()
    folder.mkdir(parents=True,exist_ok=True)
    db=core.path_bundle(folder)['db']
    cancel=_Cancel(cancelled)
    diag={'warnings':[],'fmb_failed':False,'fx':None,'naver':None,'workbook':None,
          'reports':{},'status':'failed','data_dir':str(folder),'stages':{}}
    output={'prices':0,'diag':diag,'cancelled':False}
    run_id=None
    started=time.monotonic()

    def stage(name,operation):
        tick=time.monotonic()
        try:
            result=operation()
            status=result.get('status','complete') if isinstance(result,dict) else 'complete'
            if isinstance(result,dict) and result.get('warnings') and status=='complete':status='partial'
        except Exception as exc:
            result={'warnings':[name+' 실패: '+str(exc)],'error':type(exc).__name__}
            status='failed'
        seconds=round(time.monotonic()-tick,3)
        diag['stages'][name]={'status':status,'elapsed':seconds}
        diag['warnings'].extend(result.get('warnings',[]) if isinstance(result,dict) else [])
        try:storage_runtime.save_stage(db,run_id,name,status,seconds,result)
        except Exception as exc:diag['warnings'].append('실행 단계 기록 실패: '+str(exc))
        logger(name+': '+status)
        return result,status

    def checkpoint():
        if cancel():
            output['cancelled']=True;diag['status']='cancelled'
            return True
        return False

    try:
        from app_settings import reporting_identity
        workspace_url,_=reporting_identity(settings)
        with core.exclusive_browser_job(),core.workspace_scope(workspace_url):
            storage_runtime.migrate_database(db)
            run_id=storage_runtime.start_run(db,settings)
            diag['run_id']=run_id
            if checkpoint():return output

            def fmb():
                workspace=core.current_workspace()[1]
                if settings.get('workspace_url'):
                    requested=core.verify_workspace_url(settings['workspace_url'])[1]
                    if requested!=workspace:
                        raise RuntimeError('요청 작업공간과 현재 브라우저 설정 불일치: 설정 저장 후 재시도하세요.')
                days=storage_runtime.incremental_days(db,workspace,int(settings.get('lookback_days',31)))
                rows,result=browser.scrape(days,folder,cancel,
                    workbook_path=settings.get('workbook_path') or None,defer_export=True)
                output['prices']=len(rows)
                result=dict(result or {})
                result['prices']=len(rows);result['effective_lookback_days']=days
                if not rows:result.setdefault('warnings',[]).append('FMB 신규 검증 수치 없음: 기존 SQLite 자료만 보존')
                return result
            if settings.get('fmb_enabled',True):
                fmb_result,fmb_status=stage('fmb',fmb)
            else:
                fmb_result,fmb_status=stage('fmb',lambda:{'status':'disabled'})
            diag['fmb_failed']=fmb_status not in ('complete','disabled')
            diag['fmb']=fmb_result
            if checkpoint():return output

            def fx():
                driver=browser.driver
                if driver is None:driver=browser.connect()
                result=core.fx_one_time(folder,settings.get('workbook_path') or None,
                    driver=driver,defer_export=True,gui_log=logger)
                result=dict(result or {})
                if not result.get('collected'):
                    result.setdefault('warnings',[]).append('SMBS 신규 검증 환율 없음: 기존 SQLite 자료만 보존')
                return result
            diag['fx'],_=stage('fx',fx if settings.get('fx_enabled',True) else lambda:{'status':'disabled'})
            if checkpoint():return output

            if settings.get('naver_enabled',True):
                def naver():
                    driver=browser.driver
                    if driver is None:driver=browser.connect()
                    return naver_markets.collect_and_save(driver,db,cancel,logger,
                        force=bool(settings.get('naver_force',False)))
                diag['naver'],_=stage('naver',naver)
                if diag['naver'].get('status') not in ('complete','skipped_daily'):
                    diag['warnings'].append('NAVER 수집 '+str(diag['naver'].get('status','failed'))+': 미검증/누락 수치를 성공으로 처리하지 않음')
            else:
                diag['naver']={'status':'disabled'}
            if checkpoint():return output

            def csv():
                core.export_files(folder)
                return {'status':'complete'}
            stage('csv',csv)
            if checkpoint():return output
            safe_settings={k:v for k,v in settings.items() if k not in ('report_start','report_end','report_series','start','end','series','reports_only')}
            exported,_=stage('export',lambda:export_only(safe_settings,_lock_held=True))
            diag['workbook']=exported.get('workbook')
            diag['reports']=exported.get('reports',{})
            diag['snapshot_id']=exported.get('snapshot_id')
            if checkpoint():return output
            diag['status']='partial' if diag['warnings'] or any(s['status'] in ('failed','partial') for s in diag['stages'].values()) else 'complete'
    except Exception as exc:
        diag['warnings'].append('수집 실행 중단: '+str(exc));diag['status']='failed'
    finally:
        diag['elapsed']=round(time.monotonic()-started,3)
        if run_id:
            try:storage_runtime.finish_run(db,run_id,diag['status'])
            except Exception as exc:diag['warnings'].append('실행 완료 기록 실패: '+str(exc))
        try:
            with core.atomic_text(core.path_bundle(folder)['diag']) as stream:
                json.dump(diag,stream,ensure_ascii=False,indent=2,default=str)
        except Exception as exc:diag['warnings'].append('진단 JSON 저장 실패: '+str(exc))
    return output
