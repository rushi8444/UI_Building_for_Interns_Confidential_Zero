"""Bookmap-style liquidity window: heatmap + BBO + glossy trade bubbles, with a
right-edge DOM depth ladder and a bottom volume histogram.

Interaction is TradingView-like:
  * left-drag pans, mouse-wheel zooms smoothly about the cursor,
  * while "following" it tracks the newest column and keeps YOUR zoom width,
  * any manual pan/zoom drops follow + price-autofit,
  * the Follow button or a double-click snaps back to live and re-fits price.
A timeframe selector aggregates the 1-second base columns (1s…1m).
"""

from __future__ import annotations

import time

import pyqtgraph as pg
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QMainWindow, QToolBar, QLabel, QComboBox, QPushButton

from ..engine import BookmapBuffer, SRTracker
from ..render import (
    BookHeatmapItem, BBOItem, BubbleItem, PieItem, BarsItem, ProjectionItem,
    DomLadderItem, VolumeBarsItem, SRLinesItem, DARK,
)

from ..render.bookmap import BOOKMAP_BG as BG
# label -> aggregation factor over the 1s base columns
TF = {"1s": 1, "2s": 2, "5s": 5, "10s": 10, "30s": 30, "1m": 60, "5m": 300, "10m": 600}


def _fmt(v: int) -> str:
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}M"
    if v >= 1000:
        return f"{v / 1000:.0f}K"
    return str(v)


class BookmapWindow(QMainWindow):
    def __init__(self, buffer: BookmapBuffer, tick: float, parent=None):
        super().__init__(parent)
        self.buffer = buffer
        self.tick = tick
        self.agg = 1
        self.setWindowTitle(f"Omnitrix Bookmap — {buffer.symbol}")
        self.resize(1500, 860)
        self._follow = True
        self._auto_y = True

        pg.setConfigOptions(useOpenGL=False, antialias=False)
        self._build_toolbar()
        self._build_plots()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(80)                 # ~12.5 fps data refresh
        self.refresh(initial=True)

    # ---- toolbar ---------------------------------------------------------
    def _build_toolbar(self) -> None:
        tb = QToolBar()
        tb.setMovable(False)
        self.addToolBar(tb)
        tb.addWidget(QLabel("  Timeframe "))
        self.tf_combo = QComboBox()
        self.tf_combo.addItems(list(TF))
        self.tf_combo.currentTextChanged.connect(self._on_tf)
        tb.addWidget(self.tf_combo)

        tb.addWidget(QLabel("   Type "))
        self.type_combo = QComboBox()
        self.type_combo.addItems(["Pie", "Bubbles", "Bars"])   # Pie = default
        self.type_combo.currentTextChanged.connect(self._on_style)
        tb.addWidget(self.type_combo)

        tb.addWidget(QLabel("   Min trade "))
        self.min_combo = QComboBox()
        self.min_combo.addItems(["All", "100", "250", "500", "1K", "2.5K", "5K", "10K"])
        # 500 was tuned against the dense synthetic tape; on a live feed quieter
        # symbols fall under it and their pies blink on/off as volume crosses
        # the threshold. 100 keeps the clustering benefit without that.
        self.min_combo.setCurrentText("100")
        self.min_combo.currentTextChanged.connect(self._on_minsize)
        tb.addWidget(self.min_combo)

        tb.addWidget(QLabel("   Walls "))
        self.wall_combo = QComboBox()
        self.wall_combo.addItems(["Sensitive", "Normal", "Strict"])
        self.wall_combo.setCurrentText("Normal")
        self.wall_combo.currentTextChanged.connect(self._on_wall)
        tb.addWidget(self.wall_combo)

        self.btn_follow = QPushButton("⏵ Follow")
        self.btn_follow.clicked.connect(self._reset_view)
        tb.addWidget(self.btn_follow)

        self.btn_sr = QPushButton("S/R Lines")
        self.btn_sr.setCheckable(True)
        self.btn_sr.setChecked(True)    # ON by default
        self.btn_sr.clicked.connect(self._on_sr_toggle)
        tb.addWidget(self.btn_sr)



        t = DARK
        self.setStyleSheet(
            f"QMainWindow {{ background-color:{t.bg}; }}"
            
            f" QToolBar {{ background-color:{t.panel}; border: none; border-bottom:1px solid {t.grid}; border-right:1px solid {t.grid}; padding:6px; spacing:8px; }}"
            f" QToolBar::separator {{ background-color:{t.grid}; width:1px; height:20px; margin:0px 6px; }}"
            
            f" QToolTip {{ background-color:{t.panel}; color:{t.text}; border:1px solid {t.grid}; border-radius:4px; padding:4px 8px; font-family:'Inter', 'Segoe UI', Arial, sans-serif; font-size:12px; font-weight:500; }}"
            f" QLabel {{ color:{t.text}; font-size:12px; font-weight:600; font-family:'Inter', sans-serif; }}"
            
            f" QCheckBox {{ color:{t.text}; font-size:12px; font-weight:600; spacing:6px; font-family:'Inter', sans-serif; }}"
            f" QCheckBox::indicator {{ width:14px; height:14px; border:1px solid {t.grid}; border-radius:3px; background-color:{t.bg}; }}"
            f" QCheckBox::indicator:checked {{ background-color:{t.bull}; border-color:{t.bull}; }}"
            
            f" QComboBox {{ background-color:rgba(42, 42, 42, 0.6); color:{t.text}; border:1px solid {t.grid}; border-radius:4px; padding:4px 10px; min-height:22px; font-size:12px; font-weight:500; font-family:'Inter', sans-serif; }}"
            f" QComboBox:hover {{ background-color:{t.grid}; }}"
            f" QComboBox::drop-down {{ border:none; width:0px; }}"
            f" QComboBox::down-arrow {{ image: none; }}"
            f" QComboBox QAbstractItemView {{ background-color:{t.panel}; color:{t.text}; border:1px solid {t.grid}; selection-background-color:{t.grid}; outline: none; }}"
            
            f" QPushButton {{ background-color:transparent; color:#8A8A8A; border:1px solid transparent; border-radius:4px; padding:6px 12px; font-weight:500; font-size:12px; font-family:'Inter', sans-serif; }}"
            f" QPushButton:hover {{ background-color:{t.grid}; color:{t.text}; }}"
            f" QPushButton:pressed {{ background-color:{t.grid}; color:{t.text}; }}"
            f" QPushButton:checked {{ background-color:{t.bull}; color:#ffffff; border-color:{t.bull}; font-weight:600; }}"
            f" QPushButton::menu-indicator {{ image: none; }}"
            
            f" QMenu {{ background-color:{t.panel}; color:{t.text}; border:1px solid {t.grid}; }}"
            f" QMenu::item {{ padding:6px 24px; }}"
            f" QMenu::item:selected {{ background-color:{t.grid}; }}"
            
            f" QDockWidget {{ color:{t.text}; titlebar-close-icon:none; titlebar-normal-icon:none; font-family:'Inter', sans-serif; }}"
            f" QDockWidget::title {{ background-color:{t.panel}; color:#8A8A8A; font-weight:700; font-size:11px; text-transform:uppercase; padding:8px 12px; border-bottom:1px solid {t.grid}; border-top:1px solid {t.grid}; }}"
            
            f" QTabBar::tab {{ background-color:{t.bg}; color:#8A8A8A; padding:8px 16px; border:1px solid {t.grid}; border-bottom:none; font-size:11px; font-weight:600; font-family:'Inter', sans-serif; }}"
            f" QTabBar::tab:selected {{ background-color:{t.panel}; color:{t.text}; border-top:2px solid {t.bull}; }}"
            f" QTabWidget::pane {{ border:1px solid {t.grid}; }}"
            
            f" QPushButton#sidebar_icon {{ font-size: 16px; border-radius: 4px; margin: 4px; color: #8A8A8A; border: none; background: transparent; }}"
            f" QPushButton#sidebar_icon:hover {{ background-color: #2A2A2A; color: #E8E8E8; }}"
            f" QPushButton#sidebar_icon_active {{ font-size: 16px; border-radius: 4px; margin: 4px; color: #26A69A; background-color: #2A2A2A; border: none; }}"
            f" QPushButton#sidebar_icon_danger {{ font-size: 16px; border-radius: 4px; margin: 4px; color: #8A8A8A; border: none; background: transparent; }}"
            f" QPushButton#sidebar_icon_danger:hover {{ background-color: #2A2A2A; color: #F23645; }}"
        )

    # ---- plots -----------------------------------------------------------
    def _build_plots(self) -> None:
        self.glw = pg.GraphicsLayoutWidget()
        self.glw.setBackground(BG)
        self.setCentralWidget(self.glw)

        self.main = self.glw.addPlot(row=0, col=0)
        self.main.showAxis("right"); self.main.hideAxis("left")
        self.main.hideAxis("bottom")
        self.main.showGrid(x=True, y=True, alpha=0.06)
        vb = self.main.getViewBox()
        vb.setMouseMode(pg.ViewBox.PanMode)          # left-drag pans
        vb.setMouseEnabled(x=True, y=True)

        self.dom = self.glw.addPlot(row=0, col=1)
        self.dom.hideAxis("left"); self.dom.showAxis("right")
        self.dom.hideAxis("bottom")
        self.dom.setYLink(self.main)
        self.dom.setMouseEnabled(x=False, y=False)

        self.vol_axis = TimeAxisSecs(orientation="bottom", win=self)
        self.vol = self.glw.addPlot(row=1, col=0, axisItems={"bottom": self.vol_axis})
        self.vol.hideAxis("left"); self.vol.showAxis("right")
        self.vol.setXLink(self.main)
        self.vol.setMouseEnabled(y=False)

        self.glw.ci.layout.setRowStretchFactor(0, 5)
        self.glw.ci.layout.setRowStretchFactor(1, 1)
        self.glw.ci.layout.setColumnStretchFactor(0, 14)
        self.glw.ci.layout.setColumnStretchFactor(1, 1)

        for plot in (self.main, self.dom, self.vol):
            for ax in ("right", "bottom"):
                a = plot.getAxis(ax)
                a.setPen(pg.mkPen(DARK.axis)); a.setTextPen(pg.mkPen(DARK.text))

        self.heat = BookHeatmapItem(self.tick)
        self.bbo = BBOItem(self.tick)
        self.bubbles = BubbleItem(self.tick, self.buffer)
        self.main.addItem(self.heat)
        self.main.addItem(self.bbo)
        self.main.addItem(self.bubbles)

        self.pie = PieItem(self.tick)
        self.bars = BarsItem(self.tick)
        self.main.addItem(self.pie)
        self.main.addItem(self.bars)

        self.bubbles.min_size = 100          # default noise filter (matches combo)
        self.pie.min_size = 100
        self.bars.min_size = 100
        self.style = "Pie"                   # Pie is the default view
        self.bubbles.setVisible(False)
        self.bars.setVisible(False)
        self.pie.setVisible(True)

        self.dom_item = DomLadderItem(self.tick)
        self.dom.addItem(self.dom_item)
        self.vol_item = VolumeBarsItem(self.tick)
        self.vol.addItem(self.vol_item)

        self.cursor = pg.InfiniteLine(angle=90, movable=False,
                                      pen=pg.mkPen("#E8C13A", width=1))
        self.main.addItem(self.cursor, ignoreBounds=True)
        self.price_line = pg.InfiniteLine(
            angle=0, movable=False,
            pen=pg.mkPen(DARK.cvd, width=1, style=Qt.PenStyle.DashLine),
            label="{value:.2f}",
            labelOpts={"position": 0.98, "color": "#0A0E16",
                       "fill": DARK.cvd, "movable": False})
        self.main.addItem(self.price_line, ignoreBounds=True)

        # resting limit orders projected as fat bands just ahead of price
        # (heatmap-coloured; strongest support GREEN, resistance RED).
        self.projection = ProjectionItem(self.tick)
        self.main.addItem(self.projection)
        self.proj_width = 7

        # Absolute support / resistance: the levels that have actually held,
        # drawn full width so price can be watched approaching them.
        self.sr = SRTracker()
        self.sr_item = SRLinesItem(self.tick)
        self.sr_item.setVisible(True)    # visible by default
        self.main.addItem(self.sr_item)

        # ---- crosshair with live price / time / liquidity readout ----
        self.cx_v = pg.InfiniteLine(angle=90, movable=False,
                                    pen=pg.mkPen("#666", width=1,
                                                 style=Qt.PenStyle.DashLine))
        self.cx_h = pg.InfiniteLine(
            angle=0, movable=False,
            pen=pg.mkPen("#666", width=1, style=Qt.PenStyle.DashLine),
            label="{value:.2f}",
            labelOpts={"position": 0.02, "color": "#E8E8E8",
                       "fill": "#2A2A2A", "movable": False})
        for ln in (self.cx_v, self.cx_h):
            ln.setVisible(False)
            self.main.addItem(ln, ignoreBounds=True)

        self.readout = pg.TextItem(anchor=(0, 0), color=DARK.text,
                                   fill=pg.mkBrush(28, 27, 27, 215))
        self.readout.setZValue(50)
        self.readout.setVisible(False)
        self.main.addItem(self.readout, ignoreBounds=True)

        vb.sigRangeChangedManually.connect(self._on_manual)
        self.glw.scene().sigMouseClicked.connect(self._on_click)
        self.glw.scene().sigMouseMoved.connect(self._on_mouse_move)

    # ---- interaction -----------------------------------------------------
    def _on_manual(self):
        vb = self.main.getViewBox()
        vr = vb.viewRect()
        cols = self.buffer.view(self.agg)
        
        # If they manually panned away from the live edge, stop following.
        # But if they just zoomed while near the live edge, keep following the x-axis, 
        # just disable auto_y so they keep their vertical zoom.
        if cols:
            latest = cols[-1]
            x_hi = latest.bucket + self.proj_width + 3
            if abs(vr.right() - x_hi) < max(5.0, (vr.right() - vr.left()) * 0.1):
                self._auto_y = False
                return

        self._follow = False
        self._auto_y = False
        self.btn_follow.setText("⏸ Live")

    def _on_click(self, ev):
        if ev.double():
            self._auto_y = True
            self._reset_view()

    def _on_mouse_move(self, pos) -> None:
        """Crosshair + readout: price, clock time, resting size at that price
        and its distance from the last trade."""
        vb = self.main.getViewBox()
        if not self.main.sceneBoundingRect().contains(pos):
            for it in (self.cx_v, self.cx_h, self.readout):
                it.setVisible(False)
            return
        mp = vb.mapSceneToView(pos)
        price, x = mp.y(), mp.x()
        self.cx_v.setPos(x)
        self.cx_h.setPos(price)

        ti = int(round(price / self.tick))
        cols = self.buffer.view(self.agg)
        latest = cols[-1] if cols else None

        secs = x * self.buffer.col_dt * self.agg
        when = time.strftime("%H:%M:%S", time.localtime(secs))

        size = latest.book.get(ti, 0) if latest and latest.book else 0
        lines = [f"{price:,.{self._dp()}f}   {when}"]
        if size:
            side = ""
            if latest.ask_ti is not None and ti >= latest.ask_ti:
                side = " ask"
            elif latest.bid_ti is not None and ti <= latest.bid_ti:
                side = " bid"
            lines.append(f"resting {size:,}{side}")
        if latest is not None and latest.bid_ti is not None \
                and latest.ask_ti is not None:
            mid = (latest.bid_ti + latest.ask_ti) / 2 * self.tick
            d = price - mid
            lines.append(f"{d:+,.{self._dp()}f} from last")

        self.readout.setText("\n".join(lines))
        self.readout.setPos(x, price)
        for it in (self.cx_v, self.cx_h, self.readout):
            it.setVisible(True)

    def _dp(self) -> int:
        """Decimal places implied by the tick size."""
        t = self.tick
        if t >= 1:
            return 0
        return max(0, min(6, len(f"{t:.6f}".rstrip('0').split('.')[-1])))

    def _reset_view(self):
        self._follow = True
        # We don't force _auto_y = True here so the user keeps their vertical zoom!
        # Double-clicking the chart will re-enable _auto_y.
        self.btn_follow.setText("⏵ Follow")
        self.refresh()


    def _on_tf(self, txt: str):
        self.agg = TF.get(txt, 1)
        self._reset_view()

    def _on_minsize(self, txt: str):
        mult = {"All": 0, "100": 100, "250": 250, "500": 500, "1K": 1000,
                "2.5K": 2500, "5K": 5000, "10K": 10000}
        m = mult.get(txt, 0)
        self.bubbles.min_size = self.pie.min_size = self.bars.min_size = m
        self.bubbles.update(); self.pie.update(); self.bars.update()

    def _on_wall(self, txt: str):
        mult, floor = {"Sensitive": (2.5, 2000),
                       "Normal": (4.0, 4000),
                       "Strict": (7.0, 10000)}.get(txt, (4.0, 4000))
        self.projection.wall_mult = mult
        self.projection.wall_floor = floor
        self.projection.update()

    def _on_style(self, txt: str):
        self.style = txt
        self.bubbles.setVisible(txt == "Bubbles")
        self.pie.setVisible(txt == "Pie")
        self.bars.setVisible(txt == "Bars")
        self.refresh()

    def _on_sr_toggle(self) -> None:
        """Show or hide the full-width S/R level lines."""
        enabled = self.btn_sr.isChecked()
        self.sr_item.setVisible(enabled)
        if not enabled:
            # Clear stale lines immediately when toggled off
            self.sr_item.set_levels([], [], 0, 0)

    # ---- data + view -----------------------------------------------------
    def refresh(self, initial: bool = False) -> None:
        cols = self.buffer.view(self.agg)
        if not cols:
            return
        self.heat.set_cols(cols)
        self.bbo.set_cols(cols)
        self.bubbles.xscale = 1.0 / self.agg
        if self.style == "Bubbles":
            self.bubbles.set_cols(cols)
        elif self.style == "Pie":
            self.pie.set_cols(cols)
        else:
            self.bars.set_cols(cols)
        self.vol_item.set_cols(cols)
        latest = cols[-1]
        # The newest column may have been created by a trade and carry no book;
        # fall back to the newest one that does so the DOM/projection hold.
        book_col = latest if latest.book else (self.buffer.latest_book() or latest)
        self.dom_item.set_col(book_col, self.tick)
        self.cursor.setPos(latest.bucket + 1)

        mid_ti = None
        if latest.bid_ti is not None and latest.ask_ti is not None:
            mid_ti = (latest.bid_ti + latest.ask_ti) / 2
        elif self.buffer.trades:
            mid_ti = self.buffer.trades[-1][1]
        if mid_ti is not None:
            self.price_line.setPos(mid_ti * self.tick)

        # project the resting book as fat bands just ahead of the latest pie
        vmax = 1
        for c in cols[-60:]:
            if c.book:
                m = max(c.book.values())
                if m > vmax:
                    vmax = m
        self.projection.set_projection(book_col, latest.bucket + 1, mid_ti, vmax)

        # Persistence-weighted S/R, shared by the projection bands and the
        # full-width lines so the two always name the same levels.
        sup, res, walls = self.sr.update(cols, mid_ti)
        self.projection.set_sr(sup, res)
        if self.btn_sr.isChecked():
            self.sr_item.set_levels(sup, res, cols[0].bucket,
                                    latest.bucket + self.proj_width + 1,
                                    walls=walls, mid_ti=mid_ti)

        if book_col.book:
            # Exact, no margin: the ladder's bars are right-anchored at mx, so
            # the deepest level must land flush against the price axis.
            mx = max(book_col.book.values()) or 1
            self.dom.setXRange(0, mx, padding=0)

        if initial or self._follow:
            width = self._view_width(cols, default=60)
            x_hi = latest.bucket + self.proj_width + 3    # room for projection
            self.main.setXRange(x_hi - width, x_hi, padding=0)
        if initial or self._auto_y:
            self._fit_price(cols)

    def _view_width(self, cols, default: int) -> float:
        try:
            r = self.main.getViewBox().viewRange()[0]
            w = r[1] - r[0]
            return w if w > 2 else default
        except Exception:
            return default

    def _fit_price(self, cols) -> None:
        """Follow the traded price path and pad it with ~16 ticks of context
        each side, so resting walls above/below (support/resistance) stay in
        frame without the deep book shrinking the pies."""
        width = int(self._view_width(cols, default=60))
        vis = cols[-width:] if len(cols) > width else cols
        lo = hi = None
        for c in vis:
            if c.bid_ti is not None and c.ask_ti is not None:
                m = (c.bid_ti + c.ask_ti) / 2
                lo = m if lo is None else min(lo, m)
                hi = m if hi is None else max(hi, m)
        if lo is None:                       # fallback: full book range
            for c in vis:
                for ti in (c.book or {}):
                    lo = ti if lo is None else min(lo, ti)
                    hi = ti if hi is None else max(hi, ti)
            if lo is None:
                return
        pad = max(35.0, (hi - lo) * 1.0) * self.tick
        y0, y1 = lo * self.tick - pad, hi * self.tick + pad

        # Hysteresis: re-fitting on every 80ms refresh made the chart micro-jitter
        # as price wobbled. Only move the view when it drifts meaningfully.
        prev = getattr(self, "_y_range", None)
        if prev is not None:
            span = max(1e-9, prev[1] - prev[0])
            if (abs(y0 - prev[0]) / span < 0.04 and
                    abs(y1 - prev[1]) / span < 0.04):
                return
        self._y_range = (y0, y1)
        self.main.setYRange(y0, y1, padding=0)


class TimeAxisSecs(pg.AxisItem):
    """Formats aggregated column-bucket x values as HH:MM:SS."""

    def __init__(self, *a, win=None, **k):
        super().__init__(*a, **k)
        self.win = win

    def tickStrings(self, values, scale, spacing):
        import time
        dt = (self.win.buffer.col_dt * self.win.agg) if self.win else 1.0
        res = []
        for v in values:
            try:
                sec = float(v * dt)
                if sec < 0:
                    res.append("")
                else:
                    res.append(time.strftime("%H:%M:%S", time.localtime(sec)))
            except Exception:
                res.append("")
        return res
