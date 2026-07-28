import pyqtgraph as pg
from pyqtgraph.GraphicsScene.mouseEvents import MouseClickEvent, MouseDragEvent
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QColor, QPen, QBrush, QPainter, QFont

FONT_LABEL = QFont("Arial", 9, QFont.Weight.Bold)

class FibRetracement(pg.ROI):
    """Fibonacci Retracement tool (0, 0.236, 0.382, 0.5, 0.618, 0.786, 1)"""
    def __init__(self, pos, size, **kwargs):
        super().__init__(pos, size=size, **kwargs)
        self.addFreeHandle((0, 0))
        self.addFreeHandle((1, 1))
        self.levels = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
        self.colors = [
            QColor(120, 123, 134), QColor(244, 67, 54), QColor(76, 175, 80), 
            QColor(0, 230, 118), QColor(33, 150, 243), QColor(156, 39, 176), QColor(120, 123, 134)
        ]
        self.pens = [pg.mkPen(col, width=1, style=Qt.PenStyle.DashLine) for col in self.colors]

    def paint(self, p, opt, widget):
        handles = self.getHandles()
        if len(handles) < 2: return
        p1 = handles[0].pos()
        p2 = handles[1].pos()
        
        y1, y2 = p1.y(), p2.y()
        x1, x2 = p1.x(), p2.x()
        diff = y2 - y1
        
        world_y = self.pos().y()
        world_h = self.size().y()

        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        
        tr = p.transform()
        
        for lvl, pen, col in zip(self.levels, self.pens, self.colors):
            y_lvl = y1 + (diff * lvl)
            price_lvl = world_y + (world_h * lvl)
            
            p.setPen(pen)
            p.drawLine(QPointF(x1, y_lvl), QPointF(x2, y_lvl))
            
            # Fast un-scaled text rendering
            screen_pt = tr.map(QPointF(x1, y_lvl))
            p.save()
            p.resetTransform()
            p.setPen(pg.mkPen(col))
            p.setFont(FONT_LABEL)
            p.drawText(screen_pt + QPointF(6, -4), f"{lvl:.3f} ({price_lvl:,.2f})")
            p.restore()

class PositionDrawer(pg.ROI):
    """TradingView style Long/Short position risk/reward drawer."""
    def __init__(self, pos, size, is_long=True, **kwargs):
        super().__init__(pos, size, **kwargs)
        self.is_long = is_long
        self.entry_pct = 0.5 # 0.5 means entry is perfectly in middle initially
        self.addScaleHandle([0.5, 1], [0.5, 0.5])  # Top handle (TP or SL)
        self.addScaleHandle([0.5, 0], [0.5, 0.5])  # Bottom handle (SL or TP)
        self.entry_handle = self.addFreeHandle([0.5, 0.5])
        self.sigRegionChanged.connect(self._on_region_changed)

        self.tp_color = QColor(0, 230, 118, 50) if self.is_long else QColor(255, 23, 68, 50)
        self.sl_color = QColor(255, 23, 68, 50) if self.is_long else QColor(0, 230, 118, 50)
        self.tp_brush = QBrush(self.tp_color)
        self.sl_brush = QBrush(self.sl_color)
        self.entry_pen = pg.mkPen('#FFFFFF' if self.is_long else '#000000', width=2)
        self.white_pen = pg.mkPen('#FFFFFF')

    def _on_region_changed(self):
        eh_pos = self.entry_handle.pos()
        if eh_pos.x() != 0.5:
            self.entry_handle.setPos([0.5, eh_pos.y()])
        self.entry_pct = self.entry_handle.pos().y()

    def paint(self, p, opt, widget):
        rect = self.boundingRect()
        entry_y = rect.bottom() + (rect.top() - rect.bottom()) * self.entry_pct
        
        top_y = rect.top() if self.is_long else rect.bottom()
        bot_y = rect.bottom() if self.is_long else rect.top()
        
        tp_rect = QRectF(rect.left(), entry_y, rect.width(), top_y - entry_y)
        sl_rect = QRectF(rect.left(), bot_y, rect.width(), entry_y - bot_y)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.tp_brush)
        p.drawRect(tp_rect)
        
        p.setBrush(self.sl_brush)
        p.drawRect(sl_rect)
        
        p.setPen(self.entry_pen)
        p.drawLine(QPointF(rect.left(), entry_y), QPointF(rect.right(), entry_y))

        world_y = self.pos().y()
        world_h = self.size().y()
        entry_price_world = world_y + world_h * self.entry_pct
        tp_price_world = world_y + world_h if self.is_long else world_y
        sl_price_world = world_y if self.is_long else world_y + world_h

        risk = abs(entry_price_world - sl_price_world)
        reward = abs(tp_price_world - entry_price_world)
        rr = reward / risk if risk > 0 else 0

        center_x = rect.center().x()
        tr = p.transform()
        rr_pt = tr.map(QPointF(center_x, entry_y))
        tp_pt = tr.map(QPointF(center_x, top_y))
        sl_pt = tr.map(QPointF(center_x, bot_y))
        
        p.save()
        p.resetTransform()
        p.setFont(FONT_LABEL)
        p.setPen(self.white_pen)
        
        p.drawText(rr_pt + QPointF(-25, -6), f"R/R: {rr:.2f}")
        p.drawText(tp_pt + QPointF(-40, 16 if self.is_long else -6), f"TP: {tp_price_world:,.2f}")
        p.drawText(sl_pt + QPointF(-40, -6 if self.is_long else 16), f"SL: {sl_price_world:,.2f}")
        p.restore()

class FixedVolumeProfile(pg.ROI):
    """Draws a fixed range volume profile."""
    def __init__(self, pos, size, get_bars_cb, tick_size, **kwargs):
        super().__init__(pos, size, **kwargs)
        self.get_bars_cb = get_bars_cb
        self.tick_size = tick_size
        self.addScaleHandle([0, 0.5], [1, 0.5])
        self.addScaleHandle([1, 0.5], [0, 0.5])
        
        self.outline_pen = pg.mkPen('#444444', width=1, style=Qt.PenStyle.DashLine)
        self.bg_brush = QBrush(QColor(41, 98, 255, 20))
        self.bar_brush = QBrush(QColor(100, 181, 246, 120))
        self.poc_brush = QBrush(QColor(255, 23, 68, 200))
        self.poc_pen = pg.mkPen('#FF1744', width=2)
        
        self._vp_cache_key = None
        self._vp_cached_vol = {}

    def paint(self, p, opt, widget):
        p.setPen(self.outline_pen)
        p.setBrush(self.bg_brush)
        rect = self.boundingRect()
        p.drawRect(rect)
        
        # Map ROI bounds to scene coordinates to find actual chart bar indices
        scene_rect = self.mapRectToScene(rect)
        x_min, x_max = scene_rect.left(), scene_rect.right()
        
        range_key = (round(x_min, 1), round(x_max, 1))
        if self._vp_cache_key != range_key:
            self._vp_cache_key = range_key
            bars = self.get_bars_cb(x_min, x_max)
            vol_by_price = {}
            if bars:
                for b in bars:
                    for ti, (sell_v, buy_v) in b.cells.items():
                        p_lvl = ti * self.tick_size
                        vol_by_price[p_lvl] = vol_by_price.get(p_lvl, 0) + (sell_v + buy_v)
            self._vp_cached_vol = vol_by_price
            
        vol_by_price = self._vp_cached_vol
        if not vol_by_price: return
        
        max_vol = max(vol_by_price.values())
        if max_vol == 0: return

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.bar_brush)
        box_width = rect.width()
        
        poc_price = max(vol_by_price, key=vol_by_price.get)
        
        for p_lvl, vol in vol_by_price.items():
            bar_width = (vol / max_vol) * (box_width * 0.8)
            bar_rect = QRectF(rect.right() - bar_width, p_lvl - self.tick_size/2, bar_width, self.tick_size)
            if p_lvl == poc_price:
                p.setBrush(self.poc_brush)
                p.drawRect(bar_rect)
                p.setBrush(self.bar_brush)
                p.setPen(self.poc_pen)
                p.drawLine(QPointF(rect.left(), poc_price), QPointF(rect.right(), poc_price))
                p.setPen(Qt.PenStyle.NoPen)
            else:
                p.drawRect(bar_rect)
