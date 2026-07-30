"""Data Window Widget for Omnitrix Order Flow Terminal.

Provides a real-time hover inspector displaying detailed candlestick
and footprint analytics (OHLC, Volume, Delta, Delta %, POC, Buy/Sell Vol, Imbalances).
"""

import datetime
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QLabel, QFrame
)


class DataWindowWidget(QWidget):
    """TradingView style Data Window / Order Flow Hover Inspector Panel."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Style
        self.setStyleSheet("""
            QWidget {
                background-color: #121212;
                color: #E8E8E8;
                font-family: 'Inter', sans-serif;
            }
        """)

        # Title
        self.lbl_title = QLabel("ORDER FLOW INSPECTOR")
        self.lbl_title.setStyleSheet("color: #8A8A8A; font-weight: bold; font-size: 11px; letter-spacing: 1px;")
        layout.addWidget(self.lbl_title)

        # Subtitle / Time
        self.lbl_time = QLabel("Hover over a bar...")
        self.lbl_time.setStyleSheet("color: #00E676; font-size: 13px; font-weight: bold;")
        layout.addWidget(self.lbl_time)

        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #2A2A2A;")
        layout.addWidget(line)

        # Grid Layout for Inspector Values
        grid = QGridLayout()
        grid.setSpacing(8)
        grid.setContentsMargins(0, 4, 0, 4)

        def add_row(row, label_text, default_val="--"):
            lbl_key = QLabel(label_text)
            lbl_key.setStyleSheet("color: #8A8A8A; font-weight: 500; font-size: 12px;")
            lbl_val = QLabel(default_val)
            lbl_val.setStyleSheet("color: #FFFFFF; font-weight: 600; font-family: monospace; font-size: 12px;")
            lbl_val.setAlignment(Qt.AlignmentFlag.AlignRight)
            grid.addWidget(lbl_key, row, 0)
            grid.addWidget(lbl_val, row, 1)
            return lbl_val

        self.val_open = add_row(0, "Open")
        self.val_high = add_row(1, "High")
        self.val_low = add_row(2, "Low")
        self.val_close = add_row(3, "Close")
        self.val_vol = add_row(4, "Volume")
        self.val_delta = add_row(5, "Delta")
        self.val_delta_pct = add_row(6, "Delta %")
        self.val_buy_vol = add_row(7, "Buy Vol")
        self.val_sell_vol = add_row(8, "Sell Vol")
        self.val_poc = add_row(9, "POC Price")
        self.val_poc_vol = add_row(10, "POC Vol")
        self.val_imb = add_row(11, "Imbalances (B/S)")

        layout.addLayout(grid)
        layout.addStretch()

    def set_theme(self, theme):
        self.theme = theme
        t = theme
        if getattr(t, "name", "dark") == "light":
            self.setStyleSheet(f"""
                QWidget {{
                    background-color: {t.bg};
                    color: {t.text};
                    font-family: 'Inter', sans-serif;
                }}
            """)
            self.lbl_title.setStyleSheet("color: #667085; font-weight: bold; font-size: 11px; letter-spacing: 1px;")
            self.lbl_time.setStyleSheet("color: #00897B; font-size: 13px; font-weight: bold;")
        else:
            self.setStyleSheet(f"""
                QWidget {{
                    background-color: {t.bg};
                    color: {t.text};
                    font-family: 'Inter', sans-serif;
                }}
            """)
            self.lbl_title.setStyleSheet("color: #8A8A8A; font-weight: bold; font-size: 11px; letter-spacing: 1px;")
            self.lbl_time.setStyleSheet("color: #00E676; font-size: 13px; font-weight: bold;")

    def update_bar(self, bar, tick_size: float):
        """Update inspector labels with metrics from the hovered Bar object."""
        try:
            dt_str = datetime.datetime.fromtimestamp(bar.start_ts).strftime("%H:%M:%S")
            self.lbl_time.setText(f"TIME: {dt_str}")

            self.val_open.setText(f"{bar.open:,.2f}")
            self.val_high.setText(f"{bar.high:,.2f}")
            self.val_low.setText(f"{bar.low:,.2f}")
            self.val_close.setText(f"{bar.close:,.2f}")

            # Color close based on green/red candle
            if bar.close >= bar.open:
                self.val_close.setStyleSheet("color: #00E676; font-weight: 600; font-family: monospace; font-size: 12px;")
            else:
                self.val_close.setStyleSheet("color: #FF1744; font-weight: 600; font-family: monospace; font-size: 12px;")

            self.val_vol.setText(f"{bar.volume:,}")

            # Delta
            d_color = "#00E676" if bar.delta >= 0 else "#FF1744"
            d_prefix = "+" if bar.delta > 0 else ""
            self.val_delta.setText(f"{d_prefix}{bar.delta:,}")
            self.val_delta.setStyleSheet(f"color: {d_color}; font-weight: 600; font-family: monospace; font-size: 12px;")

            # Delta %
            pct = (bar.delta / bar.volume * 100.0) if bar.volume > 0 else 0.0
            self.val_delta_pct.setText(f"{pct:+.1f}%")
            self.val_delta_pct.setStyleSheet(f"color: {d_color}; font-weight: 600; font-family: monospace; font-size: 12px;")

            # Buy / Sell Vol
            buy_v = sum(c[1] for c in bar.cells.values())
            sell_v = sum(c[0] for c in bar.cells.values())
            self.val_buy_vol.setText(f"{buy_v:,}")
            self.val_sell_vol.setText(f"{sell_v:,}")

            # POC
            poc_idx = bar.poc
            if poc_idx is not None and poc_idx in bar.cells:
                poc_price = poc_idx * tick_size
                cell = bar.cells[poc_idx]
                poc_vol = cell[0] + cell[1]
                self.val_poc.setText(f"{poc_price:,.2f}")
                self.val_poc_vol.setText(f"{poc_vol:,}")
            else:
                self.val_poc.setText("--")
                self.val_poc_vol.setText("--")

            # Imbalance Counts (3.0 ratio threshold)
            buy_imb_count = 0
            sell_imb_count = 0
            sorted_ticks = sorted(bar.cells)
            for i, ti in enumerate(sorted_ticks):
                cell = bar.cells[ti]
                # Diagonal buy imbalance: buy_vol at ti vs sell_vol at ti-1
                if ti - 1 in bar.cells:
                    below_sell = bar.cells[ti - 1][0]
                    if below_sell > 0 and (cell[1] / below_sell) >= 3.0:
                        buy_imb_count += 1
                # Diagonal sell imbalance: sell_vol at ti vs buy_vol at ti+1
                if ti + 1 in bar.cells:
                    above_buy = bar.cells[ti + 1][1]
                    if above_buy > 0 and (cell[0] / above_buy) >= 3.0:
                        sell_imb_count += 1

            self.val_imb.setText(f"{buy_imb_count} / {sell_imb_count}")

        except Exception as e:
            pass


class CandleHoverPopup(QWidget):
    """Sleek floating tooltip popup card that follows mouse cursor on candle hover."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)
        
        self.setStyleSheet("""
            CandleHoverPopup {
                background-color: #1A1A1D;
                border: 1px solid #333336;
                border-radius: 6px;
                color: #E8E8E8;
                font-family: 'Inter', sans-serif;
            }
            QLabel {
                font-size: 11px;
            }
        """)
        
        self.lbl_time = QLabel()
        self.lbl_time.setStyleSheet("color: #8A8A8A; font-weight: bold; font-size: 10px; letter-spacing: 0.5px;")
        layout.addWidget(self.lbl_time)
        
        self.lbl_ohlc = QLabel()
        self.lbl_ohlc.setStyleSheet("color: #FFFFFF; font-weight: 500; font-family: monospace;")
        layout.addWidget(self.lbl_ohlc)
        
        self.lbl_vol_delta = QLabel()
        self.lbl_vol_delta.setStyleSheet("color: #00E676; font-weight: 600; font-family: monospace;")
        layout.addWidget(self.lbl_vol_delta)
        
        self.lbl_poc_imb = QLabel()
        self.lbl_poc_imb.setStyleSheet("color: #AAAAAA; font-size: 10px;")
        layout.addWidget(self.lbl_poc_imb)

    def update_bar(self, bar, tick_size: float, global_pos):
        """Update floating popup with metrics and move to cursor position."""
        try:
            win = self.parent() or self.window()
            t = getattr(win, "theme", None)
            if t and getattr(t, "name", "dark") == "light":
                self.setStyleSheet("""
                    CandleHoverPopup {
                        background-color: #FFFFFF;
                        border: 1px solid #D0D5DD;
                        border-radius: 6px;
                        color: #12161F;
                        font-family: 'Inter', sans-serif;
                    }
                    QLabel { font-size: 11px; }
                """)
                self.lbl_time.setStyleSheet("color: #667085; font-weight: bold; font-size: 10px; letter-spacing: 0.5px;")
                self.lbl_ohlc.setStyleSheet("color: #12161F; font-weight: 500; font-family: monospace;")
                self.lbl_vol_delta.setStyleSheet("color: #00897B; font-weight: 600; font-family: monospace;")
                self.lbl_poc_imb.setStyleSheet("color: #475467; font-size: 10px;")
                close_color = "#00897B" if bar.close >= bar.open else "#E53935"
                d_color = "#00897B" if bar.delta >= 0 else "#E53935"
            else:
                self.setStyleSheet("""
                    CandleHoverPopup {
                        background-color: #1A1A1D;
                        border: 1px solid #333336;
                        border-radius: 6px;
                        color: #E8E8E8;
                        font-family: 'Inter', sans-serif;
                    }
                    QLabel { font-size: 11px; }
                """)
                self.lbl_time.setStyleSheet("color: #8A8A8A; font-weight: bold; font-size: 10px; letter-spacing: 0.5px;")
                self.lbl_ohlc.setStyleSheet("color: #FFFFFF; font-weight: 500; font-family: monospace;")
                self.lbl_vol_delta.setStyleSheet("color: #00E676; font-weight: 600; font-family: monospace;")
                self.lbl_poc_imb.setStyleSheet("color: #AAAAAA; font-size: 10px;")
                close_color = "#00E676" if bar.close >= bar.open else "#FF1744"
                d_color = "#00E676" if bar.delta >= 0 else "#FF1744"

            dt_str = datetime.datetime.fromtimestamp(bar.start_ts).strftime("%H:%M:%S")
            self.lbl_time.setText(f"BAR INSPECTOR — {dt_str}")

            self.lbl_ohlc.setTextFormat(Qt.TextFormat.RichText)
            self.lbl_ohlc.setText(
                f"O: {bar.open:,.2f}  H: {bar.high:,.2f}  L: {bar.low:,.2f}  "
                f"<span style='color:{close_color}; font-weight:bold;'>C: {bar.close:,.2f}</span>"
            )

            d_prefix = "+" if bar.delta > 0 else ""
            pct = (bar.delta / bar.volume * 100.0) if bar.volume > 0 else 0.0
            
            self.lbl_vol_delta.setTextFormat(Qt.TextFormat.RichText)
            self.lbl_vol_delta.setText(
                f"Vol: {bar.volume:,}  |  "
                f"<span style='color:{d_color}; font-weight:bold;'>Delta: {d_prefix}{bar.delta:,} ({pct:+.1f}%)</span>"
            )

            # POC
            poc_str = "--"
            poc_idx = bar.poc
            if poc_idx is not None and poc_idx in bar.cells:
                poc_price = poc_idx * tick_size
                cell = bar.cells[poc_idx]
                poc_vol = cell[0] + cell[1]
                poc_str = f"{poc_price:,.2f} ({poc_vol:,})"

            # Imbalances
            buy_imb_count = 0
            sell_imb_count = 0
            sorted_ticks = sorted(bar.cells)
            for i, ti in enumerate(sorted_ticks):
                cell = bar.cells[ti]
                if ti - 1 in bar.cells:
                    below_sell = bar.cells[ti - 1][0]
                    if below_sell > 0 and (cell[1] / below_sell) >= 3.0:
                        buy_imb_count += 1
                if ti + 1 in bar.cells:
                    above_buy = bar.cells[ti + 1][1]
                    if above_buy > 0 and (cell[0] / above_buy) >= 3.0:
                        sell_imb_count += 1

            self.lbl_poc_imb.setText(f"POC: {poc_str}  |  Imbalances: {buy_imb_count} Buy / {sell_imb_count} Sell")

            self.adjustSize()
            self.move(global_pos.x() + 15, global_pos.y() + 15)
            self.show()
        except Exception:
            pass
