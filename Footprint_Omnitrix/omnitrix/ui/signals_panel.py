"""Order-Flow Signals dock — live list of detected block prints, absorption
events and broken liquidity walls for the active symbol.
"""

from __future__ import annotations

import time

from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QPainter, QColor, QFont
from PyQt6.QtWidgets import QWidget

from ..engine import signals

BG = QColor(28, 27, 27)          # #1c1b1b
HEAD = QColor(138, 138, 138)     # #8A8A8A
RULE = QColor(42, 42, 42)        # #2A2A2A
TEXT = QColor(232, 232, 232)     # #E8E8E8
DIM = QColor(138, 138, 138)      # #8A8A8A

KIND_COL = {
    "block": QColor(156, 123, 255),
    "absorption": QColor(255, 179, 0),
    "wall_break": QColor(239, 96, 96),
}
KIND_TAG = {"block": "BLK", "absorption": "ABS", "wall_break": "BRK"}


def _fmt(v: float) -> str:
    a = abs(v)
    if a >= 1_000_000:
        return f"{v / 1_000_000:.2f}M"
    if a >= 1000:
        return f"{v / 1000:.1f}K"
    return f"{v:,.0f}"


class SignalsPanel(QWidget):
    ROW_H = 19

    def __init__(self, app_window, parent=None):
        super().__init__(parent)
        self.app = app_window
        self.setMinimumWidth(250)
        self.f_head = QFont("Consolas", 9, QFont.Weight.Bold)
        self.f_row = QFont("Consolas", 9)
        self._events: list = []
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(900)

    def _tick(self) -> None:
        app = self.app
        sym = app.active_symbol
        buf = app.bookmaps.get(sym) if sym else None
        if buf:
            try:
                self._events = signals.detect_all(buf, agg=1)[:60]
            except Exception:
                self._events = []
        self.update()

    def set_theme(self, theme) -> None:
        self.theme = theme
        self.update()

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        t = getattr(self, "theme", None) or getattr(self.app, "theme", None)
        if t and getattr(t, "name", "dark") == "light":
            bg_col = QColor("#FFFFFF")
            head_col = QColor("#667085")
            text_col = QColor("#101828")
            dim_col = QColor("#667085")
            rule_col = QColor("#E3E6EB")
        else:
            bg_col = BG
            head_col = HEAD
            text_col = TEXT
            dim_col = DIM
            rule_col = RULE

        p.fillRect(self.rect(), bg_col)
        w = self.width()

        p.setFont(self.f_head); p.setPen(head_col)
        p.drawText(8, 16, "TYPE   PRICE      SIZE   TIME")
        p.setPen(rule_col); p.drawLine(8, 21, w - 8, 21)

        if not self._events:
            p.setFont(self.f_row); p.setPen(dim_col)
            p.drawText(10, 40, "no signals yet…")
            return

        sym = self.app.active_symbol or "QQQ"
        tick = self.app.instruments.tick(sym)
        dt = self.app.bookmaps[sym].col_dt if sym in self.app.bookmaps else 1.0

        p.setFont(self.f_row)
        y = 26
        for ev in self._events:
            col = KIND_COL.get(ev["kind"], text_col)
            p.setPen(col)
            p.drawText(9, y + 13, KIND_TAG.get(ev["kind"], "?"))
            p.setPen(text_col)
            p.drawText(52, y + 13, f"{ev['ti'] * tick:,.2f}")
            p.drawText(QRectF(0, y, w - 66, self.ROW_H),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       _fmt(ev["size"]))
            p.setPen(dim_col)
            p.drawText(QRectF(0, y, w - 8, self.ROW_H),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       time.strftime("%H:%M:%S",
                                     time.localtime(ev["bucket"] * dt)))
            y += self.ROW_H
            if y > self.height():
                break
