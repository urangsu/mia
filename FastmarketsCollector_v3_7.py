"""v3.7 entry point. Interactive sessions remain owned by the user."""
from pathlib import Path
import argparse,json,sys,threading
import FastmarketsCollector_v3_4 as core

def main(argv=None):
    p=argparse.ArgumentParser(description='Fastmarkets v3.7 · Chrome 9444 전용')
    mode=p.add_mutually_exclusive_group()
    mode.add_argument('--once',action='store_true')
    mode.add_argument('--export-only',action='store_true')
    mode.add_argument('--reports-only',action='store_true')
    mode.add_argument('--diagnose',action='store_true')
    p.add_argument('--days',type=int)
    p.add_argument('--data-dir');p.add_argument('--workbook');p.add_argument('--report-dir')
    p.add_argument('--start');p.add_argument('--end');p.add_argument('--series')
    p.add_argument('--with-fx',action='store_true',help='v3.6 호환; v3.7 전체 실행에 SMBS가 기본 포함됩니다')
    p.add_argument('--naver-force',action='store_true',default=None)
    p.add_argument('--no-naver',action='store_true',default=None)
    p.add_argument('--public-only',action='store_true',help='브라우저 없이 FDR 공개 종가만 수집')
    p.add_argument('--no-fdr',action='store_true',default=None)
    p.add_argument('--fdr-force',action='store_true',default=None,help='일일 FDR 캐시를 건너뛰고 정정 이력 재확인')
    p.add_argument('--legacy-gui',action='store_true',help='기존 Tkinter 화면으로 실행')
    p.add_argument('--schedule',metavar='HH:MM',help='로그인한 Windows 사용자 일일 예약 등록')
    p.add_argument('--schedule-status',action='store_true')
    p.add_argument('--unschedule',action='store_true')
    args=p.parse_args(argv)
    if args.days is not None and not 0<=args.days<=3650:p.error('--days 범위는 0~3650입니다')
    if args.diagnose:
        from diagnose_windows import main as diagnose
        previous=sys.argv;sys.argv=[previous[0]]
        try:return diagnose()
        finally:sys.argv=previous
    if args.schedule:
        print(schedule_daily(args.schedule));return 0
    if args.schedule_status or args.unschedule:
        from scheduler_v37 import status,remove
        print(remove() if args.unschedule else status());return 0
    settings=core.config_load()
    for key,value in (('data_dir',args.data_dir),('workbook_path',args.workbook),('lookback_days',args.days),('report_dir',args.report_dir)):
        if value is not None:settings[key]=value
    settings.update(report_start=args.start,report_end=args.end,
                    report_series=args.series.split(',') if args.series else None,
                    reports_only=args.reports_only)
    if args.no_naver is not None:settings['naver_enabled']=not args.no_naver
    if args.naver_force is not None:settings['naver_force']=args.naver_force
    if args.public_only:settings.update(fmb_enabled=False,fx_enabled=False,naver_enabled=False,fdr_enabled=True)
    if args.no_fdr is not None:settings['fdr_enabled']=not args.no_fdr
    if args.fdr_force is not None:settings['fdr_force']=args.fdr_force
    if args.start or args.end or args.series:
        if not args.reports_only:p.error('기간·종목 필터는 --reports-only에서만 사용하세요. 누적 원본 축소를 방지합니다.')
    if args.once or args.export_only or args.reports_only:
        from app_settings import validate
        try:
            if settings.get('_settings_warning'):
                raise ValueError(settings['_settings_warning'])
            settings=validate(settings,'collect' if args.once else 'reports' if args.reports_only else 'export')
        except (ValueError,TypeError) as exc:
            print('설정 확인 필요: '+str(exc),file=sys.stderr)
            return 2
    if args.export_only or args.reports_only:
        from pipeline_v37 import export_only
        result=export_only(settings)
    elif args.once:
        from pipeline_v37 import run_collection
        folder=Path(settings['data_dir'])
        needs_browser=any(settings.get(k,True) for k in ('fmb_enabled','fx_enabled','naver_enabled'))
        browser=core.ChromeSession(lambda m:core.log(folder,m),driver_path=settings.get('driver_path')) if needs_browser else None
        try:result=run_collection(settings,browser,threading.Event(),lambda m:core.log(folder,m))
        finally:
            if browser is not None:browser.detach()
    else:
        if args.legacy_gui:
            from gui_v37 import main_gui
        else:
            try:
                from desktop_ui import main_gui
            except ImportError as exc:
                print('새 화면 의존성이 없습니다. py -m pip install -r requirements-desktop.txt 실행 후 다시 시작하세요.\n'
                      '기존 화면: py FastmarketsCollector_v3_7.py --legacy-gui',file=sys.stderr)
                return 2
        main_gui();return 0
    print(json.dumps(result,ensure_ascii=False,indent=2,default=str))
    status=result.get('diag',result).get('status')
    return 0 if status=='complete' else 2

def schedule_daily(hhmm):
    from scheduler_v37 import register
    return register(hhmm)

if __name__=='__main__':sys.exit(main())
