"""Ten-run offline structural benchmark, never a claim about live Windows speed."""
import argparse,json,statistics,time
from com_updates import contiguous_blocks

def run(repeats=10):
    if repeats<10:raise ValueError('비교 실행은 10회 이상 필요합니다.')
    # 20 managed cells + 1 intentionally untouched user column per row.
    edits=[dict(row=r,col=c if c<11 else c+1,incoming=r+c/100) for r in range(3,253) for c in range(2,22)]
    timings=[];failed=0;blocks=[]
    for _ in range(repeats):
        started=time.perf_counter()
        try:
            blocks=contiguous_blocks(edits)
            assert sum(b['width']*b['height'] for b in blocks)==len(edits)
            assert all(not b['col']<=11<b['col']+b['width'] for b in blocks)
        except Exception:failed+=1
        timings.append(time.perf_counter()-started)
    ordered=sorted(timings)
    return dict(synthetic=True,scope='CPU sparse block planning only; no browser or COM timing',runs=repeats,
        mean_seconds=statistics.mean(timings),p95_seconds=ordered[__import__('math').ceil(.95*repeats)-1],
        worst_seconds=max(timings),failure_rate=failed/repeats,
        before_numeric_write_calls=len(edits),after_numeric_write_calls=len(blocks),
        excludes='formula checks, Save/reopen, DRM, browser, network; not end-to-end 30% evidence')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--runs',type=int,default=10);a=p.parse_args()
    print(json.dumps(run(a.runs),ensure_ascii=False,indent=2))
