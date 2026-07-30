"""Microstructure Analytics: four stacked, time-aligned panes derived from the
L2 book and tick-by-tick prints.

  1. Book Imbalance   resting bid vs ask depth (-1..+1)  — L2 pressure
  2. Resting Depth    absolute bid / ask depth curves    — liquidity supply
  3. Spread           bid/ask width in ticks             — liquidity stress
  4. Tape Speed + CVD volume per column & cumulative delta — aggression
"""

from __future__ import annotations

import pyqtgraph as pg
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QLinearGradient, QGradient, QColor, QBrush
from PyQt6.QtWidgets import QMainWindow, QToolBar, QLabel, QComboBox

from ..engine import metrics
from ..render import DARK
from .bookmap_window import TF

BG = "#121212"


class AnalyticsWindow(QMainWindow):
    def __init__(self, buffer, tick: float, parent=None):
        super().__init__(parent)
        self.buffer = buffer
        self.tick = tick
        self.agg = 1
        self.setWindowTitle(f"Omnitrix Analytics — {buffer.symbol}")
        self.resize(1420, 900)

        pg.setConfigOptions(useOpenGL=False, antialias=True)
        self._build_toolbar()
        self._build_plots()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(250)
        self.refresh()

    def _build_toolbar(self) -> None:
        tb = QToolBar(); tb.setMovable(False); self.addToolBar(tb)
        tb.addWidget(QLabel("  Timeframe "))
        self.tf_combo = QComboBox()
        self.tf_combo.addItems(list(TF))
        self.tf_combo.currentTextChanged.connect(self._on_tf)
        tb.addWidget(self.tf_combo)
        self.lbl = QLabel("   ")
        tb.addWidget(self.lbl)
        self.set_theme(DARK)

    def set_theme(self, theme: Theme) -> None:
        self.theme = theme
        t = theme
        self.setStyleSheet(
            f"QMainWindow {{ background-color:{t.bg}; }}"
            f" QToolBar {{ background-color:{t.panel}; border: none; border-bottom:1px solid {t.grid}; border-right:1px solid {t.grid}; padding:6px; spacing:8px; }}"
            f" QToolBar::separator {{ background-color:{t.grid}; width:1px; height:20px; margin:0px 6px; }}"
            f" QToolTip {{ background-color:{t.panel}; color:{t.text}; border:1px solid {t.grid}; border-radius:4px; padding:4px 8px; font-family:'Inter', 'Segoe UI', Arial, sans-serif; font-size:12px; font-weight:500; }}"
            f" QLabel {{ color:{t.text}; font-size:12px; font-weight:600; font-family:'Inter', sans-serif; }}"
            f" QComboBox {{ background-color:{t.panel}; color:{t.text}; border:1px solid {t.grid}; border-radius:4px; padding:4px 10px; min-height:22px; font-size:12px; font-weight:500; font-family:'Inter', sans-serif; }}"
            f" QComboBox QAbstractItemView {{ background-color:{t.panel}; color:{t.text}; border:1px solid {t.grid}; selection-background-color:{t.grid}; outline: none; }}"
            f" QPushButton {{ background-color:transparent; color:{t.text}; border:1px solid transparent; border-radius:4px; padding:6px 12px; font-weight:500; font-size:12px; font-family:'Inter', sans-serif; }}"
            f" QPushButton:hover {{ background-color:{t.grid}; color:{t.text}; }}"
        )
        if hasattr(self, 'glw'):
            self.glw.setBackground(t.bg)
            for plt in (getattr(self, 'p_imb', None), getattr(self, 'p_dep', None), getattr(self, 'p_spr', None), getattr(self, 'p_spd', None)):
                if plt:
                    for ax_name in ("right", "bottom", "left"):
                        ax = plt.getAxis(ax_name)
                        if ax:
                            ax.setPen(pg.mkPen(t.axis))
                            ax.setTextPen(pg.mkPen(t.text))

    def _build_plots(self) -> None:
        self.glw = pg.GraphicsLayoutWidget()
        self.glw.setBackground(BG)
        self.setCentralWidget(self.glw)

        titles = ["Book Imbalance  (bid vs ask depth)", "Resting Depth",
                  "Spread (ticks)", "Tape Speed / CVD"]
        self.plots = []
        for i, t in enumerate(titles):
            pl = self.glw.addPlot(row=i, col=0)
            pl.showAxis("right"); pl.hideAxis("left")
            pl.setTitle(t, color="#9A9A9A", size="11px")
            pl.showGrid(x=True, y=True, alpha=0.03)
            if i:
                pl.setXLink(self.plots[0])
            if i < len(titles) - 1:
                pl.hideAxis("bottom")
            for ax in ("right", "bottom"):
                a = pl.getAxis(ax)
                a.setPen(pg.mkPen("#2A2A2A")); a.setTextPen(pg.mkPen("#9A9A9A"))
            self.plots.append(pl)

        p_imb, p_depth, p_spread, p_speed = self.plots

        # Vertical Gradient Brush for Book Imbalance in logical data coordinates (-1 to 1)
        grad = QLinearGradient(0, 1, 0, -1)
        grad.setCoordinateMode(QGradient.CoordinateMode.LogicalMode)
        grad.setColorAt(0.0, QColor(58, 110, 165, 140))  # Top (y=1): 55% opacity #3A6EA5
        grad.setColorAt(0.5, QColor(58, 110, 165, 51))   # Middle (y=0): 20% opacity #3A6EA5
        grad.setColorAt(1.0, QColor(58, 110, 165, 140))  # Bottom (y=-1): 55% opacity #3A6EA5
        imb_brush = QBrush(grad)

        self.imb_curve = pg.PlotDataItem(pen=pg.mkPen("#5B9BD5", width=1.5),
                                         fillLevel=0,
                                         brush=imb_brush)
        p_imb.addItem(self.imb_curve)
        p_imb.addItem(pg.InfiniteLine(angle=0, pos=0, movable=False,
                                       pen=pg.mkPen("#9A9A9A", style=Qt.PenStyle.DashLine)),
                      ignoreBounds=True)
        p_imb.setYRange(-1, 1, padding=0)

        self.bid_curve = pg.PlotDataItem(pen=pg.mkPen("#388E3C", width=1.5))
        self.ask_curve = pg.PlotDataItem(pen=pg.mkPen("#D32F2F", width=1.5))
        p_depth.addItem(self.bid_curve); p_depth.addItem(self.ask_curve)

        # plain line, no fill — spread sits in a narrow band, so a fill to zero
        # would flood the pane and hide the variation
        self.spread_curve = pg.PlotDataItem(pen=pg.mkPen("#C9A227", width=1.2))
        p_spread.addItem(self.spread_curve)

        self.speed_curve = pg.PlotDataItem(pen=pg.mkPen("#7C6BAE", width=1.2),
                                           fillLevel=0,
                                           brush=pg.mkBrush(92, 75, 140, 102))
        p_speed.addItem(self.speed_curve)
        self.cvd_curve = pg.PlotDataItem(pen=pg.mkPen("#E0E0E0", width=1.5))
        self.cvd_vb = pg.ViewBox()
        p_speed.scene().addItem(self.cvd_vb)
        p_speed.getAxis("right").linkToView(self.cvd_vb)
        self.cvd_vb.setXLink(p_speed)
        self.cvd_vb.addItem(self.cvd_curve)
        p_speed.vb.sigResized.connect(self._sync_cvd)

    def _sync_cvd(self) -> None:
        self.cvd_vb.setGeometry(self.plots[3].vb.sceneBoundingRect())
        self.cvd_vb.linkedViewChanged(self.plots[3].vb, self.cvd_vb.XAxis)

    def _on_tf(self, txt: str) -> None:
        self.agg = TF.get(txt, 1)
        self.refresh()

    def refresh(self) -> None:
        cols = self.buffer.view(self.agg)
        if not cols:
            return
        cols = cols[-400:]                       # keep the panes responsive

        xs, ys = metrics.book_imbalance(cols)
        self.imb_curve.setData(xs, ys)

        xs2, bids, asks = metrics.depth_totals(cols)
        self.bid_curve.setData(xs2, bids)
        self.ask_curve.setData(xs2, asks)

        xs3, sp = metrics.spread_ticks(cols)
        self.spread_curve.setData(xs3, sp)
        if sp:
            self.plots[2].setYRange(0, max(sp) + 1, padding=0)

        xs4, vol = metrics.intensity(cols)
        self.speed_curve.setData(xs4, vol)
        xs5, cvd = metrics.cvd_series(cols)
        self.cvd_curve.setData(xs5, cvd)
        self._sync_cvd()

        if ys:
            imb = ys[-1]
            bias = "BID" if imb > 0.05 else ("ASK" if imb < -0.05 else "FLAT")
            imb_color = "#388E3C" if imb > 0.05 else ("#D32F2F" if imb < -0.05 else "#9A9A9A")
            cvd_val = cvd[-1] if cvd else 0
            cvd_color = "#388E3C" if cvd_val > 0 else ("#D32F2F" if cvd_val < 0 else "#E0E0E0")
            spread_val = sp[-1] if sp else 0
            self.lbl.setText(
                f"&nbsp;&nbsp;&nbsp;Imbalance: <span style='color:{imb_color}; font-family:\"JetBrains Mono\", monospace;'>{imb:+.2f} ({bias})</span>"
                f"&nbsp;&nbsp;&nbsp;&nbsp;Spread: <span style='color:#E0E0E0; font-family:\"JetBrains Mono\", monospace;'>{spread_val}t</span>"
                f"&nbsp;&nbsp;&nbsp;&nbsp;CVD: <span style='color:{cvd_color}; font-family:\"JetBrains Mono\", monospace;'>{cvd_val:+,}</span>"
            )
