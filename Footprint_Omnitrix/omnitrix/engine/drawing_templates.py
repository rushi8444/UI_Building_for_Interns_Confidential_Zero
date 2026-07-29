"""TemplateManager: Persistent JSON storage and management for drawing tool templates & preset styling.

Stores custom styling presets for drawing tools (FibRetracement, PositionDrawer,
FixedVolumeProfile, RangeCPR) in ~/.omnitrix_templates.json.
"""

from __future__ import annotations

import json
import os

TEMPLATES_PATH = os.path.join(os.path.expanduser("~"), ".omnitrix_templates.json")

DEFAULT_TEMPLATES = {
    "FibRetracement": {
        "Classic Fibonacci": {
            "line_color": "#26A69A",
            "line_width": 1,
            "line_style": "Solid",
            "fill_alpha": 30,
            "show_labels": True,
        },
        "Golden Zone Focus": {
            "line_color": "#FFD54F",
            "line_width": 2,
            "line_style": "Solid",
            "fill_alpha": 50,
            "show_labels": True,
        },
        "High Contrast": {
            "line_color": "#00E676",
            "line_width": 2,
            "line_style": "Dashed",
            "fill_alpha": 40,
            "show_labels": True,
        },
    },
    "PositionDrawer": {
        "Default 1:2 R:R": {
            "target_color": "#388E3C",
            "stop_color": "#D32F2F",
            "box_alpha": 45,
            "line_width": 1,
            "show_labels": True,
        },
        "Scalp 1:1": {
            "target_color": "#26A69A",
            "stop_color": "#EF5350",
            "box_alpha": 60,
            "line_width": 2,
            "show_labels": True,
        },
        "Swing 1:3": {
            "target_color": "#00C853",
            "stop_color": "#FF1744",
            "box_alpha": 40,
            "line_width": 2,
            "show_labels": True,
        },
    },
    "FixedVolumeProfile": {
        "Vibrant 70% Value Area": {
            "va_color": "#2962FF",
            "poc_color": "#FF1744",
            "out_color": "#707070",
            "line_width": 1,
            "show_labels": True,
        },
        "High Contrast Neon": {
            "va_color": "#00E676",
            "poc_color": "#FFD54F",
            "out_color": "#505050",
            "line_width": 2,
            "show_labels": True,
        },
    },
    "RangeCPR": {
        "Classic Pivot": {
            "p_color": "#E91E63",
            "tc_bc_color": "#00BCD4",
            "r_color": "#4CAF50",
            "s_color": "#F44336",
            "line_width": 1,
            "show_labels": True,
        },
        "Neon CPR": {
            "p_color": "#FF007F",
            "tc_bc_color": "#00E5FF",
            "r_color": "#76FF03",
            "s_color": "#FF3D00",
            "line_width": 2,
            "show_labels": True,
        },
    },
}


class TemplateManager:
    """Manages loading, saving, listing, and deleting drawing templates."""

    def __init__(self, path: str = TEMPLATES_PATH):
        self.path = path
        self.templates: dict[str, dict[str, dict]] = {}
        self._load()

    def _load(self):
        # Start with default presets
        self.templates = {k: dict(v) for k, v in DEFAULT_TEMPLATES.items()}
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    for tool_type, t_dict in data.items():
                        if tool_type not in self.templates:
                            self.templates[tool_type] = {}
                        if isinstance(t_dict, dict):
                            self.templates[tool_type].update(t_dict)
            except Exception:
                pass

    def save_to_disk(self) -> bool:
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.templates, f, indent=2)
            os.replace(tmp, self.path)
            return True
        except Exception:
            return False

    def get_templates_for(self, tool_type: str) -> dict[str, dict]:
        """Return dict of template_name -> style_dict for the given tool_type."""
        return dict(self.templates.get(tool_type, {}))

    def save_template(self, tool_type: str, template_name: str, style_dict: dict) -> bool:
        """Save or overwrite a named template for a drawing tool type."""
        if tool_type not in self.templates:
            self.templates[tool_type] = {}
        self.templates[tool_type][template_name] = dict(style_dict)
        return self.save_to_disk()

    def delete_template(self, tool_type: str, template_name: str) -> bool:
        """Delete a template by name for a given tool type."""
        if tool_type in self.templates and template_name in self.templates[tool_type]:
            del self.templates[tool_type][template_name]
            return self.save_to_disk()
        return False
