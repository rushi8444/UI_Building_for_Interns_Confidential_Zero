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
    """Central Pivot Range (P, TC, BC)"""
    def __init__(self):
        super().__init__()
        self.bars = []
        self.cpr_data = {}  # day_index -> (P, TC, BC)
        self.colors = {
            'P': QColor(255, 64, 129),  # Pink for main pivot
            'TC': QColor(0, 188, 212),  # Cyan for Top Central
            'BC': QColor(0, 188, 212)   # Cyan for Bottom Central
        }

    def set_bars(self, bars):
        self.bars = bars
        self._calculate()
        self.update()

    def _calculate(self):
        self.cpr_data = {}
        if not self.bars: return
        
        # Calculate daily pivots. We will group by day based on timestamp.
        # Assuming bars have a 'ts' (timestamp) or we use buckets.
        # For simplicity in this footprint view, we'll assume standard 24h trading day resets at 00:00.
        import datetime
        daily_high = {}
        daily_low = {}
        daily_close = {}
        
        for x, b in enumerate(self.bars):
            # BarSeries doesn't expose a raw timestamp on `Bar` easily without checking model.py
            # But wait, usually `b` has `open, high, low, close`. What about time?
            # In `BarSeries`, bucket is `int(ts_s // tf_s)`. We can derive time if needed.
            pass
        
        # Alternatively, if we just want a simple pivot from previous N bars 
        # (Since it's intraday, we'll calculate CPR dynamically from the first bar of the session)
        if len(self.bars) > 0:
            h = max(b.high for b in self.bars)
            l = min(b.low for b in self.bars)
            c = self.bars[-1].close
            
            p = (h + l + c) / 3
            bc = (h + l) / 2
            tc = (p - bc) + p
            
            # Re-order so TC is always higher than BC
            if tc < bc:
                tc, bc = bc, tc
                
            self.cpr_data['current'] = (p, tc, bc)

    def paint(self, p, opt, widget):
        if not self.cpr_data: return
        
        view = self.getViewBox()
        if not view: return
        
        x_min, x_max = view.viewRange()[0]
        
        pivot, tc, bc = self.cpr_data['current']
        
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        
        # Draw P
        p.setPen(pg.mkPen(self.colors['P'], width=2))
        p.drawLine(QPointF(x_min, pivot), QPointF(x_max, pivot))
        
        # Draw TC
        p.setPen(pg.mkPen(self.colors['TC'], width=1, style=Qt.PenStyle.DashLine))
        p.drawLine(QPointF(x_min, tc), QPointF(x_max, tc))
        
        # Draw BC
        p.setPen(pg.mkPen(self.colors['BC'], width=1, style=Qt.PenStyle.DashLine))
        p.drawLine(QPointF(x_min, bc), QPointF(x_max, bc))
        
        # Labels
        p.setFont(QFont("Arial", 8, QFont.Weight.Bold))
        p.setPen(pg.mkPen(self.colors['P']))
        p.drawText(QPointF(x_min + 5, pivot - 2), "P")
        p.setPen(pg.mkPen(self.colors['TC']))
        p.drawText(QPointF(x_min + 5, tc - 2), "TC")
        p.setPen(pg.mkPen(self.colors['BC']))
        p.drawText(QPointF(x_min + 5, bc - 2), "BC")

    def boundingRect(self):
        if not self.bars: return pg.QtCore.QRectF()
        min_p = min((b.low for b in self.bars), default=0)
        max_p = max((b.high for b in self.bars), default=0)
        return pg.QtCore.QRectF(-1, min_p - 1.0, len(self.bars) + 2, (max_p - min_p) + 2.0)
