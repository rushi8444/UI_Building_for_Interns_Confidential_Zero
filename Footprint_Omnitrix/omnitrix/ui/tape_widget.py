"""Time-&-Sales tape: a scrolling list of recent prints, newest on top,
coloured by aggressor and highlighted for large ("block") trades.

Reads the active symbol's `BookmapBuffer.trades` (x, tick_index, size,
aggressor) on a timer — no separate storage needed.
"""

from __future__ import annotations

import time
import pyqtgraph as pg
from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QFont

BUY = QColor(38, 166, 154)       # #26A69A
SELL = QColor(242, 54, 69)       # #F23645
BG = QColor(28, 27, 27)          # #1c1b1b
GRID = QColor(42, 42, 42)        # #2A2A2A
TEXT = QColor(232, 232, 232)     # #E8E8E8


class TapeWidget(QWidget):
    ROW_H = 18

    def __init__(self, get_source, tick_fn, block_size: int = 1000, parent=None):
        super().__init__(parent)
        self._get_source = get_source     # () -> deque of (x, ti, size, aggr) | None
        self._tick_fn = tick_fn           # () -> current tick size
        self.block_size = block_size
        self.setMinimumWidth(220)
        self.font = QFont("Consolas", 9)
        self.header_font = QFont("Consolas", 9, QFont.Weight.Bold)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(150)

    def set_theme(self, theme) -> None:
        self.theme = theme
        self.update()

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        t = getattr(self, "theme", None) or getattr(self.window(), "theme", None)
        if t and getattr(t, "name", "dark") == "light":
            bg_col = QColor("#FFFFFF")
            text_col = QColor("#101828")
            header_col = QColor("#667085")
            grid_col = QColor("#E3E6EB")
            buy_col = QColor(t.bull)
            sell_col = QColor(t.bear)
        else:
            bg_col = BG
            text_col = TEXT
            header_col = QColor(140, 147, 160)
            grid_col = GRID
            buy_col = BUY
            sell_col = SELL

        p.fillRect(self.rect(), bg_col)
        w = self.width()
        col_time, col_price, col_size = 8, int(w * 0.42), int(w * 0.72)

        # header
        p.setFont(self.header_font)
        p.setPen(pg.mkPen(header_col))
        p.drawText(col_time, 14, "TIME")
        p.drawText(col_price, 14, "PRICE")
        p.drawText(col_size, 14, "SIZE")
        p.setPen(pg.mkPen(grid_col))
        p.drawLine(0, 20, w, 20)

        src = self._get_source()
        if not src:
            return
        tick = self._tick_fn()
        p.setFont(self.font)
        n = max(0, (self.height() - 24) // self.ROW_H)
        rows = list(src)[-n:][::-1]      # newest first
        y = 24
        for x, ti, size, aggr in rows:
            is_buy = aggr.value == "buy"
            is_block = size >= self.block_size
            base = buy_col if is_buy else (sell_col if aggr.value == "sell" else QColor(120, 124, 132))
            if is_block:
                c = QColor(base); c.setAlpha(60)
                p.fillRect(QRectF(0, y, w, self.ROW_H), c)
            p.setPen(pg.mkPen(text_col))
            p.drawText(col_time, y + 13, time.strftime("%H:%M:%S", time.localtime(x)))
            p.setPen(pg.mkPen(base))
            p.drawText(col_price, y + 13, f"{ti * tick:.2f}")
            p.drawText(col_size, y + 13, f"{size:,}")
            y += self.ROW_H
            if y > self.height():
                break
