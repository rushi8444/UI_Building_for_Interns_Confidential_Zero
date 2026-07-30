# Omnitrix Order Flow Terminal — Project Progress Summary & Roadmap

## Overview
**Omnitrix** is a high-performance Python PyQt6 / PyQtGraph order flow terminal featuring real-time market data aggregation, multi-mode order flow footprint visualization, depth-of-market (DOM) bookmap liquidity engine, technical drawing tools, and synthetic spread calculators.

---

## Accomplished Features & Git Commit Reference

### 1. Order Flow Chart Modes & Rendering Refactorings
- **Commits**: `7eef0b6`, `deeabd0`
- **Footprint Mode (Bid x Ask)**: Two-column split layout `[ Bid | Ask ]`, order flow diagonal imbalance detection (emerald green buy / bright red sell highlights), dynamic font scaling, subtle center separator lines, and zero-volume protection (`"-"`).
- **Cluster Mode**: Aggregated volume nodes color-coded by net delta (sage/teal green vs. muted crimson red at 35% opacity), POC Amber Gold highlight, and volume text thresholding (`>= 500`).
- **Profile Mode**: Volume profile per bar with POC Amber Gold fill + 1px gold border and subtle center backbone wick line (`QColor(255, 255, 255, 45)`).
- **Delta Mode**: Dynamic non-linear heatmap opacity scaling (`(abs(d) / max_abs_d) ** 0.75`), micro-delta text filtering (`|Delta| >= 1.0K`), and extra bottom margin padding in `_auto_fit_y()` to prevent candle footer overlap.
- **Synchronized Level-of-Detail (LOD)**: Unified `show_cells = show_text` across Footprint, Cluster, Profile, and Delta modes so background fills and text numbers appear together at the exact same instant when zooming in.
- **Bookmap & Liquidity Heatmap**: Continuous ARGB buffer composition (`SmoothPixmapTransform = True`), non-zero logarithmic percentile scaling `[20, 88]`, smooth dark-mode LUT ramp without white core bands (`Dark Navy -> Ocean Blue -> Cyan -> Yellow -> Orange -> Hot Crimson Red`), split pie trade bubbles (green buy % / red sell %), COB depth ladder with power scaling (0.50), and multi-level S/R wall lines.

### 2. Charting Core & Layout Engine
- **Commit**: `06b81a7` — **Candle Hover Inspector**: Floating `CandleHoverPopup` card anchored to candle body/wick area showing timestamp, OHLC prices, volume, delta %, and POC metrics.
- **Commit**: `81e367c` — **Multi-Chart Grid Layout Engine**: Supports 1x1, 2x1, 1x2, 2x2 grid arrangements with crosshair synchronization and independent symbol/timeframe selections per cell.
- **Commit**: `8518f2e` — **Synthetic Spread & Math Formulas**: Real-time synthetic spread calculation engine supporting user-defined math formulas and ratio charts (e.g. `AAPL/SPY` or `NQ - ES`).
- **Commit**: `de789e0` — **Cumulative Volume Delta (CVD) & Divergences**: Sub-chart CVD indicator with bar-color alignment, divergence signals (bullish/bearish), and toggle controls.
- **Commits**: `b9b1d17`, `ffc50aa` — **Timeframe Aggregation & Tick Bar Engine**: High-frequency timeframes (1s, 5s, 10s, 30s, 1m, 5m, 15m, 1h, 1D) and trade-count tick bars with live active-bar updates.
- **Commit**: `7c91cd2` — **Drawing Tools, Templates & Styling**: Drawing presets menu, right-click styling properties modal, color/opacity customization, and template saving for all overlay tools.
- **Commits**: `a4f2726`, `72fb543` — **Auto-Fit Scaling & Zoom Engine**: Bookmap-style simultaneous X & Y cursor zoom, Y-axis double-click auto-fit scale reset, and price drag scaling.
- **Commit**: `30374ef` — **Full-Screen Immersive Mode**: F11 shortcut and navbar toggle button for full-screen chart analysis.
- **Commits**: `60b705b`, `931aee9` — **Drawing Tools (FRVP, Long/Short, Fib)**: Fixed Range Volume Profile (FRVP) tool with POC and Value Area bounds, Long/Short position risk/reward ratio calculators, and Fibonacci Retracements.

---

## Remaining Features & Chart Modes

The following specialized chart modes and advanced features are remaining for future implementation:

1. **Time Price Opportunity (TPO / Market Profile)**:
   - Period-letter bracket distribution (A, B, C... time brackets), Initial Balance (IB) range, Value Area High/Low (VAH/VAL), and TPO POC.
2. **Advanced Bookmap Modes**:
   - Historical depth heatmap replay buffer, order book iceberg detection, and large stop-run indicators.
3. **Combined Heatmap + Footprint Mode**:
   - Dual-layer composition rendering the depth liquidity heatmap background directly beneath bid/ask footprint cell numbers in a single unified view.
4. **Additional Advanced Order Flow Features**:
   - Volume Imbalance Footprint overlays, Delta Profile Mode, and Trade Cluster Bubbles embedded inside footprint cells.
