"""CustomTimeframeDialog: Modal dialog for entering arbitrary timeframe intervals.

Allows traders to enter custom intervals (e.g. "5s", "45s", "3m", "7m", "2h", "100T", "500T").
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton
)

from ..engine.timeframe import parse_timeframe, format_timeframe, is_tick_timeframe, get_tick_count


class CustomTimeframeDialog(QDialog):
    """Sleek dark-themed modal dialog for typing custom timeframe & tick intervals."""

    def __init__(self, current_tf: str = "1m", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Custom Timeframe & Tick Interval")
        self.setFixedSize(360, 230)
        self.setModal(True)
        
        self.selected_tf_text = current_tf
        self.selected_tf_val = parse_timeframe(current_tf)

        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet(
            "QDialog { background-color: #1A1D24; color: #E8E8E8; font-family: 'Inter', sans-serif; }"
            "QLabel { color: #E8E8E8; font-size: 12px; }"
            "QLineEdit { background-color: #2A2A2A; color: #FFFFFF; border: 1px solid #3A3A3A; border-radius: 4px; padding: 6px 10px; font-size: 13px; font-weight: bold; }"
            "QLineEdit:focus { border: 1px solid #26A69A; }"
            "QPushButton { background-color: #2A2A2A; color: #E8E8E8; border: 1px solid #3A3A3A; border-radius: 4px; padding: 5px 10px; font-size: 11px; font-weight: 500; }"
            "QPushButton:hover { background-color: #3A3A3A; color: #FFFFFF; }"
            "QPushButton#btn_apply { background-color: #26A69A; color: #FFFFFF; font-weight: bold; border: none; padding: 6px 14px; }"
            "QPushButton#btn_apply:hover { background-color: #2BBBAD; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        lbl_title = QLabel("Custom interval (e.g. 5s, 7m, 2h, 100T, 500T):")
        lbl_title.setStyleSheet("font-weight: 600; font-size: 12px; color: #B0B0B0;")
        layout.addWidget(lbl_title)

        # Input line
        self.input_tf = QLineEdit(self.selected_tf_text)
        self.input_tf.setPlaceholderText("e.g. 5s, 7m, 500T")
        self.input_tf.textChanged.connect(self._on_input_changed)
        layout.addWidget(self.input_tf)

        # Live validation feedback label
        self.lbl_feedback = QLabel()
        self.lbl_feedback.setStyleSheet("color: #26A69A; font-size: 11px; font-style: italic;")
        layout.addWidget(self.lbl_feedback)

        # Quick preset buttons layout
        lbl_presets = QLabel("Quick Presets:")
        lbl_presets.setStyleSheet("font-size: 11px; color: #8A8A8A; margin-top: 2px;")
        layout.addWidget(lbl_presets)

        preset_layout = QHBoxLayout()
        preset_layout.setSpacing(4)
        for preset in ["5s", "15s", "3m", "7m", "100T", "500T"]:
            btn_p = QPushButton(preset)
            btn_p.setStyleSheet("padding: 3px 6px; font-size: 11px;")
            btn_p.clicked.connect(lambda _, p=preset: self.input_tf.setText(p))
            preset_layout.addWidget(btn_p)
        layout.addLayout(preset_layout)

        # Buttons row
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        self.btn_apply = QPushButton("Apply")
        self.btn_apply.setObjectName("btn_apply")
        self.btn_apply.clicked.connect(self._on_apply)
        btn_layout.addWidget(self.btn_apply)

        layout.addLayout(btn_layout)

        self._on_input_changed(self.input_tf.text())

    def _on_input_changed(self, text: str):
        val = parse_timeframe(text)
        if isinstance(val, str) and is_tick_timeframe(val):
            cnt = get_tick_count(val) or 500
            self.lbl_feedback.setText(f"✓ Tick Interval: {cnt:,} Trades per Candle")
            self.lbl_feedback.setStyleSheet("color: #00E676; font-size: 11px; font-weight: 500;")
            self.btn_apply.setEnabled(True)
        elif isinstance(val, int) and val > 0:
            fmt = format_timeframe(val)
            self.lbl_feedback.setText(f"✓ Time Interval: {fmt} ({val:,} seconds)")
            self.lbl_feedback.setStyleSheet("color: #26A69A; font-size: 11px; font-weight: 500;")
            self.btn_apply.setEnabled(True)
        else:
            self.lbl_feedback.setText("✕ Invalid timeframe or tick format")
            self.lbl_feedback.setStyleSheet("color: #EF5350; font-size: 11px;")
            self.btn_apply.setEnabled(False)

    def _on_apply(self):
        text = self.input_tf.text().strip()
        val = parse_timeframe(text)
        self.selected_tf_val = val
        self.selected_tf_text = format_timeframe(val)
        self.accept()
