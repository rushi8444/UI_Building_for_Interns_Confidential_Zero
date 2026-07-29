"""ChartCellWidget: Individual chart pane for multi-chart grid layouts.
Includes price footprint, heatmap, CVD sub-chart, local header bar, and crosshair sync.
"""

from __future__ import annotations

from dataclasses import replace
import pyqtgraph as pg
from PyQt6.QtCore import Qt, QPointF, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton, QLabel, QFrame, QSizePolicy, QMenu, QListView
)

from ..engine import Instruments, BarSeries, Feed, parse_timeframe, format_timeframe
from ..render import (
    FootprintItem, HeatmapItem, DARK, LIGHT, TimeAxis,
    CPRItem, EMAItem
)
from .custom_tf_dialog import CustomTimeframeDialog

TF_CHOICES = {
    "5s": 5, "10s": 10, "15s": 15, "30s": 30,
    "1m": 60, "2m": 120, "3m": 180, "5m": 300,
    "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400,
    "100T": "100T", "250T": "250T", "500T": "500T", "1000T": "1000T",
    "Custom...": -1,
}

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


class MenuDropdown(QPushButton):
    """Custom dropdown button styled exactly like Indicators QMenu button."""
    def __init__(self, title: str, items: list[str] = None, on_select_cb=None, parent=None):
        super().__init__(title, parent)
        self.setStyleSheet(
            "font-size: 11px; font-weight: 500; color: #E8E8E8; "
            "background-color: #2A2A2A; border: 1px solid #3A3A3A; "
            "padding: 2px 8px; border-radius: 3px;"
        )
        self.menu = QMenu(self)
        self.menu.setStyleSheet(
            "QMenu { background-color: #1A1D24; color: #E8E8E8; border: 1px solid #3A3A3A; border-radius: 6px; padding: 4px 0px; max-height: 600px; } "
            "QMenu::item { padding: 6px 24px 6px 12px; font-size: 12px; } "
            "QMenu::item:selected { background-color: #2A2A2A; color: #FFFFFF; }"
        )
        self.setMenu(self.menu)
        self._items = list(items) if items else []
        self._current_text = title
        self._cb = on_select_cb
        self._actions = {}
        self._rebuild_menu()

    def _rebuild_menu(self):
        self.menu.clear()
        self._actions.clear()
        if self._items:
            for item in self._items:
                act = self.menu.addAction(item)
                act.setCheckable(True)
                act.setChecked(item == self._current_text)
                act.triggered.connect(lambda checked=False, val=item: self._select(val))
                self._actions[item] = act
            self.setMenu(self.menu)
        else:
            self.setMenu(None)

    def _select(self, text: str):
        self._current_text = text
        self.setText(text)
        for item, act in self._actions.items():
            act.setChecked(item == text)
        if self._cb:
            self._cb(text)

    def findText(self, text: str) -> int:
        return self._items.index(text) if text in self._items else -1

    def currentText(self) -> str:
        return self._current_text

    def setCurrentText(self, text: str):
        self._current_text = text
        self.setText(text)
        for item, act in self._actions.items():
            act.setChecked(item == text)

    def clear(self):
        self._items.clear()
        self.menu.clear()
        self._actions.clear()
        self.setMenu(None)

    def addItem(self, item: str):
        if item not in self._items:
            self._items.append(item)
            self._rebuild_menu()

    def addItems(self, items: list[str]):
        for it in items:
            if it not in self._items:
                self._items.append(it)
        self._rebuild_menu()

    def blockSignals(self, b: bool):
        pass


class CellViewBox(pg.ViewBox):
    """Interactive ViewBox for individual chart cell."""
    def __init__(self, chart_cell=None, *args, **kwargs):
        kwargs['enableMenu'] = False
        super().__init__(*args, **kwargs)
        self.chart_cell = chart_cell
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

        s = 0.84 if delta > 0 else 1.19

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
            if self.chart_cell:
                self.chart_cell._toggle_autofit(False)
            self.scaleBy((1.0, s), center=(pos.x(), pos.y()))
        else:
            vr = self.viewRect()
            new_w = vr.width() * s
            if s < 1.0 and new_w < 3.0:
                return

            self.scaleBy((s, 1.0), center=(pos.x(), pos.y()))
            if self.chart_cell and self.chart_cell._auto_fit_enabled:
                self.chart_cell._auto_fit_y()

        self.sigRangeChangedManually.emit(self.state['mouseMode'])

    def mouseDragEvent(self, ev, axis=None):
        if ev.isStart():
            self.is_dragging = True
            self._drag_start_pos = ev.pos()
        elif not ev.isFinish():
            if self._drag_start_pos is not None:
                delta = ev.pos() - self._drag_start_pos
                if abs(delta.x()) > 4 and self.chart_cell:
                    self.chart_cell.auto_scroll = False
            super().mouseDragEvent(ev, axis)
            return
        elif ev.isFinish():
            self.is_dragging = False
            if self._drag_start_pos is not None:
                delta = ev.pos() - self._drag_start_pos
                if abs(delta.y()) > 4 and abs(delta.y()) > abs(delta.x()):
                    if self.chart_cell:
                        self.chart_cell._toggle_autofit(False)
                elif abs(delta.x()) > 4:
                    if self.chart_cell:
                        self.chart_cell.auto_scroll = False
            super().mouseDragEvent(ev, axis)
            if self.chart_cell and self.chart_cell._auto_fit_enabled:
                self.chart_cell._auto_fit_y()
            return
        super().mouseDragEvent(ev, axis)

    def mouseDoubleClickEvent(self, ev):
        if self.chart_cell:
            self.chart_cell._toggle_autofit(True)
        ev.accept()


class ChartCellWidget(QWidget):
    """Independent chart cell widget for multi-chart layouts."""
    sigCrosshairMoved = pyqtSignal(float, float, object)  # (x_pos, y_pos, cell)
    sigFocused = pyqtSignal(object)                       # (cell)
    sigCloseRequested = pyqtSignal(object)                # (cell)

    def __init__(self, main_window, cell_id: int = 1, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.cell_id = cell_id
        self.instruments = main_window.instruments
        
        self.active_symbol = main_window.active_symbol or "QQQ"
        self.tf_s = 60
        self.theme = main_window.theme
        self._auto_fit_enabled = True
        self.auto_scroll = True
        self._dirty = False

        self._build_ui()
        self._apply_theme()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)

        # ---- Cell Header Toolbar ----
        self.header = QFrame()
        self.header.setObjectName("cell_header")
        self.header.setStyleSheet("QFrame#cell_header { background-color: #1A1D24; border-bottom: 1px solid #2A2A2A; max-height: 32px; }")
        hl = QHBoxLayout(self.header)
        hl.setContentsMargins(8, 2, 8, 2)
        hl.setSpacing(8)

        # Cell indicator badge
        self.lbl_cell_num = QLabel(f"#{self.cell_id}")
        self.lbl_cell_num.setStyleSheet("color: #26A69A; font-weight: bold; font-size: 11px;")
        hl.addWidget(self.lbl_cell_num)

        # Symbol dropdown
        initial_sym = self.active_symbol or (self.main_window._known_symbols[0] if (self.main_window and self.main_window._known_symbols) else "QQQ")
        known_syms = list(self.main_window._known_symbols) if (self.main_window and self.main_window._known_symbols) else [initial_sym]
        self.sym_combo = MenuDropdown(initial_sym, known_syms, on_select_cb=self._on_symbol)
        hl.addWidget(self.sym_combo)

        # Timeframe dropdown
        self.tf_combo = MenuDropdown("1m", list(TF_CHOICES.keys()), on_select_cb=self._on_tf)
        hl.addWidget(self.tf_combo)

        # Mode dropdown
        self.mode_combo = MenuDropdown("Footprint", list(MODES.keys()), on_select_cb=self._on_mode)
        hl.addWidget(self.mode_combo)

        # Indicators menu per graph cell
        self.btn_ind = QPushButton("Indicators")
        self.btn_ind.setToolTip("Toggle Chart Indicators for this graph")
        self.btn_ind.setStyleSheet(
            "font-size: 11px; font-weight: 500; color: #E8E8E8; "
            "background-color: #2A2A2A; border: 1px solid #3A3A3A; "
            "padding: 2px 8px; border-radius: 3px;"
        )
        self.menu_ind = QMenu(self)
        self.btn_ind.setMenu(self.menu_ind)
        hl.addWidget(self.btn_ind)

        self.act_imb = self.menu_ind.addAction("Imbalance")
        self.act_imb.setCheckable(True)
        self.act_imb.setChecked(True)
        self.act_imb.toggled.connect(self._on_toggle_imb)

        self.act_va = self.menu_ind.addAction("Value Area")
        self.act_va.setCheckable(True)
        self.act_va.setChecked(True)
        self.act_va.toggled.connect(self._on_toggle_va)

        self.act_vwap = self.menu_ind.addAction("VWAP")
        self.act_vwap.setCheckable(True)
        self.act_vwap.setChecked(True)
        self.act_vwap.toggled.connect(self._on_toggle_vwap)

        self.act_cpr = self.menu_ind.addAction("CPR")
        self.act_cpr.setCheckable(True)
        self.act_cpr.setChecked(False)
        self.act_cpr.toggled.connect(self._on_toggle_cpr)

        self.act_ema = self.menu_ind.addAction("EMAs")
        self.act_ema.setCheckable(True)
        self.act_ema.setChecked(False)
        self.act_ema.toggled.connect(self._on_toggle_ema)

        hl.addStretch()

        # Auto-Fit button
        self.btn_autofit = QPushButton("Auto")
        self.btn_autofit.setToolTip("Toggle Auto-Fit Y-Scale")
        self.btn_autofit.setCheckable(True)
        self.btn_autofit.setChecked(True)
        self.btn_autofit.setStyleSheet("font-size: 10px; font-weight: bold; background: #2A2A2A; color: #00E676; border: 1px solid #00E676; border-radius: 3px; padding: 1px 5px;")
        self.btn_autofit.clicked.connect(self._toggle_autofit)
        hl.addWidget(self.btn_autofit)

        # Close cell button
        self.btn_close = QPushButton("✕")
        self.btn_close.setToolTip("Remove Pane")
        self.btn_close.setStyleSheet("font-size: 11px; color: #8A8A8A; background: transparent; border: none; padding: 0 4px;")
        self.btn_close.clicked.connect(lambda: self.sigCloseRequested.emit(self))
        hl.addWidget(self.btn_close)

        layout.addWidget(self.header)

        # ---- Graphics Layout (Price + CVD) ----
        self.glw = pg.GraphicsLayoutWidget()
        layout.addWidget(self.glw)

        self.price_vb = CellViewBox(chart_cell=self)
        self.price_plot = self.glw.addPlot(row=0, col=0, viewBox=self.price_vb)
        self.price_plot.showAxis("right")
        self.price_plot.hideAxis("left")
        self.price_plot.hideAxis("bottom")
        self.price_plot.showGrid(x=True, y=True, alpha=0.25)

        self.time_axis = TimeAxis(orientation="bottom")
        self.cvd_plot = self.glw.addPlot(row=1, col=0, axisItems={"bottom": self.time_axis})
        self.cvd_plot.showAxis("right")
        self.cvd_plot.hideAxis("left")
        self.cvd_plot.showGrid(x=True, y=True, alpha=0.2)
        self.cvd_plot.setXLink(self.price_plot)
        self.glw.ci.layout.setRowStretchFactor(0, 4)
        self.glw.ci.layout.setRowStretchFactor(1, 1)

        self.heatmap = HeatmapItem(self.instruments.tick(self.active_symbol))
        self.heatmap.setVisible(False)
        self.price_plot.addItem(self.heatmap)

        self.fp = FootprintItem(self.instruments.tick(self.active_symbol), self.theme)
        self.price_plot.addItem(self.fp)

        # Overlays
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

        self.vwap_bands = []
        for mult, alpha, dash in ((1, 150, Qt.PenStyle.DashLine), (2, 90, Qt.PenStyle.DotLine)):
            for _ in range(2):
                c = pg.PlotDataItem(pen=pg.mkPen(self.theme.vwap, width=1, style=dash))
                c.setOpacity(alpha / 255.0)
                self.price_plot.addItem(c)
                self.vwap_bands.append((mult, c))

        self.cvd_curve = pg.PlotDataItem(pen=pg.mkPen(self.theme.cvd, width=2))
        self.cvd_plot.addItem(self.cvd_curve)
        self.cvd_zero = pg.InfiniteLine(angle=0, pos=0, movable=False,
                                        pen=pg.mkPen("#666", style=Qt.PenStyle.DashLine))
        self.cvd_plot.addItem(self.cvd_zero, ignoreBounds=True)

        self.price_line = pg.InfiniteLine(angle=0, movable=False,
                                          pen=pg.mkPen(self.theme.cvd, width=1, style=Qt.PenStyle.DashLine))
        self.price_plot.addItem(self.price_line, ignoreBounds=True)

        self.vline = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen("#666", style=Qt.PenStyle.DashLine))
        self.hline = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen("#666", style=Qt.PenStyle.DashLine))
        self.price_plot.addItem(self.vline, ignoreBounds=True)
        self.price_plot.addItem(self.hline, ignoreBounds=True)

        # Mouse Events & Handlers
        self.glw.scene().sigMouseMoved.connect(self._on_mouse_move)
        self.glw.scene().sigMouseClicked.connect(self._on_mouse_click)
        self.price_plot.sigXRangeChanged.connect(self._on_x_range_changed)

        axis_right = self.price_plot.getAxis("right")
        def axis_drag(ev):
            if ev.isStart():
                axis_drag.last_y = ev.pos().y()
            elif not ev.isFinish():
                curr_y = ev.pos().y()
                dy = curr_y - getattr(axis_drag, 'last_y', curr_y)
                axis_drag.last_y = curr_y
                if dy != 0:
                    s = 1.0 + (dy / 120.0)
                    self.price_vb.scaleBy((1.0, s))
                    self._toggle_autofit(False)
            ev.accept()
        axis_right.mouseDragEvent = axis_drag
        axis_right.mouseDoubleClickEvent = lambda ev: (self._toggle_autofit(True), ev.accept())

    def update_known_symbols(self, symbols: set[str]):
        curr = self.sym_combo.currentText()
        self.sym_combo.blockSignals(True)
        self.sym_combo.clear()
        for s in sorted(symbols):
            self.sym_combo.addItem(s)
        if curr in symbols:
            self.sym_combo.setCurrentText(curr)
        self.sym_combo.blockSignals(False)

    def set_symbol(self, sym: str):
        if sym:
            self.active_symbol = sym
            self.sym_combo.setCurrentText(sym)
            self.fp.tick = self.instruments.tick(sym)
            self._dirty = True
            self.redraw()

    def set_timeframe(self, tf_text: str):
        if tf_text not in TF_CHOICES:
            TF_CHOICES[tf_text] = parse_timeframe(tf_text)
            if tf_text not in self.tf_combo._items:
                self.tf_combo.addItem(tf_text)
        self.tf_s = TF_CHOICES.get(tf_text) or parse_timeframe(tf_text)
        self.tf_combo.setCurrentText(tf_text)
        self._dirty = True
        self.redraw()

    def _on_symbol(self, sym: str):
        if sym:
            self.active_symbol = sym
            self.fp.tick = self.instruments.tick(sym)
            self._dirty = True
            self.redraw()

    def _on_tf(self, txt: str):
        if txt == "Custom...":
            from PyQt6.QtWidgets import QDialog
            dlg = CustomTimeframeDialog(format_timeframe(self.tf_s), self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                tf_text = dlg.selected_tf_text
                tf_val = dlg.selected_tf_val
                TF_CHOICES[tf_text] = tf_val
                if tf_text not in self.tf_combo._items:
                    self.tf_combo.addItem(tf_text)
                self.tf_combo.setCurrentText(tf_text)
                self.tf_s = tf_val
                self._dirty = True
                self.redraw()
            else:
                self.tf_combo.setCurrentText(format_timeframe(self.tf_s))
            return

        self.tf_s = TF_CHOICES.get(txt) or parse_timeframe(txt)
        self._dirty = True
        self.redraw()

    def _on_mode(self, name: str):
        fp_mode, draw_cells, hm_visible = MODES.get(name, ("Footprint", True, False))
        self.fp.set_mode(fp_mode)
        self.fp.set_draw_cells(draw_cells)
        self.heatmap.setVisible(hm_visible)
        self._dirty = True
        self.redraw()

    def _on_toggle_imb(self, on: bool):
        self.fp.set_show_imbalance(on)
        self.redraw()

    def _on_toggle_va(self, on: bool):
        self.fp.set_show_va(on)
        self.redraw()

    def _on_toggle_vwap(self, on: bool):
        self.vwap_curve.setVisible(on)
        for _, curve in self.vwap_bands:
            curve.setVisible(on)
        self.redraw()

    def _on_toggle_cpr(self, on: bool):
        self.cpr_item.setVisible(on)
        self.redraw()

    def _on_toggle_ema(self, on: bool):
        self.ema9_item.setVisible(on)
        self.ema21_item.setVisible(on)
        self.redraw()

    def _toggle_autofit(self, checked=None):
        if checked is None:
            self._auto_fit_enabled = not self._auto_fit_enabled
        elif isinstance(checked, bool):
            self._auto_fit_enabled = checked
        else:
            self._auto_fit_enabled = True

        self.btn_autofit.setChecked(self._auto_fit_enabled)
        if self._auto_fit_enabled:
            self.auto_scroll = True
            self.btn_autofit.setStyleSheet("font-size: 10px; font-weight: bold; background: #2A2A2A; color: #00E676; border: 1px solid #00E676; border-radius: 3px; padding: 1px 5px;")
            self._auto_fit_y()
            self.redraw()
        else:
            self.btn_autofit.setStyleSheet("font-size: 10px; font-weight: bold; background: transparent; color: #8A8A8A; border: 1px solid transparent; border-radius: 3px; padding: 1px 5px;")

    def _auto_fit_y(self):
        if not self.active_symbol or self.active_symbol not in self.main_window.series:
            return
        bars = self.main_window.series[self.active_symbol].view(self.tf_s)
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
        margin = (hi - lo) * 0.05 or 1.0
        self.price_plot.setYRange(lo - margin, hi + margin, padding=0)

    def _on_x_range_changed(self, plot, range_tuple):
        if getattr(self.price_vb, 'is_dragging', False):
            return
        if self._auto_fit_enabled:
            self._auto_fit_y()

    def _on_mouse_move(self, pos):
        if self.price_plot.sceneBoundingRect().contains(pos):
            mp = self.price_plot.vb.mapSceneToView(pos)
            self.vline.setPos(mp.x())
            self.hline.setPos(mp.y())
            # Emit signal for crosshair sync across peer chart cells
            self.sigCrosshairMoved.emit(mp.x(), mp.y(), self)

        if self.main_window and hasattr(self.main_window, '_on_cell_mouse_move'):
            self.main_window._on_cell_mouse_move(self, pos)

    def _on_mouse_click(self, ev):
        if self.main_window and hasattr(self.main_window, '_on_cell_mouse_click'):
            self.main_window._on_cell_mouse_click(self, ev)

    def set_external_crosshair(self, x_val: float, y_val: float):
        """Sync crosshair from an external peer cell."""
        self.vline.setPos(x_val)

    def redraw(self):
        if not self.active_symbol or self.active_symbol not in self.main_window.series:
            return
        s = self.main_window.series[self.active_symbol]
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
                view_w = max(vr.width(), 5.0)
                right_edge = n + 3
                left_edge = max(-1, right_edge - view_w)
                self.price_plot.setXRange(left_edge, right_edge, padding=0)

    def _update_overlays(self, series: BarSeries, bars: list):
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

    def _apply_theme(self):
        t = self.theme
        self.fp.set_theme(t)
        self.vwap_curve.setPen(pg.mkPen(t.vwap, width=2))
        self.cvd_curve.setPen(pg.mkPen(t.cvd, width=2))
        self.glw.setBackground(t.bg)
        for plot in (self.price_plot, self.cvd_plot):
            for ax_name in ("bottom", "right"):
                ax = plot.getAxis(ax_name)
                ax.setPen(pg.mkPen(t.axis))
                ax.setTextPen(pg.mkPen(t.text))
