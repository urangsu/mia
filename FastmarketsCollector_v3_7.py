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
    p.add_argument('--data-dir');p.add_argument('--workbook')
    p.add_argument('--start');p.add_argument('--end');p.add_argument('--series')
    p.add_argument('--with-fx',action='store_true',help='v3.6 호환; v3.7 전체 실행에 SMBS가 기본 포함됩니다')
    p.add_argument('--naver-force',action='store_true');p.add_argument('--no-naver',action='store_true')
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
    for key,value in (('data_dir',args.data_dir),('workbook_path',args.workbook),('lookback_days',args.days)):
        if value is not None:settings[key]=value
    settings.update(report_start=args.start,report_end=args.end,
                    report_series=args.series.split(',') if args.series else None,
                    reports_only=args.reports_only,naver_enabled=not args.no_naver,naver_force=args.naver_force)
    if args.start or args.end or args.series:
        if not args.reports_only:p.error('기간·종목 필터는 --reports-only에서만 사용하세요. 누적 원본 축소를 방지합니다.')
    if args.export_only or args.reports_only:
        from pipeline_v37 import export_only
        result=export_only(settings)
    elif args.once:
        from pipeline_v37 import run_collection
        folder=Path(settings['data_dir']);browser=core.ChromeSession(lambda m:core.log(folder,m))
        try:result=run_collection(settings,browser,threading.Event(),lambda m:core.log(folder,m))
        finally:browser.detach()
    else:
        from gui_v37 import main_gui
        main_gui();return 0
    print(json.dumps(result,ensure_ascii=False,indent=2,default=str))
    status=result.get('diag',result).get('status')
    return 0 if status=='complete' else 2

def schedule_daily(hhmm):
    from scheduler_v37 import register
    return register(hhmm)

if __name__=='__main__':sys.exit(main())
