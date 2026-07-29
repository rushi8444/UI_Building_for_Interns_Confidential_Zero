"""Timeframe string parser and formatter for arbitrary interval aggregations.

Supports:
    - Seconds (s): "5s" -> 5
    - Minutes (m): "7m" -> 420
    - Hours (h):   "2h" -> 7200
    - Days (d):    "1d" -> 86400
    - Ticks (T):   "500T" -> "500T"
"""

from __future__ import annotations
import re

_TF_REGEX = re.compile(r"^\s*(\d+)\s*([sStTmMhHdD]?)\s*$")


def is_tick_timeframe(tf_str: str) -> bool:
    """Return True if timeframe string represents a tick-count interval (e.g. '500T')."""
    if not tf_str or not isinstance(tf_str, str):
        return False
    return tf_str.strip().upper().endswith("T")


def get_tick_count(tf_str: str) -> int | None:
    """Extract integer tick count from a tick timeframe string (e.g. '500T' -> 500)."""
    if not is_tick_timeframe(tf_str):
        return None
    m = _TF_REGEX.match(tf_str)
    if m:
        try:
            val = int(m.group(1))
            return val if val > 0 else 500
        except ValueError:
            pass
    return 500


def parse_timeframe(tf_str: str) -> int | str:
    """Parse a timeframe string into integer seconds or tick string descriptor.
    
    If unit is 'T' or 't' (e.g. "500T"), returns the normalized tick string "500T".
    If no unit is specified (e.g. "5"), minutes are assumed.
    Returns default of 60 seconds if invalid.
    """
    if not tf_str or not isinstance(tf_str, str):
        return 60

    tf_str = tf_str.strip()
    if is_tick_timeframe(tf_str):
        count = get_tick_count(tf_str) or 500
        return f"{count}T"

    m = _TF_REGEX.match(tf_str)
    if not m:
        return 60

    val_str, unit_str = m.groups()
    val = int(val_str)
    if val <= 0:
        return 60

    unit = unit_str.lower() if unit_str else "m"
    if unit == "s":
        return val
    elif unit == "m":
        return val * 60
    elif unit == "h":
        return val * 3600
    elif unit == "d":
        return val * 86400
    return val * 60


def format_timeframe(tf_val: int | str) -> str:
    """Format integer seconds or tick string into clean timeframe text."""
    if isinstance(tf_val, str):
        if is_tick_timeframe(tf_val):
            return tf_val.strip().upper()
        try:
            tf_val = int(tf_val)
        except ValueError:
            return "1m"

    if tf_val <= 0:
        return "1m"
    if tf_val < 60:
        return f"{tf_val}s"
    if tf_val % 86400 == 0:
        return f"{tf_val // 86400}d"
    if tf_val % 3600 == 0:
        return f"{tf_val // 3600}h"
    if tf_val % 60 == 0:
        return f"{tf_val // 60}m"
    return f"{tf_val}s"
