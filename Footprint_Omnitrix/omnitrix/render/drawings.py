import pyqtgraph as pg
from pyqtgraph.GraphicsScene.mouseEvents import MouseClickEvent, MouseDragEvent
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QColor, QPen, QBrush, QPainter, QFont

class FibRetracement(pg.ROI):
    """Fibonacci Retracement tool (0, 0.236, 0.382, 0.5, 0.618, 0.786, 1)"""
    def __init__(self, pos1, pos2, **kwargs):
        # pos1 and pos2 are [x, y]
        super().__init__(pos1, size=[pos2[0]-pos1[0], pos2[1]-pos1[1]], **kwargs)
        self.addFreeHandle((0, 0))
        self.addFreeHandle((1, 1))
        self.levels = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
        self.colors = [
            QColor(120, 123, 134), QColor(244, 67, 54), QColor(76, 175, 80), 
            QColor(0, 230, 118), QColor(33, 150, 243), QColor(156, 39, 176), QColor(120, 123, 134)
        ]
        self.sigRegionChanged.connect(self.update)

    def paint(self, p, opt, widget):
        handles = self.getHandles()
        if len(handles) < 2: return
        p1 = handles[0].pos()
        p2 = handles[1].pos()
        
        # map to view to draw horizontal lines extending to the right
        view = self.getViewBox()
        if not view: return
        
        y1, y2 = p1.y(), p2.y()
        x1, x2 = p1.x(), p2.x()
        
        diff = y2 - y1
        right_edge = self.boundingRect().right() + 5000  # extend lines infinitely right visually

        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        
        for lvl, col in zip(self.levels, self.colors):
            y_lvl = y1 + (diff * lvl)
            p.setPen(pg.mkPen(col, width=1, style=Qt.PenStyle.DashLine))
            p.drawLine(QPointF(x1, y_lvl), QPointF(right_edge, y_lvl))
            
            # Text
            p.setPen(pg.mkPen(col))
            p.setFont(QFont("Arial", 8, QFont.Weight.Bold))
            p.drawText(QPointF(x1, y_lvl - 2), f"{lvl:.3f}")

class PositionDrawer(pg.ROI):
    """TradingView style Long/Short position risk/reward drawer."""
    def __init__(self, pos, size, is_long=True, **kwargs):
        super().__init__(pos, size, **kwargs)
        self.is_long = is_long
        self.entry_pct = 0.5 # 0.5 means entry is perfectly in middle initially
        self.addScaleHandle([0.5, 1], [0.5, 0.5])  # Top handle (TP or SL)
        self.addScaleHandle([0.5, 0], [0.5, 0.5])  # Bottom handle (SL or TP)
        
        # Add a custom handle for entry price
        self.entry_handle = self.addFreeHandle([0.5, 0.5])
        
        self.sigRegionChanged.connect(self._on_region_changed)

    def _on_region_changed(self):
        # Keep entry handle horizontally centered
        eh_pos = self.entry_handle.pos()
        if eh_pos.x() != 0.5:
            self.entry_handle.setPos([0.5, eh_pos.y()])
        self.entry_pct = self.entry_handle.pos().y()
        self.update()

    def paint(self, p, opt, widget):
        rect = self.boundingRect()
        entry_y = rect.bottom() + (rect.top() - rect.bottom()) * self.entry_pct
        
        tp_color = QColor(0, 230, 118, 60) if self.is_long else QColor(255, 23, 68, 60)
        sl_color = QColor(255, 23, 68, 60) if self.is_long else QColor(0, 230, 118, 60)
        
        tp_rect = QRectF(rect.left(), entry_y, rect.width(), rect.top() - entry_y) if self.is_long else QRectF(rect.left(), rect.bottom(), rect.width(), entry_y - rect.bottom())
        sl_rect = QRectF(rect.left(), rect.bottom(), rect.width(), entry_y - rect.bottom()) if self.is_long else QRectF(rect.left(), entry_y, rect.width(), rect.top() - entry_y)

        # Draw backgrounds
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(tp_color))
        p.drawRect(tp_rect)
        
        p.setBrush(QBrush(sl_color))
        p.drawRect(sl_rect)
        
        # Draw Entry Line
        p.setPen(pg.mkPen('#FFFFFF' if self.is_long else '#000000', width=2))
        p.drawLine(QPointF(rect.left(), entry_y), QPointF(rect.right(), entry_y))

        # Risk Reward Calculation
        entry_price = entry_y
        tp_price = rect.top() if self.is_long else rect.bottom()
        sl_price = rect.bottom() if self.is_long else rect.top()

        risk = abs(entry_price - sl_price)
        reward = abs(tp_price - entry_price)
        rr = reward / risk if risk > 0 else 0

        p.setPen(pg.mkPen('#E0E0E0'))
        p.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        text_rect = QRectF(rect.left(), entry_y - 20, rect.width(), 20)
        p.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, f"R/R: {rr:.2f}")

        # TP and SL Prices
        p.setFont(QFont("Arial", 8, QFont.Weight.Bold))
        p.setPen(pg.mkPen('#FFFFFF' if self.is_long else '#000000'))
        tp_text_rect = QRectF(rect.left(), tp_price, rect.width(), 15) if self.is_long else QRectF(rect.left(), tp_price - 15, rect.width(), 15)
        p.drawText(tp_text_rect, Qt.AlignmentFlag.AlignCenter, f"TP: {tp_price:.2f}")
        
        sl_text_rect = QRectF(rect.left(), sl_price - 15, rect.width(), 15) if self.is_long else QRectF(rect.left(), sl_price, rect.width(), 15)
        p.drawText(sl_text_rect, Qt.AlignmentFlag.AlignCenter, f"SL: {sl_price:.2f}")


class FixedVolumeProfile(pg.ROI):
    """Draws a fixed range volume profile."""
    def __init__(self, pos, size, get_bars_cb, tick_size, **kwargs):
        super().__init__(pos, size, **kwargs)
        self.get_bars_cb = get_bars_cb
        self.tick_size = tick_size
        self.addScaleHandle([0, 0.5], [1, 0.5])
        self.addScaleHandle([1, 0.5], [0, 0.5])
        self.sigRegionChanged.connect(self.update)

    def paint(self, p, opt, widget):
        p.setPen(pg.mkPen('#444444', width=1, style=Qt.PenStyle.DashLine))
        p.setBrush(QBrush(QColor(41, 98, 255, 20)))
        rect = self.boundingRect()
        p.drawRect(rect)
        
        # Map ROI to scene to get x-range in coordinates
        x_min, x_max = rect.left(), rect.right()
        bars = self.get_bars_cb(x_min, x_max)
        if not bars: return
        
        # Aggregate Volume
        vol_by_price = {}
        for b in bars:
            for ti, (sell_v, buy_v) in b.cells.items():
                p_lvl = ti * self.tick_size
                vol_by_price[p_lvl] = vol_by_price.get(p_lvl, 0) + (sell_v + buy_v)

        if not vol_by_price: return
        
        max_vol = max(vol_by_price.values())
        if max_vol == 0: return

        # Draw Profile on the right side of the box
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(100, 181, 246, 120)))
        box_width = rect.width()
        
        poc_price = max(vol_by_price, key=vol_by_price.get)
        
        for p_lvl, vol in vol_by_price.items():
            bar_width = (vol / max_vol) * (box_width * 0.8)
            bar_rect = QRectF(rect.right() - bar_width, p_lvl - self.tick_size/2, bar_width, self.tick_size)
            if p_lvl == poc_price:
                p.setBrush(QBrush(QColor(255, 23, 68, 200))) # Highlight POC
                p.drawRect(bar_rect)
                p.setBrush(QBrush(QColor(100, 181, 246, 120)))
                # Draw POC line extended
                p.setPen(pg.mkPen('#FF1744', width=2))
                p.drawLine(QPointF(rect.left(), poc_price), QPointF(rect.right(), poc_price))
                p.setPen(Qt.PenStyle.NoPen)
            else:
                p.drawRect(bar_rect)
