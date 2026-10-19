"""Windows per-user scheduling. No elevation, passwords or new browser profile."""
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET
import os,re,subprocess,sys,tempfile

IS_WINDOWS=os.name=='nt'
TASK_NAME='FastmarketsCollectorDaily'
NS='http://schemas.microsoft.com/windows/2004/02/mit/task'

def task_xml(hhmm,user,script,python,now=None):
    if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',hhmm):raise ValueError('예약 시각은 HH:MM 형식입니다.')
    now=now or datetime.now();script=Path(script)
    root=ET.Element('Task',xmlns=NS,version='1.2')
    def add(parent,name,text=None,**attrs):
        element=ET.SubElement(parent,name,attrs)
        if text is not None:element.text=str(text)
        return element
    registration=add(root,'RegistrationInfo');add(registration,'Description','금속·환율·전일 종가 누적 및 보고서. ECM은 자동 쓰기하지 않습니다.')
    triggers=add(root,'Triggers');trigger=add(triggers,'CalendarTrigger')
    add(trigger,'Enabled','true');add(trigger,'StartBoundary',now.date().isoformat()+'T'+hhmm+':00')
    add(add(trigger,'ScheduleByDay'),'DaysInterval',1)
    principal=add(add(root,'Principals'),'Principal',id='Author')
    add(principal,'UserId',user);add(principal,'LogonType','InteractiveToken');add(principal,'RunLevel','LeastPrivilege')
    settings=add(root,'Settings')
    for name,value in [('MultipleInstancesPolicy','IgnoreNew'),('DisallowStartIfOnBatteries','false'),
        ('StopIfGoingOnBatteries','false'),('AllowHardTerminate','false'),('StartWhenAvailable','true'),
        ('RunOnlyIfNetworkAvailable','true'),('Enabled','true'),('WakeToRun','true'),('ExecutionTimeLimit','PT1H')]:add(settings,name,value)
    restart=add(settings,'RestartOnFailure');add(restart,'Interval','PT5M');add(restart,'Count',2)
    actions=add(root,'Actions',Context='Author');execute=add(actions,'Exec')
    add(execute,'Command',python);add(execute,'Arguments','"'+str(script)+'" --once')
    add(execute,'WorkingDirectory',script.parent)
    return ET.tostring(root,encoding='unicode')

def _run(args):
    result=subprocess.run(args,capture_output=True,text=True,errors='replace',timeout=25)
    if result.returncode:raise RuntimeError(result.stderr or result.stdout)
    return result.stdout.strip()

def register(hhmm='08:30'):
    if not IS_WINDOWS:raise RuntimeError('회사 Windows PC에서 예약 등록하세요. 이 컴퓨터에는 예약을 만들지 않았습니다.')
    user=_run(['whoami'])
    xml=task_xml(hhmm,user,Path(__file__).with_name('FastmarketsCollector_v3_7.py').resolve(),Path(sys.executable))
    # Scheduler imports UTF-16 XML from a bounded temporary file; no password saved.
    with tempfile.TemporaryDirectory(prefix='fm37-schedule-') as folder:
        path=Path(folder)/'task.xml'
        from FastmarketsCollector_v3_4 import atomic_text
        with atomic_text(path,encoding='utf-16') as fp:fp.write(xml)
        _run(['schtasks','/Create','/F','/TN',TASK_NAME,'/XML',str(path)])
    return status()

def status():
    if not IS_WINDOWS:raise RuntimeError('Windows에서 예약 상태를 조회하세요.')
    return _run(['schtasks','/Query','/TN',TASK_NAME,'/V','/FO','LIST'])

def remove():
    if not IS_WINDOWS:raise RuntimeError('Windows에서 예약을 해제하세요.')
    return _run(['schtasks','/Delete','/TN',TASK_NAME,'/F'])
