"""Custom Spread Math Formula Engine for synthetic instruments.

Supports ratio and difference charts e.g. "AAPL / SPY", "QQQ - SPY", "(2 * AAPL) + SPY".
Parses constituent tickers, safely evaluates arithmetic expressions, aligns bar timestamps,
and generates synthetic OHLC Bar series for standard footprint / chart rendering.
"""

from __future__ import annotations

import ast
import re
from .bars import Bar, BarSeries

_TICKER_REGEX = re.compile(r"[A-Za-z]{1,6}")
_ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Add, ast.Sub,
    ast.Mult, ast.Div, ast.Constant, ast.Name, ast.Load, ast.USub, ast.UAdd
)


def parse_spread_symbols(formula: str) -> list[str]:
    """Extract constituent symbol tickers from a math formula string."""
    if not formula or not isinstance(formula, str):
        return []

    # Exclude reserved words / common single tickers if simple
    tokens = _TICKER_REGEX.findall(formula.upper())
    # Keep unique ordered symbols
    symbols = []
    for t in tokens:
        if t not in symbols and t not in ("AND", "OR", "NOT"):
            symbols.append(t)
    return symbols


def is_spread_formula(symbol_str: str) -> bool:
    """Return True if symbol_str contains arithmetic formula operators (+, -, *, /)."""
    if not symbol_str or not isinstance(symbol_str, str):
        return False
    return any(op in symbol_str for op in ("/", "+", "-", "*"))


def evaluate_spread(formula: str, prices: dict[str, float]) -> float:
    """Safely evaluate an arithmetic formula given a dictionary of symbol prices."""
    if not formula:
        return 0.0

    try:
        tree = ast.parse(formula.strip(), mode="eval")
    except SyntaxError:
        return 0.0

    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            return 0.0

    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        elif isinstance(node, ast.Constant):
            return float(node.value)
        elif isinstance(node, ast.Name):
            sym = node.id.upper()
            return prices.get(sym, 0.0)
        elif isinstance(node, ast.UnaryOp):
            operand = _eval(node.operand)
            if isinstance(node.op, ast.USub):
                return -operand
            elif isinstance(node.op, ast.UAdd):
                return +operand
        elif isinstance(node, ast.BinOp):
            left = _eval(node.left)
            right = _eval(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            elif isinstance(node.op, ast.Sub):
                return left - right
            elif isinstance(node.op, ast.Mult):
                return left * right
            elif isinstance(node.op, ast.Div):
                return left / right if right != 0 else 0.0
        return 0.0

    try:
        return _eval(tree)
    except Exception:
        return 0.0


class SyntheticSpreadSeries:
    """Synthetic BarSeries produced by evaluating a spread formula over constituent BarSeries."""

    def __init__(self, formula: str, series_dict: dict[str, BarSeries]):
        self.formula = formula
        self.series_dict = series_dict
        self.symbols = parse_spread_symbols(formula)

    def cvd(self, tf: int | str) -> list[float]:
        """Synthetic CVD series."""
        acc = 0.0
        out = []
        for b in self.view(tf):
            acc += b.delta
            out.append(acc)
        return out

    def view(self, tf: int | str) -> list[Bar]:
        """Align bars across all constituent series by start_ts and produce synthetic bars."""
        if not self.symbols or not self.series_dict:
            return []

        # Gather view bars for each constituent symbol
        bars_by_sym: dict[str, list[Bar]] = {}
        for sym in self.symbols:
            s = self.series_dict.get(sym)
            if s:
                bars_by_sym[sym] = s.view(tf)
            else:
                bars_by_sym[sym] = []

        if not any(bars_by_sym.values()):
            return []

        # Find common timestamps
        ts_map: dict[int, dict[str, Bar]] = {}
        for sym, b_list in bars_by_sym.items():
            for b in b_list:
                if b.start_ts not in ts_map:
                    ts_map[b.start_ts] = {}
                ts_map[b.start_ts][sym] = b

        sorted_ts = sorted(ts_map.keys())
        out: list[Bar] = []

        for ts in sorted_ts:
            sym_bars = ts_map[ts]
            # Must have at least one valid bar at this timestamp
            opens = {sym: b.open for sym, b in sym_bars.items()}
            highs = {sym: b.high for sym, b in sym_bars.items()}
            lows = {sym: b.low for sym, b in sym_bars.items()}
            closes = {sym: b.close for sym, b in sym_bars.items()}

            s_open = evaluate_spread(self.formula, opens)
            s_high = evaluate_spread(self.formula, highs)
            s_low = evaluate_spread(self.formula, lows)
            s_close = evaluate_spread(self.formula, closes)

            # Ensure high >= max(open, close) and low <= min(open, close)
            s_high_final = max(s_high, s_open, s_close)
            s_low_final = min(s_low, s_open, s_close)

            syn_bar = Bar(ts, 0, s_open)
            syn_bar.high = s_high_final
            syn_bar.low = s_low_final
            syn_bar.close = s_close
            syn_bar.volume = sum(b.volume for b in sym_bars.values())
            syn_bar.delta = sum(b.delta for b in sym_bars.values())
            syn_bar.seal()
            out.append(syn_bar)

        return out
