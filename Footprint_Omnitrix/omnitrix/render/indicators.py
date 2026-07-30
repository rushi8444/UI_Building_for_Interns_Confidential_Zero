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
            'P': QColor(255, 64, 129),   # Magenta/Pink for main pivot
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
        if not self.bars:
            self.sessions = []
            return
        
        total_bars = len(self.bars)
        last_bar = self.bars[-1]
        last_h = getattr(last_bar, "high", 0)
        last_l = getattr(last_bar, "low", 0)
        last_c = getattr(last_bar, "close", 0)

        if (hasattr(self, '_last_calc_len') and self._last_calc_len == total_bars and
            hasattr(self, '_last_bar_high') and self._last_bar_high == last_h and
            hasattr(self, '_last_bar_low') and self._last_bar_low == last_l and
            hasattr(self, '_last_bar_close') and self._last_bar_close == last_c and
            self.sessions):
            return

        self._last_calc_len = total_bars
        self._last_bar_high = last_h
        self._last_bar_low = last_l
        self._last_bar_close = last_c
        self.sessions = []
        
        # Group bars into sessions using fast integer day keys (timestamp // 86400)
        session_groups = []
        current_day = None
        current_group = []
        current_start_idx = 0
        
        for idx, b in enumerate(self.bars):
            day_key = int(b.start_ts // 86400) if hasattr(b, 'start_ts') and b.start_ts else 0
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
            
        for i, (x_start, x_end, day_bars) in enumerate(session_groups):
            if not day_bars: continue
            high = max(b.high for b in day_bars)
            low = min(b.low for b in day_bars)
            close = day_bars[-1].close
            
            pivot = (high + low + close) / 3.0
            bc_calc = (high + low) / 2.0
            tc_calc = (pivot - bc_calc) + pivot
            
            # Label Swapping Logic: Upper central line is TC, lower is BC
            tc = max(tc_calc, bc_calc)
            bc = min(tc_calc, bc_calc)
                
            r1 = (2 * pivot) - low
            s1 = (2 * pivot) - high
            
            # Extend lines across the current session width (plus right margin for active session)
            extend_x_end = (total_bars + 5) if i == len(session_groups) - 1 else (x_end + 1)

            self.sessions.append({
                'x_start': x_start,
                'x_end': extend_x_end,
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

        win = widget.window() if widget else None
        t = getattr(win, "theme", None)
        is_light = t and getattr(t, "name", "dark") == "light"
        
        if is_light:
            col_p = QColor('#D81B60')     # Deep Magenta
            col_tc = QColor('#00838F')    # Deep Cyan / Teal
            col_r1 = QColor('#2E7D32')    # Forest Green
            col_s1 = QColor('#C62828')    # Crimson Red
        else:
            col_p = self.colors['P']
            col_tc = self.colors['TC']
            col_r1 = self.colors['R1']
            col_s1 = self.colors['S1']
        
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
            
            # P line - Distinct solid/bold line
            p.setPen(pg.mkPen(col_p, width=2, style=Qt.PenStyle.SolidLine))
            p.drawLine(QPointF(x_start, pivot), QPointF(x_end, pivot))
            
            # TC / BC lines - Dotted lines forming range band
            p.setPen(pg.mkPen(col_tc, width=1.5, style=Qt.PenStyle.DotLine))
            p.drawLine(QPointF(x_start, tc), QPointF(x_end, tc))
            p.setPen(pg.mkPen(col_tc, width=1.5, style=Qt.PenStyle.DotLine))
            p.drawLine(QPointF(x_start, bc), QPointF(x_end, bc))
            
            # R1 / S1 lines - Faint dashed lines
            p.setPen(pg.mkPen(col_r1, width=1, style=Qt.PenStyle.DashLine))
            p.drawLine(QPointF(x_start, r1), QPointF(x_end, r1))
            p.setPen(pg.mkPen(col_s1, width=1, style=Qt.PenStyle.DashLine))
            p.drawLine(QPointF(x_start, s1), QPointF(x_end, s1))
            
            # Draw session labels on start of session
            p.setFont(font)
            p.setPen(pg.mkPen(col_p))
            p.drawText(QPointF(x_start + 0.2, pivot - 2), "P")
            p.setPen(pg.mkPen(col_tc))
            p.drawText(QPointF(x_start + 0.2, tc - 2), "TC")
            p.setPen(pg.mkPen(col_tc))
            p.drawText(QPointF(x_start + 0.2, bc - 2), "BC")
            p.setPen(pg.mkPen(col_r1))
            p.drawText(QPointF(x_start + 0.2, r1 - 2), "R1")
            p.setPen(pg.mkPen(col_s1))
            p.drawText(QPointF(x_start + 0.2, s1 - 2), "S1")

    def boundingRect(self):
        if not self.bars: return pg.QtCore.QRectF()
        min_p = min((b.low for b in self.bars), default=0)
        max_p = max((b.high for b in self.bars), default=0)
        if self.sessions:
            for s in self.sessions:
                for k in ('p', 'tc', 'bc', 'r1', 's1'):
                    if k in s:
                        min_p = min(min_p, s[k])
                        max_p = max(max_p, s[k])
        return pg.QtCore.QRectF(-1, min_p - 2.0, len(self.bars) + 10, (max_p - min_p) + 4.0)
