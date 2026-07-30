"""Bookmap render items, driven by a `BookmapBuffer`:

    BookHeatmapItem  — resting-liquidity field (time × price), auto-normalised.
    BBOItem          — stepped best-bid (blue) / best-ask (red) lines.
    BubbleItem       — trade bubbles, radius ∝ √size, red=sell / pale=buy.
    DomLadderItem    — right-edge depth histogram of the latest book + numbers.
    VolumeBarsItem   — bottom per-column executed-volume bars + numbers.

x = absolute column bucket (from the buffer), y = price.
"""

from __future__ import annotations

import math
import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QRectF, QPointF, Qt
from PyQt6.QtGui import (QColor, QPainter, QFont, QPen, QBrush, QRadialGradient,
                         QImage)

# Trades read as pale-steel (buy) vs red (sell) spheres: a saturated blue buy
# competes with the blue liquidity field behind it, while pale steel floats
# clear of it at every heat level.
BUY_BUBBLE = QColor(0, 230, 118)      # emerald green (buys)
SELL_BUBBLE = QColor(255, 42, 42)     # bright red (sells)
BID_LINE = QColor(0, 212, 255)        # electric cyan
ASK_LINE = QColor(255, 145, 0)        # amber/orange

BOOKMAP_BG = "#0A1128"


def _build_bookmap_lut() -> list[QColor]:
    # 9-stop high-contrast Bookmap color ramp (navy -> blue -> cyan -> yellow -> orange -> red)
    stops = [
        (0.00, (8, 14, 26)),       # Navy background
        (0.15, (10, 32, 58)),      # Deep blue
        (0.32, (13, 58, 99)),      # Ocean blue
        (0.48, (17, 92, 150)),     # Slate teal
        (0.62, (25, 140, 180)),    # Bright cyan/teal
        (0.74, (60, 190, 150)),    # Mint green
        (0.82, (245, 230, 66)),    # Electric yellow
        (0.90, (242, 140, 30)),    # Saturated orange
        (1.00, (232, 64, 42)),     # Crimson red limit wall
    ]
    lut: list[QColor] = []
    for i in range(256):
        t = i / 255.0
        for j in range(len(stops) - 1):
            t0, c0 = stops[j]
            t1, c1 = stops[j + 1]
            if t0 <= t <= t1:
                f = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
                lut.append(QColor(
                    int(c0[0] + (c1[0] - c0[0]) * f),
                    int(c0[1] + (c1[1] - c0[1]) * f),
                    int(c0[2] + (c1[2] - c0[2]) * f)))
                break
    return lut


_LUT = _build_bookmap_lut()

# Same ramp packed as opaque 0xAARRGGBB, for compositing the field as an image.
_LUT_ARGB = np.array(
    [(0xFF000000 | (c.red() << 16) | (c.green() << 8) | c.blue()) for c in _LUT],
    dtype=np.uint32)


_pb_memo: tuple = (None, None)


def _price_bounds(cols, tick):
    # A refresh hands the *same* column list to every item, so without a memo
    # this full-buffer scan runs once per item per frame.
    global _pb_memo
    last = cols[-1]
    key = (id(cols), len(cols), cols[0].bucket, last.bucket, id(last.book), tick)
    if _pb_memo[0] == key:
        return _pb_memo[1]

    # Hot path: runs for every item on every refresh over the whole buffer.
    # min()/max() on the dict is a C-level scan instead of a Python loop, and
    # consecutive columns share one forward-filled book object, so an identity
    # check skips the repeats without changing the result.
    lo = hi = None
    seen = None
    for c in cols:
        bk = c.book
        if not bk or bk is seen:
            continue
        seen = bk
        a = min(bk)
        b = max(bk)
        if lo is None:
            lo, hi = a, b
        else:
            if a < lo:
                lo = a
            if b > hi:
                hi = b
    if lo is None:
        rect = QRectF()
    else:
        x0 = cols[0].bucket
        x1 = cols[-1].bucket
        rect = QRectF(x0 - 1, lo * tick, (x1 - x0) + 3, (hi - lo) * tick + tick)
    _pb_memo = (key, rect)
    return rect


class _BufItem(pg.GraphicsObject):
    """Base: holds a column list + tick and a cached bounding rect."""

    def __init__(self, tick: float):
        super().__init__()
        self.cols: list = []
        self.tick = tick
        self._bounds = QRectF()

    def set_cols(self, cols: list) -> None:
        # Qt caches boundingRect() in the scene index. Changing it without
        # prepareGeometryChange() leaves the stale rect in place, so the item
        # gets culled at random - which is exactly the "bubbles/pies flicker in
        # and out while the heatmap stays" symptom.
        self.prepareGeometryChange()
        self.cols = cols
        self._bounds = _price_bounds(cols, self.tick) if cols else QRectF()
        self.update()

    def boundingRect(self) -> QRectF:
        return self._bounds

    def _xrange(self):
        vb = self.getViewBox()
        if vb is None or not self.cols:
            return 0, 0
        xr = vb.viewRange()[0]
        return xr[0] - 1, xr[1] + 1


class BookHeatmapItem(_BufItem):
    """The resting-liquidity field, composited as a single image.

    Every column carries a full forward-filled ladder, so a per-cell fillRect
    means tens of thousands of Qt calls per frame (measured: ~100 ms at normal
    zoom, ~800 ms zoomed out to full history). Building one ARGB buffer with
    numpy and blitting it once is the same picture for a fraction of the cost,
    and it is how a real depth heatmap is drawn.
    """

    MAX_ROWS = 6000        # guard: pathological y-zoom must not allocate wildly

    def __init__(self, tick: float):
        super().__init__(tick)
        self.alpha = 255
        self._buf = None   # kept alive: QImage wraps this memory, never copies
        self.setZValue(-20)

    def paint(self, p: QPainter, *args) -> None:
        if not self.cols:
            return
        vb = self.getViewBox()
        if vb is None:
            return
        tick = self.tick
        x_lo, x_hi = self._xrange()

        vis = [c for c in self.cols if x_lo <= c.bucket <= x_hi and c.book]
        if not vis:
            return

        # rows span only the visible price window
        yr = vb.viewRange()[1]
        ti_lo = int(math.floor(yr[0] / tick)) - 1
        ti_hi = int(math.ceil(yr[1] / tick)) + 1
        nrows = ti_hi - ti_lo + 1
        if nrows <= 0 or nrows > self.MAX_ROWS:
            return
        b0, b1 = vis[0].bucket, vis[-1].bucket
        ncols = b1 - b0 + 1
        if ncols <= 0:
            return

        # Dynamic percentile min-max logarithmic scale over non-zero depth cells:
        # percentile [20, 88] provides clear contrast without oversaturation
        all_vs = []
        for c in vis:
            if c.book:
                all_vs.extend([v for v in c.book.values() if v > 0])

        if all_vs:
            logs = np.log1p(all_vs)
            positive_logs = logs[logs > 0]
            if len(positive_logs) > 10:
                p_low, p_high = np.percentile(positive_logs, [5, 96])
            elif len(positive_logs) > 0:
                p_low, p_high = positive_logs.min(), positive_logs.max()
            else:
                p_low, p_high = 0.0, 1.0
            span = max(0.8, float(p_high - p_low)) 
            p_low = float(p_low)
        else:
            p_low, span = 0.0, 1.0

        buf = np.zeros((nrows, ncols), dtype=np.uint32)   # 0 = transparent
        for c in vis:
            bk = c.book
            n = len(bk)
            if not n:
                continue
            ks = np.fromiter(bk.keys(), dtype=np.int64, count=n) - ti_lo
            vs = np.fromiter(bk.values(), dtype=np.float64, count=n)
            m = (ks >= 0) & (ks < nrows) & (vs > 0)
            if not m.any():
                continue
            norm_v = np.clip((np.log1p(vs[m]) - p_low) / span, 0.0, 1.0)
            idx = (norm_v * 255.0).astype(np.int32)
            buf[ks[m], c.bucket - b0] = _LUT_ARGB[idx]

        self._buf = buf                    # QImage does not own the buffer
        img = QImage(buf.data, ncols, nrows, ncols * 4,
                     QImage.Format.Format_ARGB32)
        if self.alpha < 255:
            p.setOpacity(self.alpha / 255.0)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        # Smooth bilinear anti-aliasing transform for continuous terrain rendering
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        # Row 0 maps to the rect's top edge, i.e. the *lowest* price
        p.drawImage(QRectF(b0, ti_lo * tick - tick / 2, ncols, nrows * tick), img)
        if self.alpha < 255:
            p.setOpacity(1.0)


class BBOItem(_BufItem):
    def __init__(self, tick: float):
        super().__init__(tick)
        self.setZValue(-5)

    def paint(self, p: QPainter, *args) -> None:
        if not self.cols:
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        tick = self.tick
        x_lo, x_hi = self._xrange()
        # Width 2: the bid/ask pair has to read as a spread *channel* over a
        # bright heatmap, and a hairline disappears against white/amber walls.
        for side, color in (("bid_ti", BID_LINE), ("ask_ti", ASK_LINE)):
            p.setPen(pg.mkPen(color, width=2))
            prev = None
            for c in self.cols:
                if not (x_lo <= c.bucket <= x_hi):
                    prev = None
                    continue
                ti = getattr(c, side)
                if ti is None:
                    prev = None
                    continue
                y = ti * tick
                x = c.bucket
                if prev is not None:
                    py, px = prev
                    p.drawLine(QPointF(px, py), QPointF(x, py))   # horizontal hold
                    p.drawLine(QPointF(x, py), QPointF(x, y))     # vertical step
                p.drawLine(QPointF(x, y), QPointF(x + 1, y))
                prev = (y, x + 1)


# Columns of tolerance for out-of-order prints when scanning the tape backwards.
_TRADE_SCAN_SLACK = 8.0


class BubbleItem(_BufItem):
    def __init__(self, tick: float, buffer=None):
        super().__init__(tick)
        self.buffer = buffer
        self.xscale = 1.0            # 1/agg — aligns bubbles with aggregated columns
        self.min_r = 3.0
        self.max_r = 26.0
        self.min_size = 0           # hide clustered prints below this (noise filter)
        self.cluster_bins = 3.0     # time bins per display column for clustering
        self.max_bubbles = 320      # cap on bubbles drawn per frame (see paint)
        self.setZValue(0)

    def paint(self, p: QPainter, *args) -> None:
        if self.buffer is None:
            return
        trades = self.buffer.trades
        if not trades:
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        tick = self.tick
        xs = self.xscale
        x_lo, x_hi = self._xrange()

        # ---- cluster prints into (time-bin, price) cells (Bookmap volume-dots
        # clustering): consolidates the swarm of tiny circles into meaningful
        # bubbles, then a min-size threshold removes the rest of the noise. ----
        cb = self.cluster_bins
        cells: dict[tuple, list] = {}     # (xbin, ti) -> [buy, sell]
        # Scan newest-first and stop once we are past the left edge: the tape
        # holds up to 60k prints and walking all of them every frame dominated
        # the frame time. The slack lets a print that arrived slightly out of
        # order still be found before the scan gives up.
        for x, ti, size, aggr in reversed(trades):
            xd = x * xs
            if xd < x_lo - _TRADE_SCAN_SLACK:
                break
            if xd > x_hi:
                continue
            key = (round(xd * cb), ti)
            e = cells.get(key)
            if e is None:
                e = cells[key] = [0, 0]
            if aggr.value == "sell":
                e[1] += size
            else:
                e[0] += size
        if not cells:
            return

        agg = [(xb / cb, ti, b, s, b + s) for (xb, ti), (b, s) in cells.items()
               if (b + s) >= self.min_size]
        if not agg:
            return

        # draw largest last so big prints sit on top
        agg.sort(key=lambda t: t[4])
        if len(agg) > self.max_bubbles:
            agg = agg[-self.max_bubbles:]
        smax = agg[-1][4] or 1

        tr = p.transform()
        p.resetTransform()
        for xd, ti, buy_v, sell_v, total in agg:
            pt = tr.map(QPointF(xd, ti * tick))
            r = self.min_r + (self.max_r - self.min_r) * math.sqrt(total / smax)
            buy_pct = buy_v / total if total > 0 else 0.5
            self._pie_bubble(p, pt, r, buy_pct)

    @staticmethod
    def _pie_bubble(p: QPainter, pt: QPointF, r: float, buy_pct: float) -> None:
        rect = QRectF(pt.x() - r, pt.y() - r, 2 * r, 2 * r)
        buy_span = int(round(360 * 16 * buy_pct))
        sell_span = 360 * 16 - buy_span

        # Green buy wedge (from 12 o'clock CCW)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(BUY_BUBBLE))
        p.drawPie(rect, 90 * 16, buy_span)

        # Red sell wedge
        p.setBrush(QBrush(SELL_BUBBLE))
        p.drawPie(rect, 90 * 16 + buy_span, sell_span)

        # Crisp stroke and vibrant outer ring highlights matching main.py demo
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(140, 255, 170, 220), 1.2))
        p.drawArc(rect, 90 * 16, buy_span)
        p.setPen(QPen(QColor(255, 150, 140, 220), 1.2))
        p.drawArc(rect, 90 * 16 + buy_span, sell_span)
        p.setPen(QPen(QColor(17, 17, 17, 240), 1.0))
        p.drawEllipse(pt, r, r)


PIE_BUY = QColor(0, 230, 118)       # vivid emerald green (aggressive buys)
PIE_SELL = QColor(255, 42, 42)      # bright red (aggressive sells)
SUPPORT_GREEN = QColor(40, 210, 122)
RESIST_RED = QColor(244, 74, 86)
# Darker, heavier tones for the absolute S/R levels: these are structural marks
# that must stay legible across the whole pane without competing with the trade
# bubbles for attention the way the bright projection bands do.
SR_SUPPORT = QColor(18, 102, 56)
SR_RESIST = QColor(138, 28, 36)


def _bmfmt(v: int) -> str:
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}M"
    if v >= 1000:
        return f"{v / 1000:.0f}K"
    return str(v)


class SRLinesItem(pg.GraphicsObject):
    """Absolute support (dark green) / resistance (dark red) levels.

    Drawn full width and carried past the last trade into the projection zone,
    so the level price is heading toward is visible before it gets there. Each
    is a translucent zone band (the level has depth, it is not a hairline) with
    a solid rule at the exact price and a label carrying the resting size and
    how long it has held.
    """

    def __init__(self, tick: float):
        super().__init__()
        self.tick = tick
        self.support = None
        self.resistance = None
        self.walls = []
        self.mid_ti = None
        self.x0 = 0.0
        self.x1 = 1.0
        self.zone_ticks = 1.6          # half-height of the shaded zone
        self.font = QFont("Consolas", 8, QFont.Weight.Bold)
        self._bounds = QRectF()
        self.setZValue(-12)            # above the heatmap, below trades

    def set_levels(self, support, resistance, x0: float, x1: float, walls: list = None, mid_ti: float = None, zones: list = None) -> None:
        self.prepareGeometryChange()
        self.support, self.resistance = support, resistance
        self.walls = walls or []
        self.zones = zones or []
        self.mid_ti = mid_ti
        self.x0, self.x1 = x0, x1
        
        all_tis = []
        if self.zones:
            for z in self.zones:
                all_tis.extend([getattr(z, 'p_min_ti', z.peak_ti), getattr(z, 'p_max_ti', z.peak_ti)])
        else:
            all_lvs = [lv for lv in (support, resistance) if lv is not None] + self.walls
            all_tis = [lv.ti for lv in all_lvs if hasattr(lv, 'ti')]

        if all_tis and x1 > x0:
            lo = (min(all_tis) - self.zone_ticks - 1) * self.tick
            hi = (max(all_tis) + self.zone_ticks + 1) * self.tick
            self._bounds = QRectF(x0, lo, x1 - x0, hi - lo)
        else:
            self._bounds = QRectF()
        self.update()

    def boundingRect(self) -> QRectF:
        return self._bounds

    def paint(self, p: QPainter, *args) -> None:
        tick = self.tick
        x0, x1 = self.x0, self.x1
        if x1 <= x0:
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        tr = p.transform()
        mid = self.mid_ti

        if hasattr(self, 'zones') and self.zones:
            p.save()
            p.resetTransform()
            for z in self.zones:
                peak_ti = getattr(z, 'peak_ti', getattr(z, 'ti', None))
                if peak_ti is None:
                    continue
                is_bid = getattr(z, 'side', 'bid') == 'bid' or (mid is not None and peak_ti < mid)
                base_color = QColor(0, 230, 118) if is_bid else QColor(255, 42, 42)
                tag = "S" if is_bid else "R"
                vol = getattr(z, 'total_volume', getattr(z, 'size', 1000))

                # Map data coords -> screen coords (pixels)
                peak_y_data = peak_ti * tick
                pt_left  = tr.map(QPointF(x0, peak_y_data))
                pt_right = tr.map(QPointF(x1, peak_y_data))
                pt_above = tr.map(QPointF(x0, peak_y_data + tick))
                px_left  = pt_left.x()
                px_right = pt_right.x()
                px_y     = pt_left.y()
                px_tick  = abs(pt_above.y() - px_y)          # 1 tick in screen pixels

                # Subtle highlight band: exactly ±1 tick above/below the rule line
                band_h_px = max(2.0, px_tick * 2.4)
                band_y_px = px_y - band_h_px / 2.0
                band_brush = QBrush(QColor(base_color.red(), base_color.green(), base_color.blue(), 35))
                p.fillRect(QRectF(px_left, band_y_px, px_right - px_left, band_h_px), band_brush)

                # Crisp 2px rule line at peak price tick
                p.setPen(QPen(base_color, 2.0, Qt.PenStyle.SolidLine))
                p.drawLine(QPointF(px_left, px_y), QPointF(px_right, px_y))

                # Right-aligned badge label: "S 15K" / "R 22K"
                p.setFont(self.font)
                fm = p.fontMetrics()
                label = f"{tag} {_bmfmt(int(vol))}"
                w = fm.horizontalAdvance(label) + 10
                box = QRectF(px_right - w - 4, px_y - 9, w, 18)
                p.fillRect(box, QColor(base_color.red(), base_color.green(), base_color.blue(), 220))
                p.setPen(QPen(QColor("#06131E"), 1.0))
                p.drawText(box, Qt.AlignmentFlag.AlignCenter, label)
            p.restore()
            return

        # Fallback for legacy Level objects
        all_lvs = []
        seen_tis = set()
        if self.walls:
            for lv in self.walls:
                if lv.ti not in seen_tis:
                    seen_tis.add(lv.ti)
                    all_lvs.append(lv)
        for lv in (self.support, self.resistance):
            if lv is not None and lv.ti not in seen_tis:
                seen_tis.add(lv.ti)
                all_lvs.append(lv)

        if not all_lvs:
            return

        for lv in all_lvs:
            y = lv.ti * tick
            if mid is not None and lv.ti < mid:
                color = QColor(0, 230, 118)
                tag = "S"
            elif mid is not None and lv.ti > mid:
                color = QColor(255, 42, 42)
                tag = "R"
            else:
                color = QColor(235, 240, 245)
                tag = "W"

            vol = getattr(lv, 'size', 1000)
            line_w = float(min(3.0, max(1.2, 1.2 + (vol / 5000.0))))
            p.setPen(QPen(color, line_w))
            p.drawLine(QPointF(x0, y), QPointF(x1, y))

            pt = tr.map(QPointF(x1, y))
            label = f"{tag} {_bmfmt(vol)}"
            p.save(); p.resetTransform()
            p.setFont(self.font)
            fm = p.fontMetrics()
            w = fm.horizontalAdvance(label) + 8
            box = QRectF(pt.x() - w - 4, pt.y() - 8, w, 16)
            p.fillRect(box, QColor(color.red(), color.green(), color.blue(), 215))
            p.setPen(QPen(QColor("#06131E"), 1.0))
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, label)
            p.restore()


class ProjectionItem(pg.GraphicsObject):
    """Projects the CURRENT resting book as fat horizontal bands in the empty
    space just ahead of the latest pie — the limit orders waiting for price.
    Bands are heatmap-coloured (blue->amber->red by size); the single strongest
    bid wall below price is drawn GREEN (support) and the strongest ask wall
    above price RED (resistance), each labelled with its size."""

    def __init__(self, tick: float):
        super().__init__()
        self.col = None
        self.tick = tick
        self.x0 = 0.0
        self.width = 7.0
        self.mid_ti = None
        self.vmax = 1
        self.wall_mult = 4.0         # wall = this × average book size
        self.wall_floor = 4000       # …and at least this many shares
        self.support = None          # set by set_sr(); shared with SRLinesItem
        self.resistance = None
        self.font = QFont("Consolas", 8, QFont.Weight.Bold)
        self._bounds = QRectF()
        self.setZValue(-14)          # above heatmap, below pies/bubbles

    def set_sr(self, support, resistance) -> None:
        """Use the tracker's persistence-weighted levels rather than picking the
        biggest level in this one snapshot - otherwise the band highlighted here
        and the line drawn by SRLinesItem can disagree on the same frame."""
        self.support, self.resistance = support, resistance
        self.update()

    def set_projection(self, col, x0, mid_ti, vmax) -> None:
        self.prepareGeometryChange()
        self.col = col
        self.x0 = x0
        self.mid_ti = mid_ti
        self.vmax = max(1, vmax)
        if col and col.book:
            lo = min(col.book) * self.tick
            hi = max(col.book) * self.tick
            self._bounds = QRectF(x0, lo - self.tick, self.width, (hi - lo) + 2 * self.tick)
        else:
            self._bounds = QRectF()
        self.update()

    def boundingRect(self) -> QRectF:
        return self._bounds

    def paint(self, p: QPainter, *args) -> None:
        col = self.col
        if col is None or not col.book:
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        tick = self.tick
        x0, w, mid = self.x0, self.width, self.mid_ti
        book = col.book

        # Wall threshold still gates whether the band is worth highlighting, but
        # *which* level counts comes from the persistence tracker.
        avg = sum(book.values()) / len(book)
        thr = max(self.wall_floor, avg * self.wall_mult)
        sup_ti = self.support.ti if self.support is not None else None
        res_ti = self.resistance.ti if self.resistance is not None else None
        sup_sz = book.get(sup_ti, 0) if sup_ti is not None else 0
        res_sz = book.get(res_ti, 0) if res_ti is not None else 0

        # absolute support (green) / resistance (red) — fat bright bands + label
        tr = p.transform()
        for ti, size, color, tag in ((sup_ti, sup_sz, SUPPORT_GREEN, "S"),
                                     (res_ti, res_sz, RESIST_RED, "R")):
            if ti is None or size < thr:
                continue
            p.fillRect(QRectF(x0, ti * tick - tick * 0.85, w, tick * 1.7), color)
            pt = tr.map(QPointF(x0, ti * tick))
            p.save(); p.resetTransform()
            p.setFont(self.font); p.setPen(pg.mkPen("#06131E"))
            p.drawText(QPointF(pt.x() + 4, pt.y() + 4), f"{tag} {_bmfmt(size)}")
            p.restore()


class PieItem(_BufItem):
    """One pie per time column at the column's volume-weighted price, split into
    a blue (buy) and red (sell) wedge — reads the aggression ratio at a glance,
    with no overlapping circles."""

    def __init__(self, tick: float):
        super().__init__(tick)
        self.min_size = 0
        self.min_r = 10.0
        self.max_r = 45.0
        self.setZValue(0)

    def paint(self, p: QPainter, *args) -> None:
        if not self.cols:
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        tick = self.tick
        x_lo, x_hi = self._xrange()

        data = []
        for c in self.cols:
            if not (x_lo <= c.bucket <= x_hi):
                continue
            tb = sum(c.buy.values())
            ts = sum(c.sell.values())
            tot = tb + ts
            if tot == 0 or tot < self.min_size:
                continue
            num = den = 0
            for ti, v in c.buy.items():
                num += ti * v; den += v
            for ti, v in c.sell.items():
                num += ti * v; den += v
            if den == 0:
                continue
            data.append((c.bucket + 0.5, num / den, tb, ts, tot))
        if not data:
            return
        smax = max(d[4] for d in data) or 1
        data.sort(key=lambda d: d[4])          # big pies on top

        tr = p.transform()
        # One pie per column, so a pie wider than its column necessarily
        # collides with its neighbours - which is the one thing this mode exists
        # to avoid. Cap the radius at just under half a column's on-screen width
        # so the row stays a clean sequence at any zoom level.
        colw = abs(tr.map(QPointF(1.0, 0.0)).x() - tr.map(QPointF(0.0, 0.0)).x())
        rmax = max(8.0, min(self.max_r, colw * 0.85))
        rmin = max(5.0, min(self.min_r, rmax))

        p.resetTransform()
        for x, vti, tb, ts, tot in data:
            pt = tr.map(QPointF(x, vti * tick))
            r = rmin + (rmax - rmin) * math.sqrt(tot / smax)
            self._glossy_pie(p, pt, r, tb / tot)

    @staticmethod
    def _glossy_pie(p: QPainter, pt: QPointF, r: float, buy_frac: float) -> None:
        rect = QRectF(pt.x() - r, pt.y() - r, 2 * r, 2 * r)
        buy_span = int(round(360 * 16 * buy_frac))
        # flat wedges (clear red/blue split)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(PIE_BUY))
        p.drawPie(rect, 90 * 16, buy_span)                  # buy from 12 o'clock, CCW
        p.setBrush(QBrush(PIE_SELL))
        p.drawPie(rect, 90 * 16 + buy_span, 360 * 16 - buy_span)
        # glossy sphere sheen (white highlight top-left -> transparent)
        g = QRadialGradient(pt.x() - r * 0.34, pt.y() - r * 0.4, r * 1.35)
        g.setColorAt(0.0, QColor(255, 255, 255, 140))
        g.setColorAt(0.45, QColor(255, 255, 255, 24))
        g.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(QBrush(g))
        p.drawEllipse(pt, r, r)
        # dark rim for depth
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(6, 18, 34, 230), 1.2))
        p.drawEllipse(pt, r, r)


class BarsItem(_BufItem):
    """One vertical split-bar per column at its VWAP price: blue segment ∝ buy
    volume, red ∝ sell volume — a compact non-overlapping alternative."""

    def __init__(self, tick: float):
        super().__init__(tick)
        self.min_size = 0
        self.setZValue(0)

    def paint(self, p: QPainter, *args) -> None:
        if not self.cols:
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        tick = self.tick
        x_lo, x_hi = self._xrange()
        rows = []
        for c in self.cols:
            if not (x_lo <= c.bucket <= x_hi):
                continue
            tb = sum(c.buy.values()); ts = sum(c.sell.values()); tot = tb + ts
            if tot == 0 or tot < self.min_size:
                continue
            num = den = 0
            for ti, v in c.buy.items():
                num += ti * v; den += v
            for ti, v in c.sell.items():
                num += ti * v; den += v
            if den:
                rows.append((c.bucket, num / den, tb, ts, tot))
        if not rows:
            return
        smax = max(r[4] for r in rows) or 1
        for bucket, vti, tb, ts, tot in rows:
            y = vti * tick
            h = tick * (0.6 + 6.0 * (tot / smax))          # bar half-height in price
            frac = tb / tot
            p.fillRect(QRectF(bucket + 0.2, y, 0.6, h * frac), QBrush(PIE_BUY))
            p.fillRect(QRectF(bucket + 0.2, y - h * (1 - frac), 0.6, h * (1 - frac)),
                       QBrush(PIE_SELL))


class DomLadderItem(pg.GraphicsObject):
    """Right-edge depth histogram of one Column's book, with size numbers."""

    def __init__(self, tick: float):
        super().__init__()
        self.col = None
        self.tick = tick
        self.vmax = 1                 # right edge the bars are anchored to
        self.font = QFont("Consolas", 8, QFont.Weight.Bold)
        self._bounds = QRectF()

    def set_col(self, col, tick=None) -> None:
        self.prepareGeometryChange()
        self.col = col
        if tick is not None:
            self.tick = tick
        if col and col.book:
            lo = min(col.book) * self.tick
            hi = max(col.book) * self.tick
            self.vmax = max(col.book.values()) or 1
            self._bounds = QRectF(0, lo - self.tick, self.vmax,
                                  (hi - lo) + 2 * self.tick)
        else:
            self.vmax = 1
            self._bounds = QRectF()
        self.update()

    def boundingRect(self) -> QRectF:
        return self._bounds

    def paint(self, p: QPainter, *args) -> None:
        col = self.col
        if col is None or not col.book:
            return
        tick = self.tick
        mx = max(1, self.vmax)
        ask_ti = col.ask_ti if col.ask_ti is not None else 10 ** 12
        tr = p.transform()

        BID_BAR_COLOR = QColor(0, 163, 224, 225)     # #00A3E0 cyan-blue for bids
        ASK_BAR_COLOR = QColor(229, 57, 53, 225)     # #E53935 red for asks

        col_width_px = abs(tr.map(QPointF(mx, 0.0)).x() - tr.map(QPointF(0.0, 0.0)).x()) or 100.0
        min_px = 3.0
        min_data_w = (min_px / col_width_px) * mx if col_width_px > 0 else mx * 0.04

        
        # Proportional bar length for EVERY row in view: power scaling (0.50) + 4% width floor
        # guarantees small sizes (80-130) display a visible cyan (#00A3E0) or red (#E53935) bar.
        for ti, size in col.book.items():
            if size <= 0:
                continue
            is_ask = ti >= ask_ti
            c = ASK_BAR_COLOR if is_ask else BID_BAR_COLOR
            frac = (size / mx) ** 0.50
            bar_w = max(min_data_w, frac * mx)
            p.fillRect(QRectF(mx - bar_w, ti * tick - tick / 2, bar_w, tick), c)

        p.setFont(self.font)
        p.setPen(pg.mkPen("#EAEEF5"))
        drawn_y: list[float] = []
        min_spacing = 14.0
        for ti, size in sorted(col.book.items(), key=lambda kv: kv[1], reverse=True):
            rp = tr.map(QPointF(mx, ti * tick))
            sy = rp.y()
            if any(abs(sy - dy) < min_spacing for dy in drawn_y):
                continue
            drawn_y.append(sy)
            p.save(); p.resetTransform()
            p.drawText(QRectF(rp.x() - 62, sy - 7, 58, 14),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       _bmfmt(size))
            p.restore()


class VolumeBarsItem(_BufItem):
    """Bottom per-column executed-volume bars, coloured by net delta, formatted."""

    def __init__(self, tick: float):
        super().__init__(tick)
        self.font = QFont("Consolas", 7, QFont.Weight.Bold)

    def set_cols(self, cols):
        self.prepareGeometryChange()
        self.cols = cols
        if cols:
            mx = max((c.vol for c in cols), default=1) or 1
            x0, x1 = cols[0].bucket, cols[-1].bucket
            self._bounds = QRectF(x0 - 1, 0, (x1 - x0) + 3, mx * 1.15)
        else:
            self._bounds = QRectF()
        self.update()

    def paint(self, p: QPainter, *args) -> None:
        if not self.cols:
            return
        x_lo, x_hi = self._xrange()
        tr = p.transform()
        colw = abs(tr.map(QPointF(1.0, 0.0)).x() - tr.map(QPointF(0.0, 0.0)).x())
        show_labels = colw >= 20.0  # skip label overlay when columns are densely packed to avoid overlap

        for c in self.cols:
            if not (x_lo <= c.bucket <= x_hi):
                continue
            if c.vol == 0:
                # Render a subtle 2px baseline indicator for 0-volume seconds so the timeline stays continuous
                p.fillRect(QRectF(c.bucket + 0.30, 0, 0.40, 2), QColor(90, 100, 115, 160))
                continue
            buy_vol = sum(c.buy.values())
            sell_vol = sum(c.sell.values())
            color = BUY_BUBBLE if buy_vol >= sell_vol else SELL_BUBBLE
            p.fillRect(QRectF(c.bucket + 0.28, 0, 0.44, c.vol),
                       QColor(color.red(), color.green(), color.blue(), 225))
            if show_labels:
                rp = tr.map(QPointF(c.bucket + 0.5, c.vol))
                p.save(); p.resetTransform()
                p.setFont(self.font)
                p.setPen(pg.mkPen("#AEB4C0"))
                p.drawText(QRectF(rp.x() - 16, rp.y() - 14, 32, 12),
                           Qt.AlignmentFlag.AlignCenter, _bmfmt(c.vol))
                p.restore()


class IcebergItem(pg.GraphicsObject):
    """Detects and renders Iceberg / Hidden Order markers (yellow diamonds).
    Triggered when total executed trade volume at a price tier exceeds the resting limit book size by >= 2.5x."""

    def __init__(self, tick: float):
        super().__init__()
        self.tick = tick
        self.cols = []
        self.ratio_threshold = 2.5     # trade volume >= 2.5x resting book size
        self.min_iceberg_vol = 300      # min executed volume to flag an iceberg
        self.font = QFont("Consolas", 8, QFont.Weight.Bold)
        self._bounds = QRectF()
        self.setZValue(10)             # top layer above bubbles

    def set_cols(self, cols):
        self.prepareGeometryChange()
        self.cols = cols
        if cols:
            x0, x1 = cols[0].bucket, cols[-1].bucket
            self._bounds = QRectF(x0 - 1, 0, (x1 - x0) + 3, 1000000)
        else:
            self._bounds = QRectF()
        self.update()

    def boundingRect(self) -> QRectF:
        return self._bounds

    def paint(self, p: QPainter, *args) -> None:
        if not self.cols:
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        tick = self.tick
        tr = p.transform()

        ICEBERG_YELLOW = QColor(255, 220, 0, 240)
        ICEBERG_BORDER = QColor(30, 30, 30, 240)

        for c in self.cols[-60:]:
            bk = c.book or {}
            for ti in set(c.buy.keys()) | set(c.sell.keys()):
                exec_vol = c.buy.get(ti, 0) + c.sell.get(ti, 0)
                if exec_vol < self.min_iceberg_vol:
                    continue
                rest_sz = bk.get(ti, 100)
                if exec_vol >= rest_sz * self.ratio_threshold:
                    pt = tr.map(QPointF(c.bucket + 0.5, ti * tick))
                    p.save(); p.resetTransform()
                    r = 6.0
                    polygon = [
                        QPointF(pt.x(), pt.y() - r),
                        QPointF(pt.x() + r, pt.y()),
                        QPointF(pt.x(), pt.y() + r),
                        QPointF(pt.x() - r, pt.y()),
                    ]
                    p.setBrush(QBrush(ICEBERG_YELLOW))
                    p.setPen(QPen(ICEBERG_BORDER, 1.2))
                    p.drawPolygon(polygon)
                    p.restore()
