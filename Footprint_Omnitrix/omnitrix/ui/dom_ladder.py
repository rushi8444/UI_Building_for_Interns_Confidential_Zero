"""Classic DOM price ladder — the vertical depth grid every professional
trading terminal has.

Rows are prices (descending). Columns:

    BID SIZE | resting bid depth bar | PRICE | resting ask depth bar | ASK SIZE
                                     | VOLUME traded at that price (session)

The best bid / best ask rows are highlighted, the session POC is marked, and
depth bars are scaled to the largest resting order on screen so liquidity walls
stand out immediately.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QPainter, QColor, QFont, QPen
from PyQt6.QtWidgets import QWidget, QMainWindow

# Obsidian Pro Dark Theme Constants (Synchronized across all Omnitrix Windows)
BG = QColor("#121212")
HEADER_BG = QColor("#161616")
GRID = QColor("#1C1C1C")
GRID_ROW = QColor("#171717")
TEXT = QColor("#E8E8E8")
DIM = QColor("#888888")

BID = QColor("#388E3C")
ASK = QColor("#D32F2F")
BID_BAR = QColor(56, 142, 60, 75)
ASK_BAR = QColor(211, 47, 47, 75)

BID_ROW_BG = QColor(56, 142, 60, 35)
ASK_ROW_BG = QColor(211, 47, 47, 35)
SPREAD_BG = QColor(22, 22, 22)
ALT_ROW_BG = QColor(16, 16, 16)
PRICE_COL_BG = QColor(20, 20, 20)

POC_COL = QColor("#C9A227")
POC_BG = QColor(201, 162, 39, 38)

VOL_BAR = QColor(124, 107, 174, 55)
VOL_TEXT = QColor("#A090C0")


def _fmt(v: float) -> str:
    a = abs(v)
    if a >= 1_000_000:
        return f"{v / 1_000_000:.1f}M"
    if a >= 1000:
        return f"{v / 1000:.1f}K"
    return f"{v:,.0f}"


class DomLadderWidget(QWidget):
    ROW_H = 20

    def __init__(self, app_window, parent=None):
        super().__init__(parent)
        self.app = app_window
        self.setMinimumWidth(460)
        self.f_head = QFont("Consolas", 9, QFont.Weight.Bold)
        self.f_row = QFont("Consolas", 9)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(200)

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), BG)
        app = self.app
        sym = app.active_symbol
        buf = app.bookmaps.get(sym) if sym else None
        col = buf.latest() if buf else None
        w, h = self.width(), self.height()

        px_price_left = int(w * 0.39)
        px_price_w = int(w * 0.19)
        px_ask_left = px_price_left + px_price_w
        px_vol_left = int(w * 0.83)

        # Header Band
        p.fillRect(QRectF(0, 0, w, 24), HEADER_BG)
        p.setPen(QPen(GRID, 1))
        p.drawLine(0, 24, w, 24)

        p.setFont(self.f_head); p.setPen(DIM)
        p.drawText(QRectF(4, 0, px_price_left - 12, 24),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "BID")
        p.drawText(QRectF(px_price_left, 0, px_price_w, 24),
                   Qt.AlignmentFlag.AlignCenter, "PRICE")
        p.drawText(QRectF(px_ask_left + 8, 0, px_vol_left - px_ask_left - 16, 24),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "ASK")
        p.drawText(QRectF(px_vol_left, 0, w - px_vol_left - 10, 24),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "VOLUME")

        if col is None or not col.book:
            p.setFont(self.f_row); p.setPen(DIM)
            p.drawText(QRectF(0, 40, w, 30),
                       Qt.AlignmentFlag.AlignCenter, "waiting for L2 depth…")
            return

        tick = app.instruments.tick(sym)
        rows = max(1, (h - 26) // self.ROW_H)
        bid_ti, ask_ti = col.bid_ti, col.ask_ti
        centre = ((bid_ti + ask_ti) // 2 if bid_ti is not None and ask_ti is not None
                  else max(col.book))
        top = centre + rows // 2

        prof = app.profiles.get(sym)
        vols = prof.analytics()["totals"] if prof and prof.total else {}
        poc = prof.analytics()["poc"] if prof and prof.total else None
        max_sz = max(col.book.values()) or 1
        max_vol = max(vols.values()) if vols else 1

        p.setFont(self.f_row)
        for k in range(rows):
            y = 25 + k * self.ROW_H
            if y > h:
                break
            ti = top - k
            size = col.book.get(ti, 0)
            is_bid = bid_ti is not None and ti <= bid_ti
            is_ask = ask_ti is not None and ti >= ask_ti
            price = ti * tick

            # Row background highlight
            if bid_ti is not None and ti == bid_ti:
                p.fillRect(QRectF(0, y, w, self.ROW_H), BID_ROW_BG)
                p.fillRect(QRectF(0, y, 3, self.ROW_H), BID)
            elif ask_ti is not None and ti == ask_ti:
                p.fillRect(QRectF(0, y, w, self.ROW_H), ASK_ROW_BG)
                p.fillRect(QRectF(0, y, 3, self.ROW_H), ASK)
            elif bid_ti is not None and ask_ti is not None and bid_ti < ti < ask_ti:
                p.fillRect(QRectF(0, y, w, self.ROW_H), SPREAD_BG)
            elif k % 2 == 1:
                p.fillRect(QRectF(0, y, w, self.ROW_H), ALT_ROW_BG)

            # Center Price column background strip
            p.fillRect(QRectF(px_price_left, y, px_price_w, self.ROW_H), PRICE_COL_BG)

            # Resting Bid Depth Bar and Size
            if size > 0 and is_bid:
                frac = size / max_sz
                bar_w = px_price_left - 16
                bw = max(2, int(bar_w * frac))
                p.setPen(Qt.PenStyle.NoPen); p.setBrush(BID_BAR)
                p.drawRoundedRect(QRectF(px_price_left - 4 - bw, y + 2, bw, self.ROW_H - 4), 2, 2)
                p.setPen(BID)
                p.drawText(QRectF(8, y, px_price_left - 14, self.ROW_H),
                           Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, _fmt(size))

            # Resting Ask Depth Bar and Size
            if size > 0 and is_ask:
                frac = size / max_sz
                bar_w = px_vol_left - px_ask_left - 16
                bw = max(2, int(bar_w * frac))
                p.setPen(Qt.PenStyle.NoPen); p.setBrush(ASK_BAR)
                p.drawRoundedRect(QRectF(px_ask_left + 4, y + 2, bw, self.ROW_H - 4), 2, 2)
                p.setPen(ASK)
                p.drawText(QRectF(px_ask_left + 12, y, bar_w, self.ROW_H),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, _fmt(size))

            # Session Volume Traded at level
            v = vols.get(ti, 0)
            if v:
                vol_w = w - px_vol_left - 10
                vw = max(2, int(vol_w * (v / max_vol)))
                p.setPen(Qt.PenStyle.NoPen); p.setBrush(VOL_BAR)
                p.drawRoundedRect(QRectF(w - 6 - vw, y + 3, vw, self.ROW_H - 6), 2, 2)
                p.setPen(VOL_TEXT)
                p.drawText(QRectF(px_vol_left, y, vol_w, self.ROW_H),
                           Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, _fmt(v))

            # Price text & POC Badge
            if poc is not None and ti == poc:
                p.setPen(QPen(POC_COL, 1)); p.setBrush(POC_BG)
                p.drawRoundedRect(QRectF(px_price_left + 4, y + 2, px_price_w - 8, self.ROW_H - 4), 3, 3)
                p.setPen(POC_COL)
            else:
                p.setPen(TEXT)
            p.drawText(QRectF(px_price_left, y, px_price_w, self.ROW_H),
                       Qt.AlignmentFlag.AlignCenter, f"{price:,.2f}")

            # Horizontal row border separator
            p.setPen(QPen(GRID_ROW, 1))
            p.drawLine(0, int(y + self.ROW_H - 1), w, int(y + self.ROW_H - 1))

        # Vertical Column Divider Lines
        p.setPen(QPen(GRID, 1))
        p.drawLine(px_price_left, 24, px_price_left, h)
        p.drawLine(px_ask_left, 24, px_ask_left, h)
        p.drawLine(px_vol_left, 24, px_vol_left, h)


class DomLadderWindow(QMainWindow):
    def __init__(self, app_window, parent=None):
        super().__init__(parent)
        sym = app_window.active_symbol or ""
        self.setWindowTitle(f"Omnitrix DOM Ladder — {sym}")
        self.resize(520, 820)
        self.dom_widget = DomLadderWidget(app_window, self)
        self.setCentralWidget(self.dom_widget)
        if hasattr(app_window, 'theme'):
            self.set_theme(app_window.theme)
        else:
            self.setStyleSheet("QMainWindow { background: #121212; }")

    def set_theme(self, theme: Theme) -> None:
        self.theme = theme
        t = theme
        self.setStyleSheet(f"QMainWindow {{ background: {t.bg}; }}")
        if hasattr(self, 'dom_widget'):
            self.dom_widget.setStyleSheet(f"background: {t.bg}; color: {t.text};")
