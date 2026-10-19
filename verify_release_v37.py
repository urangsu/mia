"""Reproducible local verification, logs separate from live Windows acceptance."""
from pathlib import Path
import argparse,json,os,py_compile,subprocess,sys,tempfile
from FastmarketsCollector_v3_4 import atomic_text,SAMPLE_JS

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--linkedom',type=Path);p.add_argument('--gui-smoke',action='store_true');a=p.parse_args()
    root=Path(__file__).parent.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    results={}
    def run(name,command):
        result=subprocess.run(command,cwd=root,text=True,capture_output=True,timeout=180)
        with atomic_text(out/(name+'.log')) as fp:fp.write(result.stdout+'\n'+result.stderr)
        results[name]={'exit_code':result.returncode,'command':list(map(str,command))}
        print(name+': '+str(result.returncode),flush=True)
        return result
    for path in root.glob('*.py'):py_compile.compile(str(path),doraise=True)
    results['compile']={'status':'passed','files':len(list(root.glob('*.py')))}
    run('regression',[sys.executable,'-m','unittest','discover','-s',str(root),'-p','test*.py','-v'])
    run('v37_resource_checks',[sys.executable,'-W','error::ResourceWarning','-m','unittest','discover','-s',str(root),'-p','test_v37*.py','-q'])
    benchmark=run('benchmark',[sys.executable,str(root/'benchmark_v37.py'),'--runs','10'])
    if benchmark.returncode==0:
        with atomic_text(out/'benchmark.json') as fp:fp.write(benchmark.stdout)
    if a.linkedom:
        with tempfile.TemporaryDirectory(prefix='fm37-dom-') as tmp:
            script=Path(tmp)/'sample.json'
            with atomic_text(script) as fp:json.dump(SAMPLE_JS,fp)
            run('dom_pinned',['node',str(root/'test_dom_harness.cjs'),str(script),str(a.linkedom.resolve())])
    if a.gui_smoke:run('gui_smoke',[sys.executable,str(root/'smoke_gui_v37.py')])
    results['live_windows']='NOT_RUN'
    with atomic_text(out/'results.json') as fp:json.dump(results,fp,ensure_ascii=False,indent=2)
    return 1 if any(isinstance(v,dict) and v.get('exit_code',0) for v in results.values()) else 0

if __name__=='__main__':sys.exit(main())
