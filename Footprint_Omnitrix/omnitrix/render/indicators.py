import pyqtgraph as pg
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QColor, QPen, QPainter, QFont

class EMAItem(pg.GraphicsObject):
    """Draws an Exponential Moving Average."""
    def __init__(self, period=9, color=QColor(255, 193, 7)):
        super().__init__()
        self.period = period
        self.color = color
        self.bars = []
        self.emas = []

    def set_bars(self, bars):
        self.bars = bars
        self._calculate()
        self.update()

    def _calculate(self):
        if not self.bars: 
            self.emas = []
            return
            
        k = 2 / (self.period + 1)
        
        # Incremental calculation to avoid O(N) on every tick
        start_idx = 0
        if len(self.emas) > 0 and len(self.emas) <= len(self.bars):
            start_idx = len(self.emas) - 1
            ema = self.emas[-1]
        else:
            self.emas = []
            ema = self.bars[0].close
            start_idx = 0
            
        for i in range(start_idx, len(self.bars)):
            b = self.bars[i]
            ema = (b.close - ema) * k + ema
            if i == len(self.emas):
                self.emas.append(ema)
            else:
                self.emas[i] = ema

    def paint(self, p, opt, widget):
        if not self.emas or len(self.emas) < 2: return
        
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(pg.mkPen(self.color, width=2))
        
        view = self.getViewBox()
        if not view: return
        
        x_min, x_max = view.viewRange()[0]
        x_start = max(0, int(x_min) - 1)
        x_end = min(len(self.emas), int(x_max) + 2)

        path = pg.QtGui.QPainterPath()
        path.moveTo(x_start, self.emas[x_start])
        for x in range(x_start + 1, x_end):
            path.lineTo(x, self.emas[x])
        
        p.drawPath(path)

    def boundingRect(self):
        if not self.bars: return pg.QtCore.QRectF()
        min_p = min((b.low for b in self.bars), default=0)
        max_p = max((b.high for b in self.bars), default=0)
        return pg.QtCore.QRectF(-1, min_p - 1.0, len(self.bars) + 2, (max_p - min_p) + 2.0)


class CPRItem(pg.GraphicsObject):
    """Central Pivot Range (P, TC, BC, R1, S1) per session/day."""
    def __init__(self):
        super().__init__()
        self.bars = []
        self.sessions = []  # list of dicts: {'x_start': i, 'x_end': j, 'p': ..., 'tc': ..., 'bc': ..., 'r1': ..., 's1': ...}
        self.colors = {
            'P': QColor(255, 64, 129),   # Pink for main pivot
            'TC': QColor(0, 188, 212),   # Cyan for Top Central
            'BC': QColor(0, 188, 212),   # Cyan for Bottom Central
            'R1': QColor(0, 230, 118),   # Green for Resistance 1
            'S1': QColor(255, 23, 68),    # Red for Support 1
        }

    def set_bars(self, bars):
        self.bars = bars
        self._calculate()
        self.update()

    def _calculate(self):
        self.sessions = []
        if not self.bars: return
        
        import datetime
        
        # Group bars into sessions by calendar day or fixed blocks
        session_groups = []
        current_day = None
        current_group = []
        current_start_idx = 0
        
        for idx, b in enumerate(self.bars):
            day_key = datetime.datetime.fromtimestamp(b.start_ts).date() if hasattr(b, 'start_ts') and b.start_ts else 0
            if current_day is None:
                current_day = day_key
                current_start_idx = idx
            elif day_key != current_day:
                session_groups.append((current_start_idx, idx - 1, current_group))
                current_day = day_key
                current_group = []
                current_start_idx = idx
            current_group.append(b)
            
        if current_group:
            session_groups.append((current_start_idx, len(self.bars) - 1, current_group))
            
        for x_start, x_end, day_bars in session_groups:
            if not day_bars: continue
            high = max(b.high for b in day_bars)
            low = min(b.low for b in day_bars)
            close = day_bars[-1].close
            
            pivot = (high + low + close) / 3.0
            bc = (high + low) / 2.0
            tc = (pivot - bc) + pivot
            if tc < bc:
                tc, bc = bc, tc
                
            r1 = (2 * pivot) - low
            s1 = (2 * pivot) - high
            
            self.sessions.append({
                'x_start': x_start,
                'x_end': x_end + 1,
                'p': pivot,
                'tc': tc,
                'bc': bc,
                'r1': r1,
                's1': s1,
            })

    def paint(self, p, opt, widget):
        if not self.sessions: return
        
        view = self.getViewBox()
        if not view: return
        
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        font = QFont("Arial", 8, QFont.Weight.Bold)
        
        for sess in self.sessions:
            x_start = sess['x_start']
            x_end = sess['x_end']
            pivot = sess['p']
            tc = sess['tc']
            bc = sess['bc']
            r1 = sess['r1']
            s1 = sess['s1']
            
            # P line
            p.setPen(pg.mkPen(self.colors['P'], width=2))
            p.drawLine(QPointF(x_start, pivot), QPointF(x_end, pivot))
            
            # TC / BC lines
            p.setPen(pg.mkPen(self.colors['TC'], width=1, style=Qt.PenStyle.DashLine))
            p.drawLine(QPointF(x_start, tc), QPointF(x_end, tc))
            p.setPen(pg.mkPen(self.colors['BC'], width=1, style=Qt.PenStyle.DashLine))
            p.drawLine(QPointF(x_start, bc), QPointF(x_end, bc))
            
            # R1 / S1 lines
            p.setPen(pg.mkPen(self.colors['R1'], width=1, style=Qt.PenStyle.DotLine))
            p.drawLine(QPointF(x_start, r1), QPointF(x_end, r1))
            p.setPen(pg.mkPen(self.colors['S1'], width=1, style=Qt.PenStyle.DotLine))
            p.drawLine(QPointF(x_start, s1), QPointF(x_end, s1))
            
            # Draw session labels on start of session
            p.setFont(font)
            p.setPen(pg.mkPen(self.colors['P']))
            p.drawText(QPointF(x_start + 0.2, pivot - 2), "P")
            p.setPen(pg.mkPen(self.colors['TC']))
            p.drawText(QPointF(x_start + 0.2, tc - 2), "TC")
            p.setPen(pg.mkPen(self.colors['BC']))
            p.drawText(QPointF(x_start + 0.2, bc - 2), "BC")

    def boundingRect(self):
        if not self.bars: return pg.QtCore.QRectF()
        min_p = min((b.low for b in self.bars), default=0)
        max_p = max((b.high for b in self.bars), default=0)
        return pg.QtCore.QRectF(-1, min_p - 1.0, len(self.bars) + 2, (max_p - min_p) + 2.0)
