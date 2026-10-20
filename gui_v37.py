# -*- coding: utf-8 -*-
"""Task-based Windows UI. UI concepts inspired by provided Toss style reference.
No third-party fonts/assets bundled; native Malgun Gothic fallback.
"""
from __future__ import annotations
from pathlib import Path
from queue import Queue, Empty
import threading, traceback

# DESIGN.md reference: restrained dark surfaces; no proprietary assets/fonts.
BLUE='#4391ff';BLUE_DARK='#2562b9';INK='#f3e9e9';MUTED='#a2a2ab'
SOFT='#202025';BORDER='#35353f';WHITE='#101013';RED='#f5445a'


def main_gui():
    import tkinter as tk
    from tkinter import ttk,messagebox,filedialog
    import FastmarketsCollector_v3_4 as core
    from ecm_excel_sync import prepare_ecm_plan, apply_ecm_plan, write_json, ECMBlocked
    from ecm_automation import execute as ecm_open
    from ecm_binding import bind_open
    from pipeline_v37 import run_collection,export_only
    cfg=core.config_load()
    root=tk.Tk()
    root.title('금속·시장 데이터  |  Fastmarkets Collector v3.7')
    root.geometry('1180x900');root.minsize(980,760);root.configure(bg=WHITE)
    family='맑은 고딕' if core.IS_WINDOWS else 'Arial'
    root.option_add('*Font',f'{{{family}}} 10')
    style=ttk.Style(root)
    if 'clam' in style.theme_names():style.theme_use('clam')
    style.configure('Treeview',rowheight=26,background=WHITE,fieldbackground=WHITE,foreground=INK)
    style.configure('Treeview.Heading',background=SOFT,foreground=INK,font=(family,10,'bold'))
    style.configure('TNotebook',background=WHITE,borderwidth=0)
    style.configure('TNotebook.Tab',padding=(16,8))
    style.configure('TEntry',fieldbackground=SOFT,foreground=INK,insertcolor=INK)
    style.map('Treeview',background=[('selected','#243956')])
    q=Queue();cancel=threading.Event();busy=[False];browser=core.ChromeSession(lambda m:q.put(('log',m)))
    save_dir=tk.StringVar(value=cfg['data_dir'])
    excel_path=tk.StringVar(value=cfg.get('workbook_path',''))
    lookback=tk.StringVar(value=str(cfg.get('lookback_days',31)))
    lme_enabled=tk.BooleanVar(value=bool(cfg.get('lme_enabled',True)))
    workspace=tk.StringVar(value=cfg.get('workspace_url',core.WORKSPACE_URL))
    ecm_title=tk.StringVar(value=('fastmarkets_prices.xlsx' if cfg.get('ecm_title')=='(리뉴얼)금속 가격 현황' else cfg.get('ecm_title','fastmarkets_prices.xlsx')))
    ecm_search=tk.StringVar(value=('fastmarkets_prices' if cfg.get('ecm_search')=='금속 가격 현황' else cfg.get('ecm_search','fastmarkets_prices')))
    username=tk.StringVar(value='');password=tk.StringVar(value='')
    report_start=tk.StringVar();report_end=tk.StringVar();report_series=tk.StringVar()
    schedule_time=tk.StringVar(value=cfg.get('v37_auto_time','08:30'))
    status=tk.StringVar(value='대기 · 수집 파일 경로와 ECM 문서명을 확인하세요.')
    details=tk.StringVar(value='FMB: 미실행  |  SMBS: 미실행  |  누적 Excel: 미확인  |  ECM: 미연결')
    running_buttons=[]
    pending={'plan':None}

    def L(parent,text='',size=10,bold=False,color=INK,**kw):
        return tk.Label(parent,text=text,font=(family,size,'bold' if bold else 'normal'),
                        bg=parent.cget('bg') if 'bg' in parent.keys() else WHITE,fg=color,**kw)
    def safe_config():
        url,_=core.verify_workspace_url(workspace.get())
        days=int(lookback.get())
        if not 0<=days<=3650:raise ValueError('수집 기간은 0~3650일로 입력하세요.')
        if not save_dir.get().strip():raise ValueError('저장 폴더를 선택하세요.')
        if excel_path.get().strip() and Path(excel_path.get().strip()).suffix.lower()!='.xlsx':
            raise ValueError('누적 Excel은 .xlsx 파일만 지원합니다.')
        if not ecm_search.get().strip():raise ValueError('ECM 검색어를 입력하세요.')
        if not ecm_title.get().strip().lower().endswith('.xlsx'):
            raise ValueError('ECM 업로드 문서명은 .xlsx까지 정확하게 입력하세요.')
        name=ecm_title.get().strip()
        if '/' in name or '\\' in name:raise ValueError('ECM 문서명은 경로가 아닌 파일명만 입력하세요.')
        out=dict(cfg)
        out.update(data_dir=str(Path(save_dir.get()).expanduser()),workbook_path=excel_path.get().strip(),
                   lookback_days=days,workspace_url=url,ecm_title=name,ecm_search=ecm_search.get().strip(),
                   v37_auto_time=schedule_time.get().strip(),lme_enabled=bool(lme_enabled.get()))
        from datetime import date
        for value in (report_start.get(),report_end.get()):
            if value.strip():date.fromisoformat(value.strip())
        core.config_save(out)
        return out
    def emit(msg):q.put(('log',msg))
    def syslog(msg):
        core.log(Path(save_dir.get()),msg)
    def launch(title,fn,kind='work'):
        if busy[0]:return
        try:settings=safe_config()
        except Exception as exc:
            messagebox.showerror('설정 오류',str(exc));return
        busy[0]=True;cancel.clear();status.set(f'{title} 진행 중')
        for b in running_buttons:b.configure(state='disabled')
        cancel_button.configure(state='normal' if kind in ('collect','collect_ecm') else 'disabled')
        def job():
            try:
                result=fn(settings)
                if result is False:raise RuntimeError('작업 성공을 확인하지 못했습니다. Chrome 로그인 화면과 연결 진단을 확인하세요.')
                q.put(('done',title,kind,result))
            except Exception as exc:
                trace=''.join(traceback.format_exception(type(exc),exc,exc.__traceback__))
                try:
                    (Path(settings['data_dir'])/'collector_error_trace.log').open('a',encoding='utf8').write(f'{title}\n{trace[-6500:]}\n')
                except OSError:pass
                q.put(('fail',title,str(exc)))
        threading.Thread(target=job,daemon=True,name='collector-v36-worker').start()

    def snapshot_target(settings):
        return settings['workbook_path'] or str(core.path_bundle(Path(settings['data_dir']))['xlsx'])

    def collect(settings):
        result=run_collection(settings,browser,cancel,emit)
        queue_snapshot(settings['data_dir'])
        return result

    def queue_snapshot(folder):
        try:
            from report_model import build_context
            q.put(('snapshot',build_context(Path(folder))))
        except Exception as exc:emit('저장된 시세 조회 실패: '+str(exc))

    def preview_ecm(settings):
        folder=Path(settings['data_dir'])
        emit('일반 Edge에서 ECM 문서 검색·열기; 9222/9337/9444 브라우저 변경 안 함')
        # execute() acquires its own single-instance ECM UIA lock.
        # Do not nest exclusive_ecm_job: Windows msvcrt locks are not re-entrant.
        bound=bind_open(folder,settings['ecm_title'],snapshot_target(settings),lambda:
            ecm_open(lambda m:emit('ECM: '+m),search_text=settings['ecm_search'],
                     target_title=settings['ecm_title']))
        plan=prepare_ecm_plan(folder,settings['ecm_title'],local_path=snapshot_target(settings),
                              target_fullname=bound['full_name'],target_hwnd=bound['excel_hwnd'],log=emit)
        write_json(folder/'ecm_sync_plan.json',plan)
        return plan

    def apply_ecm(settings):
        plan=pending['plan']
        if not plan:raise ECMBlocked('승인된 ECM 미리보기가 없습니다.')
        from ecm_automation import exclusive_ecm_job
        with exclusive_ecm_job():
            result=apply_ecm_plan(Path(settings['data_dir']),settings['ecm_title'],plan,
                                 local_path=snapshot_target(settings),log=emit)
        write_json(Path(settings['data_dir'])/'ecm_sync_result.json',result)
        return result

    def request_sync():launch('ECM 파일 확인·반영 미리보기',preview_ecm,'ecm_preview')
    def request_collect(with_ecm=False):launch('전체 작업' if with_ecm else '시세 수집·Excel 갱신',collect,
                                              'collect_ecm' if with_ecm else 'collect')

    root.columnconfigure(0,weight=1)
    header=tk.Frame(root,bg=WHITE,padx=26,pady=18);header.pack(fill='x')
    L(header,'매일 쌓이는 시장 데이터',size=22,bold=True).pack(anchor='w')
    L(header,'Fastmarkets · SMBS · NAVER   /   누적 Excel · 편집 가능한 보고서 · ECM',size=10,color=MUTED).pack(anchor='w',pady=(4,0))
    current_file=tk.StringVar()
    def refresh_file(*_):
        current_file.set('누적 Excel  ' + (excel_path.get().strip() or str(core.path_bundle(Path(save_dir.get() or '.'))['xlsx'])))
    save_dir.trace_add('write',refresh_file);excel_path.trace_add('write',refresh_file);refresh_file()
    tk.Label(header,textvariable=current_file,bg=WHITE,fg=MUTED,font=(family,9),anchor='w').pack(fill='x',pady=(5,0))
    top=tk.Frame(root,bg=WHITE,padx=26);top.pack(fill='x')
    L(top,'오늘의 작업',size=13,bold=True).pack(anchor='w',pady=(0,10))
    acts=tk.Frame(top,bg=WHITE);acts.pack(fill='x')
    acts.grid_columnconfigure(0,weight=1);acts.grid_columnconfigure(1,weight=1);acts.grid_columnconfigure(2,weight=1)
    def action(text,sub,fn,primary=False):
        i=len(running_buttons)
        panel=tk.Frame(acts,bg=WHITE,highlightthickness=1,highlightbackground=BORDER)
        panel.grid(row=0,column=i,sticky='nsew',padx=(0,10) if i<2 else 0)
        btn=tk.Button(panel,text=text,command=fn,bg=BLUE if primary else SOFT,
                      fg=WHITE if primary else INK,activebackground=BLUE_DARK if primary else BORDER,
                      activeforeground=WHITE if primary else INK,relief='flat',cursor='hand2',
                      font=(family,11,'bold'),pady=13)
        btn.pack(fill='x',padx=10,pady=(10,6))
        L(panel,sub,size=9,color=MUTED,wraplength=270,justify='left').pack(anchor='w',padx=12,pady=(0,12))
        running_buttons.append(btn)
    action('전체 실행','금속·환율·시장 → 누적 Excel·보고서 → ECM 승인',lambda:request_collect(True),True)
    action('시세 수집·Excel 갱신','ECM은 건드리지 않고 누적 자료만 갱신',lambda:request_collect(False))
    action('ECM 반영·재시도','재수집 없이 ECM 파일의 필요한 셀만 갱신',request_sync)

    sframe=tk.Frame(root,bg=SOFT,padx=16,pady=12);sframe.pack(fill='x',padx=26,pady=(14,8))
    tk.Label(sframe,textvariable=status,bg=SOFT,fg=INK,font=(family,11,'bold'),anchor='w').pack(fill='x')
    tk.Label(sframe,textvariable=details,bg=SOFT,fg=MUTED,anchor='w').pack(fill='x',pady=(4,0))
    cancel_button=tk.Button(sframe,text='중단 요청',command=lambda:(cancel.set(),status.set('중단 요청됨 — 수집 작업 정리 중')),
                            state='disabled',bg=WHITE,fg=RED,relief='flat',cursor='hand2')
    cancel_button.pack(anchor='e',pady=(5,0))

    adv_open=tk.BooleanVar(value=False)
    settings_outer=tk.Frame(root,bg=WHITE,padx=26);settings_outer.pack(fill='x')
    settings_window=tk.Toplevel(root);settings_window.withdraw();settings_window.title('연결·저장·자동 실행 설정')
    settings_window.configure(bg=WHITE);settings_window.resizable(True,True)
    panel=tk.Frame(settings_window,bg=WHITE,highlightthickness=1,highlightbackground=BORDER,padx=18,pady=14)
    panel.pack(fill='both',expand=True)
    def toggle_settings():
        settings_window.deiconify();settings_window.lift()
    settings_window.protocol('WM_DELETE_WINDOW',settings_window.withdraw)
    adv_btn=tk.Button(settings_outer,text='연결·저장·자동 실행 설정',command=toggle_settings,
                      relief='flat',bg=WHITE,fg=BLUE,font=(family,10,'bold'),cursor='hand2')
    adv_btn.pack(anchor='w')
    panel.columnconfigure(1,weight=1);panel.columnconfigure(3,weight=1)
    def field(row,label,variable,column=0,width=42):
        L(panel,label,size=9,color=MUTED).grid(row=row,column=column,sticky='w',padx=(0,8),pady=4)
        entry=ttk.Entry(panel,textvariable=variable,width=width)
        entry.grid(row=row,column=column+1,sticky='ew',padx=(0,16),pady=4)
        return entry
    field(0,'저장 폴더',save_dir)
    tk.Button(panel,text='폴더 선택',relief='flat',bg=SOFT,
              command=lambda:(lambda v:save_dir.set(v) if v else None)(filedialog.askdirectory(initialdir=save_dir.get()))).grid(row=0,column=2,columnspan=2,sticky='w')
    field(1,'누적 Excel',excel_path)
    L(panel,'공란: 저장폴더/fastmarkets_prices.xlsx 자동 생성',size=9,color=MUTED).grid(row=1,column=2,columnspan=2,sticky='w')
    field(2,'FMB 기간(일)',lookback)
    field(3,'FMB 대시보드',workspace)
    field(4,'ECM 파일명',ecm_title)
    field(5,'ECM 검색어',ecm_search)
    L(panel,'ECM에 올린 Excel의 실제 파일명과 일치해야 합니다. 권장: fastmarkets_prices.xlsx',size=9,color=MUTED).grid(row=5,column=2,columnspan=2,sticky='w')
    def save_click():
        if busy[0]:
            messagebox.showinfo('작업 진행 중','실행이 끝난 뒤 설정을 저장하세요.');return
        try:safe_config();status.set('설정 저장 완료')
        except Exception as exc:messagebox.showerror('설정',str(exc))
    tk.Button(panel,text='설정 저장',command=save_click,bg=BLUE,fg=WHITE,relief='flat',padx=20,pady=7).grid(row=6,column=0,columnspan=2,sticky='w',pady=(8,2))
    tk.Button(panel,text='Chrome 연결·로그인',command=lambda:launch('Chrome 로그인',lambda s:browser.open_workspace(*core.credentials_get()),'login'),
              bg=SOFT,relief='flat').grid(row=6,column=2,sticky='w',pady=(8,2))
    tk.Button(panel,text='Excel·보고서 재시도',command=lambda:launch('저장된 DB에서 출력 재시도',
              lambda s:export_only(s)),bg=SOFT,fg=INK,relief='flat').grid(row=6,column=3,sticky='w',pady=(8,2))
    L(panel,'계정과 포트 진단, 공식 CSV 및 예약 설정은 기존 명령행 기능으로 유지합니다.',size=9,color=MUTED).grid(row=7,column=0,columnspan=4,sticky='w',pady=(8,0))
    field(8,'로그인 이메일',username)
    field(9,'비밀번호',password).configure(show='•')
    def store_account():
        user,pwd=username.get(),password.get()
        launch('Windows 자격 증명 저장',lambda s:core.credentials_set(user,pwd),'account')
        password.set('')
    tk.Button(panel,text='계정 저장',command=store_account,bg=SOFT,fg=INK,relief='flat').grid(row=9,column=2,sticky='w')
    field(10,'매일 실행 시각',schedule_time,width=10)
    def register_schedule():
        value=schedule_time.get().strip()
        from scheduler_v37 import register
        def work(s):
            result=register(value);emit(result);return {'message':result}
        launch('일일 자동 실행 등록',work)
    tk.Button(panel,text='자동 실행 등록',command=register_schedule,bg=SOFT,fg=BLUE,relief='flat').grid(row=10,column=2,sticky='w')
    L(panel,'권장 08:30 · Windows 로그인/네트워크 필요 · 누락 실행 보강 · 중복 실행 차단',size=9,color=MUTED).grid(row=11,column=0,columnspan=4,sticky='w')
    ttk.Checkbutton(panel,text='Westmetall LME 니켈·구리 Cash/3개월·재고 함께 수집',
                    variable=lme_enabled).grid(row=12,column=0,columnspan=4,sticky='w',pady=(8,0))

    lower=tk.Frame(root,bg=WHITE,padx=26,pady=8);lower.pack(fill='both',expand=True)
    note=ttk.Notebook(lower);note.pack(fill='both',expand=True)
    markettab=tk.Frame(note,bg=WHITE);note.add(markettab,text='저장된 최신 시세')
    L(markettab,'실시간 호가가 아닙니다. 종목별 실제 기준일·출처를 확인하세요.',color=MUTED).pack(anchor='w',pady=8)
    latest=ttk.Treeview(markettab,columns=('item','price','unit','date','source','state'),show='headings',height=9)
    for name,label,width in [('item','종목',270),('price','가격',125),('unit','단위',120),('date','실제 기준일',120),('source','출처',100),('state','상태',180)]:
        latest.heading(name,text=label);latest.column(name,width=width,anchor='e' if name=='price' else 'w')
    latest.pack(fill='both',expand=True)
    controls=tk.Frame(markettab,bg=WHITE);controls.pack(fill='x',pady=8)
    L(controls,'보고 기간').pack(side='left')
    for variable,width in ((report_start,11),(report_end,11),(report_series,24)):
        ttk.Entry(controls,textvariable=variable,width=width).pack(side='left',padx=5)
    L(controls,'시작·종료 YYYY-MM-DD / 종목코드 쉼표 구분',size=9,color=MUTED).pack(side='left')
    def request_reports():
        filters=dict(reports_only=True,report_start=report_start.get().strip() or None,
                     report_end=report_end.get().strip() or None,
                     report_series=[s.strip() for s in report_series.get().split(',') if s.strip()] or None)
        launch('선택 기간 보고서 생성',lambda s:export_only(dict(s,**filters)))
    rb=tk.Button(controls,text='보고서 생성',bg=SOFT,fg=BLUE,relief='flat',command=request_reports)
    rb.pack(side='right');running_buttons.append(rb)
    logtab=tk.Frame(note,bg=WHITE);note.add(logtab,text='진행 로그')
    log_widget=tk.Text(logtab,font=('Consolas',10),height=14,wrap='word',borderwidth=0,
                       bg='#17171c',fg=INK,state='disabled',padx=10,pady=10)
    scroll=ttk.Scrollbar(logtab,orient='vertical',command=log_widget.yview)
    log_widget.configure(yscrollcommand=scroll.set)
    log_widget.pack(side='left',fill='both',expand=True);scroll.pack(side='right',fill='y')
    previewtab=tk.Frame(note,bg=WHITE);note.add(previewtab,text='ECM 변경 예정')
    preview_text=tk.Text(previewtab,font=('Consolas',10),wrap='none',borderwidth=0,bg=SOFT,fg=INK,state='disabled',padx=10,pady=10)
    preview_text.pack(fill='both',expand=True)
    footer=tk.Frame(root,bg=WHITE,padx=26,pady=10);footer.pack(fill='x')
    L(footer,'Chrome 9444 / ECM 일반 Edge  ·  보안 문서 우회 없음  ·  ECM 서버 반영은 별도 확인',size=9,color=MUTED).pack(anchor='w')

    def pump():
        try:
            while True:
                try:item=q.get_nowait()
                except Empty:break
                typ=item[0]
                if typ=='log':
                    msg=str(item[1]);syslog('GUI: '+msg)
                    log_widget.configure(state='normal');log_widget.insert('end',msg+'\n');log_widget.see('end');log_widget.configure(state='disabled')
                elif typ=='snapshot':
                    try:
                        from report_exports import display_value
                        ctx=item[1]
                        latest.delete(*latest.get_children())
                        for table in ('보고용_금속시세','보고용_환율','보고용_시장지표'):
                            rows=ctx.tables[table];headers=rows[0]
                            for row in rows[1:]:
                                data=dict(zip(headers,row))
                                values=(data.get('종목',data.get('통화',data.get('지표'))),
                                        data.get('Mid',data.get('매매기준율',data.get('수치'))),
                                        data.get('단위'),data.get('고시일',data.get('시장일')),
                                        data.get('출처'),data.get('상태',data.get('구분','고시')))
                                latest.insert('', 'end',values=tuple(display_value(v) for v in values))
                    except Exception as exc:status.set('최신 시세 표시 불가: '+str(exc))
                elif typ in ('done','fail'):
                    busy[0]=False
                    for b in running_buttons:b.configure(state='normal')
                    cancel_button.configure(state='disabled')
                    if typ=='fail':
                        _,title,error=item;status.set(title+' 실패: '+error)
                        syslog('오류: '+title+': '+error);messagebox.showerror(title,error[:1600]);continue
                    _,title,kind,result=item
                    if kind in ('collect','collect_ecm'):
                        if result.get('cancelled'):
                            status.set('작업 취소 · 이전 DB 유지');continue
                        d=result['diag'];warnings=d.get('warnings',[])
                        details.set(f'FMB {result["prices"]}행 수집  |  SMBS '+str((d.get('fx') or {}).get('collected','확인 필요'))+
                                    '건  |  LME '+str((d.get('lme') or {}).get('collected','미실행'))+
                                    '건  |  Excel '+('생성·갱신' if d.get('workbook') else '실패')+f'  |  확인사항 {len(warnings)}건')
                        outcome={'complete':'완료','partial':'부분 완료','failed':'실패'}.get(d.get('status'),'상태 확인 필요')
                        status.set(title+' '+outcome+' · '+('주의사항을 확인하세요' if warnings else '진단 상태를 확인하세요' if outcome!='완료' else '시세 저장 완료'))
                        if warnings:
                            syslog('수집 확인사항: '+ ' / '.join(map(str,warnings))[:1200])
                            messagebox.showwarning('수집 점검 필요',f'수집 경고 {len(warnings)}건. 누락 종목은 채우지 않습니다. collector.log와 진단 JSON 확인.')
                        if kind=='collect_ecm':
                            if d.get('status')=='failed' or d.get('fmb_failed'):
                                messagebox.showwarning('ECM 자동 반영 보류','FMB 수집 실패로 전체 자료를 검증하지 못했습니다. 환율/DB는 유지되며 ECM은 별도 미리보기 버튼으로 확인하세요.')
                            elif not d.get('workbook'):
                                messagebox.showwarning('ECM 진행 보류','누적 Excel 갱신이 실패했습니다. ECM 반영을 시작하지 않습니다.')
                            else:root.after(250,request_sync)
                    elif kind=='ecm_preview':
                        pending['plan']=result
                        stats=result['stats']
                        status.set('ECM 변경사항 확인 완료 · 승인 대기')
                        preview_text.configure(state='normal');preview_text.delete('1.0','end')
                        preview_text.insert('end',f'대상: {result["workbook_name"]} / {result["sheet"]}\n')
                        preview_text.insert('end',f'열린 실제 경로: {result["workbook_path"]}\n')
                        preview_text.insert('end',f'날짜 행 +{stats["new_dates"]}; 품목 열 +{stats["new_columns"]}\n')
                        preview_text.insert('end',f'신규/빈셀 {stats["fill"]}, 정정 {stats["correction"]}, 충돌 보류·비우기 {stats.get("cleared",0)}, 동일 {stats["unchanged"]}, 원본 미고시 {stats["missing_source"]}\n\n')
                        for change in result['edits'][:180]:
                            incoming='보류(값 비움)' if change['incoming'] is None else str(change['incoming'])
                            decision={'quarantine':'충돌 보류','fill':'입력','correction':'정정'}.get(change['decision'],change['decision'])
                            preview_text.insert('end',f'{change["date"]}  {change["header"]:20} '
                                                     f'{str(change["previous"]):>12} -> {incoming:>12} '
                                                     f'({decision})\n')
                        preview_text.configure(state='disabled');note.select(previewtab)
                        if not result['edits'] and not stats['new_columns'] and not stats['new_dates']:
                            messagebox.showinfo('변경 없음','ECM은 DB와 동일하여 쓸 값이 없습니다.');continue
                        if messagebox.askyesno('ECM Excel 변경 승인',
                            f'파일: {result["workbook_name"]}\n'
                            f'열린 경로: {result["workbook_path"]}\n'
                            '이 경로가 ECM에서 연 실제 통합문서인지 확인하세요.\n\n'
                            f'새 날짜 {stats["new_dates"]}행 / 새 항목 {stats["new_columns"]}열\n'
                            f'입력 {stats["fill"]}건 / 기존 숫자 수정 {stats["correction"]}건\n\n'
                            f'충돌 수치 보류로 기존 값 비우기 {stats.get("cleared",0)}건\n\n'
                            '기존 수식·타사 열은 유지합니다.\n'
                            'Excel Save 이후에도 ECM 서버 반영 확인이 필요합니다.\n계속할까요?'):
                            launch('ECM Excel 승인 후 저장',apply_ecm,'ecm_apply')
                        else:status.set('ECM 미리보기만 완료 · 실제 Excel 변경 없음')
                    elif kind=='ecm_apply':
                        status.set(f'ECM Excel 저장 {result["applied"]}셀 완료 · ECM 서버 반영은 별도 확인 필요')
                        messagebox.showinfo('Excel 저장 완료 / ECM 서버 확인 필요',
                            f'Excel 셀 {result["applied"]}건 저장 후 재읽기 확인 완료.\n'
                            'ECM의 체크인/업로드·서버 반영 성공은 확인하지 못했습니다. ECM에서 변경내역을 열어 확인하세요.')
                    else:
                        warnings=result.get('warnings',[]) if isinstance(result,dict) else []
                        if warnings:
                            for msg in warnings:syslog(str(msg))
                        status.set(title+(' · 확인 필요: '+str(warnings[0]) if warnings else ' 완료'))
        except Exception as exc:
            # Keep polling even if one queued result cannot be rendered.
            status.set('상태 처리 오류: '+str(exc))
            try:syslog('GUI 결과 처리 오류: '+str(exc))
            except Exception:pass
        finally:
            root.after(160,pump)
    root.after(160,pump)
    threading.Thread(target=lambda:queue_snapshot(cfg['data_dir']),daemon=True).start()
    def close():
        if busy[0]:
            cancel.set();messagebox.showinfo('종료 대기','작업에 중단 요청했습니다. 완료 후 종료하세요.');return
        try:threading.Thread(target=browser.detach,daemon=True).start()
        except Exception:pass
        root.destroy()
    root.protocol('WM_DELETE_WINDOW',close)
    root.mainloop()
