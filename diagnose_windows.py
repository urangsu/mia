"""Read-only Fastmarkets 9444 diagnostic. No browser launch, navigation, or secrets."""
import argparse
import json
import os
import sys
import time
from pathlib import Path
import FastmarketsCollector_v3_4 as fm


def main():
    parser=argparse.ArgumentParser(description="Fastmarkets 9444-only diagnostic")
    parser.add_argument("--driver-check",action="store_true", help="Attach chromedriver to EXISTING verified 9444 without navigating or closing tabs")
    args=parser.parse_args()
    start=time.perf_counter()
    result={'windows':os.name=='nt','port':9444,'profile':str(fm.CHROME_PROFILE),
            'checked':'Only Fastmarkets 9444. Ports 9222/9337 are not queried.'}
    if os.name!='nt':
        result['status']='unsupported';result['error']='Windows에서 실행하세요.'
    else:
        try:
            owners=fm.inspect_windows_listeners()
            # Intentionally omit CommandLine and any URLs/tokens from diagnostic output.
            result['listeners']=[{'pid':p.get('pid'),'name':p.get('name'),'local_address':p.get('local_address')} for p in owners]
            if owners:
                fm.verify_chrome_owner(owners)
                metadata=fm.cdp_version()
                result['chrome']=str((metadata or {}).get('Browser') or '')
                result['status']='verified' if result['chrome'].startswith('Chrome/') else 'bad_cdp'
                if result['status']=='verified' and args.driver_check:
                    session=fm.ChromeSession()
                    # Connect only to verified 9444; _attach_driver will NOT switch or navigate tabs.
                    try:
                        driver=session._attach_driver(owners=owners)
                        result['driver_status']='connected'
                        result['driver_version']=str(getattr(driver,'capabilities',{}).get('chrome',{}).get('chromedriverVersion','')).split(' ')[0]
                    except Exception as exc:
                        result['status']='driver_failed'
                        result['error']=fm._safe_driver_error(exc)
                    finally:
                        if 'driver' in locals():
                            try:driver.service.stop()
                            except Exception:pass
            else:result['status']='not_running'
        except (fm.SessionError, OSError, RuntimeError) as exc:
            result['status']='rejected';result['error']=fm._safe_driver_error(exc)
    result['seconds']=round(time.perf_counter()-start,3)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['status'] in {'verified','not_running'} else 1

if __name__=='__main__':sys.exit(main())
