"""Read-only model/view tables: sorting and filtering never modify source data."""
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
from PySide6.QtCore import QAbstractTableModel, Qt, QSortFilterProxyModel, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTableView, QLabel, QHeaderView, QPushButton

STATUS_TEXT = {'complete':'완료', 'partial':'부분 완료', 'failed':'실패', 'cancelled':'취소', 'needs_action':'확인 필요', 'running':'실행 중', 'pending':'대기', 'skipped':'생략'}
STAGE_TEXT = {'fmb':'금속', 'fx':'환율', 'naver':'확정 종가', 'excel':'Excel', 'reports':'보고서', 'collect':'수집', 'export':'출력', 'ecm':'ECM'}


def concise_feedback(action, state, message):
    """Only short human Korean reaches primary UI. Diagnostics stay in logs."""
    text = ' '.join(str(message or '').split())
    technical = re.search(r'traceback|stacktrace|exception|selenium|webdriver|message:|\{', text, re.I)
    if text and len(text) <= 130 and re.search('[가-힣]', text) and not technical:
        return text
    if state == 'complete':
        return '작업 결과를 확인했습니다.'
    if state == 'partial':
        return '일부 결과를 확인하지 못했습니다. 실행 기록에서 확인하세요.'
    if state == 'cancelled':
        return '작업을 중단했습니다. 실행 기록에서 처리 범위를 확인하세요.'
    if action in ('reports', 'export'):
        return '실행 기록에서 출력 오류를 확인한 뒤 재수집 없이 출력을 다시 시도하세요.'
    if action in ('connect', 'collect', 'diagnose'):
        return '연결·로그인 상태와 실행 기록을 확인하세요.'
    if action.startswith('ecm_'):
        return '실행 기록과 대상 문서를 확인한 뒤 미리보기부터 다시 진행하세요.'
    if action.startswith('schedule_'):
        return 'Windows 사용자 예약과 실행 기록을 확인하세요.'
    return '설정 항목과 실행 기록을 확인한 뒤 다시 시도하세요.'


def report_summary(action_label, state_label, feedback, paths):
    labels = {'.html':'HTML 보고서', '.pptx':'편집 가능한 PPTX', '.xlsx':'Excel 자료', '.json':'스냅샷 JSON'}
    lines = [f'{state_label} · {action_label}', feedback, '', f'생성된 파일 {len(paths)}개']
    for path in paths:
        lines += ['', labels.get(Path(path).suffix.lower(), '결과 파일'), str(path)]
    if not paths:
        lines += ['확인된 결과 파일이 없습니다. 자세한 내용은 실행 기록에서 확인하세요.']
    return '\n'.join(lines)


def existing_output_paths(data):
    """Run on the service worker: network shares must not stall the UI thread."""
    found = []
    def visit(value):
        if isinstance(value, dict):
            for item in value.values():
                visit(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item)
        elif isinstance(value, (str, Path)):
            path = Path(value)
            if path.suffix.lower() in ('.html', '.pptx', '.xlsx', '.json') and path.is_file():
                found.append(str(path.resolve()))
    visit(data)
    return list(dict.fromkeys(found))


def history_rows(runs):
    rows = [('실행 ID', '시작', '종료', '결과', '단계', '단계 결과', '오류·경고', '소요 (초)')]
    for run in runs:
        stages = run.get('stages') or [{}]
        if isinstance(stages, dict):
            stages = [dict(stage=key, **value) if isinstance(value, dict) else dict(stage=key, error=value) for key, value in stages.items()]
        for stage in stages:
            rows.append((run.get('run_id'), run.get('started_at'), run.get('finished_at'), STATUS_TEXT.get(run.get('status'), run.get('status')), STAGE_TEXT.get(stage.get('stage'), stage.get('stage')), STATUS_TEXT.get(stage.get('status'), stage.get('status')), stage.get('error') or stage.get('message') or stage.get('warnings'), stage.get('elapsed_seconds')))
    return rows if runs else []


def ecm_rows(edits):
    decisions = {'fill':'신규', 'correction':'정정', 'quarantine':'충돌 철회·비움'}
    rows = [('행', '열', '기준일', '품목', '종목 코드', '기존 값', '반영 값', '결정', '출처')]
    for edit in edits:
        rows.append((edit.get('row'), edit.get('col'), edit.get('date'), edit.get('header'), edit.get('key'), edit.get('previous'), '비움' if edit.get('incoming') is None else edit['incoming'], decisions.get(edit.get('decision'), edit.get('decision')), edit.get('source')))
    return rows


def numeric(value):
    if isinstance(value, bool) or value in (None, ''):
        return None
    try:
        number = Decimal(str(value).replace(',', '').rstrip('%'))
        return number if number.is_finite() else None
    except InvalidOperation:
        return None


class TableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.headers, self.rows = [], []

    def replace(self, rows):
        self.beginResetModel()
        self.headers = list(rows[0]) if rows else []
        self.rows = [list(r) for r in rows[1:]] if rows else []
        self.endResetModel()

    def rowCount(self, parent=None):
        return len(self.rows)

    def columnCount(self, parent=None):
        return len(self.headers)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return str(self.headers[section])

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        value = row[index.column()] if index.column() < len(row) else None
        number = numeric(value)
        if role == Qt.DisplayRole:
            if value is None or value == '':
                return '—'
            if number is not None and not isinstance(value, str):
                return f'{number:,}'
            return str(value)
        if role == Qt.UserRole:
            return float(number) if number is not None else str(value or '')
        if role == Qt.ToolTipRole:
            return str(value if value is not None else '확인된 자료 없음')
        if role == Qt.TextAlignmentRole:
            return int((Qt.AlignRight if number is not None else Qt.AlignLeft) | Qt.AlignVCenter)
        if role == Qt.ForegroundRole:
            label = str(self.headers[index.column()])
            if number is not None and any(k in label for k in ('등락', '대비', 'change', 'pct')):
                return QColor('#f5445a' if number > 0 else '#4391ff' if number < 0 else '#f3e9e9')
            if str(value) in ('missing_history', 'partial', 'failed', 'conflict', 'stale'):
                return QColor('#f0ce86')
        return None


class DataTable(QWidget):
    onboarding = Signal(str)

    def __init__(self, parent=None, onboard=False):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.empty_panel = QWidget()
        empty_layout = QVBoxLayout(self.empty_panel)
        empty_layout.addStretch()
        self.empty = QLabel('아직 저장된 자료가 없습니다\n\n연결 확인 → 저장 위치 설정 → 첫 수집\n확인된 수치만 표시하고 이전 종가를 추정하지 않습니다.' if onboard else '저장된 기록이 없습니다.')
        self.empty.setWordWrap(True)
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setObjectName('muted')
        empty_layout.addWidget(self.empty)
        if onboard:
            actions = QHBoxLayout()
            actions.addStretch()
            self.setup_button = QPushButton('저장 위치·계정 설정')
            self.setup_button.clicked.connect(lambda: self.onboarding.emit('settings'))
            actions.addWidget(self.setup_button)
            diagnose = QPushButton('연결 진단')
            diagnose.clicked.connect(lambda: self.onboarding.emit('diagnose'))
            actions.addWidget(diagnose)
            actions.addStretch()
            empty_layout.addLayout(actions)
        empty_layout.addStretch()
        layout.addWidget(self.empty_panel, 1)
        self.view = QTableView()
        self.model = TableModel(self)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterKeyColumn(-1)
        self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy.setSortRole(Qt.UserRole)
        self.view.setModel(self.proxy)
        self.view.setSortingEnabled(True)
        self.view.setAlternatingRowColors(True)
        self.view.setSelectionBehavior(QTableView.SelectRows)
        self.view.setEditTriggers(QTableView.NoEditTriggers)
        self.view.verticalHeader().hide()
        self.view.verticalHeader().setDefaultSectionSize(36)
        self.view.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.setHorizontalScrollMode(QTableView.ScrollPerPixel)
        layout.addWidget(self.view, 1)
        self.view.hide()

    def set_rows(self, rows):
        self.model.replace(rows)
        self.empty_panel.setVisible(not self.model.rows)
        self.view.setVisible(bool(self.model.rows))
        self.view.resizeColumnsToContents()
        for column in range(self.model.columnCount()):
            self.view.setColumnWidth(column, min(360, max(105, self.view.columnWidth(column))))

    def search(self, text):
        self.proxy.setFilterFixedString(text)


class SnapshotSummary(QWidget):
    """Derived counts/dates only; no live-price or synthetic statistics."""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        row.setSpacing(12)
        self.cards = []
        for title in ('금속', '환율', '확정 종가'):
            card = QLabel(f'{title} · 자료 없음\n기준일 미확인')
            card.setObjectName('summaryCard')
            card.setWordWrap(True)
            row.addWidget(card, 1)
            self.cards.append(card)
        layout.addLayout(row)
        self.representatives = QLabel('대표 금속 · 설정에서 표시할 종목 코드를 지정하세요.')
        self.representatives.setObjectName('muted')
        self.representatives.setWordWrap(True)
        layout.addWidget(self.representatives)

    def update_snapshot(self, data, symbols):
        tables = data.get('tables', {})
        for index, (title, key) in enumerate((('금속', '보고용_금속시세'), ('환율', '보고용_환율'), ('확정 종가', '보고용_시장지표'))):
            rows = list(tables.get(key, []))[1:]
            confirmed = [r for r in rows if len(r) > 2 and r[2] is not None and (index != 2 or 'close_pair' in r)]
            dates = [str(r[1]) for r in confirmed if r[1]]
            detail = ('최근 기준일 ' + max(dates)) if dates else '기준일 미확인'
            if index == 2:
                detail += f' · 이력 부족 {sum("missing_history" in r for r in rows)}개'
            self.cards[index].setText(f'{title}  {len(confirmed)}개\n{detail}')
        rows = list(tables.get('보고용_금속시세', []))[1:]
        selected = [r for r in rows if str(r[0]) in symbols]
        text = '   /   '.join(f'{r[0]}  {r[2] if r[2] is not None else "미확인"} {r[3]} · {r[1] or "기준일 없음"}' for r in selected[:4] if len(r) >= 4)
        self.representatives.setText('대표 금속 · ' + (text or '선택 종목의 저장 자료 없음' if symbols else '설정에서 표시할 종목 코드를 지정하세요.'))
