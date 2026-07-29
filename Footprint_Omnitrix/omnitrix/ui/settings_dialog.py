"""Customization dialog — every knob that shapes the chart lives here."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QDoubleSpinBox, QSpinBox, QCheckBox, QPushButton,
    QColorDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget, QFrame,
)

DIALOG_STYLE = """
QDialog {
    background-color: #121212;
    color: #E8E8E8;
    font-family: "Inter", "Segoe UI", sans-serif;
    font-size: 10pt;
}
QLabel {
    color: #CECECE;
    font-size: 10pt;
    font-weight: 500;
}
QLineEdit, QSpinBox, QDoubleSpinBox {
    background-color: #1A1A1A;
    color: #E8E8E8;
    border: 1px solid #2A2A2A;
    border-radius: 4px;
    padding: 4px 8px;
    selection-background-color: #26A69A;
    selection-color: #000000;
}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover {
    border-color: #388E3C;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #26A69A;
    background-color: #1E1E1E;
}
QCheckBox {
    color: #CECECE;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    background-color: #1A1A1A;
    border: 1px solid #2A2A2A;
    border-radius: 3px;
}
QCheckBox::indicator:hover {
    border-color: #26A69A;
}
QCheckBox::indicator:checked {
    background-color: #26A69A;
    border-color: #26A69A;
}
QPushButton {
    background-color: #1A1A1A;
    color: #E8E8E8;
    border: 1px solid #2A2A2A;
    border-radius: 4px;
    padding: 5px 16px;
    min-height: 24px;
}
QPushButton:hover {
    background-color: #242424;
    border-color: #404040;
}
QPushButton:pressed {
    background-color: #26A69A;
    color: #000000;
}
QPushButton#ApplyButton {
    background-color: #26A69A;
    color: #000000;
    font-weight: bold;
    border-radius: 4px;
    padding: 6px 20px;
    border: none;
    min-height: 26px;
}
QPushButton#ApplyButton:hover {
    background-color: #2EBAAE;
}
QPushButton#ApplyButton:pressed {
    background-color: #1F8E83;
}
QPushButton#CancelButton {
    background-color: #1A1A1A;
    color: #E8E8E8;
    border: 1px solid #2A2A2A;
    border-radius: 4px;
    padding: 6px 20px;
    min-height: 26px;
}
QPushButton#CancelButton:hover {
    background-color: #242424;
    border-color: #404040;
}
"""


class _ColorButton(QPushButton):
    """A button that opens a colour picker and remembers the chosen QColor."""

    def __init__(self, color: QColor):
        super().__init__()
        self._color = QColor(color)
        self.setFixedWidth(85)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh()
        self.clicked.connect(self._pick)

    def _refresh(self) -> None:
        c = self._color
        lum = (0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()) / 255.0
        text_col = "#000000" if lum > 0.55 else "#FFFFFF"
        self.setStyleSheet(
            f"background:{c.name()}; color:{text_col}; border:1px solid #3A3A3A; "
            f"border-radius:4px; font-weight:700; font-family:'Consolas',monospace; padding:3px 6px;"
        )
        self.setText(c.name().upper())

    def _pick(self) -> None:
        dlg = QColorDialog(self._color, self)
        dlg.setWindowTitle("Omnitrix Colour Picker")
        dlg.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
        dlg.setStyleSheet(DIALOG_STYLE)
        if dlg.exec():
            c = dlg.currentColor()
            if c.isValid():
                self._color = c
                self._refresh()

    def color(self) -> QColor:
        return self._color


class SettingsDialog(QDialog):
    """Reads current state from the window, lets the user edit, and applies."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Omnitrix Chart Settings")
        self.setMinimumWidth(380)
        self.setStyleSheet(DIALOG_STYLE)

        fp = win.fp
        t = win.theme

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        header = QLabel("TERMINAL & CHART PREFERENCES")
        header.setStyleSheet("color: #888888; font-size: 8pt; font-weight: bold; letter-spacing: 1px; margin-bottom: 4px;")
        root.addWidget(header)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(form)

        self.tick = QDoubleSpinBox()
        self.tick.setDecimals(4); self.tick.setRange(0.0001, 100.0)
        self.tick.setSingleStep(0.01)
        self.tick.setValue(win.instruments.tick(win.active_symbol or "QQQ"))
        form.addRow("Tick size", self.tick)

        self.imb = QDoubleSpinBox()
        self.imb.setRange(1.1, 20.0); self.imb.setSingleStep(0.5)
        self.imb.setValue(fp.imbalance_factor)
        form.addRow("Imbalance factor ×", self.imb)

        self.minvol = QSpinBox()
        self.minvol.setRange(0, 100000); self.minvol.setValue(fp.min_imbalance_vol)
        form.addRow("Min imbalance vol", self.minvol)

        self.stacked = QSpinBox()
        self.stacked.setRange(2, 20); self.stacked.setValue(fp.stacked_min)
        form.addRow("Stacked levels ≥", self.stacked)

        self.vapct = QSpinBox()
        self.vapct.setRange(30, 95); self.vapct.setValue(int(fp.va_pct * 100))
        self.vapct.setSuffix(" %")
        form.addRow("Value area", self.vapct)

        self.hm_alpha = QSpinBox()
        self.hm_alpha.setRange(20, 255); self.hm_alpha.setValue(win.heatmap.alpha)
        form.addRow("Heatmap intensity", self.hm_alpha)

        self.hm_gamma = QDoubleSpinBox()
        self.hm_gamma.setRange(0.2, 1.5); self.hm_gamma.setSingleStep(0.05)
        self.hm_gamma.setValue(win.heatmap.gamma)
        form.addRow("Heatmap gamma", self.hm_gamma)

        self.chk_candles = QCheckBox(); self.chk_candles.setChecked(fp.show_candles)
        form.addRow("Show candles", self.chk_candles)

        self.chk_cvd_div = QCheckBox(); self.chk_cvd_div.setChecked(getattr(win, "show_cvd_div", False))
        form.addRow("Show CVD Divergence", self.chk_cvd_div)

        # Colour pickers
        self.c_bull = _ColorButton(QColor(t.bull))
        self.c_bear = _ColorButton(QColor(t.bear))
        self.c_buy = _ColorButton(t.buy_imb)
        self.c_sell = _ColorButton(t.sell_imb)
        for label, btn in (("Up / buy", self.c_bull), ("Down / sell", self.c_bear),
                           ("Buy imbalance", self.c_buy), ("Sell imbalance", self.c_sell)):
            form.addRow(label, btn)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Plain)
        sep.setStyleSheet("color: #1F1F1F; margin-top: 6px; margin-bottom: 2px;")
        root.addWidget(sep)

        btns = QHBoxLayout()
        ok = QPushButton("Apply"); ok.setObjectName("ApplyButton"); ok.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel = QPushButton("Cancel"); cancel.setObjectName("CancelButton"); cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.clicked.connect(self.accept); cancel.clicked.connect(self.reject)
        btns.addStretch(1); btns.addWidget(cancel); btns.addWidget(ok)
        root.addLayout(btns)

    def values(self) -> dict:
        return {
            "tick": self.tick.value(),
            "imbalance_factor": self.imb.value(),
            "min_imbalance_vol": self.minvol.value(),
            "stacked_min": self.stacked.value(),
            "va_pct": self.vapct.value() / 100.0,
            "hm_alpha": self.hm_alpha.value(),
            "hm_gamma": self.hm_gamma.value(),
            "show_candles": self.chk_candles.isChecked(),
            "show_cvd_div": self.chk_cvd_div.isChecked(),
            "bull": self.c_bull.color().name(),
            "bear": self.c_bear.color().name(),
            "buy_imb": self.c_buy.color(),
            "sell_imb": self.c_sell.color(),
        }
