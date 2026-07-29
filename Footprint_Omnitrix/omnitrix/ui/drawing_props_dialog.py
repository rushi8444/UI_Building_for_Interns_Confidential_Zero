"""DrawingPropsDialog: Modal dialog for editing drawing properties and managing templates."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QColorDialog, QSpinBox, QComboBox, QGroupBox, QListWidget, QMessageBox
)

from ..engine.drawing_templates import TemplateManager


class DrawingPropsDialog(QDialog):
    """Modal dialog for customizing drawing tool styles & managing templates."""

    def __init__(self, tool_type: str, current_style: dict, template_mgr: TemplateManager | None = None, parent=None):
        super().__init__(parent)
        self.tool_type = tool_type
        self.style = dict(current_style)
        self.tmpl_mgr = template_mgr or TemplateManager()
        
        self.setWindowTitle(f"Drawing Properties — {tool_type}")
        self.setFixedSize(450, 420)
        self.setModal(True)

        self._color_btns: dict[str, QPushButton] = {}
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet(
            "QDialog { background-color: #1A1D24; color: #E8E8E8; font-family: 'Inter', sans-serif; }"
            "QLabel { color: #E8E8E8; font-size: 12px; }"
            "QGroupBox { border: 1px solid #2A2A2A; border-radius: 6px; margin-top: 10px; font-weight: bold; color: #26A69A; font-size: 11px; padding: 10px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }"
            "QPushButton { background-color: #2A2A2A; color: #E8E8E8; border: 1px solid #3A3A3A; border-radius: 4px; padding: 4px 10px; font-size: 11px; }"
            "QPushButton:hover { background-color: #3A3A3A; color: #FFFFFF; }"
            "QPushButton#btn_apply { background-color: #26A69A; color: #FFFFFF; font-weight: bold; border: none; padding: 6px 14px; }"
            "QPushButton#btn_apply:hover { background-color: #2BBBAD; }"
            "QSpinBox, QComboBox, QLineEdit { background-color: #2A2A2A; color: #FFFFFF; border: 1px solid #3A3A3A; border-radius: 4px; padding: 4px; font-size: 11px; }"
            "QListWidget { background-color: #14161C; color: #E8E8E8; border: 1px solid #2A2A2A; border-radius: 4px; font-size: 11px; }"
            "QListWidget::item:selected { background-color: #26A69A; color: #FFFFFF; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Style Options Group
        grp_style = QGroupBox("STYLE & APPEARANCE")
        grp_layout = QVBoxLayout(grp_style)
        grp_layout.setSpacing(8)

        # Dynamic Color fields depending on style keys
        color_keys = [k for k in self.style if "color" in k]
        for key in color_keys:
            r = QHBoxLayout()
            label_name = key.replace("_", " ").title()
            lbl = QLabel(label_name)
            r.addWidget(lbl)

            btn_c = QPushButton()
            btn_c.setFixedWidth(65)
            self._update_btn_color(btn_c, self.style[key])
            btn_c.clicked.connect(lambda _, k=key, b=btn_c: self._pick_color(k, b))
            self._color_btns[key] = btn_c
            r.addWidget(btn_c)
            grp_layout.addLayout(r)

        # Line Width
        if "line_width" in self.style:
            r = QHBoxLayout()
            r.addWidget(QLabel("Line Width"))
            sb_w = QSpinBox()
            sb_w.setRange(1, 10)
            sb_w.setValue(int(self.style["line_width"]))
            sb_w.valueChanged.connect(lambda v: self.style.update({"line_width": v}))
            r.addWidget(sb_w)
            grp_layout.addLayout(r)

        # Opacity / Alpha
        alpha_key = "fill_alpha" if "fill_alpha" in self.style else ("box_alpha" if "box_alpha" in self.style else None)
        if alpha_key:
            r = QHBoxLayout()
            r.addWidget(QLabel("Opacity / Alpha (0-255)"))
            sb_a = QSpinBox()
            sb_a.setRange(0, 255)
            sb_a.setValue(int(self.style[alpha_key]))
            sb_a.valueChanged.connect(lambda v, k=alpha_key: self.style.update({k: v}))
            r.addWidget(sb_a)
            grp_layout.addLayout(r)

        layout.addWidget(grp_style)

        # Template Management Group
        grp_tmpl = QGroupBox("PRESET TEMPLATES")
        tmpl_layout = QVBoxLayout(grp_tmpl)

        t_row = QHBoxLayout()
        self.list_tmpls = QListWidget()
        self.list_tmpls.setMaximumHeight(80)
        self._refresh_template_list()
        t_row.addWidget(self.list_tmpls)

        btn_col = QVBoxLayout()
        btn_apply_tmpl = QPushButton("Apply Template")
        btn_apply_tmpl.clicked.connect(self._on_apply_template)
        btn_col.addWidget(btn_apply_tmpl)

        btn_del_tmpl = QPushButton("Delete")
        btn_del_tmpl.clicked.connect(self._on_delete_template)
        btn_col.addWidget(btn_del_tmpl)

        t_row.addLayout(btn_col)
        tmpl_layout.addLayout(t_row)

        # Save template row
        save_row = QHBoxLayout()
        self.txt_tmpl_name = QLineEdit()
        self.txt_tmpl_name.setPlaceholderText("Template Name (e.g. Gold Support)")
        save_row.addWidget(self.txt_tmpl_name)

        btn_save_tmpl = QPushButton("Save Style As Template")
        btn_save_tmpl.clicked.connect(self._on_save_template)
        save_row.addWidget(btn_save_tmpl)

        tmpl_layout.addLayout(save_row)
        layout.addWidget(grp_tmpl)

        # Dialog Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_ok = QPushButton("Apply Style")
        btn_ok.setObjectName("btn_apply")
        btn_ok.clicked.connect(self.accept)
        btn_row.addWidget(btn_ok)

        layout.addLayout(btn_row)

    def _update_btn_color(self, btn: QPushButton, hex_color: str):
        btn.setText(hex_color)
        btn.setStyleSheet(f"background-color: {hex_color}; color: #FFFFFF; font-weight: bold; border: 1px solid #555;")

    def _pick_color(self, key: str, btn: QPushButton):
        c = QColorDialog.getColor(QColor(self.style.get(key, "#26A69A")), self, "Select Color")
        if c.isValid():
            hex_c = c.name().upper()
            self.style[key] = hex_c
            self._update_btn_color(btn, hex_c)

    def _refresh_template_list(self):
        self.list_tmpls.clear()
        tmpls = self.tmpl_mgr.get_templates_for(self.tool_type)
        for t_name in sorted(tmpls.keys()):
            self.list_tmpls.addItem(t_name)

    def _on_save_template(self):
        name = self.txt_tmpl_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing Name", "Please enter a template name.")
            return
        self.tmpl_mgr.save_template(self.tool_type, name, self.style)
        self._refresh_template_list()
        self.txt_tmpl_name.clear()

    def _on_apply_template(self):
        curr = self.list_tmpls.currentItem()
        if not curr:
            return
        t_name = curr.text()
        tmpls = self.tmpl_mgr.get_templates_for(self.tool_type)
        if t_name in tmpls:
            self.style.update(tmpls[t_name])
            for key, btn in self._color_btns.items():
                if key in self.style:
                    self._update_btn_color(btn, self.style[key])
            self.accept()

    def _on_delete_template(self):
        curr = self.list_tmpls.currentItem()
        if not curr:
            return
        t_name = curr.text()
        self.tmpl_mgr.delete_template(self.tool_type, t_name)
        self._refresh_template_list()
