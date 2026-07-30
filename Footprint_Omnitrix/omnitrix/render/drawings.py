import pyqtgraph as pg
from pyqtgraph.GraphicsScene.mouseEvents import MouseClickEvent, MouseDragEvent
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import QColor, QPen, QBrush, QPainter, QFont

FONT_LABEL = QFont("Arial", 9, QFont.Weight.Bold)

class BaseDrawingROI(pg.ROI):
    """Base ROI drawing class with right-click context menu signal."""
    sigRightClicked = pyqtSignal(object, object)

    def mouseClickEvent(self, ev):
        if ev.button() in (Qt.MouseButton.RightButton, 2):
            ev.accept()
            self.sigRightClicked.emit(self, ev)
        else:
            super().mouseClickEvent(ev)

    def raiseContextMenu(self, ev):
        ev.accept()
        self.sigRightClicked.emit(self, ev)

class FibRetracement(BaseDrawingROI):
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
        self.show_labels = True

    def get_style(self) -> dict:
        return {
            "line_color": self.colors[2].name().upper() if hasattr(self.colors[2], 'name') else "#26A69A",
            "line_width": self.pens[0].width(),
            "line_style": "Solid" if self.pens[0].style() == Qt.PenStyle.SolidLine else "Dashed",
            "fill_alpha": getattr(self, "fill_alpha", 30),
            "show_labels": getattr(self, "show_labels", True),
        }

    def apply_style(self, style: dict) -> None:
        if "line_color" in style:
            base_col = QColor(style["line_color"])
            width = int(style.get("line_width", 1))
            p_style = Qt.PenStyle.SolidLine if style.get("line_style") == "Solid" else Qt.PenStyle.DashLine
            self.colors = [
                QColor(120, 123, 134), QColor(244, 67, 54), base_col,
                QColor(0, 230, 118), base_col, QColor(156, 39, 176), QColor(120, 123, 134)
            ]
            self.pens = [pg.mkPen(col, width=width, style=p_style) for col in self.colors]
        if "fill_alpha" in style:
            self.fill_alpha = int(style["fill_alpha"])
        if "show_labels" in style:
            self.show_labels = bool(style["show_labels"])
        self.update()

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

class PositionDrawer(BaseDrawingROI):
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
        self.show_labels = True

    def get_style(self) -> dict:
        return {
            "target_color": self.tp_color.name().upper(),
            "stop_color": self.sl_color.name().upper(),
            "box_alpha": self.tp_color.alpha(),
            "line_width": self.entry_pen.width(),
            "show_labels": getattr(self, "show_labels", True),
        }

    def apply_style(self, style: dict) -> None:
        alpha = int(style.get("box_alpha", 50))
        if "target_color" in style:
            c = QColor(style["target_color"])
            c.setAlpha(alpha)
            self.tp_color = c
            self.tp_brush = QBrush(c)
        if "stop_color" in style:
            c = QColor(style["stop_color"])
            c.setAlpha(alpha)
            self.sl_color = c
            self.sl_brush = QBrush(c)
        if "line_width" in style:
            w = int(style["line_width"])
            self.entry_pen.setWidth(w)
        if "show_labels" in style:
            self.show_labels = bool(style["show_labels"])
        self.update()

    def _on_region_changed(self):
        eh_pos = self.entry_handle.pos()
        if eh_pos.x() != 0.5:
            self.entry_handle.setPos(QPointF(0.5, eh_pos.y()))
        self.entry_pct = self.entry_handle.pos().y()

    def paint(self, p, opt, widget):
        rect = self.boundingRect()
        entry_y = rect.bottom() + (rect.top() - rect.bottom()) * self.entry_pct
        
        top_y = rect.top() if self.is_long else rect.bottom()
        bot_y = rect.bottom() if self.is_long else rect.top()
        
        tp_rect = QRectF(rect.left(), entry_y, rect.width(), top_y - entry_y)
        sl_rect = QRectF(rect.left(), bot_y, rect.width(), entry_y - bot_y)

        win = widget.window() if widget else None
        t = getattr(win, "theme", None)
        is_light = t and getattr(t, "name", "dark") == "light"

        entry_pen = pg.mkPen('#101828' if is_light else '#FFFFFF', width=2)
        label_pen = pg.mkPen('#101828' if is_light else '#FFFFFF')

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.tp_brush)
        p.drawRect(tp_rect)
        
        p.setBrush(self.sl_brush)
        p.drawRect(sl_rect)
        
        p.setPen(entry_pen)
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
        p.setPen(label_pen)
        
        p.drawText(rr_pt + QPointF(-25, -6), f"R/R: {rr:.2f}")
        p.drawText(tp_pt + QPointF(-40, 16 if self.is_long else -6), f"TP: {tp_price_world:,.2f}")
        p.drawText(sl_pt + QPointF(-40, -6 if self.is_long else 16), f"SL: {sl_price_world:,.2f}")
        p.restore()

class FixedVolumeProfile(BaseDrawingROI):
    """Draws a fixed range volume profile with 70% Value Area, POC, VAH, and VAL on particular candles."""
    def __init__(self, pos, size, get_bars_cb, tick_size, **kwargs):
        super().__init__(pos, size, **kwargs)
        self.get_bars_cb = get_bars_cb
        self.tick_size = tick_size
        self.addScaleHandle([0, 0.5], [1, 0.5])
        self.addScaleHandle([1, 0.5], [0, 0.5])
        
        self.outline_pen = pg.mkPen('#444444', width=1, style=Qt.PenStyle.DashLine)
        self.bg_brush = QBrush(QColor(24, 26, 32, 120))
        self._va_color_hex = "#2962FF"
        self._poc_color_hex = "#FF1744"
        self._out_color_hex = "#707070"
        self.va_bar_brush = QBrush(QColor(41, 98, 255, 160))     # Value Area 70% volume - Vibrant Blue
        self.non_va_bar_brush = QBrush(QColor(120, 120, 120, 70)) # Outside Value Area volume - Muted Gray
        self.poc_brush = QBrush(QColor(255, 23, 68, 220))        # POC Bar - Vibrant Red
        self.poc_pen = pg.mkPen('#FF1744', width=2)
        self.va_pen = pg.mkPen('#FFC107', width=1, style=Qt.PenStyle.DashLine) # VAH / VAL lines - Gold
        self.show_labels = True
        
        self._vp_cache_key = None
        self._vp_cached_vol = {}
        self._vp_cached_va = (None, None, None, set()) # (poc_price, vah_price, val_price, va_prices)

    def get_style(self) -> dict:
        return {
            "va_color": getattr(self, "_va_color_hex", "#2962FF"),
            "poc_color": getattr(self, "_poc_color_hex", "#FF1744"),
            "out_color": getattr(self, "_out_color_hex", "#707070"),
            "line_width": self.poc_pen.width(),
            "show_labels": getattr(self, "show_labels", True),
        }

    def apply_style(self, style: dict) -> None:
        if "va_color" in style:
            self._va_color_hex = style["va_color"]
            c = QColor(style["va_color"])
            c.setAlpha(160)
            self.va_bar_brush = QBrush(c)
        if "poc_color" in style:
            self._poc_color_hex = style["poc_color"]
            c = QColor(style["poc_color"])
            c.setAlpha(220)
            self.poc_brush = QBrush(c)
            width = int(style.get("line_width", 2))
            self.poc_pen = pg.mkPen(c, width=width)
        if "out_color" in style:
            self._out_color_hex = style["out_color"]
            c = QColor(style["out_color"])
            c.setAlpha(70)
            self.non_va_bar_brush = QBrush(c)
        if "show_labels" in style:
            self.show_labels = bool(style["show_labels"])
        self.update()

    def paint(self, p, opt, widget):
        rect = self.boundingRect()

        win = widget.window() if widget else None
        t = getattr(win, "theme", None)
        is_light = t and getattr(t, "name", "dark") == "light"

        if self.isSelected():
            outline = pg.mkPen('#B7BDC7' if is_light else '#444444', width=1, style=Qt.PenStyle.DashLine)
            p.setPen(outline)
            bg = QBrush(QColor(0, 0, 0, 10) if is_light else QColor(255, 255, 255, 10))
            p.setBrush(bg)
            p.drawRect(rect)
        
        pos_x = self.pos().x()
        size_x = self.size().x()
        x_min = min(pos_x, pos_x + size_x)
        x_max = max(pos_x, pos_x + size_x)
        
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

            # Calculate 70% Value Area (VAH, VAL) and POC
            if vol_by_price:
                poc_price = max(vol_by_price, key=vol_by_price.get)
                total_vol = sum(vol_by_price.values())
                target_va_vol = total_vol * 0.70

                sorted_prices = sorted(vol_by_price.keys())
                poc_idx = sorted_prices.index(poc_price)
                
                va_prices = {poc_price}
                accum_vol = vol_by_price[poc_price]
                up_idx = poc_idx + 1
                dn_idx = poc_idx - 1
                
                while accum_vol < target_va_vol and (up_idx < len(sorted_prices) or dn_idx >= 0):
                    up_vol = vol_by_price[sorted_prices[up_idx]] if up_idx < len(sorted_prices) else -1
                    dn_vol = vol_by_price[sorted_prices[dn_idx]] if dn_idx >= 0 else -1
                    
                    if up_vol >= dn_vol and up_vol >= 0:
                        accum_vol += up_vol
                        va_prices.add(sorted_prices[up_idx])
                        up_idx += 1
                    elif dn_vol >= 0:
                        accum_vol += dn_vol
                        va_prices.add(sorted_prices[dn_idx])
                        dn_idx -= 1
                    else:
                        break
                        
                vah_price = max(va_prices)
                val_price = min(va_prices)
                self._vp_cached_va = (poc_price, vah_price, val_price, va_prices)
            else:
                self._vp_cached_va = (None, None, None, set())

        vol_by_price = self._vp_cached_vol
        if not vol_by_price: return
        
        max_vol = max(vol_by_price.values())
        if max_vol == 0: return

        poc_price, vah_price, val_price, va_prices = self._vp_cached_va
        
        box_width = rect.width()
        world_y = self.pos().y()
        
        if is_light:
            va_brush = QBrush(QColor(30, 136, 229, 180))       # Vivid Blue #1E88E5
            non_va_brush = QBrush(QColor(176, 190, 197, 120))  # Light Slate Gray #B0BEC5
            poc_brush_col = QBrush(QColor(229, 57, 53, 230))   # Crimson Red #E53935
            poc_pen_col = pg.mkPen('#E53935', width=2)
            va_pen_col = pg.mkPen('#E65100', width=1.5, style=Qt.PenStyle.DashLine) # Dark Amber / Gold
            lbl_poc_pen = pg.mkPen('#E53935')
            lbl_va_pen = pg.mkPen('#E65100')
        else:
            va_brush = self.va_bar_brush
            non_va_brush = self.non_va_bar_brush
            poc_brush_col = self.poc_brush
            poc_pen_col = self.poc_pen
            va_pen_col = self.va_pen
            lbl_poc_pen = pg.mkPen('#FF1744')
            lbl_va_pen = pg.mkPen('#FFC107')

        p.setPen(Qt.PenStyle.NoPen)
        
        for p_lvl, vol in vol_by_price.items():
            bar_width = (vol / max_vol) * (box_width * 0.8)
            local_y = p_lvl - world_y
            bar_rect = QRectF(rect.right() - bar_width, local_y - self.tick_size/2, bar_width, self.tick_size)
            
            if p_lvl == poc_price:
                p.setBrush(poc_brush_col)
                p.drawRect(bar_rect)
            elif p_lvl in va_prices:
                p.setBrush(va_brush)
                p.drawRect(bar_rect)
            else:
                p.setBrush(non_va_brush)
                p.drawRect(bar_rect)
                
        # Draw POC line across selected candles
        if poc_price is not None:
            poc_y = poc_price - world_y
            p.setPen(poc_pen_col)
            p.drawLine(QPointF(rect.left(), poc_y), QPointF(rect.right(), poc_y))

        # Draw VAH and VAL dashed lines across selected candles
        if vah_price is not None and val_price is not None:
            p.setPen(va_pen_col)
            vah_y = vah_price - world_y
            val_y = val_price - world_y
            p.drawLine(QPointF(rect.left(), vah_y), QPointF(rect.right(), vah_y))
            p.drawLine(QPointF(rect.left(), val_y), QPointF(rect.right(), val_y))

        # Draw text labels
        tr = p.transform()
        p.save()
        p.resetTransform()
        p.setFont(FONT_LABEL)
        
        if poc_price is not None:
            pt = tr.map(QPointF(rect.right(), poc_price - world_y))
            p.setPen(lbl_poc_pen)
            p.drawText(pt + QPointF(6, 4), f"POC: {poc_price:,.2f}")
            
        if vah_price is not None:
            pt = tr.map(QPointF(rect.right(), vah_price - world_y))
            p.setPen(lbl_va_pen)
            p.drawText(pt + QPointF(6, -4), f"VAH: {vah_price:,.2f}")
            
        if val_price is not None:
            pt = tr.map(QPointF(rect.right(), val_price - world_y))
            p.setPen(lbl_va_pen)
            p.drawText(pt + QPointF(6, 14), f"VAL: {val_price:,.2f}")
            
        p.restore()


class RangeCPR(BaseDrawingROI):
    """Central Pivot Range (P, TC, BC, R1, S1) drawing tool for particular selected candles."""
    def __init__(self, pos, size, get_bars_cb, tick_size, **kwargs):
        super().__init__(pos, size, **kwargs)
        self.get_bars_cb = get_bars_cb
        self.tick_size = tick_size
        self.addScaleHandle([0, 0.5], [1, 0.5])
        self.addScaleHandle([1, 0.5], [0, 0.5])
        
        self._p_color_hex = "#FF4081"
        self._tc_bc_color_hex = "#00BCD4"
        self._r_color_hex = "#00E676"
        self._s_color_hex = "#FF1744"
        self.p_pen = pg.mkPen('#FF4081', width=2)                       # Main Pivot - Pink
        self.tc_pen = pg.mkPen('#00BCD4', width=1, style=Qt.PenStyle.DashLine) # Top Central - Cyan
        self.bc_pen = pg.mkPen('#00BCD4', width=1, style=Qt.PenStyle.DashLine) # Bottom Central - Cyan
        self.r1_pen = pg.mkPen('#00E676', width=1, style=Qt.PenStyle.DotLine)  # Resistance 1 - Green
        self.s1_pen = pg.mkPen('#FF1744', width=1, style=Qt.PenStyle.DotLine)  # Support 1 - Red
        self.outline_pen = pg.mkPen('#444444', width=1, style=Qt.PenStyle.DashLine)
        self.show_labels = True

    def get_style(self) -> dict:
        return {
            "p_color": getattr(self, "_p_color_hex", "#FF4081"),
            "tc_bc_color": getattr(self, "_tc_bc_color_hex", "#00BCD4"),
            "r_color": getattr(self, "_r_color_hex", "#00E676"),
            "s_color": getattr(self, "_s_color_hex", "#FF1744"),
            "line_width": self.p_pen.width(),
            "show_labels": getattr(self, "show_labels", True),
        }

    def apply_style(self, style: dict) -> None:
        w = int(style.get("line_width", 1))
        if "p_color" in style:
            self._p_color_hex = style["p_color"]
            self.p_pen = pg.mkPen(style["p_color"], width=max(2, w))
        if "tc_bc_color" in style:
            self._tc_bc_color_hex = style["tc_bc_color"]
            self.tc_pen = pg.mkPen(style["tc_bc_color"], width=w, style=Qt.PenStyle.DashLine)
            self.bc_pen = pg.mkPen(style["tc_bc_color"], width=w, style=Qt.PenStyle.DashLine)
        if "r_color" in style:
            self._r_color_hex = style["r_color"]
            self.r1_pen = pg.mkPen(style["r_color"], width=w, style=Qt.PenStyle.DotLine)
        if "s_color" in style:
            self._s_color_hex = style["s_color"]
            self.s1_pen = pg.mkPen(style["s_color"], width=w, style=Qt.PenStyle.DotLine)
        if "show_labels" in style:
            self.show_labels = bool(style["show_labels"])
        self.update()
        
    def paint(self, p, opt, widget):
        if self.isSelected():
            rect = self.boundingRect()
            p.setPen(self.outline_pen)
            p.setBrush(QBrush(QColor(255, 255, 255, 5)))
            p.drawRect(rect)
        
        pos_x = self.pos().x()
        size_x = self.size().x()
        x_min = min(pos_x, pos_x + size_x)
        x_max = max(pos_x, pos_x + size_x)
        
        cache_key = (round(x_min, 2), round(x_max, 2))
        if getattr(self, '_cache_key', None) != cache_key or not hasattr(self, '_cached_cpr_levels'):
            bars = self.get_bars_cb(x_min, x_max)
            if not bars:
                self._cached_cpr_levels = None
                return
            high = max(b.high for b in bars)
            low = min(b.low for b in bars)
            close = bars[-1].close
            
            pivot = (high + low + close) / 3.0
            bc_calc = (high + low) / 2.0
            tc_calc = (pivot - bc_calc) + pivot
            tc = max(tc_calc, bc_calc)
            bc = min(tc_calc, bc_calc)
                
            r1 = (2 * pivot) - low
            s1 = (2 * pivot) - high
            self._cached_cpr_levels = (pivot, tc, bc, r1, s1)
            self._cache_key = cache_key
            
        cpr_data = getattr(self, '_cached_cpr_levels', None)
        if not cpr_data:
            return
        pivot, tc, bc, r1, s1 = cpr_data

        world_y = self.pos().y()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        win = widget.window() if widget else None
        t = getattr(win, "theme", None)
        is_light = t and getattr(t, "name", "dark") == "light"
        
        if is_light:
            col_p = QColor('#D81B60')     # Deep Magenta
            col_tc = QColor('#00838F')    # Deep Cyan / Teal
            col_r1 = QColor('#2E7D32')    # Forest Green
            col_s1 = QColor('#C62828')    # Crimson Red
        else:
            col_p = QColor(getattr(self, "_p_color_hex", "#FF4081"))
            col_tc = QColor(getattr(self, "_tc_bc_color_hex", "#00BCD4"))
            col_r1 = QColor(getattr(self, "_r_color_hex", "#00E676"))
            col_s1 = QColor(getattr(self, "_s_color_hex", "#FF1744"))

        p_pen = pg.mkPen(col_p, width=2, style=Qt.PenStyle.SolidLine)
        tc_pen = pg.mkPen(col_tc, width=1.5, style=Qt.PenStyle.DotLine)
        bc_pen = pg.mkPen(col_tc, width=1.5, style=Qt.PenStyle.DotLine)
        r1_pen = pg.mkPen(col_r1, width=1, style=Qt.PenStyle.DashLine)
        s1_pen = pg.mkPen(col_s1, width=1, style=Qt.PenStyle.DashLine)
        
        lines = [
            (pivot, p_pen, "P", col_p),
            (tc, tc_pen, "TC", col_tc),
            (bc, bc_pen, "BC", col_tc),
            (r1, r1_pen, "R1", col_r1),
            (s1, s1_pen, "S1", col_s1),
        ]
        
        tr = p.transform()
        rect = self.boundingRect()
        
        for price_val, pen, label, col_q in lines:
            local_y = price_val - world_y
            p.setPen(pen)
            p.drawLine(QPointF(rect.left(), local_y), QPointF(rect.right(), local_y))
            
            screen_pt = tr.map(QPointF(rect.right(), local_y))
            p.save()
            p.resetTransform()
            p.setPen(pg.mkPen(col_q))
            p.setFont(FONT_LABEL)
            p.drawText(screen_pt + QPointF(6, 4), f"{label}: {price_val:,.2f}")
            p.restore()
