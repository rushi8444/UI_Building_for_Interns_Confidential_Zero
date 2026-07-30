"""The footprint / cluster GraphicsObject.

Consumes engine `Bar` objects directly and leans on their *cached* analytics
(POC, value area) so a frame's cost is drawing, not recomputation. Only the
bars inside the current viewport are drawn.

x axis  = bar index (0..n-1)
y axis  = price
Each bar draws a thin candlestick on the left, then a two-column volume block
(sell | buy) per traded price level.
"""

from __future__ import annotations

import pyqtgraph as pg
from PyQt6.QtCore import QRectF, QPointF, Qt
from PyQt6.QtGui import QFont, QColor, QPainter, QBrush

from .theme import Theme, DARK


class FootprintItem(pg.GraphicsObject):
    BOX_W = 0.66                      # column block width in x-units
    CANDLE_GAP = 0.06                 # gap between candle and block

    def __init__(self, tick: float, theme: Theme = DARK):
        super().__init__()
        self.bars: list = []
        self.tick = tick
        self.theme = theme
        self.mode = "Footprint"       # Footprint | Cluster | Profile | Delta
        self.show_imbalance = True
        self.show_va = True
        self.show_candles = True
        self.draw_cells = True        # False = candles only (heatmap-only view)
        self.imbalance_factor = 3.0
        self.min_imbalance_vol = 20
        self.stacked_min = 3
        self.va_pct = 0.70
        self.min_cluster_text_vol = 500   # Volume threshold for displaying cell text (500 shares / 0.5K)
        self.min_delta_text_vol = 1000    # Threshold for displaying delta text (|Delta| >= 1.0K / 1000 shares)
        self.font = QFont("Consolas", 8, QFont.Weight.Bold)
        self._bounds = QRectF()

    # ---- external setters ------------------------------------------------
    def set_bars(self, bars: list) -> None:
        self.bars = bars
        self._recompute_bounds()
        self.update()

    def set_theme(self, theme: Theme) -> None:
        self.theme = theme
        self.update()

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.update()

    def set_show_imbalance(self, on: bool) -> None:
        self.show_imbalance = on
        self.update()

    def set_show_va(self, on: bool) -> None:
        self.show_va = on
        self.update()

    def set_imbalance_factor(self, f: float) -> None:
        self.imbalance_factor = f
        self.update()

    def set_draw_cells(self, on: bool) -> None:
        self.draw_cells = on
        self.update()

    def set_show_candles(self, on: bool) -> None:
        self.show_candles = on
        self.update()

    def configure(self, **kw) -> None:
        """Bulk-set customization attributes from a settings dict."""
        for k, v in kw.items():
            if hasattr(self, k):
                setattr(self, k, v)
        self.update()

    # ---- geometry --------------------------------------------------------
    def _recompute_bounds(self) -> None:
        # Must precede any boundingRect() change or Qt culls against the stale
        # rect and the item flickers.
        self.prepareGeometryChange()
        if not self.bars:
            self._bounds = QRectF()
            return
        lo = min(b.low for b in self.bars)
        hi = max(b.high for b in self.bars)
        # Extra bottom padding margin so footer summary pills sit cleanly below lowest candle wicks
        self._bounds = QRectF(-1, lo - (3.0 * self.tick), len(self.bars) + 2, (hi - lo) + (4.5 * self.tick))

    def boundingRect(self) -> QRectF:
        return self._bounds

    # ---- painting --------------------------------------------------------
    def paint(self, p: QPainter, *args) -> None:
        if not self.bars:
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        t = self.theme
        tick = self.tick
        half = self.BOX_W / 2

        vb = self.getViewBox()
        if vb is None:
            return
        px_w, px_h = vb.viewPixelSize()
        px_w_abs = abs(px_w) if px_w != 0 else 0.001
        px_h_abs = abs(px_h) if px_h != 0 else 0.001

        box_px = self.BOX_W / px_w_abs
        tick_px = tick / px_h_abs

        # Level-of-Detail (LOD) Thresholds:
        show_text = (box_px >= 45.0) and (tick_px >= 4.0)
        show_cells = show_text
        show_footer = (box_px >= 35.0) and (tick_px >= 3.0)

        xr = vb.viewRange()[0]
        x_lo = max(0, int(xr[0]) - 1)
        x_hi = min(len(self.bars), int(xr[1]) + 2)

        c_bull = QColor(t.bull)
        c_bear = QColor(t.bear)

        for x in range(x_lo, x_hi):
            bar = self.bars[x]
            cc = c_bull if bar.is_bull else c_bear
            if self.show_candles:
                self._paint_candle(p, x, bar, cc, half, tick)
            if self.draw_cells and bar.cells and show_cells:
                self._paint_block(p, x, bar, half, tick, show_text, show_footer, tick_px)

    def _paint_candle(self, p, x, bar, color, half, tick) -> None:
        cx = x - half - self.CANDLE_GAP
        top = max(bar.open, bar.close)
        bot = min(bar.open, bar.close)
        if top == bot:
            top += tick / 8

        if not self.draw_cells:
            # Heatmap mode view: render hollow lightweight wicks and thin open-close outline
            # so the limit order book heatmap background remains 100% visible underneath
            p.setPen(pg.mkPen(color, width=1))
            p.drawLine(QPointF(cx, bar.low), QPointF(cx, bar.high))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(cx - 0.06, bot, 0.12, top - bot))
        else:
            p.setPen(pg.mkPen(color, width=2))
            p.drawLine(QPointF(cx, bar.low), QPointF(cx, bar.high))
            p.setPen(pg.mkPen(color, width=1))
            p.setBrush(pg.mkBrush(color))
            p.drawRect(QRectF(cx - 0.09, bot, 0.18, top - bot))

    def _paint_block(self, p, x, bar, half, tick, show_text, show_footer, tick_px=8.0) -> None:
        t = self.theme
        cells = bar.cells
        poc = bar.poc
        vah, val = bar.value_area(self.va_pct)
        mode = self.mode

        font_sz = max(7, min(9, int(abs(tick_px) * 0.75)))
        cell_font = QFont("Consolas", font_sz, QFont.Weight.Bold)

        buy_imb, sell_imb = (
            bar.imbalances(self.imbalance_factor, self.min_imbalance_vol)
            if self.show_imbalance and mode == "Footprint" else (set(), set())
        )

        # value-area wash + VAH/VAL guides
        if self.show_va and vah is not None:
            y_lo = val * tick - tick / 2
            y_hi = vah * tick + tick / 2
            p.fillRect(QRectF(x - half, y_lo, self.BOX_W, y_hi - y_lo), t.va_wash)
            p.setPen(pg.mkPen(t.va_line, width=1, style=Qt.PenStyle.DashLine))
            for edge in (y_hi, y_lo):
                p.drawLine(QPointF(x - half, edge), QPointF(x + half, edge))

        # scaling references for Profile / Delta modes
        max_tot = max((s + b for s, b in cells.values()), default=1) or 1
        max_abs_d = max((abs(b - s) for s, b in cells.values()), default=1) or 1

        if mode == "Profile":
            # Candle Backbone / Wick Line down center axis (x) behind profile bars
            p.setPen(pg.mkPen(QColor(255, 255, 255, 45), width=1, style=Qt.PenStyle.DashLine))
            p.drawLine(QPointF(x, bar.low), QPointF(x, bar.high))

        tr = p.transform()
        for ti, (sell_v, buy_v) in cells.items():
            tot = sell_v + buy_v
            if tot == 0:
                continue
            y = ti * tick - tick / 2
            is_poc = ti == poc

            if mode == "Footprint":
                c_sell = QColor(t.poc_bg) if is_poc else QColor(t.bid_bg)
                c_buy = QColor(t.poc_bg) if is_poc else QColor(t.ask_bg)
                if ti in sell_imb:
                    c_sell = t.sell_imb
                if ti in buy_imb:
                    c_buy = t.buy_imb
                p.fillRect(QRectF(x - half, y, half, tick), c_sell)
                p.fillRect(QRectF(x, y, half, tick), c_buy)
                if show_text:
                    self._cell_two(p, tr, x, y, tick, half, sell_v, buy_v,
                                   t.poc_text if is_poc else t.cell_text, font=cell_font)

            elif mode == "Cluster":
                if show_text:
                    d = buy_v - sell_v
                    if is_poc:
                        bg = QColor(255, 193, 7, 140)       # Amber gold POC highlight
                    elif d >= 0:
                        bg = QColor(40, 180, 120, 90)       # Sage/Teal green (~35% opacity)
                    else:
                        bg = QColor(220, 70, 80, 90)        # Muted coral/crimson red (~35% opacity)
                    p.fillRect(QRectF(x - half, y, self.BOX_W, tick), bg)
                    if tot >= getattr(self, "min_cluster_text_vol", 500):
                        self._cell_one(p, tr, x, y, tick, half, _fmt(tot),
                                       t.poc_text if is_poc else t.cell_text, font=cell_font)

            elif mode == "Profile":
                if show_text:
                    w = self.BOX_W * (tot / max_tot)
                    col = QColor(255, 193, 7) if is_poc else (QColor(t.bull) if buy_v >= sell_v else QColor(t.bear))
                    p.fillRect(QRectF(x - half, y, w, tick), col)
                    if is_poc:
                        # Distinct amber/gold outline border around Point of Control (POC) bar
                        p.setPen(pg.mkPen(QColor(255, 215, 0), width=1))
                        p.drawRect(QRectF(x - half, y, w, tick))
                    self._cell_one(p, tr, x, y, tick, half, _fmt(tot),
                                   t.poc_text if is_poc else t.cell_text,
                                   align_left=True, font=cell_font)

            elif mode == "Delta":
                if show_text:
                    d = buy_v - sell_v
                    inten = min(1.0, (abs(d) / max_abs_d) ** 0.75) if max_abs_d > 0 else 0.0
                    base = QColor(255, 193, 7) if is_poc else (QColor(t.bull) if d >= 0 else QColor(t.bear))
                    col = QColor(base.red(), base.green(), base.blue(), int(40 + 195 * inten))
                    p.fillRect(QRectF(x - half, y, self.BOX_W, tick), col)
                    if is_poc:
                        p.setPen(pg.mkPen(QColor(255, 215, 0, 180), width=1))
                        p.drawRect(QRectF(x - half, y, self.BOX_W, tick))
                    if abs(d) >= getattr(self, "min_delta_text_vol", 500):
                        self._cell_one(p, tr, x, y, tick, half,
                                       f"{'+' if d > 0 else ''}{_fmt(d)}",
                                       t.poc_text if is_poc else t.cell_text, font=cell_font)

        if self.show_imbalance and mode == "Footprint":
            self._paint_stacks(p, x, tick, half, sorted(buy_imb), sorted(sell_imb))

        if show_footer:
            self._paint_footer(p, tr, x, bar, half)

    def _cell_two(self, p, tr, x, y, tick, half, sell_v, buy_v, color, font=None) -> None:
        p.save()
        p.resetTransform()
        p.setFont(font or self.font)
        p.setPen(pg.mkPen(color))
        rb = tr.mapRect(QRectF(x - half, y, half - 0.05, tick))
        ra = tr.mapRect(QRectF(x + 0.05, y, half - 0.05, tick))
        align_r = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight | Qt.TextFlag.TextDontClip
        align_l = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextDontClip
        p.drawText(rb, align_r, _fmt(sell_v))
        p.drawText(ra, align_l, _fmt(buy_v))
        p.restore()

    def _cell_one(self, p, tr, x, y, tick, half, text, color, align_left=False, font=None) -> None:
        r = tr.mapRect(QRectF(x - half + 0.03, y, self.BOX_W - 0.06, tick))
        row_h = abs(r.height())
        if row_h < 7.0:
            return  # skip text if row height is too narrow to prevent overlap
        p.save()
        p.resetTransform()
        f = QFont(font or self.font)
        if row_h < 13.0:
            f.setPointSize(max(6, int(row_h - 4)))
        p.setFont(f)
        p.setPen(pg.mkPen(color))
        align = (Qt.AlignmentFlag.AlignVCenter |
                 (Qt.AlignmentFlag.AlignLeft if align_left else Qt.AlignmentFlag.AlignHCenter))
        p.drawText(r, align, text)
        p.restore()

    def _paint_stacks(self, p, x, tick, half, buy_sorted, sell_sorted) -> None:
        p.setBrush(Qt.BrushStyle.NoBrush)
        for a, b in _runs(buy_sorted, self.stacked_min):
            p.setPen(pg.mkPen(self.theme.buy_imb, width=2))
            p.drawRect(QRectF(x, a * tick - tick / 2, half, (b - a) * tick + tick))
        for a, b in _runs(sell_sorted, self.stacked_min):
            p.setPen(pg.mkPen(self.theme.sell_imb, width=2))
            p.drawRect(QRectF(x - half, a * tick - tick / 2, half, (b - a) * tick + tick))

    def _paint_footer(self, p, tr, x, bar, half) -> None:
        t = self.theme
        vb = self.getViewBox()
        if vb is not None:
            yr = vb.viewRange()[1]
            y_bottom = yr[0]  # fixed footer bar aligned above bottom time axis
        else:
            y_bottom = bar.low

        pt_screen = tr.map(QPointF(x, y_bottom))
        pt_left = tr.map(QPointF(x - half, y_bottom))
        pt_right = tr.map(QPointF(x + half, y_bottom))
        w_screen = abs(pt_right.x() - pt_left.x())
        
        # Wide enough screen box (min 80px) centered at candle, unclipped
        w_box = max(w_screen, 80.0)
        r = QRectF(pt_screen.x() - w_box / 2, pt_screen.y() - 36, w_box, 32)
        
        p.save()
        p.resetTransform()
        if t.name == "light":
            card_bg = QColor(245, 247, 250, 240)
            card_border = QColor(200, 205, 215, 230)
        else:
            card_bg = QColor(10, 17, 40, 235)
            card_border = QColor(30, 44, 79, 200)

        p.setBrush(QBrush(card_bg))
        p.setPen(pg.mkPen(card_border, width=1))
        p.drawRoundedRect(r, 4.0, 4.0)

        p.setFont(self.font)
        d = bar.delta
        p.setPen(pg.mkPen(t.delta_up if d >= 0 else t.delta_dn))
        align = Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextDontClip
        p.drawText(r.adjusted(0, 2, 0, 0), align, f"Δ {'+' if d > 0 else ''}{_fmt(d)}")
        p.setPen(pg.mkPen(t.cell_text))
        p.drawText(r.adjusted(0, 16, 0, 0), align, _fmt(bar.volume))
        p.restore()


def _fmt(v: int) -> str:
    a = abs(v)
    if a >= 1_000_000:
        return f"{v/1_000_000:.2f}M"
    if a >= 1000:
        return f"{v/1000:.1f}K"
    return str(v)


def _runs(sorted_idxs, min_len):
    """Group sorted ints into consecutive runs of length >= min_len."""
    out = []
    if not sorted_idxs:
        return out
    start = prev = sorted_idxs[0]
    for v in sorted_idxs[1:]:
        if v == prev + 1:
            prev = v
        else:
            if prev - start + 1 >= min_len:
                out.append((start, prev))
            start = prev = v
    if prev - start + 1 >= min_len:
        out.append((start, prev))
    return out
