# -*- coding: utf-8 -*-
"""Task-based Windows UI. UI concepts inspired by provided Toss style reference.
No third-party fonts/assets bundled; native Malgun Gothic fallback.
"""
from __future__ import annotations
from pathlib import Path
from queue import Queue, Empty
import threading, traceback

# Semantic palette: first-party documentation values provided by user.
BLUE='#3182f6';BLUE_DARK='#2272eb';INK='#191f28';MUTED='#6b7684'
SOFT='#f2f4f6';BORDER='#e5e8eb';WHITE='#ffffff';RED='#e42939'


def main_gui():
    import tkinter as tk
    from tkinter import ttk,messagebox,filedialog
    import FastmarketsCollector_v3_4 as core
    from ecm_excel_sync import prepare_ecm_plan, apply_ecm_plan, write_json, ECMBlocked
    from ecm_automation import execute as ecm_open
    cfg=core.config_load()
    root=tk.Tk()
    root.title('금속 시세 수집 · ECM 연동  |  Fastmarkets Collector v3.6')
    root.geometry('1040x760');root.minsize(850,670);root.configure(bg=WHITE)
    family='맑은 고딕' if core.IS_WINDOWS else 'Arial'
    root.option_add('*Font',f'{{{family}}} 10')
    style=ttk.Style(root)
    if 'clam' in style.theme_names():style.theme_use('clam')
    style.configure('Treeview',rowheight=26,background=WHITE,fieldbackground=WHITE,foreground=INK)
    style.configure('Treeview.Heading',background=SOFT,foreground=INK,font=(family,10,'bold'))
    style.configure('TNotebook',background=WHITE,borderwidth=0)
    style.configure('TNotebook.Tab',padding=(16,8))
    q=Queue();cancel=threading.Event();busy=[False];browser=core.ChromeSession(lambda m:q.put(('log',m)))
    save_dir=tk.StringVar(value=cfg['data_dir'])
    excel_path=tk.StringVar(value=cfg.get('workbook_path',''))
    lookback=tk.StringVar(value=str(cfg.get('lookback_days',31)))
    workspace=tk.StringVar(value=cfg.get('workspace_url',core.WORKSPACE_URL))
    ecm_title=tk.StringVar(value=('fastmarkets_prices.xlsx' if cfg.get('ecm_title')=='(리뉴얼)금속 가격 현황' else cfg.get('ecm_title','fastmarkets_prices.xlsx')))
    ecm_search=tk.StringVar(value=('fastmarkets_prices' if cfg.get('ecm_search')=='금속 가격 현황' else cfg.get('ecm_search','fastmarkets_prices')))
    username=tk.StringVar(value='');password=tk.StringVar(value='')
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
                   lookback_days=days,workspace_url=url,ecm_title=name,ecm_search=ecm_search.get().strip())
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
        target=Path(settings['data_dir']);target.mkdir(parents=True,exist_ok=True)
        with core.exclusive_browser_job():
            emit('Chrome 9444 연결 및 Fastmarkets 7개 위젯 수집 시작')
            try:
                rows,diag=browser.scrape(settings['lookback_days'],target,cancel,
                                         workbook_path=settings['workbook_path'],defer_export=True)
            except Exception as exc:
                rows=[]
                diag={'warnings':[f'FMB 수집 실패: {type(exc).__name__}: {str(exc)[:240]}'],
                      'fmb_failed':True}
                emit('FMB 실패: 기존 DB 보존; 환율 수집은 독립적으로 계속 시도')
            if cancel.is_set():return {'cancelled':True}
            emit('SMBS 4종 환율: 동일 Chrome 9444의 별도 임시 탭에서 수집')
            try:
                diag['fx']=core.fx_one_time(target,settings['workbook_path'],driver=browser.driver,
                    defer_export=True,gui_log=emit)
            except Exception as exc:
                diag.setdefault('warnings',[]).append('SMBS 수집 실패: '+str(exc))
            emit('SQLite 누적 데이터를 Excel 일별요약·일별시세·월별시세로 반영')
            try:diag['workbook']=core.export_all(target,settings['workbook_path'])
            except Exception as exc:diag.setdefault('warnings',[]).append('누적 Excel 실패: '+str(exc))
            return {'prices':len(rows),'diag':diag}

    def preview_ecm(settings):
        folder=Path(settings['data_dir'])
        emit('일반 Edge에서 ECM 문서 검색·열기; 9222/9337/9444 브라우저 변경 안 함')
        # execute() acquires its own single-instance ECM UIA lock.
        # Do not nest exclusive_ecm_job: Windows msvcrt locks are not re-entrant.
        ecm_open(lambda m:syslog('ECM: '+m),search_text=settings['ecm_search'],
                 target_title=settings['ecm_title'])
        plan=prepare_ecm_plan(folder,settings['ecm_title'],local_path=snapshot_target(settings),log=emit)
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
    L(header,'금속 시세 자동화',size=21,bold=True).pack(anchor='w')
    L(header,'Fastmarkets · 서울외국환중개 · 누적 Excel · ECM',size=10,color=MUTED).pack(anchor='w',pady=(4,0))
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
    action('전체 실행','금속·환율 수집 → DB/Excel → ECM 미리보기·승인',lambda:request_collect(True),True)
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
    panel=tk.Frame(settings_outer,bg=WHITE,highlightthickness=1,highlightbackground=BORDER,padx=12,pady=10)
    def toggle_settings():
        if adv_open.get():panel.pack_forget();adv_open.set(False);adv_btn.config(text='고급 설정  ▾')
        else:panel.pack(fill='x',pady=(5,8));adv_open.set(True);adv_btn.config(text='고급 설정  ▴')
    adv_btn=tk.Button(settings_outer,text='고급 설정  ▾',command=toggle_settings,
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
        try:safe_config();status.set('설정 저장 완료')
        except Exception as exc:messagebox.showerror('설정',str(exc))
    tk.Button(panel,text='설정 저장',command=save_click,bg=BLUE,fg=WHITE,relief='flat',padx=20,pady=7).grid(row=6,column=0,columnspan=2,sticky='w',pady=(8,2))
    tk.Button(panel,text='Chrome 연결·로그인',command=lambda:launch('Chrome 로그인',lambda s:browser.open_workspace(*core.credentials_get()),'login'),
              bg=SOFT,relief='flat').grid(row=6,column=2,sticky='w',pady=(8,2))
    tk.Button(panel,text='DB → Excel만 재생성',command=lambda:launch('DB에서 Excel 갱신',
              lambda s:core.export_all(Path(s['data_dir']),s['workbook_path'])) ,bg=SOFT,relief='flat').grid(row=6,column=3,sticky='w',pady=(8,2))
    L(panel,'계정과 포트 진단, 공식 CSV 및 예약 설정은 기존 명령행 기능으로 유지합니다.',size=9,color=MUTED).grid(row=7,column=0,columnspan=4,sticky='w',pady=(8,0))

    lower=tk.Frame(root,bg=WHITE,padx=26,pady=8);lower.pack(fill='both',expand=True)
    note=ttk.Notebook(lower);note.pack(fill='both',expand=True)
    logtab=tk.Frame(note,bg=WHITE);note.add(logtab,text='진행 로그')
    log_widget=tk.Text(logtab,font=('Consolas',10),height=14,wrap='word',borderwidth=0,
                       bg='#fafbfc',fg=INK,state='disabled',padx=10,pady=10)
    scroll=ttk.Scrollbar(logtab,orient='vertical',command=log_widget.yview)
    log_widget.configure(yscrollcommand=scroll.set)
    log_widget.pack(side='left',fill='both',expand=True);scroll.pack(side='right',fill='y')
    previewtab=tk.Frame(note,bg=WHITE);note.add(previewtab,text='ECM 변경 예정')
    preview_text=tk.Text(previewtab,font=('Consolas',10),wrap='none',borderwidth=0,state='disabled',padx=10,pady=10)
    preview_text.pack(fill='both',expand=True)
    footer=tk.Frame(root,bg=WHITE,padx=26,pady=10);footer.pack(fill='x')
    L(footer,'Chrome 9444 / ECM 일반 Edge  ·  보안 문서 우회 없음  ·  ECM 서버 반영은 별도 확인',size=9,color=MUTED).pack(anchor='w')

    def pump():
        while True:
            try:item=q.get_nowait()
            except Empty:break
            typ=item[0]
            if typ=='log':
                msg=str(item[1]);syslog('GUI: '+msg)
                log_widget.configure(state='normal');log_widget.insert('end',msg+'\n');log_widget.see('end');log_widget.configure(state='disabled')
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
                    details.set(f'FMB {result["prices"]}행 수집  |  SMBS '+str(d.get('fx',{}).get('collected','확인 필요'))+
                                '건  |  Excel '+('생성·갱신' if d.get('workbook') else '실패')+f'  |  확인사항 {len(warnings)}건')
                    status.set(title+' 완료 · '+('주의사항을 확인하세요' if warnings else '시세 저장 완료'))
                    if warnings:
                        syslog('수집 확인사항: '+ ' / '.join(map(str,warnings))[:1200])
                        messagebox.showwarning('수집 점검 필요',f'수집 경고 {len(warnings)}건. 누락 종목은 채우지 않습니다. collector.log와 진단 JSON 확인.')
                    if kind=='collect_ecm':
                        if d.get('fmb_failed'):
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
                    preview_text.insert('end',f'신규/빈셀 {stats["fill"]}, 정정 {stats["correction"]}, 동일 {stats["unchanged"]}, 원본 미고시 {stats["missing_source"]}\n\n')
                    for change in result['edits'][:180]:
                        preview_text.insert('end',f'{change["date"]}  {change["header"]:20} '
                                                 f'{str(change["previous"]):>12} -> {change["incoming"]:>12} '
                                                 f'({change["decision"]})\n')
                    preview_text.configure(state='disabled');note.select(previewtab)
                    if not stats['fill'] and not stats['correction'] and not stats['new_columns'] and not stats['new_dates']:
                        messagebox.showinfo('변경 없음','ECM은 DB와 동일하여 쓸 값이 없습니다.');continue
                    if messagebox.askyesno('ECM Excel 변경 승인',
                        f'파일: {result["workbook_name"]}\n'
                        f'열린 경로: {result["workbook_path"]}\n'
                        '이 경로가 ECM에서 연 실제 통합문서인지 확인하세요.\n\n'
                        f'새 날짜 {stats["new_dates"]}행 / 새 항목 {stats["new_columns"]}열\n'
                        f'입력 {stats["fill"]}건 / 기존 숫자 수정 {stats["correction"]}건\n\n'
                        '기존 수식·타사 열은 유지합니다.\n'
                        'Excel Save 이후에도 ECM 서버 반영 확인이 필요합니다.\n계속할까요?'):
                        launch('ECM Excel 승인 후 저장',apply_ecm,'ecm_apply')
                    else:status.set('ECM 미리보기만 완료 · 실제 Excel 변경 없음')
                elif kind=='ecm_apply':
                    status.set(f'ECM Excel 저장 {result["applied"]}셀 완료 · ECM 서버 반영은 별도 확인 필요')
                    messagebox.showinfo('Excel 저장 완료 / ECM 서버 확인 필요',
                        f'Excel 셀 {result["applied"]}건 저장 후 재읽기 확인 완료.\n'
                        'ECM의 체크인/업로드·서버 반영 성공은 확인하지 못했습니다. ECM에서 변경내역을 열어 확인하세요.')
                else:status.set(title+' 완료')
        root.after(160,pump)
    root.after(160,pump)
    def close():
        if busy[0]:
            cancel.set();messagebox.showinfo('종료 대기','작업에 중단 요청했습니다. 완료 후 종료하세요.');return
        try:threading.Thread(target=browser.detach,daemon=True).start()
        except Exception:pass
        root.destroy()
    root.protocol('WM_DELETE_WINDOW',close)
    root.mainloop()
