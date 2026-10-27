"""Functional Qt desktop. One owned worker serializes all service operations."""
from __future__ import annotations
import copy
import json
from datetime import datetime
from PySide6.QtCore import QObject, QThread, Signal, Slot, QTimer, QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QPushButton, QListWidget, QStackedWidget, QLineEdit, QSpinBox, QCheckBox,
    QGroupBox, QFormLayout, QScrollArea, QTabWidget, QPlainTextEdit,
    QFileDialog, QMessageBox, QComboBox, QToolButton,
)
from desktop_tables import DataTable, SnapshotSummary, history_rows, ecm_rows, existing_output_paths, concise_feedback, report_summary, collection_issues
from desktop_metals import MetalPanel
from desktop_theme import apply_theme
from report_model import REPORT_NAMES

LABELS = {'snapshot': '자료 새로고침', 'history': '실행 기록 조회', 'save_settings': '설정 저장',
          'collect_public':'공개 종가만 수집',
          'connect': 'Chrome 연결·로그인', 'collect': '시세 수집', 'export': '누적 Excel 갱신',
          'reports': '보고서 생성', 'ecm_preview': 'ECM 변경 미리보기', 'ecm_apply': 'ECM 승인 적용',
          'credentials_save': '계정 저장', 'credentials_delete': '저장 계정 삭제',
          'schedule_status': '예약 상태 조회', 'schedule_register': '예약 등록',
          'schedule_remove': '예약 해제', 'diagnose': '연결 진단'}
STATES = {'complete': '완료', 'partial': '부분 완료', 'failed': '실패',
          'needs_action': '사용자 확인 필요', 'cancelled': '취소됨'}


class ServiceWorker(QObject):
    result = Signal(str, object)
    log = Signal(str)
    closed = Signal()

    def __init__(self, service):
        super().__init__()
        self.service = service
        self.service.logger = self.log.emit

    @Slot(str, object, object)
    def execute(self, action, settings, payload):
        try:
            result = self.service.run(action, settings=settings, **payload)
            if not isinstance(result, dict) or result.get('status') not in STATES:
                raise RuntimeError('작업 결과 형식을 확인할 수 없습니다.')
            if action in ('reports', 'export', 'collect','collect_public'):
                result = dict(result)
                result['data'] = dict(result.get('data') or {})
                result['data']['_ui_files'] = existing_output_paths(result['data'])
        except Exception as exc:
            # Service owns redaction. Never echo a credential-bearing exception.
            result = {'status': 'failed', 'message': f'작업 오류 ({type(exc).__name__}). 실행 기록과 연결 진단을 확인하세요.', 'data': {}, 'warnings': []}
        payload.clear()
        self.result.emit(action, result)

    @Slot()
    def shutdown(self):
        try:
            self.service.close()
        finally:
            self.closed.emit()


class MainWindow(QMainWindow):
    requested = Signal(str, object, object)
    shutdown_requested = Signal()

    def __init__(self, service=None):
        super().__init__()
        if service is None:
            from desktop_controller import CollectorService
            service = CollectorService()
        self.service = service
        self.busy = False
        self._closing = False
        self._shutdown = False
        self.last_action = None
        self._retry_action = None
        self.pending_plan = None
        self.report_paths = []
        self._snapshot = {}
        self.buttons, self.fields, self.tables = {}, {}, {}
        self.setWindowTitle('mia · 금속과 시장 자료')
        self.resize(1320, 920)
        self.setMinimumSize(1060, 760)
        apply_theme(QApplication.instance())
        shell = QWidget()
        self.setCentralWidget(shell)
        root = QHBoxLayout(shell)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.nav = QListWidget()
        self.nav.setObjectName('nav')
        self.nav.setFixedWidth(200)
        self.nav.addItems(['대시보드', '자료·보고서', 'ECM', '실행 기록', '설정'])
        self.nav.setAccessibleName('주 메뉴')
        root.addWidget(self.nav)
        body = QVBoxLayout()
        body.setContentsMargins(28, 22, 28, 20)
        body.setSpacing(16)
        root.addLayout(body, 1)
        brand = QLabel('mia  /  MARKET INTELLIGENCE')
        brand.setObjectName('muted')
        body.addWidget(brand)
        self.pages = QStackedWidget()
        body.addWidget(self.pages, 1)
        self._dashboard()
        self._reports()
        self._ecm()
        self._history()
        self._settings()
        footer = QHBoxLayout()
        self.status = QLabel('대기 · 저장된 자료를 불러옵니다.')
        self.status.setObjectName('status')
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        footer.addWidget(self.status, 1)
        self.retry = QPushButton('실패 작업 재시도')
        self.retry.setEnabled(False)
        self.retry.clicked.connect(self.retry_last)
        footer.addWidget(self.retry)
        self.cancel_button = QPushButton('취소 요청')
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.request_cancel)
        footer.addWidget(self.cancel_button)
        body.addLayout(footer)
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.nav.setCurrentRow(0)
        self.load_settings(service.settings)
        for field in self.fields.values():
            signal = field.toggled if isinstance(field, QCheckBox) else field.valueChanged if isinstance(field, QSpinBox) else field.textChanged
            signal.connect(self.invalidate_preview)
        self.fields['representative_symbols'].textChanged.connect(lambda: self.summary.update_snapshot(self._snapshot, self.current_settings()['representative_symbols']))
        self.thread = QThread(self)
        self.worker = ServiceWorker(service)
        self.worker.moveToThread(self.thread)
        self.requested.connect(self.worker.execute)
        self.shutdown_requested.connect(self.worker.shutdown)
        self.worker.result.connect(self.on_result)
        self.worker.log.connect(self.log.appendPlainText)
        self.worker.closed.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self._closed)
        self.thread.start()
        QTimer.singleShot(0, lambda: self.submit('snapshot') if not self._closing else None)

    def page(self, title, description):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        heading = QLabel(title)
        heading.setObjectName('heading')
        layout.addWidget(heading)
        label = QLabel(description)
        label.setWordWrap(True)
        label.setObjectName('muted')
        layout.addWidget(label)
        self.pages.addWidget(page)
        return layout

    def button(self, action, text=None, primary=False):
        button = QPushButton(text or LABELS[action])
        button.setObjectName(action)
        button.setAccessibleName(text or LABELS[action])
        button.setProperty('primary', primary)
        button.clicked.connect(lambda: self.handle_action(action))
        self.buttons[action] = button
        return button

    def _dashboard(self):
        layout = self.page('원료·금속 시황', '리튬 · 니켈 · 코발트 · 망간 · 구리 · 블랙매스 — 출처와 조건이 확인된 저장 시세')
        bar = QHBoxLayout()
        self.as_of = QLabel('자료 기준 · 아직 없음')
        self.as_of.setObjectName('muted')
        bar.addWidget(self.as_of, 1)
        self.state_chip = QLabel('대기')
        self.state_chip.setObjectName('stateChip')
        bar.addWidget(self.state_chip)
        bar.addWidget(self.button('snapshot'))
        bar.addWidget(self.button('collect', primary=True))
        layout.addLayout(bar)
        self.summary = SnapshotSummary()
        self.summary.cards[2].hide()  # Market/index information belongs on the report page.
        layout.addWidget(self.summary)
        self.search = QLineEdit()
        self.search.setPlaceholderText('종목 · 기준일 · 출처 · 상태 검색')
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName('저장 자료 검색')
        layout.addWidget(self.search)
        tabs = self.dashboard_tabs = QTabWidget()
        self.metals=MetalPanel();tabs.addTab(self.metals,'원료·금속 시황')
        self.search.textChanged.connect(self.metals.search)
        for name, title in zip(REPORT_NAMES[:2], ('금속','환율')):
            table = DataTable(onboard=True)
            table.onboarding.connect(lambda action: self.nav.setCurrentRow(4) if action == 'settings' else self.submit('diagnose'))
            self.tables[name] = table
            tabs.addTab(table, title)
            self.search.textChanged.connect(table.search)
        self.coverage_table=DataTable();tabs.addTab(self.coverage_table,'원천 수집 범위')
        layout.addWidget(tabs, 1)
        self.details_toggle = QToolButton()
        self.details_toggle.setText('확인 내역 보기')
        self.details_toggle.setCheckable(True)
        self.details_toggle.setArrowType(Qt.RightArrow)
        self.details_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.details_toggle.setAccessibleName('확인 내역 펼치기 또는 접기')
        layout.addWidget(self.details_toggle, alignment=Qt.AlignLeft)
        self.details_panel=QWidget()
        details_layout=QVBoxLayout(self.details_panel)
        details_layout.setContentsMargins(0,0,0,0)
        self.snapshot_warning = QLabel('자료 없음 · 수집 결과와 기준일을 확인하세요.')
        self.snapshot_warning.setObjectName('muted')
        self.snapshot_warning.setWordWrap(True)
        details_layout.addWidget(self.snapshot_warning)
        self.collection_errors=QLabel();self.collection_errors.setWordWrap(True)
        self.collection_errors.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.collection_errors.setObjectName('collectionErrors');self.collection_errors.hide()
        details_layout.addWidget(self.collection_errors)
        run_log=QPushButton('실행 기록 열기')
        run_log.clicked.connect(lambda:self.nav.setCurrentRow(3))
        details_layout.addWidget(run_log,alignment=Qt.AlignLeft)
        layout.addWidget(self.details_panel)
        self.details_panel.hide()
        self.details_toggle.toggled.connect(self.details_panel.setVisible)
        self.details_toggle.toggled.connect(lambda opened:self.details_toggle.setArrowType(Qt.DownArrow if opened else Qt.RightArrow))

    def _reports(self):
        layout = self.page('자료·보고서', '저장된 DB로 출력을 다시 만듭니다. 아래 필터는 보고서에만 적용되며 누적 원본을 줄이지 않습니다.')
        filters = QGroupBox('보고 범위')
        form = QFormLayout(filters)
        self.report_start, self.report_end, self.report_series = QLineEdit(), QLineEdit(), QLineEdit()
        for widget, label, placeholder in ((self.report_start, '시작일', 'YYYY-MM-DD · 비우면 전체'), (self.report_end, '종료 기준일', 'YYYY-MM-DD · 이 날짜 이전 확정 종가'), (self.report_series, '종목 코드', 'KOSPI,MB-LI-0029 · 쉼표로 구분')):
            widget.setPlaceholderText(placeholder)
            widget.setAccessibleName(label)
            form.addRow(label, widget)
        layout.addWidget(filters)
        actions = QHBoxLayout()
        actions.addWidget(self.button('collect_public','주가·지표 수집'))
        actions.addWidget(self.button('reports', primary=True))
        actions.addWidget(self.button('export', 'Excel·보고서 재출력'))
        actions.addStretch()
        layout.addLayout(actions)
        self.output_files = QComboBox()
        self.output_files.setAccessibleName('생성된 보고서 파일')
        layout.addWidget(self.output_files)
        self.open_report = QPushButton('선택 파일 열기')
        self.open_report.clicked.connect(self.open_output)
        self.open_report.setEnabled(False)
        layout.addWidget(self.open_report, alignment=Qt.AlignLeft)
        self.report_tabs=QTabWidget()
        self.report_tabs.setAccessibleName('시장·주가 보고 자료')
        for name,title in zip(REPORT_NAMES[2:],('확정 종가','시총 원자료','시총 비교','종합','주가 종가')):
            table=DataTable(onboard=True)
            table.onboarding.connect(lambda action:self.nav.setCurrentRow(4) if action=='settings' else self.submit('diagnose'))
            self.tables[name]=table
            self.report_tabs.addTab(table,title)
            self.search.textChanged.connect(table.search)
        lme_table=DataTable(onboard=True)
        self.tables['보고용_LME']=lme_table
        self.report_tabs.addTab(lme_table,'LME 공식가격')
        self.search.textChanged.connect(lme_table.search)
        layout.addWidget(self.report_tabs,2)
        self.report_detail = QPlainTextEdit()
        self.report_detail.setReadOnly(True)
        self.report_detail.setPlaceholderText('생성된 파일의 실제 경로와 출력 결과가 여기에 표시됩니다.')
        layout.addWidget(self.report_detail, 1)
        self.sources_toggle=QToolButton();self.sources_toggle.setText('자료 기준 · 펼치기')
        self.sources_toggle.setCheckable(True);self.sources_toggle.setArrowType(Qt.RightArrow)
        self.sources_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.sources_toggle.setAccessibleName('자료 기준 펼치기 또는 접기')
        layout.addWidget(self.sources_toggle)
        self.report_sources=QPlainTextEdit();self.report_sources.setReadOnly(True)
        self.report_sources.setMaximumHeight(180);self.report_sources.hide();layout.addWidget(self.report_sources)
        self.sources_toggle.toggled.connect(self.report_sources.setVisible)
        self.sources_toggle.toggled.connect(lambda opened:self.sources_toggle.setArrowType(Qt.DownArrow if opened else Qt.RightArrow))

    def _ecm(self):
        layout = self.page('ECM 승인 작업', '기존 일반 Edge와 Excel 문서를 확인합니다. 미리보기 후 별도 승인한 셀만 반영합니다.')
        actions = QHBoxLayout()
        actions.addWidget(self.button('ecm_preview', primary=True))
        actions.addWidget(self.button('ecm_apply'))
        self.buttons['ecm_apply'].setEnabled(False)
        actions.addStretch()
        layout.addLayout(actions)
        self.ecm_target = QLabel('대상 문서 · 미확인')
        self.ecm_target.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.ecm_target.setWordWrap(True)
        layout.addWidget(self.ecm_target)
        self.ecm_stats = QLabel('변경 계획 없음 · 먼저 미리보기를 실행하세요.')
        self.ecm_stats.setObjectName('muted')
        self.ecm_stats.setWordWrap(True)
        layout.addWidget(self.ecm_stats)
        self.ecm_table = DataTable()
        layout.addWidget(self.ecm_table, 1)
        self.ecm_detail = QPlainTextEdit()
        self.ecm_detail.setReadOnly(True)
        self.ecm_detail.setPlaceholderText('미리보기 전입니다. 정확한 문서 전체 경로, 변경 셀, 보류 충돌을 확인한 뒤 승인하세요.')
        self.ecm_detail.setMaximumHeight(180)
        self.ecm_detail.hide()
        raw = QPushButton('원본 변경 계획 보기 / 접기')
        raw.clicked.connect(lambda: self.ecm_detail.setVisible(not self.ecm_detail.isVisible()))
        layout.addWidget(raw, alignment=Qt.AlignLeft)
        layout.addWidget(self.ecm_detail)
        warning = QLabel('Excel 저장·셀 재확인은 서버 체크인 성공이 아닙니다. ECM 서버 반영은 별도로 확인해야 합니다.')
        warning.setWordWrap(True)
        warning.setObjectName('muted')
        layout.addWidget(warning)

    def _history(self):
        layout = self.page('실행 기록', '단계별 실패를 확인하고 수집·출력·ECM을 분리해 복구합니다. 비밀번호는 기록하지 않습니다.')
        layout.addWidget(self.button('history'), alignment=Qt.AlignLeft)
        self.history_table = DataTable()
        layout.addWidget(self.history_table, 2)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.document().setMaximumBlockCount(1500)
        self.log.setPlaceholderText('실행 단계와 안전한 진단 메시지')
        layout.addWidget(self.log, 1)

    def _settings(self):
        layout = self.page('설정', '입력한 설정은 저장 버튼을 눌러야 유지됩니다. 실행 중에는 작업 시작 시의 설정을 사용합니다.')
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        sections = QVBoxLayout(content)
        sections.setContentsMargins(0, 0, 10, 0)
        def group(title):
            box = QGroupBox(title)
            form = QFormLayout(box)
            form.setSpacing(12)
            sections.addWidget(box)
            return form
        form = group('저장·수집')
        for key, label, picker in (('data_dir', '데이터 폴더', 'folder'), ('workbook_path', '누적 Excel', 'file'), ('report_dir', '보고서 폴더', 'folder'), ('driver_path', 'ChromeDriver (선택)', 'file'), ('workspace_url', 'Fastmarkets 작업공간', None), ('representative_symbols', '대표 종목 코드', None)):
            field = QLineEdit()
            field.setAccessibleName(label)
            field.setPlaceholderText('쉼표로 구분' if key == 'representative_symbols' else label)
            self.fields[key] = field
            row = QHBoxLayout()
            row.addWidget(field, 1)
            if picker:
                button = QPushButton('선택')
                button.setAccessibleName(f'{label} 선택')
                button.clicked.connect(lambda checked=False, k=key, mode=picker: self.pick(k, mode))
                row.addWidget(button)
            form.addRow(label, row)
        days = QSpinBox()
        days.setRange(0, 3650)
        self.fields['lookback_days'] = days
        form.addRow('수집 기간 (일)', days)
        sources = QHBoxLayout()
        for key, label in (('fmb_enabled', 'Fastmarkets'), ('fx_enabled', 'SMBS 환율'), ('lme_enabled','LME 공식가격 · 공개 표'),('naver_enabled', 'NAVER 일별 종가 · 로그인 불필요'),('fdr_enabled','FDR/Yahoo · 선택 사항')):
            field = QCheckBox(label)
            self.fields[key] = field
            sources.addWidget(field)
        form.addRow('수집원', sources)
        self.fields['fdr_stock_codes']=QLineEdit()
        self.fields['fdr_stock_codes'].setAccessibleName('FDR 관심종목 코드')
        self.fields['fdr_stock_codes'].setPlaceholderText('005490,005930 · 최대 25개')
        form.addRow('FDR 관심종목',self.fields['fdr_stock_codes'])
        timeout=QSpinBox();timeout.setRange(1,120);timeout.setSuffix(' 초 / 종목')
        self.fields['fdr_timeout']=timeout
        form.addRow('공개 조회 제한',timeout)
        note=QLabel('FDR은 브라우저 없이 공개 HTTP 이력을 조회합니다. 금/WTI는 연속선물 Close이며 한국10년·과거 시총은 지원하지 않습니다.')
        note.setWordWrap(True);note.setObjectName('muted');form.addRow(note)
        form = group('Chrome 연결·계정')
        ports = QLabel('9444  Fastmarkets 전용\n9222  기존 Chrome 보호 · 9337  관리자 Edge 보호 (접근하지 않음)')
        ports.setWordWrap(True)
        form.addRow(ports)
        self.username, self.password = QLineEdit(), QLineEdit()
        self.username.setAccessibleName('Fastmarkets 계정')
        self.password.setAccessibleName('Fastmarkets 비밀번호')
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText('한 번 사용 후 화면에서 지웁니다')
        form.addRow('계정', self.username)
        form.addRow('비밀번호', self.password)
        row = QHBoxLayout()
        for action in ('connect', 'diagnose', 'credentials_save', 'credentials_delete'):
            row.addWidget(self.button(action))
        form.addRow(row)
        form = group('ECM 문서 식별')
        for key, label in (('ecm_title', '정확한 파일명 (.xlsx)'), ('ecm_search', '검색어')):
            self.fields[key] = QLineEdit()
            self.fields[key].setAccessibleName(label)
            form.addRow(label, self.fields[key])
        form = group('Windows 사용자 예약')
        self.fields['v37_auto_time'] = QLineEdit('08:30')
        self.fields['v37_auto_time'].setAccessibleName('예약 시각 HH:MM')
        form.addRow('시각 (KST, HH:MM)', self.fields['v37_auto_time'])
        row = QHBoxLayout()
        for action in ('schedule_status', 'schedule_register', 'schedule_remove'):
            row.addWidget(self.button(action))
        form.addRow(row)
        note = QLabel('사용자 로그인과 네트워크가 필요합니다. 예약 실행은 ECM 승인 쓰기를 하지 않습니다.')
        note.setWordWrap(True)
        form.addRow(note)
        sections.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        layout.addWidget(self.button('save_settings', primary=True), alignment=Qt.AlignRight)

    def pick(self, key, mode):
        value = QFileDialog.getExistingDirectory(self, '폴더 선택', self.fields[key].text()) if mode == 'folder' else QFileDialog.getOpenFileName(self, '파일 선택', self.fields[key].text(), 'Excel (*.xlsx);;모든 파일 (*)' if key == 'workbook_path' else '모든 파일 (*)')[0]
        if value:
            self.fields[key].setText(value)

    def load_settings(self, settings):
        for key, field in self.fields.items():
            value = settings.get(key, ['005490'] if key=='fdr_stock_codes' else 20 if key=='fdr_timeout' else 31 if key == 'lookback_days' else True if key.endswith('_enabled') else '08:30' if key == 'v37_auto_time' else '')
            if isinstance(field, QCheckBox):
                field.setChecked(bool(value))
            elif isinstance(field, QSpinBox):
                field.setValue(int(value))
            else:
                field.setText(','.join(value) if isinstance(value, (list, tuple)) else str(value))
                field.setCursorPosition(0)

    def current_settings(self):
        result = copy.deepcopy(self.service.settings)
        for key, field in self.fields.items():
            result[key] = field.isChecked() if isinstance(field, QCheckBox) else field.value() if isinstance(field, QSpinBox) else field.text().strip()
        result['representative_symbols'] = [x.strip() for x in result['representative_symbols'].split(',') if x.strip()]
        result['fdr_stock_codes']=[x.strip() for x in result['fdr_stock_codes'].split(',') if x.strip()]
        result.pop('password', None)
        result.pop('username', None)
        return result

    def handle_action(self, action):
        if action in ('schedule_remove', 'credentials_delete'):
            if QMessageBox.question(self, LABELS[action], '이 작업을 진행하시겠습니까?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
        if action == 'ecm_apply':
            if not self.pending_plan:
                return
            if QMessageBox.question(self, 'ECM 변경 승인', '미리보기의 전체 문서 경로와 변경 셀을 확인했습니까?\nExcel 저장 후에도 ECM 서버 반영은 별도 확인해야 합니다.', QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
            self.submit(action, plan=copy.deepcopy(self.pending_plan))
        elif action in ('connect', 'credentials_save'):
            payload = {'username': self.username.text().strip(), 'password': self.password.text()}
            self.password.clear()
            self.submit(action, **payload)
        elif action == 'reports':
            self.submit(action, start=self.report_start.text().strip() or None, end=self.report_end.text().strip() or None, series=[s.strip() for s in self.report_series.text().split(',') if s.strip()])
        else:
            self.submit(action)

    def submit(self, action, _settings=None, _background=False, **payload):
        if self.busy or self._closing:
            return
        self.busy = True
        self._background = _background
        self.last_action = action if action not in ('snapshot', 'history') else self.last_action
        self._set_busy(True)
        if not _background:
            self.status.setText(f'{LABELS.get(action, action)} · 실행 중')
            self.state_chip.setText('실행 중')
            self.status.setProperty('state', 'running')
        settings = copy.deepcopy(self.current_settings() if _settings is None else _settings)
        self._active_settings = settings
        if action == 'ecm_preview':
            self._preview_settings = settings
            self.pending_plan = None
        self.requested.emit(action, settings, copy.deepcopy(payload))

    def invalidate_preview(self, *_):
        if self.pending_plan is not None:
            self.pending_plan = None
            self.buttons['ecm_apply'].setEnabled(False)
            self.ecm_detail.appendPlainText('\n설정이 변경되어 승인을 무효화했습니다. 미리보기를 다시 실행하세요.')

    def _set_busy(self, busy):
        for action, button in self.buttons.items():
            button.setEnabled(not busy and (action != 'ecm_apply' or self.pending_plan is not None))
        self.cancel_button.setEnabled(busy)
        self.retry.setEnabled(not busy and self.status.property('state') in ('failed', 'partial', 'needs_action') and self.last_action is not None)

    @Slot(str, object)
    def on_result(self, action, result):
        self.busy = False
        rendered = False
        try:
            self._present_result(action, result, self._background)
            rendered = True
        except Exception as exc:
            self.log.appendPlainText(f'화면 표시 오류 · {action} · {type(exc).__name__}\n원본 작업 결과는 위 실행 기록을 확인하세요. 다시 수집하지 않아도 됩니다.')
            self.status.setText('화면 표시 오류 · 실행 기록에서 원본 작업 결과를 확인하세요. 자료 새로고침으로 다시 표시할 수 있습니다.')
            self.status.setProperty('state', 'failed')
            self.state_chip.setText('화면 표시 오류')
            self.last_action = 'snapshot'  # Recovery must not repeat external writes or collection.
            self._retry_action = 'snapshot'
        finally:
            self.status.style().unpolish(self.status)
            self.status.style().polish(self.status)
            self._set_busy(False)
            if self._closing:
                self._begin_shutdown()
            elif rendered and action in ('collect','collect_public', 'export') and result['status'] in ('complete', 'partial'):
                self.submit('snapshot', _settings=self._active_settings, _background=True)

    def _present_result(self, action, result, background):
        state = result['status']
        message = str(result.get('message', ''))
        feedback = concise_feedback(action, state, message)
        if not background:
            self.state_chip.setText(STATES[state])
            self.status.setProperty('state', state)
            self.status.setText(f'{STATES[state]} · {LABELS.get(action, action)} — {feedback}')
        warnings = result.get('warnings') or []
        self.log.appendPlainText(f'{STATES[state]} · {LABELS.get(action, action)}\n{message}' + ('\n' + '\n'.join(map(str, warnings)) if warnings else ''))
        data = result.get('data') or {}
        if not background:
            self._retry_action = action
            stages = data.get('diag', {}).get('stages', {}) if isinstance(data, dict) else {}
            if action == 'collect' and state == 'partial' and stages.get('export', {}).get('status') in ('failed', 'partial'):
                self._retry_action = 'export'
            self.retry.setText('출력만 다시 시도' if self._retry_action == 'export' else '자료 표시 다시 시도' if self._retry_action == 'snapshot' else '실패 작업 재시도')
        if 'tables' in data:
            self.render_snapshot(data)
        if action == 'save_settings' and state == 'complete':
            self.load_settings(data.get('settings', self.service.settings))
            self.pending_plan = None
        if action == 'history':
            self.history_table.set_rows(history_rows(data.get('runs', [])))
        if action == 'ecm_preview':
            plan = data.get('plan', data)
            valid = isinstance(plan, dict) and all(plan.get(k) for k in ('workbook_path', 'workbook_name', 'sheet')) and isinstance(plan.get('stats'), dict) and isinstance(plan.get('edits'), list)
            self.pending_plan = plan if state in ('complete', 'needs_action') and valid and plan['edits'] else None
            self.ecm_detail.setPlainText(json.dumps(data, ensure_ascii=False, indent=2, default=str))
            self.ecm_target.setText(f"{plan['workbook_name']}\n{plan['workbook_path']}\n시트 · {plan['sheet']}" if valid else '대상 문서 · 미확인')
            stats = plan.get('stats', {}) if isinstance(plan, dict) else {}
            self.ecm_stats.setText(f"신규 {stats.get('fill', 0)} · 정정 {stats.get('correction', 0)} · 충돌 철회·비움 {stats.get('cleared', 0)} · 변경 없음 {stats.get('unchanged', 0)} · 서버 반영 미확인" if valid else '승인 가능한 변경 계획이 없습니다.')
            edits = plan.get('edits', []) if valid else []
            self.ecm_table.set_rows(ecm_rows(edits) if valid else [])
            if self._preview_settings != self.current_settings():
                self.invalidate_preview()
        if action in ('collect','collect_public', 'export', 'ecm_apply'):
            self.pending_plan = None
        if action == 'ecm_apply':
            self.ecm_detail.appendPlainText(f'\n{STATES[state]} · {feedback}\n서버 반영 미확인 — 체크인 결과를 별도 확인하세요.')
        if action in ('reports', 'export', 'collect','collect_public'):
            self._output_paths(data.pop('_ui_files', []))
            self.log.appendPlainText(json.dumps(data, ensure_ascii=False, indent=2, default=str))
            self.report_detail.setPlainText(report_summary(LABELS[action], STATES[state], feedback, self.report_paths))
        if action in ('collect','collect_public'):
            issues=collection_issues(data.get('diag',{}))
            self.collection_errors.setText(issues);self.collection_errors.setVisible(bool(issues))
            self.report_detail.appendPlainText('\n'+issues if issues else '')
        if action in ('schedule_status', 'schedule_register', 'schedule_remove', 'diagnose'):
            self.log.appendPlainText(json.dumps(data, ensure_ascii=False, indent=2, default=str))

    def render_snapshot(self, data):
        self._snapshot = data
        self.metals.set_data(data.get('metals',{}))
        coverage=data.get('metals',{}).get('coverage',[])
        self.coverage_table.set_rows([('출처','제품/계약','상태','저장 시리즈 수','확인 근거·제약')]+[
            (r['source'],r['product'],r['status'],r['count'],r['reason']) for r in coverage])
        self.report_sources.setPlainText(json.dumps({k:data.get(k) for k in ('snapshot_id','as_of','source_dates','warnings')},ensure_ascii=False,indent=2,default=str))
        self.summary.update_snapshot(data, self.current_settings().get('representative_symbols', []))
        for name, table in self.tables.items():
            table.set_rows(data.get('tables', {}).get(name, []))
            if name in ('보고용_금속시세','보고용_LME'):
                for column,header in enumerate(table.model.headers):
                    table.view.setColumnHidden(column,header=='출처')
        stamp=data.get('as_of') or ''
        try:stamp=datetime.fromisoformat(stamp).strftime('%Y-%m-%d %H:%M')
        except (ValueError,TypeError):pass
        self.as_of.setText('자료 갱신 · '+(stamp or '없음'))
        self.as_of.setToolTip('원본 자료 기준 '+str(data.get('as_of') or '없음')+'\nSnapshot '+str(data.get('snapshot_id') or '없음'))
        warnings = data.get('warnings') or []
        has_data = any(table.model.rows for table in self.tables.values())
        missing = sum('missing_history' in str(w) for w in warnings)
        summary = f'확인 필요 {len(warnings)}건' + (f' · 확정 종가 이력 부족 {missing}개' if missing else '') + ' · 상세 내용은 실행 기록에서 확인하세요.'
        self.snapshot_warning.setText(summary if warnings else '저장 관측 · 미확인·이력 부족 상태는 각 행에 표시됩니다.' if has_data else '저장된 자료 없음 · 수집 전입니다. 가격을 추정하지 않습니다.')
        self.snapshot_warning.setToolTip('\n'.join(map(str, warnings)))

    def _output_paths(self, paths):
        self.report_paths = paths
        self.output_files.clear()
        self.output_files.addItems(self.report_paths)
        self.open_report.setEnabled(bool(self.report_paths))

    def open_output(self):
        path = self.output_files.currentText()
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def retry_last(self):
        if self.last_action:
            # Credentials and approval payloads are deliberately never retained.
            self.handle_action(self._retry_action or self.last_action)

    def request_cancel(self):
        self.service.cancel()
        self.cancel_button.setEnabled(False)
        self.status.setText('취소 요청됨 · 실행 작업의 안전한 중단을 기다립니다.')

    def _begin_shutdown(self):
        if not self._shutdown:
            self._shutdown = True
            self.shutdown_requested.emit()

    @Slot()
    def _closed(self):
        if self._closing:
            self.close()

    def closeEvent(self, event):
        if not self.thread.isRunning():
            event.accept()
            return
        event.ignore()
        self._closing = True
        if self.busy:
            self.request_cancel()
        else:
            self._begin_shutdown()


def main_gui():
    import sys
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == '__main__':
    main_gui()
