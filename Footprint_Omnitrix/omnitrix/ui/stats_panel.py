"""Session Statistics dock — the at-a-glance terminal readout for the active
symbol: OHLC/range, traded volume and delta, VWAP, profile levels (POC/VAH/VAL)
and tape composition (buy vs sell share, average and largest print).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QPainter, QColor, QFont
from PyQt6.QtWidgets import QWidget

BG = QColor(28, 27, 27)         # #1c1b1b
HEAD = QColor(138, 138, 138)     # #8A8A8A
LABEL = QColor(138, 138, 138)    # #8A8A8A
VALUE = QColor(232, 232, 232)    # #E8E8E8
UP = QColor(38, 166, 154)        # #26A69A
DOWN = QColor(242, 54, 69)       # #F23645
RULE = QColor(42, 42, 42)        # #2A2A2A


def _fmt(v: float, dp: int = 0) -> str:
    a = abs(v)
    if a >= 1_000_000:
        return f"{v / 1_000_000:.2f}M"
    if a >= 1000:
        return f"{v / 1000:.1f}K"
    return f"{v:,.{dp}f}"


class StatsPanel(QWidget):
    ROW_H = 19

    def __init__(self, app_window, parent=None):
        super().__init__(parent)
        self.app = app_window
        self.setMinimumWidth(232)
        self.f_head = QFont("Consolas", 9, QFont.Weight.Bold)
        self.f_row = QFont("Consolas", 9)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(400)

    # ---- data ------------------------------------------------------------
    def _collect(self) -> list:
        app = self.app
        sym = app.active_symbol
        if not sym or sym not in app.series:
            return []
        bars = app.series[sym].view(app.tf_s)
        if not bars:
            return []
        tick = app.instruments.tick(sym)
        o = bars[0].open
        hi = max(b.high for b in bars)
        lo = min(b.low for b in bars)
        last = bars[-1].close
        chg = last - o
        vol = sum(b.volume for b in bars)
        delta = sum(b.delta for b in bars)

        buy = sell = 0
        cum_pv = cum_v = 0.0
        for b in bars:
            for ti, (s_v, b_v) in b.cells.items():
                sell += s_v; buy += b_v
                v = s_v + b_v
                cum_v += v; cum_pv += ti * tick * v
        vwap = cum_pv / cum_v if cum_v else last
        buy_pct = (buy / (buy + sell) * 100) if (buy + sell) else 0

        rows = [
            ("SESSION", None),
            ("Open", f"{o:,.2f}"), ("High", f"{hi:,.2f}"),
            ("Low", f"{lo:,.2f}"), ("Last", f"{last:,.2f}"),
            ("Change", f"{chg:+.2f}"), ("Range", f"{hi - lo:,.2f}"),
            ("VWAP", f"{vwap:,.2f}"),
            ("FLOW", None),
            ("Volume", _fmt(vol)), ("Delta", f"{delta:+,}"),
            ("Buy vol", _fmt(buy)), ("Sell vol", _fmt(sell)),
            ("Buy share", f"{buy_pct:.1f}%"),
        ]

        prof = app.profiles.get(sym)
        if prof and prof.total:
            a = prof.analytics()
            if a["poc"] is not None:
                rows += [
                    ("PROFILE", None),
                    ("POC", f"{a['poc'] * tick:,.2f}"),
                    ("VAH", f"{a['vah'] * tick:,.2f}"),
                    ("VAL", f"{a['val'] * tick:,.2f}"),
                    ("Levels", f"{len(a['totals']):,}"),
                ]

        buf = app.bookmaps.get(sym)
        if buf and buf.trades:
            sizes = [t[2] for t in buf.trades]
            rows += [
                ("TAPE", None),
                ("Prints", _fmt(len(sizes))),
                ("Avg size", _fmt(sum(sizes) / len(sizes))),
                ("Max print", _fmt(max(sizes))),
            ]
        return rows

    def set_theme(self, theme) -> None:
        self.theme = theme
        self.update()

    # ---- paint -----------------------------------------------------------
    def paintEvent(self, _) -> None:
        p = QPainter(self)
        t = getattr(self, "theme", None) or getattr(self.app, "theme", None)
        if t and getattr(t, "name", "dark") == "light":
            bg_col = QColor("#FFFFFF")
            head_col = QColor("#667085")
            lbl_col = QColor("#344054")
            val_col = QColor("#101828")
            rule_col = QColor("#E3E6EB")
            up_col = QColor(t.bull)
            down_col = QColor(t.bear)
        else:
            bg_col = BG
            head_col = HEAD
            lbl_col = LABEL
            val_col = VALUE
            rule_col = RULE
            up_col = UP
            down_col = DOWN

        p.fillRect(self.rect(), bg_col)
        rows = self._collect()
        if not rows:
            p.setFont(self.f_row); p.setPen(lbl_col)
            p.drawText(10, 24, "waiting for data…")
            return
        w = self.width()
        y = 6
        for label, value in rows:
            if value is None:                       # section header
                y += 6
                p.setFont(self.f_head); p.setPen(head_col)
                p.drawText(8, y + 12, label)
                p.setPen(rule_col)
                p.drawLine(8, y + 16, w - 8, y + 16)
                y += self.ROW_H + 2
                continue
            p.setFont(self.f_row)
            p.setPen(lbl_col)
            p.drawText(10, y + 13, label)
            col = val_col
            if label in ("Change", "Delta") and value.startswith(("+", "-")):
                col = up_col if value.startswith("+") else down_col
            p.setPen(col)
            p.drawText(QRectF(0, y, w - 10, self.ROW_H),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       value)
            y += self.ROW_H
            if y > self.height():
                break
