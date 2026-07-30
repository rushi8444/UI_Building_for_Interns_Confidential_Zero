# 🚀 Omnitrix Order Flow Terminal — Feature Roadmap & Implementation Guide

This document is a comprehensive TODO list and technical specification for implementing the **13 TradingView-inspired features** requested for the Omnitrix PyQt6 / PyQtGraph terminal. For each feature, this guide explains **what it does** for a trader and **how to technically implement it** within our existing architecture.

---

## 📊 Summary Check & Progress Tracker

- [x] **1. Multi-Chart Layouts** (Split-screen 2x1, 1x2, 2x2 grids)
- [x] **2. Custom Timeframes** (Arbitrary minute/hour bar aggregations)
- [x] **3. Crosshair Synchronization** (Sync cursor across all open charts & timeframes)
- [x] **4. Auto-Fit Scale** (Dynamic Y-axis price auto-scaling & reset)
- [x] **5. Full-Screen Mode** (F11 / Immersive chart maximize)
- [x] **6. Data Window** (Hover inspector for OHLC, Delta, POC, Imbalances)
- [x] **7. Long & Short Position Calculators** (Risk/Reward drawing tool)
- [x] **8. Drawing Templates** (Save & apply custom styles/colors to drawings)
- [x] **9. Second & Tick-Based Intervals** (High-frequency sub-minute & trade-count bars)
- [x] **10. Custom Spread Charts (Math Formulas)** (Synthetic ratio & difference charts e.g. `AAPL/SPY`)NEEDS TESTING 
- [ ] **11. Time Price Opportunity (TPO / Market Profile)** (Letter/period bracket charts)
- [x] **12. Fixed Range Volume Profile (FRVP)** (TradingView-style custom range volume tool)
- [x] **13. Cumulative Volume Delta (CVD) Enhancements** (CVD divergence, bar-color CVD, and sub-chart sync)

---

## 1. Multi-Chart Layouts
### 💡 What It Actually Does
Allows the trader to view multiple symbols or multiple timeframes of the same symbol simultaneously on a single screen (e.g., **2x2 Grid**, **Horizontal Split**, **Vertical Split**, or **3-Chart Layout**).

### 🛠️ How to Add It to Omnitrix
- **UI Component (`omnitrix/ui/main_window.py`)**:
  - Replace the single central widget layout with nested PyQt6 `QSplitter(Qt.Orientation.Horizontal)` and `QSplitter(Qt.Orientation.Vertical)` widgets.
  - Create a `ChartContainer` class that wraps a `FootprintWidget` + header toolbar.
  - Provide layout selector icons in the main navbar (`[ 1 ]`, `[ 1x2 ]`, `[ 2x1 ]`, `[ 2x2 ]`).
- **Data & Feed Routing (`omnitrix/engine/feed.py`)**:
  - Support multiple active subscriptions in `FeedManager`.
  - Route incoming tick/bar events to the specific `FootprintWidget` instance subscribed to that instrument/timeframe.

---

## 2. Custom Timeframes
### 💡 What It Actually Does
Goes beyond standard presets (1m, 5m, 15m) to let traders input **any arbitrary time interval** (e.g., **3m**, **7m**, **45m**, **2h**, **4h**).

### 🛠️ How to Add It to Omnitrix
- **Aggregation Engine (`omnitrix/engine/bars.py`)**:
  - Enhance `BarBuilder` to accept a custom `interval_seconds` integer parameter.
  - Implement a bucket-rounding rule: `bucket_timestamp = (timestamp // interval_seconds) * interval_seconds`.
- **Navbar Input (`omnitrix/ui/main_window.py`)**:
  - Add a custom timeframe modal/dialog where users type `3m`, `45m`, or `2h`.
  - Parse the string using regex (`(\d+)([smhd])`) into seconds and re-initialize `BarBuilder`.

---

## 3. Crosshair Synchronization
### 💡 What It Actually Does
When hovering over a bar on one chart, the vertical crosshair line and price/time markers **automatically move in sync across all other open charts** (even across different timeframes or secondary windows like Analytics and Bookmap).

### 🛠️ How to Add It to Omnitrix
- **Signal Bus (`omnitrix/ui/signals_panel.py` or new `omnitrix/ui/sync_bus.py`)**:
  - Define a Qt Signal: `crosshairMoved = pyqtSignal(float, float)` passing `(timestamp, price)`.
- **Plotting Integration (`omnitrix/render/footprint.py`)**:
  - In `scene().sigMouseMoved`, emit `crosshairMoved` with the mouse event’s X (time) coordinate.
  - In all peer chart widgets, connect `crosshairMoved` to a slot `on_peer_crosshair(timestamp)` that updates a dedicated `pg.InfiniteLine(pos=timestamp, angle=90)` without moving the local mouse.

---

## 4. Auto-Fit Scale
### 💡 What It Actually Does
Automatically scales and centers the Y-axis (price range) so that all candles/footprint bars currently visible in the horizontal time window fit perfectly on screen without clipping. Includes a double-click or button shortcut to "Reset Scale".

### 🛠️ How to Add It to Omnitrix
- **PyQtGraph ViewBox Controls (`omnitrix/render/footprint.py`)**:
  - Connect the X-axis range change signal: `self.plot_item.sigXRangeChanged.connect(self._auto_fit_y_axis)`.
- **Scaling Math**:
  - Determine visible bar index range `[min_x, max_x]`.
  - Slice the visible bars array to find `max_price = max(bar.high)` and `min_price = min(bar.low)`.
  - Call `self.plot_item.setYRange(min_price - padding, max_price + padding, padding=0)`.
  - Add a `"Fit"` toggle button in the bottom-right corner of the chart.

---

## 5. Full-Screen Mode
### 💡 What It Actually Does
Maximizes the chart area to fill the entire monitor, hiding Windows title bars, menus, and side docks for distraction-free order flow analysis. Pressing `F11` or `Esc` restores normal windowed mode.

### 🛠️ How to Add It to Omnitrix
- **Window Management (`omnitrix/ui/main_window.py`)**:
  - Override `keyPressEvent(self, event)` to listen for `Qt.Key.Key_F11` and `Qt.Key.Key_Escape`.
  - When triggered:
    ```python
    if self.isFullScreen():
        self.showNormal()
        self.menuBar().show()
    else:
        self.showFullScreen()
        self.menuBar().hide()
    ```
- **UI Button**: Add a full-screen expand icon (`open_in_full`) to the top-right toolbar.

---

## 6. Data Window (Hover Inspector)
### 💡 What It Actually Does
A floating or dockable inspection panel that displays exact numerical data for whichever candle the mouse is currently hovering over: **Date/Time, Open, High, Low, Close, Volume, Buy Vol, Sell Vol, Delta, Cumulative Delta, POC Price, and Imbalance Count**.

### 🛠️ How to Add It to Omnitrix
- **UI Dock (`omnitrix/ui/data_window.py` - NEW)**:
  - Create a `QDockWidget` featuring a sleek two-column `QTableWidget` or formatted `QLabel` grid.
- **Event Hook (`omnitrix/render/footprint.py`)**:
  - On mouse hover over a bar index `i`, retrieve `bar = self.bars[i]`.
  - Emit `barHovered(bar_metadata_dict)` to update the Data Window UI instantly with formatted currency, volume, and percentage values.

---

## 7. Long & Short Position Calculators
### 💡 What It Actually Does
An interactive TradingView-style Risk/Reward drawing tool. The user clicks an **Entry Price**, drags up to set a **Take Profit (Target)**, and drags down to set a **Stop Loss**. The tool calculates and renders:
- **Risk/Reward Ratio** (e.g., `2.50 : 1`).
- **Profit / Loss Amount** ($ and ticks).
- **Position Size Calculator** based on account risk percentage.

### 🛠️ How to Add It to Omnitrix
- **Drawing Item (`omnitrix/render/drawings.py`)**:
  - Create `PositionCalculatorItem(pg.GraphicsObject)`.
  - Stores three price levels: `entry_price`, `target_price`, `stop_price`.
  - In `paint(self, p, option, widget)`:
    - Draw a **semi-transparent green box** from Entry to Target (`#388E3C`, alpha `45`).
    - Draw a **semi-transparent red box** from Entry to Stop (`#D32F2F`, alpha `45`).
    - Render centered text badges showing `R:R = (Target - Entry) / (Entry - Stop)` and estimated P&L.
- **Interactive Handles**: Use PyQtGraph `LineSegmentROI` or draggable circles at the top/bottom edges to resize Target and Stop levels dynamically.

---

## 8. Drawing Templates
### 💡 What It Actually Does
Allows traders to save custom styling presets for any drawing tool (Lines, Fibonacci, Rectangles, Position Calculators) and apply them instantly in the future (e.g., saving a template named `"Major Weekly Support"` with thick gold dashed lines).

### 🛠️ How to Add It to Omnitrix
- **Template Schema (`omnitrix/render/drawings.py`)**:
  - Define a JSON structure for drawing properties:
    ```json
    {
      "name": "Major Support",
      "tool_type": "HorizontalLine",
      "color": "#C9A227",
      "width": 3,
      "style": "Dashed",
      "show_label": true
    }
    ```
- **Storage & Context Menu**:
  - Store saved templates in `C:\Users\<user>\.gemini\antigravity-ide\omnitrix_templates.json`.
  - Right-clicking any drawing item opens a Qt context menu: `Apply Template -> [User Templates] | Save As Template...`.

---

## 9. Second & Tick-Based Intervals
### 💡 What It Actually Does
- **Second-based charts (e.g., 5s, 10s, 30s)**: High-frequency charts where each candle represents a fixed number of seconds.
- **Tick-based charts (e.g., 100-tick, 500-tick, 1000-tick)**: Time-independent charts where a new candle is created every `N` individual trades, revealing true institutional transaction tempo.

### 🛠️ How to Add It to Omnitrix
- **Tick Bar Engine (`omnitrix/engine/bars.py`)**:
  - Add a `TickBarBuilder` class that tracks trade count (`self.current_tick_count`).
  - When `self.current_tick_count >= target_ticks` (e.g., 500 ticks), emit `sig_bar_closed`, push the completed footprint bar to the renderer, and reset count to 0.
- **Second Bar Engine**:
  - Sub-minute timestamps are supported natively by setting `interval_seconds = 5` or `10` in the `BarBuilder` aggregation logic.

---

## 10. Custom Spread Charts (Math Formulas)
### 💡 What It Actually Does
Allows traders to plot **synthetic instruments** by typing mathematical formulas into the ticker symbol box, such as:
- `AAPL / SPY` (Relative strength ratio chart).
- `BTCUSD - ETHUSD` (Price spread difference).
- `(ES * 50) + (NQ * 20)` (Custom basket value).

### 🛠️ How to Add It to Omnitrix
- **Formula Parser (`omnitrix/engine/spread.py` - NEW)**:
  - Build an AST or safe arithmetic evaluator using Python's `ast` module or `numexpr`.
  - Subscribe `FeedManager` to all constituent symbols in the formula (e.g., both `AAPL` and `SPY`).
- **Bar Alignment & Synthesizer**:
  - Align incoming timestamps across symbols.
  - Calculate `synthetic_open = openA / openB`, `synthetic_close = closeA / closeB`, etc.
  - Feed synthetic bars directly into `FootprintWidget` for standard footprint/candle rendering.

---

## 11. Time Price Opportunity (TPO / Market Profile)
### 💡 What It Actually Does
Presents price distribution by **Time Periods (Letters A, B, C, D...)** rather than volume.
- Each 30-minute block of the trading day is assigned a letter.
- Every price level visited during that 30-minute block gets that letter stacked horizontally.
- Identifies **Value Area (VAH/VAL)**, **Point of Control (POC)**, **Single Prints**, and **Initial Balance (IB)** based on time occupancy.

### 🛠️ How to Add It to Omnitrix
- **TPO Engine (`omnitrix/engine/tpo.py` - NEW)**:
  - Group 30-minute intervals from session open (`09:30 AM = 'A'`, `10:00 AM = 'B'`, etc.).
  - Maintain a dictionary mapping `price_level -> list_of_letters`.
- **TPO Renderer (`omnitrix/render/tpo_item.py` - NEW)**:
  - Subclass `pg.GraphicsObject` to render colored ASCII letters or solid time-bracket blocks per price level.
  - Render a side-by-side **Split TPO** (uncollapsed letters per period) or **Collapsed TPO** (traditional bell-curve letter stack).

---

## 12. Fixed Range Volume Profile (FRVP)
### 💡 What It Actually Does
A custom drawing tool that lets the user click two arbitrary points in time (Start Bar and End Bar) on the chart. The terminal dynamically calculates and renders a **horizontal Volume Profile histogram** specifically for that selected range, highlighting the **Range POC**, **VAH**, and **VAL**.

### 🛠️ How to Add It to Omnitrix
- **FRVP Tool (`omnitrix/render/profile.py` & `omnitrix/render/drawings.py`)**:
  - Use `pg.LinearRegionItem` (vertical draggable boundaries) or a two-point click bounding box.
- **Range Aggregation Math**:
  - Slice `self.bars[start_idx : end_idx + 1]`.
  - Aggregate total bid volume and ask volume at every tick price level across only that slice.
  - Calculate Value Area (70% volume threshold) and POC for the subset.
- **On-Chart Histogram Painting**:
  - Paint horizontal bars (`#388E3C` / `#D32F2F`) anchored to the start or end of the selected zone, with a prominent gold `#C9A227` line extending from the Range POC.

---

## 13. Cumulative Volume Delta (CVD) Enhancements
### 💡 What It Actually Does
While basic CVD plots already exist in our Analytics window, this enhancement brings professional TradingView/Bookmap CVD capabilities:
- **Bar-Color CVD**: Coloring price candles or footprint totals based on whether CVD is making new session highs/lows.
- **CVD Divergence Indicators**: Highlighting when Price makes a Higher High but CVD makes a Lower High (Bearish Absorption / Divergence).
- **Sub-Chart Pane**: Adding a synchronized bottom indicator sub-chart pane directly inside `main_window.py` below the main footprint chart.

### 🛠️ How to Add It to Omnitrix
- **Sub-Chart Layout (`omnitrix/ui/main_window.py`)**:
  - Add a secondary bottom `pg.PlotWidget` coupled to the main chart's X-axis (`bottom_plot.setXLink(main_plot)`).
- **Divergence Engine (`omnitrix/engine/signals.py`)**:
  - Compare rolling window swing highs in `Price` vs. swing highs in `Cumulative Delta`.
  - When divergence is detected, draw an automatic trendline on both the price chart and CVD pane with a `"DIV"` badge.

---

## 🏁 Recommended Next Implementation Step

To begin executing this roadmap, **Feature #4 (Auto-Fit Scale)** and **Feature #12 (Fixed Range Volume Profile)** are recommended first, as they provide immediate institutional utility and integrate cleanly with our newly harmonized Obsidian Pro Dark theme.
