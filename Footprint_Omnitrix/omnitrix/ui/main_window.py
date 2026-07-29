"""Main ATAS-style window: footprint price pane + cumulative-delta pane,
fed by any engine Feed via a thread-safe queue drained on the GUI thread.
"""

from __future__ import annotations

from collections import deque
from dataclasses import replace

import pyqtgraph as pg
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF
from PyQt6.QtGui import QColor, QCursor
from PyQt6.QtWidgets import (
    QMainWindow, QToolBar, QLabel, QComboBox, QCheckBox, QPushButton, QWidget,
    QSizePolicy, QDockWidget, QHBoxLayout, QVBoxLayout, QFrame, QButtonGroup, QMenu,
    QSplitter, QListView, QDialog,
)

from ..engine import (
    Instruments, BarSeries, BookmapBuffer, SessionProfile, Feed, parse_timeframe, TemplateManager
)
from ..engine.model import Trade, BookSnapshot
from ..render import (
    FootprintItem, HeatmapItem, DARK, LIGHT, TimeAxis,
    FibRetracement, PositionDrawer, FixedVolumeProfile, RangeCPR, EMAItem, CPRItem
)
from .settings_dialog import SettingsDialog
from .bookmap_window import BookmapWindow
from .profile_window import ProfileWindow
from .analytics_window import AnalyticsWindow
from .drawing_props_dialog import DrawingPropsDialog
from .monitor_window import MarketMonitorWindow
from .dom_ladder import DomLadderWindow
from . import workspace
from .tape_widget import TapeWidget
from .stats_panel import StatsPanel
from .chart_cell import MenuDropdown
from .signals_panel import SignalsPanel
from .data_window import DataWindowWidget, CandleHoverPopup
from .chart_cell import ChartCellWidget

TF_CHOICES = {
    "10s": 10, "30s": 30, "1m": 60, "2m": 120, "3m": 180, "5m": 300,
    "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400,
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
    "Profile + Heatmap": ("Profile", True, True),
    "Delta + Heatmap": ("Delta", True, True),
}


class TradingViewBox(pg.ViewBox):
    """TradingView-style interactive ViewBox.
    - Wheel scroll zooms X-axis centered at mouse cursor position.
    - Ctrl/Shift + Wheel scroll zooms Y-axis (price scale).
    - Double click resets/enables Y-axis Auto-Fit.
    """
    def __init__(self, main_window=None, *args, **kwargs):
        kwargs['enableMenu'] = False
        super().__init__(*args, **kwargs)
        self.main_window = main_window
        self.setMouseMode(pg.ViewBox.PanMode)
        self.is_dragging = False
        self._drag_start_pos = None

    def wheelEvent(self, ev, axis=None):
        ev.accept()
        if hasattr(ev, 'delta'):
            delta = ev.delta()
        elif hasattr(ev, 'angleDelta'):
            delta = ev.angleDelta().y()
        else:
            delta = 0

        if delta == 0:
            return
        
        # Smooth exponential scale factor
        s = 0.84 if delta > 0 else 1.19
        
        # Get mouse position in View coordinates
        if hasattr(ev, 'scenePos'):
            pos_scene = ev.scenePos()
        elif hasattr(ev, 'position'):
            pos_scene = ev.position()
        elif hasattr(ev, 'pos'):
            pos_scene = ev.pos()
        else:
            pos_scene = QPointF(0, 0)

        pos = self.mapSceneToView(pos_scene)
        
        modifiers = ev.modifiers() if hasattr(ev, 'modifiers') else Qt.KeyboardModifier.NoModifier
        is_ctrl_or_shift = bool(modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier))
        
        if is_ctrl_or_shift or axis == 1:
            # Zoom Y-axis (price scale) -> Disables Auto-Fit
            if self.main_window:
                self.main_window._toggle_autofit(False)
            self.scaleBy((1.0, s), center=(pos.x(), pos.y()))
        else:
            # Zoom X-axis (time scale) centered at mouse cursor
            vr = self.viewRect()
            new_w = vr.width() * s
            if s < 1.0 and new_w < 3.0:  # Minimum 3 bars visible
                return
            
            self.scaleBy((s, 1.0), center=(pos.x(), pos.y()))
            if self.main_window and getattr(self.main_window, '_auto_fit_enabled', True):
                self.main_window._auto_fit_y()

        # Notify main window that the user manually changed the view
        # so auto_scroll can be updated (prevents _redraw from overwriting zoom)
        self.sigRangeChangedManually.emit(self.state['mouseMode'])

    def mouseDragEvent(self, ev, axis=None):
        if ev.isStart():
            self.is_dragging = True
            self._drag_start_pos = ev.pos()
        elif ev.isFinish():
            self.is_dragging = False
            if self._drag_start_pos is not None:
                delta = ev.pos() - self._drag_start_pos
                # If vertical movement was significant during drag, turn off auto-fit
                if abs(delta.y()) > 4 and abs(delta.y()) > abs(delta.x()):
                    if self.main_window:
                        self.main_window._toggle_autofit(False)
            super().mouseDragEvent(ev, axis)
            if self.main_window and getattr(self.main_window, '_auto_fit_enabled', True):
                self.main_window._auto_fit_y()
            return
        super().mouseDragEvent(ev, axis)

    def mouseDoubleClickEvent(self, ev):
        if self.main_window:
            self.main_window._toggle_autofit(True)
        ev.accept()



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
        self.template_mgr = TemplateManager()

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

        # Symbol dropdown kept in memory for backwards compatibility, not shown in navbar
        self.sym_combo = QComboBox()
        self.sym_combo.setView(QListView())
        self.sym_combo.setMaxVisibleItems(12)
        self.sym_combo.currentTextChanged.connect(self._on_symbol)
        self.sym_combo.hide()

        # Layout Grid Selector Dropdown
        lbl_layout = QLabel("Grid")
        lbl_layout.setStyleSheet("color:#8A8A8A; font-size:12px; margin-left: 8px;")
        left_layout.addWidget(lbl_layout)

        self.layout_combo = MenuDropdown("1x1", ["1x1", "2x1", "1x2", "2x2"], on_select_cb=self._set_layout_mode)
        left_layout.addWidget(self.layout_combo)

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
        btn_theme.setStyleSheet("color: #8A8A8A; background: transparent; font-size: 20px; border: 1px solid transparent; border-radius: 4px;")
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

        self._auto_fit_enabled = True

        self.btn_autofit = QPushButton("Auto-Fit")
        self.btn_autofit.setToolTip("Toggle Auto-Fit Price Scale (Y-Axis)")
        self.btn_autofit.setCheckable(True)
        self.btn_autofit.setChecked(True)
        self.btn_autofit.setStyleSheet("font-size: 11px; font-weight: bold; background: #2A2A2A; color: #00E676; border: 1px solid #00E676; border-radius: 3px; padding: 2px 6px;")
        self.btn_autofit.clicked.connect(self._toggle_autofit)
        right_layout.addWidget(self.btn_autofit)

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
        add_dtb_btn("\ue8d4", "CPR Range Tool", "CPR")
        
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

        # ---- Grid Layout Container for Multi-Chart Panes ----
        self.layout_container = QWidget()
        self.central_layout = QVBoxLayout(self.layout_container)
        self.central_layout.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(self.layout_container)

        self.cells: list[ChartCellWidget] = []
        self._set_layout_mode("1x1")

        # ---- Time & Sales tape dock (right) ----
        self.tape = TapeWidget(
            get_source=lambda: (self.bookmaps.get(self.active_symbol).trades
                                if self.active_symbol in self.bookmaps else None),
            tick_fn=lambda: self.instruments.tick(self.active_symbol or "QQQ"),
        )
        self.stats = StatsPanel(self)
        self.stats_dock = QDockWidget("Session Statistics", self)
        self.stats_dock.setObjectName("stats_dock")
        self.stats_dock.setWidget(self.stats)
        self.stats_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea |
                                        Qt.DockWidgetArea.RightDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.stats_dock)

        self.tape_dock = QDockWidget("Time & Sales", self)
        self.tape_dock.setObjectName("tape_dock")
        self.tape_dock.setWidget(self.tape)
        self.tape_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea |
                                       Qt.DockWidgetArea.LeftDockWidgetArea)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.tape_dock)

        self.signals = SignalsPanel(self)
        self.signals_dock = QDockWidget("Order-Flow Signals", self)
        self.signals_dock.setObjectName("signals_dock")
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

    # ---- Property Delegates for single-cell compatibility ----
    @property
    def price_plot(self):
        return self.cells[0].price_plot if self.cells else None

    @property
    def price_vb(self):
        return self.cells[0].price_vb if self.cells else None

    @property
    def fp(self):
        return self.cells[0].fp if self.cells else None

    @property
    def heatmap(self):
        return self.cells[0].heatmap if self.cells else None

    @property
    def cpr_item(self):
        return self.cells[0].cpr_item if self.cells else None

    @property
    def ema9_item(self):
        return self.cells[0].ema9_item if self.cells else None

    @property
    def ema21_item(self):
        return self.cells[0].ema21_item if self.cells else None

    @property
    def vwap_curve(self):
        return self.cells[0].vwap_curve if self.cells else None

    @property
    def vwap_bands(self):
        return self.cells[0].vwap_bands if self.cells else ([], [])

    @property
    def cvd_curve(self):
        return self.cells[0].cvd_curve if self.cells else None

    # ---- Grid Layout Management ----
    def _set_layout_mode(self, mode: str) -> None:
        self.layout_mode = mode
        if hasattr(self, 'layout_combo') and self.layout_combo and self.layout_combo.currentText() != mode:
            self.layout_combo.setCurrentText(mode)
        while self.central_layout.count():
            item = self.central_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        self.cells.clear()
        symbols_list = list(sorted(self._known_symbols)) or ["QQQ", "AAPL", "SPY"]

        if mode == "1x1":
            cell = ChartCellWidget(self, cell_id=1)
            cell.sigCrosshairMoved.connect(self._broadcast_crosshair)
            cell.sigCloseRequested.connect(self._on_cell_close_requested)
            cell.update_known_symbols(self._known_symbols)
            if self.active_symbol:
                cell.set_symbol(self.active_symbol)
            self.cells.append(cell)
            self.central_layout.addWidget(cell)

        elif mode == "2x1":
            splitter = QSplitter(Qt.Orientation.Horizontal)
            for i in range(2):
                sym = symbols_list[i % len(symbols_list)]
                cell = ChartCellWidget(self, cell_id=i+1)
                cell.update_known_symbols(self._known_symbols)
                cell.set_symbol(sym)
                cell.sigCrosshairMoved.connect(self._broadcast_crosshair)
                cell.sigCloseRequested.connect(self._on_cell_close_requested)
                self.cells.append(cell)
                splitter.addWidget(cell)
            self.central_layout.addWidget(splitter)

        elif mode == "1x2":
            splitter = QSplitter(Qt.Orientation.Vertical)
            for i in range(2):
                sym = symbols_list[i % len(symbols_list)]
                cell = ChartCellWidget(self, cell_id=i+1)
                cell.update_known_symbols(self._known_symbols)
                cell.set_symbol(sym)
                cell.sigCrosshairMoved.connect(self._broadcast_crosshair)
                cell.sigCloseRequested.connect(self._on_cell_close_requested)
                self.cells.append(cell)
                splitter.addWidget(cell)
            self.central_layout.addWidget(splitter)

        elif mode == "2x2":
            v_splitter = QSplitter(Qt.Orientation.Vertical)
            h1 = QSplitter(Qt.Orientation.Horizontal)
            h2 = QSplitter(Qt.Orientation.Horizontal)
            for i in range(4):
                sym = symbols_list[i % len(symbols_list)]
                cell = ChartCellWidget(self, cell_id=i+1)
                cell.update_known_symbols(self._known_symbols)
                cell.set_symbol(sym)
                cell.sigCrosshairMoved.connect(self._broadcast_crosshair)
                cell.sigCloseRequested.connect(self._on_cell_close_requested)
                self.cells.append(cell)
                if i < 2:
                    h1.addWidget(cell)
                else:
                    h2.addWidget(cell)
            v_splitter.addWidget(h1)
            v_splitter.addWidget(h2)
            self.central_layout.addWidget(v_splitter)

        self._redraw()

    def _broadcast_crosshair(self, x_val: float, y_val: float, source_cell) -> None:
        for cell in self.cells:
            if cell != source_cell:
                cell.set_external_crosshair(x_val, y_val)

    def _on_cell_close_requested(self, cell) -> None:
        if len(self.cells) > 1:
            self.cells.remove(cell)
            cell.deleteLater()

            # Re-index cell badges for remaining cells
            for idx, c in enumerate(self.cells):
                c.cell_id = idx + 1
                c.lbl_cell_num.setText(f"#{c.cell_id}")

            # Sync grid layout dropdown text with remaining cell count
            n = len(self.cells)
            if n == 1:
                self.layout_mode = "1x1"
                self.layout_combo.setCurrentText("1x1")
            elif n == 2:
                if self.layout_mode not in ("2x1", "1x2"):
                    self.layout_mode = "2x1"
                self.layout_combo.setCurrentText(self.layout_mode)
            elif n == 3:
                self.layout_combo.setCurrentText("2x2")

            self._redraw()

    # ---- theme -----------------------------------------------------------
    def _apply_theme(self) -> None:
        t = self.theme
        for cell in self.cells:
            cell.theme = t
            cell._apply_theme()
        self.setStyleSheet(
            f"QMainWindow {{ background-color:{t.bg}; }}"
            
            f" QToolBar {{ background-color:{t.panel}; border: none; border-bottom:1px solid {t.grid}; border-right:1px solid {t.grid}; padding:6px; spacing:8px; }}"
            f" QToolBar::separator:horizontal {{ background-color:{t.grid}; width:1px; height:20px; margin:0px 6px; }}"
            f" QToolBar::separator:vertical {{ background-color:{t.grid}; height:1px; margin:8px 6px; }}"
            
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
            
            f" QPushButton#sidebar_icon {{ font-family: 'Material Symbols Outlined'; font-size: 20px; padding: 0px; margin: 2px; border-radius: 6px; color: #8A8A8A; border: 1px solid transparent; background: transparent; }}"
            f" QPushButton#sidebar_icon:hover {{ background-color: #2A2A2A; color: #E8E8E8; }}"
            f" QPushButton#sidebar_icon_active {{ font-family: 'Material Symbols Outlined'; font-size: 20px; padding: 0px; margin: 2px; border-radius: 6px; color: #E8E8E8; background-color: #2A2A2A; border: 1px solid #3A3A3A; }}"
            f" QPushButton#sidebar_icon_danger {{ font-family: 'Material Symbols Outlined'; font-size: 20px; padding: 0px; margin: 2px; border-radius: 6px; color: #8A8A8A; border: 1px solid transparent; background: transparent; }}"
            f" QPushButton#sidebar_icon_danger:hover {{ background-color: #2A2A2A; color: #E8E8E8; }}"
        )

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
        for cell in self.cells:
            cell.update_known_symbols(self._known_symbols)

        if self._pending_symbol and sym == self._pending_symbol:
            self._pending_symbol = ""
            self.active_symbol = sym
            self.sym_combo.setCurrentText(sym)
            if self.cells:
                self.cells[0].set_symbol(sym)
            self._dirty = True
        elif not self.active_symbol:
            self.active_symbol = sym
            self.sym_combo.setCurrentText(sym)
            if self.cells:
                self.cells[0].set_symbol(sym)

    def _redraw(self) -> None:
        for cell in self.cells:
            cell.redraw()

        if self.active_symbol and self.active_symbol in self.series:
            bars = self.series[self.active_symbol].view(self.tf_s)
            if bars:
                self._update_stats(bars[-1])

    def _update_overlays(self, series: BarSeries, bars: list) -> None:
        if not bars:
            self.vwap_curve.setData([], [])
            self.cvd_curve.setData([], [])
            return
        vx, vy, cx, cy = [], [], [], []
        vstd = []
        cum_pv = cum_v = cum_pv2 = 0.0
        for i, b in enumerate(bars):
            vol = b.volume
            if vol > 0:
                price = (b.open + b.high + b.low + b.close) / 4.0
                cum_v += vol
                cum_pv += price * vol
                cum_pv2 += price * price * vol
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

    @property
    def tf_combo(self):
        return self.cells[0].tf_combo if self.cells else None

    @property
    def mode_combo(self):
        return self.cells[0].mode_combo if self.cells else None

    def _on_tf(self, txt: str) -> None:
        self.tf_s = TF_CHOICES.get(txt) or parse_timeframe(txt)
        for c in self.cells:
            c.set_timeframe(txt)
        self._dirty = True

    def _on_mode(self, name: str) -> None:
        for c in self.cells:
            c.mode_combo.setCurrentText(name)
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
        self.show_cvd_div = v.get("show_cvd_div", True)
        if hasattr(self, "chart_grid"):
            for cell in self.chart_grid.cells:
                cell.show_cvd_div = self.show_cvd_div
                cell.redraw()
        # colour overrides -> new immutable theme
        self.theme = replace(self.theme, bull=v["bull"], bear=v["bear"],
                             buy_imb=v["buy_imb"], sell_imb=v["sell_imb"])
        self._apply_theme()
        self._dirty = True

    def _on_theme(self, txt: str) -> None:
        self.theme = DARK if txt == "Dark" else LIGHT
        self._apply_theme()
        self._dirty = True

    def _on_cell_mouse_move(self, cell, pos) -> None:
        if cell.price_plot and cell.price_plot.sceneBoundingRect().contains(pos):
            mp = cell.price_plot.vb.mapSceneToView(pos)
            bar_idx = int(round(mp.x()))
            sym = cell.active_symbol or self.active_symbol
            tf_s = cell.tf_s or self.tf_s
            if sym and sym in self.series:
                series = self.series[sym].view(tf_s)
                if 0 <= bar_idx < len(series):
                    bar = series[bar_idx]
                    tick_size = self.instruments.tick(sym)
                    y_price = mp.y()
                    margin = max(tick_size * 2.0, (bar.high - bar.low) * 0.1)
                    if (bar.low - margin) <= y_price <= (bar.high + margin):
                        global_pos = QCursor.pos()
                        self._pending_hover_data = (bar, tick_size, global_pos)
                        self._show_hover_popup()
                        return

        # Cursor outside chart or off candle
        self._hover_timer.stop()
        self._pending_hover_data = None
        if hasattr(self, 'hover_popup'):
            self.hover_popup.hide()

    def _on_mouse_move(self, pos) -> None:
        if self.cells:
            self._on_cell_mouse_move(self.cells[0], pos)

    def _show_hover_popup(self) -> None:
        if self._pending_hover_data and hasattr(self, 'hover_popup'):
            bar, tick_size, global_pos = self._pending_hover_data
            self.hover_popup.update_bar(bar, tick_size, global_pos)

    def _on_mouse_click(self, ev) -> None:
        if self.cells:
            self._on_cell_mouse_click(self.cells[0], ev)

    def _on_cell_mouse_click(self, cell, ev) -> None:
        if not self.active_drawing_tool:
            return
            
        pos = ev.scenePos()
        if not cell.price_plot or not cell.price_plot.sceneBoundingRect().contains(pos):
            return
            
        mp = cell.price_plot.vb.mapSceneToView(pos)
        
        if ev.button() in (Qt.MouseButton.LeftButton, 1):
            vr = cell.price_plot.getViewBox().viewRect()
            default_w = max(4.0, vr.width() * 0.25)
            default_h = max(2.0, vr.height() * 0.25)
            
            x = mp.x()
            y = mp.y()
            item = None
            sym = cell.active_symbol or self.active_symbol or "QQQ"
            tick_size = self.instruments.tick(sym)
            
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
                    lambda x_min, x_max, s=sym: self._get_bars_for_vp(x_min, x_max, s),
                    tick_size
                )
            elif self.active_drawing_tool == "CPR":
                item = RangeCPR(
                    [x - default_w * 0.5, vr.top()],
                    [default_w, vr.height()],
                    lambda x_min, x_max, s=sym: self._get_bars_for_vp(x_min, x_max, s),
                    tick_size
                )
            
            if item:
                tool_type_name = "FibRetracement" if self.active_drawing_tool == "Fib" else (
                    "PositionDrawer" if self.active_drawing_tool in ("Long", "Short") else (
                        "FixedVolumeProfile" if self.active_drawing_tool == "VP" else "RangeCPR"
                    )
                )
                self._setup_drawing_item_context_menu(cell, item, tool_type_name)
                cell.price_plot.addItem(item)
                self.drawing_items.append((cell.price_plot, item))
                self._set_drawing_tool(None) # Auto-revert to cursor

    def _setup_drawing_item_context_menu(self, cell, item, tool_type: str) -> None:
        def on_item_clicked(roi, ev):
            if ev.button() == Qt.MouseButton.RightButton:
                menu = QMenu(self)
                menu.setStyleSheet(
                    "QMenu { background-color: #1A1D24; color: #E8E8E8; border: 1px solid #3A3A3A; border-radius: 6px; padding: 4px 0px; max-height: 600px; } "
                    "QMenu::item { padding: 6px 24px 6px 12px; font-size: 12px; } "
                    "QMenu::item:selected { background-color: #2A2A2A; color: #FFFFFF; }"
                )
                
                act_props = menu.addAction("Properties & Styling...")
                
                tmpl_menu = menu.addMenu("Apply Template")
                tmpls = self.template_mgr.get_templates_for(tool_type)
                if tmpls:
                    for t_name, style_dict in tmpls.items():
                        act_t = tmpl_menu.addAction(t_name)
                        act_t.triggered.connect(lambda checked=False, s=style_dict: (item.apply_style(s), cell.price_plot.update()))
                else:
                    act_none = tmpl_menu.addAction("(No Saved Templates)")
                    act_none.setEnabled(False)

                act_save = menu.addAction("Save Current Style As Template...")
                menu.addSeparator()
                act_del = menu.addAction("Remove Drawing")
                
                pt = ev.screenPos()
                if hasattr(pt, 'toPoint'):
                    pt = pt.toPoint()
                elif hasattr(pt, 'x'):
                    from PyQt6.QtCore import QPoint
                    pt = QPoint(int(pt.x()), int(pt.y()))

                action = menu.exec(pt)
                if action == act_props:
                    dlg = DrawingPropsDialog(tool_type, item.get_style(), self.template_mgr, self)
                    if dlg.exec() == QDialog.DialogCode.Accepted:
                        item.apply_style(dlg.style)
                        cell.price_plot.update()
                elif action == act_save:
                    dlg = DrawingPropsDialog(tool_type, item.get_style(), self.template_mgr, self)
                    dlg.exec()
                    cell.price_plot.update()
                elif action == act_del:
                    cell.price_plot.removeItem(item)
                    if (cell.price_plot, item) in self.drawing_items:
                        self.drawing_items.remove((cell.price_plot, item))
                    cell.price_plot.update()

        if hasattr(item, 'sigRightClicked'):
            item.sigRightClicked.connect(on_item_clicked)
        if hasattr(item, 'sigClicked'):
            item.sigClicked.connect(on_item_clicked)

    def _get_bars_for_vp(self, x_min, x_max, symbol=None):
        sym = symbol or self.active_symbol
        if not sym or sym not in self.series: return []
        bars = self.series[sym].view(self.tf_s)
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

        if self.price_plot and self.price_plot.getViewBox():
            self.price_plot.getViewBox().setMouseMode(pg.ViewBox.PanMode)

    def _clear_drawings(self):
        for entry in self.drawing_items:
            if isinstance(entry, tuple):
                plot, item = entry
                try:
                    plot.removeItem(item)
                except Exception:
                    pass
            else:
                if self.price_plot:
                    try:
                        self.price_plot.removeItem(entry)
                    except Exception:
                        pass
        self.drawing_items.clear()
        self._set_drawing_tool(None)

    def _on_x_range_changed(self, plot, range_tuple):
        if getattr(self.price_vb, 'is_dragging', False):
            return
        if getattr(self, '_auto_fit_enabled', True):
            self._auto_fit_y()

    def _auto_fit_y(self) -> None:
        if not self.active_symbol:
            return
        bars = self.series[self.active_symbol].view(self.tf_s)
        if not bars:
            return
        vr = self.price_plot.getViewBox().viewRect()
        x_min = max(0, int(vr.left()))
        x_max = min(len(bars), int(vr.right()) + 1)
        if x_min >= x_max:
            return
        
        vis = bars[x_min:x_max]
        if not vis:
            return
            
        lo = min(b.low for b in vis)
        hi = max(b.high for b in vis)
        margin = (hi - lo) * 0.08 or 1.0
        self.price_plot.setYRange(lo - margin, hi + margin, padding=0)

    def _toggle_autofit(self, checked=None) -> None:
        if checked is None:
            self._auto_fit_enabled = not getattr(self, '_auto_fit_enabled', True)
        elif isinstance(checked, bool):
            self._auto_fit_enabled = checked
        else:
            self._auto_fit_enabled = True
            
        if hasattr(self, 'btn_autofit'):
            self.btn_autofit.setChecked(self._auto_fit_enabled)
            if self._auto_fit_enabled:
                self.btn_autofit.setStyleSheet("font-size: 11px; font-weight: bold; background: #2A2A2A; color: #00E676; border: 1px solid #00E676; border-radius: 3px; padding: 2px 6px;")
                self._auto_fit_y()
            else:
                self.btn_autofit.setStyleSheet("font-size: 11px; font-weight: bold; background: transparent; color: #8A8A8A; border: 1px solid transparent; border-radius: 3px; padding: 2px 6px;")

    def _on_view(self) -> None:
        if not self.active_symbol:
            return
        bars = self.series[self.active_symbol].view(self.tf_s)
        vr = self.price_plot.getViewBox().viewRect()
        self.auto_scroll = vr.right() >= len(bars) - 1.0

    def _center(self) -> None:
        for cell in getattr(self, 'cells', []):
            if not cell.active_symbol or cell.active_symbol not in self.series:
                continue
            bars = self.series[cell.active_symbol].view(cell.tf_s)
            if not bars:
                continue
            cell.auto_scroll = True
            cell._auto_fit_enabled = True
            cell.btn_autofit.setChecked(True)
            cell.btn_autofit.setStyleSheet("font-size: 10px; font-weight: bold; background: #2A2A2A; color: #00E676; border: 1px solid #00E676; border-radius: 3px; padding: 1px 5px;")
            n = len(bars)
            cell.price_plot.setXRange(max(-1, n - 22), n + 3, padding=0)
            cell._auto_fit_y()
            cell.redraw()

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
