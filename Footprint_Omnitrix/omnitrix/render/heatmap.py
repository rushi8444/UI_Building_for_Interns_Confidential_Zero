"""Bookmap-style resting-liquidity heatmap.

Draws one colour strip per bar column showing the L2 resting size at each price
(from `bar.book`). Normalisation is computed over the *visible* columns each
frame, so the scale auto-adapts as you scroll — fixing the old app's
"max_size only ever grows" wash-out bug.

Colour ramp (low -> high liquidity): deep navy -> blue -> white -> amber -> red.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QPainter


def _build_lut() -> list[QColor]:
    stops = [
        (0.00, (10, 17, 40)),      # #0A1128 Dark background navy
        (0.15, (14, 37, 69)),      # dark navy blue texture
        (0.35, (0, 102, 153)),     # ocean blue depth
        (0.52, (0, 163, 224)),     # cyan / low liquidity
        (0.70, (255, 255, 0)),     # vivid yellow / medium liquidity
        (0.85, (255, 102, 0)),     # bright orange / high liquidity
        (0.95, (230, 0, 0)),       # hot red / liquidity walls
        (1.00, (255, 255, 255)),   # pure white core for massive walls
    ]
    lut: list[QColor] = []
    for i in range(256):
        t = i / 255.0
        for j in range(len(stops) - 1):
            t0, c0 = stops[j]
            t1, c1 = stops[j + 1]
            if t0 <= t <= t1:
                f = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
                r = int(c0[0] + (c1[0] - c0[0]) * f)
                g = int(c0[1] + (c1[1] - c0[1]) * f)
                b = int(c0[2] + (c1[2] - c0[2]) * f)
                lut.append(QColor(r, g, b))
                break
    return lut


_LUT = _build_lut()


class HeatmapItem(pg.GraphicsObject):
    def __init__(self, tick: float):
        super().__init__()
        self.bars: list = []
        self.tick = tick
        self.alpha = 235
        self._bounds = QRectF()
        self.setZValue(-10)        # behind the footprint

    def set_bars(self, bars: list) -> None:
        self.prepareGeometryChange()
        self.bars = bars
        if bars:
            lo = min(b.low for b in bars)
            hi = max(b.high for b in bars)
            self._bounds = QRectF(-1, lo - 1, len(bars) + 2, (hi - lo) + 2)
        else:
            self._bounds = QRectF()
        self.update()

    def boundingRect(self) -> QRectF:
        return self._bounds

    def paint(self, p: QPainter, *args) -> None:
        if not self.bars:
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        tick = self.tick

        vb = self.getViewBox()
        if vb is None:
            return
        xr = vb.viewRange()[0]
        x_lo = max(0, int(xr[0]) - 1)
        x_hi = min(len(self.bars), int(xr[1]) + 2)

        # Percentile-based logarithmic min-max scale over visible bars
        all_vs = []
        for x in range(x_lo, x_hi):
            bk = self.bars[x].book
            if bk:
                all_vs.extend([v for v in bk.values() if v > 0])

        if all_vs:
            logs = np.log1p(all_vs)
            positive_logs = logs[logs > 0]
            if len(positive_logs) > 10:
                p_low, p_high = np.percentile(positive_logs, [20, 88])
            elif len(positive_logs) > 0:
                p_low, p_high = positive_logs.min(), positive_logs.max()
            else:
                p_low, p_high = 0.0, 1.0
            span = max(0.5, float(p_high - p_low)) 
            p_low = float(p_low)
        else:
            p_low, span = 0.0, 1.0

        for x in range(x_lo, x_hi):
            bk = self.bars[x].book
            if not bk:
                continue
            for ti, size in bk.items():
                if size <= 0:
                    continue
                v = np.clip((np.log1p(size) - p_low) / span, 0.0, 1.0)
                idx = int(v * 255.0)
                c = _LUT[idx]
                c = QColor(c.red(), c.green(), c.blue(), self.alpha)
                p.fillRect(QRectF(x - 0.5, ti * tick - tick / 2, 1.0, tick), c)
