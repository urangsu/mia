"""Native metal explorer. Paint/filter only; never accesses DB/network/COM."""
from datetime import date
from bisect import bisect_left
from PySide6.QtCore import Qt,QPointF,QRectF
from PySide6.QtGui import QPainter,QPen,QColor,QPainterPath
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QComboBox,QLabel,QLineEdit,QToolTip,QScrollArea
from desktop_tables import DataTable
from metal_dashboard import GROUPS,filter_points
from report_exports import display_value


class MetalChart(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.points=[];self.series={};self._days=[];self._ordinals={};self._first=0;self._span=0;self.setMinimumHeight(190)
        self.setMouseTracking(True);self.setAccessibleName('선택 금속의 고시일별 시세 차트')

    def set_series(self,series,points):
        self.series=series or {};self.points=sorted(points,key=lambda p:p['date'])
        self._days=[date.fromisoformat(p['date']).toordinal() for p in self.points]
        self._ordinals=dict(zip((p['date'] for p in self.points),self._days))
        self._first=self._days[0] if self._days else 0
        self._span=self._days[-1]-self._first if self._days else 0;self.update()

    def tooltip_for(self,point):
        value=display_value(point['value']) if point['value'] is not None else '값 없음 · 미고시/보류'
        return '\n'.join((self.series.get('name',''),point['date']+' · '+value+' '+self.series.get('unit',''),
            self.series.get('mode','')+' · '+point.get('status',''),self.series.get('conditions',''),
            self.series.get('source','')+' · '+self.series.get('source_url',''),
            '뷰 '+self.series.get('view_key','')))

    def _plot(self):return QRectF(90,18,max(1,self.width()-115),max(1,self.height()-55))

    def _x(self,day):
        area=self._plot()
        return area.left()+(self._ordinals[day]-self._first)/self._span*area.width() if self._span else area.center().x()

    def nearest_point(self,x):
        if not self.points:return None
        area=self._plot();ordinal=self._first+(x-area.left())/area.width()*self._span
        index=bisect_left(self._days,ordinal)
        candidates=[i for i in (index-1,index) if 0<=i<len(self.points)]
        return self.points[min(candidates,key=lambda i:abs(self._days[i]-ordinal))]

    def mouseMoveEvent(self,event):
        if not self.points:return
        point=self.nearest_point(event.position().x())
        QToolTip.showText(event.globalPosition().toPoint(),self.tooltip_for(point),self)

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        area=self._plot();values=[p['value'] for p in self.points if p['value'] is not None]
        painter.setPen(QColor('#b4b4bf'))
        if not values:
            painter.drawText(self.rect(),Qt.AlignCenter,'검증된 저장 시세 없음 · 다른 그룹 또는 수집 상태를 확인하세요.')
            return
        low,high=min(values),max(values);padding=(high-low)*.1 or max(abs(low)*.01,.01)
        low-=padding;high+=padding
        def y(v):return area.bottom()-(v-low)/(high-low)*area.height()
        for i in range(4):
            level=low+(high-low)*i/3;yy=y(level)
            painter.setPen(QPen(QColor('#303039'),1));painter.drawLine(QPointF(area.left(),yy),QPointF(area.right(),yy))
            painter.setPen(QColor('#b4b4bf'));painter.drawText(QRectF(0,yy-10,80,20),Qt.AlignRight|Qt.AlignVCenter,f'{level:,.2f}')
        path=QPainterPath();connected=False
        for point in self.points:
            if point['value'] is None:connected=False;continue
            pos=QPointF(self._x(point['date']),y(point['value']))
            if connected:path.lineTo(pos)
            else:path.moveTo(pos)
            connected=True
        painter.setPen(QPen(QColor('#4391ff'),2));painter.drawPath(path)
        painter.setBrush(QColor('#4391ff'))
        for point in self.points:
            if point['value'] is not None:painter.drawEllipse(QPointF(self._x(point['date']),y(point['value'])),2.5,2.5)
        painter.setPen(QColor('#b4b4bf'))
        painter.drawText(QRectF(area.left(),area.bottom()+9,120,22),Qt.AlignLeft,self.points[0]['date'])
        painter.drawText(QRectF(area.right()-120,area.bottom()+9,120,22),Qt.AlignRight,self.points[-1]['date'])


class MetalPanel(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self._series=[];self._search=''
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0)
        self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);outer.addWidget(self.scroll)
        content=QWidget();content.setMinimumHeight(510);self.scroll.setWidget(content)
        layout=QVBoxLayout(content);layout.setContentsMargins(0,6,0,0);layout.setSpacing(10)
        controls=QHBoxLayout()
        self.group=QComboBox();self.group.addItems(GROUPS);self.group.setAccessibleName('금속 그룹')
        self.product=QComboBox();self.product.setMinimumWidth(230);self.product.setAccessibleName('품목·조건·뷰 선택')
        self.period=QComboBox();self.period.addItems(('1개월','3개월','6개월','1년','전체'));self.period.setCurrentText('3개월');self.period.setAccessibleName('차트 기간')
        controls.addWidget(self.group);controls.addWidget(self.product,1);controls.addWidget(self.period)
        layout.addLayout(controls)
        ranges=QHBoxLayout();ranges.addWidget(QLabel('월 범위'))
        self.start=QLineEdit();self.end=QLineEdit()
        for field,label in ((self.start,'시작월'),(self.end,'종료월')):
            field.setPlaceholderText(label+' YYYY-MM');field.setAccessibleName(label);field.setMaximumWidth(180)
            field.editingFinished.connect(self.refresh);ranges.addWidget(field)
        ranges.addStretch();self.coverage=QLabel('미관측');self.coverage.setObjectName('muted');ranges.addWidget(self.coverage)
        layout.addLayout(ranges)
        self.caption=QLabel('리튬부터 니켈·코발트·망간·구리·블랙매스까지, 실제 저장된 시세만 표시합니다.')
        self.caption.setWordWrap(True);self.caption.setObjectName('muted');layout.addWidget(self.caption)
        self.chart=MetalChart();layout.addWidget(self.chart,2)
        self.history=DataTable();self.history.setMinimumHeight(150);layout.addWidget(self.history,1)
        self.group.currentIndexChanged.connect(self._products)
        self.product.currentIndexChanged.connect(self.refresh);self.period.currentIndexChanged.connect(self.refresh)

    def set_data(self,data):
        self._series=list(data.get('series',[]));self._coverage=list(data.get('coverage',[]));self._products()

    def search(self,text):
        self._search=text.casefold().strip();self._products()

    def _products(self,*_):
        current=self.product.currentData();self.product.blockSignals(True);self.product.clear()
        for item in self._series:
            if item['group']!=self.group.currentText():continue
            if self._search and self._search not in ' '.join(str(v) for k,v in item.items() if k!='points').casefold():continue
            label=' · '.join((item['name'],item['unit'],item['mode'],item['source']))
            self.product.addItem(label,item['id']);self.product.setItemData(self.product.count()-1,item['conditions']+'\n'+item['code']+' · 뷰 '+item['view_key'],Qt.ToolTipRole)
        index=self.product.findData(current)
        self.product.setCurrentIndex(index if index>=0 else 0);self.product.blockSignals(False);self.refresh()

    def refresh(self,*_):
        item=next((s for s in self._series if s['id']==self.product.currentData()),None)
        count=sum(s['group']==self.group.currentText() for s in self._series)
        self.coverage.setText(f'{count}개 저장 시리즈' if count else '미관측 · 저장 시세 없음')
        if not item:
            self.chart.set_series(None,[]);self.history.set_rows([])
            self.caption.setText('저장된 '+self.group.currentText()+' 자료 없음 · LME/FMB/SMM을 서로 대체하지 않습니다.');return
        months={'1개월':1,'3개월':3,'6개월':6,'1년':12}.get(self.period.currentText())
        try:points=filter_points(item['points'],months=months,start=self.start.text().strip() or None,end=self.end.text().strip() or None)
        except ValueError:
            self.caption.setText('월 범위를 YYYY-MM 형식과 시작 ≤ 종료 순서로 확인하세요.')
            self.chart.set_series(item,[]);self.history.set_rows([]);return
        self.caption.setText(item['name']+' · '+item['conditions'])
        self.caption.setToolTip(item['conditions']+'\n'+item['code']+'\n'+item['source_url'])
        self.chart.set_series(item,points)
        self.history.set_rows([('고시일','Mid','단위','구분','상태','출처')]+[
            (p['date'],p['value'],item['unit'],item['mode'],p['status'],item['source']) for p in reversed(points)])
