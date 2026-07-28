"""Main ATAS-style window: footprint price pane + cumulative-delta pane,
fed by any engine Feed via a thread-safe queue drained on the GUI thread.
"""

from __future__ import annotations

from collections import deque
from dataclasses import replace

import pyqtgraph as pg
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QMainWindow, QToolBar, QLabel, QComboBox, QCheckBox, QPushButton, QWidget,
    QSizePolicy, QDockWidget, QHBoxLayout, QVBoxLayout, QFrame, QButtonGroup, QMenu,
)

from ..engine import (
    Instruments, BarSeries, BookmapBuffer, SessionProfile, Feed,
)
from ..engine.model import Trade, BookSnapshot
from ..render import (
    FootprintItem, HeatmapItem, DARK, LIGHT, TimeAxis,
    FibRetracement, PositionDrawer, FixedVolumeProfile, EMAItem, CPRItem
)
from .settings_dialog import SettingsDialog
from .bookmap_window import BookmapWindow
from .profile_window import ProfileWindow
from .analytics_window import AnalyticsWindow
from .monitor_window import MarketMonitorWindow
from .dom_ladder import DomLadderWindow
from . import workspace
from .tape_widget import TapeWidget
from .stats_panel import StatsPanel
from .signals_panel import SignalsPanel
from .data_window import DataWindowWidget, CandleHoverPopup

TF_CHOICES = {
    "10s": 10, "30s": 30, "1m": 60, "2m": 120, "3m": 180, "5m": 300,
    "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400,
}

# mode -> (footprint mode, draw footprint cells, heatmap visible)
MODES = {
    "Footprint": ("Footprint", True, False),
    "Cluster": ("Cluster", True, False),
    "Profile": ("Profile", True, False),
    "Delta": ("Delta", True, False),
    "Heatmap": ("Footprint", False, True),
    "Footprint + Heatmap": ("Footprint", True, True),
    "Cluster + Heatmap": ("Cluster", True, True),
}


class OmnitrixWindow(QMainWindow):
    def __init__(self, feed: Feed, instruments: Instruments | None = None):
        super().__init__()
        self.setWindowTitle("Omnitrix — Order Flow Terminal")
        self.resize(1680, 940)

        self.instruments = instruments or Instruments(default_tick=0.01)
        self.feed = feed
        self.series: dict[str, BarSeries] = {}
        self.bookmaps: dict[str, BookmapBuffer] = {}
        self.profiles: dict[str, SessionProfile] = {}
        self._bookmap_windows: list = []
        self.latest_book: dict[str, BookSnapshot] = {}
        self.active_symbol = ""
        self.tf_s = 60
        self.theme = DARK
        self.auto_scroll = True
        self._dirty = False
        self._centered_once = False
        self._known_symbols: set[str] = set()

        # thread-safe hand-off: feed thread appends, GUI timer drains.
        # ONE queue keeps trades and books in their true time order, so a book
        # always routes to a bar the preceding trades already created.
        self._event_q: deque = deque()

        # Custom footprint painting is viewport-culled, so GL buys nothing and
        # only adds driver-dependent bugs. Software raster is crisp + portable.
        pg.setConfigOptions(useOpenGL=False, antialias=False)
        self._build_ui()
        self._apply_theme()

        feed.on_trade(self._event_q.append)
        feed.on_book(self._event_q.append)
        feed.start()

        self._pending_symbol = ""
        workspace.restore(self)               # reapply the last saved desk

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)                 # ~30 fps drain + redraw

    def _build_ui(self) -> None:
        import os
        from PyQt6.QtGui import QFontDatabase, QFont
        font_path = os.path.join(os.path.dirname(__file__), "..", "render", "MaterialSymbolsOutlined.ttf")
        QFontDatabase.addApplicationFont(font_path)

        # ---- Top Navbar (Custom Widget inside QToolBar) ----
        tb = QToolBar()
        tb.setObjectName("header_toolbar")
        tb.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)

        navbar = QWidget()
        navbar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        nav_layout = QHBoxLayout(navbar)
        nav_layout.setContentsMargins(16, 0, 16, 0)
        nav_layout.setSpacing(16)

        # Left Section
        left_sec = QWidget()
        left_layout = QHBoxLayout(left_sec)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)

        # Brand
        brand_w = QWidget()
        bl = QHBoxLayout(brand_w)
        bl.setContentsMargins(0,0,0,0)
        bl.setSpacing(4)
        lbl_icon = QLabel("\uf190")
        lbl_icon.setStyleSheet("color:#26A69A; font-family: 'Material Symbols Outlined'; font-size: 18px;")
        lbl_txt = QLabel("Omnitrix Order Flow")
        lbl_txt.setStyleSheet("color:#E8E8E8; font-weight:bold; font-size:13px;")
        bl.addWidget(lbl_icon)
        bl.addWidget(lbl_txt)
        left_layout.addWidget(brand_w)

        # Separator Line (vertical)
        vsep1 = QFrame()
        vsep1.setFrameShape(QFrame.Shape.VLine)
        vsep1.setStyleSheet("color: #2A2A2A;")
        left_layout.addWidget(vsep1)

        # Symbol
        sym_lbl = QLabel("\uef7a")
        sym_lbl.setStyleSheet("color:#26A69A; font-family: 'Material Symbols Outlined'; font-size: 18px;")
        left_layout.addWidget(sym_lbl)
        self.sym_combo = QComboBox()
        self.sym_combo.setMinimumWidth(80)
        self.sym_combo.currentTextChanged.connect(self._on_symbol)
        left_layout.addWidget(self.sym_combo)
        # Timeframe
        lbl_tf = QLabel("TF")
        lbl_tf.setStyleSheet("color:#8A8A8A; font-size:12px; margin-left: 8px;")
        left_layout.addWidget(lbl_tf)
        
        self.tf_combo = QComboBox()
        self.tf_combo.addItems(["10s", "30s", "1m", "5m", "15m", "1h"])
        self.tf_combo.setCurrentText("1m")
        self.tf_combo.currentTextChanged.connect(self._on_tf)
        left_layout.addWidget(self.tf_combo)

        # Separator
        vsep2 = QFrame()
        vsep2.setFrameShape(QFrame.Shape.VLine)
        vsep2.setStyleSheet("color: #2A2A2A; margin-left: 8px;")
        left_layout.addWidget(vsep2)

        # Modes Dropdown
        lbl_mode = QLabel("Mode")
        lbl_mode.setStyleSheet("color:#8A8A8A; font-size:12px; margin-left: 8px;")
        left_layout.addWidget(lbl_mode)
        
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(list(MODES))
        self.mode_combo.currentTextChanged.connect(self._on_mode)
        left_layout.addWidget(self.mode_combo)

        # Indicators menu
        btn_ind = QPushButton("Indicators")
        btn_ind.setStyleSheet("color:#E8E8E8; font-family: 'Inter', sans-serif; background-color:rgba(42, 42, 42, 0.6); border:1px solid #2A2A2A; padding: 4px 16px; border-radius: 4px; font-weight: 500; font-size: 12px;")
        menu_ind = QMenu(self)
        btn_ind.setMenu(menu_ind)
        left_layout.addWidget(btn_ind)

        # Add all indicators to the menu instead of cluttering the bar
        self.chk_imb = QCheckBox("Imbalance")
        self.chk_imb.setChecked(True)
        self.chk_imb.toggled.connect(lambda v: self.fp.set_show_imbalance(v))
        self.chk_imb.hide()
        
        self.imb_combo = QComboBox()
        self.imb_combo.addItems(["2.0", "3.0", "4.0", "5.0"])
        self.imb_combo.setCurrentText("3.0")
        self.imb_combo.currentTextChanged.connect(lambda s: self.fp.set_imbalance_factor(float(s)))
        self.imb_combo.hide()
        
        self.chk_va = QCheckBox("Value Area")
        self.chk_va.setChecked(True)
        self.chk_va.toggled.connect(lambda v: self.fp.set_show_va(v))
        self.chk_va.hide()
        
        self.chk_vwap = QCheckBox("VWAP")
        self.chk_vwap.setChecked(True)
        self.chk_vwap.toggled.connect(self._on_vwap_toggled)
        self.chk_vwap.hide()
        
        self.chk_cpr = QCheckBox("CPR")
        self.chk_cpr.setChecked(False)
        self.chk_cpr.toggled.connect(self._on_cpr_toggled)
        self.chk_cpr.hide()
        
        self.chk_ema = QCheckBox("EMAs")
        self.chk_ema.setChecked(False)
        self.chk_ema.toggled.connect(self._on_ema_toggled)
        self.chk_ema.hide()

        act_imb = menu_ind.addAction("Imbalance")
        act_imb.setCheckable(True)
        act_imb.setChecked(True)
        act_imb.toggled.connect(self.chk_imb.setChecked)
        
        act_va = menu_ind.addAction("Value Area")
        act_va.setCheckable(True)
        act_va.setChecked(True)
        act_va.toggled.connect(self.chk_va.setChecked)
        
        act_vwap = menu_ind.addAction("VWAP")
        act_vwap.setCheckable(True)
        act_vwap.setChecked(True)
        act_vwap.toggled.connect(self.chk_vwap.setChecked)

        act_cpr = menu_ind.addAction("CPR")
        act_cpr.setCheckable(True)
        act_cpr.toggled.connect(self.chk_cpr.setChecked)
        
        act_ema = menu_ind.addAction("EMAs")
        act_ema.setCheckable(True)
        act_ema.toggled.connect(self.chk_ema.setChecked)

        nav_layout.addWidget(left_sec)
        
        # Spacer for justify-between
        nav_layout.addStretch()

        # Right Section
        right_sec = QWidget()
        right_layout = QHBoxLayout(right_sec)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(16)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dark", "Light"])
        self.theme_combo.currentTextChanged.connect(self._on_theme)
        self.theme_combo.hide()

        btn_theme = QPushButton("\ue518")
        btn_theme.setToolTip("Toggle Theme")
        btn_theme.setStyleSheet("font-family: 'Material Symbols Outlined'; font-size: 20px; background: transparent; border: none;")
        btn_theme.clicked.connect(lambda: self.theme_combo.setCurrentText("Light" if self.theme_combo.currentText()=="Dark" else "Dark"))
        right_layout.addWidget(btn_theme)

        vsep3 = QFrame()
        vsep3.setFrameShape(QFrame.Shape.VLine)
        vsep3.setStyleSheet("color: #2A2A2A;")
        right_layout.addWidget(vsep3)

        btn_tools = QPushButton("\uea3c")
        btn_tools.setStyleSheet("font-family: 'Material Symbols Outlined'; font-size: 20px; background: transparent; color: #8A8A8A; border: none;")
        btn_tools.setToolTip("Tools")
        menu_tools = QMenu(self)
        btn_tools.setMenu(menu_tools)
        
        act_bm = menu_tools.addAction("Bookmap")
        act_bm.triggered.connect(self._open_bookmap)
        act_pr = menu_tools.addAction("Profile")
        act_pr.triggered.connect(self._open_profile)
        act_an = menu_tools.addAction("Analytics")
        act_an.triggered.connect(self._open_analytics)
        act_mo = menu_tools.addAction("Monitor")
        act_mo.triggered.connect(self._open_monitor)
        act_dom = menu_tools.addAction("DOM")
        act_dom.triggered.connect(self._open_dom)
        right_layout.addWidget(btn_tools)

        btn_fullscreen = QPushButton("\ue5d0")
        btn_fullscreen.setToolTip("Full-Screen Mode (F11)")
        btn_fullscreen.setStyleSheet("font-family: 'Material Symbols Outlined'; font-size: 20px; background: transparent; color: #8A8A8A; border: none;")
        btn_fullscreen.clicked.connect(self._toggle_fullscreen)
        self.btn_fullscreen = btn_fullscreen
        right_layout.addWidget(btn_fullscreen)

        btn_center = QPushButton("\ue3b4")
        btn_center.setToolTip("Center")
        btn_center.setStyleSheet("font-family: 'Material Symbols Outlined'; font-size: 20px; background: transparent; color: #8A8A8A; border: none;")
        btn_center.clicked.connect(self._center)
        right_layout.addWidget(btn_center)

        btn_settings = QPushButton("\ue8b8")
        btn_settings.setToolTip("Settings")
        btn_settings.setStyleSheet("font-family: 'Material Symbols Outlined'; font-size: 20px; background: transparent; color: #8A8A8A; border: none;")
        btn_settings.clicked.connect(self._open_settings)
        right_layout.addWidget(btn_settings)

        self.lbl_link = QLabel("Disconnected")
        self.lbl_link.setStyleSheet("color:#8A8A8A; font-weight:600;")
        right_layout.addWidget(self.lbl_link)

        nav_layout.addWidget(right_sec)
        tb.addWidget(navbar)

        # Stats lbl hidden but initialized
        self.lbl_stats = QLabel("")
        self.lbl_stats.hide()

        # ---- Drawing Toolbar (Left Sidebar) ----
        dtb = QToolBar("Drawings")
        dtb.setObjectName("drawing_toolbar")
        dtb.setMovable(False)
        dtb.setOrientation(Qt.Orientation.Vertical)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, dtb)
        
        self.active_drawing_tool = None
        self.drawing_items = []
        self._drawing_start_point = None

        self._drawing_buttons = {}

        def add_dtb_btn(icon, tooltip, tool_name):
            btn = QPushButton(icon)
            btn.setObjectName("sidebar_icon")
            btn.setToolTip(tooltip)
            btn.setFixedSize(38, 38)
            btn.setFont(QFont("Material Symbols Outlined", 18))
            btn.setStyleSheet("color: #8A8A8A; background: transparent; border: 1px solid transparent; border-radius: 4px;")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, t=tool_name: self._set_drawing_tool(t))
            dtb.addWidget(btn)
            self._drawing_buttons[tool_name] = btn
            return btn

        btn_cursor = add_dtb_btn("\ue836", "Cursor", None)
        btn_cursor.setObjectName("sidebar_icon_active")

        add_dtb_btn("\ue26b", "Fib Retracement", "Fib")
        add_dtb_btn("\ue8e5", "Long Position", "Long")
        add_dtb_btn("\ue8e3", "Short Position", "Short")
        add_dtb_btn("\ue24b", "Volume Profile", "VP")
        
        dtb.addSeparator()
        
        btn_clear = QPushButton("\ue872")
        btn_clear.setObjectName("sidebar_icon_danger")
        btn_clear.setToolTip("Clear Drawings")
        btn_clear.setFixedSize(38, 38)
        btn_clear.setFont(QFont("Material Symbols Outlined", 18))
        btn_clear.setStyleSheet("color: #8A8A8A; background: transparent; border: 1px solid transparent; border-radius: 4px;")
        btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_clear.clicked.connect(self._clear_drawings)
        dtb.addWidget(btn_clear)

        # ---- two linked panes: price (top), CVD (bottom) ----
        self.glw = pg.GraphicsLayoutWidget()
        self.setCentralWidget(self.glw)

        self.price_plot = self.glw.addPlot(row=0, col=0)
        self.price_plot.showAxis("right")
        self.price_plot.hideAxis("left")
        self.price_plot.hideAxis("bottom")     # time labels live on the CVD pane
        self.price_plot.showGrid(x=True, y=True, alpha=0.25)

        self.time_axis = TimeAxis(orientation="bottom")
        self.cvd_plot = self.glw.addPlot(row=1, col=0,
                                         axisItems={"bottom": self.time_axis})
        self.cvd_plot.showAxis("right")
        self.cvd_plot.hideAxis("left")
        self.cvd_plot.showGrid(x=True, y=True, alpha=0.2)
        self.cvd_plot.setXLink(self.price_plot)
        self.glw.ci.layout.setRowStretchFactor(0, 4)
        self.glw.ci.layout.setRowStretchFactor(1, 1)

        self.heatmap = HeatmapItem(self.instruments.tick("QQQ"))
        self.heatmap.setVisible(False)
        self.price_plot.addItem(self.heatmap)

        self.fp = FootprintItem(self.instruments.tick("QQQ"), self.theme)
        self.price_plot.addItem(self.fp)

        # Indicators
        self.cpr_item = CPRItem()
        self.cpr_item.setVisible(False)
        self.price_plot.addItem(self.cpr_item)

        self.ema9_item = EMAItem(period=9, color=QColor(33, 150, 243))
        self.ema21_item = EMAItem(period=21, color=QColor(255, 193, 7))
        self.ema9_item.setVisible(False)
        self.ema21_item.setVisible(False)
        self.price_plot.addItem(self.ema9_item)
        self.price_plot.addItem(self.ema21_item)

        self.vwap_curve = pg.PlotDataItem(pen=pg.mkPen(self.theme.vwap, width=2))
        self.price_plot.addItem(self.vwap_curve)

        # VWAP standard-deviation bands (±1σ, ±2σ) — institutional mean-reversion
        # envelope; price outside ±2σ is statistically stretched.
        self.vwap_bands = []
        for mult, alpha, dash in ((1, 150, Qt.PenStyle.DashLine),
                                  (2, 90, Qt.PenStyle.DotLine)):
            for _ in range(2):                    # upper + lower
                c = pg.PlotDataItem(pen=pg.mkPen(self.theme.vwap, width=1,
                                                 style=dash))
                c.setOpacity(alpha / 255.0)
                self.price_plot.addItem(c)
                self.vwap_bands.append((mult, c))

        self.cvd_curve = pg.PlotDataItem(pen=pg.mkPen(self.theme.cvd, width=2))
        self.cvd_plot.addItem(self.cvd_curve)
        self.cvd_zero = pg.InfiniteLine(angle=0, pos=0, movable=False,
                                        pen=pg.mkPen("#666", style=Qt.PenStyle.DashLine))
        self.cvd_plot.addItem(self.cvd_zero, ignoreBounds=True)

        self.price_line = pg.InfiniteLine(angle=0, movable=False,
                                          pen=pg.mkPen(self.theme.cvd, width=1,
                                                       style=Qt.PenStyle.DashLine))
        self.price_plot.addItem(self.price_line, ignoreBounds=True)
        self.vline = pg.InfiniteLine(angle=90, movable=False,
                                     pen=pg.mkPen("#666", style=Qt.PenStyle.DashLine))
        self.hline = pg.InfiniteLine(angle=0, movable=False,
                                     pen=pg.mkPen("#666", style=Qt.PenStyle.DashLine))
        self.price_plot.addItem(self.vline, ignoreBounds=True)
        self.price_plot.addItem(self.hline, ignoreBounds=True)

        self.glw.scene().sigMouseMoved.connect(self._on_mouse_move)
        self.glw.scene().sigMouseClicked.connect(self._on_mouse_click)
        self.price_plot.getViewBox().sigRangeChangedManually.connect(self._on_view)

        # ---- Time & Sales tape dock (right) ----
        self.tape = TapeWidget(
            get_source=lambda: (self.bookmaps.get(self.active_symbol).trades
                                if self.active_symbol in self.bookmaps else None),
            tick_fn=lambda: self.instruments.tick(self.active_symbol or "QQQ"),
        )
        self.stats = StatsPanel(self)
        self.stats_dock = QDockWidget("Session Statistics", self)
        self.stats_dock.setWidget(self.stats)
        self.stats_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea |
                                        Qt.DockWidgetArea.RightDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.stats_dock)

        self.tape_dock = QDockWidget("Time & Sales", self)
        self.tape_dock.setWidget(self.tape)
        self.tape_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea |
                                       Qt.DockWidgetArea.LeftDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.tape_dock)

        self.signals = SignalsPanel(self)
        self.signals_dock = QDockWidget("Order-Flow Signals", self)
        self.signals_dock.setWidget(self.signals)
        self.signals_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea |
                                          Qt.DockWidgetArea.LeftDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.signals_dock)

        self.hover_popup = CandleHoverPopup(self)
        self._pending_hover_data = None
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(100) # 100ms pause threshold
        self._hover_timer.timeout.connect(self._show_hover_popup)

        self.tabifyDockWidget(self.tape_dock, self.signals_dock)
        self.signals_dock.raise_()

    # ---- theme -----------------------------------------------------------
    def _apply_theme(self) -> None:
        t = self.theme
        self.fp.set_theme(t)
        self.vwap_curve.setPen(pg.mkPen(t.vwap, width=2))
        self.cvd_curve.setPen(pg.mkPen(t.cvd, width=2))
        self.glw.setBackground(t.bg)
        self.setStyleSheet(
            f"QMainWindow {{ background-color:{t.bg}; }}"
            
            f" QToolBar {{ background-color:{t.panel}; border: none; border-bottom:1px solid {t.grid}; border-right:1px solid {t.grid}; padding:6px; spacing:8px; }}"
            f" QToolBar::separator:horizontal {{ background-color:{t.grid}; width:1px; height:20px; margin:0px 6px; }}"
            f" QToolBar::separator:vertical {{ background-color:{t.grid}; height:1px; margin:8px 6px; }}"
            
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
            
            f" QPushButton#sidebar_icon {{ font-family: 'Material Symbols Outlined'; font-size: 20px; padding: 0px; margin: 2px; border-radius: 6px; color: #8A8A8A; border: 1px solid transparent; background: transparent; }}"
            f" QPushButton#sidebar_icon:hover {{ background-color: #2A2A2A; color: #E8E8E8; }}"
            f" QPushButton#sidebar_icon_active {{ font-family: 'Material Symbols Outlined'; font-size: 20px; padding: 0px; margin: 2px; border-radius: 6px; color: #E8E8E8; background-color: #2A2A2A; border: 1px solid #3A3A3A; }}"
            f" QPushButton#sidebar_icon_danger {{ font-family: 'Material Symbols Outlined'; font-size: 20px; padding: 0px; margin: 2px; border-radius: 6px; color: #8A8A8A; border: 1px solid transparent; background: transparent; }}"
            f" QPushButton#sidebar_icon_danger:hover {{ background-color: #2A2A2A; color: #E8E8E8; }}"
        )
        for plot in (self.price_plot, self.cvd_plot):
            for ax_name in ("bottom", "right"):
                ax = plot.getAxis(ax_name)
                ax.setPen(pg.mkPen(t.axis))
                ax.setTextPen(pg.mkPen(t.text))

    # ---- feed drain + redraw (GUI thread) --------------------------------
    def _tick(self) -> None:
        drained = 0
        q = self._event_q
        while q and drained < 40000:
            ev = q.popleft()
            drained += 1
            if isinstance(ev, Trade):
                s = self.series.get(ev.symbol)
                if s is None:
                    s = self.series[ev.symbol] = BarSeries(ev.symbol, self.instruments)
                s.add_trade(ev)
                self._bookmap(ev.symbol).add_trade(ev)
                self._profile(ev.symbol).add_trade(ev)
                if ev.symbol not in self._known_symbols:
                    self._register_symbol(ev.symbol)
                if ev.symbol == self.active_symbol:
                    self._dirty = True
            else:  # BookSnapshot
                self.latest_book[ev.symbol] = ev
                self._bookmap(ev.symbol).add_book(ev)
                s = self.series.get(ev.symbol)
                if s is not None:
                    s.add_book(ev)
                    if ev.symbol == self.active_symbol:
                        self._dirty = True

        # Refresh the live indicator ~2x/sec even when no data is flowing, so
        # "waiting for Takion" is visible before the first tick arrives.
        self._link_tick = getattr(self, "_link_tick", 0) + 1
        if self._link_tick % 15 == 0:
            self._update_link()

        if self._dirty and self.active_symbol:
            self._redraw()
            self._dirty = False
            if not self._centered_once and self.series.get(self.active_symbol) \
                    and self.series[self.active_symbol].view(self.tf_s):
                self._center()
                self._centered_once = True

    def _register_symbol(self, sym: str) -> None:
        self._known_symbols.add(sym)
        self.sym_combo.blockSignals(True)
        self.sym_combo.addItem(sym)
        self.sym_combo.blockSignals(False)
        # prefer the symbol restored from the saved workspace once it arrives
        if self._pending_symbol and sym == self._pending_symbol:
            self._pending_symbol = ""
            self.active_symbol = sym
            self.sym_combo.setCurrentText(sym)
            self.fp.tick = self.instruments.tick(sym)
            self._dirty = True
        elif not self.active_symbol:
            self.active_symbol = sym
            self.sym_combo.setCurrentText(sym)
            self.fp.tick = self.instruments.tick(sym)

    def _redraw(self) -> None:
        s = self.series[self.active_symbol]
        bars = s.view(self.tf_s)
        self.fp.set_bars(bars)
        if self.heatmap.isVisible():
            self.heatmap.set_bars(bars)
        self.time_axis.set_bars(bars)
        
        if self.cpr_item.isVisible(): self.cpr_item.set_bars(bars)
        if self.ema9_item.isVisible(): self.ema9_item.set_bars(bars)
        if self.ema21_item.isVisible(): self.ema21_item.set_bars(bars)
        
        self._update_overlays(s, bars)
        if bars:
            self.price_line.setPos(bars[-1].close)
            if self.auto_scroll:
                n = len(bars)
                vr = self.price_plot.getViewBox().viewRect()
                if vr.right() < n + 1:
                    self.price_plot.setXRange(max(-1, n - 22), n + 3, padding=0)
            self._update_stats(bars[-1])

    def _update_overlays(self, series: BarSeries, bars: list) -> None:
        if not bars:
            self.vwap_curve.setData([], [])
            self.cvd_curve.setData([], [])
            return
        tick = self.instruments.tick(self.active_symbol)
        vx, vy, cx, cy = [], [], [], []
        vstd = []
        cum_pv = cum_v = cum_pv2 = 0.0
        for i, b in enumerate(bars):
            for ti, (sell_v, buy_v) in b.cells.items():
                vol = sell_v + buy_v
                price = ti * tick
                cum_v += vol
                cum_pv += price * vol
                cum_pv2 += price * price * vol
            if cum_v > 0:
                vwap = cum_pv / cum_v
                var = max(0.0, cum_pv2 / cum_v - vwap * vwap)
                vx.append(i)
                vy.append(vwap)
                vstd.append(var ** 0.5)
        for i, cd in enumerate(series.cvd(self.tf_s)):
            cx.append(i)
            cy.append(cd)
        self.vwap_curve.setData(vx, vy)
        show_bands = self.vwap_curve.isVisible()
        for k, (mult, curve) in enumerate(self.vwap_bands):
            sign = 1 if k % 2 == 0 else -1
            if show_bands and vstd:
                curve.setData(vx, [m + sign * mult * s for m, s in zip(vy, vstd)])
            else:
                curve.setData([], [])
        self.cvd_curve.setData(cx, cy)

    def _update_stats(self, bar) -> None:
        self.lbl_stats.setText(
            f"  {self.active_symbol}   {bar.close:.2f}   "
            f"Vol {bar.volume:,}   Δ {bar.delta:+,}   "
        )
        self._update_link()

    def _update_link(self) -> None:
        """Show live-pipe status; blank for feeds that aren't pipe-based."""
        conn = getattr(self.feed, "connected", None)
        if not isinstance(conn, dict):
            return
        l1, l2 = bool(conn.get("l1")), bool(conn.get("l2"))
        if l1 and l2:
            txt, col = f"● LIVE  {len(self.series)} sym", "#26A69A"
        elif l1 or l2:
            txt, col = f"● PARTIAL  L1:{'✓' if l1 else '×'} L2:{'✓' if l2 else '×'}", "#FFB300"
        else:
            txt, col = "○ waiting for Takion…", "#EF5350"
        self.lbl_link.setText(f"  {txt}  ")
        self.lbl_link.setStyleSheet(f"color:{col}; font-weight:700;")

    # ---- interactions ----------------------------------------------------
    def _on_symbol(self, sym: str) -> None:
        if sym:
            self.active_symbol = sym
            self.fp.tick = self.instruments.tick(sym)
            self.auto_scroll = True
            self._dirty = True

    def _on_tf(self, txt: str) -> None:
        self.tf_s = TF_CHOICES.get(txt, 60)
        self.auto_scroll = True
        self._dirty = True

    def _on_vwap_toggled(self, on: bool) -> None:
        self.vwap_curve.setVisible(on)
        for _, c in self.vwap_bands:
            c.setVisible(on)
        self._dirty = True

    def _on_cpr_toggled(self, on: bool) -> None:
        self.cpr_item.setVisible(on)
        self._dirty = True

    def _on_ema_toggled(self, on: bool) -> None:
        self.ema9_item.setVisible(on)
        self.ema21_item.setVisible(on)
        self._dirty = True

    def _on_mode(self, name: str) -> None:
        fp_mode, draw_cells, hm_visible = MODES.get(name, ("Footprint", True, False))
        self.fp.set_mode(fp_mode)
        self.fp.set_draw_cells(draw_cells)
        self.heatmap.setVisible(hm_visible)
        self._dirty = True

    def _bookmap(self, sym: str) -> BookmapBuffer:
        b = self.bookmaps.get(sym)
        if b is None:
            b = self.bookmaps[sym] = BookmapBuffer(sym, self.instruments)
        return b

    def _profile(self, sym: str) -> SessionProfile:
        p = self.profiles.get(sym)
        if p is None:
            p = self.profiles[sym] = SessionProfile(sym, self.instruments)
        return p

    def _open_profile(self) -> None:
        sym = self.active_symbol or "QQQ"
        win = ProfileWindow(self._profile(sym), self.instruments.tick(sym), self)
        self._bookmap_windows.append(win)
        win.show()
        win._fit()

    def _open_analytics(self) -> None:
        sym = self.active_symbol or "QQQ"
        win = AnalyticsWindow(self._bookmap(sym), self.instruments.tick(sym), self)
        self._bookmap_windows.append(win)
        win.show()

    def _open_dom(self) -> None:
        win = DomLadderWindow(self, self)
        self._bookmap_windows.append(win)
        win.show()

    def _open_monitor(self) -> None:
        win = MarketMonitorWindow(self, self)
        self._bookmap_windows.append(win)
        win.show()

    def _open_bookmap(self) -> None:
        sym = self.active_symbol or "QQQ"
        win = BookmapWindow(self._bookmap(sym), self.instruments.tick(sym), self)
        win.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self._bookmap_windows.append(win)
        win.show()

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self)
        if not dlg.exec():
            return
        v = dlg.values()
        if self.active_symbol:
            self.instruments.set_tick(self.active_symbol, v["tick"])
            self.fp.tick = v["tick"]
            self.heatmap.tick = v["tick"]
            # tick change reshapes the price->index map; rebuild this symbol
            self.series.pop(self.active_symbol, None)
        self.fp.configure(
            imbalance_factor=v["imbalance_factor"],
            min_imbalance_vol=v["min_imbalance_vol"],
            stacked_min=v["stacked_min"],
            va_pct=v["va_pct"],
            show_candles=v["show_candles"],
        )
        self.heatmap.alpha = v["hm_alpha"]
        self.heatmap.gamma = v["hm_gamma"]
        # colour overrides -> new immutable theme
        self.theme = replace(self.theme, bull=v["bull"], bear=v["bear"],
                             buy_imb=v["buy_imb"], sell_imb=v["sell_imb"])
        self._apply_theme()
        self._dirty = True

    def _on_theme(self, txt: str) -> None:
        self.theme = DARK if txt == "Dark" else LIGHT
        self._apply_theme()
        self._dirty = True

    def _on_mouse_move(self, pos) -> None:
        if self.price_plot.sceneBoundingRect().contains(pos):
            mp = self.price_plot.vb.mapSceneToView(pos)
            self.vline.setPos(mp.x())
            self.hline.setPos(mp.y())
            
            # Hide pop-up while cursor is moving fast to guarantee 60fps smooth movement
            if hasattr(self, 'hover_popup'):
                self.hover_popup.hide()

            bar_idx = int(round(mp.x()))
            if self.active_symbol and self.active_symbol in self.series:
                series = self.series[self.active_symbol].view(self.tf_s)
                if 0 <= bar_idx < len(series):
                    bar = series[bar_idx]
                    tick_size = self.instruments.tick(self.active_symbol)
                    y_price = mp.y()
                    margin = tick_size * 2.0
                    if (bar.low - margin) <= y_price <= (bar.high + margin):
                        global_pos = self.glw.mapToGlobal(pos.toPoint())
                        self._pending_hover_data = (bar, tick_size, global_pos)
                        self._hover_timer.start() # Reset 100ms pause timer
                        return

        # Cursor outside chart or off candle
        self._hover_timer.stop()
        self._pending_hover_data = None
        if hasattr(self, 'hover_popup'):
            self.hover_popup.hide()

    def _show_hover_popup(self) -> None:
        if self._pending_hover_data and hasattr(self, 'hover_popup'):
            bar, tick_size, global_pos = self._pending_hover_data
            self.hover_popup.update_bar(bar, tick_size, global_pos)

    def _on_mouse_click(self, ev) -> None:
        if not self.active_drawing_tool:
            return
            
        pos = ev.scenePos()
        if not self.price_plot.sceneBoundingRect().contains(pos):
            return
            
        mp = self.price_plot.vb.mapSceneToView(pos)
        
        if ev.button() in (Qt.MouseButton.LeftButton, 1):
            vr = self.price_plot.getViewBox().viewRect()
            default_w = max(4.0, vr.width() * 0.25)
            default_h = max(2.0, vr.height() * 0.25)
            
            x = mp.x()
            y = mp.y()
            item = None
            
            if self.active_drawing_tool == "Fib":
                item = FibRetracement([x - default_w * 0.5, y - default_h * 0.5], [default_w, default_h])
            elif self.active_drawing_tool == "Long":
                item = PositionDrawer([x - default_w * 0.5, y - default_h * 0.5], [default_w, default_h], is_long=True)
            elif self.active_drawing_tool == "Short":
                item = PositionDrawer([x - default_w * 0.5, y - default_h * 0.5], [default_w, default_h], is_long=False)
            elif self.active_drawing_tool == "VP":
                item = FixedVolumeProfile(
                    [x - default_w * 0.5, vr.top()],
                    [default_w, vr.height()],
                    self._get_bars_for_vp,
                    self.instruments.tick(self.active_symbol)
                )
            
            if item:
                self.price_plot.addItem(item)
                self.drawing_items.append(item)
                self._set_drawing_tool(None) # Auto-revert to cursor

    def _get_bars_for_vp(self, x_min, x_max):
        if not self.active_symbol: return []
        bars = self.series[self.active_symbol].view(self.tf_s)
        # filter bars within x_min and x_max
        # Since x-axis is bar index:
        start_idx = max(0, int(x_min))
        end_idx = min(len(bars), int(x_max) + 1)
        return bars[start_idx:end_idx]

    def _set_drawing_tool(self, tool_name):
        self.active_drawing_tool = tool_name
        self._drawing_start_point = None

        if hasattr(self, '_drawing_buttons'):
            for name, btn in self._drawing_buttons.items():
                if name == tool_name:
                    btn.setStyleSheet("color: #00E676; background-color: #2A2A2A; border: 1px solid #00E676; border-radius: 4px;")
                else:
                    btn.setStyleSheet("color: #8A8A8A; background: transparent; border: 1px solid transparent; border-radius: 4px;")

        vb = self.price_plot.getViewBox()
        vb.setMouseMode(pg.ViewBox.PanMode)

    def _clear_drawings(self):
        for item in self.drawing_items:
            self.price_plot.removeItem(item)
        self.drawing_items.clear()
        self._set_drawing_tool(None)

    def _on_view(self) -> None:
        if not self.active_symbol:
            return
        bars = self.series[self.active_symbol].view(self.tf_s)
        vr = self.price_plot.getViewBox().viewRect()
        self.auto_scroll = vr.right() >= len(bars) - 1.0

    def _center(self) -> None:
        if not self.active_symbol:
            return
        bars = self.series[self.active_symbol].view(self.tf_s)
        if not bars:
            return
        vis = bars[-24:]
        lo = min(b.low for b in vis)
        hi = max(b.high for b in vis)
        margin = (hi - lo) * 0.12 or 1.0
        self.price_plot.setYRange(lo - margin, hi + margin, padding=0)
        self.price_plot.setXRange(max(-1, len(bars) - 22), len(bars) + 3, padding=0)
        self.auto_scroll = True

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
            if hasattr(self, 'btn_fullscreen'):
                self.btn_fullscreen.setText("\ue5d0")
                self.btn_fullscreen.setToolTip("Full-Screen Mode (F11)")
                self.btn_fullscreen.setStyleSheet("font-family: 'Material Symbols Outlined'; font-size: 20px; background: transparent; color: #8A8A8A; border: none;")
        else:
            self.showFullScreen()
            if hasattr(self, 'btn_fullscreen'):
                self.btn_fullscreen.setText("\ue5d1")
                self.btn_fullscreen.setToolTip("Exit Full-Screen (Esc / F11)")
                self.btn_fullscreen.setStyleSheet("font-family: 'Material Symbols Outlined'; font-size: 20px; background: transparent; color: #00E676; border: none;")

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_F11:
            self._toggle_fullscreen()
            event.accept()
        elif event.key() == Qt.Key.Key_Escape and self.isFullScreen():
            self._toggle_fullscreen()
            event.accept()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        workspace.save(self)                  # remember the desk for next time
        self.feed.stop()
        super().closeEvent(event)
