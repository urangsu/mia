"""Native, restrained desktop tokens. No bundled brand assets or fonts."""
from PySide6.QtGui import QFont


STYLE = '''
QWidget { background:#17171c; color:#f3e9e9; font-size:15px; }
QMainWindow, QStackedWidget { background:#17171c; }
QLabel#heading { font-size:24px; font-weight:700; }
QLabel#section { font-size:18px; font-weight:600; }
QLabel#summaryCard { background:#202025; border:1px solid #35353f; border-radius:8px; padding:16px; line-height:1.5; }
QLabel#stateChip { background:#24344d; color:#c1d9ff; border-radius:12px; padding:5px 12px; }
QLabel#muted { color:#b4b4bf; }
QLabel#status { background:#202025; border:1px solid #35353f; border-radius:8px; padding:12px; }
QLabel#status[state="failed"] { color:#ff8d9b; border-color:#8d3f4c; }
QLabel#status[state="partial"], QLabel#status[state="needs_action"] { color:#f0ce86; }
QLabel#status[state="complete"] { color:#a9ceff; }
QListWidget#nav { background:#101013; border:0; padding:18px 12px; outline:0; }
QListWidget#nav::item { padding:13px 12px; margin:3px 0; border-radius:8px; }
QListWidget#nav::item:selected { background:#24344d; color:#b8d5ff; }
QPushButton { background:#272730; border:1px solid #3c3c47; border-radius:8px; padding:9px 14px; min-height:18px; }
QPushButton:hover { background:#343440; border-color:#727285; }
QPushButton:pressed { background:#1c2e48; }
QPushButton[primary="true"] { background:#326fc5; border-color:#4391ff; color:white; font-weight:600; }
QPushButton:disabled { color:#7e7e89; background:#202025; border-color:#303039; }
QLineEdit, QSpinBox, QComboBox { background:#202025; border:1px solid #41414b; border-radius:8px; padding:9px; min-height:18px; selection-background-color:#326fc5; }
QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border-color:#4391ff; }
QCheckBox { spacing:10px; padding:7px; }
QCheckBox::indicator { width:18px; height:18px; }
QTextEdit, QPlainTextEdit { background:#101013; border:1px solid #35353f; border-radius:8px; padding:10px; }
QTableView { background:#17171c; alternate-background-color:#1c1c22; border:1px solid #35353f; border-radius:8px; gridline-color:#2d2d35; selection-background-color:#243956; selection-color:#f3e9e9; }
QHeaderView::section { background:#202025; color:#bcbcc8; padding:10px 12px; border:0; border-bottom:1px solid #35353f; }
QTabWidget::pane { border:0; padding-top:8px; }
QTabBar::tab { color:#b4b4bf; padding:12px 16px; border-bottom:2px solid transparent; }
QTabBar::tab:selected { color:#c5dcff; border-bottom:2px solid #4391ff; }
QScrollArea { border:0; }
QGroupBox { border:1px solid #35353f; border-radius:8px; margin-top:22px; padding:20px 14px 12px; }
QGroupBox::title { subcontrol-origin:margin; left:16px; padding:0 6px; color:#dddde6; font-size:17px; }
QToolTip { background:#202025; color:#f3e9e9; border:1px solid #53535f; padding:6px; }
QScrollBar:vertical { background:#17171c; width:10px; }
QScrollBar::handle:vertical { background:#494952; min-height:30px; border-radius:5px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
'''


def apply_theme(app):
    import sys
    if app.property('miaThemeApplied'):
        return
    font = QFont('Malgun Gothic' if sys.platform == 'win32' else 'Apple SD Gothic Neo')
    font.setPointSize(11)
    app.setFont(font)
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)
    app.setProperty('miaThemeApplied', True)
