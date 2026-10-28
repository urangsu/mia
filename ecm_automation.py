# -*- coding: utf-8 -*-
"""ECM 일반 Edge UIA 제어 모듈/독립 GUI. 실행: py ecm_automation.py.
9337 등 디버그 Edge는 제외. 새 프로필/브라우저/인증정보 복사를 사용하지 않음.
개발용 입력 확인: py ecm_automation.py --input-only.
"""
from __future__ import annotations

import re
import threading
import time
import os
import json
import subprocess
from contextlib import contextmanager
from queue import Queue, Empty
from urllib.parse import urlsplit

auto = None
pyperclip = None


def _load_backend():
    global auto, pyperclip
    if os.name != 'nt':
        raise RuntimeError('ECM 제어는 로그인된 Windows 일반 Edge에서 실행하세요.')
    if auto is None:
        try:
            import uiautomation as backend
            import pyperclip as clipboard
        except ImportError as exc:
            raise RuntimeError('ECM 패키지 설치: py -m pip install uiautomation pyperclip') from exc
        auto, pyperclip = backend, clipboard

ECM_HOST = "swpecm.posco.net"
TREE_LIMIT = 6000
SEARCH_TEXT = "금속 가격 현황"
TARGET_TITLE = "(리뉴얼)금속 가격 현황"


def safe_url(url):
    """세션 정보 보호: 주소의 쿼리스트링과 fragment는 기록하지 않는다."""
    try:
        parsed = urlsplit(url)
        return f"{parsed.hostname or '-'}{(':' + str(parsed.port)) if parsed.port else ''}{parsed.path}"
    except Exception:
        return "(인식 불가)"


def is_ecm(url):
    try:
        p = urlsplit(url.strip())
        return (p.scheme in ("http", "https")
                and (p.hostname or "").lower() == ECM_HOST
                and (p.port is None or p.port == 7091)
                and p.path.startswith("/ECM/"))
    except Exception:
        return False


def is_normal_edge_process(proc):
    cmd = str(proc.get('CommandLine') or '')
    return (str(proc.get('Name') or '').lower() == 'msedge.exe' and bool(cmd)
            and '--remote-debugging-' not in cmd.lower()
            and '--type=' not in cmd.lower())


def _edge_processes():
    script = ("$ErrorActionPreference='Stop'; "
              "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); "
              "ConvertTo-Json -InputObject @(Get-CimInstance Win32_Process -Filter \"Name='msedge.exe'\" "
              "| Select-Object ProcessId,Name,CommandLine) -Compress")
    try:
        r = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],
                           capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=12,
                           creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if r.returncode:raise RuntimeError('Edge 프로세스 조회 권한 오류')
        rows=json.loads(r.stdout.lstrip('\ufeff') or '[]')
        if isinstance(rows,dict):rows=[rows]
        return {int(p['ProcessId']):p for p in rows}
    except Exception as exc:
        raise RuntimeError('ECM Edge 프로세스를 검증할 수 없습니다. PowerShell/CIM 권한을 확인하세요.') from exc


def _browser_windows():
    processes = _edge_processes()
    wins=[]
    for w in auto.GetRootControl().GetChildren():
        try:
            if w.ClassName == 'Chrome_WidgetWin_1' and is_normal_edge_process(processes.get(w.ProcessId,{})):
                wins.append(w)
        except Exception:pass
    return wins


def _activate(win):
    try:win.ShowWindow(auto.ShowWindow.Restore)
    except Exception:pass
    win.SetActive()
    deadline=time.monotonic()+1.5
    while time.monotonic()<deadline:
        if auto.GetForegroundControl().NativeWindowHandle == win.NativeWindowHandle:
            return
        time.sleep(.05)
    raise RuntimeError('ECM 창 활성화 실패: 일반/관리자 권한 차이 또는 다른 창이 전면을 차지했습니다.')


def _read_current_url(win=None):
    marker = "__TTP_EMPTY_ECM_URL_7501__"
    for shortcut in ("{Ctrl}l", "{Alt}d"):
        if win is not None and auto.GetForegroundControl().NativeWindowHandle!=win.NativeWindowHandle:
            raise RuntimeError('주소 확인 중 활성 창이 변경되었습니다. 키 입력을 취소했습니다.')
        pyperclip.copy(marker)
        auto.SendKeys(shortcut)
        time.sleep(0.15)
        auto.SendKeys("{Ctrl}c")
        time.sleep(0.25)
        text = str(pyperclip.paste() or "").strip().strip('"')
        if text.startswith(("http://", "https://")) and text != marker:
            auto.SendKeys("{Esc}")
            return text
    auto.SendKeys("{Esc}")
    return ""


def _controls(root, limit=TREE_LIMIT):
    stack = [(root, 0)]
    count = 0
    while stack and count < limit:
        ctrl, depth = stack.pop()
        count += 1
        yield ctrl
        if depth >= 35:
            continue
        try:
            children = ctrl.GetChildren()
            stack.extend((c, depth + 1) for c in reversed(children))
        except Exception:
            pass


def _visible(ctrl):
    try:
        return not bool(ctrl.IsOffscreen)
    except Exception:
        return True


def _norm(name):
    return " ".join((name or "").replace("\u00a0", " ").split())


def _find_element(win, *, name=None, name_fragment=None, automation_id=None, timeout=0):
    deadline = time.monotonic() + timeout
    while True:
        weak_match = None
        for ctrl in _controls(win):
            try:
                n = _norm(ctrl.Name)
                a = ctrl.AutomationId or ""
                matches = ((automation_id and a == automation_id)
                           or (name and n == name)
                           or (name_fragment and name_fragment in n))
                if matches:
                    if _visible(ctrl):
                        return ctrl
                    weak_match = weak_match or ctrl
            except Exception:
                pass
        # Offscreen 요소는 실제 클릭할 수 없으므로 성공으로 간주하지 않는다.
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.4)


def _locate_ecm(log, *, require_menu=False):
    windows=_browser_windows()
    log(f"일반 Edge 창 {len(windows)}개 확인 (디버그/9337 창 제외)")
    for win in windows:
        # Inspect tab titles through UIA first. Never rotate unrelated tabs with Ctrl+Tab.
        tabs=[]
        for c in _controls(win):
            try:
                if c.ControlTypeName=='TabItemControl':tabs.append(c)
            except Exception:pass
        original=None
        for tab in tabs:
            try:
                if tab.GetSelectionItemPattern().IsSelected:original=tab;break
            except Exception:pass
        candidates=[c for c in tabs if any(t in _norm(c.Name).lower() for t in ('ecm','enterprise content'))]
        # If ECM is already active, address verification needs no tab switch.
        _activate(win)
        url=_read_current_url(win)
        if is_ecm(url) and (not require_menu or _find_element(win,name='중요 컨텐츠')):
            log('로그인 ECM 확인: '+safe_url(url))
            return win
        found=False
        try:
            for tab in candidates:
                tab.GetSelectionItemPattern().Select()
                url=_read_current_url(win)
                if is_ecm(url) and (not require_menu or _find_element(win,name='중요 컨텐츠',timeout=2)):
                    found=True
                    log('로그인 ECM 탭 확인: '+safe_url(url))
                    return win
        finally:
            if not found and original is not None:
                try:original.GetSelectionItemPattern().Select()
                except Exception:pass
    raise RuntimeError('일반 Edge의 로그인된 ECM 탭을 찾지 못했습니다. ECM 탭을 직접 선택한 뒤 재시도하세요. 관리자 Edge 권한 차이도 확인하세요.')


def _click(ctrl, *, double=False):
    try:
        ctrl.SetFocus()
    except Exception:
        pass
    if double:
        ctrl.DoubleClick()
    else:
        ctrl.Click()


SEARCH_PLACEHOLDER = "컨텐츠명 또는 소유자 검색"


def _is_edit(ctrl):
    """HTML input[type=text]는 대개 UIA EditControl로 노출된다."""
    try:
        name = str(ctrl.ControlTypeName or "").lower()
        if "edit" in name:
            return True
    except Exception:
        pass
    try:
        return ctrl.ControlType == auto.ControlType.EditControl
    except Exception:
        return False


def _rect(ctrl):
    try:
        r = ctrl.BoundingRectangle
        coords = (r.left, r.top, r.right, r.bottom)
        return coords if coords[2] > coords[0] and coords[3] > coords[1] else None
    except Exception:
        return None


def _search_input(win, timeout=6):
    """동일 문자열을 가진 상위 패널이 아니라 실제 EditControl만 선택한다.

    브라우저 접근성 AutomationId와 HTML id가 항상 일치하는 것은 아니므로,
    searchValueT 우선 -> placeholder(접근성 Name/HelpText) 순으로 확인한다.
    """
    deadline = time.monotonic() + timeout
    while True:
        candidates = []
        for ctrl in _controls(win):
            try:
                if not _is_edit(ctrl) or not _visible(ctrl) or not _rect(ctrl):
                    continue
                aid = (ctrl.AutomationId or "").strip()
                name = _norm(ctrl.Name)
                try:
                    help_text = _norm(ctrl.HelpText)
                except Exception:
                    help_text = ""
                score = 0
                if aid == "searchValueT":
                    score += 200
                if SEARCH_PLACEHOLDER in name:
                    score += 100
                if SEARCH_PLACEHOLDER in help_text:
                    score += 90
                if score:
                    candidates.append((score, ctrl))
            except Exception:
                continue
        if candidates:
            candidates.sort(key=lambda row: row[0], reverse=True)
            best_score = candidates[0][0]
            if sum(score == best_score for score, _ in candidates) == 1:
                return candidates[0][1]
            raise RuntimeError(
                "동일한 ECM 검색 입력창 후보가 여러 개 검색됐습니다. "
                "다른 ECM 탭을 닫거나 활성화한 뒤 다시 시도하세요."
            )
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.4)


def _same_edit(a, b):
    if b is None or not _is_edit(b):return False
    try:
        if auto.ControlsAreSame(a,b):return True
    except Exception:pass
    ar,br=_rect(a),_rect(b)
    return bool(ar and br and ar==br and _norm(a.Name)==_norm(b.Name)
                and a.ProcessId==b.ProcessId)


def _focus_search(win, edit):
    for _ in range(3):
        _activate(win)
        try:
            edit.Click(waitTime=0)
        except TypeError:
            edit.Click()
        except Exception:
            try:
                edit.SetFocus()
            except Exception:
                pass
        time.sleep(0.25)
        try:
            if _same_edit(edit, auto.GetFocusedControl()):
                return True
        except Exception:
            pass
        try:
            edit.SetFocus()
            time.sleep(0.15)
            if _same_edit(edit, auto.GetFocusedControl()):
                return True
        except Exception:
            pass
    return False


def _value_pattern(edit):
    try:
        return edit.GetValuePattern()
    except Exception:
        return None


def _read_edit_text(edit):
    """1순위 ValuePattern, 2순위 검색칸 안에서 Ctrl+A/C 복사."""
    pat = _value_pattern(edit)
    if pat is not None:
        try:
            return str(pat.Value or "")
        except Exception:
            pass

    try:
        focused = auto.GetFocusedControl()
        if not _same_edit(edit, focused):
            return None
        saved = pyperclip.paste()
        marker = "__TTP_READ_MARKER_38284__"
        try:
            pyperclip.copy(marker)
            auto.SendKeys("{Ctrl}a")
            auto.SendKeys("{Ctrl}c")
            time.sleep(0.2)
            read = str(pyperclip.paste() or "")
            return None if read == marker else read
        finally:
            pyperclip.copy(saved)
    except Exception:
        return None


def _input_search(win, log, search_text=None):
    search_text=search_text or SEARCH_TEXT
    """잘못된 곳에 쓰지 않도록 입력 전 포커스와 입력 후 값을 모두 검사."""
    edit = _search_input(win, timeout=6)
    if edit is None:
        raise RuntimeError(
            "HTML id=searchValueT에 대응하는 입력 요소를 찾지 못했습니다. "
            "Edge 접근성 트리에서 EditControl의 이름/AutomationId가 노출되는지 확인해야 합니다."
        )
    try:
        log(f"검색칸 선택: EditControl / AutomationId={edit.AutomationId or '(미노출)'} "
            f"/ Name={_norm(edit.Name) or '(미노출)'}")
    except Exception:
        log("검색칸 선택: EditControl")

    focused = _focus_search(win, edit)
    if focused:
        # 한글 IME 조합 상태에서 키보드 타이핑이 어긋나는 경우를 피한다.
        # Ctrl+A/V는 대상 EditControl 포커스가 확인된 뒤에만 전송한다.
        previous = None
        try:
            previous = pyperclip.paste()
            pyperclip.copy(search_text)
            auto.SendKeys("{Ctrl}a")
            auto.SendKeys("{Ctrl}v")
            time.sleep(0.4)
            observed = _read_edit_text(edit)
            if observed == search_text:
                log("[입력 성공] 클립보드 붙여넣기 후 검색창 값 일치 확인")
                return edit
            log("[입력 재시도] 붙여넣기 후 검색창 값 불일치 또는 값 읽기 실패")
        finally:
            if previous is not None:
                pyperclip.copy(previous)
    else:
        log("[입력 진단] 검색칸에 키보드 포커스가 확인되지 않아 잘못된 위치에 타이핑하지 않았습니다.")

    # ValuePattern은 입력창을 직접 설정하므로 IME/포커스 문제에 대한 차선책이다.
    # ECM은 검색 시 input.value를 읽으므로 이 방법으로도 검색어 전달 가능하다.
    pat = _value_pattern(edit)
    if pat is not None:
        try:
            pat.SetValue(search_text)
            time.sleep(0.3)
            observed = _read_edit_text(edit)
            if observed == search_text:
                log("[입력 성공] UI Automation ValuePattern으로 검색창 값 일치 확인")
                return edit
        except Exception as ex:
            log(f"[입력 진단] ValuePattern 입력 실패: {type(ex).__name__}")

    raise RuntimeError(
        f"ECM 검색창에 {search_text!r}을 정확히 입력하지 못했습니다. "
        "검색을 진행하지 않았습니다. 위 검색칸/포커스 진단 로그를 보내주세요."
    )


def _submit_search(win, edit, log, search_text=None):
    if _read_edit_text(edit) != (search_text or SEARCH_TEXT):
        raise RuntimeError('검색 직전 입력값 변경: 검색 취소')
    button=_find_element(win,automation_id='simpleSrchT',timeout=1)
    if button is None:
        button=_find_element(win,name='검색',timeout=1)
    if button is None:
        raise RuntimeError('검색 버튼 simpleSrchT/검색 접근성 요소를 찾지 못했습니다. 임의 Enter를 전송하지 않았습니다.')
    try:button.GetInvokePattern().Invoke()
    except Exception:_click(button)
    log('[3/5] 검색 버튼 실행')


def _is_target_link(ctrl, target_title=None):
    from ecm_names import file_matches
    target_title=target_title or TARGET_TITLE
    try:
        return (ctrl.ControlTypeName=='HyperlinkControl'
                and file_matches(_norm(ctrl.Name),target_title,allow_stem=True)
                and _visible(ctrl) and _rect(ctrl) is not None)
    except Exception:return False


def _target_file(win, timeout=14, target_title=None):
    deadline=time.monotonic()+timeout
    while True:
        matches=[c for c in _controls(win) if _is_target_link(c, target_title)]
        if len(matches)==1:return matches[0]
        if len(matches)>1:
            raise RuntimeError('동일 이름의 ECM 링크가 여러 개입니다. 경로/소유자를 확인해야 하므로 클릭을 취소했습니다.')
        if time.monotonic()>=deadline:return None
        time.sleep(.12)


def link_click_point(rect):
    left,top,right,bottom=rect
    if right-left<4 or bottom-top<4:raise RuntimeError('링크 영역이 너무 작습니다.')
    # A Chromium UIA hyperlink can span an entire table cell. Prefer its left text region.
    x=int(left+min(65,max(2,(right-left)*.20)))
    y=int(top+(bottom-top)/2)
    return x,y


def _ancestor_target(ctrl, item):
    for _ in range(8):
        if ctrl is None:return False
        try:
            if auto.ControlsAreSame(ctrl,item):return True
        except Exception:pass
        if _is_target_link(ctrl) and _rect(ctrl)==_rect(item) and ctrl.ProcessId==item.ProcessId:
            return True
        try:ctrl=ctrl.GetParentControl()
        except Exception:return False
    return False


def _double_click_link(item, log, target_title=None):
    if not _is_target_link(item, target_title):raise RuntimeError('더블클릭 대상이 실제 파일 Hyperlink가 아닙니다.')
    try:item.GetScrollItemPattern().ScrollIntoView()
    except Exception:pass
    rect=_rect(item)
    if not rect:raise RuntimeError('링크 좌표를 읽을 수 없습니다.')
    # Candidate points stay within the leftmost 120 physical pixels. Hit-test every point.
    first=link_click_point(rect)
    points=[first]+[(int(rect[0]+offset),first[1]) for offset in (24,40,90,120)
                   if rect[0]+offset<rect[2]-2]
    chosen=None
    for x,y in points:
        hit=auto.ControlFromPoint(x,y)
        if _ancestor_target(hit,item):chosen=(x,y);break
    if chosen is None:
        log(f'클릭 거부: 링크={_norm(item.Name)}, rect={rect}, 후보={points}')
        raise RuntimeError('링크 위 클릭 지점이 파일 링크로 확인되지 않았습니다. 오버레이/DPI/스크롤 상태를 확인하세요.')
    current=_rect(item)
    if current!=rect:
        raise RuntimeError('클릭 직전 링크 위치가 변경되었습니다. 재검색하세요.')
    x,y=chosen
    log(f'파일 링크 클릭: name={_norm(item.Name)}, type=HyperlinkControl, rect={rect}, point=({x},{y})')
    # UIA's DoubleClick supports offsets; no default center and no guessed row click.
    item.DoubleClick(x=x-int(rect[0]),y=y-int(rect[1]),simulateMove=False,waitTime=0)


def _open_documents(target_title=None):
    documents=set()
    from ecm_names import split_name
    expected=split_name(target_title or TARGET_TITLE)[0]
    for win in auto.GetRootControl().GetChildren():
        try:
            if win.ClassName not in {'XLMAIN','Chrome_WidgetWin_1'}:continue
            if win.ClassName=='XLMAIN' and expected in _norm(win.Name):
                documents.add(('Excel',win.NativeWindowHandle,_norm(win.Name)))
            for c in _controls(win,limit=1200):
                if c.ControlTypeName=='DocumentControl' and expected in _norm(c.Name):
                    documents.add(('Document',win.NativeWindowHandle,_norm(c.Name)))
        except Exception:pass
    return documents


def _wait_open(before, timeout=12, target_title=None):
    deadline=time.monotonic()+timeout
    while True:
        opened=_open_documents(target_title)-before
        if opened:return sorted(opened)[0]
        if time.monotonic()>=deadline:
            raise RuntimeError('링크 더블클릭은 전송했으나 새 Excel/문서 접근성 화면을 확인하지 못했습니다. 중복 클릭하지 않았습니다. 다운로드/보안 팝업을 확인하세요.')
        time.sleep(.15)


def _open_important_contents(win, log):
    tab = _find_element(win, name="중요 컨텐츠", timeout=5)
    if tab is None:
        raise RuntimeError("'중요 컨텐츠' 탭이 더 이상 보이지 않습니다. 로그인 상태를 확인하세요.")
    _click(tab)
    log("[1/5] 중요 컨텐츠 클릭")


def run_input_only(log, search_text=None, target_title=None):
    """검색창 입력 오류만 안전하게 재현·확인한다. 실제 조회/파일 열기는 하지 않는다."""
    win = _locate_ecm(log, require_menu=True)
    _activate(win)
    _open_important_contents(win, log)
    _input_search(win, log,search_text)
    return f"검색창에 {search_text or SEARCH_TEXT!r}이 정확히 들어간 것을 검증했습니다. 검색이나 파일 열기는 실행하지 않았습니다."


def run_ecm_control(log, search_text=None, target_title=None):
    win = _locate_ecm(log, require_menu=True)
    _activate(win)
    log("기존 로그인 브라우저 사용. 디버그 포트/Selenium은 사용하지 않습니다.")
    _open_important_contents(win, log)

    search = _input_search(win, log,search_text) if search_text is not None else _input_search(win, log)
    log('[2/4] ECM 검색어 입력 검증 완료')
    _submit_search(win, search, log,search_text) if search_text is not None else _submit_search(win,search,log)

    item = _target_file(win,target_title=target_title) if target_title is not None else _target_file(win)
    if item is None:
        raise RuntimeError(
            f"검색 결과의 {target_title or TARGET_TITLE!r} 링크를 찾지 못했습니다. "
            "실제 검색 결과가 표시되는지, Edge 접근성 트리에 링크가 노출되는지 확인하세요."
        )
    before=_open_documents(target_title)
    if before:
        return '목표 문서가 이미 열려 있습니다. 중복 더블클릭을 생략했습니다.'
    if not is_ecm(_read_current_url(win)):
        raise RuntimeError('클릭 직전 ECM 탭 주소가 변경되었습니다.')
    _double_click_link(item,log,target_title)
    opened=_wait_open(before,target_title=target_title)
    log('[5/5] 문서 열림 확인: '+opened[0])
    return '목표 Excel/문서 화면 열림을 접근성으로 확인했습니다.'


@contextmanager
def exclusive_ecm_job():
    folder=__import__('pathlib').Path(os.environ.get('LOCALAPPDATA') or __import__('pathlib').Path.home())/'FastmarketsCollector'
    folder.mkdir(parents=True,exist_ok=True)
    with (folder/'ecm_ui.lock').open('a+b') as fp:
        fp.seek(0,2)
        if fp.tell()==0:fp.write(b'0');fp.flush()
        fp.seek(0)
        import msvcrt
        try:msvcrt.locking(fp.fileno(),msvcrt.LK_NBLCK,1)
        except OSError as exc:raise RuntimeError('다른 ECM 작업이 실행 중입니다.') from exc
        try:yield
        finally:
            fp.seek(0);msvcrt.locking(fp.fileno(),msvcrt.LK_UNLCK,1)


def execute(log, input_only=False, *, search_text=None, target_title=None):
    _load_backend()
    # UIA and physical screen points must share a DPI coordinate space.
    try:
        import ctypes
        ctypes.windll.user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:pass
    with exclusive_ecm_job(), auto.UIAutomationInitializerInThread():
        try:
            saved=pyperclip.paste()
        except Exception:saved=None
        try:
            fn=(run_input_only if input_only else run_ecm_control)
            return fn(log, search_text, target_title) if search_text is not None or target_title is not None else fn(log)
        finally:
            if saved is not None:
                try:pyperclip.copy(saved)
                except Exception:pass


def main():
    import tkinter as tk
    from tkinter import ttk, scrolledtext, messagebox
    root=tk.Tk();root.title('ECM · 기존 로그인 Edge');root.geometry('760x480')
    q=Queue();busy=False
    panel=ttk.Frame(root,padding=16);panel.pack(fill='both',expand=True)
    ttk.Label(panel,text='ECM 금속 가격 파일 열기',font=('Malgun Gothic',14,'bold')).pack(anchor='w')
    ttk.Label(panel,text='일반 Edge에서 ECM에 로그인하세요. 작업 중 마우스·키보드 조작을 멈춰주세요.').pack(pady=10)
    state=tk.StringVar(value='준비')
    ttk.Label(panel,textvariable=state).pack(anchor='w')
    box=scrolledtext.ScrolledText(panel,state='disabled');box.pack(fill='both',expand=True,pady=10)
    def start(input_only=False):
        nonlocal busy
        if busy:return
        busy=True;button.configure(state='disabled');state.set('진행 중')
        def work():
            try:q.put(('done',execute(lambda s:q.put(('log',s)),input_only)))
            except Exception as exc:q.put(('error',str(exc)))
        threading.Thread(target=work,daemon=True).start()
    button=ttk.Button(panel,text='ECM 컨트롤 · 검색 → 엑셀 열기',command=start);button.pack(fill='x')
    def pump():
        nonlocal busy
        while True:
            try:kind,msg=q.get_nowait()
            except Empty:break
            box.configure(state='normal');box.insert('end',msg+'\n');box.see('end');box.configure(state='disabled')
            if kind in ('done','error'):
                busy=False;button.configure(state='normal');state.set(msg)
                if kind=='error':messagebox.showerror('ECM',msg)
        root.after(100,pump)
    def close():
        if busy:state.set('작업 종료 후 닫아주세요.');return
        root.destroy()
    root.protocol('WM_DELETE_WINDOW',close);root.after(100,pump);root.mainloop()


if __name__=='__main__':
    import sys
    if '--input-only' in sys.argv:
        print(execute(print,input_only=True))
    else:main()
