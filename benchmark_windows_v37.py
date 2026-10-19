"""Explicit warm acceptance benchmark; executes collection and local exports N times.

Use only on a permitted Windows test-data folder. Never runs ECM. A signed-in
desktop, verified Chrome 9444 and subscription are required. No paid APIs.
"""
import argparse,json,statistics,threading,math,sys
from datetime import datetime
from pathlib import Path
import FastmarketsCollector_v3_4 as core
from pipeline_v37 import run_collection

def main():
    p=argparse.ArgumentParser();p.add_argument('--runs',type=int,default=10)
    p.add_argument('--data-dir',required=True);p.add_argument('--confirm-test-run',action='store_true')
    a=p.parse_args()
    if not a.confirm_test_run:p.error('테스트 사본에 수집/출력을 반복합니다. --confirm-test-run 확인이 필요합니다.')
    if not core.IS_WINDOWS:p.error('Windows 회사 환경 전용입니다.')
    if a.runs<10:p.error('10회 이상 실행하세요.')
    settings=dict(core.config_load(),data_dir=a.data_dir,workbook_path=str(Path(a.data_dir)/'benchmark_prices.xlsx'))
    stages={};failed=0;results=[]
    browser=core.ChromeSession(lambda m:core.log(Path(a.data_dir),m))
    try:
        for _ in range(a.runs):
            result=run_collection(settings,browser,threading.Event())
            diag=result['diag'];failed+=diag['status']!='complete'
            results.append(diag)
            for name,stage in diag['stages'].items():stages.setdefault(name,[]).append(stage['elapsed'])
    finally:browser.detach()
    summary={name:dict(mean=statistics.mean(values),p95=sorted(values)[math.ceil(.95*len(values))-1],worst=max(values)) for name,values in stages.items()}
    report=dict(synthetic=False,actual_windows=True,runs=a.runs,failure_rate=failed/a.runs,stages=summary,results=results)
    output=Path(a.data_dir)/('warm_benchmark_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.json')
    with core.atomic_text(output) as fp:json.dump(report,fp,ensure_ascii=False,indent=2,default=str)
    print(output);return 0 if not failed else 2

if __name__=='__main__':sys.exit(main())
