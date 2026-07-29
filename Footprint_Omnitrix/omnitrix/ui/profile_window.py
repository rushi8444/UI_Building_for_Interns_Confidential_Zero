"""Market Profile window: TPO (time-price opportunity) beside the session
Volume Profile, sharing one price axis — the classic institutional read of
*where the market spent time* vs *where size actually traded*.
"""

from __future__ import annotations

import pyqtgraph as pg
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QMainWindow, QToolBar, QLabel, QComboBox, QPushButton,
)

from ..render import TPOItem, VolumeProfileItem, DARK

BG = "#131313"


class ProfileWindow(QMainWindow):
    def __init__(self, profile, tick: float, parent=None):
        super().__init__(parent)
        self.profile = profile
        self.tick = tick
        self.va_pct = 0.70
        self.setWindowTitle(f"Omnitrix Market Profile — {profile.symbol}")
        self.resize(1180, 900)

        pg.setConfigOptions(useOpenGL=False, antialias=False)
        self._build_toolbar()
        self._build_plots()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(400)
        self.refresh()

    def _build_toolbar(self) -> None:
        tb = QToolBar(); tb.setMovable(False); self.addToolBar(tb)
        tb.addWidget(QLabel("  Value area "))
        self.va_combo = QComboBox()
        self.va_combo.addItems(["60%", "68%", "70%", "80%"])
        self.va_combo.setCurrentText("70%")
        self.va_combo.currentTextChanged.connect(self._on_va)
        tb.addWidget(self.va_combo)
        tb.addWidget(QLabel("   TPO "))
        self.tpo_combo = QComboBox()
        self.tpo_combo.addItems(["Profile", "Split by bracket"])
        self.tpo_combo.currentTextChanged.connect(self._on_tpo_mode)
        tb.addWidget(self.tpo_combo)

        self.btn_fit = QPushButton("\ue3b4")
        self.btn_fit.setToolTip("Fit")
        self.btn_fit.setStyleSheet("font-family: 'Material Symbols Outlined'; font-size: 20px; background: transparent; color: #8A8A8A; border: none;")
        self.btn_fit.clicked.connect(self._fit)
        tb.addWidget(self.btn_fit)
        self.lbl = QLabel("   ")
        tb.addWidget(self.lbl)
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

    def _build_plots(self) -> None:
        self.glw = pg.GraphicsLayoutWidget()
        self.glw.setBackground(BG)
        self.setCentralWidget(self.glw)

        self.tpo_plot = self.glw.addPlot(row=0, col=0)
        self.tpo_plot.hideAxis("left"); self.tpo_plot.showAxis("right")
        self.tpo_plot.setLabel("bottom", "TPO brackets (30m)")
        self.tpo_plot.showGrid(x=False, y=True, alpha=0.12)

        self.vp_plot = self.glw.addPlot(row=0, col=1)
        self.vp_plot.hideAxis("left"); self.vp_plot.showAxis("right")
        self.vp_plot.setLabel("bottom", "Volume @ price")
        self.vp_plot.showGrid(x=False, y=True, alpha=0.12)
        self.vp_plot.setYLink(self.tpo_plot)
        self.vp_plot.setMouseEnabled(x=False)

        self.glw.ci.layout.setColumnStretchFactor(0, 3)
        self.glw.ci.layout.setColumnStretchFactor(1, 2)

        for plot in (self.tpo_plot, self.vp_plot):
            for ax in ("right", "bottom"):
                a = plot.getAxis(ax)
                a.setPen(pg.mkPen(DARK.axis)); a.setTextPen(pg.mkPen(DARK.text))

        self.tpo_item = TPOItem(self.tick)
        self.tpo_plot.addItem(self.tpo_item)
        self.vp_item = VolumeProfileItem(self.tick)
        self.vp_plot.addItem(self.vp_item)

        # POC / VAH / VAL guides on the TPO pane
        self.poc_line = pg.InfiniteLine(angle=0, movable=False,
                                        pen=pg.mkPen("#FFC43C", width=2))
        self.vah_line = pg.InfiniteLine(angle=0, movable=False,
                                        pen=pg.mkPen("#78BEFF", width=1,
                                                     style=Qt.PenStyle.DashLine))
        self.val_line = pg.InfiniteLine(angle=0, movable=False,
                                        pen=pg.mkPen("#78BEFF", width=1,
                                                     style=Qt.PenStyle.DashLine))
        for ln in (self.poc_line, self.vah_line, self.val_line):
            self.tpo_plot.addItem(ln, ignoreBounds=True)

    def _on_va(self, txt: str) -> None:
        self.va_pct = float(txt.rstrip("%")) / 100.0
        self.refresh()

    def _on_tpo_mode(self, txt: str) -> None:
        self.tpo_item.set_collapsed(txt == "Profile")
        self.refresh()
        self._fit()

    def refresh(self) -> None:
        prof = self.profile
        a = prof.analytics(self.va_pct)
        rows = prof.tpo_rows()
        br = prof.bracket_range()
        if not rows or br is None:
            return
        self.tpo_item.set_data(rows, br[0], a["poc"], a["vah"], a["val"])
        self.vp_item.set_data(prof.buy, prof.sell, a["poc"], a["vah"],
                              a["val"], a["hvn"])
        if a["poc"] is not None:
            self.poc_line.setPos(a["poc"] * self.tick)
            self.vah_line.setPos(a["vah"] * self.tick)
            self.val_line.setPos(a["val"] * self.tick)
            self.lbl.setText(
                f"   POC {a['poc'] * self.tick:.2f}   "
                f"VAH {a['vah'] * self.tick:.2f}   "
                f"VAL {a['val'] * self.tick:.2f}   "
                f"Total {prof.total:,}")

    def _fit(self) -> None:
        a = self.profile.analytics(self.va_pct)
        tot = a["totals"]
        if not tot:
            return
        lo, hi = min(tot) * self.tick, max(tot) * self.tick
        pad = (hi - lo) * 0.04 or self.tick
        self.tpo_plot.setYRange(lo - pad, hi + pad, padding=0)
        w = self.tpo_item.boundingRect().width()
        if w > 0:
            self.tpo_plot.setXRange(0, w, padding=0)
        self.vp_plot.setXRange(0, 1.02, padding=0)
